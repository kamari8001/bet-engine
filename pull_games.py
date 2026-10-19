"""Load this season's upcoming games and new final scores into the live tables.

Usage: python3 pull_games.py nfl | ncaaf | all

- New upcoming games are added to `games`.
- If a kickoff time moved before the game starts, it is updated.
- Games whose kickoff time hasn't been announced yet are skipped until it is.
- Final scores for games already in `games` are added to `results`.
Safe to re-run: nothing is added twice. Prints the next 7 days in Eastern time.
"""

import csv
import io
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import config
import db
from pull_history import CFBD, CURRENT_SEASON, NFLVERSE_GAMES, blank, current_season, fetch


def nfl_games():
    """Yield this season's NFL games from nflverse in a common shape."""
    rows = csv.DictReader(io.StringIO(fetch(NFLVERSE_GAMES).decode()))
    for r in rows:
        if r["season"] != str(CURRENT_SEASON):
            continue
        kickoff = None
        if not blank(r["gametime"]):
            kickoff = datetime.strptime(f"{r['gameday']} {r['gametime']}", "%Y-%m-%d %H:%M") \
                .replace(tzinfo=db.EASTERN)
        done = not blank(r["home_score"]) and not blank(r["away_score"])
        yield dict(external_id=r["game_id"], league="NFL", kickoff=kickoff,
                   espn_id=None if blank(r["espn"]) else r["espn"],
                   home_team=r["home_team"], away_team=r["away_team"],
                   neutral_site=r["location"] == "Neutral", live_eligible=True,
                   home_score=int(r["home_score"]) if done else None,
                   away_score=int(r["away_score"]) if done else None)


def ncaaf_games():
    """Yield this season's college games from CFBD in a common shape."""
    if not config.CFBD_API_KEY:
        raise RuntimeError("CFBD_API_KEY is empty in .env")
    headers = {"Authorization": f"Bearer {config.CFBD_API_KEY}"}
    games = json.loads(fetch(f"{CFBD}/games?year={CURRENT_SEASON}&seasonType=both", headers))
    for g in games:
        kickoff = None
        if not g.get("startTimeTBD"):
            kickoff = datetime.strptime(g["startDate"][:19], "%Y-%m-%dT%H:%M:%S") \
                .replace(tzinfo=timezone.utc)
        done = g.get("completed") and g.get("homePoints") is not None
        yield dict(external_id=str(g["id"]), league="NCAAF", kickoff=kickoff, espn_id=str(g["id"]),
                   home_team=g["homeTeam"], away_team=g["awayTeam"],
                   neutral_site=bool(g.get("neutralSite")),
                   # live betting table: only games between two top-division teams
                   live_eligible=g.get("homeClassification") == "fbs"
                   and g.get("awayClassification") == "fbs",
                   home_score=g["homePoints"] if done else None,
                   away_score=g["awayPoints"] if done else None)


def nba_games():
    """NBA games from ESPN's scoreboard, 3 days back (for results) through 7 days ahead."""
    from pull_basketball_history import ESPN_DAY, NBA_TEAMS, NBA_TYPES, espn_get
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date()
    for offset in range(-3, 8):
        d = today + timedelta(days=offset)
        data = espn_get(ESPN_DAY.format(d=d.strftime("%Y%m%d"))) or {}
        for e in data.get("events", []):
            if NBA_TYPES.get(e["season"]["type"]) is None:
                continue  # preseason and All-Star
            comp = e["competitions"][0]
            teams = {t["homeAway"]: t for t in comp["competitors"]}
            home, away = teams["home"]["team"]["abbreviation"], teams["away"]["team"]["abbreviation"]
            if {home, away} - NBA_TEAMS:
                continue
            done = e["status"]["type"].get("completed")
            kickoff = datetime.strptime(e["date"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            yield dict(external_id=e["id"], league="NBA", kickoff=kickoff, espn_id=e["id"],
                       home_team=home, away_team=away, neutral_site=bool(comp.get("neutralSite")),
                       live_eligible=True,
                       home_score=int(teams["home"]["score"]) if done else None,
                       away_score=int(teams["away"]["score"]) if done else None)


def ncaab_games():
    """College basketball games from CBBD, 3 days back through 7 days ahead (1 call)."""
    if not config.CFBD_API_KEY:
        raise RuntimeError("CFBD_API_KEY is empty in .env (CBBD uses the same key)")
    from pull_basketball_history import cbbd_get
    headers = {"Authorization": f"Bearer {config.CFBD_API_KEY}"}
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date()
    games = cbbd_get(f"/games?season={current_season('ncaab')}&startDateRange={today - timedelta(days=3)}"
                     f"&endDateRange={today + timedelta(days=7)}", headers)
    for g in games:
        kickoff = None
        if not g.get("startTimeTbd"):
            kickoff = datetime.strptime(g["startDate"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        done = g.get("status") == "final" and g.get("homePoints") is not None
        yield dict(external_id=str(g["id"]), league="NCAAB", kickoff=kickoff,
                   espn_id=str(g["sourceId"]) if g.get("sourceId") else None,
                   home_team=g["homeTeam"], away_team=g["awayTeam"], neutral_site=bool(g.get("neutralSite")),
                   live_eligible=True,
                   home_score=g["homePoints"] if done else None, away_score=g["awayPoints"] if done else None)


SOURCES = {"nfl": ("nflverse", nfl_games), "ncaaf": ("cfbd", ncaaf_games),
           "nba": ("espn", nba_games), "ncaab": ("cbbd", ncaab_games)}


def sync(conn, sport):
    source, loader = SOURCES[sport]
    now = datetime.now(timezone.utc)
    added = moved = results = tbd = 0
    problems, notes = [], []
    for g in loader():
        if not g["live_eligible"]:
            continue
        row = conn.execute("SELECT * FROM games WHERE source = ? AND external_id = ?",
                           (source, g["external_id"])).fetchone()
        label = f"{g['away_team']} at {g['home_team']}"

        if row is None:
            if g["home_score"] is not None:
                continue  # already played before we started tracking it
            if g["kickoff"] is None:
                tbd += 1
                continue
            if g["kickoff"] <= now:
                continue  # in progress; too late to log anything
            gid = db.add_game(conn, sport, g["league"], str(current_season(sport)), g["home_team"],
                              g["away_team"], g["kickoff"], source=source,
                              external_id=g["external_id"], neutral_site=g["neutral_site"])
            conn.execute("UPDATE games SET espn_id = ? WHERE id = ?", (g["espn_id"], gid))
            conn.commit()
            added += 1
            continue

        if g.get("espn_id") and not row["espn_id"]:
            conn.execute("UPDATE games SET espn_id = ? WHERE id = ?", (g["espn_id"], row["id"]))
            conn.commit()
        if (row["home_team"], row["away_team"]) != (g["home_team"], g["away_team"]):
            problems.append(f"{label}: teams differ from what we stored "
                            f"({row['away_team']} at {row['home_team']}); not changed")
            continue

        if g["kickoff"] is not None and db.to_utc(g["kickoff"]) != row["start_time_utc"] \
                and g["home_score"] is None:
            old_start = datetime.strptime(row["start_time_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if old_start <= now and g["kickoff"] <= now:
                # Already underway by both times: a feed correction, not a postponement. Leave it.
                notes.append(f"{label}: source changed the kickoff of a game already underway; not moved")
                continue
            manual = conn.execute("SELECT 1 FROM schedule_changes WHERE game_id = ? AND source <> ?",
                                  (row["id"], source)).fetchone()
            if manual and db.to_utc(g["kickoff"]) < row["start_time_utc"]:
                # A postponement was recorded by hand; don't let a lagging feed undo it.
                notes.append(f"{label}: feed still shows {db.fmt_et(db.to_utc(g['kickoff']))}; keeping the "
                                f"manually recorded kickoff {db.fmt_et(row['start_time_utc'])}")
                continue
            try:
                db.move_kickoff(conn, row["id"], g["kickoff"], source, "data feed changed the kickoff time")
                moved += 1
                print(f"  kickoff moved: {label} {db.fmt_et(row['start_time_utc'])}"
                      f" -> {db.fmt_et(db.to_utc(g['kickoff']))}")
            except sqlite3.DatabaseError as e:
                problems.append(f"{label}: kickoff change refused ({e})")

        if g["home_score"] is not None and not conn.execute(
                "SELECT 1 FROM results WHERE game_id = ?", (row["id"],)).fetchone():
            db.add_result(conn, row["id"], "final", source,
                          home_score=g["home_score"], away_score=g["away_score"])
            results += 1

    print(f"{sport.upper()}: {added} games added, {moved} kickoff times moved, "
          f"{results} final scores added, {tbd} skipped (kickoff time not announced yet)")
    for n in notes:
        print(f"  NOTE: {n}")
    for p in problems:
        print(f"  PROBLEM: {p}")
    return not problems


def print_slate(conn, sport, days=7):
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " ORDER BY start_time_utc, id",
        (sport, db.to_utc(now), db.to_utc(now + timedelta(days=days)))).fetchall()
    print(f"\n{sport.upper()} games in the next {days} days ({len(rows)}):")
    for r in rows:
        where = " (neutral site)" if r["neutral_site"] else ""
        print(f"  {db.fmt_et(r['start_time_utc']):<24} {r['away_team']} at {r['home_team']}{where}")


def main():
    sports = list(SOURCES) if sys.argv[1:] == ["all"] else sys.argv[1:]
    if not sports or any(s not in SOURCES for s in sports):
        sys.exit(__doc__)
    conn = db.connect()
    ok = True
    for sport in sports:
        ok = sync(conn, sport) and ok
    for sport in sports:
        print_slate(conn, sport)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

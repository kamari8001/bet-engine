"""Record what Claude finds in the news: confirmed starters and capped adjustments.

Usage:
  python3 news.py games nfl|ncaaf
      list upcoming games (next 7 days) with ids and current expected starters
  python3 news.py qb <game id> <team> "<player>" confirmed|expected <source url> "<reason>"
      record a starting QB (NFL). The formula turns it into a probability.
  python3 news.py check <game id> <team> "<player>" <source url> "<reason>"
      record that the news supports the starter the model already assumes
      ("verified": nothing contradicts him). Refused if the name doesn't match;
      record a `qb` fact instead in that case.
  python3 news.py targets ncaaf|ncaab|nba|soccer_club [hours]
      games in the next N hours (default 24) that need a news check and have none recorded:
      college and club soccer games where the engine differs from the market by 4+ points
      (soccer: on any of home/draw/away); every NBA game.
      Biggest disagreements first, at most 15.
  python3 news.py reviewed <game id> <source url> "<reason>"
      record that the news was checked and nothing material changes the game (a
      0-point adjustment). Like a verified QB check, it logs a claude prediction.
  python3 news.py adjust <game id> <home shift in points> <source url> "<reason>"
      a judgment adjustment, e.g. 1.5 moves the home team up 1.5 percentage
      points (away down 1.5). Capped at config.MAX_ADJUSTMENT per game in total.
      Club soccer: the draw chance is left unchanged; the shift moves between home and away.

Then run `python3 predict.py <sport>` to log the claude prediction.
Every entry needs a source link and a reason, and must be made before kickoff.
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import config
import db


def list_games(conn, sport):
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " ORDER BY start_time_utc, id",
        (sport, db.to_utc(now), db.to_utc(now + timedelta(days=7)))).fetchall()
    for g in rows:
        facts = conn.execute("SELECT team, player_name, status FROM lineup_facts WHERE game_id = ?"
                             " ORDER BY created_at", (g["id"],)).fetchall()
        checks = conn.execute("SELECT team, player_name FROM qb_checks WHERE game_id = ? ORDER BY created_at",
                              (g["id"],)).fetchall()
        adj = conn.execute("SELECT d_home FROM adjustments WHERE game_id = ? ORDER BY created_at", (g["id"],)).fetchall()
        known = "; ".join([f"{f['team']} QB {f['player_name']} ({f['status']})" for f in facts]
                          + [f"{c['team']} QB {c['player_name']} (verified)" for c in checks]
                          + [("news reviewed" if a["d_home"] == 0 else f"adjusted home {a['d_home'] * 100:+.1f}")
                             for a in adj])
        print(f"  [{g['id']}] {db.fmt_et(g['start_time_utc']):<24} {g['away_team']} at {g['home_team']}"
              + (f"   recorded: {known}" if known else ""))


def find_player_id(conn, name):
    """nflverse id of a QB who has started before, matched by name; None if never started."""
    r = conn.execute(
        "SELECT id FROM (SELECT home_starter_id AS id, game_date_et FROM hist_games"
        "  WHERE sport = 'nfl' AND home_starter_name = ?"
        " UNION ALL SELECT away_starter_id, game_date_et FROM hist_games"
        "  WHERE sport = 'nfl' AND away_starter_name = ?) ORDER BY game_date_et DESC LIMIT 1",
        (name, name)).fetchone()
    return r[0] if r else None


def record_qb(conn, game_id, team, player, status, url, reason):
    g = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if g is None or g["sport"] != "nfl":
        sys.exit("No NFL game with that id. Use `python3 news.py games nfl`.")
    pid = find_player_id(conn, player)
    db.add_lineup_fact(conn, game_id, team, "QB", player, status, url, reason, player_id=pid)
    print(f"Recorded: {team} QB {player} ({status}) for {g['away_team']} at {g['home_team']}.")
    print(f"  nflverse id {pid}" if pid else
          "  No previous NFL starts found: the model treats him as a first-time starter.")


def assumed_qb(conn, g, team):
    """(name, nflverse id) of the QB the model currently uses for a team in a game."""
    fact = conn.execute("SELECT player_name, player_id FROM lineup_facts WHERE game_id = ? AND team = ?"
                        " ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"], team)).fetchone()
    if fact:
        return fact["player_name"], fact["player_id"]
    eng = conn.execute("SELECT note FROM predictions WHERE game_id = ? AND source = 'engine'"
                       " ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"],)).fetchone()
    if eng is None:
        return None, None
    side = "home" if team == g["home_team"] else "away"
    inputs = json.loads(eng["note"] or "{}").get("inputs", {})
    return inputs.get(f"{side}_starter_name"), inputs.get(f"{side}_starter_id")


def record_check(conn, game_id, team, player, url, reason):
    g = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if g is None or g["sport"] != "nfl":
        sys.exit("No NFL game with that id. Use `python3 news.py games nfl`.")
    if team not in (g["home_team"], g["away_team"]):
        sys.exit(f"{team} isn't in this game ({g['away_team']} at {g['home_team']}).")
    name, pid = assumed_qb(conn, g, team)
    if name is None:
        sys.exit("No engine prediction for that game yet. Run predict.py first.")
    if name.strip().lower() != player.strip().lower():
        sys.exit(f"The model assumes {name} for {team}, not {player}. If {player} is starting, "
                 f"record it with `news.py qb` instead.")
    db.add_qb_check(conn, game_id, team, name, url, reason, player_id=pid)
    print(f"Recorded check: {team} QB {name} verified for {g['away_team']} at {g['home_team']}.")


def news_targets(conn, sport, hours=24, limit=15):
    """Games needing a news check: 4+ point disagreement with the market, not yet reviewed."""
    import statistics
    from datetime import datetime, timedelta, timezone
    from odds_math import no_vig
    now = datetime.now(timezone.utc)
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id)"
        " AND NOT EXISTS (SELECT 1 FROM adjustments a WHERE a.game_id = games.id)",
        (sport, db.to_utc(now), db.to_utc(now + timedelta(hours=hours)))).fetchall()
    out = []
    if sport == "soccer_club":
        from predict_soccer import latest_odds
        for g in games:
            eng = conn.execute("SELECT p_home, p_draw, p_away FROM predictions WHERE game_id = ? AND source = 'engine'"
                               " AND corrects_id IS NULL ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"],)).fetchone()
            mkt = latest_odds(conn, g["id"])
            if not eng or not mkt:
                continue
            gaps = [eng[k] - mkt["p"][i] for i, k in enumerate(("p_home", "p_draw", "p_away"))]
            if max(abs(x) for x in gaps) >= config.EDGE_THRESHOLD:
                out.append((max(abs(x) for x in gaps), g, eng["p_home"], mkt["p_home"]))
        out.sort(key=lambda x: -x[0])
        return out[:limit]
    for g in games:
        eng = conn.execute("SELECT p_home FROM predictions WHERE game_id = ? AND source = 'engine'"
                           " AND corrects_id IS NULL ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"],)).fetchone()
        odds = conn.execute("SELECT home_ml, away_ml FROM odds WHERE game_id = ? AND captured_at ="
                            " (SELECT MAX(captured_at) FROM odds WHERE game_id = ?)", (g["id"], g["id"])).fetchall()
        if not eng or not odds:
            continue
        mkt = statistics.mean(no_vig(o["home_ml"], o["away_ml"])[0] for o in odds)
        gap = eng["p_home"] - mkt
        # NBA: every game needs an injury/rest check; college: only where engine and market disagree
        if sport == "nba" or abs(gap) >= config.EDGE_THRESHOLD:
            out.append((abs(gap), g, eng["p_home"], mkt))
    out.sort(key=lambda x: -x[0])
    return out[:limit]


def record_adjustment(conn, game_id, shift_points, url, reason):
    base = conn.execute("SELECT id FROM predictions WHERE game_id = ? AND source = 'engine'"
                        " ORDER BY created_at DESC, id DESC LIMIT 1", (game_id,)).fetchone()
    if base is None:
        sys.exit("No engine prediction for that game yet. Run predict.py first.")
    d = shift_points / 100
    soccer = conn.execute("SELECT sport FROM games WHERE id = ?", (game_id,)).fetchone()[0] == "soccer_club"
    db.add_adjustment(conn, game_id, base["id"], d_home=d, d_away=-d, d_draw=0.0 if soccer else None,
                      reason=reason, source_url=url)
    used = conn.execute("SELECT SUM(d_home) FROM adjustments WHERE game_id = ?", (game_id,)).fetchone()[0]
    if shift_points == 0:
        print("Recorded review: news checked, nothing material (no change to the probability).")
    else:
        print(f"Recorded: home {shift_points:+.1f} points. Total for this game {used * 100:+.1f} "
              f"(cap {config.MAX_ADJUSTMENT * 100:.0f}).")


def main():
    a = sys.argv[1:]
    conn = db.connect()
    try:
        if len(a) == 2 and a[0] == "games":
            list_games(conn, a[1])
        elif len(a) == 7 and a[0] == "qb" and a[4] in ("confirmed", "expected"):
            record_qb(conn, int(a[1]), a[2], a[3], a[4], a[5], a[6])
        elif len(a) == 6 and a[0] == "check":
            record_check(conn, int(a[1]), a[2], a[3], a[4], a[5])
        elif a[:1] == ["targets"] and len(a) in (2, 3):
            rows = news_targets(conn, a[1], int(a[2]) if len(a) == 3 else 24)
            if not rows:
                print("No games need a news check right now.")
            for gap, g, eng, mkt in rows:
                print(f"  [{g['id']}] {db.fmt_et(g['start_time_utc']):<24} {g['away_team']} at {g['home_team']}: "
                      f"engine {g['home_team']} {eng:.0%} vs market {mkt:.0%} ({gap * 100:.0f} pt gap)")
        elif len(a) == 4 and a[0] == "reviewed":
            record_adjustment(conn, int(a[1]), 0.0, a[2], a[3])
        elif len(a) == 5 and a[0] == "adjust":
            record_adjustment(conn, int(a[1]), float(a[2]), a[3], a[4])
        else:
            sys.exit(__doc__)
    except sqlite3.DatabaseError as e:
        sys.exit(f"Refused by the database: {e}")


if __name__ == "__main__":
    main()

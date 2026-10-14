"""Load past NFL and college football seasons into the backtest tables.

Usage: python3 pull_history.py nfl | ncaaf | all

Safe to re-run: each run replaces that sport's history with a fresh copy.
Only completed games are loaded. If anything fails, nothing is saved.
"""

import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone

import config
import db

NFLVERSE_GAMES = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
CFBD = "https://api.collegefootballdata.com"
CFBD_FIRST_SEASON = 2013
CURRENT_SEASON = 2026


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def blank(value):
    return value is None or value in ("", "NA")


def insert_game(conn, **g):
    cols = ", ".join(g)
    marks = ", ".join("?" for _ in g)
    return conn.execute(f"INSERT INTO hist_games ({cols}) VALUES ({marks})",
                        list(g.values())).lastrowid


def insert_odds(conn, **o):
    cols = ", ".join(o)
    marks = ", ".join("?" for _ in o)
    conn.execute(f"INSERT INTO hist_odds ({cols}) VALUES ({marks})", list(o.values()))


def load_nfl(conn):
    print("Downloading NFL games from nflverse...")
    rows = list(csv.DictReader(io.StringIO(fetch(NFLVERSE_GAMES).decode())))
    for r in rows:
        if blank(r["home_score"]) or blank(r["away_score"]):
            continue  # not played yet
        # nflverse gives kickoff in Eastern time
        kickoff_et = kickoff_utc = None
        if not blank(r["gametime"]):
            et = datetime.strptime(f"{r['gameday']} {r['gametime']}", "%Y-%m-%d %H:%M") \
                .replace(tzinfo=db.EASTERN)
            kickoff_et = et.strftime("%Y-%m-%d %H:%M")
            kickoff_utc = db.to_utc(et)
        game_id = insert_game(
            conn, sport="nfl", season=int(r["season"]), week=int(r["week"]),
            season_type="regular" if r["game_type"] == "REG" else "postseason",
            game_date_et=r["gameday"], kickoff_et=kickoff_et, kickoff_utc=kickoff_utc,
            home_team=r["home_team"], away_team=r["away_team"],
            home_score=int(r["home_score"]), away_score=int(r["away_score"]),
            neutral_site=int(r["location"] == "Neutral"),
            source="nflverse", external_id=r["game_id"])
        has_ml = not blank(r["home_moneyline"]) and not blank(r["away_moneyline"])
        if has_ml or not blank(r["spread_line"]) or not blank(r["total_line"]):
            insert_odds(
                conn, hist_game_id=game_id, provider="nflverse (book not stated)",
                home_ml=int(float(r["home_moneyline"])) if has_ml else None,
                away_ml=int(float(r["away_moneyline"])) if has_ml else None,
                # nflverse spread_line is positive when home is favored; flip to betting convention
                home_spread=-float(r["spread_line"]) if not blank(r["spread_line"]) else None,
                total=float(r["total_line"]) if not blank(r["total_line"]) else None,
                source="nflverse")


def load_ncaaf(conn):
    if not config.CFBD_API_KEY:
        raise RuntimeError("CFBD_API_KEY is empty in .env")
    headers = {"Authorization": f"Bearer {config.CFBD_API_KEY}"}
    for year in range(CFBD_FIRST_SEASON, CURRENT_SEASON + 1):
        print(f"Downloading college {year} from CFBD...")
        games = json.loads(fetch(f"{CFBD}/games?year={year}&seasonType=both", headers))
        lines = json.loads(fetch(f"{CFBD}/lines?year={year}&seasonType=both", headers))
        lines_by_game = {g["id"]: g["lines"] for g in lines}
        for g in games:
            if not g.get("completed") or g.get("homePoints") is None or g.get("awayPoints") is None:
                continue
            if "fbs" not in (g.get("homeClassification"), g.get("awayClassification")):
                continue  # games between lower divisions don't matter for us
            start = datetime.strptime(g["startDate"][:19], "%Y-%m-%dT%H:%M:%S") \
                .replace(tzinfo=timezone.utc)
            et = start.astimezone(db.EASTERN)
            time_known = not g.get("startTimeTBD")
            game_id = insert_game(
                conn, sport="ncaaf", season=g["season"], week=g.get("week"),
                season_type="regular" if g["seasonType"] == "regular" else "postseason",
                game_date_et=et.strftime("%Y-%m-%d"),
                kickoff_et=et.strftime("%Y-%m-%d %H:%M") if time_known else None,
                kickoff_utc=db.to_utc(start) if time_known else None,
                home_team=g["homeTeam"], away_team=g["awayTeam"],
                home_division=g.get("homeClassification"),
                away_division=g.get("awayClassification"),
                home_score=g["homePoints"], away_score=g["awayPoints"],
                neutral_site=int(bool(g.get("neutralSite"))),
                source="cfbd", external_id=str(g["id"]))
            for line in lines_by_game.get(g["id"], []):
                has_ml = line.get("homeMoneyline") is not None and line.get("awayMoneyline") is not None
                if not has_ml and line.get("spread") is None and line.get("overUnder") is None:
                    continue
                insert_odds(
                    conn, hist_game_id=game_id, provider=line["provider"],
                    home_ml=int(line["homeMoneyline"]) if has_ml else None,
                    away_ml=int(line["awayMoneyline"]) if has_ml else None,
                    home_spread=line.get("spread"), total=line.get("overUnder"),
                    source="cfbd")


def summarize(conn, sport):
    print(f"\n{sport.upper()} history now in the database:")
    print("season   games   with moneyline   with spread")
    for r in conn.execute("""
        SELECT g.season, COUNT(*) AS games,
               SUM(EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id
                           AND o.home_ml IS NOT NULL)) AS ml,
               SUM(EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id
                           AND o.home_spread IS NOT NULL)) AS spread
        FROM hist_games g WHERE g.sport = ? GROUP BY g.season ORDER BY g.season""", (sport,)):
        print(f"{r['season']}   {r['games']:6d}   {r['ml']:14d}   {r['spread']:11d}")


LOADERS = {"nfl": load_nfl, "ncaaf": load_ncaaf}


def main():
    sports = list(LOADERS) if sys.argv[1:] == ["all"] else sys.argv[1:]
    if not sports or any(s not in LOADERS for s in sports):
        sys.exit(__doc__)
    conn = db.connect()
    db.upgrade_db(conn)
    for sport in sports:
        try:
            conn.execute("BEGIN")
            conn.execute("DELETE FROM hist_games WHERE sport = ?", (sport,))
            LOADERS[sport](conn)
            conn.commit()
        except Exception as e:
            conn.rollback()
            sys.exit(f"\nFAILED loading {sport}: {e}\nNothing was saved for {sport}.")
        summarize(conn, sport)


if __name__ == "__main__":
    main()

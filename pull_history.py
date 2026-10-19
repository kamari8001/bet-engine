"""Load past NFL and college football seasons into the backtest tables.

Usage: python3 pull_history.py nfl | ncaaf | all  [--current]

Safe to re-run: each run replaces that sport's history with a fresh copy.
--current refreshes only this season (fast, few API calls); use it before predicting.
Only completed games are loaded. If anything fails, nothing is saved.
"""

import csv
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import config
import db

NFLVERSE_GAMES = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
NFLVERSE_TEAM_WEEK = ("https://github.com/nflverse/nflverse-data/releases/download/"
                      "stats_team/stats_team_week_{season}.csv")
# The team stats files use today's abbreviations for franchises that moved.
NFL_FRANCHISE = {"SD": "LAC", "OAK": "LV", "STL": "LA"}
CFBD = "https://api.collegefootballdata.com"
CFBD_FIRST_SEASON = 2013
CURRENT_SEASON = 2026   # football (seasons are labeled by the year they start)
# Basketball seasons are labeled by the year they end (2027 = the 2026-27 season), like the sources.
SEASONS = {"nfl": 2026, "ncaaf": 2026, "nba": 2027, "ncaab": 2027}


SPORT_NAMES = {"nfl": "NFL", "ncaaf": "College football", "nba": "NBA", "ncaab": "College basketball"}
SHORT_NAMES = {"nfl": "NFL", "ncaaf": "NCAAF", "nba": "NBA", "ncaab": "NCAAM"}


def current_season(sport):
    return SEASONS[sport]


def season_label(sport, season):
    """2026 for football; '2026-27' for a basketball season ending in 2027."""
    return f"{season - 1}-{str(season)[2:]}" if sport in ("nba", "ncaab") else str(season)


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


def nfl_team_efficiency(seasons):
    """{(game_id, team): (offense EPA, offensive plays)} from nflverse weekly team stats."""
    out = {}
    for season in seasons:
        try:
            raw = fetch(NFLVERSE_TEAM_WEEK.format(season=season)).decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"team stats for {season} unavailable (HTTP {e.code})")
        for r in csv.DictReader(io.StringIO(raw)):
            num = lambda k: float(r[k]) if not blank(r[k]) else 0.0
            epa = num("passing_epa") + num("rushing_epa")
            plays = int(num("attempts") + num("sacks_suffered") + num("carries"))
            out[(r["game_id"], r["team"])] = (epa, plays)
    return out


def load_nfl(conn, only_season=None):
    print("Downloading NFL games from nflverse...")
    rows = list(csv.DictReader(io.StringIO(fetch(NFLVERSE_GAMES).decode())))
    if only_season:
        rows = [r for r in rows if int(r["season"]) == only_season]
    seasons = sorted({int(r["season"]) for r in rows if not blank(r["home_score"])})
    print(f"Downloading NFL weekly team stats {seasons[0]}-{seasons[-1]}...")
    eff = nfl_team_efficiency(seasons)
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
        home_eff = eff.get((r["game_id"], NFL_FRANCHISE.get(r["home_team"], r["home_team"])))
        away_eff = eff.get((r["game_id"], NFL_FRANCHISE.get(r["away_team"], r["away_team"])))
        game_id = insert_game(
            conn, sport="nfl", season=int(r["season"]), week=int(r["week"]),
            season_type="regular" if r["game_type"] == "REG" else "postseason",
            game_date_et=r["gameday"], kickoff_et=kickoff_et, kickoff_utc=kickoff_utc,
            home_team=r["home_team"], away_team=r["away_team"],
            home_score=int(r["home_score"]), away_score=int(r["away_score"]),
            neutral_site=int(r["location"] == "Neutral"),
            home_starter_id=None if blank(r["home_qb_id"]) else r["home_qb_id"],
            home_starter_name=None if blank(r["home_qb_name"]) else r["home_qb_name"],
            away_starter_id=None if blank(r["away_qb_id"]) else r["away_qb_id"],
            away_starter_name=None if blank(r["away_qb_name"]) else r["away_qb_name"],
            home_rest_days=None if blank(r["home_rest"]) else int(r["home_rest"]),
            away_rest_days=None if blank(r["away_rest"]) else int(r["away_rest"]),
            home_coach=None if blank(r["home_coach"]) else r["home_coach"],
            away_coach=None if blank(r["away_coach"]) else r["away_coach"],
            home_off_epa=home_eff[0] if home_eff else None,
            home_off_plays=home_eff[1] if home_eff else None,
            away_off_epa=away_eff[0] if away_eff else None,
            away_off_plays=away_eff[1] if away_eff else None,
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


def load_ncaaf(conn, only_season=None):
    if not config.CFBD_API_KEY:
        raise RuntimeError("CFBD_API_KEY is empty in .env")
    headers = {"Authorization": f"Bearer {config.CFBD_API_KEY}"}
    for year in [only_season] if only_season else range(CFBD_FIRST_SEASON, CURRENT_SEASON + 1):
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
                home_pub_elo=g.get("homePregameElo"), away_pub_elo=g.get("awayPregameElo"),
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


def load_ncaaf_team_seasons(conn, only_season=None):
    """Talent, returning production, and last season's SP+ for every team-season."""
    headers = {"Authorization": f"Bearer {config.CFBD_API_KEY}"}
    years = [only_season] if only_season else list(range(CFBD_FIRST_SEASON, CURRENT_SEASON + 1))
    conn.execute(f"DELETE FROM hist_team_season WHERE sport = 'ncaaf' AND season IN ({','.join('?' * len(years))})", years)
    for year in years:
        print(f"Downloading college {year} preseason team data from CFBD...")
        teams = {}
        for t in json.loads(fetch(f"{CFBD}/talent?year={year}", headers)):
            teams.setdefault(t["team"], {})["talent"] = float(t["talent"])
        for t in json.loads(fetch(f"{CFBD}/player/returning?year={year}", headers)):
            if t.get("percentPPA") is not None:
                teams.setdefault(t["team"], {})["returning_pct"] = t["percentPPA"]
        for t in json.loads(fetch(f"{CFBD}/ratings/sp?year={year - 1}", headers)):
            if t.get("team") and t.get("rating") is not None and t["team"] != "nationalAverages":
                teams.setdefault(t["team"], {})["prev_sp"] = t["rating"]
        for team, v in teams.items():
            conn.execute(
                "INSERT INTO hist_team_season (sport, season, team, talent, returning_pct, prev_sp, source)"
                " VALUES ('ncaaf', ?, ?, ?, ?, ?, 'cfbd')",
                (year, team, v.get("talent"), v.get("returning_pct"), v.get("prev_sp")))


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
    args = [a for a in sys.argv[1:] if a != "--current"]
    only = CURRENT_SEASON if "--current" in sys.argv[1:] else None
    sports = list(LOADERS) if args == ["all"] else args
    if not sports or any(s not in LOADERS for s in sports):
        sys.exit(__doc__)
    conn = db.connect()
    db.upgrade_db(conn)
    for sport in sports:
        try:
            conn.execute("BEGIN")
            if only:
                conn.execute("DELETE FROM hist_games WHERE sport = ? AND season = ?", (sport, only))
            else:
                conn.execute("DELETE FROM hist_games WHERE sport = ?", (sport,))
            LOADERS[sport](conn, only)
            if sport == "ncaaf":
                load_ncaaf_team_seasons(conn, only)
            conn.commit()
        except Exception as e:
            conn.rollback()
            sys.exit(f"\nFAILED loading {sport}: {e}\nNothing was saved for {sport}.")
        summarize(conn, sport)


if __name__ == "__main__":
    main()

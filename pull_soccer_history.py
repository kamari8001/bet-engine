"""Load past club soccer seasons into the backtest tables.

Usage:
  python3 pull_soccer_history.py past                 2005-06 to 2025-26 from football-data.co.uk
                                                      (Big 5 leagues + their second divisions)
  python3 pull_soccer_history.py current [--from YYYY-MM-DD]
                                                      this season's finished Big 5 games from ESPN
                                                      (last 4 days; --from to backfill; daily)
  python3 pull_soccer_history.py summary              what's loaded, per league and season

Seasons are labeled by the year they end (2026 = 2025-26), like basketball.
football-data files are cached in cache/football_data/ (re-downloaded only with --refresh).
Their kickoff times are UK time. Odds there are decimal; they're stored as American
moneylines with timing "pre-close" (collected a day or two before the games) or "close".
Past seasons come from football-data; the current season comes from ESPN, which updates
daily (football-data only about twice a week). Nothing is ever deleted: re-running skips
games already loaded. An unknown team name stops the run instead of guessing.
"""

import csv
import io
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import db
from odds_math import american_from_decimal
from pull_basketball_history import espn_get
from pull_history import current_season, insert_game, insert_odds
from teams import SOCCER_BY_ESPN_ID, SOCCER_LEAGUES

FD_URL = "https://football-data.co.uk/mmz4281/{code}/{div}.csv"
CACHE = Path(__file__).parent / "cache" / "football_data"
PAST_SEASONS = range(2006, 2027)          # 2005-06 through 2025-26
SECOND_DIVISIONS = {"E1": "Championship", "SP2": "La Liga 2", "D2": "2. Bundesliga",
                    "I2": "Serie B", "F2": "Ligue 2"}
UK = ZoneInfo("Europe/London")
ESPN_DAY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={d}"
PAUSE = 0.12
SOURCE = "espn_soccer"                  # live games and this season's history (ESPN ids)
# (provider, timing, home/draw/away columns), first column set present wins per provider
ODDS_COLUMNS = [
    ("Bet365", "pre-close", [("B365H", "B365D", "B365A")]),
    ("Bet365 (close)", "close", [("B365CH", "B365CD", "B365CA")]),
    ("Pinnacle", "pre-close", [("PSH", "PSD", "PSA")]),
    ("Pinnacle (close)", "close", [("PSCH", "PSCD", "PSCA")]),
    ("Market average", "pre-close", [("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA")]),
    ("Market average (close)", "close", [("AvgCH", "AvgCD", "AvgCA")]),
]


def season_code(season):
    """2026 -> '2526' (football-data's folder name)."""
    return f"{(season - 1) % 100:02d}{season % 100:02d}"


def divisions():
    """{football-data division code: league name} for all ten divisions."""
    out = {fd: name for name, (fd, _, _, _) in SOCCER_LEAGUES.items()}
    out.update(SECOND_DIVISIONS)
    return out


def fd_file(div, season, refresh=False):
    path = CACHE / f"{div}_{season_code(season)}.csv"
    if refresh or not path.exists() or path.stat().st_size == 0:
        CACHE.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(FD_URL.format(code=season_code(season), div=div),
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_bytes(r.read())
        time.sleep(0.3)
    raw = path.read_bytes().decode("latin-1").lstrip("﻿").lstrip("ï»¿")
    if not raw.startswith("Div"):
        raise RuntimeError(f"{path.name} isn't a football-data CSV file; delete it and re-run")
    return [r for r in csv.DictReader(io.StringIO(raw)) if r.get("HomeTeam") and r.get("FTHG")]


def num(r, key, kind=float):
    v = (r.get(key) or "").strip()
    try:
        return kind(v) if v else None
    except ValueError:
        return None


def past(conn, refresh=False):
    added = odds_rows = 0
    for season in PAST_SEASONS:
        season_added = 0
        for div, league in divisions().items():
            for r in fd_file(div, season, refresh):
                d = datetime.strptime(r["Date"], "%d/%m/%Y" if len(r["Date"]) == 10 else "%d/%m/%y").date()
                kickoff = None
                if (r.get("Time") or "").strip():
                    hh, mm = map(int, r["Time"].strip().split(":"))
                    kickoff = datetime(d.year, d.month, d.day, hh, mm, tzinfo=UK)
                et = kickoff.astimezone(db.EASTERN) if kickoff else None
                ext = f"{div}-{d.isoformat()}-{r['HomeTeam']}-{r['AwayTeam']}"
                try:
                    gid = insert_game(conn, sport="soccer_club", league=league, season=season, week=None,
                                      season_type="regular",
                                      game_date_et=et.strftime("%Y-%m-%d") if et else d.isoformat(),
                                      kickoff_et=et.strftime("%Y-%m-%d %H:%M") if et else None,
                                      kickoff_utc=db.to_utc(kickoff) if kickoff else None,
                                      home_team=r["HomeTeam"].strip(), away_team=r["AwayTeam"].strip(),
                                      home_score=int(r["FTHG"]), away_score=int(r["FTAG"]),
                                      home_shots_ot=num(r, "HST", int), away_shots_ot=num(r, "AST", int),
                                      home_xg=num(r, "HxG"), away_xg=num(r, "AxG"),
                                      neutral_site=0, source="football-data", external_id=ext)
                except Exception as err:
                    if "UNIQUE" not in str(err):
                        raise
                    continue  # already loaded
                added += 1
                season_added += 1
                for provider, timing, options in ODDS_COLUMNS:
                    for cols in options:
                        h, dr, a = (american_from_decimal(num(r, c)) for c in cols)
                        if None not in (h, dr, a):
                            insert_odds(conn, hist_game_id=gid, provider=provider, timing=timing,
                                        home_ml=h, draw_ml=dr, away_ml=a, source="football-data")
                            odds_rows += 1
                            break
        conn.commit()
        print(f"  {season - 1}-{season % 100:02d}: {season_added} games added", flush=True)
    print(f"Past seasons: {added} games and {odds_rows} odds rows added.")


def current(conn, start=None):
    """This season's finished Big 5 league games from ESPN, day by day."""
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date()
    d = start or today - timedelta(days=4)
    season = current_season("soccer_club")
    added, unknown = 0, set()
    while d <= today:
        for league, (_, _, slug, _) in SOCCER_LEAGUES.items():
            data = espn_get(ESPN_DAY.format(slug=slug, d=d.strftime("%Y%m%d"))) or {}
            for e in data.get("events", []):
                if not e["status"]["type"].get("completed"):
                    continue
                comp = e["competitions"][0]
                teams = {t["homeAway"]: t for t in comp["competitors"]}
                names = {}
                for side in ("home", "away"):
                    hit = SOCCER_BY_ESPN_ID.get(teams[side]["team"]["id"])
                    if hit is None:
                        unknown.add(f"{teams[side]['team']['displayName']} (ESPN id {teams[side]['team']['id']}, {league})")
                    else:
                        names[side] = hit[1]
                if len(names) < 2:
                    continue
                kickoff = datetime.strptime(e["date"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
                et = kickoff.astimezone(db.EASTERN)
                try:
                    insert_game(conn, sport="soccer_club", league=league, season=season, week=None,
                                season_type="regular", game_date_et=et.strftime("%Y-%m-%d"),
                                kickoff_et=et.strftime("%Y-%m-%d %H:%M"), kickoff_utc=db.to_utc(kickoff),
                                home_team=names["home"], away_team=names["away"],
                                home_score=int(teams["home"]["score"]), away_score=int(teams["away"]["score"]),
                                neutral_site=int(bool(comp.get("neutralSite"))), source=SOURCE,
                                external_id=e["id"])
                    added += 1
                except Exception as err:
                    if "UNIQUE" not in str(err):
                        raise
            time.sleep(PAUSE)
        conn.commit()
        d += timedelta(days=1)
    print(f"Club soccer (this season, from ESPN): {added} new finished games.")
    for name in sorted(unknown):
        print(f"  NOTE: unknown team {name}, its games not loaded: add it to SOCCER_TEAMS in teams.py "
              "(checked against all three sources). Predictions skip its games until then.")


def summary(conn):
    rows = conn.execute(
        "SELECT g.league, g.season, COUNT(*) n,"
        " SUM(EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id AND o.timing = 'pre-close')) pre,"
        " SUM(EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id AND o.timing = 'close')) close,"
        " SUM(EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id AND o.provider = 'Pinnacle (close)')) pin,"
        " SUM(g.home_shots_ot IS NOT NULL) sot, SUM(g.kickoff_utc IS NOT NULL) timed"
        " FROM hist_games g WHERE g.sport = 'soccer_club' GROUP BY g.league, g.season ORDER BY g.league, g.season"
    ).fetchall()
    print(f"{'league':<14}{'season':>8}{'games':>7}{'pre-close odds':>16}{'closing':>9}{'Pinnacle close':>16}"
          f"{'shots on tgt':>14}{'kickoff time':>14}")
    for r in rows:
        print(f"{r['league']:<14}{r['season'] - 1}-{r['season'] % 100:02d}{r['n']:>7}{r['pre']:>16}{r['close']:>9}"
              f"{r['pin']:>16}{r['sot']:>14}{r['timed']:>14}")
    total = conn.execute("SELECT COUNT(*) FROM hist_games WHERE sport = 'soccer_club'").fetchone()[0]
    print(f"Total: {total} games.")


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("past", "current", "summary"):
        sys.exit(__doc__)
    conn = db.connect()
    db.upgrade_db(conn)
    if args[0] == "past":
        past(conn, refresh="--refresh" in args)
    elif args[0] == "current":
        start = date.fromisoformat(args[args.index("--from") + 1]) if "--from" in args else None
        current(conn, start)
    else:
        summary(conn)


if __name__ == "__main__":
    main()

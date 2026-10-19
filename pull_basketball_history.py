"""Load past NBA and college basketball seasons into the backtest tables.

Usage:
  python3 pull_basketball_history.py ncaab            college: games + lines from CBBD (about 150 calls)
  python3 pull_basketball_history.py nba games        NBA scores from ESPN, one request per day (resumable)
  python3 pull_basketball_history.py nba odds         NBA moneylines from ESPN, one request per game (resumable)
  python3 pull_basketball_history.py summary          what's loaded so far

Seasons are labeled by the year they end (2025 = the 2024-25 season), like the sources.
NBA loading never deletes anything: re-running skips what's already loaded, so it can be
stopped and resumed. If ESPN keeps refusing requests, it stops and says so (no gap-filling).
"""

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

import config
import db
from pull_history import fetch, insert_game, insert_odds

ESPN_DAY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d}"
ESPN_ODDS = ("https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{e}/competitions/{e}/odds")
CBBD = "https://api.collegebasketballdata.com"
NBA_START = date(2014, 10, 1)          # ESPN moneylines start around the 2014-15 season
NCAAB_SEASONS = range(2015, 2027)       # 2014-15 through 2025-26
PAUSE = 0.12                            # seconds between ESPN requests (be polite)
MAX_FAILS = 20                          # consecutive failures before stopping
NBA_TYPES = {2: "regular", 3: "postseason", 5: "postseason"}   # 5 = play-in; 1 (preseason) and 4 (All-Star) skipped
# ESPN's codes for the 30 NBA teams (unchanged since 2014-15). Anything else is an All-Star
# Weekend exhibition (East/West, Team LeBron, Rising Stars...), which ESPN sometimes files as regular season.
NBA_TEAMS = {"ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM",
             "MIA", "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX", "POR", "SA", "SAC", "TOR", "UTAH", "WSH"}


def espn_get(url):
    """GET with retries and back-off. Returns parsed JSON, or raises after 3 tries."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"ESPN request kept failing: {url}")


# ---------- NBA ----------

def nba_games(conn):
    """Every completed regular-season / play-in / playoff game, day by day. Skips days already done."""
    have_days = {r[0] for r in conn.execute("SELECT DISTINCT game_date_et FROM hist_games WHERE sport = 'nba'")}
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date()
    d, fails, added = NBA_START, 0, 0
    while d < today:
        key = d.isoformat()
        if key in have_days and d < today - timedelta(days=3):
            d += timedelta(days=1)
            continue
        try:
            data = espn_get(ESPN_DAY.format(d=d.strftime("%Y%m%d")))
            fails = 0
        except RuntimeError as e:
            fails += 1
            if fails >= MAX_FAILS:
                sys.exit(f"STOP: {e}\nESPN refused {MAX_FAILS} requests in a row. Nothing is lost; "
                         "re-run later to resume.")
            d += timedelta(days=1)
            continue
        for e in (data or {}).get("events", []):
            stype = NBA_TYPES.get(e["season"]["type"])
            status = e["status"]["type"]
            if stype is None or not status.get("completed"):
                continue
            comp = e["competitions"][0]
            teams = {t["homeAway"]: t for t in comp["competitors"]}
            if {teams["home"]["team"]["abbreviation"], teams["away"]["team"]["abbreviation"]} - NBA_TEAMS:
                continue  # All-Star Weekend exhibition
            start = datetime.strptime(e["date"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            et = start.astimezone(db.EASTERN)
            try:
                insert_game(conn, sport="nba", season=e["season"]["year"], week=None, season_type=stype,
                            game_date_et=et.strftime("%Y-%m-%d"), kickoff_et=et.strftime("%Y-%m-%d %H:%M"),
                            kickoff_utc=db.to_utc(start), home_team=teams["home"]["team"]["abbreviation"],
                            away_team=teams["away"]["team"]["abbreviation"],
                            home_score=int(teams["home"]["score"]), away_score=int(teams["away"]["score"]),
                            neutral_site=int(bool(comp.get("neutralSite"))), source="espn", external_id=e["id"])
                added += 1
            except Exception as err:
                if "UNIQUE" not in str(err):
                    raise
        conn.commit()
        if d.day == 1:
            print(f"  {d:%b %Y}: {added} NBA games added so far", flush=True)
        d += timedelta(days=1)
        time.sleep(PAUSE)
    print(f"NBA games: {added} added.")


def nba_odds(conn):
    """Moneylines for every NBA game that hasn't been checked yet (one ESPN request each).
    A game with no moneyline gets a placeholder row with empty prices, so it isn't asked again."""
    todo = conn.execute(
        "SELECT g.id, g.external_id FROM hist_games g WHERE g.sport = 'nba'"
        " AND NOT EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id) ORDER BY g.game_date_et").fetchall()
    print(f"NBA odds: {len(todo)} games to check (about {len(todo) * (PAUSE + 0.25) / 60:.0f} minutes).", flush=True)
    fails = done = with_ml = 0
    for g in todo:
        try:
            data = espn_get(ESPN_ODDS.format(e=g["external_id"]))
            fails = 0
        except RuntimeError as e:
            fails += 1
            if fails >= MAX_FAILS:
                conn.commit()
                sys.exit(f"STOP: {e}\nESPN refused {MAX_FAILS} requests in a row after {done} games. "
                         "Everything so far is saved; re-run later to resume.")
            continue
        books = {}
        for item in (data or {}).get("items", []):
            name = (item.get("provider") or {}).get("name") or "unknown"
            h, a = item.get("homeTeamOdds") or {}, item.get("awayTeamOdds") or {}
            hm, am = h.get("moneyLine"), a.get("moneyLine")
            if "(" in name or hm is None or am is None:
                continue  # skip state-specific duplicates and lines without both prices
            if abs(hm) < 100 or abs(am) < 100:
                continue  # not a valid American price
            books[name] = (int(hm), int(am), item.get("spread"), item.get("overUnder"))
        if books:
            with_ml += 1
            for name, (hm, am, spread, total) in books.items():
                insert_odds(conn, hist_game_id=g["id"], provider=name, home_ml=hm, away_ml=am,
                            home_spread=spread, total=total, source="espn")
        else:
            insert_odds(conn, hist_game_id=g["id"], provider="espn: no moneyline", source="espn")
        done += 1
        if done % 200 == 0:
            conn.commit()
            print(f"  {done}/{len(todo)} checked, {with_ml} with moneylines", flush=True)
        time.sleep(PAUSE)
    conn.commit()
    print(f"NBA odds: {done} checked, {with_ml} with moneylines.")


# ---------- college basketball ----------

CBBD_PAUSE = 1.0   # CBBD rate-limits fast bursts; one request per second is safe


def cbbd_get(path, headers):
    """CBBD GET, paced, with patient retries on 'too many requests'."""
    for attempt in range(5):
        time.sleep(CBBD_PAUSE)
        try:
            return json.loads(fetch(f"{CBBD}{path}", headers))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"CBBD kept saying 'too many requests' for {path}")

def ncaab(conn):
    """Games and lines from CBBD, month by month (each request returns at most 3,000 games)."""
    if not config.CFBD_API_KEY:
        sys.exit("CFBD_API_KEY is empty in .env (CBBD uses the same key).")
    headers = {"Authorization": f"Bearer {config.CFBD_API_KEY}"}
    calls = 0
    for season in NCAAB_SEASONS:
        if conn.execute("SELECT 1 FROM hist_games WHERE sport = 'ncaab' AND season = ?", (season,)).fetchone():
            print(f"  college {season}: already loaded, skipped", flush=True)
            continue
        months = [(season - 1, m) for m in (11, 12)] + [(season, m) for m in (1, 2, 3, 4)]
        games, lines = [], {}
        for y, m in months:
            start = date(y, m, 1)
            end = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
            rng = f"season={season}&startDateRange={start}&endDateRange={end}"
            g = cbbd_get(f"/games?{rng}", headers)
            l = cbbd_get(f"/lines?{rng}", headers)
            calls += 2
            if len(g) >= 3000 or len(l) >= 3000:
                sys.exit(f"STOP: a CBBD page hit the 3,000-row limit ({start} to {end}); season {season} not saved.")
            games += g
            lines.update({x["gameId"]: x.get("lines") or [] for x in l})
        added = ml = 0
        conn.execute("BEGIN")
        for g in games:
            if g.get("status") != "final" or g.get("homePoints") is None or g.get("awayPoints") is None:
                continue
            start = datetime.strptime(g["startDate"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            et = start.astimezone(db.EASTERN)
            known_time = not g.get("startTimeTbd")
            gid = insert_game(conn, sport="ncaab", season=season, week=None,
                              season_type="regular" if g.get("seasonType") == "regular" else "postseason",
                              game_date_et=et.strftime("%Y-%m-%d"),
                              kickoff_et=et.strftime("%Y-%m-%d %H:%M") if known_time else None,
                              kickoff_utc=db.to_utc(start) if known_time else None,
                              home_team=g["homeTeam"], away_team=g["awayTeam"],
                              home_score=g["homePoints"], away_score=g["awayPoints"],
                              neutral_site=int(bool(g.get("neutralSite"))), source="cbbd", external_id=str(g["id"]))
            added += 1
            has_any = False
            for line in lines.get(g["id"], []):
                hm, am = line.get("homeMoneyline"), line.get("awayMoneyline")
                if hm is None or am is None or abs(hm) < 100 or abs(am) < 100:
                    hm = am = None
                if hm is None and line.get("spread") is None:
                    continue
                insert_odds(conn, hist_game_id=gid, provider=line.get("provider") or "unknown",
                            home_ml=int(hm) if hm is not None else None, away_ml=int(am) if am is not None else None,
                            home_spread=line.get("spread"), total=line.get("overUnder"), source="cbbd")
                has_any = has_any or hm is not None
            ml += has_any
        conn.commit()   # each season saved on its own
        print(f"  college {season}: {added} games, {ml} with moneylines", flush=True)
    print(f"College basketball loaded ({calls} CBBD calls).")


def summary(conn):
    for sport in ("nba", "ncaab"):
        print(f"\n{sport.upper()}: season  games  with moneyline")
        for r in conn.execute(
                "SELECT g.season, COUNT(*) n, SUM(EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id"
                " AND o.home_ml IS NOT NULL)) ml FROM hist_games g WHERE g.sport = ? GROUP BY g.season ORDER BY g.season",
                (sport,)):
            print(f"        {r['season']}  {r['n']:5d}  {r['ml']:5d}")


def main():
    a = sys.argv[1:]
    conn = db.connect()
    db.upgrade_db(conn)
    if a == ["ncaab"]:
        ncaab(conn)
    elif a == ["nba", "games"]:
        nba_games(conn)
    elif a == ["nba", "odds"]:
        nba_odds(conn)
    elif a == ["summary"]:
        summary(conn)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

"""Pull current moneylines from The Odds API into the live odds table.

Usage: python3 pull_odds.py nfl | ncaaf | nba | ncaab | soccer_club | all

Costs 1 credit per sport (up to 10 bookmakers, listed in config.ODDS_BOOKMAKERS); club soccer
costs 1 per league (5), and its prices include the Draw. `all` = the live sports (ALL_SPORTS). Refuses to run when fewer than MIN_CREDITS remain.
Every price is saved with the time it was pulled. Games that can't be matched
to our schedule with certainty are listed and nothing is saved for them.
"""

import json
import sqlite3
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import config
import db
from teams import TeamNames

API = "https://api.the-odds-api.com/v4"
SPORT_KEYS = {"nfl": "americanfootball_nfl", "ncaaf": "americanfootball_ncaaf",
              "nba": "basketball_nba", "ncaab": "basketball_ncaab", "soccer_club": None}
ALL_SPORTS = ("nfl", "ncaaf", "nba", "ncaab")   # club soccer joins once it goes live


def api_keys(sport):
    """The Odds API sport keys for one of our sports (club soccer: one per league)."""
    if sport == "soccer_club":
        from teams import SOCCER_LEAGUES
        return [k for _, _, _, k in SOCCER_LEAGUES.values()]
    return [SPORT_KEYS[sport]]
MIN_CREDITS = 50
KICKOFF_TOLERANCE = timedelta(minutes=15)   # warn if the two sources disagree by more
SAME_GAME_WINDOW = timedelta(hours=24)      # how far apart kickoffs can be and still match


def odds_api(path, **params):
    query = "&".join(f"{k}={v}" for k, v in {**params, "apiKey": config.ODDS_API_KEY}.items())
    with urllib.request.urlopen(f"{API}{path}?{query}", timeout=60) as resp:
        return json.load(resp), resp.headers


def credits_left():
    _, headers = odds_api("/sports")  # free call; used only to read the credit balance
    return int(headers["x-requests-remaining"])


def parse_time(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def find_game(conn, sport, home, away, kickoff):
    """Return (game row, swapped) for the one game that matches, or (None, None)."""
    lo, hi = db.to_utc(kickoff - SAME_GAME_WINDOW), db.to_utc(kickoff + SAME_GAME_WINDOW)
    rows = conn.execute(
        "SELECT *, (home_team = ?) AS same_order FROM games WHERE sport = ?"
        " AND ((home_team = ? AND away_team = ?) OR (home_team = ? AND away_team = ?))"
        " AND start_time_utc BETWEEN ? AND ?",
        (home, sport, home, away, away, home, lo, hi)).fetchall()
    if len(rows) != 1:
        return None, None
    return rows[0], not rows[0]["same_order"]


def pull(conn, sport):
    names = TeamNames(sport)
    events, headers = [], {}
    for key in api_keys(sport):
        got, headers = odds_api(f"/sports/{key}/odds", bookmakers=",".join(config.ODDS_BOOKMAKERS),
                                markets="h2h", oddsFormat="american")
        events += got
    three_way = sport.startswith("soccer")
    now = datetime.now(timezone.utc)
    saved_games = saved_rows = started = untracked = 0
    problems, warnings = [], []

    for e in events:
        kickoff = parse_time(e["commence_time"])
        label = f"{e['away_team']} at {e['home_team']}"
        if kickoff <= now:
            started += 1  # live in-game prices; we only keep pregame odds
            continue
        home, away = names.lookup(e["home_team"]), names.lookup(e["away_team"])
        if home is None or away is None:
            bad = [n for n, v in ((e["home_team"], home), (e["away_team"], away)) if v is None]
            problems.append(f"{label}: unknown team name {bad}")
            continue
        game, swapped = find_game(conn, sport, home, away, kickoff)
        if game is None:
            untracked += 1  # not in our schedule (lower division, or kickoff not announced)
            continue
        if swapped and not game["neutral_site"]:
            problems.append(f"{label}: home and away are reversed vs our schedule "
                            "and it's not a neutral site")
            continue
        drift = abs(parse_time(game["start_time_utc"].replace(" ", "T") + "Z") - kickoff)
        if drift > KICKOFF_TOLERANCE:
            warnings.append(f"{label}: Odds API kickoff {db.fmt_et(db.to_utc(kickoff))}, "
                            f"our schedule {db.fmt_et(game['start_time_utc'])}")

        rows_for_game = 0
        for book in e["bookmakers"]:
            market = next((m for m in book["markets"] if m["key"] == "h2h"), None)
            if market is None:
                continue
            prices = {o["name"]: o["price"] for o in market["outcomes"]}
            odds_home, odds_away = prices.get(e["home_team"]), prices.get(e["away_team"])
            odds_draw = prices.get("Draw") if three_way else None
            if odds_home is None or odds_away is None or (three_way and odds_draw is None):
                warnings.append(f"{label}: {book['title']} didn't price every outcome; skipped")
                continue
            if swapped:
                odds_home, odds_away = odds_away, odds_home
            try:
                db.add_odds(conn, game["id"], book["title"], home_ml=odds_home,
                            away_ml=odds_away, draw_ml=odds_draw, source="the-odds-api")
                rows_for_game += 1
            except sqlite3.DatabaseError as err:
                problems.append(f"{label}: {book['title']} price refused ({err})")
        if rows_for_game:
            saved_games += 1
            saved_rows += rows_for_game

    print(f"\n{sport.upper()}: saved {saved_rows} prices for {saved_games} games | "
          f"{started} already started (skipped) | {untracked} not in our schedule | "
          f"credits left: {headers.get('x-requests-remaining')}")
    for w in warnings:
        print(f"  NOTE: {w}")
    for p in problems:
        print(f"  PROBLEM: {p}")
    return not problems


def show_latest(conn, sport, days=7):
    """Print the most recent pull for each game in the next few days, from the database."""
    now = datetime.now(timezone.utc)
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " ORDER BY start_time_utc, id",
        (sport, db.to_utc(now), db.to_utc(now + timedelta(days=days)))).fetchall()
    print(f"\n{sport.upper()} latest moneylines, next {days} days (median across books):")
    for g in games:
        rows = conn.execute(
            "SELECT * FROM odds WHERE game_id = ? AND captured_at ="
            " (SELECT MAX(captured_at) FROM odds WHERE game_id = ?)", (g["id"], g["id"])).fetchall()
        if not rows:
            print(f"  {db.fmt_et(g['start_time_utc']):<24} {g['away_team']} at {g['home_team']}: no odds yet")
            continue
        away = round(statistics.median(r["away_ml"] for r in rows))
        home = round(statistics.median(r["home_ml"] for r in rows))
        draw = (f"  draw {round(statistics.median(r['draw_ml'] for r in rows)):+d}"
                if rows[0]["draw_ml"] is not None else "")
        print(f"  {db.fmt_et(g['start_time_utc']):<24} {g['away_team']} {away:+d} at "
              f"{g['home_team']} {home:+d}{draw}   ({len(rows)} books)")


def main():
    sports = list(ALL_SPORTS) if sys.argv[1:] == ["all"] else sys.argv[1:]
    if not sports or any(s not in SPORT_KEYS for s in sports):
        sys.exit(__doc__)
    if sys.argv[1:] == ["all"]:
        # Only sports with games in the next 7 days, so an off-season sport doesn't cost credits
        conn = db.connect()
        soon = db.to_utc(datetime.now(timezone.utc) + timedelta(days=7))
        now_txt = db.to_utc(datetime.now(timezone.utc))
        sports = [s for s in sports if conn.execute(
            "SELECT 1 FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?",
            (s, now_txt, soon)).fetchone()]
        if not sports:
            sys.exit("No sport has games in the next 7 days; nothing to pull.")
    if not config.ODDS_API_KEY:
        sys.exit("ODDS_API_KEY is empty in .env")
    try:
        left = credits_left()
    except urllib.error.HTTPError as e:
        sys.exit(f"The Odds API refused the request: HTTP {e.code}")
    print(f"Odds API credits left before this run: {left}")
    if left - sum(len(api_keys(s)) for s in sports) < MIN_CREDITS:
        sys.exit(f"Stopping: fewer than {MIN_CREDITS} credits would remain.")
    conn = db.connect()
    ok = True
    for sport in sports:
        ok = pull(conn, sport) and ok
    for sport in sports:
        show_latest(conn, sport)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

"""Test whether certain kinds of games are mispriced by the sportsbooks.

Usage: python3 market_patterns.py

Read-only. Patterns, bet sides, periods and the pass bar are fixed in
backtest_results/market_patterns_plan.md (committed before this ran).
"""

import math
from collections import defaultdict

import db
from odds_math import decimal_odds, no_vig

PERIODS = {"nfl": {"discovery": (2006, 2018), "confirmation": (2019, 2025)},
           "ncaaf": {"discovery": (2021, 2022), "confirmation": (2023, 2025)}}
POPULAR_NFL = {"DAL", "KC", "GB", "PIT", "SF"}
FRANCHISE = {"SD": "LAC", "OAK": "LV", "STL": "LA"}


def load(conn, sport):
    """Games with moneylines: one dict per game, oldest first."""
    rows = conn.execute(
        "SELECT g.*, o.home_ml, o.away_ml FROM hist_games g JOIN hist_odds o ON o.hist_game_id = g.id"
        " WHERE g.sport = ? AND o.home_ml IS NOT NULL ORDER BY g.game_date_et, g.kickoff_utc, g.id",
        (sport,)).fetchall()
    games = {}
    for r in rows:
        g = games.setdefault(r["id"], {**dict(r), "lines": []})
        g["lines"].append((r["home_ml"], r["away_ml"]))
    out = []
    for g in games.values():
        n = len(g["lines"])
        g["p_home"] = sum(no_vig(h, a)[0] for h, a in g["lines"]) / n
        g["dec_home"] = sum(decimal_odds(h) for h, _ in g["lines"]) / n
        g["dec_away"] = sum(decimal_odds(a) for _, a in g["lines"]) / n
        for side in ("home", "away"):
            g[f"{side}_team"] = FRANCHISE.get(g[f"{side}_team"], g[f"{side}_team"]) if sport == "nfl" else g[f"{side}_team"]
        out.append(g)
    return out


def previous_games(conn, sport):
    """{hist game id: {team: (previous margin this season, previous starter id)}} using ALL past games
    (with or without odds), so 'previous game' is truly the last one played."""
    rows = conn.execute("SELECT * FROM hist_games WHERE sport = ? ORDER BY game_date_et, kickoff_utc, id",
                        (sport,)).fetchall()
    last = {}  # (season, team) -> (margin, starter)
    out = {}
    for r in rows:
        teams = {}
        for side, other in (("home", "away"), ("away", "home")):
            team = FRANCHISE.get(r[f"{side}_team"], r[f"{side}_team"]) if sport == "nfl" else r[f"{side}_team"]
            teams[team] = last.get((r["season"], team))
            last[(r["season"], team)] = (r[f"{side}_score"] - r[f"{other}_score"], r[f"{side}_starter_id"])
        out[r["id"]] = teams
    return out


def bets_for(pattern, g, prev, sport):
    """List of sides ('home'/'away') this pattern bets in game g."""
    p = g["p_home"]
    home, away = g["home_team"], g["away_team"]
    sides = []
    if pattern == "1" and not g["neutral_site"] and p < 0.5:
        sides.append("home")
    elif pattern == "2a":
        if p < 0.25:
            sides.append("home")
        elif 1 - p < 0.25:
            sides.append("away")
    elif pattern == "2b":
        if p > 0.75:
            sides.append("home")
        elif 1 - p > 0.75:
            sides.append("away")
    elif pattern == "3":
        if home in POPULAR_NFL and away not in POPULAR_NFL:
            sides.append("away")
        elif away in POPULAR_NFL and home not in POPULAR_NFL:
            sides.append("home")
    elif pattern == "4":
        for side in ("home", "away"):
            before = prev.get(g[f"{side}_team"])
            if before and before[1] and g[f"{side}_starter_id"] and before[1] != g[f"{side}_starter_id"]:
                sides.append(side)
    elif pattern == "5a":
        for side in ("home", "away"):
            before = prev.get(g[f"{side}_team"])
            if before and before[0] <= -20:
                sides.append(side)
    elif pattern == "5b":
        for side, other in (("home", "away"), ("away", "home")):
            before = prev.get(g[f"{side}_team"])
            if before and before[0] >= 20:
                sides.append(other)
    elif pattern == "6" and not g["neutral_site"] and g["away_rest_days"] is not None and g["away_rest_days"] <= 4:
        sides.append("home")
    return sides


PATTERNS = [("1", "Home underdogs", "home team", ("nfl", "ncaaf")),
            ("2a", "Big underdogs (<25%)", "the underdog", ("nfl", "ncaaf")),
            ("2b", "Big favorites (>75%)", "the favorite", ("nfl", "ncaaf")),
            ("3", "Popular NFL teams", "against them", ("nfl",)),
            ("4", "New starting QB", "the new-QB team", ("nfl",)),
            ("5a", "After losing by 20+", "that team", ("nfl", "ncaaf")),
            ("5b", "After winning by 20+", "against that team", ("nfl", "ncaaf")),
            ("6", "Road team on short rest", "the home team", ("nfl",))]


def evaluate(games, prev, pattern, sport, period):
    lo, hi = period
    n = wins = 0
    expected = var = units = 0.0
    for g in games:
        if not (lo <= g["season"] <= hi):
            continue
        for side in bets_for(pattern, g, prev.get(g["id"], {}), sport):
            p = g["p_home"] if side == "home" else 1 - g["p_home"]
            dec = g["dec_home"] if side == "home" else g["dec_away"]
            n += 1
            if g["home_score"] == g["away_score"]:
                continue  # push: stake back, not counted in wins or expectations
            won = (g["home_score"] > g["away_score"]) == (side == "home")
            wins += won
            expected += p
            var += p * (1 - p)
            units += (dec - 1) if won else -1
    if not n:
        return None
    return {"n": n, "wins": wins, "expected": expected, "units": units, "roi": units / n,
            "z": (wins - expected) / math.sqrt(var) if var else 0.0}


def main():
    conn = db.connect()
    report = []
    for sport in ("nfl", "ncaaf"):
        games = load(conn, sport)
        prev = previous_games(conn, sport)
        label = "NFL" if sport == "nfl" else "College"
        report.append(f"\n### {label}\n")
        report.append("| # | Pattern (bet) | Period | Bets | Won | Market expected | ROI | z | |")
        report.append("|---|---|---|---|---|---|---|---|---|")
        for code, name, bet, sports in PATTERNS:
            if sport not in sports:
                continue
            res = {k: evaluate(games, prev, code, sport, v) for k, v in PERIODS[sport].items()}
            d, c = res["discovery"], res["confirmation"]
            passed = bool(d and c and d["roi"] > 0 and c["roi"] > 0 and c["z"] >= 2)
            for period, r in res.items():
                if r is None:
                    continue
                verdict = ("**PASS**" if passed else "fail") if period == "confirmation" else ""
                report.append(f"| {code} | {name} ({bet}) | {period} {PERIODS[sport][period][0]}-{PERIODS[sport][period][1]} "
                              f"| {r['n']} | {r['wins']} | {r['expected']:.1f} | {r['roi']:+.1%} | {r['z']:+.2f} | {verdict} |")
    text = "\n".join(report)
    print(text)
    return text


if __name__ == "__main__":
    main()

"""Grade finished games: a scorecard for each prediction source, by sport.

Usage: python3 grade.py nfl | ncaaf  [--season YEAR]   (default: current season)

For each game with a final result, the graded prediction from each source
(engine, claude, me) is its latest row logged before kickoff (corrections
added after kickoff are never graded). The market is shown as a benchmark,
using the no-vig price at the time of each engine prediction.

Scorecard:
  Brier score and log loss (lower is better), calibration table
  Flagged bets: edge >= config.EDGE_THRESHOLD vs the no-vig market at the
    time of that prediction, 1 unit at the best price at your books then
  Closing-line value (CLV): for the side each source leaned toward vs the
    market, how much the market moved toward it by the close (last odds
    pulled before kickoff). Positive average CLV over many games is the best
    early sign of a real edge.
Closing lines pulled more than 60 minutes before kickoff are marked approximate.
"""

import math
import statistics
import sys

import config
import db
from odds_math import decimal_odds, no_vig
from pull_history import CURRENT_SEASON

SOURCES = ("engine", "claude", "me")
CLOSE_WARN_MIN = 60


def market_at(conn, game_id, captured_at):
    """No-vig P(home) and best prices at my books, from one odds pull."""
    rows = conn.execute("SELECT * FROM odds WHERE game_id = ? AND captured_at = ?",
                        (game_id, captured_at)).fetchall()
    if not rows:
        return None
    mine = [r for r in rows if r["bookmaker"] in config.MY_BOOKS]
    best = {side: max((r[f"{side}_ml"] for r in mine), key=decimal_odds) if mine else None
            for side in ("home", "away")}
    return {"p_home": statistics.mean(no_vig(r["home_ml"], r["away_ml"])[0] for r in rows),
            "best": best}


def closing(conn, game):
    r = conn.execute("SELECT MAX(captured_at) AS t FROM odds WHERE game_id = ? AND captured_at < ?",
                     (game["id"], game["start_time_utc"])).fetchone()
    if not r["t"]:
        return None, None
    minutes = (db.utc_to_eastern(game["start_time_utc"]) - db.utc_to_eastern(r["t"])).total_seconds() / 60
    return market_at(conn, game["id"], r["t"]), minutes


def graded_prediction(conn, game, source):
    return conn.execute(
        "SELECT * FROM predictions WHERE game_id = ? AND source = ? AND corrects_id IS NULL"
        " AND created_at < ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (game["id"], source, game["start_time_utc"])).fetchone()


def log_loss(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def grade(conn, sport, season):
    games = conn.execute(
        "SELECT g.*, r.home_score, r.away_score FROM games g JOIN results r ON r.game_id = g.id"
        " WHERE g.sport = ? AND g.season = ? AND r.status = 'final' ORDER BY g.start_time_utc",
        (sport, str(season))).fetchall()
    stats = {s: {"rows": [], "bets": [], "clv": []} for s in SOURCES + ("market",)}
    approx_close = 0
    for g in games:
        if g["home_score"] == g["away_score"]:
            continue  # ties: moneyline pushes, left out of scoring
        y = int(g["home_score"] > g["away_score"])
        close, minutes = closing(conn, g)
        if close and minutes > CLOSE_WARN_MIN and any(graded_prediction(conn, g, s) for s in SOURCES):
            approx_close += 1
        for source in SOURCES:
            pred = graded_prediction(conn, g, source)
            if pred is None:
                continue
            p = pred["p_home"]
            stats[source]["rows"].append((p, y))
            snap = conn.execute("SELECT captured_at FROM odds WHERE id = ?", (pred["odds_id"],)).fetchone() \
                if pred["odds_id"] else None
            mkt = market_at(conn, g["id"], snap["captured_at"]) if snap else None
            if mkt is None:
                continue
            if source == "engine":
                stats["market"]["rows"].append((mkt["p_home"], y))
            # flagged bets
            for side, edge, won in (("home", p - mkt["p_home"], y == 1), ("away", mkt["p_home"] - p, y == 0)):
                if edge >= config.EDGE_THRESHOLD and mkt["best"][side] is not None:
                    dec = decimal_odds(mkt["best"][side])
                    stats[source]["bets"].append(dec - 1 if won else -1.0)
            # closing-line value for the side this source leaned toward
            if close and abs(p - mkt["p_home"]) > 1e-9:
                side_home = p > mkt["p_home"]
                then = mkt["p_home"] if side_home else 1 - mkt["p_home"]
                at_close = close["p_home"] if side_home else 1 - close["p_home"]
                stats[source]["clv"].append(at_close - then)
    return games, stats, approx_close


def print_scorecard(sport, season, games, stats, approx_close):
    print(f"===== {sport.upper()} {season} scorecard: {len(games)} finished games =====")
    if approx_close:
        print(f"Note: {approx_close} game(s) had no odds pull within {CLOSE_WARN_MIN} min of kickoff; "
              "their closing line is approximate.")
    print(f"\n{'source':<8} {'graded':>6} {'Brier':>7} {'log loss':>9}   {'flagged bets':<26} "
          f"{'avg CLV':>8} {'CLV+ rate':>9}")
    for source in ("market",) + SOURCES:
        s = stats[source]
        n = len(s["rows"])
        if not n:
            print(f"{source:<8} {0:>6}")
            continue
        brier = sum((p - y) ** 2 for p, y in s["rows"]) / n
        ll = sum(log_loss(p, y) for p, y in s["rows"]) / n
        bets = s["bets"]
        wins = sum(1 for b in bets if b > 0)
        bet_txt = (f"{wins}-{len(bets) - wins}, {sum(bets):+.1f}u ({sum(bets) / len(bets):+.1%})"
                   if bets else "none")
        clv = s["clv"]
        clv_txt = (f"{statistics.mean(clv):+8.1%} {sum(c > 0 for c in clv) / len(clv):9.0%}"
                   if clv else f"{'':>8} {'':>9}")
        print(f"{source:<8} {n:>6} {brier:7.4f} {ll:9.4f}   {bet_txt if source != 'market' else '':<26} "
              f"{clv_txt if source != 'market' else ''}")
    print("\n'market' = no-vig price when each engine prediction was logged (the benchmark to beat).")
    print("CLV = how far the market moved toward the side the source leaned, by the close.")

    for source in SOURCES:
        rows = stats[source]["rows"]
        if len(rows) < 20:
            continue
        print(f"\nCalibration, {source}: when it gave the home team...")
        for lo in range(0, 100, 10):
            b = [(p, y) for p, y in rows if lo / 100 <= p < (lo + 10) / 100 or (lo == 90 and p == 1)]
            if b:
                print(f"   {lo:2d}-{lo + 10:3d}%  {len(b):4d} games  predicted {sum(p for p, _ in b) / len(b):6.1%}"
                      f"  home won {sum(y for _, y in b) / len(b):6.1%}")

    graded = len(stats["engine"]["rows"])
    print(f"\nRule 8: {graded} graded games this season "
          f"({'enough' if graded >= 200 else f'{200 - graded} more needed'} before weighting sources by track record).")


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("nfl", "ncaaf"):
        sys.exit(__doc__)
    season = int(a[a.index("--season") + 1]) if "--season" in a else CURRENT_SEASON
    conn = db.connect()
    print_scorecard(a[0], season, *grade(conn, a[0], season))


if __name__ == "__main__":
    main()

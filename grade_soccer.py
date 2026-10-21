"""Grade finished club soccer games: a three-way scorecard per source (grade.py hands soccer here).

Usage: python3 grade.py soccer_club [--season YEAR]   (YEAR = the year the season ends; default current)

Same rules as grade.py: each source's graded prediction is its latest row before kickoff; the
market benchmark is the no-vig price when the engine prediction was logged.
  Brier (summed over home/draw/away), log loss (of what happened), RPS (ranked probability score:
    home, draw, away in order, so a draw is "between"; lower is better for all three)
  Flagged bets: per game, the outcome with the largest edge if >= config.EDGE_THRESHOLD (as in
    predict_soccer.py and the final exam), 1 unit at the best price at your books then
  CLV: for the outcome each source leaned to most vs the market, how much the market moved
    toward it by the close
"""

import math
import statistics

import config
import db
from grade import CLOSE_WARN_MIN, SOURCES, graded_prediction
from odds_math import decimal_odds, no_vig
from pull_history import season_label

OUTCOMES = ("home", "draw", "away")


def market_at(conn, game_id, captured_at):
    rows = [r for r in conn.execute("SELECT * FROM odds WHERE game_id = ? AND captured_at = ?",
                                    (game_id, captured_at)) if r["draw_ml"] is not None]
    if not rows:
        return None
    fair = [no_vig(r["home_ml"], r["draw_ml"], r["away_ml"]) for r in rows]
    mine = [r for r in rows if r["bookmaker"] in config.MY_BOOKS]
    best = {o: max((r[f"{o}_ml"] for r in mine), key=decimal_odds) if mine else None for o in OUTCOMES}
    return {"p": tuple(statistics.mean(f[i] for f in fair) for i in range(3)), "best": best}


def closing(conn, game):
    r = conn.execute("SELECT MAX(captured_at) AS t FROM odds WHERE game_id = ? AND captured_at < ?",
                     (game["id"], game["start_time_utc"])).fetchone()
    if not r["t"]:
        return None, None
    minutes = (db.utc_to_eastern(game["start_time_utc"]) - db.utc_to_eastern(r["t"])).total_seconds() / 60
    return market_at(conn, game["id"], r["t"]), minutes


def scores(p, y):
    """(Brier, log loss, RPS) for one game: p = (home, draw, away), y = index of what happened."""
    brier = sum((p[i] - (i == y)) ** 2 for i in range(3))
    ll = -math.log(min(max(p[y], 1e-6), 1))
    rps = ((p[0] - (y == 0)) ** 2 + (p[0] + p[1] - (y <= 1)) ** 2) / 2
    return brier, ll, rps


def grade(conn, season):
    games = conn.execute(
        "SELECT g.*, r.home_score, r.away_score FROM games g JOIN results r ON r.game_id = g.id"
        " WHERE g.sport = 'soccer_club' AND g.season = ? AND r.status = 'final' ORDER BY g.start_time_utc",
        (str(season),)).fetchall()
    stats = {s: {"rows": [], "bets": [], "clv": []} for s in SOURCES + ("market",)}
    stats["per_game"] = []
    approx_close = 0
    for g in games:
        y = 0 if g["home_score"] > g["away_score"] else 1 if g["home_score"] == g["away_score"] else 2
        close, minutes = closing(conn, g)
        if close and minutes > CLOSE_WARN_MIN and any(graded_prediction(conn, g, s) for s in SOURCES):
            approx_close += 1
        game_probs = {"y": y}
        stats["per_game"].append(game_probs)
        for source in SOURCES:
            pred = graded_prediction(conn, g, source)
            if pred is None or pred["p_draw"] is None:
                continue
            p = (pred["p_home"], pred["p_draw"], pred["p_away"])
            stats[source]["rows"].append((p, y))
            game_probs[source] = p
            snap = conn.execute("SELECT captured_at FROM odds WHERE id = ?", (pred["odds_id"],)).fetchone() \
                if pred["odds_id"] else None
            mkt = market_at(conn, g["id"], snap["captured_at"]) if snap else None
            if mkt is None:
                continue
            if source == "engine":
                stats["market"]["rows"].append((mkt["p"], y))
                game_probs["market"] = mkt["p"]
            edges = [p[i] - mkt["p"][i] for i in range(3)]
            i = max(range(3), key=lambda k: edges[k])
            if edges[i] >= config.EDGE_THRESHOLD and mkt["best"][OUTCOMES[i]] is not None:
                dec = decimal_odds(mkt["best"][OUTCOMES[i]])
                stats[source]["bets"].append(dec - 1 if y == i else -1.0)
            if close and edges[i] > 1e-9:
                stats[source]["clv"].append(close["p"][i] - mkt["p"][i])
    return games, stats, approx_close


def summary(rows):
    n = len(rows)
    totals = [sum(scores(p, y)[k] for p, y in rows) / n for k in range(3)]
    return n, *totals


def print_scorecard(season, games, stats, approx_close):
    print(f"===== CLUB SOCCER {season_label('soccer_club', season)} scorecard: {len(games)} finished games =====")
    if approx_close:
        print(f"Note: {approx_close} game(s) had no odds pull within {CLOSE_WARN_MIN} min of kickoff; "
              "their closing line is approximate.")
    print(f"\n{'source':<8} {'graded':>6} {'Brier':>7} {'log loss':>9} {'RPS':>7}   {'flagged bets':<26} "
          f"{'avg CLV':>8} {'CLV+ rate':>9}")
    for source in ("market",) + SOURCES:
        s = stats[source]
        if not s["rows"]:
            print(f"{source:<8} {0:>6}")
            continue
        n, brier, ll, rps = summary(s["rows"])
        bets = s["bets"]
        wins = sum(1 for b in bets if b > 0)
        bet_txt = (f"{wins}-{len(bets) - wins}, {sum(bets):+.1f}u ({sum(bets) / len(bets):+.1%})" if bets else "none")
        clv = s["clv"]
        clv_txt = (f"{statistics.mean(clv):+8.1%} {sum(c > 0 for c in clv) / len(clv):9.0%}" if clv else "")
        print(f"{source:<8} {n:>6} {brier:7.4f} {ll:9.4f} {rps:7.4f}   "
              f"{bet_txt if source != 'market' else '':<26} {clv_txt if source != 'market' else ''}")
    print("\n'market' = no-vig price when each engine prediction was logged (the benchmark to beat).")
    print("CLV = how far the market moved toward the outcome the source leaned to most, by the close.")

    for source in SOURCES:
        rows = stats[source]["rows"]
        if len(rows) < 30:
            continue
        print(f"\nCalibration, {source}:")
        for i, name in enumerate(OUTCOMES):
            parts = []
            for lo in range(0, 100, 10):
                b = [(p[i], int(y == i)) for p, y in rows if lo / 100 <= p[i] < (lo + 10) / 100]
                if len(b) >= 5:
                    parts.append(f"{lo}%: {len(b)} games, predicted {sum(x for x, _ in b) / len(b):.0%}, "
                                 f"happened {sum(z for _, z in b) / len(b):.0%}")
            print(f"   {name}: " + ("; ".join(parts) or "too few games yet"))

    lines = []
    for a, b in (("me", "engine"), ("claude", "engine"), ("me", "claude")):
        common = [g for g in stats["per_game"] if a in g and b in g and "market" in g]
        if common:
            cells = [f"{src} {summary([(g[src], g['y']) for g in common])[1]:.4f} / "
                     f"{summary([(g[src], g['y']) for g in common])[2]:.4f}" for src in (a, b, "market")]
            lines.append(f"  {a} vs {b}, on the {len(common)} game(s) both picked:  " + "   ".join(cells))
    if lines:
        print("\nHead-to-head (Brier / log loss on the same games; lower is better):")
        print("\n".join(lines))
    graded = len(stats["engine"]["rows"])
    print(f"\nRule 8: {graded} graded games this season "
          f"({'enough' if graded >= 200 else f'{200 - graded} more needed'} before weighting sources by track record).")

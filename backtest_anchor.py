"""Fit and test the market-anchored engine (plan: plans/anchor.md).

Usage: python3 backtest_anchor.py nfl | ncaaf | nba | ncaab | soccer_club [--save] [--out]

In log-odds: anchored = market + c + w*d + w_early*early*d + w_big*d*|d| + w_fav*fav_size,
where d = engine - market. Every term, w included, is kept only if it improves CHECK-season log loss by
>= 0.001 over the market alone (forward selection). Soccer blends each outcome's log probability the same way (one w,
one w_big, one w_early) and renormalizes. --save writes the weights under "anchor" in
model_params.json; --out appends the report to backtest_results/anchor.md. The final-exam seasons
are never used here; the real test is live (shadow mode).
"""

import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
import db
import model
from factor_study import ball_table, fit, periods, sigmoid, recent_form

MIN_GAIN = 0.001
EARLY_GAMES = {"nfl": 4, "ncaaf": 4, "nba": 10, "ncaab": 10, "soccer_club": 5}
RESULTS = Path(__file__).parent / "backtest_results" / "anchor.md"
TERMS = ["w_early", "w_big", "w_fav"]


# ---------- two-outcome sports ----------

def ball_rows(conn, sport):
    import backtest
    mkt = backtest.market_by_game(conn, sport)
    rows = ball_table(conn, sport)
    early_n = EARLY_GAMES[sport]
    out = []
    for r in rows:
        f = r["f"]
        d = f["engine_logit"] - f["market_logit"]
        early = max(0.0, 1 - f["games_played"] / early_n)
        m = mkt[r["id"]]
        out.append({"id": r["id"], "season": r["season"], "y": r["y"], "m": f["market_logit"],
                    "x": {"w": d, "w_early": early * d, "w_big": d * abs(d), "w_fav": f["fav_size"]},
                    "dec": (m["dec_home"], m["dec_away"])})
    return out


def design(rows, names):
    return [[r["x"][n] for n in names] for r in rows], [r["y"] for r in rows], [r["m"] for r in rows]


def ll2(rows, w, names):
    X, y, off = design(rows, names)
    tot = 0.0
    for xi, yi, oi in zip(X, y, off):
        q = sigmoid(oi + w[0] + sum(a * b for a, b in zip(w[1:], xi)))
        q = min(max(q, 1e-9), 1 - 1e-9)
        tot -= yi * math.log(q) + (1 - yi) * math.log(1 - q)
    return tot / len(y)


def fit2(rows, names):
    X, y, off = design(rows, names)
    return fit(X, y, off, lam=0.01)


def select2(rt, rc):
    """Start from the market alone (intercept only); add terms, w included, only if they earn it."""
    names = []
    w = fit2(rt, names)
    best = ll2(rc, w, names)
    log = [("(market only)", best, None)]
    remaining = ["w"] + list(TERMS)
    while remaining:
        trials = []
        for t in remaining:
            nm = names + [t]
            wt = fit2(rt, nm)
            trials.append((ll2(rc, wt, nm), t, wt))
        ll, t, wt = min(trials, key=lambda x: x[0])
        if best - ll < MIN_GAIN:
            break
        names.append(t)
        remaining.remove(t)
        log.append((t, ll, best - ll))
        best, w = ll, wt
    return names, w, log


def probs2(rows, w, names):
    return [sigmoid(r["m"] + w[0] + sum(a * r["x"][n] for a, n in zip(w[1:], names))) for r in rows]


def bets2(rows, p_model):
    """Flagged bets (edge >= threshold vs the market) at the average listed price: (n, wins, units)."""
    n = wins = 0
    units = 0.0
    for r, p in zip(rows, p_model):
        m = sigmoid(r["m"])
        for side, edge, won, dec in (("home", p - m, r["y"] == 1, r["dec"][0]), ("away", m - p, r["y"] == 0, r["dec"][1])):
            if edge >= config.EDGE_THRESHOLD and dec:
                n += 1
                wins += won
                units += (dec - 1) if won else -1
    return n, wins, units


# ---------- soccer (three outcomes) ----------

def soccer_rows(conn):
    import soccer_model as sm
    from backtest_soccer import market
    params = sm.load_params()["ratings"]
    games = sm.load_games(conn)
    preds, _ = sm.walk_forward(games, params, keep=lambda g: g["league"] in sm.BIG5)
    mkt = market(conn)
    form = recent_form(games)
    out = []
    for g in games:
        m = mkt.get(g["id"], {})
        if g["id"] not in preds or "Market average" not in m:
            continue
        y = 0 if g["home_score"] > g["away_score"] else 1 if g["home_score"] == g["away_score"] else 2
        ph, pa = form[g["id"]][:2]
        out.append({"id": g["id"], "season": g["season"], "y": y, "e": preds[g["id"]][:3], "m": m["Market average"],
                    "close": m.get("Market average (close)"), "dec": m["Market average dec"],
                    "early": max(0.0, 1 - (ph + pa) / 2 / EARLY_GAMES["soccer_club"])})
    return out


def blend3(r, t):
    """Geometric blend of engine and market over three outcomes with terms t = {w, w_early, w_big}."""
    logs = []
    for e, m in zip(r["e"], r["m"]):
        d = math.log(max(e, 1e-9)) - math.log(max(m, 1e-9))
        logs.append(math.log(max(m, 1e-9)) + t.get("w", 0) * d + t.get("w_early", 0) * r["early"] * d
                    + t.get("w_big", 0) * d * abs(d))
    mx = max(logs)
    ex = [math.exp(x - mx) for x in logs]
    s = sum(ex)
    return tuple(x / s for x in ex)


def ll3(rows, t):
    return sum(-math.log(max(blend3(r, t)[r["y"]], 1e-9)) for r in rows) / len(rows)


def fit3(rows, names, start=None):
    """Coordinate descent on tune log loss over the named terms."""
    t = {n: 0.0 for n in names}
    t.update({k: v for k, v in (start or {}).items() if k in names})
    best = ll3(rows, t)
    for step in (0.2, 0.05, 0.01, 0.002):
        improved = True
        while improved:
            improved = False
            for n in names:
                for sgn in (1, -1):
                    trial = dict(t)
                    trial[n] += sgn * step
                    s = ll3(rows, trial)
                    if s < best - 1e-7:
                        best, t, improved = s, trial, True
    return t


def select3(rt, rc):
    names = []
    t = {}
    best = ll3(rc, t)
    log = [("(market only)", best, None)]
    remaining = ["w", "w_early", "w_big"]
    while remaining:
        trials = []
        for term in remaining:
            tt = fit3(rt, names + [term], t)
            trials.append((ll3(rc, tt), term, tt))
        ll, term, tt = min(trials, key=lambda x: x[0])
        if best - ll < MIN_GAIN:
            break
        names.append(term)
        remaining.remove(term)
        log.append((term, ll, best - ll))
        best, t = ll, tt
    return names, t, log


def bets3(rows, probs):
    n = wins = clv_n = 0
    units = clv = 0.0
    for r, p in zip(rows, probs):
        edges = [p[i] - r["m"][i] for i in range(3)]
        i = max(range(3), key=lambda k: edges[k])
        if edges[i] < config.EDGE_THRESHOLD:
            continue
        n += 1
        won = r["y"] == i
        wins += won
        units += (r["dec"][i] - 1) if won else -1
        if r["close"]:
            clv += r["close"][i] - r["m"][i]
            clv_n += 1
    return n, wins, units, (clv / clv_n if clv_n else None), clv_n


# ---------- report ----------

def report(sport, save):
    conn = db.connect()
    tune, check = periods(sport)
    lines = [f"\n## {sport}: tune {tune[0]}-{tune[1]}, check {check[0]}-{check[1]}\n"]
    if sport in ("ncaaf", "ncaab"):
        lines.append("Priced seasons only (overlap the final exam): information, not a pre-registered test.\n")
    if sport == "soccer_club":
        rows = soccer_rows(conn)
        rt = [r for r in rows if tune[0] <= r["season"] <= tune[1]]
        rc = [r for r in rows if check[0] <= r["season"] <= check[1]]
        names, t, log = select3(rt, rc)
        lines.append(f"Fitted terms: {json.dumps({k: round(v, 4) for k, v in t.items()})}\n")
        pm = [r["m"] for r in rc]
        pe = [r["e"] for r in rc]
        pa = [blend3(r, t) for r in rc]
        ll_m = sum(-math.log(max(p[r["y"]], 1e-9)) for r, p in zip(rc, pm)) / len(rc)
        ll_e = sum(-math.log(max(p[r["y"]], 1e-9)) for r, p in zip(rc, pe)) / len(rc)
        ll_a = ll3(rc, t)
        lines.append(f"Check-season log loss: market {ll_m:.4f} | engine {ll_e:.4f} | anchored {ll_a:.4f} ({len(rc)} games)\n")
        lines.append("| model | flagged bets | won | units | ROI | avg CLV (games with a close) |")
        lines.append("|---|---|---|---|---|---|")
        for label, probs in (("engine", pe), ("anchored", pa)):
            n, w_, u, clv, cn = bets3(rc, probs)
            lines.append(f"| {label} | {n} | {w_} | {u:+.1f} | {u / n if n else 0:+.1%} | "
                         f"{'' if clv is None else f'{clv * 100:+.2f} pts'} ({cn}) |")
        weights = {k: round(v, 5) for k, v in t.items()}
    else:
        rows = ball_rows(conn, sport)
        rt = [r for r in rows if tune[0] <= r["season"] <= tune[1]]
        rc = [r for r in rows if check[0] <= r["season"] <= check[1]]
        names, w, log = select2(rt, rc)
        weights = {"c": round(w[0], 5), **{n: round(v, 5) for n, v in zip(names, w[1:])}}
        lines.append(f"Fitted terms: {json.dumps(weights)}\n")
        pm = [sigmoid(r["m"]) for r in rc]
        pe = [sigmoid(r["m"] + r["x"]["w"]) for r in rc]
        pa = probs2(rc, w, names)
        def ll(ps):
            return sum(-(r["y"] * math.log(max(p, 1e-9)) + (1 - r["y"]) * math.log(max(1 - p, 1e-9))) for r, p in zip(rc, ps)) / len(rc)
        lines.append(f"Check-season log loss: market {ll(pm):.4f} | engine {ll(pe):.4f} | anchored {ll(pa):.4f} ({len(rc)} games)\n")
        lines.append("| model | flagged bets | won | units | ROI |")
        lines.append("|---|---|---|---|---|")
        for label, probs in (("engine", pe), ("anchored", pa)):
            n, w_, u = bets2(rc, probs)
            lines.append(f"| {label} | {n} | {w_} | {u:+.1f} | {u / n if n else 0:+.1%} |")
    lines.append("\nForward selection (check-season log loss after each kept term):\n")
    lines.append("| term | check log loss | gain |")
    lines.append("|---|---|---|")
    for n, l, g in log:
        lines.append(f"| {n} | {l:.4f} | {'' if g is None else f'{g:+.4f}'} |")
    if save:
        saved = json.loads(model.PARAMS_PATH.read_text())
        saved[sport]["anchor"] = {"version": f"anchor-v1-{datetime.now(timezone.utc):%Y%m%d}", "terms": weights,
                                  "early_games": EARLY_GAMES[sport], "tune_seasons": list(tune), "check_seasons": list(check),
                                  "note": "Market-anchored engine (plans/anchor.md); shadow-tested live, not the engine."}
        model.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
        lines.append(f"\nSaved as {saved[sport]['anchor']['version']} under {sport}.anchor in model_params.json.")
    return "\n".join(lines)


def main():
    a = sys.argv[1:]
    if not a or a[0] not in EARLY_GAMES:
        sys.exit(__doc__)
    text = report(a[0], "--save" in a)
    print(text)
    if "--out" in a:
        if not RESULTS.exists():
            RESULTS.write_text("# Market-anchored engine: tune/check results\n\nPlan: `plans/anchor.md`. Produced by "
                               "`backtest_anchor.py`. Flagged bets use the average listed price. Run 2026-10-23.\n")
        RESULTS.write_text(RESULTS.read_text() + text + "\n")


if __name__ == "__main__":
    main()

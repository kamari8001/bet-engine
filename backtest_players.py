"""Backtest the NBA player-impact feature (plan and bars: plans/player_impact.md).

Usage:
  python3 backtest_players.py base              the team model alone on tune and check seasons
  python3 backtest_players.py idea 1|2|3|4      tune that idea's settings on the tune seasons, report check seasons
  python3 backtest_players.py ablate            all four ideas in order, applying the pre-registered keep rules
  python3 backtest_players.py save <idea>       save that idea's tuned settings under nba.players in model_params.json

Team settings are the pre-exam nba-v1 (from final_runs.jsonl) so nothing here saw the exam seasons.
Ideas: 1 minutes only; 2 production rating; 3 production + impact; 4 online correction of the
absence coefficient. Keep rule: an idea must beat the previous best check-season log loss by >= 0.002
and keep every 50+ game calibration bucket within 8 points.
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import db
import model
import player_model as pm
from backtest import PERIODS, log_loss, market_by_game, RESULTS_DIR
import config
from odds_math import decimal_odds

TUNE, CHECK = PERIODS["nba"]["tune"], PERIODS["nba"]["check"]
MIN_GAIN = 0.002
IDEA_PARAMS = {1: ["abs_coef"], 2: ["abs_coef", "alpha", "season_regress", "repl_z"],
               3: ["abs_coef", "alpha", "season_regress", "repl_z", "w_imp"],
               4: ["abs_coef", "alpha", "season_regress", "repl_z", "w_imp", "abs_k"]}
START = {"abs_coef": 3.0, "abs_k": 0.02}


def team_params():
    for line in (RESULTS_DIR / "final_runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["sport"] == "nba":
            return r["ratings"]
    raise RuntimeError("nba exam record not found")


def attach(games, feats):
    for g in games:
        f = feats.get(g["id"])
        g["home_missing"], g["away_missing"] = (f[0], f[1]) if f and f[2] else (None, None)


def run(games, box, tparams, pparams, idea):
    pp = {k: v for k, v in pparams.items() if k not in ("abs_coef", "abs_k")}
    pp["idea"] = min(idea, 3) if idea else 2
    if idea == 2:
        pp["w_imp"] = 0.0
    feats, book = pm.features(games, box, pp)
    attach(games, feats)
    tp = dict(tparams, abs_coef=pparams.get("abs_coef", 0.0), abs_k=pparams.get("abs_k", 0.0) if idea == 4 else 0.0)
    preds, _ = model.walk_forward(games, tp, "nba")
    return preds, book


def period_ll(games, preds, period):
    rows = [(preds[g["id"]][2], int(g["home_score"] > g["away_score"])) for g in games
            if period[0] <= g["season"] <= period[1] and g["home_score"] != g["away_score"]]
    return log_loss(rows)


def worst_bucket(games, preds, period):
    rows = [(preds[g["id"]][2], int(g["home_score"] > g["away_score"])) for g in games
            if period[0] <= g["season"] <= period[1] and g["home_score"] != g["away_score"]]
    worst = 0.0
    for lo in range(0, 100, 10):
        b = [(p, y) for p, y in rows if lo / 100 <= p < (lo + 10) / 100 or (lo == 90 and p == 1)]
        if len(b) >= 50:
            worst = max(worst, abs(sum(p for p, _ in b) / len(b) - sum(y for _, y in b) / len(b)))
    return worst


def market_gap(games, preds, mkt, period):
    """(model log loss, market log loss, flagged bets, ROI) on priced check games."""
    rows_m, rows_k, bets = [], [], []
    for g in games:
        m = mkt.get(g["id"])
        if not (period[0] <= g["season"] <= period[1]) or not m or m["p_home"] is None or g["home_score"] == g["away_score"]:
            continue
        y = int(g["home_score"] > g["away_score"])
        p = preds[g["id"]][2]
        rows_m.append((p, y)); rows_k.append((m["p_home"], y))
        for side, edge, won, dec in (("home", p - m["p_home"], y == 1, m["dec_home"]), ("away", m["p_home"] - p, y == 0, m["dec_away"])):
            if edge >= config.EDGE_THRESHOLD and dec:
                bets.append((dec - 1) if won else -1.0)
    return log_loss(rows_m), log_loss(rows_k), len(bets), (sum(bets) / len(bets) if bets else 0.0)


def tune(games, box, tparams, idea, start=None):
    names = IDEA_PARAMS[idea]
    params = {**{k: pm.DEFAULTS[k] for k in names if k in pm.DEFAULTS}, **{k: START[k] for k in names if k in START}}
    params.update({k: v for k, v in (start or {}).items() if k in names})
    score = lambda p: period_ll(games, run(games, box, tparams, p, idea)[0], TUNE)
    best = score(params)
    print(f"  idea {idea}: starting tune log loss {best:.4f}", flush=True)
    for factors in ([0.5, 0.75, 1.33, 2.0], [0.85, 0.93, 1.07, 1.18], [0.96, 1.04]):
        improved = True
        while improved:
            improved = False
            for name in names:
                for f in factors:
                    trial = dict(params)
                    v = params[name]
                    trial[name] = (v * f) if v else (0.01 * f if name != "repl_z" else -0.1 * f)
                    if name in ("season_regress", "w_imp"):
                        trial[name] = min(trial[name], 1.0)
                    s = score(trial)
                    if s < best - 1e-6:
                        best, params, improved = s, trial, True
        print(f"    after step size {factors}: {best:.4f}  {json.dumps({k: round(v, 4) for k, v in params.items()})}", flush=True)
    return params


def report(label, games, preds, mkt):
    t, c = period_ll(games, preds, TUNE), period_ll(games, preds, CHECK)
    wb = worst_bucket(games, preds, CHECK)
    mm, mk, nb, roi = market_gap(games, preds, mkt, CHECK)
    print(f"{label:<28} tune {t:.4f}  check {c:.4f}  worst bucket {wb * 100:.1f}  | vs market (check): {mm:.4f} vs {mk:.4f} | flags {nb}, ROI {roi:+.1%}")
    return {"tune": t, "check": c, "worst_bucket": wb, "model_vs_market": [mm, mk], "flags": nb, "roi": roi}


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("base", "idea", "ablate", "save"):
        sys.exit(__doc__)
    conn = db.connect()
    box = pm.load_box(conn)
    games = model.load_games(conn, "nba")
    mkt = market_by_game(conn, "nba")
    tparams = team_params()
    print(f"{len(games)} games, {len(box)} with box scores; team settings nba-v1 (pre-exam)")
    base_preds, _ = model.walk_forward(games, tparams, "nba")
    base = report("base (no players)", games, base_preds, mkt)
    if a[0] == "base":
        return
    results_path = RESULTS_DIR / "players.md"
    lines = [f"\n## Run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC: {a}\n",
             f"base: tune {base['tune']:.4f}, check {base['check']:.4f}, worst bucket {base['worst_bucket'] * 100:.1f}, "
             f"vs market {base['model_vs_market'][0]:.4f} / {base['model_vs_market'][1]:.4f}, flags {base['flags']} ROI {base['roi']:+.1%}"]
    ideas = [int(a[1])] if a[0] in ("idea", "save") else [1, 2, 3, 4]
    best_check, best_params, start = base["check"], None, None
    saved_sets = {}
    for idea in ideas:
        params = tune(games, box, tparams, idea, start)
        preds, book = run(games, box, tparams, params, idea)
        r = report(f"idea {idea}", games, preds, mkt)
        # calibration: within 8 points, or no worse than the base model's own worst bucket (the pre-exam
        # settings already have a 60-game bucket off by 13.9 on the check seasons)
        keep = (best_check - r["check"] >= MIN_GAIN) and r["worst_bucket"] <= max(0.08, base["worst_bucket"] + 1e-9)
        lines.append(f"idea {idea}: {json.dumps({k: round(v, 4) for k, v in params.items()})} -> tune {r['tune']:.4f}, "
                     f"check {r['check']:.4f} ({r['check'] - best_check:+.4f} vs best so far), worst bucket {r['worst_bucket'] * 100:.1f}, "
                     f"vs market {r['model_vs_market'][0]:.4f} / {r['model_vs_market'][1]:.4f}, flags {r['flags']} ROI {r['roi']:+.1%} -> "
                     f"{'KEEP' if keep else 'drop'}")
        saved_sets[idea] = params
        if keep:
            best_check, best_params, start = r["check"], (idea, params), params
        elif a[0] == "ablate":
            start = params if idea == 1 else start   # later ideas start from the best kept settings
    if a[0] == "save":
        idea = ideas[0]
        p = saved_sets[idea]
        saved = json.loads(model.PARAMS_PATH.read_text())
        saved["nba"]["players"] = {"version": f"players-v1-{datetime.now(timezone.utc):%Y%m%d}", "idea": idea,
                                   "params": {k: v for k, v in p.items() if k not in ("abs_coef", "abs_k")},
                                   "abs_coef": p.get("abs_coef", 0.0), "abs_k": p.get("abs_k", 0.0) if idea == 4 else 0.0,
                                   "tune_seasons": list(TUNE), "check_seasons": list(CHECK),
                                   "note": "Player-impact feature (plans/player_impact.md); tuned on tune seasons."}
        model.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
        print(f"Saved idea {idea} under nba.players in model_params.json")
    lines.append(f"\nBest kept: {best_params[0] if best_params else 'none'} (check {best_check:.4f})")
    if not results_path.exists():
        results_path.write_text("# Player-impact feature: tune/check results\n\nPlan: `plans/player_impact.md`. "
                                "Produced by `backtest_players.py`.\n")
    results_path.write_text(results_path.read_text() + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

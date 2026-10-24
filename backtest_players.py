"""Backtest the NBA player-impact feature (plan and bars: plans/player_impact.md).

Usage:
  python3 backtest_players.py base              the team model alone on tune and check seasons
  python3 backtest_players.py idea 1|2|3|4      tune that idea's settings on the tune seasons, report check seasons
  python3 backtest_players.py ablate            all four ideas in order, applying the pre-registered keep rules
  python3 backtest_players.py early             early-season ideas 5 and 6 (plans/player_early_season.md) on top of
                                                the kept idea 2, bar 0.001; first-20-games vs rest report
  python3 backtest_players.py look              second look: the kept settings on the exam seasons (already used once
                                                for nba-v1), plus whether the engine adds anything beside the market
  python3 backtest_players.py save              save the kept settings (players_best.json) under nba.players in model_params.json
  python3 backtest_players.py refit             nba-v2 for live use: team + player settings refit on every season
                                                (no seasons left untouched: judged on live results only). Saved to
                                                backtest_results/nba_refit_pending.json, NOT live yet.
  python3 backtest_players.py apply             puts the pending refit live (replaces the NBA block of model_params.json)

College basketball: add `--sport ncaab` to base, ablate (ideas 1-2) or look (plans/college_player_impact.md);
results in players_ncaab.md / players_best_ncaab.json.

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
import factor_study
import model
import player_model as pm
from backtest import PERIODS, log_loss, market_by_game, RESULTS_DIR
import config
from odds_math import decimal_odds

SPORT = "nba"
TUNE, CHECK, FINAL = PERIODS["nba"]["tune"], PERIODS["nba"]["check"], PERIODS["nba"]["final"]
RESULTS_NAME = "players.md"
BEST_PATH = RESULTS_DIR / "players_best.json"
PENDING_PATH = RESULTS_DIR / "nba_refit_pending.json"
EARLY_BEST_PATH = RESULTS_DIR / "players_best_early.json"
MIN_GAIN = 0.002
IDEA_PARAMS = {1: ["abs_coef"], 2: ["abs_coef", "alpha", "season_regress", "repl_z"],
               3: ["abs_coef", "alpha", "season_regress", "repl_z", "w_imp"],
               4: ["abs_coef", "alpha", "season_regress", "repl_z", "w_imp", "abs_k"]}
IDEA_PARAMS[5] = IDEA_PARAMS[6] = IDEA_PARAMS[2]
IDEA_FLAGS = {5: {"regress_to": "average"}, 6: {"carry_unseen": True}}   # idea 6 also gets 5's flag if 5 is kept
START = {"abs_coef": 3.0, "abs_k": 0.02}
EARLY_BAR = 0.001
EARLY_GAMES = 20


def configure(sport):
    """Point the test at a sport (nba default; ncaab per plans/college_player_impact.md)."""
    global SPORT, TUNE, CHECK, FINAL, BEST_PATH, RESULTS_NAME
    SPORT = sport
    TUNE, CHECK, FINAL = (PERIODS[sport][k] for k in ("tune", "check", "final"))
    if sport != "nba":
        BEST_PATH = RESULTS_DIR / f"players_best_{sport}.json"
        RESULTS_NAME = f"players_{sport}.md"


def team_params():
    """The sport's pre-exam team settings: its first final-exam record."""
    for line in (RESULTS_DIR / "final_runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["sport"] == SPORT:
            return r["ratings"]
    raise RuntimeError(f"{SPORT} exam record not found")


def attach(games, feats):
    for g in games:
        f = feats.get(g["id"])
        g["home_missing"], g["away_missing"] = (f[0], f[1]) if f and f[2] else (None, None)


def run(games, box, tparams, pparams, idea):
    pp = {k: v for k, v in pparams.items() if k not in ("abs_coef", "abs_k")}
    pp["idea"] = 2 if not idea or idea >= 5 else min(idea, 3)
    if idea in (2, 5, 6):
        pp["w_imp"] = 0.0
    pp.update(IDEA_FLAGS.get(idea, {}))
    feats, book = pm.features(games, box, pp)
    attach(games, feats)
    tp = dict(tparams, abs_coef=pparams.get("abs_coef", 0.0), abs_k=pparams.get("abs_k", 0.0) if idea == 4 else 0.0)
    preds, _ = model.walk_forward(games, tp, SPORT)
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


def early_split(games, preds, period):
    """(log loss on games where either team is in its first EARLY_GAMES of the season, n, log loss on the rest, n)."""
    count, early, rest = {}, [], []
    for g in games:
        key = (g["season"],)
        nh, na = count.get(key + (g["home_team"],), 0), count.get(key + (g["away_team"],), 0)
        count[key + (g["home_team"],)], count[key + (g["away_team"],)] = nh + 1, na + 1
        if period[0] <= g["season"] <= period[1] and g["home_score"] != g["away_score"]:
            (early if min(nh, na) < EARLY_GAMES else rest).append((preds[g["id"]][2], int(g["home_score"] > g["away_score"])))
    return log_loss(early), len(early), log_loss(rest), len(rest)


def early(games, box, tparams, mkt):
    """Ideas 5 and 6 on top of the kept idea 2 (players_best.json), pre-registered bar EARLY_BAR."""
    best = json.loads(BEST_PATH.read_text())
    params, base_flags = dict(best["params"]), {}
    preds, _ = run(games, box, tparams, params, 2)
    r0 = report("idea 2 (live design)", games, preds, mkt)
    e0 = early_split(games, preds, CHECK)
    lines = [f"\n## Early-season ideas {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC (plans/player_early_season.md)\n",
             f"idea 2 (starting point): check {r0['check']:.4f}, worst bucket {r0['worst_bucket'] * 100:.1f}; "
             f"check first {EARLY_GAMES} games {e0[0]:.4f} ({e0[1]}), rest {e0[2]:.4f} ({e0[3]})"]
    best_check, kept = r0["check"], []
    for idea in (5, 6):
        IDEA_FLAGS[idea] = {**base_flags, **IDEA_FLAGS[idea]}
        p = tune(games, box, tparams, idea, params)
        preds, _ = run(games, box, tparams, p, idea)
        r = report(f"idea {idea}", games, preds, mkt)
        e = early_split(games, preds, CHECK)
        keep = best_check - r["check"] >= EARLY_BAR and r["worst_bucket"] <= max(0.08, r0["worst_bucket"] + 1e-9)
        lines.append(f"idea {idea} {json.dumps(IDEA_FLAGS[idea])}: {json.dumps({k: round(v, 4) for k, v in p.items()})} -> "
                     f"tune {r['tune']:.4f}, check {r['check']:.4f} ({r['check'] - best_check:+.4f} vs best so far), "
                     f"worst bucket {r['worst_bucket'] * 100:.1f}; first {EARLY_GAMES} games {e[0]:.4f} ({e[0] - e0[0]:+.4f}), "
                     f"rest {e[2]:.4f} ({e[2] - e0[2]:+.4f}); vs market {r['model_vs_market'][0]:.4f} / "
                     f"{r['model_vs_market'][1]:.4f}, flags {r['flags']} ROI {r['roi']:+.1%} -> {'KEEP' if keep else 'drop'}")
        if keep:
            best_check, params, base_flags = r["check"], p, dict(IDEA_FLAGS[idea])
            kept.append(idea)
    lines.append(f"\nKept: {', '.join(map(str, kept)) or 'none'} (check {best_check:.4f})")
    if kept:
        EARLY_BEST_PATH.write_text(json.dumps({"idea": 2, "flags": base_flags, "params": params, "check": best_check,
                                               "kept": kept}, indent=2) + "\n")
    return lines


def beside_market(games, preds, mkt, fit_period, test_period):
    """Information only: fit market + c + w*(engine - market) in log-odds on fit_period, test on test_period.
    Returns (w, market-alone log loss, market + engine log loss, games) on test_period."""
    logit = lambda q: math.log(q / (1 - q))
    def rows(period):
        out = []
        for g in games:
            m = mkt.get(g["id"])
            if period[0] <= g["season"] <= period[1] and m and m["p_home"] and g["home_score"] != g["away_score"]:
                p = min(max(preds[g["id"]][2], 1e-6), 1 - 1e-6)
                out.append((logit(m["p_home"]), logit(p) - logit(m["p_home"]), int(g["home_score"] > g["away_score"])))
        return out
    fr, tr = rows(fit_period), rows(test_period)
    w0 = factor_study.fit([[] for _ in fr], [r[2] for r in fr], [r[0] for r in fr])
    w1 = factor_study.fit([[r[1]] for r in fr], [r[2] for r in fr], [r[0] for r in fr])
    ll = lambda w, use: log_loss([(factor_study.sigmoid(r[0] + w[0] + (w[1] * r[1] if use else 0)), r[2]) for r in tr])
    return w1[1], ll(w0, False), ll(w1, True), len(tr)


def look(games, box, tparams, mkt, base_preds):
    best = json.loads(BEST_PATH.read_text())
    preds, _ = run(games, box, tparams, best["params"], best["idea"])
    lines = [f"\n## Second look {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC: {SPORT} idea {best['idea']} on the exam seasons "
             f"{FINAL[0]}-{FINAL[1]}\n",
             f"These seasons were already used for the {SPORT} final exam, so this is a second look, not an "
             "untouched test. Settings tuned on tune seasons only.\n",
             "| model | log loss | worst bucket | model vs market log loss | flagged bets | ROI |", "|---|---|---|---|---|---|"]
    for label, p in ((f"team model only ({SPORT}-v1 pre-exam)", base_preds), (f"with players (idea {best['idea']})", preds)):
        mm, mk, nb, roi = market_gap(games, p, mkt, FINAL)
        lines.append(f"| {label} | {period_ll(games, p, FINAL):.4f} | {worst_bucket(games, p, FINAL) * 100:.1f} | "
                     f"{mm:.4f} vs {mk:.4f} | {nb} | {roi:+.1%} |")
    lines += ["\nInformation only: does the engine add anything beside the market price? Fit market + c + w x "
              "(engine - market) in log-odds on the tune seasons, test on later seasons (w = 0 means the engine adds nothing).\n",
              "| model | test seasons | w | market alone | market + engine | games |", "|---|---|---|---|---|---|"]
    for label, p in (("team model only", base_preds), ("with players", preds)):
        for per in (CHECK, FINAL):
            w, l0, l1, n = beside_market(games, p, mkt, TUNE, per)
            lines.append(f"| {label} | {per[0]}-{per[1]} | {w:+.3f} | {l0:.4f} | {l1:.4f} | {n} |")
    return lines


def refit(games, box, mkt):
    """Tune the team settings and the kept idea's player settings together on every season, starting
    from the live nba-v1-refit team settings and the tune-season player settings. Saves nba-v2-refit."""
    import backtest
    old = model.load_params("nba")
    best = json.loads(BEST_PATH.read_text())
    if best["idea"] != 2:
        sys.exit("refit is written for idea 2 (production rating)")
    allp = PERIODS["nba"]["all"]
    team_names = backtest.TUNED + backtest.TUNED_EXTRA["nba"]
    pl_names = ["alpha", "season_regress", "repl_z", "abs_coef"]
    tp = {k: v for k, v in old["ratings"].items() if k != "abs_coef"}
    pp = {k: best["params"][k] for k in pl_names}
    cache = {}

    def feats_for(p):
        key = tuple(p[k] for k in pl_names if k != "abs_coef")
        if key not in cache:
            if len(cache) >= 3:
                cache.pop(next(iter(cache)))
            cache[key] = pm.features(games, box, {**{k: p[k] for k in pl_names if k != "abs_coef"}, "idea": 2})[0]
        return cache[key]

    def score(t, p):
        attach(games, feats_for(p))
        preds, _ = model.walk_forward(games, dict(t, abs_coef=p["abs_coef"]), "nba")
        return period_ll(games, preds, allp)

    bestll = score(tp, pp)
    print(f"Refit on {allp[0]}-{allp[1]}: starting log loss {bestll:.4f}", flush=True)
    for factors in ([0.5, 0.75, 1.33, 2.0], [0.85, 0.93, 1.07, 1.18], [0.96, 1.04]):
        improved = True
        while improved:
            improved = False
            for name in team_names + pl_names:
                for f in factors:
                    t, p = dict(tp), dict(pp)
                    d = t if name in team_names else p
                    v = d[name]
                    d[name] = v * f if v else (0.001 * f if name in team_names else 0.01 * f)
                    if name in ("regress", "season_regress"):
                        d[name] = min(d[name], 1.0)
                    sc = score(t, p)
                    if sc < bestll - 1e-6:
                        bestll, tp, pp, improved = sc, t, p, True
        print(f"  after step size {factors}: {bestll:.4f}  team {json.dumps({k: round(v, 4) for k, v in tp.items()})}"
              f"  players {json.dumps({k: round(v, 4) for k, v in pp.items()})}", flush=True)
    day = f"{datetime.now(timezone.utc):%Y%m%d}"
    saved = {"nba": None}
    prev = old
    saved["nba"] = {**{k: v for k, v in prev.items() if k not in ("version", "ratings", "players", "note", "previous")},
                    "version": f"nba-v2-refit-{day}",
                    "ratings": {**{k: round(v, 5) for k, v in tp.items()}, "abs_coef": round(pp["abs_coef"], 5)},
                    "combiner": None, "calibration": {"a": 1.0, "b": 0.0}, "fit_seasons": list(allp),
                    "players": {"version": f"players-v1-refit-{day}", "idea": 2,
                                "params": {k: round(pp[k], 5) for k in pl_names if k != "abs_coef"},
                                "plan": "plans/player_impact.md", "results": "backtest_results/players.md"},
                    "previous": prev["version"],
                    "note": "nba-v2: team ratings + rest + player absences (production rating, idea 2). Refit on all "
                            "seasons after the tune/check test; judged on live results only."}
    PENDING_PATH.write_text(json.dumps(saved["nba"], indent=2) + "\n")
    attach(games, feats_for(pp))
    preds, _ = model.walk_forward(games, saved["nba"]["ratings"], "nba")
    mm, mk, nb, roi = market_gap(games, preds, mkt, allp)
    line = (f"\n## Refit {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC: {saved['nba']['version']} "
            f"(pending: live after `backtest_players.py apply`)\n\n"
            f"Team {json.dumps(saved['nba']['ratings'])}; players {json.dumps(saved['nba']['players']['params'])}.\n"
            f"In-sample on {allp[0]}-{allp[1]} (used for fitting, so NOT a test): log loss {bestll:.4f}, "
            f"worst bucket {worst_bucket(games, preds, allp) * 100:.1f}, vs market {mm:.4f} / {mk:.4f}, "
            f"flags {nb} ROI {roi:+.1%}. Replaces {prev['version']}.")
    print(line)
    path = RESULTS_DIR / "players.md"
    path.write_text(path.read_text() + line + "\n")


def apply():
    """Put the pending refit live: replace the NBA block of model_params.json, nothing else."""
    if not PENDING_PATH.exists():
        sys.exit("No pending refit. Run `python3 backtest_players.py refit` first.")
    new = json.loads(PENDING_PATH.read_text())
    saved = json.loads(model.PARAMS_PATH.read_text())
    live = saved["nba"]["version"]
    if live == new["version"]:
        sys.exit(f"{live} is already live.")
    if live != new["previous"]:
        sys.exit(f"STOP: the pending refit was built to replace {new['previous']}, but {live} is live now. Refit again.")
    saved["nba"] = new
    model.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
    print(f"NBA model is now {new['version']} (was {live}). Every other sport is unchanged.")
    print("Next NBA predictions use it; run `python3 predict.py nba` to log them now.")


def main():
    a = sys.argv[1:]
    if "--sport" in a:
        i = a.index("--sport")
        sport = a[i + 1]
        del a[i:i + 2]
        if sport not in ("nba", "ncaab"):
            sys.exit("--sport must be nba or ncaab")
        configure(sport)
        if sport != "nba" and a[:1] not in (["base"], ["ablate"], ["look"]):
            sys.exit("For college basketball only base, ablate and look exist so far (step 2 of the plan).")
    if a[:1] == ["apply"]:
        apply()
        return
    if not a or a[0] not in ("base", "idea", "ablate", "look", "save", "refit", "apply", "early"):
        sys.exit(__doc__)
    conn = db.connect()
    box = pm.load_box(conn, SPORT)
    games = model.load_games(conn, SPORT, players=False)
    mkt = market_by_game(conn, SPORT)
    tparams = team_params()
    print(f"{len(games)} {SPORT} games, {len(box)} with box scores; team settings {SPORT}-v1 (pre-exam)")
    base_preds, _ = model.walk_forward(games, tparams, SPORT)
    base = report("base (no players)", games, base_preds, mkt)
    if a[0] == "base":
        return
    if a[0] == "refit":
        refit(games, box, mkt)
        return
    if a[0] == "save":
        best = json.loads(BEST_PATH.read_text())
        idea, p = best["idea"], best["params"]
        saved = json.loads(model.PARAMS_PATH.read_text())
        saved["nba"]["players"] = {"version": f"players-v1-{datetime.now(timezone.utc):%Y%m%d}", "idea": idea,
                                   "params": {k: v for k, v in p.items() if k not in ("abs_coef", "abs_k")},
                                   "abs_coef": p.get("abs_coef", 0.0), "abs_k": p.get("abs_k", 0.0) if idea == 4 else 0.0,
                                   "tune_seasons": list(TUNE), "check_seasons": list(CHECK),
                                   "note": "Player-impact feature (plans/player_impact.md); tuned on tune seasons."}
        model.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
        print(f"Saved idea {idea} under nba.players in model_params.json")
        return
    results_path = RESULTS_DIR / RESULTS_NAME
    lines = [f"\n## Run {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC: {a}\n",
             f"base: tune {base['tune']:.4f}, check {base['check']:.4f}, worst bucket {base['worst_bucket'] * 100:.1f}, "
             f"vs market {base['model_vs_market'][0]:.4f} / {base['model_vs_market'][1]:.4f}, flags {base['flags']} ROI {base['roi']:+.1%}"]
    if a[0] == "early":
        lines += early(games, box, tparams, mkt)
        results_path.write_text(results_path.read_text() + "\n".join(lines) + "\n")
        print("\n".join(lines))
        return
    if a[0] == "look":
        lines += look(games, box, tparams, mkt, base_preds)
        results_path.write_text(results_path.read_text() + "\n".join(lines) + "\n")
        print("\n".join(lines))
        return
    ideas = [int(a[1])] if a[0] == "idea" else [1, 2, 3, 4] if SPORT == "nba" else [1, 2]
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
    if a[0] == "ablate" and best_params:
        BEST_PATH.write_text(json.dumps({"idea": best_params[0], "params": best_params[1], "check": best_check}, indent=2) + "\n")
    lines.append(f"\nBest kept: {best_params[0] if best_params else 'none'} (check {best_check:.4f})")
    if not results_path.exists():
        results_path.write_text("# Player-impact feature: tune/check results\n\nPlan: `plans/player_impact.md`. "
                                "Produced by `backtest_players.py`.\n")
    results_path.write_text(results_path.read_text() + "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

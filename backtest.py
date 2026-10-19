"""Test the model honestly on past seasons.

Usage:
  python3 backtest.py tune  nfl|ncaaf   pick settings on the tune seasons, fit the
                                        calibration on the check seasons, save them
  python3 backtest.py check nfl|ncaaf   report on tune and check seasons (saved settings)
  python3 backtest.py ablate nfl        tune each new idea alone and together, compare
  python3 backtest.py ablate ncaaf      compare combiner inputs (published ratings etc.)
  python3 backtest.py refit nfl|ncaaf   after the final exam: refit on all seasons for live use
  python3 backtest.py final nfl|ncaaf   the final exam on seasons never used for tuning.
                                        Every run is recorded in backtest_results/.

Every prediction only uses games played before it (see model.walk_forward).
Betting lines are never used by the model, only for comparison.
"""

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import combiner
import config
import db
import model
from odds_math import decimal_odds, is_pregame_sportsbook, no_vig

PERIODS = {
    "nfl":   {"tune": (2006, 2018), "check": (2019, 2022), "final": (2023, 2025), "all": (2006, 2025)},
    "ncaaf": {"tune": (2014, 2018), "check": (2019, 2020), "final": (2021, 2025), "all": (2014, 2025)},
    "nba":   {"tune": (2015, 2020), "check": (2021, 2023), "final": (2024, 2026), "all": (2015, 2026)},
    "ncaab": {"tune": (2015, 2020), "check": (2021, 2023), "final": (2024, 2026), "all": (2015, 2026)},
}
TUNED = ["k", "hfa_start", "hfa_rate", "regress", "cap", "sigma"]
# Which combiner inputs each sport uses (None = our model alone). Chosen with
# `backtest.py ablate`, judged on the check seasons.
COMBINER_SET = {"nfl": None, "ncaaf": "ours + preseason data", "nba": None, "ncaab": None}
TUNED_EXTRA = {"nfl": ["qb_k", "new_qb", "qb_regress", "rest_coef"], "ncaaf": ["new_team"],
               "nba": ["rest_coef"], "ncaab": ["rest_coef"]}
RESULTS_DIR = Path(__file__).parent / "backtest_results"


# ---------- scoring ----------

def clamp(p):
    return min(max(p, 1e-6), 1 - 1e-6)


def brier(rows):
    return sum((p - y) ** 2 for p, y in rows) / len(rows)


def log_loss(rows):
    return -sum(y * math.log(clamp(p)) + (1 - y) * math.log(1 - clamp(p)) for p, y in rows) / len(rows)


def logit(p):
    p = clamp(p)
    return math.log(p / (1 - p))


def calibrate(p, cal):
    return 1 / (1 + math.exp(-(cal["a"] * logit(p) + cal["b"])))


def fit_calibration(rows):
    """Fit q = sigmoid(a*logit(p) + b) by Newton's method (Platt scaling)."""
    a, b = 1.0, 0.0
    for _ in range(50):
        ga = gb = haa = hab = hbb = 0.0
        for p, y in rows:
            x = logit(p)
            q = 1 / (1 + math.exp(-(a * x + b)))
            w = q * (1 - q)
            ga += (q - y) * x
            gb += q - y
            haa += w * x * x
            hab += w * x
            hbb += w
        det = haa * hbb - hab * hab
        a -= (hbb * ga - hab * gb) / det
        b -= (haa * gb - hab * ga) / det
    return {"a": round(a, 4), "b": round(b, 4)}


# ---------- data ----------

def market_by_game(conn, sport):
    """{hist game id: (no-vig P(home), mean decimal odds home, away, market margin, total)}.
    Averages across every book that priced both sides."""
    out = {}
    rows = conn.execute(
        "SELECT o.* FROM hist_odds o JOIN hist_games g ON g.id = o.hist_game_id"
        " WHERE g.sport = ?", (sport,)).fetchall()
    by_game = {}
    for r in rows:
        if not is_pregame_sportsbook(r["provider"]):
            continue  # prediction sites, averages, opening and live prices aren't the market
        by_game.setdefault(r["hist_game_id"], []).append(r)
    for gid, lines in by_game.items():
        ml = [l for l in lines if l["home_ml"] is not None]
        spreads = [l["home_spread"] for l in lines if l["home_spread"] is not None]
        totals = [l["total"] for l in lines if l["total"] is not None]
        out[gid] = {
            "p_home": sum(no_vig(l["home_ml"], l["away_ml"])[0] for l in ml) / len(ml) if ml else None,
            "dec_home": sum(decimal_odds(l["home_ml"]) for l in ml) / len(ml) if ml else None,
            "dec_away": sum(decimal_odds(l["away_ml"]) for l in ml) / len(ml) if ml else None,
            "margin": -sum(spreads) / len(spreads) if spreads else None,
            "total": sum(totals) / len(totals) if totals else None,
        }
    return out


def in_period(g, period):
    return period[0] <= g["season"] <= period[1]


def period_log_loss(games, preds, period):
    rows = [(preds[g["id"]][2], int(g["home_score"] > g["away_score"]))
            for g in games if in_period(g, period) and g["home_score"] != g["away_score"]]
    return log_loss(rows)


# ---------- tuning ----------

def tune(games, sport, names=None, start=None, period_name="tune"):
    params = dict(start or model.DEFAULT_PARAMS[sport])
    names = names or TUNED + TUNED_EXTRA[sport]
    period = PERIODS[sport][period_name]

    def score(p):
        preds, _ = model.walk_forward(games, p, sport)
        return period_log_loss(games, preds, period)

    best = score(params)
    print(f"Starting log loss on {period_name} seasons: {best:.4f}")
    for factors in ([0.5, 0.75, 1.33, 2.0], [0.85, 0.93, 1.07, 1.18], [0.96, 1.04]):
        improved = True
        while improved:
            improved = False
            for name in names:
                for f in factors:
                    trial = dict(params)
                    trial[name] = params[name] * f if params[name] else 0.001 * f
                    if name == "regress":
                        trial[name] = min(trial[name], 1.0)
                    s = score(trial)
                    if s < best - 1e-6:
                        best, params, improved = s, trial, True
        print(f"  after step size {factors}: log loss {best:.4f}")
    return {k: round(v, 5) for k, v in params.items()}


# ---------- testing ideas one at a time ----------

NFL_V3_FEATURES = {
    "#1 efficiency (EPA) ratings": ["epa_w", "epa_k"],
    "#2 new-coach reset": ["coach_regress"],
    "#3 early-season learning": ["early_boost"],
    "#4 travel / time zones": ["travel_coef", "early_west"],
}


def combiner_rows(conn, games, preds, sport, period):
    team_seasons = combiner.load_team_seasons(conn, sport)
    played = combiner.games_played_before(games)
    return [(combiner.features(g, preds[g["id"]][0] - preds[g["id"]][1], played[g["id"]], team_seasons),
             int(g["home_score"] > g["away_score"]))
            for g in games if in_period(g, period) and g["home_score"] != g["away_score"]]


def ablate_combiner(conn, games, sport):
    """Fit each combiner input set on the tune seasons; score on check seasons."""
    params = model.load_params(sport)["ratings"]
    preds, _ = model.walk_forward(games, params, sport)
    tune_rows = combiner_rows(conn, games, preds, sport, PERIODS[sport]["tune"])
    check_rows = combiner_rows(conn, games, preds, sport, PERIODS[sport]["check"])
    raw = [(preds[g["id"]][2], int(g["home_score"] > g["away_score"])) for g in games
           if in_period(g, PERIODS[sport]["check"]) and g["home_score"] != g["away_score"]]
    print(f"\n===== {sport.upper()} combiner inputs, fit on tune seasons, scored on check seasons =====")
    print(f"{'inputs':<28} {'tune LL':>8} {'check LL':>9} {'check Brier':>12}   weights")
    print(f"{'our model as is':<28} {'':>8} {log_loss(raw):9.4f} {brier(raw):12.4f}")
    for label, names in combiner.FEATURE_SETS.items():
        comb = combiner.fit(tune_rows, names)
        score = lambda rows: [(combiner.probability(comb, f), y) for f, y in rows]
        print(f"{label:<28} {log_loss(score(tune_rows)):8.4f} {log_loss(score(check_rows)):9.4f} "
              f"{brier(score(check_rows)):12.4f}   "
              + ", ".join(f"{n} {c:+.2f}" for n, c in zip(["const"] + names, comb["coef"])))


def ablate(games, sport):
    """Tune v2 plus each new idea alone, then all together; score on check seasons."""
    base = dict(model.load_params(sport)["ratings"])
    base_names = TUNED + TUNED_EXTRA[sport]
    check = PERIODS[sport]["check"]
    variants = [("v2 (none of the new ideas)", [])] + [(k, v) for k, v in NFL_V3_FEATURES.items()] \
        + [("all four together", sum(NFL_V3_FEATURES.values(), []))]
    results = []
    for label, feats in variants:
        print(f"\n--- tuning: {label} ---")
        start = dict(base, **{f: model.NFL_V3_START[f] for f in feats})
        params = tune(games, sport, base_names + feats, start) if feats else base
        preds, _ = model.walk_forward(games, params, sport)
        rows = [(preds[g["id"]][2], int(g["home_score"] > g["away_score"]))
                for g in games if in_period(g, check) and g["home_score"] != g["away_score"]]
        results.append((label, period_log_loss(games, preds, PERIODS[sport]["tune"]),
                        log_loss(rows), brier(rows), {f: params[f] for f in feats}))
    print("\n===== Each idea on the check seasons (before calibration; lower is better) =====")
    print(f"{'variant':<30} {'tune LL':>8} {'check LL':>9} {'check Brier':>12}   tuned settings")
    for label, tl, cl, cb, fp in results:
        print(f"{label:<30} {tl:8.4f} {cl:9.4f} {cb:12.4f}   {json.dumps(fp)}")


# ---------- reporting ----------

def report(games, preds, market, sport, period_name, cal):
    period = PERIODS[sport][period_name]
    pg = [g for g in games if in_period(g, period)]
    decided = [g for g in pg if g["home_score"] != g["away_score"]]
    rows = [(calibrate(preds[g["id"]][2], cal), int(g["home_score"] > g["away_score"])) for g in decided]

    tune_period = PERIODS[sport]["tune"]
    tune_games = [g for g in games if in_period(g, tune_period) and g["home_score"] != g["away_score"]]
    home_rate = sum(g["home_score"] > g["away_score"] for g in tune_games) / len(tune_games)
    base_rows = [(home_rate, y) for _, y in rows]

    out = {"period": f"{period[0]}-{period[1]}", "games": len(pg), "ties": len(pg) - len(decided),
           "model_brier": brier(rows), "model_log_loss": log_loss(rows),
           "baseline_brier": brier(base_rows), "baseline_log_loss": log_loss(base_rows)}

    print(f"\n===== {sport.upper()} {period_name} seasons {out['period']}: "
          f"{len(pg)} games ({out['ties']} ties left out) =====")
    print("                          Brier    log loss   (lower is better)")
    print(f"  Model                   {out['model_brier']:.4f}   {out['model_log_loss']:.4f}")
    print(f"  Home team always {home_rate:.0%}   {out['baseline_brier']:.4f}   "
          f"{out['baseline_log_loss']:.4f}   (no-skill baseline)")

    mk = [(g, market[g["id"]]) for g in decided if market.get(g["id"], {}).get("p_home") is not None]
    if mk:
        m_rows = [(calibrate(preds[g["id"]][2], cal), int(g["home_score"] > g["away_score"])) for g, _ in mk]
        k_rows = [(m["p_home"], int(g["home_score"] > g["away_score"])) for g, m in mk]
        out.update(market_games=len(mk), model_brier_vs_mkt=brier(m_rows),
                   model_log_loss_vs_mkt=log_loss(m_rows), market_brier=brier(k_rows),
                   market_log_loss=log_loss(k_rows))
        print(f"  On the {len(mk)} games with moneylines:")
        print(f"    Model                 {out['model_brier_vs_mkt']:.4f}   {out['model_log_loss_vs_mkt']:.4f}")
        print(f"    Market (no-vig)       {out['market_brier']:.4f}   {out['market_log_loss']:.4f}")

    print("\n  Calibration: when the model gave the home team...")
    print("    range      games   model avg   home won")
    cal_rows = []
    for lo in range(0, 100, 10):
        b = [(p, y) for p, y in rows if lo / 100 <= p < (lo + 10) / 100 or (lo == 90 and p == 1)]
        if b:
            avg_p, won = sum(p for p, _ in b) / len(b), sum(y for _, y in b) / len(b)
            cal_rows.append([lo, len(b), round(avg_p, 4), round(won, 4)])
            print(f"    {lo:2d}-{lo + 10:3d}%   {len(b):6d}   {avg_p:8.1%}   {won:8.1%}")
    out["calibration"] = cal_rows

    # Flagged bets: model edge vs no-vig market at or above the threshold, 1 unit each
    w = l = push = 0
    units = 0.0
    for g, m in mk + [(g, market[g["id"]]) for g in pg if g["home_score"] == g["away_score"]
                      and market.get(g["id"], {}).get("p_home") is not None]:
        p = calibrate(preds[g["id"]][2], cal)
        for side, edge, dec, won in (("home", p - m["p_home"], m["dec_home"], g["home_score"] > g["away_score"]),
                                     ("away", m["p_home"] - p, m["dec_away"], g["away_score"] > g["home_score"])):
            if edge >= config.EDGE_THRESHOLD:
                if g["home_score"] == g["away_score"]:
                    push += 1
                elif won:
                    w += 1
                    units += dec - 1
                else:
                    l += 1
                    units -= 1
    bets = w + l + push
    out.update(flagged_bets=bets, wins=w, losses=l, pushes=push, units=round(units, 2),
               roi=round(units / bets, 4) if bets else None)
    print(f"\n  Flagged bets (edge >= {config.EDGE_THRESHOLD:.0%}): {bets} bets, "
          f"{w}-{l}" + (f"-{push}" if push else "") +
          (f", {units:+.1f} units, ROI {units / bets:+.1%}" if bets else ""))

    sc = [(g, market.get(g["id"], {})) for g in pg]
    mae_margin = sum(abs((preds[g["id"]][0] - preds[g["id"]][1]) - (g["home_score"] - g["away_score"]))
                     for g, _ in sc) / len(sc)
    mae_total = sum(abs((preds[g["id"]][0] + preds[g["id"]][1]) - (g["home_score"] + g["away_score"]))
                    for g, _ in sc) / len(sc)
    out.update(model_margin_mae=round(mae_margin, 2), model_total_mae=round(mae_total, 2))
    print(f"\n  Projected score, average miss: margin {mae_margin:.1f} pts, total {mae_total:.1f} pts")
    sp = [(g, m) for g, m in sc if m.get("margin") is not None and m.get("total") is not None]
    if sp:
        mm = sum(abs(m["margin"] - (g["home_score"] - g["away_score"])) for g, m in sp) / len(sp)
        mt = sum(abs(m["total"] - (g["home_score"] + g["away_score"])) for g, m in sp) / len(sp)
        out.update(market_margin_mae=round(mm, 2), market_total_mae=round(mt, 2))
        print(f"  Market spread/total, average miss: margin {mm:.1f} pts, total {mt:.1f} pts "
              f"({len(sp)} games)")
    return out


def refit(conn, games, market, sport):
    """After the final exam: refit the same design on every season, for live use.
    No seasons are left untouched, so this version is judged on live results only.
    No separate calibration correction: sigma is tuned on all seasons instead."""
    old = model.load_params(sport)
    ratings = tune(games, sport, start=old["ratings"], period_name="all")
    preds, _ = model.walk_forward(games, ratings, sport)
    comb = None
    if old.get("combiner"):
        names = old["combiner"]["features"]
        comb = combiner.fit(combiner_rows(conn, games, preds, sport, PERIODS[sport]["all"]), names)
        print(f"\nCombiner refit on all seasons: "
              + ", ".join(f"{n} {c:+.3f}" for n, c in zip(["const"] + names, comb["coef"])))
        preds = combiner.apply(conn, games, preds, comb, sport, ratings["sigma"])
    cal = {"a": 1.0, "b": 0.0}
    base_version = old["version"].rsplit("-", 1)[0].replace("-refit", "")
    saved = json.loads(model.PARAMS_PATH.read_text())
    saved[sport] = {"version": f"{base_version}-refit-{datetime.now(timezone.utc):%Y%m%d}",
                    "ratings": ratings, "combiner": comb, "calibration": cal,
                    "fit_seasons": PERIODS[sport]["all"],
                    "note": "Refit on all seasons after the final exam; judged on live results only."}
    model.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
    print(f"Saved settings to {model.PARAMS_PATH.name} as {saved[sport]['version']}:")
    print("  " + json.dumps(ratings))
    print("\n(In-sample report below: these seasons were used for fitting, so it is NOT a test.)")
    report(games, preds, market, sport, "all", cal)


# ---------- main ----------

def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("tune", "check", "final", "ablate", "refit") or sys.argv[2] not in PERIODS:
        sys.exit(__doc__)
    mode, sport = sys.argv[1], sys.argv[2]
    conn = db.connect()
    games = model.load_games(conn, sport)
    market = market_by_game(conn, sport)

    if mode == "ablate":
        if sport == "ncaaf":
            ablate_combiner(conn, games, sport)
        else:
            ablate(games, sport)
        return

    if mode == "refit":
        refit(conn, games, market, sport)
        return

    if mode == "tune":
        ratings = tune(games, sport)
        preds, _ = model.walk_forward(games, ratings, sport)
        comb = None
        if COMBINER_SET[sport]:
            names = combiner.FEATURE_SETS[COMBINER_SET[sport]]
            comb = combiner.fit(combiner_rows(conn, games, preds, sport, PERIODS[sport]["tune"]), names)
            print(f"\nCombiner ({COMBINER_SET[sport]}) fit on tune seasons: "
                  + ", ".join(f"{n} {c:+.3f}" for n, c in zip(["const"] + names, comb["coef"])))
            preds = combiner.apply(conn, games, preds, comb, sport, ratings["sigma"])
        check = PERIODS[sport]["check"]
        check_rows = [(preds[g["id"]][2], int(g["home_score"] > g["away_score"]))
                      for g in games if in_period(g, check) and g["home_score"] != g["away_score"]]
        cal = fit_calibration(check_rows)
        before = log_loss(check_rows)
        after = log_loss([(calibrate(p, cal), y) for p, y in check_rows])
        print(f"\nCalibration fit on check seasons: a={cal['a']}, b={cal['b']} "
              f"(log loss {before:.4f} -> {after:.4f})")
        if before - after < 0.002:
            cal = {"a": 1.0, "b": 0.0}
            print("  Improvement too small to be worth it; no calibration correction applied.")
        saved = json.loads(model.PARAMS_PATH.read_text()) if model.PARAMS_PATH.exists() else {}
        number = int(saved[sport]["version"].split("-v")[1].split("-")[0]) + 1 if sport in saved else 1
        saved[sport] = {"version": f"{sport}-v{number}-{datetime.now(timezone.utc):%Y%m%d}",
                        "ratings": ratings, "combiner": comb, "calibration": cal,
                        "tune_seasons": PERIODS[sport]["tune"], "check_seasons": check}
        model.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
        print(f"Saved settings to {model.PARAMS_PATH.name} as {saved[sport]['version']}:")
        print("  " + json.dumps(ratings))

    params = model.load_params(sport)
    cal = params.get("calibration", {"a": 1.0, "b": 0.0})
    preds, _ = model.walk_forward(games, params["ratings"], sport)
    if params.get("combiner"):
        preds = combiner.apply(conn, games, preds, params["combiner"], sport, params["ratings"]["sigma"])

    if mode in ("tune", "check"):
        report(games, preds, market, sport, "tune", cal)
        report(games, preds, market, sport, "check", cal)
        return

    RESULTS_DIR.mkdir(exist_ok=True)
    log_path = RESULTS_DIR / "final_runs.jsonl"
    earlier = [json.loads(l) for l in log_path.read_text().splitlines()] if log_path.exists() else []
    earlier = [e for e in earlier if e["sport"] == sport]
    if earlier:
        print(f"WARNING: the {sport} final exam has been run {len(earlier)} time(s) before "
              f"(versions: {', '.join(e['version'] for e in earlier)}). If settings changed "
              "after seeing those results, these seasons are no longer untouched.")
    result = report(games, preds, market, sport, "final", cal)
    with log_path.open("a") as f:
        f.write(json.dumps({"sport": sport, "version": params["version"],
                            "run_at_utc": db.to_utc(datetime.now(timezone.utc)),
                            "ratings": params["ratings"], "combiner": params.get("combiner"),
                            "calibration": cal,
                            "result": result}) + "\n")
    print(f"\nRecorded in {log_path.relative_to(Path(__file__).parent)}")


if __name__ == "__main__":
    main()

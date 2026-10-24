"""Backtest the club soccer model (criteria: backtest_results/criteria_soccer.md).

Usage:
  python3 backtest_soccer.py tune      tune settings on the tune seasons, save them, report tune + check
  python3 backtest_soccer.py check     report tune + check seasons with the saved settings
  python3 backtest_soccer.py ablate    test the pre-registered ideas one at a time
  python3 backtest_soccer.py final     the ONE-TIME final exam (recorded in final_runs.jsonl)
  python3 backtest_soccer.py refit     refit on all seasons for live use (after the final exam)
  python3 backtest_soccer.py xg        the pre-registered xG test (plans/soccer_xg.md): xg_w tuned with the base
                                       settings on the tune seasons, kept only if better on both tune and check

Graded games: Big 5 leagues only. Second divisions feed the ratings but aren't graded.
"""

import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import db
import soccer_model as sm
from odds_math import decimal_odds, no_vig

PERIODS = {"tune": (2013, 2019), "check": (2020, 2022), "final": (2023, 2026)}
TUNED = ["k", "k_lg", "regress", "cap", "promo_gap", "new_team", "rho", "home_start"]
IDEAS = {"#1 shots on target": ["sot_w"], "#2 ClubElo ratings": ["elo_w"], "#3 rest days": ["rest_coef"]}
EDGE = 0.04
RESULTS_DIR = Path(__file__).parent / "backtest_results"


def outcome(g):
    return 0 if g["home_score"] > g["away_score"] else 1 if g["home_score"] == g["away_score"] else 2


def graded(g, period):
    return g["league"] in sm.BIG5 and period[0] <= g["season"] <= period[1]


def scores(rows):
    """rows: [(probs (h, d, a), outcome index)] -> (log loss, Brier, RPS)."""
    n = len(rows)
    ll = sum(-math.log(max(p[y], 1e-12)) for p, y in rows) / n
    br = sum(sum((p[i] - (i == y)) ** 2 for i in range(3)) for p, y in rows) / n
    rps = sum(((p[0] - (y == 0)) ** 2 + (p[0] + p[1] - (y <= 1)) ** 2) / 2 for p, y in rows) / n
    return ll, br, rps


def market(conn):
    """{hist game id: {provider: (home, draw, away) no-vig probabilities, '<provider> dec': decimal odds}}"""
    out = defaultdict(dict)
    for r in conn.execute("SELECT o.* FROM hist_odds o JOIN hist_games g ON g.id = o.hist_game_id"
                          " WHERE g.sport = 'soccer_club' AND o.draw_ml IS NOT NULL"):
        out[r["hist_game_id"]][r["provider"]] = no_vig(r["home_ml"], r["draw_ml"], r["away_ml"])
        out[r["hist_game_id"]][r["provider"] + " dec"] = tuple(decimal_odds(m) for m in (r["home_ml"], r["draw_ml"], r["away_ml"]))
    return out


def period_log_loss(games, preds, period):
    return scores([(preds[g["id"]][:3], outcome(g)) for g in games if graded(g, period)])[0]


def run(games, params, elo=None, periods=("tune", "check", "final")):
    keep = lambda g: g["league"] in sm.BIG5 and any(PERIODS[p][0] <= g["season"] <= PERIODS[p][1] for p in periods)
    return sm.walk_forward(games, params, elo, keep)[0]


def tune(games, start, names, elo=None):
    params = dict(start)
    score = lambda p: period_log_loss(games, run(games, p, elo, ("tune",)), PERIODS["tune"])
    best = score(params)
    print(f"Starting log loss on tune seasons: {best:.4f}", flush=True)
    for factors in ([0.5, 0.75, 1.33, 2.0], [0.85, 0.93, 1.07, 1.18], [0.96, 1.04]):
        improved = True
        while improved:
            improved = False
            for name in names:
                for f in factors:
                    trial = dict(params)
                    trial[name] = params[name] * f if params[name] else 0.01 * f
                    if name == "regress":
                        trial[name] = min(trial[name], 1.0)
                    s = score(trial)
                    if s < best - 1e-6:
                        best, params, improved = s, trial, True
        print(f"  after step size {factors}: log loss {best:.4f}", flush=True)
    return {k: round(v, 5) if isinstance(v, float) else v for k, v in params.items()}


def baseline(games):
    """Each league's home/draw/away frequencies on the tune seasons."""
    counts = defaultdict(lambda: [0, 0, 0])
    for g in games:
        if graded(g, PERIODS["tune"]):
            counts[g["league"]][outcome(g)] += 1
    return {lg: tuple(c / sum(v) for c in v) for lg, v in counts.items()}


def report(games, preds, mkt, period_name):
    period = PERIODS[period_name]
    gs = [g for g in games if graded(g, period)]
    base = baseline(games)
    rows = [(preds[g["id"]][:3], outcome(g)) for g in gs]
    m_ll, m_br, m_rps = scores(rows)
    b_ll, b_br, b_rps = scores([(base[g["league"]], outcome(g)) for g in gs])
    print(f"\n===== {period_name} seasons {period[0] - 1}-{period[0] % 100:02d} to {period[1] - 1}-{period[1] % 100:02d}:"
          f" {len(gs)} Big 5 games =====")
    print(f"{'':28}{'log loss':>10}{'Brier':>9}{'RPS':>9}")
    print(f"{'model':28}{m_ll:>10.4f}{m_br:>9.4f}{m_rps:>9.4f}")
    print(f"{'baseline (league rates)':28}{b_ll:>10.4f}{b_br:>9.4f}{b_rps:>9.4f}")
    result = {"period": f"{period[0]}-{period[1]}", "games": len(gs), "model_log_loss": m_ll, "model_brier": m_br,
              "model_rps": m_rps, "baseline_log_loss": b_ll, "baseline_brier": b_br, "baseline_rps": b_rps}

    for prov, label in (("Market average (close)", "market avg close"), ("Pinnacle (close)", "Pinnacle close")):
        same = [g for g in gs if prov in mkt.get(g["id"], {})]
        if not same:
            continue
        mo = scores([(preds[g["id"]][:3], outcome(g)) for g in same])
        mk = scores([(mkt[g["id"]][prov], outcome(g)) for g in same])
        print(f"  vs {label} ({len(same)} games): model {mo[0]:.4f} / {mo[1]:.4f} / {mo[2]:.4f}   "
              f"market {mk[0]:.4f} / {mk[1]:.4f} / {mk[2]:.4f}")
        key = "market_avg_close" if prov.startswith("Market") else "pinnacle_close"
        result[key] = {"games": len(same), "model": mo, "market": mk}

    # calibration per outcome
    worst = 0.0
    result["calibration"] = {}
    for i, name in enumerate(("home", "draw", "away")):
        buckets = defaultdict(list)
        for p, y in rows:
            buckets[min(int(p[i] * 10), 9)].append((p[i], int(y == i)))
        cal = []
        for b in sorted(buckets):
            v = buckets[b]
            avg_p, hit = sum(x for x, _ in v) / len(v), sum(y for _, y in v) / len(v)
            cal.append([b * 10, len(v), round(avg_p, 4), round(hit, 4)])
            if len(v) >= 50:
                worst = max(worst, abs(avg_p - hit))
        result["calibration"][name] = cal
        print(f"  calibration {name:<5}: " + "  ".join(f"{c[0]}%:{c[1]} pred {c[2]:.2f} real {c[3]:.2f}" for c in cal if c[1] >= 50))
    result["worst_calibration_gap"] = worst
    print(f"  worst gap in a bucket with 50+ games: {worst * 100:.1f} points")

    # flagged bets at the pre-close market average
    bets = wins = 0
    units = clv = 0.0
    clv_n = 0
    for g in gs:
        m = mkt.get(g["id"], {})
        if "Market average" not in m:
            continue
        p = preds[g["id"]][:3]
        edges = [p[i] - m["Market average"][i] for i in range(3)]
        i = max(range(3), key=lambda k: edges[k])
        if edges[i] < EDGE:
            continue
        bets += 1
        won = outcome(g) == i
        wins += won
        units += (m["Market average dec"][i] - 1) if won else -1
        if "Market average (close)" in m:
            clv += m["Market average (close)"][i] - m["Market average"][i]
            clv_n += 1
    roi = units / bets if bets else 0.0
    print(f"  flagged bets (edge >= {EDGE:.0%} vs pre-close average): {bets}, won {wins}, "
          f"units {units:+.1f}, ROI {roi:+.1%}" + (f", avg CLV {clv / clv_n * 100:+.2f} pts ({clv_n} with a close)" if clv_n else ""))
    result.update({"flagged_bets": bets, "wins": wins, "units": round(units, 2), "roi": round(roi, 4),
                   "avg_clv": round(clv / clv_n, 5) if clv_n else None})
    return result


def save_params(ratings, note, fit_seasons=None):
    saved = json.loads(sm.PARAMS_PATH.read_text())
    old = saved.get("soccer_club")
    number = int(old["version"].split("-v")[1].split("-")[0]) + (0 if fit_seasons else 1) if old else 1
    stamp = f"{datetime.now(timezone.utc):%Y%m%d}"
    version = f"soccer-v{number}-refit-{stamp}" if fit_seasons else f"soccer-v{number}-{stamp}"
    entry = {"version": version, "ratings": ratings, "note": note}
    if fit_seasons:
        entry["fit_seasons"] = fit_seasons
    else:
        entry.update({"tune_seasons": PERIODS["tune"], "check_seasons": PERIODS["check"]})
    saved["soccer_club"] = entry
    sm.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
    print(f"Saved settings to {sm.PARAMS_PATH.name} as {version}:\n  {json.dumps(ratings)}")


def ablate(games, mkt, base_params, elo=None):
    base_preds = run(games, base_params, elo, ("tune", "check"))
    base_t, base_c = (period_log_loss(games, base_preds, PERIODS[p]) for p in ("tune", "check"))
    print(f"Base model: tune {base_t:.4f}, check {base_c:.4f}")
    kept = {}
    for idea, names in IDEAS.items():
        if idea.startswith("#2") and not elo:
            print(f"\n{idea}: skipped (no ClubElo data loaded)")
            continue
        print(f"\n{idea}: tuning {names} (plus the base settings) on the tune seasons")
        p = tune(games, base_params, TUNED + names, elo)
        preds = run(games, p, elo, ("tune", "check"))
        t, c = (period_log_loss(games, preds, PERIODS[x]) for x in ("tune", "check"))
        keep = t < base_t and c < base_c
        print(f"  {idea}: tune {t:.4f} ({t - base_t:+.4f}), check {c:.4f} ({c - base_c:+.4f}) -> "
              f"{'KEEP (better on both)' if keep else 'drop'}; settings {', '.join(f'{n}={p[n]}' for n in names)}")
        if keep:
            kept[idea] = p
    return kept


def pre_exam_settings():
    """The soccer settings the final exam ran with (tune seasons only): the base for later ideas."""
    for line in (RESULTS_DIR / "final_runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["sport"] == "soccer_club":
            return dict(r["ratings"])
    raise RuntimeError("soccer exam record not found")


def xg_test(games, mkt):
    """plans/soccer_xg.md: tune xg_w (with the base settings and sot_w) on the tune seasons; keep only if log
    loss is better on both tune and check and no per-outcome calibration bucket (50+ games) is off by 8+ points."""
    base = pre_exam_settings()
    base_preds = run(games, base, None, ("tune", "check"))
    bt, bc = (period_log_loss(games, base_preds, PERIODS[x]) for x in ("tune", "check"))
    print(f"Base (pre-exam soccer settings): tune {bt:.4f}, check {bc:.4f}")
    p = tune(games, {**base, "xg_w": 0.0}, TUNED + ["sot_w", "xg_w"])
    preds = run(games, p, None, ("tune", "check", "final"))
    t, c = (period_log_loss(games, preds, PERIODS[x]) for x in ("tune", "check"))
    base_check = report(games, base_preds, mkt, "check")
    chk = report(games, preds, mkt, "check")
    keep = t < bt and c < bc and chk["worst_calibration_gap"] <= 0.08
    lines = [f"\n## xG test {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC (plans/soccer_xg.md)\n",
             f"Base (pre-exam settings): tune {bt:.4f}, check {bc:.4f}, check RPS {base_check['model_rps']:.4f}, worst calibration "
             f"{base_check['worst_calibration_gap'] * 100:.1f}, flagged {base_check['flagged_bets']} ROI {base_check['roi']:+.1%}.",
             f"With xG: xg_w {p['xg_w']}, sot_w {p['sot_w']} -> tune {t:.4f} ({t - bt:+.4f}), check {c:.4f} ({c - bc:+.4f}), "
             f"check RPS {chk['model_rps']:.4f}, worst calibration {chk['worst_calibration_gap'] * 100:.1f}, "
             f"flagged {chk['flagged_bets']} ROI {chk['roi']:+.1%}"
             + (f", avg CLV {chk['avg_clv'] * 100:+.2f} pts" if chk.get("avg_clv") is not None else "") + ".",
             f"Market (avg close) on check games: {json.dumps(chk.get('market_avg_close'))}",
             f"Decision: {'KEEP (better on both, calibrated)' if keep else 'drop'}.",
             f"Settings: {json.dumps(p)}"]
    if keep:
        fin_b = report(games, run(games, base, None, ("final",)), mkt, "final")
        fin = report(games, preds, mkt, "final")
        lines.append(f"Second look on the exam seasons (already used once, NOT an untouched test): log loss "
                     f"{fin_b['model_log_loss']:.4f} -> {fin['model_log_loss']:.4f}, RPS {fin_b['model_rps']:.4f} -> "
                     f"{fin['model_rps']:.4f}, flagged ROI {fin_b['roi']:+.1%} -> {fin['roi']:+.1%}.")
        (RESULTS_DIR / "soccer_xg_best.json").write_text(json.dumps(p, indent=2) + "\n")
    path = RESULTS_DIR / "soccer_xg.md"
    if not path.exists():
        path.write_text("# Soccer xG test\n\nPlan: `plans/soccer_xg.md`. Produced by `backtest_soccer.py xg`.\n")
    path.write_text(path.read_text() + "\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    modes = ("tune", "check", "ablate", "final", "refit", "xg")
    if len(sys.argv) < 2 or sys.argv[1] not in modes:
        sys.exit(__doc__)
    mode = sys.argv[1]
    conn = db.connect()
    games = sm.load_games(conn)
    mkt = market(conn)
    elo = None
    if "--elo" in sys.argv or mode in ("final", "refit") and sm.load_params()["ratings"].get("elo_w"):
        import clubelo
        elo = clubelo.ratings_for_games(conn, games)

    if mode == "xg":
        xg_test(games, mkt)
        return
    if mode == "tune":
        ratings = tune(games, sm.DEFAULT_PARAMS, TUNED)
        save_params(ratings, "Tuned on 2013-2019 Big 5 seasons; ideas off.")
    params = sm.load_params()["ratings"]

    if mode in ("tune", "check"):
        preds = run(games, params, elo, ("tune", "check"))
        report(games, preds, mkt, "tune")
        report(games, preds, mkt, "check")
    elif mode == "ablate":
        ablate(games, mkt, params, elo)
    elif mode == "final":
        log_path = RESULTS_DIR / "final_runs.jsonl"
        earlier = [json.loads(l) for l in log_path.read_text().splitlines()] if log_path.exists() else []
        earlier = [e for e in earlier if e["sport"] == "soccer_club"]
        if earlier:
            print(f"WARNING: the soccer final exam has been run {len(earlier)} time(s) before "
                  f"(versions: {', '.join(e['version'] for e in earlier)}). If settings changed after "
                  "seeing those results, these seasons are no longer untouched.")
        preds = run(games, params, elo, ("final",))
        result = report(games, preds, mkt, "final")
        with log_path.open("a") as f:
            f.write(json.dumps({"sport": "soccer_club", "version": sm.load_params()["version"],
                                "run_at_utc": db.to_utc(datetime.now(timezone.utc)),
                                "ratings": params, "result": result}) + "\n")
        print(f"\nRecorded in {log_path.relative_to(Path(__file__).parent)}")
    elif mode == "refit":
        fit = {**PERIODS, "tune": (2013, 2026)}
        PERIODS["tune"] = fit["tune"]
        names = [n for n in TUNED + [x for v in IDEAS.values() for x in v] if params.get(n)]
        ratings = tune(games, params, names, elo)
        save_params(ratings, "Refit on all seasons after the final exam; judged on live results only.",
                    fit_seasons=[2013, 2026])


if __name__ == "__main__":
    main()

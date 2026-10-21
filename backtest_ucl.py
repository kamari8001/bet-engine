"""Backtest the Champions League model (criteria: backtest_results/criteria_ucl.md).

Usage:
  python3 backtest_ucl.py tune      tune the European settings on 2016-2019, save them, report tune + check
  python3 backtest_ucl.py check     report tune + check seasons with the saved settings
  python3 backtest_ucl.py ablate    test the pre-registered ideas one at a time
  python3 backtest_ucl.py final     the ONE-TIME final exam (recorded in final_runs.jsonl)
  python3 backtest_ucl.py refit     refit the European settings on all seasons for live use

Domestic ratings use the club soccer settings tuned BEFORE the soccer final exam (soccer-v2-20261019,
read from final_runs.jsonl), so nothing here was tuned with knowledge of the exam seasons. Only the
European settings (eu_*) are tuned. Graded: Champions League main-competition games.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import db
import soccer_model as sm
from backtest_soccer import scores
from odds_math import decimal_odds, is_pregame_sportsbook, no_vig

PERIODS = {"tune": (2016, 2019), "check": (2020, 2022), "final": (2023, 2026)}
TUNED = ["eu_k_s", "eu_k_lg", "eu_home_start"]
IDEAS = {"#1 club ratings learn from European games": ["eu_k_team"],
         "#2 league strengths shrink between seasons": ["eu_regress_s"]}
EDGE = 0.04
RESULTS_DIR = Path(__file__).parent / "backtest_results"
GRADED = "Champions League"


def domestic_params():
    """The soccer settings tuned before the soccer final exam (no knowledge of 2023-2026)."""
    for line in (RESULTS_DIR / "final_runs.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["sport"] == "soccer_club":
            return r["ratings"]
    raise RuntimeError("soccer final exam record not found in final_runs.jsonl")


def outcome(g):
    return 0 if g["home_score"] > g["away_score"] else 1 if g["home_score"] == g["away_score"] else 2


def graded(g, period):
    return g["league"] == GRADED and period[0] <= g["season"] <= period[1]


def market(conn):
    """{hist game id: {"p": no-vig (home, draw, away) averaged over real books, "dec": average decimal odds}}"""
    rows = defaultdict(list)
    for r in conn.execute("SELECT o.* FROM hist_odds o JOIN hist_games g ON g.id = o.hist_game_id"
                          " WHERE g.league = ? AND o.draw_ml IS NOT NULL", (GRADED,)):
        if is_pregame_sportsbook(r["provider"]):
            rows[r["hist_game_id"]].append(r)
    out = {}
    for gid, rs in rows.items():
        fair = [no_vig(r["home_ml"], r["draw_ml"], r["away_ml"]) for r in rs]
        out[gid] = {"p": tuple(sum(f[i] for f in fair) / len(fair) for i in range(3)),
                    "dec": tuple(sum(decimal_odds(r[k]) for r in rs) / len(rs) for k in ("home_ml", "draw_ml", "away_ml")),
                    "books": len(rs)}
    return out


def run(games, params, periods=("tune", "check", "final")):
    keep = lambda g: g["league"] == GRADED and any(PERIODS[p][0] <= g["season"] <= PERIODS[p][1] for p in periods)
    return sm.walk_forward(games, params, keep=keep)[0]


def period_log_loss(games, preds, period):
    rows = [(preds[g["id"]][:3], outcome(g)) for g in games if graded(g, period) and g["id"] in preds]
    return scores(rows)[0]


def tune(games, start, names):
    params = dict(start)
    score = lambda p: period_log_loss(games, run(games, p, ("tune",)), PERIODS["tune"])
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
                    if name == "eu_regress_s":
                        trial[name] = min(trial[name], 1.0)
                    s = score(trial)
                    if s < best - 1e-6:
                        best, params, improved = s, trial, True
        print(f"  after step size {factors}: log loss {best:.4f}", flush=True)
    return params


def report(games, preds, mkt, period_name):
    period = PERIODS[period_name]
    gs = [g for g in games if graded(g, period) and g["id"] in preds]
    rows = [(preds[g["id"]][:3], outcome(g)) for g in gs]
    tune_gs = [g for g in games if graded(g, PERIODS["tune"])]
    base = tuple(sum(outcome(g) == i for g in tune_gs) / len(tune_gs) for i in range(3))
    m, b = scores(rows), scores([(base, outcome(g)) for g in gs])
    print(f"\n===== {period_name} seasons {period[0] - 1}-{period[0] % 100:02d} to {period[1] - 1}-{period[1] % 100:02d}: "
          f"{len(gs)} Champions League games =====")
    print(f"{'':28}{'log loss':>10}{'Brier':>9}{'RPS':>9}")
    print(f"{'model':28}{m[0]:>10.4f}{m[1]:>9.4f}{m[2]:>9.4f}")
    print(f"{'baseline (UCL rates)':28}{b[0]:>10.4f}{b[1]:>9.4f}{b[2]:>9.4f}")
    result = {"period": f"{period[0]}-{period[1]}", "games": len(gs), "model": m, "baseline": b}
    same = [g for g in gs if g["id"] in mkt]
    if same:
        mo = scores([(preds[g["id"]][:3], outcome(g)) for g in same])
        mk = scores([(mkt[g["id"]]["p"], outcome(g)) for g in same])
        print(f"  vs market ({len(same)} games): model {mo[0]:.4f} / {mo[1]:.4f} / {mo[2]:.4f}   "
              f"market {mk[0]:.4f} / {mk[1]:.4f} / {mk[2]:.4f}")
        result["market"] = {"games": len(same), "model": mo, "market": mk}
    worst = 0.0
    result["calibration"] = {}
    for i, name in enumerate(("home", "draw", "away")):
        buckets = defaultdict(list)
        for p, y in rows:
            buckets[min(int(p[i] * 10), 9)].append((p[i], int(y == i)))
        cal = []
        for k in sorted(buckets):
            v = buckets[k]
            ap, hit = sum(x for x, _ in v) / len(v), sum(z for _, z in v) / len(v)
            cal.append([k * 10, len(v), round(ap, 4), round(hit, 4)])
            if len(v) >= 50:
                worst = max(worst, abs(ap - hit))
        result["calibration"][name] = cal
        print(f"  calibration {name:<5}: " + "  ".join(f"{c[0]}%:{c[1]} pred {c[2]:.2f} real {c[3]:.2f}" for c in cal if c[1] >= 20))
    result["worst_calibration_gap"] = worst
    print(f"  worst gap in a bucket with 50+ games: {worst * 100:.1f} points")
    bets = wins = 0
    units = 0.0
    for g in same:
        p, mp = preds[g["id"]][:3], mkt[g["id"]]
        edges = [p[i] - mp["p"][i] for i in range(3)]
        i = max(range(3), key=lambda k: edges[k])
        if edges[i] < EDGE:
            continue
        bets += 1
        won = outcome(g) == i
        wins += won
        units += (mp["dec"][i] - 1) if won else -1
    roi = units / bets if bets else 0.0
    print(f"  flagged bets (edge >= {EDGE:.0%}, one per game, average price): {bets}, won {wins}, units {units:+.1f}, ROI {roi:+.1%}")
    result.update({"flagged_bets": bets, "wins": wins, "units": round(units, 2), "roi": round(roi, 4)})
    return result


def domestic_unchanged(games_eu, params):
    """Big 5 domestic predictions with European games loaded must equal those without (when club
    ratings don't learn from European games). Returns True/False."""
    import backtest_soccer as bs
    conn = db.connect()
    dom = sm.load_games(conn)
    a = bs.run(dom, params, None, ("tune", "check"))
    b = sm.walk_forward(games_eu, params, keep=lambda g: g["league"] in sm.BIG5 and 2013 <= g["season"] <= 2022)[0]
    return all(abs(a[k][i] - b[k][i]) < 1e-12 for k in a for i in range(3))


def save(eu, note, fit=None):
    saved = json.loads(sm.PARAMS_PATH.read_text())
    old = saved["soccer_club"].get("europe")
    number = int(old["version"].split("-v")[1].split("-")[0]) + (0 if fit else 1) if old else 1
    stamp = f"{datetime.now(timezone.utc):%Y%m%d}"
    entry = {"version": f"ucl-v{number}{'-refit' if fit else ''}-{stamp}",
             "settings": {k: round(v, 5) if isinstance(v, float) else v for k, v in eu.items()}, "note": note}
    if fit:
        entry["fit_seasons"] = fit
    saved["soccer_club"]["europe"] = entry
    sm.PARAMS_PATH.write_text(json.dumps(saved, indent=2) + "\n")
    print(f"Saved European settings as {entry['version']}: {json.dumps(entry['settings'])}")


def main():
    modes = ("tune", "check", "ablate", "final", "refit")
    if len(sys.argv) < 2 or sys.argv[1] not in modes:
        sys.exit(__doc__)
    mode = sys.argv[1]
    conn = db.connect()
    games = sm.load_games(conn, include_europe=True)
    mkt = market(conn)
    dom = domestic_params()
    if mode == "tune":
        start = {**dom, **sm.EU_DEFAULTS}
        p = tune(games, start, TUNED)
        save({k: p[k] for k in sm.EU_DEFAULTS}, "Tuned on 2016-2019 Champions League games; ideas off.")
    europe = json.loads(sm.PARAMS_PATH.read_text())["soccer_club"].get("europe")
    if europe is None:
        sys.exit("No European settings yet: run `python3 backtest_ucl.py tune` first.")
    params = {**dom, **europe["settings"]}
    if mode in ("tune", "check"):
        preds = run(games, params, ("tune", "check"))
        report(games, preds, mkt, "tune")
        report(games, preds, mkt, "check")
        print("\nDomestic Big 5 predictions unchanged by European games:", domestic_unchanged(games, params))
    elif mode == "ablate":
        preds = run(games, params, ("tune", "check"))
        base_t, base_c = (period_log_loss(games, preds, PERIODS[x]) for x in ("tune", "check"))
        print(f"Base: tune {base_t:.4f}, check {base_c:.4f}")
        for idea, names in IDEAS.items():
            print(f"\n{idea}: tuning {names} (plus the European settings) on the tune seasons")
            p = tune(games, params, TUNED + names)
            pr = run(games, p, ("tune", "check"))
            t, c = (period_log_loss(games, pr, PERIODS[x]) for x in ("tune", "check"))
            keep = t < base_t and c < base_c
            if keep and idea.startswith("#1"):
                import backtest_soccer as bs
                d0 = bs.run(sm.load_games(conn), params, None, ("tune", "check"))
                d1 = sm.walk_forward(games, p, keep=lambda g: g["league"] in sm.BIG5 and 2013 <= g["season"] <= 2022)[0]
                dom_games = [g for g in sm.load_games(conn) if g["league"] in sm.BIG5]
                for per in (bs.PERIODS["tune"], bs.PERIODS["check"]):
                    gs = [g for g in dom_games if per[0] <= g["season"] <= per[1]]
                    ll0 = scores([(d0[g["id"]][:3], outcome(g)) for g in gs])[0]
                    ll1 = scores([(d1[g["id"]][:3], outcome(g)) for g in gs])[0]
                    print(f"  Big 5 domestic log loss {per}: {ll0:.4f} -> {ll1:.4f}")
                    keep = keep and ll1 <= ll0
            print(f"  {idea}: tune {t:.4f} ({t - base_t:+.4f}), check {c:.4f} ({c - base_c:+.4f}) -> "
                  f"{'KEEP' if keep else 'drop'}; settings {', '.join(f'{n}={p[n]:.5f}' for n in names)}")
    elif mode == "final":
        log_path = RESULTS_DIR / "final_runs.jsonl"
        earlier = [json.loads(l) for l in log_path.read_text().splitlines()]
        earlier = [e for e in earlier if e["sport"] == "ucl"]
        if earlier:
            print(f"WARNING: the Champions League final exam has been run {len(earlier)} time(s) before.")
        preds = run(games, params, ("final",))
        result = report(games, preds, mkt, "final")
        with log_path.open("a") as f:
            f.write(json.dumps({"sport": "ucl", "version": europe["version"], "domestic": "soccer-v2-20261019",
                                "run_at_utc": db.to_utc(datetime.now(timezone.utc)), "settings": europe["settings"],
                                "result": result}) + "\n")
        print(f"\nRecorded in {log_path.relative_to(Path(__file__).parent)}")
    elif mode == "refit":
        PERIODS["tune"] = (2016, 2026)
        live_dom = sm.load_params()["ratings"]
        names = TUNED + [n for v in IDEAS.values() for n in v if europe["settings"].get(n)]
        p = tune(games, {**live_dom, **europe["settings"]}, names)
        save({k: p[k] for k in sm.EU_DEFAULTS}, "Refit on all seasons (2016-2026) with the live domestic settings "
             "after the final exam; judged on live results only.", fit=[2016, 2026])


if __name__ == "__main__":
    main()

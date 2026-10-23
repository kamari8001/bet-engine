"""Factor study: which pre-game factors predict winning, and which predict the market's errors.

Usage: python3 factor_study.py nfl | ncaaf | nba | ncaab | soccer_club   [--out]

Plan and pass bars: plans/factor_study.md (pre-registered). Read-only: changes no probabilities.
Two ridge logistic regressions per sport, fit on the tune seasons and judged on the check seasons:
  (a) P(home wins) from the factors;
  (b) the same with the market's no-vig home log-odds as a fixed offset: a factor that still earns a
      coefficient is one the market underweights.
Plus forward selection (which factors improve check-season log loss) and a PCA diagnostic.
With --out, appends the sport's report to backtest_results/factor_study.md.
"""

import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import db
import model
from combiner import _solve
from odds_math import no_vig

RIDGE = 1.0            # L2 penalty on standardized coefficients (not the intercept)
MIN_GAIN = 0.001       # check-season log loss improvement a factor must give
MAX_STEPS = 6
RESULTS = Path(__file__).parent / "backtest_results" / "factor_study.md"


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(z):
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


# ---------- feature tables ----------

def recent_form(games, margin_key=lambda g, side: None):
    """Walk the games once: {game id: (home games played this season, away played,
    home last-5 avg margin, away last-5 avg margin)} using only earlier games."""
    played, last5, out = {}, defaultdict(list), {}
    for g in games:
        h, a = g["home_team"], g["away_team"]
        key_h, key_a = (g["season"], h), (g["season"], a)
        lh, la = last5[key_h], last5[key_a]
        out[g["id"]] = (played.get(key_h, 0), played.get(key_a, 0),
                        statistics.mean(lh) if lh else 0.0, statistics.mean(la) if la else 0.0)
        mh = g["home_score"] - g["away_score"]
        last5[key_h] = (lh + [mh])[-5:]
        last5[key_a] = (la + [-mh])[-5:]
        played[key_h] = played.get(key_h, 0) + 1
        played[key_a] = played.get(key_a, 0) + 1
    return out


def ball_table(conn, sport):
    """Rows for football/basketball: {id, season, y, features{}} with walk-forward engine inputs."""
    import combiner
    params = model.load_params(sport)
    games = model.load_games(conn, sport)
    mkt = market_by_game(conn, sport)
    form = recent_form(games)
    # walk forward, capturing the ratings the model had BEFORE each game
    first = games[0]["season"]
    first_season = [g for g in games if g["season"] == first]
    avg = sum(g["home_score"] + g["away_score"] for g in first_season) / (2 * len(first_season))
    m = model.RatingModel(sport, params["ratings"], avg, 0.0)
    pre, preds = {}, {}
    i = 0
    while i < len(games):
        key = games[i]["kickoff_utc"] or games[i]["game_date_et"]
        j = i
        while j < len(games) and (games[j]["kickoff_utc"] or games[j]["game_date_et"]) == key:
            j += 1
        group = games[i:j]
        for g in group:
            m.start_season(g["season"])
            m.prepare(g)
            h, a = m._name(g["home_team"]), m._name(g["away_team"])
            qb = None
            if m._uses_qbs():
                qh, qa = m._qb(g.get("home_starter_id")), m._qb(g.get("away_starter_id"))
                qb = (m.qb[qh] if qh else params["ratings"]["new_qb"]) - (m.qb[qa] if qa else params["ratings"]["new_qb"])
            pre[g["id"]] = {"off_diff": m.off[h] - m.off[a], "def_diff": m.dfn[h] - m.dfn[a], "qb_diff": qb}
            preds[g["id"]] = m.project(g)
        for g in group:
            m.update(g)
        i = j
    if params.get("combiner"):
        preds = combiner.apply(conn, games, preds, params["combiner"], sport, params["ratings"]["sigma"])
        team_seasons = combiner.load_team_seasons(conn, sport)
    # season-to-date offensive EPA (NFL): mean of a team's earlier games this season
    epa_sum, epa_n, epa_before = defaultdict(float), defaultdict(int), {}
    for g in games:
        kh, ka = (g["season"], g["home_team"]), (g["season"], g["away_team"])
        eh = epa_sum[kh] / epa_n[kh] if epa_n[kh] else None
        ea = epa_sum[ka] / epa_n[ka] if epa_n[ka] else None
        epa_before[g["id"]] = eh - ea if eh is not None and ea is not None else None
        for k, v in ((kh, g.get("home_off_epa")), (ka, g.get("away_off_epa"))):
            if v is not None:
                epa_sum[k] += v
                epa_n[k] += 1
    rows = []
    for g in games:
        mk = mkt.get(g["id"])
        if not mk or mk["p_home"] is None or g["home_score"] == g["away_score"]:
            continue
        ph, pa, hp, ap = form[g["id"]]
        f = {"engine_logit": logit(preds[g["id"]][2]), "market_logit": logit(mk["p_home"]),
             "home": 0.0 if g["neutral_site"] else 1.0,
             "rest_diff": ((g.get("home_rest_days") or 0) - (g.get("away_rest_days") or 0))
             if g.get("home_rest_days") is not None and g.get("away_rest_days") is not None else 0.0,
             "games_played": (ph + pa) / 2, "form_diff": hp - ap, "fav_size": abs(logit(mk["p_home"]))}
        if sport == "nfl":
            f["qb_diff"] = pre[g["id"]]["qb_diff"] or 0.0
            f["epa_diff"] = epa_before[g["id"]] or 0.0
        if sport == "ncaaf":
            hs = team_seasons.get((g["season"], g["home_team"]), {})
            as_ = team_seasons.get((g["season"], g["away_team"]), {})
            for key, name in (("talent", "talent_diff"), ("returning_pct", "returning_diff"), ("prev_sp", "prev_sp_diff")):
                f[name] = (hs[key] - as_[key]) if hs.get(key) is not None and as_.get(key) is not None else 0.0
        rows.append({"id": g["id"], "season": g["season"], "y": int(g["home_score"] > g["away_score"]), "f": f})
    return rows


def market_by_game(conn, sport):
    import backtest
    return backtest.market_by_game(conn, sport)


def soccer_table(conn):
    import soccer_model as sm
    params = sm.load_params()["ratings"]
    games = sm.load_games(conn)
    preds, _ = sm.walk_forward(games, params, keep=lambda g: g["league"] in sm.BIG5)
    form = recent_form(games)
    prices = defaultdict(dict)
    for r in conn.execute("SELECT o.* FROM hist_odds o JOIN hist_games g ON g.id = o.hist_game_id"
                          " WHERE g.sport = 'soccer_club' AND o.provider IN ('Market average', 'Market average (close)')"):
        prices[r["hist_game_id"]][r["provider"]] = no_vig(r["home_ml"], r["draw_ml"], r["away_ml"])[0]
    sot_sum, sot_n = defaultdict(float), defaultdict(int)
    rows = []
    for g in games:
        kh, ka = (g["season"], g["home_team"]), (g["season"], g["away_team"])
        sh = sot_sum[kh] / sot_n[kh] if sot_n[kh] else None
        sa = sot_sum[ka] / sot_n[ka] if sot_n[ka] else None
        pr = prices.get(g["id"], {})
        if g["id"] in preds and "Market average" in pr:
            ph, pa, hp, ap = form[g["id"]]
            pre = pr["Market average"]
            close = pr.get("Market average (close)")
            f = {"engine_logit": logit(preds[g["id"]][0]), "market_logit": logit(pre),
                 "home": 0.0 if g["neutral_site"] else 1.0,
                 "rest_diff": (g["home_rest"] - g["away_rest"]) if g.get("home_rest") and g.get("away_rest") else 0.0,
                 "games_played": (ph + pa) / 2, "form_diff": hp - ap, "fav_size": abs(logit(pre)),
                 "sot_diff": (sh - sa) if sh is not None and sa is not None else 0.0,
                 "line_move": (logit(close) - logit(pre)) if close is not None else 0.0}
            rows.append({"id": g["id"], "season": g["season"], "y": int(g["home_score"] > g["away_score"]), "f": f})
        for k, v in ((kh, g.get("home_shots_ot")), (ka, g.get("away_shots_ot"))):
            if v is not None:
                sot_sum[k] += v
                sot_n[k] += 1
    return rows


# ---------- ridge logistic regression with an optional offset ----------

def standardize(rows, names, stats=None):
    if stats is None:
        stats = {}
        for n in names:
            xs = [r["f"][n] for r in rows]
            mu = statistics.mean(xs)
            sd = statistics.pstdev(xs) or 1.0
            stats[n] = (mu, sd)
    X = [[(r["f"][n] - stats[n][0]) / stats[n][1] for n in names] for r in rows]
    return X, stats


def fit(X, y, offset=None, lam=RIDGE):
    """Ridge-penalized logistic regression by Newton's method. Returns [intercept, coefs...]."""
    k = len(X[0]) if X else 0
    w = [0.0] * (k + 1)
    off = offset or [0.0] * len(y)
    for _ in range(30):
        grad = [0.0] * (k + 1)
        hess = [[0.0] * (k + 1) for _ in range(k + 1)]
        for i in range(1, k + 1):
            grad[i] += lam * w[i]
            hess[i][i] += lam
        for xi, yi, oi in zip(X, y, off):
            x = [1.0] + xi
            q = sigmoid(oi + sum(a * b for a, b in zip(w, x)))
            d = q - yi
            s = q * (1 - q)
            for i in range(k + 1):
                grad[i] += d * x[i]
                row = hess[i]
                xs = s * x[i]
                for j in range(k + 1):
                    row[j] += xs * x[j]
        step = _solve(hess, grad)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(s_) for s_ in step) < 1e-8:
            break
    return w


def log_loss(X, y, w, offset=None):
    off = offset or [0.0] * len(y)
    tot = 0.0
    for xi, yi, oi in zip(X, y, off):
        q = sigmoid(oi + w[0] + sum(a * b for a, b in zip(w[1:], xi)))
        q = min(max(q, 1e-9), 1 - 1e-9)
        tot -= yi * math.log(q) + (1 - yi) * math.log(1 - q)
    return tot / len(y)


def sub(X, idx):
    return [[row[i] for i in idx] for row in X]


def forward_select(names, Xt, yt, Xc, yc, offt=None, offc=None):
    """Greedy: add the factor that most improves CHECK log loss; stop when no gain >= MIN_GAIN."""
    chosen, log = [], []
    base_w = fit([[] for _ in yt], yt, offt)
    best = log_loss([[] for _ in yc], yc, base_w, offc)
    log.append(("(none)", best, 0.0))
    remaining = list(range(len(names)))
    while remaining and len(chosen) < MAX_STEPS:
        trial = []
        for i in remaining:
            idx = chosen + [i]
            w = fit(sub(Xt, idx), yt, offt)
            trial.append((log_loss(sub(Xc, idx), yc, w, offc), i))
        ll, i = min(trial)
        if best - ll < MIN_GAIN:
            break
        chosen.append(i)
        remaining.remove(i)
        log.append((names[i], ll, best - ll))
        best = ll
    return chosen, log


# ---------- PCA diagnostic (Jacobi eigenvalues on the correlation matrix) ----------

def pca(X, names):
    k = len(names)
    n = len(X)
    C = [[sum(X[r][i] * X[r][j] for r in range(n)) / n for j in range(k)] for i in range(k)]
    V = [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
    for _ in range(60):
        off = max((abs(C[i][j]), i, j) for i in range(k) for j in range(k) if i != j)
        if off[0] < 1e-9:
            break
        _, p, q = off
        theta = 0.5 * math.atan2(2 * C[p][q], C[q][q] - C[p][p])
        c, s = math.cos(theta), math.sin(theta)
        for r in range(k):
            cp, cq = C[r][p], C[r][q]
            C[r][p], C[r][q] = c * cp - s * cq, s * cp + c * cq
        for r in range(k):
            cp, cq = C[p][r], C[q][r]
            C[p][r], C[q][r] = c * cp - s * cq, s * cp + c * cq
        for r in range(k):
            vp, vq = V[r][p], V[r][q]
            V[r][p], V[r][q] = c * vp - s * vq, s * vp + c * vq
    eig = sorted(((C[i][i], i) for i in range(k)), reverse=True)
    total = sum(e for e, _ in eig)
    out, cum = [], 0.0
    for e, i in eig:
        cum += e / total
        loads = sorted(((abs(V[r][i]), names[r], V[r][i]) for r in range(k)), reverse=True)[:3]
        out.append((e / total, cum, [(nm, round(v, 2)) for _, nm, v in loads]))
    return out


# ---------- report ----------

# College sports have sportsbook prices only from 2021 (football) / 2023 (basketball), so their
# pre-registered tune seasons hold no priced games. Deviation from the plan, documented in the results:
# the priced seasons are split in date order instead. These overlap the sports' final-exam seasons
# (already used once), so the college results are information, not a pre-registered test.
PRICED_PERIODS = {"ncaaf": ((2021, 2023), (2024, 2025)), "ncaab": ((2023, 2024), (2025, 2026))}


def periods(sport):
    if sport in PRICED_PERIODS:
        return PRICED_PERIODS[sport]
    if sport == "soccer_club":
        from backtest_soccer import PERIODS as P
        return P["tune"], P["check"]
    from backtest import PERIODS as P
    return P[sport]["tune"], P[sport]["check"]


def study(conn, sport):
    rows = soccer_table(conn) if sport == "soccer_club" else ball_table(conn, sport)
    tune, check = periods(sport)
    rt = [r for r in rows if tune[0] <= r["season"] <= tune[1]]
    rc = [r for r in rows if check[0] <= r["season"] <= check[1]]
    names = [n for n in rows[0]["f"] if n != "market_logit"]
    all_names = ["market_logit"] + names
    lines = [f"\n## {sport}: {len(rt)} tune games ({tune[0]}-{tune[1]}), {len(rc)} check games ({check[0]}-{check[1]})\n"]
    if sport in PRICED_PERIODS:
        lines.append("**Deviation from the plan:** this sport has sportsbook prices only in recent seasons, so the "
                     "priced seasons are split in date order (tune then check). They overlap the sport's final-exam "
                     "seasons, so treat this as information, not a pre-registered test.\n")
    Xt, stats = standardize(rt, all_names)
    Xc, _ = standardize(rc, all_names, stats)
    yt, yc = [r["y"] for r in rt], [r["y"] for r in rc]
    off_t, off_c = [r["f"]["market_logit"] for r in rt], [r["f"]["market_logit"] for r in rc]
    base_names = {"market alone": [0], "engine alone": [all_names.index("engine_logit")]}
    lines.append("Baselines (check-season log loss): " + ", ".join(
        f"{k} {log_loss(sub(Xc, idx), yc, fit(sub(Xt, idx), yt)):.4f}" for k, idx in base_names.items()))
    lines.append(f"Home-win rate: tune {statistics.mean(yt):.3f}, check {statistics.mean(yc):.3f}\n")

    for label, use_offset in (("(a) What predicts winning", False), ("(b) What the market misses (market log-odds as a fixed offset)", True)):
        nm = names if use_offset else all_names
        idx = [all_names.index(n) for n in nm]
        ot, oc = (off_t, off_c) if use_offset else (None, None)
        wt = fit(sub(Xt, idx), yt, ot)
        wc = fit(sub(Xc, idx), yc, oc)
        lines.append(f"### {label}\n")
        lines.append("| factor | coef (tune) | coef (check) | same sign |")
        lines.append("|---|---|---|---|")
        for i, n in enumerate(nm):
            lines.append(f"| {n} | {wt[i + 1]:+.3f} | {wc[i + 1]:+.3f} | {'yes' if wt[i + 1] * wc[i + 1] > 0 else 'no'} |")
        lines.append(f"\nAll factors, check-season log loss: {log_loss(sub(Xc, idx), yc, wt, oc):.4f}\n")
        chosen, log = forward_select(nm, sub(Xt, idx), yt, sub(Xc, idx), yc, ot, oc)
        lines.append("Forward selection (each step adds the factor that most improves check-season log loss):\n")
        lines.append("| step | factor | check log loss | gain |")
        lines.append("|---|---|---|---|")
        for k, (n, ll, gain) in enumerate(log):
            lines.append(f"| {k} | {n} | {ll:.4f} | {gain:+.4f} |")
        found = [nm[i] for i in chosen if wt[nm.index(nm[i]) + 1] * wc[nm.index(nm[i]) + 1] > 0]
        lines.append(f"\n**Factors that matter (selected, gain >= {MIN_GAIN}, same sign on tune and check):** "
                     + (", ".join(found) if found else "none") + "\n")

    comps = pca(Xt, all_names)
    n90 = next(i + 1 for i, c in enumerate(comps) if c[1] >= 0.9)
    lines.append(f"### PCA diagnostic\n\n{n90} of {len(all_names)} components explain 90% of the factors' variance.\n")
    for i, (share, cum, loads) in enumerate(comps[:4], 1):
        lines.append(f"- component {i}: {share:.0%} of variance; main loadings " + ", ".join(f"{n} {v:+.2f}" for n, v in loads))
    return "\n".join(lines)


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("nfl", "ncaaf", "nba", "ncaab", "soccer_club"):
        sys.exit(__doc__)
    conn = db.connect()
    text = study(conn, a[0])
    print(text)
    if "--out" in a:
        if not RESULTS.exists():
            RESULTS.write_text("# Factor study results\n\nPlan: `plans/factor_study.md`. Produced by `factor_study.py`.\n"
                               "Coefficients are per standard deviation of each factor (log-odds). Ridge penalty 1.0.\n")
        RESULTS.write_text(RESULTS.read_text() + text + "\n")


if __name__ == "__main__":
    main()

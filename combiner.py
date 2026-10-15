"""Combine our model with published ratings into one win probability.

A logistic formula takes several inputs for the home team, each known before
kickoff, and learns from the tune seasons how much weight each deserves:

  margin       our model's projected margin (points / 10)
  home         1 unless the game is at a neutral site
  elo          published pregame Elo difference (CFBD; / 100)
  talent_early roster talent difference (/ 100), fading out over the first 8 games
  sp_early     last season's SP+ difference (/ 10), fading out the same way
  ret_early    returning-production difference (0-1), fading out the same way
  margin_early our margin again, but only early in the season (lets the
               formula trust our ratings less before they've seen games)

A missing input counts as 0 (no information). Betting lines are never used.
"""

import math
from statistics import NormalDist

EARLY_GAMES = 8

FEATURE_SETS = {
    "ours only (recalibrated)": ["margin", "home"],
    "published Elo only": ["elo", "home"],
    "ours + Elo": ["margin", "home", "elo"],
    "ours + preseason data": ["margin", "home", "margin_early", "talent_early", "sp_early", "ret_early"],
    "ours + Elo + preseason": ["margin", "home", "elo", "margin_early", "talent_early", "sp_early", "ret_early"],
}


def load_team_seasons(conn, sport):
    return {(r["season"], r["team"]): dict(r) for r in conn.execute(
        "SELECT * FROM hist_team_season WHERE sport = ?", (sport,))}


def games_played_before(games):
    """{game id: (home team's games so far this season, away team's)}."""
    seen, out = {}, {}
    for g in games:
        h, a = (g["season"], g["home_team"]), (g["season"], g["away_team"])
        out[g["id"]] = (seen.get(h, 0), seen.get(a, 0))
        seen[h] = seen.get(h, 0) + 1
        seen[a] = seen.get(a, 0) + 1
    return out


def features(g, margin, played, team_seasons):
    """All inputs for one game, from the home team's point of view."""
    early = max(0.0, 1 - sum(played) / 2 / EARLY_GAMES)
    hs = team_seasons.get((g["season"], g["home_team"]), {})
    as_ = team_seasons.get((g["season"], g["away_team"]), {})

    def diff(key, scale):
        if hs.get(key) is None or as_.get(key) is None:
            return 0.0
        return (hs[key] - as_[key]) / scale

    elo = 0.0
    if g.get("home_pub_elo") is not None and g.get("away_pub_elo") is not None:
        elo = (g["home_pub_elo"] - g["away_pub_elo"]) / 100
    return {
        "margin": margin / 10,
        "home": 0.0 if g["neutral_site"] else 1.0,
        "elo": elo,
        "talent_early": early * diff("talent", 100),
        "sp_early": early * diff("prev_sp", 10),
        "ret_early": early * diff("returning_pct", 1),
        "margin_early": early * margin / 10,
    }


def _sigmoid(z):
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def fit(rows, names):
    """Logistic regression by Newton's method. rows: [(feature dict, won 0/1)].
    Returns {"features": names, "coef": [intercept, one per feature]}."""
    n = len(names) + 1
    w = [0.0] * n
    for _ in range(25):
        grad = [0.0] * n
        hess = [[1e-6 if i == j else 0.0 for j in range(n)] for i in range(n)]
        for f, y in rows:
            x = [1.0] + [f[k] for k in names]
            q = _sigmoid(sum(wi * xi for wi, xi in zip(w, x)))
            for i in range(n):
                grad[i] += (q - y) * x[i]
                for j in range(n):
                    hess[i][j] += q * (1 - q) * x[i] * x[j]
        step = _solve(hess, grad)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return {"features": names, "coef": [round(c, 5) for c in w]}


def _solve(a, b):
    """Solve a x = b (small system, Gaussian elimination with pivoting)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c and m[c][c]:
                factor = m[r][c] / m[c][c]
                m[r] = [x - factor * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def probability(comb, f):
    x = [1.0] + [f[k] for k in comb["features"]]
    return _sigmoid(sum(c * xi for c, xi in zip(comb["coef"], x)))


def apply(conn, games, preds, comb, sport, sigma):
    """Replace the model's probabilities with the combiner's. The projected
    score keeps its total, with the margin moved to match the new probability."""
    team_seasons = load_team_seasons(conn, sport)
    played = games_played_before(games)
    out = {}
    for g in games:
        home_pts, away_pts, _ = preds[g["id"]]
        f = features(g, home_pts - away_pts, played[g["id"]], team_seasons)
        p = probability(comb, f)
        margin = sigma * NormalDist().inv_cdf(min(max(p, 1e-6), 1 - 1e-6))
        total = home_pts + away_pts
        out[g["id"]] = ((total + margin) / 2, (total - margin) / 2, p)
    return out

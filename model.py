"""The base model: team offense and defense ratings in points, updated game by game.

No betting lines are used here. The model only sees scores, schedule, home
field, and division (college).

How it works:
  projected home points = league avg + home offense - away defense + half of home field
  projected away points = league avg + away offense - home defense - half of home field
  P(home wins) = normal curve of (projected margin / sigma)
After each game, ratings move by k times the (capped) surprise in each team's
points. Between seasons ratings are pulled part of the way back to their
starting point. League average and home-field size drift slowly with the data.

NFL only (v2): each starting quarterback has a rating that adds to the team's
offense, learned from results the same way, and follows the QB between teams.
A QB's first start begins at new_qb. The difference in rest days shifts the
projected margin by rest_coef points per day (capped at 7 days).
"""

import json
import math
from pathlib import Path

PARAMS_PATH = Path(__file__).parent / "model_params.json"

# Franchises that moved: always rate them as one team under today's name.
NFL_FRANCHISE = {"SD": "LAC", "OAK": "LV", "STL": "LA"}

DEFAULT_PARAMS = {
    "nfl": {"k": 0.08, "hfa_start": 2.5, "hfa_rate": 0.002, "regress": 0.3,
            "cap": 21.0, "sigma": 13.5, "new_team": 0.0, "avg_rate": 0.005,
            "qb_k": 0.05, "new_qb": -2.0, "qb_regress": 0.2, "rest_coef": 0.15},
    "ncaaf": {"k": 0.08, "hfa_start": 3.0, "hfa_rate": 0.002, "regress": 0.3,
              "cap": 28.0, "sigma": 16.0, "new_team": 10.0, "avg_rate": 0.005},
}


def load_params(sport):
    if PARAMS_PATH.exists():
        saved = json.loads(PARAMS_PATH.read_text())
        if sport in saved:
            return saved[sport]
    return {"version": f"{sport}-untuned", "ratings": dict(DEFAULT_PARAMS[sport])}


def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class RatingModel:
    def __init__(self, sport, ratings_params, avg_start):
        self.sport = sport
        self.p = ratings_params
        self.avg = avg_start            # league average points per team per game
        self.hfa = self.p["hfa_start"]  # home-field advantage in points
        self.off = {}                   # team -> offense rating (points above average)
        self.dfn = {}                   # team -> defense rating (points prevented)
        self.base = {}                  # team -> starting rating (lower for smaller divisions)
        self.qb = {}                    # NFL: starting QB id -> rating (points added to offense)
        self.season = None

    def _team(self, name, division=None):
        if self.sport == "nfl":
            name = NFL_FRANCHISE.get(name, name)
        if name not in self.off:
            # College teams outside the top division start below average
            start = -self.p["new_team"] if division not in (None, "fbs") else 0.0
            self.base[name] = start
            self.off[name] = start
            self.dfn[name] = start
        return name

    def _uses_qbs(self):
        return "qb_k" in self.p

    def _qb(self, qb_id):
        if not self._uses_qbs() or qb_id is None:
            return None
        if qb_id not in self.qb:
            self.qb[qb_id] = self.p["new_qb"]
        return qb_id

    def start_season(self, season):
        if self.season is not None and season != self.season:
            r = self.p["regress"]
            for t in self.off:
                self.off[t] += r * (self.base[t] - self.off[t])
                self.dfn[t] += r * (self.base[t] - self.dfn[t])
            if self._uses_qbs():
                for q in self.qb:
                    self.qb[q] -= self.p["qb_regress"] * self.qb[q]
        self.season = season

    def project(self, g):
        """Return (home points, away points, P(home wins)) for a game dict with keys
        home_team, away_team, neutral_site, and optionally home_division,
        away_division, home_starter_id, away_starter_id, home_rest_days, away_rest_days."""
        h = self._team(g["home_team"], g.get("home_division"))
        a = self._team(g["away_team"], g.get("away_division"))
        qh, qa = self._qb(g.get("home_starter_id")), self._qb(g.get("away_starter_id"))
        bump = 0.0 if g["neutral_site"] else self.hfa / 2
        if self._uses_qbs() and g.get("home_rest_days") is not None and g.get("away_rest_days") is not None:
            rest_diff = max(-7, min(7, g["home_rest_days"] - g["away_rest_days"]))
            bump += self.p["rest_coef"] * rest_diff / 2
        home_pts = self.avg + self.off[h] + (self.qb[qh] if qh else 0) - self.dfn[a] + bump
        away_pts = self.avg + self.off[a] + (self.qb[qa] if qa else 0) - self.dfn[h] - bump
        p_home = normal_cdf((home_pts - away_pts) / self.p["sigma"])
        return home_pts, away_pts, p_home

    def update(self, g):
        """Learn from a finished game (same dict as project, plus home_score, away_score)."""
        home_pts, away_pts, _ = self.project(g)
        h = self._team(g["home_team"], g.get("home_division"))
        a = self._team(g["away_team"], g.get("away_division"))
        qh, qa = self._qb(g.get("home_starter_id")), self._qb(g.get("away_starter_id"))
        cap, k = self.p["cap"], self.p["k"]
        err_home = max(-cap, min(cap, g["home_score"] - home_pts))
        err_away = max(-cap, min(cap, g["away_score"] - away_pts))
        self.off[h] += k * err_home
        self.dfn[a] -= k * err_home
        self.off[a] += k * err_away
        self.dfn[h] -= k * err_away
        if qh:
            self.qb[qh] += self.p["qb_k"] * err_home
        if qa:
            self.qb[qa] += self.p["qb_k"] * err_away
        self.avg += self.p["avg_rate"] * ((g["home_score"] + g["away_score"]) / 2 - self.avg)
        if not g["neutral_site"]:
            self.hfa += self.p["hfa_rate"] * (err_home - err_away)

    def rating(self, team):
        team = NFL_FRANCHISE.get(team, team) if self.sport == "nfl" else team
        return self.off.get(team), self.dfn.get(team)


def load_games(conn, sport):
    """All completed past games for a sport, oldest first."""
    return [dict(r) for r in conn.execute(
        "SELECT id, season, game_date_et, kickoff_utc, home_team, away_team,"
        " home_division, away_division, home_score, away_score, neutral_site,"
        " home_starter_id, away_starter_id, home_rest_days, away_rest_days"
        " FROM hist_games WHERE sport = ?"
        " ORDER BY game_date_et, coalesce(kickoff_utc, ''), id", (sport,))]


def walk_forward(games, ratings_params, sport):
    """Predict every game using only earlier games, then learn from it.

    Games kicking off at the same moment (or same date, if the time is
    unknown) are all predicted before any of their results are used.
    Returns {game id: (home pts, away pts, P(home wins))} and the final model.
    League average starts at the first season's mean; that season is warm-up only.
    """
    first = games[0]["season"]
    first_season = [g for g in games if g["season"] == first]
    avg_start = sum(g["home_score"] + g["away_score"] for g in first_season) / (2 * len(first_season))
    model = RatingModel(sport, ratings_params, avg_start)
    preds = {}
    i = 0
    while i < len(games):
        key = games[i]["kickoff_utc"] or games[i]["game_date_et"]
        j = i
        while j < len(games) and (games[j]["kickoff_utc"] or games[j]["game_date_et"]) == key:
            j += 1
        group = games[i:j]
        for g in group:
            model.start_season(g["season"])
            preds[g["id"]] = model.project(g)
        for g in group:
            model.update(g)
        i = j
    return preds, model

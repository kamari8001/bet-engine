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
"""

import json
import math
from pathlib import Path

PARAMS_PATH = Path(__file__).parent / "model_params.json"

# Franchises that moved: always rate them as one team under today's name.
NFL_FRANCHISE = {"SD": "LAC", "OAK": "LV", "STL": "LA"}

DEFAULT_PARAMS = {
    "nfl": {"k": 0.08, "hfa_start": 2.5, "hfa_rate": 0.002, "regress": 0.3,
            "cap": 21.0, "sigma": 13.5, "new_team": 0.0, "avg_rate": 0.005},
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

    def start_season(self, season):
        if self.season is not None and season != self.season:
            r = self.p["regress"]
            for t in self.off:
                self.off[t] += r * (self.base[t] - self.off[t])
                self.dfn[t] += r * (self.base[t] - self.dfn[t])
        self.season = season

    def project(self, home, away, neutral=False, home_div=None, away_div=None):
        """Return (home points, away points, P(home wins))."""
        h, a = self._team(home, home_div), self._team(away, away_div)
        bump = 0.0 if neutral else self.hfa / 2
        home_pts = self.avg + self.off[h] - self.dfn[a] + bump
        away_pts = self.avg + self.off[a] - self.dfn[h] - bump
        p_home = normal_cdf((home_pts - away_pts) / self.p["sigma"])
        return home_pts, away_pts, p_home

    def update(self, home, away, home_score, away_score, neutral=False,
               home_div=None, away_div=None):
        home_pts, away_pts, _ = self.project(home, away, neutral, home_div, away_div)
        h, a = self._team(home, home_div), self._team(away, away_div)
        cap, k = self.p["cap"], self.p["k"]
        err_home = max(-cap, min(cap, home_score - home_pts))
        err_away = max(-cap, min(cap, away_score - away_pts))
        self.off[h] += k * err_home
        self.dfn[a] -= k * err_home
        self.off[a] += k * err_away
        self.dfn[h] -= k * err_away
        self.avg += self.p["avg_rate"] * ((home_score + away_score) / 2 - self.avg)
        if not neutral:
            self.hfa += self.p["hfa_rate"] * (err_home - err_away)

    def rating(self, team):
        team = NFL_FRANCHISE.get(team, team) if self.sport == "nfl" else team
        return self.off.get(team), self.dfn.get(team)


def load_games(conn, sport):
    """All completed past games for a sport, oldest first."""
    return [dict(r) for r in conn.execute(
        "SELECT id, season, game_date_et, kickoff_utc, home_team, away_team,"
        " home_division, away_division, home_score, away_score, neutral_site"
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
            preds[g["id"]] = model.project(g["home_team"], g["away_team"], g["neutral_site"],
                                           g["home_division"], g["away_division"])
        for g in group:
            model.update(g["home_team"], g["away_team"], g["home_score"], g["away_score"],
                         g["neutral_site"], g["home_division"], g["away_division"])
        i = j
    return preds, model

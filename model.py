"""The base model: team ratings updated game by game.

No betting lines are used here. The model only sees results, schedule, home
field, division (college), and for the NFL: starting QBs, rest, head coaches,
offensive efficiency (EPA), and time zones.

How it works:
  Points ratings: each team has an offense and a defense rating in points.
    projected home points = league avg + home offense + home QB - away defense + half of bumps
    projected away points = league avg + away offense + away QB - home defense - half of bumps
  Efficiency ratings (NFL v3): the same idea, measured in expected points added
    (EPA) instead of points, so lucky bounces count less.
  Projected margin = blend of the points view and the efficiency view (epa_w),
    plus QB difference, home field, rest, and travel.
  P(home wins) = normal curve of (projected margin / sigma)

After each game, ratings move by k times the (capped) surprise. Teams learn
faster in their first 4 games of a season (early_boost). Between seasons
ratings are pulled part of the way back to their starting point, and further
for teams with a new head coach (coach_regress). League average and home-field
size drift slowly with the data.

Every NFL v3 feature is switched off when its setting is 0 or missing, so
older saved settings behave exactly as they did.
"""

import json
import math
from pathlib import Path

from teams import NFL_HOME_TZ

PARAMS_PATH = Path(__file__).parent / "model_params.json"

# Franchises that moved: always rate them as one team under today's name.
NFL_FRANCHISE = {"SD": "LAC", "OAK": "LV", "STL": "LA"}
EARLY_GAMES = 4   # games per season that count as "early"

DEFAULT_PARAMS = {
    "nfl": {"k": 0.08, "hfa_start": 2.5, "hfa_rate": 0.002, "regress": 0.3,
            "cap": 21.0, "sigma": 13.5, "new_team": 0.0, "avg_rate": 0.005,
            "qb_k": 0.05, "new_qb": -2.0, "qb_regress": 0.2, "rest_coef": 0.15},
    "ncaaf": {"k": 0.08, "hfa_start": 3.0, "hfa_rate": 0.002, "regress": 0.3,
              "cap": 28.0, "sigma": 16.0, "new_team": 10.0, "avg_rate": 0.005},
    # Basketball: many more games, so smaller steps; rest counts days since each team's last game
    # (1 = back-to-back), with the difference capped at rest_cap days.
    "nba": {"k": 0.03, "hfa_start": 2.5, "hfa_rate": 0.0005, "regress": 0.3,
            "cap": 25.0, "sigma": 12.0, "new_team": 0.0, "avg_rate": 0.002,
            "rest_coef": 0.5, "rest_cap": 3},
    "ncaab": {"k": 0.04, "hfa_start": 3.0, "hfa_rate": 0.0005, "regress": 0.5,
              "cap": 25.0, "sigma": 11.0, "new_team": 0.0, "avg_rate": 0.002,
              "rest_coef": 0.3, "rest_cap": 3},
}
BASKETBALL = ("nba", "ncaab")

# Starting values used when tuning each NFL v3 feature (0 would mean "off").
NFL_V3_START = {"epa_w": 0.3, "epa_k": 0.08, "coach_regress": 0.15,
                "early_boost": 0.5, "travel_coef": 0.3, "early_west": 0.5}


def load_params(sport):
    if PARAMS_PATH.exists():
        saved = json.loads(PARAMS_PATH.read_text())
        if sport in saved:
            return saved[sport]
    return {"version": f"{sport}-untuned", "ratings": dict(DEFAULT_PARAMS[sport])}


def normal_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class RatingModel:
    def __init__(self, sport, ratings_params, avg_start, epa_avg_start=0.0):
        self.sport = sport
        self.p = ratings_params
        self.avg = avg_start            # league average points per team per game
        self.epa_avg = epa_avg_start    # league average offense EPA per team per game
        self.hfa = self.p["hfa_start"]  # home-field advantage in points
        self.off = {}                   # team -> offense rating (points above average)
        self.dfn = {}                   # team -> defense rating (points prevented)
        self.eoff = {}                  # team -> offense efficiency rating (EPA)
        self.edef = {}                  # team -> defense efficiency rating (EPA prevented)
        self.base = {}                  # team -> starting rating (lower for smaller divisions)
        self.qb = {}                    # NFL: starting QB id -> rating (points added to offense)
        self.coach = {}                 # team -> last head coach seen
        self.team_season = {}           # team -> season of its last game
        self.games_this_season = {}     # team -> games played so far this season
        self.season = None
        # Player absences (basketball, plans/player_impact.md): points of margin per unit of
        # "missing value"; corrected online when abs_k > 0
        self.abs_coef = self.p.get("abs_coef", 0.0)

    def _get(self, name):
        return self.p.get(name, 0.0)

    def _name(self, name):
        return NFL_FRANCHISE.get(name, name) if self.sport == "nfl" else name

    def _team(self, name, division=None):
        name = self._name(name)
        if name not in self.off:
            # College teams outside the top division start below average
            start = -self.p["new_team"] if division not in (None, "fbs") else 0.0
            self.base[name] = start
            self.off[name] = self.dfn[name] = start
            self.eoff[name] = self.edef[name] = 0.0
        return name

    def _uses_qbs(self):
        return "qb_k" in self.p

    def _qb(self, qb_id):
        if not self._uses_qbs() or qb_id is None:
            return None
        if qb_id not in self.qb:
            self.qb[qb_id] = self.p["new_qb"]
        return qb_id

    def _pull_back(self, team, amount):
        self.off[team] += amount * (self.base[team] - self.off[team])
        self.dfn[team] += amount * (self.base[team] - self.dfn[team])
        self.eoff[team] -= amount * self.eoff[team]
        self.edef[team] -= amount * self.edef[team]

    def start_season(self, season):
        if self.season is not None and season != self.season:
            for t in self.off:
                self._pull_back(t, self.p["regress"])
            if self._uses_qbs():
                for q in self.qb:
                    self.qb[q] -= self.p["qb_regress"] * self.qb[q]
        self.season = season

    def prepare(self, g):
        """Before a game: note each team's first game of the season, and give
        teams with a new head coach an extra pull back toward average."""
        for side in ("home", "away"):
            t = self._team(g[f"{side}_team"], g.get(f"{side}_division"))
            if self.team_season.get(t) != g["season"]:
                coach = g.get(f"{side}_coach")
                if (coach and self.coach.get(t) and coach != self.coach[t]
                        and self._get("coach_regress")):
                    self._pull_back(t, self._get("coach_regress"))
                self.team_season[t] = g["season"]
                self.games_this_season[t] = 0
            if g.get(f"{side}_coach"):
                self.coach[t] = g[f"{side}_coach"]

    def _bumps(self, g):
        """Points added to the home margin by home field, rest and travel."""
        if g["neutral_site"]:
            bump = 0.0
        else:
            bump = self.hfa
            if self._get("travel_coef") or self._get("early_west"):
                home_tz = NFL_HOME_TZ.get(g["home_team"])
                away_tz = NFL_HOME_TZ.get(g["away_team"])
                if home_tz is not None and away_tz is not None:
                    bump += self._get("travel_coef") * abs(home_tz - away_tz)
                    kickoff = g.get("kickoff_et") or ""
                    if away_tz == -8 and kickoff[11:13] in ("12", "13"):
                        bump += self._get("early_west")  # West Coast body clock at ~1 PM ET
        if "rest_coef" in self.p and g.get("home_rest_days") is not None and g.get("away_rest_days") is not None:
            cap = self.p.get("rest_cap", 7)
            bump += self.p["rest_coef"] * max(-cap, min(cap, g["home_rest_days"] - g["away_rest_days"]))
        if self.abs_coef and g.get("home_missing") is not None and g.get("away_missing") is not None:
            bump -= self.abs_coef * (g["home_missing"] - g["away_missing"])
        return bump

    def _points_view(self, g):
        """Points-only projection: (home points, away points)."""
        h = self._team(g["home_team"], g.get("home_division"))
        a = self._team(g["away_team"], g.get("away_division"))
        qh, qa = self._qb(g.get("home_starter_id")), self._qb(g.get("away_starter_id"))
        half = self._bumps(g) / 2
        home_pts = self.avg + self.off[h] + (self.qb[qh] if qh else 0) - self.dfn[a] + half
        away_pts = self.avg + self.off[a] + (self.qb[qa] if qa else 0) - self.dfn[h] - half
        return home_pts, away_pts

    def project(self, g):
        """Return (home points, away points, P(home wins)).

        g is a game dict with home_team, away_team, neutral_site, and optionally
        season, home/away _division, _starter_id, _rest_days, _coach, kickoff_et."""
        home_pts, away_pts = self._points_view(g)
        w = self._get("epa_w")
        if w:
            h, a = self._name(g["home_team"]), self._name(g["away_team"])
            points_core = (self.off[h] - self.dfn[a]) - (self.off[a] - self.dfn[h])
            epa_core = (self.eoff[h] - self.edef[a]) - (self.eoff[a] - self.edef[h])
            shift = w * (epa_core - points_core) / 2   # move the margin, keep the total
            home_pts, away_pts = home_pts + shift, away_pts - shift
        p_home = normal_cdf((home_pts - away_pts) / self.p["sigma"])
        return home_pts, away_pts, p_home

    def update(self, g):
        """Learn from a finished game (same dict as project, plus scores and EPA)."""
        home_pts, away_pts = self._points_view(g)
        h = self._team(g["home_team"], g.get("home_division"))
        a = self._team(g["away_team"], g.get("away_division"))
        qh, qa = self._qb(g.get("home_starter_id")), self._qb(g.get("away_starter_id"))
        boost = 1 + self._get("early_boost")
        kh = self.p["k"] * (boost if self.games_this_season.get(h, 0) < EARLY_GAMES else 1)
        ka = self.p["k"] * (boost if self.games_this_season.get(a, 0) < EARLY_GAMES else 1)
        cap = self.p["cap"]
        err_home = max(-cap, min(cap, g["home_score"] - home_pts))
        err_away = max(-cap, min(cap, g["away_score"] - away_pts))
        self.off[h] += kh * err_home
        self.dfn[a] -= ka * err_home
        self.off[a] += ka * err_away
        self.dfn[h] -= kh * err_away
        if qh:
            self.qb[qh] += self.p["qb_k"] * err_home
        if qa:
            self.qb[qa] += self.p["qb_k"] * err_away

        if self._get("epa_w") and g.get("home_off_epa") is not None and g.get("away_off_epa") is not None:
            ek = self._get("epa_k")
            ekh = ek * kh / self.p["k"]
            eka = ek * ka / self.p["k"]
            # The QB's part is already in the QB rating, so the team efficiency
            # ratings learn only what's left (same split as the points ratings).
            qbh = self.qb[qh] if qh else 0
            qba = self.qb[qa] if qa else 0
            e_home = max(-cap, min(cap, g["home_off_epa"] - (self.epa_avg + self.eoff[h] + qbh - self.edef[a])))
            e_away = max(-cap, min(cap, g["away_off_epa"] - (self.epa_avg + self.eoff[a] + qba - self.edef[h])))
            self.eoff[h] += ekh * e_home
            self.edef[a] -= eka * e_home
            self.eoff[a] += eka * e_away
            self.edef[h] -= ekh * e_away
            self.epa_avg += self.p["avg_rate"] * ((g["home_off_epa"] + g["away_off_epa"]) / 2 - self.epa_avg)

        if self._get("abs_k") and g.get("home_missing") is not None and g.get("away_missing") is not None:
            # online correction of the absence coefficient: move it toward what this result implied
            x = g["home_missing"] - g["away_missing"]
            err = (g["home_score"] - g["away_score"]) - (home_pts - away_pts)
            self.abs_coef = max(0.0, min(10.0, self.abs_coef - self._get("abs_k") * err * x / (1 + x * x)))
        self.games_this_season[h] = self.games_this_season.get(h, 0) + 1
        self.games_this_season[a] = self.games_this_season.get(a, 0) + 1
        self.avg += self.p["avg_rate"] * ((g["home_score"] + g["away_score"]) / 2 - self.avg)
        if not g["neutral_site"]:
            self.hfa += self.p["hfa_rate"] * (err_home - err_away)

    def rating(self, team):
        team = self._name(team)
        return self.off.get(team), self.dfn.get(team)


def add_rest_days(games):
    """Basketball: fill rest days from the schedule (days since each team's previous game;
    None for a team's first game after a 30+ day break, e.g. the season opener)."""
    from datetime import date
    last = {}
    for g in games:
        d = date.fromisoformat(g["game_date_et"])
        for side in ("home", "away"):
            prev = last.get(g[f"{side}_team"])
            gap = (d - prev).days if prev else None
            g[f"{side}_rest_days"] = gap if gap is not None and gap <= 30 else None
            last[g[f"{side}_team"]] = d
    return games


def load_games(conn, sport):
    """All completed past games for a sport, oldest first."""
    games = [dict(r) for r in conn.execute(
        "SELECT id, season, game_date_et, kickoff_et, kickoff_utc, home_team, away_team,"
        " home_division, away_division, home_score, away_score, neutral_site,"
        " home_starter_id, away_starter_id, home_rest_days, away_rest_days,"
        " home_coach, away_coach, home_off_epa, away_off_epa, home_pub_elo, away_pub_elo"
        " FROM hist_games WHERE sport = ?"
        " ORDER BY game_date_et, coalesce(kickoff_utc, ''), id", (sport,))]
    return add_rest_days(games) if sport in BASKETBALL else games


def walk_forward(games, ratings_params, sport):
    """Predict every game using only earlier games, then learn from it.

    Games kicking off at the same moment (or same date, if the time is
    unknown) are all predicted before any of their results are used.
    Returns {game id: (home pts, away pts, P(home wins))} and the final model.
    League averages start at the first season's mean; that season is warm-up only.
    """
    first = games[0]["season"]
    first_season = [g for g in games if g["season"] == first]
    avg_start = sum(g["home_score"] + g["away_score"] for g in first_season) / (2 * len(first_season))
    epa = [g[k] for g in first_season for k in ("home_off_epa", "away_off_epa") if g.get(k) is not None]
    model = RatingModel(sport, ratings_params, avg_start, sum(epa) / len(epa) if epa else 0.0)
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
            model.prepare(g)
            preds[g["id"]] = model.project(g)
        for g in group:
            model.update(g)
        i = j
    return preds, model

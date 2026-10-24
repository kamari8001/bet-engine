"""Club soccer model: team attack/defense ratings -> expected goals -> home/draw/away chances.

How it works (plain English):
- Every team has an ATTACK and a DEFENSE rating, measured relative to its league (0 = average).
  Each league has its own average goals and home advantage.
- Expected goals: home = exp(league base + home advantage + home attack - away defense);
  away = exp(league base + away attack - home defense). (exp keeps them positive.)
- Those two numbers give the chance of every scoreline (Poisson), with the Dixon-Coles
  correction (rho) for 0-0, 1-0, 0-1 and 1-1, which plain Poisson gets slightly wrong.
  Home win = sum of home-winning scorelines, and so on.
- After each game, ratings move toward what happened (learning rate k), goals capped at `cap`.
  League averages and home advantage update slowly (k_lg).
- Between seasons ratings shrink toward average (regress). A team moving up a division loses
  `promo_gap` from both ratings (the new league is stronger); a relegated team gains it.
  A team never seen before starts at `new_team`.
- Optional ideas (off unless their setting is non-zero): shots on target in the updates (sot_w),
  rest days (rest_coef), ClubElo ratings (elo_w).
- European games (Champions/Europa/Conference League, only when loaded with include_europe=True):
  each league has a STRENGTH (log-goals, starts at 0) learned from European results (eu_k_s). In a
  European game a club's attack and defense are its domestic ratings shifted by half its league's
  strength; European games have their own average goals and home advantage (eu_k_lg). Optional:
  club ratings learn from European games too (eu_k_team), league strengths shrink between seasons
  (eu_regress_s). Domestic games and predictions are unaffected unless eu_k_team > 0.

Only ratings from games BEFORE a game are used to predict it (walk forward, no hindsight).
"""

import json
import math
from collections import defaultdict
from pathlib import Path

PARAMS_PATH = Path(__file__).parent / "model_params.json"

BIG5 = ("EPL", "La Liga", "Bundesliga", "Serie A", "Ligue 1")
SECOND = {"Championship": "EPL", "La Liga 2": "La Liga", "2. Bundesliga": "Bundesliga",
          "Serie B": "Serie A", "Ligue 2": "Ligue 1"}
TIER = {**{lg: 1 for lg in BIG5}, **{lg: 2 for lg in SECOND}}
COUNTRY = {**{lg: lg for lg in BIG5}, **SECOND}
EUROPE = ("Champions League", "Europa League", "Conference League",          # cross-league competitions
          "Champions League qualifying", "Europa League qualifying", "Conference League qualifying")

DEFAULT_PARAMS = {
    "k": 0.06,          # rating learning rate (log-goals per goal of surprise)
    "k_lg": 0.002,      # league base / home advantage learning rate
    "regress": 0.2,     # share of rating removed between seasons
    "cap": 5.0,         # goals above this don't count extra in updates
    "promo_gap": 0.25,  # rating cost of moving up a division (log-goals, attack and defense)
    "new_team": -0.1,   # starting attack and defense for a team never seen
    "rho": -0.08,       # Dixon-Coles low-score correction (negative = more 0-0 and 1-1)
    "home_start": 0.25, # starting home advantage (log-goals)
    "sot_w": 0.0,       # idea 1: weight of shots on target in updates (0 = off)
    "xg_w": 0.0,        # xG idea (plans/soccer_xg.md): weight of Understat expected goals in updates (0 = off)
    "rest_coef": 0.0,   # idea 3: effect of rest-day difference (0 = off)
    "rest_cap": 7,
    "elo_w": 0.0,       # idea 2: weight of ClubElo difference (0 = off)
}
EU_DEFAULTS = {
    "eu_k_s": 0.05,         # league strength learning rate (European games)
    "eu_k_lg": 0.01,        # European average-goals / home-advantage learning rate
    "eu_home_start": 0.25,  # starting European home advantage (log-goals)
    "eu_k_team": 0.0,       # UCL idea 1: club ratings learn from European games (0 = off)
    "eu_regress_s": 0.0,    # UCL idea 2: share of league strength removed between seasons (0 = off)
}
MAX_GOALS = 10


def load_games(conn, include_europe=False):
    """All club soccer games in the history, oldest first, with rest days filled in. European
    competition games are left out unless include_europe (the domestic model doesn't use them)."""
    rows = conn.execute(
        "SELECT id, league, season, game_date_et, kickoff_utc, home_team, away_team, home_score, away_score,"
        " home_shots_ot, away_shots_ot, home_xg, away_xg, neutral_site FROM hist_games WHERE sport = 'soccer_club'"
        + ("" if include_europe else f" AND league NOT IN ({','.join(repr(x) for x in EUROPE)})")
        + " ORDER BY game_date_et, COALESCE(kickoff_utc, game_date_et), id").fetchall()
    games = [dict(r) for r in rows]
    last = {}
    from datetime import date
    for g in games:
        if g["league"] in EUROPE:            # rest days count league games only (as tuned)
            g["home_rest"] = g["away_rest"] = None
            continue
        d = date.fromisoformat(g["game_date_et"])
        for side in ("home", "away"):
            prev = last.get(g[f"{side}_team"])
            g[f"{side}_rest"] = (d - prev).days if prev and (d - prev).days <= 30 else None
            last[g[f"{side}_team"]] = d
    return games


def outcome_probs(lh, la, rho):
    """(P home win, P draw, P away win) from expected goals, Poisson + Dixon-Coles."""
    ph = [math.exp(-lh)]
    pa = [math.exp(-la)]
    for n in range(1, MAX_GOALS + 1):
        ph.append(ph[-1] * lh / n)
        pa.append(pa[-1] * la / n)
    home = draw = away = 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = ph[i] * pa[j]
            if i <= 1 and j <= 1:
                p *= (1 - lh * la * rho if i == j == 0 else 1 + lh * rho if (i, j) == (0, 1)
                      else 1 + la * rho if (i, j) == (1, 0) else 1 - rho)
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
    total = home + draw + away
    return home / total, draw / total, away / total


class Ratings:
    def __init__(self, params, elo=None):
        self.p = {**DEFAULT_PARAMS, **params}
        self.att = defaultdict(float)
        self.dfn = defaultdict(float)
        self.team_league = {}
        self.team_season = {}
        self.base = defaultdict(lambda: math.log(1.35))
        self.home = defaultdict(lambda: self.p["home_start"])
        self.sot_ratio = defaultdict(lambda: 0.32)   # goals per shot on target, per league
        self.elo = elo or {}
        self.e = {**EU_DEFAULTS, **{k: v for k, v in params.items() if k.startswith("eu_")}}
        self.strength = defaultdict(float)          # league strength from European games (log-goals)
        self.strength_season = {}
        self.eu_base = math.log(1.35)
        self.eu_home = self.e["eu_home_start"]

    def _arrive(self, team, league, season):
        """Season regression and promotion/relegation shift, at a team's first game of a season."""
        p = self.p
        if team not in self.team_league:
            self.att[team] = self.dfn[team] = p["new_team"]
        elif self.team_season[team] != season:
            self.att[team] *= 1 - p["regress"]
            self.dfn[team] *= 1 - p["regress"]
            old = self.team_league[team]
            if COUNTRY.get(old) == COUNTRY.get(league) and TIER.get(old) != TIER.get(league):
                shift = p["promo_gap"] if TIER[league] > TIER[old] else -p["promo_gap"]  # relegated: +, promoted: -
                self.att[team] += shift
                self.dfn[team] += shift
        self.team_league[team] = league
        self.team_season[team] = season

    def _euro_leagues(self, g):
        """Domestic leagues of both clubs, or None if either has no domestic history yet."""
        lh, la = self.team_league.get(g["home_team"]), self.team_league.get(g["away_team"])
        if lh is None or la is None:
            return None
        for lg in {lh, la}:
            if self.e["eu_regress_s"] and self.strength_season.get(lg) not in (None, g["season"]):
                self.strength[lg] *= 1 - self.e["eu_regress_s"]
            self.strength_season[lg] = g["season"]
        return lh, la

    def expected_goals(self, g):
        """(xG home, xG away), or None for a European game with a club we have no domestic history for."""
        if g["league"] in EUROPE:
            leagues = self._euro_leagues(g)
            if leagues is None:
                return None
            h, a = g["home_team"], g["away_team"]
            sh, sa = self.strength[leagues[0]] / 2, self.strength[leagues[1]] / 2
            hfa = 0.0 if g.get("neutral_site") else self.eu_home
            xh = self.eu_base + hfa + (self.att[h] + sh) - (self.dfn[a] + sa)
            xa = self.eu_base + (self.att[a] + sa) - (self.dfn[h] + sh)
            return math.exp(xh), math.exp(xa)
        p, lg = self.p, g["league"]
        h, a = g["home_team"], g["away_team"]
        self._arrive(h, lg, g["season"])
        self._arrive(a, lg, g["season"])
        hfa = 0.0 if g.get("neutral_site") else self.home[lg]
        xh = self.base[lg] + hfa + self.att[h] - self.dfn[a]
        xa = self.base[lg] + self.att[a] - self.dfn[h]
        if p["rest_coef"] and g.get("home_rest") and g.get("away_rest"):
            r = (min(g["home_rest"], p["rest_cap"]) - min(g["away_rest"], p["rest_cap"])) / 7
            xh += p["rest_coef"] * r
            xa -= p["rest_coef"] * r
        if p["elo_w"]:
            eh, ea = self.elo.get((g["id"], "home")), self.elo.get((g["id"], "away"))
            if eh is not None and ea is not None:
                d = (eh - ea) / 1000
                xh += p["elo_w"] * d
                xa -= p["elo_w"] * d
        return math.exp(xh), math.exp(xa)

    def update_europe(self, g, lh, la):
        p, e = self.p, self.e
        eh = min(g["home_score"], p["cap"]) - lh
        ea = min(g["away_score"], p["cap"]) - la
        lg_h, lg_a = self.team_league[g["home_team"]], self.team_league[g["away_team"]]
        if lg_h != lg_a:
            self.strength[lg_h] += e["eu_k_s"] * (eh - ea) / 2
            self.strength[lg_a] += e["eu_k_s"] * (ea - eh) / 2
        self.eu_base += e["eu_k_lg"] * (eh + ea) / 2
        if not g.get("neutral_site"):
            self.eu_home += e["eu_k_lg"] * (eh - ea) / 2
        if e["eu_k_team"]:
            h, a = g["home_team"], g["away_team"]
            self.att[h] += e["eu_k_team"] * eh
            self.dfn[a] -= e["eu_k_team"] * eh
            self.att[a] += e["eu_k_team"] * ea
            self.dfn[h] -= e["eu_k_team"] * ea

    def update(self, g, lh, la):
        if g["league"] in EUROPE:
            return self.update_europe(g, lh, la)
        p, lg = self.p, g["league"]
        gh, ga = min(g["home_score"], p["cap"]), min(g["away_score"], p["cap"])
        xg_w = p.get("xg_w", 0.0) if g.get("home_xg") is not None and g.get("away_xg") is not None else 0.0
        if p["sot_w"] and g.get("home_shots_ot") is not None and g.get("away_shots_ot") is not None:
            ratio = self.sot_ratio[lg]
            sot_w = min(p["sot_w"], 1 - xg_w)
            gh = (1 - sot_w - xg_w) * gh + sot_w * ratio * g["home_shots_ot"] + xg_w * g["home_xg"] if xg_w else \
                (1 - p["sot_w"]) * gh + p["sot_w"] * ratio * g["home_shots_ot"]
            ga = (1 - sot_w - xg_w) * ga + sot_w * ratio * g["away_shots_ot"] + xg_w * g["away_xg"] if xg_w else \
                (1 - p["sot_w"]) * ga + p["sot_w"] * ratio * g["away_shots_ot"]
            shots = g["home_shots_ot"] + g["away_shots_ot"]
            if shots:
                self.sot_ratio[lg] += 0.002 * ((g["home_score"] + g["away_score"]) / shots - self.sot_ratio[lg])
        elif xg_w:
            gh, ga = (1 - xg_w) * gh + xg_w * g["home_xg"], (1 - xg_w) * ga + xg_w * g["away_xg"]
        eh, ea = gh - lh, ga - la
        h, a = g["home_team"], g["away_team"]
        self.att[h] += p["k"] * eh
        self.dfn[a] -= p["k"] * eh
        self.att[a] += p["k"] * ea
        self.dfn[h] -= p["k"] * ea
        self.base[lg] += p["k_lg"] * (eh + ea) / 2
        if not g.get("neutral_site"):
            self.home[lg] += p["k_lg"] * (eh - ea) / 2


def walk_forward(games, params, elo=None, keep=lambda g: True):
    """{game id: (P home, P draw, P away, xG home, xG away)} for games where keep(g) is true,
    each predicted from games before it only. Returns (predictions, final Ratings)."""
    r = Ratings(params, elo)
    rho = r.p["rho"]
    preds = {}
    for g in games:
        xg = r.expected_goals(g)
        if xg is None:
            continue                       # European game with a club we can't rate yet
        lh, la = xg
        if keep(g):
            preds[g["id"]] = (*outcome_probs(lh, la, rho), lh, la)
        r.update(g, lh, la)
    return preds, r


def load_params():
    return json.loads(PARAMS_PATH.read_text())["soccer_club"]

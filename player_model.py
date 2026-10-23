"""NBA player ratings from box scores, and what a team is missing when players are out.

Plan and pre-registration: plans/player_impact.md. Everything is walk-forward: a game is scored
with ratings built from earlier games only.

Per player, two running measures (recency-weighted, minutes-weighted averages):
- production: Hollinger game score per 36 minutes (points, shooting efficiency, rebounds, assists,
  turnovers, steals, blocks, fouls; fixed weights);
- impact: plus-minus per 36 minutes on court.
Both start at the league's replacement level and move toward the evidence at a tuned rate (a player
with few minutes stays near replacement: the "not a fluke" rule). Between seasons they shrink toward
the prior. Each is standardized against the previous season's rotation players (z-scores), then mixed:
rating_z = (1 - w_imp) * z_production + w_imp * z_impact.

Value to the roster per game = (rating_z - replacement_z) * expected minutes / 36, where expected
minutes is the player's recent minutes per game. When a rotation player (10+ minutes per game, seen
with the team recently) doesn't play, the team is "missing" that value; the team model turns the
home-minus-away missing value into points of margin with one coefficient (abs_coef).

Idea #1 ("minutes only") sets every rotation player's rating to a constant, so value = minutes / 36.
Player OVR (display) places the per-game value on a frozen bell curve of past rotation-player seasons.
"""

import math
from collections import defaultdict
from datetime import date

PRIOR = {"prod": 7.0, "imp": -2.0}      # replacement-level starting points (game score / 36, +/- per 36)
SCALE_DEFAULT = {"prod": (11.5, 4.5), "imp": (0.0, 6.0)}   # (mean, sd) used until a season has ended

DEFAULTS = {
    "alpha": 0.08,          # how fast a player's measures move per 36 minutes of evidence
    "season_regress": 0.3,  # share of a player's measures pulled back to the prior between seasons
    "w_imp": 0.0,           # weight of impact (+/-) vs production in the rating (idea #3 tunes it)
    "repl_z": -0.6,         # replacement level, in z-units
    "min_mpg": 10.0,        # rotation = players at or above this many minutes per game
    "window_days": 21,      # a player counts as on the roster if seen with the team this recently
    "idea": 2,              # 1 = minutes only, 2 = production, 3 = production + impact
}


def game_score(r):
    """Hollinger game score for one player-game row (dict with the box-score columns)."""
    g = lambda k: r[k] or 0
    return (g("points") + 0.4 * g("fg_made") - 0.7 * g("fg_att") - 0.4 * (g("ft_att") - g("ft_made"))
            + 0.7 * g("oreb") + 0.3 * g("dreb") + g("stl") + 0.7 * g("ast") + 0.7 * g("blk")
            - 0.4 * g("pf") - g("tov"))


def load_box(conn):
    """{hist game id: [player rows]} for every fetched NBA game."""
    out = defaultdict(list)
    for r in conn.execute("SELECT p.* FROM hist_player_games p JOIN hist_games g ON g.id = p.hist_game_id"
                          " WHERE g.sport = 'nba'"):
        out[r["hist_game_id"]].append(dict(r))
    return out


class PlayerBook:
    def __init__(self, params=None):
        self.p = {**DEFAULTS, **(params or {})}
        self.st = {}                 # player id -> state
        self.scale = dict(SCALE_DEFAULT)
        self.season = None
        self.season_snapshots = {}   # season -> [(player id, name, team, position, value, rating_z, mpg)] at season end

    # ---------- ratings ----------
    def _state(self, pid):
        if pid not in self.st:
            self.st[pid] = {"prod": PRIOR["prod"], "imp": PRIOR["imp"], "mpg": 0.0, "n": 0.0,
                            "team": None, "last": None, "season": None, "name": "", "pos": None}
        return self.st[pid]

    def z(self, s):
        zp = (s["prod"] - self.scale["prod"][0]) / self.scale["prod"][1]
        zi = (s["imp"] - self.scale["imp"][0]) / self.scale["imp"][1]
        return (1 - self.p["w_imp"]) * zp + self.p["w_imp"] * zi

    def value(self, s):
        """Per-game value to the roster, in the model's units (z-units x share of 36 minutes)."""
        if self.p["idea"] == 1:
            return s["mpg"] / 36
        return (self.z(s) - self.p["repl_z"]) * s["mpg"] / 36

    def _start_season(self, season):
        if self.season is not None and season != self.season:
            rot = [s for s in self.st.values() if s["mpg"] >= self.p["min_mpg"] and s["n"] >= 5 and s["season"] == self.season]
            self.season_snapshots[self.season] = [(pid, s["name"], s["team"], s["pos"], self.value(s), self.z(s), s["mpg"])
                                                  for pid, s in self.st.items() if s in rot]
            if len(rot) >= 50:
                for k in ("prod", "imp"):
                    xs = [s[k] for s in rot]
                    mu = sum(xs) / len(xs)
                    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs)) or 1.0
                    self.scale[k] = (mu, sd)
            r = self.p["season_regress"]
            for s in self.st.values():
                s["prod"] += r * (PRIOR["prod"] - s["prod"])
                s["imp"] += r * (PRIOR["imp"] - s["imp"])
                s["n"] *= 1 - r
        self.season = season

    def rotation(self, team, on_date):
        """Rotation players currently on this team."""
        out = []
        for pid, s in self.st.items():
            if s["team"] == team and s["last"] and (on_date - s["last"]).days <= self.p["window_days"] \
                    and s["mpg"] >= self.p["min_mpg"]:
                out.append((pid, s))
        return out

    def before_game(self, g, rows):
        """(home missing value, away missing value, {team: [absent (name, value)]}) using earlier games only."""
        self._start_season(g["season"])
        on_date = date.fromisoformat(g["game_date_et"])
        played = {(r["team"], r["player_id"]) for r in rows if r["played"]}
        missing, absent = {}, {}
        for team in (g["home_team"], g["away_team"]):
            tot, lst = 0.0, []
            for pid, s in self.rotation(team, on_date):
                if (team, pid) not in played:
                    v = self.value(s)
                    tot += v
                    lst.append((s["name"], round(v, 3)))
            missing[team], absent[team] = tot, lst
        return missing[g["home_team"]], missing[g["away_team"]], absent

    def after_game(self, g, rows):
        on_date = date.fromisoformat(g["game_date_et"])
        a = self.p["alpha"]
        for r in rows:
            s = self._state(r["player_id"])
            s.update(team=r["team"], last=on_date, season=g["season"], name=r["player_name"], pos=r["pos"] if "pos" in r else r.get("position"))
            if not r["played"] or not r["minutes"] or r["minutes"] < 1:
                continue
            m = r["minutes"]
            share = m / 36
            prod = game_score(r) / m * 36
            s["prod"] += a * share * (prod - s["prod"])
            if r["plus_minus"] is not None:
                s["imp"] += a * share * (r["plus_minus"] / m * 36 - s["imp"])
            s["mpg"] += 0.15 * (m - s["mpg"]) if s["n"] > 0 else (m - s["mpg"])
            s["n"] += share


def features(games, box, params=None):
    """{game id: (home missing, away missing, absent lists)} for every game, walk-forward.
    Returns (features, final PlayerBook)."""
    book = PlayerBook(params)
    out = {}
    for g in games:
        rows = box.get(g["id"], [])
        out[g["id"]] = book.before_game(g, rows) if rows else (0.0, 0.0, {})
        if rows:
            book.after_game(g, rows)
    return out, book

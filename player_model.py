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

Live (nba-v2, kept idea #2): the saved settings live under nba.players in model_params.json. History
games get their missing values from box scores (`attach`, also used by model.load_games so rankings and
predictions see the same ratings); upcoming games get theirs from ESPN's injury list (`espn_injuries`,
players marked Out) plus Claude's sourced facts (`absences`).
"""

import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
PARAMS_PATH = Path(__file__).parent / "model_params.json"

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
    # Early-season ideas (plans/player_early_season.md); off = nba-v2 exactly
    "regress_to": "replacement",   # idea 5: "average" = pull toward last season's average rotation player
    "carry_unseen": False,         # idea 6: last season's rotation players count as missing until they first play
}


def game_score(r):
    """Hollinger game score for one player-game row (dict with the box-score columns)."""
    g = lambda k: r[k] or 0
    return (g("points") + 0.4 * g("fg_made") - 0.7 * g("fg_att") - 0.4 * (g("ft_att") - g("ft_made"))
            + 0.7 * g("oreb") + 0.3 * g("dreb") + g("stl") + 0.7 * g("ast") + 0.7 * g("blk")
            - 0.4 * g("pf") - g("tov"))


def load_box(conn, sport="nba"):
    """{hist game id: [player rows]} for every fetched game of a sport (NBA, or college from CBBD)."""
    out = defaultdict(list)
    for r in conn.execute("SELECT p.* FROM hist_player_games p JOIN hist_games g ON g.id = p.hist_game_id"
                          " WHERE g.sport = ?", (sport,)):
        out[r["hist_game_id"]].append(dict(r))
    return out


class PlayerBook:
    def __init__(self, params=None):
        self.p = {**DEFAULTS, **(params or {})}
        self.st = {}                 # player id -> state
        self.scale = dict(SCALE_DEFAULT)
        self.season = None
        self.season_snapshots = {}   # season -> [(player id, name, team, position, value, rating_z, mpg)] at season end
        self.carry = {}              # idea 6: team -> [player ids] in its rotation at the end of last season
        self.first_play = {}         # idea 6 (history stand-in): (player id, season) -> (first date played, team)

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

    def start_season(self, season):
        """Public: roll the book into a season (live use before the season's first game)."""
        self._start_season(season)

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
            self.carry = defaultdict(list)
            for pid, s in self.st.items():
                if s in rot:
                    self.carry[s["team"]].append(pid)
            r = self.p["season_regress"]
            target = PRIOR if self.p.get("regress_to", "replacement") == "replacement" else \
                {"prod": self.scale["prod"][0], "imp": self.scale["imp"][0]}
            for s in self.st.values():
                s["prod"] += r * (target["prod"] - s["prod"])
                s["imp"] += r * (target["imp"] - s["imp"])
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
            if self.p.get("carry_unseen"):
                seen = {pid for pid, _ in self.rotation(team, on_date)}
                for pid in self.carry.get(team, []):
                    fp = self.first_play.get((pid, g["season"]))
                    if pid in seen or (team, pid) in played or not fp or fp[1] != team or fp[0] <= on_date:
                        continue
                    s = self.st[pid]
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
    if book.p.get("carry_unseen"):
        book.first_play = first_appearances(games, box)
    out = {}
    for g in games:
        rows = box.get(g["id"], [])
        out[g["id"]] = book.before_game(g, rows) if rows else (0.0, 0.0, {})
        if rows:
            book.after_game(g, rows)
    return out, book


def first_appearances(games, box):
    """(player id, season) -> (date of first game played that season, team): the history stand-in for
    "on this team's roster but injured" in idea 6 (plans/player_early_season.md)."""
    out = {}
    for g in games:
        for r in box.get(g["id"], []):
            if r["played"] and r["minutes"] and r["minutes"] >= 1 and (r["player_id"], g["season"]) not in out:
                out[(r["player_id"], g["season"])] = (date.fromisoformat(g["game_date_et"]), r["team"])
    return out


# ---------- live use (nba-v2) ----------

def saved_settings():
    """The live player settings (nba.players in model_params.json), or None (player feature off)."""
    if not PARAMS_PATH.exists():
        return None
    return json.loads(PARAMS_PATH.read_text()).get("nba", {}).get("players")


def attach(conn, games, settings=None):
    """Give each NBA history game home_missing / away_missing (None where the box score is unknown),
    walk-forward, with the saved settings. Returns the PlayerBook after the last game (today's player
    ratings), or None when the player feature is off."""
    settings = settings or saved_settings()
    if not settings:
        return None
    feats, book = features(games, load_box(conn), dict(settings["params"], idea=settings["idea"]))
    for g in games:
        f = feats.get(g["id"])
        g["home_missing"], g["away_missing"] = (f[0], f[1]) if f and f[2] else (None, None)
    return book


def espn_injuries():
    """{team code: [{"id", "name", "status", "detail", "date"}]} from ESPN's public NBA injury list.
    Raises RuntimeError if it can't be read: callers stop rather than guess (no fake data)."""
    from pull_history import fetch
    try:
        data = json.loads(fetch(INJURIES_URL).decode())
        teams = data["injuries"]
    except Exception as e:                      # network, bad JSON, or a changed format
        raise RuntimeError(f"ESPN's NBA injury list couldn't be read ({e}).") from e
    out = defaultdict(list)
    for t in teams:
        for i in t.get("injuries") or []:
            a = i.get("athlete") or {}
            team = (a.get("team") or {}).get("abbreviation")
            m = next((re.search(r"/id/(\d+)", l.get("href", "")) for l in a.get("links") or []
                      if re.search(r"/id/(\d+)", l.get("href", ""))), None)
            if not team or not m:
                continue
            d = i.get("details") or {}
            detail = " ".join(x for x in (d.get("type"), f"({d['detail']})" if d.get("detail") else None) if x)
            out[team].append({"id": m.group(1), "name": a.get("displayName", ""), "status": i.get("status", ""),
                              "detail": detail, "date": i.get("date")})
    return dict(out)


def plain(name):
    """Name for matching: no accents, punctuation or case ("Nikola Jokić" = "nikola jokic")."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", n.lower()).strip()


def absences(book, team, on_date, injuries=(), facts=()):
    """What a team is missing for a game on `on_date`: rotation players marked Out on ESPN's injury
    list, plus Claude's 'out' facts, minus Claude's 'playing' facts (the latest fact per player wins).
    Returns (missing value, out list, listed list): out entries {id, name, value, source}; listed =
    rotation players on the injury list with another status (e.g. Day-To-Day), counted as playing."""
    rot = dict(book.rotation(team, on_date))
    state = {}
    for i in injuries:
        if i["id"] in rot:
            state[i["id"]] = ("out" if i["status"].lower() == "out" else i["status"], "ESPN injury list")
    for f in facts:
        pid = f["player_id"]
        if pid in rot:
            state[pid] = (f["status"], f"Claude, fact {f['id']}")
    out, listed = [], []
    for pid, (st, src) in state.items():
        s = rot[pid]
        if st == "out":
            out.append({"id": pid, "name": s["name"], "value": round(book.value(s), 3), "source": src})
        elif st != "playing":
            listed.append({"id": pid, "name": s["name"], "status": st})
    out.sort(key=lambda x: -x["value"])
    return sum(x["value"] for x in out), out, listed


def find_in_rotation(book, team, on_date, name):
    """(player id, state) of the rotation player on `team` whose name matches, or None."""
    want = plain(name)
    hits = [(pid, s) for pid, s in book.rotation(team, on_date) if plain(s["name"]) == want]
    return hits[0] if len(hits) == 1 else None

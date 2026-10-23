"""NBA players for display: OVR, team rosters, player profiles, player rankings (plans/player_display.md).

Display only: nothing here is stored in the logbook and no probability depends on it. Everything comes
from the live NBA model's player book (player_model.py), so a player's OVR is built from the same number
the model charges when they sit out: their value per game, in points of margin.

Player OVR: that value ranked among every rotation player's end-of-season value from 2015-16 on, then
placed on the same bell curve as team OVR (62 = typical rotation player, 80+ = top ~7%, 90+ = top ~1%),
frozen per model version in rankings_scale.json (key "nba_players").
"""

import json
import statistics
import sys
import time
from datetime import datetime, timezone

import db
import model
import player_model as pm
from pull_history import current_season, season_label

SCALE_KEY = "nba_players"
FIRST_SCALE_SEASON = 2016          # 2015-16 (2014-15 is the warm-up season)
CACHE_SECONDS = 600
QUANTILES = 1000
HEADSHOT = "https://a.espncdn.com/i/headshots/nba/players/full/{}.png"
_cache = {}


def position_group(pos):
    """G / F / C from ESPN's positions (older box scores use PG, SG, SF, PF)."""
    p = (pos or "").upper()
    return "C" if p.startswith("C") else "F" if p.endswith("F") or p.startswith("F") else "G" if p.endswith("G") or p.startswith("G") else "?"


def _cached(key, build):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = build()
    _cache[key] = (time.time(), value)
    return value


def live_book(conn):
    """{"book", "coef", "version", "season"} for the live NBA model, rebuilt when box scores or the
    model change (and at most every 10 minutes)."""
    params = model.load_params("nba")
    settings = params.get("players")
    if not settings:
        raise RuntimeError("The NBA player feature is off, so there are no player ratings.")
    stamp = conn.execute("SELECT COUNT(*), MAX(pulled_at) FROM hist_box_pulled").fetchone()
    key = ("book", params["version"], tuple(stamp))

    def build():
        games = model.load_games(conn, "nba", players=False)
        book = pm.attach(conn, games, settings)
        season = current_season("nba")
        book.start_season(season)
        return {"book": book, "coef": params["ratings"].get("abs_coef", 0.0), "season": season,
                "version": f'{params["version"]}+{settings.get("version", "")}'}
    return _cached(key, build)


def injuries():
    """ESPN's injury list by team ({} with an error note if it can't be read), cached 10 minutes."""
    def build():
        try:
            return pm.espn_injuries(), None
        except RuntimeError as e:
            return {}, str(e)
    return _cached(("injuries",), build)


# ---------- OVR ----------

def scale(conn, lb):
    """Frozen reference: quantiles of every rotation player-season's end-of-season value (points)."""
    path = __import__("rankings").SCALE_PATH
    saved = json.loads(path.read_text()) if path.exists() else {}
    ref = saved.get(SCALE_KEY)
    if ref and ref["model_version"] == lb["version"]:
        return ref
    xs = sorted(lb["coef"] * row[4] for season, rows in lb["book"].season_snapshots.items()
                if season >= FIRST_SCALE_SEASON for row in rows)
    n = len(xs)

    def at(q):
        pos = q * (n - 1)
        lo = int(pos)
        return xs[lo] + (xs[min(lo + 1, n - 1)] - xs[lo]) * (pos - lo)
    seasons = [s for s in lb["book"].season_snapshots if s >= FIRST_SCALE_SEASON]
    saved[SCALE_KEY] = {"model_version": lb["version"], "player_seasons": n, "seasons": [min(seasons), max(seasons)],
                        "built_utc": db.to_utc(datetime.now(timezone.utc)),
                        "quantiles": [round(at(i / QUANTILES), 5) for i in range(QUANTILES + 1)]}
    path.write_text(json.dumps(saved, indent=1) + "\n")
    print(f"Froze the NBA player OVR scale from {n} player-seasons.", file=sys.stderr)
    return saved[SCALE_KEY]


def ovr(points, ref):
    """OVR from a value in points: rank among past player-seasons, then the bell curve (as team OVR)."""
    import rankings
    qs, n = ref["quantiles"], ref["player_seasons"]
    if points <= qs[0]:
        frac = 0.0
    elif points >= qs[-1]:
        frac = 1.0
    else:
        lo, hi = 0, len(qs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if qs[mid] <= points else (lo, mid)
        frac = (lo + (points - qs[lo]) / (qs[hi] - qs[lo] or 1)) / QUANTILES
    frac = min(max(frac, 0.5 / n), 1 - 0.5 / n)
    return max(1, min(99, int(rankings.OVR_MID + rankings.OVR_PER_SD * statistics.NormalDist().inv_cdf(frac) + 0.5)))


# ---------- rows ----------

def _row(pid, name, team, pos, points, mpg, ref, rotation):
    return {"id": pid, "name": name, "team": team, "pos": position_group(pos), "points": round(points, 1),
            "mpg": round(mpg, 1), "ovr": ovr(points, ref) if rotation else None, "headshot": HEADSHOT.format(pid)}


def current_rows(conn, lb=None):
    """Every player seen this season (played or listed), with OVR for rotation players (10+ minutes)."""
    lb = lb or live_book(conn)
    ref, book, coef = scale(conn, lb), lb["book"], lb["coef"]
    out = []
    for pid, s in book.st.items():
        if s["season"] != lb["season"]:
            continue
        out.append(_row(pid, s["name"], s["team"], s["pos"], coef * book.value(s), s["mpg"], ref,
                        s["mpg"] >= book.p["min_mpg"]))
    return out


def season_rows(conn, season):
    """Ranked rotation players for a season: live for the current one, end-of-season values for past ones."""
    lb = live_book(conn)
    if season == lb["season"]:
        rows = [r for r in current_rows(conn, lb) if r["ovr"] is not None]
    else:
        ref = scale(conn, lb)
        rows = [_row(pid, name, team, pos, lb["coef"] * v, mpg, ref, True)
                for pid, name, team, pos, v, z, mpg in lb["book"].season_snapshots.get(season, [])]
    rows.sort(key=lambda r: -r["points"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def seasons(conn):
    """Seasons with player rankings, newest first: [(season, label)]."""
    lb = live_book(conn)
    past = sorted((s for s in lb["book"].season_snapshots if s >= FIRST_SCALE_SEASON), reverse=True)
    return [(lb["season"], f'{season_label("nba", lb["season"])} (this season)')] + [(s, season_label("nba", s)) for s in past]


def roster(conn, team):
    """Players on a team now: seen with it this season, plus anyone ESPN lists as injured for it."""
    lb = live_book(conn)
    inj, inj_error = injuries()
    listed = {i["id"]: i for i in inj.get(team, [])}
    rows = [r for r in current_rows(conn, lb) if r["team"] == team]
    have = {r["id"] for r in rows}
    ref, book = scale(conn, lb), lb["book"]
    for pid, i in listed.items():
        if pid not in have:
            s = book.st.get(pid)
            if s:
                r = _row(pid, s["name"], team, s["pos"], lb["coef"] * book.value(s), s["mpg"], ref,
                         s["mpg"] >= book.p["min_mpg"])
                r["not_yet"] = True
            else:
                r = {"id": pid, "name": i["name"], "team": team, "pos": "?", "points": None, "mpg": None,
                     "ovr": None, "headshot": HEADSHOT.format(pid), "not_yet": True}
            rows.append(r)
    for r in rows:
        i = listed.get(r["id"])
        r["status"] = i["status"] if i else None
        r["detail"] = i["detail"] if i else None
    rows.sort(key=lambda r: (r["ovr"] is None, -(r["ovr"] or 0), -(r["points"] if r["points"] is not None else -99)))
    return {"team": team, "rows": rows, "injury_error": inj_error, "season": lb["season"]}


def _averages(conn, pid, season):
    r = conn.execute(
        "SELECT COUNT(*) gp, AVG(p.minutes) mpg, AVG(p.points) pts, AVG(coalesce(p.oreb,0) + coalesce(p.dreb,0)) reb,"
        " AVG(p.ast) ast, AVG(p.stl) stl, AVG(p.blk) blk, AVG(p.tov) tov, AVG(p.plus_minus) pm,"
        " SUM(p.fg_made) fgm, SUM(p.fg_att) fga, SUM(p.tp_made) tpm, SUM(p.tp_att) tpa, SUM(p.ft_made) ftm, SUM(p.ft_att) fta"
        " FROM hist_player_games p JOIN hist_games g ON g.id = p.hist_game_id"
        " WHERE p.player_id = ? AND g.sport = 'nba' AND g.season = ? AND p.played = 1 AND p.minutes >= 1",
        (pid, season)).fetchone()
    if not r["gp"]:
        return None
    pct = lambda m, a: round(100 * m / a, 1) if a else None
    return {"label": season_label("nba", season), "gp": r["gp"], "mpg": round(r["mpg"], 1), "pts": round(r["pts"], 1),
            "reb": round(r["reb"], 1), "ast": round(r["ast"], 1), "stl": round(r["stl"] or 0, 1),
            "blk": round(r["blk"] or 0, 1), "tov": round(r["tov"] or 0, 1), "pm": round(r["pm"] or 0, 1),
            "fg": pct(r["fgm"], r["fga"]), "tp": pct(r["tpm"], r["tpa"]), "ft": pct(r["ftm"], r["fta"])}


def profile(conn, pid):
    """Everything the player page shows, or None if we have no box scores for this id."""
    lb = live_book(conn)
    book, coef, cur = lb["book"], lb["coef"], lb["season"]
    s = book.st.get(pid)
    if s is None:
        return None
    ref = scale(conn, lb)
    rotation = s["mpg"] >= book.p["min_mpg"]
    me = _row(pid, s["name"], s["team"], s["pos"], coef * book.value(s), s["mpg"], ref, rotation)
    me["this_season"] = s["season"] == cur
    if me["ovr"] is not None and me["this_season"]:
        ranked = season_rows(conn, cur)
        mine = next((r for r in ranked if r["id"] == pid), None)
        if mine:
            me["rank"], me["of"] = mine["rank"], len(ranked)
            same = [r for r in ranked if r["pos"] == me["pos"]]
            me["pos_rank"], me["pos_of"] = next(i for i, r in enumerate(same, 1) if r["id"] == pid), len(same)
    inj, inj_error = injuries()
    me["injury"] = next((i for i in inj.get(s["team"], []) if i["id"] == pid), None)
    me["injury_error"] = inj_error
    me["notes"] = [dict(r) for r in conn.execute(
        "SELECT f.status, f.reason, f.source_url, f.created_at, g.away_team, g.home_team, g.start_time_utc"
        " FROM player_facts f JOIN games g ON g.id = f.game_id WHERE f.player_id = ?"
        " ORDER BY f.created_at DESC LIMIT 10", (pid,))]
    for n in me["notes"]:
        n["time"], n["game"] = db.fmt_et(n["created_at"]), f'{n["away_team"]} at {n["home_team"]}'
    me["recent"] = []
    for r in conn.execute(
            "SELECT g.game_date_et, g.home_team, g.away_team, g.home_score, g.away_score, p.* FROM hist_player_games p"
            " JOIN hist_games g ON g.id = p.hist_game_id WHERE p.player_id = ? AND g.sport = 'nba'"
            " ORDER BY g.game_date_et DESC LIMIT 5", (pid,)):
        home = r["team"] == r["home_team"]
        us, them = (r["home_score"], r["away_score"]) if home else (r["away_score"], r["home_score"])
        me["recent"].append({"date": r["game_date_et"], "opp": ("vs " if home else "at ") + (r["away_team"] if home else r["home_team"]),
                             "result": f'{"W" if us > them else "L"} {us}-{them}', "played": bool(r["played"]) and (r["minutes"] or 0) >= 1,
                             "reason": r["reason"], "min": r["minutes"], "pts": r["points"],
                             "reb": (r["oreb"] or 0) + (r["dreb"] or 0), "ast": r["ast"], "pm": r["plus_minus"]})
    me["averages"] = [a for a in (_averages(conn, pid, cur), _averages(conn, pid, cur - 1)) if a]
    me["history"] = []
    for season in sorted(book.season_snapshots):
        if season < FIRST_SCALE_SEASON:
            continue
        row = next((x for x in book.season_snapshots[season] if x[0] == pid), None)
        if row:
            me["history"].append((season_label("nba", season), ovr(coef * row[4], ref), row[2]))
    if me["ovr"] is not None and me["this_season"]:
        me["history"].append((season_label("nba", cur), me["ovr"], s["team"]))
    return me

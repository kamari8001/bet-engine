"""Power rankings: every team ranked by the model's own current rating, with an OVR (0-99).

Usage: python3 rankings.py nfl | ncaaf | nba | ncaab  [--top N]

- Strength = the team's rating in the same model the predictions use: offense + defense, in
  points above an average team (NFL: plus the starting QB the engine expects next game).
- Step 1: the model's chance that the team beats an average team of its league on a neutral field.
  College football uses its combiner, so preseason information counts early in the season.
- Step 2 (OVR, FIFA-style): where that chance ranks among EVERY team-season in our history for the
  sport (finished seasons, final ratings), turned into a bell-curve score: OVR = 62 + 12 x z, where z
  is the normal-curve value of that rank, rounded and kept between 1 and 99. So: average team = 62,
  top ~16% of all teams ever = 74+, top ~7% = 80+, top 1% = 90+, top 0.1% = 98; bottom ~16% = 50 or less.
  Using rank (not raw distance from average) keeps college's extreme teams from all piling up at 99.
  The reference ranking is computed once per model version and frozen in rankings_scale.json, so OVR
  means the same thing in every season: a 95 was more dominant over its league than an 88.
- Past seasons: each team's rating after its last game (playoffs included); NFL with the QB who
  started that game. Cached in cache/rankings_history_<sport>.json (rebuilt if the model changes).
- Movement compares with the ranking a week ago (current season only).
Display only: nothing goes into the logbook.

Club soccer (soccer_club): all Big 5 clubs in one ranking. A club's own-league rating (from the
soccer model) is shifted by its league's strength from UEFA's country coefficients
(uefa_coefficients.json; the ranking known before that season), by config.SOCCER_LEAGUE_STRENGTH,
then compared with an average Big 5 club on a neutral field: chance = P(win) + half of P(draw).
That league shift is an outside assumption, not measured from our data. Seasons 2012-13 on.

Also: python3 rankings.py <sport> --season 2017 | --all-time | --team KC | --rebuild
"""

import json
import math
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import combiner
import config
import db
import model
from pull_history import current_season, season_label

CACHE = Path(__file__).parent / "cache"
FBS_CACHE = CACHE / "cfbd_fbs.json"
SCALE_PATH = Path(__file__).parent / "rankings_scale.json"
OVR_MID, OVR_PER_SD = 62, 12
_memo = {}          # (sport, as-of date) -> (computed at, rows)
MEMO_SECONDS = 600
EARLY = {"nfl": 3, "ncaaf": 3, "nba": 10, "ncaab": 10, "soccer_club": 5}
SOCCER_FIRST_SEASON = 2013      # first season with a UEFA ranking in uefa_coefficients.json (ranking 2012)
UEFA_PATH = Path(__file__).parent / "uefa_coefficients.json"   # games played before ratings are "settled"


def fbs_teams(season):
    """{school: conference} for FBS teams (1 CFBD call, cached for a week)."""
    fresh = FBS_CACHE.exists() and time.time() - FBS_CACHE.stat().st_mtime < 7 * 86400
    if not fresh and config.CFBD_API_KEY:
        try:
            req = urllib.request.Request(f"https://api.collegefootballdata.com/teams/fbs?year={season}",
                                         headers={"Authorization": f"Bearer {config.CFBD_API_KEY}"})
            out = {t["school"]: t.get("conference") for t in json.load(urllib.request.urlopen(req, timeout=30))}
            CACHE.mkdir(exist_ok=True)
            FBS_CACHE.write_text(json.dumps(out))
            return out
        except Exception:
            pass  # fall back to an older cache
    try:
        return json.loads(FBS_CACHE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        raise RuntimeError("FBS team list unavailable (CFBD unreachable and no cached copy)")


def ncaab_conferences():
    """{school: conference}; where CBBD lists two schools with one name (e.g. Holy Cross), the one
    with a conference (the Division I school) wins."""
    from teams import cbbd_teams
    out = {}
    for t in cbbd_teams():
        if t.get("conference") or t["school"] not in out:
            out[t["school"]] = t.get("conference")
    return out


def ranked_teams(conn, sport, history, season, live=True):
    """{team: conference or None} for the teams that get a ranking. Past seasons (live=False)
    use only that season's games: NFL/NBA teams that played, FBS teams (college football), and
    college basketball teams with 15+ games (Division I schools; others play only a few D1 games)."""
    if not live:
        counts, fbs = {}, set()
        for g in history:
            if g["season"] == season:
                for side in ("home", "away"):
                    t = model.NFL_FRANCHISE.get(g[f"{side}_team"], g[f"{side}_team"]) if sport == "nfl" else g[f"{side}_team"]
                    counts[t] = counts.get(t, 0) + 1
                    if g.get(f"{side}_division") == "fbs":
                        fbs.add(t)
        if sport == "ncaaf":
            return {t: None for t in fbs}
        if sport == "ncaab":
            return {t: None for t, n in counts.items() if n >= 15}
        if sport == "nba":
            from pull_basketball_history import NBA_TEAMS
            return {t: None for t in counts if t in NBA_TEAMS}
        return {t: None for t in counts}
    if sport == "nfl":
        names = {model.NFL_FRANCHISE.get(t, t) for g in history if g["season"] >= season - 1
                 for t in (g["home_team"], g["away_team"])}
        return {t: None for t in names}
    if sport == "nba":
        from pull_basketball_history import NBA_TEAMS
        return {t: None for t in NBA_TEAMS}
    if sport == "ncaaf":
        return fbs_teams(season)
    # college basketball: Division I schools (a conference in CBBD) with 10+ games this season or last
    counts = {}
    for g in history:
        if g["season"] >= season - 1:
            for t in (g["home_team"], g["away_team"]):
                counts[(g["season"], t)] = counts.get((g["season"], t), 0) + 1
    conf = ncaab_conferences()
    return {t: conf[t] for (s, t), n in counts.items() if n >= 10 and conf.get(t)}


def expected_qbs(conn, history):
    """NFL: {team: (QB id, name)} the engine expects next game (latest logged prediction for the
    team's next game, Claude's if any), else the team's most recent starter."""
    out = {}
    for g in history:
        for side in ("home", "away"):
            if g.get(f"{side}_starter_id"):
                out[model.NFL_FRANCHISE.get(g[f"{side}_team"], g[f"{side}_team"])] = (g[f"{side}_starter_id"], None)
    now = db.to_utc(datetime.now(timezone.utc))
    rows = conn.execute(
        "SELECT g.home_team, g.away_team, p.note, p.source FROM games g JOIN predictions p ON p.game_id = g.id"
        " WHERE g.sport = 'nfl' AND g.start_time_utc > ? AND p.corrects_id IS NULL"
        " ORDER BY g.start_time_utc DESC, (p.source = 'claude'), p.created_at, p.id", (now,)).fetchall()
    for r in rows:  # later rows win: earliest game, Claude's latest
        try:
            inp = json.loads(r["note"] or "{}").get("inputs", {})
        except json.JSONDecodeError:
            continue
        for side in ("home", "away"):
            if inp.get(f"{side}_starter_id"):
                out[r[f"{side}_team"]] = (inp[f"{side}_starter_id"], inp.get(f"{side}_starter_name"))
    return out


def _symmetric(prob_home):
    """Chance team beats average on a neutral field, from a function giving P(first side wins)
    with (team first) and (average first); averaging both orders removes any home/intercept lean."""
    return (prob_home(True) + 1 - prob_home(False)) / 2


def compute(conn, sport, as_of=None, season=None, games=None):
    """Ranking rows (best first). Current season: using only games before `as_of` (a date, Eastern;
    default today). A past `season`: ratings after that season's last game. Rows carry `p`, the
    chance to beat an average team; `rate()` turns it into OVR."""
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date()
    as_of = as_of or today
    live = season is None or season == current_season(sport)
    season = current_season(sport) if live else season
    key = (sport, as_of.isoformat() if live else f"season-{season}")
    hit = _memo.get(key)
    if hit and time.time() - hit[0] < MEMO_SECONDS:
        return hit[1]

    if sport == "soccer_club":
        rows = soccer_compute(conn, season, live, as_of, games)
        _memo[key] = (time.time(), rows)
        return rows
    params = model.load_params(sport)
    games = games if games is not None else model.load_games(conn, sport)
    if live:
        history = [g for g in games if g["game_date_et"] < as_of.isoformat()]
    else:
        history = [g for g in games if g["season"] <= season]
    _, m = model.walk_forward(history, params["ratings"], sport)
    if live:
        m.start_season(season)
    teams = ranked_teams(conn, sport, history, season, live)
    qbs = expected_qbs(conn, history) if sport == "nfl" and live and as_of == today else (
        expected_qbs_from_history(history) if sport == "nfl" else {})

    played, record, form = {}, {}, {}
    for g in history:
        if g["season"] != season:
            continue
        for side, other in (("home", "away"), ("away", "home")):
            t = model.NFL_FRANCHISE.get(g[f"{side}_team"], g[f"{side}_team"]) if sport == "nfl" else g[f"{side}_team"]
            res = "W" if g[f"{side}_score"] > g[f"{other}_score"] else "L" if g[f"{side}_score"] < g[f"{other}_score"] else "T"
            played[t] = played.get(t, 0) + 1
            w, l, ti = record.get(t, (0, 0, 0))
            record[t] = (w + (res == "W"), l + (res == "L"), ti + (res == "T"))
            form[t] = (form.get(t, "") + res)[-5:]

    rows = []
    for t, conf in teams.items():
        if t not in m.off:
            continue  # no games in the history yet
        qb = 0.0
        qb_name = None
        if sport == "nfl" and t in qbs:
            qid, qb_name = qbs[t]
            qb = m.qb.get(qid, params["ratings"].get("new_qb", 0.0))
        rows.append({"team": t, "conference": conf, "off": m.off[t] + qb, "def": m.dfn[t], "qb": qb_name,
                     "played": played.get(t, 0), "record": record.get(t, (0, 0, 0)), "form": form.get(t, "")})
    if not rows:
        return []
    avg_off = statistics.mean(r["off"] for r in rows)
    avg_def = statistics.mean(r["def"] for r in rows)
    sigma = params["ratings"]["sigma"]
    cal = params.get("calibration") or {"a": 1.0, "b": 0.0}
    comb = params.get("combiner")
    team_seasons = combiner.load_team_seasons(conn, sport) if comb else {}
    if comb:
        fields = ("talent", "prev_sp", "returning_pct")
        avg_ts = {f: statistics.mean(v[f] for (s, tm), v in team_seasons.items()
                                     if s == season and tm in teams and v.get(f) is not None)
                  for f in fields if any(s == season and v.get(f) is not None for (s, _), v in team_seasons.items())}
        team_seasons = {**team_seasons, (season, "__average__"): avg_ts}

    for r in rows:
        r["net"] = (r["off"] - avg_off) + (r["def"] - avg_def)   # points better than an average team
        if comb:
            def p_first(team_first, r=r):
                a, b = (r["team"], "__average__") if team_first else ("__average__", r["team"])
                margin = r["net"] if team_first else -r["net"]
                g = {"season": season, "home_team": a, "away_team": b, "neutral_site": 1}
                f = combiner.features(g, margin, (r["played"], r["played"]), team_seasons)
                return combiner.probability(comb, f)
            p = _symmetric(p_first)
        else:
            def p_first(team_first, r=r):
                p = model.normal_cdf((r["net"] if team_first else -r["net"]) / sigma)
                if cal != {"a": 1.0, "b": 0.0}:
                    import backtest
                    p = backtest.calibrate(p, cal)
                return p
            p = _symmetric(p_first)
        r["p"] = p

    rows.sort(key=lambda r: -r["p"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["season"] = season
    for key_, field in (("off_rank", "off"), ("def_rank", "def")):
        for i, r in enumerate(sorted(rows, key=lambda r: -r[field]), 1):
            r[key_] = i
    _memo[key] = (time.time(), rows)
    return rows


def expected_qbs_from_history(history):
    out = {}
    for g in history:
        for side in ("home", "away"):
            if g.get(f"{side}_starter_id"):
                out[model.NFL_FRANCHISE.get(g[f"{side}_team"], g[f"{side}_team"])] = (g[f"{side}_starter_id"], None)
    return out


def with_movement(conn, sport):
    """Today's rows, each with `move` = places gained since a week ago (None if unranked then)."""
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date()
    now = rate(conn, sport, compute(conn, sport, today))
    before = {r["team"]: r["rank"] for r in compute(conn, sport, today - timedelta(days=7))}
    for r in now:
        r["move"] = before[r["team"]] - r["rank"] if r["team"] in before else None
    return now


# ---------- club soccer ----------

def _model_version(sport):
    """The model version the cached history and frozen scale belong to (soccer: plus the league
    strength setting, since changing it changes every club's chance)."""
    if sport == "soccer_club":
        import soccer_model as sm
        return f'{sm.load_params()["version"]}+league{config.SOCCER_LEAGUE_STRENGTH}'
    return model.load_params(sport)["version"]


def uefa_shift(season):
    """{league: log-goal shift} for a season, from the UEFA ranking known before it started."""
    data = json.loads(UEFA_PATH.read_text())["rankings"]
    coef = data.get(str(season - 1))
    if coef is None:
        raise RuntimeError(f"no UEFA ranking for {season - 2}-{(season - 1) % 100:02d} in uefa_coefficients.json; "
                           "add it (with its source) before ranking this season")
    avg = statistics.mean(coef.values())
    return {lg: config.SOCCER_LEAGUE_STRENGTH * math.log(c / avg) for lg, c in coef.items()}


def soccer_compute(conn, season, live, as_of, games=None):
    import soccer_model as sm
    params = sm.load_params()["ratings"]
    games = games if games is not None else sm.load_games(conn)
    history = ([g for g in games if g["game_date_et"] < as_of.isoformat()] if live
               else [g for g in games if g["season"] <= season])
    _, r = sm.walk_forward(history, params, keep=lambda g: False)
    shift = uefa_shift(season)
    base = statistics.mean(r.base[lg] for lg in sm.BIG5)     # an average Big 5 scoring level
    rho = r.p["rho"]

    played, record, form = {}, {}, {}
    for g in history:
        if g["season"] != season or g["league"] not in sm.BIG5:
            continue
        for side, other in (("home", "away"), ("away", "home")):
            t = g[f"{side}_team"]
            res = "W" if g[f"{side}_score"] > g[f"{other}_score"] else "L" if g[f"{side}_score"] < g[f"{other}_score"] else "D"
            played[t] = played.get(t, 0) + 1
            w, l, d = record.get(t, (0, 0, 0))
            record[t] = (w + (res == "W"), l + (res == "L"), d + (res == "D"))
            form[t] = (form.get(t, "") + res)[-5:]

    rows = []
    for t, lg in r.team_league.items():
        if lg not in sm.BIG5 or r.team_season.get(t) != season:
            continue
        o = shift[lg] / 2
        att, dfn = r.att[t] + o, r.dfn[t] + o
        xg_for, xg_against = math.exp(base + att), math.exp(base - dfn)
        ph, pd, pa = sm.outcome_probs(xg_for, xg_against, rho)
        rows.append({"team": t, "conference": lg, "off": att, "def": dfn, "qb": None, "p": ph + pd / 2,
                     "net": xg_for - xg_against, "played": played.get(t, 0), "record": record.get(t, (0, 0, 0)),
                     "form": form.get(t, "")})
    rows.sort(key=lambda x: -x["p"])
    for i, x in enumerate(rows, 1):
        x["rank"] = i
        x["season"] = season
    for key_, field in (("off_rank", "off"), ("def_rank", "def")):
        for i, x in enumerate(sorted(rows, key=lambda x: -x[field]), 1):
            x[key_] = i
    return rows


# ---------- OVR scale and past seasons ----------

def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _history_path(sport):
    return CACHE / f"rankings_history_{sport}.json"


def past_seasons(conn, sport, rebuild=False):
    """{season: rows} for every finished season (warm-up season excluded), cached per model version."""
    version = _model_version(sport)
    path = _history_path(sport)
    if not rebuild and path.exists():
        try:
            data = json.loads(path.read_text())
            if data["model_version"] == version:
                return {int(k): v for k, v in data["seasons"].items()}
        except (json.JSONDecodeError, KeyError):
            pass
    if sport == "soccer_club":
        import soccer_model as sm
        games = sm.load_games(conn)
        seasons = [s for s in sorted({g["season"] for g in games}) if s >= SOCCER_FIRST_SEASON]
        version = sm.load_params()["version"]
    else:
        games = model.load_games(conn, sport)
        seasons = sorted({g["season"] for g in games})[1:]   # the first season is the model's warm-up
    out = {}
    for s in seasons:
        if s == current_season(sport):
            continue
        print(f"  {sport} {season_label(sport, s)}...", file=sys.stderr, flush=True)
        rows = compute(conn, sport, season=s, games=games)
        out[s] = [{k: r[k] for k in ("team", "p", "rank", "record", "form", "net", "off_rank", "def_rank", "season",
                                     "conference")} for r in rows]
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps({"model_version": version, "built_utc": db.to_utc(datetime.now(timezone.utc)),
                                "seasons": out}))
    return out


QUANTILES = 1000


def scale(conn, sport):
    """The frozen reference for a sport: log-odds of every past team-season's chance, summarized as
    1,001 evenly spaced quantiles (0th, 0.1th, ... 100th percentile). Built from all finished seasons
    the first time, and again only when the model version changes; stored in rankings_scale.json."""
    saved = json.loads(SCALE_PATH.read_text()) if SCALE_PATH.exists() else {}
    version = _model_version(sport)
    if sport in saved and saved[sport]["model_version"] == version and "quantiles" in saved[sport]:
        return saved[sport]
    seasons = past_seasons(conn, sport)
    xs = sorted(logit(r["p"]) for rows in seasons.values() for r in rows)
    n = len(xs)

    def at(q):
        pos = q * (n - 1)
        lo = int(pos)
        return xs[lo] + (xs[min(lo + 1, n - 1)] - xs[lo]) * (pos - lo)
    saved[sport] = {"model_version": version, "team_seasons": n, "seasons": [min(seasons), max(seasons)],
                    "built_utc": db.to_utc(datetime.now(timezone.utc)),
                    "quantiles": [round(at(i / QUANTILES), 5) for i in range(QUANTILES + 1)]}
    SCALE_PATH.write_text(json.dumps(saved, indent=1) + "\n")
    print(f"Froze the {sport} OVR scale from {n} team-seasons ({min(seasons)}-{max(seasons)}).", file=sys.stderr)
    return saved[sport]


_NORMAL = statistics.NormalDist()


def ovr(p, ref):
    """OVR from a chance, using the frozen reference: rank among past team-seasons -> bell curve."""
    x, qs, n = logit(p), ref["quantiles"], ref["team_seasons"]
    if x <= qs[0]:
        frac = 0.0
    elif x >= qs[-1]:
        frac = 1.0
    else:
        lo, hi = 0, len(qs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if qs[mid] <= x else (lo, mid)
        frac = (lo + (x - qs[lo]) / (qs[hi] - qs[lo] or 1)) / QUANTILES
    frac = min(max(frac, 0.5 / n), 1 - 0.5 / n)          # the best/worst ever sit just inside the ends
    return max(1, min(99, int(OVR_MID + OVR_PER_SD * _NORMAL.inv_cdf(frac) + 0.5)))


def rate(conn, sport, rows):
    ref = scale(conn, sport)
    for r in rows:
        r["ovr"] = ovr(r["p"], ref)
    return rows


def season_rows(conn, sport, season):
    """Rows for one season with OVR: the current season live (with movement), a past one final."""
    if season == current_season(sport):
        return with_movement(conn, sport)
    rows = [dict(r, qb=None, move=None) for r in past_seasons(conn, sport).get(season, [])]
    if sport != "soccer_club":
        for r in rows:
            r["conference"] = None          # conferences change over the years; only today's list is known
    return rate(conn, sport, rows)


def all_time(conn, sport, top=25):
    """The best team-seasons ever (final ratings of finished seasons, plus the current season so far)."""
    rows = [dict(r) for rs in past_seasons(conn, sport).values() for r in rs]
    rows += [dict(r, current=True) for r in compute(conn, sport)]
    rate(conn, sport, rows)
    rows.sort(key=lambda r: -r["p"])
    return rows[:top]


def team_history(conn, sport, team):
    """[(season, row)] for one team, oldest first, current season included."""
    out = [(s, r) for s, rs in sorted(past_seasons(conn, sport).items()) for r in rs if r["team"] == team]
    out += [(r["season"], r) for r in compute(conn, sport) if r["team"] == team]
    rate(conn, sport, [r for _, r in out])
    return out


def early_season(rows, sport):
    played = [r["played"] for r in rows]
    return bool(played) and statistics.median(played) < EARLY[sport]


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("nfl", "ncaaf", "nba", "ncaab", "soccer_club"):
        sys.exit(__doc__)
    sport = args[0]
    top = int(args[args.index("--top") + 1]) if "--top" in args else 25
    conn = db.connect()
    if "--rebuild" in args:
        past_seasons(conn, sport, rebuild=True)
        print(f"Rebuilt {sport} season history.")
        return
    if "--all-time" in args:
        print(f"{'#':>3}  {'team':<22}{'season':>9}{'OVR':>5}{'record':>9}")
        for i, r in enumerate(all_time(conn, sport, top), 1):
            w, l, t = r["record"]
            print(f"{i:>3}  {r['team']:<22}{season_label(sport, r['season']):>9}{r['ovr']:>5}"
                  f"{f'{w}-{l}' + (f'-{t}' if t else ''):>9}" + ("  (so far)" if r.get("current") else ""))
        return
    if "--team" in args:
        team = args[args.index("--team") + 1]
        for s, r in team_history(conn, sport, team):
            w, l, t = r["record"]
            print(f"{season_label(sport, s):>9}  OVR {r['ovr']:>3}  #{r['rank']:<4} {w}-{l}" + (f"-{t}" if t else ""))
        return
    if "--season" in args:
        rows = season_rows(conn, sport, int(args[args.index("--season") + 1]))
        for r in rows[:top]:
            w, l, t = r["record"]
            print(f"{r['rank']:>3}  {r['team']:<22}{r['ovr']:>4}  {w}-{l}" + (f"-{t}" if t else ""))
        return
    rows = with_movement(conn, sport)
    if early_season(rows, sport):
        print("Early season: ratings are still mostly last season's, pulled toward average.\n")
    print(f"{'#':>3} {'move':>5}  {'team':<22}{'OVR':>4} {'net pts':>8} {'record':>8}  {'last 5':<6} {'off':>4} {'def':>4}  conference")
    for r in rows[:top]:
        w, l, t = r["record"]
        rec = f"{w}-{l}" + (f"-{t}" if t else "")
        mv = "new" if r["move"] is None else "-" if r["move"] == 0 else (f"▲{r['move']}" if r["move"] > 0 else f"▼{-r['move']}")
        print(f"{r['rank']:>3} {mv:>5}  {r['team']:<22}{r['ovr']:>4} {r['net']:>+8.1f} {rec:>8}  {r['form']:<6} "
              f"{r['off_rank']:>4} {r['def_rank']:>4}  {r['conference'] or ''}")
    print(f"\n{len(rows)} teams ranked. OVR: 62 = average team, 80+ great, 90+ historically great (same scale every season).")


if __name__ == "__main__":
    main()

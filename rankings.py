"""Power rankings: every team ranked by the model's own current rating, with an OVR (0-99).

Usage: python3 rankings.py nfl | ncaaf | nba | ncaab  [--top N]

- Strength = the team's rating in the same model the predictions use: offense + defense, in
  points above an average team (NFL: plus the starting QB the engine expects next game).
- OVR = the model's chance (in %) that the team beats an average team of its league on a
  neutral field, rounded to a whole number and capped at 99. About 50 = average.
  College football uses its combiner, so preseason information counts early in the season.
- Movement compares with the ranking a week ago (same model, only games before then).
Display only: nothing is stored, so the logbook is untouched.
"""

import json
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
from pull_history import current_season

CACHE = Path(__file__).parent / "cache"
FBS_CACHE = CACHE / "cfbd_fbs.json"
_memo = {}          # (sport, as-of date) -> (computed at, rows)
MEMO_SECONDS = 600
EARLY = {"nfl": 3, "ncaaf": 3, "nba": 10, "ncaab": 10}   # games played before ratings are "settled"


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


def ranked_teams(conn, sport, history, season):
    """{team: conference or None} for the teams that get a ranking."""
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


def compute(conn, sport, as_of=None):
    """Ranking rows (best first) using only games before `as_of` (a date, Eastern; default today)."""
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date()
    as_of = as_of or today
    key = (sport, as_of.isoformat())
    hit = _memo.get(key)
    if hit and time.time() - hit[0] < MEMO_SECONDS:
        return hit[1]

    params = model.load_params(sport)
    season = current_season(sport)
    history = [g for g in model.load_games(conn, sport) if g["game_date_et"] < as_of.isoformat()]
    _, m = model.walk_forward(history, params["ratings"], sport)
    m.start_season(season)
    teams = ranked_teams(conn, sport, history, season)
    qbs = expected_qbs(conn, history) if sport == "nfl" and as_of == today else (
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
        r["ovr"] = max(0, min(99, int(p * 100 + 0.5)))

    rows.sort(key=lambda r: -r["p"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
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
    now = compute(conn, sport, today)
    before = {r["team"]: r["rank"] for r in compute(conn, sport, today - timedelta(days=7))}
    for r in now:
        r["move"] = before[r["team"]] - r["rank"] if r["team"] in before else None
    return now


def early_season(rows, sport):
    played = [r["played"] for r in rows]
    return bool(played) and statistics.median(played) < EARLY[sport]


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("nfl", "ncaaf", "nba", "ncaab"):
        sys.exit(__doc__)
    sport = args[0]
    top = int(args[args.index("--top") + 1]) if "--top" in args else 25
    conn = db.connect()
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
    print(f"\n{len(rows)} teams ranked. OVR = chance to beat an average team on a neutral field.")


if __name__ == "__main__":
    main()

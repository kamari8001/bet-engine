"""Log engine and Claude predictions for upcoming games, then print the slate.

Usage: python3 predict.py nfl | ncaaf  [--days N]   (default: next 7 days)

Run first: pull_games.py, pull_odds.py, and pull_history.py <sport> --current.

- engine row: the base model with automatic data only. NFL starters come from
  nflverse; if nflverse doesn't list one, the team's most recent starter is
  assumed (marked "assumed" in the logged inputs).
- claude row: the same formula rerun with starters Claude confirmed from the
  news (lineup_facts), plus Claude's capped adjustments. Only logged when
  such facts or adjustments exist.
- A new row is logged only if there's no earlier one, the probability moved by
  1 point or more, or the starters changed. The latest row before kickoff is
  the one that gets graded.
- Stops without logging if past results are missing (ratings would be stale).
  Won't flag edges against odds older than ODDS_MAX_AGE.
"""

import csv
import io
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone

import combiner
import config
import db
import model
from cautions import game_warnings
from odds_math import decimal_odds, fair_moneyline, no_vig
from pull_history import CURRENT_SEASON, NFLVERSE_GAMES, blank, current_season, fetch

RELOG_MOVE = 0.01
ODDS_MAX_AGE = timedelta(hours=3)
RESULT_GRACE = timedelta(hours=5)   # a game this long past kickoff should have a result


def utc_now():
    return datetime.now(timezone.utc)


def parse_utc(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


# ---------- safety checks ----------

def check_history_current(conn, sport):
    """Every live game that should be over must be in the history, or ratings are stale."""
    cutoff = db.to_utc(utc_now() - RESULT_GRACE)
    missing = conn.execute(
        "SELECT g.* FROM games g WHERE g.sport = ? AND g.start_time_utc < ?"
        " AND NOT EXISTS (SELECT 1 FROM hist_games h WHERE h.source = g.source"
        "                 AND h.external_id = g.external_id)"
        " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = g.id AND r.status = 'cancelled')",
        (sport, cutoff)).fetchall()
    if missing:
        lines = "\n".join(f"  {db.fmt_et(g['start_time_utc'])}  {g['away_team']} at {g['home_team']}"
                          for g in missing)
        sys.exit(f"STOP: {len(missing)} finished game(s) have no result in the history yet:\n{lines}\n"
                 f"Run `python3 pull_history.py {sport} --current` and try again. If the source "
                 "hasn't posted them, ratings would be stale, so nothing was logged.\n"
                 "If a game was cancelled or postponed: `python3 game_status.py cancel <id> <link> <reason>` "
                 "or `python3 game_status.py postpone <id> \"YYYY-MM-DD HH:MM\" <link> <reason>`.")


# ---------- inputs for upcoming games ----------

def nfl_inputs(conn, games):
    """{game id: input dict} using nflverse's upcoming rows; assumes the most
    recent starter when nflverse doesn't list one."""
    rows = {r["game_id"]: r for r in csv.DictReader(io.StringIO(fetch(NFLVERSE_GAMES).decode()))
            if r["season"] == str(CURRENT_SEASON)}
    out = {}
    for g in games:
        r = rows.get(g["external_id"])
        if r is None:
            sys.exit(f"STOP: {g['away_team']} at {g['home_team']} ({g['external_id']}) "
                     "is missing from nflverse's schedule.")
        inp = {"kickoff_et": db.utc_to_eastern(g["start_time_utc"]).strftime("%Y-%m-%d %H:%M"),
               "home_rest_days": None if blank(r["home_rest"]) else int(r["home_rest"]),
               "away_rest_days": None if blank(r["away_rest"]) else int(r["away_rest"]),
               "home_coach": None if blank(r["home_coach"]) else r["home_coach"],
               "away_coach": None if blank(r["away_coach"]) else r["away_coach"]}
        for side in ("home", "away"):
            if not blank(r[f"{side}_qb_id"]):
                inp[f"{side}_starter_id"] = r[f"{side}_qb_id"]
                inp[f"{side}_starter_name"] = r[f"{side}_qb_name"]
                inp[f"{side}_starter_status"] = "expected (nflverse)"
            else:
                last = last_starter(conn, g[f"{side}_team"])
                inp[f"{side}_starter_id"] = last[0] if last else None
                inp[f"{side}_starter_name"] = last[1] if last else None
                inp[f"{side}_starter_status"] = "assumed (most recent starter)"
        out[g["id"]] = inp
    return out


def basketball_inputs(conn, sport, games):
    """{game id: {rest days, kickoff}}: days since each team's previous game (scheduled or
    finished), from the live schedule and this season's history. None after a 30+ day break."""
    def last_game_date(team, before_utc):
        live = conn.execute("SELECT MAX(start_time_utc) FROM games WHERE sport = ? AND ? IN (home_team, away_team)"
                            " AND start_time_utc < ? AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id"
                            " AND r.status = 'cancelled')", (sport, team, before_utc)).fetchone()[0]
        hist = conn.execute("SELECT MAX(kickoff_utc) FROM hist_games WHERE sport = ? AND ? IN (home_team, away_team)"
                            " AND kickoff_utc < ?", (sport, team, before_utc)).fetchone()[0]
        last = max(x for x in (live, hist, "") if x is not None)
        return db.utc_to_eastern(last).date() if last else None
    out = {}
    for g in games:
        day = db.utc_to_eastern(g["start_time_utc"]).date()
        inp = {"kickoff_et": db.utc_to_eastern(g["start_time_utc"]).strftime("%Y-%m-%d %H:%M")}
        for side in ("home", "away"):
            prev = last_game_date(g[f"{side}_team"], g["start_time_utc"])
            gap = (day - prev).days if prev else None
            inp[f"{side}_rest_days"] = gap if gap is not None and gap <= 30 else None
        out[g["id"]] = inp
    return out


def last_starter(conn, team):
    teams = [team] + [old for old, new in model.NFL_FRANCHISE.items() if new == team]
    marks = ",".join("?" * len(teams))
    r = conn.execute(
        f"SELECT CASE WHEN home_team IN ({marks}) THEN home_starter_id ELSE away_starter_id END,"
        f"       CASE WHEN home_team IN ({marks}) THEN home_starter_name ELSE away_starter_name END"
        f" FROM hist_games WHERE sport = 'nfl' AND (home_team IN ({marks}) OR away_team IN ({marks}))"
        " ORDER BY game_date_et DESC, kickoff_utc DESC LIMIT 1", teams * 4).fetchone()
    return (r[0], r[1]) if r and r[0] else None


def confirmed_starters(conn, game_id):
    """Latest QB fact per team for this game: {team: row}."""
    out = {}
    for r in conn.execute("SELECT * FROM lineup_facts WHERE game_id = ? AND role = 'QB'"
                          " ORDER BY created_at, id", (game_id,)):
        out[r["team"]] = r
    return out


# ---------- the model ----------

class Engine:
    def __init__(self, conn, sport):
        self.conn, self.sport = conn, sport
        self.params = model.load_params(sport)
        self.history = model.load_games(conn, sport)
        _, self.model = model.walk_forward(self.history, self.params["ratings"], sport)
        self.season = current_season(sport)
        self.model.start_season(self.season)
        self.cal = self.params.get("calibration") or {"a": 1.0, "b": 0.0}
        self.comb = self.params.get("combiner")
        if self.comb:
            self.team_seasons = combiner.load_team_seasons(conn, sport)
            self.played = {}
            for h in self.history:
                if h["season"] == self.season:
                    for t in (h["home_team"], h["away_team"]):
                        self.played[t] = self.played.get(t, 0) + 1

    def predict(self, g, inputs):
        """(home pts, away pts, P(home wins)) for a live game with given inputs."""
        gd = dict(g, season=self.season, home_division="fbs" if self.sport == "ncaaf" else None,
                  away_division="fbs" if self.sport == "ncaaf" else None, **inputs)
        # Look ahead without changing the model: copy state the prepare step touches
        saved = (dict(self.model.off), dict(self.model.dfn), dict(self.model.eoff),
                 dict(self.model.edef), dict(self.model.coach), dict(self.model.team_season),
                 dict(self.model.games_this_season))
        self.model.prepare(gd)
        home_pts, away_pts, p = self.model.project(gd)
        (self.model.off, self.model.dfn, self.model.eoff, self.model.edef, self.model.coach,
         self.model.team_season, self.model.games_this_season) = saved
        if self.comb:
            f = combiner.features(gd, home_pts - away_pts,
                                  (self.played.get(g["home_team"], 0), self.played.get(g["away_team"], 0)),
                                  self.team_seasons)
            p = combiner.probability(self.comb, f)
            margin = self.params["ratings"]["sigma"] * statistics.NormalDist().inv_cdf(p)
            total = home_pts + away_pts
            home_pts, away_pts = (total + margin) / 2, (total - margin) / 2
        if self.cal != {"a": 1.0, "b": 0.0}:
            import backtest
            p = backtest.calibrate(p, self.cal)
        return home_pts, away_pts, p


# ---------- logging ----------

def latest_prediction(conn, game_id, source):
    return conn.execute("SELECT * FROM predictions WHERE game_id = ? AND source = ? AND corrects_id IS NULL"
                        " ORDER BY created_at DESC, id DESC LIMIT 1", (game_id, source)).fetchone()


def starters_of(note):
    try:
        inp = json.loads(note or "{}").get("inputs", {})
    except json.JSONDecodeError:
        return None
    return (inp.get("home_starter_id"), inp.get("away_starter_id"))


def maybe_log(conn, g, source, pred, inputs, odds_id, version, extra=None):
    """Log a prediction unless an equivalent one is already the latest. Returns 'logged' or 'unchanged'."""
    home_pts, away_pts, p = pred
    p = min(max(p, 0.001), 0.999)
    note = json.dumps({"inputs": inputs, **(extra or {})}, default=str)
    old = latest_prediction(conn, g["id"], source)
    if old and abs(old["p_home"] - p) < RELOG_MOVE and starters_of(old["note"]) == starters_of(note):
        return "unchanged", old
    p = round(p, 4)
    pid = db.add_prediction(conn, g["id"], source, p_home=p, p_away=round(1 - p, 4),
                            proj_home_score=round(home_pts, 1), proj_away_score=round(away_pts, 1),
                            odds_id=odds_id, model_version=version, note=note)
    return "logged", conn.execute("SELECT * FROM predictions WHERE id = ?", (pid,)).fetchone()


# ---------- market ----------

def latest_odds(conn, game_id):
    rows = conn.execute("SELECT * FROM odds WHERE game_id = ? AND captured_at ="
                        " (SELECT MAX(captured_at) FROM odds WHERE game_id = ?) ORDER BY id",
                        (game_id, game_id)).fetchall()
    if not rows:
        return None
    p_home = statistics.mean(no_vig(r["home_ml"], r["away_ml"])[0] for r in rows)
    mine = [r for r in rows if r["bookmaker"] in config.MY_BOOKS]
    best = {}
    for side in ("home", "away"):
        if mine:
            r = max(mine, key=lambda r: decimal_odds(r[f"{side}_ml"]))
            best[side] = (r[f"{side}_ml"], r["bookmaker"])
    return {"odds_id": rows[0]["id"], "captured_at": rows[0]["captured_at"], "p_home": p_home,
            "books": len(rows), "best": best}


# ---------- main ----------

def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("nfl", "ncaaf", "nba", "ncaab"):
        sys.exit(__doc__)
    sport = args[0]
    days = int(args[args.index("--days") + 1]) if "--days" in args else 7
    conn = db.connect()
    check_history_current(conn, sport)

    now = utc_now()
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id)"
        " ORDER BY start_time_utc, id",
        (sport, db.to_utc(now), db.to_utc(now + timedelta(days=days)))).fetchall()
    if not games:
        print(f"No {sport.upper()} games in the next {days} days.")
        return

    engine = Engine(conn, sport)
    version = engine.params["version"]
    inputs = (nfl_inputs(conn, games) if sport == "nfl"
              else basketball_inputs(conn, sport, games) if sport in ("nba", "ncaab")
              else {g["id"]: {} for g in games})
    counts = {"logged": 0, "unchanged": 0}
    print(f"{sport.upper()} slate, next {days} days | model {version} | "
          f"flag threshold {config.EDGE_THRESHOLD:.0%} | your books: {', '.join(config.MY_BOOKS)}")
    print("All flags are LOW CONFIDENCE, PAPER ONLY: this model failed its final exam (see "
          "backtest_results/criteria.md).\n")

    for g in games:
        mkt = latest_odds(conn, g["id"])
        odds_id = mkt["odds_id"] if mkt else None
        eng_inputs = inputs[g["id"]]
        status, eng_row = maybe_log(conn, g, "engine", engine.predict(g, eng_inputs), eng_inputs,
                                    odds_id, version)
        counts[status] += 1

        # Claude row: confirmed starters and/or capped adjustments
        facts = confirmed_starters(conn, g["id"]) if sport == "nfl" else {}
        checks = {r["team"]: r for r in conn.execute(
            "SELECT * FROM qb_checks WHERE game_id = ? ORDER BY created_at, id", (g["id"],))}
        adjust = conn.execute("SELECT * FROM adjustments WHERE game_id = ? ORDER BY created_at",
                              (g["id"],)).fetchall()
        cl_row = None
        if facts or checks or adjust:
            cl_inputs = dict(eng_inputs)
            sources = []
            for side in ("home", "away"):
                f = facts.get(g[f"{side}_team"])
                if f:
                    cl_inputs[f"{side}_starter_id"] = f["player_id"] or f"new:{f['player_name']}"
                    cl_inputs[f"{side}_starter_name"] = f["player_name"]
                    cl_inputs[f"{side}_starter_status"] = f"{f['status']} (Claude, fact {f['id']})"
                    sources.append(f["source_url"])
                elif g[f"{side}_team"] in checks:
                    c = checks[g[f"{side}_team"]]
                    cl_inputs[f"{side}_starter_status"] = f"verified (Claude check {c['id']})"
                    sources.append(c["source_url"])
            hp, ap, p = engine.predict(g, cl_inputs)
            shift = sum(a["d_home"] for a in adjust)
            status, cl_row = maybe_log(conn, g, "claude", (hp, ap, p + shift), cl_inputs, odds_id,
                                       version, {"adjustment_ids": [a["id"] for a in adjust],
                                                 "adjustment_total": shift, "fact_sources": sources})
            counts[status] += 1
        print_game(conn, g, eng_row, cl_row, mkt, now)

    print(f"\nPredictions: {counts['logged']} logged, {counts['unchanged']} unchanged (no new row needed).")


def print_game(conn, g, eng, cl, mkt, now):
    final = cl or eng
    warnings = game_warnings(conn, g, final, mkt, now)
    p = final["p_home"]
    print(f"{db.fmt_et(g['start_time_utc'])}  {g['away_team']} at {g['home_team']}"
          + ("  (neutral site)" if g["neutral_site"] else ""))
    inp = json.loads(final["note"]).get("inputs", {})
    if inp.get("home_starter_name") or inp.get("away_starter_name"):
        print(f"    QBs: {inp.get('away_starter_name')} [{inp.get('away_starter_status')}]"
              f" / {inp.get('home_starter_name')} [{inp.get('home_starter_status')}]")
    print(f"    projected score {g['away_team']} {final['proj_away_score']:.0f} - "
          f"{g['home_team']} {final['proj_home_score']:.0f}")
    line = (f"    engine {g['away_team']} {eng['p_away']:.1%} / {g['home_team']} {eng['p_home']:.1%}")
    if cl:
        line += f"   claude {cl['p_away']:.1%} / {cl['p_home']:.1%}"
    print(line + f"   fair ML {fair_moneyline(1 - p):+d} / {fair_moneyline(p):+d}")
    if not mkt:
        for w in warnings:
            print(f"    ! {w}")
        return
    age = now - parse_utc(mkt["captured_at"])
    stale = age > ODDS_MAX_AGE
    print(f"    market (no-vig, {mkt['books']} books, as of {db.fmt_et(mkt['captured_at'])}"
          + (", STALE: no flags" if stale else "") + f") {1 - mkt['p_home']:.1%} / {mkt['p_home']:.1%}")
    for side, prob, mprob, team in (("away", 1 - p, 1 - mkt["p_home"], g["away_team"]),
                                    ("home", p, mkt["p_home"], g["home_team"])):
        edge = prob - mprob
        best = mkt["best"].get(side)
        price = f"best at your books {best[0]:+d} ({best[1]})" if best else "not offered at your books"
        ev = f", expected profit ${100 * (prob * decimal_odds(best[0]) - 1):+.0f} per $100" if best else ""
        flag = "  << FLAG (low confidence, paper only)" if edge >= config.EDGE_THRESHOLD and not stale and best else ""
        print(f"    {team:<22} edge {edge:+.1%}   {price}{ev}{flag}")
    for w in warnings:
        print(f"    ! {w}")


if __name__ == "__main__":
    main()

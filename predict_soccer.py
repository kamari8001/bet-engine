"""Club soccer predictions: home / draw / away for every Big 5 league game before kickoff.

Usage: python3 predict.py soccer_club [--days N]    (predict.py hands soccer to this file)

Run first: pull_games.py soccer_club, pull_odds.py soccer_club, pull_soccer_history.py current.

- engine row: the soccer model (soccer_model.py, settings soccer_club in model_params.json):
  team attack/defense ratings -> expected goals -> Poisson + Dixon-Coles -> home/draw/away.
- claude row: the engine plus Claude's capped adjustments (news.py), only when some exist.
- A new row is logged when there's no earlier one or any of the three chances moved 1+ point.
- Edges are model minus the no-vig market for each outcome. At most one flag per game: the
  outcome with the largest edge, if it's 4+ points (as in the final exam), at fresh odds.
- Same safety checks as the other sports: a game whose team has a finished game with no result
  loaded is skipped; any result 24+ hours late stops everything.
"""

import json
import statistics
from datetime import timedelta

import config
import db
import soccer_model as sm
from cautions import game_warnings
from odds_math import decimal_odds, fair_moneyline, no_vig
from predict import ODDS_MAX_AGE, RELOG_MOVE, latest_prediction, missing_results, parse_utc, utc_now
from pull_history import current_season

SPORT = "soccer_club"
OUTCOMES = ("home", "draw", "away")


class SoccerEngine:
    """The domestic model plus the European branch (league strengths learned from European games).
    European games don't change domestic ratings (eu_k_team = 0), so league predictions are the same
    as the domestic model alone."""
    def __init__(self, conn):
        self.params = sm.load_params()
        self.europe = self.params.get("europe")
        settings = {**self.params["ratings"], **(self.europe["settings"] if self.europe else {})}
        games = sm.load_games(conn, include_europe=bool(self.europe))
        _, self.r = sm.walk_forward(games, settings, keep=lambda g: False)
        self.season = current_season(SPORT)

    def version_for(self, g):
        if g["league"] in sm.EUROPE and self.europe:
            return f'{self.params["version"]}+{self.europe["version"]}'
        return self.params["version"]

    def predict(self, g, inputs):
        """(xG home, xG away, P home, P draw, P away) for a live game, or None for a European game
        with a club we have no domestic history for."""
        gd = {"league": g["league"], "season": self.season, "home_team": g["home_team"],
              "away_team": g["away_team"], "neutral_site": g["neutral_site"],
              "home_rest": inputs.get("home_rest_days"), "away_rest": inputs.get("away_rest_days")}
        xg = self.r.expected_goals(gd)
        if xg is None:
            return None
        lh, la = xg
        return (lh, la, *sm.outcome_probs(lh, la, self.r.p["rho"]))


def soccer_inputs(conn, games):
    """{game id: {kickoff, rest days}}: days since each team's previous league game (history or
    live schedule); None after a 30+ day break. European games don't count (the model was tuned on
    domestic rest days)."""
    def last_date(team, before_utc):
        live = conn.execute("SELECT MAX(start_time_utc) FROM games WHERE sport = ? AND ? IN (home_team, away_team)"
                            " AND start_time_utc < ? AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id"
                            " AND r.status = 'cancelled')", (SPORT, team, before_utc)).fetchone()[0]
        hist = conn.execute("SELECT MAX(kickoff_utc) FROM hist_games WHERE sport = ? AND ? IN (home_team, away_team)"
                            f" AND kickoff_utc < ? AND league NOT IN ({','.join(repr(x) for x in sm.EUROPE)})",
                            (SPORT, team, before_utc)).fetchone()[0]
        last = max(x for x in (live, hist, "") if x is not None)
        return db.utc_to_eastern(last).date() if last else None
    out = {}
    for g in games:
        day = db.utc_to_eastern(g["start_time_utc"]).date()
        inp = {"kickoff_et": db.utc_to_eastern(g["start_time_utc"]).strftime("%Y-%m-%d %H:%M")}
        for side in ("home", "away"):
            prev = last_date(g[f"{side}_team"], g["start_time_utc"])
            gap = (day - prev).days if prev else None
            inp[f"{side}_rest_days"] = gap if gap is not None and gap <= 30 else None
        out[g["id"]] = inp
    return out


def clean_probs(ph, pd, pa):
    """Clip to [0.001, 0.999], renormalize, round to 4 places; draw takes the rounding remainder."""
    ph, pd, pa = (min(max(x, 0.001), 0.999) for x in (ph, pd, pa))
    total = ph + pd + pa
    ph, pa = round(ph / total, 4), round(pa / total, 4)
    return ph, round(1 - ph - pa, 4), pa


def maybe_log(conn, g, source, pred, inputs, odds_id, version, extra=None):
    """Log a three-way prediction unless the latest one is within RELOG_MOVE on every outcome."""
    lh, la, ph, pd, pa = pred
    ph, pd, pa = clean_probs(ph, pd, pa)
    note = json.dumps({"inputs": inputs, **(extra or {})}, default=str)
    old = latest_prediction(conn, g["id"], source)
    if old and max(abs(old["p_home"] - ph), abs(old["p_draw"] - pd), abs(old["p_away"] - pa)) < RELOG_MOVE:
        return "unchanged", old
    pid = db.add_prediction(conn, g["id"], source, p_home=ph, p_draw=pd, p_away=pa,
                            proj_home_score=round(lh, 2), proj_away_score=round(la, 2),
                            odds_id=odds_id, model_version=version, note=note)
    return "logged", conn.execute("SELECT * FROM predictions WHERE id = ?", (pid,)).fetchone()


def latest_odds(conn, game_id):
    """The latest odds pull: no-vig (home, draw, away) averaged over books, and the best price
    for each outcome at my books."""
    rows = conn.execute("SELECT * FROM odds WHERE game_id = ? AND captured_at ="
                        " (SELECT MAX(captured_at) FROM odds WHERE game_id = ?) ORDER BY id",
                        (game_id, game_id)).fetchall()
    rows = [r for r in rows if r["draw_ml"] is not None]
    if not rows:
        return None
    fair = [no_vig(r["home_ml"], r["draw_ml"], r["away_ml"]) for r in rows]
    p = tuple(statistics.mean(f[i] for f in fair) for i in range(3))
    mine = [r for r in rows if r["bookmaker"] in config.MY_BOOKS]
    best = {}
    for o in OUTCOMES:
        if mine:
            r = max(mine, key=lambda r: decimal_odds(r[f"{o}_ml"]))
            best[o] = (r[f"{o}_ml"], r["bookmaker"])
    return {"odds_id": rows[0]["id"], "captured_at": rows[0]["captured_at"], "p": p, "p_home": p[0],
            "books": len(rows), "best": best}


def flag_outcome(probs, mkt, stale):
    """The one outcome to flag (index), or None: the largest edge, if >= threshold, fresh odds,
    and priced at my books."""
    if mkt is None or stale:
        return None
    edges = [probs[i] - mkt["p"][i] for i in range(3)]
    i = max(range(3), key=lambda k: edges[k])
    if edges[i] >= config.EDGE_THRESHOLD and OUTCOMES[i] in mkt["best"]:
        return i
    return None


def run(conn, days=7):
    waiting = missing_results(conn, SPORT)
    now = utc_now()
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id)"
        " ORDER BY start_time_utc, id", (SPORT, db.to_utc(now), db.to_utc(now + timedelta(days=days)))).fetchall()
    for g in [g for g in games if {g["home_team"], g["away_team"]} & waiting]:
        print(f"Skipped (a team's last result isn't loaded yet): {db.fmt_et(g['start_time_utc'])}  "
              f"{g['away_team']} at {g['home_team']}")
    games = [g for g in games if not {g["home_team"], g["away_team"]} & waiting]
    if not games:
        print(f"No club soccer games in the next {days} days.")
        return

    engine = SoccerEngine(conn)
    inputs = soccer_inputs(conn, games)
    counts = {"logged": 0, "unchanged": 0}
    print(f"Club soccer slate, next {days} days | model {engine.params['version']}"
          + (f" (+ {engine.europe['version']} for European games)" if engine.europe else "") + " | flag threshold "
          f"{config.EDGE_THRESHOLD:.0%} (one per game) | your books: {', '.join(config.MY_BOOKS)}")
    print("All flags are LOW CONFIDENCE, PAPER ONLY: this model failed its final exam's money test "
          "(see backtest_results/criteria_soccer.md).\n")
    league = None
    for g in sorted(games, key=lambda g: (g["league"], g["start_time_utc"], g["id"])):
        if g["league"] != league:
            league = g["league"]
            print(f"== {league} ==")
        mkt = latest_odds(conn, g["id"])
        odds_id = mkt["odds_id"] if mkt else None
        inp = inputs[g["id"]]
        pred = engine.predict(g, inp)
        if pred is None:
            print(f"Skipped (a club has no domestic history to rate it): {db.fmt_et(g['start_time_utc'])}  "
                  f"{g['away_team']} at {g['home_team']}")
            continue
        status, eng = maybe_log(conn, g, "engine", pred, inp, odds_id, engine.version_for(g))
        counts[status] += 1
        adjust = conn.execute("SELECT * FROM adjustments WHERE game_id = ? ORDER BY created_at, id",
                              (g["id"],)).fetchall()
        cl = None
        if adjust:
            lh, la, ph, pd, pa = pred
            dh = sum(a["d_home"] for a in adjust)
            dd = sum(a["d_draw"] or 0 for a in adjust)
            da = sum(a["d_away"] for a in adjust)
            status, cl = maybe_log(conn, g, "claude", (lh, la, ph + dh, pd + dd, pa + da), inp, odds_id,
                                   engine.version_for(g), {"adjustment_ids": [a["id"] for a in adjust],
                                                    "adjustment_total": [dh, dd, da]})
            counts[status] += 1
        print_game(conn, g, eng, cl, mkt, now)
    print(f"\nPredictions: {counts['logged']} logged, {counts['unchanged']} unchanged (no new row needed).")


def print_game(conn, g, eng, cl, mkt, now):
    final = cl or eng
    probs = (final["p_home"], final["p_draw"], final["p_away"])
    print(f"{db.fmt_et(g['start_time_utc'])}  {g['away_team']} at {g['home_team']}"
          + ("  (neutral site)" if g["neutral_site"] else ""))
    print(f"    expected goals {g['home_team']} {final['proj_home_score']:.1f} - {g['away_team']} {final['proj_away_score']:.1f}")
    line = f"    engine home {eng['p_home']:.1%} / draw {eng['p_draw']:.1%} / away {eng['p_away']:.1%}"
    if cl:
        line += f"   claude {cl['p_home']:.1%} / {cl['p_draw']:.1%} / {cl['p_away']:.1%}"
    print(line + "   fair ML " + " / ".join(f"{fair_moneyline(p):+d}" for p in probs))
    warnings = game_warnings(conn, g, final, mkt, now)
    if mkt:
        stale = now - parse_utc(mkt["captured_at"]) > ODDS_MAX_AGE
        print(f"    market (no-vig, {mkt['books']} books, as of {db.fmt_et(mkt['captured_at'])}"
              + (", STALE: no flags" if stale else "") + ") "
              + " / ".join(f"{p:.1%}" for p in mkt["p"]))
        flag = flag_outcome(probs, mkt, stale)
        for i, (o, label) in enumerate(zip(OUTCOMES, (g["home_team"], "Draw", g["away_team"]))):
            best = mkt["best"].get(o)
            price = f"best at your books {best[0]:+d} ({best[1]})" if best else "not offered at your books"
            ev = f", expected profit ${100 * (probs[i] * decimal_odds(best[0]) - 1):+.0f} per $100" if best else ""
            print(f"    {label:<22} edge {probs[i] - mkt['p'][i]:+.1%}   {price}{ev}"
                  + ("  << FLAG (low confidence, paper only)" if flag == i else ""))
    for w in warnings:
        print(f"    ! {w}")

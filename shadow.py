"""Shadow mode: challengers make predictions or bets on real games, logged before
kickoff and kept apart from the real logbook. Definitions and the promotion bar
are pre-registered in backtest_results/shadow_challengers.md; never edit a
challenger here without giving it a new version name.

Usage:
  python3 shadow.py log nfl|ncaaf|all     log every challenger for upcoming games (automation runs this)
  python3 shadow.py report [nfl|ncaaf]    each challenger's scorecard and promotion status
"""

import json
import math
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone

import config
import db
import grade
from odds_math import decimal_odds
from predict import latest_odds
from pull_history import CURRENT_SEASON

RELOG_MOVE = 0.01
POPULAR_NFL = {"DAL", "KC", "GB", "PIT", "SF"}


# ---------- challengers ----------

class NotYetKnown(Exception):
    """The team's latest game hasn't reached the history yet; decide later."""


def previous_margin(conn, sport, team, before_utc):
    """Margin of the team's previous game this season (positive = won by), or None if it
    has none. Raises NotYetKnown if its most recent scheduled game has no result loaded yet."""
    last_live = conn.execute(
        "SELECT g.* FROM games g WHERE g.sport = ? AND ? IN (g.home_team, g.away_team) AND g.start_time_utc < ?"
        " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = g.id AND r.status = 'cancelled')"
        " ORDER BY g.start_time_utc DESC LIMIT 1", (sport, team, before_utc)).fetchone()
    if last_live and not conn.execute("SELECT 1 FROM hist_games WHERE source = ? AND external_id = ?",
                                      (last_live["source"], last_live["external_id"])).fetchone():
        raise NotYetKnown(team)
    r = conn.execute(
        "SELECT * FROM hist_games WHERE sport = ? AND season = ? AND ? IN (home_team, away_team)"
        " AND coalesce(kickoff_utc, game_date_et) < ? ORDER BY game_date_et DESC, kickoff_utc DESC LIMIT 1",
        (sport, CURRENT_SEASON, team, before_utc)).fetchone()
    if r is None:
        return None
    return (r["home_score"] - r["away_score"]) * (1 if r["home_team"] == team else -1)


def rule_after_blowout_loss(conn, g):
    sides = [s for s in ("home", "away")
             if (m := previous_margin(conn, g["sport"], g[f"{s}_team"], g["start_time_utc"])) is not None and m <= -20]
    return sides[0] if len(sides) == 1 else None


def rule_back_popular(conn, g):
    home, away = g["home_team"] in POPULAR_NFL, g["away_team"] in POPULAR_NFL
    return "home" if home and not away else "away" if away and not home else None


def model_market_anchor(conn, g, mkt):
    eng = conn.execute("SELECT p_home FROM predictions WHERE game_id = ? AND source = 'engine'"
                       " AND corrects_id IS NULL ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"],)).fetchone()
    if eng is None or mkt is None:
        return None
    return mkt["p_home"] + 0.25 * (eng["p_home"] - mkt["p_home"])


def rule_dk_sharp_money(conn, g):
    """First recorded DraftKings snapshot where one side's money share beats its bet share by 15+."""
    for s in conn.execute("SELECT * FROM expert_signals WHERE game_id = ? AND source = 'dk_splits'"
                          " ORDER BY created_at, id", (g["id"],)):
        if s["home_handle"] - s["home_bets"] >= 15:
            return "home"
        if s["away_handle"] - s["away_bets"] >= 15:
            return "away"
    return None


def rule_circa_consensus(conn, g):
    """A top-5 Circa Million consensus side."""
    s = conn.execute("SELECT side FROM expert_signals WHERE game_id = ? AND source = 'circa_consensus'"
                     " AND pick_rank <= 5 ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"],)).fetchone()
    return s["side"] if s else None


CHALLENGERS = {
    "nfl_after_blowout_loss_v1": {"type": "rule", "sports": ("nfl",), "fn": rule_after_blowout_loss,
                                  "about": "Bet a team after a 20+ point loss"},
    "nfl_back_popular_v1": {"type": "rule", "sports": ("nfl",), "fn": rule_back_popular,
                            "about": "Bet DAL/KC/GB/PIT/SF"},
    "market_anchor_v1": {"type": "model", "sports": ("nfl", "ncaaf"), "fn": model_market_anchor,
                         "about": "Market + 25% of the way toward the engine"},
    "dk_sharp_money_v1": {"type": "rule", "sports": ("nfl", "ncaaf", "nba", "ncaab"), "fn": rule_dk_sharp_money,
                          "about": "Bet the side with 15+ pts more money than bets (DraftKings splits)"},
    "circa_consensus_v1": {"type": "rule", "sports": ("nfl",), "fn": rule_circa_consensus,
                           "about": "Bet the Circa Million contest's 5 most-picked sides"},
}


# ---------- logging ----------

def log(conn, sport):
    now = datetime.now(timezone.utc)
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id) ORDER BY start_time_utc",
        (sport, db.to_utc(now), db.to_utc(now + timedelta(days=7)))).fetchall()
    counts = {}
    for name, ch in CHALLENGERS.items():
        if sport not in ch["sports"]:
            continue
        n = 0
        for g in games:
            mkt = latest_odds(conn, g["id"])
            try:
                if ch["type"] == "rule":
                    try:
                        side = ch["fn"](conn, g)
                    except NotYetKnown:
                        continue  # wait until the team's last result is loaded
                    if side is None or mkt is None or side not in mkt["best"]:
                        continue  # no bet, or no price at my books yet
                    if conn.execute("SELECT 1 FROM shadow_bets WHERE challenger = ? AND game_id = ?",
                                    (name, g["id"])).fetchone():
                        continue  # one bet per game
                    ml, book = mkt["best"][side]
                    p_side = mkt["p_home"] if side == "home" else 1 - mkt["p_home"]
                    conn.execute(
                        "INSERT INTO shadow_bets (challenger, game_id, side, team, price_ml, book, market_p,"
                        " odds_captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (name, g["id"], side, g[f"{side}_team"], ml, book, round(p_side, 4), mkt["captured_at"]))
                    n += 1
                else:
                    p = ch["fn"](conn, g, mkt)
                    if p is None:
                        continue
                    p = round(min(max(p, 0.001), 0.999), 4)
                    old = conn.execute("SELECT p_home FROM shadow_predictions WHERE challenger = ? AND game_id = ?"
                                       " ORDER BY created_at DESC, id DESC LIMIT 1", (name, g["id"])).fetchone()
                    if old and abs(old["p_home"] - p) < RELOG_MOVE:
                        continue
                    conn.execute("INSERT INTO shadow_predictions (challenger, game_id, p_home, p_away, odds_id, note)"
                                 " VALUES (?, ?, ?, ?, ?, ?)",
                                 (name, g["id"], p, round(1 - p, 4), mkt["odds_id"],
                                  json.dumps({"market_p_home": round(mkt["p_home"], 4)})))
                    n += 1
            except sqlite3.DatabaseError as e:
                print(f"  {name}: {g['away_team']} at {g['home_team']} refused ({e})")
        conn.commit()
        counts[name] = n
    print(f"{sport.upper()} shadow: " + ", ".join(f"{k} {v} new" for k, v in counts.items()))


# ---------- report ----------

def finished_games(conn, sport):
    return {g["id"]: g for g in conn.execute(
        "SELECT g.*, r.home_score, r.away_score FROM games g JOIN results r ON r.game_id = g.id"
        " WHERE g.sport = ? AND r.status = 'final'", (sport,))}


def report_rule(conn, name, sport):
    done = finished_games(conn, sport)
    bets = conn.execute("SELECT * FROM shadow_bets WHERE challenger = ? ORDER BY created_at", (name,)).fetchall()
    graded = [b for b in bets if b["game_id"] in done]
    w = l = push = 0
    units = expected = var = 0.0
    clv = []
    for b in graded:
        g = done[b["game_id"]]
        close, _ = grade.closing(conn, g)
        if close:
            clv.append((close["p_home"] if b["side"] == "home" else 1 - close["p_home"]) - b["market_p"])
        if g["home_score"] == g["away_score"]:
            push += 1
            continue
        won = (g["home_score"] > g["away_score"]) == (b["side"] == "home")
        w, l = w + won, l + (not won)
        units += (decimal_odds(b["price_ml"]) - 1) if won else -1
        expected += b["market_p"]
        var += b["market_p"] * (1 - b["market_p"])
    n = w + l
    out = {"name": name, "type": "rule", "about": CHALLENGERS[name]["about"], "logged": len(bets),
           "graded": n, "w": w, "l": l, "push": push, "units": units, "roi": units / n if n else None,
           "z": (w - expected) / math.sqrt(var) if var else None,
           "clv": statistics.mean(clv) if clv else None}
    out["eligible"] = bool(n >= 100 and out["clv"] and out["clv"] > 0 and out["z"] and out["z"] >= 2)
    out["bar"] = "100+ bets, CLV > 0, z >= 2"
    return out


def report_model(conn, name, sport):
    done = finished_games(conn, sport)
    rows = []
    for gid, g in done.items():
        if g["home_score"] == g["away_score"]:
            continue
        ch = conn.execute("SELECT * FROM shadow_predictions WHERE challenger = ? AND game_id = ? AND created_at < ?"
                          " ORDER BY created_at DESC, id DESC LIMIT 1", (name, gid, g["start_time_utc"])).fetchone()
        eng = grade.graded_prediction(conn, g, "engine")
        if ch is None or eng is None:
            continue
        y = int(g["home_score"] > g["away_score"])
        close, _ = grade.closing(conn, g)

        def clv_of(pred):
            snap = conn.execute("SELECT captured_at FROM odds WHERE id = ?", (pred["odds_id"],)).fetchone() \
                if pred["odds_id"] else None
            m = grade.market_at(conn, gid, snap["captured_at"]) if snap else None
            if not (m and close) or abs(pred["p_home"] - m["p_home"]) < 1e-9:
                return None
            home = pred["p_home"] > m["p_home"]
            return (close["p_home"] - m["p_home"]) * (1 if home else -1)
        rows.append({"y": y, "ch": ch["p_home"], "eng": eng["p_home"], "clv_ch": clv_of(ch), "clv_eng": clv_of(eng)})
    n = len(rows)
    out = {"name": name, "type": "model", "about": CHALLENGERS[name]["about"], "graded": n}
    if n:
        out["ll_ch"] = sum(grade.log_loss(r["ch"], r["y"]) for r in rows) / n
        out["ll_eng"] = sum(grade.log_loss(r["eng"], r["y"]) for r in rows) / n
        out["brier_ch"] = sum((r["ch"] - r["y"]) ** 2 for r in rows) / n
        out["brier_eng"] = sum((r["eng"] - r["y"]) ** 2 for r in rows) / n
        cc = [r["clv_ch"] for r in rows if r["clv_ch"] is not None]
        ce = [r["clv_eng"] for r in rows if r["clv_eng"] is not None]
        out["clv_ch"] = statistics.mean(cc) if cc else None
        out["clv_eng"] = statistics.mean(ce) if ce else None
    out["eligible"] = bool(n >= 150 and out["ll_ch"] < out["ll_eng"] and out.get("clv_ch") is not None
                           and out.get("clv_eng") is not None and out["clv_ch"] > out["clv_eng"])
    out["bar"] = "150+ games, better log loss AND better CLV than the engine"
    return out


def report_data(conn, sport):
    return [(report_rule if ch["type"] == "rule" else report_model)(conn, name, sport)
            for name, ch in CHALLENGERS.items() if sport in ch["sports"]]


def print_report(conn, sport):
    print(f"===== {sport.upper()} shadow challengers =====")
    for r in report_data(conn, sport):
        status = "ELIGIBLE (Talal decides)" if r["eligible"] else "not yet eligible"
        print(f"\n{r['name']} ({r['type']}): {r['about']}  ->  {status}; bar: {r['bar']}")
        if r["type"] == "rule":
            if not r["graded"]:
                print(f"  {r['logged']} bet(s) logged, none graded yet")
                continue
            z = f"{r['z']:+.2f}" if r["z"] is not None else "-"
            clv = f"{r['clv'] * 100:+.1f} pts" if r["clv"] is not None else "-"
            print(f"  {r['logged']} logged, {r['graded']} graded: {r['w']}-{r['l']}" + (f"-{r['push']}" if r["push"] else "")
                  + f", {r['units']:+.1f} units ({r['roi']:+.1%}), z vs market {z}, avg CLV {clv}")
        else:
            if not r["graded"]:
                print("  no graded games yet")
                continue
            fmt = lambda x: "-" if x is None else f"{x * 100:+.1f} pts"
            print(f"  {r['graded']} graded games | log loss {r['ll_ch']:.4f} vs engine {r['ll_eng']:.4f} | "
                  f"Brier {r['brier_ch']:.4f} vs {r['brier_eng']:.4f} | CLV {fmt(r['clv_ch'])} vs {fmt(r['clv_eng'])}")


def main():
    a = sys.argv[1:]
    conn = db.connect()
    sports = ("nfl", "ncaaf", "nba", "ncaab")
    if len(a) == 2 and a[0] == "log" and a[1] in sports + ("all",):
        for sport in (sports if a[1] == "all" else (a[1],)):
            log(conn, sport)
    elif a and a[0] == "report":
        for sport in (a[1:] or list(sports)):
            print_report(conn, sport)
            print()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

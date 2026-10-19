"""Data for the slate page: one dict per game card, the 'my picks' list, and the
scorecard numbers. Read-only. HTML lives in slate_views.py.
"""

import json
import statistics
import time
import urllib.request
from pathlib import Path

import config
import db
import grade
from cautions import game_warnings, qb_status
from odds_math import decimal_odds, fair_moneyline, no_vig
from predict import ODDS_MAX_AGE, latest_odds, parse_utc
from pull_history import CURRENT_SEASON, current_season
from teams import nba_logo_url, nfl_logo_url

SOURCES = ("engine", "claude", "me")
LOGO_CACHE = Path(__file__).parent / "cache" / "cfbd_teams.json"
LOGO_CACHE_DAYS = 7


def whole(p):
    """0.567 -> 57 (rounds half up)."""
    return int(p * 100 + 0.5)


# ---------- logos ----------

def college_logos():
    """{school: dark-background logo URL}, cached for a week (1 CFBD call to refresh)."""
    fresh = LOGO_CACHE.exists() and time.time() - LOGO_CACHE.stat().st_mtime < LOGO_CACHE_DAYS * 86400
    if not fresh and config.CFBD_API_KEY:
        try:
            req = urllib.request.Request("https://api.collegefootballdata.com/teams",
                                         headers={"Authorization": f"Bearer {config.CFBD_API_KEY}"})
            teams = json.load(urllib.request.urlopen(req, timeout=30))
            out = {}
            for t in teams:
                logos = t.get("logos") or []
                dark = next((u for u in logos if "logos-dark/" in u), None)
                url = dark or (logos[0] if logos else None)
                if url:
                    out[t["school"]] = url.replace("/500/", "/64/")
            LOGO_CACHE.parent.mkdir(exist_ok=True)
            LOGO_CACHE.write_text(json.dumps(out))
            return out
        except Exception:
            pass  # fall back to an older cache, or no logos
    try:
        return json.loads(LOGO_CACHE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def logo_for(sport, team, college):
    if sport == "nfl":
        return nfl_logo_url(team)
    if sport == "nba":
        return nba_logo_url(team)
    return college.get(team) or _cbb_logos().get(team)


_cbb_cache = {}


def _cbb_logos():
    """{school: dark-background logo} for college basketball, from the cached CBBD team list."""
    if not _cbb_cache:
        try:
            from teams import cbbd_teams
            for t in cbbd_teams():
                dark = next((u for u in t.get("logos") or [] if "logos-dark/" in u), None)
                if dark:
                    _cbb_cache[t["school"]] = dark.replace("/500/", "/64/")
        except Exception:
            pass
    return _cbb_cache


# ---------- one game card ----------

def latest_rows(conn, game_id):
    return {s: conn.execute("SELECT * FROM predictions WHERE game_id = ? AND source = ? AND corrects_id IS NULL"
                            " ORDER BY created_at DESC, id DESC LIMIT 1", (game_id, s)).fetchone()
            for s in SOURCES}


def team_form(conn, sport, team, before_utc, n=5):
    """Last n results this season before a time, plus the season record."""
    rows = conn.execute(
        "SELECT * FROM hist_games WHERE sport = ? AND season = ? AND ? IN (home_team, away_team)"
        " AND coalesce(kickoff_utc, game_date_et) < ? ORDER BY game_date_et DESC, kickoff_utc DESC",
        (sport, current_season(sport), team, before_utc)).fetchall()
    games, w, l, t = [], 0, 0, 0
    for r in rows:
        home = r["home_team"] == team
        us, them = (r["home_score"], r["away_score"]) if home else (r["away_score"], r["home_score"])
        res = "W" if us > them else "L" if us < them else "T"
        w, l, t = w + (res == "W"), l + (res == "L"), t + (res == "T")
        if len(games) < n:
            games.append({"result": res, "score": f"{us}-{them}", "where": "vs" if home else "at",
                          "opp": r["away_team"] if home else r["home_team"], "date": r["game_date_et"]})
    record = f"{w}-{l}" + (f"-{t}" if t else "")
    return {"record": record, "games": games}


def market_snapshots(conn, game_id):
    """(first pull, latest pull) as (captured_at, no-vig P(home)), or None."""
    def at(order):
        t = conn.execute(f"SELECT {order}(captured_at) FROM odds WHERE game_id = ?", (game_id,)).fetchone()[0]
        if not t:
            return None
        rows = conn.execute("SELECT home_ml, away_ml FROM odds WHERE game_id = ? AND captured_at = ?",
                            (game_id, t)).fetchall()
        return t, statistics.mean(no_vig(r["home_ml"], r["away_ml"])[0] for r in rows)
    return at("MIN"), at("MAX")


def game_view(conn, g, now, college):
    """Everything one game card needs."""
    rows = latest_rows(conn, g["id"])
    final = rows["claude"] or rows["engine"]
    mkt = latest_odds(conn, g["id"])
    away, home = g["away_team"], g["home_team"]
    stale = mkt is not None and now - parse_utc(mkt["captured_at"]) > ODDS_MAX_AGE
    view = {
        "id": g["id"], "sport": g["sport"], "away": away, "home": home,
        "away_logo": logo_for(g["sport"], away, college), "home_logo": logo_for(g["sport"], home, college),
        "kickoff": db.fmt_et(g["start_time_utc"]), "started": parse_utc(g["start_time_utc"]) <= now,
        "neutral": bool(g["neutral_site"]), "market": None, "picks": [], "prices": [],
        "warnings": game_warnings(conn, g, final, mkt, now), "projected": None, "qbs": None, "rest": None,
        "my_pick": None, "books": [], "movement": None, "odds_time": None,
        "cancelled": conn.execute("SELECT 1 FROM results WHERE game_id = ? AND status = 'cancelled'",
                                  (g["id"],)).fetchone() is not None,
    }
    m_home = mkt["p_home"] if mkt else None
    if mkt:
        fav_home = m_home >= 0.5
        view["market"] = {"team": home if fav_home else away, "pct": whole(m_home if fav_home else 1 - m_home),
                          "books": mkt["books"], "time": db.fmt_et(mkt["captured_at"]), "stale": stale}
        view["odds_time"] = db.fmt_et(mkt["captured_at"])

    # Each source's pick, in words
    for s in SOURCES:
        r = rows[s]
        if r is None:
            view["picks"].append({"source": s, "team": None})
            continue
        fav_home = r["p_home"] >= 0.5
        team, p = (home, r["p_home"]) if fav_home else (away, 1 - r["p_home"])
        edge = None
        disagrees = False
        if mkt:
            mp = m_home if fav_home else 1 - m_home
            edge = round((p - mp) * 100)
            disagrees = (m_home >= 0.5) != fav_home
        view["picks"].append({"source": s, "team": team, "pct": whole(p), "edge": edge,
                              "disagrees": disagrees, "logo": logo_for(g["sport"], team, college)})
        if s == "me":
            view["my_pick"] = f"{team} {whole(p)}%"

    # Prices for each side, against the final (claude or engine) probability
    if final:
        p = final["p_home"]
        for side, team, prob in (("away", away, 1 - p), ("home", home, p)):
            price = {"team": team, "fair": fair_moneyline(prob), "best": None, "book": None,
                     "edge": None, "ev": None, "flag": False}
            if mkt:
                mprob = m_home if side == "home" else 1 - m_home
                price["edge"] = round((prob - mprob) * 100)
                best = mkt["best"].get(side)
                if best:
                    price["best"], price["book"] = best
                    price["ev"] = round(100 * (prob * decimal_odds(best[0]) - 1))
                    price["flag"] = prob - mprob >= config.EDGE_THRESHOLD and not stale
            view["prices"].append(price)
        if final["proj_home_score"] is not None:
            view["projected"] = (round(final["proj_away_score"]), round(final["proj_home_score"]))
        inp = json.loads(final["note"] or "{}").get("inputs", {})
        qbs = qb_status(conn, g, final)
        if qbs:
            label = {"confirmed": "confirmed", "expected": "per news", "verified": "checked",
                     "assumed": "assumed", "listed": "nflverse listing, not checked"}
            view["qbs"] = {side: ({"name": qbs[side]["name"],
                                   "tag": label[qbs[side]["kind"]] + (f", {qbs[side]['time']}" if qbs[side]["time"] else "")}
                                  if side in qbs else {"name": "?", "tag": "unknown"})
                           for side in ("away", "home")}
        if inp.get("away_rest_days") is not None:
            view["rest"] = (inp["away_rest_days"], inp.get("home_rest_days"))

    # Back of the card: every book, line movement, form
    if mkt:
        book_rows = conn.execute("SELECT * FROM odds WHERE game_id = ? AND captured_at = ? ORDER BY bookmaker",
                                 (g["id"], mkt["captured_at"])).fetchall()
        best_away = max((b["away_ml"] for b in book_rows), key=decimal_odds)
        best_home = max((b["home_ml"] for b in book_rows), key=decimal_odds)
        for b in book_rows:
            view["books"].append({"book": b["bookmaker"], "away": b["away_ml"], "home": b["home_ml"],
                                  "mine": b["bookmaker"] in config.MY_BOOKS,
                                  "best_away": b["away_ml"] == best_away, "best_home": b["home_ml"] == best_home})
    first, last = market_snapshots(conn, g["id"])
    if first and last and first[0] != last[0]:
        moved = (last[1] - first[1]) * 100
        view["movement"] = {"since": db.fmt_et(first[0]), "away_then": whole(1 - first[1]),
                            "away_now": whole(1 - last[1]), "home_then": whole(first[1]),
                            "home_now": whole(last[1]), "pts": round(abs(moved)),
                            "toward": home if moved > 0 else away}
    view["news"] = [{"points": round(a["d_home"] * 100, 1), "reason": a["reason"], "source": a["source_url"],
                     "time": db.fmt_et(a["created_at"])}
                    for a in conn.execute("SELECT * FROM adjustments WHERE game_id = ? ORDER BY created_at", (g["id"],))]
    view["form"] = {side: team_form(conn, g["sport"], g[f"{side}_team"], g["start_time_utc"])
                    for side in ("away", "home")}
    return view


def slate(conn, sport, now, days, college):
    from datetime import timedelta
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " ORDER BY start_time_utc, id",
        (sport, db.to_utc(now - timedelta(hours=4)), db.to_utc(now + timedelta(days=days)))).fetchall()
    return [(db.utc_to_eastern(g["start_time_utc"]).strftime("%A, %B %-d"), game_view(conn, g, now, college))
            for g in games]


# ---------- live ----------

def live(conn, now, college, sport=None):
    """Games from 8 hours ago through the end of today (Eastern), with live scores and picks.
    Returns (groups {"in": [...], "post": [...], "pre": [...]}, error message or None)."""
    import live_scores
    from datetime import timedelta
    today_end = now.astimezone(db.EASTERN).replace(hour=23, minute=59, second=59)
    games = conn.execute(
        "SELECT g.*, r.status AS result_status FROM games g LEFT JOIN results r ON r.game_id = g.id"
        " WHERE g.start_time_utc >= ? AND g.start_time_utc <= ? AND (? IS NULL OR g.sport = ?)"
        " ORDER BY g.start_time_utc, g.id",
        (db.to_utc(now - timedelta(hours=8)), db.to_utc(today_end), sport, sport)).fetchall()
    boards, error = {}, None
    for sport in {g["sport"] for g in games}:
        try:
            boards[sport] = live_scores.scoreboard(sport, now)
        except live_scores.LiveUnavailable as e:
            error = str(e)
    groups = {"in": [], "post": [], "pre": []}
    for g in games:
        if g["result_status"] == "cancelled":
            continue
        info = boards.get(g["sport"], {}).get(g["espn_id"] or "")
        started = parse_utc(g["start_time_utc"]) <= now
        state = info["state"] if info else ("in" if started else "pre")
        v = {"id": g["id"], "sport": g["sport"], "away": g["away_team"], "home": g["home_team"],
             "away_logo": logo_for(g["sport"], g["away_team"], college),
             "home_logo": logo_for(g["sport"], g["home_team"], college),
             "kickoff": db.fmt_et(g["start_time_utc"]), "live": info, "state": state, "picks": []}
        rows = {s: (grade.graded_prediction(conn, g, s) if started else latest_rows(conn, g["id"])[s]) for s in SOURCES}
        mkt = latest_odds(conn, g["id"])
        entries = [(s, rows[s]["p_home"]) for s in SOURCES if rows[s]] + ([("market", mkt["p_home"])] if mkt else [])
        for src, p in entries:
            side = "home" if p >= 0.5 else "away"
            status = None
            if info and info["state"] != "pre":
                mine, theirs = (info["home_score"], info["away_score"]) if side == "home" \
                    else (info["away_score"], info["home_score"])
                if info["state"] == "post":
                    status = "won" if mine > theirs else "lost" if mine < theirs else "tied"
                else:
                    status = "ahead" if mine > theirs else "behind" if mine < theirs else "tied"
            v["picks"].append({"source": src, "team": g[f"{side}_team"], "pct": whole(p if side == "home" else 1 - p),
                               "logo": logo_for(g["sport"], g[f"{side}_team"], college), "status": status})
        groups[state if state in groups else "pre"].append(v)
    return groups, error


# ---------- my picks ----------

def my_picks(conn, now, college):
    """(upcoming, finished, summary) for every game with a 'me' prediction."""
    games = conn.execute(
        "SELECT g.*, r.status AS result_status, r.home_score, r.away_score FROM games g"
        " LEFT JOIN results r ON r.game_id = g.id"
        " WHERE EXISTS (SELECT 1 FROM predictions p WHERE p.game_id = g.id AND p.source = 'me')"
        " ORDER BY g.start_time_utc DESC, g.id").fetchall()
    upcoming, finished = [], []
    sums = {s: [] for s in ("me", "engine", "market")}
    right = 0
    for g in games:
        started = parse_utc(g["start_time_utc"]) <= now
        mine = grade.graded_prediction(conn, g, "me") if started else latest_rows(conn, g["id"])["me"]
        if mine is None:
            continue
        eng = grade.graded_prediction(conn, g, "engine") if started else latest_rows(conn, g["id"])["engine"]
        base = {"id": g["id"], "sport": g["sport"], "away": g["away_team"], "home": g["home_team"],
                "kickoff": db.fmt_et(g["start_time_utc"]), "start": g["start_time_utc"], "logos": (logo_for(g["sport"], g["away_team"], college),
                                                                    logo_for(g["sport"], g["home_team"], college))}

        def side(p):
            return (g["home_team"], whole(p)) if p >= 0.5 else (g["away_team"], whole(1 - p))
        base["me"] = side(mine["p_home"])
        base["engine"] = side(eng["p_home"]) if eng else None
        if mine["odds_id"]:
            snap = conn.execute("SELECT captured_at FROM odds WHERE id = ?", (mine["odds_id"],)).fetchone()
            m = grade.market_at(conn, g["id"], snap["captured_at"]) if snap else None
        else:
            m = None
        base["market"] = side(m["p_home"]) if m else None

        if not started:
            upcoming.append(base)
        elif g["result_status"] == "final" and g["home_score"] != g["away_score"]:
            y = int(g["home_score"] > g["away_score"])
            winner = g["home_team"] if y else g["away_team"]
            base["final"] = f"{g['away_team']} {g['away_score']} - {g['home_team']} {g['home_score']}"
            base["correct"] = base["me"][0] == winner
            right += base["correct"]
            base["brier"] = {"me": (mine["p_home"] - y) ** 2}
            sums["me"].append(base["brier"]["me"])
            if eng and m:
                base["brier"]["engine"] = (eng["p_home"] - y) ** 2
                base["brier"]["market"] = (m["p_home"] - y) ** 2
                sums["engine"].append(base["brier"]["engine"])
                sums["market"].append(base["brier"]["market"])
            finished.append(base)
        else:
            base["final"] = "awaiting result" if g["result_status"] is None else g["result_status"]
            base["correct"] = None
            finished.append(base)
    graded = [f for f in finished if f.get("correct") is not None]
    summary = {"graded": len(graded), "right": right,
               "avg": {k: (sum(v) / len(v) if v else None) for k, v in sums.items()},
               "compared": len(sums["engine"])}
    upcoming.sort(key=lambda x: x["start"])
    return upcoming, finished, summary


# ---------- scorecard ----------

def scorecard(conn, sport):
    games, stats, approx = grade.grade(conn, sport, current_season(sport))
    tiles = {}
    for s in ("market",) + SOURCES:
        st = stats[s]
        n = len(st["rows"])
        tile = {"n": n}
        if n:
            tile["brier"] = sum((p - y) ** 2 for p, y in st["rows"]) / n
            tile["log_loss"] = sum(grade.log_loss(p, y) for p, y in st["rows"]) / n
        bets = st["bets"]
        if bets and s != "market":
            wins = sum(1 for b in bets if b > 0)
            tile["bets"] = {"w": wins, "l": len(bets) - wins, "units": sum(bets), "roi": sum(bets) / len(bets)}
        if st["clv"] and s != "market":
            tile["clv"] = {"avg": statistics.mean(st["clv"]), "pos": sum(c > 0 for c in st["clv"]) / len(st["clv"]),
                           "n": len(st["clv"])}
        if n and s != "market":
            bins = []
            for lo in range(0, 100, 10):
                b = [(p, y) for p, y in st["rows"] if lo / 100 <= p < (lo + 10) / 100 or (lo == 90 and p == 1)]
                if b:
                    bins.append({"lo": lo, "n": len(b), "pred": sum(p for p, _ in b) / len(b),
                                 "actual": sum(y for _, y in b) / len(b)})
            tile["bins"] = bins
        tiles[s] = tile
    h2h = []
    for a, b in (("me", "engine"), ("claude", "engine"), ("me", "claude")):
        common = [x for x in stats["per_game"] if a in x and b in x and "market" in x]
        if common:
            row = {"pair": (a, b), "n": len(common)}
            for src in (a, b, "market"):
                row[src] = sum((x[src] - x["y"]) ** 2 for x in common) / len(common)
            h2h.append(row)
    import shadow
    return {"finished": len(games), "approx": approx, "tiles": tiles, "h2h": h2h,
            "graded": len(stats["engine"]["rows"]), "shadow": shadow.report_data(conn, sport)}

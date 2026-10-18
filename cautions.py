"""Per-game warnings: concrete reasons not to trust an edge, which the
probabilities alone don't show. Used by predict.py and show_picks.py.

Edge size is NOT treated as a confidence signal: in the out-of-sample
backtest (2023-25 NFL, 2021-25 college), teams the model liked by 10+ points
more than the market won about as often as the market said, or less, so a
very large edge is a warning, not a recommendation.
"""

import json
from datetime import datetime, timezone

import db

from pull_history import CURRENT_SEASON

STALE_ODDS_HOURS = 3     # flagged only within 24 hours of kickoff
FEW_BOOKS = 4
EARLY_GAMES = 3          # fewer games than this this season = ratings still settling
LARGE_EDGE = 0.10


def games_played(conn, sport, team):
    return conn.execute(
        "SELECT COUNT(*) FROM hist_games WHERE sport = ? AND season = ? AND ? IN (home_team, away_team)",
        (sport, CURRENT_SEASON, team)).fetchone()[0]


def qb_status(conn, g, pred):
    """{side: {"name", "kind", "time"}} for NFL starters. kind is one of:
    confirmed / expected (a news fact), verified (news checked, matches the model),
    assumed (last starter), listed (nflverse listing, not checked). Facts win over checks."""
    if pred is None:
        return {}
    inputs = json.loads(pred["note"] or "{}").get("inputs", {})
    out = {}
    for side in ("away", "home"):
        team = g[f"{side}_team"]
        fact = conn.execute("SELECT * FROM lineup_facts WHERE game_id = ? AND team = ?"
                            " ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"], team)).fetchone()
        check = conn.execute("SELECT * FROM qb_checks WHERE game_id = ? AND team = ?"
                             " ORDER BY created_at DESC, id DESC LIMIT 1", (g["id"], team)).fetchone()
        name = inputs.get(f"{side}_starter_name")
        status = inputs.get(f"{side}_starter_status") or ""
        if fact:
            out[side] = {"name": fact["player_name"], "kind": fact["status"], "time": db.fmt_et(fact["created_at"])}
        elif check:
            out[side] = {"name": check["player_name"], "kind": "verified", "time": db.fmt_et(check["created_at"])}
        elif name:
            out[side] = {"name": name, "kind": "assumed" if "assumed" in status else "listed", "time": None}
    return out


def game_warnings(conn, g, pred, mkt, now=None):
    """List of short warning strings for one game.

    g: games row; pred: the prediction row being shown (claude if any, else engine);
    mkt: dict with p_home, books, captured_at (UTC text), or None."""
    now = now or datetime.now(timezone.utc)
    out = []

    # Starting QBs (NFL): one short note unless something specific stands out
    qbs = qb_status(conn, g, pred)
    if any(q["kind"] == "listed" for q in qbs.values()):
        out.append("QBs not yet checked against the news")
    for side, q in qbs.items():
        if q["kind"] == "assumed":
            out.append(f"{g[f'{side}_team']} QB {q['name']} is only assumed (last starter; nflverse lists none)")
        elif q["kind"] == "expected":
            out.append(f"{g[f'{side}_team']} QB {q['name']} expected per news, not officially confirmed")

    # Market problems
    if mkt is None:
        out.append("no odds yet")
    else:
        captured = datetime.strptime(mkt["captured_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        hours = (now - captured).total_seconds() / 3600
        kickoff = datetime.strptime(g["start_time_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if hours > STALE_ODDS_HOURS and (kickoff - now).total_seconds() < 24 * 3600:
            out.append(f"odds {hours:.0f} hours old and kickoff is within a day")
        if mkt["books"] < FEW_BOOKS:
            out.append(f"only {mkt['books']} book(s) priced this")
        if pred is not None:
            edge = abs(pred["p_home"] - mkt["p_home"])
            if edge >= LARGE_EDGE:
                out.append(f"edge of {edge * 100:.0f} pts: in backtests, edges this big were usually model error")
            if g["sport"] == "ncaaf" and edge >= 0.04 and not conn.execute(
                    "SELECT 1 FROM adjustments WHERE game_id = ?", (g["id"],)).fetchone():
                out.append("news not checked for this game (the model can't see college injuries)")

    # Early season: ratings still settling
    for side in ("away", "home"):
        n = games_played(conn, g["sport"], g[f"{side}_team"])
        if n < EARLY_GAMES:
            out.append(f"early season: {g[f'{side}_team']} has played {n} game(s)")
    return out

"""Try to break the logbook rules and show the database refusing.

Uses a throwaway database in a temp folder, deleted at the end. The games and
teams below are test fixtures, not real data, and never touch bet_engine.db.
"""

import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db

results = []


def check(label, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"\n      -> {detail}" if detail else ""))


def expect_ok(label, fn):
    try:
        fn()
        check(label, True)
    except Exception as e:
        check(label, False, f"unexpected error: {e}")


def expect_blocked(label, fn):
    try:
        fn()
        check(label, False, "it was allowed, but should have been blocked")
    except sqlite3.DatabaseError as e:
        check(label, True, f"database said: {e}")


def main():
    tmp = tempfile.TemporaryDirectory()
    conn = db.init_db(Path(tmp.name) / "test.db")
    now = datetime.now(timezone.utc)

    # A football game far in the future, and one that kicks off in 3 seconds.
    future = db.add_game(conn, "nfl", "NFL", "test", "Test Home", "Test Away",
                         now + timedelta(days=1), source="test")
    soon = db.add_game(conn, "nfl", "NFL", "test", "Test Home B", "Test Away B",
                       now + timedelta(seconds=3), source="test")
    soccer = db.add_game(conn, "soccer_club", "TEST", "test", "Test FC", "Test United",
                         now + timedelta(days=1), source="test")

    print("\n-- Valid rows are saved --")
    odds_id = db.add_odds(conn, future, "testbook", home_ml=-150, away_ml=130, source="test")
    expect_ok("save an engine prediction with odds and projected score",
              lambda: db.add_prediction(conn, future, "engine", 0.58, 0.42,
                                        proj_home_score=24, proj_away_score=20,
                                        odds_id=odds_id, model_version="test"))
    engine_id = conn.execute("SELECT MAX(id) FROM predictions").fetchone()[0]
    expect_ok("save my own pick",
              lambda: db.add_prediction(conn, future, "me", 0.60, 0.40))
    expect_ok("save a soccer prediction with a draw",
              lambda: db.add_prediction(conn, soccer, "engine", 0.45, 0.27, p_draw=0.28))
    expect_ok("save a 2-point adjustment with reason and link",
              lambda: db.add_adjustment(conn, future, engine_id, -0.02, 0.02,
                                        "test: starting QB ruled out",
                                        "https://example.com/test-report"))

    print("\n-- Bad data is rejected --")
    expect_blocked("probabilities that add to 110%",
                   lambda: db.add_prediction(conn, future, "engine", 0.60, 0.50))
    expect_blocked("a draw probability in football",
                   lambda: db.add_prediction(conn, future, "engine", 0.5, 0.3, p_draw=0.2))
    expect_blocked("a soccer prediction missing the draw",
                   lambda: db.add_prediction(conn, soccer, "engine", 0.6, 0.4))
    expect_blocked("an unknown source",
                   lambda: db.add_prediction(conn, future, "uncle_bob", 0.5, 0.5))
    expect_blocked("a backdated prediction (timestamp faked to yesterday)",
                   lambda: conn.execute(
                       "INSERT INTO predictions (game_id, source, created_at, p_home, p_away)"
                       " VALUES (?, 'engine', datetime('now', '-1 day'), 0.5, 0.5)", (future,)))

    print("\n-- Claude's adjustments are bounded and sourced --")
    expect_blocked("adjustment with no source link",
                   lambda: db.add_adjustment(conn, future, engine_id, -0.01, 0.01,
                                             "test reason", ""))
    expect_blocked("adjustment with no reason",
                   lambda: db.add_adjustment(conn, future, engine_id, -0.01, 0.01,
                                             "  ", "https://example.com/x"))
    expect_blocked("a single 5-point adjustment (cap is 3)",
                   lambda: db.add_adjustment(conn, future, engine_id, -0.05, 0.05,
                                             "test reason", "https://example.com/x"))
    expect_blocked("a second 2-point adjustment (total would be 4, cap is 3)",
                   lambda: db.add_adjustment(conn, future, engine_id, -0.02, 0.02,
                                             "test reason", "https://example.com/x"))
    expect_ok("a second 1-point adjustment (total 3, exactly at cap)",
              lambda: db.add_adjustment(conn, future, engine_id, -0.01, 0.01,
                                        "test: second injury", "https://example.com/y"))

    print("\n-- Confirmed starters (lineup facts) --")
    fact = lambda **kw: db.add_lineup_fact(conn, **dict(dict(
        game_id=future, team="Test Home", role="QB", player_name="Test Passer",
        status="confirmed", source_url="https://example.com/test-news",
        reason="test: named starter"), **kw))
    expect_ok("save a confirmed starter with a source", lambda: fact())
    expect_blocked("starter with no source link", lambda: fact(source_url=""))
    expect_blocked("starter with no reason", lambda: fact(reason=" "))
    expect_blocked("starter for a team not in the game", lambda: fact(team="Some Other Team"))
    expect_blocked("edit a starter fact",
                   lambda: conn.execute("UPDATE lineup_facts SET player_name = 'X'"))
    expect_blocked("delete a starter fact", lambda: conn.execute("DELETE FROM lineup_facts"))

    print("\n-- Verified QB checks --")
    qbcheck = lambda **kw: db.add_qb_check(conn, **dict(dict(
        game_id=future, team="Test Away", player_name="Test Away QB",
        source_url="https://example.com/test-inactives", reason="test: active, no report otherwise"), **kw))
    expect_ok("save a verified QB check with a source", lambda: qbcheck())
    expect_blocked("check with no source link", lambda: qbcheck(source_url="nope"))
    expect_blocked("check with no reason", lambda: qbcheck(reason=""))
    expect_blocked("check for a team not in the game", lambda: qbcheck(team="Some Other Team"))
    expect_blocked("edit a check", lambda: conn.execute("UPDATE qb_checks SET player_name = 'X'"))
    expect_blocked("delete a check", lambda: conn.execute("DELETE FROM qb_checks"))

    print("\n-- Shadow challengers --")
    shadow_bet = lambda **kw: conn.execute(
        "INSERT INTO shadow_bets (challenger, game_id, side, team, price_ml, book, market_p, odds_captured_at)"
        " VALUES (:challenger, :game_id, 'home', 'Test Home', -150, 'FanDuel', 0.58, datetime('now'))",
        dict(dict(challenger="test_rule_v1", game_id=future), **kw))
    expect_ok("log a shadow bet before kickoff", lambda: shadow_bet())
    expect_blocked("a second bet by the same challenger on the same game", lambda: shadow_bet())
    expect_blocked("edit a shadow bet", lambda: conn.execute("UPDATE shadow_bets SET price_ml = 200"))
    expect_blocked("delete a shadow bet", lambda: conn.execute("DELETE FROM shadow_bets"))
    shadow_pred = lambda p_home, p_away: conn.execute(
        "INSERT INTO shadow_predictions (challenger, game_id, p_home, p_away) VALUES ('test_model_v1', ?, ?, ?)",
        (future, p_home, p_away))
    expect_ok("log a shadow prediction before kickoff", lambda: shadow_pred(0.6, 0.4))
    expect_blocked("shadow probabilities that don't add to 100%", lambda: shadow_pred(0.6, 0.5))
    expect_blocked("edit a shadow prediction", lambda: conn.execute("UPDATE shadow_predictions SET p_home = 0.9"))

    print("\n-- The past can't be edited --")
    early_id = db.add_prediction(conn, soon, "engine", 0.55, 0.45)
    # A second game kicking off at the same moment, to be postponed after its start
    ppd = db.add_game(conn, "nfl", "NFL", "test", "Test Home P", "Test Away P",
                      now + timedelta(seconds=3), source="test")
    db.add_prediction(conn, ppd, "engine", 0.5, 0.5)
    cxl = db.add_game(conn, "nfl", "NFL", "test", "Test Home X", "Test Away X",
                      now + timedelta(days=2), source="test")
    expect_blocked("save a result before kickoff",
                   lambda: db.add_result(conn, soon, "final", "test", 21, 17))
    print("      (waiting 4 seconds for the test game to kick off...)")
    time.sleep(4)
    expect_blocked("new prediction after kickoff",
                   lambda: db.add_prediction(conn, soon, "me", 0.7, 0.3))
    expect_blocked("starter fact after kickoff",
                   lambda: db.add_lineup_fact(conn, soon, "Test Home B", "QB", "Late Passer",
                                              "confirmed", "https://example.com/x", "test"))
    expect_blocked("QB check after kickoff",
                   lambda: db.add_qb_check(conn, soon, "Test Home B", "Late QB",
                                           "https://example.com/x", "test"))
    expect_blocked("shadow bet after kickoff",
                   lambda: shadow_bet(game_id=soon, challenger="late_v1"))
    expect_blocked("new odds after kickoff",
                   lambda: db.add_odds(conn, soon, "testbook", -110, -110, "test"))
    expect_blocked("edit a prediction's probability",
                   lambda: conn.execute("UPDATE predictions SET p_home = 0.9, p_away = 0.1"
                                        " WHERE id = ?", (early_id,)))
    expect_blocked("delete a prediction",
                   lambda: conn.execute("DELETE FROM predictions WHERE id = ?", (early_id,)))
    expect_blocked("move kickoff EARLIER after the game started",
                   lambda: conn.execute("UPDATE games SET start_time_utc = '2000-01-01 00:00:00'"
                                        " WHERE id = ?", (soon,)))

    print("\n-- Postponed and cancelled games --")
    expect_ok("postpone a game LATER after its original kickoff (no result yet)",
              lambda: db.move_kickoff(conn, ppd, now + timedelta(days=1), "test", "test: weather postponement"))
    check("the move is recorded in schedule_changes",
          conn.execute("SELECT COUNT(*) FROM schedule_changes WHERE game_id = ? AND kind = 'moved'",
                       (ppd,)).fetchone()[0] == 1)
    expect_ok("predictions allowed again before the new kickoff",
              lambda: db.add_prediction(conn, ppd, "engine", 0.52, 0.48))
    expect_blocked("move a kickoff earlier than an existing prediction",
                   lambda: db.move_kickoff(conn, ppd, now - timedelta(days=1), "test", "test"))
    expect_ok("cancel a game before kickoff",
              lambda: db.cancel_game(conn, cxl, "https://example.com/test", "test: cancelled"))
    expect_blocked("a final result for a game not yet started",
                   lambda: db.add_result(conn, ppd, "final", "test", 1, 0))
    expect_blocked("a second result for a cancelled game",
                   lambda: db.add_result(conn, cxl, "final", "test", 1, 0))
    expect_blocked("move a cancelled game's kickoff",
                   lambda: db.move_kickoff(conn, cxl, now + timedelta(days=9), "test", "test"))
    expect_blocked("edit a schedule change",
                   lambda: conn.execute("UPDATE schedule_changes SET reason = 'x'"))
    expect_blocked("delete a schedule change", lambda: conn.execute("DELETE FROM schedule_changes"))
    expect_blocked("correction with no note",
                   lambda: db.add_prediction(conn, soon, "engine", 0.5, 0.5, corrects_id=early_id))
    expect_ok("correction with a note (kept for the record, never graded)",
              lambda: db.add_prediction(conn, soon, "engine", 0.53, 0.47, corrects_id=early_id,
                                        note="test: original used stale injury data"))
    locked = db.lock_started_games(conn)
    check("lock predictions for started games", locked == 2, f"{locked} rows locked")
    expect_blocked("unlock a locked prediction",
                   lambda: conn.execute("UPDATE predictions SET locked = 0 WHERE id = ?",
                                        (early_id,)))
    expect_ok("save the final result after kickoff",
              lambda: db.add_result(conn, soon, "final", "test", 21, 17))
    expect_blocked("move kickoff after a final result",
                   lambda: db.move_kickoff(conn, soon, now + timedelta(days=5), "test", "test"))
    expect_blocked("change a final result",
                   lambda: conn.execute("UPDATE results SET home_score = 28 WHERE game_id = ?",
                                        (soon,)))

    print("\n-- Eastern time display --")
    check("Thursday night game shows in Eastern",
          db.fmt_et("2026-10-16 00:15:00") == "Thu Oct 15, 8:15 PM ET",
          db.fmt_et("2026-10-16 00:15:00"))
    hours = [now.replace(year=2026, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
             + timedelta(hours=h) for h in range(5 * 365 * 24)]
    conn.executemany(
        "INSERT INTO games (sport, league, season, home_team, away_team, start_time_utc, source)"
        " VALUES ('nfl', 'NFL', 'tz-test', 'A', 'B', ?, 'tz-test')",
        [(db.to_utc(h),) for h in hours])
    mismatches = [
        (r["kickoff_et"], r["start_time_utc"]) for r in conn.execute(
            "SELECT e.kickoff_et, g.start_time_utc FROM games_et e JOIN games g ON g.id = e.id"
            " WHERE g.season = 'tz-test'")
        if r["kickoff_et"] != db.utc_to_eastern(r["start_time_utc"]).strftime("%Y-%m-%d %H:%M") + " ET"]
    check(f"database Eastern view matches official time-zone rules for all {len(hours):,} "
          "hours of 2026-2030", not mismatches, f"{len(mismatches)} mismatches" if mismatches else "")

    conn.close()
    tmp.cleanup()
    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

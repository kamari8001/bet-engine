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

    print("\n-- The past can't be edited --")
    early_id = db.add_prediction(conn, soon, "engine", 0.55, 0.45)
    expect_blocked("save a result before kickoff",
                   lambda: db.add_result(conn, soon, "final", "test", 21, 17))
    print("      (waiting 4 seconds for the test game to kick off...)")
    time.sleep(4)
    expect_blocked("new prediction after kickoff",
                   lambda: db.add_prediction(conn, soon, "me", 0.7, 0.3))
    expect_blocked("new odds after kickoff",
                   lambda: db.add_odds(conn, soon, "testbook", -110, -110, "test"))
    expect_blocked("edit a prediction's probability",
                   lambda: conn.execute("UPDATE predictions SET p_home = 0.9, p_away = 0.1"
                                        " WHERE id = ?", (early_id,)))
    expect_blocked("delete a prediction",
                   lambda: conn.execute("DELETE FROM predictions WHERE id = ?", (early_id,)))
    expect_blocked("move kickoff time after the game started",
                   lambda: conn.execute("UPDATE games SET start_time_utc = '2099-01-01 00:00:00'"
                                        " WHERE id = ?", (soon,)))
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

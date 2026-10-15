"""Record what Claude finds in the news: confirmed starters and capped adjustments.

Usage:
  python3 news.py games nfl|ncaaf
      list upcoming games (next 7 days) with ids and current expected starters
  python3 news.py qb <game id> <team> "<player>" confirmed|expected <source url> "<reason>"
      record a starting QB (NFL). The formula turns it into a probability.
  python3 news.py adjust <game id> <home shift in points> <source url> "<reason>"
      a judgment adjustment, e.g. 1.5 moves the home team up 1.5 percentage
      points (away down 1.5). Capped at config.MAX_ADJUSTMENT per game in total.

Then run `python3 predict.py <sport>` to log the claude prediction.
Every entry needs a source link and a reason, and must be made before kickoff.
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import config
import db


def list_games(conn, sport):
    now = datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " ORDER BY start_time_utc, id",
        (sport, db.to_utc(now), db.to_utc(now + timedelta(days=7)))).fetchall()
    for g in rows:
        facts = conn.execute("SELECT team, player_name, status FROM lineup_facts WHERE game_id = ?"
                             " ORDER BY created_at", (g["id"],)).fetchall()
        known = "; ".join(f"{f['team']} QB {f['player_name']} ({f['status']})" for f in facts)
        print(f"  [{g['id']}] {db.fmt_et(g['start_time_utc']):<24} {g['away_team']} at {g['home_team']}"
              + (f"   recorded: {known}" if known else ""))


def find_player_id(conn, name):
    """nflverse id of a QB who has started before, matched by name; None if never started."""
    r = conn.execute(
        "SELECT id FROM (SELECT home_starter_id AS id, game_date_et FROM hist_games"
        "  WHERE sport = 'nfl' AND home_starter_name = ?"
        " UNION ALL SELECT away_starter_id, game_date_et FROM hist_games"
        "  WHERE sport = 'nfl' AND away_starter_name = ?) ORDER BY game_date_et DESC LIMIT 1",
        (name, name)).fetchone()
    return r[0] if r else None


def record_qb(conn, game_id, team, player, status, url, reason):
    g = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if g is None or g["sport"] != "nfl":
        sys.exit("No NFL game with that id. Use `python3 news.py games nfl`.")
    pid = find_player_id(conn, player)
    db.add_lineup_fact(conn, game_id, team, "QB", player, status, url, reason, player_id=pid)
    print(f"Recorded: {team} QB {player} ({status}) for {g['away_team']} at {g['home_team']}.")
    print(f"  nflverse id {pid}" if pid else
          "  No previous NFL starts found: the model treats him as a first-time starter.")


def record_adjustment(conn, game_id, shift_points, url, reason):
    base = conn.execute("SELECT id FROM predictions WHERE game_id = ? AND source = 'engine'"
                        " ORDER BY created_at DESC, id DESC LIMIT 1", (game_id,)).fetchone()
    if base is None:
        sys.exit("No engine prediction for that game yet. Run predict.py first.")
    d = shift_points / 100
    db.add_adjustment(conn, game_id, base["id"], d_home=d, d_away=-d, reason=reason, source_url=url)
    used = conn.execute("SELECT SUM(d_home) FROM adjustments WHERE game_id = ?", (game_id,)).fetchone()[0]
    print(f"Recorded: home {shift_points:+.1f} points. Total for this game {used * 100:+.1f} "
          f"(cap {config.MAX_ADJUSTMENT * 100:.0f}).")


def main():
    a = sys.argv[1:]
    conn = db.connect()
    try:
        if len(a) == 2 and a[0] == "games":
            list_games(conn, a[1])
        elif len(a) == 7 and a[0] == "qb" and a[4] in ("confirmed", "expected"):
            record_qb(conn, int(a[1]), a[2], a[3], a[4], a[5], a[6])
        elif len(a) == 5 and a[0] == "adjust":
            record_adjustment(conn, int(a[1]), float(a[2]), a[3], a[4])
        else:
            sys.exit(__doc__)
    except sqlite3.DatabaseError as e:
        sys.exit(f"Refused by the database: {e}")


if __name__ == "__main__":
    main()

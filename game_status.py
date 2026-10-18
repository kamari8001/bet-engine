"""Record a cancelled or postponed game when the data feeds don't.

Usage:
  python3 game_status.py cancel <game id> "<source url>" "<reason>"
      The game gets a 'cancelled' result: it's never graded, and it stops
      blocking predict.py. Allowed before or after the scheduled kickoff.
  python3 game_status.py postpone <game id> "<new kickoff, Eastern: YYYY-MM-DD HH:MM>" "<source url>" "<reason>"
      Moves the kickoff later. Never earlier than a logged prediction, and
      never after a result exists (the database refuses).
  python3 game_status.py list
      Every schedule change recorded so far.

Find game ids with `python3 news.py games nfl` (or ncaaf).
"""

import sqlite3
import sys
from datetime import datetime

import db


def main():
    a = sys.argv[1:]
    conn = db.connect()
    try:
        if a == ["list"]:
            rows = conn.execute(
                "SELECT c.*, g.away_team, g.home_team FROM schedule_changes c JOIN games g ON g.id = c.game_id"
                " ORDER BY c.id").fetchall()
            if not rows:
                print("No schedule changes recorded.")
            for r in rows:
                what = (f"moved {db.fmt_et(r['old_start_utc'])} -> {db.fmt_et(r['new_start_utc'])}"
                        if r["kind"] == "moved" else f"cancelled (was {db.fmt_et(r['old_start_utc'])})")
                print(f"[{r['game_id']}] {r['away_team']} at {r['home_team']}: {what} | {r['reason']} | {r['source']}")
            return
        if len(a) == 4 and a[0] == "cancel":
            g = conn.execute("SELECT * FROM games WHERE id = ?", (int(a[1]),)).fetchone()
            if g is None:
                sys.exit("No game with that id.")
            db.cancel_game(conn, g["id"], a[2], a[3])
            print(f"Cancelled: {g['away_team']} at {g['home_team']} ({db.fmt_et(g['start_time_utc'])}). "
                  "It won't be graded.")
            return
        if len(a) == 5 and a[0] == "postpone":
            g = conn.execute("SELECT * FROM games WHERE id = ?", (int(a[1]),)).fetchone()
            if g is None:
                sys.exit("No game with that id.")
            new = datetime.strptime(a[2], "%Y-%m-%d %H:%M").replace(tzinfo=db.EASTERN)
            old, new_utc = db.move_kickoff(conn, g["id"], new, a[3], a[4])
            print(f"Moved {g['away_team']} at {g['home_team']}: {db.fmt_et(old)} -> {db.fmt_et(new_utc)}.")
            return
        sys.exit(__doc__)
    except ValueError:
        sys.exit("Couldn't read the new kickoff. Use Eastern time like 2026-10-19 20:15.")
    except sqlite3.DatabaseError as e:
        sys.exit(f"Refused by the database: {e}")


if __name__ == "__main__":
    main()

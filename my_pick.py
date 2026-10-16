"""Log your own pick (source 'me') before kickoff.

Usage:
  python3 my_pick.py list nfl|ncaaf          upcoming games (next 7 days) with ids
  python3 my_pick.py <game id> <team> <win %>
      e.g. python3 my_pick.py 1234 DEN 60  means you think Denver wins 60% of the time.

A pick can't be edited. To change your mind before kickoff, log a new one;
the latest one before kickoff is graded.
"""

import sqlite3
import sys

import db
from news import list_games


class PickError(Exception):
    """A pick that can't be logged; the message says why."""


def log_pick(conn, game_id, team, pct):
    """Log a 'me' prediction. Returns a confirmation message; raises PickError if refused.
    Used by this command and by the slate page (slate.py)."""
    g = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if g is None:
        raise PickError("No game with that id. Use `python3 my_pick.py list nfl`.")
    if team not in (g["home_team"], g["away_team"]):
        raise PickError(f"{team} isn't in this game ({g['away_team']} at {g['home_team']}).")
    if not 0 < pct < 100:
        raise PickError("Win % must be between 0 and 100.")
    p_home = round(pct / 100 if team == g["home_team"] else 1 - pct / 100, 4)
    odds = conn.execute("SELECT id FROM odds WHERE game_id = ? ORDER BY captured_at DESC, id LIMIT 1",
                        (game_id,)).fetchone()
    try:
        db.add_prediction(conn, game_id, "me", p_home=p_home, p_away=round(1 - p_home, 4),
                          odds_id=odds["id"] if odds else None)
    except sqlite3.DatabaseError as e:
        raise PickError(f"Refused by the database: {e}")
    return (f"Logged your pick: {team} {pct:.0f}% in {g['away_team']} at {g['home_team']} "
            f"({db.fmt_et(g['start_time_utc'])}).")


def main():
    a = sys.argv[1:]
    conn = db.connect()
    if len(a) == 2 and a[0] == "list":
        list_games(conn, a[1])
        return
    if len(a) != 3:
        sys.exit(__doc__)
    try:
        print(log_pick(conn, int(a[0]), a[1], float(a[2])))
    except PickError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()

"""Log your own pick (source 'me') before kickoff.

Usage:
  python3 my_pick.py list nfl|ncaaf          upcoming games (next 7 days) with ids
  python3 my_pick.py <game id> <team> <win %>
      e.g. python3 my_pick.py 1234 DEN 60  means you think Denver wins 60% of the time.
  Club soccer: <team> can also be Draw. The other two outcomes split the rest in the market's
      proportions (latest odds), e.g. my_pick.py 5678 Draw 35.

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
    soccer = g["sport"] == "soccer_club"
    choices = (g["home_team"], g["away_team"]) + (("Draw",) if soccer else ())
    if team not in choices:
        raise PickError(f"{team} isn't in this game ({g['away_team']} at {g['home_team']})"
                        + ("; for a draw, pick Draw." if soccer else "."))
    if not 0 < pct < 100:
        raise PickError("Win % must be between 0 and 100.")
    odds = conn.execute("SELECT id FROM odds WHERE game_id = ? ORDER BY captured_at DESC, id LIMIT 1",
                        (game_id,)).fetchone()
    if soccer:
        from predict_soccer import clean_probs, latest_odds
        mkt = latest_odds(conn, game_id)
        if mkt is None:
            raise PickError("No odds yet for this game, so the other two outcomes can't be split by the market. "
                            "Try again after the next odds pull.")
        i = (g["home_team"], "Draw", g["away_team"]).index(team)
        rest = [mkt["p"][k] for k in range(3) if k != i]
        probs = [0.0, 0.0, 0.0]
        probs[i] = pct / 100
        for k, share in zip([k for k in range(3) if k != i], rest):
            probs[k] = (1 - pct / 100) * share / sum(rest)
        ph, pd, pa = clean_probs(*probs)
        values = {"p_home": ph, "p_draw": pd, "p_away": pa}
    else:
        p_home = round(pct / 100 if team == g["home_team"] else 1 - pct / 100, 4)
        values = {"p_home": p_home, "p_away": round(1 - p_home, 4)}
    try:
        db.add_prediction(conn, game_id, "me", odds_id=odds["id"] if odds else None, **values)
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

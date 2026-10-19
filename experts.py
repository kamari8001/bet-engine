"""Record what expert sources showed before a game, with the source link.

Usage:
  python3 experts.py games nfl|ncaaf|nba|ncaab [hours]
      upcoming games (default next 8 hours) with ids, for matching what a page shows
  python3 experts.py splits <game id> <away handle %> <away bets %> <home handle %> <home bets %> "<source url>"
      DraftKings moneyline splits for both sides (each pair must add to about 100)
  python3 experts.py circa <game id> <team> <pick %> <rank> "<source url>"
      a Circa Million consensus side (rank 1 = most-picked), NFL
  python3 experts.py list [sport]
      signals recorded in the last 7 days

Signals feed the shadow challengers dk_sharp_money_v1 and circa_consensus_v1
(backtest_results/shadow_challengers.md). Run `python3 shadow.py log <sport>` after recording.
"""

import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import db


def list_upcoming(conn, sport, hours):
    now = datetime.now(timezone.utc)
    for g in conn.execute("SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
                          " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id)"
                          " ORDER BY start_time_utc", (sport, db.to_utc(now), db.to_utc(now + timedelta(hours=hours)))):
        print(f"  [{g['id']}] {db.fmt_et(g['start_time_utc']):<24} {g['away_team']} at {g['home_team']}")


def main():
    a = sys.argv[1:]
    conn = db.connect()
    try:
        if a[:1] == ["games"] and len(a) in (2, 3):
            list_upcoming(conn, a[1], float(a[2]) if len(a) == 3 else 8)
        elif a[:1] == ["splits"] and len(a) == 7:
            g = conn.execute("SELECT * FROM games WHERE id = ?", (int(a[1]),)).fetchone()
            if g is None:
                sys.exit("No game with that id.")
            ah, ab, hh, hb = (float(x) for x in a[2:6])
            db.add_expert_signal(conn, g["id"], "dk_splits", source_url=a[6],
                                 away_handle=ah, away_bets=ab, home_handle=hh, home_bets=hb)
            print(f"Recorded DK splits for {g['away_team']} at {g['home_team']}: "
                  f"{g['away_team']} {ah:.0f}% money / {ab:.0f}% bets, {g['home_team']} {hh:.0f}% / {hb:.0f}%")
        elif a[:1] == ["circa"] and len(a) == 6:
            g = conn.execute("SELECT * FROM games WHERE id = ?", (int(a[1]),)).fetchone()
            if g is None or g["sport"] != "nfl":
                sys.exit("No NFL game with that id.")
            if a[2] not in (g["home_team"], g["away_team"]):
                sys.exit(f"{a[2]} isn't in this game ({g['away_team']} at {g['home_team']}).")
            side = "home" if a[2] == g["home_team"] else "away"
            db.add_expert_signal(conn, g["id"], "circa_consensus", source_url=a[5], side=side,
                                 pick_pct=float(a[3]), pick_rank=int(a[4]))
            print(f"Recorded Circa consensus #{a[4]}: {a[2]} ({float(a[3]):.0f}% of entries).")
        elif a[:1] == ["list"]:
            sport = a[1] if len(a) > 1 else None
            for r in conn.execute(
                    "SELECT e.*, g.sport, g.away_team, g.home_team FROM expert_signals e JOIN games g ON g.id = e.game_id"
                    " WHERE e.created_at > datetime('now', '-7 days') AND (? IS NULL OR g.sport = ?) ORDER BY e.created_at",
                    (sport, sport)):
                what = (f"money {r['away_handle']:.0f}/{r['home_handle']:.0f}, bets {r['away_bets']:.0f}/{r['home_bets']:.0f}"
                        if r["source"] == "dk_splits" else
                        f"#{r['pick_rank']} {r[r['side'] + '_team']} {r['pick_pct']:.0f}%")
                print(f"  {db.fmt_et(r['created_at']):<24} {r['sport'].upper():<6} {r['away_team']} at {r['home_team']}: "
                      f"{r['source']} {what}")
        else:
            sys.exit(__doc__)
    except (ValueError, IndexError):
        sys.exit("Couldn't read the numbers. " + __doc__)
    except sqlite3.DatabaseError as e:
        sys.exit(f"Refused by the database: {e}")


if __name__ == "__main__":
    main()

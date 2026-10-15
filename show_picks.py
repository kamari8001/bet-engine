"""Show each source's current pick for upcoming games, side by side. Read-only.

Usage: python3 show_picks.py nfl | ncaaf  [--days N]   (default: next 7 days)

For each game: the latest prediction from engine, claude and me (the one that
would be graded if kickoff were now), plus the market's no-vig view.
"""

import statistics
import sys
from datetime import datetime, timedelta, timezone

import db
from odds_math import no_vig

SOURCES = ("engine", "claude", "me")


def pick_text(g, p_home):
    if p_home is None:
        return "-"
    if p_home >= 0.5:
        return f"{g['home_team']} {p_home:.0%}"
    return f"{g['away_team']} {1 - p_home:.0%}"


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("nfl", "ncaaf"):
        sys.exit(__doc__)
    days = int(a[a.index("--days") + 1]) if "--days" in a else 7
    conn = db.connect()
    now = datetime.now(timezone.utc)
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " ORDER BY start_time_utc, id",
        (a[0], db.to_utc(now), db.to_utc(now + timedelta(days=days)))).fetchall()
    width = max([len(f"{g['away_team']} at {g['home_team']}") for g in games] + [4])
    print(f"{'kickoff':<24} {'game':<{width}}  " + "".join(f"{s:<26}" for s in SOURCES + ("market",)))
    for g in games:
        cells = []
        for s in SOURCES:
            r = conn.execute("SELECT p_home FROM predictions WHERE game_id = ? AND source = ?"
                             " AND corrects_id IS NULL ORDER BY created_at DESC, id DESC LIMIT 1",
                             (g["id"], s)).fetchone()
            cells.append(pick_text(g, r["p_home"] if r else None))
        odds = conn.execute("SELECT home_ml, away_ml FROM odds WHERE game_id = ? AND captured_at ="
                            " (SELECT MAX(captured_at) FROM odds WHERE game_id = ?)",
                            (g["id"], g["id"])).fetchall()
        mkt = statistics.mean(no_vig(o["home_ml"], o["away_ml"])[0] for o in odds) if odds else None
        cells.append(pick_text(g, mkt))
        print(f"{db.fmt_et(g['start_time_utc']):<24} {g['away_team'] + ' at ' + g['home_team']:<{width}}  "
              + "".join(f"{c:<26}" for c in cells))
    print("\nEach cell: the team that source favors and its win chance. '-' = no prediction logged.")


if __name__ == "__main__":
    main()

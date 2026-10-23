"""NBA box scores from ESPN for the player-impact model (plans/player_impact.md).

Usage:
  python3 pull_nba_players.py history     every NBA game in the history not yet fetched (resumable; ~1 hour first time)
  python3 pull_nba_players.py current     games from the last 7 days (for the daily routine)
  python3 pull_nba_players.py summary     what's loaded

One ESPN request per game: each player's position, minutes, full box-score line (shooting, rebounds,
assists, turnovers, steals, blocks, fouls), plus-minus, starter flag, and whether he didn't play and why. Games with no box score are remembered so they aren't asked again.
"""

import sys
import time
from datetime import datetime, timedelta, timezone

import db
from pull_basketball_history import espn_get

SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={e}"
PAUSE = 0.12
MAX_FAILS = 20


def minutes_of(text):
    if not text:
        return None
    try:
        if ":" in text:
            m, s = text.split(":")
            return int(m) + int(s) / 60
        return float(text)
    except ValueError:
        return None


def number(text):
    try:
        return int(str(text).replace("+", ""))
    except (TypeError, ValueError):
        return None


def made_att(text):
    """'5-9' -> (5, 9)."""
    try:
        m, a = str(text).split("-")
        return int(m), int(a)
    except (TypeError, ValueError, AttributeError):
        return None, None


def fetch_game(conn, g):
    """Fetch and store one game's box score. Returns the number of player rows, or None if ESPN failed."""
    try:
        data = espn_get(SUMMARY.format(e=g["external_id"]))
    except RuntimeError:
        return None
    rows = []
    for team in ((data or {}).get("boxscore") or {}).get("players") or []:
        code = team["team"]["abbreviation"]
        if code not in (g["home_team"], g["away_team"]):
            continue
        for block in team.get("statistics") or []:
            names = block.get("names") or block.get("keys") or []
            idx = {n: i for i, n in enumerate(names)}
            for a in block.get("athletes") or []:
                if not (a.get("athlete") or {}).get("id"):
                    continue                        # a placeholder entry with no player behind it
                stats = a.get("stats") or []
                get = lambda key: stats[idx[key]] if key in idx and idx[key] < len(stats) else None
                dnp = bool(a.get("didNotPlay"))
                mins = minutes_of(get("MIN")) if not dnp else 0.0
                fg, tp, ft = made_att(get("FG")), made_att(get("3PT")), made_att(get("FT"))
                pos = ((a["athlete"].get("position") or {}).get("abbreviation"))
                rows.append((g["id"], code, str(a["athlete"]["id"]), a["athlete"]["displayName"], pos,
                             int(bool(a.get("starter"))), int(not dnp and (mins or 0) > 0), mins,
                             number(get("PTS")), fg[0], fg[1], tp[0], tp[1], ft[0], ft[1],
                             number(get("OREB")), number(get("DREB")), number(get("AST")), number(get("TO")),
                             number(get("STL")), number(get("BLK")), number(get("PF")),
                             number(get("+/-")), a.get("reason") if dnp else None))
    if not any(r[6] and r[6] > 0 for r in rows):
        rows = []          # ESPN has no box score for this game ("--" minutes for everyone): store nothing,
                           # so the feature treats it as unknown rather than as a whole roster absent
    conn.executemany("INSERT OR REPLACE INTO hist_player_games VALUES (" + ",".join("?" * 24) + ")", rows)
    conn.execute("INSERT OR REPLACE INTO hist_box_pulled (hist_game_id, players) VALUES (?, ?)", (g["id"], len(rows)))
    return len(rows)


def pull(conn, games):
    done = fails = players = 0
    for g in games:
        n = fetch_game(conn, g)
        if n is None:
            fails += 1
            if fails >= MAX_FAILS:
                conn.commit()
                sys.exit(f"STOP: ESPN refused {MAX_FAILS} requests in a row after {done} games. Everything so far is saved; re-run to resume.")
            continue
        fails = 0
        done += 1
        players += n
        if done % 200 == 0:
            conn.commit()
            print(f"  {done}/{len(games)} games fetched ({g['game_date_et']})", flush=True)
        time.sleep(PAUSE)
    conn.commit()
    print(f"Box scores: {done} games fetched, {players} player rows.")


def todo(conn, since=None):
    q = ("SELECT g.* FROM hist_games g WHERE g.sport = 'nba' AND NOT EXISTS"
         " (SELECT 1 FROM hist_box_pulled b WHERE b.hist_game_id = g.id)")
    args = ()
    if since:
        q += " AND g.game_date_et >= ?"
        args = (since,)
    return conn.execute(q + " ORDER BY g.game_date_et, g.id", args).fetchall()


def summary(conn):
    for r in conn.execute(
            "SELECT g.season, COUNT(DISTINCT g.id) games, COUNT(DISTINCT b.hist_game_id) fetched,"
            " ROUND(1.0 * COUNT(p.player_id) / MAX(1, COUNT(DISTINCT b.hist_game_id)), 1) players_per_game,"
            " SUM(p.played = 0) dnp FROM hist_games g LEFT JOIN hist_box_pulled b ON b.hist_game_id = g.id"
            " LEFT JOIN hist_player_games p ON p.hist_game_id = g.id WHERE g.sport = 'nba' GROUP BY g.season"):
        print(f"  {r['season'] - 1}-{r['season'] % 100:02d}: {r['fetched']}/{r['games']} games fetched, "
              f"{r['players_per_game']} players per game, {r['dnp'] or 0} did-not-play rows")


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("history", "current", "summary"):
        sys.exit(__doc__)
    conn = db.connect()
    db.upgrade_db(conn)
    if a[0] == "summary":
        summary(conn)
        return
    since = None if a[0] == "history" else (datetime.now(timezone.utc).astimezone(db.EASTERN).date() - timedelta(days=7)).isoformat()
    games = todo(conn, since)
    print(f"{len(games)} game(s) to fetch.", flush=True)
    pull(conn, games)


if __name__ == "__main__":
    main()

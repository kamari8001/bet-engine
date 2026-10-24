"""College basketball box scores from CBBD for the player-impact model (plans/college_player_impact.md).

Usage:
  python3 pull_ncaab_players.py history     every college game in the history not yet fetched (resumable; ~200 CBBD calls)
  python3 pull_ncaab_players.py current     games from the last 7 days (for the daily routine; 1-2 calls)
  python3 pull_ncaab_players.py summary     what's loaded

CBBD's /games/players returns each team's box score per game: position, minutes, shooting, rebounds,
assists, turnovers, steals, blocks, fouls, starter flag (no plus-minus; only players who played are
listed). One call returns at most 1,000 team rows (500 games), so dates are fetched in windows of at
most WINDOW_GAMES of our games; a window that comes back full is split in two and asked again.
Games CBBD returns no box score for are remembered (0 players) so they aren't asked again.
Player id = ESPN's id when CBBD gives it (for headshots and ESPN's injury list), else "cbbd:<id>".
"""

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import db
from pull_basketball_history import cbbd_get

ROW_LIMIT = 1000           # CBBD's cap on team rows per call
WINDOW_GAMES = 380         # our games per request window (CBBD lists a few more games than we keep)
MAX_CALLS = 450            # safety stop for one run (the key allows ~1,000 calls a month)

COLUMNS = ("hist_game_id", "team", "player_id", "player_name", "position", "starter", "played", "minutes",
           "points", "fg_made", "fg_att", "tp_made", "tp_att", "ft_made", "ft_att", "oreb", "dreb", "ast",
           "tov", "stl", "blk", "pf", "plus_minus", "reason")


def headers():
    key = next((l.split("=", 1)[1].strip() for l in open(Path(__file__).parent / ".env")
                if l.startswith("CFBD_API_KEY=")), "")
    if not key:
        sys.exit("CFBD_API_KEY is empty in .env (CBBD uses the same key).")
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}


def player_rows(hist_id, rec):
    out = []
    for p in rec.get("players") or []:
        pid = p.get("athleteSourceId") or (f"cbbd:{p['athleteId']}" if p.get("athleteId") is not None else None)
        if not pid or not p.get("name"):
            continue
        m = p.get("minutes") or 0
        g = lambda k, sub=None: ((p.get(k) or {}).get(sub) if sub else p.get(k))
        out.append((hist_id, rec["team"], str(pid), p["name"], p.get("position"), int(bool(p.get("starter"))),
                    int(m > 0), m, g("points"), g("fieldGoals", "made"), g("fieldGoals", "attempted"),
                    g("threePointFieldGoals", "made"), g("threePointFieldGoals", "attempted"),
                    g("freeThrows", "made"), g("freeThrows", "attempted"), g("rebounds", "offensive"),
                    g("rebounds", "defensive"), g("assists"), g("turnovers"), g("steals"), g("blocks"),
                    g("fouls"), None, None))
    return out


def windows(pending):
    """Split pending games into runs of consecutive dates with at most WINDOW_GAMES games."""
    by_date = defaultdict(list)
    for g in pending:
        by_date[g["game_date_et"]].append(g)
    out, cur, n = [], [], 0
    for d in sorted(by_date):
        k = len(by_date[d])
        if cur and n + k > WINDOW_GAMES:
            out.append(cur)
            cur, n = [], 0
        cur.append(d)
        n += k
    if cur:
        out.append(cur)
    return out, by_date


class Puller:
    def __init__(self, conn):
        self.conn, self.h, self.calls = conn, headers(), 0

    def fetch(self, season, first, last):
        """CBBD rows for ET dates first..last (UTC range reaches one day further for evening games);
        a full response is split in half and asked again."""
        if self.calls >= MAX_CALLS:
            self.conn.commit()
            sys.exit(f"STOP: {MAX_CALLS} CBBD calls in this run (safety limit). Saved so far; re-run to resume.")
        end = (date.fromisoformat(last) + timedelta(days=1)).isoformat()
        self.calls += 1
        rows = cbbd_get(f"/games/players?season={season}&startDateRange={first}&endDateRange={end}", self.h)
        if len(rows) >= ROW_LIMIT:
            if first == last:
                self.conn.commit()
                sys.exit(f"STOP: CBBD returned a full page for the single day {first}; can't split further.")
            mid = (date.fromisoformat(first) + (date.fromisoformat(last) - date.fromisoformat(first)) / 2).isoformat()
            nxt = (date.fromisoformat(mid) + timedelta(days=1)).isoformat()
            return self.fetch(season, first, mid) + self.fetch(season, nxt, last)
        return rows

    def run(self, pending):
        by_season = defaultdict(list)
        for g in pending:
            by_season[g["season"]].append(g)
        games = players = missing = 0
        for season in sorted(by_season):
            wins, by_date = windows(by_season[season])
            for dates in wins:
                todo = {g["external_id"]: g for d in dates for g in by_date[d]}
                recs = defaultdict(list)
                for r in self.fetch(season, dates[0], dates[-1]):
                    recs[str(r["gameId"])].append(r)
                with self.conn:
                    for ext, g in todo.items():
                        rows = [x for r in recs.get(ext, []) for x in player_rows(g["id"], r)]
                        if rows:
                            self.conn.executemany(f"INSERT OR IGNORE INTO hist_player_games ({', '.join(COLUMNS)})"
                                                  f" VALUES ({', '.join('?' * len(COLUMNS))})", rows)
                        else:
                            missing += 1
                        self.conn.execute("INSERT OR REPLACE INTO hist_box_pulled (hist_game_id, players) VALUES (?, ?)",
                                          (g["id"], len(rows)))
                        games += 1
                        players += len(rows)
            print(f"  {season - 1}-{season % 100:02d}: done ({self.calls} calls so far)", flush=True)
        print(f"Box scores: {games} games ({missing} with none on CBBD), {players} player rows, {self.calls} CBBD calls.")


def todo(conn, since=None):
    q = ("SELECT g.* FROM hist_games g WHERE g.sport = 'ncaab' AND g.source = 'cbbd' AND NOT EXISTS"
         " (SELECT 1 FROM hist_box_pulled b WHERE b.hist_game_id = g.id)")
    args = ()
    if since:
        q += " AND g.game_date_et >= ?"
        args = (since,)
    return conn.execute(q + " ORDER BY g.game_date_et, g.id", args).fetchall()


def summary(conn):
    for r in conn.execute(
            "SELECT g.season, COUNT(DISTINCT g.id) games, COUNT(DISTINCT b.hist_game_id) fetched,"
            " SUM(b.players = 0) empty FROM hist_games g LEFT JOIN hist_box_pulled b ON b.hist_game_id = g.id"
            " WHERE g.sport = 'ncaab' GROUP BY g.season"):
        per = conn.execute(
            "SELECT ROUND(1.0 * COUNT(*) / MAX(1, COUNT(DISTINCT p.hist_game_id || p.team)), 1),"
            " ROUND(AVG(p.team IN (g.home_team, g.away_team)), 3) FROM hist_player_games p"
            " JOIN hist_games g ON g.id = p.hist_game_id WHERE g.sport = 'ncaab' AND g.season = ?", (r["season"],)).fetchone()
        print(f"  {r['season'] - 1}-{r['season'] % 100:02d}: {r['fetched']}/{r['games']} games fetched "
              f"({r['empty'] or 0} with no box score), {per[0] or 0} players per team, team names matched {per[1] or 0:.1%}")


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
    # only finished games: CBBD has no box score before the game is played
    today = datetime.now(timezone.utc).astimezone(db.EASTERN).date().isoformat()
    games = [g for g in games if g["game_date_et"] < today]
    print(f"{len(games)} college game(s) to fetch.", flush=True)
    if games:
        Puller(conn).run(games)


if __name__ == "__main__":
    main()

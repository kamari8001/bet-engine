"""Watch ESPN's NBA injury list and react to news right away (plans/news_timing.md).

Usage:
  python3 injury_watch.py run       look once (the automation does this every 10 minutes on NBA days):
                                    record status changes for rotation players in games within 36 hours;
                                    on material news, pull NBA odds and log predictions immediately
  python3 injury_watch.py report    the news-timing test: news CLV per material event vs the pre-registered bar

Material news = a team's missing value moves by MATERIAL points of margin or more at one look (a
rotation player ruled Out, or listed Out and then cleared), in a game within TRIGGER_AHEAD. Triggered
odds pulls are limited to one per MIN_GAP and MAX_PER_DAY a day (1 Odds API credit each).
News CLV = how far the no-vig market moved from our triggered pull to the close, toward the side the
news favors (the opponent of the team that lost a player). Display/measurement only: the probabilities
come from predict.py exactly as before; they're just logged sooner.
"""

import json
import math
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db

HERE = Path(__file__).parent
STATE_PATH = HERE / "cache" / "injury_watch.json"
LOOKAHEAD = timedelta(hours=36)
TRIGGER_AHEAD = timedelta(hours=24)
MATERIAL = 1.0
MIN_GAP = timedelta(minutes=15)
MAX_PER_DAY = 30
PULL_MATCH = timedelta(minutes=15)    # the triggered pull = first odds snapshot this soon after the event
PROGRESS_AT, DECIDE_AT = 50, 100


def utc_now():
    return datetime.now(timezone.utc)


def parse(t):
    return datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def listed_now():
    """{player id: (team, status, name)} from ESPN's injury list; None if it can't be read."""
    import player_model as pm
    try:
        inj = pm.espn_injuries()
    except RuntimeError as e:
        print(f"Couldn't read ESPN's injury list ({e}); nothing recorded, will look again next run.")
        return None
    return {i["id"]: (team, i["status"], i["name"]) for team, rows in inj.items() for i in rows}


def run(conn):
    now = utc_now()
    current = listed_now()
    if current is None:
        return
    STATE_PATH.parent.mkdir(exist_ok=True)
    prev = json.loads(STATE_PATH.read_text())["listed"] if STATE_PATH.exists() else None
    STATE_PATH.write_text(json.dumps({"listed": current, "seen_at": db.to_utc(now)}))
    if prev is None:
        print(f"First look: {len(current)} players on ESPN's list saved as the starting point.")
        return
    changes = []
    for pid in set(prev) | set(current):
        old, new = prev.get(pid), current.get(pid)
        old_status, new_status = (old[1] if old else "none"), (new[1] if new else "none")
        if old_status != new_status:
            team, name = (new or old)[0], (new or old)[2]
            changes.append((pid, team, name, old_status, new_status))
    if not changes:
        print("No changes on ESPN's injury list.")
        return

    games = conn.execute("SELECT * FROM games WHERE sport = 'nba' AND start_time_utc > ? AND start_time_utc <= ?"
                         " AND NOT EXISTS (SELECT 1 FROM results r WHERE r.game_id = games.id)"
                         " ORDER BY start_time_utc", (db.to_utc(now), db.to_utc(now + LOOKAHEAD))).fetchall()
    next_game = {}
    for g in games:
        for team in (g["home_team"], g["away_team"]):
            next_game.setdefault(team, g)
    relevant = [c for c in changes if c[1] in next_game]
    if not relevant:
        print(f"{len(changes)} change(s) on ESPN's list, none for a team playing in the next 36 hours.")
        return

    import players_view
    lb = players_view.live_book(conn)
    book, coef = lb["book"], lb["coef"]
    rows, team_change = [], {}
    for pid, team, name, old_status, new_status in relevant:
        g = next_game[team]
        day = db.utc_to_eastern(g["start_time_utc"]).date()
        rot = dict(book.rotation(team, day))
        if pid not in rot:
            continue
        value = coef * book.value(rot[pid])
        was_out, is_out = old_status.lower() == "out", new_status.lower() == "out"
        change = value if is_out and not was_out else -value if was_out and not is_out else 0.0
        rows.append([g, team, pid, rot[pid]["name"], old_status, new_status, value, change])
        team_change[(g["id"], team)] = team_change.get((g["id"], team), 0.0) + change
    if not rows:
        print(f"{len(relevant)} change(s) for teams playing soon, none for rotation players.")
        return

    material_keys = {k for k, v in team_change.items() if abs(v) >= MATERIAL}
    material_keys = {k for k in material_keys
                     if parse(next(r[0] for r in rows if (r[0]["id"], r[1]) == k)["start_time_utc"]) - now <= TRIGGER_AHEAD}
    last = conn.execute("SELECT MAX(created_at) FROM injury_events WHERE triggered = 1").fetchone()[0]
    today_et = db.utc_to_eastern(db.to_utc(now)).date()
    today_count = sum(1 for (t,) in conn.execute("SELECT created_at FROM injury_events WHERE triggered = 1 AND created_at > ?",
                                                 (db.to_utc(now - timedelta(days=1)),))
                      if db.utc_to_eastern(t).date() == today_et)
    trigger = bool(material_keys) and (last is None or now - parse(last) >= MIN_GAP) and today_count < MAX_PER_DAY
    with conn:
        for g, team, pid, name, old_status, new_status, value, change in rows:
            material = (g["id"], team) in material_keys
            conn.execute("INSERT INTO injury_events (game_id, team, player_id, player_name, old_status, new_status,"
                         " value_pts, missing_change, material, triggered) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (g["id"], team, pid, name, old_status, new_status, round(value, 2), round(change, 2),
                          int(material), int(material and trigger)))
            print(f"{team} {name}: {old_status} -> {new_status} (value {value:+.1f} pts; {g['away_team']} at "
                  f"{g['home_team']}, {db.fmt_et(g['start_time_utc'])}){'  MATERIAL' if material else ''}")
    if material_keys and not trigger:
        print("Material news, but the triggered-pull limit is reached; the next scheduled pull will pick it up.")
    if trigger:
        for step in (["pull_odds.py", "nba"], ["predict.py", "nba", "--days", "2"]):
            r = subprocess.run([sys.executable, str(HERE / step[0])] + step[1:], cwd=HERE, capture_output=True,
                               text=True, timeout=900)
            print(f"-- {' '.join(step)} --\n{(r.stdout + r.stderr).strip()[-1500:]}")
            if r.returncode != 0:
                sys.exit(f"STOP: {step[0]} failed after material news (see above).")


# ---------- the test ----------

def news_timing(conn):
    """Per material event (the first per game and team, before tip-off, in a finished game): the market
    for the side the news favors at the morning line, at our triggered pull, and at the close."""
    from grade import closing, market_at
    seen, out = set(), []
    events = conn.execute(
        "SELECT e.game_id, e.team, e.created_at, SUM(e.missing_change) change, GROUP_CONCAT(e.player_name || ' ' ||"
        " e.new_status, ', ') what FROM injury_events e WHERE e.material = 1 GROUP BY e.game_id, e.team, e.created_at"
        " ORDER BY e.created_at").fetchall()
    for e in events:
        key = (e["game_id"], e["team"])
        if key in seen:
            continue
        seen.add(key)
        g = conn.execute("SELECT * FROM games WHERE id = ?", (e["game_id"],)).fetchone()
        if parse(g["start_time_utc"]) > utc_now():
            continue                                  # not finished: no closing line yet
        t = parse(e["created_at"])
        pull = conn.execute("SELECT MIN(captured_at) FROM odds WHERE game_id = ? AND captured_at >= ? AND captured_at <= ?",
                            (g["id"], db.to_utc(t), db.to_utc(t + PULL_MATCH))).fetchone()[0]
        close, _ = closing(conn, g)
        if not pull or not close:
            continue
        day_start = datetime.combine(db.utc_to_eastern(e["created_at"]).date(), datetime.min.time(), tzinfo=db.EASTERN)
        morning = conn.execute("SELECT MIN(captured_at) FROM odds WHERE game_id = ? AND captured_at >= ? AND captured_at < ?",
                               (g["id"], db.to_utc(day_start.astimezone(timezone.utc)), e["created_at"])).fetchone()[0]
        favored_home = (e["team"] == g["away_team"]) == (e["change"] > 0)   # the news hurts the team that lost a player
        side = (lambda p: p) if favored_home else (lambda p: 1 - p)
        at_pull, at_close = side(market_at(conn, g["id"], pull)["p_home"]), side(close["p_home"])
        at_morning = side(market_at(conn, g["id"], morning)["p_home"]) if morning else None
        total = at_close - at_morning if at_morning is not None else None
        out.append({"game": f"{g['away_team']} at {g['home_team']}", "when": db.fmt_et(e["created_at"]),
                    "news": f"{e['team']}: {e['what']}", "change": e["change"],
                    "favored": g["home_team"] if favored_home else g["away_team"],
                    "morning": at_morning, "at_pull": at_pull, "close": at_close, "news_clv": at_close - at_pull,
                    "already": (at_pull - at_morning) / total if total is not None and abs(total) >= 0.005 else None,
                    "minutes_before_tip": (parse(g["start_time_utc"]) - t).total_seconds() / 60})
    clv = [r["news_clv"] for r in out]
    summary = {"n": len(clv), "mean": statistics.mean(clv) if clv else None,
               "ci": None, "verdict": None}
    if len(clv) >= 2:
        half = 1.96 * statistics.stdev(clv) / math.sqrt(len(clv))
        summary["ci"] = (summary["mean"] - half, summary["mean"] + half)
    n = len(clv)
    summary["verdict"] = (f"collecting ({n} of {DECIDE_AT} events)" if n < PROGRESS_AT else
                          f"progress look only ({n} of {DECIDE_AT})" if n < DECIDE_AT else
                          "EARLY: the line kept moving after we saw the news" if summary["ci"][0] > 0 else
                          "NOT EARLY: ESPN's list doesn't beat the market")
    return out, summary


def report(conn):
    rows, s = news_timing(conn)
    print("News timing (NBA, plans/news_timing.md): material injury news, first look per team and game.")
    for r in rows:
        already = f"{r['already']:.0%} of the day's move already done" if r["already"] is not None else "no morning line"
        print(f"  {r['when']}  {r['game']}: {r['news']} -> favors {r['favored']}: market {r['at_pull']:.1%} at our pull, "
              f"{r['close']:.1%} at close (news CLV {r['news_clv'] * 100:+.1f} pts; {already}; "
              f"{r['minutes_before_tip']:.0f} min before tip)")
    if s["n"]:
        ci = f", 95% range {s['ci'][0] * 100:+.2f} to {s['ci'][1] * 100:+.2f}" if s["ci"] else ""
        print(f"\n{s['n']} events: average news CLV {s['mean'] * 100:+.2f} pts{ci}.")
    print(f"Status: {s['verdict']}. Bar: after {DECIDE_AT} events, the 95% range must sit above 0.")
    pending = conn.execute("SELECT COUNT(*) FROM injury_events WHERE material = 1").fetchone()[0]
    print(f"(Material events recorded so far, including games not finished: {pending}.)")


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("run", "report"):
        sys.exit(__doc__)
    conn = db.connect()
    run(conn) if a[0] == "run" else report(conn)


if __name__ == "__main__":
    main()

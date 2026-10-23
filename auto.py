"""Run the routine on a schedule. launchd runs this every 10 minutes
(automation/com.betengine.auto.plist); each run does whatever is due.

Usage:
  python3 auto.py             do whatever is due now
  python3 auto.py --dry-run   show what would run, run nothing
  python3 auto.py --status    show what's done and what's coming

Tasks (all times Eastern):
  morning  9:00 AM   results -> history -> odds -> predictions -> grades
  windows  20-30 min before each kickoff window: odds for that sport, then predictions
           (a window = games starting within 30 minutes of the first one)
  night    3:00 AM   results -> grades
  catch-up right after the Mac wakes (no run for 20+ min): if games start within
           2 hours and our latest odds for that sport are 2+ hours old, pull now
           (the normal 20-30 min pull still happens later if the Mac stays awake)
Every step's output goes to logs/auto.log. If a step fails, the rest of that
task is skipped and a Mac notification says so (rule 5: stop, don't guess).
"""

import fcntl
import json
import socket
import subprocess
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
from pull_odds import MIN_CREDITS, api_keys, credits_left

HERE = Path(__file__).parent
LOG_DIR = HERE / "logs"
STATE_PATH = LOG_DIR / "auto_state.json"
LOCK_PATH = LOG_DIR / "auto.lock"
MORNING_HOUR, NIGHT_HOUR = 9, 3
WINDOW_GAP = timedelta(minutes=30)          # games this close together share one pull
PULL_BEFORE = (timedelta(minutes=5), timedelta(minutes=30))  # pull when first kickoff is this far away
CATCHUP_AHEAD = timedelta(hours=2)          # look this far ahead after waking
CATCHUP_STALE = timedelta(hours=2)          # ...and pull if odds are older than this
FRESH_ODDS = timedelta(minutes=15)          # a sport's odds newer than this don't need another pull
WOKE_GAP = timedelta(minutes=20)            # a gap this long between runs = Mac was asleep
LOW_CREDITS_WARN = 150                       # notify below this
COLLEGE_WINDOWS_MIN_CREDITS = 100            # below this, skip college pre-kickoff pulls
SPORTS = ("nfl", "ncaaf", "nba", "ncaab", "soccer_club")

MORNING = [["pull_games.py", "all"], ["pull_history.py", "all", "--current"],
           ["pull_basketball_history.py", "nba", "current"], ["pull_basketball_history.py", "ncaab", "current"],
           ["pull_nba_players.py", "current"],
           ["pull_soccer_history.py", "current"], ["pull_soccer_history.py", "extra", "--refresh"],
           ["pull_europe.py", "fetch", "--refresh"], ["pull_europe.py", "load"],
           ["pull_odds.py", "all"]] + [["predict.py", s] for s in SPORTS] + [["shadow.py", "log", "all"]] \
          + [["grade.py", s] for s in SPORTS]
NIGHT = [["pull_games.py", "all"], ["pull_soccer_history.py", "current"],
         ["pull_europe.py", "fetch", "--refresh"], ["pull_europe.py", "load"]] + [["grade.py", s] for s in SPORTS]


def window_steps(sport):
    """Steps for a pre-kickoff pull: odds, predictions, and shadow challengers (none for soccer yet)."""
    return [["pull_odds.py", sport], ["predict.py", sport]] + (
        [] if sport == "soccer_club" else [["shadow.py", "log", sport]])


def online():
    """True if the internet is reachable. A sleeping Mac wakes briefly every ~15 min
    for maintenance without network; runs then should do nothing and leave no trace."""
    try:
        socket.create_connection(("api.the-odds-api.com", 443), timeout=5).close()
        return True
    except OSError:
        return False


def now_et():
    return datetime.now(timezone.utc).astimezone(db.EASTERN)


def log(msg):
    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / "auto.log").open("a") as f:
        f.write(f"[{now_et():%Y-%m-%d %H:%M:%S} ET] {msg}\n")


def notify(msg):
    log(f"NOTIFY: {msg}")
    safe = msg.replace('"', "'")
    subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "Kamari\'s Prediction Engine"'],
                   capture_output=True)


def load_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"morning": None, "night": None, "windows": {}}


def save_state(state):
    # forget windows older than 3 days
    cutoff = db.to_utc(datetime.now(timezone.utc) - timedelta(days=3))
    state["windows"] = {k: v for k, v in state["windows"].items() if k.split("|")[1] >= cutoff}
    STATE_PATH.write_text(json.dumps(state, indent=2))


def run_steps(name, steps, dry):
    """Run steps in order; stop at the first failure. Returns True if all succeeded."""
    for step in steps:
        if dry:
            print(f"  would run: python3 {' '.join(step)}")
            continue
        log(f"{name}: running {' '.join(step)}")
        r = subprocess.run([sys.executable, str(HERE / step[0])] + step[1:], cwd=HERE,
                           capture_output=True, text=True, timeout=1800)
        out = (r.stdout + r.stderr).strip()
        log(out if out else "(no output)")
        if r.returncode != 0:
            last = out.splitlines()[0] if out else "no output"
            notify(f"{name} stopped at {step[0]} {' '.join(step[1:])}: {last[:150]}")
            return False
    return True


def kickoff_windows(conn, sport, start, end, now=None):
    """[(first kickoff UTC text, number of games)] for windows starting between start and end.
    Only games that haven't started count, so once a window's first game kicks off, its later
    games form their own window and still get a closing pull."""
    since = start - WINDOW_GAP if now is None else max(start - WINDOW_GAP, now)
    games = [r["start_time_utc"] for r in conn.execute(
        "SELECT start_time_utc FROM games WHERE sport = ? AND start_time_utc > ? ORDER BY start_time_utc",
        (sport, db.to_utc(since)))]
    windows, current = [], None
    for k in games:
        t = datetime.strptime(k, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if current and t - current[0] <= WINDOW_GAP:
            current[1] += 1
        else:
            current = [t, 1]
            windows.append(current)
    return [(db.to_utc(t), n) for t, n in windows if start <= t <= end]


def latest_odds_time(conn, sport):
    r = conn.execute("SELECT MAX(o.captured_at) FROM odds o JOIN games g ON g.id = o.game_id"
                     " WHERE g.sport = ?", (sport,)).fetchone()[0]
    return datetime.strptime(r, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if r else None


def due_tasks(conn, state, et, woke=False):
    """List of (task name, state key, steps) that should run now."""
    tasks = []
    today = et.strftime("%Y-%m-%d")
    if et.hour >= MORNING_HOUR and state["morning"] != today:
        tasks.append(("morning routine", ("morning", today), MORNING))
    if NIGHT_HOUR <= et.hour < MORNING_HOUR and state["night"] != today:
        tasks.append(("night results", ("night", today), NIGHT))
    utc = et.astimezone(timezone.utc)
    for sport in SPORTS:
        last = latest_odds_time(conn, sport)
        if last is not None and utc - last < FRESH_ODDS:
            continue  # just pulled (e.g. the previous window); the next run will look again
        for first, n in kickoff_windows(conn, sport, utc + PULL_BEFORE[0], utc + PULL_BEFORE[1], utc):
            key = f"{sport}|{first}"
            if key not in state["windows"]:
                tasks.append((f"{sport.upper()} closing odds ({n} game(s) from {db.fmt_et(first)})",
                              ("windows", key), window_steps(sport)))
        if woke:
            if last is None or utc - last >= CATCHUP_STALE:
                for first, n in kickoff_windows(conn, sport, utc + PULL_BEFORE[1], utc + CATCHUP_AHEAD, utc):
                    key = f"{sport}|{first}|catchup"
                    if key not in state["windows"]:
                        tasks.append((f"{sport.upper()} catch-up odds after wake ({n} game(s) from "
                                      f"{db.fmt_et(first)})", ("windows", key), window_steps(sport)))
                        break  # one pull covers every game of the sport
    return tasks


def status(conn, state):
    et = now_et()
    print(f"Now: {et:%a %b %d, %I:%M %p} ET")
    print(f"Morning routine last done: {state['morning']} | night results last done: {state['night']}")
    print(f"Pre-kickoff pulls done (last 3 days): {len(state['windows'])}")
    utc = et.astimezone(timezone.utc)
    print("\nUpcoming pre-kickoff odds pulls (next 3 days):")
    for sport in SPORTS:
        for first, n in kickoff_windows(conn, sport, utc, utc + timedelta(days=3)):
            pull_at = db.utc_to_eastern(first) - PULL_BEFORE[1]
            print(f"  {sport.upper():<6} pull around {pull_at:%a %I:%M %p} ET for {n} game(s) "
                  f"kicking off {db.fmt_et(first)}")
    try:
        print(f"\nOdds API credits left: {credits_left()}")
    except Exception as e:
        print(f"\nOdds API credits: couldn't check ({e})")


def main():
    dry = "--dry-run" in sys.argv
    LOG_DIR.mkdir(exist_ok=True)
    conn = db.connect()
    state = load_state()
    if "--status" in sys.argv:
        status(conn, state)
        return

    lock = LOCK_PATH.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("previous run still going; skipping this one")
        return

    if not online():
        # Don't record this run, so the next run with internet still counts as "just woke"
        log("no internet (Mac probably in a brief maintenance wake); doing nothing")
        return
    now = datetime.now(timezone.utc)
    last_run = state.get("last_run")
    woke = last_run is None or now - datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc) > WOKE_GAP
    if not dry:
        state["last_run"] = db.to_utc(now)
        save_state(state)
    tasks = due_tasks(conn, state, now_et(), woke)
    if not tasks:
        if dry:
            print("Nothing due right now.")
        return

    credits = None
    if any(t[1][0] == "windows" for t in tasks):
        try:
            credits = credits_left()
        except urllib.error.HTTPError as e:
            notify(f"Couldn't check Odds API credits: {e}")
            return
        except OSError as e:
            # Internet dropped between the online check and this call (common right after a
            # wake). Retry quietly next run, which should still count as "just woke".
            log(f"internet dropped while checking credits ({e}); retrying next run")
            if not dry:
                state["last_run"] = last_run
                save_state(state)
            return
        except Exception as e:
            notify(f"Couldn't check Odds API credits: {e}")
            return
        if credits < LOW_CREDITS_WARN:
            notify(f"Odds API credits low: {credits} left this month.")

    for name, (kind, key), steps in tasks:
        if kind == "windows" and key.startswith(("ncaaf", "ncaab")) and credits is not None \
                and credits < COLLEGE_WINDOWS_MIN_CREDITS:
            log(f"skipping {name}: only {credits} credits left (saving them for NFL)")
            continue
        cost = len(api_keys(key.split("|")[0])) if kind == "windows" else 0
        if kind == "windows" and credits is not None and credits - cost < MIN_CREDITS:
            notify(f"Skipping {name}: credits would drop below {MIN_CREDITS}.")
            continue
        if dry:
            print(f"{name}:")
        ok = run_steps(name, steps, dry)
        if not dry:
            if kind == "windows":
                state["windows"][key] = db.to_utc(datetime.now(timezone.utc))
                credits = credits - cost if credits is not None else None
            elif ok:
                state[kind] = key
            save_state(state)
            log(f"{name}: {'done' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()

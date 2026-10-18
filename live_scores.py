"""Live scores from ESPN's public scoreboard (unofficial, free, no key).

Display only: these are never stored as results. Official results and grading
still come from nflverse and CFBD. Each scoreboard is fetched at most once every
30 seconds, and only while someone has the Live tab open.
"""

import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import db

URLS = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates={date}",
    "ncaaf": ("https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
              "?dates={date}&groups=80&limit=300"),
}
CACHE_SECONDS = 30
_cache = {}  # (sport, date) -> (fetched at, {espn id: info})


class LiveUnavailable(Exception):
    pass


def _fetch(sport, date):
    key = (sport, date)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        req = urllib.request.Request(URLS[sport].format(date=date), headers={"User-Agent": "Mozilla/5.0"})
        data = json.load(urllib.request.urlopen(req, timeout=15))
    except Exception as e:
        raise LiveUnavailable(f"ESPN scoreboard unavailable ({e})")
    out = {}
    for e in data.get("events", []):
        comp = e["competitions"][0]
        status = e["status"]["type"]
        teams = {t["homeAway"]: t for t in comp["competitors"]}
        poss_id = (comp.get("situation") or {}).get("possession")
        possession = next((side for side, t in teams.items() if poss_id and t["team"]["id"] == poss_id), None)
        out[e["id"]] = {
            "state": status["state"],              # pre / in / post
            "detail": status.get("shortDetail", ""),  # e.g. "6:29 - 3rd", "Final", "Halftime"
            "home_score": int(teams["home"].get("score") or 0),
            "away_score": int(teams["away"].get("score") or 0),
            "possession": possession,
            "down": (comp.get("situation") or {}).get("shortDownDistanceText"),
        }
    _cache[key] = (time.time(), out)
    return out


def scoreboard(sport, now=None):
    """{espn id: info} for today's and yesterday's games (Eastern dates), so late
    games that run past midnight still show."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(db.EASTERN)
    out = {}
    for d in (today - timedelta(days=1), today):
        out.update(_fetch(sport, d.strftime("%Y%m%d")))
    return out

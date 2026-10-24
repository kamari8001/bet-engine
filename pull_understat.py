"""Expected goals (xG) for Big 5 league games from Understat (plans/soccer_xg.md).

Usage:
  python3 pull_understat.py history     every season 2014-15 on (one request per league and season, cached)
  python3 pull_understat.py current     this season again (5 requests; morning and night routines)
  python3 pull_understat.py summary     games with xG per league and season

Understat (understat.com, free, no key) publishes per-match xG. Its team names differ from ours, so
the name pairs are learned from games with the same date and score (the name each Understat team
matches most), saved to soccer_understat_teams.json for review, then every game is matched by league,
teams and date (within a day). A league-season is saved only if MIN_MATCH of its finished games match (games newer than our latest
loaded result don't count yet);
otherwise nothing is written for it and it's reported (never guessed). Stored in hist_games.home_xg /
away_xg (history only).
"""

import gzip
import json
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import db

HERE = Path(__file__).parent
CACHE = HERE / "cache" / "understat"
NAMES_PATH = HERE / "soccer_understat_teams.json"
URL = "https://understat.com/getLeagueData/{code}/{year}"
LEAGUES = {"EPL": "EPL", "La Liga": "La_liga", "Bundesliga": "Bundesliga", "Serie A": "Serie_A", "Ligue 1": "Ligue_1"}
FIRST_YEAR = 2014            # Understat's first season (2014-15 = our season 2015)
MIN_MATCH = 0.98
PAUSE = 2.0


def current_year():
    """Understat labels a season by the year it starts (2026 = 2026-27)."""
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


def fetch(code, year, refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{code}_{year}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    req = urllib.request.Request(URL.format(code=code, year=year), headers={
        "X-Requested-With": "XMLHttpRequest", "Accept-Encoding": "gzip", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    data = json.loads(raw)
    if "dates" not in data:
        raise RuntimeError(f"Understat's answer for {code} {year} has no match list")
    path.write_text(json.dumps(data))
    time.sleep(PAUSE)
    return data


def finished(data):
    out = []
    for m in data["dates"]:
        if not m.get("isResult") or m.get("xG", {}).get("h") in (None, ""):
            continue
        d = date.fromisoformat(m["datetime"][:10])
        out.append({"h": m["h"]["title"], "a": m["a"]["title"], "gh": int(m["goals"]["h"]), "ga": int(m["goals"]["a"]),
                    "xh": float(m["xG"]["h"]), "xa": float(m["xG"]["a"]), "dates": {d.isoformat(), (d - timedelta(days=1)).isoformat()}})
    return out


def our_games(conn, league, season):
    return [dict(r) for r in conn.execute(
        "SELECT id, game_date_et, home_team, away_team, home_score, away_score FROM hist_games"
        " WHERE sport = 'soccer_club' AND league = ? AND season = ?", (league, season))]


def learn_names(conn, seasons_data):
    """{league: {Understat title: our name}} from games with the same date and score."""
    votes = defaultdict(Counter)
    for (league, season), data in seasons_data.items():
        ours = defaultdict(list)
        for g in our_games(conn, league, season):
            ours[(g["game_date_et"], g["home_score"], g["away_score"])].append(g)
        for m in finished(data):
            cands = [g for d in m["dates"] for g in ours.get((d, m["gh"], m["ga"]), [])]
            if len(cands) == 1:
                votes[(league, m["h"])][cands[0]["home_team"]] += 1
                votes[(league, m["a"])][cands[0]["away_team"]] += 1
    names = defaultdict(dict)
    for (league, title), c in votes.items():
        best, n = c.most_common(1)[0]
        if n >= 3 and n >= 0.8 * sum(c.values()):
            names[league][title] = best
    saved = json.loads(NAMES_PATH.read_text()) if NAMES_PATH.exists() else {}
    for league, m in names.items():
        saved.setdefault(league, {}).update({k: v for k, v in m.items() if k not in saved.get(league, {})})
    NAMES_PATH.write_text(json.dumps(saved, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return saved


def store(conn, league, season, data, names):
    """Match a league-season's games and write their xG. Returns (matched, finished, saved?)."""
    ours = {}
    for g in our_games(conn, league, season):
        ours[(g["game_date_et"], g["home_team"], g["away_team"])] = g
    latest = max((k[0] for k in ours), default="")
    rows, total = [], 0
    for m in finished(data):
        if min(m["dates"]) > latest:
            continue          # our history hasn't loaded this result yet (next run will match it)
        total += 1
        h, a = names.get(league, {}).get(m["h"]), names.get(league, {}).get(m["a"])
        g = next((ours[(d, h, a)] for d in sorted(m["dates"], reverse=True) if (d, h, a) in ours), None) if h and a else None
        if g and g["home_score"] == m["gh"] and g["away_score"] == m["ga"]:
            rows.append((round(m["xh"], 3), round(m["xa"], 3), g["id"]))
    ok = total > 0 and len(rows) / total >= MIN_MATCH
    if ok:
        with conn:
            conn.executemany("UPDATE hist_games SET home_xg = ?, away_xg = ? WHERE id = ?", rows)
    return len(rows), total, ok


def load(conn, years, refresh_current=False):
    data = {}
    for league, code in LEAGUES.items():
        for year in years:
            try:
                data[(league, year + 1)] = fetch(code, year, refresh=refresh_current and year == current_year())
            except Exception as e:
                sys.exit(f"STOP: Understat {code} {year} couldn't be read ({e}). Nothing written for it; re-run later.")
    names = learn_names(conn, data)
    problems = []
    for (league, season), d in sorted(data.items()):
        n, total, ok = store(conn, league, season, d, names)
        label = f"{season - 1}-{season % 100:02d}"
        print(f"  {league:<11} {label}: {n}/{total} games matched{'' if ok else '  NOT SAVED (under 98%)'}")
        if not ok and total:
            problems.append((league, label, n, total))
    unmapped = sorted({(lg, m["h"]) for (lg, s), d in data.items() for m in finished(d) if m["h"] not in names.get(lg, {})})
    if unmapped:
        print("Understat teams with no name match (their games stay without xG):", unmapped)
    if problems:
        print(f"{len(problems)} league-season(s) not saved; see above.")


def summary(conn):
    for r in conn.execute(
            "SELECT league, season, COUNT(*) n, SUM(home_xg IS NOT NULL) x FROM hist_games WHERE sport = 'soccer_club'"
            " AND league IN ('EPL', 'La Liga', 'Bundesliga', 'Serie A', 'Ligue 1') AND season >= 2015"
            " GROUP BY league, season ORDER BY league, season"):
        print(f"  {r['league']:<11} {r['season'] - 1}-{r['season'] % 100:02d}: {r['x']}/{r['n']} games with xG")


def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("history", "current", "summary"):
        sys.exit(__doc__)
    conn = db.connect()
    db.upgrade_db(conn)
    if a[0] == "summary":
        summary(conn)
    elif a[0] == "history":
        load(conn, range(FIRST_YEAR, current_year() + 1))
    else:
        load(conn, [current_year()], refresh_current=True)


if __name__ == "__main__":
    main()

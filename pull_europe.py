"""European club competitions (Champions League, Europa League, Conference League) from ESPN.

Usage:
  python3 pull_europe.py fetch [--refresh]   download games month by month into cache/espn_europe/
                                             (--refresh re-downloads the current season's months)
  python3 pull_europe.py teams               propose a match between each ESPN club and our club names
                                             (from the domestic history); writes soccer_europe_teams.json
                                             and prints the ones to review
  python3 pull_europe.py load                save finished games where both clubs are matched
  python3 pull_europe.py odds                Champions League moneylines (home/draw/away) from ESPN, 2019-20 on
  python3 pull_europe.py summary             what's loaded

Scores are the 90-minute score, which is how a three-way moneyline settles. Games that went to
extra time are rebuilt from ESPN's goal minutes (goals in minute 90 or its stoppage time count;
later goals and penalty shootouts don't); if those details are missing, the game is skipped.
A club from a league we have no history for is "uncovered": its games are skipped, never guessed.
Seasons are labeled by the year they end (2025 = 2024-25), like the domestic leagues.
"""

import difflib
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path

import db
from odds_math import is_pregame_sportsbook
from pull_basketball_history import espn_get
from pull_history import current_season, insert_game, insert_odds

COMPS = {"uefa.champions": "Champions League", "uefa.europa": "Europa League",
         "uefa.europa.conf": "Conference League"}
FIRST = {"uefa.champions": 2015, "uefa.europa": 2015, "uefa.europa.conf": 2022}   # first season (end year)
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={month}&limit=300"
ODDS = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/{slug}/events/{e}/competitions/{e}/odds"
CACHE = Path(__file__).parent / "cache" / "espn_europe"
TEAMS_PATH = Path(__file__).parent / "soccer_europe_teams.json"
SOURCE = "espn_soccer"
PAUSE = 0.15
AUTO_OK = 0.6           # name similarity needed to accept a match within the club's own country
TEAM_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/teams/{id}"
# ESPN league-slug country prefix -> our leagues in that country
COUNTRY_LEAGUES = {
    "eng": ("EPL", "Championship"), "esp": ("La Liga", "La Liga 2"), "ger": ("Bundesliga", "2. Bundesliga"),
    "ita": ("Serie A", "Serie B"), "fra": ("Ligue 1", "Ligue 2"), "por": ("Primeira Liga",), "ned": ("Eredivisie",),
    "bel": ("Belgian Pro League",), "sco": ("Scottish Premiership",), "tur": ("Super Lig",),
    "gre": ("Greek Super League",), "aut": ("Austrian Bundesliga",), "sui": ("Swiss Super League",),
    "den": ("Danish Superliga",), "nor": ("Eliteserien",), "swe": ("Allsvenskan",), "pol": ("Ekstraklasa",),
    "rou": ("Romanian Liga I",), "rus": ("Russian Premier League",)}


# ---------- fetch ----------

def months(season):
    """Year-month codes covering a season ending in `season` (July before through August after)."""
    out = []
    for y, m in [(season - 1, mm) for mm in range(7, 13)] + [(season, mm) for mm in range(1, 9)]:
        if date(y, m, 1) <= date.today():
            out.append(f"{y}{m:02d}")
    return out


def fetch(refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    cur = current_season("soccer_club")
    n, failed = 0, []
    for slug, first in FIRST.items():
        for season in range(first, cur + 1):
            for month in months(season):
                path = CACHE / f"{slug}_{month}.json"
                if path.exists() and not (refresh and season == cur):
                    continue
                try:
                    data = espn_get(SCOREBOARD.format(slug=slug, month=month)) or {"events": []}
                except RuntimeError:
                    failed.append(f"{slug} {month}")
                    continue
                path.write_text(json.dumps(data.get("events", [])))
                n += 1
                time.sleep(PAUSE)
    print(f"Downloaded {n} month files into {CACHE.relative_to(Path(__file__).parent)}.")
    if failed:
        print(f"ESPN refused {len(failed)} month(s) (re-run to fill them in): {', '.join(failed)}")


def events():
    """{event id: (competition slug, event)} for every cached European game, de-duplicated."""
    out = {}
    for path in sorted(CACHE.glob("uefa.*_*.json")):          # month files only (not teams.json)
        slug = path.name.rsplit("_", 1)[0]
        for e in json.loads(path.read_text()):
            out[e["id"]] = (slug, e)
    return out


def league_of(slug, e):
    """'Champions League', or 'Champions League qualifying' for qualifying/preliminary/playoff rounds
    (kept for learning league strength; never graded or predicted). ESPN's stage labels vary by
    season, so the rule is the date: main competitions never start before September 1 of the season's
    first year; anything earlier is qualifying. (The August 2020 COVID finals belong to 2019-20, so
    they fall after that date and count as main competition.)"""
    qualifying = e["date"][:10] < f"{season_of(e) - 1}-09-01"
    return COMPS[slug] + (" qualifying" if qualifying else "")


def season_of(e):
    """ESPN's season year is the year it starts (2024 = 2024-25); ours is the year it ends."""
    return int(e["season"]["year"]) + 1


# ---------- scores ----------

def minute(clock):
    """ "45'+2'" -> (45, 2); "96'" -> (96, 0)."""
    m = re.match(r"\s*(\d+)'?(?:\s*\+\s*(\d+))?", clock or "")
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (None, None)


def regulation_score(e):
    """(home goals, away goals) after 90 minutes plus stoppage time, or None if it can't be known."""
    comp = e["competitions"][0]
    teams = {t["homeAway"]: t for t in comp["competitors"]}
    status = e["status"]["type"]["name"]
    if status == "STATUS_FULL_TIME":
        return int(teams["home"]["score"]), int(teams["away"]["score"])
    if status not in ("STATUS_FINAL_AET", "STATUS_FINAL_PEN"):
        return None
    side_of = {teams["home"]["team"]["id"]: "home", teams["away"]["team"]["id"]: "away"}
    goals = {"home": 0, "away": 0}
    plays = [d for d in comp.get("details", []) if d.get("scoringPlay")]
    if not plays and (int(teams["home"]["score"]) or int(teams["away"]["score"])):
        return None                                      # goals but no details: can't split 90 vs extra time
    for d in plays:
        if d.get("shootout") or "Shootout" in (d.get("type", {}).get("text") or ""):
            continue
        base, _ = minute((d.get("clock") or {}).get("displayValue"))
        if base is None:
            return None
        if base == 120 and "Penalty" in (d.get("type", {}).get("text") or ""):
            continue                                     # ESPN files shootout kicks at 120'
        if base <= 90:
            side = side_of.get((d.get("team") or {}).get("id"))
            if side is None:
                return None
            goals[side] += 1
    # sanity: the 120-minute total can't be below the 90-minute count
    if goals["home"] > int(teams["home"]["score"]) or goals["away"] > int(teams["away"]["score"]):
        return None
    return goals["home"], goals["away"]


# ---------- club names ----------

DROP = {"fc", "cf", "sc", "ac", "afc", "sv", "fk", "sk", "as", "ss", "ssc", "rc", "cd", "ud", "rcd", "if", "ff",
        "bk", "kv", "krc", "rsc", "club", "de", "the", "calcio", "football", "futbol", "sporting", "united",
        "city", "1", "04", "05", "07", "09", "1899", "1846", "1848", "1900", "1913"}


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("'", ""))
    tokens = [t for t in s.split() if t not in DROP]
    return " ".join(tokens) or s.strip()


def domestic_clubs(conn):
    """{season: {club: league}} from the domestic history."""
    import soccer_model as sm
    out = {}
    for r in conn.execute("SELECT DISTINCT season, league, home_team FROM hist_games WHERE sport = 'soccer_club'"
                          f" AND league NOT IN ({','.join(repr(x) for x in sm.EUROPE)})"):
        out.setdefault(r["season"], {})[r["home_team"]] = r["league"]
    return out


def club_countries(club_ids):
    """{espn id: ESPN home-league slug (e.g. 'ita.1')}, cached in cache/espn_europe/teams.json."""
    path = CACHE / "teams.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    for tid in club_ids:
        if tid in known:
            continue
        try:
            d = espn_get(TEAM_URL.format(id=tid)) or {}
        except RuntimeError:
            continue                              # asked again next time
        known[tid] = ((d.get("team") or {}).get("defaultLeague") or {}).get("slug")
        time.sleep(PAUSE)
    path.write_text(json.dumps(known, indent=0))
    return known


def propose(conn):
    """Match every ESPN club in the cached games to one of our names. Keeps existing manual
    decisions in soccer_europe_teams.json; writes the file; returns (matched, review, uncovered)."""
    from teams import SOCCER_BY_ESPN_ID
    saved = json.loads(TEAMS_PATH.read_text()) if TEAMS_PATH.exists() else {}
    clubs = {}      # espn id -> {"name", "seasons"}
    for _, e in events().values():
        for t in e["competitions"][0]["competitors"]:
            c = clubs.setdefault(t["team"]["id"], {"name": t["team"]["displayName"], "seasons": set()})
            c["seasons"].add(season_of(e))
    dom = domestic_clubs(conn)
    league_slug = club_countries(clubs)
    out = {}
    for tid, c in sorted(clubs.items(), key=lambda x: x[1]["name"]):
        if tid in saved and saved[tid].get("how") == "manual":
            out[tid] = saved[tid]
            continue
        if tid in SOCCER_BY_ESPN_ID:                     # this season's Big 5 clubs: already checked by hand
            out[tid] = {"espn_name": c["name"], "ours": SOCCER_BY_ESPN_ID[tid][1], "how": "big5 map", "score": 1.0}
            continue
        slug = league_slug.get(tid) or ""
        leagues = COUNTRY_LEAGUES.get(slug.split(".")[0])
        if not leagues:
            out[tid] = {"espn_name": c["name"], "ours": None, "how": "uncovered", "espn_league": slug or None}
            continue
        cands = {}
        for s in c["seasons"]:
            for yr in (s - 1, s, s + 1):
                cands.update({club: lg for club, lg in dom.get(yr, {}).items() if lg in leagues})
        best, score = None, 0.0
        n = norm(c["name"])
        for club in cands:
            r = difflib.SequenceMatcher(None, n, norm(club)).ratio()
            if norm(club) in n.split() or n in norm(club).split():
                r = max(r, 0.9)
            if r > score:
                best, score = club, r
        out[tid] = {"espn_name": c["name"], "ours": best if score >= AUTO_OK else None,
                    "proposed": best, "league": cands.get(best), "espn_league": slug,
                    "how": "auto" if score >= AUTO_OK else "review", "score": round(score, 3)}
    TEAMS_PATH.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return out


# ---------- load ----------

VENUE_DROP = {"estadio", "stadium", "stade", "stadio", "stadion", "santiago", "the", "de", "do", "da", "del"}


def venue_key(e):
    """A stadium's simplified name: ESPN gives one stadium several ids and spellings
    ("Estadio Bernabeu" / "Santiago Bernabeu", "SIGNAL IDUNA PARK" / "Signal Iduna Park")."""
    name = (e["competitions"][0].get("venue") or {}).get("fullName")
    if not name:
        return None
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(t for t in re.sub(r"[^a-z0-9 ]", " ", s).split() if t not in VENUE_DROP) or s


def same_venue(a, b):
    """Equal simplified names, or the shorter one (2+ words) contained in the longer:
    'bollaert delelis' / 'felix bollaert delelis', 'raiffeisen arena' / 'raiffeisen arena linz'."""
    if not a or not b:
        return False
    if a == b:
        return True
    x, y = sorted((set(a.split()), set(b.split())), key=len)
    return len(x) >= 2 and x <= y


def usual_home_venues(evs):
    """{(club id, season): venues where it hosted 2+ European games that season} plus
    {(club id, None): the venue where it hosted the most European games over all seasons}."""
    from collections import Counter
    season_counts, career = {}, {}
    for _, e in evs.values():
        home = next(t for t in e["competitions"][0]["competitors"] if t["homeAway"] == "home")["team"]["id"]
        if venue_key(e):
            season_counts.setdefault((home, season_of(e)), Counter())[venue_key(e)] += 1
            career.setdefault(home, Counter())[venue_key(e)] += 1
    out = {k: {v for v, n in c.items() if n >= 2} for k, c in season_counts.items()}
    out.update({(club, None): c.most_common(1)[0][0] for club, c in career.items()})
    for (club, _), venues in list(out.items()):
        if isinstance(venues, set):
            out.setdefault((club, "any"), set()).update(venues)
    return out


def is_neutral(e, usual):
    """ESPN doesn't flag neutral venues. A game is neutral if the home club never hosted 2+ European
    games at that venue in one season and it isn't the club's usual European home over all seasons:
    finals, the 2020 Lisbon/Germany tournaments, 2021's relocated games. Mid-season moves (Tottenham
    2019, Barcelona at Montjuic 2025) stay home games."""
    if e["competitions"][0].get("neutralSite"):
        return True
    home = next(t for t in e["competitions"][0]["competitors"] if t["homeAway"] == "home")["team"]["id"]
    v = venue_key(e)
    if not v:
        return False
    known = usual.get((home, season_of(e)), set()) | usual.get((home, "any"), set()) | {usual.get((home, None))}
    return not any(same_venue(v, k) for k in known)

def load(conn):
    mapping = json.loads(TEAMS_PATH.read_text())
    added = skipped_unmapped = skipped_score = skipped_unfinished = 0
    evs = events()
    usual = usual_home_venues(evs)
    for eid, (slug, e) in evs.items():                   # neutral flags for games already loaded
        conn.execute("UPDATE hist_games SET neutral_site = ? WHERE source = ? AND external_id = ?",
                     (int(is_neutral(e, usual)), SOURCE, eid))
    for eid, (slug, e) in sorted(evs.items(), key=lambda x: x[1][1]["date"]):
        if not e["status"]["type"].get("completed"):
            skipped_unfinished += 1
            continue
        comp = e["competitions"][0]
        teams = {t["homeAway"]: t for t in comp["competitors"]}
        names = {side: (mapping.get(teams[side]["team"]["id"]) or {}).get("ours") for side in ("home", "away")}
        if None in names.values():
            skipped_unmapped += 1
            continue
        score = regulation_score(e)
        if score is None:
            skipped_score += 1
            continue
        kickoff = datetime.strptime(e["date"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
        et = kickoff.astimezone(db.EASTERN)
        try:
            insert_game(conn, sport="soccer_club", league=league_of(slug, e), season=season_of(e), week=None,
                        season_type="regular", game_date_et=et.strftime("%Y-%m-%d"),
                        kickoff_et=et.strftime("%Y-%m-%d %H:%M"), kickoff_utc=db.to_utc(kickoff),
                        home_team=names["home"], away_team=names["away"], home_score=score[0], away_score=score[1],
                        neutral_site=int(is_neutral(e, usual)), source=SOURCE, external_id=eid)
            added += 1
        except Exception as err:
            if "UNIQUE" not in str(err):
                raise
    conn.commit()
    print(f"European games: {added} added | skipped: {skipped_unmapped} with an uncovered club, "
          f"{skipped_score} extra-time games without goal details, {skipped_unfinished} not finished.")


def odds(conn):
    """Champions League moneylines from ESPN for loaded games, 2019-20 on (one request per game).
    Only real sportsbooks' pregame prices; a game with none gets no row (asked again next time)."""
    todo = conn.execute(
        "SELECT g.id, g.external_id FROM hist_games g WHERE g.sport = 'soccer_club' AND g.league = 'Champions League'"
        " AND g.season >= 2020 AND NOT EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id)"
        " ORDER BY g.game_date_et").fetchall()
    print(f"Champions League odds: {len(todo)} games to check.", flush=True)
    with_ml = rows = 0
    for g in todo:
        data = espn_get(ODDS.format(slug="uefa.champions", e=g["external_id"])) or {}
        books = {}
        for item in data.get("items", []):
            name = (item.get("provider") or {}).get("name") or "unknown"
            h, a, d = item.get("homeTeamOdds") or {}, item.get("awayTeamOdds") or {}, item.get("drawOdds") or {}
            hm, am, dm = h.get("moneyLine"), a.get("moneyLine"), d.get("moneyLine")
            if "(" in name or not is_pregame_sportsbook(name) or None in (hm, am, dm):
                continue
            if min(abs(hm), abs(am), abs(dm)) < 100:
                continue
            books[name] = (int(hm), int(dm), int(am))
        for name, (hm, dm, am) in books.items():
            insert_odds(conn, hist_game_id=g["id"], provider=name, timing="unknown",
                        home_ml=hm, draw_ml=dm, away_ml=am, source="espn")
            rows += 1
        with_ml += bool(books)
        time.sleep(PAUSE)
    conn.commit()
    print(f"Saved {rows} prices for {with_ml} of {len(todo)} games.")


def summary(conn):
    for r in conn.execute(
            "SELECT g.league, g.season, COUNT(*) n, SUM(EXISTS (SELECT 1 FROM hist_odds o WHERE o.hist_game_id = g.id)) odds"
            " FROM hist_games g WHERE g.sport = 'soccer_club' AND (g.league LIKE '%League' OR g.league LIKE '%qualifying')"
            " AND g.league IN ('Champions League', 'Europa League', 'Conference League', 'Champions League qualifying',"
            " 'Europa League qualifying', 'Conference League qualifying') GROUP BY 1, 2 ORDER BY 1, 2"):
        print(f"{r['league']:<20}{r['season'] - 1}-{r['season'] % 100:02d}{r['n']:>6} games{r['odds']:>6} with odds")


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("fetch", "teams", "load", "odds", "summary"):
        sys.exit(__doc__)
    if args[0] == "fetch":
        fetch(refresh="--refresh" in args)
        return
    conn = db.connect()
    if args[0] == "teams":
        out = propose(conn)
        review = [v for v in out.values() if v["how"] == "review"]
        auto = [v for v in out.values() if v["how"] == "auto"]
        print(f"{len(out)} clubs: {sum(v['how'] in ('auto', 'big5 map', 'manual') for v in out.values())} matched, "
              f"{sum(v['how'] == 'uncovered' for v in out.values())} from countries we don't cover, "
              f"{len(review)} to review (written to {TEAMS_PATH.name}).")
        print("\nAutomatic matches (check these):")
        for v in sorted(auto, key=lambda v: v["score"]):
            print(f"  {v['score']:.2f}  {v['espn_name']:<30} -> {v['ours']} ({v['league']})")
        print("\nTo review (no confident match in the club's country):")
        for v in sorted(review, key=lambda v: -v["score"]):
            print(f"  {v['espn_name']:<32} best guess: {v['proposed']} ({v['league']}, {v['score']}) [ESPN {v['espn_league']}]")
    elif args[0] == "load":
        load(conn)
    elif args[0] == "odds":
        odds(conn)
    else:
        summary(conn)


if __name__ == "__main__":
    main()

"""Translate The Odds API's team names into the names our games table uses.

NFL: a fixed list (nflverse uses abbreviations).
College: built from CFBD's team list as "school + mascot", plus a few manual
fixes in COLLEGE_OVERRIDES. A name that can't be matched returns None; the
caller must report it, never guess.
"""

import json
import re
import unicodedata
import urllib.request

import config

NFL = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Los Angeles Rams": "LA", "Los Angeles Chargers": "LAC",
    "Las Vegas Raiders": "LV", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "Seattle Seahawks": "SEA", "San Francisco 49ers": "SF", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}

# Odds API name -> CFBD school, for names the automatic rule can't work out.
COLLEGE_OVERRIDES = {
    "Citadel Bulldogs": "The Citadel",
}


def normalize(name):
    """Lowercase, strip accents and punctuation: "San José State" -> "san jose state"."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-z0-9& ()]", "", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def load_college_names():
    """Return {normalized Odds-API-style name: CFBD school} for every CFBD team."""
    req = urllib.request.Request("https://api.collegefootballdata.com/teams",
                                 headers={"Authorization": f"Bearer {config.CFBD_API_KEY}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        teams = json.load(resp)
    names, ambiguous = {}, set()
    for t in teams:
        mascot = t.get("mascot") or ""
        for school_name in {t["school"], *(t.get("alternateNames") or [])}:
            key = normalize(f"{school_name} {mascot}")
            if key in names and names[key] != t["school"]:
                ambiguous.add(key)
            names[key] = t["school"]
    for key in ambiguous:
        del names[key]  # two schools claim this name: refuse to guess
    for odds_name, school in COLLEGE_OVERRIDES.items():
        names[normalize(odds_name)] = school
    return names


class TeamNames:
    def __init__(self, sport):
        self.sport = sport
        self.college = (load_college_names() if sport == "ncaaf"
                        else load_ncaab_names() if sport == "ncaab" else None)

    def lookup(self, odds_api_name):
        if self.sport == "nfl":
            return NFL.get(odds_api_name)
        if self.sport == "nba":
            return NBA.get(odds_api_name)
        return self.college.get(normalize(odds_api_name))


# Each NFL team's home time zone, as hours behind UTC in standard time.
# Uses the abbreviation of the era (STL was Central, SD and OAK Pacific).
NFL_HOME_TZ = {
    **{t: -5 for t in ("ATL", "BAL", "BUF", "CAR", "CIN", "CLE", "DET", "IND", "JAX",
                       "MIA", "NE", "NYG", "NYJ", "PHI", "PIT", "TB", "WAS")},
    **{t: -6 for t in ("CHI", "DAL", "GB", "HOU", "KC", "MIN", "NO", "TEN", "STL")},
    **{t: -7 for t in ("DEN", "ARI")},
    **{t: -8 for t in ("LA", "LAC", "LV", "SEA", "SF", "SD", "OAK")},
}


# ESPN's logo codes for NFL teams, where they differ from ours (others: lowercase).
NFL_ESPN_CODE = {"LA": "lar", "WAS": "wsh"}


def nfl_logo_url(team):
    code = NFL_ESPN_CODE.get(team, team.lower())
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nfl/500/{code}.png&h=64&w=64"



# NBA: Odds API name -> ESPN code (as stored in the games and history tables)
NBA = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GS", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NO", "New York Knicks": "NY",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SA", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTAH", "Washington Wizards": "WSH",
}

# College basketball: Odds API name -> CBBD school, for names the automatic rule can't work out.
NCAAB_OVERRIDES = {}


def cbbd_teams():
    """CBBD's team list, cached for a week in cache/cbbd_teams.json (1 CBBD call to refresh)."""
    import time
    from pathlib import Path
    cache = Path(__file__).parent / "cache" / "cbbd_teams.json"
    if not cache.exists() or time.time() - cache.stat().st_mtime > 7 * 86400:
        try:
            req = urllib.request.Request("https://api.collegebasketballdata.com/teams",
                                         headers={"Authorization": f"Bearer {config.CFBD_API_KEY}"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            cache.parent.mkdir(exist_ok=True)
            cache.write_text(json.dumps(data))
        except Exception:
            if not cache.exists():
                raise
    return json.loads(cache.read_text())


def load_ncaab_names():
    names, ambiguous = {}, set()
    for t in cbbd_teams():
        for full in {t.get("displayName") or "", f"{t['school']} {t.get('mascot') or ''}"}:
            key = normalize(full)
            if not key:
                continue
            if key in names and names[key] != t["school"]:
                ambiguous.add(key)
            names[key] = t["school"]
    for key in ambiguous:
        del names[key]
    for odds_name, school in NCAAB_OVERRIDES.items():
        names[normalize(odds_name)] = school
    return names


def nba_logo_url(team):
    return f"https://a.espncdn.com/combiner/i?img=/i/teamlogos/nba/500/{team.lower()}.png&h=64&w=64"

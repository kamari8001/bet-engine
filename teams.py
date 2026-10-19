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
        if self.sport == "soccer_club":
            return SOCCER_BY_ODDS_NAME.get(odds_api_name)
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

# ---------- club soccer ----------
# Our team names are football-data.co.uk's (the history source). Each league:
# football-data file code, its second division's code (history only, for promoted teams),
# ESPN league slug, and The Odds API sport key.
SOCCER_LEAGUES = {
    "EPL": ("E0", "E1", "eng.1", "soccer_epl"),
    "La Liga": ("SP1", "SP2", "esp.1", "soccer_spain_la_liga"),
    "Bundesliga": ("D1", "D2", "ger.1", "soccer_germany_bundesliga"),
    "Serie A": ("I1", "I2", "ita.1", "soccer_italy_serie_a"),
    "Ligue 1": ("F1", "F2", "fra.1", "soccer_france_ligue_one"),
}

# This season's teams: our name -> (ESPN team id, ESPN name, Odds API name). Checked 2026-10-19
# against all three sources' 2026-27 team lists (one-to-one). Promoted teams must be added each
# summer; an unknown name stops the run instead of guessing.
SOCCER_TEAMS = {
    "EPL": {
        'Arsenal': ('359', 'Arsenal', 'Arsenal'),
        'Aston Villa': ('362', 'Aston Villa', 'Aston Villa'),
        'Bournemouth': ('349', 'AFC Bournemouth', 'Bournemouth'),
        'Brentford': ('337', 'Brentford', 'Brentford'),
        'Brighton': ('331', 'Brighton & Hove Albion', 'Brighton and Hove Albion'),
        'Chelsea': ('363', 'Chelsea', 'Chelsea'),
        'Coventry': ('388', 'Coventry City', 'Coventry City'),
        'Crystal Palace': ('384', 'Crystal Palace', 'Crystal Palace'),
        'Everton': ('368', 'Everton', 'Everton'),
        'Fulham': ('370', 'Fulham', 'Fulham'),
        'Hull': ('306', 'Hull City', 'Hull City'),
        'Ipswich': ('373', 'Ipswich Town', 'Ipswich Town'),
        'Leeds': ('357', 'Leeds United', 'Leeds United'),
        'Liverpool': ('364', 'Liverpool', 'Liverpool'),
        'Man City': ('382', 'Manchester City', 'Manchester City'),
        'Man United': ('360', 'Manchester United', 'Manchester United'),
        'Newcastle': ('361', 'Newcastle United', 'Newcastle United'),
        "Nott'm Forest": ('393', 'Nottingham Forest', 'Nottingham Forest'),
        'Sunderland': ('366', 'Sunderland', 'Sunderland'),
        'Tottenham': ('367', 'Tottenham Hotspur', 'Tottenham Hotspur'),
    },
    "La Liga": {
        'Alaves': ('96', 'Alavés', 'Alavés'),
        'Ath Bilbao': ('93', 'Athletic Club', 'Athletic Bilbao'),
        'Ath Madrid': ('1068', 'Atlético Madrid', 'Atlético Madrid'),
        'Barcelona': ('83', 'Barcelona', 'Barcelona'),
        'Betis': ('244', 'Real Betis', 'Real Betis'),
        'Celta': ('85', 'Celta Vigo', 'Celta Vigo'),
        'Elche': ('3751', 'Elche', 'Elche CF'),
        'Espanol': ('88', 'Espanyol', 'Espanyol'),
        'Getafe': ('2922', 'Getafe', 'Getafe'),
        'La Coruna': ('90', 'Deportivo', 'Deportivo La Coruña'),
        'Levante': ('1538', 'Levante', 'Levante'),
        'Malaga': ('99', 'Málaga', 'Málaga'),
        'Osasuna': ('97', 'Osasuna', 'CA Osasuna'),
        'Real Madrid': ('86', 'Real Madrid', 'Real Madrid'),
        'Santander': ('87', 'Racing Santander', 'Real Racing Club de Santander'),
        'Sevilla': ('243', 'Sevilla', 'Sevilla'),
        'Sociedad': ('89', 'Real Sociedad', 'Real Sociedad'),
        'Valencia': ('94', 'Valencia', 'Valencia'),
        'Vallecano': ('101', 'Rayo Vallecano', 'Rayo Vallecano'),
        'Villarreal': ('102', 'Villarreal', 'Villarreal'),
    },
    "Bundesliga": {
        'Augsburg': ('3841', 'FC Augsburg', 'Augsburg'),
        'Bayern Munich': ('132', 'Bayern Munich', 'Bayern Munich'),
        'Dortmund': ('124', 'Borussia Dortmund', 'Borussia Dortmund'),
        'Ein Frankfurt': ('125', 'Eintracht Frankfurt', 'Eintracht Frankfurt'),
        'Elversberg': ('10388', 'SV Elversberg', 'Elversberg'),
        'FC Koln': ('122', 'FC Cologne', '1. FC Köln'),
        'Freiburg': ('126', 'SC Freiburg', 'SC Freiburg'),
        'Hamburg': ('127', 'Hamburg SV', 'Hamburger SV'),
        'Hoffenheim': ('7911', 'TSG Hoffenheim', 'TSG Hoffenheim'),
        'Leverkusen': ('131', 'Bayer Leverkusen', 'Bayer Leverkusen'),
        "M'gladbach": ('268', 'Borussia Mönchengladbach', 'Borussia Monchengladbach'),
        'Mainz': ('2950', 'Mainz', 'FSV Mainz 05'),
        'Paderborn': ('3307', 'SC Paderborn 07', 'SC Paderborn'),
        'RB Leipzig': ('11420', 'RB Leipzig', 'RB Leipzig'),
        'Schalke 04': ('133', 'Schalke 04', 'FC Schalke 04'),
        'Stuttgart': ('134', 'VfB Stuttgart', 'VfB Stuttgart'),
        'Union Berlin': ('598', '1. FC Union Berlin', 'Union Berlin'),
        'Werder Bremen': ('137', 'Werder Bremen', 'Werder Bremen'),
    },
    "Serie A": {
        'Atalanta': ('105', 'Atalanta', 'Atalanta BC'),
        'Bologna': ('107', 'Bologna', 'Bologna'),
        'Cagliari': ('2925', 'Cagliari', 'Cagliari'),
        'Como': ('2572', 'Como', 'Como'),
        'Fiorentina': ('109', 'Fiorentina', 'Fiorentina'),
        'Frosinone': ('4057', 'Frosinone', 'Frosinone'),
        'Genoa': ('3263', 'Genoa', 'Genoa'),
        'Inter': ('110', 'Internazionale', 'Inter Milan'),
        'Juventus': ('111', 'Juventus', 'Juventus'),
        'Lazio': ('112', 'Lazio', 'Lazio'),
        'Lecce': ('113', 'Lecce', 'Lecce'),
        'Milan': ('103', 'AC Milan', 'AC Milan'),
        'Monza': ('4007', 'Monza', 'Monza'),
        'Napoli': ('114', 'Napoli', 'Napoli'),
        'Parma': ('115', 'Parma', 'Parma'),
        'Roma': ('104', 'AS Roma', 'AS Roma'),
        'Sassuolo': ('3997', 'Sassuolo', 'Sassuolo'),
        'Torino': ('239', 'Torino', 'Torino'),
        'Udinese': ('118', 'Udinese', 'Udinese'),
        'Venezia': ('17530', 'Venezia', 'Venezia'),
    },
    "Ligue 1": {
        'Angers': ('7868', 'Angers', 'Angers'),
        'Auxerre': ('172', 'AJ Auxerre', 'Auxerre'),
        'Brest': ('6997', 'Brest', 'Brest'),
        'Le Havre': ('3236', 'Le Havre AC', 'Le Havre'),
        'Le Mans': ('2697', 'Le Mans', 'Le Mans FC'),
        'Lens': ('175', 'Lens', 'RC Lens'),
        'Lille': ('166', 'Lille', 'Lille'),
        'Lorient': ('273', 'Lorient', 'Lorient'),
        'Lyon': ('167', 'Lyon', 'Lyon'),
        'Marseille': ('176', 'Marseille', 'Marseille'),
        'Monaco': ('174', 'AS Monaco', 'AS Monaco'),
        'Nice': ('2502', 'Nice', 'Nice'),
        'Paris FC': ('6851', 'Paris FC', 'Paris FC'),
        'Paris SG': ('160', 'Paris Saint-Germain', 'Paris Saint Germain'),
        'Rennes': ('169', 'Stade Rennais', 'Rennes'),
        'Strasbourg': ('180', 'Strasbourg', 'Strasbourg'),
        'Toulouse': ('179', 'Toulouse', 'Toulouse'),
        'Troyes': ('170', 'Troyes', 'Troyes'),
    },
}
SOCCER_BY_ESPN_ID = {e: (lg, ours) for lg, teams in SOCCER_TEAMS.items() for ours, (e, _, _) in teams.items()}
SOCCER_BY_ODDS_NAME = {o: ours for teams in SOCCER_TEAMS.values() for ours, (_, _, o) in teams.items()}
assert len(SOCCER_BY_ODDS_NAME) == sum(map(len, SOCCER_TEAMS.values())), "Odds API names must be unique"


def soccer_logo_url(team):
    for teams in SOCCER_TEAMS.values():
        if team in teams:
            return f"https://a.espncdn.com/i/teamlogos/soccer/500/{teams[team][0]}.png"
    return None

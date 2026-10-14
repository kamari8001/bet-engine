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
        self.college = load_college_names() if sport == "ncaaf" else None

    def lookup(self, odds_api_name):
        if self.sport == "nfl":
            return NFL.get(odds_api_name)
        return self.college.get(normalize(odds_api_name))

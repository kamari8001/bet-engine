"""Settings for the bet engine. Change numbers here, not inside other scripts."""

import os
from pathlib import Path

# The single SQLite database file, kept in this folder. BET_ENGINE_DB can point
# scripts at a throwaway copy for testing.
DB_PATH = Path(os.environ.get("BET_ENGINE_DB") or Path(__file__).parent / "bet_engine.db")

# A game is flagged as a bet when engine probability minus no-vig market
# probability is at least this much. 0.04 = 4 percentage points.
EDGE_THRESHOLD = 0.04

# The most Claude's news adjustments may move any one outcome's probability
# for a game, in total. 0.03 = 3 percentage points.
# This is written into the database rules when the database is created, so
# changing it later also requires updating the database.
MAX_ADJUSTMENT = 0.03


def _load_env(path=Path(__file__).parent / ".env"):
    """Read KEY=value lines from .env. Keys stay out of the code and out of git."""
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


_env = _load_env()
CFBD_API_KEY = _env.get("CFBD_API_KEY", "")
ODDS_API_KEY = _env.get("ODDS_API_KEY", "")

# Odds API bookmakers pulled each run. Up to 10 cost 1 credit per sport.
# All of them feed the no-vig market probability; MY_BOOKS are where you bet.
ODDS_BOOKMAKERS = ["fanduel", "draftkings", "polymarket", "polymarket_us", "betmgm",
                   "betus", "betrivers", "bovada", "lowvig", "betonlineag"]
MY_BOOKS = ["FanDuel", "DraftKings", "Polymarket", "Polymarket (US)"]

# Soccer power rankings across leagues (display only; never used in predictions):
# a league's strength shift, in log-goals, = this x ln(its UEFA coefficient / the Big 5 average),
# split between attack and defense. 0.5: a league 20% above average gets ~10% more goals for and
# ~10% fewer against. An assumption, not measured from our data; adjust if the rankings look off.
SOCCER_LEAGUE_STRENGTH = 0.5

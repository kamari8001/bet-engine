"""Settings for the bet engine. Change numbers here, not inside other scripts."""

from pathlib import Path

# The single SQLite database file, kept in this folder.
DB_PATH = Path(__file__).parent / "bet_engine.db"

# A game is flagged as a bet when engine probability minus no-vig market
# probability is at least this much. 0.04 = 4 percentage points.
EDGE_THRESHOLD = 0.04

# The most Claude's news adjustments may move any one outcome's probability
# for a game, in total. 0.03 = 3 percentage points.
# This is written into the database rules when the database is created, so
# changing it later also requires updating the database.
MAX_ADJUSTMENT = 0.03

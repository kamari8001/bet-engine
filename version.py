"""The app's name and version. See CHANGELOG.md for what each version changed.

Versioning (MAJOR.MINOR.PATCH):
  MAJOR  anything that changes the probabilities: a new model version or a new sport
  MINOR  new features (a new tab, a new tool)
  PATCH  fixes and polish
Bump APP_VERSION, add a CHANGELOG.md entry, and tag the commit (git tag vX.Y.Z).
Model versions (e.g. nfl-v2-refit-20261015) live in model_params.json and are
recorded on every prediction.
"""

import json
from pathlib import Path

APP_NAME = "Kamari's Prediction Engine"
APP_VERSION = "4.2.0"


def model_versions():
    """{'nfl': 'nfl-v2-refit-20261015', 'ncaaf': ...} from model_params.json."""
    try:
        saved = json.loads((Path(__file__).parent / "model_params.json").read_text())
        return {sport: p["version"] for sport, p in saved.items()}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}

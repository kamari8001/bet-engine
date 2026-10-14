"""Database helpers: create the database and save rows to it.

Run `python3 db.py` to create bet_engine.db (safe to re-run; it won't
overwrite an existing database).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import config

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(path=config.DB_PATH):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path=config.DB_PATH):
    """Create the tables and rules. Refuses if the database already exists."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} already exists; not touching it")
    schema = SCHEMA_PATH.read_text().replace("{{MAX_ADJ}}", repr(config.MAX_ADJUSTMENT))
    conn = connect(path)
    conn.executescript(schema)
    conn.commit()
    return conn


def to_utc(dt):
    """Turn a timezone-aware datetime into the UTC text format the database uses."""
    if dt.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _insert(conn, table, **values):
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))
    conn.commit()
    return cur.lastrowid


def add_game(conn, sport, league, season, home_team, away_team, start_time,
             source, external_id=None, neutral_site=False):
    return _insert(conn, "games", sport=sport, league=league, season=season,
                   home_team=home_team, away_team=away_team,
                   start_time_utc=to_utc(start_time), neutral_site=int(neutral_site),
                   source=source, external_id=external_id)


def add_odds(conn, game_id, bookmaker, home_ml, away_ml, source, draw_ml=None):
    return _insert(conn, "odds", game_id=game_id, bookmaker=bookmaker,
                   home_ml=home_ml, draw_ml=draw_ml, away_ml=away_ml, source=source)


def add_prediction(conn, game_id, source, p_home, p_away, p_draw=None,
                   proj_home_score=None, proj_away_score=None, odds_id=None,
                   model_version=None, corrects_id=None, note=None):
    return _insert(conn, "predictions", game_id=game_id, source=source,
                   p_home=p_home, p_draw=p_draw, p_away=p_away,
                   proj_home_score=proj_home_score, proj_away_score=proj_away_score,
                   odds_id=odds_id, model_version=model_version,
                   corrects_id=corrects_id, note=note)


def add_adjustment(conn, game_id, base_prediction_id, d_home, d_away, reason,
                   source_url, d_draw=None):
    return _insert(conn, "adjustments", game_id=game_id,
                   base_prediction_id=base_prediction_id, d_home=d_home,
                   d_draw=d_draw, d_away=d_away, reason=reason, source_url=source_url)


def add_result(conn, game_id, status, source, home_score=None, away_score=None):
    return _insert(conn, "results", game_id=game_id, status=status, source=source,
                   home_score=home_score, away_score=away_score)


def lock_started_games(conn):
    """Set the locked flag on every prediction whose game has started."""
    cur = conn.execute(
        "UPDATE predictions SET locked = 1 WHERE locked = 0 AND game_id IN "
        "(SELECT id FROM games WHERE start_time_utc <= datetime('now'))")
    conn.commit()
    return cur.rowcount


if __name__ == "__main__":
    conn = init_db()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    triggers = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger'").fetchone()[0]
    print(f"Created {config.DB_PATH.name}")
    print(f"Tables: {', '.join(tables)}")
    print(f"Protection rules (triggers): {triggers}")

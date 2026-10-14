-- Bet Engine database blueprint.
--
-- All times are UTC, stored as text in the form 'YYYY-MM-DD HH:MM:SS'
-- (the same form SQLite's datetime('now') uses, so times compare correctly).
--
-- {{MAX_ADJ}} is replaced with config.MAX_ADJUSTMENT by db.py when the
-- database is created.
--
-- Soccer sports ('soccer_club', 'soccer_intl') are three-way: they must have
-- draw values. All other sports must leave draw values empty.


------------------------------------------------------------------------
-- games: one row per game.
------------------------------------------------------------------------
CREATE TABLE games (
    id              INTEGER PRIMARY KEY,
    sport           TEXT NOT NULL CHECK (sport IN
                        ('nfl', 'ncaaf', 'nba', 'ncaab', 'mlb',
                         'soccer_club', 'soccer_intl')),
    league          TEXT NOT NULL,
    season          TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    start_time_utc  TEXT NOT NULL CHECK (start_time_utc GLOB
                        '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9] [0-2][0-9]:[0-5][0-9]:[0-5][0-9]'),
    neutral_site    INTEGER NOT NULL DEFAULT 0 CHECK (neutral_site IN (0, 1)),
    source          TEXT NOT NULL,          -- where the game data came from
    external_id     TEXT,                   -- that source's id for the game
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (home_team <> away_team),
    UNIQUE (source, external_id)
);

-- Kickoff time can't change once the original kickoff has passed, and can't
-- be moved earlier than a prediction that was already logged.
CREATE TRIGGER games_no_kickoff_change_after_start
BEFORE UPDATE OF start_time_utc ON games
WHEN NEW.start_time_utc IS NOT OLD.start_time_utc
 AND (OLD.start_time_utc <= datetime('now')
      OR NEW.start_time_utc <= (SELECT MAX(created_at) FROM predictions
                                WHERE game_id = OLD.id))
BEGIN
    SELECT RAISE(ABORT, 'kickoff time cannot change after the game started or before existing predictions');
END;

-- Once a game has predictions, its sport and teams are fixed.
CREATE TRIGGER games_no_identity_change_after_predictions
BEFORE UPDATE ON games
WHEN EXISTS (SELECT 1 FROM predictions WHERE game_id = OLD.id)
 AND (NEW.sport IS NOT OLD.sport OR NEW.home_team IS NOT OLD.home_team
      OR NEW.away_team IS NOT OLD.away_team
      OR NEW.neutral_site IS NOT OLD.neutral_site)
BEGIN
    SELECT RAISE(ABORT, 'game details cannot change once predictions exist');
END;

CREATE TRIGGER games_no_delete_with_history
BEFORE DELETE ON games
WHEN EXISTS (SELECT 1 FROM odds WHERE game_id = OLD.id)
  OR EXISTS (SELECT 1 FROM predictions WHERE game_id = OLD.id)
  OR EXISTS (SELECT 1 FROM results WHERE game_id = OLD.id)
BEGIN
    SELECT RAISE(ABORT, 'games with odds, predictions or results cannot be deleted');
END;


------------------------------------------------------------------------
-- odds: every moneyline we see, with when we saw it. Add-only.
-- American odds: +150 means win $150 on $100; -150 means risk $150 to win $100.
------------------------------------------------------------------------
CREATE TABLE odds (
    id           INTEGER PRIMARY KEY,
    game_id      INTEGER NOT NULL REFERENCES games(id),
    bookmaker    TEXT NOT NULL,
    captured_at  TEXT NOT NULL DEFAULT (datetime('now')),
    home_ml      INTEGER NOT NULL CHECK (home_ml >= 100 OR home_ml <= -100),
    draw_ml      INTEGER CHECK (draw_ml IS NULL OR draw_ml >= 100 OR draw_ml <= -100),
    away_ml      INTEGER NOT NULL CHECK (away_ml >= 100 OR away_ml <= -100),
    source       TEXT NOT NULL
);

CREATE TRIGGER odds_must_be_current
BEFORE INSERT ON odds
WHEN abs(julianday(NEW.captured_at) - julianday('now')) * 86400 > 5
BEGIN
    SELECT RAISE(ABORT, 'odds must be stamped with the current time');
END;

CREATE TRIGGER odds_pregame_only
BEFORE INSERT ON odds
WHEN datetime('now') >= (SELECT start_time_utc FROM games WHERE id = NEW.game_id)
BEGIN
    SELECT RAISE(ABORT, 'odds can only be saved before kickoff');
END;

CREATE TRIGGER odds_draw_matches_sport
BEFORE INSERT ON odds
WHEN ((SELECT sport FROM games WHERE id = NEW.game_id) LIKE 'soccer%')
     <> (NEW.draw_ml IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'draw odds are required for soccer and not allowed otherwise');
END;

CREATE TRIGGER odds_no_update BEFORE UPDATE ON odds
BEGIN SELECT RAISE(ABORT, 'odds rows can never be changed'); END;

CREATE TRIGGER odds_no_delete BEFORE DELETE ON odds
BEGIN SELECT RAISE(ABORT, 'odds rows can never be deleted'); END;

-- Closing line: the last price saved before kickoff, per game and bookmaker.
CREATE VIEW closing_odds AS
SELECT o.*
FROM odds o
JOIN games g ON g.id = o.game_id
WHERE o.captured_at < g.start_time_utc
  AND o.id = (SELECT o2.id FROM odds o2
              WHERE o2.game_id = o.game_id AND o2.bookmaker = o.bookmaker
                AND o2.captured_at < g.start_time_utc
              ORDER BY o2.captured_at DESC, o2.id DESC LIMIT 1);


------------------------------------------------------------------------
-- predictions: the logbook. Add-only; the only allowed change is locking.
--
-- Normal predictions must be logged before kickoff. A correction (a row with
-- corrects_id set and a note) may be added later for the record, but grading
-- only ever uses rows created before kickoff.
------------------------------------------------------------------------
CREATE TABLE predictions (
    id              INTEGER PRIMARY KEY,
    game_id         INTEGER NOT NULL REFERENCES games(id),
    source          TEXT NOT NULL CHECK (source IN ('engine', 'claude', 'me')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    p_home          REAL NOT NULL CHECK (p_home BETWEEN 0 AND 1),
    p_draw          REAL CHECK (p_draw IS NULL OR p_draw BETWEEN 0 AND 1),
    p_away          REAL NOT NULL CHECK (p_away BETWEEN 0 AND 1),
    proj_home_score REAL,
    proj_away_score REAL,
    odds_id         INTEGER REFERENCES odds(id),   -- the price seen at prediction time
    model_version   TEXT,
    locked          INTEGER NOT NULL DEFAULT 0 CHECK (locked IN (0, 1)),
    corrects_id     INTEGER REFERENCES predictions(id),
    note            TEXT,
    CHECK (abs(p_home + coalesce(p_draw, 0) + p_away - 1) < 1e-6),
    CHECK (corrects_id IS NULL OR length(trim(coalesce(note, ''))) > 0)
);

CREATE TRIGGER predictions_must_be_current
BEFORE INSERT ON predictions
WHEN abs(julianday(NEW.created_at) - julianday('now')) * 86400 > 5
BEGIN
    SELECT RAISE(ABORT, 'predictions must be stamped with the current time (no backdating)');
END;

CREATE TRIGGER predictions_before_kickoff
BEFORE INSERT ON predictions
WHEN NEW.corrects_id IS NULL
 AND datetime('now') >= (SELECT start_time_utc FROM games WHERE id = NEW.game_id)
BEGIN
    SELECT RAISE(ABORT, 'kickoff has passed: predictions must be logged before the game starts');
END;

CREATE TRIGGER predictions_draw_matches_sport
BEFORE INSERT ON predictions
WHEN ((SELECT sport FROM games WHERE id = NEW.game_id) LIKE 'soccer%')
     <> (NEW.p_draw IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'draw probability is required for soccer and not allowed otherwise');
END;

CREATE TRIGGER predictions_odds_same_game
BEFORE INSERT ON predictions
WHEN NEW.odds_id IS NOT NULL
 AND (SELECT game_id FROM odds WHERE id = NEW.odds_id) IS NOT NEW.game_id
BEGIN
    SELECT RAISE(ABORT, 'odds_id belongs to a different game');
END;

CREATE TRIGGER predictions_correction_same_game
BEFORE INSERT ON predictions
WHEN NEW.corrects_id IS NOT NULL
 AND (SELECT game_id FROM predictions WHERE id = NEW.corrects_id) IS NOT NEW.game_id
BEGIN
    SELECT RAISE(ABORT, 'a correction must point to a prediction for the same game');
END;

CREATE TRIGGER predictions_only_lock
BEFORE UPDATE ON predictions
WHEN NOT (OLD.locked = 0 AND NEW.locked = 1
          AND NEW.id IS OLD.id AND NEW.game_id IS OLD.game_id
          AND NEW.source IS OLD.source AND NEW.created_at IS OLD.created_at
          AND NEW.p_home IS OLD.p_home AND NEW.p_draw IS OLD.p_draw
          AND NEW.p_away IS OLD.p_away
          AND NEW.proj_home_score IS OLD.proj_home_score
          AND NEW.proj_away_score IS OLD.proj_away_score
          AND NEW.odds_id IS OLD.odds_id AND NEW.model_version IS OLD.model_version
          AND NEW.corrects_id IS OLD.corrects_id AND NEW.note IS OLD.note)
BEGIN
    SELECT RAISE(ABORT, 'predictions can never be edited; add a correction row instead');
END;

CREATE TRIGGER predictions_no_delete BEFORE DELETE ON predictions
BEGIN SELECT RAISE(ABORT, 'predictions can never be deleted'); END;


------------------------------------------------------------------------
-- adjustments: Claude's bounded news changes to an engine prediction.
-- Each delta moves one outcome's probability; together they sum to zero.
-- The running total per outcome per prediction can't exceed the cap.
------------------------------------------------------------------------
CREATE TABLE adjustments (
    id                  INTEGER PRIMARY KEY,
    game_id             INTEGER NOT NULL REFERENCES games(id),
    base_prediction_id  INTEGER NOT NULL REFERENCES predictions(id),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    d_home              REAL NOT NULL,
    d_draw              REAL,
    d_away              REAL NOT NULL,
    reason              TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    source_url          TEXT NOT NULL CHECK (source_url LIKE 'http://_%'
                                          OR source_url LIKE 'https://_%'),
    CHECK (abs(d_home + coalesce(d_draw, 0) + d_away) < 1e-6)
);

CREATE TRIGGER adjustments_must_be_current
BEFORE INSERT ON adjustments
WHEN abs(julianday(NEW.created_at) - julianday('now')) * 86400 > 5
BEGIN
    SELECT RAISE(ABORT, 'adjustments must be stamped with the current time (no backdating)');
END;

CREATE TRIGGER adjustments_before_kickoff
BEFORE INSERT ON adjustments
WHEN datetime('now') >= (SELECT start_time_utc FROM games WHERE id = NEW.game_id)
BEGIN
    SELECT RAISE(ABORT, 'kickoff has passed: adjustments must be logged before the game starts');
END;

CREATE TRIGGER adjustments_base_is_engine
BEFORE INSERT ON adjustments
WHEN NOT EXISTS (SELECT 1 FROM predictions
                 WHERE id = NEW.base_prediction_id AND source = 'engine'
                   AND game_id = NEW.game_id)
BEGIN
    SELECT RAISE(ABORT, 'an adjustment must point to an engine prediction for the same game');
END;

CREATE TRIGGER adjustments_draw_matches_sport
BEFORE INSERT ON adjustments
WHEN ((SELECT sport FROM games WHERE id = NEW.game_id) LIKE 'soccer%')
     <> (NEW.d_draw IS NOT NULL)
BEGIN
    SELECT RAISE(ABORT, 'draw adjustment is required for soccer and not allowed otherwise');
END;

CREATE TRIGGER adjustments_within_cap
BEFORE INSERT ON adjustments
WHEN abs(NEW.d_home + coalesce((SELECT SUM(d_home) FROM adjustments
         WHERE base_prediction_id = NEW.base_prediction_id), 0)) > {{MAX_ADJ}} + 1e-9
  OR abs(NEW.d_away + coalesce((SELECT SUM(d_away) FROM adjustments
         WHERE base_prediction_id = NEW.base_prediction_id), 0)) > {{MAX_ADJ}} + 1e-9
  OR abs(coalesce(NEW.d_draw, 0) + coalesce((SELECT SUM(d_draw) FROM adjustments
         WHERE base_prediction_id = NEW.base_prediction_id), 0)) > {{MAX_ADJ}} + 1e-9
BEGIN
    SELECT RAISE(ABORT, 'adjustment exceeds the per-game cap');
END;

CREATE TRIGGER adjustments_stay_valid_probability
BEFORE INSERT ON adjustments
WHEN EXISTS (
    SELECT 1 FROM predictions p
    WHERE p.id = NEW.base_prediction_id
      AND (p.p_home + NEW.d_home + coalesce((SELECT SUM(d_home) FROM adjustments
              WHERE base_prediction_id = p.id), 0) NOT BETWEEN 0 AND 1
        OR p.p_away + NEW.d_away + coalesce((SELECT SUM(d_away) FROM adjustments
              WHERE base_prediction_id = p.id), 0) NOT BETWEEN 0 AND 1
        OR coalesce(p.p_draw, 0) + coalesce(NEW.d_draw, 0) + coalesce((SELECT SUM(d_draw)
              FROM adjustments WHERE base_prediction_id = p.id), 0) NOT BETWEEN 0 AND 1))
BEGIN
    SELECT RAISE(ABORT, 'adjustment would push a probability below 0 or above 1');
END;

CREATE TRIGGER adjustments_no_update BEFORE UPDATE ON adjustments
BEGIN SELECT RAISE(ABORT, 'adjustments can never be changed'); END;

CREATE TRIGGER adjustments_no_delete BEFORE DELETE ON adjustments
BEGIN SELECT RAISE(ABORT, 'adjustments can never be deleted'); END;


------------------------------------------------------------------------
-- results: final outcome, one row per game, saved after kickoff.
-- For soccer, store the 90-minute score (moneyline bets settle on it).
------------------------------------------------------------------------
CREATE TABLE results (
    game_id      INTEGER PRIMARY KEY REFERENCES games(id),
    status       TEXT NOT NULL CHECK (status IN ('final', 'cancelled')),
    home_score   INTEGER CHECK (home_score IS NULL OR home_score >= 0),
    away_score   INTEGER CHECK (away_score IS NULL OR away_score >= 0),
    source       TEXT NOT NULL,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((status = 'final' AND home_score IS NOT NULL AND away_score IS NOT NULL)
        OR (status = 'cancelled' AND home_score IS NULL AND away_score IS NULL))
);

CREATE TRIGGER results_after_kickoff
BEFORE INSERT ON results
WHEN datetime('now') < (SELECT start_time_utc FROM games WHERE id = NEW.game_id)
BEGIN
    SELECT RAISE(ABORT, 'a result cannot be saved before the game starts');
END;

CREATE TRIGGER results_no_update BEFORE UPDATE ON results
BEGIN SELECT RAISE(ABORT, 'results can never be changed'); END;

CREATE TRIGGER results_no_delete BEFORE DELETE ON results
BEGIN SELECT RAISE(ABORT, 'results can never be deleted'); END;

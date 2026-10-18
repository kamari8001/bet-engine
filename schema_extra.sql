-- Additions to the database: backtest tables and Eastern-time views.
-- Safe to run again on an existing database (IF NOT EXISTS everywhere).


------------------------------------------------------------------------
-- Backtest tables: past seasons from outside sources, used to test the
-- model. Kept apart from the live logbook (games, odds, predictions...),
-- and replaced in full each time pull_history.py runs.
------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hist_games (
    id             INTEGER PRIMARY KEY,
    sport          TEXT NOT NULL CHECK (sport IN
                       ('nfl', 'ncaaf', 'nba', 'ncaab', 'mlb',
                        'soccer_club', 'soccer_intl')),
    season         INTEGER NOT NULL,
    week           INTEGER,
    season_type    TEXT NOT NULL CHECK (season_type IN ('regular', 'postseason')),
    game_date_et   TEXT NOT NULL,     -- 'YYYY-MM-DD', Eastern
    kickoff_et     TEXT,              -- 'YYYY-MM-DD HH:MM', Eastern; empty if unknown
    kickoff_utc    TEXT,              -- same moment in UTC; empty if unknown
    home_team      TEXT NOT NULL,
    away_team      TEXT NOT NULL,
    home_division  TEXT,              -- college only: fbs, fcs, ii, iii
    away_division  TEXT,
    home_score     INTEGER NOT NULL CHECK (home_score >= 0),
    away_score     INTEGER NOT NULL CHECK (away_score >= 0),
    neutral_site   INTEGER NOT NULL CHECK (neutral_site IN (0, 1)),
    home_starter_id   TEXT,          -- starting QB (NFL); empty if unknown
    home_starter_name TEXT,
    away_starter_id   TEXT,
    away_starter_name TEXT,
    home_rest_days    INTEGER,       -- days since the team's previous game
    away_rest_days    INTEGER,
    home_coach        TEXT,          -- head coach (NFL)
    away_coach        TEXT,
    home_off_epa      REAL,          -- offense expected points added, whole game (NFL)
    home_off_plays    INTEGER,       -- offensive plays: passes + sacks + runs
    away_off_epa      REAL,
    away_off_plays    INTEGER,
    home_pub_elo      REAL,          -- published pregame Elo (college: CFBD)
    away_pub_elo      REAL,
    source         TEXT NOT NULL,
    external_id    TEXT NOT NULL,
    imported_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source, external_id)
);

-- Preseason team information published by outside sources (college: CFBD).
-- All of it is known before the season starts, so using it has no hindsight.
CREATE TABLE IF NOT EXISTS hist_team_season (
    sport          TEXT NOT NULL,
    season         INTEGER NOT NULL,
    team           TEXT NOT NULL,
    talent         REAL,      -- roster talent composite (recruiting-based)
    returning_pct  REAL,      -- share of last season's production that returns (0-1)
    prev_sp        REAL,      -- previous season's final SP+ rating
    source         TEXT NOT NULL,
    PRIMARY KEY (sport, season, team)
);

-- Past lines. Timing is 'unknown' because the sources don't say whether
-- these are closing lines. home_spread uses betting convention:
-- -3.5 means the home team is favored by 3.5.
CREATE TABLE IF NOT EXISTS hist_odds (
    id            INTEGER PRIMARY KEY,
    hist_game_id  INTEGER NOT NULL REFERENCES hist_games(id) ON DELETE CASCADE,
    provider      TEXT NOT NULL,
    home_ml       INTEGER CHECK (home_ml IS NULL OR home_ml >= 100 OR home_ml <= -100),
    away_ml       INTEGER CHECK (away_ml IS NULL OR away_ml >= 100 OR away_ml <= -100),
    home_spread   REAL,
    total         REAL,
    timing        TEXT NOT NULL DEFAULT 'unknown',
    source        TEXT NOT NULL,
    CHECK ((home_ml IS NULL) = (away_ml IS NULL)),
    UNIQUE (hist_game_id, provider)
);


------------------------------------------------------------------------
-- Eastern-time views of the live tables, for browsing the database.
-- Times are stored in UTC; these show them in Eastern (EDT or EST).
-- US daylight saving: 2nd Sunday of March 2am to 1st Sunday of November 2am
-- (rules in force since 2007; the live tables only hold 2026 onward).
------------------------------------------------------------------------
CREATE VIEW IF NOT EXISTS games_et AS
SELECT g.id, g.sport, g.league, g.season, g.away_team, g.home_team,
       strftime('%Y-%m-%d %H:%M', g.start_time_utc,
           CASE WHEN g.start_time_utc >= datetime(substr(g.start_time_utc, 1, 4) || '-03-01', 'weekday 0', '+7 days', '+7 hours')
                 AND g.start_time_utc <  datetime(substr(g.start_time_utc, 1, 4) || '-11-01', 'weekday 0', '+6 hours')
                THEN '-4 hours' ELSE '-5 hours' END) || ' ET' AS kickoff_et,
       g.neutral_site, g.source, g.external_id
FROM games g;

CREATE VIEW IF NOT EXISTS odds_et AS
SELECT o.id, o.game_id, o.bookmaker,
       strftime('%Y-%m-%d %H:%M:%S', o.captured_at,
           CASE WHEN o.captured_at >= datetime(substr(o.captured_at, 1, 4) || '-03-01', 'weekday 0', '+7 days', '+7 hours')
                 AND o.captured_at <  datetime(substr(o.captured_at, 1, 4) || '-11-01', 'weekday 0', '+6 hours')
                THEN '-4 hours' ELSE '-5 hours' END) || ' ET' AS captured_et,
       o.home_ml, o.draw_ml, o.away_ml, o.source
FROM odds o;

CREATE VIEW IF NOT EXISTS predictions_et AS
SELECT p.id, p.game_id, p.source,
       strftime('%Y-%m-%d %H:%M:%S', p.created_at,
           CASE WHEN p.created_at >= datetime(substr(p.created_at, 1, 4) || '-03-01', 'weekday 0', '+7 days', '+7 hours')
                 AND p.created_at <  datetime(substr(p.created_at, 1, 4) || '-11-01', 'weekday 0', '+6 hours')
                THEN '-4 hours' ELSE '-5 hours' END) || ' ET' AS created_et,
       p.p_home, p.p_draw, p.p_away, p.proj_home_score, p.proj_away_score,
       p.odds_id, p.model_version, p.locked, p.corrects_id, p.note
FROM predictions p;

CREATE VIEW IF NOT EXISTS adjustments_et AS
SELECT a.id, a.game_id, a.base_prediction_id,
       strftime('%Y-%m-%d %H:%M:%S', a.created_at,
           CASE WHEN a.created_at >= datetime(substr(a.created_at, 1, 4) || '-03-01', 'weekday 0', '+7 days', '+7 hours')
                 AND a.created_at <  datetime(substr(a.created_at, 1, 4) || '-11-01', 'weekday 0', '+6 hours')
                THEN '-4 hours' ELSE '-5 hours' END) || ' ET' AS created_et,
       a.d_home, a.d_draw, a.d_away, a.reason, a.source_url
FROM adjustments a;


------------------------------------------------------------------------
-- lineup_facts: starters Claude confirmed from the news, with a source.
-- These are facts fed into the formula (rule 3), not probability guesses.
-- Same protections as the logbook: saved before kickoff, never changed.
------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lineup_facts (
    id           INTEGER PRIMARY KEY,
    game_id      INTEGER NOT NULL REFERENCES games(id),
    team         TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('QB')),
    player_name  TEXT NOT NULL CHECK (length(trim(player_name)) > 0),
    player_id    TEXT,              -- nflverse id when the player has started before
    status       TEXT NOT NULL CHECK (status IN ('confirmed', 'expected')),
    source_url   TEXT NOT NULL CHECK (source_url LIKE 'http://_%' OR source_url LIKE 'https://_%'),
    reason       TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS lineup_facts_must_be_current
BEFORE INSERT ON lineup_facts
WHEN abs(julianday(NEW.created_at) - julianday('now')) * 86400 > 5
BEGIN
    SELECT RAISE(ABORT, 'lineup facts must be stamped with the current time (no backdating)');
END;

CREATE TRIGGER IF NOT EXISTS lineup_facts_before_kickoff
BEFORE INSERT ON lineup_facts
WHEN datetime('now') >= (SELECT start_time_utc FROM games WHERE id = NEW.game_id)
BEGIN
    SELECT RAISE(ABORT, 'kickoff has passed: lineup facts must be logged before the game starts');
END;

CREATE TRIGGER IF NOT EXISTS lineup_facts_team_in_game
BEFORE INSERT ON lineup_facts
WHEN NOT EXISTS (SELECT 1 FROM games WHERE id = NEW.game_id
                 AND NEW.team IN (home_team, away_team))
BEGIN
    SELECT RAISE(ABORT, 'that team is not playing in this game');
END;

CREATE TRIGGER IF NOT EXISTS lineup_facts_no_update BEFORE UPDATE ON lineup_facts
BEGIN SELECT RAISE(ABORT, 'lineup facts can never be changed; add a new one instead'); END;

CREATE TRIGGER IF NOT EXISTS lineup_facts_no_delete BEFORE DELETE ON lineup_facts
BEGIN SELECT RAISE(ABORT, 'lineup facts can never be deleted'); END;


------------------------------------------------------------------------
-- qb_checks: Claude checked the news and the starter the model already
-- assumes is right ("verified"). Weaker than a confirmed lineup fact: it means
-- nothing contradicts him, not that the team announced him. Same protections.
------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS qb_checks (
    id           INTEGER PRIMARY KEY,
    game_id      INTEGER NOT NULL REFERENCES games(id),
    team         TEXT NOT NULL,
    player_name  TEXT NOT NULL CHECK (length(trim(player_name)) > 0),
    player_id    TEXT,
    source_url   TEXT NOT NULL CHECK (source_url LIKE 'http://_%' OR source_url LIKE 'https://_%'),
    reason       TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TRIGGER IF NOT EXISTS qb_checks_must_be_current
BEFORE INSERT ON qb_checks
WHEN abs(julianday(NEW.created_at) - julianday('now')) * 86400 > 5
BEGIN
    SELECT RAISE(ABORT, 'QB checks must be stamped with the current time (no backdating)');
END;

CREATE TRIGGER IF NOT EXISTS qb_checks_before_kickoff
BEFORE INSERT ON qb_checks
WHEN datetime('now') >= (SELECT start_time_utc FROM games WHERE id = NEW.game_id)
BEGIN
    SELECT RAISE(ABORT, 'kickoff has passed: QB checks must be logged before the game starts');
END;

CREATE TRIGGER IF NOT EXISTS qb_checks_team_in_game
BEFORE INSERT ON qb_checks
WHEN NOT EXISTS (SELECT 1 FROM games WHERE id = NEW.game_id
                 AND NEW.team IN (home_team, away_team))
BEGIN
    SELECT RAISE(ABORT, 'that team is not playing in this game');
END;

CREATE TRIGGER IF NOT EXISTS qb_checks_no_update BEFORE UPDATE ON qb_checks
BEGIN SELECT RAISE(ABORT, 'QB checks can never be changed; add a new one instead'); END;

CREATE TRIGGER IF NOT EXISTS qb_checks_no_delete BEFORE DELETE ON qb_checks
BEGIN SELECT RAISE(ABORT, 'QB checks can never be deleted'); END;

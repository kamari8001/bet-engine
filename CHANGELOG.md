# Changelog: Kamari's Prediction Engine

Versions follow MAJOR.MINOR.PATCH (see `version.py`): MAJOR changes the probabilities
(new model version or sport), MINOR adds features, PATCH fixes and polishes.
Each version is tagged in git (`git tag -l`).

## 2.0.0 (2026-10-19): basketball
New sport (MAJOR): NBA `nba-v1-refit-20261019` and college basketball `ncaab-v1-refit-20261019`
(team ratings + home court + rest days; NBA back-to-backs matter, college rest doesn't).
- History: NBA 2014-15 to 2025-26 from ESPN (15,479 games, real sportsbook prices); college
  basketball from CBBD (68,806 games; real sportsbook moneylines from 2023 on).
- Final exam (see `backtest_results/criteria_basketball.md`): both work and are calibrated but trail
  the market; neither made money (NBA -10.5%, college -4.2%). Flags are paper only, Low confidence.
- Fixed a data bug in past odds: ESPN "Live Odds" in-game prices and prediction-site projections
  were being counted as market prices; past odds now count only real sportsbooks' pregame prices.
- Live: NBA and college basketball schedules, results, odds, predictions with rest days, grading,
  warnings ("injury report not checked"), and slate/Live/Scorecard tabs with logos.
- News: scheduled NBA injury checks (noon and 6 PM) and college basketball checks (11 AM and 5 PM),
  recording reviews or capped adjustments with sources.
- Automation covers all four sports; `pull_odds.py all` skips sports with no games in the next week.

## 1.1.0 (2026-10-18)
- Named the engine **Kamari's Prediction Engine**, with the app and model versions shown in the slate page header.
- Live tab: separate NFL and College tabs.
- Live tab: the possession dot now lines up with the team name.
- Started versioning: `version.py`, this changelog, git tags.

## 1.0.0 (2026-10-18): football complete
Models: NFL `nfl-v2-refit-20261015` (team + starting-QB ratings + rest), College `ncaaf-v2-refit-20261015`
(team ratings + CFBD preseason talent, returning production, last season's SP+).
- Data: NFL (nflverse, 1999+) and college (CFBD, 2013+) history; live schedules, results, and odds from 10 books incl. your FanDuel, DraftKings, Polymarket.
- Database rules enforce log-before-kickoff, never-edit-the-past, sourced and capped adjustments.
- Backtested with a one-time final exam (both sports work but trail the market; no money edge), then refit on all seasons for live use.
- Live predictions from three sources (engine, claude, you), news step for NFL QBs (facts and verified checks) and college (reviews and capped adjustments).
- Grading: Brier, log loss, calibration, paper bets, closing-line value, head-to-head.
- Automation: daily routine, closing-line pulls before each kickoff window, wake-up catch-up; scheduled Claude news checks.
- Slate page: flip cards, My picks, visual scorecard, Live tab; per-game warnings instead of unearned confidence ratings.
- Cancelled/postponed games; shadow mode with three pre-registered challengers; market-pattern tests (none passed).

## Before 1.0.0
Built 2026-10-14 to 2026-10-18; see `git log` for every step.

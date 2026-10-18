# Changelog: Kamari's Prediction Engine

Versions follow MAJOR.MINOR.PATCH (see `version.py`): MAJOR changes the probabilities
(new model version or sport), MINOR adds features, PATCH fixes and polishes.
Each version is tagged in git (`git tag -l`).

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

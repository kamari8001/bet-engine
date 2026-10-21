# Changelog: Kamari's Prediction Engine

Versions follow MAJOR.MINOR.PATCH (see `version.py`): MAJOR changes the probabilities
(new model version or sport), MINOR adds features, PATCH fixes and polishes.
Each version is tagged in git (`git tag -l`).

## 2.4.0 (2026-10-21): soccer power rankings
- Rankings tab has **Soccer**: every Big 5 club in one list, with the same OVR scale, season picker
  (2012-13 on), all-time top 25, and team pages. Clubs from different leagues are compared using
  UEFA's country coefficients (downloaded with sources to `uefa_coefficients.json`): an outside
  assumption, adjustable with `SOCCER_LEAGUE_STRENGTH` in `config.py`. Records are wins-draws-losses.
- The 9 AM routine now refreshes this season's soccer results (last step, so it can't block the others).

## 2.3.1 (2026-10-21)
- Odds pulls no longer fail (and notify) when The Odds API still lists a game as upcoming after
  our schedule's kickoff; that game is skipped as "already started" and the other prices save.

## 2.3.0 (2026-10-20): OVR on one scale, past seasons
- OVR now works like a FIFA rating and means the same thing in every season: 62 = an average team,
  80+ = great (top ~7% of all team-seasons in our history), 90+ = historically great (top ~1%).
  It starts from the model's chance to beat an average team that season, then places it on a bell
  curve of every past team-season in that sport. The curve is frozen per model version
  (`rankings_scale.json`), so a 95 in 2017 really was more dominant than an 88 today.
- Rankings tab: season picker (past seasons show each team's rating after its last game, records
  incl. playoffs), an all-time top 25, and a page per team with its OVR by season (chart + table).
  History: NFL 2000+, college football 2014+, NBA and college basketball 2015-16+.

## 2.2.2 (2026-10-20)
- Fixed "DraftKings" showing a stray symbol on iPhone: the Doppio One font's "ft" ligature (joined letters) is now turned off.

## 2.2.1 (2026-10-20): phone layout
- The slate now fits phone screens (it used to render the full desktop page zoomed out): compact
  header, swipeable tab bar, one game card per row, bigger tap targets, text boxes that don't make
  the iPhone zoom in, the book name under the price, Positions picks stacked as blocks, summary
  tiles two per row, and Rankings showing the key columns. Desktop layout unchanged.
  Checked at 375 and 430 pixels wide on every page.

## 2.2.0 (2026-10-19): power rankings
- New **Rankings** tab (and `python3 rankings.py <sport>`): every team ranked by the model's own
  current rating, with an **OVR** (0-99) = the model's chance to beat an average team of its league
  on a neutral field. Also net points vs. average, record, last 5, offense and defense ranks, and
  movement since a week ago. College lists have search and a conference filter; NFL shows the QB the
  engine expects next game. Display only; nothing is stored.
- Header's model list shows only live sports (it briefly listed the unfinished soccer model).

## 2.1.3 (2026-10-19)
- The "My picks" page is now called "Positions".

## 2.1.2 (2026-10-19)
- Slate page font: Doppio One (Google Fonts). Falls back to the system font when offline.

## 2.1.1 (2026-10-19): health-check fixes
- Pre-game refreshes no longer stop because an earlier game that day has no result loaded yet.
  Now only games whose own team is waiting on a result are skipped; if any result is 24+ hours
  late, the run still stops (the data source is probably broken). This broke Sunday night's refresh.
- After the Mac wakes, games in a kickoff group whose first game already started now get their own
  closing-odds pull (Sunday, the 4:25 PM games were missed). A sport whose odds are under 15
  minutes old isn't pulled again.
- A brief internet drop while checking credits retries quietly next run instead of sending a
  failure notification.

## 2.1.0 (2026-10-19): expert signals
- New paper-only shadow challengers, pre-registered: `dk_sharp_money_v1` (bet the side with 15+
  points more of the money than of the bets, from DraftKings' public splits; all four sports) and
  `circa_consensus_v1` (bet the Circa Million contest's 5 most-picked NFL sides).
- `experts.py` records signals with their source link in the protected `expert_signals` table.
- Scheduled checks: DraftKings splits snapshots (11:45 AM, 5:45 PM) and Circa consensus (Saturday 9 PM).

## 2.0.1 (2026-10-19)
- Tab labels: "NCAAF" (college football) and "NCAAM" (college basketball).

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

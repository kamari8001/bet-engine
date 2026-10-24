# Development queue

The to-do list for Kamari's Prediction Engine. **Talal: edit freely.** Reorder items, delete
them, or add new ones anywhere. Claude reads this at the start of each session, works top-down
through "Up next", and asks before starting anything big.

How items move: Up next → In progress → Done (with the date and version). Ideas wait in
"Later" until promoted. Anything touching more than one file still gets a plan and your OK
first (CLAUDE.md).

## In progress

(nothing right now)

## Up next

1. **Club soccer + Champions League shakedown** (after Nov 3-4, matchday 4): Champions League games added about Oct 27 (7 days ahead), predictions before kickoff, 90-minute results loaded overnight, grading.
2. **Club soccer shakedown check** (after the first weekend, around Mon Oct 26): early-kickoff closing pulls (6:50 AM wake), predictions before every game, results and grading, the 8 AM news check.

**Model accuracy program** (added 2026-10-23). Reordered 2026-10-23 after the factor study and the
anchor fit (`backtest_results/factor_study.md`, `backtest_results/anchor.md`): the market price already
holds everything the engine knows, so engine-accuracy work (margin compression, learning-rate decay)
can't become an edge against the market. What can is information the market doesn't have yet:
measured player availability and sourced news before the line moves. Talal chose to keep the engine as
is (option 1); the anchored model is recorded, not deployed.

3. **Check ESPN's college basketball injury list after Nov 3** (is it filled in during the season?). If it
   is, a possible shadow test of the college player rating (it narrowly missed its bar; see
   `plans/college_player_impact.md`).

Paused (engine accuracy only; revisit if live scorecards ever show the engine beating the closing line):
- Margin with diminishing returns (football and basketball).
- Within-season learning-rate decay.
- Market anchor as a model input / edge recalibration: done as a study; every sport reduces to the market
  (`plans/anchor.md`). Not deployed by Talal's choice.

## Waiting on a date or on data

- **NBA news timing test** (v4.2.0): 100 material injury events, then the verdict (`python3 injury_watch.py report`; progress look at 50). If we're early, extend to NFL QB news and soccer team news.
- **Each summer (from July 2027):** add promoted soccer clubs to `teams.SOCCER_TEAMS` (checked against football-data, ESPN, The Odds API) before the season starts.
- **200 graded games per sport:** evidence-based Low / Medium / High confidence, and
  rule-8 blending by track record.
- **Shadow challengers' promotion bars** (100+ bets for rules, 150+ games for models).
  Check `python3 shadow.py report` monthly.
- **Circa consensus:** the first record is Saturday, Oct 24.

## Later (ideas, not ordered; promote to "Up next" when wanted)

- **Basketball preseason roster data:** better early-season ratings.
- **Data-driven college football QB model** (the 3-point cap is small for a QB change).
- **Verify college basketball neutral-site lines** from a second source (ESPN's odds by game, ~2,800 games 2023-26) so they can return to the backtests (CBBD stores some for the wrong side; see `criteria_basketball.md`).
- **Europa League predictions** (its results already feed the league strengths).
- **More covered leagues** for Champions League clubs we skip (Czechia, Ukraine, Croatia, Serbia, Cyprus, ...): needs a history source.
- **MLS** (its season runs March to November).
- **Three-way shadow mode** for soccer challengers (the current table is two-way only).
- **MLB** (build order #4).
- **International soccer** (build order #5).

## Done

- **Soccer xG model** (2026-10-24, no version change): Understat xG for every Big 5 game since 2014-15 (daily refresh); tested, better log loss on both tune and check but failed the calibration rule (9.8 vs 8), so not kept (`plans/soccer_xg.md`).
- **Sharper news timing, NBA** (2026-10-24, v4.2.0): injury watcher, instant odds + predictions on material news, news-timing panel (`plans/news_timing.md`).
- **College basketball player model** (2026-10-24, no version change): box scores loaded (daily refresh); tested, neither idea cleared the bar (production rating +0.0015 vs 0.002 needed), so nothing went live (`plans/college_player_impact.md`).
- **Player display release** (2026-10-23, v4.1.0): player OVR, rosters, profiles, player rankings (`plans/player_display.md`).
- **Early-season player values** (2026-10-23, no version change): both ideas tested, neither kept; the summer pull toward replacement predicts best (`plans/player_early_season.md`).
- **NBA player-impact model** (2026-10-23, v4.0.0): `nba-v2-refit-20261023`, plan `plans/player_impact.md`.

- 2026-10-23: factor study (`backtest_results/factor_study.md`): the market price is the only factor that matters; the engine adds ~0 beyond it except in college basketball (+0.15); NFL favorite size is the one small market miss
- 2026-10-22 v3.1.1: filter kept after logging a pick; phone scrolling fix (flat cards on touch screens); modern look and light animations
- 2026-10-22 v3.1.0: Champions League live (learned league strengths; final exam -1.0%); soccer rankings use learned strengths
- 2026-10-21 v3.0.0: club soccer live (Big 5, three-way predictions, grading with RPS, Soccer tab, automation, 8 AM news check); $30 Odds API plan bought
- 2026-10-21 v2.4.0: soccer power rankings (Big 5 together via UEFA coefficients; adjustable league strength)
- 2026-10-21 v2.3.1: odds pulls skip games our schedule says already started (was a false failure)
- 2026-10-21: club soccer final exam (works, calibrated, trails market, no money edge; ClubElo untested, API down 3 days) and refit `soccer-v2-refit-20261021`
- 2026-10-21: basketball shakedown passed (predictions before every tip, scheduled checks ran, grading works; one pull-failure bug found)
- 2026-10-20 v2.3.0: OVR on one scale across seasons; past seasons, all-time top 25, team history
- 2026-10-20 v2.2.2: fixed the "ft" ligature glitch in DraftKings on iPhone
- 2026-10-20 v2.2.1: phone layout for the slate
- 2026-10-20: phone access to the slate via Tailscale (private; Mac must be awake)
- 2026-10-19 v2.2.0: power rankings tab (NFL, NCAAF, NBA, NCAAM)
- 2026-10-19 v2.1.3: "My picks" renamed "Positions"
- 2026-10-19: club soccer data step (82,822 past games, 322,854 odds rows; live schedule and odds tested, not switched on)
- 2026-10-19: Mac wakes at 6:50 AM on Saturdays and Sundays (`pmset repeat`, set by Talal; check with `pmset -g sched`)
- 2026-10-19 v2.1.2: slate font Doppio One
- 2026-10-19 v2.1.1: health-check fixes (same-day missing results, wake-up closing pulls, quiet retry)
- 2026-10-19 v2.1.0: expert signals (DraftKings splits, Circa consensus) as shadow challengers
- 2026-10-19 v2.0.1: NCAAF and NCAAM labels
- 2026-10-19 v2.0.0: NBA and college basketball live
- 2026-10-18: shadow mode, market-pattern tests, college news step, Live tab
- 2026-10-16: automation (launchd), slate page
- 2026-10-15: NFL and college football live (v1.x)

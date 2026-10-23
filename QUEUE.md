# Development queue

The to-do list for Kamari's Prediction Engine. **Talal: edit freely.** Reorder items, delete
them, or add new ones anywhere. Claude reads this at the start of each session, works top-down
through "Up next", and asks before starting anything big.

How items move: Up next → In progress → Done (with the date and version). Ideas wait in
"Later" until promoted. Anything touching more than one file still gets a plan and your OK
first (CLAUDE.md).

## In progress

_(nothing)_

## Up next

1. **Club soccer + Champions League shakedown** (after Nov 3-4, matchday 4): Champions League games added about Oct 27 (7 days ahead), predictions before kickoff, 90-minute results loaded overnight, grading.
2. **Club soccer shakedown check** (after the first weekend, around Mon Oct 26): early-kickoff closing pulls (6:50 AM wake), predictions before every game, results and grading, the 8 AM news check.

**Model accuracy program** (added 2026-10-23; each one: pre-registered criteria, tune/check split,
one final test, then a new MAJOR version if it changes probabilities). Why this order: the measured
weakness is overconfident disagreement with the market, so the cheap fixes that target it come first;
the biggest build (player impact) comes once live NBA data shows how much injuries move lines.

3. **Market anchor as a model input** (all sports): blend the engine with the market's opening line,
   with the weight fit on past data and allowed to vary by sport and by time of season (lean on the
   market early, when our ratings are mostly last year's). The `market_anchor_v1` shadow challenger
   is the crude version; its closing-line value is the early signal.
4. **Edge recalibration** (all sports): a second calibration step that maps the size of an edge to how
   often edges that size were right historically, flattening big edges toward the market. Fit on tune
   seasons, checked on check seasons.
5. **Margin with diminishing returns** (football and basketball): compress blowouts in the rating
   updates (square-root or log scale on the margin) instead of counting every point up to the cap.
   Test with `backtest.py ablate`.
6. **Within-season learning-rate decay** (basketball first, 82 games): ratings learn faster right after
   the off-season regression, then settle. A smooth decay, not the crude NFL early boost that was rejected.
7. **Basketball player-impact model**: estimate each player's value from minutes and plus-minus data,
   subtract absent players before predicting, replacing the 3-point cap for missing stars. Start after a
   few weeks of live NBA results (moved up from "Later").
8. **Soccer xG model**: shadow-only until a few seasons of expected-goals data exist (moved from "Later").

## Waiting on a date or on data

- **Each summer (from July 2027):** add promoted soccer clubs to `teams.SOCCER_TEAMS` (checked against football-data, ESPN, The Odds API) before the season starts.
- **200 graded games per sport:** evidence-based Low / Medium / High confidence, and
  rule-8 blending by track record.
- **Shadow challengers' promotion bars** (100+ bets for rules, 150+ games for models).
  Check `python3 shadow.py report` monthly.
- **Circa consensus:** the first record is Saturday, Oct 24.

## Later (ideas, not ordered; promote to "Up next" when wanted)

- **Basketball preseason roster data:** better early-season ratings.
- **Data-driven college football QB model** (the 3-point cap is small for a QB change).
- **Europa League predictions** (its results already feed the league strengths).
- **More covered leagues** for Champions League clubs we skip (Czechia, Ukraine, Croatia, Serbia, Cyprus, ...): needs a history source.
- **MLS** (its season runs March to November).
- **Three-way shadow mode** for soccer challengers (the current table is two-way only).
- **MLB** (build order #4).
- **International soccer** (build order #5).

## Done

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

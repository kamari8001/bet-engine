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

1. **Club soccer: live (v3.0.0)**, needs the $30 Odds API plan. Add soccer to `pull_games`/`pull_odds` `all`, the morning routine (`pull_soccer_history.py current`), and pre-kickoff windows.

## Waiting on a date or on data

- **Nov 3:** Talal buys the $30 Odds API plan (approved) when college basketball starts.
- **200 graded games per sport:** evidence-based Low / Medium / High confidence, and
  rule-8 blending by track record.
- **Shadow challengers' promotion bars** (100+ bets for rules, 150+ games for models).
  Check `python3 shadow.py report` monthly.
- **Circa consensus:** the first record is Saturday, Oct 24.

## Later (ideas, not ordered; promote to "Up next" when wanted)

- **Basketball player-impact model:** turn "star X is out" into a probability with data,
  instead of the 3-point cap. Wait for a few weeks of live NBA results first.
- **Basketball preseason roster data:** better early-season ratings.
- **Data-driven college football QB model** (the 3-point cap is small for a QB change).
- **Champions League and Europa League**, after club soccer: needs cross-league strength.
- **MLS** (its season runs March to November).
- **Three-way shadow mode** for soccer challengers (the current table is two-way only).
- **Soccer xG model**, once a few seasons of expected-goals data exist.
- **MLB** (build order #4).
- **International soccer** (build order #5).

## Done

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

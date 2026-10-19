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

1. **Basketball shakedown check** (around Wed Oct 21 to Thu Oct 22): confirm predictions
   were logged before every tip, closing pulls happened, NBA injury checks and DraftKings
   splits recorded entries, and overnight grading ran.
2. **Club soccer: data step** (plan: `plans/club_soccer.md`; waiting for OK on its 4 decisions)
3. **Club soccer: model and final exam**
4. **Club soccer: live (v3.0.0)**, needs the $30 Odds API plan

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

- 2026-10-19 v2.1.1: health-check fixes (same-day missing results, wake-up closing pulls, quiet retry)
- 2026-10-19 v2.1.0: expert signals (DraftKings splits, Circa consensus) as shadow challengers
- 2026-10-19 v2.0.1: NCAAF and NCAAM labels
- 2026-10-19 v2.0.0: NBA and college basketball live
- 2026-10-18: shadow mode, market-pattern tests, college news step, Live tab
- 2026-10-16: automation (launchd), slate page
- 2026-10-15: NFL and college football live (v1.x)

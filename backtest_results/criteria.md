# Final exam pass/fail criteria

Written and committed **before** the first final-exam run (2026-10-15), so the
bar can't move after seeing results.

Models under test:
- NFL v2 (`nfl-v2-20261015`): seasons 2023-2025
- College v2 (`ncaaf-v2-20261015`): seasons 2021-2025

## Tests

1. **Works at all.** Log loss beats the "home team always wins at its usual
   rate" baseline. Fail means something is broken.
2. **Honest percentages.** In the calibration table, no 10-point bucket with
   50 or more games is off by more than 8 percentage points (average
   predicted vs. actual win rate). Fail means the probabilities can't be
   trusted as stated.
3. **Vs. the market.** Model and no-vig market Brier/log loss are reported on
   the same games. Information only, not pass/fail.
4. **Would it have made money?** Flagged bets (edge >= 4 points), 1 unit each,
   show a profit over at least 150 bets. A backtest profit is not proof of an
   edge: with ~500 bets, luck alone moves the return by about +/-9%.

## What happens on a fail

- Tests 1-2: look for a bug (code not doing what was designed). Fixing a real
  bug is allowed and gets documented here. Re-tuning settings to pass is not.
- Test 4: the sport continues (predictions logged and graded live), but
  flagged bets are shown as Low confidence, paper only.
- Either way, these seasons are now used. Any later version is judged on live
  results.

## Real money

Only after a sport has 200+ live graded games and consistently beats the
closing line.

## Results

Run 2026-10-15. Full numbers in `final_runs.jsonl`.

| Test | NFL v2 (2023-2025, 855 games) | College v2 (2021-2025, 4,546 games) |
|---|---|---|
| 1. Works at all | PASS: log loss 0.632 vs baseline 0.689 | PASS: 0.504 vs 0.659 |
| 2. Honest percentages | **FAIL** (narrowly): the 20-30% bucket (55 games) predicted 25.6%, home won 34.5%, off by 8.9 | PASS: worst bucket (0-10%, 115 games) off by 5.3 |
| 3. Vs. market (same games) | model 0.632 vs market 0.608 | model 0.557 vs market 0.535 (3,933 games) |
| 4. Made money? | **FAIL**: 524 bets, 197-326-1, -55.9 units, -10.7% | **FAIL**: 2,256 bets, 1063-1193, -86.0 units, -3.8% |

**NFL test 2, bug check:** no bug found. The calibration correction was fit on
2019-2022, when home teams won only 50-52% in three of four seasons (2020 had
empty stadiums), so it lowered home-team probabilities. In 2023-2025 home
teams won 54.9% against an average prediction of 52.3%. Without the
correction the model would have overshot instead (57.3%). Home-field size in
the NFL moves around from year to year; that's a modeling limit, not a code
error, so nothing is changed and the fail stands.

**Verdict:** both sports continue to live logging and grading, with flagged
bets shown as Low confidence, paper only. Neither has evidence of an edge
over the market from the base model alone.

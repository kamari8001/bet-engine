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

(Filled in after the runs.)

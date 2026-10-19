# Basketball final exam: pass/fail criteria

Written and committed **before** any basketball model was built or tuned
(2026-10-19), so the bar can't move after seeing results. Same tests as football
(`criteria.md`).

## Seasons (labeled by the year they end)

| Sport | Tune | Check | Final exam (run once) |
|---|---|---|---|
| NBA | 2015-2020 | 2021-2023 | 2024-2026 |
| College basketball | 2015-2020 | 2021-2023 | 2024-2026 |

Settings are chosen on the tune seasons only; ideas are kept only if they help on
both tune and check seasons; the final-exam seasons are touched once.

## Tests

1. **Works at all.** Log loss beats the "home team always wins at its usual rate" baseline.
2. **Honest percentages.** No 10-point calibration bucket with 50+ games is off by more
   than 8 percentage points.
3. **Vs. the market.** Model and no-vig market Brier / log loss on the same games.
   Information only.
4. **Would it have made money?** Flagged bets (edge >= 4 points), 1 unit each at the
   average listed price, show a profit over at least 150 bets.

## What happens on a fail

Same as football: tests 1-2 fail -> look for a bug (fixing a real bug is allowed and
documented here; re-tuning to pass is not). Test 4 fails -> the sport goes live with
flags paper only / Low confidence. Real money only after 200+ live graded games and
consistent closing-line value.

## Results

(Appended after the run.)

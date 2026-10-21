# Club soccer final exam: pass/fail criteria

Written and committed **before** any soccer model was built or tuned (2026-10-19), so the bar
can't move after seeing results. Same idea as football and basketball (`criteria.md`,
`criteria_basketball.md`), adapted to three outcomes (home, draw, away).

## Games and seasons (labeled by the year they end)

Graded games: **Big 5 league games only** (Premier League, La Liga, Bundesliga, Serie A, Ligue 1).
Second-division games (2005-06 on) feed the ratings, so promoted teams arrive with a history,
but are never graded. Ratings run from 2005-06, so the first graded season has a warm-up.

| Tune | Check | Final exam (run once) |
|---|---|---|
| 2013-2019 (2012-13 to 2018-19) | 2020-2022 (2019-20 to 2021-22) | 2023-2026 (2022-23 to 2025-26) |

Settings are chosen on the tune seasons only; an idea is kept only if it improves log loss on
**both** tune and check seasons; the final-exam seasons are touched once. 2020-21 was mostly
played without crowds (home advantage nearly vanished); the model's home advantage updates as it
goes, and this season is in the check period, not tuned on.

## Tests

1. **Works at all.** Log loss beats a baseline that gives every game its league's home/draw/away
   frequencies from the tune seasons.
2. **Honest percentages.** For **each** outcome (home, draw, away) separately: no 10-point
   calibration bucket with 50+ games is off by more than 8 percentage points.
3. **Vs. the market.** Model vs. the no-vig **market-average closing** price (log loss, Brier,
   RPS) on the same games. Pinnacle's no-vig closing price is shown too where present
   (2012-13 to 2024-25; mostly missing in 2025-26). Information only.
4. **Would it have made money?** For each game, the outcome with the largest edge (model minus the
   no-vig **pre-close market-average** probability) is flagged if that edge is 4+ points (at most one
   bet per game; draws included). 1 unit staked at the pre-close market-average decimal price.
   **Pass = a profit over at least 150 flagged bets.** Closing-line value against the market-average
   closing price is reported too.

Scores used: **log loss** (of the outcome that happened), **Brier** (summed over the three
outcomes), **RPS** (ranked probability score: home, draw, away in order, so a draw is "between").

## Ideas to test with `ablate` (pre-registered)

1. Shots on target as an extra signal in the rating updates.
2. ClubElo published ratings blended in (rating from the day **before** each game, so no hindsight).
3. Rest days since each team's previous league game.
4. Expected goals (xG): only 2026-27 has it, so it **can't** be judged here; live/shadow only.

## What happens on a fail

Same as before: tests 1-2 fail → look for a bug (fixing a real bug is allowed and documented here;
re-tuning to pass is not). Test 4 fails → club soccer goes live with flags paper only / Low
confidence. Real money only after 200+ live graded games and consistent closing-line value.

## Results

**Ideas (tune 2013-2019, check 2020-2022; log in `ablate_soccer_20261019.log`):** #1 shots on target kept
(tune -0.0010, check -0.0009); #3 rest days kept by the rule but negligible (< 0.0001 both); #2 ClubElo
**not tested**: api.clubelo.com returned HTTP 502 on every try 2026-10-19 to 2026-10-21 (its website
was up but has no usable rating history), so per Talal's choice the exam ran without it; ClubElo can only
be judged live from now on. #4 xG untestable here (as pre-registered). A calibration stretch fit on the
check seasons improved log loss by 0.0001 (< 0.002), so none was applied. Check-season worst calibration
gap was 8.8 (2020-21, no crowds); that was a check, not the exam.

**Final exam, run once 2026-10-21 with `soccer-v2-20261019`** (full numbers in `final_runs.jsonl`):

| Test | Result (2022-23 to 2025-26, 7,082 Big 5 games) |
|---|---|
| 1. Works at all | PASS: log loss 0.9834 vs baseline 1.0734 |
| 2. Honest percentages | PASS: worst bucket with 50+ games off by 5.6 (draws within 3) |
| 3. Vs. market | model 0.9834 / Brier 0.5860 / RPS 0.1996 vs market-average close 0.9669 / 0.5749 / 0.1944 (7,082 games); vs Pinnacle close 0.9801 vs 0.9630 (6,228 games) |
| 4. Made money? | **FAIL**: 2,815 flagged bets, 948 won, -391.3 units, -13.9%; avg CLV -0.26 pts |

**Verdict:** works and is calibrated, trails the market, no money edge: same as every other sport.
Club soccer goes live with flags paper only / Low confidence. Refit on 2013-2026 for live use:
`soccer-v2-refit-20261021`.

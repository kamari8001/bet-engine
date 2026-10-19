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

_(filled in after the one-time final exam)_

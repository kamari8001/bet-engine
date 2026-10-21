# Champions League final exam: pass/fail criteria

Written and committed **before** any Champions League model was built or tuned (2026-10-21), so the
bar can't move after seeing results. Same four tests as club soccer (`criteria_soccer.md`).

## Games and seasons (labeled by the year they end)

Graded: **Champions League main-competition games** (group/league phase and knockouts, not
qualifiers) where both clubs come from leagues we cover (about 80% of games). Scores are 90-minute
scores. All European games (Champions, Europa, Conference League, qualifiers included) feed the
learning; only main Champions League games are graded. 2014-15 is the warm-up season.

| Tune | Check | Final exam (run once) |
|---|---|---|
| 2016-2019 (2015-16 to 2018-19) | 2020-2022 (2019-20 to 2021-22) | 2023-2026 (2022-23 to 2025-26), 521 games |

## The model being tested

The club soccer model's domestic ratings (`soccer-v2-refit-20261021`, frozen: domestic settings are
not re-tuned here) plus a **strength per league learned from European games**: it starts at 0 for
every league, and after each European game moves toward what happened (learning rate tuned). In a
European game, each club's attack and defense are shifted by half its league's strength; European
games have their own average-goals level and home advantage, also learned. Only the new European
settings are tuned (on tune seasons; ideas kept only if better on both tune and check seasons).

## Tests

1. **Works at all.** Log loss beats a baseline of the Champions League's home/draw/away frequencies
   on the tune seasons.
2. **Honest percentages.** For each outcome (home, draw, away): no 10-point calibration bucket with
   50+ games is off by more than 8 percentage points.
3. **Vs. the market.** Model vs. the no-vig average of real sportsbooks' prices from ESPN (timing of
   those prices unknown, as for football). Information only.
4. **Would it have made money?** Per game, the outcome with the largest edge vs that market, if 4+
   points (draws included, one bet per game), 1 unit at the average decimal price of those books.
   **Pass = a profit over at least 150 flagged bets.** (Fewer than 150 bets = inconclusive, treated
   as a fail.)

Scores: log loss, Brier (summed over three outcomes), RPS.

## Ideas to test with `ablate` (pre-registered)

1. **European results also update club ratings** (a club's attack/defense learn from its European
   games too). Kept only if it improves Champions League log loss on tune AND check seasons AND does
   not worsen Big 5 domestic log loss on the tune or check seasons of `criteria_soccer.md` (it would
   change domestic predictions).
2. **League strengths shrink toward 0 between seasons** (a season regression for league strength).

## What happens on a fail

Tests 1-2 fail -> look for a bug (fixing a real bug is allowed and documented; re-tuning to pass is
not); if none, Champions League stays out of the live slate. Test 4 fails -> it goes live with
flags paper only / Low confidence, like every other sport.

## Results

_(filled in after the one-time final exam)_

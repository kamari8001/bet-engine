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

**Tuning (2016-2019) and check (2020-2022), `ucl-v1-20261021`:** log loss tune 0.9639 (baseline 1.0482),
check 0.9170 (baseline 1.0568; market 0.8886 on 313 games). Domestic Big 5 predictions confirmed
identical with European games loaded. Calibration was shaky on these small samples (worst bucket 15.0 on
tune, 10.7 on check; check includes 2020-21 without crowds). Ideas: #1 club ratings learning from European
games: tune -0.0118 but check +0.0025, dropped (overfits); #2 league-strength season shrink: no effect,
dropped. A calibration stretch fit on the check seasons improved log loss by 0.0011 (< 0.002), not applied.

**Final exam, run once 2026-10-21** (domestic settings `soccer-v2-20261019`, tuned before the soccer exam;
full numbers in `final_runs.jsonl`):

| Test | Result (2022-23 to 2025-26, 521 Champions League games) |
|---|---|
| 1. Works at all | PASS: log loss 0.9455 vs baseline 1.0303 |
| 2. Honest percentages | PASS: worst bucket with 50+ games off by 5.0 |
| 3. Vs. market | model 0.9455 / Brier 0.5590 / RPS 0.2032 vs market 0.9208 / 0.5419 / 0.1952 (521 games) |
| 4. Made money? | **FAIL** (narrowly): 354 flagged bets, 127 won, -3.5 units, -1.0% |

**Verdict:** works and is calibrated, trails the market, no money edge (the closest to break-even of
any exam so far). Goes live with flags paper only / Low confidence. Refit on 2016-2026 with the live
domestic settings: `ucl-v1-refit-20261021` (league strength learning rate 0.034, European home
advantage 0.275 log-goals).

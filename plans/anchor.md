# Market-anchored engine (QUEUE items 3 + 4): plan and pre-registration

Written 2026-10-23 after the factor study (`backtest_results/factor_study.md`), **before** any anchor
model was fit. Status: tune/check fitting approved by Talal ("get started"); going live needs his
separate OK (it would change every probability: a MAJOR version).

## Why items 3 and 4 are one model
The factor study found that, once the market price is known, the engine's extra information is small
(log-odds weight about 0 to 0.15) and its large disagreements with the market are mostly error. The
"market anchor" (item 3) and "edge recalibration" (item 4) are therefore the same thing: how far to
trust the engine's disagreement with the market, as a function of its size and the time of season.

## The model (per sport), in log-odds
Let `d = engine_logit − market_logit` (the engine's disagreement).

    anchored_logit = market_logit + c + w·d + w_early·early·d + w_big·d·|d| + w_fav·fav_size

- `w`: the basic anchor weight (0 = pure market, 1 = pure engine). Expected 0 to 0.2.
- `w_early·early·d`: more or less trust in the engine early in the season (`early` = 1 at a team's
  first game, fading to 0 by the sport's EARLY_GAMES count). Tests the queue's "lean on the market
  early" idea.
- `w_big·d·|d|`: a nonlinear term. Negative means big disagreements are trusted *less* than small ones
  (edge recalibration). Zero means trust scales linearly.
- `w_fav·fav_size`: the favorite-longshot term the NFL study flagged. (`fav_size` = |market_logit|.)
- `c`: a small intercept.

Soccer (three outcomes): the same blend applied to each outcome's log probability relative to the
market's, then renormalized (a geometric blend); one `w` for all three, plus the `w_big` term.

## Fitting and testing (pre-registered)
- Terms are added by forward selection on the tune seasons and kept only if they improve check-season
  log loss by >= 0.001 (same bar as the factor study). `w` alone is always kept.
- Seasons: the same tune/check splits as the factor study (college sports on their priced seasons,
  with the same caveat).
- Report per sport on the check seasons: log loss of market / engine / anchored; number of flagged
  bets (4+ point edge vs the market) under the engine and under the anchored model, with their ROI
  at the average listed price; closing-line value where a closing price exists (soccer).
- **The final-exam seasons are not re-run.** They were used once for the engine models; a second
  exam on them is not an untouched test. The anchored model's real test is live: it is logged as a
  shadow model (`market_anchor_v2_<sport>`) with its fitted weights, and judged by the existing
  shadow promotion bar (150+ games, better log loss AND better CLV than the engine).

## What "success" would look like
The anchored model should beat the engine's check-season log loss in every sport (almost certain,
since it starts from the market) and, if it has any value as a betting tool, its few remaining flags
should show positive closing-line value live. If flags all but vanish, that is a true finding: our
edges were noise, and Claude's sourced news is the only place an edge can come from.

## Files
`backtest_anchor.py` (fit, report; saves weights under `anchor` in `model_params.json`),
`backtest_results/anchor.md` (results), then `shadow.py` for the live shadow challengers (separate
step, pre-registered in `backtest_results/shadow_challengers.md` before logging starts).

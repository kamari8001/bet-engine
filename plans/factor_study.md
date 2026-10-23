# Factor study: which pre-game factors predict winning, and which predict the market's errors

Written and committed 2026-10-23 **before** the study ran, so the questions, factors, and pass bars
can't be bent to the results. Read-only: it changes no probabilities. Its findings feed the model
accuracy program in QUEUE.md (market anchor, edge recalibration).

## Two questions, two regressions (per sport)

**(a) What predicts winning?** A penalized logistic regression (ridge: coefficients shrunk toward 0
so overlapping factors don't inflate each other) predicting "home team wins" from the factors.

**(b) What does the market miss?** The same regression with the market's no-vig home probability
built in as a fixed starting point (an *offset*, coefficient held at 1). Any factor that still earns
a coefficient is one the market underweights. This is the question that matters for betting.

Soccer is three-way; here "home wins" vs "doesn't" is used for both questions, with the draw treated
as a loss for the home side. A three-way version is a later refinement.

## Honesty rules (as every backtest)
- Every factor is known before kickoff and built walk-forward (ratings as they stood that morning).
- Fit on the tune seasons, judged on the check seasons of each sport's criteria file
  (NFL/college football `criteria.md`; basketball `criteria_basketball.md`; soccer `criteria_soccer.md`).
  Final-exam seasons are not used.
- Features are standardized on the tune seasons (so coefficients are comparable: "a one standard
  deviation increase in this factor changes the log-odds by w").

## Factors (home minus away where it's a difference)
Common: engine logit (the base model's home probability, as log-odds); market logit (question (a)
only; in (b) it's the offset); home field (0 for neutral); rest-day difference; games played so far
this season (early-season indicator); last-5 average margin difference (recent form); the size of the
favorite (|market logit|, to test favorite-longshot bias).
NFL: starting-QB rating difference; season-to-date offensive EPA difference.
College football: preseason talent, returning production and last season's SP+ differences.
Soccer: season-to-date shots-on-target difference; league strength difference (Champions League games
excluded here; domestic leagues only); line movement from the pre-close to the closing price
(known only at the close, so for (b) the offset is the *pre-close* price: this tests whether the
market's own late movement carries information beyond its opening price).

## What counts as a finding (pre-registered)
A factor "matters" for a question if forward selection (adding factors one at a time, keeping the one
that most improves check-season log loss) picks it, it improves check-season log loss by at least
0.001 over the model without it, and its coefficient has the same sign on tune and check seasons.
For question (b), the comparison baseline is the market alone; the headline number is how much the
best factor set beats the market's log loss on the check seasons (expected: little or nothing).

## PCA (diagnostic only)
A principal component analysis of the standardized factors reports how many components explain 90%
of their variance and each component's main loadings. It says how redundant the factors are; it is
not used to pick factors (components blend factors, which hides which one matters).

## Output
`backtest_results/factor_study.md`: per sport, the (a) and (b) coefficient tables, forward-selection
order with check-season gains, the market and engine baselines, and the PCA summary.
`python3 factor_study.py <sport>` reproduces it.

## Amendment (2026-10-23, at run time)
College football has sportsbook prices only from 2021 and college basketball only from 2023, so their
pre-registered tune seasons hold no priced games (the study crashed on them). They were rerun on their
priced seasons split in date order (football 2021-23 / 2024-25; basketball 2023-24 / 2025-26). Those
seasons overlap the sports' final exams, so their results are information, not a pre-registered test.
Also: the planned "league strength difference" factor for soccer is always 0 in domestic games (both
clubs share a league), so it was dropped.

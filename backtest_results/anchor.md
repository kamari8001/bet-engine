# Market-anchored engine: tune/check results

Plan: `plans/anchor.md`. Produced by `backtest_anchor.py`. Flagged bets use the average listed price. Run 2026-10-23.

## nfl: tune 2006-2018, check 2019-2022

Fitted terms: {"c": -0.01431, "w": 0.26068}

Check-season log loss: market 0.6088 | engine 0.6326 | anchored 0.6119 (1100 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 633 | 229 | -84.3 | -13.3% |
| anchored | 56 | 24 | +4.7 | +8.3% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| w | 0.6119 |  |

Saved as anchor-v1-20261023 under nfl.anchor in model_params.json.

## nba: tune 2015-2020, check 2021-2023

Fitted terms: {"c": -0.00852, "w": -0.01732}

Check-season log loss: market 0.6173 | engine 0.6397 | anchored 0.6173 (3814 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 2489 | 1012 | -62.1 | -2.5% |
| anchored | 0 | 0 | +0.0 | +0.0% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| w | 0.6173 |  |

Saved as anchor-v1-20261023 under nba.anchor in model_params.json.

## soccer_club: tune 2013-2019, check 2020-2022

Fitted terms: {"w": -0.19}

Check-season log loss: market 0.9781 | engine 0.9909 | anchored 0.9777 (5376 games)

| model | flagged bets | won | units | ROI | avg CLV (games with a close) |
|---|---|---|---|---|---|
| engine | 2288 | 719 | -229.9 | -10.0% | -0.09 pts (2288) |
| anchored | 11 | 4 | -2.9 | -26.2% | -2.00 pts (11) |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| w | 0.9777 |  |

Saved as anchor-v1-20261023 under soccer_club.anchor in model_params.json.

## ncaaf: tune 2021-2023, check 2024-2025

Priced seasons only (overlap the final exam): information, not a pre-registered test.

Fitted terms: {"c": 0.00864, "w": 0.07962}

Check-season log loss: market 0.5155 | engine 0.5327 | anchored 0.5154 (1694 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 927 | 421 | -53.4 | -5.8% |
| anchored | 0 | 0 | +0.0 | +0.0% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| w | 0.5154 |  |

Saved as anchor-v1-20261023 under ncaaf.anchor in model_params.json.

## ncaab: tune 2023-2024, check 2025-2026

Priced seasons only (overlap the final exam): information, not a pre-registered test.

Fitted terms: {"c": 0.08874, "w": -0.11036, "w_big": 0.23676}

Check-season log loss: market 0.5349 | engine 0.5515 | anchored 0.5324 (9876 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 5798 | 2923 | -250.6 | -4.3% |
| anchored | 356 | 194 | +166.0 | +46.6% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| w | 0.5342 |  |
| w_big | 0.5324 | +0.0018 |

Saved as anchor-v1-20261023 under ncaab.anchor in model_params.json.

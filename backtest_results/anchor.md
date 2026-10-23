# Market-anchored engine: tune/check results

Plan: `plans/anchor.md`. Produced by `backtest_anchor.py`. Flagged bets use the average listed price. Run 2026-10-23.

## nfl: tune 2006-2018, check 2019-2022

Fitted terms: {"c": -0.135, "w_fav": 0.16473}

Check-season log loss: market 0.6088 | engine 0.6326 | anchored 0.6072 (1100 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 633 | 229 | -84.3 | -13.3% |
| anchored | 0 | 0 | +0.0 | +0.0% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| (market only) | 0.6082 |  |
| w_fav | 0.6072 | +0.0011 |

Saved as anchor-v1-20261023 under nfl.anchor in model_params.json.

## nba: tune 2015-2020, check 2021-2023

Fitted terms: {"c": -0.00763}

Check-season log loss: market 0.6173 | engine 0.6397 | anchored 0.6173 (3814 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 2489 | 1012 | -62.1 | -2.5% |
| anchored | 0 | 0 | +0.0 | +0.0% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| (market only) | 0.6173 |  |

Saved as anchor-v1-20261023 under nba.anchor in model_params.json.

## soccer_club: tune 2013-2019, check 2020-2022

Fitted terms: {}

Check-season log loss: market 0.9781 | engine 0.9909 | anchored 0.9781 (5376 games)

| model | flagged bets | won | units | ROI | avg CLV (games with a close) |
|---|---|---|---|---|---|
| engine | 2288 | 719 | -229.9 | -10.0% | -0.09 pts (2288) |
| anchored | 0 | 0 | +0.0 | +0.0% |  (0) |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| (market only) | 0.9781 |  |

Saved as anchor-v1-20261023 under soccer_club.anchor in model_params.json.

## ncaaf: tune 2021-2023, check 2024-2025

Priced seasons only (overlap the final exam): information, not a pre-registered test.

Fitted terms: {"c": 0.01133}

Check-season log loss: market 0.5155 | engine 0.5327 | anchored 0.5154 (1694 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 927 | 421 | -53.4 | -5.8% |
| anchored | 0 | 0 | +0.0 | +0.0% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| (market only) | 0.5154 |  |

Saved as anchor-v1-20261023 under ncaaf.anchor in model_params.json.

## ncaab: tune 2023-2024, check 2025-2026

Priced seasons only (overlap the final exam): information, not a pre-registered test.

Fitted terms: {"c": 0.10167}

Check-season log loss: market 0.5234 | engine 0.5430 | anchored 0.5234 (8554 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 4974 | 2520 | -397.9 | -8.0% |
| anchored | 0 | 0 | +0.0 | +0.0% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| (market only) | 0.5234 |  |

Saved as anchor-v1-20261023 under ncaab.anchor in model_params.json.

## ncaaf: tune 2021-2023, check 2024-2025

Priced seasons only (overlap the final exam): information, not a pre-registered test.

Fitted terms: {"c": 0.01688}

Check-season log loss: market 0.5158 | engine 0.5327 | anchored 0.5156 (1694 games)

| model | flagged bets | won | units | ROI |
|---|---|---|---|---|
| engine | 929 | 423 | -48.9 | -5.3% |
| anchored | 0 | 0 | +0.0 | +0.0% |

Forward selection (check-season log loss after each kept term):

| term | check log loss | gain |
|---|---|---|
| (market only) | 0.5156 |  |

Saved as anchor-v1-20261023 under ncaaf.anchor in model_params.json.

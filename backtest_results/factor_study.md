# Factor study results

Plan: `plans/factor_study.md` (pre-registered 2026-10-23). Produced by `factor_study.py`. Coefficients are
per standard deviation of each factor, in log-odds. Ridge penalty 1.0. Run 2026-10-23.

## Summary (all five sports)

| Sport | Seasons (tune / check) | Market alone | Engine alone | Engine's weight next to the market (b) | Market misses |
|---|---|---|---|---|---|
| NFL | 2006-18 / 2019-22 | 0.608 | 0.633 | +0.02 tune, -0.17 check | favorite size (+0.0011, barely) |
| College football* | 2021-23 / 2024-25 | 0.515 | 0.534 | -0.12 tune, +0.10 check | nothing (after the line fix) |
| NBA | 2015-20 / 2021-23 | 0.617 | 0.642 | +0.00 tune, -0.01 check | nothing |
| College basketball* | 2023-24 / 2025-26 | 0.522 | 0.543 | +0.18 tune, +0.16 check | engine (+0.0013; neutral-site games excluded) |
| Club soccer | 2013-19 / 2020-22 | 0.604 | 0.613 | +0.05 tune, +0.04 check | nothing |

\* Priced seasons only, split in date order; they overlap the final-exam seasons (information, not a
pre-registered test). Numbers are check-season log loss (lower is better).

**What this says:**
1. **The market price is the only factor that matters for predicting winners.** In every sport, forward
   selection picks the market first and then stops: once the market is in, no other factor (not the
   engine, not rest, form, home field, QB ratings, EPA, or preseason data) improves check-season log
   loss by even 0.001. Those factors do predict winning, but the market already prices them.
2. **The engine adds almost nothing on top of the market.** Its coefficient next to the market is about
   zero in the NFL, NBA and soccer, and flips sign between tune and check in the NFL and college
   football (noise). College basketball is the one exception: a stable +0.15, and the only sport where
   the engine passes the "market misses it" bar. That is the sport with the thinnest, slowest market.
3. **The one market inefficiency with any support is favorite size in the NFL** (+0.08 tune, +0.12
   check): big favorites win slightly more often than priced. The gain is tiny (0.0011) and the usual
   favorite-longshot bias is well known, so the price may already have moved since.
4. **Soccer line movement:** +1.0 on check seasons and 0 on tune seasons, because closing prices exist
   only from 2019-20 (the check period). Where both prices exist, the closing price explains everything
   the opening price doesn't; the late move carries information, but it's only known at close.
5. **PCA:** the engine, the market and the strength-type factors all load on one component (40-47% of
   variance): they measure the same thing, team strength, which the market measures best.

**Consequence for the accuracy program (QUEUE.md items 3 and 4):** the best anchor weight is
mostly market (engine weight ~0 to 0.15 in log-odds), and the engine's disagreements with the market
are mostly its own error. Items 3 and 4 are the same model: `p = market + w x (engine - market)` in
log-odds, with w fit per sport. Under that model, flagged bets will be rare. See `plans/anchor.md`.

## nfl: 3327 tune games (2006-2018), 1100 check games (2019-2022)

Baselines (check-season log loss): market alone 0.6081, engine alone 0.6330
Home-win rate: tune 0.571, check 0.527

### (a) What predicts winning

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| market_logit | +0.621 | +1.130 | yes |
| engine_logit | +0.206 | -0.410 | no |
| home | +0.063 | +0.015 | yes |
| rest_diff | +0.041 | -0.032 | no |
| games_played | -0.071 | +0.079 | no |
| form_diff | -0.060 | -0.072 | yes |
| fav_size | +0.100 | +0.117 | yes |
| qb_diff | +0.023 | +0.154 | yes |
| epa_diff | +0.044 | +0.064 | yes |

All factors, check-season log loss: 0.6125

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6955 | +0.0000 |
| 1 | market_logit | 0.6081 | +0.0874 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** market_logit

### (b) What the market misses (market log-odds as a fixed offset)

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| engine_logit | +0.017 | -0.167 | no |
| home | +0.064 | +0.018 | yes |
| rest_diff | +0.046 | -0.035 | no |
| games_played | -0.075 | +0.076 | no |
| form_diff | -0.069 | -0.061 | yes |
| fav_size | +0.082 | +0.123 | yes |
| qb_diff | +0.044 | +0.147 | yes |
| epa_diff | +0.024 | +0.091 | yes |

All factors, check-season log loss: 0.6094

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6082 | +0.0000 |
| 1 | fav_size | 0.6072 | +0.0011 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** fav_size

### PCA diagnostic

6 of 9 components explain 90% of the factors' variance.

- component 1: 44% of variance; main loadings engine_logit -0.48, market_logit -0.47, qb_diff -0.41
- component 2: 12% of variance; main loadings games_played +0.69, rest_diff +0.55, home -0.43
- component 3: 11% of variance; main loadings home +0.76, rest_diff +0.62, epa_diff -0.13
- component 4: 10% of variance; main loadings games_played -0.65, rest_diff +0.55, home -0.47

## ncaaf: 2239 tune games (2021-2023), 1694 check games (2024-2025)

**Deviation from the plan:** this sport has sportsbook prices only in recent seasons, so the priced seasons are split in date order (tune then check). They overlap the sport's final-exam seasons, so treat this as information, not a pre-registered test.

Baselines (check-season log loss): market alone 0.5154, engine alone 0.5343
Home-win rate: tune 0.569, check 0.605

### (a) What predicts winning

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| market_logit | +1.350 | +1.256 | yes |
| engine_logit | -0.193 | +0.095 | no |
| home | -0.003 | +0.032 | no |
| rest_diff | +0.000 | +0.000 | no |
| games_played | -0.059 | +0.035 | no |
| form_diff | +0.163 | +0.034 | yes |
| fav_size | -0.003 | +0.186 | no |
| talent_diff | +0.014 | -0.266 | no |
| returning_diff | +0.130 | +0.005 | yes |
| prev_sp_diff | -0.037 | +0.059 | no |

All factors, check-season log loss: 0.5181

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6736 | +0.0000 |
| 1 | market_logit | 0.5154 | +0.1582 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** market_logit

### (b) What the market misses (market log-odds as a fixed offset)

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| engine_logit | -0.116 | +0.101 | no |
| home | -0.002 | +0.032 | no |
| rest_diff | +0.000 | +0.000 | no |
| games_played | -0.061 | +0.035 | no |
| form_diff | +0.170 | +0.035 | yes |
| fav_size | -0.000 | +0.186 | no |
| talent_diff | +0.018 | -0.266 | no |
| returning_diff | +0.128 | +0.005 | yes |
| prev_sp_diff | -0.028 | +0.059 | no |

All factors, check-season log loss: 0.5179

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.5156 | +0.0000 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** none

### PCA diagnostic

6 of 10 components explain 90% of the factors' variance.

- component 1: 39% of variance; main loadings engine_logit -0.51, market_logit -0.51, prev_sp_diff -0.43
- component 2: 15% of variance; main loadings games_played -0.66, home +0.62, fav_size +0.27
- component 3: 12% of variance; main loadings returning_diff -0.88, talent_diff +0.29, home -0.23
- component 4: 10% of variance; main loadings fav_size -0.62, home +0.41, talent_diff -0.40

## nba: 7586 tune games (2015-2020), 3814 check games (2021-2023)

Baselines (check-season log loss): market alone 0.6173, engine alone 0.6415
Home-win rate: tune 0.579, check 0.559

### (a) What predicts winning

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| market_logit | +1.033 | +0.984 | yes |
| engine_logit | -0.018 | +0.004 | no |
| home | -0.007 | +0.179 | no |
| rest_diff | -0.030 | +0.026 | no |
| games_played | +0.017 | -0.017 | no |
| form_diff | -0.014 | -0.057 | yes |
| fav_size | -0.035 | +0.020 | no |

All factors, check-season log loss: 0.6177

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6870 | +0.0000 |
| 1 | market_logit | 0.6173 | +0.0698 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** market_logit

### (b) What the market misses (market log-odds as a fixed offset)

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| engine_logit | +0.004 | -0.008 | no |
| home | -0.007 | +0.179 | no |
| rest_diff | -0.030 | +0.026 | no |
| games_played | +0.017 | -0.017 | no |
| form_diff | -0.012 | -0.057 | yes |
| fav_size | -0.031 | +0.018 | no |

All factors, check-season log loss: 0.6176

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6173 | +0.0000 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** none

### PCA diagnostic

5 of 7 components explain 90% of the factors' variance.

- component 1: 40% of variance; main loadings market_logit +0.56, engine_logit +0.56, form_diff +0.48
- component 2: 15% of variance; main loadings games_played +0.77, rest_diff -0.51, home +0.37
- component 3: 14% of variance; main loadings home +0.71, rest_diff +0.67, form_diff -0.18
- component 4: 14% of variance; main loadings home -0.60, games_played +0.59, rest_diff +0.48

## ncaab: 9176 tune games (2023-2024), 8554 check games (2025-2026)

**Deviation from the plan:** this sport has sportsbook prices only in recent seasons, so the priced seasons are split in date order (tune then check). They overlap the sport's final-exam seasons, so treat this as information, not a pre-registered test.

Baselines (check-season log loss): market alone 0.5218, engine alone 0.5429
Home-win rate: tune 0.654, check 0.635

### (a) What predicts winning

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| market_logit | +1.208 | +1.420 | yes |
| engine_logit | +0.172 | -0.032 | no |
| home | +0.000 | +0.000 | no |
| rest_diff | -0.026 | -0.031 | yes |
| games_played | -0.025 | +0.007 | no |
| form_diff | +0.002 | +0.041 | yes |
| fav_size | -0.018 | -0.063 | yes |

All factors, check-season log loss: 0.5220

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6569 | +0.0000 |
| 1 | market_logit | 0.5218 | +0.1351 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** market_logit

### (b) What the market misses (market log-odds as a fixed offset)

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| engine_logit | +0.178 | +0.159 | yes |
| home | +0.000 | +0.000 | no |
| rest_diff | -0.026 | -0.030 | yes |
| games_played | -0.025 | -0.001 | yes |
| form_diff | +0.002 | +0.037 | yes |
| fav_size | -0.017 | -0.024 | yes |

All factors, check-season log loss: 0.5220

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.5234 | +0.0000 |
| 1 | engine_logit | 0.5221 | +0.0013 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** engine_logit

### PCA diagnostic

4 of 7 components explain 90% of the factors' variance.

- component 1: 51% of variance; main loadings market_logit +0.54, engine_logit +0.53, fav_size +0.46
- component 2: 17% of variance; main loadings rest_diff -1.00, games_played +0.05, fav_size -0.03
- component 3: 16% of variance; main loadings games_played +0.90, form_diff +0.39, fav_size -0.14
- component 4: 10% of variance; main loadings form_diff -0.68, fav_size +0.61, games_played +0.38

## soccer_club: 12782 tune games (2013-2019), 5376 check games (2020-2022)

Baselines (check-season log loss): market alone 0.6035, engine alone 0.6130
Home-win rate: tune 0.458, check 0.422

### (a) What predicts winning

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| market_logit | +1.009 | +1.001 | yes |
| engine_logit | -0.072 | -0.080 | yes |
| home | +0.000 | +0.000 | no |
| rest_diff | -0.006 | +0.001 | no |
| games_played | +0.020 | +0.034 | yes |
| form_diff | +0.018 | -0.019 | no |
| fav_size | +0.047 | -0.007 | no |
| sot_diff | +0.008 | -0.018 | no |
| line_move | +0.000 | +1.023 | no |

All factors, check-season log loss: 0.6036

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6835 | +0.0000 |
| 1 | market_logit | 0.6035 | +0.0800 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** market_logit

### (b) What the market misses (market log-odds as a fixed offset)

| factor | coef (tune) | coef (check) | same sign |
|---|---|---|---|
| engine_logit | +0.046 | +0.037 | yes |
| home | +0.000 | +0.000 | no |
| rest_diff | -0.006 | +0.001 | no |
| games_played | +0.022 | +0.034 | yes |
| form_diff | +0.023 | -0.015 | no |
| fav_size | +0.039 | -0.014 | no |
| sot_diff | +0.021 | -0.009 | no |
| line_move | +0.000 | +1.015 | no |

All factors, check-season log loss: 0.6039

Forward selection (each step adds the factor that most improves check-season log loss):

| step | factor | check log loss | gain |
|---|---|---|---|
| 0 | (none) | 0.6036 | +0.0000 |

**Factors that matter (selected, gain >= 0.001, same sign on tune and check):** none

### PCA diagnostic

5 of 9 components explain 90% of the factors' variance.

- component 1: 47% of variance; main loadings market_logit -0.52, engine_logit -0.52, sot_diff -0.47
- component 2: 14% of variance; main loadings games_played +0.98, fav_size +0.17, rest_diff -0.11
- component 3: 14% of variance; main loadings rest_diff +0.99, games_played +0.12, fav_size -0.04
- component 4: 12% of variance; main loadings fav_size -0.95, games_played +0.17, form_diff -0.17

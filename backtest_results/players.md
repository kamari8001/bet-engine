# Player-impact feature: tune/check results

Plan: `plans/player_impact.md`. Produced by `backtest_players.py`. Seasons are labeled by the year they end.

## Summary (2026-10-23)
- **Data:** ESPN box scores for 15,495 NBA games (2014-15 to now). 689 games have no usable box score on
  ESPN (minutes shown as "--"), almost all in 2014-15 to 2017-18 (about 13% of those seasons); the player
  feature is switched off for those games ("absences unknown"), never guessed.
- **Ideas (pre-registered order and bar):** #1 minutes only: KEEP (check 0.6433 -> 0.6386). #2 production
  rating: KEEP (-> 0.6340; calibration's worst bucket 13.9 -> 5.3). #3 adding plus-minus: drop (+0.0001).
  #4 self-correcting absence coefficient: drop (+0.0001; its learning rate tuned to zero).
- **Kept: idea 2** (`players_best.json`). Second look on the exam seasons agrees (0.6096 -> 0.6002).
- **Against the market:** the gap shrinks by about a third, but the model still trails the market, and
  flagged bets still lose. Beside the market price, the player-aware engine adds nothing on later seasons
  (weight 0.05, log loss unchanged): historical lines already price who's out. Any live edge would have
  to come from timing (reacting to news before the line moves), which only live closing-line value can show.
- **Starting-point note:** the first tune started the absence coefficient at 3.0, which was about three
  times too big (untuned log loss 0.6238); the tuner brought it to 0.75 (idea 1) and 1.22 (idea 2).

## Run 2026-10-23 18:21 UTC: ['ablate']

base: tune 0.6112, check 0.6433, worst bucket 13.9, vs market 0.6433 / 0.6173, flags 2557 ROI -3.3%
idea 1: {"abs_coef": 0.7481} -> tune 0.6100, check 0.6386 (-0.0046 vs best so far), worst bucket 10.1, vs market 0.6386 / 0.6173, flags 2446 ROI -2.9% -> KEEP
idea 2: {"alpha": 0.074, "season_regress": 0.675, "repl_z": -0.4219, "abs_coef": 1.2189} -> tune 0.6052, check 0.6340 (-0.0046 vs best so far), worst bucket 5.3, vs market 0.6340 / 0.6173, flags 2330 ROI -2.1% -> KEEP
idea 3: {"alpha": 0.074, "season_regress": 0.675, "repl_z": -0.4219, "w_imp": 0.04, "abs_coef": 1.2189} -> tune 0.6052, check 0.6339 (-0.0001 vs best so far), worst bucket 5.3, vs market 0.6339 / 0.6173, flags 2330 ROI -2.2% -> drop
idea 4: {"alpha": 0.0687, "season_regress": 0.6124, "repl_z": -0.3876, "w_imp": 0.0626, "abs_coef": 1.2721, "abs_k": 0.0} -> tune 0.6052, check 0.6339 (-0.0001 vs best so far), worst bucket 5.0, vs market 0.6339 / 0.6173, flags 2324 ROI -2.6% -> drop

Best kept: 2 (check 0.6340)

## Run 2026-10-23 18:52 UTC: ['look']

base: tune 0.6112, check 0.6433, worst bucket 13.9, vs market 0.6433 / 0.6173, flags 2557 ROI -3.3%

## Second look 2026-10-23 18:52 UTC: idea 2 on the exam seasons 2024-2026

These seasons were already used once (the nba-v1 final exam), so this is a second look, not an untouched test. Settings tuned on tune seasons only.

| model | log loss | worst bucket | model vs market log loss | flagged bets | ROI |
|---|---|---|---|---|---|
| team model only (nba-v1 pre-exam) | 0.6096 | 5.0 | 0.6096 vs 0.5799 | 2513 | -8.8% |
| with players (idea 2) | 0.6002 | 5.8 | 0.6002 vs 0.5799 | 2334 | -7.0% |

Information only: does the engine add anything beside the market price? Fit market + c + w x (engine - market) in log-odds on the tune seasons, test on later seasons (w = 0 means the engine adds nothing).

| model | test seasons | w | market alone | market + engine | games |
|---|---|---|---|---|---|
| team model only | 2021-2023 | -0.002 | 0.6173 | 0.6173 | 3814 |
| team model only | 2024-2026 | -0.002 | 0.5799 | 0.5799 | 3962 |
| with players | 2021-2023 | +0.054 | 0.6173 | 0.6174 | 3814 |
| with players | 2024-2026 | +0.054 | 0.5799 | 0.5801 | 3962 |

## Refit 2026-10-23 19:06 UTC: nba-v2-refit-20261023 (pending: live after `backtest_players.py apply`)

Team {"k": 0.02954, "hfa_start": 1.89925, "hfa_rate": 0.0, "regress": 0.4478, "cap": 30.24087, "sigma": 11.00501, "new_team": 0.0, "avg_rate": 0.002, "rest_coef": 0.61971, "rest_cap": 3, "abs_coef": 1.03099}; players {"alpha": 0.06973, "season_regress": 0.597, "repl_z": -0.76494}.
In-sample on 2015-2026 (used for fitting, so NOT a test): log loss 0.6095, worst bucket 2.0, vs market 0.6095 / 0.5941, flags 8905 ROI -4.6%. Replaces nba-v1-refit-20261019.

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

## Run 2026-10-23 20:08 UTC: ['early']

base: tune 0.6112, check 0.6433, worst bucket 13.9, vs market 0.6433 / 0.6173, flags 2557 ROI -3.3%

## Early-season ideas 2026-10-23 20:08 UTC (plans/player_early_season.md)

idea 2 (starting point): check 0.6340, worst bucket 5.3; check first 20 games 0.6587 (927), rest 0.6261 (2887)
idea 5 {"regress_to": "average"}: {"alpha": 0.0792, "season_regress": 0.3815, "repl_z": -0.2987, "abs_coef": 1.1789} -> tune 0.6057, check 0.6347 (+0.0006 vs best so far), worst bucket 5.9; first 20 games 0.6597 (+0.0010), rest 0.6266 (+0.0005); vs market 0.6347 / 0.6173, flags 2304 ROI -2.8% -> drop
idea 6 {"carry_unseen": true}: {"alpha": 0.074, "season_regress": 0.5417, "repl_z": -0.3924, "abs_coef": 1.2189} -> tune 0.6051, check 0.6340 (-0.0001 vs best so far), worst bucket 5.2; first 20 games 0.6590 (+0.0002), rest 0.6259 (-0.0002); vs market 0.6340 / 0.6173, flags 2330 ROI -2.3% -> drop

Kept: none (check 0.6340)

## Run 2026-10-26 00:12 UTC: ['moves']

base: tune 0.6112, check 0.6433, worst bucket 13.9, vs market 0.6433 / 0.6173, flags 2557 ROI -3.3%

## Player moves 2026-10-26 00:13 UTC (plans/nba_roster_moves.md)

idea 2 (starting point): check 0.6340, worst bucket 5.3; first 20 games 0.6587 (927), rest 0.6261 (2887)
idea 7: move_coef 0.4012, regress 0.3079 (was 0.3079) -> tune 0.6047 (-0.0005), check 0.6328 (-0.0013), worst bucket 6.2; first 20 games 0.6578 (-0.0009), rest 0.6248 (-0.0014); vs market 0.6328 / 0.6173 (was 0.6340), flags 2278 ROI -3.2% (was 2330, -2.1%) -> KEEP

Sanity check, moves seen per season (and the three biggest by value carried):
- 2014-15: 85 moves; Brandon Knight MIL -> PHX (2015-02-20, value +0.4 pts); Isaiah Thomas PHX -> BOS (2015-02-22, value +0.4 pts); D.J. Augustin DET -> OKC (2015-02-21, value +0.3 pts)
- 2015-16: 170 moves; LaMarcus Aldridge POR -> SA (2015-10-28, value +0.6 pts); Greg Monroe DET -> MIL (2015-10-28, value +0.5 pts); Tyson Chandler DAL -> PHX (2015-10-28, value +0.3 pts)
- 2016-17: 169 moves; Kevin Durant OKC -> GS (2016-10-25, value +1.4 pts); Lou Williams LAL -> HOU (2017-02-25, value +0.9 pts); Dwyane Wade MIA -> CHI (2017-04-16, value +0.8 pts)
- 2017-18: 190 moves; Chris Paul LAC -> HOU (2017-10-17, value +1.4 pts); Paul George IND -> OKC (2017-10-19, value +1.4 pts); Kyrie Irving CLE -> BOS (2017-10-17, value +1.2 pts)
- 2018-19: 234 moves; LeBron James CLE -> LAL (2018-10-18, value +1.8 pts); Dwight Howard CHA -> WSH (2018-11-02, value +0.7 pts); Tobias Harris LAC -> PHI (2019-02-08, value +0.7 pts)
- 2019-20: 230 moves; Kawhi Leonard TOR -> LAC (2019-10-22, value +1.6 pts); Kemba Walker CHA -> BOS (2019-10-23, value +1.3 pts); Mike Conley MEM -> UTAH (2019-10-23, value +1.3 pts)
- 2020-21: 233 moves; Nikola Vucevic ORL -> CHI (2021-03-27, value +1.0 pts); Christian Wood DET -> HOU (2020-12-26, value +0.9 pts); Chris Paul OKC -> PHX (2020-12-23, value +0.8 pts)
- 2021-22: 313 moves; Russell Westbrook WSH -> LAL (2021-10-19, value +1.1 pts); Domantas Sabonis IND -> SAC (2022-02-09, value +1.0 pts); Jonas Valanciunas MEM -> NO (2021-10-20, value +0.9 pts)
- 2022-23: 208 moves; Kevin Durant BKN -> PHX (2023-03-01, value +1.4 pts); Kyrie Irving BKN -> DAL (2023-02-08, value +1.2 pts); Dejounte Murray SA -> ATL (2022-10-19, value +1.1 pts)
- 2023-24: 256 moves; Damian Lillard POR -> MIL (2023-10-26, value +1.8 pts); Kristaps Porzingis WSH -> BOS (2023-10-25, value +1.2 pts); Pascal Siakam TOR -> IND (2024-01-19, value +0.8 pts)
- 2024-25: 229 moves; Anthony Davis LAL -> DAL (2025-02-08, value +1.2 pts); Luka Doncic DAL -> LAL (2025-02-10, value +1.1 pts); DeMar DeRozan CHI -> SAC (2024-10-24, value +1.0 pts)
- 2025-26: 238 moves; James Harden LAC -> CLE (2026-02-07, value +0.9 pts); Kevin Durant PHX -> HOU (2025-10-21, value +0.9 pts); Nikola Vucevic CHI -> BOS (2026-02-04, value +0.6 pts)
- 2026-27: 103 moves; Giannis Antetokounmpo MIL -> MIA (2026-10-21, value +1.3 pts); Kawhi Leonard LAC -> TOR (2026-10-21, value +1.3 pts); LaMelo Ball CHA -> MIN (2026-10-21, value +0.8 pts)

Second look on the exam seasons 2024-2026 (already used; NOT an untouched test): log loss 0.6002 -> 0.5993; vs market 0.6002 -> 0.5993 (market 0.5799); flags ROI -7.0% -> -7.8%

Decision: KEEP (bar: check better by >= 0.001, calibration rule).

## Refit 2026-10-26 00:17 UTC: nba-v3-refit-20261026 (pending: live after `backtest_players.py apply`)

Team {"k": 0.02747, "hfa_start": 1.89925, "hfa_rate": 0.0, "regress": 0.47915, "cap": 30.24087, "sigma": 11.00501, "new_team": 0.0, "avg_rate": 0.002, "rest_coef": 0.61971, "rest_cap": 3, "move_coef": 0.55501, "abs_coef": 1.07223}; players {"alpha": 0.05596, "season_regress": 0.52775, "repl_z": -0.73434, "moves": true}.
In-sample on 2015-2026 (used for fitting, so NOT a test): log loss 0.6085, worst bucket 2.3, vs market 0.6085 / 0.5941, flags 8592 ROI -5.2%. Replaces nba-v2-refit-20261023.

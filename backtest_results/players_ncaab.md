# Player-impact feature: tune/check results

Plan: `plans/player_impact.md`. Produced by `backtest_players.py`.

## Run 2026-10-24 02:55 UTC: ['ablate']

base: tune 0.5155, check 0.5125, worst bucket 5.9, vs market 0.5286 / 0.5164, flags 2999 ROI -3.6%
idea 1: {"abs_coef": 0.1582} -> tune 0.5155, check 0.5124 (-0.0001 vs best so far), worst bucket 5.7, vs market 0.5285 / 0.5164, flags 2989 ROI -3.6% -> drop
idea 2: {"alpha": 0.1113, "season_regress": 0.9136, "repl_z": -0.2992, "abs_coef": 1.7045} -> tune 0.5144, check 0.5110 (-0.0015 vs best so far), worst bucket 4.1, vs market 0.5256 / 0.5164, flags 3031 ROI -2.0% -> drop

Best kept: none (check 0.5125)

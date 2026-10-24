# Soccer xG test

Plan: `plans/soccer_xg.md`. Produced by `backtest_soccer.py xg`.

## xG test 2026-10-24 03:43 UTC (plans/soccer_xg.md)

Base (pre-exam settings): tune 0.9722, check 0.9934, check RPS 0.2028, worst calibration 8.8, flagged 2580 ROI -12.4%.
With xG: xg_w 0.30962, sot_w 0.19142 -> tune 0.9718 (-0.0004), check 0.9915 (-0.0018), check RPS 0.2023, worst calibration 9.8, flagged 2485 ROI -10.1%, avg CLV -0.03 pts.
Market (avg close) on check games: {"games": 5377, "model": [0.9915292015243271, 0.5906569897430689, 0.20227842180909955], "market": [0.9753224445818957, 0.5794013356508925, 0.1972298407035277]}
Decision: drop.
Settings: {"k": 0.02306, "k_lg": 0.00021, "regress": 9e-05, "cap": 13.3, "promo_gap": 0.54431, "new_team": -0.04988, "rho": -0.06677, "home_start": 0.30241, "sot_w": 0.19142, "rest_coef": 0.02, "rest_cap": 7, "elo_w": 0.0, "xg_w": 0.30962}

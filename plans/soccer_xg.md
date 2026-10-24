# Soccer expected goals (xG) (QUEUE item 5): plan and pre-registration

Written 2026-10-24, before any xG was matched or anything fit. Talal pre-approved this plan ("any plan
is automatically approved"); putting a new model live still goes through `apply`, which Talal runs.

## Why
Expected goals values every shot by how often shots like it go in. A team's xG predicts its future
results better than its actual goals (less luck). Our soccer model already blends shots on target into
its rating updates (32% weight); xG is the better version of the same idea.

## The amendment to the soccer criteria
`criteria_soccer.md` listed xG as idea #4 "untestable here", because football-data.co.uk only has xG
from 2026-27. **Understat** (understat.com, free, no key) has per-match xG for all Big 5 leagues from
2014-15 on (checked 2026-10-24: 380 matches for 2023-24 Premier League, with xG, score and kickoff
time). So the idea becomes testable, under the soccer criteria's existing rules.

## Step 1: data
- `pull_understat.py history | current | summary`: one request per league and season (5 leagues x 13
  seasons = 65 requests, cached in `cache/understat/`), polite pacing.
- Matching to our games: same league, kickoff date within a day, same score; Understat's team names
  are mapped to ours automatically (the name that matches most of its games) and the mapping is saved
  and shown for review. A league-season counts only if 98%+ of its games match; unmatched games stay
  without xG (never guessed).
- Stored in the existing `hist_games.home_xg / away_xg` columns (history only, not the logbook).
- `current` (this season, 5 requests) joins the morning and night routines.

## Step 2: the test (pre-registered)
- **Idea #4 xG in the updates**: the "observed" goals a rating learns from become a blend of actual
  goals, shots on target (scaled to goals, as now) and xG, with one tuned weight `xg_w` (the goals weight
  is what's left: 1 - sot_w - xg_w). Games without xG use goals and shots on target as before.
- Base: the pre-exam soccer settings (`soccer-v2`, from `final_runs.jsonl`), so the comparison is like
  for like with the original ideas. `xg_w` is tuned together with the base settings on the tune seasons
  (2012-13 to 2018-19; xG exists from 2014-15).
- **Keep rule (the soccer criteria's own):** log loss better on **both** tune and check seasons (check
  = 2019-20 to 2021-22), and no per-outcome calibration bucket with 50+ games off by more than 8 points.
- Information only: RPS, Brier, gap to the market, flagged bets and their ROI, closing-line value.
- Second look on the exam seasons 2022-23 to 2025-26 (used once), labeled as such.

## Step 3: live (only if kept)
- Refit on all seasons with xG (staged in a pending file); Talal runs `apply`; version 5.0.0 (MAJOR:
  soccer probabilities change). The Champions League branch is unchanged.
- Live xG comes from Understat's current season (refreshed morning and night). Predictions note how
  many recent games lack xG; a game without it simply updates from goals and shots, as in history.
- If it's not kept: the finding is recorded, the data stays for later ideas, nothing goes live.

## Results (2026-10-24; full lines in `backtest_results/soccer_xg.md`)
Step 1 done: xG for 21,925 of 21,935 Big 5 games since 2014-15 (every league-season matched 98%+; one
2026-27 game, PSG v Rennes, has home and away swapped between ESPN and Understat and stays without xG).
Refreshed in the morning and night routines.

Step 2: **xG is not kept; nothing goes live.**
- Tuned weights: xG 0.31, shots on target 0.19 (down from 0.30), actual goals 0.50.
- Log loss improved on both tune (0.9722 -> 0.9718) and check (0.9934 -> 0.9915), and flagged-bet ROI
  on the check seasons went from -12.4% to -10.1%. Gap to the market's closing price: 0.0181 -> 0.0162.
- But the calibration rule fails: the away-win 50-60% bucket (357 games) was off by 9.8 points (the
  pre-exam model already missed the 8-point line in that bucket, at 8.8). The plan's rule says no
  bucket over 8, so it's dropped; under the gentler reading used in the NBA tests ("no worse than the
  base"), 9.8 is still worse than 8.8, so the decision is the same either way.
- The second look on the exam seasons was for a kept idea, so it wasn't run.
- The xG data and the `xg_w` switch (off) stay, for a future, separately pre-registered idea (for
  example, xG together with a calibration fix for away favorites, or a three-way shadow challenger).

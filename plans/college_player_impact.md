# College basketball player-impact model (QUEUE item 3, follow-up): plan and pre-registration

Written 2026-10-23, before any data was loaded or anything fit. Needs Talal's OK. Same design as the
NBA model that went live in v4.0.0 (`plans/player_impact.md`); this file only records what differs.

## Data checked before writing (3 CBBD calls, 2026-10-23)
- CBBD (`api.collegebasketballdata.com`, our existing key) has player box scores per game
  (`/games/players`): minutes, points, shooting, rebounds, assists, steals, blocks, turnovers, fouls,
  starter, position, and the player's ESPN id. **No plus-minus.** Game ids match our `hist_games`.
- Only players who played are listed (58 of 9,846 rows in Jan 2025 had 0 minutes), so "absent" =
  a rotation player who isn't in the box score, as in the NBA version.
- Player data goes back to 2014-15 (checked: Jan 15, 2015, ~9 players per team).
- One call returns at most 1,000 team rows (500 games). A season is ~6,000 games, so the history
  needs **about 170-200 calls** (of the key's 1,000 per month), in date windows split until each
  returns under 500 games. Daily refresh: 1-2 calls.
- ESPN has a college injury list endpoint, but it's empty in the preseason; how complete it is during
  the season is unknown until games start (Nov 3).

## Step 1: data
- `pull_ncaab_players.py history | current | summary`: box scores into the existing
  `hist_player_games` table (player id = ESPN id when given, else `cbbd:<id>`), resumable, stops on
  any CBBD error (no partial seasons saved). `current` joins the morning routine.
- Proof: games per season with box scores, players per team (~9-10), a known absence found.

## Step 2: the model (pre-registered)
- Same player ratings as the NBA (`player_model.py`, generalized by sport): game score per 36 minutes,
  recency-weighted, pulled toward replacement over the summer, rotation = 10+ minutes a game and seen
  in the last 21 days, missing value x one coefficient in the projected margin.
- Players follow their id, so transfers carry their rating to the new team once they play for it;
  freshmen start at replacement level.
- Ideas, in order: **#1 minutes only, #2 production rating.** (The NBA's #3 needs plus-minus, which
  CBBD doesn't have; #4 was rejected in the NBA test.) Each kept only if it improves check-season log
  loss by >= 0.002 over the best so far, and no 50+ game calibration bucket is off by more than 8 points
  (or more than the base model's own worst).
- Seasons as the college criteria: tune 2015-2020, check 2021-2023. Team settings: the pre-exam
  `ncaab-v1` (from `final_runs.jsonl`), so nothing tuned here saw the exam seasons.
- Information only: gap to the market (college sportsbook moneylines exist only from 2022-23, so
  the check seasons have one priced season), flagged bets, first-20-games vs rest.
- Second look on the exam seasons 2024-2026 (already used three times), labeled as such.

## Step 3: live (only if step 2 passes; its own OK, MAJOR version)
- Engine input: ESPN's college injury list (players marked Out), if it carries real data during the
  season (checked after Nov 3). If it doesn't, the engine runs without known absences and only
  Claude's sourced facts (`news.py out`) count, through the claude prediction.
- Claude's college checks (11 AM and 5 PM, games where engine and market differ by 4+ points) would
  record absences as facts. Talal may want them to cover more games, since in college the news is the
  only reliable absence source.
- Refit on all seasons, staged; Talal runs `apply`. Card back, rankings and player pages follow the
  NBA versions.

## Results (2026-10-24; full lines in `backtest_results/players_ncaab.md`)
Step 1 done: 68,806 games, 1.34 million player rows, 212 CBBD calls; CBBD has no box score for 2,758
games (4%, checked directly for two of them), treated as "absences unknown". Daily refresh in the
morning routine.

Step 2: **neither idea clears the pre-registered bar; no college player model goes live.**
- #1 minutes only: check 0.5124 vs 0.5125 (the tuner shrank its weight to almost nothing). Dropped.
- #2 production rating: check 0.5110, a 0.0015 gain, short of the 0.002 bar. Dropped. It did look
  better on the side measures (calibration's worst bucket 5.9 -> 4.1; on the one priced check season,
  gap to the market 0.0122 -> 0.0092; flagged-bet ROI -3.6% -> -2.0%), but the bar was set before the
  test and isn't moved after seeing results. Its tuned summer pull-back was 0.91: college rosters turn
  over so much that last season's ratings carry little.
- The second look on the exam seasons was for a kept idea, so it wasn't run.
- What remains for college: Claude's capped adjustments for absences (as before). A future, separate
  test could be idea 2 as a live shadow challenger, if ESPN's college injury list turns out to have
  real data once the season starts (to be checked after Nov 3).

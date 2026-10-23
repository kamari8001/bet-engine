# Basketball player-impact model (QUEUE item 3, formerly 7): plan and pre-registration

Written 2026-10-23, before any of it was built. Talal said "begin"; step 1 (data) is under way.
The model design below needs his OK before step 2 starts.

## Why
The NBA model can't see who's playing. A missing star can move a game by 8-10 points of win
probability; Claude's judgment adjustments are capped at 3. The factor study showed the market already
prices everything in our ratings, so the only route to an edge is information the market hasn't fully
priced yet: who is out, known early. This model turns "player X is out" into a probability with data
instead of a cap.

## Step 1: data (self-contained; started 2026-10-23)
- `pull_nba_players.py history`: ESPN's box score for every NBA game in `hist_games` (2014-15 on,
  ~15,500 games, one request each, resumable): per player and game, team, minutes, points, plus-minus,
  starter, did-not-play and its reason (e.g. injury vs coach's decision). Stored in `hist_player_games`
  (`schema_extra.sql`). `hist_box_pulled` remembers which games were fetched.
- `pull_nba_players.py current`: the same for recently finished games, for the daily routine.
- Proof: counts per season, players per game (should be ~26), a known absence found in the data.

## Step 2: the model (needs OK)
A **missing-value** feature per team and game, built walk-forward from box scores only:
- A team's *rotation* before a game = players with 10+ minutes per game over the team's previous
  games this season (last season's data in the first 5 games).
- Each rotation player gets a **value**: idea #1, minutes per game alone; idea #2, minutes x a
  box-score efficiency relative to a replacement player (a simplified game score per minute, shrunk
  toward the league average with few minutes); idea #3, minutes x plus-minus per minute, shrunk the
  same way. Pre-registered: ideas are kept only if they improve check-season log loss by >= 0.002
  (double the usual bar, since this feature is noisy) over the base model, and the better of #2/#3 is
  kept only if it beats #1 by the same bar.
- **Absent** = a rotation player who does not play (0 minutes / did not play). The team's missing
  value is the sum of absent players' values; the feature is home missing value minus away missing
  value, scaled by a tuned coefficient into the projected margin (like rest days).
- Hindsight check: "did not play" is known at tip-off, but not always at the morning line. In the
  backtest, absences are treated as known pre-game (the inactive list is public before tip-off). The
  live version only uses what the injury report says before the game (below), so it can be worse
  than the backtest, never better.

## Step 2 tests (pre-registered)
- Seasons as the NBA criteria file: tune 2015-2020, check 2021-2023 (2014-15 is warm-up).
- The feature passes if check-season log loss improves by >= 0.002 and calibration doesn't worsen
  (no 50+ game bucket off by more than 8). Information only: the gap to the market on check seasons
  (expected to shrink; the market knows absences too).
- **The NBA final-exam seasons (2024-2026) were already used once** for `nba-v1`. A second run on
  them is a second look, not an untouched test, and is reported with that label. The real test of
  `nba-v2` is live: judged on the 2026-27 scorecard and closing-line value.

## Step 3: live (after step 2 passes)
- The engine's automatic input: ESPN's injury list per game (status Out) before tip-off, the way
  nflverse QB listings feed the NFL engine.
- Claude's scheduled NBA injury check records absences as **facts** with a source (`news.py out`),
  like confirmed QBs; the formula turns them into the `claude` probability. Judgment adjustments stay
  for everything else (rest decisions, returns from injury), still capped.
- Slate: absent players shown on the card back. Released as `nba-v2` (MAJOR).
- College basketball follows if the NBA version passes (CBBD box scores; a separate plan).

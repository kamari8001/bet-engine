# Early-season player values (QUEUE item 3, follow-up 2): plan and pre-registration

Written 2026-10-23, before any of it was built or fit. Needs Talal's OK before step 2.
Builds on `plans/player_impact.md` (nba-v2, idea 2 live since v4.0.0).

## The two problems (found while wiring nba-v2)
- **A. Values start too low.** Over the summer every player's rating is pulled most of the way
  (tuned: 60-68%) toward *replacement level*. So a star starts the season rated like a bench player
  and climbs back over ~15-20 games. On 2026-10-23 Jokic was worth 1.2 points of margin, vs 4.7 at
  the end of 2025-26, and about half the rotation was rated below replacement.
- **B. Players who haven't played yet don't count.** The model counts a player as missing only after
  seeing them play this season. A rotation player hurt since opening night is invisible: the team is
  rated as if they were there (last season's rating included them).

## Ideas, in order (each kept only if it clears the bar below)
- **#5 Regress toward the average, not replacement.** Between seasons, pull each returning player's
  production and plus-minus part of the way toward the *average rotation player of the season that
  just ended* instead of toward replacement level. Rookies still start at replacement. Same tuned
  settings as idea 2 (learning rate, summer pull-back, replacement level, absence weight), re-tuned.
- **#6 Count returning players who haven't played yet.** A player who was a rotation player at the
  end of last season (10+ minutes a game) **for the same team** counts as missing in that team's
  games this season until they first play, at their carried-over value.
  - *History* has no injury lists, so the backtest uses a stand-in: the player's first appearance
    this season (in a box score) is for that same team; every earlier team game this season counts
    them as missing. This uses a later box score to know the player was still on the roster, which
    the public roster/injury report showed at the time. Caveat: it can't see players who never
    return that season (season-ending injuries); live, ESPN's list does.
  - *Live*: a player on ESPN's injury list as Out for team X, whose last team was X, who was a
    rotation player at the end of last season, and who hasn't played this season. For consistency,
    the live engine also counts them as missing in X's games already played this season (exactly what
    the stand-in does in history), so the team's rating isn't charged twice.
  - Not covered: players who changed teams over the summer and got hurt before their first game
    (rare; Claude can't add them either; a capped adjustment remains the fallback).
  - Applied on top of the better of idea 2 (live) and idea 5. Tuned settings: the same four.

## Tests (pre-registered)
- Seasons as before: tune 2015-2020, check 2021-2023 (2014-15 warm-up). Team settings: pre-exam
  nba-v1, as in the idea 1-4 test, so the comparison is like for like.
- **Keep rule:** check-season log loss improves by >= 0.001 over the best so far (starting from idea
  2's 0.6340), and no 50+ game calibration bucket off by more than 8 points (or more than the base
  model's own worst, as before). The bar is the standard 0.001, not the 0.002 used for the new player
  feature: these ideas only change each team's first weeks of a season (~25% of games), so a real
  gain is diluted across the season.
- Information only (not part of the keep rule): log loss on each team's first 20 games of a season
  vs the rest of the season (the rest should not get worse), the gap to the market, flagged bets.
- Second look on the exam seasons 2024-2026 (already used), labeled as such.
- If something is kept: refit on all seasons (`backtest_players.py refit`, staged), Talal runs
  `apply`, version 5.0.0 (MAJOR: NBA probabilities change). If nothing is kept, nba-v2 stays and the
  finding is recorded.

## Files
`player_model.py` (the two ideas, switched off by default so nba-v2 is unchanged), `backtest_players.py`
(ideas 5 and 6, early-season report), `predict.py` / `news.py` (idea 6 live, only if kept),
results appended to `backtest_results/players.md`.

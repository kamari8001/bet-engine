# NBA starting ratings from player moves: plan and pre-registration

Written 2026-10-25, before anything was built or fit. Needs Talal's OK.

## Why
The NBA engine is furthest from the market early in a season: each team's first 20 games score
0.6587 log loss in the check seasons vs 0.6261 for the rest (`backtest_results/players.md`), and the
first 36 live games of 2026-27 score 0.637 vs the market's 0.578. The market knows about summer
trades and signings on day one; our team ratings only learn about them by watching games (they
start each season at 55% of last season's rating). We now rate every player, so a team's rating can
account for who actually moved.

## The idea (#7: player moves carry their value)
Whenever a player first appears in a box score for a **different team than his last one**, his value
moves with him, before that game is predicted:
- new team: margin rating + `move_coef` x value; old team: margin rating - `move_coef` x value
  (split equally between offense and defense, like the rest of the model);
- value = the same per-game value the absence model uses (rating x minutes, above replacement). For a
  move over the summer it's his value at the end of last season (before the summer pull-back);
  during a season, his current value. Rookies and unrated players carry 0.
- Covers summer trades and signings, and trades and signings during the season. Uses nothing that
  wasn't public before the game: a move is announced before the player suits up.

Not covered (documented, not fixed here): retirements and players who leave the league (no new team
ever appears), and a move is only seen once the player appears in a box score (a traded player who is
injured shows up late). Live, ESPN rosters could catch moves sooner; a possible later step.

Rejected design (recorded so it isn't retried by accident): comparing opening-night box scores with
last season's roster. ESPN box scores don't list inactive injured players, so an injured star would
look like a departure; there's no way to tell those apart in the history without hindsight.

## The test (pre-registered)
- Base: the model that's live in design, on tune-season settings: pre-exam nba-v1 team settings plus
  the kept player settings (idea 2, `players_best.json`), check log loss 0.6340.
- Tuned on the tune seasons (2014-15 to 2019-20): `move_coef`, plus the team rating's summer pull-back
  (`regress`), since knowing who moved changes how much last season should carry over.
- **Keep rule:** check-season (2020-21 to 2022-23) log loss better by >= 0.001 (the standard bar: like
  the early-season ideas, it mostly changes the first weeks of a season and trade periods), and no
  50+ game calibration bucket off by more than 8 points or by more than the base's own worst.
- Information only: first-20-games vs rest of season, gap to the market, flagged bets; number of moves
  per season and the biggest ones (sanity check: e.g. a star traded in the summer).
- Second look on the exam seasons 2023-24 to 2025-26, labeled as such.

## If kept
Refit on all seasons (staged), Talal runs `apply`, version 5.0.0 (MAJOR: NBA probabilities change).
Because the live engine replays this season's box scores, moves already seen this season take effect
immediately. Rankings and player pages use the same ratings automatically.

## Files
`player_model.py` (detect moves, off by default), `model.py` (apply them, off unless `move_coef` > 0),
`backtest_players.py` (`moves` mode), results in `backtest_results/players.md`.

## Results (2026-10-26; full lines in `backtest_results/players.md`)
**Kept.** Tuned move weight 0.40 points of margin per unit of value (the summer pull-back didn't
change). Check seasons 0.6340 -> 0.6328 (bar 0.001), calibration's worst bucket 6.2 (rule: within 8).
It helps both a team's first 20 games (0.6587 -> 0.6578) and the rest of the season (0.6261 -> 0.6248,
trade periods). Second look on the exam seasons: 0.6002 -> 0.5993. Still trails the market (0.6173 on
the check seasons); flagged-bet ROI moved from -2.1% to -3.2% (information only).
Sanity check: 85-313 moves per season; the biggest are the famous ones (Durant to Golden State 2016,
LeBron to the Lakers 2018, Leonard to the Clippers 2019, the Doncic-Davis trade 2025).
Next: refit on all seasons (`backtest_players.py refit --moves`, staged), Talal runs `apply` -> nba-v3,
version 5.0.0.

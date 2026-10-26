# Changelog: Kamari's Prediction Engine

Versions follow MAJOR.MINOR.PATCH (see `version.py`): MAJOR changes the probabilities
(new model version or sport), MINOR adds features, PATCH fixes and polishes.
Each version is tagged in git (`git tag -l`).

## 5.0.1 (2026-10-26): retries for temporary server errors
- Downloads now retry when a source has a temporary problem (server errors 500/502/503/504, a timeout,
  or a dropped connection): up to 4 tries, waiting 5, 15 and 45 seconds. Real errors (wrong key, not
  found, too many requests) still stop right away. Covers nflverse, the college football and basketball
  data services, ESPN's injury list, The Odds API, football-data.co.uk and Understat (`net.py`). On
  Oct 25 a one-off college football server error made the morning routine fail twice and run 20
  minutes late; now it would have retried. You're only notified if every try fails.
- Understat xG refresh: games our history hasn't loaded yet no longer count against the 98% match rule
  (they're matched the next day), and kickoff dates may differ by a day either way, as planned (e.g.
  Toulouse v Troyes, dated a day early by Understat).

## 5.0.0 (2026-10-26): NBA player moves
- New NBA model, `nba-v3-refit-20261026`. When a player first appears for a different team, his value
  moves with him: the new team's rating goes up and the old team's goes down. Covers summer trades and
  signings and the trade deadline, so a team's rating no longer waits weeks to learn who it added or
  lost. The 25 moves already seen this season count right away (e.g. Kawhi Leonard to Toronto, Giannis
  Antetokounmpo to Miami).
- Tested before going live (plan `plans/nba_roster_moves.md`): on the 2020-21 to 2022-23 check
  seasons, log loss improved from 0.6340 to 0.6328 (bar: 0.001), in both a team's first 20 games and
  the rest of the season; second look on the exam seasons 0.6002 to 0.5993. It still trails the market
  and flagged bets still lose in the backtest, so flags stay paper only.
- Not covered: retirements, and a traded player who's injured only counts once he appears.
- Rankings and player OVRs were rebuilt for the new model.

## 4.2.0 (2026-10-24): NBA news timing
- An injury watcher checks ESPN's NBA injury list every 10 minutes (8 AM to the day's last tip-off)
  and records every status change for a rotation player, stamped when we first saw it.
- When news moves a team's missing value by 1+ point of margin within 24 hours of tip-off, it pulls
  odds and logs predictions right away (at most one extra pull per 15 minutes, 30 a day), so the
  prediction sits next to the line at that moment instead of hours later.
- NBA scorecard: a "News timing" panel. News CLV = how far the line kept moving after we saw the news.
  Pre-registered bar (`plans/news_timing.md`): after 100 events the 95% range must sit above 0. If it
  does, public injury news gives us a head start; if not, that route to an edge is closed.
- No probabilities change: same model, just logged sooner.

## 4.1.0 (2026-10-23): NBA players
- **Player OVR (1-99)** for every NBA rotation player, built from what the model charges when the
  player sits out (points of team margin per game). It's ranked among every rotation player-season
  since 2015-16 on the same bell curve as team OVR: 62 = typical rotation player, 80+ = top ~7%,
  90+ = top ~1%. Last season's top three: Doncic 95, Jokic 94, Wembanyama 90. Early in a season
  OVRs run low (ratings rebuild as games are played), which is what predicted best in testing.
- **Team rosters**: tap a team on an NBA card (or "roster" on its Rankings history page) for every
  player with headshot, position, OVR, minutes and ESPN injury status.
- **Player profiles**: headshot (a silhouette if ESPN has none), OVR with league and position rank,
  injury detail, Claude's recorded notes with sources, last 5 games, per-game averages this season
  and last, and OVR by season.
- **Rankings, NBA**: a Teams | Players switch; players by OVR with a position filter
  (guards/forwards/centers), search, and past seasons.
- Display only: nothing is stored in the logbook and no probabilities change.
- Season charts keep their first and last labels inside the chart.

## 4.0.1 (2026-10-23): faster slate
- Slate pages load in well under a second (NBA, college football and soccer took about 4 seconds).
  Each card's form and record lookups were reading every past game of every sport; a database
  index now takes them straight to the right season. Nothing on the cards changed.

## 4.0.0 (2026-10-23): the NBA model sees who's playing
- New NBA model, `nba-v2-refit-20261023`. Every player gets a rating from their box scores (scoring,
  shooting efficiency, rebounds, assists, turnovers, steals, blocks, fouls), weighted by their
  minutes. Ratings update after every game but move only as evidence builds up, so one big night
  doesn't swing them. When a rotation player is out, the team's projected margin drops by that
  player's value.
- Tested before going live (plan `plans/player_impact.md`, results `backtest_results/players.md`):
  on the 2020-21 to 2022-23 check seasons, log loss improved from 0.6433 to 0.6340 and calibration's
  worst bucket from 13.9 to 5.3 points off. Plus-minus and a self-correcting absence weight added
  nothing and were left out. It still trails the market, and flagged bets still lose in the backtest,
  so flags stay paper only.
- Before each prediction the engine reads ESPN's injury list: rotation players marked Out count as
  missing. Day-to-day players count as playing and show up as a warning. If the list can't be read,
  NBA predictions stop instead of guessing.
- Claude's NBA injury checks now record confirmed absences as sourced facts (`news.py out`, or
  `news.py playing` when ESPN's list is wrong), and the formula turns them into the claude
  probability. This replaces the 3-point cap for missing players. Capped adjustments remain for what
  the formula can't see, like a star returning from a long injury.
- Card backs show "Missing players" with each one's effect on the team's win chance.
- Rankings use the same absence-aware ratings.
- Known limitation: player ratings are pulled toward replacement level over the summer, so in a
  season's first 15-20 games even stars count for little (Jokic is worth 1.2 points today, versus
  4.7 at the end of last season). A fix needs its own test and is in the queue.

## 3.1.1 (2026-10-22): smoother slate
- Logging a pick keeps your league filter (it's now part of the page address, so reloads and
  bookmarks keep it too) and brings you back to the card you picked.
- Phones and tablets: cards no longer trap swipes. They're flat (no 3D layers, no scroll area inside
  the card) and as tall as their content; tapping swaps front and back with a quick flip. iPhone
  Safari often wouldn't scroll the page when a swipe started on a 3D card. Desktop keeps the 3D flip.
- New look: frosted header, softer glowing cards that lift under the mouse, cards fading in one after
  another, a smoother flip, pill-shaped edges and FLAG tags, day headings with a rule line, focus
  rings, messages that slide in (success messages fade away), smooth page-to-page transitions in
  browsers that support them. Animations switch off with the system's Reduce Motion setting.
- Price tables show the book under the price on every screen; desktop cards are a bit taller.

## 3.1.0 (2026-10-22): Champions League
- Champions League games are predicted (home/draw/away) when both clubs come from leagues we cover
  (about 80% of games; 32 of this season's 36 clubs). New probabilities only for these new games;
  Big 5 league predictions are unchanged (checked to be identical).
- The model learns each league's strength from European results (Champions, Europa and Conference
  League since 2014-15, with history for 14 more European leagues). Final exam (2022-23 to 2025-26,
  521 games): works and is calibrated, trails the market, -1.0% on flagged bets, so paper only.
- Soccer tab: "Champions League" in the league filter; logos for clubs outside the Big 5; Live tab
  scores. Odds pulls add the Champions League feed (6 credits per soccer pull).
- The routines refresh the other European leagues and the European results every day.
- The 8 AM team news check covers Champions League games (incl. UEFA suspensions and rotation).
- Soccer power rankings now use the league strengths learned from European games instead of UEFA
  coefficients (seasons from 2015-16; the OVR scale was rebuilt).

## 3.0.0 (2026-10-21): club soccer is live
New sport (MAJOR): the Big 5 European leagues (Premier League, La Liga, Bundesliga, Serie A,
Ligue 1), with three outcomes: home, draw, away.
- Model `soccer-v2-refit-20261021`: attack and defense ratings per club, expected goals, and a
  scoreline model (Poisson + Dixon-Coles); shots on target help the ratings. Final exam: works and
  is calibrated, trails the market, no money edge (-13.9%), so flags are paper only, Low confidence.
- Predictions before every kickoff with edges on all three outcomes; at most one flag per game
  (draws can be flagged). Grading adds RPS, a soccer-standard score where a draw sits between a
  home and an away win.
- Slate: a Soccer tab (league filter, Draw row, three-way odds by book), plus Live, Positions,
  and Scorecard. Your pick: a team or Draw and your chance; the other two split the rest in the
  market's proportions.
- Automation: soccer odds (5 credits a pull) and predictions in the 9 AM routine and before each
  kickoff group, results overnight; a scheduled Claude team news check at 8 AM daily.
- The $30 Odds API plan (20,000 credits a month) is active.

## 2.4.0 (2026-10-21): soccer power rankings
- Rankings tab has **Soccer**: every Big 5 club in one list, with the same OVR scale, season picker
  (2012-13 on), all-time top 25, and team pages. Clubs from different leagues are compared using
  UEFA's country coefficients (downloaded with sources to `uefa_coefficients.json`): an outside
  assumption, adjustable with `SOCCER_LEAGUE_STRENGTH` in `config.py`. Records are wins-draws-losses.
- The 9 AM routine now refreshes this season's soccer results (last step, so it can't block the others).

## 2.3.1 (2026-10-21)
- Odds pulls no longer fail (and notify) when The Odds API still lists a game as upcoming after
  our schedule's kickoff; that game is skipped as "already started" and the other prices save.

## 2.3.0 (2026-10-20): OVR on one scale, past seasons
- OVR now works like a FIFA rating and means the same thing in every season: 62 = an average team,
  80+ = great (top ~7% of all team-seasons in our history), 90+ = historically great (top ~1%).
  It starts from the model's chance to beat an average team that season, then places it on a bell
  curve of every past team-season in that sport. The curve is frozen per model version
  (`rankings_scale.json`), so a 95 in 2017 really was more dominant than an 88 today.
- Rankings tab: season picker (past seasons show each team's rating after its last game, records
  incl. playoffs), an all-time top 25, and a page per team with its OVR by season (chart + table).
  History: NFL 2000+, college football 2014+, NBA and college basketball 2015-16+.

## 2.2.2 (2026-10-20)
- Fixed "DraftKings" showing a stray symbol on iPhone: the Doppio One font's "ft" ligature (joined letters) is now turned off.

## 2.2.1 (2026-10-20): phone layout
- The slate now fits phone screens (it used to render the full desktop page zoomed out): compact
  header, swipeable tab bar, one game card per row, bigger tap targets, text boxes that don't make
  the iPhone zoom in, the book name under the price, Positions picks stacked as blocks, summary
  tiles two per row, and Rankings showing the key columns. Desktop layout unchanged.
  Checked at 375 and 430 pixels wide on every page.

## 2.2.0 (2026-10-19): power rankings
- New **Rankings** tab (and `python3 rankings.py <sport>`): every team ranked by the model's own
  current rating, with an **OVR** (0-99) = the model's chance to beat an average team of its league
  on a neutral field. Also net points vs. average, record, last 5, offense and defense ranks, and
  movement since a week ago. College lists have search and a conference filter; NFL shows the QB the
  engine expects next game. Display only; nothing is stored.
- Header's model list shows only live sports (it briefly listed the unfinished soccer model).

## 2.1.3 (2026-10-19)
- The "My picks" page is now called "Positions".

## 2.1.2 (2026-10-19)
- Slate page font: Doppio One (Google Fonts). Falls back to the system font when offline.

## 2.1.1 (2026-10-19): health-check fixes
- Pre-game refreshes no longer stop because an earlier game that day has no result loaded yet.
  Now only games whose own team is waiting on a result are skipped; if any result is 24+ hours
  late, the run still stops (the data source is probably broken). This broke Sunday night's refresh.
- After the Mac wakes, games in a kickoff group whose first game already started now get their own
  closing-odds pull (Sunday, the 4:25 PM games were missed). A sport whose odds are under 15
  minutes old isn't pulled again.
- A brief internet drop while checking credits retries quietly next run instead of sending a
  failure notification.

## 2.1.0 (2026-10-19): expert signals
- New paper-only shadow challengers, pre-registered: `dk_sharp_money_v1` (bet the side with 15+
  points more of the money than of the bets, from DraftKings' public splits; all four sports) and
  `circa_consensus_v1` (bet the Circa Million contest's 5 most-picked NFL sides).
- `experts.py` records signals with their source link in the protected `expert_signals` table.
- Scheduled checks: DraftKings splits snapshots (11:45 AM, 5:45 PM) and Circa consensus (Saturday 9 PM).

## 2.0.1 (2026-10-19)
- Tab labels: "NCAAF" (college football) and "NCAAM" (college basketball).

## 2.0.0 (2026-10-19): basketball
New sport (MAJOR): NBA `nba-v1-refit-20261019` and college basketball `ncaab-v1-refit-20261019`
(team ratings + home court + rest days; NBA back-to-backs matter, college rest doesn't).
- History: NBA 2014-15 to 2025-26 from ESPN (15,479 games, real sportsbook prices); college
  basketball from CBBD (68,806 games; real sportsbook moneylines from 2023 on).
- Final exam (see `backtest_results/criteria_basketball.md`): both work and are calibrated but trail
  the market; neither made money (NBA -10.5%, college -4.2%). Flags are paper only, Low confidence.
- Fixed a data bug in past odds: ESPN "Live Odds" in-game prices and prediction-site projections
  were being counted as market prices; past odds now count only real sportsbooks' pregame prices.
- Live: NBA and college basketball schedules, results, odds, predictions with rest days, grading,
  warnings ("injury report not checked"), and slate/Live/Scorecard tabs with logos.
- News: scheduled NBA injury checks (noon and 6 PM) and college basketball checks (11 AM and 5 PM),
  recording reviews or capped adjustments with sources.
- Automation covers all four sports; `pull_odds.py all` skips sports with no games in the next week.

## 1.1.0 (2026-10-18)
- Named the engine **Kamari's Prediction Engine**, with the app and model versions shown in the slate page header.
- Live tab: separate NFL and College tabs.
- Live tab: the possession dot now lines up with the team name.
- Started versioning: `version.py`, this changelog, git tags.

## 1.0.0 (2026-10-18): football complete
Models: NFL `nfl-v2-refit-20261015` (team + starting-QB ratings + rest), College `ncaaf-v2-refit-20261015`
(team ratings + CFBD preseason talent, returning production, last season's SP+).
- Data: NFL (nflverse, 1999+) and college (CFBD, 2013+) history; live schedules, results, and odds from 10 books incl. your FanDuel, DraftKings, Polymarket.
- Database rules enforce log-before-kickoff, never-edit-the-past, sourced and capped adjustments.
- Backtested with a one-time final exam (both sports work but trail the market; no money edge), then refit on all seasons for live use.
- Live predictions from three sources (engine, claude, you), news step for NFL QBs (facts and verified checks) and college (reviews and capped adjustments).
- Grading: Brier, log loss, calibration, paper bets, closing-line value, head-to-head.
- Automation: daily routine, closing-line pulls before each kickoff window, wake-up catch-up; scheduled Claude news checks.
- Slate page: flip cards, My picks, visual scorecard, Live tab; per-game warnings instead of unearned confidence ratings.
- Cancelled/postponed games; shadow mode with three pre-registered challengers; market-pattern tests (none passed).

## Before 1.0.0
Built 2026-10-14 to 2026-10-18; see `git log` for every step.

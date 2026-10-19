# Club soccer: build plan

Written 2026-10-19. Status: **approved 2026-10-19** (all four recommendations: Big 5 leagues, draws can be flagged, scheduled weekend Mac wake set by Talal, live after the Nov 3 Odds API plan). Not built yet.
Sport code in the database: `soccer_club` (already allowed by the schema).

## What changes compared with football and basketball

- **Three outcomes.** Every game gets a home, draw, and away probability. Live predictions
  already store a draw probability (`p_draw`); history, grading, the slate, and shadow mode
  need to learn about it.
- **Goals, not points.** Soccer scores are small numbers, so the model predicts each team's
  expected goals and turns them into a scoreline grid (Poisson, see below). The projected
  score shown on cards is those expected goals.
- **Leagues.** Five domestic leagues at once, each with its own home advantage. Teams move
  between leagues (promotion and relegation), so we also load the second divisions for history.
- **Early kickoffs.** European games start as early as 7:30 AM ET, so the Mac is often
  asleep for closing-line pulls (see Decision 3).

## Decisions for Talal

1. **Leagues.** Recommended: the "Big 5": Premier League, La Liga, Bundesliga, Serie A, and
   Ligue 1. All are priced at FanDuel and DraftKings and have deep free history. Fallback if
   credits get tight: Premier League only. Champions League and Europa League come later (see
   QUEUE.md), because they need cross-league strength.
2. **Draws can be flagged bets.** Recommended: yes. A draw is a normal outcome of a soccer
   moneyline, and the edge rule (4 points) applies to it the same way.
3. **Early-morning closing lines.** The Mac must be awake around 7 AM ET on weekends for the
   earliest games. Option: a scheduled wake in System Settings, which Talal sets himself.
   Otherwise those games' closing lines fall back to the last earlier pull and are graded as
   approximate, like now.
4. **Timing.** Live soccer needs the $30 Odds API plan (about 250 credits a month extra).
   That fits the Nov 3 purchase, since soccer won't be live before then.

## Data sources (checked 2026-10-19)

| Need | Source | Notes |
|---|---|---|
| Past results and odds | **football-data.co.uk** (free CSV files, no key) | Results back to the 1990s. 1X2 odds from many books, including a "pre-closing" average (collected a day or two before the games) and **closing** prices since 2019-20. Pinnacle (the sharpest book) prices through 2025-26; Pinnacle is gone from 2026-27 files. Shots and shots on target for every game. Expected goals (xG) from 2026-27 only. |
| Live schedule and results | **ESPN soccer scoreboards** (free, unofficial; the same feed as the Live tab) | Checked: works per league and date (e.g. `eng.1`). Gives ESPN ids for the Live tab. football-data only updates about twice a week, too slowly for daily ratings. |
| Live odds | **The Odds API** (`soccer_epl`, `soccer_spain_la_liga`, `soccer_germany_bundesliga`, `soccer_italy_serie_a`, `soccer_france_ligue_one`) | The moneyline market includes the Draw price. 1 credit per league per pull. |
| Optional, tested in the backtest | **ClubElo** (free published club ratings, api.clubelo.com) | Your "other people's ratings" idea. Kept only if it helps on both tune and check seasons. |

## The model (`soccer_model.py`, settings in `model_params.json`)

- Each team has an **attack** and a **defense** rating in goals, updated after every game
  (like the current models). Each league has its own home advantage and average goals.
- Expected goals: home = league average + home attack − away defense + home advantage
  (and the mirror for the away team).
- **Poisson scoreline grid.** The chance of each score (0-0, 1-0, 2-1, …) comes from the
  two expected-goals numbers. Home win = sum of the home-winning scores, and likewise for
  draw and away. The **Dixon-Coles correction** nudges the 0-0, 1-0, 0-1, and 1-1 chances,
  because real draws are a little more common than plain Poisson says.
- **Promoted teams** start the season from the average rating of the teams that were
  relegated from that league (their second-division games are loaded to support this).
- **Season regression** toward the league average between seasons, as in the other sports.
- Tuned settings: learning rate, season regression, home advantage, the Dixon-Coles
  correction, and the promoted-team starting point.

**Ideas tested with `ablate`** (kept only if they help on both tune and check seasons):
1. Shots on target as an extra signal (less luck than goals, and available for every season).
2. ClubElo ratings blended in.
3. Rest days and midweek European games (fixture congestion).
4. Expected goals (xG). Only 2026-27 has it, so this can only be judged live (shadow mode),
   not in the backtest.

## Final exam (criteria file committed before any model is built)

| Tune | Check | Final exam (run once) |
|---|---|---|
| 2012-13 to 2018-19 | 2019-20 to 2021-22 | 2022-23 to 2025-26 |

Seasons are labeled by the year they end (2026 = 2025-26), like basketball. 2020-21 was mostly
played without crowds, and home advantage almost disappeared that season. The model's
home-advantage setting updates as it goes, which handles this; the criteria file will note it.

Tests, the same idea as before:
1. **Works at all:** log loss beats each league's usual home/draw/away rates.
2. **Honest percentages:** for each outcome, including draws, no 10-point calibration bucket
   with 50+ games is off by more than 8 points.
3. **Vs. the market:** the model against Pinnacle's no-vig closing prices. Information only.
4. **Would it have made money?** Bets are flagged against the pre-closing average price (a
   known time, about a day before kickoff), staked 1 unit at that price, with 150+ bets.
   Closing-line value is also reported against the closing price. This is a cleaner test than
   football's, whose line timing was unknown.

On a fail: same rules as before (bug → fix and document; money test fails → paper only, Low
confidence).

## Grading three outcomes

- **Brier score** summed over the three outcomes, and **log loss** of what actually happened.
- **RPS (ranked probability score):** a soccer-standard score that treats a draw as "between"
  a home win and an away win. Predicting 60% home when the game was drawn is less wrong than
  when the away team won.
- Flagged bets on any of the three outcomes; units and closing-line value at your books.

## Step 1 results (data, 2026-10-19)

- 82,481 past games (2005-06 to 2025-26, 10 divisions) and 322,854 odds rows from football-data;
  341 games this season (Big 5, Aug 15 to Oct 18) from ESPN. One Ligue 2 game with no score in
  the file (Bastia vs Red Star, Dec 5, 2025) was left out.
- Odds by season: pre-close (Bet365 + market average) for every season; closing prices from
  2012-13 (Pinnacle) and 2019-20 (market average, Bet365). **Pinnacle is mostly missing in
  2025-26**, so test 3's market benchmark is the **market-average closing price** (every
  final-exam season has it); Pinnacle is shown as extra information where present.
- Kickoff times exist from 2019-20 (UK time in the files, stored in UTC and Eastern).
- Cross-check: the 297 games of 2026-27 in both ESPN and football-data have identical scores.
- Team-name map (`teams.SOCCER_TEAMS`, 96 teams) checked one-to-one against all three sources.
- Live schedule (`pull_games.py soccer_club`) and odds with the Draw (`pull_odds.py soccer_club`,
  5 credits) tested on a throwaway copy: 53 games, all priced, FanDuel and DraftKings on every
  game, Polymarket on 11. Not loaded into the real logbook or automation until soccer goes live
  (games without results would trip the 24-hour stale-result stop).

## Build steps (commit after each; plan approval as usual)

1. **Data:**
   - Schema additions: `league` on `hist_games`, `draw_ml` on `hist_odds`, and the odds
     timing ("pre-close" or "close").
   - `pull_soccer_history.py`: the five leagues plus their second divisions, about 2005 on.
   - A team-name map (football-data, ESPN, and Odds API names). Unknown names stop the run
     rather than guessing.
   - Live schedule and results from ESPN, and soccer odds with the Draw price.
   - Proof: game counts per league and season, plus a sample of matched odds.
2. **Model:** criteria file first, then the model, tune, check, and ablate the four ideas;
   then the one-time final exam and the refit on all seasons.
3. **Live:**
   - `predict.py` (three-way edges), `grade.py` (Brier, log loss, RPS), cautions.
   - Slate cards with a Draw row, a Soccer tab with a league filter, and soccer in the Live tab.
   - Automation (early kickoffs, per-league pulls), and a scheduled lineup and news check.
   - Release as **v3.0.0**, since a new sport changes probabilities.

## Not in this plan (in QUEUE.md)

Champions League and Europa League, MLS, a three-way shadow table (current shadow
challengers are two-way only), and an xG-based model once more seasons of xG exist.

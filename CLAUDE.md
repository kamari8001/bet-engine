# Kamari's Prediction Engine: Project Rules

(Project folder: `bet-engine`.)

Read this file at the start of every session and follow it. Then read `QUEUE.md` (the development queue Talal edits): work from "Up next" top-down, and move items to "Done" with the date and version when finished.

## Who you're working with

- I'm Talal. I'm new to coding and to Claude Code.
- Explain what you're doing in plain English. Define any technical term the first time you use it.
- Before any change that touches more than one file, show me the plan and wait for my OK.
- After building something, show it working with real output. "Done" without proof doesn't count.
- If something fails, tell me plainly what broke and why before fixing it.

## What we're building

A sports prediction engine for **moneyline betting**.

- **Main output:** a win probability for every side of every game. Soccer is three-way: home, draw, and away.
- **Also show:** a fair moneyline, the book's moneyline, the no-vig market probability, the edge, a confidence rating, and a projected score.
- **Projected score:** shown only so I can see how close a game should be. It is not a betting target.
- **Sports, in build order:**
  1. NFL and college football
  2. NBA and college basketball
  3. Club soccer
  4. MLB
  5. International soccer
- **Three prediction sources:** the base model (`engine`), Claude's news adjustments (`claude`), and my own picks (`me`).

## Non-negotiable rules

1. **Log before kickoff.** Every prediction from every source is saved to the database with a timestamp before the game starts.
2. **Never edit the past.** Once a game starts, its predictions are locked. Corrections go in as new rows with a note, never as edits.
3. **Formula governs.** All probabilities come from code, never from Claude guessing a number in chat.
4. **News adjustments are bounded and logged.** Claude's injury and lineup adjustments must:
   - stay within a set maximum per game,
   - record the reason and the source link,
   - be stored separately from the base model output.
   - Confirmed starters are facts, not adjustments: Claude records them with a source (`news.py qb`, `lineup_facts` table) and the formula turns them into a probability (the `claude` prediction). The cap applies to judgment adjustments (`news.py adjust`). When the news supports the starter the model already assumes, Claude records a verified check (`news.py check`, `qb_checks` table, source required); it also produces a `claude` prediction (equal to the engine's), so Claude is graded on every game it reviewed, not only the ones it changed.
5. **No fake data.** Never invent, placeholder, or estimate data and present it as real. If a source fails, stop and tell me.
6. **Track the closing line.** Store the moneyline at prediction time and the final pregame (closing) moneyline for every game.
7. **Grade everything.** After games finish, compute for each source by sport: Brier score, log loss, calibration, win/loss on flagged bets, and closing-line value.
8. **Blending waits for evidence.** Don't weight sources by track record until a sport has at least 200 graded games. Before that, the final probability is the base model plus Claude's bounded adjustments.
9. **One sport at a time.** A sport isn't "done" until it has data, a backtested and calibrated model, an edge finder, and grading working.
10. **Commit after each working step.** Use git with a clear message so we can always undo.
11. **Version every release.** The app version lives in `version.py` (MAJOR.MINOR.PATCH: MAJOR = anything that changes the probabilities, i.e. a new model version or sport; MINOR = new features; PATCH = fixes and polish). When a change is user-visible, bump the version, add a `CHANGELOG.md` entry in plain English, and tag the commit (`git tag -a vX.Y.Z`). Model versions stay in `model_params.json` and on every prediction.

## Technical defaults

- Language: Python.
- Database: one SQLite file in this folder. Tables:
  - `games`
  - `odds` (with timestamps)
  - `predictions` (source, probability per outcome, projected score, timestamp, locked flag)
  - `results`
  - `adjustments`
  - `hist_games` and `hist_odds`: past seasons for backtesting only, kept apart from the live logbook
  - `lineup_facts` (news-confirmed starters) and `qb_checks` (verified: news supports the assumed starter)
- Times: stored in UTC; always shown to me in Eastern time (`*_et` views, `db.fmt_et`).
- API keys go in a `.env` file that is never committed to git.
- Keep scripts small and named clearly, e.g., `pull_nfl.py`, `predict.py`, `grade.py`.
- `COMMANDS.md` lists every terminal command. Whenever a command is added, removed, or changed, update it in the same commit.
- A simple local page shows the daily slate and lets me enter my picks.

## Edge and confidence

- **Fair probability:** convert the book's odds to implied probabilities and remove the vig before comparing.
- **Edge:** engine probability minus the no-vig market probability.
- **Flagged bets:** only games where the edge is at or above the threshold in `config` (start at 4 percentage points).
- **Confidence:** for now, show specific warnings per game (unconfirmed starters, stale odds, few books, early season, very large edges; `cautions.py`). Edge size is not a confidence signal; in backtests, larger edges were more often model error. After a sport has 200+ graded games, add a Low / Medium / High rating based on which situations have actually beaten the closing line, with the reason.

## Daily routine (once automation is set up)

1. Pull new results, schedules, rosters, injuries, and odds.
2. Run the base model.
3. Claude scans news and proposes bounded adjustments, with sources.
4. Generate today's slate.
5. Grade yesterday's games and update the scorecard.

## Status

Update this section at the end of each session: what's working, what's next, any open problems.

Last updated 2026-10-19.

- **Working:**
  - Database and logbook with rules enforced by the database itself (`schema.sql`, `db.py`; `python3 test_db.py` checks them).
  - Past seasons loaded (`pull_history.py`): NFL from nflverse (games 1999+, moneylines 2006+), college from CFBD (games 2013+, moneylines 2021+, FBS-involved games only). Line timing is unknown, so backtests are a strong hint, not proof.
  - Live schedule and results (`pull_games.py`): NFL, and college games between two FBS teams. Games with no announced kickoff time are skipped until they have one.
  - Live odds (`pull_odds.py`): The Odds API ($30 plan, 20,000 credits/month since 2026-10-21), 1 credit per sport per run (club soccer 5), refuses below 50 credits. Team names matched via `teams.py`.
- **Data sources:** nflverse (no key), CFBD (free key, 1,000 calls/month), The Odds API (free key, 500 credits/month). `python3 check_keys.py` tests the keys.
  - Base models (`model.py`, `combiner.py`, settings in `model_params.json`): NFL v2 (team ratings + starting-QB ratings + rest), college v2 (team ratings + CFBD preseason talent, returning production, last season's SP+). `backtest.py` tunes, compares ideas (`ablate`), and runs the one-time final exam.
  - Final exams run 2026-10-15 (see `backtest_results/criteria.md`): both sports work and trail the market; neither made money on flagged bets (NFL -10.7%, college -3.8%). NFL also narrowly failed calibration. Flagged bets are paper only, Low confidence, until live results prove an edge.
  - Tested and rejected (code kept, switched off): NFL efficiency (EPA) ratings, coach reset, early-season learning, travel; CFBD published Elo; QB/team-combo market bias.
  - Models refit on all seasons through 2025 for live use (`*-v2-refit`); judged on live results only.
  - Live predictions (`predict.py`): logs `engine` and `claude` rows before kickoff (new row only on a 1+ point move or starter change), prints the slate with best price at my books (`config.MY_BOOKS`: FanDuel, DraftKings, Polymarket). Skips a game while one of its teams has a finished game with no result loaded yet, and stops entirely if any result is 24+ hours late; no flags on odds older than 3 hours. `news.py` records confirmed QBs and capped adjustments; `my_pick.py` logs my picks.
  - Routine: `pull_games.py all` -> `pull_odds.py all` -> `pull_history.py all --current` -> `predict.py nfl|ncaaf` -> Claude checks news (`news.py`) -> `predict.py` again.
  - Grading (`grade.py nfl|ncaaf`): per source (engine, claude, me) plus the market benchmark: Brier, log loss, calibration, flagged-bet W/L and units at my books, closing-line value. Run after `pull_games.py` loads results.
  - First live logs 2026-10-15: 14 NFL + 59 college engine predictions; claude row for SEA at DEN (Darnold expected; nflverse wrongly listed Lock).
  - Automation (`auto.py`, run every 10 min by launchd: `automation/com.betengine.auto.plist`): morning routine 9 AM ET, odds + predictions 20-30 min before each kickoff window (closing lines), results + grades 3 AM, and a catch-up odds pull right after the Mac wakes if games start within 2 hours and odds are 2+ hours old. Skips quietly when there's no internet (brief maintenance wakes) without counting as a run, so the catch-up still fires on the next real wake. Logs in `logs/auto.log`; failures send a Mac notification and stop. `python3 auto.py --status` shows what's done and coming. The Mac also wakes itself at 6:50 AM on weekends (`pmset repeat`, set 2026-10-19 for early soccer kickoffs; `pmset -g sched` shows it). Works best with the Mac awake (plugged in, no auto-sleep, lid open), especially Sunday 12:30-8:30 PM ET, Saturday afternoons/evenings, and Thu/Mon evenings; while asleep, closing lines for those windows fall back to the last earlier pull (graded as approximate).
  - Scheduled Claude NFL QB checks (desktop app, Auto mode; QB facts only, no adjustments): Sat 10 AM (next 2 days), Sun 11 AM, Sun 3 PM (late games, after their inactives), Thu/Mon 5 PM. Run only while the Claude app is open. Scheduled tasks are tied to the folder they were created in: if the project folder ever moves, recreate them from a session in the new folder (the 2026-10-16 move silently broke the first set; those are paused and marked OLD).
  - `show_picks.py` shows each source's current pick side by side; `grade.py` includes head-to-head on shared games.
  - Per-game warnings (`cautions.py`) in `predict.py` and `show_picks.py`.
  - Live tab (`/live`, `live_scores.py`): ESPN's public scoreboard (unofficial, free), matched by ESPN game id (`games.espn_id`; college ids are ESPN's), cached 30 s, refreshed every minute while open. Display only: never stored as results.
  - Phone access (2026-10-20): Tailscale Serve shares the slate privately at https://talals-macbook-pro.tail7eeb70.ts.net (Talal's devices only; set from Talal's terminal, since Claude's sandbox can't change Tailscale settings). See COMMANDS.md.
  - Slate page runs in the background (launchd `automation/com.betengine.slate.plist`, logs `logs/slate.*`) and restarts itself when any project .py file changes.
  - Slate page (`slate.py` server, `slate_data.py` data, `slate_views.py` HTML; http://localhost:8765, this Mac only, dark theme): flip cards per game (front: each source's pick in words with logos, prices at my books, flags, pick entry with the same rules as `my_pick.py`, warning badge; back: warnings, odds by book, line movement, last-5 form, QBs, rest), a Positions page (your picks) (upcoming / in progress / finished), a Rankings tab (`rankings.py`: teams ranked by the model's own rating; OVR 1-99 = the chance to beat an average team of its league that season on a neutral field, placed on a bell curve of every past team-season in that sport (62 average, 80+ top ~7%, 90+ top ~1%), frozen per model version in `rankings_scale.json` so it compares across seasons; season picker with past seasons' final ratings, all-time top 25, team history chart; club soccer too (all Big 5 clubs in one list: own-league rating shifted by UEFA country coefficients from `uefa_coefficients.json` via `config.SOCCER_LEAGUE_STRENGTH`, an adjustable assumption; 2012-13 on; this season's soccer results refresh in the 9 AM routine); display only, nothing stored in the logbook), and a visual scorecard (stat tiles, head-to-head, calibration chart). Logos: ESPN (NFL), CFBD (college, cached weekly in `cache/`).
  - Shadow mode (`shadow.py`, tables `shadow_predictions` / `shadow_bets`): pre-registered challengers (`backtest_results/shadow_challengers.md`) log before kickoff, apart from the real logbook; scorecard on the Scorecard tab and `shadow.py report`. Started 2026-10-18 with `nfl_after_blowout_loss_v1`, `nfl_back_popular_v1`, `market_anchor_v1`. Never edit a challenger; make a new version. Eligible challengers wait for Talal's decision.
  - Market-pattern tests (`market_patterns.py`, `backtest_results/market_patterns_plan.md`): no pre-registered pattern beat the closing line.
  - College news step: scheduled checks (Sat 9:30 AM; Tue-Fri 4 PM) review college games where engine and market differ by 4+ points (`news.py targets`), recording `news.py reviewed` (0-point) or capped `news.py adjust` (scale: starting QB out = 3, questionable = 1.5, several key starters = 1-2). Cap stays at 3; a data-driven college QB model is a possible later project. Claude's college record covers a selected (harder) set of games, so judge it by head-to-head.
  - Basketball (v2.0.0, 2026-10-19): NBA (ESPN history 2015-2026 + live schedule/results) and college basketball (CBBD), models `nba-v1-refit` / `ncaab-v1-refit` (ratings + home court + rest days from the schedule). Final exams in `backtest_results/criteria_basketball.md`: both calibrated, both trail the market, no money edge. Past odds count only real sportsbooks' pregame prices (`odds_math.is_pregame_sportsbook`). Daily refresh: `pull_basketball_history.py nba|ncaab current`. News: scheduled NBA injury checks (noon, 6 PM; every game) and college basketball checks (11 AM, 5 PM; 4+ point disagreements). Basketball seasons are labeled by the year they end (2027 = 2026-27).
  - Club soccer (v3.0.0, live 2026-10-21): Big 5 leagues, three-way (home/draw/away). History `pull_soccer_history.py` (football-data.co.uk 2005-06 to 2025-26 incl. second divisions; this season from ESPN, refreshed in the morning and night routines); team map `teams.SOCCER_TEAMS` (promoted teams must be added each summer; unknown teams are skipped with a NOTE). Model `soccer_model.py`, live settings `soccer-v2-refit-20261021`; final exam in `backtest_results/criteria_soccer.md` (works and calibrated, trails the market, no money edge; ClubElo untested, its API was down). `predict.py soccer_club` -> `predict_soccer.py` (one flag per game at most, draws included); `grade.py soccer_club` -> `grade_soccer.py` (Brier, log loss, RPS). Odds cost 5 credits per pull (1 per league); in `all`, the routines and pre-kickoff windows (no shadow challengers for soccer yet). My picks: a team or Draw plus a chance; the other two outcomes split the rest in the market's proportions. Scheduled Claude team news check 8 AM daily (games in the next 12 hours with a 4+ point engine/market gap; adjustments shift home vs away, draw unchanged; scale: most important player out = 2).
  - Expert signals (v2.1.0): `experts.py` records DraftKings moneyline splits (scheduled 11:45 AM, 5:45 PM) and the Circa Million consensus (Saturday 9 PM) in `expert_signals`, with links; they feed paper-only challengers `dk_sharp_money_v1` and `circa_consensus_v1` (pre-registered). No free history exists, so they're judged on live results only.
- **Next:** watch basketball's first live week; buy the $30 Odds API plan when college basketball starts (Nov 3) (Talal approved). Possible later projects: preseason roster data for basketball early-season ratings, a data-driven player-impact model (the 3-point cap is too small for a missing star). Then club soccer. Waiting on data: evidence-based confidence and rule-8 blending (200 graded games per sport), shadow challengers' promotion bars. Evidence-based Low/Medium/High confidence after 200 graded games per sport.
- **Open items:**
  - Closing lines need the Mac awake ~20-30 min before each kickoff group; Saturday 2026-10-17 it slept and 49 of 57 college closing lines were approximate. The $30 Odds API plan is active (bought 2026-10-21).
  - Results load on the next `pull_games.py` run after games finish. Cancelled/postponed games: `game_status.py` (feeds rarely flag them); kickoffs can move later, never earlier than a logged prediction; every change is logged in `schedule_changes`.
  - nflverse's upcoming starters appear to be last week's starter, so they lag injuries and returns; confirm from news before kickoff.
  - The 3-point cap on Claude's adjustments is too small for a starting-QB change or a missing NBA star; data-driven player-impact models are in QUEUE.md.

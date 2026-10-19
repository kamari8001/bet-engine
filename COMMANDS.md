# Kamari's Prediction Engine: commands

Run everything from the project folder. If a terminal starts somewhere else:

```bash
cd ~/bet-engine
```

`nfl` can be swapped for `ncaaf` (college football), `nba`, or `ncaab` (college basketball), and, where noted, `all` (every sport in season).

## Everyday

| Command | What it does |
|---|---|
| http://localhost:8765 | **The slate page** (dark theme), always running in the background: a Live tab (ESPN scores with each source's pick, refreshing every minute), flip cards for every game (front: each source's pick, prices at your books, pick box; back: warnings, odds by book, line movement, form), a My picks page, and a visual scorecard. It restarts itself after code changes. |
| `python3 show_picks.py nfl` | Every source's current pick side by side (engine, claude, you, market). Add `--days 3` to change how far ahead it looks. |
| `python3 my_pick.py list nfl` | Upcoming games with their id numbers |
| `python3 my_pick.py 3 CHI 60` | Log your pick: game 3, Chicago, 60% to win. College teams use the full name in quotes, e.g. `"Ohio State"`. |
| `python3 grade.py nfl` | Scorecard: accuracy, calibration, paper bets, closing-line value, head-to-head. Add `--season 2026` for a specific season. |
| `python3 auto.py --status` | What automation has done and what's coming, plus credits left |

## The routine by hand

Automation does these for you; use them when you want things fresh right now.
Typical order: `pull_games` → `pull_odds` → `pull_history --current` → `predict`.

| Command | What it does |
|---|---|
| `python3 pull_games.py all` | New games, kickoff time changes, and final scores |
| `python3 pull_odds.py all` | Current moneylines from 10 books. **Costs 1 credit per sport.** |
| `python3 pull_history.py all --current` | Refreshes this season's history so the model's ratings are current |
| `python3 pull_basketball_history.py nba current` | Same for the NBA (recent days from ESPN) |
| `python3 pull_basketball_history.py ncaab current` | Same for college basketball (1 CBBD call) |
| `python3 predict.py nfl` | Logs engine and claude predictions and prints the slate with edges. Add `--days 3` to change how far ahead it looks. |

## Automation

| Command | What it does |
|---|---|
| `python3 auto.py --status` | Status and upcoming pulls |
| `python3 auto.py --dry-run` | What would run right now, without running it |
| `python3 auto.py` | Run whatever is due right now (what the background job does) |
| `tail -20 logs/auto.log` | Last 20 lines of the automation log |
| `launchctl bootout gui/$(id -u)/com.betengine.auto` | **Turn the background job off** |
| `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.betengine.auto.plist` | **Turn it back on** |
| `launchctl bootout gui/$(id -u)/com.betengine.slate` | **Turn the background slate page off** |
| `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.betengine.slate.plist` | **Turn it back on** |
| `python3 slate.py` | Run the slate page by hand instead (only if the background one is off; Ctrl+C stops it) |
| `tail -20 logs/slate.err` | Slate page errors, if the page won't load |

## News (mostly Claude's, but you can use them)

| Command | What it does |
|---|---|
| `python3 news.py games nfl` | Upcoming games with ids, plus starters already recorded |
| `python3 news.py qb <id> <team> "<Name>" confirmed "<link>" "<reason>"` | Record a starting QB (NFL). Use `expected` instead of `confirmed` if it's not official. |
| `python3 news.py check <id> <team> "<Name>" "<link>" "<reason>"` | Records that the news supports the QB the model already assumes ("verified"). Refused if the name doesn't match; use `qb` then. |
| `python3 news.py targets ncaaf [hours]` | College games that need a news check (engine vs market 4+ points apart, not yet reviewed) |
| `python3 news.py reviewed <id> "<link>" "<reason>"` | Records "news checked, nothing material" (a 0-point adjustment; logs a claude prediction) |
| `python3 news.py adjust <id> <points> "<link>" "<reason>"` | Judgment adjustment for the home team, e.g. `1.5` or `-2`. Capped at 3 points per game. |

## Cancelled or postponed games

| Command | What it does |
|---|---|
| `python3 game_status.py cancel <id> "<link>" "<reason>"` | Marks a game cancelled: never graded, stops blocking predictions |
| `python3 game_status.py postpone <id> "YYYY-MM-DD HH:MM" "<link>" "<reason>"` | Moves a kickoff later (Eastern time). Can't move earlier than a logged prediction. |
| `python3 game_status.py list` | Every schedule change recorded |

## Shadow mode (paper tests of challengers)

| Command | What it does |
|---|---|
| `python3 shadow.py report` | Each challenger's record and whether it's eligible for promotion (also on the Scorecard tab) |
| `python3 shadow.py log all` | Logs every challenger for upcoming games (automation does this after each prediction run) |

Challengers and the promotion bar are fixed in `backtest_results/shadow_challengers.md`.

## Checks and setup

| Command | What it does |
|---|---|
| `python3 test_db.py` | Runs the database rule checks on a throwaway database; should end with all checks passed |
| `python3 check_keys.py` | Tests your two API keys (costs 1 Odds API credit) |
| `python3 db.py` | Creates the database or adds any new tables; never deletes data |
| `open -e .env` | Opens your keys file in TextEdit |

## Model work (mostly Claude's)

| Command | What it does |
|---|---|
| `python3 backtest.py check nfl` | How the current settings did on past seasons |
| `python3 backtest.py ablate nfl` | Tests model ideas one at a time against history |
| `python3 backtest.py tune nfl` | Re-tunes settings on the tune seasons (overwrites saved settings) |
| `python3 backtest.py refit nfl` | Refits on all seasons for live use (overwrites saved settings) |
| `python3 market_patterns.py` | Pre-registered tests of whether kinds of games (home underdogs, big favorites, etc.) are mispriced; see `backtest_results/market_patterns_plan.md` |
| `python3 pull_history.py all` | Reloads *all* past seasons. Slow; about 50 college API calls. |
| `python3 pull_basketball_history.py summary` | What basketball history is loaded (games and moneylines per season) |

**Avoid `backtest.py final`**: the one-time final exam has already been used. Running it again is recorded with a warning.

## Git (undo history)

| Command | What it does |
|---|---|
| `git log --oneline -10` | The last 10 saved steps |
| `git status` | Whether anything changed since the last save |
| `git tag -l` | Every released version (see `CHANGELOG.md` for what each changed) |

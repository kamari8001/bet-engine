# Bet Engine commands

Run everything from the project folder. If a terminal starts somewhere else:

```bash
cd ~/bet-engine
```

`nfl` can be swapped for `ncaaf` (college) and, where noted, `all` (both).

## Everyday

| Command | What it does |
|---|---|
| `python3 slate.py` | **The slate page**: opens in your browser (dark theme) with every game, all sources' picks, prices at your books, warnings, scorecards, and a box to log picks. Ctrl+C stops it. |
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

## News (mostly Claude's, but you can use them)

| Command | What it does |
|---|---|
| `python3 news.py games nfl` | Upcoming games with ids, plus starters already recorded |
| `python3 news.py qb <id> <team> "<Name>" confirmed "<link>" "<reason>"` | Record a starting QB (NFL). Use `expected` instead of `confirmed` if it's not official. |
| `python3 news.py adjust <id> <points> "<link>" "<reason>"` | Judgment adjustment for the home team, e.g. `1.5` or `-2`. Capped at 3 points per game. |

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
| `python3 pull_history.py all` | Reloads *all* past seasons. Slow; about 50 college API calls. |

**Avoid `backtest.py final`**: the one-time final exam has already been used. Running it again is recorded with a warning.

## Git (undo history)

| Command | What it does |
|---|---|
| `git log --oneline -10` | The last 10 saved steps |
| `git status` | Whether anything changed since the last save |

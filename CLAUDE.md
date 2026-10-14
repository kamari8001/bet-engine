# Bet Engine: Project Rules

Read this file at the start of every session and follow it.

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
5. **No fake data.** Never invent, placeholder, or estimate data and present it as real. If a source fails, stop and tell me.
6. **Track the closing line.** Store the moneyline at prediction time and the final pregame (closing) moneyline for every game.
7. **Grade everything.** After games finish, compute for each source by sport: Brier score, log loss, calibration, win/loss on flagged bets, and closing-line value.
8. **Blending waits for evidence.** Don't weight sources by track record until a sport has at least 200 graded games. Before that, the final probability is the base model plus Claude's bounded adjustments.
9. **One sport at a time.** A sport isn't "done" until it has data, a backtested and calibrated model, an edge finder, and grading working.
10. **Commit after each working step.** Use git with a clear message so we can always undo.

## Technical defaults

- Language: Python.
- Database: one SQLite file in this folder. Tables:
  - `games`
  - `odds` (with timestamps)
  - `predictions` (source, probability per outcome, projected score, timestamp, locked flag)
  - `results`
  - `adjustments`
- API keys go in a `.env` file that is never committed to git.
- Keep scripts small and named clearly, e.g., `pull_nfl.py`, `predict.py`, `grade.py`.
- A simple local page shows the daily slate and lets me enter my picks.

## Edge and confidence

- **Fair probability:** convert the book's odds to implied probabilities and remove the vig before comparing.
- **Edge:** engine probability minus the no-vig market probability.
- **Flagged bets:** only games where the edge is at or above the threshold in `config` (start at 4 percentage points).
- **Confidence:** combine edge size with data quality (confirmed lineups, sample size, league data depth). Show it as Low, Medium, or High, with the reason.

## Daily routine (once automation is set up)

1. Pull new results, schedules, rosters, injuries, and odds.
2. Run the base model.
3. Claude scans news and proposes bounded adjustments, with sources.
4. Generate today's slate.
5. Grade yesterday's games and update the scorecard.

## Status

Update this section at the end of each session: what's working, what's next, any open problems.

- Current step: Step 0 (setup)
- Next: Step 2 (database and logbook)

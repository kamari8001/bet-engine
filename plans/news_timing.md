# Sharper news timing (QUEUE item 4): plan and pre-registration

Written 2026-10-24, before anything was built. Needs Talal's OK.

## Why
Every study so far says the market already prices what our models know. The one place an edge could
come from is **speed**: reacting to news (a player ruled out) before the betting line moves. Today we
can't even measure that. NBA odds and predictions run at 9 AM and ~30 minutes before tip-off, so when
an injury breaks at 3 PM, our new prediction is logged at the pre-tip run, next to a line that has
already moved. Its closing-line value (CLV) is ~0 by construction.

## What changes (NBA first: the only sport where absences feed the formula automatically)
1. **Injury watcher** (`injury_watch.py`, run by the automation every 10 minutes from 8 AM to the last
   tip-off on NBA days; ESPN's injury list is free). It compares the list with the last look and records
   every status change for a **rotation player in a game within 36 hours** in a new table
   `injury_events`: when we first saw it (UTC), player, team, game, old and new status, the player's
   value in points. Same protections as the logbook (stamped with the current time, never edited or
   deleted).
2. **Instant reaction to material news**: when a change moves a team's missing value by **1.0 point
   of margin or more** (e.g. a starter ruled Out, or listed Out and then cleared) for a game within 24
   hours, the automation immediately pulls NBA odds (1 credit) and runs `predict.py nba`. The new engine
   row (and claude row, if Claude has facts) is logged next to the line **at that moment**. Limits: at
   most one triggered pull per 15 minutes and 30 per day (at most ~900 of the 20,000 monthly credits).
3. **Morning line as the reference**: the 9 AM pull stays as the day's reference line. The scorecard
   gets a "news timing" section for the NBA: for each material event, the market at the event (our
   pull), the morning line, and the close, so it shows whether the line had already moved when we saw
   the news, and whether it kept moving after.
4. Claude's scheduled NBA checks are unchanged (their facts are already graded the same way).

## The test (pre-registered)
- Unit: each material event with a triggered pull before tip-off (one per team and game: the first).
- **News CLV** = how far the no-vig market moved, from our triggered pull to the close, in the
  direction the news points (toward the team that didn't lose the player).
- **Success**: after 100 such events, average news CLV > 0 with its 95% interval above 0 (the line
  kept moving after we saw the news: we're early). Reported at 50 events as a progress look only.
- **Failure**: the interval includes 0 or sits below it: ESPN's list doesn't beat the market, and
  edge-hunting through public injury news is closed. That's a real, useful answer.
- Also reported (information): share of the total move (morning line to close) that had already
  happened when we saw the news; minutes from event to tip-off.
- No probabilities change: same model, same formula; predictions are just logged sooner. Version 4.2.0
  (MINOR).

## Later (not in this step)
NFL starting-QB news (nflverse lags) and soccer team news could get the same treatment if the NBA test
shows we can be early.

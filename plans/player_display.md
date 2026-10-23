# Player display release (QUEUE item 3, follow-up 1): plan

Written 2026-10-23. Needs Talal's OK before building. A MINOR release: display only, nothing stored in
the logbook, no probability changes. NBA only for now (it's the only sport with player ratings;
college basketball follows its own player model).

## Player OVR (1-99)
- Built from the same number the model uses when a player is out: their **value per game** (rating x
  expected minutes; points of margin the team loses without them).
- Placed on a bell curve the same way as team OVR: rank among every rotation player's end-of-season
  value from 2015-16 to 2025-26 (about 4,800 player-seasons), then OVR = 62 + 12 x the normal-curve
  score of that rank, so 62 = a typical rotation player, 80+ = top ~7%, 90+ = top ~1%. Rounded.
- Frozen per model version in `rankings_scale.json` (key `nba_players`), so it compares across
  seasons; rebuilt automatically when the model version changes.
- Players below 10 minutes a game have no OVR ("n/a": the model doesn't count them).
- Early-season note shown on the page: ratings are pulled toward replacement over the summer and
  rebuild over a season's first games, so October OVRs run low. That pull is what predicted best in
  testing (`plans/player_early_season.md`), so the OVR shows what the model actually believes.

## Pages
1. **Team roster** (tap a team name or logo on an NBA card, or a team in Rankings):
   `/team?sport=nba&team=LAL`. Every player seen with the team this season (plus last season's
   rotation players listed injured), sorted by OVR: headshot, name, position, OVR, minutes per game,
   status (ESPN injury list; Claude's recorded facts for the next game). Tapping a player opens the
   profile.
2. **Player profile** `/player?id=<ESPN id>`: headshot (ESPN; a generic silhouette if it fails to
   load), name, team, position, OVR and rank (league and position), value in points, status with
   ESPN's injury detail and date, Claude's recorded notes with sources, last 5 games (date, opponent,
   minutes, points, rebounds, assists, plus-minus), this season's and last season's per-game averages,
   OVR by season (small chart).
3. **Rankings tab, NBA:** a Teams | Players switch. Players: ranked by OVR with a position filter
   (All / Guards / Forwards / Centers; older box scores' PG/SG/SF/PF fold into these), the same season
   picker as teams (past seasons use end-of-season values), top 100 shown.

## How it's built
- `players_view.py` (new, data only): builds the live player book once per model version and day
  (cached like rankings; ~5 s the first time), rosters, profiles, player rankings, OVR scale.
- `slate_views.py` (pages, links on cards), `slate.py` (two routes), `rankings` switch.
- Headshots load straight from ESPN's image server in the browser (nothing downloaded or stored).
- Checks: real output for a few teams and players, phone and desktop screenshots, all slate pages
  still load fast, nothing written to the logbook.
- Version 4.1.0, CHANGELOG, tag.

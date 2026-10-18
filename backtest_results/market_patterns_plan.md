# Market-pattern tests: pre-registered plan

Written and committed **before** any analysis was run (2026-10-18), so the
patterns, bet sides, periods, and pass bar can't be chosen after seeing results.

## Question

Are certain kinds of games mispriced by the sportsbooks by enough to beat their
cut (the vig)? This tests the market itself, not our model.

## Data

- `hist_games` + `hist_odds`, games with both moneylines present.
- NFL: nflverse lines (one book, timing unknown, probably closing), 2006-2025.
- College: CFBD lines 2021-2025, averaged across books (no-vig probability and
  payout both averaged, as in the backtest).
- Market probability = no-vig (vig removed). Payout = the listed price, vig included.
- NFL ties are pushes (stake returned, 0 units).

## Periods

| Sport | Discovery | Confirmation |
|---|---|---|
| NFL | 2006-2018 | 2019-2025 |
| College | 2021-2022 | 2023-2025 |

## Patterns (bet side fixed in advance)

| # | Pattern | Bet | Sports |
|---|---|---|---|
| 1 | Home underdogs (non-neutral games, home team's no-vig chance < 50%) | home team | both |
| 2a | Big underdogs (no-vig chance < 25%) | the underdog | both |
| 2b | Big favorites (no-vig chance > 75%) | the favorite | both |
| 3 | Popular NFL teams: DAL, KC, GB, PIT, SF (every game they play) | against them | NFL |
| 4 | New starting QB (team's starter differs from its previous game this season) | the team with the new QB | NFL |
| 5a | Team lost its previous game this season by 20+ | that team | both |
| 5b | Team won its previous game this season by 20+ | against that team | both |
| 6 | Road team on short rest (4 days or fewer) | the home team | NFL |

Each pattern is evaluated on its own (a game can count in several).

## Measures (per pattern, per period)

- Bets, wins, and expected wins (sum of the market's no-vig chances for the side bet).
- Units won at the listed price (1 unit per bet) and return per bet (ROI).
- z = (wins - expected wins) / sqrt(sum of p(1-p)): how many "standard luck
  units" the result is from what the market predicted.

## Pass bar

A pattern **passes** only if ALL hold:
1. ROI > 0 in the discovery period,
2. ROI > 0 in the confirmation period, and
3. z >= 2 in the confirmation period.

With 13 pattern-sport combinations, about one may look good by chance; anything
short of the bar is treated as noise. A passing pattern becomes a *candidate*
rule only: it would be tested live (shadow mode) before being trusted.

## Results

Run 2026-10-18 with `python3 market_patterns.py`. z = how far wins landed from what the
market's no-vig prices predicted, in standard luck units. ROI is at the listed price, vig included.

### NFL

| # | Pattern (bet) | Period | Bets | Won | Market expected | ROI | z | |
|---|---|---|---|---|---|---|---|---|
| 1 | Home underdogs (home team) | discovery 2006-2018 | 1088 | 396 | 391.1 | +0.2% | +0.31 |  |
| 1 | Home underdogs (home team) | confirmation 2019-2025 | 742 | 247 | 260.2 | -8.2% | -1.04 | fail |
| 2a | Big underdogs (<25%) (the underdog) | discovery 2006-2018 | 762 | 138 | 141.8 | -7.8% | -0.36 |  |
| 2a | Big underdogs (<25%) (the underdog) | confirmation 2019-2025 | 433 | 74 | 82.5 | -15.0% | -1.05 | fail |
| 2b | Big favorites (>75%) (the favorite) | discovery 2006-2018 | 762 | 622 | 618.2 | -1.7% | +0.36 |  |
| 2b | Big favorites (>75%) (the favorite) | confirmation 2019-2025 | 433 | 358 | 349.5 | -1.1% | +1.05 | fail |
| 3 | Popular NFL teams (against them) | discovery 2006-2018 | 950 | 413 | 427.6 | -5.9% | -1.04 |  |
| 3 | Popular NFL teams (against them) | confirmation 2019-2025 | 566 | 206 | 229.9 | -13.6% | -2.19 | fail |
| 4 | New starting QB (the new-QB team) | discovery 2006-2018 | 577 | 225 | 237.1 | -7.1% | -1.11 |  |
| 4 | New starting QB (the new-QB team) | confirmation 2019-2025 | 416 | 156 | 168.7 | -15.6% | -1.38 | fail |
| 5a | After losing by 20+ (that team) | discovery 2006-2018 | 639 | 279 | 266.9 | +4.5% | +1.06 |  |
| 5a | After losing by 20+ (that team) | confirmation 2019-2025 | 334 | 141 | 132.5 | +5.7% | +1.03 | fail |
| 5b | After winning by 20+ (against that team) | discovery 2006-2018 | 690 | 295 | 279.6 | +0.8% | +1.29 |  |
| 5b | After winning by 20+ (against that team) | confirmation 2019-2025 | 358 | 148 | 150.4 | -4.3% | -0.28 | fail |
| 6 | Road team on short rest (the home team) | discovery 2006-2018 | 157 | 93 | 89.3 | -0.7% | +0.64 |  |
| 6 | Road team on short rest (the home team) | confirmation 2019-2025 | 115 | 61 | 62.4 | -5.6% | -0.28 | fail |

### College

| # | Pattern (bet) | Period | Bets | Won | Market expected | ROI | z | |
|---|---|---|---|---|---|---|---|---|
| 1 | Home underdogs (home team) | discovery 2021-2022 | 515 | 165 | 153.4 | +2.9% | +1.15 |  |
| 1 | Home underdogs (home team) | confirmation 2023-2025 | 814 | 251 | 245.7 | -4.0% | +0.42 | fail |
| 2a | Big underdogs (<25%) (the underdog) | discovery 2021-2022 | 624 | 105 | 100.0 | -0.1% | +0.56 |  |
| 2a | Big underdogs (<25%) (the underdog) | confirmation 2023-2025 | 1092 | 132 | 158.0 | -29.9% | -2.28 | fail |
| 2b | Big favorites (>75%) (the favorite) | discovery 2021-2022 | 624 | 519 | 524.0 | -5.7% | -0.56 |  |
| 2b | Big favorites (>75%) (the favorite) | confirmation 2023-2025 | 1092 | 960 | 934.0 | -1.7% | +2.28 | fail |
| 5a | After losing by 20+ (that team) | discovery 2021-2022 | 405 | 166 | 161.9 | +7.1% | +0.48 |  |
| 5a | After losing by 20+ (that team) | confirmation 2023-2025 | 738 | 289 | 288.3 | -9.8% | +0.06 | fail |
| 5b | After winning by 20+ (against that team) | discovery 2021-2022 | 610 | 254 | 256.8 | +1.2% | -0.26 |  |
| 5b | After winning by 20+ (against that team) | confirmation 2023-2025 | 1003 | 393 | 409.0 | -17.8% | -1.19 | fail |

**Verdict: no pattern passes.** None is profitable in both periods with a confirmation z of 2 or more.

Observations (NOT findings: noted for future pre-registered tests only):
- NFL 5a, backing teams after a 20+ point loss, was profitable in both periods (+4.5%, +5.7%),
  but each result is only about 1 standard luck unit from the market. Too weak to call real;
  worth re-testing on future seasons.
- College shows the classic favorite-longshot pattern in 2023-2025: big underdogs won less than
  their prices implied (z -2.28) and big favorites more (z +2.28). But after the vig, backing the
  favorites still lost (-1.7%), so the bias isn't big enough to profit from.
- Fading popular NFL teams lost money; in 2019-2025 those teams won more than the market expected
  (z +2.19 from their side). Backing them was not pre-registered, so this can't be claimed from this
  data; it could be pre-registered and tested on 2026+ games.


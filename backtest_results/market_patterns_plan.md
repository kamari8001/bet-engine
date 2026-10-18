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

(Appended after the run.)

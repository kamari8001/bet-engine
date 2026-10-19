# Shadow challengers: pre-registered definitions

Committed 2026-10-18, **before** any challenger logged anything. A challenger's
definition never changes; a changed idea gets a new version (`_v2`) whose record
starts from zero. Challengers are logged before kickoff in `shadow_predictions` /
`shadow_bets`, kept apart from the real logbook, and never shown on game cards.

## Challengers

### `nfl_after_blowout_loss_v1` (rule, NFL), start 2026-10-18
Bet the team whose **previous game this season** was a loss by **20 or more**
points. If both teams qualify, no bet. Origin: market-pattern test 5a (profitable
in both periods, but z only ~1, so unproven).

### `nfl_back_popular_v1` (rule, NFL), start 2026-10-18
Bet **DAL, KC, GB, PIT or SF** in every game, unless their opponent is also on
the list (then no bet). Origin: market-pattern test 3, where fading these teams
lost; backing them was *not* pre-registered there, so it must be proven here.

### `market_anchor_v1` (model, NFL and college), start 2026-10-18
Win probability = market no-vig probability + **0.25 × (engine − market)**, using
the latest odds pull and the latest engine prediction. Moves only a quarter of the
way from the market toward the engine, so it disagrees with the market less.

## How bets and predictions are logged

- Rule bets: logged **once per game**, the first time the game qualifies and has
  odds, at that moment's best price at my books (FanDuel, DraftKings, Polymarket)
  and the market's no-vig chance for that side.
- Model predictions: logged like engine predictions (a new row when the probability
  moves 1+ point); the graded one is the latest before kickoff.
- Cancelled games and ties are not graded (ties are pushes for rule bets).

## Promotion bar (makes a challenger "eligible"; adoption is Talal's decision)

- **Model:** at least 150 graded games shared with the engine, **better log loss
  than the engine** on those games, **and** better average closing-line value.
- **Rule:** at least 100 graded bets, **positive average closing-line value**, and
  wins beating the market's expected wins by **z >= 2**.

Real-money rules in CLAUDE.md still apply to anything that becomes eligible.

## Added 2026-10-19 (expert signals; committed before any signal was recorded)

Signals are read by scheduled Claude checks from public pages and stored with their
source link in `expert_signals` (before kickoff, never edited). See `experts.py`.

### `dk_sharp_money_v1` (rule, NFL, NCAAF, NBA, NCAAM), start 2026-10-19
From DraftKings' public betting splits (moneyline): bet the side whose **share of money
(handle %) exceeds its share of bets by 15 or more points**, i.e. bigger bettors are on it.
Logged once per game, at the first recorded snapshot where a side qualifies, at that
moment's best price at my books. Origin: the "sharp money" idea; VSiN's own tracking found
majority-handle sides roughly break-even, so this is unproven.

### `circa_consensus_v1` (rule, NFL), start 2026-10-19
From the Circa Sports Million contest's weekly consensus (most-picked sides, released
Saturday evenings): bet the **5 most-picked sides** each week on the moneyline, at the best
price at my books when recorded. The contest is against the spread; this tests whether the
crowd's favorite sides also beat the moneyline closing price.

Promotion bar: the same rule bar as above (100+ graded bets, positive average CLV, z >= 2).

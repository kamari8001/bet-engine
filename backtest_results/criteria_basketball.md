# Basketball final exam: pass/fail criteria

Written and committed **before** any basketball model was built or tuned
(2026-10-19), so the bar can't move after seeing results. Same tests as football
(`criteria.md`).

## Seasons (labeled by the year they end)

| Sport | Tune | Check | Final exam (run once) |
|---|---|---|---|
| NBA | 2015-2020 | 2021-2023 | 2024-2026 |
| College basketball | 2015-2020 | 2021-2023 | 2024-2026 |

Settings are chosen on the tune seasons only; ideas are kept only if they help on
both tune and check seasons; the final-exam seasons are touched once.

## Tests

1. **Works at all.** Log loss beats the "home team always wins at its usual rate" baseline.
2. **Honest percentages.** No 10-point calibration bucket with 50+ games is off by more
   than 8 percentage points.
3. **Vs. the market.** Model and no-vig market Brier / log loss on the same games.
   Information only.
4. **Would it have made money?** Flagged bets (edge >= 4 points), 1 unit each at the
   average listed price, show a profit over at least 150 bets.

## What happens on a fail

Same as football: tests 1-2 fail -> look for a bug (fixing a real bug is allowed and
documented here; re-tuning to pass is not). Test 4 fails -> the sport goes live with
flags paper only / Low confidence. Real money only after 200+ live graded games and
consistent closing-line value.

## Results

Run 2026-10-19. Full numbers in `final_runs.jsonl` (both runs are recorded).

**Data bug found and fixed (allowed: a real bug, not re-tuning).** The first run used
historical "market" prices that included (a) ESPN's "Live Odds" listings from 2024 on, whose
saved price is the in-game price at the final whistle (e.g. -10000 for a team already
winning), and (b) prediction sites' projected lines (teamrankings, numberfire, accuscore,
betegy) plus averages and opening lines (consensus, Opening, Fantasy911). None of those are
pregame prices you could bet. The first NBA run therefore showed an impossible market (log
loss 0.534) and paper bets at nonsense prices (-32.8%). Fix: past odds now count only real
sportsbooks' pregame prices (`odds_math.is_pregame_sportsbook`), and the loader no longer saves
live listings. Model settings were NOT changed between runs; the model never uses odds. College
football was checked and is unaffected (those sources carried no football moneylines). Real
sportsbook moneylines for college basketball exist only from 2023 on.

| Test | NBA (2024-2026, 3,962 games) | College basketball (2024-2026, 18,172 games) |
|---|---|---|
| 1. Works at all | PASS: log loss 0.608 vs baseline 0.690 | PASS: 0.499 vs 0.633 |
| 2. Honest percentages | PASS: worst bucket with 50+ games (10-20%, 82 games) off by 7.0 | PASS: worst bucket off by 3.3 |
| 3. Vs. market (same games) | model 0.608 vs market 0.580 | model 0.552 vs market 0.533 (15,047 games) |
| 4. Made money? | **FAIL**: 2,500 bets, 863-1637, -261.9 units, -10.5% | **FAIL**: 9,145 bets, 4775-4370, -384.9 units, -4.2% |

**Note on NBA timing:** from 2024 on, ESPN records each book's true closing price; earlier
seasons store a price of unknown timing. True closing lines include final injury and rest news,
which a ratings-only model can't see, so the NBA gap widened on the exam seasons even though the
model itself improved (0.640 -> 0.608).

**Verdict:** both sports work and are calibrated but trail the market; neither made money.
They go live with flags paper only / Low confidence, like football. For basketball, player
availability (injuries, rest) is the main thing the model misses, so the news step matters most.

**Note added 2026-10-21:** "Betradar" (a sports-data supplier, not a sportsbook) was later found among
ESPN's NBA odds providers: 151 NBA game prices. They're now excluded (`odds_math.NOT_A_SPORTSBOOK`) and
deleted from `hist_odds`. The final exam above (run 2026-10-19) counted them in the market average for
those games; it is not re-run (one-time rule), and the effect is small (about 151 of roughly 4,000 games
had a Betradar price alongside real sportsbooks').

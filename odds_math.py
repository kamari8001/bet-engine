"""Moneyline math: implied probability, removing the vig, fair odds."""


def implied_prob(ml):
    """American odds -> the book's implied probability (includes the vig).
    -150 -> 0.600, +130 -> 0.435."""
    if ml < 0:
        return -ml / (-ml + 100)
    return 100 / (ml + 100)


def no_vig(*mls):
    """Remove the book's margin by scaling the implied probabilities to sum to 1.
    no_vig(-150, +130) -> (0.580, 0.420). Works for 2-way and 3-way markets."""
    probs = [implied_prob(ml) for ml in mls]
    total = sum(probs)
    return tuple(p / total for p in probs)


def decimal_odds(ml):
    """American odds -> total return per 1 unit staked, including the stake.
    -150 -> 1.667, +130 -> 2.30."""
    return 1 + (100 / -ml if ml < 0 else ml / 100)


def fair_moneyline(p):
    """Probability -> American odds with no vig. 0.60 -> -150, 0.40 -> +150."""
    if p >= 0.5:
        return -round(100 * p / (1 - p))
    return round(100 * (1 - p) / p)


def american_from_decimal(dec):
    """European decimal odds (e.g. 2.50) -> American moneyline (+150), rounded to a whole number.
    None for missing or impossible prices (1.00 or less)."""
    if dec is None or dec <= 1.0:
        return None
    ml = round((dec - 1) * 100) if dec >= 2.0 else round(-100 / (dec - 1))
    return ml if abs(ml) >= 100 else (100 if ml > 0 else -100)


# Entries in the historical odds that are NOT prices you could bet before the game:
# prediction sites' own projections, averages, opening lines, and live in-game prices.
NOT_A_SPORTSBOOK = {"numberfire", "teamrankings", "accuscore", "betegy", "consensus", "opening",
                    "fantasy911.com", "espn: no moneyline", "market average", "market average (close)"}


def is_pregame_sportsbook(provider):
    """True only for a real sportsbook's pregame price (used when reading past odds)."""
    name = (provider or "").strip().lower()
    return name not in NOT_A_SPORTSBOOK and "live" not in name and "in-play" not in name

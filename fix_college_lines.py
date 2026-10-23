"""Verify the home/away orientation of stored college football lines against CFBD's named favorite.

Usage: python3 fix_college_lines.py [--apply]

CFBD's line objects carry formattedSpread, e.g. "Kansas -14": the favorite by name. A stored line
whose moneyline favors the other side is reversed (seen at neutral sites, where the sportsbook's
"home" can differ from CFBD's). Without --apply it only counts; with --apply it swaps the reversed
rows' home/away moneylines and spread sign. One CFBD call per season.
"""
import json
import sys

import config
import db
from pull_history import CFBD, fetch

SEASONS = range(2021, 2027)


def main():
    apply = "--apply" in sys.argv
    conn = db.connect()
    headers = {"Authorization": f"Bearer {config.CFBD_API_KEY}"}
    checked = reversed_ = unknown = 0
    for year in SEASONS:
        for attempt in range(4):                     # CFBD returns the odd 502; retry with a pause
            try:
                lines = json.loads(fetch(f"{CFBD}/lines?year={year}&seasonType=both", headers))
                break
            except Exception as e:
                if attempt == 3:
                    raise
                import time
                time.sleep(5 * (attempt + 1))
        by_id = {str(g["id"]): g for g in lines}
        for g in conn.execute("SELECT id, external_id, home_team, away_team, neutral_site FROM hist_games"
                              " WHERE sport = 'ncaaf' AND season = ?", (year,)).fetchall():
            src = by_id.get(g["external_id"])
            if not src:
                continue
            for line in src.get("lines") or []:
                fs = line.get("formattedSpread") or ""
                hm, am = line.get("homeMoneyline"), line.get("awayMoneyline")
                if hm is None or am is None or not fs.strip() or fs.strip().upper() in ("PK", "EVEN"):
                    continue
                name, _, num = fs.rpartition(" ")
                try:
                    spread = float(num)
                except ValueError:
                    continue
                if spread >= 0:
                    continue                            # "+" spreads name the underdog; skip
                fav = name.strip()
                if fav == g["home_team"]:
                    fav_home = True
                elif fav == g["away_team"]:
                    fav_home = False
                else:
                    unknown += 1
                    continue
                checked += 1
                ml_fav_home = hm < am                   # the lower (more negative) price is the favorite
                if fav_home != ml_fav_home:
                    reversed_ += 1
                    if apply:
                        conn.execute("UPDATE hist_odds SET home_ml = away_ml, away_ml = home_ml,"
                                     " home_spread = -home_spread WHERE hist_game_id = ? AND provider = ?",
                                     (g["id"], line.get("provider")))
        print(f"  {year}: checked so far {checked}, reversed {reversed_}, favorite name unmatched {unknown}", flush=True)
    conn.commit()
    print(f"{'Fixed' if apply else 'Would fix'} {reversed_} reversed lines of {checked} checked.")


if __name__ == "__main__":
    main()

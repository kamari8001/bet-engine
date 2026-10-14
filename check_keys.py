"""Make one test call to each data service to confirm the API keys work.

Never prints the keys themselves.
"""

import json
import sys
import urllib.error
import urllib.request

import config


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp), resp.headers


def check_cfbd():
    print("== CollegeFootballData ==")
    if not config.CFBD_API_KEY:
        print("FAIL  CFBD_API_KEY is empty in .env")
        return False
    try:
        lines, _ = get("https://api.collegefootballdata.com/lines?year=2025&week=1",
                       {"Authorization": f"Bearer {config.CFBD_API_KEY}"})
    except urllib.error.HTTPError as e:
        print(f"FAIL  HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    with_ml = [g for g in lines if any(l.get("homeMoneyline") for l in g.get("lines", []))]
    print(f"OK    key works: {len(lines)} games returned for 2025 week 1")
    print(f"      {len(with_ml)} of them include moneylines")
    if with_ml:
        g = with_ml[0]
        print(f"      sample: {g['awayTeam']} at {g['homeTeam']}, "
              f"final {g.get('awayScore')}-{g.get('homeScore')}")
        for l in g["lines"]:
            print(f"        {l.get('provider')}: home {l.get('homeMoneyline')}, "
                  f"away {l.get('awayMoneyline')}, spread {l.get('spread')}")
    return True


def check_odds_api():
    print("\n== The Odds API ==")
    if not config.ODDS_API_KEY:
        print("FAIL  ODDS_API_KEY is empty in .env")
        return False
    url = ("https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"
           f"?regions=us&markets=h2h&oddsFormat=american&apiKey={config.ODDS_API_KEY}")
    try:
        events, headers = get(url)
    except urllib.error.HTTPError as e:
        print(f"FAIL  HTTP {e.code}: {e.read().decode()[:200]}")
        return False
    print(f"OK    key works: {len(events)} upcoming NFL games with moneylines")
    print(f"      credits used this month: {headers.get('x-requests-used')}, "
          f"remaining: {headers.get('x-requests-remaining')}")
    if events:
        e = events[0]
        print(f"      sample: {e['away_team']} at {e['home_team']}, kickoff {e['commence_time']}")
        for book in e["bookmakers"][:4]:
            prices = {o["name"]: o["price"] for o in book["markets"][0]["outcomes"]}
            print(f"        {book['title']}: " + ", ".join(f"{k} {v:+d}" for k, v in prices.items()))
    return True


if __name__ == "__main__":
    ok = check_cfbd() & check_odds_api()
    sys.exit(0 if ok else 1)

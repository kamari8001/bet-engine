"""The slate page: upcoming games, every source's pick, prices, warnings, and a
box to log your own picks. Runs only on this Mac.

Usage: python3 slate.py [--port 8765] [--no-open]
Then open http://localhost:8765 (it opens automatically). Ctrl+C stops it.

The page only reads the database, except for logging your picks (same rules
as my_pick.py). Odds and engine predictions come from automation / predict.py.
"""

import contextlib
import html
import io
import json
import sys
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import config
import db
import grade
from cautions import game_warnings
from my_pick import PickError, log_pick
from odds_math import decimal_odds, fair_moneyline
from predict import ODDS_MAX_AGE, latest_odds, parse_utc

SPORTS = {"nfl": "NFL", "ncaaf": "College"}
SOURCES = ("engine", "claude", "me")

CSS = """
:root { --bg:#0e1116; --card:#161b22; --line:#262d36; --text:#e6edf3; --muted:#8b949e;
        --accent:#58a6ff; --good:#3fb950; --flag:#d29922; --warn:#f0883e; --bad:#f85149; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header { position:sticky; top:0; z-index:5; background:rgba(14,17,22,.95); border-bottom:1px solid var(--line);
         padding:12px 20px; display:flex; gap:18px; align-items:center; flex-wrap:wrap; }
header h1 { font-size:16px; margin:0 8px 0 0; }
nav a { color:var(--muted); text-decoration:none; padding:6px 10px; border-radius:6px; }
nav a.on { color:var(--text); background:var(--card); border:1px solid var(--line); }
.note { color:var(--muted); font-size:12px; }
main { padding:16px 20px 40px; max-width:1400px; margin:auto; }
.msg { padding:10px 14px; border-radius:8px; margin-bottom:14px; border:1px solid var(--line); }
.msg.ok { background:rgba(63,185,80,.12); border-color:var(--good); }
.msg.err { background:rgba(248,81,73,.12); border-color:var(--bad); }
.day { color:var(--muted); font-weight:600; margin:22px 0 8px; text-transform:uppercase; font-size:12px; letter-spacing:.06em; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(410px, 1fr)); gap:12px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; }
.top { display:flex; justify-content:space-between; gap:10px; align-items:baseline; }
.teams { font-size:16px; font-weight:600; }
.time { color:var(--muted); white-space:nowrap; }
.sub { color:var(--muted); font-size:12px; margin-top:2px; }
table { width:100%; border-collapse:collapse; margin-top:10px; font-variant-numeric:tabular-nums; }
th { color:var(--muted); font-weight:500; text-align:right; font-size:12px; padding:3px 4px; }
th:first-child, td:first-child { text-align:left; }
td { padding:4px; text-align:right; border-top:1px solid var(--line); }
.bar { height:6px; background:#30363d; border-radius:3px; overflow:hidden; min-width:70px; }
.bar span { display:block; height:100%; background:var(--accent); }
.edge.pos { color:var(--good); } .edge.neg { color:var(--muted); }
.flag { color:var(--flag); font-weight:600; }
.warns { margin:10px 0 0; padding:0; list-style:none; }
.warns li { color:var(--warn); font-size:12px; padding-left:16px; position:relative; }
.warns li:before { content:"!"; position:absolute; left:3px; font-weight:700; }
form.pick { display:flex; gap:8px; margin-top:12px; align-items:center; flex-wrap:wrap; }
select, input { background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 8px; font:inherit; }
input[type=number] { width:76px; }
button { background:var(--accent); color:#0e1116; border:0; border-radius:6px; padding:7px 12px; font-weight:600; cursor:pointer; }
button:hover { filter:brightness(1.1); }
.started { color:var(--muted); font-size:12px; margin-top:12px; }
pre { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; overflow-x:auto;
      font:12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
"""

esc = html.escape


def money(x):
    """+12.4 -> '+$12', -0.3 -> '$0', -31 -> '-$31'."""
    x = round(x)
    return "$0" if x == 0 else f"{'+' if x > 0 else '-'}${abs(x)}"


def pct(p):
    return "&ndash;" if p is None else f"{p:.0%}" if p in (0, 1) else f"{p * 100:.1f}%"


def page(title, active, body, msg=None):
    tabs = "".join(
        f'<a class="{"on" if active == key else ""}" href="{url}">{label}</a>'
        for key, url, label in (("slate-nfl", "/slate?sport=nfl", "NFL"), ("slate-ncaaf", "/slate?sport=ncaaf", "College"),
                                ("score-nfl", "/scorecard?sport=nfl", "NFL scorecard"),
                                ("score-ncaaf", "/scorecard?sport=ncaaf", "College scorecard")))
    banner = ""
    if msg:
        kind, text = msg
        banner = f'<div class="msg {kind}">{esc(text)}</div>'
    now = datetime.now(timezone.utc)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title>
<style>{CSS}</style></head><body>
<header><h1>Bet Engine</h1><nav>{tabs}</nav>
<span class="note">Updated {esc(db.fmt_et(db.to_utc(now)))} &middot; all flags are low confidence, paper only</span></header>
<main>{banner}{body}</main></body></html>"""


def latest_rows(conn, game_id):
    return {s: conn.execute("SELECT * FROM predictions WHERE game_id = ? AND source = ? AND corrects_id IS NULL"
                            " ORDER BY created_at DESC, id DESC LIMIT 1", (game_id, s)).fetchone()
            for s in SOURCES}


def game_card(conn, g, now):
    rows = latest_rows(conn, g["id"])
    final = rows["claude"] or rows["engine"]
    mkt = latest_odds(conn, g["id"])
    warnings = game_warnings(conn, g, final, mkt, now)
    away, home = g["away_team"], g["home_team"]
    kickoff = parse_utc(g["start_time_utc"])
    started = kickoff <= now

    sub = []
    if g["neutral_site"]:
        sub.append("neutral site")
    if final:
        inp = json.loads(final["note"] or "{}").get("inputs", {})
        if inp.get("away_starter_name") or inp.get("home_starter_name"):
            def qb(side):
                status = inp.get(f"{side}_starter_status") or ""
                tag = "confirmed" if status.startswith("confirmed") else "news" if "Claude" in status \
                    else "assumed" if "assumed" in status else "nflverse"
                return f"{esc(inp.get(f'{side}_starter_name') or '?')} ({tag})"
            sub.append(f"QBs: {qb('away')} / {qb('home')}")
        sub.append(f"projected {esc(away)} {final['proj_away_score']:.0f} &ndash; {esc(home)} {final['proj_home_score']:.0f}"
                   if final["proj_home_score"] is not None else "")

    prob_rows = ""
    for s in SOURCES:
        r = rows[s]
        p_home = r["p_home"] if r else None
        bar = f'<div class="bar"><span style="width:{p_home * 100:.1f}%"></span></div>' if r else ""
        prob_rows += f"<tr><td>{s}</td><td>{pct(None if p_home is None else 1 - p_home)}</td><td>{pct(p_home)}</td><td>{bar}</td></tr>"
    if mkt:
        bar = f'<div class="bar"><span style="width:{mkt["p_home"] * 100:.1f}%;background:#8b949e"></span></div>'
        prob_rows += f"<tr><td>market (no-vig)</td><td>{pct(1 - mkt['p_home'])}</td><td>{pct(mkt['p_home'])}</td><td>{bar}</td></tr>"

    price_rows = ""
    if final:
        p = final["p_home"]
        stale = mkt is not None and now - parse_utc(mkt["captured_at"]) > ODDS_MAX_AGE
        for side, team, prob in (("away", away, 1 - p), ("home", home, p)):
            fair = fair_moneyline(prob)
            if mkt:
                mprob = mkt["p_home"] if side == "home" else 1 - mkt["p_home"]
                edge = prob - mprob
                best = mkt["best"].get(side)
                price = f"{best[0]:+d} <span class='note'>{esc(best[1])}</span>" if best else "<span class='note'>not at your books</span>"
                ev = money(100 * (prob * decimal_odds(best[0]) - 1)) if best else "&ndash;"
                flag = " <span class='flag'>FLAG</span>" if edge >= config.EDGE_THRESHOLD and not stale and best else ""
                price_rows += (f"<tr><td>{esc(team)}</td><td>{fair:+d}</td><td>{price}</td>"
                               f"<td class='edge {'pos' if edge > 0 else 'neg'}'>{edge * 100:+.1f}{flag}</td><td>{ev}</td></tr>")
            else:
                price_rows += f"<tr><td>{esc(team)}</td><td>{fair:+d}</td><td colspan=3 class='note'>no odds yet</td></tr>"
    odds_note = (f"odds as of {esc(db.fmt_et(mkt['captured_at']))}, {mkt['books']} books" if mkt else "no odds yet")

    if started:
        form = '<div class="started">Game has started: picks are locked.</div>'
    else:
        mine = rows["me"]
        current = ""
        if mine:
            team, prob = (home, mine["p_home"]) if mine["p_home"] >= 0.5 else (away, 1 - mine["p_home"])
            current = f"<span class='note'>your current pick: {esc(team)} {prob:.0%}</span>"
        form = f"""<form class="pick" method="post" action="/pick">
<input type="hidden" name="game_id" value="{g['id']}"><input type="hidden" name="sport" value="{esc(g['sport'])}">
<select name="team"><option value="{esc(away)}">{esc(away)}</option><option value="{esc(home)}">{esc(home)}</option></select>
<input type="number" name="pct" min="1" max="99" step="1" placeholder="win %" required>
<button type="submit">Log pick</button>{current}</form>"""

    warn_html = "".join(f"<li>{esc(w)}</li>" for w in warnings)
    return f"""<div class="card" id="g{g['id']}">
<div class="top"><div class="teams">{esc(away)} <span class="note">at</span> {esc(home)}</div>
<div class="time">{esc(db.fmt_et(g['start_time_utc']))}</div></div>
<div class="sub">{' &middot; '.join(x for x in sub if x)}</div>
<table><tr><th>win %</th><th>{esc(away)}</th><th>{esc(home)}</th><th></th></tr>{prob_rows}</table>
<table><tr><th>{esc(odds_note)}</th><th>fair ML</th><th>best at your books</th><th>edge (pts)</th><th>per $100</th></tr>{price_rows}</table>
{f'<ul class="warns">{warn_html}</ul>' if warn_html else ''}{form}</div>"""


def slate_page(conn, sport, days, msg):
    now = datetime.now(timezone.utc)
    games = conn.execute(
        "SELECT * FROM games WHERE sport = ? AND start_time_utc > ? AND start_time_utc <= ?"
        " ORDER BY start_time_utc, id",
        (sport, db.to_utc(now - timedelta(hours=4)), db.to_utc(now + timedelta(days=days)))).fetchall()
    if not games:
        body = f"<p class='note'>No {SPORTS[sport]} games in the next {days} days.</p>"
    else:
        body, day = "", None
        for g in games:
            d = db.utc_to_eastern(g["start_time_utc"]).strftime("%A, %B %-d")
            if d != day:
                body += ("</div>" if day else "") + f'<div class="day">{esc(d)}</div><div class="grid">'
                day = d
            body += game_card(conn, g, now)
        body += "</div>"
    intro = (f"<p class='note'>{len(games)} {SPORTS[sport]} games, next {days} days (games that started in the last "
             f"4 hours stay visible, locked). Edge = win % minus the market's no-vig %. Flags need an edge of "
             f"{config.EDGE_THRESHOLD:.0%}+ and fresh odds. Per $100 = expected profit at that price if the win % is right.</p>")
    return page(f"{SPORTS[sport]} slate", f"slate-{sport}", intro + body, msg)


def scorecard_page(conn, sport):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        grade.print_scorecard(sport, grade.CURRENT_SEASON, *grade.grade(conn, sport, grade.CURRENT_SEASON))
    return page(f"{SPORTS[sport]} scorecard", f"score-{sport}", f"<pre>{esc(buf.getvalue())}</pre>")


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, url):
        self.send_response(303)
        self.send_header("Location", url)
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        sport = q.get("sport", "nfl") if q.get("sport") in SPORTS else "nfl"
        conn = db.connect()
        try:
            if url.path in ("/", "/slate"):
                msg = (q["kind"], q["msg"]) if "msg" in q and q.get("kind") in ("ok", "err") else None
                self._send(slate_page(conn, sport, int(q.get("days", 7)), msg))
            elif url.path == "/scorecard":
                self._send(scorecard_page(conn, sport))
            else:
                self._send(page("Not found", "", "<p>Not found.</p>"), 404)
        finally:
            conn.close()

    def do_POST(self):
        if self.path != "/pick":
            return self._send(page("Not found", "", "<p>Not found.</p>"), 404)
        length = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(length).decode()).items()}
        sport = form.get("sport") if form.get("sport") in SPORTS else "nfl"
        conn = db.connect()
        try:
            text, kind = log_pick(conn, int(form["game_id"]), form["team"], float(form["pct"])), "ok"
        except (PickError, KeyError, ValueError) as e:
            text, kind = str(e) or "Couldn't read the pick.", "err"
        finally:
            conn.close()
        anchor = f"#g{form.get('game_id', '')}"
        self._redirect(f"/slate?sport={sport}&kind={kind}&msg={urllib.parse.quote(text)}{anchor}")

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


def main():
    a = sys.argv[1:]
    port = int(a[a.index("--port") + 1]) if "--port" in a else 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)   # this Mac only
    url = f"http://localhost:{port}"
    print(f"Slate page running at {url}  (Ctrl+C to stop)")
    if "--no-open" not in a:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

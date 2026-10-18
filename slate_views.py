"""HTML for the slate page (dark theme). Data comes from slate_data.py."""

import html
import json

import config
import db
from version import APP_NAME, APP_VERSION, model_versions

esc = html.escape
SOURCE_LABEL = {"engine": "Engine", "claude": "Claude", "me": "You", "market": "Market"}
# Chart series colors (validated for color-blind safety on the card surface #161b22)
SERIES = {"engine": "#3987e5", "me": "#d95926", "claude": "#199e70"}

CSS = """
:root { --card-h:470px; --bg:#0e1116; --card:#161b22; --raise:#1c222b; --line:#262d36; --text:#e6edf3; --muted:#8b949e;
        --soft:#c3c9d1; --accent:#58a6ff; --good:#3fb950; --flag:#d29922; --warn:#f0883e; --bad:#f85149; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { position:sticky; top:0; z-index:20; background:rgba(14,17,22,.96); border-bottom:1px solid var(--line);
         padding:12px 20px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
header h1 { font-size:16px; margin:0 6px 0 0; white-space:nowrap; }
header h1 .ver { font-size:11px; font-weight:500; color:var(--muted); border:1px solid var(--line); border-radius:999px;
                 padding:1px 7px; margin-left:4px; vertical-align:middle; cursor:help; }
nav a { color:var(--muted); text-decoration:none; padding:6px 10px; border-radius:6px; }
nav a.on { color:var(--text); background:var(--card); border:1px solid var(--line); }
.note { color:var(--muted); font-size:12px; }
main { padding:16px 20px 48px; max-width:1400px; margin:auto; }
.msg { padding:10px 14px; border-radius:8px; margin-bottom:14px; border:1px solid var(--line); }
.msg.ok { background:rgba(63,185,80,.12); border-color:var(--good); }
.msg.err { background:rgba(248,81,73,.12); border-color:var(--bad); }
.day { color:var(--muted); font-weight:600; margin:24px 0 10px; text-transform:uppercase; font-size:12px; letter-spacing:.06em; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(400px, 1fr)); gap:14px; }
.logo { width:22px; height:22px; object-fit:contain; vertical-align:middle; }
.logo.sm { width:16px; height:16px; }
.tm { display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
th { color:var(--muted); font-weight:500; text-align:right; font-size:12px; padding:4px 6px; }
td { padding:6px; text-align:right; border-top:1px solid var(--line); }
th:first-child, td:first-child, th.l, td.l { text-align:left; }
.when { white-space:nowrap; }
td.pk { padding-left:18px; } td.pp { font-weight:600; width:48px; }
.panel { overflow-x:auto; }
.panel table .tm { max-width:160px; }
.vs { color:var(--muted); margin-top:2px; white-space:nowrap; display:flex; align-items:center; gap:4px; } .vs .tm { color:var(--text); }
.panel table .tm { max-width:140px; }
.pos { color:var(--good); } .neg { color:var(--muted); }
.flag { color:var(--flag); font-weight:600; font-size:11px; border:1px solid var(--flag); border-radius:4px; padding:0 4px; margin-left:4px; }

/* flip cards */
.card { perspective:1400px; cursor:pointer; }
.inner { position:relative; height:var(--card-h); transition:transform .55s ease; transform-style:preserve-3d; }
.card.flipped .inner { transform:rotateY(180deg); }
.face { position:absolute; inset:0; overflow-y:auto; backface-visibility:hidden; -webkit-backface-visibility:hidden; background:var(--card);
        border:1px solid var(--line); border-radius:12px; padding:14px; min-width:0; }
.back { transform:rotateY(180deg); }
.top { display:flex; justify-content:space-between; align-items:center; gap:10px; }
.matchup { display:flex; align-items:center; gap:8px; font-size:16px; font-weight:600; flex-wrap:wrap; }
.at { color:var(--muted); font-weight:400; font-size:13px; }
.time { color:var(--muted); white-space:nowrap; font-size:13px; }
.sub { color:var(--muted); font-size:12px; margin:3px 0 10px; }
.sub2 { display:flex; justify-content:space-between; align-items:center; gap:8px; margin:4px 0 8px; min-height:22px; }
.sub2 .time { font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.matchup { flex-wrap:nowrap !important; overflow:hidden; }
.matchup .tm { min-width:0; }
.tm .nm { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.face table .tm { max-width:150px; }
.prices th, .prices td { white-space:nowrap; } .prices .tm { max-width:112px; } .prices .note { font-size:11px; }
.badge { background:rgba(240,136,62,.14); color:var(--warn); border:1px solid rgba(240,136,62,.5); border-radius:999px;
         padding:1px 9px; font-size:12px; font-weight:600; cursor:pointer; font-family:inherit; }
.picks td.src { color:var(--soft); width:72px; border-left:3px solid transparent; padding-left:8px; }
.picks tr.dis td.src { border-left-color:var(--flag); }
.picks tr.mkt td { color:var(--muted); }
.picks td.pct { font-weight:600; width:64px; }
.picks td { height:34px; }
.picks td.l { padding-left:14px; }
.logo.sm { flex:0 0 16px; }
.section { margin-top:12px; }
.section h4 { margin:0 0 4px; font-size:12px; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:.05em; }
form.pick { display:flex; gap:8px; margin-top:12px; align-items:center; flex-wrap:wrap; cursor:auto; }
select, input { background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:6px; padding:6px 8px; font:inherit; }
input[type=number] { width:76px; }
button.go { background:var(--accent); color:#0e1116; border:0; border-radius:6px; padding:7px 12px; font-weight:600; cursor:pointer; }
.hint { color:var(--muted); font-size:11px; text-align:right; margin-top:8px; }
.locked { color:var(--muted); font-size:12px; margin-top:12px; }
.mine { color:var(--soft); font-size:12px; }
.back td { padding:3px 6px; } .back .section { margin-top:10px; }
.books tr.my td { color:var(--text); } .books tr:not(.my) td { color:var(--muted); }
.books td.best { color:var(--good); font-weight:600; }
.form-row { display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-top:1px solid var(--line); gap:8px; }
.chips { display:flex; gap:4px; }
.chip { width:22px; height:22px; border-radius:5px; display:inline-flex; align-items:center; justify-content:center;
        font-size:11px; font-weight:700; background:var(--raise); border:1px solid var(--line); color:var(--soft); }
.chip.W { color:var(--good); border-color:rgba(63,185,80,.5); } .chip.L { color:var(--bad); border-color:rgba(248,81,73,.45); }
ul.warns { margin:4px 0 0; padding:0; list-style:none; }
ul.warns li { color:var(--warn); font-size:12px; padding:3px 0 3px 16px; position:relative; }
ul.warns li:before { content:"!"; position:absolute; left:3px; font-weight:700; }
.kv { display:flex; justify-content:space-between; font-size:13px; padding:4px 0; border-top:1px solid var(--line); gap:10px; }
.kv span:first-child { color:var(--muted); }

/* my picks & scorecard */
.panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
.panel h2 { font-size:15px; margin:0 0 10px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fill, minmax(230px, 1fr)); gap:12px; margin-bottom:16px; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }
.tile .name { display:flex; align-items:center; gap:8px; color:var(--soft); font-weight:600; }
.dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.big { font-size:28px; font-weight:600; margin:6px 0 2px; }
.tile .kv { font-size:12px; }
.ok { color:var(--good); } .bad { color:var(--bad); }
.result.W { color:var(--good); font-weight:600; } .result.L { color:var(--bad); font-weight:600; }
.chart-wrap { position:relative; }
.tip { position:absolute; pointer-events:none; background:#0b0e13; border:1px solid var(--line); border-radius:8px;
       padding:8px 10px; font-size:12px; display:none; white-space:nowrap; z-index:5; }
.legend { display:flex; gap:16px; font-size:12px; color:var(--soft); margin-bottom:6px; flex-wrap:wrap; }
.toggle { display:inline-flex; border:1px solid var(--line); border-radius:8px; overflow:hidden; margin-bottom:14px; }
.toggle a { color:var(--muted); text-decoration:none; padding:6px 14px; }
.toggle a.on { background:var(--card); color:var(--text); }
a { color:var(--accent); }
.lgrid { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:12px; }
.lcard { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
.lstatus { display:flex; justify-content:space-between; color:var(--muted); font-size:12px; margin-bottom:6px; }
.lstatus.on { color:var(--good); font-weight:600; }
.lrow { display:flex; justify-content:space-between; align-items:center; padding:3px 0; font-size:15px; }
.lscore { font-size:20px; font-weight:600; color:var(--soft); font-variant-numeric:tabular-nums; }
.lscore.lead { color:var(--text); }
.lteam { display:inline-flex; align-items:center; gap:6px; }
.ball { color:var(--flag); font-size:10px; line-height:1; display:inline-flex; align-items:center; }
.lcard .picks { margin-top:8px; }
.lcard .picks td { height:28px; padding:3px 6px; }
.lcard .picks tr.me td { background:rgba(88,166,255,.08); }
.bad { color:var(--bad); }
details summary { color:var(--accent); cursor:pointer; font-size:12px; margin-top:8px; }
"""

JS = """
document.querySelectorAll('.card').forEach(function (c) {
  c.addEventListener('click', function (e) {
    if (e.target.closest('form, input, select, button.go, a')) return;
    c.classList.toggle('flipped');
  });
});
"""


def page(title, active, body, msg=None, scripts=""):
    tabs = "".join(
        f'<a class="{"on" if active == key else ""}" href="{url}">{label}</a>'
        for key, url, label in (("slate-nfl", "/slate?sport=nfl", "NFL"),
                                ("slate-ncaaf", "/slate?sport=ncaaf", "College"),
                                ("live", "/live", "Live"),
                                ("mine", "/mine", "My picks"),
                                ("score", "/scorecard?sport=nfl", "Scorecard")))
    banner = f'<div class="msg {msg[0]}">{esc(msg[1])}</div>' if msg else ""
    mv = model_versions()
    models = "models: " + ", ".join(f"{'NFL' if k == 'nfl' else 'College'} {v}" for k, v in mv.items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} &middot; {esc(APP_NAME)}</title>
<style>{CSS}</style></head><body>
<header><h1>{esc(APP_NAME)} <span class="ver" title="{esc(models)}">v{APP_VERSION}</span></h1><nav>{tabs}</nav>
<span class="note">{esc(models)} &middot; all flags are low confidence, paper only</span></header>
<main>{banner}{body}</main><script>{JS}{scripts}</script></body></html>"""


def team(name, logo, small=False):
    img = (f'<img class="logo{" sm" if small else ""}" src="{esc(logo)}" alt="" loading="lazy" '
           f'onerror="this.remove()">') if logo else ""
    return f'<span class="tm" title="{esc(name)}">{img}<span class="nm">{esc(name)}</span></span>'


def money(x):
    return "$0" if not x else f"{'+' if x > 0 else '-'}${abs(x)}"


def signed(x):
    return "0" if not x else f"{x:+d}"


# ---------- slate ----------

def card(v):
    away = team(v["away"], v["away_logo"])
    home = team(v["home"], v["home_logo"])
    n_warn = len(v["warnings"])
    badge = (f'<button type="button" class="badge" title="Warnings on the back of the card">&#9888; {n_warn}</button>'
             if n_warn else "")
    sub = []
    if v["neutral"]:
        sub.append("neutral site")
    if v["projected"]:
        sub.append(f"projected {esc(v['away'])} {v['projected'][0]} &ndash; {esc(v['home'])} {v['projected'][1]}")
    logos = {v["away"]: v["away_logo"], v["home"]: v["home_logo"]}

    rows = ""
    for p in v["picks"]:
        if p["team"] is None:
            rows += (f'<tr><td class="src">{SOURCE_LABEL[p["source"]]}</td><td class="l neg">no pick</td>'
                     f'<td></td><td></td></tr>')
            continue
        edge = "" if p["edge"] is None else f'<span class="{"pos" if p["edge"] > 0 else "neg"}">{signed(p["edge"])} pts</span>'
        title = ' title="Picks a different team than the market"' if p["disagrees"] else ""
        rows += (f'<tr class="{"dis" if p["disagrees"] else ""}"{title}><td class="src">{SOURCE_LABEL[p["source"]]}</td>'
                 f'<td class="l">{team(p["team"], logos[p["team"]], True)}</td>'
                 f'<td class="pct">{p["pct"]}%</td><td>{edge}</td></tr>')
    m = v["market"]
    if m:
        rows += (f'<tr class="mkt"><td class="src">Market</td><td class="l">{team(m["team"], logos[m["team"]], True)}</td>'
                 f'<td class="pct">{m["pct"]}%</td><td>no vig</td></tr>')

    prices = ""
    for pr in v["prices"]:
        best = (f'{pr["best"]:+d} <span class="note">{esc(pr["book"])}</span>' if pr["best"] is not None
                else '<span class="note">&ndash;</span>')
        edge = "" if pr["edge"] is None else f'<span class="{"pos" if pr["edge"] > 0 else "neg"}">{signed(pr["edge"])}</span>'
        flag = '<span class="flag">FLAG</span>' if pr["flag"] else ""
        ev = money(pr["ev"]) if pr["ev"] is not None else "&ndash;"
        prices += (f'<tr><td>{team(pr["team"], logos[pr["team"]], True)}</td><td>{pr["fair"]:+d}</td>'
                   f'<td>{best}</td><td>{edge}{flag}</td><td>{ev}</td></tr>')
    stale = " &middot; odds are old: no flags" if m and m["stale"] else ""
    prices_html = (f'<div class="section"><h4>Prices at your books{stale}</h4><table class="prices"><tr><th>team</th>'
                   f'<th>fair</th><th>best price</th><th>edge</th><th>per $100</th></tr>{prices}</table></div>'
                   if prices else "")

    if v.get("cancelled"):
        form = '<div class="locked">Game cancelled: nothing on it is graded.</div>'
    elif v["started"]:
        form = '<div class="locked">Game has started: picks are locked.</div>'
    else:
        form = f"""<form class="pick" method="post" action="/pick">
<input type="hidden" name="game_id" value="{v['id']}"><input type="hidden" name="sport" value="{esc(v['sport'])}">
<select name="team"><option value="{esc(v['away'])}">{esc(v['away'])}</option><option value="{esc(v['home'])}">{esc(v['home'])}</option></select>
<input type="number" name="pct" min="1" max="99" step="1" placeholder="win %" required>
<button class="go" type="submit">Log pick</button></form>"""

    front = f"""<div class="face front">
<div class="matchup">{away}<span class="at">at</span>{home}</div>
<div class="sub2"><span class="time">{'<b style="color:var(--bad)">CANCELLED</b> &middot; ' if v.get('cancelled') else ''}{esc(v['kickoff'])}{' &middot; ' + ' &middot; '.join(sub) if sub else ''}</span>{badge}</div>
<table class="picks"><tr><th>source</th><th class="l">pick</th><th>win %</th><th>vs market</th></tr>{rows}</table>
{prices_html}{form}<div class="hint">click card for details &#8635;</div></div>"""

    # back
    books = ""
    for b in v["books"]:
        books += (f'<tr class="{"my" if b["mine"] else ""}"><td>{esc(b["book"])}{" &#9733;" if b["mine"] else ""}</td>'
                  f'<td class="{"best" if b["best_away"] else ""}">{b["away"]:+d}</td>'
                  f'<td class="{"best" if b["best_home"] else ""}">{b["home"]:+d}</td></tr>')
    books_html = (f'<div class="section"><h4>Odds by book &middot; {esc(v["odds_time"] or "")}</h4>'
                  f'<table class="books"><tr><th>book (&#9733; = yours)</th><th>{esc(v["away"])}</th>'
                  f'<th>{esc(v["home"])}</th></tr>{books}</table></div>') if books else \
        '<div class="section"><h4>Odds by book</h4><div class="note">no odds yet</div></div>'
    mv = v["movement"]
    move_html = ""
    if mv:
        what = "no real move" if mv["pts"] == 0 else f'moved {mv["pts"]} pts toward {esc(mv["toward"])}'
        move_html = (f'<div class="section"><h4>Line movement</h4>'
                     f'<div class="kv"><span>since {esc(mv["since"])}</span><span>{what}</span></div>'
                     f'<div class="kv"><span>{esc(v["away"])} / {esc(v["home"])} (no vig)</span>'
                     f'<span>{mv["away_then"]}% / {mv["home_then"]}% &rarr; {mv["away_now"]}% / {mv["home_now"]}%</span></div></div>')
    form_rows = ""
    for side in ("away", "home"):
        f = v["form"][side]
        chips = "".join(
            f'<span class="chip {g["result"]}" title="{g["result"]} {g["score"]} {g["where"]} {esc(g["opp"])} ({g["date"]})">'
            f'{g["result"]}</span>' for g in reversed(f["games"]))
        form_rows += (f'<div class="form-row">{team(v[side], v[side + "_logo"], True)}'
                      f'<span class="note">{f["record"]} this season</span><span class="chips">{chips or "<span class=note>no games yet</span>"}</span></div>')
    form_html = f'<div class="section"><h4>Form (last 5, oldest &rarr; newest; hover for scores)</h4>{form_rows}</div>'
    extra = ""
    if v["qbs"]:
        extra += (f'<div class="kv"><span>QBs</span><span>{esc(v["qbs"]["away"]["name"])} ({v["qbs"]["away"]["tag"]}) / '
                  f'{esc(v["qbs"]["home"]["name"])} ({v["qbs"]["home"]["tag"]})</span></div>')
    if v["rest"]:
        extra += f'<div class="kv"><span>Rest days</span><span>{v["rest"][0]} / {v["rest"][1]}</span></div>'
    extra_html = f'<div class="section"><h4>Matchup</h4>{extra}</div>' if extra else ""
    warn_html = ("".join(f"<li>{esc(w)}</li>" for w in v["warnings"]))
    warn_html = (f'<div class="section"><h4>Warnings</h4><ul class="warns">{warn_html}</ul></div>' if warn_html
                 else '<div class="section"><h4>Warnings</h4><div class="note">none</div></div>')
    news_items = ""
    for n in v.get("news", []):
        what = "reviewed, no change" if n["points"] == 0 else f'{esc(v["home"])} {n["points"]:+.1f} pts'
        news_items += (f'<div class="kv"><span>{esc(n["time"])}: {what}</span>'
                       f'<span><a href="{esc(n["source"])}" target="_blank" rel="noopener">source</a></span></div>'
                       f'<div class="note" style="padding:0 0 4px">{esc(n["reason"])}</div>')
    news_html = f'<div class="section"><h4>News check</h4>{news_items}</div>' if news_items else ""
    back = f"""<div class="face back">
<div class="top"><div class="matchup">{away}<span class="at">at</span>{home}</div><span class="time">{esc(v['kickoff'])}</span></div>
{warn_html}{news_html}{books_html}{move_html}{form_html}{extra_html}<div class="hint">click to flip back &#8634;</div></div>"""
    return f'<div class="card" id="g{v["id"]}"><div class="inner">{front}{back}</div></div>'


def slate_page(sport, days, groups, msg):
    label = "NFL" if sport == "nfl" else "College"
    if not groups:
        body = f"<p class='note'>No {label} games in the next {days} days.</p>"
    else:
        body, day = "", None
        for d, v in groups:
            if d != day:
                body += ("</div>" if day else "") + f'<div class="day">{esc(d)}</div><div class="grid">'
                day = d
            body += card(v)
        body += "</div>"
    intro = (f"<p class='note'>{len(groups)} {label} games, next {days} days. &#9888; = warnings on the back. "
             f"An orange edge on a row means that source picks a different team than the market. "
             f"Flags need an edge of {config.EDGE_THRESHOLD:.0%}+ and fresh odds.</p>")
    return page(f"{label} slate", f"slate-{sport}", intro + body, msg)


# ---------- live ----------

LIVE_LABEL = {"ahead": ("winning", "pos"), "behind": ("losing", "bad"), "tied": ("tied", "neg"),
              "won": ("won", "pos"), "lost": ("lost", "bad")}


def live_card(v):
    info = v["live"]
    if info and info["state"] != "pre":
        a, h = info["away_score"], info["home_score"]
        status = esc(info["detail"]) + (f' &middot; {esc(info["down"])}' if info.get("down") and info["state"] == "in" else "")
    else:
        a = h = None
        status = esc(v["kickoff"])

    def row(side):
        ball = ' <span class="ball" title="has the ball">&#9679;</span>' if info and info.get("possession") == side \
            and info["state"] == "in" else ""
        score = v["live"][f"{side}_score"] if a is not None else ""
        lead = a is not None and ((side == "home" and h > a) or (side == "away" and a > h))
        return (f'<div class="lrow"><span class="lteam">{team(v[side], v[side + "_logo"])}{ball}</span>'
                f'<span class="lscore{" lead" if lead else ""}">{score}</span></div>')

    picks = ""
    for p in v["picks"]:
        label, cls = LIVE_LABEL.get(p["status"], ("", "neg"))
        picks += (f'<tr class="{"me" if p["source"] == "me" else ""}"><td class="src">{SOURCE_LABEL[p["source"]]}</td>'
                  f'<td class="l">{team(p["team"], p["logo"], True)}</td><td class="pct">{p["pct"]}%</td>'
                  f'<td class="{cls}">{label}</td></tr>')
    picks_html = (f'<table class="picks"><tr><th>source</th><th class="l">pick</th><th>win %</th><th></th></tr>{picks}</table>'
                  if picks else '<div class="note">No picks logged for this game.</div>')
    return (f'<div class="lcard"><div class="lstatus{" on" if v["state"] == "in" else ""}">{status}'
            f'<span class="note">{v["sport"].upper()}</span></div>{row("away")}{row("home")}{picks_html}</div>')


def live_fragment(groups, error):
    out = f'<div class="msg err">{esc(error)}: showing kickoff times and picks only.</div>' if error else ""
    titles = (("in", "In progress"), ("post", "Final"), ("pre", "Later today"))
    if not any(groups.values()):
        return out + '<p class="note">No games today.</p>'
    for key, title in titles:
        if groups[key]:
            out += f'<div class="day">{title} ({len(groups[key])})</div><div class="lgrid">'
            out += "".join(live_card(v) for v in groups[key]) + "</div>"
    return out


LIVE_JS = """
setInterval(function () {
  fetch('/live?fragment=1&sport=' + (new URLSearchParams(location.search).get('sport') || 'nfl')).then(function (r) { return r.text(); }).then(function (h) {
    document.getElementById('live').innerHTML = h;
    document.getElementById('upd').textContent = new Date().toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', second: '2-digit'});
  });
}, 60000);
"""


def live_page(groups, error, sport, counts):
    toggle = ('<div class="toggle">' + "".join(
        f'<a class="{"on" if sport == k else ""}" href="/live?sport={k}">{n}'
        f'{f" <span class=note>({counts[k]} live)</span>" if counts.get(k) else ""}</a>'
        for k, n in (("nfl", "NFL"), ("ncaaf", "College"))) + "</div>")
    intro = toggle + ("<p class='note'>Scores from ESPN, refreshed every minute while this tab is open (last update "
             "<span id='upd'>now</span>). Display only: official results still come from nflverse and CFBD. "
             "Picks are the ones logged before kickoff.</p>")
    return page("Live", "live", intro + f'<div id="live">{live_fragment(groups, error)}</div>', scripts=LIVE_JS)


# ---------- my picks ----------

def mine_page(upcoming, finished, summary):
    def pick_cell(x, logos, names):
        """Two table cells: team (left) and win % (right), so columns line up."""
        if not x:
            return '<td class="l neg">&ndash;</td><td></td>'
        logo = logos[0] if x[0] == names[0] else logos[1]
        return f'<td class="l pk">{team(x[0], logo, True)}</td><td class="pp">{x[1]}%</td>'

    s = summary
    tiles = f"""<div class="tiles">
<div class="tile"><div class="name">Graded picks</div><div class="big">{s['graded']}</div>
<div class="note">{s['right']} picked the winner ({(s['right'] / s['graded'] if s['graded'] else 0):.0%})</div></div>"""
    for key, label in (("me", "You"), ("engine", "Engine"), ("market", "Market")):
        val = s["avg"][key]
        tiles += (f'<div class="tile"><div class="name">{label}: accuracy</div>'
                  f'<div class="big">{"&ndash;" if val is None else f"{val:.3f}"}</div>'
                  f'<div class="note">avg Brier score on your graded games{" (" + str(s["compared"]) + " compared)" if key != "me" else ""}; lower is better</div></div>')
    tiles += "</div>"

    up = "".join(
        f'<tr><td class="when">{esc(u["kickoff"])}<div class="note">{u["sport"].upper()}</div></td>'
        f'<td class="l">{team(u["away"], u["logos"][0], True)}<div class="vs">@ {team(u["home"], u["logos"][1], True)}</div></td>'
        f'{pick_cell(u["me"], u["logos"], (u["away"], u["home"]))}'
        f'{pick_cell(u["engine"], u["logos"], (u["away"], u["home"]))}'
        f'{pick_cell(u["market"], u["logos"], (u["away"], u["home"]))}</tr>' for u in upcoming)
    up_html = (f'<div class="panel"><h2>Upcoming ({len(upcoming)})</h2><table><tr><th>kickoff</th><th class="l">game</th>'
               f'<th class="l" colspan="2">your pick</th><th class="l" colspan="2">engine</th>'
               f'<th class="l" colspan="2">market when you picked</th></tr>{up}</table></div>'
               if upcoming else '<div class="panel"><h2>Upcoming</h2><div class="note">No upcoming picks.</div></div>')

    waiting = [f for f in finished if f.get("correct") is None]
    finished = [f for f in finished if f.get("correct") is not None]
    wait_rows = "".join(
        f'<tr><td class="when">{esc(f["kickoff"])}<div class="note">{f["sport"].upper()}</div></td>'
        f'<td class="l">{team(f["away"], f["logos"][0], True)}<div class="vs">@ {team(f["home"], f["logos"][1], True)}</div></td>'
        f'{pick_cell(f["me"], f["logos"], (f["away"], f["home"]))}'
        f'{pick_cell(f["engine"], f["logos"], (f["away"], f["home"]))}'
        f'<td class="note">{esc(f["final"])}</td></tr>' for f in waiting)
    wait_html = (f'<div class="panel"><h2>In progress / awaiting result ({len(waiting)})</h2><table><tr><th>kickoff</th>'
                 f'<th class="l">game</th><th class="l" colspan="2">your pick</th><th class="l" colspan="2">engine</th><th>status</th></tr>{wait_rows}</table></div>'
                 if waiting else "")
    fin = ""
    for f in finished:
        if f.get("correct") is None:
            res = f'<span class="note">{esc(f["final"])}</span>'
        else:
            res = f'<span class="result {"W" if f["correct"] else "L"}">{"right" if f["correct"] else "wrong"}</span>'
        b = f.get("brier", {})
        briers = " / ".join("&ndash;" if k not in b else f"{b[k]:.3f}" for k in ("me", "engine", "market"))
        fin += (f'<tr><td class="when">{esc(f["kickoff"])}<div class="note">{f["sport"].upper()}</div></td>'
                f'<td class="l">{team(f["away"], f["logos"][0], True)}<div class="vs">@ {team(f["home"], f["logos"][1], True)}</div>'
                f'<div class="note">{esc(f["final"]) if f.get("correct") is not None else ""}</div></td>'
                f'{pick_cell(f["me"], f["logos"], (f["away"], f["home"]))}<td>{res}</td>'
                f'{pick_cell(f["engine"], f["logos"], (f["away"], f["home"]))}<td>{briers}</td></tr>')
    fin_html = (f'<div class="panel"><h2>Finished ({len(finished)})</h2><table><tr><th>kickoff</th><th class="l">game</th>'
                f'<th class="l" colspan="2">your pick</th><th>result</th><th class="l" colspan="2">engine</th>'
                f'<th>Brier: you / engine / market</th></tr>{fin}</table></div>'
                if finished else "")
    intro = ("<p class='note'>Every game you picked, both sports. Brier score = how far a probability was from "
             "what happened (0 is perfect, 0.25 is a coin flip); lower is better.</p>")
    return page("My picks", "mine", intro + tiles + up_html + wait_html + fin_html)


# ---------- scorecard ----------

def calibration_chart(tiles):
    """SVG: predicted vs. actual home-win rate per 10% bucket, one series per source."""
    W, H, L, R, T, B = 560, 340, 48, 16, 14, 40
    pw, ph = W - L - R, H - T - B
    x = lambda p: L + p * pw
    y = lambda p: T + (1 - p) * ph
    grid = ""
    for v in (0, .25, .5, .75, 1):
        grid += (f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#262d36" stroke-width="1"/>'
                 f'<text x="{L - 8}" y="{y(v) + 4:.1f}" fill="#8b949e" font-size="11" text-anchor="end">{v:.0%}</text>'
                 f'<text x="{x(v):.1f}" y="{H - B + 18}" fill="#8b949e" font-size="11" text-anchor="middle">{v:.0%}</text>')
    grid += (f'<line x1="{x(0)}" y1="{y(0)}" x2="{x(1)}" y2="{y(1)}" stroke="#8b949e" stroke-width="1" stroke-dasharray="4 4"/>'
             f'<text x="{x(.97):.1f}" y="{y(.97) + 16:.1f}" fill="#8b949e" font-size="11" text-anchor="end">perfectly calibrated</text>'
             f'<text x="{L + pw / 2}" y="{H - 4}" fill="#8b949e" font-size="11" text-anchor="middle">predicted chance the home team wins</text>'
             f'<text transform="translate(12 {T + ph / 2}) rotate(-90)" fill="#8b949e" font-size="11" text-anchor="middle">how often it actually won</text>')
    series, legend = "", ""
    for src in ("engine", "claude", "me"):
        bins = tiles[src].get("bins") or []
        if not bins:
            continue
        color = SERIES[src]
        legend += f'<span><span class="dot" style="background:{color}"></span> {SOURCE_LABEL[src]}</span>'
        for b in bins:
            info = json.dumps({"s": SOURCE_LABEL[src], "lo": b["lo"], "pred": round(b["pred"] * 100),
                               "act": round(b["actual"] * 100), "n": b["n"]})
            series += (f'<circle cx="{x(b["pred"]):.1f}" cy="{y(b["actual"]):.1f}" r="6" fill="{color}" '
                       f'opacity="{1 if b["n"] >= 10 else 0.4}" stroke="#161b22" stroke-width="2"/>'
                       f'<circle class="hit" data-i=\'{esc(info)}\' cx="{x(b["pred"]):.1f}" cy="{y(b["actual"]):.1f}" r="12" fill="transparent"/>')
    if not series:
        return '<div class="note">Not enough graded games yet.</div>'
    svg = (f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:{W}px" role="img" '
           f'aria-label="Calibration chart">{grid}{series}</svg>')
    return f'<div class="legend">{legend}</div><div class="chart-wrap">{svg}<div class="tip"></div></div>'


CHART_JS = """
document.querySelectorAll('.chart-wrap').forEach(function (w) {
  var tip = w.querySelector('.tip');
  w.querySelectorAll('.hit').forEach(function (h) {
    h.addEventListener('mouseenter', function () {
      var d = JSON.parse(h.getAttribute('data-i'));
      tip.innerHTML = '<b>' + d.s + '</b> &middot; ' + d.lo + '-' + (d.lo + 10) + '% bucket<br>predicted ' + d.pred +
        '% &middot; actually won ' + d.act + '%<br>' + d.n + ' game' + (d.n === 1 ? '' : 's');
      tip.style.display = 'block';
    });
    h.addEventListener('mousemove', function (e) {
      var r = w.getBoundingClientRect();
      tip.style.left = (e.clientX - r.left + 14) + 'px'; tip.style.top = (e.clientY - r.top - 10) + 'px';
    });
    h.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
  });
});
"""


def scorecard_page(sport, sc):
    label = "NFL" if sport == "nfl" else "College"
    switch = ('<div class="toggle">' + "".join(
        f'<a class="{"on" if sport == k else ""}" href="/scorecard?sport={k}">{n}</a>'
        for k, n in (("nfl", "NFL"), ("ncaaf", "College"))) + "</div>")
    t = sc["tiles"]
    tiles = '<div class="tiles">'
    for src in ("market", "engine", "claude", "me"):
        x = t[src]
        dot = f'<span class="dot" style="background:{SERIES[src]}"></span>' if src in SERIES else '<span class="dot" style="background:#8b949e"></span>'
        if not x["n"]:
            tiles += f'<div class="tile"><div class="name">{dot}{SOURCE_LABEL[src]}</div><div class="big">&ndash;</div><div class="note">no graded games yet</div></div>'
            continue
        rows = f'<div class="kv"><span>graded games</span><span>{x["n"]}</span></div>'
        rows += f'<div class="kv"><span>log loss</span><span>{x["log_loss"]:.3f}</span></div>'
        if "bets" in x:
            b = x["bets"]
            cls = "ok" if b["units"] > 0 else "bad"
            rows += (f'<div class="kv"><span>paper bets</span><span>{b["w"]}-{b["l"]}, '
                     f'<span class="{cls}">{b["units"]:+.1f}u ({b["roi"]:+.0%})</span></span></div>')
        elif src != "market":
            rows += '<div class="kv"><span>paper bets</span><span>none</span></div>'
        if "clv" in x:
            c = x["clv"]
            avg = round(c["avg"] * 100, 1) or 0.0
            rows += (f'<div class="kv"><span>closing-line value</span><span>{avg:+.1f} pts avg, '
                     f'{c["pos"]:.0%} positive</span></div>')
        tiles += (f'<div class="tile"><div class="name">{dot}{SOURCE_LABEL[src]}</div>'
                  f'<div class="big">{x["brier"]:.3f}</div><div class="note">Brier score (lower is better)</div>{rows}</div>')
    tiles += "</div>"
    approx = (f'<p class="note">{sc["approx"]} game(s) had no odds pull within an hour of kickoff, so their '
              f'closing-line value is approximate.</p>') if sc["approx"] else ""

    h2h = "".join(
        f'<tr><td>{SOURCE_LABEL[r["pair"][0]]} vs {SOURCE_LABEL[r["pair"][1]]}</td><td>{r["n"]}</td>'
        + "".join(f'<td class="{"ok" if r[s] == min(r[a] for a in (*r["pair"], "market")) else ""}">'
                  f'<span class="note">{SOURCE_LABEL[s]}</span> {r[s]:.3f}</td>'
                  for s in (*r["pair"], "market")) + "</tr>" for r in sc["h2h"])
    h2h_html = (f'<div class="panel"><h2>Head-to-head (same games only)</h2><table><tr><th>matchup</th><th>games</th>'
                f'<th colspan="3">Brier score on those games</th></tr>{h2h}</table>'
                f'<div class="note" style="margin-top:6px">Brier scores; green = best of the three.</div></div>') if h2h else ""

    table_rows = ""
    for src in ("engine", "claude", "me"):
        for b in t[src].get("bins") or []:
            table_rows += (f'<tr><td>{SOURCE_LABEL[src]}</td><td>{b["lo"]}-{b["lo"] + 10}%</td><td>{b["n"]}</td>'
                           f'<td>{b["pred"]:.0%}</td><td>{b["actual"]:.0%}</td></tr>')
    chart = (f'<div class="panel"><h2>Calibration: do the percentages mean what they say?</h2>'
             f'<div class="note" style="margin-bottom:8px">Points near the dashed line = honest percentages. '
             f'Faded points have fewer than 10 games, so luck dominates them; hover any point for its game count.</div>'
             f'{calibration_chart(t)}<details><summary>Show as table</summary><table><tr><th>source</th><th>bucket</th>'
             f'<th>games</th><th>predicted</th><th>won</th></tr>{table_rows}</table></details></div>')
    rule8 = (f'<p class="note">Rule 8: {sc["graded"]} graded games this season; '
             f'{"enough" if sc["graded"] >= 200 else str(200 - sc["graded"]) + " more needed"} before weighting sources by track record.</p>')
    shadow_rows = ""
    for r in sc.get("shadow", []):
        status = '<span class="ok">eligible</span>' if r["eligible"] else '<span class="note">not yet</span>'
        if r["type"] == "rule":
            if r["graded"]:
                z = "&ndash;" if r["z"] is None else f'{r["z"]:+.2f}'
                clv = "&ndash;" if r["clv"] is None else f'{r["clv"] * 100:+.1f} pts'
                res = (f'{r["w"]}-{r["l"]}{"-" + str(r["push"]) if r["push"] else ""}, '
                       f'<span class="{"ok" if r["units"] > 0 else "bad"}">{r["units"]:+.1f}u ({r["roi"]:+.0%})</span>, '
                       f'z {z}, CLV {clv}')
            else:
                res = f'{r["logged"]} bet(s) logged, none graded yet'
        else:
            if r["graded"]:
                f = lambda x: "&ndash;" if x is None else f"{x * 100:+.1f} pts"
                res = (f'{r["graded"]} games: log loss {r["ll_ch"]:.3f} vs engine {r["ll_eng"]:.3f}, '
                       f'CLV {f(r["clv_ch"])} vs {f(r["clv_eng"])}')
            else:
                res = "no graded games yet"
        shadow_rows += (f'<tr><td><b>{esc(r["name"])}</b><div class="note">{esc(r["about"])} ({r["type"]})</div></td>'
                        f'<td class="l">{res}</td><td>{status}<div class="note">{esc(r["bar"])}</div></td></tr>')
    shadow_html = (f'<div class="panel"><h2>Shadow challengers (paper tests, kept out of the slate)</h2>'
                   f'<table><tr><th>challenger</th><th class="l">record so far</th><th>promotion</th></tr>{shadow_rows}</table>'
                   f'<div class="note" style="margin-top:6px">Definitions and the bar are fixed in '
                   f'backtest_results/shadow_challengers.md. Eligible means you decide; it never switches on by itself.</div></div>'
                   ) if shadow_rows else ""
    body = switch + tiles + approx + h2h_html + chart + shadow_html + rule8
    return page(f"{label} scorecard", "score", body, scripts=CHART_JS)

"""HTML for the slate page (dark theme). Data comes from slate_data.py."""

import html
import urllib.parse
import json

import config
import db
from pull_history import SHORT_NAMES, SPORT_NAMES
from version import APP_NAME, APP_VERSION, model_versions

esc = html.escape
SOURCE_LABEL = {"engine": "Engine", "claude": "Claude", "me": "You", "market": "Market"}
# Chart series colors (validated for color-blind safety on the card surface #161b22)
SERIES = {"engine": "#3987e5", "me": "#d95926", "claude": "#199e70"}

CSS = """
:root { --card-h:495px; --bg:#0a0d13; --card:#121821; --raise:#19202b; --line:#222a36; --text:#e8edf4; --muted:#909aa8;
        --soft:#c6ccd5; --accent:#5aa9ff; --good:#3fb950; --flag:#d8a12a; --warn:#f0883e; --bad:#f85149;
        --glow:rgba(90,169,255,.35); --ease:cubic-bezier(.2,.8,.2,1); color-scheme:dark; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:14px/1.45 "Doppio One", system-ui, -apple-system, "Segoe UI", sans-serif;
       font-variant-ligatures:none; font-feature-settings:"liga" 0, "clig" 0, "dlig" 0; }
header { position:sticky; top:0; z-index:20; background:rgba(14,17,22,.96); border-bottom:1px solid var(--line);
         padding:12px 20px; display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
header h1 { font-size:16px; margin:0 6px 0 0; white-space:nowrap; }
header h1 .ver { font-size:11px; font-weight:500; color:var(--muted); border:1px solid var(--line); border-radius:999px;
                 padding:1px 7px; margin-left:4px; vertical-align:middle; cursor:help; }
nav a { color:var(--muted); text-decoration:none; padding:6px 10px; border-radius:6px; }
nav a.on { color:var(--text); background:var(--card); border:1px solid var(--line); }
.note { color:var(--muted); font-size:12px; } .note.warn { color:var(--warn); }
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
table.rk { width:auto; } .rk td { padding:6px 10px; } .rk th { padding:6px 10px; }
.rk td.num, .rk th.num { text-align:right; } .rk td.rank { color:var(--muted); width:36px; text-align:right; }
.rk td.team { text-align:left; white-space:nowrap; } .rk td.team img { width:22px; height:22px; vertical-align:middle; margin-right:8px; }
.rk td.conf, .rk td.form { text-align:left; white-space:nowrap; }
.rk .qb { color:var(--muted); font-size:11px; margin-left:6px; }
.ovr { display:inline-block; min-width:34px; text-align:center; border-radius:6px; padding:2px 6px; font-weight:700; color:#0e1116; }
.o6 { background:#2ea043; } .o5 { background:#56c26a; } .o4 { background:#9fdc9a; } .o3 { background:#c3c9d1; } .o2 { background:#f0a35e; } .o1 { background:#f85149; }
a.tlink { color:inherit; text-decoration:none; } a.tlink:hover { text-decoration:underline; }
.thead { display:flex; align-items:center; gap:10px; font-size:20px; margin:4px 0 8px; } .tlogo { width:32px; height:32px; }
.ovrchart { width:100%; height:auto; display:block; } .ovrchart .gl { stroke:var(--line); stroke-width:1; }
.ovrchart .ax { fill:var(--muted); font-size:11px; } .ovrchart .ln { fill:none; stroke:var(--accent); stroke-width:2; }
.ovrchart .dot { fill:var(--accent); stroke:var(--card); stroke-width:2; } .ovrchart .hit { fill:transparent; }
.ovrchart .pt:hover .dot { r:6; }
.mv.up { color:var(--good); } .mv.down { color:var(--bad); } .mv { font-size:12px; white-space:nowrap; }
.form span { display:inline-block; width:14px; text-align:center; font-size:12px; font-weight:700; }
.form .W { color:var(--good); } .form .L { color:var(--bad); } .form .T, .form .D { color:var(--muted); }
.filters { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
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
.card.three .inner { height:calc(var(--card-h) + 40px); } .card.three .prices .tm { max-width:96px; }
.card.three .prices td, .card.three .prices th { padding-left:4px; padding-right:4px; }
.models { } .hint .touch { display:none; }
@media (hover: none) { .hint .mouse { display:none; } .hint .touch { display:inline; } }


/* ---------- modern look (v3.1.1) ---------- */
body { background:
         radial-gradient(1100px 520px at 8% -8%, rgba(90,169,255,.09), transparent 60%),
         radial-gradient(900px 480px at 100% -4%, rgba(63,185,80,.05), transparent 60%), var(--bg);
       background-repeat:no-repeat; min-height:100vh; }
header { background:rgba(10,13,19,.72); backdrop-filter:blur(16px) saturate(150%); -webkit-backdrop-filter:blur(16px) saturate(150%);
         border-bottom:1px solid rgba(255,255,255,.06); }
header h1 { letter-spacing:.01em; }
nav a { transition:color .2s, background-color .2s; }
nav a:hover { color:var(--text); background:rgba(255,255,255,.04); }
nav a.on { background:rgba(90,169,255,.13); border-color:rgba(90,169,255,.35); color:var(--text); view-transition-name:navpill; }
.toggle { background:rgba(255,255,255,.02); }
.toggle a { transition:color .2s, background-color .2s; }
.toggle a.on { background:rgba(90,169,255,.13); color:var(--text); }
.face, .panel, .tile, .lcard {
  background:linear-gradient(180deg, rgba(255,255,255,.028), rgba(255,255,255,0) 38%), var(--card);
  border:1px solid var(--line); border-radius:14px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.035), 0 10px 28px -16px rgba(0,0,0,.7); }
.inner { transition:transform .65s var(--ease); }
.card { scroll-margin-top:96px; transition:transform .25s var(--ease); }
@media (hover: hover) {
  .card:hover { transform:translateY(-3px); }
  .card:hover .face { border-color:rgba(90,169,255,.32); box-shadow:inset 0 1px 0 rgba(255,255,255,.04), 0 16px 34px -18px rgba(0,0,0,.85), 0 0 0 1px rgba(90,169,255,.08); }
  .tile:hover, .lcard:hover { border-color:rgba(90,169,255,.28); }
  .rk tr:hover td { background:rgba(255,255,255,.025); }
  button.go:hover { filter:brightness(1.08); box-shadow:0 6px 18px -8px var(--glow); }
}
.card:target .face { border-color:rgba(90,169,255,.55); }
button.go { transition:transform .12s var(--ease), filter .2s, box-shadow .2s; }
button.go:active, .badge:active, .toggle a:active, nav a:active { transform:scale(.96); }
.badge { transition:transform .12s var(--ease), background-color .2s; }
select, input { transition:border-color .2s, box-shadow .2s; }
select:focus, input:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px rgba(90,169,255,.18); }
.face::-webkit-scrollbar { width:6px; } .face::-webkit-scrollbar-thumb { background:var(--line); border-radius:6px; }
.face { scrollbar-width:thin; scrollbar-color:var(--line) transparent; }
.chip, .ovr { transition:transform .2s var(--ease); }
.msg { animation:msg-in .45s var(--ease) both; }
.msg.ok { animation:msg-in .45s var(--ease) both, msg-out .6s ease 6s forwards; }

/* entrance: cards and panels rise in, one after another (--i set by the page script) */
.anim .card, .anim .lcard, .anim .tile, .anim .panel { animation:rise .5s var(--ease) both; animation-delay:calc(var(--i, 0) * 40ms); }
.anim .ovr { animation:pop .45s var(--ease) both; animation-delay:calc(var(--i, 0) * 40ms + 120ms); }
.picks tr.dis td.src { animation:edge-pulse 1.4s ease .6s 1; }
@keyframes rise { from { opacity:0; translate:0 10px; } to { opacity:1; translate:0 0; } }
@keyframes pop { from { opacity:0; scale:.8; } to { opacity:1; scale:1; } }
@keyframes msg-in { from { opacity:0; transform:translateY(-8px); } to { opacity:1; transform:none; } }
@keyframes msg-out { to { opacity:0; transform:translateY(-6px); height:0; padding-top:0; padding-bottom:0; margin:0; border-width:0; } }
@keyframes edge-pulse { 0%, 100% { box-shadow:none; } 40% { box-shadow:inset 4px 0 0 var(--flag), -6px 0 14px -6px var(--flag); } }
@keyframes face-in { from { opacity:0; scale:.82 1; } to { opacity:1; scale:1 1; } }

/* lighter, cleaner details */
td { border-top-color:rgba(255,255,255,.055); }
.kv, .form-row { border-top-color:rgba(255,255,255,.055); }
select, input { border-radius:10px; background:rgba(255,255,255,.03); }
button.go { border-radius:10px; background:linear-gradient(180deg, #6db3ff, #4a9df5); }
.flag { border-radius:999px; padding:0 7px; background:rgba(216,161,42,.12); }
.picks td:last-child span.pos { background:rgba(63,185,80,.12); border-radius:999px; padding:1px 7px; }
.prices .flag { padding:0 5px; }
.prices .tm { max-width:96px; } .prices td, .prices th { padding-left:4px; padding-right:4px; }
.prices td .note { display:block; line-height:1.1; } .prices th { white-space:normal; line-height:1.15; }
.day { display:flex; align-items:center; gap:10px; }
.day::after { content:""; flex:1; height:1px; background:linear-gradient(90deg, var(--line), transparent); }
.section h4 { color:#7f8a99; letter-spacing:.08em; }
.chip { border-radius:7px; }
.ovr { border-radius:8px; box-shadow:0 2px 10px -4px rgba(0,0,0,.6); }
.msg { border-radius:12px; backdrop-filter:blur(6px); }

/* smooth page-to-page changes in browsers that support it (the tab highlight slides) */
@media (prefers-reduced-motion: no-preference) {
  @view-transition { navigation: auto; }
  ::view-transition-old(root), ::view-transition-new(root) { animation-duration:.22s; }
  ::view-transition-group(navpill) { animation-duration:.32s; animation-timing-function:cubic-bezier(.2,.8,.2,1); }
}

/* ---------- phones ---------- */
@media (max-width: 640px) {
  :root { --card-h:565px; }
  body { font-size:15px; -webkit-text-size-adjust:100%; }
  header { padding:8px 12px 0; gap:6px 10px; flex-wrap:wrap; }
  header h1 { font-size:15px; }
  header .models { display:none; }
  nav { order:3; flex:1 0 100%; display:flex; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:none;
        margin:0 -12px; padding:0 8px 8px; gap:2px; }
  nav::-webkit-scrollbar { display:none; }
  nav a { flex:0 0 auto; padding:9px 12px; white-space:nowrap; }
  main { padding:12px 12px 40px; }
  .grid { grid-template-columns:minmax(0, 1fr); gap:12px; }
  .tiles { grid-template-columns:repeat(2, minmax(0, 1fr)); gap:8px; } .tile { padding:10px; } .tile .big { font-size:22px; } .tile .note { font-size:12px; }
  .note, .sub, .day, th, .hint, .mine, .locked, details summary { font-size:13px; }
  .flag, .prices .note, .mv, .qb { font-size:12px; }
  .face { padding:12px; }
  td { padding:7px 5px; } th { padding:4px 5px; }
  .face table .tm { max-width:120px; } .prices .tm { max-width:96px; }
  select, input { font-size:16px; padding:8px 10px; }      /* 16px stops iPhone zooming in on tap */
  button.go { font-size:16px; padding:9px 14px; }
  .toggle { display:flex; overflow-x:auto; scrollbar-width:none; max-width:100%; }
  .toggle::-webkit-scrollbar { display:none; }
  .toggle a { flex:0 0 auto; padding:9px 14px; }
  .filters input, .filters select { flex:1 1 140px; min-width:0; }
  .rk .hide-sm { display:none; }
  .rk td, .rk th { padding:7px 3px; } .rk .form span { width:11px; } .rk td.team img { margin-right:6px; }
  .panel { padding:10px; } .panel td { overflow-wrap:anywhere; }
  .prices .fair { display:none; } .prices th { white-space:normal; line-height:1.15; } .prices .tm { max-width:84px; }
  form.pick { flex-wrap:nowrap; } form.pick select { flex:1 1 auto; min-width:0; max-width:55%; }
  input[type=number] { width:72px; }
  .sub2 .time { white-space:normal; overflow:visible; }
  .badge { padding:7px 12px; align-self:center; white-space:nowrap; flex:0 0 auto; }
  button.go { white-space:nowrap; flex:0 0 auto; }
  .prices td .note { display:block; line-height:1.1; }
  .prices td, .prices th { padding-left:4px; padding-right:4px; }
  .rk td.team { white-space:normal; }
  /* Positions: each pick becomes a stacked block */
  table.mt, table.mt tbody { display:block; }
  table.mt tr:first-child { display:none; }
  table.mt tr { display:flex; flex-wrap:wrap; align-items:center; border-top:1px solid var(--line); padding:10px 0; }
  table.mt td { border:0; padding:3px 0; }
  table.mt td.when { flex:1 0 100%; text-align:left; display:flex; gap:8px; color:var(--muted); font-size:13px; }
  table.mt td.when .note { font-size:13px; }
  table.mt td.game { flex:1 0 100%; display:flex; flex-wrap:wrap; gap:2px 6px; align-items:center; padding-bottom:6px; }
  table.mt td.game .vs { margin:0; }
  table.mt td.pk { flex:1 1 70%; padding-left:0; display:flex; align-items:center; gap:6px; }
  table.mt td.pk::before, table.mt td.res::before, table.mt td[data-label="Status"]::before {
    content:attr(data-label); color:var(--muted); font-size:13px; min-width:92px; }
  table.mt td.pp { flex:0 0 auto; text-align:right; width:auto; }
  table.mt td.res, table.mt td[data-label="Status"] { flex:1 0 100%; text-align:left; display:flex; gap:6px; }
}
/* ---------- touch screens and phones: flat cards ----------
   iPhone Safari often won't scroll the page when a swipe starts on a 3D-flipped card with its own
   scroll area. So on touch devices the cards are flat: no 3D, no inner scrolling, each face as tall
   as its content; tapping swaps front and back with a quick 2D flip. */
@media (hover: none), (max-width: 640px) {
  .card { perspective:none; touch-action:manipulation; }
  .inner, .card.three .inner { height:auto; transform:none !important; transform-style:flat; transition:none; }
  .face { position:relative; inset:auto; overflow:visible; backface-visibility:visible; -webkit-backface-visibility:visible; }
  .back { transform:none; display:none; }
  .card.flipped .front { display:none; }
  .card.flipped .back { display:block; }
  .card.flipping .face { animation:face-in .32s var(--ease) both; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
}
"""

JS = """
// entrance animation only when the page is on screen as it loads (a page opened in a background
// tab would otherwise hold its cards invisible until viewed); done after 2 s either way
if (document.visibilityState === 'visible') {
  document.documentElement.classList.add('anim');
  setTimeout(function () { document.documentElement.classList.remove('anim'); }, 2000);
}
// stagger the entrance animation (first dozen items per kind; the rest appear together)
['.card', '.lcard', '.tile', '.panel', '.ovr'].forEach(function (sel) {
  document.querySelectorAll(sel).forEach(function (el, i) { el.style.setProperty('--i', Math.min(i, 12)); });
});
document.querySelectorAll('.card').forEach(function (c) {
  c.addEventListener('click', function (e) {
    if (e.target.closest('form, input, select, button.go, a')) return;
    c.classList.add('flipping');
    c.classList.toggle('flipped');
    setTimeout(function () { c.classList.remove('flipping'); }, 350);
  });
});
"""


def page(title, active, body, msg=None, scripts=""):
    tabs = "".join(
        f'<a class="{"on" if active == key else ""}" href="{url}">{label}</a>'
        for key, url, label in tuple((f"slate-{s}", f"/slate?sport={s}", SHORT_NAMES[s]) for s in SHORT_NAMES)
                                + (("live", "/live", "Live"),
                                ("mine", "/mine", "Positions"),
                                ("rank", "/rankings?sport=nfl", "Rankings"),
                                   ("score", "/scorecard?sport=nfl", "Scorecard")))
    banner = f'<div class="msg {msg[0]}">{esc(msg[1])}</div>' if msg else ""
    mv = model_versions()
    models = "models: " + ", ".join(f"{SHORT_NAMES[k]} {v}" for k, v in mv.items() if k in SHORT_NAMES)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} &middot; {esc(APP_NAME)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Doppio+One&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header><h1>{esc(APP_NAME)} <span class="ver" title="{esc(models)}">v{APP_VERSION}</span></h1><nav>{tabs}</nav>
<span class="note models">{esc(models)} &middot; all flags are low confidence, paper only</span></header>
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
    three = v.get("three_way")
    if v["projected"]:
        sub.append(f"{'expected goals' if three else 'projected'} {esc(v['away'])} {v['projected'][0]} "
                   f"&ndash; {esc(v['home'])} {v['projected'][1]}")
    logos = {v["away"]: v["away_logo"], v["home"]: v["home_logo"], "Draw": None}

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
        prices += (f'<tr><td>{team(pr["team"], logos[pr["team"]], True)}</td><td class="fair">{pr["fair"]:+d}</td>'
                   f'<td>{best}</td><td>{edge}{flag}</td><td>{ev}</td></tr>')
    stale = " &middot; odds are old: no flags" if m and m["stale"] else ""
    prices_html = (f'<div class="section"><h4>Prices at your books{stale}</h4><table class="prices"><tr><th>team</th>'
                   f'<th class="fair">fair</th><th>best price</th><th>edge</th><th>per $100</th></tr>{prices}</table></div>'
                   if prices else "")

    if v.get("cancelled"):
        form = '<div class="locked">Game cancelled: nothing on it is graded.</div>'
    elif v["started"]:
        form = '<div class="locked">Game has started: picks are locked.</div>'
    else:
        form = f"""<form class="pick" method="post" action="/pick">
<input type="hidden" name="game_id" value="{v['id']}"><input type="hidden" name="sport" value="{esc(v['sport'])}"><input type="hidden" name="league" value="" class="keep-league">
<select name="team"><option value="{esc(v['away'])}">{esc(v['away'])}</option>{'<option value="Draw">Draw</option>' if three else ''}<option value="{esc(v['home'])}">{esc(v['home'])}</option></select>
<input type="number" name="pct" min="1" max="99" step="1" placeholder="{'chance %' if three else 'win %'}" required>
<button class="go" type="submit">Log pick</button></form>"""

    front = f"""<div class="face front">
<div class="matchup">{away}<span class="at">at</span>{home}</div>
<div class="sub2"><span class="time">{'<b style="color:var(--bad)">CANCELLED</b> &middot; ' if v.get('cancelled') else ''}{esc(v['kickoff'])}{' &middot; ' + ' &middot; '.join(sub) if sub else ''}</span>{badge}</div>
<table class="picks"><tr><th>source</th><th class="l">pick</th><th>{'chance' if three else 'win %'}</th><th>vs market</th></tr>{rows}</table>
{prices_html}{form}<div class="hint"><span class="mouse">click</span><span class="touch">tap</span> card for details &#8635;</div></div>"""

    # back
    books = ""
    for b in v["books"]:
        books += (f'<tr class="{"my" if b["mine"] else ""}"><td>{esc(b["book"])}{" &#9733;" if b["mine"] else ""}</td>'
                  f'<td class="{"best" if b["best_away"] else ""}">{b["away"]:+d}</td>'
                  + (f'<td class="{"best" if b["best_draw"] else ""}">{b["draw"]:+d}</td>' if three else "")
                  + f'<td class="{"best" if b["best_home"] else ""}">{b["home"]:+d}</td></tr>')
    books_html = (f'<div class="section"><h4>Odds by book &middot; {esc(v["odds_time"] or "")}</h4>'
                  f'<table class="books"><tr><th>book (&#9733; = yours)</th><th>{esc(v["away"])}</th>'
                  + ("<th>Draw</th>" if three else "")
                  + f'<th>{esc(v["home"])}</th></tr>{books}</table></div>') if books else \
        '<div class="section"><h4>Odds by book</h4><div class="note">no odds yet</div></div>'
    mv = v["movement"]
    move_html = ""
    if mv:
        what = "no real move" if mv["pts"] == 0 else f'moved {mv["pts"]} pts toward {esc(mv["toward"])}'
        if three:
            then, now_ = " / ".join(f"{x}%" for x in mv["then"]), " / ".join(f"{x}%" for x in mv["now"])
            line = (f'<div class="kv"><span>{esc(v["away"])} / Draw / {esc(v["home"])} (no vig)</span>'
                    f'<span>{then} &rarr; {now_}</span></div>')
        else:
            line = (f'<div class="kv"><span>{esc(v["away"])} / {esc(v["home"])} (no vig)</span>'
                    f'<span>{mv["away_then"]}% / {mv["home_then"]}% &rarr; {mv["away_now"]}% / {mv["home_now"]}%</span></div>')
        move_html = (f'<div class="section"><h4>Line movement</h4>'
                     f'<div class="kv"><span>since {esc(mv["since"])}</span><span>{what}</span></div>{line}</div>')
    form_rows = ""
    for side in ("away", "home"):
        f = v["form"][side]
        chips = "".join(
            f'<span class="chip {g["result"]}" title="{g["result"]} {g["score"]} {g["where"]} {esc(g["opp"])} ({g["date"]})">'
            f'{g["result"]}</span>' for g in reversed(f["games"]))
        form_rows += (f'<div class="form-row">{team(v[side], v[side + "_logo"], True)}'
                      f'<span class="note">{f["record"]}{" (W-D-L)" if three else ""} this season</span><span class="chips">{chips or "<span class=note>no games yet</span>"}</span></div>')
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
    return (f'<div class="card{" three" if three else ""}" id="g{v["id"]}" data-league="{esc(v.get("league") or "")}">'
            f'<div class="inner">{front}{back}</div></div>')


def slate_page(sport, days, groups, msg):
    label = SPORT_NAMES[sport]
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
    script = ""
    if sport == "soccer_club":
        intro += ("<p class='note'>Three outcomes: each source&rsquo;s pick is its most likely result (a team or Draw). "
                  "At most one flag per game (the largest edge). Your pick: choose a team or Draw and your chance "
                  "for it; the other two split the rest in the market&rsquo;s proportions.</p>")
        leagues = sorted({v["league"] for _, v in groups})
        intro += ('<div class="filters"><select id="lg"><option value="">All leagues</option>'
                  + "".join(f'<option value="{esc(lg)}">{esc(lg)}</option>' for lg in leagues) + "</select></div>")
        script = """
(function () {
  var s = document.getElementById('lg'); if (!s) return;
  function apply(push) {
    document.querySelectorAll('.card[data-league]').forEach(function (c) {
      c.style.display = !s.value || c.dataset.league === s.value ? '' : 'none';
    });
    document.querySelectorAll('.grid').forEach(function (g) {
      var any = [].some.call(g.children, function (c) { return c.style.display !== 'none'; });
      g.style.display = any ? '' : 'none'; g.previousElementSibling.style.display = any ? '' : 'none';
    });
    document.querySelectorAll('input.keep-league').forEach(function (i) { i.value = s.value; });
    if (push) {   // remember the filter in the address, so reloads and pick logging keep it
      var u = new URL(location.href);
      if (s.value) u.searchParams.set('league', s.value); else u.searchParams.delete('league');
      u.searchParams.delete('msg'); u.searchParams.delete('kind'); u.hash = '';
      history.replaceState(null, '', u);
    }
  }
  var want = new URLSearchParams(location.search).get('league');
  if (want && [].some.call(s.options, function (o) { return o.value === want; })) s.value = want;
  apply(false);
  s.addEventListener('change', function () { apply(true); });
})();
"""
    return page(f"{label} slate", f"slate-{sport}", intro + body, msg, scripts=script)


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
        for k, n in SHORT_NAMES.items()) + "</div>")
    intro = toggle + ("<p class='note'>Scores from ESPN, refreshed every minute while this tab is open (last update "
             "<span id='upd'>now</span>). Display only: official results still come from nflverse and CFBD. "
             "Picks are the ones logged before kickoff.</p>")
    return page("Live", "live", intro + f'<div id="live">{live_fragment(groups, error)}</div>', scripts=LIVE_JS)


# ---------- my picks ----------

def mine_page(upcoming, finished, summary):
    def pick_cell(x, logos, names, label=""):
        """Two table cells: team (left) and win % (right), so columns line up.
        `label` is shown before the pick on phones, where rows stack."""
        if not x:
            return f'<td class="l neg pk" data-label="{label}">&ndash;</td><td class="pp"></td>'
        logo = None if x[0] == "Draw" else logos[0] if x[0] == names[0] else logos[1]
        return f'<td class="l pk" data-label="{label}">{team(x[0], logo, True)}</td><td class="pp">{x[1]}%</td>'

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
        f'<td class="l game">{team(u["away"], u["logos"][0], True)}<div class="vs">@ {team(u["home"], u["logos"][1], True)}</div></td>'
        f'{pick_cell(u["me"], u["logos"], (u["away"], u["home"]), "You")}'
        f'{pick_cell(u["engine"], u["logos"], (u["away"], u["home"]), "Engine")}'
        f'{pick_cell(u["market"], u["logos"], (u["away"], u["home"]), "Market at your pick")}</tr>' for u in upcoming)
    up_html = (f'<div class="panel"><h2>Upcoming ({len(upcoming)})</h2><table class="mt"><tr><th>kickoff</th><th class="l">game</th>'
               f'<th class="l" colspan="2">your pick</th><th class="l" colspan="2">engine</th>'
               f'<th class="l" colspan="2">market when you picked</th></tr>{up}</table></div>'
               if upcoming else '<div class="panel"><h2>Upcoming</h2><div class="note">No upcoming picks.</div></div>')

    waiting = [f for f in finished if f.get("correct") is None]
    finished = [f for f in finished if f.get("correct") is not None]
    wait_rows = "".join(
        f'<tr><td class="when">{esc(f["kickoff"])}<div class="note">{f["sport"].upper()}</div></td>'
        f'<td class="l game">{team(f["away"], f["logos"][0], True)}<div class="vs">@ {team(f["home"], f["logos"][1], True)}</div></td>'
        f'{pick_cell(f["me"], f["logos"], (f["away"], f["home"]), "You")}'
        f'{pick_cell(f["engine"], f["logos"], (f["away"], f["home"]), "Engine")}'
        f'<td class="note" data-label="Status">{esc(f["final"])}</td></tr>' for f in waiting)
    wait_html = (f'<div class="panel"><h2>In progress / awaiting result ({len(waiting)})</h2><table class="mt"><tr><th>kickoff</th>'
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
                f'<td class="l game">{team(f["away"], f["logos"][0], True)}<div class="vs">@ {team(f["home"], f["logos"][1], True)}</div>'
                f'<div class="note">{esc(f["final"]) if f.get("correct") is not None else ""}</div></td>'
                f'{pick_cell(f["me"], f["logos"], (f["away"], f["home"]), "You")}<td class="res" data-label="Result">{res}</td>'
                f'{pick_cell(f["engine"], f["logos"], (f["away"], f["home"]), "Engine")}<td class="res" data-label="Brier you / engine / market">{briers}</td></tr>')
    fin_html = (f'<div class="panel"><h2>Finished ({len(finished)})</h2><table class="mt"><tr><th>kickoff</th><th class="l">game</th>'
                f'<th class="l" colspan="2">your pick</th><th>result</th><th class="l" colspan="2">engine</th>'
                f'<th>Brier: you / engine / market</th></tr>{fin}</table></div>'
                if finished else "")
    intro = ("<p class='note'>Every game you picked, both sports. Brier score = how far a probability was from "
             "what happened (0 is perfect, 0.25 is a coin flip); lower is better.</p>")
    return page("Positions", "mine", intro + tiles + up_html + wait_html + fin_html)


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


def ovr_tier(v):
    """Color band for an OVR badge (90+ / 80s / 70s / 60s / 50s / below 50)."""
    return "o6" if v >= 90 else "o5" if v >= 80 else "o4" if v >= 70 else "o3" if v >= 60 else "o2" if v >= 50 else "o1"


def ovr_chart(points):
    """Line chart of OVR by season (one series, so no legend): [(season label, OVR, hover text)]."""
    if not points:
        return ""
    w, h, left, right, top, bottom = 640, 220, 34, 14, 12, 28
    lo = min(40, min(p[1] for p in points) - 5)
    lo = max(1, lo - lo % 10)
    xs = [left + (w - left - right) * (i / (len(points) - 1) if len(points) > 1 else 0.5) for i in range(len(points))]
    y = lambda v: top + (h - top - bottom) * (99 - v) / (99 - lo)
    grid = "".join(f'<line x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="gl"/>'
                   f'<text x="{left - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{v}</text>'
                   for v in range(lo + (10 - lo % 10) % 10, 100, 10))
    step = max(1, len(points) // 8)
    labels = "".join(f'<text x="{xs[i]:.1f}" y="{h - 8}" class="ax" text-anchor="middle">{esc(points[i][0])}</text>'
                     for i in range(len(points)) if i % step == 0 or i == len(points) - 1)
    line = " ".join(f"{x:.1f},{y(p[1]):.1f}" for x, p in zip(xs, points))
    dots = "".join(f'<g class="pt"><circle cx="{x:.1f}" cy="{y(p[1]):.1f}" r="12" class="hit"/>'
                   f'<circle cx="{x:.1f}" cy="{y(p[1]):.1f}" r="4.5" class="dot"/><title>{esc(p[2])}</title></g>'
                   for x, p in zip(xs, points))
    return (f'<svg class="ovrchart" viewBox="0 0 {w} {h}" role="img" aria-label="OVR by season">{grid}{labels}'
            f'<polyline points="{line}" class="ln"/>{dots}</svg>')


RANK_SPORTS = {**SHORT_NAMES, "soccer_club": "Soccer"}


def rankings_page(sport, d):
    soccer = sport == "soccer_club"
    switch = ('<div class="toggle">' + "".join(
        f'<a class="{"on" if sport == k else ""}" href="/rankings?sport={k}">{n}</a>'
        for k, n in RANK_SPORTS.items()) + "</div>")
    if d["error"]:
        return page("Rankings", "rank", switch + f'<p class="note">Rankings unavailable: {esc(d["error"])}</p>')
    college = sport in ("ncaaf", "ncaab")
    selected = "all" if d["mode"] == "all" else str(d["season"])
    picker = ('<select id="rk-s" aria-label="Season">' + "".join(
        f'<option value="{v}"{" selected" if v == selected and d["mode"] != "team" else ""}>{esc(label)}</option>'
        for v, label in d["options"]) + "</select>")
    intro = ('<p class="note"><b>OVR</b> (1&ndash;99) rates each team the same way in every season, so numbers '
             'compare across years: 62 = an average team, 80+ = great (top ~7% of all teams in our history), '
             '90+ = historically great (top ~1%). It starts from the model&rsquo;s chance that the team beats an '
             'average team of its league that season on a neutral field. Past seasons use each team&rsquo;s rating '
             'after its last game; records include playoffs. Tap a team for its history.</p>')
    link = lambda team, text: f'<a class="tlink" href="/rankings?sport={sport}&amp;team={esc(urllib.parse.quote(team))}">{text}</a>'
    script = """
(function () {
  var s = document.getElementById('rk-s');
  if (s) s.addEventListener('change', function () { location.href = '/rankings?sport=__SPORT__&season=' + s.value; });
  var q = document.getElementById('rk-q'), c = document.getElementById('rk-c');
  if (!q) return;
  function apply() {
    var text = (q.value || '').toLowerCase(), conf = c ? c.value : '';
    document.querySelectorAll('table.rk tr[data-name]').forEach(function (tr) {
      var ok = tr.dataset.name.indexOf(text) !== -1 && (!conf || tr.dataset.conf === conf);
      tr.style.display = ok ? '' : 'none';
    });
  }
  q.addEventListener('input', apply); if (c) c.addEventListener('change', apply);
})();
""".replace("__SPORT__", sport)

    def rec(r):
        w, l, t = r["record"]
        if soccer:
            return f"{w}-{t}-{l}"          # soccer convention: wins-draws-losses
        return f"{w}-{l}" + (f"-{t}" if t else "")

    def badge(v):
        return f'<span class="ovr {ovr_tier(v)}">{v}</span>'

    if d["mode"] == "team":
        hist = d["history"]
        logo = f'<img src="{esc(d["logo"])}" alt="" class="tlogo">' if d.get("logo") else ""
        title = f'<h2 class="thead">{logo}{esc(d["team"])}</h2>'
        if not hist:
            body = f'<p class="note">No seasons found for {esc(d["team"])}.</p>'
        else:
            pts = [(lbl, r["ovr"], f'{lbl}: OVR {r["ovr"]}, #{r["rank"]}, {rec(r)}') for lbl, r in hist]
            best = max(hist, key=lambda x: x[1]["ovr"])
            rows = "".join(f'<tr><td>{esc(lbl)}{" <span class=note>(so far)</span>" if lbl == d["options"][0][1].split(" ")[0] else ""}</td>'
                           f'<td class="num">{badge(r["ovr"])}</td><td class="num">#{r["rank"]}</td>'
                           f'<td class="num">{rec(r)}</td></tr>' for lbl, r in reversed(hist))
            body = (f'<p class="note">Best season: {esc(best[0])} (OVR {best[1]["ovr"]}). Hover or tap a point for details.</p>'
                    f'<div class="panel">{ovr_chart(pts)}</div>'
                    f'<div class="panel"><table class="rk"><tr><th style="text-align:left">season</th><th class="num">OVR</th>'
                    f'<th class="num">rank</th><th class="num">record</th></tr>{rows}</table></div>')
        back = f'<p><a class="tlink" href="/rankings?sport={sport}">&larr; back to rankings</a></p>'
        return page(f"{d['team']} history", "rank", switch + back + title + body, scripts=script)

    filters = f'<div class="filters">{picker}'
    if d["mode"] == "all":
        head = ('<tr><th class="num">#</th><th style="text-align:left">team</th><th class="num">season</th>'
                '<th class="num">OVR</th><th class="num">record</th></tr>')
        body = "".join(
            f'<tr><td class="rank">{i}</td><td class="team">'
            + (f'<img src="{esc(r["logo"])}" alt="" loading="lazy">' if r.get("logo") else "")
            + link(r["team"], esc(r["team"])) + f'</td><td class="num">{esc(r["season_label"])}'
            + (' <span class="note">so far</span>' if r.get("current") else "")
            + f'</td><td class="num">{badge(r["ovr"])}</td><td class="num">{rec(r)}</td></tr>'
            for i, r in enumerate(d["rows"], 1))
        filters += "</div>"
        return page(f"{RANK_SPORTS[sport]} all-time", "rank", switch + intro + filters
                    + f'<div class="panel"><table class="rk">{head}{body}</table></div>', scripts=script)

    live = d["season"] == d["current"]
    rows = d["rows"]
    if sport == "nfl" and live:
        intro += '<p class="note">NFL ratings include the starting QB the engine expects for each team&rsquo;s next game.</p>'
    if soccer:
        intro += ('<p class="note">Big 5 leagues in one list. Each club&rsquo;s rating within its own league is '
                  'shifted by its league&rsquo;s strength as learned from European games (the same strengths the '
                  'Champions League predictions use), then compared with an average Big 5 club: a win counts 1, a draw &frac12;. '
                  '<b>Net</b> = goals per game better than an average Big 5 club. Records are wins-draws-losses '
                  '(league games). Seasons from 2015-16.</p>')
    if sport == "ncaaf":
        intro += '<p class="note">FBS teams only. Early in a season, preseason information (talent, returning players, last season) counts too, as in the predictions.</p>'
    if d["early"]:
        intro += '<p class="note warn">Early season: ratings are still mostly last season&rsquo;s, pulled toward average.</p>'
    filters += '<input id="rk-q" placeholder="Search teams" autocomplete="off">'
    show_conf = (college and live) or soccer
    group = "league" if soccer else "conference"
    if show_conf:
        confs = sorted({r["conference"] for r in rows if r.get("conference")})
        filters += (f'<select id="rk-c"><option value="">All {group}s</option>'
                    + "".join(f'<option>{esc(c)}</option>' for c in confs) + "</select>")
    filters += "</div>"
    head = ('<tr><th class="num">#</th>' + ('<th></th>' if live else "") + '<th style="text-align:left">team</th><th class="num">OVR</th>'
            '<th class="num hide-sm">net</th><th class="num">record</th><th style="text-align:left">last 5</th>'
            '<th class="num hide-sm">off</th><th class="num hide-sm">def</th>'
            + (f'<th class="hide-sm" style="text-align:left">{group}</th>' if show_conf else "") + "</tr>")
    body = ""
    for r in rows:
        mv = r.get("move")
        mv_html = ("" if not live else '<td><span class="mv">new</span></td>' if mv is None
                   else '<td><span class="mv">&ndash;</span></td>' if mv == 0
                   else f'<td><span class="mv up">&#9650;{mv}</span></td>' if mv > 0
                   else f'<td><span class="mv down">&#9660;{-mv}</span></td>')
        logo = f'<img src="{esc(r["logo"])}" alt="" loading="lazy">' if r.get("logo") else ""
        qb = f'<span class="qb">QB {esc(r["qb"])}</span>' if r.get("qb") else ""
        form = "".join(f'<span class="{c}">{c}</span>' for c in r["form"]) or '<span class="T">&ndash;</span>'
        body += (f'<tr data-name="{esc(r["team"].lower())}" data-conf="{esc(r.get("conference") or "")}">'
                 f'<td class="rank">{r["rank"]}</td>{mv_html}<td class="team">{logo}{link(r["team"], esc(r["team"]))}{qb}</td>'
                 f'<td class="num">{badge(r["ovr"])}</td><td class="num hide-sm">{r["net"]:+.{2 if soccer else 1}f}</td>'
                 f'<td class="num">{rec(r)}</td><td class="form">{form}</td><td class="num hide-sm">{r["off_rank"]}</td>'
                 f'<td class="num hide-sm">{r["def_rank"]}</td>'
                 + (f'<td class="conf hide-sm">{esc(r.get("conference") or "")}</td>' if show_conf else "") + "</tr>")
    title = "" if live else f'<p class="note">Final ratings for {esc(rows[0]["season_label"]) if rows else ""}, after each team&rsquo;s last game.</p>'
    return page(f"{RANK_SPORTS[sport]} rankings", "rank", switch + intro + filters + title
                + f'<div class="panel"><table class="rk">{head}{body}</table></div>', scripts=script)


def scorecard_page(sport, sc):
    label = SPORT_NAMES[sport]
    switch = ('<div class="toggle">' + "".join(
        f'<a class="{"on" if sport == k else ""}" href="/scorecard?sport={k}">{n}</a>'
        for k, n in SHORT_NAMES.items()) + "</div>")
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
        if "rps" in x:
            rows += f'<div class="kv"><span>RPS</span><span>{x["rps"]:.3f}</span></div>'
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
    if sc.get("three_way"):
        approx = ('<p class="note">Three outcomes (home, draw, away): Brier is summed over all three, so about 0.58 is '
                  'typical here and isn&rsquo;t comparable with the other sports. RPS (ranked probability score) treats a '
                  'draw as between a home and an away win; lower is better. The calibration chart below is for the '
                  'home-win chance.</p>') + approx

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

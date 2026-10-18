"""The slate page: upcoming games as flip cards (every source's pick, prices at
your books, warnings, odds by book, line movement, form), your picks, and the
scorecard. Dark theme. Runs only on this Mac.

Usage: python3 slate.py [--port 8765] [--no-open]
Then open http://localhost:8765 (it opens automatically). Ctrl+C stops it.

The page only reads the database, except for logging your picks (same rules
as my_pick.py). Odds and engine predictions come from automation / predict.py.
Data: slate_data.py. HTML: slate_views.py.
"""

import sys
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db
import slate_data
import slate_views
from my_pick import PickError, log_pick

SPORTS = ("nfl", "ncaaf")


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
        sport = q.get("sport") if q.get("sport") in SPORTS else "nfl"
        now = datetime.now(timezone.utc)
        conn = db.connect()
        try:
            college = slate_data.college_logos()
            if url.path in ("/", "/slate"):
                days = int(q.get("days", 7))
                msg = (q["kind"], q["msg"]) if "msg" in q and q.get("kind") in ("ok", "err") else None
                groups = slate_data.slate(conn, sport, now, days, college)
                self._send(slate_views.slate_page(sport, days, groups, msg))
            elif url.path == "/mine":
                self._send(slate_views.mine_page(*slate_data.my_picks(conn, now, college)))
            elif url.path == "/scorecard":
                self._send(slate_views.scorecard_page(sport, slate_data.scorecard(conn, sport)))
            else:
                self._send(slate_views.page("Not found", "", "<p>Not found.</p>"), 404)
        finally:
            conn.close()

    def do_POST(self):
        if self.path != "/pick":
            return self._send(slate_views.page("Not found", "", "<p>Not found.</p>"), 404)
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

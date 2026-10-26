"""Downloads with retries for temporary server problems.

get(url) tries up to TRIES times. It retries when the server has a temporary problem (HTTP 500, 502,
503 or 504), when the request times out, or when the connection drops, waiting WAITS seconds between
tries (about a minute in all). Real errors (a wrong key, forbidden, not found, too many requests, ...)
are raised right away: retrying can't fix them, and callers that handle them (e.g. CBBD's rate limit,
ESPN's 404s) keep doing so. Each retry is printed, so the routine log shows flaky sources.
"""

import socket
import sys
import time
import urllib.error
import urllib.request

TRIES = 4
WAITS = (5, 15, 45)
RETRY_CODES = {500, 502, 503, 504}


def _temporary(e):
    if isinstance(e, urllib.error.HTTPError):
        return e.code in RETRY_CODES
    return isinstance(e, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError))


def get(url, headers=None, timeout=60, label=None):
    """(body bytes, response headers). Raises the last error if every try fails."""
    req = urllib.request.Request(url, headers=headers or {})
    for attempt in range(TRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), resp.headers
        except Exception as e:
            if not _temporary(e) or attempt == TRIES - 1:
                raise
            what = f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__
            print(f"  (temporary problem from {label or url.split('?')[0]}: {what}; retrying in "
                  f"{WAITS[attempt]} s, try {attempt + 2} of {TRIES})", file=sys.stderr, flush=True)
            time.sleep(WAITS[attempt])

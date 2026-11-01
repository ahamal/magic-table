"""Mate's live status, polled from its own API (http://mate.local/status) once a second.

The hub doesn't drive Mate (agents call Mate's API directly; see agent/mate.md); this
only keeps what the 3D view and the scene need, such as the flipper angle.
"""

import json
import threading
import time
import urllib.request

MATE = "http://mate.local"


class MateLink:
    def __init__(self, url=MATE, every=1.0):
        self.url, self.every = url, every
        self.status = None        # last /status reply, or None while unreachable
        self.seen_at = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                with urllib.request.urlopen(f"{self.url}/status", timeout=2) as r:
                    self.status, self.seen_at = json.loads(r.read()), time.time()
            except (OSError, ValueError):
                self.status = None
            time.sleep(self.every)

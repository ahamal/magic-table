"""Speech to text for the talk page, via Meta's Muse Voice Transcribe.

The page records one utterance, turns it into a 16 kHz mono WAV and posts it
here; the hub sends it to Meta's one-shot endpoint and keeps the text. Every
transcript is kept in order (and appended to transcripts.jsonl) so the agent
can read what people said, and pushed to open pages as it arrives.

The key comes from MODEL_API_KEY (the hub service reads it from ~/hub/.env,
which never goes in git).
"""

import json
import os
import threading
import time
from pathlib import Path

import requests

URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL = "muse-voice-transcribe-1.0"
MAX_BYTES = 32 * 1024 * 1024  # the endpoint's limit (also 10 minutes of audio)
# words the model would otherwise mis-hear at a card table
KEYWORDS = ["Mate", "fold", "check", "call", "raise", "all in", "blind", "flop", "turn", "river",
            "deal", "shuffle", "poker", "chips", "hearts", "spades", "clubs", "diamonds"]
LOG = Path(__file__).parent / "transcripts.jsonl"


class TranscribeError(RuntimeError):
    pass


class Transcripts:
    def __init__(self, emit):
        self.emit = emit
        self.items = []
        self._lock = threading.Lock()
        if LOG.exists():
            for line in LOG.read_text().splitlines():
                try:
                    self.items.append(json.loads(line))
                except ValueError:
                    pass

    def transcribe(self, wav, source="talk"):
        """Send one WAV to Meta, keep the text, return the new item."""
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            raise TranscribeError("MODEL_API_KEY isn't set on the hub (see the hub README)")
        if len(wav) > MAX_BYTES:
            raise TranscribeError("recording is over 32 MB")

        request = {"mode": "PUSH_TO_TALK", "model": MODEL, "audioEncoding": "WAV", "keywords": KEYWORDS}
        t0 = time.time()
        r = requests.post(URL, headers={"Authorization": f"Bearer {key}"}, timeout=60, files={
            "request": (None, json.dumps(request), "application/json"),
            "audio": ("talk.wav", wav, "audio/wav"),
        })
        if r.status_code != 200:
            raise TranscribeError(f"Meta API {r.status_code}: {r.text[:200]}")
        result = r.json()

        text = (result.get("transcript") or "").strip()
        if not text:
            return None
        with self._lock:
            item = {"id": len(self.items) + 1, "at": time.time(), "text": text, "source": source,
                    "audio_ms": result.get("audioDurationMs"), "took_ms": round((time.time() - t0) * 1000)}
            self.items.append(item)
            with LOG.open("a") as f:
                f.write(json.dumps(item) + "\n")
        self.emit({"type": "transcript", **item})
        return item

    def since(self, after_id=0):
        return [i for i in self.items if i["id"] > after_id]

    def clear(self):
        with self._lock:
            self.items = []
            LOG.unlink(missing_ok=True)
        self.emit({"type": "transcripts_cleared"})

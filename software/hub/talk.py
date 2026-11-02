"""The table's chat: what people say or type, what the agent says, and Mate's gestures, in one log.

People talk on the talk page: it streams the mic (16 kHz PCM) to the hub, which relays it to
Meta's Muse Voice Transcribe realtime endpoint and passes the words back as they're recognised
(about 0.3 s behind the speech), so the page can show them live; the final text becomes the
message. (A whole recorded WAV can also be sent to the one-shot endpoint.) People can also
type. Everything the agent says out loud (/api/say) goes in too, and Mate's gestures
(/api/mate/gesture), since that's how Mate talks. Each message is kept in order (and appended
to chat.jsonl), pushed to open pages as a `chat` event, and agents can wait for new ones
(GET /api/chat?after=<id>&wait=30).

The key comes from MODEL_API_KEY (the hub service reads it from ~/hub/.env,
which never goes in git).
"""

import asyncio
import json
import os
import threading
import time
from pathlib import Path

import requests
import websockets

URL = "https://api.meta.ai/v1/asr/transcribe"
REALTIME_URL = "wss://api.meta.ai/v1/asr/realtime"   # handshake JSON, PCM16 frames, {"type": "endStream"}
MODEL = "muse-voice-transcribe-1.0"
MAX_BYTES = 32 * 1024 * 1024  # the endpoint's limit (also 10 minutes of audio)
# words the model would otherwise mis-hear at a card table
KEYWORDS = ["Mate", "fold", "check", "call", "raise", "all in", "blind", "flop", "turn", "river",
            "deal", "shuffle", "poker", "chips", "hearts", "spades", "clubs", "diamonds"]
LOG = Path(__file__).parent / "chat.jsonl"
OLD_LOG = Path(__file__).parent / "transcripts.jsonl"   # before the chat: player speech only


class TranscribeError(RuntimeError):
    pass


class Chat:
    def __init__(self, emit):
        self.emit = emit
        self.items = []
        self._lock = threading.Lock()
        src = LOG if LOG.exists() else OLD_LOG
        for line in src.read_text().splitlines() if src.exists() else []:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            item.setdefault("by", "player")
            item.setdefault("via", "voice")
            self.items.append(item)

    def add(self, text, by="player", via="typed", **extra):
        """Add one message. by: "player" (people at the table), "mate" (its gestures),
        or an agent's name; via: "voice", "typed", "speaker" or "gesture"."""
        text = text.strip()
        if not text:
            return None
        with self._lock:
            item = {"id": (self.items[-1]["id"] if self.items else 0) + 1, "at": time.time(),
                    "by": by, "via": via, "text": text, **extra}
            self.items.append(item)
            with LOG.open("a") as f:
                f.write(json.dumps(item) + "\n")
        self.emit({"type": "chat", **item})
        return item

    def transcribe(self, wav):
        """Send one WAV to Meta, keep the text as a player message, return it (None if silent)."""
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

        return self.add(result.get("transcript") or "", "player", "voice",
                        audio_ms=result.get("audioDurationMs"), took_ms=round((time.time() - t0) * 1000))

    async def stream(self, audio, partial):
        """Live transcription of one utterance. `audio` is an async iterator of 16 kHz mono PCM16
        chunks that ends when the person stops; `partial(text)` is awaited with the words so far
        (cumulative) as Meta recognises them. Keeps the final text as a player message and
        returns it (None if nothing was said)."""
        key = os.environ.get("MODEL_API_KEY")
        if not key:
            raise TranscribeError("MODEL_API_KEY isn't set on the hub (see the hub README)")
        t0, final = time.time(), {}
        try:
            async with websockets.connect(REALTIME_URL, max_size=None, open_timeout=10) as ws:
                await ws.send(json.dumps({"authorization": {"accessToken": key}, "audioEncoding": "PCM_16KHZ",
                                          "model": MODEL, "mode": "PUSH_TO_TALK", "partialMode": "CUMULATIVE",
                                          "emitAudioProgress": False, "keywords": KEYWORDS}))

                async def receive():
                    async for raw in ws:
                        m = json.loads(raw)
                        if m.get("type") == "error":
                            final["error"] = str(m)[:200]
                            return
                        if m.get("type") == "transcript":
                            if m.get("final"):
                                final.update(text=m.get("transcript", ""), audio_ms=m.get("audioProcessedMs"))
                                return
                            await partial(m.get("transcript", ""))

                listening = asyncio.create_task(receive())
                async for chunk in audio:
                    if listening.done():
                        break
                    await ws.send(chunk)
                if not listening.done():
                    await ws.send(json.dumps({"type": "endStream"}))
                await asyncio.wait_for(listening, 15)
        except (OSError, asyncio.TimeoutError, websockets.WebSocketException) as e:
            raise TranscribeError(f"Meta realtime: {e}") from e
        if "error" in final:
            raise TranscribeError(f"Meta realtime: {final['error']}")
        return self.add(final.get("text", ""), "player", "voice", audio_ms=final.get("audio_ms"),
                        took_ms=round((time.time() - t0) * 1000), live=True)

    def since(self, after_id=0):
        return [i for i in self.items if i["id"] > after_id]

    def clear(self):
        with self._lock:
            self.items = []
            LOG.unlink(missing_ok=True)
            OLD_LOG.unlink(missing_ok=True)
        self.emit({"type": "chat_cleared"})

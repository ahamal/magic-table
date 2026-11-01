"""The table's voice: text to speech on the Bluetooth speaker (Anker SoundCore 2).

espeak-ng turns the text into a WAV and paplay plays it through PipeWire. The hub
service needs the user's audio session: hub.service sets XDG_RUNTIME_DIR, and
`loginctl enable-linger ash` keeps PipeWire running without anyone logged in.
Lines are spoken one after another; open pages get a `speaking` event.
"""

import queue
import subprocess
import tempfile
import threading
from pathlib import Path


class Voice:
    def __init__(self, emit, voice="en-us", wpm=160):
        self.emit, self.voice, self.wpm = emit, voice, wpm
        self.speaking = None
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def say(self, text, wait=False):
        """Queue a line. wait=True blocks until it has been spoken; returns any error."""
        done = threading.Event() if wait else None
        result = {}
        self._q.put((text, done, result))
        if done:
            done.wait(60)
        return result.get("error")

    def _run(self):
        while True:
            text, done, result = self._q.get()
            self.speaking = text
            self.emit({"type": "speaking", "text": text})
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
                    subprocess.run(["espeak-ng", "-v", self.voice, "-s", str(self.wpm), "-w", wav.name, text],
                                   check=True, capture_output=True, timeout=30)
                    subprocess.run(["paplay", wav.name], check=True, capture_output=True, timeout=60)
            except (subprocess.SubprocessError, OSError) as e:
                result["error"] = getattr(e, "stderr", b"").decode(errors="replace").strip() or str(e)
            self.speaking = None
            self.emit({"type": "speaking", "text": None})
            if done:
                done.set()

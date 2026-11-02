"""The table's voice: text to speech on the Bluetooth speaker (Anker SoundCore 2).

Piper (a local neural voice, no internet) turns the text into audio a sentence at a time,
and paplay plays it through PipeWire as it comes, so a line starts in well under a second.
The voices are ~60 MB `.onnx` files in `voices/` (not in git; see README); the chosen one
is kept loaded. Without Piper or a voice file it falls back to espeak-ng (robotic, instant).
The hub service needs the user's audio session: hub.service sets XDG_RUNTIME_DIR, and
`loginctl enable-linger ash` keeps PipeWire running without anyone logged in.
Lines are spoken one after another; open pages get a `speaking` event.
"""

import json
import queue
import subprocess
import tempfile
import threading
from pathlib import Path

try:
    from piper import PiperVoice, SynthesisConfig
except ImportError:
    PiperVoice = None

HERE = Path(__file__).parent
VOICES = HERE / "voices"
CHOICE = HERE / "voice.json"        # the chosen voice and pace, kept across restarts
DEFAULT = {"voice": "en_US-norman-medium", "speaker": None, "pace": 0.85}   # calm, dry, a bit brisk


class Voice:
    def __init__(self, emit):
        self.emit = emit
        self.speaking = None
        self.choice = {**DEFAULT, **(json.loads(CHOICE.read_text()) if CHOICE.exists() else {})}
        self._piper, self._loaded = None, None
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()
        self._q.put((None, None, {}))  # load the voice in the background now, not on the first line

    def voices(self):
        return sorted(p.stem for p in VOICES.glob("*.onnx")) if PiperVoice else []

    def speakers(self, voice):
        """Speaker names in a multi-speaker voice file ({} for single-speaker ones)."""
        cfg = VOICES / f"{voice}.onnx.json"
        return json.loads(cfg.read_text()).get("speaker_id_map", {}) if cfg.exists() else {}

    def choose(self, voice=None, pace=None, speaker=None):
        """Pick a Piper voice (a name from voices()), a speaker in it (name or number, for
        multi-speaker files) and/or a pace (1 = normal, <1 faster)."""
        if voice is not None and voice not in self.voices():
            return f"no voice {voice!r}; have {self.voices()}"
        v = voice if voice is not None else self.choice["voice"]
        names = self.speakers(v)
        if speaker is not None and str(speaker) not in names and str(speaker) not in map(str, names.values()):
            return f"no speaker {speaker!r} in {v}; have {list(names)[:20]}"
        if voice is not None:
            self.choice["voice"] = voice
            self.choice["speaker"] = speaker if names else None
        elif speaker is not None:
            self.choice["speaker"] = speaker
        if pace is not None:
            self.choice["pace"] = max(0.5, min(2.0, float(pace)))
        CHOICE.write_text(json.dumps(self.choice))
        return None

    def say(self, text, wait=False):
        """Queue a line. wait=True blocks until it has been spoken; returns any error."""
        done = threading.Event() if wait else None
        result = {}
        self._q.put((text, done, result))
        if done:
            done.wait(60)
        return result.get("error")

    def _voice(self):
        name = self.choice["voice"]
        if PiperVoice and self._loaded != name and (VOICES / f"{name}.onnx").exists():
            self._piper, self._loaded = PiperVoice.load(str(VOICES / f"{name}.onnx")), name
        return self._piper if self._loaded == name else None

    def _piper_say(self, piper, text):
        spk, names = self.choice.get("speaker"), self.speakers(self.choice["voice"])
        sid = names.get(str(spk), int(spk) if str(spk).isdigit() else None) if names and spk is not None else None
        cfg = SynthesisConfig(speaker_id=sid, length_scale=self.choice["pace"])
        play = None
        try:
            for chunk in piper.synthesize(text, cfg):      # a sentence at a time
                if play is None:
                    play = subprocess.Popen(["paplay", "--raw", f"--rate={chunk.sample_rate}", "--channels=1",
                                             "--format=s16le"], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
                play.stdin.write(chunk.audio_int16_bytes)
                play.stdin.flush()
        finally:
            if play:
                play.stdin.close()
                if play.wait(timeout=60):
                    raise subprocess.CalledProcessError(play.returncode, "paplay", stderr=play.stderr.read())

    def _espeak_say(self, text):
        with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
            subprocess.run(["espeak-ng", "-v", "en-us", "-s", "160", "-w", wav.name, text],
                           check=True, capture_output=True, timeout=30)
            subprocess.run(["paplay", wav.name], check=True, capture_output=True, timeout=60)

    def _run(self):
        while True:
            text, done, result = self._q.get()
            if text is None:
                try:
                    self._voice()
                except Exception:
                    pass
                continue
            self.speaking = text
            self.emit({"type": "speaking", "text": text})
            try:
                piper = self._voice()
                self._piper_say(piper, text) if piper else self._espeak_say(text)
            except (subprocess.SubprocessError, OSError, RuntimeError) as e:
                result["error"] = (getattr(e, "stderr", b"") or b"").decode(errors="replace").strip() or str(e)
            self.speaking = None
            self.emit({"type": "speaking", "text": None})
            if done:
                done.set()

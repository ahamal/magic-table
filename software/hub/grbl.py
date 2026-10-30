"""One long-lived connection to GRBL over USB serial.

Opening the port resets the Uno (and GRBL forgets its position), so the
hub opens it once and keeps it open. Lines are sent one at a time and wait
for GRBL's `ok`/`error`; real-time bytes (status, hold, resume, reset, jog
cancel) skip the queue. A poller asks for status a few times a second and
every parsed status or message goes to the listeners.
"""

import queue
import re
import threading
import time

import serial

REALTIME = {
    "status": b"?",
    "hold": b"!",
    "resume": b"~",
    "reset": b"\x18",
    "jog_cancel": b"\x85",
}

STATUS_RE = re.compile(r"<([^>]+)>")


def parse_status(body):
    """'<Idle|MPos:1,2,3|FS:0,0|WCO:0,0,0>' body -> dict."""
    parts = body.split("|")
    out = {"state": parts[0]}
    for p in parts[1:]:
        key, _, val = p.partition(":")
        nums = val.split(",")
        try:
            out[key] = [float(n) for n in nums]
        except ValueError:
            out[key] = val
    return out


class Grbl:
    def __init__(self, port="/dev/ttyACM0", baud=115200, poll_hz=5):
        self.port, self.baud, self.poll_s = port, baud, 1 / poll_hz
        self.ser = None
        self.listeners = []          # callables(event: dict)
        self.status = {"state": "Disconnected"}
        self.wco = [0.0, 0.0, 0.0]   # GRBL only reports WCO every few statuses
        self.homed = False
        self.settings = {}
        self._lines = queue.Queue()  # (line, reply_queue)
        self._reply = None           # reply queue of the line waiting for ok
        self._write = threading.Lock()

    # ---- lifecycle ----

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                self._connect()
                threading.Thread(target=self._sender, daemon=True).start()
                threading.Thread(target=self._poller, daemon=True).start()
                self._reader()
            except (serial.SerialException, OSError) as e:
                self._emit({"type": "log", "dir": "sys", "text": f"serial: {e}"})
            self.ser = None
            self.homed = False
            self._set_status({"state": "Disconnected"})
            self._fail_pending("disconnected")
            time.sleep(2)

    def _connect(self):
        self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
        self._emit({"type": "log", "dir": "sys", "text": f"opened {self.port}, waiting for GRBL"})
        time.sleep(2)  # the Uno resets on open
        self.ser.reset_input_buffer()
        self.ser.write(b"\r\n\r\n")
        threading.Thread(target=self.load_settings, daemon=True).start()

    # ---- sending ----

    def send(self, line, timeout=30):
        """Queue one line; block until GRBL answers ok/error. Returns the reply."""
        if self.ser is None:
            return "error:disconnected"
        reply = queue.Queue()
        self._lines.put((line.strip(), reply))
        try:
            return reply.get(timeout=timeout)
        except queue.Empty:
            return "error:timeout"

    def realtime(self, name):
        if self.ser is None:
            return False
        with self._write:
            self.ser.write(REALTIME[name])
        if name == "reset":
            self.homed = False
            self._fail_pending("reset")
        return True

    def _sender(self):
        ser = self.ser
        while self.ser is ser:
            try:
                line, reply = self._lines.get(timeout=0.5)
            except queue.Empty:
                continue
            self._reply = reply
            with self._write:
                ser.write((line + "\n").encode())
            self._emit({"type": "log", "dir": "out", "text": line})
            # wait for the reader to answer this line before sending the next
            deadline = time.time() + 60
            while self._reply is reply and time.time() < deadline and self.ser is ser:
                time.sleep(0.005)
            if self._reply is reply:
                self._reply = None
                reply.put("error:no reply")

    def _fail_pending(self, why):
        if self._reply:
            self._reply.put(f"error:{why}")
            self._reply = None
        while not self._lines.empty():
            self._lines.get_nowait()[1].put(f"error:{why}")

    def _poller(self):
        ser = self.ser
        while self.ser is ser:
            try:
                with self._write:
                    ser.write(b"?")
            except (serial.SerialException, OSError):
                return
            time.sleep(self.poll_s)

    # ---- receiving ----

    def _reader(self):
        buf = b""
        while True:
            chunk = self.ser.read(256)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode(errors="replace").strip()
                if line:
                    self._handle(line)

    def _handle(self, line):
        m = STATUS_RE.fullmatch(line)
        if m:
            st = parse_status(m.group(1))
            if "WCO" in st:
                self.wco = st["WCO"]
            if "MPos" in st:
                st["WPos"] = [round(a - b, 3) for a, b in zip(st["MPos"], self.wco)]
            st["homed"] = self.homed
            self._set_status(st)
            return

        if line == "ok" or line.startswith("error:"):
            if self._reply:
                r, self._reply = self._reply, None
                r.put(line)
            if line.startswith("error:"):
                self._emit({"type": "log", "dir": "in", "text": line})
            return

        if line.startswith("$") and "=" in line:
            key, _, val = line.partition("=")
            try:
                self.settings[key] = float(val)
            except ValueError:
                self.settings[key] = val
        if line.startswith("ALARM:") or line.startswith("Grbl "):
            self.homed = False
        self._emit({"type": "log", "dir": "in", "text": line})

    def _set_status(self, st):
        self.status = st
        self._emit({"type": "status", **st})

    def _emit(self, event):
        for fn in list(self.listeners):
            try:
                fn(event)
            except Exception:
                pass

    # ---- helpers ----

    def load_settings(self):
        time.sleep(0.5)
        self.send("$$")
        self._emit({"type": "settings", "settings": self.settings})
        return self.settings

    def home(self):
        reply = self.send("$H", timeout=120)
        self.homed = reply == "ok"
        return reply

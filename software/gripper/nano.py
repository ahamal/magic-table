"""One long-lived connection to the gripper Nano over USB serial.

The Nano answers every command with a state line (`pump=1 valve=0`) and
also sends one on its own when the valve times out. A reader thread keeps
the latest state and hands every change to the listeners.
"""

import re
import threading
import time

import serial

STATE_RE = re.compile(r"pump=(\d) valve=(\d)")
COMMANDS = {"pump_on": "P", "pump_off": "p", "valve_on": "V", "valve_off": "v",
            "grip": "G", "drop": "D", "stop": "S", "status": "?"}


class Nano:
    def __init__(self, port, baud=115200):
        self.port, self.baud = port, baud
        self.ser = None
        self.listeners = []  # callables(state: dict)
        self.state = {"connected": False, "pump": False, "valve": False}
        self._changed = threading.Condition()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
                time.sleep(2)  # the Nano resets on open
                self.ser.reset_input_buffer()
                self.ser.write(b"?")
                self._reader()
            except (serial.SerialException, OSError):
                pass
            self.ser = None
            self._set({"connected": False, "pump": False, "valve": False})
            time.sleep(2)

    def _reader(self):
        buf = b""
        while True:
            buf += self.ser.read(64)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                m = STATE_RE.search(raw.decode(errors="replace"))
                if m:
                    self._set({"connected": True, "pump": m[1] == "1", "valve": m[2] == "1"})

    def _set(self, state):
        with self._changed:
            self.state = state
            self._changed.notify_all()
        for fn in list(self.listeners):
            try:
                fn(state)
            except Exception:
                pass

    def send(self, name, timeout=1.0):
        """Send one command; return the state the Nano reports back."""
        if self.ser is None:
            return None
        with self._changed:
            self.ser.write(COMMANDS[name].encode())
            self._changed.wait(timeout)
            return self.state

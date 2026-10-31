"""Suction gripper, switched by GRBL itself.

The pump's MOSFET is on the CNC Shield's CoolEn pin (M8/M9) and the vent
valve's on SpnDir (M4 S0 opens, M3 S0 closes; S0 keeps the spindle off).
GRBL runs these in order with the moves, so a grip or drop never jumps ahead
of motion. One USB cable instead of a Nano also keeps the motor current out of
the Pi's ground (a second USB device on the 12V side knocked the Uno off USB).

GRBL doesn't report SpnDir while the spindle is at S0, so the hub keeps the
state itself.
"""

import threading

SEQUENCES = {
    "pump_on": ["M8"],
    "pump_off": ["M9"],
    "valve_on": ["M4 S0"],
    "valve_off": ["M3 S0", "M5"],
    "grip": ["M3 S0", "M5", "M8"],                         # valve shut, pump on
    "drop": ["M9", "M4 S0", "G4 P0.3", "M3 S0", "M5"],     # pump off, vent 0.3 s
    "stop": ["M9", "M3 S0", "M5"],
}
AFTER = {  # (pump, valve) once a sequence finishes; None = unchanged
    "pump_on": (True, None), "pump_off": (False, None),
    "valve_on": (None, True), "valve_off": (None, False),
    "grip": (True, False), "drop": (False, False), "stop": (False, False),
}
VALVE_MAX_S = 10  # the valve coil heats up if left open


class Gripper:
    def __init__(self, grbl, emit):
        self.grbl, self.emit = grbl, emit
        self.pump = self.valve = False
        self._timer = None
        grbl.listeners.append(self._on_grbl)

    @property
    def state(self):
        return {"pump": self.pump, "valve": self.valve}

    def run(self, name):
        """Send one sequence; waits for any queued motion first (M-codes sync)."""
        for line in SEQUENCES[name]:
            reply = self.grbl.send(line, timeout=300)
            if reply != "ok":
                return {**self.state, "error": f"{line}: {reply}"}
        pump, valve = AFTER[name]
        if pump is not None:
            self.pump = pump
        if valve is not None:
            self.valve = valve
        self._arm_timer()
        self._publish()
        return self.state

    def _arm_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self.valve:
            self._timer = threading.Timer(VALVE_MAX_S, self.run, args=("valve_off",))
            self._timer.daemon = True
            self._timer.start()

    def _on_grbl(self, ev):
        # a reset or reconnect turns coolant (the pump) off; SpnDir may stay set,
        # so a still-open valve is closed after the next unlock or home
        if ev.get("type") == "log" and ev.get("text", "").startswith("Grbl "):
            self.pump = False
            self._publish()

    def _publish(self):
        self.emit({"type": "gripper", **self.state})

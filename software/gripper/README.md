# Gripper server (Pi 5)

Pump and vent valve switches, separate from the GRBL hub so either can restart on its own.

- [`firmware/firmware.ino`](firmware/firmware.ino): the Nano. D2 pump, D3 valve, through 30N06L low-side MOSFETs. One-character commands at 115200: `P`/`p` pump on/off, `V`/`v` valve on/off, `G` grip, `D` drop (valve 0.3 s), `S` stop, `?` state. Every command answers `pump=1 valve=0`. The valve turns itself off after 10 s.
- [`server.py`](server.py) + [`nano.py`](nano.py): FastAPI on port 8001, one kept-open serial connection (opening it resets the Nano).
- [`static/index.html`](static/index.html): the page at `http://raspberrypi.local:8001/`, a switch each for pump and valve, Grip / Drop / STOP. Esc stops.

| Endpoint | |
|---|---|
| `GET /api/state` | `{connected, pump, valve}` |
| `POST /api/{pump_on,pump_off,valve_on,valve_off,grip,drop,stop,status}` | Returns the new state |
| `WS /ws` | State on every change |

**Flash the Nano** (compile on the Mac, flash from the Pi; this Nano has the old bootloader, 57600):

```bash
arduino-cli compile -b arduino:avr:nano --output-dir /tmp/nano software/gripper/firmware
scp /tmp/nano/firmware.ino.hex ash@raspberrypi.local:/tmp/gripper.hex
ssh ash@raspberrypi.local 'sudo systemctl stop gripper; avrdude -p atmega328p -c arduino -P /dev/ttyUSB0 -b 57600 -U flash:w:/tmp/gripper.hex:i; sudo systemctl start gripper'
```

**Deploy** (runs as `gripper.service`, starts on boot):

```bash
rsync -a --exclude .venv --exclude __pycache__ --exclude firmware software/gripper/ ash@raspberrypi.local:gripper/
ssh ash@raspberrypi.local 'sudo systemctl restart gripper'
```

First time: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` in `~/gripper`, then copy `gripper.service` to `/etc/systemd/system/` and `sudo systemctl enable --now gripper`. Set `GRIPPER_PORT` if the Nano isn't the CH340 at `/dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0`.

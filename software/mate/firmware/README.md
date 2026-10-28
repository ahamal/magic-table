# Mate firmware (ESP32)

Our own firmware. Raw motion only — no drive or turn logic. Mate's whole program runs on the ESP32: the Wi-Fi API ([spec](../README.md)), the control page, steppers, servos, the OLED face, the camera and the edge reflex.

> **Status:** [`mate/mate.ino`](mate/mate.ino) is still the **Arduino Nano version** from the earlier Pi 3 + Nano design. It was tested on both wheels. It is being ported to the ESP32; the step logic, finishing together, limits, edge reflex and stop carry over. The serial protocol below is the Nano sketch's; on the ESP32 the same commands move behind the HTTP API.

## Port plan

- **Per-board pin config** (DevKit now, ESP32-S3 CAM later) — pins in [`hardware/mate/README.md`](../../../hardware/mate/README.md#pins). The rest of the code is shared.
- **Stepping on its own core**, Wi-Fi and camera on the other, so motion stays smooth.
- **Servos:** ESP32Servo on GPIO 4, 13, 23 (DevKit), or the PCA9685 at 0x40 (required on the S3).
- **OLED:** SSD1306 at 0x3C, raw 128×64 images from `/screen`.
- **Camera:** OV2640 on the S3 only; the DevKit build answers `/capture` with `NO_CAMERA`.
- **OTA updates** over Wi-Fi, so Mate doesn't need USB once it's on battery.

Tested on the DevKit so far (throwaway sketches, not in the repo): I2C scan finds 0x29 (VL6180X), 0x3C (OLED), 0x40 + 0x70 (PCA9685); the VL6180X distance shows live on the OLED.

## Responsibilities

- Move both 28BYJ-48 steppers **at the same time, finishing together**, with acceleration ramps (AccelStepper).
- Set servo angles; detach servos 600 ms after each move to stop jitter and save power.
- **Edge reflex:** read the VL6180X while moving; if the table disappears, stop, back off, report `EDGE`.
- Enforce limits: max steps per command, max speed, max acceleration.
- Coils off when idle.
- Never block: no `delay()` in the loop — `run()` is called continuously.

## Serial protocol

115200 baud, one command per line (`\n`, `\r` ignored), one reply line per command. On boot the firmware prints `READY mate <version>`.

| Command | Meaning | Reply |
|---|---|---|
| `M <s1> <s2> [speed] [accel]` | Move both steppers by raw half-steps (+/−). Replies when finished. | `OK <d1> <d2>` · `EDGE <d1> <d2>` · `STOPPED <d1> <d2>` · `ERR LIMIT` |
| `V <id> <angle>` | Servo `id` (0 pan, 1 tilt, 2 flipper) to `angle` 0–180 | `OK` · `ERR RANGE` |
| `X` | Stop now and release coils (accepted mid-move) | `STOPPED <d1> <d2>` then `OK` if a move was running, else `OK` |
| `R` | Release coils | `OK` |
| `Q` | Status | `S busy=<0\|1> p1=<steps> p2=<steps> edge=<mm\|none> v0=<deg> v1=<deg> v2=<deg>` |
| `I` | Info | `I fw=<version> maxsteps=<n> maxspeed=<n> maxaccel=<n> servos=<n> edge=<0\|1>` |

- `<d1> <d2>` are the half-steps each wheel **actually** moved during the command (net, including any edge back-off).
- Servo angles report `-1` until first set.
- **While a move is running, only `X` and `Q` are accepted**; anything else gets `ERR BUSY`. This keeps replies unambiguous.
- Malformed lines → `ERR PARSE`. Lines over 47 characters are truncated.

### Defaults and limits

| | Default | Max |
|---|---|---|
| Steps per command | — | 4096 half-steps (about one wheel turn) |
| Speed | 500 half-steps/s | 800 |
| Acceleration | 400 half-steps/s² | 1000 |

## Edge reflex

- **Edge** = the VL6180X reads ≥ 50 mm (or 255, out of range) for **2 consecutive samples** (the sensor samples every 20 ms). Glitches are filtered.
- **On edge during a move:** hard stop, then reverse **200 half-steps** the way it came, keeping the same wheel ratio. That needs no idea of which way is "forward". Reply `EDGE <d1> <d2>`.
- **If a move starts with the sensor already over the edge:** the move is allowed. If the sensor comes back over the table, it's moving away — fine. If it's still over the edge after **120 half-steps**, it's moving further out: stop and back off.
- **No sensor connected:** the reflex is disabled; `I` reports `edge=0` and `Q` reports `edge=none`.

All of these are constants at the top of the sketch. Tune `EDGE_MM` once Mate is built: it should sit well above the normal table reading (expected 10–30 mm, depending on mounting height).

## Pins (Nano sketch — ESP32 pins are in the hardware README)

| Pin | Connects to |
|---|---|
| D2 D3 D4 D5 | ULN2003 #1 IN1–IN4 (stepper 1) |
| D6 D7 D8 D9 | ULN2003 #2 IN1–IN4 (stepper 2) |
| D10 | Servo 0 (pan) |
| D11 | Servo 1 (tilt) |
| D12 | Servo 2 (flipper) |
| A4 / A5 | VL6180X SDA / SCL |

Wire the ULN2003 boards IN1→IN1 etc.; the sketch handles the HALF4WIRE pin order (IN1, IN3, IN2, IN4). More in [`hardware/mate/README.md`](../../../hardware/mate/README.md).

## Build and upload (Nano sketch)

Libraries: **AccelStepper**, **Servo**, **VL6180X** (Pololu).

```bash
arduino-cli lib install AccelStepper Servo VL6180X
```

```bash
arduino-cli compile --fqbn arduino:avr:nano software/mate/firmware/mate
```

Upload (port from `arduino-cli board list`; many Nano clones need `arduino:avr:nano:cpu=atmega328old`):

```bash
arduino-cli upload --fqbn arduino:avr:nano -p /dev/cu.usbserial-XXXX software/mate/firmware/mate
```

Compiled size for Nano/Uno: about 16 KB flash (53%), 740 bytes RAM (36%).

## Quick test (Serial Monitor at 115200, newline line endings)

```
I                  → I fw=0.1.0 maxsteps=4096 maxspeed=800 maxaccel=1000 servos=3 edge=1
Q                  → S busy=0 p1=0 p2=0 edge=23 v0=-1 v1=-1 v2=-1
M 400 400          → OK 400 400        (watch: straight, or a spin?)
M 400 -400         → OK 400 -400
V 0 90             → OK
M 4000 4000        → then send X mid-move → STOPPED 1234 1234, OK
```

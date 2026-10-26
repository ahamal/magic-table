# Mate firmware (Arduino)

Our own firmware. Raw motion only — no drive or turn logic. Talks to the Pi 3 over USB serial.

## Responsibilities

- Move both 28BYJ-48 steppers **at the same time**, finishing together, with acceleration ramps (AccelStepper).
- Set servo angles.
- **Edge reflex:** read the VL6180X while moving; if the table disappears, stop, back off a little, report `EDGE`.
- Enforce limits: max steps per command, max speed, max acceleration.
- Coils off when idle.
- Never block: no `delay()` — `run()` must be called continuously in `loop()`.

## Serial protocol

115200 baud, one command per line, one reply per command. Moves reply only when finished.

| Command | Meaning | Reply |
|---|---|---|
| `M <s1> <s2> [speed] [accel]` | Move both steppers by raw half-steps (+/−) | `OK <done1> <done2>` · `EDGE <done1> <done2>` · `STOPPED <done1> <done2>` · `ERR LIMIT` |
| `V <id> <angle>` | Servo `id` to `angle` (0–180) | `OK` · `ERR RANGE` |
| `X` | Stop now, release coils (accepted mid-move) | `OK` |
| `R` | Release coils | `OK` |
| `Q` | Status | `S busy=<0\|1> p1=<steps> p2=<steps> edge=<mm\|255> v0=<deg> v1=<deg> v2=<deg>` |
| `I` | Info | `I fw=<version> maxsteps=<n> maxspeed=<n> maxaccel=<n> servos=<n> edge=<0\|1>` |

Unknown or malformed lines → `ERR PARSE`.

## Implementation notes

- **Constructor:** `AccelStepper(AccelStepper::HALF4WIRE, IN1, IN3, IN2, IN4)` — note the pin order.
- **Finishing together:** scale the shorter move's max speed and acceleration by `|short| / |long|` (MultiStepper has no acceleration, so don't use it).
- **Edge detection:** "edge" = reading jumps to 255 (out of range) or rises well above the baseline table distance. Check every few ms while moving. On edge: stop hard, reverse ~200 half-steps on both wheels (the direction just travelled, reversed), reply `EDGE`. Backing off avoids needing to know which way is "forward".
- **Servos:** `Servo` library. On Uno/Nano it uses Timer1, which disables `analogWrite` on D9/D10 — fine, they're used as digital outputs for the stepper.
- **Serial while moving:** keep reading serial in `loop()` so `X` works mid-move.

## Pins

See [`hardware/mate/README.md`](../../../hardware/mate/README.md#wiring-proposed-for-an-arduino-nano-or-uno).

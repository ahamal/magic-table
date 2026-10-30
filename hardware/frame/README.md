# The Frame (hardware)

The Robo Diner CoreXY gantry, reused as the table's hands and eyes. Controlled by the Pi 5, which is also the hub for the whole table.

## Components

| Part | Detail | Status |
|---|---|---|
| Gantry | CoreXY, V-wheel gantry, inverted Z rail, NEMA 17 steppers, TMC2208 drivers | Exists (Robo Diner) |
| Controller | Arduino Uno + CNC Shield V3, GRBL 1.1h built with CoreXY (`$I` → `[OPT:VCZ,15,128]`), 12V motor supply | Exists, working |
| Limit switches | Homing (`$H`) for repeatable coordinates | Exists |
| Computer | Raspberry Pi 5 (`ash@raspberrypi.local`), the table hub | Exists |
| Overhead camera | Camera v2 (imx219), ~50 cm above the table | Have camera; needs mount + 22→15-pin cable |
| Gripper | 12 mm 2-layer bellows suction cup on a sprung printed mount | Have |
| Pump | 12V self-priming diaphragm pump (uxcell or CrocSee, 1.3 L/min, ~300 mA) | Ordering |
| Release valve | AIRZOE 2V025-08, 12V, normally closed, direct-acting, outlet wire; 1/4" NPT | Ordering |
| Gripper driver | Arduino Nano + 2× 30N06L logic-level MOSFET modules, 1N4007 across each load | Have |
| Height sensor | VL6180X on the head, I2C to the Pi 5 | Have |
| Touch switch | Optional, on the cup's spring mount, to GRBL probe pin (`G38.2`) | Optional |
| E-stop | Button to GRBL reset / feed-hold pin | To add |

## Wiring

```
Pi 5 ── USB ──────────► Uno + CNC Shield (GRBL, /dev/ttyACM0)
                         ├─ X/Y (CoreXY) + Z steppers
                         ├─ limit switches
                         └─ probe pin ◄── touch switch (optional)
Pi 5 ── USB ──────────► Nano ── D2 ─► MOSFET ─► diaphragm pump   (12V)
                              └─ D3 ─► MOSFET ─► solenoid valve   (12V)
Pi 5 ── CSI (22-pin) ─► adapter ─► long ribbon (≤ 1 m) ─► Camera v2
Pi 5 ── I2C (pins 3/5) ► VL6180X on the head   (short cable, low bus speed)
```

**Air path:** cup ── tube ── T ── pump inlet; the T's third leg goes to the valve, whose other port is open to the air. The valve can sit on the frame next to the pump; only the cup and tube ride on the head.

**VL6180X:** VIN → pin 1 (3.3V), GND → pin 6, SDA → pin 3 (GPIO 2), SCL → pin 5 (GPIO 3). Address 0x29. Enable I2C with `sudo raspi-config nonint do_i2c 0`.

## GRBL settings

Tuned on Oct 30 at 12V (see [`docs/log.md`](../../docs/log.md)):

| Setting | Value | Note |
|---|---|---|
| `$100`–`$102` steps/mm | 50 | **Not measured yet.** GT2 + 20T pulley is 40 (1/8 step) or 80 (1/16 step) |
| `$110`, `$111` max rate X/Y | 9000 mm/min (~150 mm/s) | 12000 skipped steps |
| `$112` max rate Z | 7000 mm/min | Z doesn't need more; keep picks gentle |
| `$120`–`$122` acceleration | 500 mm/s² | Was 80; halved the test time, clean |
| `$22` homing | on | GRBL starts in alarm: `$H` to home, or `$X` to unlock |
| `$1` step idle delay | 25 ms | Shared enable pin: idle motors click at move start/end. `$1=255` keeps them energized |

- **The 12V supply is the speed limit,** not power: about 200 mm/s is the estimated ceiling (coil inductance and back-EMF). 24V would roughly double it, but the pump and valve are 12V parts and would need their own supply.
- **Build options** (`$I`): `V` variable spindle, `C` CoreXY, `Z` homing sets machine zero at the switches. 15-block planner, 128-byte serial buffer. Moves are sent as normal X/Y; GRBL does the CoreXY mixing.
- **Keep the serial port open.** Opening it resets the Uno, which loses position and re-locks GRBL.
- **Never plug or unplug a motor with the 12V on.**

## Notes

- **Pick sequence:** lower until touch (or to `sense_z` height), pump on (grips in under a second), move with the pump still on, then pump off and valve on ~0.3 s to drop.
- **Why a valve:** a diaphragm pump can't reverse (its check valves set the direction), and it leaks back slowly when off. The NC valve vents the line for a clean drop. The peristaltic pump was too weak; it can stand in as a vent on the T until the valve arrives.
- **Why a Nano:** the Pi 5 never touches the 12V side, only USB. Protocol: `G` grip, `D` drop, `S` stop. Power the Nano from USB only.
- **Camera:** Camera v2 field of view is ~62°×49°; at ~50 cm it covers about 60×44 cm. Keep the ribbon away from stepper wires.
- **VL6180X:** usable ~5–100 mm; mount so the table is 20–60 mm below with the head up. Keep its window clear. 255 = out of range. Average ~5 readings.
- **Calibration:** ArUco marker on the head, move to a grid of points, fit pixel → gantry mm. Remove the marker afterwards. Small backup markers on top of the frame corners.
- **Robo Diner hand:** the tilt/grab servos (PCA9685) — keep or replace with the suction head? See open questions.

## Open

See [`docs/open-questions.md`](../../docs/open-questions.md#frame): travel, steps/mm, camera cable, e-stop.

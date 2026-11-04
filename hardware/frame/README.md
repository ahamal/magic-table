# The Frame (hardware)

A CoreXY gantry rebuilt for this project from a dismantled earlier machine (rails, NEMA 17 steppers, GT2 belts and drivers salvaged, then cut, modified and reassembled): the table's hands and eyes. Controlled by the Pi 5, which is also the hub for the whole table.

## Components

| Part | Detail | Status |
|---|---|---|
| Gantry | CoreXY, V-wheel gantry, inverted Z rail, NEMA 17 steppers, TMC2208 drivers, GT2 belts | Rebuilt from salvaged parts (cut and modified) |
| Controller | Arduino Uno + GRBL CNC Shield (from a Longruner CNC kit; the kit's RAMPS 1.4 isn't used), standard GRBL 1.1h built with CoreXY (`$I` → `[OPT:VCZ,15,128]`), 12V motor supply | Working |
| Limit switches | None. No homing: position comes from re-anchoring (saved position or both cameras) and a Z touch-off | — |
| Computer | Raspberry Pi 5 (`ash@raspberrypi.local`), the table hub | Exists |
| Overhead camera | Camera v2 (imx219), ~50 cm above the table | Working on the Pi 5 (`GET /api/capture`); needs a mount |
| Gripper | 2-layer bellows suction cup, 15 mm across (sold as 12 mm), on a sprung printed mount | Working |
| Pump | 12V self-priming diaphragm pump (uxcell or CrocSee, 1.3 L/min, ~300 mA) | Working |
| Release valve | AIRZOE 2V025-08, 12V, normally closed, direct-acting, outlet wire; 1/4" NPT | Working |
| Gripper driver | 2× 30N06L logic-level MOSFET modules on the CNC Shield's CoolEn and SpnDir pins, 1N4007 across each load | Working |
| Height sensor | VL6180X on the head, I2C to the Pi 5 | Have |
| Touch switch | Optional, on the cup's spring mount, to GRBL probe pin (`G38.2`) | Optional |
| E-stop | Button to GRBL reset / feed-hold pin | To add |

## Wiring

```
Pi 5 ── USB ──────────► Uno + CNC Shield (GRBL, /dev/ttyACM0)
                         ├─ X/Y (CoreXY) + Z steppers
                         ├─ probe pin ◄── touch switch (optional)
                         ├─ CoolEn (A3) ─► MOSFET ─► diaphragm pump   (12V)  M8 / M9
                         └─ SpnDir (D13) ─► MOSFET ─► solenoid valve  (12V)  M4 S0 / M3 S0
Pi 5 ── CSI (22-pin) ─► 22→15 cable ─► Camera v2
Pi 5 ── I2C (pins 3/5) ► VL6180X on the head   (short cable, low bus speed)
```

**Air path:** cup ── tube ── T ── pump inlet; the T's third leg goes to the valve, whose other port is open to the air. The valve can sit on the frame next to the pump; only the cup and tube ride on the head.

**MOSFETs:** shield signal pin → 220 Ω → gate, 10 k gate → GND; source → shield GND and 12V −; drain → load −; load + → 12V +; 1N4007 across the load, stripe on +.

**Leave SpnEn and the Z+/Z− end-stop header free.** There are no limit switches. In this variable-spindle build GRBL uses D11 (the shield's Z end-stop header) for the spindle output and reads D12 (the header labeled SpnEn) as the Z limit input; nothing is connected to either.

**VL6180X:** VIN → pin 1 (3.3V), GND → pin 6, SDA → pin 3 (GPIO 2), SCL → pin 5 (GPIO 3). Address 0x29. Enable I2C with `sudo raspi-config nonint do_i2c 0`.

## GRBL settings

Tuned on Oct 30 at 12V (see [`docs/log.md`](../../docs/log.md)):

| Setting | Value | Note |
|---|---|---|
| `$100`, `$101` steps/mm X/Y | 40 | Measured Nov 1: a 100 mm jog moves 100 mm. GT2 belt, 20T pulley, TMC2208 at 1/8 step (no jumpers) |
| `$102` steps/mm Z | 40 | Measured Nov 1: 100 commanded moved 126 at 50. Same belt and pulley as X/Y |
| Z travel | −1 to 150 | Work Z 0 = cup touching the board, 150 = top of travel; the hub keeps moves and jogs inside this. Travel height (over Esper) is Z 110 |
| `$3` direction invert | 4 (Z) | The Z motor ran backwards (Z+ lowered the cup). Now Z+ is up, as on any CNC |
| `$110`, `$111` max rate X/Y | 11000 mm/min (~183 mm/s) | Real mm since steps/mm = 40. About the step rate that ran clean on Oct 30; ~15000 real mm/min skipped steps |
| `$112` max rate Z | 7000 mm/min | Z doesn't need more; keep picks gentle |
| `$120`–`$122` acceleration | 500 mm/s² | Was 80; halved the test time, clean |
| `$22` homing | on, but there are no switches | Never `$H`: it would drive the axes into the frame. GRBL starts in alarm; `$X` to unlock, then re-anchor |
| `$1` step idle delay | 25 ms | Shared enable pin: idle motors click at move start/end. `$1=255` keeps them energized |

- **The 12V supply is the speed limit,** not power: about 200 mm/s is the estimated ceiling (coil inductance and back-EMF). 24V would roughly double it, but the pump and valve are 12V parts and would need their own supply.
- **Build options** (`$I`): `V` variable spindle, `C` CoreXY, `Z` homing sets machine zero at the switches (unused: there are none). 15-block planner, 128-byte serial buffer. Moves are sent as normal X/Y; GRBL does the CoreXY mixing.
- **Keep the serial port open.** Opening it resets the Uno, which loses position and re-locks GRBL.
- **Never plug or unplug a motor with the 12V on.**

## Notes

- **Pick sequence:** lower until touch (or to `sense_z` height), pump on (grips in under a second), move with the pump still on, then pump off and valve on ~0.3 s to drop.
- **Why a valve:** a diaphragm pump can't reverse (its check valves set the direction), and it leaks back slowly when off. The NC valve vents the line for a clean drop. The peristaltic pump was too weak; it can stand in as a vent on the T until the valve arrives.
- **Why GRBL drives the gripper, not a Nano:** a Nano on USB with its ground tied to 12V − made a second ground path through the Pi, and stepper current on it knocked the Uno off USB on every move. With the MOSFETs on the shield there's one USB cable and one ground. The pump and valve also run in order with the moves (M-codes wait for motion to finish), and the Pi still never touches 12V.
- **SpnDir as the valve:** GRBL sets the spindle direction pin with `M4` and clears it with `M3`, and `S0` keeps the spindle itself off. It's also the Uno's LED pin, so the valve blips while the Uno boots. A soft reset can leave it set; the hub closes the valve after the next unlock or home.
- **Camera:** Camera v2 field of view is ~62°×49°; at ~50 cm it covers about 60×44 cm. Keep the ribbon away from stepper wires.
- **VL6180X:** usable ~5–100 mm; mount so the table is 20–60 mm below with the head up. Keep its window clear. 255 = out of range. Average ~5 readings.
- **Calibration:** ArUco head marker (on the [marker plate](markers/README.md)) moved over a grid at three heights; the hub fits each camera ([`software/hub/vision.py`](../../software/hub/vision.py)). Start with Z at its top over the middle of the board: calibration only goes down from there, never closer than 15 mm to the board, and stops with no further moves on any reset, pause or error.
- **No limit switches, so counts can lie.** A move into an end of travel stalls and skips steps, but GRBL counts it anyway, and the next move "back" by count overshoots. On Nov 1 calibration went up into the top of Z, then "returned" 40 mm too low and tore the board paper. Hence: start at the top and go down, never assume room above.
- **Esper rule:** a sideways bump is fine, pressing down into Esper isn't. Travel height is Z 110 (Esper is 105 to the top of its corner caps); below it the hub never lowers or ends the cup over Esper, and moves across it go up first. Esper's toggle switch now sits at the back, off the top.
- **The old machine's hand:** replaced by the suction head (pump on CoolEn, valve on SpnDir); the tilt/grab servos aren't used.

## Open

See [`docs/open-questions.md`](../../docs/open-questions.md#frame): travel, steps/mm, camera cable, e-stop.

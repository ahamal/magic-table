# The Frame (hardware)

The Robo Diner CoreXY gantry, reused as the table's hands and eyes. Controlled by the Pi 5, which is also the hub for the whole table.

## Components

| Part | Detail | Status |
|---|---|---|
| Gantry | CoreXY, V-wheel gantry, inverted Z rail, NEMA 17 steppers, TMC2208 drivers | Exists (Robo Diner) |
| Controller | Arduino + RAMPS 1.4, GRBL, 12V input | Exists — confirm board and GRBL build |
| Limit switches | Homing (`$H`) for repeatable coordinates | Exists |
| Computer | Raspberry Pi 5 — table hub | Exists |
| Overhead camera | Camera v2 (imx219), ~50 cm above the table | Have camera; needs mount + 22→15-pin cable |
| Gripper | 12 mm 2-layer bellows suction cup on a sprung printed mount | Ordered? |
| Pump | 12V peristaltic pump, reversible | Exists — confirm DC or stepper |
| Pump driver | H-bridge (MX1508 / L9110S / DRV8871) on 12V, controlled by Pi 5 GPIO | To buy |
| Height sensor | VL6180X on the head, I2C to the Pi 5 | Have |
| Touch switch | Optional, on the cup's spring mount, to GRBL probe pin (`G38.2`) | Optional |
| E-stop | Button to GRBL reset / feed-hold pin | To add |

## Wiring

```
Pi 5 ── USB ──────────► Arduino + RAMPS (GRBL)
                         ├─ X/Y (CoreXY) + Z steppers
                         ├─ limit switches
                         └─ probe pin ◄── touch switch (optional)
Pi 5 ── CSI (22-pin) ─► adapter ─► long ribbon (≤ 1 m) ─► Camera v2
Pi 5 ── I2C (pins 3/5) ► VL6180X on the head   (short cable, low bus speed)
Pi 5 ── GPIO ─────────► H-bridge ─► peristaltic pump   (12V from the RAMPS supply)
```

**VL6180X:** VIN → pin 1 (3.3V), GND → pin 6, SDA → pin 3 (GPIO 2), SCL → pin 5 (GPIO 3). Address 0x29. Enable I2C with `sudo raspi-config nonint do_i2c 0`.

## Notes

- **Pump:** RAMPS MOSFET outputs (D8/D9/D10) only switch on/off, but the peristaltic pump must **reverse** to release. Hence the H-bridge. If the pump is a stepper, an alternative is a spare RAMPS stepper slot as an extra GRBL axis (needs a multi-axis GRBL build).
- **Pick sequence:** lower until touch (or to `sense_z` height), pump forward 1–2 s, stop (grip holds), move, reverse ~0.5 s to drop.
- **Camera:** Camera v2 field of view is ~62°×49°; at ~50 cm it covers about 60×44 cm. Keep the ribbon away from stepper wires.
- **VL6180X:** usable ~5–100 mm; mount so the table is 20–60 mm below with the head up. Keep its window clear. 255 = out of range. Average ~5 readings.
- **Calibration:** ArUco marker on the head, move to a grid of points, fit pixel → gantry mm. Remove the marker afterwards. Small backup markers on top of the frame corners.
- **Robo Diner hand:** the tilt/grab servos (PCA9685) — keep or replace with the suction head? See open questions.

## Open

See [`docs/open-questions.md`](../../docs/open-questions.md#frame): travel, board/GRBL build, pump type and current, hostname, camera cable, e-stop.

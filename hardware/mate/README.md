# Mate (hardware)

A small wheeled robot on the table — the AI player's body. Self-contained: its own Pi, its own API, its own safety.

## Components

| Part | Detail | Status |
|---|---|---|
| Computer | Raspberry Pi 3 Model B, Raspbian 11 (bullseye), hostname `mate` | Working |
| Motor controller | Arduino (model TBD) over USB serial, our own firmware | Have |
| Wheels | 2× 28BYJ-48 + ULN2003, differential drive, ball caster or skid at the back | Have motors |
| Servos | Pan (SG90/MG90S), optional tilt, optional flipper (MG90S) | Have |
| Camera | ov5647 (the cheaper one), on the pan/tilt mount — also the peek camera | Working (tested) |
| Screen | Tiny screen for faces — the Pi has a 3.5" SPI touchscreen overlay (ads7846) configured | Confirm |
| Edge sensor | VL6180X, front, pointing down, 2–3 cm ahead of the wheels, I2C to the Arduino | Have |
| Range sensor | TF-Luna on the pan mount (I2C mode, 0x10) | Later |
| Speaker | For `say` | TBD |
| Marker | ArUco on the roof, designed into Mate's look | To make |
| Power | 3A two-port 5V power bank | Needed — Mate currently reports under-voltage |

## Wiring (proposed, for an Arduino Nano or Uno)

```
Pi 3 ── USB ──► Arduino
                 ├─ D2  D3  D4  D5   → ULN2003 #1 IN1..IN4 → stepper 1
                 ├─ D6  D7  D8  D9   → ULN2003 #2 IN1..IN4 → stepper 2
                 ├─ D10              → servo 0 (pan)
                 ├─ D11              → servo 1 (tilt)
                 ├─ D12              → servo 2 (flipper)
                 └─ A4 (SDA), A5 (SCL) → VL6180X edge sensor
Pi 3 ── CSI ──► ov5647 camera
Pi 3 ── SPI ──► screen   (its pins are reserved: GPIO 25, SPI)
```

- **AccelStepper pin order for the 28BYJ-48 is IN1, IN3, IN2, IN4** — get it wrong and it buzzes.
- **Servos and motors are powered from the battery's 5V line, not the Arduino's 5V pin.** A stalled servo draws ~650 mA.
- **Shared ground** between the Pi, the Arduino, the ULN2003 boards and the servo supply.

## Power

| Part | Typical | Peak |
|---|---|---|
| Pi 3 | 500–700 mA | ~1.2 A |
| Camera | ~250 mA | ~250 mA |
| 28BYJ-48 (each, moving) | ~150 mA | ~200 mA |
| Servo (each) | 10 mA idle / 150 mA moving | ~650 mA stalled |
| Arduino | ~30 mA | ~50 mA |

Total: 1.2–1.5 A typical, 2–2.5 A peak. Use a **3A two-port bank**: Pi on one port, Arduino + motors + servos on the other, grounds shared. Short, thick cables. Mount the battery low and centred. A 10,000 mAh bank gives roughly 4–5 hours.

## Notes

- **Camera:** mounted upside down so far — images need a 180° rotation (`--rotation 180`).
- **Edge sensor reflex** lives in the Arduino firmware, not the Pi, so the stop is instant.
- **Speed:** 28BYJ-48 tops out around 500–800 half-steps/s; about 3–5 cm/s with 60 mm wheels.
- **Peek:** the gantry hovers a card over Mate's camera (tilted up), or drops it on a clear flipper paddle above the camera. The ov5647 focuses at ~1 m by default; screw the lens out for close focus (~8–10 cm) or use a clip-on macro lens.

## Open

See [`docs/open-questions.md`](../../docs/open-questions.md#blocking-step-1-mate): Arduino model, wheel size and spacing, servo count, screen, speaker, chassis, power bank.

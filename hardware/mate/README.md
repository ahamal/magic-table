# Mate (hardware)

A small wheeled robot on the table — the AI player's body. Self-contained: its own ESP32, its own API over Wi-Fi, its own safety.

## Components

| Part | Detail | Status |
|---|---|---|
| Controller (now) | ESP32 DevKit V1, 30-pin (ESP32-WROOM, CP2102 USB). Runs everything: Wi-Fi API, steppers, servos, face, edge reflex | Working — I2C bus tested |
| Controller (target) | Freenove ESP32-S3-WROOM CAM (8 MB PSRAM, USB-C, OV2640 camera). Same firmware, different pin config | Arriving |
| Wheels | 2× 28BYJ-48 + ULN2003, differential drive, 60 mm printed wheels ([`wheels/`](wheels/)), ball caster or skid at the back | Have motors, wheels designed |
| Servos | Pan (SG90/MG90S), tilt, optional flipper (MG90S) | Have |
| Servo driver | PCA9685 (I2C 0x40), servo power on its V+ terminal from the 5V side | Have — on the bus |
| Camera | OV2640 on the S3 board, on the pan/tilt head — also the peek camera. None on the DevKit (`/capture` returns "no camera") | Arriving |
| Face | 0.96" SSD1306 OLED, 128×64, I2C 0x3C, on the pan/tilt head with the camera just below it | Working |
| Edge sensor | VL6180X (I2C 0x29), front, pointing down, 2–3 cm ahead of the wheels, 10–30 mm above the table | Working |
| Range sensor | TF-Luna on the pan mount (I2C mode, 0x10, 5V power) | Later |
| Speech | Done by the hub (the Pi 5 speaks for Mate) | — |
| Marker | ArUco on the roof, designed into Mate's look | To make |
| Hub board | ~5 × 7 cm perfboard: 5V and I2C buses with JST-XH connectors (below) | Built — I2C side tested |
| Power | 5V USB power bank through a cut USB cable on the robot; CanaKit 5V supply on the bench | Have |

Spares: Raspberry Pi 3B, Arduino Nano and ov5647 camera (the earlier design). The first ESP32 DevKit no longer programs over USB — don't use it.

## Wiring

```
                 ┌─────────────── HUB (perfboard) ───────────────┐
 CanaKit / bank ─┤ PWR IN (XH-2)                  I2C-1 (XH-4) ──├─► OLED
                 │  + 1000µF                      I2C-2 (XH-4) ──├─► VL6180X
 ESP32 ─────────►┤ LINK (XH-4): GND,3V3,SDA,SCL   I2C-3 (XH-4) ──├─► PCA9685
 ESP32 GPIO ────►┤ SERVO SIG (XH-3): 4,13,23      SV0 SV1 SV2 ───├─► servos
                 │                                MOT-1 (XH-2) ──├─► ULN2003 #1 power
                 │ ESP PWR (XH-2, battery only)   MOT-2 (XH-2) ──├─► ULN2003 #2 power
                 └────────────────────────────────────────────────┘
 ESP32 GPIO 16,17,18,19 ─ 4-wire dupont ──► ULN2003 #1 IN1–IN4  (direct, not via hub)
 ESP32 GPIO 25,26,27,32 ─ 4-wire dupont ──► ULN2003 #2 IN1–IN4  (direct, not via hub)
```

### Pins

| Function | ESP32 DevKit | ESP32-S3 CAM (check Freenove's pinout first) |
|---|---|---|
| Stepper 1 IN1–IN4 | 16, 17, 18, 19 | 1, 2, 14, 21 |
| Stepper 2 IN1–IN4 | 25, 26, 27, 32 | 38, 39, 40, 41 |
| I2C SDA, SCL | 21, 22 | 42, 47 |
| Servos | GPIO 4, 13, 23 through the hub, or the PCA9685 | PCA9685 only (not enough pins) |

- **Avoid on the DevKit:** GPIO 6–11 (flash), 34–39 (input only), 0, 2, 5, 12, 15 (boot strapping).
- **Wire ULN2003 IN1→IN1 and so on;** the firmware handles the 28BYJ-48 coil order (IN1, IN3, IN2, IN4).
- **3.3V signals are fine** for the ULN2003 boards, servos, OLED, VL6180X and PCA9685.
- **Only one VL6180X on the bus** — a second one also answers at 0x29.

### Hub board

- **Top half 5V** (PWR IN, MOT-1/2, servo headers, ESP PWR), **bottom half 3.3V I2C** (LINK, I2C-1/2/3). Only GND joins the halves.
- **The I2C bus is powered from the ESP32's 3V3 pin** through LINK. Never connect it to 5V.
- **GND is pin 1 on every connector**, marked on the board. XH-2 power: GND, 5V. XH-4 I2C: GND, 3.3V, SDA, SCL. Servo headers: GND, 5V, signal.
- **Wire colours:** black GND, red 5V, orange 3.3V, blue SDA, yellow SCL.
- **1000 µF** across 5V and GND at PWR IN (stripe to GND). A 100 µF near the ESP32's power input helps against brownouts.
- **All grounds join,** star-style at the hub. Motor and servo current returns through the hub, not through the ESP32.
- Before plugging in, check with a multimeter: 5V–GND, 3V3–GND and 5V–3V3 all open.

## Power

| Part | Idle | Typical | Peak |
|---|---|---|---|
| ESP32-S3 + Wi-Fi | 80 mA | 120 mA | ~500 mA (Wi-Fi bursts) |
| Camera (OV2640) | — | 120 mA | 150 mA |
| 2× 28BYJ-48 | 0 (coils off) | 400 mA | 480 mA |
| Servo (each) | ~10 mA | 150–250 mA | 650–1,000 mA stalled |
| OLED, VL6180X, PCA9685 | ~20 mA | ~35 mA | ~45 mA |
| TF-Luna (later) | — | 70 mA | 100 mA |

About 0.15–0.3 A parked, 0.7 A driving, 1.5 A busy, 2–2.5 A if a servo stalls. A 10,000 mAh bank gives ~10–12 h of mixed play (the Pi version managed 4–5 h). A 2 A port is enough.

- **Bench:** ESP32 on USB, CanaKit 5V into PWR IN, **ESP PWR unplugged.**
- **Battery:** USB unplugged, power bank into PWR IN, ESP PWR into the ESP32's VIN and GND.
- **Never have USB and ESP PWR plugged in together** — two supplies fight through the ESP32. Unplug ESP PWR to program on battery (or use OTA once the web server runs).
- **Keep the ESP32 drawing from the same port as the motors,** so the bank doesn't switch the port off while Mate is parked.
- Power banks and the CanaKit have built-in short-circuit protection; zip-tie the cut cable near the joint for strain relief.

## Size (estimate, chassis not designed yet)

About **14 × 11 × 12 cm, 350–450 g**.

| | Estimate | What sets it |
|---|---|---|
| Wheel spacing (centre to centre) | ~100 mm | Stable, precise turns |
| Overall width | ~110 mm | Spacing plus the 8 mm wheels |
| Length | ~130–150 mm | Power bank behind the axle (a ~70 mm-wide bank doesn't fit between the motors), edge sensor in front |
| Deck height | ~50–60 mm | Axle at 30 mm, ULN2003 boards on edge |
| Head top | ~110–130 mm | Pan/tilt bracket with the OLED and camera |

The head has to fit under the gantry head while it holds a card over the camera for a peek — check against the Frame's Z travel.

## Notes

- **Edge sensor reflex** runs in the firmware on the ESP32, so the stop is instant. On the bench it reads ~34–40 mm; the edge cutoff is 50 mm.
- **Speed:** 28BYJ-48 tops out around 500–800 half-steps/s; about 3.7 cm/s with 60 mm wheels.
- **Motors on their own core:** stepping runs on one ESP32 core, Wi-Fi and the camera on the other, so motion stays smooth.
- **Peek:** the gantry hovers a card over Mate's camera (tilted up), or drops it on a clear flipper paddle above the camera. The OV2640 should read card corners at 10–15 cm once the lens is focused close — **test this first when the S3 arrives.** If it can't, the overhead camera handles peeking another way.
- **Mood light:** the S3 board's RGB LED.

## Open

See [`docs/open-questions.md`](../../docs/open-questions.md#blocking-step-1-mate): servo count, chassis, OV2640 card reading.

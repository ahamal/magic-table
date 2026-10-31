# Mate (hardware)

A small wheeled robot on the table — the AI player's body. Self-contained: its own ESP32-S3, its own API over Wi-Fi, its own camera.

## Components

| Part | Detail | Status |
|---|---|---|
| Controller | Freenove ESP32-S3-WROOM CAM: ESP32-S3 (rev v0.2), 8 MB flash, 8 MB PSRAM, CH343 USB-serial, camera connector. Runs everything: Wi-Fi API, steppers, servos, face, camera | Working — firmware in [`software/mate/firmware`](../../software/mate/firmware) |
| Camera | The board's bundled **GC0308**, 640×480, no hardware JPEG (the firmware encodes in software). On the pan/tilt head — also the peek camera. An OV2640/OV3660 module fits the same connector | Working |
| Wheels | 2× 28BYJ-48 + ULN2003, differential drive, 70 mm printed wheels ([`wheels/`](wheels/)), ball caster or skid at the back | Have motors, wheels designed |
| Servos | Pan (SG90/MG90S), tilt, optional flipper (MG90S), driven straight from the ESP32's PWM | Have |
| Face | 0.96" SSD1306 OLED, 128×64, I2C 0x3C, on the pan/tilt head with the camera just below it. The only I2C device | Working on the DevKit; not yet rewired to the S3 |
| Range sensor | TF-Luna on the pan mount (I2C mode, 0x10, 5V power) | Later |
| Speech | Done by the hub (the Pi 5 speaks for Mate) | — |
| Marker | ArUco on the roof, designed into Mate's look | To make |
| Hub board | ~5 × 7 cm perfboard: 5V and I2C buses with JST-XH connectors (below) | Built — needs the S3 rewiring |
| Power | 5V USB power bank through a cut USB cable on the robot; CanaKit 5V supply on the bench | Have |

**Dropped:** the PCA9685 servo board (took too much space; the S3 has enough pins once the distance sensor is gone) and the VL6180X edge sensor. Without the edge sensor nothing on Mate stops it at the table edge — see [Notes](#notes).

Spares: Raspberry Pi 3B, Arduino Nano, ov5647 camera, the classic ESP32 DevKit (browns out with Wi-Fi on), PCA9685, VL6180X.

## Wiring

```
                 ┌─────────────── HUB (perfboard) ───────────────┐
 CanaKit / bank ─┤ PWR IN (XH-2)                  I2C-1 (XH-4) ──├─► OLED
                 │  + 1000µF                                      │
 ESP32-S3 ──────►┤ LINK (XH-4): GND,3V3,SDA,SCL                   │
 ESP32-S3 GPIO ─►┤ SERVO SIG (XH-3): 38,39,40     SV0 SV1 SV2 ───├─► servos
                 │                                MOT-1 (XH-2) ──├─► ULN2003 #1 power
                 │ ESP PWR (XH-2, battery only)   MOT-2 (XH-2) ──├─► ULN2003 #2 power
                 └────────────────────────────────────────────────┘
 ESP32-S3 GPIO 1,2,14,21  ─ 4-wire dupont ──► ULN2003 #1 IN1–IN4  (direct, not via hub)
 ESP32-S3 GPIO 3,45,46,47 ─ 4-wire dupont ──► ULN2003 #2 IN1–IN4  (direct, not via hub)
```

### Pins (Freenove ESP32-S3-WROOM CAM)

| Function | GPIO |
|---|---|
| Wheel 1 (ULN2003 #1) IN1–IN4 | 1, 2, 14, 21 |
| Wheel 2 (ULN2003 #2) IN1–IN4 | 3, 45, 46, 47 |
| I2C SDA, SCL (OLED) | 41, 42 |
| Servos: pan, tilt, flipper | 38, 39, 40 |
| RGB LED (on board, mood light) | 48 |

- **Taken, don't use:** 4–13 and 15–18 (camera), 35–37 (PSRAM), 19/20 (the second USB-C port), 43/44 (USB serial), 0 (BOOT button).
- **Leave the SD card slot empty:** it shares 38–40 with the servos.
- **Wheel 2 is on strapping pins** (3, 45, 46). That's safe because the ULN2003 inputs pull them low at boot, which is what the chip wants. Don't move servos or anything with a pull-up there.
- **Wire ULN2003 IN1→IN1 and so on;** the firmware handles the 28BYJ-48 coil order (IN1, IN3, IN2, IN4).
- **3.3V signals are fine** for the ULN2003 boards, the servos and the OLED.
- **Servo power from the 5V side** (hub SV headers), never from the 3V3 pin. Only the signal wire goes to the ESP32; grounds join at the hub.

### Hub board

- **Top half 5V** (PWR IN, MOT-1/2, servo headers, ESP PWR), **bottom half 3.3V I2C** (LINK, I2C-1). Only GND joins the halves. I2C-2 and I2C-3 (VL6180X, PCA9685) are now unused.
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
| Camera (GC0308) | ~0 (clock stopped) | ~50 mA | ~60 mA |
| 2× 28BYJ-48 | 0 (coils off) | 400 mA | 480 mA |
| Servo (each) | ~10 mA | 150–250 mA | 650–1,000 mA stalled |
| OLED | ~10 mA | ~20 mA | ~25 mA |
| TF-Luna (later) | — | 70 mA | 100 mA |

About 0.15–0.3 A parked, 0.7 A driving, 1.5 A busy, 2–2.5 A if a servo stalls. A 10,000 mAh bank gives ~10–12 h of mixed play (the Pi version managed 4–5 h). A 2 A port is enough.

- **Bench:** ESP32 on USB, CanaKit 5V into PWR IN, **ESP PWR unplugged.**
- **Battery:** USB unplugged, power bank into PWR IN, ESP PWR into the board's 5V and GND pins.
- **Never have USB and ESP PWR plugged in together** — two supplies fight through the board. Unplug ESP PWR to program on battery (or use OTA once it's added).
- **Keep the ESP32 drawing from the same port as the motors,** so the bank doesn't switch the port off while Mate is parked.
- Power banks and the CanaKit have built-in short-circuit protection; zip-tie the cut cable near the joint for strain relief.

## Size (estimate, chassis not designed yet)

About **14 × 11 × 12 cm, 350–450 g**.

| | Estimate | What sets it |
|---|---|---|
| Wheel spacing (centre to centre) | ~100 mm | Stable, precise turns |
| Overall width | ~110 mm | Spacing plus the 8 mm wheels |
| Length | ~130–150 mm | Power bank behind the axle (a ~70 mm-wide bank doesn't fit between the motors) |
| Deck height | ~50–60 mm | Axle at 35 mm, ULN2003 boards on edge |
| Head top | ~110–130 mm | Pan/tilt bracket with the OLED and camera |

The head has to fit under the gantry head while it holds a card over the camera for a peek — check against the Frame's Z travel.

## Notes

- **No edge reflex any more.** Mate can drive off the table if told to. What keeps it on: the firmware's max steps per command (one wheel turn, ~22 cm), and the hub's no-go check against Mate's position from the overhead camera. Until the hub does that, drive with someone watching.
- **The camera jams the Wi-Fi when it runs.** On this board the camera clock and DMA push pings from ~5 ms to 100–300 ms and stall transfers for seconds. The firmware runs the camera clock at 10 MHz and only while capturing or streaming; idle, Wi-Fi is normal.
- **Speed:** 28BYJ-48 tops out around 500–800 half-steps/s; about 4.3 cm/s with 70 mm wheels.
- **Motors on their own core:** stepping runs on core 1; Wi-Fi, the camera and the OLED on core 0, so motion stays smooth.
- **Peek:** the gantry hovers a card over Mate's camera (tilted up), or drops it on a clear flipper paddle above the camera. The GC0308 is only 640×480 — **test whether it can read a card corner at 10–15 cm.** If it can't, swap in an OV2640/OV3660 module (same connector, the firmware detects it), or let the overhead camera handle peeking.
- **Mood light:** the board's RGB LED (GPIO 48). Dim green means the firmware is ready.

## Open

See [`docs/open-questions.md`](../../docs/open-questions.md#blocking-step-1-mate): servo count, chassis, whether the GC0308 can read cards.

# Build log

What happened, when, and what we learned. Newest at the bottom. Times are ET and approximate unless they come from a commit. Settled choices also go in [`decisions.md`](decisions.md).

## Oct 26 (day 1)

- **12:00** Project structure and design docs (commit `2db1535`).

## Oct 28 (day 3)

- **04:12** Mate switches from Pi 3B + Nano to an **ESP32**. First wheels added (commit `dfce644`).
- **06:01** Printed plywood corner joints for the Mate chassis (commit `ed77900`).
- **Wheels:** the 28BYJ-48 bore was too tight at +0.2 and +0.4 mm. The fit test picked **+0.5 mm** (5.5 mm round, 3.5 mm across the flats).
- **ESP32 bring-up, three rounds, all passed** on a classic ESP32 DevKit:
  1. I2C: VL6180X (0x29), SSD1306 OLED (0x3C), PCA9685 (0x40).
  2. Web server at `mate.local`, about 25 ms per request with Wi-Fi power saving off.
  3. Both 28BYJ-48 steppers over Wi-Fi.
- **The OLED is mounted upside down,** so the firmware sets rotation 2.
- **A 3.3V-to-GND short in the I2C/hub wiring** caused brownouts and failed uploads, and damaged one board. That board still runs, but browns out with Wi-Fi on. Lessons:
  - Meter 3.3V ↔ GND before connecting a board.
  - Upload with only USB connected.
  - `arduino-cli upload` doesn't compile, so compile first.
  - A failed upload erases the flash (`invalid header: 0xffffffff`).
- **11:14** ESP32 bring-up test committed (commit `97774d6`).
- **11:15** Nano firmware removed (commit `42c9ae4`).
- **Speed:** the 28BYJ-48 tops out at about 3.7 cm/s with a 60 mm wheel; 10–20 cm/s would feel natural. Wheel enlarged to **70 mm** (about 4.3 cm/s).
- **NEMA 17 + TMC2208 at 5V: the motor never moved,** with two drivers and a healthy ESP32. These driver boards need **at least 5.5V (12V on some boards)** on the motor supply.
  - Bench Vref was set to 0.77 V.
  - The ESP32 code was step/dir on GPIO 16/17, enable on 18.

## Oct 29 (day 4)

- **Middle-ground drivetrain for Mate:** a NEMA 14 or pancake NEMA 17 on **DRV8834** drivers (2.5–10.8V) would run from the 5V battery. Not bought yet; the 28BYJ-48 stays as the fallback.
- **Servos without the PCA9685:** the ESP32's hardware PWM can drive them directly (GPIO 25, 13, 14), with servo power from the battery, not the 3V3 pin. Not changed yet.
- **Suction gripper:** the 12 mm cup arrived. **The peristaltic pump is too weak/slow** for it. New plan:
  - **Pump:** a 12V self-priming diaphragm pump (uxcell or CrocSee, 1.3 L/min), with the cup on the inlet.
  - **Release valve:** a diaphragm pump **can't reverse**, because its check valves set the direction. A normally-closed solenoid valve on a T vents the line to drop the coin. Desktop arms (uArm, Dobot) and vending pickers release the same way.
  - **Valve choice:** the **AIRZOE 2V025-08**, 12V, outlet wire. It's direct-acting, so it works on vacuum. The 4V210 is pilot-operated and won't.
  - **Sequence:** pump on to grip and hold; pump off and the valve on for ~0.3 s to drop.
  - **Switching:** a **Nano** over USB from the Pi, so a 12V mistake can't reach the Pi 5. Two **30N06L logic-level MOSFET** modules (D2 pump, D3 valve), with a 1N4007 across each load. No H-bridge.
- **Frame bring-up** (separate session):
  - The controller is an **Uno + CNC Shield running GRBL** (not RAMPS + Mega), on the Pi at `/dev/ttyACM0`.
  - The Pi is `ash@raspberrypi.local`.
  - X and Z moves confirmed. A reversed CoreXY motor would be fixed with `$3`.
  - The shared enable pin makes the idle motors click at the start and end of a move. That's normal.

## Oct 30 (day 5)

- **~05:00** The Pi 5 LED was solid red, meaning powered but halted. It booted again after reconnecting.
- **Frame motion test:** a script on the Pi moved ±50 mm 10 times. It ran on X, then Z, then X, Y and Z together. All returned to 0,0,0.
  - The script is `/home/ash/shuttle.py` on the Pi. It keeps the serial port open, because reopening it resets the Uno.
- **Frame tuning at 12V:**
  - **Acceleration:** `$120`–`$122` raised from 80 to **500 mm/s²**. The test went from about 52 s to 28 s, clean.
  - **Max speed:** `$110`/`$111` went 7000 → **9000 mm/min (~150 mm/s)**, which ran clean. **12000 skipped steps**, so it went back to 9000. `$112` (Z) stays at 7000.
  - **Why it's capped:** the estimated ceiling at 12V is about 200 mm/s, set by coil inductance and back-EMF. 24V would roughly double it, but would need the 12V pump and valve on a separate supply. Not doing it.
- **GRBL build checked** with `$I`: **GRBL 1.1h (2019-08-30), CoreXY enabled** (`[OPT:VCZ,15,128]`). Variable spindle, homing forces machine zero. So X/Y moves are already mixed for CoreXY by GRBL.
- **Hub server + jog page** (`software/hub/`): FastAPI on the Pi at port 8000, one kept-open GRBL connection, live status over WebSocket. The page builds on the Robo Diner jog page (click a target on the XY table and Z rail) with hold-to-jog, keyboard, live position, zeroing, STOP and a console.
- **Gripper Nano + server** (`software/gripper/`): Nano flashed from the Pi with avrdude (old bootloader, 57600). Separate FastAPI service on port 8001 with pump and valve switches. Both services came back on their own after a power outage.
- **Still open:**
  - Steps/mm (`$100`–`$102` = 50) hasn't been measured.
  - GRBL starts in alarm and needs `$H` or `$X`.

## Oct 31 (day 6)

- **Mate moves to the Freenove ESP32-S3-WROOM CAM** (ESP32-S3 rev v0.2, 8 MB flash, 8 MB PSRAM, CH343 USB at `/dev/cu.usbmodem5C930529801`, MAC `44:b1:76:c7:cd:74`). At first macOS didn't see it at all; a replug fixed it.
- **Dropped from Mate:** the VL6180X edge sensor and the PCA9685. Servos run from the S3's PWM on GPIO 38–40; the OLED is the only I2C device. Pins were then regrouped so each wheel is one 4-pin row on the right header: wheel 1 on 1, 2, 42, 41, wheel 2 on 45, 48, 47, 21, OLED on 20/19 (pin order from Freenove's ESP32-S3-WROOM-1 diagram). The RGB LED on 48 is lost as a mood light. Nothing on Mate stops it at the table edge now; that's the hub's job.
- **The bundled camera is a GC0308** (640×480), not an OV2640. It has no JPEG encoder, so the firmware encodes in software (~370 ms per frame).
- **The running camera wrecked the Wi-Fi:** pings went from ~5 ms to 170–300 ms and a 25 KB snapshot took 1–17 s. Camera off: normal. A 10 MHz clock helped only partly. Fix: the camera clock runs only during a capture or stream. Result: idle ping ~11 ms, snapshot ~0.9 s, MJPEG stream ~2 fps, `/status` still ~20–40 ms while streaming.
- **New firmware** `software/mate/firmware/`: API, wheels, servos, OLED, `GET /capture` (JPEG), `:81/stream` (MJPEG), `POST /camera` (flip). Wheels, servo and capture tested over Wi-Fi with nothing wired yet.
- **Orientation:** camera and OLED are mounted upside down. The camera now starts rotated 180°; the OLED uses rotation 0. The GC0308 driver silently ignores vflip (only hmirror works), so the firmware flips raw frames itself before encoding.
- **No pan or tilt servos;** the flipper is the only servo (GPIO 40). 38 and 39 are free.
- **The OLED shows bitmaps now:** `POST /screen` takes 1024-byte frames (128×64, 1 bit per pixel), up to 64 at once, looped at `X-FPS`. Without a picture it shows a status screen ("not connected" or the IP). The control page has a drawable screen preview and a text box that renders into it; a drawn frame reaches Mate in ~50 ms. The OLED was found on the S3 at 0x3C on the new pins.
- **Gotcha:** the ESP32 `WebServer` doesn't parse query args when it hands over a raw body, so the frame rate is a header (`X-FPS`), not `?fps=`.
- **Control page driving:** an arrow pad (and keyboard arrows) plus an accel box. On the bench, both wheels + turns Mate anticlockwise, so the wheels face opposite ways: ← = +/+, → = −/−, ↑ forward = s1 −, s2 + (checked on the bench). Speed and accel are sliders.
- **Battery resets:** on the power bank Mate dropped off Wi-Fi when the servo moved. The servo is an **MG996R** (not an MG90S): up to ~2.5 A stalled, against the bank's 5V/3A USB-A port. Capacitors (2× 470 µF) and a 1N5819 diode in the ESP32's 5V feed didn't help. A restart-reason readout showed **brownouts**, not the bank cutting out. Fix in firmware: brownout reset off (`esp_brownout_disable()`; the raw register write boot-loops the S3) and Wi-Fi transmit power at 8.5 dBm. After that it stayed up on the bank through servo and wheel moves. Still a risk: a servo held stalled against its end stop, or a low bank.
- **Faces:** `software/mate/faces/` holds ready-made screen animations, drawn in code by `make.py`: blinking, glancing **eyes** (56 frames, 12 fps) a pecking **chicken** (4 frames, 3 fps), and a **portrait**: a cartoon of the person on Mate's camera, smiling, blinking and waving (20 frames, 6 fps). A dithered photo didn't work: the person was backlit by a window and came out as a dark blob at 128×64, so a drawn cartoon reads far better. All played on Mate.
- **API tidy-up:** the full Mate API reference is in `software/mate/README.md` (every endpoint, field, error and a typical agent loop). `/info` keys are now `max_steps`, `max_speed`, `max_accel`. `/screen` takes `X-Repeat` (0 = forever, N = play N times then hold the last frame), and `/status` reports `screen.done`. Tested: play-once finished in ~1 s, play-3× in ~3 s.
- **Faces on the control page:** a grid of 19 animations drawn in the browser (eyes, chicken, happy, wink, love, sleepy, surprised, angry, dizzy, talking, heartbeat, bounce, rain, stars, code, spinner, fireworks, countdown, marquee), with a page preview and a loop/once switch. Tested on Mate: sent in ~130 ms, play-once ends with `done: true`.

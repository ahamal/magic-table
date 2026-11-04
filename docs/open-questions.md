# Open questions

## Blocking step 1 (Esper)
- [x] Controller: Freenove ESP32-S3 CAM (since Oct 31) — no Pi, no Arduino, no PCA9685, no edge sensor
- [x] Wheel diameter: 70 mm. Spacing: ~100 mm suggested, set when the chassis is designed
- [x] Servos in v1: just the flipper; no pan or tilt
- [x] Screen: 0.96" SSD1306 OLED, raw 128×64 bitmaps and preloaded animations over `/screen`
- [x] Speaker: none on Esper; the hub speaks
- [ ] Chassis: still to design/print (estimate ~14 × 11 × 12 cm)
- [x] Power: power bank via cut USB cable, CanaKit on the bench
- [ ] Can the bundled GC0308 (640×480) read a card corner at 10–15 cm? If not: OV2640 module on the same connector, or peek with the overhead camera.
- [x] Freenove ESP32-S3 CAM pins: see [`hardware/esper`](../hardware/esper/README.md#pins-freenove-esp32-s3-wroom-cam) (camera pins confirmed on the board)

## Frame
- [ ] Gantry travel in X, Y, Z
- [x] Controller: Uno + CNC Shield V3 running GRBL 1.1h with CoreXY (not RAMPS)
- [x] Pump: 12V diaphragm pump + NC solenoid vent valve, switched by GRBL through the CNC Shield (peristaltic was too weak; a Nano made a ground loop)
- [ ] Steps/mm: `$100`–`$102` are 50, unmeasured. Send a 100 mm move and measure
- [x] Does the old machine's hand (tilt/grab servos via PCA9685) stay, or is it replaced by the suction head? Replaced.
- [x] Pi 5 hostname: `raspberrypi.local` (user `ash`)
- [x] Camera v2 on the Pi 5: works (`GET /api/capture`). Still needs a mount ~55–60 cm above the table
- [ ] Emergency stop button wired to GRBL reset / feed hold

## Hackathon
- [ ] Application accepted?
- [ ] Do the official rules allow building on pre-existing work (the salvaged gantry parts, Xenote)?
- [ ] Per-place prize split

## Design
- [ ] Esper's role is settled as the AI's body — confirm courier / recon are out of scope
- [ ] Live video for humans in addition to `capture` snapshots? (Proposed: snapshots as the interface, optional live view for debugging only)
- [ ] Does `actuate` exist in v1, or only once a powered extra appears?

# Open questions

## Blocking step 1 (Mate)
- [x] Controller: Freenove ESP32-S3 CAM (since Oct 31) — no Pi, no Arduino, no PCA9685, no edge sensor
- [x] Wheel diameter: 70 mm. Spacing: ~100 mm suggested, set when the chassis is designed
- [ ] How many servos in v1: pan, pan + tilt, + flipper?
- [x] Screen: 0.96" SSD1306 OLED, raw 128×64 images; the control page ships named faces
- [x] Speaker: none on Mate; the hub speaks
- [ ] Chassis: still to design/print (estimate ~14 × 11 × 12 cm)
- [x] Power: power bank via cut USB cable, CanaKit on the bench
- [ ] Can the bundled GC0308 (640×480) read a card corner at 10–15 cm? If not: OV2640 module on the same connector, or peek with the overhead camera.
- [x] Freenove ESP32-S3 CAM pins: see [`hardware/mate`](../hardware/mate/README.md#pins-freenove-esp32-s3-wroom-cam) (camera pins confirmed on the board)

## Frame
- [ ] Gantry travel in X, Y, Z
- [x] Controller: Uno + CNC Shield V3 running GRBL 1.1h with CoreXY (not RAMPS)
- [x] Pump: 12V diaphragm pump + NC solenoid vent valve, switched by a Nano (peristaltic was too weak)
- [ ] Steps/mm: `$100`–`$102` are 50, unmeasured. Send a 100 mm move and measure
- [ ] Does the Robo Diner hand (tilt/grab servos via PCA9685) stay, or is it replaced by the suction head?
- [x] Pi 5 hostname: `raspberrypi.local` (user `ash`)
- [ ] 22→15-pin camera adapter cable for the Pi 5 — on hand?
- [ ] Emergency stop button wired to GRBL reset / feed hold

## Hackathon
- [ ] Application accepted?
- [ ] Do the official rules allow building on pre-existing work (Robo Diner gantry, Xenote)?
- [ ] Per-place prize split

## Design
- [ ] Mate's role is settled as the AI's body — confirm courier / recon are out of scope
- [ ] Live video for humans in addition to `capture` snapshots? (Proposed: snapshots as the interface, optional live view for debugging only)
- [ ] Does `actuate` exist in v1, or only once a powered extra appears?

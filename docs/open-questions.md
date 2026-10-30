# Open questions

## Blocking step 1 (Mate)
- [x] Controller: ESP32 (DevKit now, Freenove ESP32-S3 CAM next) — no Pi, no Arduino
- [x] Wheel diameter: 60 mm. Spacing: ~100 mm suggested, set when the chassis is designed
- [ ] How many servos in v1: pan, pan + tilt, + flipper?
- [x] Screen: 0.96" SSD1306 OLED, raw 128×64 images; the control page ships named faces
- [x] Speaker: none on Mate; the hub speaks
- [ ] Chassis: still to design/print (estimate ~14 × 11 × 12 cm)
- [x] Power: power bank via cut USB cable, CanaKit on the bench
- [ ] Can the OV2640 read a card corner at 10–15 cm? (Test as soon as the S3 board arrives.)
- [ ] Freenove ESP32-S3 CAM pinout: confirm the free pins before wiring

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

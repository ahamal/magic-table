# Open questions

## Blocking step 1 (Mate)
- [ ] Which Arduino on Mate: Nano, Uno, other?
- [ ] Wheel diameter and wheel spacing (track width) — useful for sanity checks, even though the agent learns calibration
- [ ] How many servos in v1: pan, pan + tilt, + flipper?
- [ ] The screen: is it the 3.5" SPI touchscreen already configured on the Pi 3 (ads7846 overlay), or a different tiny screen?
- [ ] Screen interface: named faces (`neutral`, `thinking`…) or raw image (the AI designs its own faces)?
- [ ] Speaker: present now, or later?
- [ ] Is Mate's chassis built, or still to design/print?
- [ ] Mate's power: 3A two-port bank on hand? (Mate currently reports under-voltage.)

## Frame
- [ ] Gantry travel in X, Y, Z
- [ ] Arduino board under the RAMPS (RAMPS is a Mega shield) and GRBL build
- [ ] Pump: DC or stepper? Current draw? (Decides H-bridge vs extra GRBL axis.)
- [ ] Does the Robo Diner hand (tilt/grab servos via PCA9685) stay, or is it replaced by the suction head?
- [ ] Pi 5 hostname
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

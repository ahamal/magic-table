# Shared hardware

Things both robots (and the table itself) rely on.

## Markers

ArUco markers, kept discreet so players don't notice them.

| Marker | Where | Purpose | Visible to players? |
|---|---|---|---|
| Head marker | On the Frame's gantry head | Calibration (pixel → gantry mm). Removed after calibrating. | Only during calibration |
| Corner markers | Top of the frame corners, 2–3 cm | Safety net if the camera moves | No — faces up, out of sight from seats |
| Mate marker | Mate's roof | Mate's position, heading, and the gantry no-go zone | Yes — designed as part of Mate's look |

Options for blending in: tone-on-tone colours, a pixel-art border, a logo badge. Test detection under the demo lighting.

## Network

- Mate's ESP32 is **2.4 GHz only**. Use WPA2 or WPA2/WPA3 mixed.
- Demo: a phone hotspot on 2.4 GHz WPA2 is the easiest. Reserve IPs where possible; `.local` names can occasionally fail on busy networks.

## Power

- The Pi 5 needs a real supply: **5V 3A** with a short, thick cable. Computer USB ports and phone chargers cause under-voltage and throttling.
- Shut down before unplugging (`sudo poweroff`) to avoid corrupting SD cards.

## Printed parts

To design: suction cup mount (sprung), card flipper (passive), peek window / Mate paddle, card and chip trays, stone dispenser, Mate chassis and pan/tilt mount, camera mount for the Frame.

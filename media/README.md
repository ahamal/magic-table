# Media

Photos, clips, screenshots and the demo video. Drop files in the folder named below, with the suggested
name if you can, then tick the box (or ask Claude to check them, trim them, and link them from the README).

**Size:** GitHub refuses files over 100 MB and warns above 50 MB. Put the full demo video on YouTube
(unlisted is fine) and its link here and in the README; keep files in the repo under ~25 MB.
**Raw footage** goes in `raw/`, which git ignores.

## video/ — the demo

- [ ] `demo.mp4` or a YouTube link: the 3-minute video ([shooting script](../docs/desk-duo-shooting-script.md)). **Required for the submission.**
- [ ] `demo-thumbnail.jpg`: one frame for the README and the submission page (both robots and cards in frame)

## clips/ — short loops for the README (5–15 s each, no sound needed, MP4 or GIF)

- [ ] `pick-place.mp4`: the cup comes down on a card, lifts it, carries it, puts it down
- [ ] `stack-chips.mp4`: a chip picked and stacked on another
- [ ] `esper-turn.mp4`: a card put on Esper's top, Esper turns, the crane picks it back up square (the "sum of parts" shot)
- [ ] `esper-flip.mp4`: Esper flips a card face up
- [ ] `esper-peek.mp4`: Esper lifts a card's corner, plus a frame of what her camera saw
- [ ] `esper-gesture.mp4`: Esper waves or celebrates
- [ ] `talk-live.mp4`: the talk page on a phone, words appearing as someone speaks, Muse answering out loud
- [ ] `find-chip.mp4` or 4 stills: a chip as the camera sees it, SAM's outline, the crane picking it (the 0:51 shot in the script)

## photos/ — the hardware (JPG, landscape, good light)

- [ ] `table-overview.jpg`: the whole table: frame, board with its four markers, Esper, cameras
- [ ] `crane-head.jpg`: close-up of the head: suction cup, its spring mount, the head marker
- [ ] `gripper-air.jpg`: pump, vent valve and the T, with the tubes
- [ ] `electronics.jpg`: Uno + CNC Shield, the two MOSFET modules on CoolEn and SpnDir, the 12V supply
- [ ] `pi-hub.jpg`: the Pi 5 with both camera ribbons and the USB to the Uno
- [ ] `cameras.jpg`: where cam 1 (front, angled) and cam 0 (low, side) are mounted
- [ ] `esper-front.jpg`: Esper's face (OLED), camera and flipper arm
- [ ] `esper-top.jpg`: her top marker and the arrow toward her face
- [ ] `esper-inside.jpg` (optional): ESP32-S3 board, steppers, wiring
- [ ] `salvaged-parts.jpg` (optional): the old machine's parts, or the frame before the rebuild

## screenshots/ — the pages (PNG)

- [ ] `home.png`: the hub's home page (`/`)
- [ ] `scene-3d.png`: the 3D scene with cards, Esper and the head (`/scene`)
- [ ] `vision.png`: a find with SAM's outlines and Muse's answers (`/vision`)
- [ ] `talk-phone.png`: the talk page on a phone, mid-conversation (`/talk`)
- [ ] `jog.png`: the jog page with both camera views (`/jog`)
- [ ] `agent-terminal.png`: the live agent's terminal while it plays

## Also missing from the repo (not media, but only you have them)

- [ ] The suction cup's spring mount: its STL or CAD file, for `hardware/frame/gripper/`

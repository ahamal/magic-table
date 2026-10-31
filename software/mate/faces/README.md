# Mate faces

Ready-made animations for Mate's 128×64 OLED. Each is a `.bin` file of frames in the [`/screen` format](../README.md#post-screen) (1024 bytes per frame), with a `.png` preview.

| Face | Frames | Send at | What it does | Preview |
|---|---|---|---|---|
| `eyes` | 56 | 12 fps | Two rounded eyes: rest, blink, look left, look right, glance up, double blink (~5 s loop) | ![eyes](eyes.png) |
| `chicken` | 4 | 3 fps | A chicken pecking at seeds | ![chicken](chicken.png) |
| `portrait` | 20 | 6 fps | A cartoon of a person in glasses and a hoodie, drawn from Mate's camera: smiles, blinks, waves | ![portrait](portrait.png) |

The control page at `http://mate.local/` also has a **Faces** grid with 19 animations (including these two) you can tap to play, loop or once; those are drawn in the page script.

## Show one on Mate

```bash
curl -X POST -H 'Content-Type: application/octet-stream' -H 'X-FPS: 12' \
  --data-binary @software/mate/faces/eyes.bin http://mate.local/screen
```

Use the face's frame rate in `X-FPS`. Add `-H 'X-Repeat: 1'` to play it once and stop on the last frame (`0`, the default, loops forever). To go back to the status screen, send an empty body (or press **Status screen** on the control page).

## Make or change one

All faces are drawn in code in [`make.py`](make.py) with Pillow, so they're easy to tweak and rebuild:

```bash
pip install pillow
python3 software/mate/faces/make.py
```

To add a face: write a function that returns a list of 128×64 one-bit Pillow images (64 frames at most), and add it to `FACES` with its frame rate and which frames to show in the preview.

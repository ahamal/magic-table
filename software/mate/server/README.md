# Mate server (Pi 3)

A small Python web server that exposes Mate's API (spec in [`../README.md`](../README.md)) and serves the control page from [`../ui`](../ui).

## Responsibilities

- Translate HTTP calls into firmware serial commands (`/step` → `M`, `/servo` → `V`, `/stop` → `X`, `/status` → `Q`).
- Camera capture (`libcamera-still` / Picamera2), rotated 180° to match the current mount.
- Screen output (faces or images).
- Speech, if a speaker is fitted.
- One move at a time: reject a second `/step` while busy (`409 BUSY`); `/stop` always goes through.
- Report power problems (`vcgencmd get_throttled`) in `/status`.

## Stack (proposed)

- Python 3.9 (bullseye default), **FastAPI** + Uvicorn
- `pyserial` for the Arduino
- Picamera2 or `libcamera-still` for capture
- Runs as a systemd service so it starts on boot

## Notes

- Serial port: Arduino shows up as `/dev/ttyUSB0` (Nano clones, CH340) or `/dev/ttyACM0` (Uno). Prefer a stable `/dev/serial/by-id/...` path.
- Opening the serial port resets most Arduinos — wait ~2 s before the first command.

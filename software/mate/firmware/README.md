# Mate firmware (ESP32-S3)

[`firmware.ino`](firmware.ino) runs Mate on the Freenove ESP32-S3-WROOM CAM: Wi-Fi API, both wheels, three servos straight from the ESP32's PWM, the OLED face, the camera and the control page at `http://mate.local/`. Endpoints and how to get pictures: [`../README.md`](../README.md#api). Pins: [`hardware/mate`](../../../hardware/mate/README.md#pins-freenove-esp32-s3-wroom-cam).

## Build

Copy `secrets.example.h` to `secrets.h` (git-ignored) and fill in the Wi-Fi name and password. The ESP32 needs a 2.4 GHz network.

```bash
arduino-cli lib install AccelStepper "Adafruit SSD1306" "Adafruit GFX Library"
arduino-cli compile --fqbn esp32:esp32:esp32s3:PSRAM=opi,FlashSize=8M,PartitionScheme=default_8MB software/mate/firmware
arduino-cli upload --fqbn esp32:esp32:esp32s3:PSRAM=opi,FlashSize=8M,PartitionScheme=default_8MB -p /dev/cu.usbmodem5C930529801 software/mate/firmware
```

Use the USB-C port marked for serial (the CH343, `/dev/cu.usbmodem…`). The camera and PSRAM need `PSRAM=opi`; without it the camera fails to start.

Serial (115200) prints the IP and `READY oled=… cam=…` once it's up.

## How it's put together

- **Cores:** `loop()` on core 1 only runs the steppers. The API server, I2C and OLED run in `netTask` on core 0; the video stream is a second server (port 81) with its own task.
- **Camera:** tries hardware JPEG first (OV2640/OV3660); the bundled GC0308 can't, so it falls back to RGB565 at 640×480 and encodes with `frame2jpg`.
- **Camera sleeps between pictures.** On this board a running camera wrecks Wi-Fi (pings 100–300 ms, multi-second stalls even at 10 MHz). The camera clock (LEDC timer 3) is paused unless a capture or stream is in progress, and a snapshot is sent after the camera goes back to sleep. Measured: idle ping ~11 ms, snapshot ~0.9 s, stream ~2 fps.
- **IPv6 is on** only so `mate.local` resolves at once on a Mac; without it every lookup waits 5 s for an IPv6 answer.
- **Servos:** LEDC channels 0–2 at 50 Hz, 14-bit, attached after the camera so they share timer 0 and stay off the camera's timer 3.

The earlier Arduino Nano firmware (USB serial protocol) was removed; it's in git history if ever needed. The classic-DevKit bench test is in [`../tests/web_i2c/`](../tests/web_i2c/).

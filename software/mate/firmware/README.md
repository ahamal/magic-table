# Mate firmware (ESP32)

Mate's real firmware will live here: Wi-Fi API, raw steppers, servos, face, camera and the edge reflex.

Until it's written, the working ESP32 code is the bench test in [`../tests/web_i2c/`](../tests/web_i2c/): I2C devices, web server and both steppers. See [`../tests/README.md`](../tests/README.md) for its endpoints and pins.

The earlier Arduino Nano firmware (USB serial protocol) was removed; it's in git history before this change if ever needed.

# Mate bring-up tests (ESP32)

> **History.** This is the classic-DevKit test, with the VL6180X and PCA9685 that Mate no longer uses. Mate now runs [`../firmware`](../firmware) on the ESP32-S3.

[`web_i2c/`](web_i2c/) is the bench test for the ESP32 Mate: I2C devices, web server and both steppers. It passed all three rounds:

1. **I2C:** VL6180X (0x29), SSD1306 OLED (0x3C, mounted upside down), PCA9685 (0x40).
2. **Web server:** `http://mate.local/`, about 25 ms per request with Wi-Fi power saving off.
3. **Steppers:** both wheels, together and opposite, stop mid-move, over Wi-Fi.

## Endpoints

| | |
|---|---|
| `GET /` | Control page: live distance, latency, wheel buttons, STOP, OLED text, servo sliders |
| `GET /status` | `range_mm`, `busy`, `p1`/`p2`, last move result, servo angles, RSSI |
| `GET /info` | Firmware, limits, which devices were found |
| `GET /scan` | I2C addresses on the bus |
| `POST /step?s1=&s2=[&speed=&accel=&edge=1]` | Start a move (half-steps). Returns at once; poll `/status` for the result |
| `POST /stop` | Stop now, coils off |
| `POST /screen?text=` | Text on the OLED |
| `POST /servo?id=&angle=` | PCA9685 channel 0–2, 0–180° |

The edge reflex is off unless `edge=1`, since on the bench the sensor sees nothing.

## Pins (classic ESP32 DevKit)

| | GPIO |
|---|---|
| ULN2003 #1 IN1–IN4 | 16, 17, 18, 19 |
| ULN2003 #2 IN1–IN4 | 32, 33, 26, 27 |
| I2C SDA / SCL | 21 / 22 |
| Servos | PCA9685 channels 0, 1, 2 |

## Build

Copy `web_i2c/secrets.example.h` to `web_i2c/secrets.h` (git-ignored) and fill in the Wi-Fi name and password. The ESP32 needs a 2.4 GHz network.

```bash
arduino-cli lib install AccelStepper VL6180X "Adafruit SSD1306" "Adafruit GFX Library" "Adafruit PWM Servo Driver Library"
arduino-cli compile --fqbn esp32:esp32:esp32 software/mate/tests/web_i2c
arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/cu.usbserial-XXXX software/mate/tests/web_i2c
```

## Lessons from bring-up

- A **3.3V-to-GND short** in the I2C wiring caused brownouts, failed USB uploads and one damaged board (it still runs, but browns out with Wi-Fi on). Check 3.3V ↔ GND and 5V ↔ 3.3V with a meter before connecting a board.
- A failed USB upload erases the flash, so the board then reports `invalid header: 0xffffffff` until it's reflashed.
- Wi-Fi transmit power is set to 8.5 dBm to keep current spikes down.

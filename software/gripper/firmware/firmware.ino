// Gripper driver: Arduino Nano, USB serial from the Pi 5.
// Switches the 12V pump and vent valve through two low-side MOSFETs.
// The Pi never touches the 12V side.
//
// Commands (one character, newline optional), 115200 baud:
//   P / p   pump on / off
//   V / v   valve on / off   (the valve turns itself off after VALVE_MAX_MS)
//   G       grip: valve off, pump on
//   D       drop: pump off, valve on for DROP_MS, then off
//   S       stop: both off
//   ?       report state
// Every command answers with the state line:  pump=1 valve=0

const int PUMP_PIN = 2;
const int VALVE_PIN = 3;
const unsigned long DROP_MS = 300;
const unsigned long VALVE_MAX_MS = 10000;  // keep the coil from cooking

bool pump = false;
bool valve = false;
unsigned long valveSince = 0;
unsigned long valveFor = 0;  // 0 = until told, capped at VALVE_MAX_MS

void setPump(bool on) {
  pump = on;
  digitalWrite(PUMP_PIN, on ? HIGH : LOW);
}

void setValve(bool on, unsigned long forMs = 0) {
  valve = on;
  valveSince = millis();
  valveFor = forMs;
  digitalWrite(VALVE_PIN, on ? HIGH : LOW);
}

void report() {
  Serial.print("pump=");
  Serial.print(pump ? 1 : 0);
  Serial.print(" valve=");
  Serial.println(valve ? 1 : 0);
}

void setup() {
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(VALVE_PIN, OUTPUT);
  setPump(false);
  setValve(false);
  Serial.begin(115200);
  Serial.println("gripper ready");
  report();
}

void loop() {
  if (valve) {
    unsigned long limit = valveFor ? valveFor : VALVE_MAX_MS;
    if (millis() - valveSince >= limit) {
      setValve(false);
      report();
    }
  }

  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 'P': setPump(true); break;
    case 'p': setPump(false); break;
    case 'V': setValve(true); break;
    case 'v': setValve(false); break;
    case 'G': setValve(false); setPump(true); break;
    case 'D': setPump(false); setValve(true, DROP_MS); break;
    case 'S': setPump(false); setValve(false); break;
    case '?': break;
    default: return;  // ignore newlines and noise
  }
  report();
}

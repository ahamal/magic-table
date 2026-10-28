// Round 2 + 3 test: I2C devices, web server and steppers on the ESP32.
// VL6180X distance, the OLED, PCA9685 servos and both wheels, all over Wi-Fi.
// Open http://mate.local/ (or the IP shown on the OLED).
//
// Cores: loop() on core 1 only runs the steppers, so Wi-Fi can't make them
// stutter. The web server, I2C and OLED run in netTask on core 0.

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <Wire.h>
#include <AccelStepper.h>
#include <VL6180X.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_PWMServoDriver.h>
#include "secrets.h"  // WIFI_SSID, WIFI_PASS (copy secrets.example.h)

const char *HOSTNAME = "mate";
const uint8_t SDA_PIN = 21, SCL_PIN = 22;
const uint8_t NUM_SERVOS = 3;
const uint16_t SERVO_MIN_US = 500, SERVO_MAX_US = 2500;
const uint16_t OLED_PERIOD_MS = 150;

// ---- Steppers: 28BYJ-48 + ULN2003, HALF4WIRE needs IN1, IN3, IN2, IN4 ----
AccelStepper s1(AccelStepper::HALF4WIRE, 16, 18, 17, 19);
AccelStepper s2(AccelStepper::HALF4WIRE, 32, 26, 33, 27);

// Same limits as the Nano firmware.
const long MAX_STEPS = 4096;
const long MAX_SPEED = 800;
const long MAX_ACCEL = 1000;
const long DEFAULT_SPEED = 500;
const long DEFAULT_ACCEL = 400;

// Edge reflex: off by default here, since on the bench the wheels are in the air
// and the sensor sees nothing. Turn on per move with edge=1.
const int EDGE_MM = 50;
const uint8_t EDGE_CONFIRM = 2;
const long EDGE_BACKOFF = 200;

VL6180X range;
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
Adafruit_PWMServoDriver pca(0x40);
WebServer server(80);

bool hasRange = false, hasOled = false, hasPca = false;
volatile int rangeMm = -1;  // -1 = nothing in range
volatile uint8_t edgeHits = 0;
int servoAngle[NUM_SERVOS] = {-1, -1, -1};
String screenText = "";
unsigned long lastOled = 0;

// ---- Motion state, shared between cores ----
enum State { IDLE, MOVING, BACKING_OFF };
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
struct MoveCmd { long d1, d2, speed, accel; bool edge; };
volatile bool movePending = false, stopPending = false;
MoveCmd pendingMove;
volatile State state = IDLE;
volatile long pos1 = 0, pos2 = 0;
// Result of the last move.
volatile long lastD1 = 0, lastD2 = 0, lastMs = 0;
const char *volatile lastResult = "none";

bool present(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

// ---------------------------------------------------------------- motion (core 1)

long start1, start2, cmd1, cmd2;
bool edgeOn;
unsigned long moveStartMs;

void startMove(long d1, long d2, long speed, long accel) {
  long longest = max(labs(d1), labs(d2));
  float r1 = (float)labs(d1) / longest;
  float r2 = (float)labs(d2) / longest;
  s1.setMaxSpeed(max(speed * r1, 1.0f));
  s1.setAcceleration(max(accel * r1, 1.0f));
  s2.setMaxSpeed(max(speed * r2, 1.0f));
  s2.setAcceleration(max(accel * r2, 1.0f));
  s1.enableOutputs();
  s2.enableOutputs();
  s1.move(d1);
  s2.move(d2);
}

void hardStop() {
  s1.setCurrentPosition(s1.currentPosition());
  s2.setCurrentPosition(s2.currentPosition());
}

void finish(const char *result) {
  s1.disableOutputs();
  s2.disableOutputs();
  lastD1 = s1.currentPosition() - start1;
  lastD2 = s2.currentPosition() - start2;
  lastMs = millis() - moveStartMs;
  lastResult = result;
  state = IDLE;
}

long sign(long v) { return (v > 0) - (v < 0); }

void triggerEdge() {
  hardStop();
  long longest = max(labs(cmd1), labs(cmd2));
  state = BACKING_OFF;
  startMove(-sign(cmd1) * (EDGE_BACKOFF * labs(cmd1) / longest),
            -sign(cmd2) * (EDGE_BACKOFF * labs(cmd2) / longest), DEFAULT_SPEED, MAX_ACCEL);
}

// ---------------------------------------------------------------- devices (core 0)

void pollRange() {
  if (!hasRange) return;
  uint8_t status = range.readReg(VL6180X::RESULT__INTERRUPT_STATUS_GPIO);
  if ((status & 0x07) != 0x04) return;
  uint8_t mm = range.readReg(VL6180X::RESULT__RANGE_VAL);
  range.writeReg(VL6180X::SYSTEM__INTERRUPT_CLEAR, 0x01);
  rangeMm = mm == 255 ? -1 : mm;
  if (rangeMm < 0 || rangeMm >= EDGE_MM) {
    if (edgeHits < 255) edgeHits++;
  } else {
    edgeHits = 0;
  }
}

void setServo(uint8_t id, int angle) {
  uint16_t us = map(angle, 0, 180, SERVO_MIN_US, SERVO_MAX_US);
  pca.writeMicroseconds(id, us);
  servoAngle[id] = angle;
}

void drawOled() {
  if (!hasOled) return;
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  if (WiFi.status() == WL_CONNECTED) oled.print(WiFi.localIP()); else oled.print("WiFi connecting...");
  if (state != IDLE) oled.print(" MOVE");
  oled.setTextSize(3);
  oled.setCursor(0, 14);
  if (!hasRange) oled.print("no VL");
  else if (rangeMm < 0) oled.print("--");
  else { oled.print(rangeMm); oled.setTextSize(1); oled.print(" mm"); }
  oled.setTextSize(1);
  oled.setCursor(0, 44);
  oled.print(screenText.substring(0, 42));  // two lines of text from /screen
  oled.display();
}

// ---------------------------------------------------------------- web (core 0)

const char PAGE[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta name=viewport content="width=device-width,initial-scale=1"><title>Mate test</title>
<style>
body{font-family:system-ui,sans-serif;max-width:420px;margin:16px auto;padding:0 16px;background:#111;color:#eee}
h1{font-size:18px;color:#aaa;font-weight:500}
h2{font-size:14px;color:#aaa;font-weight:500;margin:22px 0 6px}
#mm{font-size:64px;font-weight:700}
.row{margin:10px 0}
label{display:block;color:#aaa;font-size:13px;margin-bottom:4px}
input[type=range]{width:100%}
input[type=text],input[type=number]{padding:6px;background:#222;color:#eee;border:1px solid #444}
input[type=number]{width:70px}
button{padding:8px 12px;margin:2px}
#stop{background:#c33;color:#fff;border:0;font-weight:700;width:100%;padding:12px}
small,#res{color:#888}
</style></head><body>
<h1>Mate &middot; test</h1>
<div id=mm>--</div>
<small>distance (mm) &middot; latency <span id=lat>-</span> ms avg / <span id=max>-</span> max</small>

<h2>Wheels (half-steps, 4096 = one turn)</h2>
<div class=row>
 s1 <input id=s1 type=number value=1024> s2 <input id=s2 type=number value=1024>
 speed <input id=sp type=number value=500>
</div>
<div class=row>
 <button onclick="go()">Go</button>
 <button onclick="preset(1024,1024)">both +</button>
 <button onclick="preset(-1024,-1024)">both &minus;</button>
 <button onclick="preset(1024,-1024)">opposite</button>
 <button onclick="preset(1024,0)">s1 only</button>
 <button onclick="preset(0,1024)">s2 only</button>
 <label><input id=edge type=checkbox> edge reflex (only with Mate on the table)</label>
</div>
<button id=stop onclick="fetch('/stop',{method:'POST'})">STOP</button>
<div class=row id=res>-</div>

<h2>OLED text</h2>
<div class=row><input id=t type=text maxlength=42> <button onclick="send()">Show</button></div>
<h2>Servos</h2>
<div id=servos></div>
<script>
const $=id=>document.getElementById(id);
['pan','tilt','flipper'].forEach((n,i)=>{$('servos').insertAdjacentHTML('beforeend',
 `<div class=row><label>servo ${i} (${n}): <span id=v${i}>-</span>&deg;</label>
  <input type=range min=0 max=180 value=90 oninput="servo(${i},this.value)"></div>`)});
let pending={};
function servo(i,a){$('v'+i).textContent=a;
 if(pending[i])return; pending[i]=1;
 fetch(`/servo?id=${i}&angle=${a}`,{method:'POST'}).finally(()=>pending[i]=0)}
function send(){fetch('/screen?text='+encodeURIComponent($('t').value),{method:'POST'})}
function preset(a,b){$('s1').value=a;$('s2').value=b;go()}
async function go(){
 const q=`s1=${$('s1').value}&s2=${$('s2').value}&speed=${$('sp').value}&edge=${$('edge').checked?1:0}`;
 const r=await (await fetch('/step?'+q,{method:'POST'})).json();
 if(r.error)$('res').textContent='error: '+r.error}
const lats=[];
async function poll(){
 const t0=performance.now();
 try{const r=await (await fetch('/status')).json();
  lats.push(performance.now()-t0); if(lats.length>50)lats.shift();
  $('mm').textContent=r.range_mm===null?'--':r.range_mm;
  $('lat').textContent=(lats.reduce((a,b)=>a+b)/lats.length).toFixed(0);
  $('max').textContent=Math.max(...lats).toFixed(0);
  const l=r.last;
  $('res').textContent=r.busy?`moving… p1=${r.p1} p2=${r.p2}`
   :`last: ${l.result} d1=${l.d1} d2=${l.d2} in ${l.ms} ms`;
 }catch(e){$('mm').textContent='offline'}
 setTimeout(poll,100)}
poll();
</script></body></html>)HTML";

void sendJson(const String &body, int code = 200) { server.send(code, "application/json", body); }

void handleStatus() {
  String j = "{\"range_mm\":";
  j += rangeMm < 0 ? String("null") : String(rangeMm);
  j += ",\"busy\":" + String(state != IDLE ? "true" : "false");
  j += ",\"p1\":" + String(pos1) + ",\"p2\":" + String(pos2);
  j += ",\"last\":{\"result\":\"" + String(lastResult) + "\",\"d1\":" + String(lastD1) +
       ",\"d2\":" + String(lastD2) + ",\"ms\":" + String(lastMs) + "}";
  j += ",\"servos\":[";
  for (uint8_t i = 0; i < NUM_SERVOS; i++) { if (i) j += ','; j += servoAngle[i]; }
  j += "],\"uptime_ms\":" + String(millis());
  j += ",\"rssi\":" + String(WiFi.RSSI()) + "}";
  sendJson(j);
}

void handleInfo() {
  String j = "{\"fw\":\"web-test\",\"ip\":\"" + WiFi.localIP().toString() + "\"";
  j += ",\"maxsteps\":" + String(MAX_STEPS) + ",\"maxspeed\":" + String(MAX_SPEED) +
       ",\"maxaccel\":" + String(MAX_ACCEL);
  j += ",\"range\":" + String(hasRange ? "true" : "false");
  j += ",\"oled\":" + String(hasOled ? "true" : "false");
  j += ",\"pca9685\":" + String(hasPca ? "true" : "false") + "}";
  sendJson(j);
}

void handleScan() {
  String j = "{\"i2c\":[";
  bool first = true;
  for (uint8_t a = 1; a < 127; a++) {
    if (!present(a)) continue;
    if (!first) j += ',';
    first = false;
    j += "\"0x" + String(a, HEX) + "\"";
  }
  sendJson(j + "]}");
}

// Starts a move and returns at once; poll /status for the result.
void handleStep() {
  if (!server.hasArg("s1") || !server.hasArg("s2")) return sendJson("{\"error\":\"need s1 and s2\"}", 400);
  long d1 = server.arg("s1").toInt(), d2 = server.arg("s2").toInt();
  long speed = server.hasArg("speed") ? server.arg("speed").toInt() : DEFAULT_SPEED;
  long accel = server.hasArg("accel") ? server.arg("accel").toInt() : DEFAULT_ACCEL;
  if (labs(d1) > MAX_STEPS || labs(d2) > MAX_STEPS || speed < 1 || speed > MAX_SPEED ||
      accel < 1 || accel > MAX_ACCEL) {
    return sendJson("{\"error\":\"limit\"}", 400);
  }
  if (state != IDLE || movePending) return sendJson("{\"error\":\"busy\"}", 409);
  portENTER_CRITICAL(&mux);
  pendingMove = {d1, d2, speed, accel, server.arg("edge") == "1"};
  movePending = true;
  portEXIT_CRITICAL(&mux);
  sendJson("{\"ok\":true}");
}

void handleStop() {
  stopPending = true;
  sendJson("{\"ok\":true}");
}

void handleScreen() {
  screenText = server.arg("text");
  sendJson("{\"ok\":true}");
}

void handleServo() {
  if (!hasPca) return sendJson("{\"error\":\"no pca9685\"}", 503);
  long id = server.arg("id").toInt(), angle = server.arg("angle").toInt();
  if (!server.hasArg("id") || !server.hasArg("angle") || id < 0 || id >= NUM_SERVOS || angle < 0 || angle > 180) {
    return sendJson("{\"error\":\"range\"}", 400);
  }
  setServo(id, angle);
  sendJson("{\"ok\":true}");
}

void netTask(void *) {
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);

  hasOled = present(0x3C) && oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (hasOled) {
    oled.setTextColor(SSD1306_WHITE);
    oled.setRotation(2);  // mounted upside down
  }

  hasRange = present(0x29);
  if (hasRange) {
    range.init();
    range.configureDefault();
    range.setTimeout(50);
    range.stopContinuous();
    delay(50);
    range.startRangeContinuous(20);
  }

  hasPca = present(0x40);
  if (hasPca) {
    pca.begin();
    pca.setOscillatorFrequency(25000000);
    pca.setPWMFreq(50);
  }
  drawOled();

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.setSleep(false);  // power save adds 100 ms+ latency spikes
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);  // smaller current spikes; full power browned out the 3.3V rail
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print('.');
    pollRange();
    drawOled();
  }
  Serial.print(" ip=");
  Serial.println(WiFi.localIP());
  MDNS.begin(HOSTNAME);
  MDNS.addService("http", "tcp", 80);

  server.on("/", HTTP_GET, [] { server.send_P(200, "text/html", PAGE); });
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/info", HTTP_GET, handleInfo);
  server.on("/scan", HTTP_GET, handleScan);
  server.on("/step", HTTP_POST, handleStep);
  server.on("/stop", HTTP_POST, handleStop);
  server.on("/screen", HTTP_POST, handleScreen);
  server.on("/servo", HTTP_POST, handleServo);
  server.begin();

  Serial.printf("READY range=%d oled=%d pca=%d\n", hasRange, hasOled, hasPca);

  for (;;) {
    server.handleClient();
    pollRange();
    unsigned long now = millis();
    if (now - lastOled >= OLED_PERIOD_MS) {
      lastOled = now;
      drawOled();
    }
    delay(1);
  }
}

// ---------------------------------------------------------------- main

void setup() {
  Serial.begin(115200);
  s1.disableOutputs();
  s2.disableOutputs();
  xTaskCreatePinnedToCore(netTask, "net", 8192, nullptr, 1, nullptr, 0);
}

// Core 1: steppers only.
void loop() {
  if (stopPending) {
    stopPending = false;
    if (state != IDLE) {
      hardStop();
      finish("stopped");
    }
    s1.disableOutputs();
    s2.disableOutputs();
  }

  if (movePending && state == IDLE) {
    portENTER_CRITICAL(&mux);
    MoveCmd m = pendingMove;
    movePending = false;
    portEXIT_CRITICAL(&mux);
    start1 = s1.currentPosition();
    start2 = s2.currentPosition();
    cmd1 = m.d1;
    cmd2 = m.d2;
    edgeOn = m.edge && hasRange;
    moveStartMs = millis();
    if (m.d1 == 0 && m.d2 == 0) {
      finish("ok");
    } else {
      state = MOVING;
      startMove(m.d1, m.d2, m.speed, m.accel);
    }
  }

  if (state != IDLE) {
    s1.run();
    s2.run();
    pos1 = s1.currentPosition();
    pos2 = s2.currentPosition();
    if (state == MOVING && edgeOn && edgeHits >= EDGE_CONFIRM) triggerEdge();
    if (state != IDLE && s1.distanceToGo() == 0 && s2.distanceToGo() == 0) {
      finish(state == MOVING ? "ok" : "edge");
    }
  }
}

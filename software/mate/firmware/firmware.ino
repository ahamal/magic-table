// Mate firmware for the Freenove ESP32-S3-WROOM CAM.
// Both wheels, the flipper servo, the OLED face and the camera, all over Wi-Fi.
// Open http://mate.local/ (or the IP shown on the OLED).
//
// Cores: loop() on core 1 only runs the steppers, so Wi-Fi and the camera can't make them
// stutter. The API server, I2C and OLED run in netTask on core 0; the video stream is a
// separate server on port 81 with its own task.

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <Wire.h>
#include <AccelStepper.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "esp_camera.h"
#include "img_converters.h"
#include "esp_http_server.h"
#include "esp_system.h"
#include "esp_private/brownout.h"
#include "secrets.h"  // WIFI_SSID, WIFI_PASS (copy secrets.example.h)

const char *HOSTNAME = "mate";
const uint16_t STATUS_PERIOD_MS = 500;  // how often the status screen redraws

// ---- Pins, all on the right-hand header. The camera takes 4–18 (bar 14); PSRAM takes 35–37 ----
const uint8_t SDA_PIN = 20, SCL_PIN = 19;  // the second USB port's pins; that port is unused
const uint8_t SERVO_PIN = 40;  // flipper (shared with the unused SD slot)
const uint16_t SERVO_MIN_US = 500, SERVO_MAX_US = 2500;
const uint8_t SERVO_BITS = 14;  // 20 ms period / 16384 ≈ 1.2 µs per count
const uint16_t MAX_SERVO_SPEED = 600;  // °/s; /servo without speed jumps at full speed
const uint16_t SERVO_TICK_MS = 10;

// ---- Steppers: 28BYJ-48 + ULN2003, HALF4WIRE needs IN1, IN3, IN2, IN4 ----
// Each wheel is four header pins in a row: wheel 1 on 1, 2, 42, 41 and wheel 2 on 45, 48, 47, 21.
// 45 is a strapping pin that must be low at boot, which the ULN2003 input guarantees.
// 48 also drives the on-board RGB LED, so it flickers while wheel 2 turns.
AccelStepper s1(AccelStepper::HALF4WIRE, 1, 42, 2, 41);
AccelStepper s2(AccelStepper::HALF4WIRE, 45, 47, 48, 21);

const long MAX_STEPS = 4096;
const long MAX_SPEED = 800;
const long MAX_ACCEL = 1000;
const long DEFAULT_SPEED = 500;
const long DEFAULT_ACCEL = 400;

Adafruit_SSD1306 oled(128, 64, &Wire, -1);
WebServer server(80);
httpd_handle_t streamServer = nullptr;

// One camera frame as JPEG, from grabJpeg(); free with freeJpeg().
struct Jpeg { uint8_t *buf; size_t len; camera_fb_t *fb; };

// Why the chip last restarted, and how many restarts since power was first applied
// (RTC memory keeps the count through every reset except a full power loss).
RTC_NOINIT_ATTR uint32_t bootCount;
const char *resetReason = "?";

const char *reasonName(esp_reset_reason_t r) {
  switch (r) {
    case ESP_RST_POWERON: return "power_on";      // power was gone completely
    case ESP_RST_BROWNOUT: return "brownout";     // supply sagged too low
    case ESP_RST_EXT: return "reset_pin";         // EN pin pulled low
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "crash";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT: return "watchdog";
    case ESP_RST_USB: return "usb";
    default: return "other";
  }
}

bool hasOled = false, hasCam = false;
const char *camName = "none";
int servoAngle = -1;       // target, -1 = never set
float servoNow = -1;       // where the pulse points now (moves toward the target at servoSpeed)
uint16_t servoSpeed = 0;   // °/s, 0 = jump straight there
unsigned long servoTick = 0;

// ---- Screen: 128×64, 1 bit per pixel, rows top to bottom, 16 bytes per row, MSB = leftmost ----
// POST /screen with N frames back to back plays them X-Repeat times (0 = forever), then holds
// the last frame; no frames = the status screen.
const size_t FRAME_BYTES = 128 * 64 / 8;
const uint16_t MAX_FRAMES = 64;
const uint8_t MAX_FPS = 30;
const uint16_t MAX_REPEAT = 1000;
uint8_t *frames = nullptr, *upload = nullptr;  // PSRAM, MAX_FRAMES each; swapped when an upload completes
size_t uploadLen = 0;
uint16_t frameCount = 0, frameIdx = 0;
uint8_t fps = 10;
uint16_t repeatTotal = 0, loopsDone = 0;  // repeatTotal 0 = loop forever
bool screenDone = true;                   // finished playing (always true for a still or the status screen)
bool screenDirty = true, shownOnline = false;
unsigned long lastOled = 0;

// ---- Motion state, shared between cores ----
enum State { IDLE, MOVING };
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
struct MoveCmd { long d1, d2, speed, accel; };
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

long start1, start2;
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

// ---------------------------------------------------------------- camera

// Freenove ESP32-S3-WROOM CAM pinout. The bundled GC0308 (640×480) has no JPEG encoder,
// so frames come out as RGB565 and are JPEG-encoded in software; an OV2640/OV3660 on the
// same connector is used in JPEG mode directly.
// The camera is mounted upside down: both flips = rotate 180°. JPEG sensors flip in hardware;
// the GC0308's driver ignores vflip, so raw frames are flipped in software before encoding.
bool flipV = true, flipH = true;

void applyFlips() {
  sensor_t *s = esp_camera_sensor_get();
  bool hw = s->pixformat == PIXFORMAT_JPEG;
  s->set_vflip(s, hw && flipV);
  s->set_hmirror(s, hw && flipH);
}

void flipFrame(camera_fb_t *fb) {
  uint16_t *p = (uint16_t *)fb->buf;
  size_t w = fb->width, h = fb->height;
  if (flipV && flipH) {
    std::reverse(p, p + w * h);
  } else if (flipH) {
    for (size_t y = 0; y < h; y++) std::reverse(p + y * w, p + (y + 1) * w);
  } else if (flipV) {
    for (size_t y = 0; y < h / 2; y++) std::swap_ranges(p + y * w, p + (y + 1) * w, p + (h - 1 - y) * w);
  }
}

bool initCamera() {
  camera_config_t c = {};
  c.pin_pwdn = -1; c.pin_reset = -1; c.pin_xclk = 15;
  c.pin_sccb_sda = 4; c.pin_sccb_scl = 5;
  c.pin_d7 = 16; c.pin_d6 = 17; c.pin_d5 = 18; c.pin_d4 = 12;
  c.pin_d3 = 10; c.pin_d2 = 8; c.pin_d1 = 9; c.pin_d0 = 11;
  c.pin_vsync = 6; c.pin_href = 7; c.pin_pclk = 13;
  c.xclk_freq_hz = 10000000;  // 20 MHz jams this board's Wi-Fi
  c.ledc_timer = LEDC_TIMER_3;  // keep clear of the servos, which take timer 0
  c.ledc_channel = LEDC_CHANNEL_7;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_UXGA;
  c.jpeg_quality = 12;
  c.fb_count = 1;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  if (esp_camera_init(&c) != ESP_OK) {
    // No hardware JPEG: retry as raw RGB565 at the sensor's largest size.
    esp_camera_deinit();
    c.pixel_format = PIXFORMAT_RGB565;
    c.frame_size = FRAMESIZE_VGA;
    if (esp_camera_init(&c) != ESP_OK) return false;
  }
  sensor_t *s = esp_camera_sensor_get();
  camera_sensor_info_t *info = esp_camera_sensor_get_info(&s->id);
  if (info) camName = info->name;
  if (s->pixformat == PIXFORMAT_JPEG) s->set_framesize(s, FRAMESIZE_VGA);
  applyFlips();
  ledc_timer_pause(LEDC_LOW_SPEED_MODE, LEDC_TIMER_3);  // asleep until someone wants a picture
  return true;
}

// The running camera (its clock and DMA) slows Wi-Fi to a crawl on this board, even at 10 MHz:
// pings go from ~5 ms to 100–300 ms. So the camera clock only runs while someone is capturing
// or streaming. Snapshots are encoded with the camera awake and sent with it asleep.
portMUX_TYPE camMux = portMUX_INITIALIZER_UNLOCKED;
SemaphoreHandle_t camLock;  // one grab at a time
int camUsers = 0;
bool camStale = false;      // the frame buffer still holds a picture from before the last sleep

void camWake() {
  portENTER_CRITICAL(&camMux);
  if (camUsers++ == 0) {
    ledc_timer_resume(LEDC_LOW_SPEED_MODE, LEDC_TIMER_3);
    camStale = true;
  }
  portEXIT_CRITICAL(&camMux);
}

void camSleep() {
  portENTER_CRITICAL(&camMux);
  if (--camUsers == 0) ledc_timer_pause(LEDC_LOW_SPEED_MODE, LEDC_TIMER_3);
  portEXIT_CRITICAL(&camMux);
}

const uint8_t JPEG_QUALITY = 80;  // software encoder, 0–100

// Call between camWake() and camSleep().
bool grabJpeg(Jpeg &j) {
  xSemaphoreTake(camLock, portMAX_DELAY);
  // Drop the old picture and any half frame cut off by the last sleep.
  for (int i = 0; camStale && i < 2; i++) {
    camera_fb_t *old = esp_camera_fb_get();
    if (old) esp_camera_fb_return(old);
  }
  camStale = false;
  camera_fb_t *fb = esp_camera_fb_get();
  bool ok = fb != nullptr;
  if (ok && fb->format == PIXFORMAT_JPEG) {
    j = {fb->buf, fb->len, fb};
  } else if (ok) {
    flipFrame(fb);
    ok = frame2jpg(fb, JPEG_QUALITY, &j.buf, &j.len);
    esp_camera_fb_return(fb);
    j.fb = nullptr;
  }
  xSemaphoreGive(camLock);
  return ok;
}

void freeJpeg(Jpeg &j) {
  if (j.fb) esp_camera_fb_return(j.fb); else free(j.buf);
}

// MJPEG stream on port 81, so a watching page never blocks the API on port 80.
#define BOUNDARY "mateframe"
esp_err_t streamHandler(httpd_req_t *req) {
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=" BOUNDARY);
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  char head[80];
  esp_err_t e = ESP_OK;
  camWake();
  while (e == ESP_OK) {  // until the viewer goes away
    Jpeg j;
    if (!grabJpeg(j)) { e = ESP_FAIL; break; }
    int n = snprintf(head, sizeof head, "\r\n--" BOUNDARY "\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", j.len);
    e = httpd_resp_send_chunk(req, head, n);
    if (e == ESP_OK) e = httpd_resp_send_chunk(req, (const char *)j.buf, j.len);
    freeJpeg(j);
  }
  camSleep();
  return e;
}

void startStreamServer() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 81;
  cfg.ctrl_port = 32769;
  cfg.core_id = 0;
  cfg.stack_size = 8192;  // the software JPEG encoder needs more than the default 4 KB
  httpd_uri_t uri = {.uri = "/stream", .method = HTTP_GET, .handler = streamHandler, .user_ctx = nullptr};
  if (httpd_start(&streamServer, &cfg) == ESP_OK) httpd_register_uri_handler(streamServer, &uri);
}

// ---------------------------------------------------------------- devices (core 0)

void servoPulse(float angle) {
  uint32_t us = SERVO_MIN_US + angle * (SERVO_MAX_US - SERVO_MIN_US) / 180;
  ledcWrite(SERVO_PIN, us * ((1 << SERVO_BITS) - 1) / 20000);
}

// speed 0 = jump. The first move after boot always jumps, since where the servo is isn't known.
void setServo(int angle, uint16_t speed) {
  servoAngle = angle;
  servoSpeed = servoNow < 0 ? 0 : speed;
  if (servoSpeed == 0) {
    servoNow = angle;
    servoPulse(servoNow);
  }
}

// Called often from netTask: steps the pulse toward the target at servoSpeed.
void updateServo() {
  if (servoAngle < 0 || servoNow == servoAngle) return;
  unsigned long now = millis();
  if (now - servoTick < SERVO_TICK_MS) return;
  servoTick = now;
  float step = servoSpeed * SERVO_TICK_MS / 1000.0f;
  servoNow += constrain(servoAngle - servoNow, -step, step);
  if (fabsf(servoAngle - servoNow) < 0.01f) servoNow = servoAngle;
  servoPulse(servoNow);
}

// Shown while offline, or online with nothing sent yet.
void drawStatus(bool online) {
  oled.clearDisplay();
  oled.setTextSize(2);
  oled.setCursor(0, 0);
  oled.print("Mate");
  oled.setTextSize(1);
  oled.setCursor(0, 24);
  if (online) {
    oled.print("mate.local");
    oled.setCursor(0, 36);
    oled.print(WiFi.localIP());
    oled.setCursor(0, 52);
    oled.print("cam ");
    oled.print(camName);
  } else {
    oled.print("not connected");
    oled.setCursor(0, 36);
    oled.print("WiFi: ");
    oled.print(WIFI_SSID);
    oled.setCursor(0, 52);
    oled.print("retrying...");
  }
  oled.display();
}

void drawFrame(const uint8_t *f) {
  oled.clearDisplay();
  oled.drawBitmap(0, 0, f, 128, 64, SSD1306_WHITE);
  oled.display();
}

// Called often from netTask. Redraws only when something changed or the next frame is due.
void updateOled() {
  if (!hasOled) return;
  unsigned long now = millis();
  bool online = WiFi.status() == WL_CONNECTED;
  if (online != shownOnline) {
    shownOnline = online;
    screenDirty = true;
  }
  if (!online || frameCount == 0) {
    if (screenDirty || now - lastOled >= STATUS_PERIOD_MS) {
      drawStatus(online);
      lastOled = now;
      screenDirty = false;
    }
    return;
  }
  bool due = frameCount > 1 && !screenDone && now - lastOled >= 1000 / fps;
  if (!screenDirty && !due) return;
  if (!screenDirty) {
    if (frameIdx + 1 == frameCount && repeatTotal && ++loopsDone >= repeatTotal) {
      screenDone = true;  // played X-Repeat times: stay on the last frame
      return;
    }
    frameIdx = (frameIdx + 1) % frameCount;
  }
  drawFrame(frames + frameIdx * FRAME_BYTES);
  lastOled = now;
  screenDirty = false;
}

// ---------------------------------------------------------------- web (core 0)

const char PAGE[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta name=viewport content="width=device-width,initial-scale=1"><title>Mate</title>
<style>
body{font-family:system-ui,sans-serif;max-width:420px;margin:16px auto;padding:0 16px;background:#111;color:#eee}
h1{font-size:18px;color:#aaa;font-weight:500}
h2{font-size:14px;color:#aaa;font-weight:500;margin:22px 0 6px}
#cam{width:100%;aspect-ratio:4/3;background:#222;display:block}
#scr,#fx{width:100%;aspect-ratio:2/1;image-rendering:pixelated;background:#000;border:1px solid #444;
 display:block;touch-action:none;cursor:crosshair}
.row{margin:10px 0}
label{color:#aaa;font-size:13px}
input[type=range]{width:100%}
input[type=text],input[type=number]{padding:6px;background:#222;color:#eee;border:1px solid #444}
input[type=text]{width:100%;box-sizing:border-box}
input[type=number]{width:70px}
button{padding:8px 12px;margin:2px}
button.on{background:#ddd;color:#111}
#stop{background:#c33;color:#fff;border:0;font-weight:700;width:100%;padding:12px}
.pad{display:grid;grid-template-columns:repeat(3,64px);grid-template-rows:repeat(3,48px);gap:4px;margin:10px 0}
.pad button{margin:0;font-size:20px}
small,#res{color:#888}
</style></head><body>
<h1>Mate</h1>
<img id=cam alt="camera">
<div class=row>
 <button onclick="live()">Live</button>
 <button onclick="snap()">Snapshot</button>
 <a id=dl href="/capture" download="mate.jpg"><button>Download</button></a>
 <small>latency <span id=lat>-</span> ms</small>
</div>

<h2>Screen (128&times;64) &mdash; click or drag to draw</h2>
<canvas id=scr width=128 height=64></canvas>
<div class=row><input id=t type=text placeholder="type to put text on the screen"></div>
<div class=row>
 <button id=pen class=on onclick="tool(1)">Draw</button>
 <button id=era onclick="tool(-1)">Erase</button>
 <button onclick="clearAll()">Clear</button>
 <button onclick="sendScreen()">Send</button>
 <button onclick="statusScreen()">Status screen</button>
 <label><input id=auto type=checkbox checked> send as I draw</label>
</div>
<small id=scrmsg>-</small>

<h2>Faces &mdash; tap one to play it on Mate</h2>
<canvas id=fx width=128 height=64></canvas>
<div class=row id=faces></div>
<div class=row>
 <label><input type=radio name=rep value=0 checked> loop</label>
 <label><input type=radio name=rep value=1> once</label>
 <small id=fxmsg>-</small>
</div>

<h2>Wheels (half-steps, 4096 = one turn)</h2>
<div class=row>
 <label>speed: <span id=spv>500</span> half-steps/s</label>
 <input id=sp type=range min=50 max=800 step=10 value=500 oninput="$('spv').textContent=this.value">
 <label>accel: <span id=acv>400</span> half-steps/s&sup2;</label>
 <input id=ac type=range min=50 max=1000 step=10 value=400 oninput="$('acv').textContent=this.value">
</div>
<div class=row>steps per arrow <input id=n type=number value=1024 min=1 max=4096> <small>or use the arrow keys</small></div>
<div class=pad>
 <span></span><button onclick="drive('up')" title="forward">&uarr;</button><span></span>
 <button onclick="drive('left')" title="turn left">&larr;</button>
 <button onclick="fetch('/stop',{method:'POST'})" title="stop">&#9632;</button>
 <button onclick="drive('right')" title="turn right">&rarr;</button>
 <span></span><button onclick="drive('down')" title="back">&darr;</button><span></span>
</div>
<div class=row>
 raw: s1 <input id=s1 type=number value=1024> s2 <input id=s2 type=number value=1024>
 <button onclick="go()">Go</button>
</div>
<button id=stop onclick="fetch('/stop',{method:'POST'})">STOP</button>
<div class=row id=res>-</div>

<h2>Flipper servo: <span id=sv>-</span>&deg;</h2>
<input type=range min=0 max=180 value=90 oninput="servo(this.value)">
<label>speed: <span id=ssv>full</span></label>
<input id=ss type=range min=0 max=600 step=10 value=0 oninput="$('ssv').textContent=this.value>0?this.value+' °/s':'full'">
<script>
const $=id=>document.getElementById(id);
const streamUrl=`http://${location.hostname}:81/stream`;
function live(){$('cam').src=streamUrl}
function snap(){$('cam').src='/capture?t='+Date.now()}

// ---- screen: text layer + a drawing layer on top (1 = drawn, -1 = erased, 0 = show text) ----
const W=128,H=64,cv=$('scr'),cx=cv.getContext('2d');
let text=new Uint8Array(W*H),ink=new Int8Array(W*H),pen=1,down=false,last=null,timer=null;
function px(i){return ink[i]?ink[i]>0:text[i]}
function render(){
 const img=cx.createImageData(W,H);
 for(let i=0;i<W*H;i++){const v=px(i)?255:0;img.data.set([v,v,v,255],i*4)}
 cx.putImageData(img,0,0)}
function renderText(s){
 text.fill(0); if(!s.trim())return;
 const o=document.createElement('canvas');o.width=W;o.height=H;const g=o.getContext('2d');
 let size=48,lines;
 for(;size>=8;size--){                       // biggest font where the wrapped text fits
  g.font=`bold ${size}px system-ui,sans-serif`;lines=[];let cur='';
  for(const w of s.split(/\s+/)){const t=cur?cur+' '+w:w;
   if(g.measureText(t).width<=W-2||!cur)cur=t;else{lines.push(cur);cur=w}}
  lines.push(cur);
  if(lines.length*size*1.05<=H&&lines.every(l=>g.measureText(l).width<=W))break}
 g.fillStyle='#fff';g.textAlign='center';g.textBaseline='middle';
 const lh=size*1.05,y0=H/2-(lines.length-1)*lh/2;
 lines.forEach((l,i)=>g.fillText(l,W/2,y0+i*lh));
 const d=g.getImageData(0,0,W,H).data;
 for(let i=0;i<W*H;i++)text[i]=d[i*4]>110?1:0}
function plot(x,y){if(x>=0&&x<W&&y>=0&&y<H)ink[y*W+x]=pen}
function line(a,b){let dx=Math.abs(b.x-a.x),dy=-Math.abs(b.y-a.y),sx=a.x<b.x?1:-1,sy=a.y<b.y?1:-1,e=dx+dy,x=a.x,y=a.y;
 for(;;){plot(x,y);if(x==b.x&&y==b.y)break;const e2=2*e;if(e2>=dy){e+=dy;x+=sx}if(e2<=dx){e+=dx;y+=sy}}}
function at(ev){const r=cv.getBoundingClientRect();
 return{x:Math.floor((ev.clientX-r.left)*W/r.width),y:Math.floor((ev.clientY-r.top)*H/r.height)}}
cv.onpointerdown=ev=>{down=true;cv.setPointerCapture(ev.pointerId);last=at(ev);plot(last.x,last.y);render()};
cv.onpointermove=ev=>{if(!down)return;const p=at(ev);line(last,p);last=p;render()};
cv.onpointerup=cv.onpointercancel=()=>{if(!down)return;down=false;autoSend()};
$('t').oninput=()=>{renderText($('t').value);render();autoSend()};
function tool(t){pen=t;$('pen').className=t>0?'on':'';$('era').className=t<0?'on':''}
function clearAll(){ink.fill(0);text.fill(0);$('t').value='';render();autoSend()}
function autoSend(){if(!$('auto').checked)return;clearTimeout(timer);timer=setTimeout(sendScreen,120)}
function bytes(){const b=new Uint8Array(W*H/8);
 for(let i=0;i<W*H;i++)if(px(i))b[i>>3]|=0x80>>(i&7);return b}
async function postScreen(body){
 const t0=performance.now();
 try{const r=await (await fetch('/screen',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body})).json();
  $('scrmsg').textContent=r.error?'error: '+r.error:(r.frames?`sent in ${(performance.now()-t0).toFixed(0)} ms`:'showing status screen')}
 catch(e){$('scrmsg').textContent='offline'}}
function sendScreen(){postScreen(bytes())}
function statusScreen(){postScreen(new Uint8Array(0))}
render();

// ---- faces: little animations drawn here and sent to Mate as frames ----
const TAU=Math.PI*2,fc=document.createElement('canvas');fc.width=W;fc.height=H;
const g=fc.getContext('2d');
function fill(s){g.fillStyle=g.strokeStyle=s}
function rr(x,y,w,h,r){g.beginPath();g.roundRect(x,y,w,h,r);g.fill()}
function dot(x,y,r){g.beginPath();g.arc(x,y,r,0,TAU);g.fill()}
function ring(x,y,r,w){g.lineWidth=w;g.beginPath();g.arc(x,y,r,0,TAU);g.stroke()}
function heart(x,y,s){g.beginPath();g.moveTo(x,y+s*.9);
 g.bezierCurveTo(x-s*1.5,y-s*.1,x-s*.7,y-s*1.1,x,y-s*.35);
 g.bezierCurveTo(x+s*.7,y-s*1.1,x+s*1.5,y-s*.1,x,y+s*.9);g.fill()}
function txt(s,x,y,px){g.font=`bold ${px}px system-ui,sans-serif`;g.textAlign='center';g.textBaseline='middle';g.fillText(s,x,y)}
function rnd(seed){return()=>(seed=(seed*16807)%2147483647)/2147483647}   // repeatable random
// the standard pair of eyes: dx/dy look direction, o = how open (0–1)
function eyes(dx=0,dy=0,o=1,shine=true){
 const EW=34,EH=40,GAP=18,h=Math.max(3,EH*o);
 for(const s of[-1,1]){const x0=64+dx+s*(GAP/2+EW/2)-EW/2,y0=32+dy-h/2;
  fill('#fff');rr(x0,y0,EW,h,Math.min(10,h/2));
  if(shine&&o>.5){fill('#000');dot(x0+EW/2+dx/2+6,y0+8,4)}}
 fill('#fff')}
const EYES=(()=>{const f=[],R=(k,n)=>{for(let j=0;j<n;j++)f.push(k)},S=a=>a.forEach(k=>f.push(k));
 R([0,0,1],6);S([.6,.2,.05,.2,.6].map(o=>[0,0,o]));R([0,0,1],4);
 S([-6,-12,-16].map(d=>[d,0,1]));R([-16,0,1],5);S([-10,-4].map(d=>[d,0,1]));R([0,0,1],3);
 S([6,12,16].map(d=>[d,0,1]));R([16,0,1],5);S([10,4].map(d=>[d,0,1]));R([0,0,1],3);
 R([0,-6,1],3);f.push([0,-3,1]);R([0,0,1],2);S([.6,.2,.05,.2,.6,1,.2,.05,.6].map(o=>[0,0,o]));return f})();
function chicken(peck){
 g.lineWidth=1;g.beginPath();g.moveTo(0,60.5);g.lineTo(128,60.5);g.stroke();
 for(const x of[20,26,100,108,113])g.fillRect(x,58,1,1);
 g.beginPath();g.moveTo(38,26);g.lineTo(28,14);g.lineTo(34,30);g.fill();
 g.beginPath();g.moveTo(38,30);g.lineTo(24,22);g.lineTo(34,34);g.fill();
 g.lineWidth=2;g.beginPath();g.ellipse(56,37,22,15,0,0,TAU);g.stroke();
 g.beginPath();g.ellipse(55,38,11,8,0,200/57.3,340/57.3);g.stroke();
 for(const x of[52,62]){g.fillRect(x-1,51,2,8);g.fillRect(x-3,59,8,1)}
 const[hx,hy]=peck?[90,50]:[80,16];
 g.lineWidth=3;g.beginPath();peck?(g.moveTo(74,38),g.lineTo(86,48)):(g.moveTo(72,30),g.lineTo(78,20));g.stroke();
 fill('#000');dot(hx,hy,7);fill('#fff');ring(hx,hy,6.5,2);
 for(const[cx,cy]of[[hx-4,hy-7],[hx,hy-9],[hx+4,hy-7]])dot(cx,cy,2.5);
 g.beginPath();g.moveTo(hx+6,hy-2);g.lineTo(hx+13,hy+1);g.lineTo(hx+6,hy+3);g.fill();
 dot(hx+6,hy+6,2.5);g.fillRect(hx+1,hy-3,3,3)}
function spiral(x,y,rot){g.lineWidth=2;g.beginPath();
 for(let t=0;t<3*TAU;t+=.2){const r=1+t*1.1;g.lineTo(x+r*Math.cos(t+rot),y+r*Math.sin(t+rot))}g.stroke()}

// name: [frames, fps, draw(i, n)]
const FACES={
 eyes:[EYES.length,12,i=>eyes(...EYES[i])],
 chicken:[4,3,i=>chicken(i==2)],
 happy:[16,12,i=>{const b=Math.sin(i/16*TAU)*3;g.lineWidth=6;
  for(const s of[-1,1]){g.beginPath();g.arc(64+s*26,40+b,14,Math.PI,0);g.stroke()}}],
 wink:[24,12,i=>{eyes();if(i>=8&&i<18){fill('#000');g.fillRect(0,0,64,64);fill('#fff');
  g.lineWidth=5;g.beginPath();g.arc(38,40,13,Math.PI,0);g.stroke()}}],
 love:[16,10,i=>{const s=14+3*Math.sin(i/16*TAU);heart(38,32,s);heart(90,32,s)}],
 sleepy:[32,8,i=>{const o=.22+.06*Math.sin(i/32*TAU);eyes(0,6,o,false);
  for(let k=0;k<3;k++){const t=((i/32)+k/3)%1;txt('z',104+t*14,40-t*36,8+t*10)}}],
 surprised:[16,12,i=>{const r=14+(i<4?i:4)*.8;
  for(const s of[-1,1]){ring(64+s*28,26,r,3);dot(64+s*28,26,4)}ring(64,54,5+(i<4?i/2:2),2)}],
 angry:[12,12,i=>{const sh=i%2?2:-2;eyes(sh,4,.8,false);fill('#000');
  g.beginPath();g.moveTo(14+sh,12);g.lineTo(64+sh,36);g.lineTo(64+sh,0);g.lineTo(14+sh,0);g.fill();   // slanted brows cut in
  g.beginPath();g.moveTo(114+sh,12);g.lineTo(64+sh,36);g.lineTo(64+sh,0);g.lineTo(114+sh,0);g.fill();fill('#fff')}],
 dizzy:[16,12,i=>{const a=i/16*TAU;spiral(38,32,a);spiral(90,32,-a)}],
 talking:[16,10,i=>{eyes(0,-10,.55,true);const m=[2,6,10,5,2,8,12,6,3,1,7,11,4,2,9,3][i];
  g.beginPath();g.ellipse(64,52,10,m/2+1,0,0,TAU);g.fill()}],
 heartbeat:[32,16,i=>{const P=[0,0,0,0,0,-3,0,0,6,-22,14,0,0,0,-5,-6,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
  g.lineWidth=2;g.beginPath();for(let x=0;x<=128;x+=4){const k=((x/4)+i)%32;g.lineTo(x,40+P[k])}g.stroke();
  const b=(i%32)>8&&(i%32)<13;heart(116,12,b?8:6)}],
 bounce:[24,20,i=>{const t=i/24,y=54-46*Math.abs(Math.sin(t*Math.PI)),sq=y>50?1.4:1;
  g.lineWidth=1;g.beginPath();g.moveTo(0,62.5);g.lineTo(128,62.5);g.stroke();
  g.beginPath();g.ellipse(64,y+(sq>1?2:0),8*sq,8/sq,0,0,TAU);g.fill()}],
 rain:[16,12,i=>{const r=rnd(7);for(let k=0;k<40;k++){const x=r()*128,y=(r()*64+i*4)%64;g.fillRect(x,y,1,4)}}],
 stars:[32,16,i=>{const r=rnd(11);for(let k=0;k<45;k++){const a=r()*TAU,d=((r()*64)+i*2)%64,
  s=d>40?2:1;g.fillRect(64+Math.cos(a)*d*1.6,32+Math.sin(a)*d,s,s)}}],
 code:[16,12,i=>{const r=rnd(3);   // falling 0s and 1s, drawn as tiny pixel shapes
  for(let c=0;c<16;c++){const off=r()*64;for(let j=0;j<5;j++){const y=Math.floor((off+j*13+i*4)%64),x=c*8+2;
   if(r()<.5)g.fillRect(x+1,y,1,6);else{g.fillRect(x,y,3,1);g.fillRect(x,y+5,3,1);g.fillRect(x,y,1,6);g.fillRect(x+2,y,1,6)}}}}],
 spinner:[8,10,i=>{for(let k=0;k<8;k++){const a=k/8*TAU,on=(k+8-i)%8;dot(64+Math.cos(a)*20,32+Math.sin(a)*20,on==0?5:on<3?3:1.5)}}],
 fireworks:[24,12,i=>{const r=rnd(5),cx=40+r()*48,cy=20+r()*16;
  if(i<6){g.fillRect(cx,64-(64-cy)*i/6,2,4);return}
  const t=(i-6)/18;for(let k=0;k<20;k++){const a=k/20*TAU,d=4+t*30;if(t<.85||k%2)dot(cx+Math.cos(a)*d,cy+Math.sin(a)*d+t*t*12,t<.6?1.5:1)}}],
 countdown:[4,1,i=>txt(['3','2','1','GO!'][i],64,34,i<3?52:34)],
 marquee:[64,20,(i,n)=>{const s=$('t').value.trim()||'Hello from Mate!';g.font='bold 30px system-ui,sans-serif';
  const w=g.measureText(s).width;g.textAlign='left';g.textBaseline='middle';g.fillText(s,128-(w+128)*i/(n-1),34)}],
};
function build(name){const[n,fps,draw]=FACES[name],out=[];
 for(let i=0;i<n;i++){g.clearRect(0,0,W,H);fill('#000');g.fillRect(0,0,W,H);fill('#fff');draw(i,n);
  const d=g.getImageData(0,0,W,H).data,b=new Uint8Array(W*H/8);
  for(let p=0;p<W*H;p++)if(d[p*4]>127)b[p>>3]|=0x80>>(p&7);out.push(b)}
 return{frames:out,fps}}
// preview on the page canvas
const fx=$('fx'),fxc=fx.getContext('2d');let fxTimer=null;
function show(b){const img=fxc.createImageData(W,H);
 for(let p=0;p<W*H;p++){const v=b[p>>3]&(0x80>>(p&7))?255:0;img.data.set([v,v,v,255],p*4)}fxc.putImageData(img,0,0)}
function preview(frames,fps,once){clearInterval(fxTimer);let i=0;show(frames[0]);if(frames.length<2)return;
 fxTimer=setInterval(()=>{if(++i>=frames.length){if(once){clearInterval(fxTimer);return}i=0}show(frames[i])},1000/fps)}
async function play(name){
 const{frames,fps}=build(name),once=document.querySelector('input[name=rep]:checked').value=='1';
 preview(frames,fps,once);
 const body=new Uint8Array(frames.length*1024);frames.forEach((f,k)=>body.set(f,k*1024));
 const t0=performance.now();
 try{const r=await (await fetch('/screen',{method:'POST',headers:{'Content-Type':'application/octet-stream',
   'X-FPS':String(fps),'X-Repeat':once?'1':'0'},body})).json();
  $('fxmsg').textContent=r.error?'error: '+r.error:`${name}: ${r.frames} frames at ${r.fps} fps, sent in ${(performance.now()-t0).toFixed(0)} ms`}
 catch(e){$('fxmsg').textContent='offline'}}
for(const name of Object.keys(FACES))$('faces').insertAdjacentHTML('beforeend',`<button onclick="play('${name}')">${name}</button>`);
show(build('eyes').frames[0]);

let busyServo=0;
function servo(a){$('sv').textContent=a;
 if(busyServo)return;busyServo=1;
 fetch(`/servo?angle=${a}&speed=${$('ss').value}`,{method:'POST'}).finally(()=>busyServo=0)}
// The wheels face opposite ways: same sign on both turns Mate, opposite signs drive it.
// both + turns anticlockwise, and s1 −, s2 + drives forward (checked on the bench).
const DIRS={up:[-1,1],down:[1,-1],left:[1,1],right:[-1,-1]};
function drive(d){const n=+$('n').value,[a,b]=DIRS[d];move(a*n,b*n)}
addEventListener('keydown',e=>{
 if(e.target.tagName=='INPUT')return;
 const d={ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right'}[e.key];
 if(d){e.preventDefault();if(!e.repeat)drive(d)}
 else if(e.key==' '||e.key=='Escape'){e.preventDefault();fetch('/stop',{method:'POST'})}});
function go(){move($('s1').value,$('s2').value)}
async function move(a,b){
 const q=`s1=${a}&s2=${b}&speed=${$('sp').value}&accel=${$('ac').value}`;
 const r=await (await fetch('/step?'+q,{method:'POST'})).json();
 if(r.error)$('res').textContent='error: '+r.error}
const lats=[];
async function poll(){
 const t0=performance.now();
 try{const r=await (await fetch('/status')).json();
  lats.push(performance.now()-t0); if(lats.length>50)lats.shift();
  $('lat').textContent=(lats.reduce((a,b)=>a+b)/lats.length).toFixed(0);
  const l=r.last;
  $('res').textContent=r.busy?`moving… p1=${r.p1} p2=${r.p2}`
   :`last: ${l.result} d1=${l.d1} d2=${l.d2} in ${l.ms} ms`;
 }catch(e){$('res').textContent='offline'}
 setTimeout(poll,200)}
snap();poll();
</script></body></html>)HTML";

void sendJson(const String &body, int code = 200) { server.send(code, "application/json", body); }

void handleStatus() {
  String j = "{\"busy\":" + String(state != IDLE ? "true" : "false");
  j += ",\"p1\":" + String(pos1) + ",\"p2\":" + String(pos2);
  j += ",\"last\":{\"result\":\"" + String(lastResult) + "\",\"d1\":" + String(lastD1) +
       ",\"d2\":" + String(lastD2) + ",\"ms\":" + String(lastMs) + "}";
  j += ",\"servo\":" + String(servoAngle) + ",\"servo_now\":" + String((int)roundf(servoNow)) +
       ",\"servo_moving\":" + String(servoAngle >= 0 && servoNow != servoAngle ? "true" : "false");
  j += ",\"screen\":{\"frames\":" + String(frameCount) + ",\"fps\":" + String(fps) +
       ",\"repeat\":" + String(repeatTotal) + ",\"done\":" + String(screenDone ? "true" : "false") + "}";
  j += ",\"uptime_ms\":" + String(millis());
  j += ",\"reset_reason\":\"" + String(resetReason) + "\",\"boots\":" + String(bootCount);
  j += ",\"rssi\":" + String(WiFi.RSSI()) + "}";
  sendJson(j);
}

void handleInfo() {
  String j = "{\"fw\":\"mate-s3\",\"ip\":\"" + WiFi.localIP().toString() + "\"";
  j += ",\"max_steps\":" + String(MAX_STEPS) + ",\"max_speed\":" + String(MAX_SPEED) +
       ",\"max_accel\":" + String(MAX_ACCEL);
  j += ",\"max_servo_speed\":" + String(MAX_SERVO_SPEED);
  j += ",\"oled\":" + String(hasOled ? "true" : "false");
  j += ",\"screen\":{\"width\":128,\"height\":64,\"frame_bytes\":" + String(FRAME_BYTES) +
       ",\"max_frames\":" + String(MAX_FRAMES) + ",\"max_fps\":" + String(MAX_FPS) +
       ",\"max_repeat\":" + String(MAX_REPEAT) + "}";
  j += ",\"camera\":\"" + String(camName) + "\"";
  if (hasCam) {
    j +=",\"stream\":\"http://" + WiFi.localIP().toString() + ":81/stream\"";
    j += ",\"vflip\":" + String(flipV) + ",\"hmirror\":" + String(flipH);
  }
  sendJson(j + "}");
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
  pendingMove = {d1, d2, speed, accel};
  movePending = true;
  portEXIT_CRITICAL(&mux);
  sendJson("{\"ok\":true}");
}

void handleStop() {
  stopPending = true;
  sendJson("{\"ok\":true}");
}

// POST /screen, body = N × 1024 bytes (application/octet-stream), optional headers X-FPS (1–30)
// and X-Repeat (0 = forever, the default, or how many times to play). One frame is a still
// picture; several play at X-FPS. An empty body goes back to the status screen. (Headers, not
// query args, because WebServer skips query args on raw bodies.)
void handleScreenBody() {
  HTTPRaw &raw = server.raw();
  if (raw.status == RAW_START) {
    uploadLen = 0;
  } else if (raw.status == RAW_WRITE && uploadLen + raw.currentSize <= MAX_FRAMES * FRAME_BYTES) {
    memcpy(upload + uploadLen, raw.buf, raw.currentSize);
    uploadLen += raw.currentSize;
  }
}

void handleScreen() {
  long len = server.clientContentLength();
  if (len == 0) uploadLen = 0;  // an empty body may never reach handleScreenBody
  if (len < 0 || len % FRAME_BYTES || len > (long)(MAX_FRAMES * FRAME_BYTES) || (size_t)len != uploadLen) {
    return sendJson("{\"error\":\"body must be 0–" + String(MAX_FRAMES) + " frames of " + String(FRAME_BYTES) + " bytes\"}", 400);
  }
  long f = server.hasHeader("X-FPS") ? server.header("X-FPS").toInt() : 10;
  if (f < 1 || f > MAX_FPS) return sendJson("{\"error\":\"X-FPS 1–" + String(MAX_FPS) + "\"}", 400);
  long r = server.hasHeader("X-Repeat") ? server.header("X-Repeat").toInt() : 0;
  if (r < 0 || r > MAX_REPEAT) return sendJson("{\"error\":\"X-Repeat 0–" + String(MAX_REPEAT) + "\"}", 400);
  std::swap(frames, upload);
  frameCount = len / FRAME_BYTES;
  frameIdx = 0;
  fps = f;
  repeatTotal = r;
  loopsDone = 0;
  screenDone = frameCount <= 1;
  screenDirty = true;
  sendJson("{\"frames\":" + String(frameCount) + ",\"fps\":" + String(fps) + ",\"repeat\":" + String(repeatTotal) + "}");
}

// /servo?angle=0–180[&speed=1–600 °/s]. No speed (or 0) = jump at the servo's own full speed.
void handleServo() {
  long angle = server.arg("angle").toInt();
  if (!server.hasArg("angle") || angle < 0 || angle > 180) return sendJson("{\"error\":\"range\"}", 400);
  long speed = server.hasArg("speed") ? server.arg("speed").toInt() : 0;
  if (speed < 0 || speed > MAX_SERVO_SPEED) return sendJson("{\"error\":\"speed 0–" + String(MAX_SERVO_SPEED) + "\"}", 400);
  setServo(angle, speed);
  sendJson("{\"ok\":true}");
}

void handleCapture() {
  if (!hasCam) return sendJson("{\"error\":\"no camera\"}", 503);
  Jpeg j;
  camWake();
  bool ok = grabJpeg(j);
  camSleep();
  if (!ok) return sendJson("{\"error\":\"capture failed\"}", 500);
  server.sendHeader("Cache-Control", "no-store");
  server.setContentLength(j.len);
  server.send(200, "image/jpeg", "");
  server.sendContent((const char *)j.buf, j.len);
  freeJpeg(j);
}

// /camera?vflip=0|1&hmirror=0|1 — flip the image to match how the camera is mounted.
void handleCamera() {
  if (!hasCam) return sendJson("{\"error\":\"no camera\"}", 503);
  if (server.hasArg("vflip")) flipV = server.arg("vflip").toInt();
  if (server.hasArg("hmirror")) flipH = server.arg("hmirror").toInt();
  applyFlips();
  sendJson("{\"vflip\":" + String(flipV) + ",\"hmirror\":" + String(flipH) + "}");
}

void netTask(void *) {
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);

  hasOled = present(0x3C) && oled.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if (hasOled) {
    oled.setTextColor(SSD1306_WHITE);
  }
  frames = (uint8_t *)ps_malloc(MAX_FRAMES * FRAME_BYTES);
  upload = (uint8_t *)ps_malloc(MAX_FRAMES * FRAME_BYTES);

  camLock = xSemaphoreCreateMutex();
  hasCam = initCamera();
  // Servos after the camera, so the LEDC allocator sees its timer is taken.
  ledcAttachChannel(SERVO_PIN, 50, SERVO_BITS, 0);
  updateOled();

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.enableIPv6();  // without an IPv6 address, macOS waits 5 s on every mate.local lookup
  WiFi.setSleep(false);  // power save adds 100 ms+ latency spikes
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setTxPower(WIFI_POWER_8_5dBm);  // smaller current spikes on battery; plenty for a table
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print('.');
    updateOled();
  }
  WiFi.setSleep(false);  // again: on the S3 the setting doesn't stick until connected
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
  server.on("/screen", HTTP_POST, handleScreen, handleScreenBody);
  const char *headers[] = {"X-FPS", "X-Repeat"};
  server.collectHeaders(headers, 2);
  server.on("/servo", HTTP_POST, handleServo);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/camera", HTTP_POST, handleCamera);
  server.begin();
  if (hasCam) startStreamServer();

  Serial.printf("READY oled=%d cam=%s\n", hasOled, camName);

  for (;;) {
    server.handleClient();
    updateServo();
    updateOled();
    delay(1);
  }
}

// ---------------------------------------------------------------- main

void setup() {
  // On the power bank the MG996R's current sags the 5V enough to trip the brownout reset. The
  // dips are short and the chip rides through them, so the reset is off. Mate never writes
  // flash while running, so a dip can't corrupt anything. (Writing 0 to the brownout register
  // directly, the usual ESP32 trick, boot-loops the S3.)
  esp_brownout_disable();
  Serial.begin(115200);
  esp_reset_reason_t r = esp_reset_reason();
  resetReason = reasonName(r);
  if (r == ESP_RST_POWERON) bootCount = 0;
  bootCount++;
  s1.disableOutputs();
  s2.disableOutputs();
  xTaskCreatePinnedToCore(netTask, "net", 16384, nullptr, 1, nullptr, 0);
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
    if (s1.distanceToGo() == 0 && s2.distanceToGo() == 0) finish("ok");
  }
}

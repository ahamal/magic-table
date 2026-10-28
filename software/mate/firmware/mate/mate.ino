// Mate firmware: raw steppers, servos, edge reflex.
// No drive/turn logic on purpose — the agent learns the mapping.
// Serial protocol: see ../README.md

#include <AccelStepper.h>
#include <Servo.h>
#include <Wire.h>
#include <VL6180X.h>

#define FW_VERSION "0.1.0"

// ---- Pins (hardware/mate/README.md) ----
// 28BYJ-48 + ULN2003 in HALF4WIRE needs the order IN1, IN3, IN2, IN4.
AccelStepper s1(AccelStepper::HALF4WIRE, 2, 4, 3, 5);
AccelStepper s2(AccelStepper::HALF4WIRE, 6, 8, 7, 9);
const uint8_t SERVO_PINS[] = {10, 11, 12};  // pan, tilt, flipper
const uint8_t NUM_SERVOS = sizeof(SERVO_PINS);

// ---- Limits ----
const long MAX_STEPS = 4096;  // half-steps per command, about one wheel turn
const long MAX_SPEED = 800;   // half-steps/s
const long MAX_ACCEL = 1000;  // half-steps/s^2
const long DEFAULT_SPEED = 500;
const long DEFAULT_ACCEL = 400;

// ---- Edge reflex ----
const uint8_t EDGE_MM = 50;        // reading at or above this means no table below (255 = out of range)
const uint8_t EDGE_CONFIRM = 2;    // consecutive edge samples before reacting (filters glitches)
const long EDGE_BACKOFF = 200;     // half-steps to reverse after an edge stop
const long EDGE_GRACE = 120;       // half-steps allowed when a move starts over the edge
const uint8_t SENSOR_PERIOD_MS = 20;
const uint8_t SENSOR_POLL_MS = 5;

const uint16_t SERVO_HOLD_MS = 600;  // detach after a move to stop jitter and save power

enum State { IDLE, MOVING, BACKING_OFF };

VL6180X edgeSensor;
bool hasEdge = false;
uint8_t edgeMm = 255;
uint8_t edgeHits = 0;  // consecutive samples at or above EDGE_MM
unsigned long lastPoll = 0;

Servo servos[NUM_SERVOS];
int servoAngle[NUM_SERVOS];
unsigned long servoDetachAt[NUM_SERVOS];  // 0 = nothing pending

State state = IDLE;
long start1, start2;  // positions when the current command started
long cmd1, cmd2;      // steps requested by the current command
bool startOnEdge;

char line[48];
uint8_t lineLen = 0;

// ---------------------------------------------------------------- sensor

bool atEdge() { return hasEdge && edgeHits >= EDGE_CONFIRM; }
bool onTable() { return !hasEdge || edgeHits == 0; }

void pollEdgeSensor() {
  if (!hasEdge) return;
  // Non-blocking read of the continuous-mode result.
  uint8_t status = edgeSensor.readReg(VL6180X::RESULT__INTERRUPT_STATUS_GPIO);
  if ((status & 0x07) != 0x04) return;
  edgeMm = edgeSensor.readReg(VL6180X::RESULT__RANGE_VAL);
  edgeSensor.writeReg(VL6180X::SYSTEM__INTERRUPT_CLEAR, 0x01);
  if (edgeMm >= EDGE_MM) {
    if (edgeHits < 255) edgeHits++;
  } else {
    edgeHits = 0;
  }
}

// ---------------------------------------------------------------- motion

// Scale speed and acceleration by each wheel's share of the distance so both
// trapezoids have the same duration and the wheels finish together.
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
  // setCurrentPosition() zeroes speed and target: an immediate stop.
  s1.setCurrentPosition(s1.currentPosition());
  s2.setCurrentPosition(s2.currentPosition());
}

void release() {
  s1.disableOutputs();
  s2.disableOutputs();
}

void finish(const __FlashStringHelper *result) {
  release();
  state = IDLE;
  Serial.print(result);
  Serial.print(' ');
  Serial.print(s1.currentPosition() - start1);
  Serial.print(' ');
  Serial.println(s2.currentPosition() - start2);
}

long sign(long v) { return (v > 0) - (v < 0); }

// Reverse the way we came, keeping the same wheel ratio. This needs no idea
// of which way is "forward".
void triggerEdge() {
  hardStop();
  long longest = max(labs(cmd1), labs(cmd2));
  long b1 = -sign(cmd1) * (EDGE_BACKOFF * labs(cmd1) / longest);
  long b2 = -sign(cmd2) * (EDGE_BACKOFF * labs(cmd2) / longest);
  state = BACKING_OFF;
  startMove(b1, b2, DEFAULT_SPEED, MAX_ACCEL);
}

void checkEdge() {
  if (!hasEdge) return;
  if (startOnEdge) {
    // Started over the edge: fine if we're moving back onto the table,
    // otherwise stop after a short grace distance.
    if (onTable()) {
      startOnEdge = false;
    } else {
      long moved = max(labs(s1.currentPosition() - start1), labs(s2.currentPosition() - start2));
      if (moved > EDGE_GRACE) triggerEdge();
    }
  } else if (atEdge()) {
    triggerEdge();
  }
}

// ---------------------------------------------------------------- servos

void setServo(uint8_t id, int angle) {
  if (!servos[id].attached()) servos[id].attach(SERVO_PINS[id]);
  servos[id].write(angle);
  servoAngle[id] = angle;
  servoDetachAt[id] = millis() + SERVO_HOLD_MS;
  if (servoDetachAt[id] == 0) servoDetachAt[id] = 1;
}

void updateServos(unsigned long now) {
  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    if (servoDetachAt[i] && (long)(now - servoDetachAt[i]) >= 0) {
      servos[i].detach();
      servoDetachAt[i] = 0;
    }
  }
}

// ---------------------------------------------------------------- protocol

// Next argument: 1 = parsed, 0 = absent, -1 = malformed.
int8_t optLong(long &out) {
  char *tok = strtok(NULL, " ");
  if (!tok) return 0;
  char *end;
  out = strtol(tok, &end, 10);
  return *end == '\0' ? 1 : -1;
}

bool nextLong(long &out) { return optLong(out) == 1; }

bool noMoreArgs() { return strtok(NULL, " ") == NULL; }

void reply(const __FlashStringHelper *msg) { Serial.println(msg); }

void printStatus() {
  Serial.print(F("S busy="));
  Serial.print(state != IDLE ? 1 : 0);
  Serial.print(F(" p1="));
  Serial.print(s1.currentPosition());
  Serial.print(F(" p2="));
  Serial.print(s2.currentPosition());
  Serial.print(F(" edge="));
  if (hasEdge) Serial.print(edgeMm); else Serial.print(F("none"));
  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    Serial.print(F(" v"));
    Serial.print(i);
    Serial.print('=');
    Serial.print(servoAngle[i]);
  }
  Serial.println();
}

void printInfo() {
  Serial.print(F("I fw=" FW_VERSION " maxsteps="));
  Serial.print(MAX_STEPS);
  Serial.print(F(" maxspeed="));
  Serial.print(MAX_SPEED);
  Serial.print(F(" maxaccel="));
  Serial.print(MAX_ACCEL);
  Serial.print(F(" servos="));
  Serial.print(NUM_SERVOS);
  Serial.print(F(" edge="));
  Serial.println(hasEdge ? 1 : 0);
}

void cmdMove() {
  long d1, d2, speed = DEFAULT_SPEED, accel = DEFAULT_ACCEL;
  if (!nextLong(d1) || !nextLong(d2)) return reply(F("ERR PARSE"));
  if (optLong(speed) < 0 || optLong(accel) < 0 || !noMoreArgs()) return reply(F("ERR PARSE"));
  if (labs(d1) > MAX_STEPS || labs(d2) > MAX_STEPS ||
      speed < 1 || speed > MAX_SPEED || accel < 1 || accel > MAX_ACCEL) {
    return reply(F("ERR LIMIT"));
  }
  start1 = s1.currentPosition();
  start2 = s2.currentPosition();
  if (d1 == 0 && d2 == 0) return finish(F("OK"));
  cmd1 = d1;
  cmd2 = d2;
  startOnEdge = !onTable();
  state = MOVING;
  startMove(d1, d2, speed, accel);
}

void cmdServo() {
  long id, angle;
  if (!nextLong(id) || !nextLong(angle) || !noMoreArgs()) return reply(F("ERR PARSE"));
  if (id < 0 || id >= NUM_SERVOS || angle < 0 || angle > 180) return reply(F("ERR RANGE"));
  setServo(id, angle);
  reply(F("OK"));
}

void cmdStop() {
  if (state != IDLE) {
    hardStop();
    finish(F("STOPPED"));
  }
  release();
  reply(F("OK"));
}

void handleLine(char *text) {
  char *cmd = strtok(text, " ");
  if (!cmd) return;
  if (cmd[1] != '\0') return reply(F("ERR PARSE"));
  char c = toupper(cmd[0]);

  // While moving, only stop and status are accepted, so replies stay unambiguous.
  if (state != IDLE && c != 'X' && c != 'Q') return reply(F("ERR BUSY"));

  switch (c) {
    case 'M': return cmdMove();
    case 'V': return cmdServo();
    case 'X': return cmdStop();
    case 'R': release(); return reply(F("OK"));
    case 'Q': return printStatus();
    case 'I': return printInfo();
    default:  return reply(F("ERR PARSE"));
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[lineLen] = '\0';
      handleLine(line);
      lineLen = 0;
    } else if (lineLen < sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }
}

// ---------------------------------------------------------------- main

void setup() {
  Serial.begin(115200);

  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    servoAngle[i] = -1;  // unknown until first set
    servoDetachAt[i] = 0;
  }

  Wire.begin();
  Wire.setClock(400000);
  Wire.beginTransmission(0x29);
  hasEdge = Wire.endTransmission() == 0;
  if (hasEdge) {
    edgeSensor.init();
    edgeSensor.configureDefault();
    edgeSensor.setTimeout(50);
    edgeSensor.stopContinuous();
    delay(50);
    edgeSensor.startRangeContinuous(SENSOR_PERIOD_MS);
  }

  release();
  Serial.println(F("READY mate " FW_VERSION));
}

void loop() {
  readSerial();

  unsigned long now = millis();
  if (now - lastPoll >= SENSOR_POLL_MS) {
    lastPoll = now;
    pollEdgeSensor();
  }

  if (state != IDLE) {
    s1.run();
    s2.run();
    if (state == MOVING) checkEdge();
    if (state != IDLE && s1.distanceToGo() == 0 && s2.distanceToGo() == 0) {
      finish(state == MOVING ? F("OK") : F("EDGE"));
    }
  }

  updateServos(now);
}

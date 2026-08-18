#define PUL_PIN  4
#define DIR_PIN  5
#define EN_PIN   6

#define MICROSTEP      16
#define STEPS_PER_REV  200
#define MAX_DEGREES    380
#define MAX_STEPS      (200L * 16L * 380L / 360L)  // = 3022 — long explicite

long currentPosition = 0;
int  stepDelay       = 500;

void stepMotor(long steps, bool clockwise) {
  digitalWrite(DIR_PIN, clockwise ? HIGH : LOW);
  delayMicroseconds(10);
  for (long i = 0; i < steps; i++) {
    if (clockwise  && currentPosition >= MAX_STEPS) { Serial.println("LIMIT_MAX"); break; }
    if (!clockwise && currentPosition <= 0)          { Serial.println("LIMIT_MIN"); break; }
    digitalWrite(PUL_PIN, HIGH); delayMicroseconds(stepDelay);
    digitalWrite(PUL_PIN, LOW);  delayMicroseconds(stepDelay);
    currentPosition += clockwise ? 1 : -1;
  }
}

void goToAngle(int angle) {
  angle = constrain(angle, 0, MAX_DEGREES);
  long target = (200L * 16L * angle) / 360L;
  long delta  = target - currentPosition;
  if (delta != 0) stepMotor(abs(delta), delta > 0);
  Serial.print("ACK:"); Serial.println(currentPosition);
}

void setup() {
  pinMode(PUL_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN,  OUTPUT);
  digitalWrite(EN_PIN, LOW);
  currentPosition = 0;
  Serial.begin(9600);
  Serial.println("READY");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("ANGLE:"))      { goToAngle(cmd.substring(6).toInt()); }
    else if (cmd.startsWith("SPEED:")) {
      stepDelay = constrain(cmd.substring(6).toInt(), 50, 5000);
      Serial.print("SPEED_OK:"); Serial.println(stepDelay);
    }
    else if (cmd == "HOME") {
      Serial.println("HOMING");
      digitalWrite(DIR_PIN, LOW);
      delayMicroseconds(10);
      while (currentPosition > 0) {
        digitalWrite(PUL_PIN, HIGH); delayMicroseconds(stepDelay);
        digitalWrite(PUL_PIN, LOW);  delayMicroseconds(stepDelay);
        currentPosition--;
      }
      currentPosition = 0;
      Serial.println("HOME_OK");
    }
    else if (cmd == "POS")      { Serial.print("POS:"); Serial.println(currentPosition); }
    else if (cmd == "RESETPOS") { currentPosition = 0; Serial.println("RESET_OK"); }
    else if (cmd == "STOP")     { digitalWrite(EN_PIN, HIGH); Serial.println("STOPPED"); }
    else if (cmd == "START")    { digitalWrite(EN_PIN, LOW);  Serial.println("STARTED"); }
  }
}
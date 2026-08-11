// ── Pins ──────────────────────────────────────────────────────────────────
#define PUL_PIN  4
#define DIR_PIN  5
#define EN_PIN   6

// ── Config mécanique ──────────────────────────────────────────────────────
#define MICROSTEP       16
#define STEPS_PER_REV   200
#define MAX_DEGREES     340
#define MAX_STEPS       (long)(STEPS_PER_REV * MICROSTEP * MAX_DEGREES / 360.0)

// ── Variables ─────────────────────────────────────────────────────────────
long currentPosition = 0;
int  stepDelay       = 150;

// ── Déplacement avec limites ──────────────────────────────────────────────
void stepMotor(long steps, bool clockwise) {
  digitalWrite(DIR_PIN, clockwise ? HIGH : LOW);
  delayMicroseconds(10);
  for (long i = 0; i < abs(steps); i++) {
    if (clockwise  && currentPosition >= MAX_STEPS) { Serial.println("LIMIT_MAX"); break; }
    if (!clockwise && currentPosition <= 0)          { Serial.println("LIMIT_MIN"); break; }
    digitalWrite(PUL_PIN, HIGH); delayMicroseconds(stepDelay);
    digitalWrite(PUL_PIN, LOW);  delayMicroseconds(stepDelay);
    currentPosition += clockwise ? 1 : -1;
  }
}

// ── Aller à un angle précis (0–340°) ─────────────────────────────────────
void goToAngle(int angle) {
  angle = constrain(angle, 0, MAX_DEGREES);
  long target = (long)(angle * STEPS_PER_REV * MICROSTEP / 360.0);
  long delta  = target - currentPosition;
  if (delta != 0) stepMotor(abs(delta), delta > 0);
  Serial.print("ACK:"); Serial.println(currentPosition);
}

// ── Setup ─────────────────────────────────────────────────────────────────
void setup() {
  pinMode(PUL_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN,  OUTPUT);
  digitalWrite(EN_PIN, LOW);
  Serial.begin(9600);
  Serial.println("READY");
}

// ── Loop ──────────────────────────────────────────────────────────────────
void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("ANGLE:")) {
      goToAngle(cmd.substring(6).toInt());
    }
    else if (cmd.startsWith("SPEED:")) {
      stepDelay = constrain(cmd.substring(6).toInt(), 50, 5000);
      Serial.print("SPEED_OK:"); Serial.println(stepDelay);
    }
    else if (cmd == "HOME") {
      Serial.println("HOMING");
      currentPosition = MAX_STEPS;
      digitalWrite(DIR_PIN, LOW);
      delayMicroseconds(10);
      for (long i = 0; i < MAX_STEPS + 100; i++) {
        if (currentPosition <= 0) break;
        digitalWrite(PUL_PIN, HIGH); delayMicroseconds(stepDelay);
        digitalWrite(PUL_PIN, LOW);  delayMicroseconds(stepDelay);
        currentPosition--;
      }
      currentPosition = 0;
      Serial.println("HOME_OK");
    }
    else if (cmd == "POS") {
      Serial.print("POS:"); Serial.println(currentPosition);
    }
    else if (cmd == "RESETPOS") {
      // Remet la position à 0 SANS bouger le moteur
      // La position physique actuelle devient le nouveau zéro
      currentPosition = 0;
      Serial.println("RESET_OK");
    }
    else if (cmd == "STOP") {
      digitalWrite(EN_PIN, HIGH);
      Serial.println("STOPPED");
    }
    else if (cmd == "START") {
      digitalWrite(EN_PIN, LOW);
      Serial.println("STARTED");
    }
  }
}

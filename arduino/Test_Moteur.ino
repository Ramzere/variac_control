// ── Pins ──────────────────────────────────────────────────────────────────
#define PUL_PIN  4   // STEP → PUL+
#define DIR_PIN  5   // DIR  → DIR+
#define EN_PIN   6   // EN   → ENA+
// GND Arduino → PUL− / DIR− / ENA−

// ── Config ────────────────────────────────────────────────────────────────
#define MICROSTEP      16    // selon DIP switches (SW1=OFF SW2=OFF SW3=ON)
#define STEPS_PER_REV  200   // NEMA 23 = 1.8° par pas
#define STEPS_FULL_REV (STEPS_PER_REV * MICROSTEP)  // 3200 micro-pas/tour

int stepDelay = 150;  // µs entre chaque micro-pas (plus petit = plus rapide)

// ── Fonction de rotation ──────────────────────────────────────────────────
void rotate(long steps, bool clockwise) {
  digitalWrite(DIR_PIN, clockwise ? HIGH : LOW);
  delayMicroseconds(10);  // laisser DIR se stabiliser
  for (long i = 0; i < steps; i++) {
    digitalWrite(PUL_PIN, HIGH);
    delayMicroseconds(stepDelay);
    digitalWrite(PUL_PIN, LOW);
    delayMicroseconds(stepDelay);
  }
}

void setup() {
  pinMode(PUL_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN,  OUTPUT);
  digitalWrite(EN_PIN, LOW);  // LOW = moteur actif
  Serial.begin(9600);
  Serial.println("TB6600 test ready");
  Serial.println("Commands: CW / CCW / FAST / SLOW / STOP / START");
}

void loop() {
  // Test automatique : 1 tour CW puis 1 tour CCW
  Serial.println("→ 1 tour CW");
  rotate(STEPS_FULL_REV, true);
  delay(1000);

  Serial.println("← 1 tour CCW");
  rotate(STEPS_FULL_REV, false);
  delay(1000);

  // Écoute les commandes série pour tester manuellement
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if      (cmd == "CW")    { rotate(STEPS_FULL_REV, true);  }
    else if (cmd == "CCW")   { rotate(STEPS_FULL_REV, false); }
    else if (cmd == "FAST")  { stepDelay = 80;  Serial.println("Speed: FAST"); }
    else if (cmd == "SLOW")  { stepDelay = 500; Serial.println("Speed: SLOW"); }
    else if (cmd == "STOP")  { digitalWrite(EN_PIN, HIGH); Serial.println("DISABLED"); }
    else if (cmd == "START") { digitalWrite(EN_PIN, LOW);  Serial.println("ENABLED");  }
  }
}
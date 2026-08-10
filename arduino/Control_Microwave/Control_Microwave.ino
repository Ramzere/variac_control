#define EN_PIN    6
#define STEP_PIN  4
#define DIR_PIN   5

void setup() {
  pinMode(EN_PIN,   OUTPUT);
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN,  OUTPUT);
  digitalWrite(EN_PIN, LOW);
  Serial.begin(9600);
  Serial.println("READY");
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "POS") {
      Serial.println("POS:0");
    }
    else if (cmd == "STOP") {
      digitalWrite(EN_PIN, HIGH);
      Serial.println("STOPPED");
    }
    else if (cmd == "START") {
      digitalWrite(EN_PIN, LOW);
      Serial.println("STARTED");
    }
    else if (cmd.startsWith("ANGLE:")) {
      Serial.print("ACK:");
      Serial.println(cmd.substring(6));
    }
    else if (cmd == "HOME") {
      Serial.println("HOME_OK");
    }
  }
}
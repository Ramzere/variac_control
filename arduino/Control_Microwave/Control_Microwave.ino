// =============================================================================
// Variac Control System — Arduino Nano Firmware
// =============================================================================
// Controls a NEMA 23 stepper motor via TB6600 driver to physically rotate
// the knob of a Clairtronic 10534 Variac.
//
// The Arduino receives text commands from a Python script over USB serial
// (9600 baud) and generates STEP/DIR pulses for the TB6600 driver.
//
// Hardware:
//   - Arduino Nano CH340 USB-C
//   - TB6600 stepper driver (DIP: 1/16 microstep, 2.8A)
//   - NEMA 23 stepper motor (23HS22-2804S, 1.26 Nm)
//   - Variac mechanical travel: 0 to 380 degrees (maps to 0V-270V output)
//
// Pin mapping:
//   D4 -> TB6600 PUL+   (step pulse)
//   D5 -> TB6600 DIR+   (rotation direction)
//   D6 -> TB6600 ENA+   (driver enable, active LOW)
//   GND -> PUL- / DIR- / ENA-
// =============================================================================

// ── Pin definitions ───────────────────────────────────────────────────────────
#define PUL_PIN  4   // Step pulse output -> TB6600 PUL+
#define DIR_PIN  5   // Direction output  -> TB6600 DIR+
#define EN_PIN   6   // Enable output     -> TB6600 ENA+  (LOW = enabled)

// ── Mechanical constants ──────────────────────────────────────────────────────
#define MICROSTEP      16    // 1/16 microstepping (TB6600 DIP: SW1=OFF SW2=OFF SW3=ON)
#define STEPS_PER_REV  200   // Full steps per revolution (NEMA 23 = 1.8 deg per step)
#define MAX_DEGREES    380   // Variac mechanical travel in degrees

// Total micro-steps for full travel: 200 x 16 x 380 / 360 = 3377 steps
// Using long literals (L) to prevent integer overflow during calculation
#define MAX_STEPS      (200L * 16L * 380L / 360L)

// ── Runtime variables ─────────────────────────────────────────────────────────
long currentPosition = 0;    // Current position in micro-steps (0 = home / 0V output)
int  stepDelay       = 500;  // Delay between pulses in microseconds (controls speed)
                             // Lower = faster. Range: 50us to 5000us

// =============================================================================
// stepMotor() -- Move the motor a given number of micro-steps
// =============================================================================
// Parameters:
//   steps     -- number of micro-steps to move
//   clockwise -- true = increase angle (raise voltage), false = decrease
//
// Enforces mechanical limits: stops and reports if 0 deg or 380 deg is reached.
// =============================================================================
void stepMotor(long steps, bool clockwise) {
  // Set direction and allow the TB6600 DIR signal to stabilise
  digitalWrite(DIR_PIN, clockwise ? HIGH : LOW);
  delayMicroseconds(10);

  for (long i = 0; i < steps; i++) {
    // Check upper limit before each step
    if (clockwise  && currentPosition >= MAX_STEPS) {
      Serial.println("LIMIT_MAX");
      break;
    }
    // Check lower limit before each step
    if (!clockwise && currentPosition <= 0) {
      Serial.println("LIMIT_MIN");
      break;
    }

    // Generate one step pulse (HIGH then LOW)
    digitalWrite(PUL_PIN, HIGH); delayMicroseconds(stepDelay);
    digitalWrite(PUL_PIN, LOW);  delayMicroseconds(stepDelay);

    // Update position tracker
    currentPosition += clockwise ? 1 : -1;
  }
}

// =============================================================================
// goToAngle() -- Move to an absolute angle (0 to 380 degrees)
// =============================================================================
// Converts the target angle to micro-steps, computes the delta from current
// position, and calls stepMotor() in the correct direction.
// Sends "ACK:<position>" when movement is complete.
// =============================================================================
void goToAngle(int angle) {
  // Clamp angle to valid mechanical range
  angle = constrain(angle, 0, MAX_DEGREES);

  // Convert angle to micro-steps (long arithmetic to avoid overflow)
  long target = (200L * 16L * angle) / 360L;

  // Calculate displacement from current position (positive = clockwise)
  long delta = target - currentPosition;

  // Move only if there is a displacement to make
  if (delta != 0) stepMotor(abs(delta), delta > 0);

  // Confirm completion with current position in micro-steps
  Serial.print("ACK:"); Serial.println(currentPosition);
}

// =============================================================================
// setup() -- Initialise pins and serial communication
// =============================================================================
void setup() {
  pinMode(PUL_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN,  OUTPUT);

  // Enable the TB6600 driver (ENA+ = LOW activates the driver)
  digitalWrite(EN_PIN, LOW);

  // Assume startup position is the physical zero reference
  currentPosition = 0;

  Serial.begin(9600);
  Serial.println("READY");
}

// =============================================================================
// loop() -- Listen for serial commands from Python and execute them
// =============================================================================
// Supported commands:
//   ANGLE:<deg>  -> Move to absolute angle (0-380 deg)        -> ACK:<pos>
//   SPEED:<us>   -> Set step delay in microseconds (50-5000)  -> SPEED_OK:<val>
//   HOME         -> Return to physical zero (step by step)    -> HOMING ... HOME_OK
//   POS          -> Report current position in micro-steps    -> POS:<pos>
//   RESETPOS     -> Reset position counter to 0 (no movement) -> RESET_OK
//   STOP         -> Disable driver (cuts holding torque)      -> STOPPED
//   START        -> Re-enable driver                          -> STARTED
// =============================================================================
void loop() {
  if (Serial.available()) {
    // Read command terminated by newline
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();  // Remove whitespace and carriage return

    // ── ANGLE:<degrees> -- absolute position command ──────────────────────
    if (cmd.startsWith("ANGLE:")) {
      goToAngle(cmd.substring(6).toInt());
    }

    // ── SPEED:<microseconds> -- set step pulse delay ──────────────────────
    else if (cmd.startsWith("SPEED:")) {
      stepDelay = constrain(cmd.substring(6).toInt(), 50, 5000);
      Serial.print("SPEED_OK:"); Serial.println(stepDelay);
    }

    // ── HOME -- return to position zero step by step ──────────────────────
    // Moves the motor to the minimum position without a limit switch.
    // The position counter decrements with each step so LIMIT_MIN
    // is never triggered during homing.
    else if (cmd == "HOME") {
      Serial.println("HOMING");
      digitalWrite(DIR_PIN, LOW);   // CCW direction (decreasing angle)
      delayMicroseconds(10);
      while (currentPosition > 0) {
        digitalWrite(PUL_PIN, HIGH); delayMicroseconds(stepDelay);
        digitalWrite(PUL_PIN, LOW);  delayMicroseconds(stepDelay);
        currentPosition--;
      }
      currentPosition = 0;
      Serial.println("HOME_OK");
    }

    // ── POS -- report current position ───────────────────────────────────
    else if (cmd == "POS") {
      Serial.print("POS:"); Serial.println(currentPosition);
    }

    // ── RESETPOS -- reset position counter without moving ─────────────────
    // Declares the current physical position as the new zero reference.
    // Used after manually repositioning the coupler on the Variac knob.
    else if (cmd == "RESETPOS") {
      currentPosition = 0;
      Serial.println("RESET_OK");
    }

    // ── STOP -- disable the TB6600 driver ────────────────────────────────
    // Cuts holding torque. Use with caution: the Variac knob may drift.
    else if (cmd == "STOP") {
      digitalWrite(EN_PIN, HIGH);
      Serial.println("STOPPED");
    }

    // ── START -- re-enable the TB6600 driver ─────────────────────────────
    else if (cmd == "START") {
      digitalWrite(EN_PIN, LOW);
      Serial.println("STARTED");
    }
  }
}

# Variac Control System

Automated control of a Clairtronic 10534 Variac using a NEMA 23 stepper motor, Arduino Nano, TB6600 driver and a Python/Flask web interface. Developed as part of an internship project at CESI École d'ingénieurs, Limerick, Ireland.

---

## Overview

The system physically rotates the Variac knob using a stepper motor controlled by software. An operator can set a target temperature, run automated thermal cycles, and monitor data in real time from a web browser — no installation required on the client side.

---

## Hardware

| Component | Model | Role |
|---|---|---|
| Variac | Clairtronic 10534 — 5A 230V | Adjustable power supply |
| Stepper motor | NEMA 23 — 23HS22-2804S 2.8A 1.26Nm | Rotates the Variac knob |
| Motor driver | TB6600 | Drives the NEMA 23 (up to 4A) |
| Microcontroller | Arduino Nano CH340 USB-C | Receives commands, generates step pulses |
| 3D coupler | PLA+ jaw coupler | Links motor shaft to Variac knob |
| USB hub | UGREEN 4-port USB 3.0 | Single connection to PC |
| Power supply | 12V 3A minimum | Powers motor via TB6600 |

---

## Wiring

### Arduino → TB6600

| Arduino | TB6600 | Wire color |
|---|---|---|
| D4 | PUL+ | Blue |
| D5 | DIR+ | Green |
| D6 | ENA+ | Orange |
| GND | PUL− / DIR− / ENA− | Black |

### Power supply → TB6600

| Supply | TB6600 | Wire color |
|---|---|---|
| +12V | VCC | Red |
| GND | GND | Black |

### TB6600 → NEMA 23

| TB6600 | Motor wire | Wire color |
|---|---|---|
| A+ | Coil A+ | Red |
| A− | Coil A− | Blue |
| B+ | Coil B+ | Black |
| B− | Coil B− | Green |

### TB6600 DIP switches

**Microstep:**
| SW1 | SW2 | SW3 | Mode |
|---|---|---|---|
| OFF | OFF | ON | 1/16 — 3200 steps/rev |

**Current:**
| SW4 | SW5 | SW6 | Current |
|---|---|---|---|
| OFF | OFF | ON | 2.8A |

---

## 3D Printed Coupler

Jaw coupler that grips the 10 knurls of the Variac knob — no permanent modification to the equipment.

| Parameter | Value |
|---|---|
| Material | PLA+ |
| Inner diameter | 65.4mm |
| Outer diameter | 80mm |
| Height | 28mm |
| Teeth | 10 (one per knurl) |
| Clamping | 2× M3 screws with brass inserts |
| Infill | 40% minimum |

---

## Software

### Stack

- **Arduino** — C++ firmware (Arduino IDE)
- **Python 3** — Flask server + PID control
- **HTML / CSS / JS** — Web interface (no framework)

### Dependencies

```bash
pip install flask flask-socketio pyserial
```

### Project structure

```
variac_control/
├── app.py              # Flask server + PID + sensor reading
├── config.ini          # Configuration (port, baudrate, sensors, PID)
├── launch.command      # Mac launcher (double-click)
├── launch.bat          # Windows launcher (double-click)
├── logs/               # CSV data logs (auto-created)
└── templates/
    └── index.html      # Web interface
```

---

## Installation

### Mac

```bash
git clone https://github.com/YOUR_USERNAME/variac-control.git
cd variac-control/variac_control
pip3 install flask flask-socketio pyserial
chmod +x launch.command
xattr -d com.apple.quarantine launch.command
```

Double-click `launch.command` — the browser opens automatically at `http://localhost:5001`.

### Windows

```bash
git clone https://github.com/YOUR_USERNAME/variac-control.git
cd variac-control\variac_control
pip install flask flask-socketio pyserial
```

Double-click `launch.bat` — the browser opens automatically at `http://localhost:5001`.

> **Note:** Python must be installed with "Add Python to PATH" checked. Install the CH340 driver if the Arduino is not detected.

---

## Configuration

Edit `config.ini` to match your setup:

```ini
[server]
host = 0.0.0.0
port = 5001

[paths]
# Mac   : /Users/yourname/Documents/variac_control
# Win   : C:\Users\yourname\Documents\variac_control
app_dir = /Users/remirodriguez/Documents/CESI/A4/MI/Travail/variac_control

[arduino]
baudrate = 9600
timeout = 2

[pid]
p = 1.2
i = 0.05
d = 0.0
bangbang_threshold = 20

[sensor_1]
name = Sensor A — Low range
min_temp = 0
max_temp = 400

[sensor_2]
name = Sensor B — High range
min_temp = 300
max_temp = 800
```

---

## Usage

1. Connect Arduino Nano via USB hub
2. Connect 12V power supply to TB6600
3. Launch the server (`launch.command` on Mac, `launch.bat` on Windows)
4. Open `http://localhost:5001` in your browser
5. Run **Autotest** — verifies serial port, Arduino communication, and motor response
6. Select the active temperature sensor (Sensor A or B) from the header dropdown
7. Use **Manual** mode or program **Cycles**

### Interface tabs

| Tab | Description |
|---|---|
| 🔍 Autotest | System check — port, Arduino, motor, sensor |
| 🎛️ Manual | Target temperature + PID regulation |
| 🔄 Cycles | Programmed thermal cycles (T max/min, hold times, repetitions) |
| 📋 Log | Live data log — export to CSV |
| ⚙️ Motor | Direct motor control — angle input, quick positions, reset |

### Arduino serial commands

| Command | Response | Action |
|---|---|---|
| `ANGLE:170` | `ACK:1511` | Go to 170° |
| `HOME` | `HOME_OK` | Return to 0° (physical stop) |
| `POS` | `POS:0` | Read current position (micro-steps) |
| `RESETPOS` | `RESET_OK` | Set current position as 0° (no movement) |
| `SPEED:150` | `SPEED_OK:150` | Set step delay in µs |
| `STOP` | `STOPPED` | Disable motor (no holding torque) |
| `START` | `STARTED` | Enable motor |

---

## Temperature Sensors

Two sensors supported — selected from the web interface header dropdown:

| Sensor | Range | Connection |
|---|---|---|
| Sensor A | 0 – 400°C | USB-B cable |
| Sensor B | 300 – 800°C | USB-B cable |

Only one sensor active at a time. Switching automatically recalibrates the slider, chart Y-axis, and constrains the target temperature to the sensor range. Each session log file includes the sensor name.

> **Note:** Sensor serial format (CSV columns, baud rate) to be confirmed once the sensor model is known. Update `read_temperature()` in `app.py` accordingly.

---

## PID Control

The PID loop runs in Python, not on the Arduino. The Arduino only receives an angle and moves the motor.

**Strategy:**
- **Phase 1 — Bang-bang:** motor runs at full speed until within 20°C of target
- **Phase 2 — PID:** fine-tunes motor angle to hold target temperature precisely

**Parameters (adjust in `config.ini`):**

| Parameter | Default | Role |
|---|---|---|
| P | 1.2 | Corrects instantaneous error |
| I | 0.05 | Corrects accumulated error |
| D | 0.0 | Anticipates rate of change |
| bangbang_threshold | 20 | Switch from bang-bang to PID (°C) |

> Calibrate PID parameters on real hardware. First test with a neutral material before using carbon fibre.

---

## Project Status

| Task | Status |
|---|---|
| System architecture | ✅ Done |
| Hardware selection and validation | ✅ Done |
| NEMA 23 motor test (TB6600) | ✅ Done |
| 3D coupler printed and fitted | ✅ Done |
| Arduino firmware | ✅ Done |
| Python server + web interface | ✅ Done |
| Autotest (port + Arduino + motor) | ✅ Done |
| Mac + Windows compatibility | ✅ Done |
| PID calibration on real Variac | 🔲 To do |
| Temperature sensor integration | 🔲 To do |
| Carbon fibre thermal cycle tests | 🔲 To do |

---

## Context

- **Location:** Limerick, Ireland — 230V / 50Hz / BS1363
- **Material:** Carbon fibre
- **Temperature range:** 0°C to 1000°C (depending on sensor)
- **Project:** Internship — CESI École d'ingénieurs (2025–2026)
- **Supervisor:** Anne



xattr -d com.apple.quarantine "/Users/remirodriguez/Documents/CESI/A4/MI/Travail/variac_control/launch.command" && chmod +x "/Users/remirodriguez/Documents/CESI/A4/MI/Travail/variac_control/launch.command"

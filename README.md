# Variac Control System

Automated control of a Clairtronic 10534 Variac using a NEMA 23 stepper motor, Arduino Nano, TB6600 driver and a Python/Flask web interface. Developed as part of an internship project at CESI École d'ingénieurs, Limerick, Ireland.

---

## Overview

The system physically rotates the Variac knob using a stepper motor controlled by software. An operator can set a target temperature, run automated thermal cycles, and monitor data in real time from a web browser — no installation required on the client side.

---

## Hardware

| Component | Model | Role |
|---|---|---|
| Variac | Clairtronic 10534 — 5A 230V | Adjustable power supply (0V–270V) |
| Stepper motor | NEMA 23 — 23HS22-2804S 2.8A 1.26Nm | Rotates the Variac knob |
| Motor driver | TB6600 | Drives the NEMA 23 (up to 4A) |
| Microcontroller | Arduino Nano CH340 USB-C | Receives commands, generates step pulses |
| 3D coupler | PLA+ jaw coupler | Links motor shaft to Variac knob |
| Motor base | PLA+ printed base | Holds motor, driver, PSU and USB hub |
| Power supply | Mean Well LRS-50-12 — 12V 4.2A | Powers motor via TB6600 (mounted on base) |
| USB hub | UGREEN 4-port USB 3.0 | Single PC connection for all USB devices |
| Sensor A | CalexConfig pyrometer | 0–800°C — reads CSV file |
| Sensor B | Optris CT 3MH3CF | 250–1800°C — reads via serial port COM7 |

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

## 3D Printed Parts

| Part | Role |
|---|---|
| Jaw coupler (PLA+) | Grips the 10 knurls of the Variac knob — no permanent modification |
| Motor base (PLA+) | Holds motor, TB6600 driver, LRS-50-12 PSU and USB hub |

**Coupler specifications:**

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
├── app.py                  # Flask server + PID + sensor reading
├── config.ini              # Configuration (ports, baudrates, sensors, PID)
├── launch.command          # Mac launcher (double-click)
├── launch.bat              # Windows launcher (double-click)
├── CalexConfig/
│   └── data/               # Drop CalexConfig CSV files here (Mac only)
├── logs/                   # CSV data logs (auto-created at each session)
└── templates/
    └── index.html          # Web interface
```

---

## Installation

### Mac

```bash
git clone https://github.com/Ramzere/variac_control.git
cd variac_control
pip3 install flask flask-socketio pyserial
chmod +x launch.command
xattr -d com.apple.quarantine launch.command
```

Double-click `launch.command` — the browser opens automatically at `http://localhost:5001`.

### Windows

```bash
git clone https://github.com/Ramzere/variac_control.git
cd variac_control
pip install flask flask-socketio pyserial
```

Double-click `launch.bat` — the browser opens automatically at `http://localhost:5001`.

> **Note:** Python must be installed with "Add Python to PATH" checked.  
> Install the CH340 driver (CH341SER.EXE) if the Arduino is not detected.

---

## Configuration

Edit `config.ini` to match your setup. Open with Notepad++ and save as **UTF-8 without BOM**.

```ini
[server]
host = 0.0.0.0
port = 5001

[arduino]
# Check Device Manager -> Ports (COM & LPT) -> USB-SERIAL CH340
port = COM5
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
max_temp = 800

[sensor_2]
name = Sensor B — High range
min_temp = 250
max_temp = 1800

[optris]
# Serial port for Optris CT 3MH — close CompactConnect before starting
port = COM7
baudrate = 115200

[sensor_csv]
# Folder where CalexConfig saves its CSV log files
csv_dir_1 = C:\Users\...\CalexConfig log files
# Column index: 2=Unfiltered, 3=Filtered (recommended), 4=Sensor
column_1 = 3
```

---

## Usage

1. Connect Arduino Nano and sensors via USB hub
2. Power on the LRS-50-12 supply (TB6600 green LED on)
3. Launch the server (`launch.command` on Mac, `launch.bat` on Windows)
4. Open `http://localhost:5001` in your browser
5. Click **? Setup guide** in the top bar and follow the steps
6. Run **Autotest** — verifies port, Arduino, motor and sensor
7. Select the active sensor (Sensor A or B) from the header dropdown
8. Use **Manual** mode or program **Cycles**

### Sensor selection

| Sensor | Range | Protocol | Prerequisite |
|---|---|---|---|
| Sensor A — CalexConfig | 0–800°C | CSV file (reads most recent) | CalexConfig must be recording |
| Sensor B — Optris CT 3MH | 250–1800°C | Serial COM7 @ 115200 baud | CompactConnect must be **closed** |

### Interface tabs

| Tab | Description |
|---|---|
| 🔍 Autotest | System check — port, Arduino, motor, sensor |
| 🎛️ Manual | Target temperature + PID regulation |
| 🔄 Cycles | Programmed thermal cycles (T max/min, hold times, repetitions) |
| 📋 Log | Live data log — export to CSV |
| ⚙️ Motor | Direct motor control — angle input, quick positions, speed, reset |

### Arduino serial commands

| Command | Response | Action |
|---|---|---|
| `ANGLE:170` | `ACK:1511` | Go to 170° (absolute position) |
| `HOME` | `HOME_OK` | Return to 0° step by step |
| `POS` | `POS:0` | Read current position in micro-steps |
| `RESETPOS` | `RESET_OK` | Set current position as 0° (no movement) |
| `SPEED:150` | `SPEED_OK:150` | Set step delay in µs (50–5000) |
| `STOP` | `STOPPED` | Disable driver (cuts holding torque) |
| `START` | `STARTED` | Re-enable driver |

---

## Temperature Sensors

Two sensors supported — selected from the header dropdown. Only one active at a time.

| Sensor | Range | Software | Data source |
|---|---|---|---|
| Sensor A | 0–800°C | CalexConfig | Most recent CSV in configured folder |
| Sensor B | 250–1800°C | Optris CT 3MH3CF | Serial port COM7, command 0x01, formula: (byte1×256 + byte2 − 1000) / 10 |

Switching sensors automatically recalibrates the slider, chart Y-axis, and constrains the target temperature.

---

## PID Control

The PID loop runs in Python. The Arduino only receives an `ANGLE:XXX` command and moves the motor accordingly.

**Control strategy:**
- **Phase 1 — Bang-bang:** motor runs at full speed when `|error| > bangbang_threshold`
- **Phase 2 — PID:** fine correction when close to target
- **Stop:** motor returns to 0° (0V output) without cutting motor power

**Parameters (adjust in `config.ini`):**

| Parameter | Default | Role |
|---|---|---|
| P | 1.2 | Proportional — corrects instantaneous error |
| I | 0.05 | Integral — corrects accumulated error |
| D | 0.0 | Derivative — anticipates rate of change |
| bangbang_threshold | 20°C | Error threshold for bang-bang phase |

---

## Project Status

| Task | Status |
|---|---|
| System architecture | ✅ Done |
| Hardware selection and validation | ✅ Done |
| NEMA 23 motor test (TB6600) | ✅ Done |
| 3D coupler and motor base printed | ✅ Done |
| LRS-50-12 PSU mounted on base | ✅ Done |
| Arduino firmware | ✅ Done |
| Python server + web interface | ✅ Done |
| Autotest (port + Arduino + motor + sensor) | ✅ Done |
| Mac + Windows compatibility | ✅ Done |
| Sensor A integration (CalexConfig CSV) | ✅ Done |
| Sensor B integration (Optris serial) | ✅ Done |
| Manual mode with PID | ✅ Done |
| Cycle mode | ✅ Done |
| PID calibration on real Variac | 🔲 To do |
| Carbon fibre thermal cycle tests | 🔲 To do |

---

## Context

- **Location:** Limerick, Ireland — 230V / 50Hz / BS1363
- **Material processed:** Carbon fibre
- **Project:** Internship — CESI École d'ingénieurs (2025–2026)
- **Supervisor:** Anne McLoughlin & Rahul Samyal
- **GitHub:** [github.com/Ramzere/variac_control](https://github.com/Ramzere/variac_control)

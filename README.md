# Variac Control System
Automated control of a Clairtronic 10534 Variac using a NEMA 23 stepper motor, 
Arduino Nano, TB6600 driver, and a Python/Flask web interface.

---

## Hardware
| Component | Model | Role |
|---|---|---|
| Variac | Clairtronic 10534 — 5A 230V | Adjustable power supply |
| Stepper motor | NEMA 23 — 23HS22-2804S 2.8A | Rotates the Variac knob |
| Motor driver | TB6600 | Drives the NEMA 23 |
| Microcontroller | Arduino Nano CH340 USB-C | Receives commands, generates pulses |
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
| SW1 | SW2 | SW3 | Mode |
|---|---|---|---|
| OFF | OFF | ON | 1/16 microstep (3200 steps/rev) |

| SW4 | SW5 | SW6 | Current |
|---|---|---|---|
| OFF | OFF | ON | 2.8A |

---

## Software

### Stack
- **Arduino** — C++ firmware (Arduino IDE)
- **Python 3** — Flask server + PID control
- **HTML/CSS/JS** — Web interface (no framework)

### Dependencies
```bash
pip3 install flask flask-socketio pyserial
```

### Project structure
variac_control/
├── app.py # Flask server + PID + sensor reading
├── config.ini # Configuration (port, baudrate, sensors)
├── launch.command # Mac launcher (double-click)
├── logs/ # CSV data logs (auto-created)
└── templates/
└── index.html # Web interface

### Configuration — config.ini
```ini
[server]
host = 0.0.0.0
port = 5001

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
format = csv

[sensor_2]
name = Sensor B — High range
min_temp = 300
max_temp = 800
format = csv
```

---

## Installation

### Mac
```bash
git clone https://github.com/Ramzere/variac-control.git
cd variac-control/variac_control
pip3 install flask flask-socketio pyserial
chmod +x launch.command
xattr -d com.apple.quarantine launch.command
```
Then double-click `launch.command` — the browser opens automatically.

### Windows
```bash
git clone https://github.com/Ramzere/variac-control.git
cd variac-control\variac_control
pip install flask flask-socketio pyserial
python app.py
```
Open `http://localhost:5001` in your browser.

---

## Usage

1. Connect Arduino Nano via USB hub
2. Connect 12V power supply to TB6600
3. Launch the server (double-click `launch.command` on Mac)
4. Open `http://localhost:5001`
5. Run **Autotest** — verify Arduino connection
6. Select the active temperature sensor (Sensor A or B)
7. Use **Manual** mode or program **Cycles**

### Serial commands (Arduino)
| Command | Response | Action |
|---|---|---|
| `ANGLE:170` | `ACK:xxx` | Go to 170° |
| `HOME` | `HOME_OK` | Return to 0° |
| `POS` | `POS:xxx` | Read current position |
| `STOP` | `STOPPED` | Disable motor |
| `START` | `STARTED` | Enable motor |

---

## Temperature sensors

Two sensors supported — selected from the web interface header:

| Sensor | Range | USB |
|---|---|---|
| Sensor A | 0 – 400°C | Separate USB-B cable |
| Sensor B | 300 – 800°C | Separate USB-B cable |

Only one sensor active at a time. Switching automatically recalibrates 
the slider, chart, and constrains the target temperature to the sensor range.

---

## Mechanical — 3D printed coupler

Jaw coupler grips the 10 knurls of the Variac knob.

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

## Status

| Task | Status |
|---|---|
| Architecture design | ✅ Done |
| Hardware selection | ✅ Done |
| NEMA 23 motor test | ✅ Done |
| 3D coupler printed | ✅ Done |
| TB6600 wiring | ⏳ In progress |
| Arduino firmware | ⏳ In progress |
| Python + web interface | ⏳ In progress |
| PID calibration | 🔲 To do |
| Carbon fibre tests | 🔲 To do |

---

## Context

- Location: Limerick, Ireland — 230V / 50Hz / BS1363
- Material processed: carbon fibre
- Temperature range: 0°C to 1000°C (depending on sensor)
- Internship project — CESI École d'ingénieurs
# =============================================================================
# Variac Control System — Flask Server
# =============================================================================
# Main Python backend for the Variac Control System.
# Responsibilities:
#   - Reads temperature from CalexConfig CSV (Sensor A) or Optris serial (Sensor B)
#   - Runs PID control loop to compute motor angle
#   - Sends ANGLE:XXX commands to Arduino Nano over USB serial
#   - Serves the web interface via Flask + SocketIO
#   - Manages thermal cycle execution
#
# Usage:
#   python app.py              (or double-click launch.bat / launch.command)
#
# Config: edit config.ini before starting (ports, PID params, sensor paths)
# =============================================================================

import os
import time
import csv
import threading
import configparser
from datetime import datetime
import platform

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import serial
import serial.tools.list_ports

# =============================================================================
# Configuration — read from config.ini
# =============================================================================
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
# utf-8-sig handles Windows BOM automatically
config.read(config_path, encoding='utf-8-sig')

HOST     = config.get('server',  'host',     fallback='0.0.0.0')
PORT     = int(config.get('server',  'port',     fallback='5001'))
BAUDRATE = int(config.get('arduino', 'baudrate', fallback='9600'))
TIMEOUT  = int(config.get('arduino', 'timeout',  fallback='2'))

# PID parameters — tuned for the real Variac + carbon fibre setup
PID_P    = float(config.get('pid', 'p',                  fallback='1.2'))
PID_I    = float(config.get('pid', 'i',                  fallback='0.05'))
PID_D    = float(config.get('pid', 'd',                  fallback='0.0'))
# Error threshold (°C) above which bang-bang control replaces PID
BANGBANG = float(config.get('pid', 'bangbang_threshold', fallback='20'))

# =============================================================================
# Sensor definitions — loaded from config.ini
# =============================================================================
SENSORS = {
    'sensor_1': {
        'id':       'sensor_1',
        'name':     config.get('sensor_1', 'name',     fallback='Sensor A — Low range'),
        'min_temp': int(config.get('sensor_1', 'min_temp', fallback='0')),
        'max_temp': int(config.get('sensor_1', 'max_temp', fallback='400')),
        'format':   config.get('sensor_1', 'format',   fallback='csv'),
        'port':     None,   # not used for CSV sensors
        'serial':   None,   # not used for CSV sensors
    },
    'sensor_2': {
        'id':       'sensor_2',
        'name':     config.get('sensor_2', 'name',     fallback='Sensor B — High range'),
        'min_temp': int(config.get('sensor_2', 'min_temp', fallback='300')),
        'max_temp': int(config.get('sensor_2', 'max_temp', fallback='800')),
        'format':   config.get('sensor_2', 'format',   fallback='csv'),
        'port':     None,
        'serial':   None,
    }
}

# =============================================================================
# CSV sensor helpers (Sensor A — CalexConfig)
# =============================================================================

def get_sensor_csv_dir(sensor_id):
    """Return the CSV output folder for the given sensor, based on OS."""
    if platform.system() == 'Windows':
        if sensor_id == 'sensor_1':
            return config.get('sensor_csv', 'csv_dir_1',
                fallback=r'C:\Users\Rahul.Samyal\OneDrive - University of Limerick\Research\Documents\CalexConfig log files')
        else:
            # Sensor 2 (Optris) does not use CSV — this path is unused
            return config.get('sensor_csv', 'csv_dir_2',
                fallback=r'C:\Users\Rahul.Samyal\OneDrive - University of Limerick\Research\Documents\Optris log files')
    else:
        # macOS: use local project subfolders
        if sensor_id == 'sensor_1':
            return os.path.join(os.path.dirname(__file__), 'CalexConfig', 'data')
        else:
            return os.path.join(os.path.dirname(__file__), 'Optris', 'data')

def get_sensor_csv_column(sensor_id=None):
    """Return the CSV column index for the temperature value of the given sensor."""
    if sensor_id is None:
        sensor_id = state.get('active_sensor', 'sensor_1')
    if sensor_id == 'sensor_1':
        return int(config.get('sensor_csv', 'column_1', fallback='3'))
    else:
        return int(config.get('sensor_csv', 'column_2', fallback='3'))

# Create local CSV folders on macOS if they don't exist
if platform.system() != 'Windows':
    os.makedirs(get_sensor_csv_dir('sensor_1'), exist_ok=True)
    os.makedirs(get_sensor_csv_dir('sensor_2'), exist_ok=True)

# =============================================================================
# Optris CT 3MH serial configuration (Sensor B)
# =============================================================================
# Protocol: send 0x01, receive 2 bytes, decode as:
#   temperature = (byte1 * 256 + byte2 - 1000) / 10   [degrees C]
# Source: CompactConnect manual, section 5.5, p.104
OPTRIS_PORT     = config.get('optris', 'port',     fallback='COM7')
OPTRIS_BAUDRATE = int(config.get('optris', 'baudrate', fallback='115200'))

# =============================================================================
# Logging — session CSV saved in /logs/
# =============================================================================
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

def clean_sensor_data_dir():
    # No longer deletes files — CalexConfig and Optris manage their own files
    pass

print(f"Config : {config_path}")
print(f"Server  : {HOST}:{PORT}")
print(f"Sensor 1 : {SENSORS['sensor_1']['name']} ({SENSORS['sensor_1']['min_temp']}–{SENSORS['sensor_1']['max_temp']}°C)")
print(f"Sensor 2 : {SENSORS['sensor_2']['name']} ({SENSORS['sensor_2']['min_temp']}–{SENSORS['sensor_2']['max_temp']}°C)")

# =============================================================================
# Flask + SocketIO setup
# =============================================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'variac_secret'
# threading async_mode required for background control loop + Flask routes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# =============================================================================
# Global system state
# =============================================================================
state = {
    'running':         False,          # True when PID loop is active
    'mode':            'manual',       # 'manual' or 'cycle'
    'target_temp':     0.0,            # Target temperature in °C
    'current_temp':    0.0,            # Last measured temperature in °C
    'current_angle':   0,              # Current motor angle in degrees
    'arduino_port':    None,           # Detected Arduino COM port
    'arduino':         None,           # serial.Serial object for Arduino
    'active_sensor':   'sensor_1',     # Currently selected sensor ID
    'sensor_csv_ok':   False,          # True if last CSV read succeeded
    'optris_serial':   None,           # serial.Serial object for Optris (sensor_2)
    'sensor_csv_file': None,           # Name of last CSV file read
    'cycle_config': {
        'temp_max':   500,             # Upper temperature target for cycles (°C)
        'hold_max':   30,              # Hold time at T max (seconds)
        'temp_min':   200,             # Lower temperature target for cycles (°C)
        'hold_min':   60,              # Hold time at T min (seconds)
        'num_cycles': 3,               # Number of cycles to run
    }
}

def active_sensor():
    """Return the dict for the currently selected sensor."""
    return SENSORS[state['active_sensor']]

# =============================================================================
# Arduino connection helpers
# =============================================================================

def find_arduino():
    """Return the serial port for the Arduino, from config.ini or auto-detect."""
    # Use forced port from config if set
    forced = config.get('arduino', 'port', fallback='')
    if forced:
        return forced.strip()
    # Auto-detect by USB description
    for port in serial.tools.list_ports.comports():
        desc = port.description.lower()
        if any(x in desc for x in ['arduino', 'ch340', 'usb serial', 'usbserial']):
            return port.device
    return None

def find_all_sensors():
    """Return all serial ports that are not the Arduino port."""
    arduino_port = state['arduino_port']
    found = []
    for port in serial.tools.list_ports.comports():
        if port.device != arduino_port:
            desc = port.description.lower()
            if any(x in desc for x in ['usb', 'serial', 'usbserial']):
                found.append(port.device)
    return found

def connect_arduino(port):
    """Open a serial connection to the Arduino Nano."""
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
        time.sleep(2)  # Wait for Arduino bootloader to finish
        ser.reset_input_buffer()
        print(f"Arduino connected: {port}")
        return ser
    except Exception as e:
        print(f"Arduino error: {e}")
        return None

def connect_sensor(sensor_id, port):
    """Open a serial connection to a sensor (legacy — not used for CSV or Optris)."""
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
        time.sleep(1)
        SENSORS[sensor_id]['port']   = port
        SENSORS[sensor_id]['serial'] = ser
        print(f"{SENSORS[sensor_id]['name']} connected: {port}")
        return True
    except Exception as e:
        print(f"Sensor {sensor_id} error: {e}")
        return False

def send_to_arduino(cmd, timeout=None):
    """Send a text command to the Arduino and return the response line."""
    if state['arduino']:
        try:
            if timeout is not None:
                state['arduino'].timeout = timeout
            state['arduino'].reset_input_buffer()
            state['arduino'].write(f"{cmd}\n".encode())
            response = state['arduino'].readline().decode().strip()
            return response
        except Exception as e:
            print(f"Arduino error: {e}")
            return None
    return None

# =============================================================================
# Optris CT 3MH serial helpers (Sensor B)
# =============================================================================

def connect_optris():
    """Open the serial connection to the Optris CT 3MH pyrometer on COM7.
    CompactConnect must be closed before calling this — only one connection allowed.
    """
    try:
        ser = serial.Serial(OPTRIS_PORT, OPTRIS_BAUDRATE, timeout=1)
        state['optris_serial'] = ser
        print(f"Optris connected: {OPTRIS_PORT} @ {OPTRIS_BAUDRATE}")
        return True
    except Exception as e:
        print(f"Optris connection failed: {e}")
        state['optris_serial'] = None
        return False

def disconnect_optris():
    """Close the serial connection to the Optris pyrometer."""
    if state['optris_serial']:
        try:
            state['optris_serial'].close()
        except:
            pass
        state['optris_serial'] = None

def read_optris_temperature():
    """Read one temperature measurement from the Optris CT 3MH via serial.

    Protocol (CompactConnect manual, p.104, section 5.5):
      Command : 0x01  (1 byte)
      Response: 2 bytes
      Formula : (byte1 * 256 + byte2 - 1000) / 10  → degrees C
    """
    ser = state['optris_serial']
    if not ser or not ser.is_open:
        return None
    try:
        ser.reset_input_buffer()
        ser.write(bytes([0x01]))   # Request process temperature
        ser.flush()
        response = ser.read(2)    # Expect exactly 2 bytes back
        if len(response) < 2:
            return None
        byte1, byte2 = response[0], response[1]
        temp = (byte1 * 256 + byte2 - 1000) / 10.0
        return temp
    except Exception as e:
        print(f"Optris read error: {e}")
        return None

# =============================================================================
# Temperature reading — routes to the correct sensor
# =============================================================================

def get_latest_csv(sensor_id=None):
    """Return the path of the most recently modified CSV file for the given sensor."""
    if sensor_id is None:
        sensor_id = state.get('active_sensor', 'sensor_1')
    csv_dir = get_sensor_csv_dir(sensor_id)
    if not csv_dir or not os.path.isdir(csv_dir):
        return None
    files = [
        os.path.join(csv_dir, f)
        for f in os.listdir(csv_dir)
        if f.lower().endswith('.csv')
    ]
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def read_temperature():
    """Read temperature from the active sensor.
    - sensor_1 (CalexConfig): parse the most recent CSV file
    - sensor_2 (Optris CT):   query via serial port
    """
    sensor_id = state.get('active_sensor', 'sensor_1')

    # ── Sensor 2 — Optris via serial port ────────────────────────────────────
    if sensor_id == 'sensor_2':
        temp = read_optris_temperature()
        if temp is not None:
            state['current_temp']  = temp
            state['sensor_csv_ok'] = True
            return temp
        # Return last known value if serial read fails
        state['sensor_csv_ok'] = False
        return state['current_temp']

    # ── Sensor 1 — CalexConfig CSV ────────────────────────────────────────────
    csv_path = get_latest_csv()
    if not csv_path:
        # Simulation fallback if no CSV present (e.g. on macOS during development)
        target  = state['target_temp']
        current = state['current_temp']
        diff    = target - current
        noise   = (time.time() % 1 - 0.5) * 2
        state['current_temp'] = current + diff * 0.05 + noise
        return state['current_temp']
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        # Scan from the end to find the last valid data row
        # CalexConfig format: Time, Sample No., Unfiltered, Filtered, Sensor Temp
        # First 5 rows are headers; data rows have at least 5 comma-separated fields
        col = get_sensor_csv_column()
        for line in reversed(lines):
            parts = line.strip().split(',')
            if len(parts) >= col + 1:
                try:
                    temp = float(parts[col])
                    state['current_temp']  = temp
                    state['sensor_csv_ok'] = True
                    return temp
                except ValueError:
                    continue
    except Exception as e:
        print(f"CSV read error: {e}")
        state['sensor_csv_ok'] = False
    return state['current_temp']

# =============================================================================
# Session logging — one CSV file per session in /logs/
# =============================================================================
log_file   = None
log_writer = None

def init_log():
    """Create a new log CSV file for the current session."""
    global log_file, log_writer
    sensor_name = active_sensor()['name'].replace(' ', '_').replace('—', '').strip()
    filename = os.path.join(LOG_DIR, f"log_{sensor_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    log_file   = open(filename, 'w', newline='')
    log_writer = csv.writer(log_file)
    log_writer.writerow(['timestamp', 'sensor', 'measured_temp', 'target_temp', 'angle', 'mode'])
    print(f"Log: {filename}")

def write_log(temp, target, angle, mode):
    """Append one data row to the current session log."""
    if log_writer:
        log_writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            active_sensor()['name'],
            round(temp, 2), round(target, 2), angle, mode
        ])
        log_file.flush()

# =============================================================================
# PID control loop — runs in a background thread
# =============================================================================

def control_loop():
    """Background thread: read temperature, compute PID output, send ANGLE command.

    Two-phase control strategy:
      Phase 1 — Bang-bang: if |error| > BANGBANG threshold, run motor at full
                speed toward the target for fast initial ramp-up.
      Phase 2 — PID:       fine-tune motor angle when close to the target.
    """
    integral   = 0.0
    prev_error = 0.0
    MAX_ANGLE  = 340   # Maximum motor angle in degrees (maps to max Variac voltage)

    while True:
        if state['running']:
            temp   = read_temperature()
            target = state['target_temp']
            error  = target - temp
            sensor = active_sensor()

            if target > 0:
                if abs(error) > BANGBANG:
                    # Bang-bang: go to max angle if below target, 0° if above
                    new_angle = MAX_ANGLE if error > 0 else 0
                    integral  = 0.0   # Reset integrator to prevent wind-up
                else:
                    # Standard PID calculation (0.5s sample period)
                    integral   += error * 0.5
                    derivative  = (error - prev_error) / 0.5
                    output      = PID_P * error + PID_I * integral + PID_D * derivative
                    new_angle   = state['current_angle'] + int(output)
                    new_angle   = max(0, min(MAX_ANGLE, new_angle))
                prev_error = error

                # Send command only if the angle has changed
                if new_angle != state['current_angle']:
                    print(f"PID -> ANGLE:{new_angle} (temp={round(temp,1)} target={target} error={round(error,1)})")
                    # Short timeout: don't block the loop waiting for a slow move
                    send_to_arduino(f'ANGLE:{new_angle}', timeout=0.1)
                    state['current_angle'] = new_angle
            else:
                # Target is 0 — return motor to 0° (Variac at 0V)
                if state['current_angle'] != 0:
                    send_to_arduino('ANGLE:0')
                    state['current_angle'] = 0
                integral = 0.0

            write_log(temp, target, state['current_angle'], state['mode'])
            socketio.emit('update', {
                'temp':       round(temp, 1),
                'target':     target,
                'angle':      state['current_angle'],
                'mode':       state['mode'],
                'time':       datetime.now().strftime('%H:%M:%S'),
                'sensor_min': sensor['min_temp'],
                'sensor_max': sensor['max_temp'],
            })
        else:
            # Reset PID state when not running
            integral   = 0.0
            prev_error = 0.0
        time.sleep(0.5)

# =============================================================================
# Flask routes
# =============================================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    """Return full system status as JSON (used by the web interface on connect)."""
    sensor = active_sensor()
    return jsonify({
        'running':         state['running'],
        'mode':            state['mode'],
        'target_temp':     state['target_temp'],
        'current_temp':    round(state['current_temp'], 1),
        'angle':           state['current_angle'],
        'arduino_port':    state['arduino_port'],
        'arduino_ok':      state['arduino'] is not None,
        'active_sensor':   state['active_sensor'],
        'sensor_name':     sensor['name'],
        'sensor_min':      sensor['min_temp'],
        'sensor_max':      sensor['max_temp'],
        'sensor_port':     sensor['port'],
        'sensor_ok':       sensor['serial'] is not None,
        'sensor_csv_ok':   state['sensor_csv_ok'],
        'sensor_csv_file': os.path.basename(get_latest_csv()) if get_latest_csv() else None,
        'sensors': {k: {
            'id':       v['id'],
            'name':     v['name'],
            'min_temp': v['min_temp'],
            'max_temp': v['max_temp'],
            'port':     v['port'],
            'ok':       v['serial'] is not None,
        } for k, v in SENSORS.items()}
    })

@app.route('/api/scan_ports', methods=['POST'])
def scan_ports():
    """Detect Arduino port and attempt connection. Called by Autotest."""
    state['arduino_port'] = find_arduino()
    if state['arduino_port'] and state['arduino'] is None:
        state['arduino'] = connect_arduino(state['arduino_port'])
    # Sensors are not connected here — CalexConfig uses CSV, Optris connects on sensor select
    print(f"Arduino: {state['arduino_port']}")
    return jsonify({
        'arduino_port': state['arduino_port'],
        'arduino_ok':   state['arduino'] is not None,
        'sensor_ports': [],
        'sensors': {k: {'port': None, 'ok': False} for k, v in SENSORS.items()}
    })

@app.route('/api/set_sensor/<sensor_id>', methods=['POST'])
def set_sensor(sensor_id):
    """Switch the active sensor. Opens Optris serial if switching to sensor_2,
    closes it when switching away.
    """
    if sensor_id not in SENSORS:
        return jsonify({'ok': False, 'error': 'Unknown sensor'}), 400
    old_sensor = state['active_sensor']
    state['active_sensor'] = sensor_id
    sensor = active_sensor()
    # Clamp target temperature to the new sensor's valid range
    state['target_temp'] = max(sensor['min_temp'],
                          min(state['target_temp'], sensor['max_temp']))
    print(f"Active sensor: {sensor['name']}")

    # Manage Optris serial connection based on sensor selection
    if sensor_id == 'sensor_2' and old_sensor != 'sensor_2':
        connect_optris()
    elif sensor_id != 'sensor_2' and old_sensor == 'sensor_2':
        disconnect_optris()

    socketio.emit('sensor_changed', {
        'active_sensor': sensor_id,
        'sensor_name':   sensor['name'],
        'sensor_min':    sensor['min_temp'],
        'sensor_max':    sensor['max_temp'],
    })
    return jsonify({'ok': True, 'sensor': sensor})

@app.route('/api/test_arduino', methods=['POST'])
def test_arduino():
    """Autotest: send POS command and check for a valid response."""
    if state['arduino'] is None:
        return jsonify({'ok': False, 'response': 'Arduino not connected'})
    try:
        state['arduino'].timeout = TIMEOUT
        state['arduino'].reset_input_buffer()
        state['arduino'].write(b'POS\n')
        time.sleep(0.5)
        response = state['arduino'].readline().decode().strip()
        ok = len(response) > 0
        return jsonify({'ok': ok, 'response': response if ok else 'No response — flash Arduino code first'})
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e)})

@app.route('/api/start', methods=['POST'])
def start():
    """Start the PID control loop."""
    state['running'] = True
    init_log()
    return jsonify({'status': 'started'})

@app.route('/api/stop', methods=['POST'])
def stop():
    """Stop the PID loop and return the motor to 0° (Variac at 0V).
    Motor power is NOT cut — holding torque is maintained.
    """
    state['running'] = False
    resp = send_to_arduino('ANGLE:0')
    if resp and resp.startswith('ACK:'):
        state['current_angle'] = 0
    return jsonify({'status': 'stopped'})

@app.route('/api/set_target/<temp>', methods=['POST'])
def set_target(temp):
    """Set the target temperature. Value is clamped to the active sensor range."""
    try:
        temp = float(temp)
    except ValueError:
        return jsonify({'status': 'error'}), 400
    sensor = active_sensor()
    temp = max(float(sensor['min_temp']), min(temp, float(sensor['max_temp'])))
    state['target_temp'] = temp
    return jsonify({'status': 'ok', 'target': temp})

@app.route('/api/set_cycle', methods=['POST'])
def set_cycle():
    """Update cycle configuration (T max, T min, hold times, number of cycles)."""
    data = request.json
    state['cycle_config'].update(data)
    return jsonify({'status': 'ok'})

# =============================================================================
# Motor direct control routes (used by the Motor tab)
# =============================================================================

@app.route('/api/test_motor', methods=['POST'])
def test_motor():
    """Autotest: move motor to 10°, wait for ACK, return to 0°.
    Confirms that the TB6600 driver is powered and responsive.
    """
    if state['arduino'] is None:
        return jsonify({'ok': False, 'response': 'Arduino not connected'})
    try:
        state['arduino'].timeout = 5
        state['arduino'].reset_input_buffer()
        state['arduino'].write(b'ANGLE:10\n')
        # Read lines until ACK is found or 5-second timeout expires
        response = ''
        deadline = time.time() + 5
        while time.time() < deadline:
            line = state['arduino'].readline().decode().strip()
            if line.startswith('ACK:'):
                response = line
                break
            if not line:
                time.sleep(0.1)
        ok = response.startswith('ACK:')
        if ok:
            # Return to home position after test
            state['arduino'].reset_input_buffer()
            state['arduino'].write(b'ANGLE:0\n')
            deadline2 = time.time() + 5
            while time.time() < deadline2:
                line = state['arduino'].readline().decode().strip()
                if line.startswith('ACK:') or not line:
                    break
        return jsonify({
            'ok': ok,
            'response': response if ok else 'No ACK within 5s — check TB6600 wiring and power'
        })
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e)})

@app.route('/api/motor/go/<angle>', methods=['POST'])
def motor_go(angle):
    """Move motor to an absolute angle (0–380°). Returns actual position in degrees."""
    try:
        angle = int(angle)
    except ValueError:
        return jsonify({'ok': False}), 400
    if state['arduino'] is None:
        return jsonify({'ok': False, 'response': 'Arduino not connected'})
    angle = max(0, min(380, angle))
    try:
        state['arduino'].reset_input_buffer()
        state['arduino'].write(f'ANGLE:{angle}\n'.encode())
        response = ''
        for _ in range(15):
            line = state['arduino'].readline().decode().strip()
            if line.startswith('ACK:'):
                response = line
                break
            if not line:
                break
        ok = response.startswith('ACK:')
        if ok:
            # Convert micro-steps back to degrees for display
            microsteps    = int(response.split(':')[1])
            angle_actual  = round(microsteps * 360 / (200 * 16), 1)
        else:
            angle_actual = angle
        return jsonify({'ok': ok, 'angle': angle_actual, 'response': response})
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e)})

@app.route('/api/motor/reset', methods=['POST'])
def motor_reset():
    """Send RESETPOS to declare the current physical position as 0° (no movement)."""
    if state['arduino'] is None:
        return jsonify({'ok': False, 'response': 'Arduino not connected'})
    try:
        state['arduino'].reset_input_buffer()
        state['arduino'].write(b'RESETPOS\n')
        time.sleep(0.3)
        response = state['arduino'].readline().decode().strip()
        ok = response == 'RESET_OK'
        return jsonify({'ok': ok, 'response': response})
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e)})

@app.route('/api/motor/speed/<delay_us>', methods=['POST'])
def motor_speed(delay_us):
    """Set the step pulse delay in microseconds (50–5000). Lower = faster."""
    if state['arduino'] is None:
        return jsonify({'ok': False, 'response': 'Arduino not connected'})
    try:
        delay_us = int(delay_us)
    except ValueError:
        return jsonify({'ok': False, 'response': 'invalid value'}), 400
    delay_us = max(50, min(5000, delay_us))
    try:
        state['arduino'].reset_input_buffer()
        state['arduino'].write(f'SPEED:{delay_us}\n'.encode())
        time.sleep(0.3)
        response = state['arduino'].readline().decode().strip()
        return jsonify({'ok': True, 'response': response})
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e)})

# =============================================================================
# Sensor autotest route
# =============================================================================

@app.route('/api/test_sensor', methods=['POST'])
def test_sensor():
    """Autotest: verify the active sensor is reachable and returning live data.
    - Sensor 1 (CalexConfig): finds latest CSV, checks file age (<10s = live)
    - Sensor 2 (Optris):      queries COM7 and decodes a temperature reading
    """
    sensor_id = state.get('active_sensor', 'sensor_1')
    sensor = active_sensor()

    # ── Sensor 2 — Optris via serial port ────────────────────────────────────
    if sensor_id == 'sensor_2':
        if not state.get('optris_serial') or not state['optris_serial'].is_open:
            connect_optris()
        temp = read_optris_temperature()
        if temp is not None:
            return jsonify({
                'ok': True,
                'response': f'{temp:.1f}°C — Optris connected on {OPTRIS_PORT}',
                'temp': temp,
                'file': f'Serial {OPTRIS_PORT}'
            })
        else:
            return jsonify({
                'ok': False,
                'response': f'No response from Optris on {OPTRIS_PORT} — close CompactConnect first',
                'temp': None,
                'file': None
            })

    # ── Sensor 1 — CalexConfig CSV ────────────────────────────────────────────
    csv_dir  = get_sensor_csv_dir(sensor_id)
    csv_path = get_latest_csv(sensor_id)

    if not csv_path:
        msg = 'No CSV file found'
        if not csv_dir:
            msg = 'csv_dir not configured in config.ini'
        elif not os.path.isdir(csv_dir):
            msg = f'Folder not found: {csv_dir}'
        return jsonify({'ok': False, 'response': msg, 'temp': None, 'file': None})

    # Double-read to verify recording is active (CalexConfig writes 1 row/second)
    try:
        temp1    = read_temperature()
        filename = os.path.basename(csv_path)
        time.sleep(3)           # Wait for at least 3 new rows to be written
        temp2    = read_temperature()

        if temp1 is None or temp2 is None:
            return jsonify({'ok': False, 'response': f'Could not read temperature from {filename}',
                            'temp': None, 'file': filename})

        # Check file age — if older than 10s, recording is likely not running
        file_age = time.time() - os.path.getmtime(csv_path)
        if file_age > 10:
            return jsonify({
                'ok': False,
                'response': f'CSV file not updating — last update {int(file_age)}s ago. Start recording in CalexConfig.',
                'temp': temp2,
                'file': filename
            })
        return jsonify({
            'ok': True,
            'response': f'{temp2:.1f}°C — recording active (file updated {int(file_age)}s ago)',
            'temp': temp2,
            'file': filename
        })
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e), 'temp': None, 'file': None})

# =============================================================================
# Cycle mode routes
# =============================================================================

@app.route('/api/start_cycle', methods=['POST'])
def start_cycle():
    """Start a thermal cycle sequence in a background thread."""
    state['running'] = True
    state['mode']    = 'cycle'
    init_log()
    threading.Thread(target=run_cycle, daemon=True).start()
    return jsonify({'status': 'cycle_started'})

def run_cycle():
    """Execute the configured number of thermal cycles.

    Each cycle has 4 steps:
      1. Ramp up to T max (wait until within ±5°C)
      2. Hold at T max for hold_max seconds
      3. Ramp down to T min (wait until within ±5°C)
      4. Hold at T min for hold_min seconds
    Sends 'cycle_update' SocketIO events at each step change.
    """
    cfg        = state['cycle_config']
    temp_max   = cfg['temp_max']
    temp_min   = cfg['temp_min']
    hold_max   = cfg['hold_max']
    hold_min   = cfg['hold_min']
    num_cycles = cfg['num_cycles']
    total_steps = num_cycles * 4
    steps_done  = 0

    def emit_cycle(step, current_cycle, complete=False):
        progress = steps_done / total_steps if total_steps > 0 else 0
        socketio.emit('cycle_update', {
            'step':          step,
            'current_cycle': current_cycle,
            'num_cycles':    num_cycles,
            'progress':      round(progress, 2),
            'complete':      complete,
        })

    for cycle_num in range(1, num_cycles + 1):
        if not state['running']: break

        # Step 1 — Ramp up to T max
        state['target_temp'] = temp_max
        emit_cycle(1, cycle_num)
        while state['running'] and abs(state['current_temp'] - temp_max) > 5:
            time.sleep(1)
        steps_done += 1
        if not state['running']: break

        # Step 2 — Hold at T max
        emit_cycle(2, cycle_num)
        for _ in range(int(hold_max)):
            if not state['running']: break
            time.sleep(1)
        steps_done += 1
        if not state['running']: break

        # Step 3 — Ramp down to T min
        state['target_temp'] = temp_min
        emit_cycle(3, cycle_num)
        while state['running'] and abs(state['current_temp'] - temp_min) > 5:
            time.sleep(1)
        steps_done += 1
        if not state['running']: break

        # Step 4 — Hold at T min
        emit_cycle(4, cycle_num)
        for _ in range(int(hold_min)):
            if not state['running']: break
            time.sleep(1)
        steps_done += 1

    # Final step — return to 0° and stop
    state['target_temp'] = 0
    state['running']     = False
    emit_cycle(5, num_cycles, complete=True)
    print("Cycle complete")

# =============================================================================
# Shutdown route
# =============================================================================

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """Stop the Python server and close the terminal window.
    Called by the Disconnect button in the web interface.
    """
    def stop_server():
        time.sleep(2)   # Let the HTTP response reach the browser first
        system = platform.system()
        if system == 'Darwin':  # macOS
            os.system("osascript -e 'tell application \"Safari\" to close (tabs of windows whose URL contains \"localhost:5001\")' 2>/dev/null")
            os.system("osascript -e 'delay 1' -e 'tell application \"Terminal\" to close (every window whose name contains \"launch\")' &")
        elif system == 'Windows':
            os.system('taskkill /F /FI "WINDOWTITLE eq *variac*" >nul 2>&1')
            os.system('taskkill /F /IM cmd.exe >nul 2>&1')
        time.sleep(0.5)
        os.kill(os.getpid(), 9)  # Hard kill the Python process
    threading.Thread(target=stop_server, daemon=True).start()
    return jsonify({'status': 'shutting_down'})

@app.route('/api/config')
def get_config():
    """Return current configuration as JSON (for debugging)."""
    return jsonify({
        'port':     PORT,
        'baudrate': BAUDRATE,
        'pid':      {'p': PID_P, 'i': PID_I, 'd': PID_D, 'bangbang': BANGBANG},
        'sensors':  {k: {'name': v['name'], 'min': v['min_temp'], 'max': v['max_temp']} for k, v in SENSORS.items()}
    })

# =============================================================================
# SocketIO events
# =============================================================================

@socketio.on('connect')
def on_connect(auth=None):
    """Send current system state to a newly connected browser client."""
    print('Client connected')
    sensor = active_sensor()
    emit('status', {
        'running':       state['running'],
        'mode':          state['mode'],
        'target_temp':   state['target_temp'],
        'current_temp':  round(state['current_temp'], 1),
        'angle':         state['current_angle'],
        'arduino_port':  state['arduino_port'],
        'arduino_ok':    state['arduino'] is not None,
        'active_sensor': state['active_sensor'],
        'sensor_name':   sensor['name'],
        'sensor_min':    sensor['min_temp'],
        'sensor_max':    sensor['max_temp'],
    })

# =============================================================================
# Entry point
# =============================================================================

if __name__ == '__main__':
    print("=" * 44)
    print("   VARIAC CONTROL SYSTEM")
    print("=" * 44)

    # Detect and connect Arduino
    state['arduino_port'] = find_arduino()
    print(f"Arduino: {state['arduino_port'] or 'Not detected'}")
    if state['arduino_port']:
        state['arduino'] = connect_arduino(state['arduino_port'])

    # Print sensor status (sensors connect on demand, not at startup)
    sensor_ports = find_all_sensors()
    for i, (sid, s) in enumerate(SENSORS.items()):
        if i < len(sensor_ports):
            connect_sensor(sid, sensor_ports[i])
        print(f"{s['name']}: {s['port'] or 'Not detected'}")

    # Start PID control loop in background thread
    t = threading.Thread(target=control_loop, daemon=True)
    t.start()

    print(f"\n🌍 http://localhost:{PORT}")
    print("   Press CTRL+C to stop\n")
    socketio.run(app, host=HOST, port=PORT, debug=False)

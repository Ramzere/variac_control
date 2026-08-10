import os
import time
import csv
import threading
import configparser
from datetime import datetime

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import serial
import serial.tools.list_ports

# ── Config ───────────────────────────────────────────────────────────────────
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
config.read(config_path)

HOST     = config.get('server',  'host',     fallback='0.0.0.0')
PORT     = int(config.get('server',  'port',     fallback='5001'))
BAUDRATE = int(config.get('arduino', 'baudrate', fallback='9600'))
TIMEOUT  = int(config.get('arduino', 'timeout',  fallback='2'))
PID_P    = float(config.get('pid', 'p',                   fallback='1.2'))
PID_I    = float(config.get('pid', 'i',                   fallback='0.05'))
PID_D    = float(config.get('pid', 'd',                   fallback='0.0'))
BANGBANG = float(config.get('pid', 'bangbang_threshold',  fallback='20'))

# ── Définition des sondes depuis config.ini ───────────────────────────────────
SENSORS = {
    'sensor_1': {
        'id':       'sensor_1',
        'name':     config.get('sensor_1', 'name',     fallback='Sensor A — Low range'),
        'min_temp': int(config.get('sensor_1', 'min_temp', fallback='0')),
        'max_temp': int(config.get('sensor_1', 'max_temp', fallback='400')),
        'format':   config.get('sensor_1', 'format',   fallback='csv'),
        'port':     None,
        'serial':   None,
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

# Dossier logs
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

print(f"Config : {config_path}")
print(f"Serveur : {HOST}:{PORT}")
print(f"Sensor 1 : {SENSORS['sensor_1']['name']} ({SENSORS['sensor_1']['min_temp']}–{SENSORS['sensor_1']['max_temp']}°C)")
print(f"Sensor 2 : {SENSORS['sensor_2']['name']} ({SENSORS['sensor_2']['min_temp']}–{SENSORS['sensor_2']['max_temp']}°C)")

# ── Flask + SocketIO ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = 'variac_secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── État global ───────────────────────────────────────────────────────────────
state = {
    'running':        False,
    'mode':           'manual',
    'target_temp':    0.0,
    'current_temp':   0.0,
    'current_angle':  0,
    'arduino_port':   None,
    'arduino':        None,
    'active_sensor':  'sensor_1',   # sonde active par défaut
    'cycle_config': {
        'temp_max':   500,
        'hold_max':   30,
        'temp_min':   200,
        'hold_min':   60,
        'num_cycles': 3,
    }
}

# ── Helpers sonde active ──────────────────────────────────────────────────────
def active_sensor():
    return SENSORS[state['active_sensor']]

# ── Détection ports ───────────────────────────────────────────────────────────
def find_arduino():
    for port in serial.tools.list_ports.comports():
        desc = port.description.lower()
        if any(x in desc for x in ['arduino', 'ch340', 'usb serial', 'usbserial']):
            return port.device
    return None

def find_all_sensors():
    """Trouve tous les ports USB qui ne sont pas l'Arduino."""
    arduino_port = state['arduino_port']
    found = []
    for port in serial.tools.list_ports.comports():
        if port.device != arduino_port:
            desc = port.description.lower()
            if any(x in desc for x in ['usb', 'serial', 'usbserial']):
                found.append(port.device)
    return found

def connect_arduino(port):
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
        time.sleep(2)
        ser.reset_input_buffer()
        print(f"Arduino connecté : {port}")
        return ser
    except Exception as e:
        print(f"Arduino error: {e}")
        return None

def connect_sensor(sensor_id, port):
    try:
        ser = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
        time.sleep(1)
        SENSORS[sensor_id]['port']   = port
        SENSORS[sensor_id]['serial'] = ser
        print(f"{SENSORS[sensor_id]['name']} connecté : {port}")
        return True
    except Exception as e:
        print(f"Sensor {sensor_id} error: {e}")
        return False

# ── Envoi commande Arduino ────────────────────────────────────────────────────
def send_to_arduino(cmd):
    if state['arduino']:
        try:
            state['arduino'].reset_input_buffer()
            state['arduino'].write(f"{cmd}\n".encode())
            response = state['arduino'].readline().decode().strip()
            return response
        except Exception as e:
            print(f"Arduino error: {e}")
            return None
    return None

# ── Lecture température ───────────────────────────────────────────────────────
def read_temperature():
    # TODO : remplacer par lecture réelle du port série de la sonde active
    # sensor = active_sensor()
    # if sensor['serial']:
    #     line = sensor['serial'].readline().decode().strip()
    #     return float(line.split(',')[1])  # adapter selon le format CSV réel
    target  = state['target_temp']
    current = state['current_temp']
    diff    = target - current
    noise   = (time.time() % 1 - 0.5) * 2
    state['current_temp'] = current + diff * 0.05 + noise
    return state['current_temp']

# ── Log CSV ───────────────────────────────────────────────────────────────────
log_file   = None
log_writer = None

def init_log():
    global log_file, log_writer
    sensor_name = active_sensor()['name'].replace(' ', '_').replace('—', '').strip()
    filename = os.path.join(LOG_DIR, f"log_{sensor_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    log_file   = open(filename, 'w', newline='')
    log_writer = csv.writer(log_file)
    log_writer.writerow(['timestamp', 'sensor', 'measured_temp', 'target_temp', 'angle', 'mode'])
    print(f"Log : {filename}")

def write_log(temp, target, angle, mode):
    if log_writer:
        log_writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            active_sensor()['name'],
            round(temp, 2), round(target, 2), angle, mode
        ])
        log_file.flush()

# ── Boucle de contrôle ────────────────────────────────────────────────────────
def control_loop():
    while True:
        if state['running']:
            temp = read_temperature()
            write_log(temp, state['target_temp'], state['current_angle'], state['mode'])
            sensor = active_sensor()
            socketio.emit('update', {
                'temp':       round(temp, 1),
                'target':     state['target_temp'],
                'angle':      state['current_angle'],
                'mode':       state['mode'],
                'time':       datetime.now().strftime('%H:%M:%S'),
                'sensor_min': sensor['min_temp'],
                'sensor_max': sensor['max_temp'],
            })
        time.sleep(0.5)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    sensor = active_sensor()
    return jsonify({
        'running':        state['running'],
        'mode':           state['mode'],
        'target_temp':    state['target_temp'],
        'current_temp':   round(state['current_temp'], 1),
        'angle':          state['current_angle'],
        'arduino_port':   state['arduino_port'],
        'arduino_ok':     state['arduino'] is not None,
        'active_sensor':  state['active_sensor'],
        'sensor_name':    sensor['name'],
        'sensor_min':     sensor['min_temp'],
        'sensor_max':     sensor['max_temp'],
        'sensor_port':    sensor['port'],
        'sensor_ok':      sensor['serial'] is not None,
        'sensors':        {k: {
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
    # Arduino
    state['arduino_port'] = find_arduino()
    if state['arduino_port'] and state['arduino'] is None:
        state['arduino'] = connect_arduino(state['arduino_port'])

    # Sondes — assigne automatiquement les ports trouvés
    sensor_ports = find_all_sensors()
    for i, (sensor_id, sensor) in enumerate(SENSORS.items()):
        if i < len(sensor_ports) and sensor['serial'] is None:
            connect_sensor(sensor_id, sensor_ports[i])

    print(f"Arduino: {state['arduino_port']} | Sensors: {sensor_ports}")
    return jsonify({
        'arduino_port': state['arduino_port'],
        'arduino_ok':   state['arduino'] is not None,
        'sensor_ports': sensor_ports,
        'sensors': {k: {'port': v['port'], 'ok': v['serial'] is not None} for k, v in SENSORS.items()}
    })

@app.route('/api/set_sensor/<sensor_id>', methods=['POST'])
def set_sensor(sensor_id):
    if sensor_id not in SENSORS:
        return jsonify({'ok': False, 'error': 'Unknown sensor'}), 400
    state['active_sensor'] = sensor_id
    sensor = active_sensor()
    # Remet la température cible dans la plage de la nouvelle sonde
    state['target_temp'] = max(sensor['min_temp'],
                          min(state['target_temp'], sensor['max_temp']))
    print(f"Sonde active : {sensor['name']}")
    socketio.emit('sensor_changed', {
        'active_sensor': sensor_id,
        'sensor_name':   sensor['name'],
        'sensor_min':    sensor['min_temp'],
        'sensor_max':    sensor['max_temp'],
    })
    return jsonify({'ok': True, 'sensor': sensor})

@app.route('/api/test_arduino', methods=['POST'])
def test_arduino():
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
    state['running'] = True
    init_log()
    return jsonify({'status': 'started'})

@app.route('/api/stop', methods=['POST'])
def stop():
    state['running'] = False
    send_to_arduino('STOP')
    return jsonify({'status': 'stopped'})

@app.route('/api/set_target/<float:temp>', methods=['POST'])
def set_target(temp):
    sensor = active_sensor()
    temp = max(sensor['min_temp'], min(temp, sensor['max_temp']))
    state['target_temp'] = temp
    return jsonify({'status': 'ok', 'target': temp})

@app.route('/api/set_cycle', methods=['POST'])
def set_cycle():
    data = request.json
    state['cycle_config'].update(data)
    return jsonify({'status': 'ok'})

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    def stop_server():
        time.sleep(2)
        os.system("osascript -e 'tell application \"Safari\" to close (tabs of windows whose URL contains \"localhost:5001\")' 2>/dev/null")
        os.system("osascript -e 'delay 1' -e 'tell application \"Terminal\" to close (every window whose name contains \"launch\")' &")
        time.sleep(0.5)
        os.kill(os.getpid(), 9)
    threading.Thread(target=stop_server, daemon=True).start()
    return jsonify({'status': 'shutting_down'})

@app.route('/api/config')
def get_config():
    return jsonify({
        'port': PORT, 'baudrate': BAUDRATE,
        'pid':  {'p': PID_P, 'i': PID_I, 'd': PID_D, 'bangbang': BANGBANG},
        'sensors': {k: {'name': v['name'], 'min': v['min_temp'], 'max': v['max_temp']} for k, v in SENSORS.items()}
    })

# ── SocketIO ──────────────────────────────────────────────────────────────────
@socketio.on('connect')
def on_connect(auth=None):
    print('Client connecté')
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

# ── Démarrage ─────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 44)
    print("   VARIAC CONTROL SYSTEM")
    print("=" * 44)
    state['arduino_port'] = find_arduino()
    print(f"Arduino : {state['arduino_port'] or 'Non détecté'}")
    if state['arduino_port']:
        state['arduino'] = connect_arduino(state['arduino_port'])
    sensor_ports = find_all_sensors()
    for i, (sid, s) in enumerate(SENSORS.items()):
        if i < len(sensor_ports):
            connect_sensor(sid, sensor_ports[i])
        print(f"{s['name']} : {s['port'] or 'Non détecté'}")
    t = threading.Thread(target=control_loop, daemon=True)
    t.start()
    print(f"\n🌍 http://localhost:{PORT}")
    print("   CTRL+C pour arrêter\n")
    socketio.run(app, host=HOST, port=PORT, debug=False)

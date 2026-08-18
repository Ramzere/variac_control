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

# ── Config ───────────────────────────────────────────────────────────────────
config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
config.read(config_path, encoding='utf-8-sig')

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

# ── Config capteur CSV — un dossier par capteur ──────────────────────────────
def get_sensor_csv_dir(sensor_id):
    """Retourne le dossier CSV pour un capteur donné selon l'OS."""
    if platform.system() == 'Windows':
        if sensor_id == 'sensor_1':
            return config.get('sensor_csv', 'csv_dir_1',
                fallback=r'C:\Users\Rahul.Samyal\OneDrive - University of Limerick\Research\Documents\CalexConfig log files')
        else:
            return config.get('sensor_csv', 'csv_dir_2',
                fallback=r'C:\Users\Rahul.Samyal\OneDrive - University of Limerick\Research\Documents\Optais log files')
    else:
        # Mac : dossiers locaux au projet
        if sensor_id == 'sensor_1':
            return os.path.join(os.path.dirname(__file__), 'CalexConfig', 'data')
        else:
            return os.path.join(os.path.dirname(__file__), 'Optais', 'data')

def get_sensor_csv_column(sensor_id=None):
    if sensor_id is None:
        sensor_id = state.get('active_sensor', 'sensor_1')
    if sensor_id == 'sensor_1':
        return int(config.get('sensor_csv', 'column_1', fallback='3'))
    else:
        return int(config.get('sensor_csv', 'column_2', fallback='3'))
    
# Créer les dossiers Mac si absents
if platform.system() != 'Windows':
    os.makedirs(get_sensor_csv_dir('sensor_1'), exist_ok=True)
    os.makedirs(get_sensor_csv_dir('sensor_2'), exist_ok=True)

# Dossier logs
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
# ── Nettoyage du dossier CalexConfig/data au démarrage ───────────────────────
def clean_sensor_data_dir():
    # On ne supprime plus les fichiers — CalexConfig/Optais gèrent leurs propres fichiers
    pass

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
    'sensor_csv_ok':  False,
    'sensor_csv_file': None,
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
    # Si port forcé dans config.ini, l'utiliser directement
    forced = config.get('arduino', 'port', fallback='')
    if forced:
        return forced.strip()
    # Sinon détection automatique
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
def send_to_arduino(cmd, timeout=None):
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

# ── Lecture température ───────────────────────────────────────────────────────
def get_latest_csv(sensor_id=None):
    """Retourne le fichier CSV le plus récent pour le capteur actif."""
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
    """Lit la dernière température du CSV CalexConfig le plus récent."""
    csv_path = get_latest_csv()
    if not csv_path:
        # Fallback simulation si pas de fichier
        target  = state['target_temp']
        current = state['current_temp']
        diff    = target - current
        noise   = (time.time() % 1 - 0.5) * 2
        state['current_temp'] = current + diff * 0.05 + noise
        return state['current_temp']
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        # Cherche la dernière ligne avec des données valides
        # Format : Time, Sample No., Unfiltered, Filtered, Sensor
        # Les 5 premières lignes sont des headers
        for line in reversed(lines):
            parts = line.strip().split(',')
            col = get_sensor_csv_column()
            if len(parts) >= col + 1:
                try:
                    temp = float(parts[col])
                    state['current_temp'] = temp
                    state['sensor_csv_ok'] = True
                    return temp
                except ValueError:
                    continue
    except Exception as e:
        print(f"CSV read error: {e}")
        state['sensor_csv_ok'] = False
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
    integral = 0.0
    prev_error = 0.0
    # Position moteur : 0 = 0V, MAX_ANGLE = tension max
    MAX_ANGLE = 340

    while True:
        if state['running']:
            temp   = read_temperature()
            target = state['target_temp']
            error  = target - temp
            sensor = active_sensor()

            # ── PID ────────────────────────────────────────────────────────
            if target > 0:
                if abs(error) > BANGBANG:
                    # Bang-bang : pleine puissance vers la cible
                    new_angle = MAX_ANGLE if error > 0 else 0
                    integral = 0.0  # reset intégral en bang-bang
                else:
                    # PID
                    integral   += error * 0.5          # 0.5s de période
                    derivative  = (error - prev_error) / 0.5
                    output      = PID_P * error + PID_I * integral + PID_D * derivative
                    # Convertir output en angle (0–340°)
                    new_angle   = state['current_angle'] + int(output)
                    new_angle   = max(0, min(MAX_ANGLE, new_angle))
                prev_error = error

                # Envoyer au moteur si la position a changé
                if new_angle != state['current_angle']:
                    print(f"PID -> ANGLE:{new_angle} (temp={round(temp,1)} target={target} error={round(error,1)})")
                    send_to_arduino(f'ANGLE:{new_angle}', timeout=0.1)
                    state['current_angle'] = new_angle
            else:
                # Cible à 0 — retour à zéro
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
            integral   = 0.0
            prev_error = 0.0
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
        'sensor_csv_ok':  state['sensor_csv_ok'],
        'sensor_csv_file': os.path.basename(get_latest_csv()) if get_latest_csv() else None,
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
    state['arduino_port'] = find_arduino()
    if state['arduino_port'] and state['arduino'] is None:
        state['arduino'] = connect_arduino(state['arduino_port'])
    # Ne pas essayer de connecter les capteurs — on lit juste le CSV
    print(f"Arduino: {state['arduino_port']}")
    return jsonify({
        'arduino_port': state['arduino_port'],
        'arduino_ok':   state['arduino'] is not None,
        'sensor_ports': [],
        'sensors': {k: {'port': None, 'ok': False} for k, v in SENSORS.items()}
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
    # Retourne à 0° sans couper le courant moteur
    resp = send_to_arduino('ANGLE:0')
    if resp and resp.startswith('ACK:'):
        state['current_angle'] = 0
    return jsonify({'status': 'stopped'})

@app.route('/api/set_target/<temp>', methods=['POST'])
def set_target(temp):
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
    data = request.json
    state['cycle_config'].update(data)
    return jsonify({'status': 'ok'})


# ── Routes moteur direct ──────────────────────────────────────────────────────

@app.route('/api/test_motor', methods=['POST'])
def test_motor():
    if state['arduino'] is None:
        return jsonify({'ok': False, 'response': 'Arduino not connected'})
    try:
        state['arduino'].timeout = 5
        state['arduino'].reset_input_buffer()
        state['arduino'].write(b'ANGLE:10\n')
        # Lire toutes les lignes jusqu'à ACK ou timeout 5s
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
            # Revenir à 0
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
        # Lire toutes les lignes jusqu'à ACK
        response = ''
        for _ in range(15):
            line = state['arduino'].readline().decode().strip()
            if line.startswith('ACK:'):
                response = line
                break
            if not line:
                break
        ok = response.startswith('ACK:')
        # Extraire la position en degrés depuis les micro-pas
        if ok:
            microsteps = int(response.split(':')[1])
            steps_per_rev  = 200
            microstep      = 16
            angle_actual   = round(microsteps * 360 / (steps_per_rev * microstep), 1)
        else:
            angle_actual = angle
        return jsonify({'ok': ok, 'angle': angle_actual, 'response': response})
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e)})

@app.route('/api/motor/reset', methods=['POST'])
def motor_reset():
    """Remet la position Arduino à 0 sans bouger le moteur."""
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
    """Change la vitesse du moteur (µs entre chaque micro-pas)."""
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

@app.route('/api/test_sensor', methods=['POST'])
def test_sensor():
    """Vérifie que le fichier CSV du capteur actif est lisible."""
    sensor_id = state.get('active_sensor', 'sensor_1')
    sensor = active_sensor()
    csv_dir = get_sensor_csv_dir(sensor_id)
    csv_path = get_latest_csv(sensor_id)
    if not csv_path:
        msg = 'No CSV file found'
        if not csv_dir:
            msg = 'csv_dir not configured in config.ini'
        elif not os.path.isdir(csv_dir):
            msg = f'Folder not found: {csv_dir}'
        return jsonify({'ok': False, 'response': msg, 'temp': None, 'file': None,
                        'sensor': sensor['name']})
    try:
        temp = read_temperature()
        filename = os.path.basename(csv_path)
        mod_time = datetime.fromtimestamp(os.path.getmtime(csv_path)).strftime('%H:%M:%S')
        return jsonify({
            'ok': True,
            'response': f'{temp:.1f}°C — last update: {mod_time}',
            'temp': temp,
            'file': filename
        })
    except Exception as e:
        return jsonify({'ok': False, 'response': str(e), 'temp': None, 'file': None})


@app.route('/api/start_cycle', methods=['POST'])
def start_cycle():
    state['running'] = True
    state['mode'] = 'cycle'
    init_log()
    # Lancer le cycle dans un thread séparé
    threading.Thread(target=run_cycle, daemon=True).start()
    return jsonify({'status': 'cycle_started'})

def run_cycle():
    """Exécute les cycles thermiques avec mise à jour de l'interface."""
    cfg = state['cycle_config']
    temp_max   = cfg['temp_max']
    temp_min   = cfg['temp_min']
    hold_max   = cfg['hold_max']
    hold_min   = cfg['hold_min']
    num_cycles = cfg['num_cycles']
    total_steps = num_cycles * 4  # 4 étapes par cycle
    steps_done  = 0

    def emit_cycle(step, current_cycle, complete=False):
        progress = steps_done / (total_steps) if total_steps > 0 else 0
        socketio.emit('cycle_update', {
            'step':          step,
            'current_cycle': current_cycle,
            'num_cycles':    num_cycles,
            'progress':      round(progress, 2),
            'complete':      complete,
        })

    for cycle_num in range(1, num_cycles + 1):
        if not state['running']: break

        # Étape 1 — Montée vers T max
        state['target_temp'] = temp_max
        emit_cycle(1, cycle_num)
        # Attendre que la température soit atteinte (±5°C)
        while state['running'] and abs(state['current_temp'] - temp_max) > 5:
            time.sleep(1)
        steps_done += 1

        if not state['running']: break

        # Étape 2 — Maintien à T max
        emit_cycle(2, cycle_num)
        for _ in range(int(hold_max)):
            if not state['running']: break
            time.sleep(1)
        steps_done += 1

        if not state['running']: break

        # Étape 3 — Descente vers T min
        state['target_temp'] = temp_min
        emit_cycle(3, cycle_num)
        while state['running'] and abs(state['current_temp'] - temp_min) > 5:
            time.sleep(1)
        steps_done += 1

        if not state['running']: break

        # Étape 4 — Maintien à T min
        emit_cycle(4, cycle_num)
        for _ in range(int(hold_min)):
            if not state['running']: break
            time.sleep(1)
        steps_done += 1

    # Étape 5 — Fin
    state['target_temp'] = 0
    state['running'] = False
    emit_cycle(5, num_cycles, complete=True)
    print("Cycle complete")

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    import platform
    def stop_server():
        time.sleep(2)
        system = platform.system()
        if system == 'Darwin':  # Mac
            os.system("osascript -e 'tell application \"Safari\" to close (tabs of windows whose URL contains \"localhost:5001\")' 2>/dev/null")
            os.system("osascript -e 'delay 1' -e 'tell application \"Terminal\" to close (every window whose name contains \"launch\")' &")
        elif system == 'Windows':
            # Ferme le navigateur et le terminal Windows
            os.system(f'taskkill /F /FI "WINDOWTITLE eq *variac*" >nul 2>&1')
            os.system('taskkill /F /IM cmd.exe >nul 2>&1')
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

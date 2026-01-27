from flask import Flask, render_template, Response, request, jsonify
import json
import time
import io
import subprocess
import paho.mqtt.client as mqtt
from PIL import Image
import glob
import csv
import os
import re
import threading
import logging
import requests

# --- REMOTE QUEEN CONFIGURATION ---
# Set QUEEN_IP environment variable to connect to remote Pi
# Example: export QUEEN_IP=192.168.1.100
QUEEN_IP = os.environ.get('QUEEN_IP', None)
QUEEN_API_URL = f"http://{QUEEN_IP}:5001" if QUEEN_IP else None
IS_REMOTE_MODE = QUEEN_IP is not None

# Dashboard port (default 5000, but macOS AirPlay uses 5000)
DASHBOARD_PORT = int(os.environ.get('DASHBOARD_PORT', 5050 if IS_REMOTE_MODE else 5000))

# Silence the Flask access logs for /data polling
log = logging.getLogger('werkzeug')
class FilterDataLogs(logging.Filter):
    def filter(self, record):
        return "/data" not in record.getMessage() and "/video_feed" not in record.getMessage()
log.addFilter(FilterDataLogs())

app = Flask(__name__)

# --- CONFIGURATION ---
MQTT_BROKER = QUEEN_IP if QUEEN_IP else "localhost"
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    if IS_REMOTE_MODE:
        print(f"/// MQTT Connected to Queen at {MQTT_BROKER} ///")
except:
    print(f"Warning: Brain not found (MQTT Disconnected at {MQTT_BROKER})")

# --- CAMERA SYSTEM ---
# Camera is only available on Pi, disabled in remote mode
latest_frame = None
CAMERA_ENABLED = not IS_REMOTE_MODE

def get_camera_command():
    return [
        "rpicam-still", "--width", "320", "--height", "240", # Lower res for speed
        "--encoding", "jpg", "--output", "-", "--timeout", "1", "--nopreview"
    ]

def camera_loop():
    global latest_frame
    if not CAMERA_ENABLED:
        print("/// CAMERA DISABLED (Remote Mode) ///")
        return

    print("/// CAMERA SENSOR ONLINE ///")

    while True:
        try:
            # 1. Capture Frame
            result = subprocess.run(get_camera_command(), capture_output=True)

            if result.stdout:
                img_data = result.stdout
                latest_frame = img_data

                # --- OPTICAL CORTEX ANALYSIS ---
                try:
                    image = Image.open(io.BytesIO(img_data))
                    # Resize to 1x1 pixel to get average brightness instantly
                    avg_color = image.resize((1, 1)).getpixel((0, 0))
                    # Handle grayscale (int) or RGB (tuple)
                    brightness = avg_color if isinstance(avg_color, int) else sum(avg_color) / 3

                    # Publish to Hive Mind
                    client.publish("hive/environment", int(brightness))
                except:
                    pass
                # -------------------------------
            else:
                if result.stderr:
                    print(f"Cam Error: {result.stderr.decode('utf-8')}")

            time.sleep(0.5) # 2 FPS is plenty for "Eye" function

        except Exception as e:
            print(f"Cam Exception: {e}")
            time.sleep(1)

def gen_frames():
    global latest_frame
    while True:
        if latest_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        else:
            # Return a placeholder frame in remote mode
            yield (b'--frame\r\n'
                   b'Content-Type: text/plain\r\n\r\nNo camera feed\r\n')
        time.sleep(0.1)



@app.route('/')
def index():
    return render_template('live.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/data')
def data():
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/data", timeout=2)
            return resp.json()
        except Exception as e:
            print(f"Queen API Proxy Error: {e}")
            return {"grid": [], "drones": {}, "mood": "DISCONNECTED"}

    # Local mode: read directly from file
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "hive_state.json")
        with open(json_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Dashboard Read Error: {e}")
        return {"grid": [], "drones": {}}

@app.route('/history_data')
def history_data():
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            window = request.args.get('window', 60)
            resp = requests.get(f"{QUEEN_API_URL}/history_data?window={window}", timeout=5)
            return resp.json()
        except Exception as e:
            print(f"Queen API History Proxy Error: {e}")
            return {}

    # Local mode: read directly from files
    try:
        window = int(request.args.get('window', 60))
        now = time.time()
        cutoff = now - window

        # Find latest log file
        list_of_files = glob.glob('flight_logs/*.csv')
        if not list_of_files:
            return {}

        latest_file = max(list_of_files, key=os.path.getctime)

        history = {} # {id: [[x,y], [x,y]]}

        with open(latest_file, 'r') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            for row in reader:
                if not row: continue
                # format: timestamp, drone_id, x, y, intensity, rssi
                try:
                    ts = float(row[0])
                    if ts > cutoff:
                        did = row[1]
                        x = int(row[2])
                        y = int(row[3])

                        if did not in history:
                            history[did] = []
                        history[did].append([x,y])
                except ValueError:
                    continue

        return history
    except Exception as e:
        print(f"History Error: {e}")
        return {}

@app.route('/set_mode')
def set_mode():
    mode = request.args.get('mode', 'RANDOM')
    client.publish("hive/control/mode", mode)
    return "OK"

@app.route('/set_virtual_swarm')
def set_virtual_swarm():
    count = request.args.get('count', '0')
    client.publish("hive/control/virtual_swarm", count)
    return "OK"

@app.route('/reset_hive')
def reset_hive():
    client.publish("hive/control/reset", "1")
    return "OK"

# --- PLAYBACK DASHBOARD ROUTES ---

@app.route('/playback')
def playback():
    return render_template('playback.html')

@app.route('/api/archives')
def list_archives():
    """List archived JSON snapshots from snapshots/ directory"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/archives", timeout=5)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Archives Proxy Error: {e}")
            return jsonify([])

    # Local mode
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        snapshots_dir = os.path.join(base_dir, "snapshots")

        if not os.path.exists(snapshots_dir):
            return jsonify([])

        archives = []
        # Pattern: hive_state_ARCHIVE_YYYY-MM-DD_HHMMSS.json
        pattern = re.compile(r'^hive_state_ARCHIVE_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.json$')

        for filename in os.listdir(snapshots_dir):
            match = pattern.match(filename)
            if match:
                # Parse timestamp from groups: year, month, day, time
                try:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    time_str = match.group(4)
                    hour = int(time_str[0:2])
                    minute = int(time_str[2:4])
                    second = int(time_str[4:6])

                    import datetime
                    dt = datetime.datetime(year, month, day, hour, minute, second)
                    timestamp = dt.timestamp()
                    display_time = dt.strftime("%Y-%m-%d %H:%M:%S")

                    # Read archive file for metadata
                    file_path = os.path.join(snapshots_dir, filename)
                    drone_count = 0
                    mood = None
                    decay_rate = None
                    sim_mode = None
                    try:
                        with open(file_path, 'r') as f:
                            archive_data = json.load(f)
                            drone_count = len(archive_data.get('drones', {}))
                            mood = archive_data.get('mood')
                            decay_rate = archive_data.get('decay_rate')
                            sim_mode = archive_data.get('sim_mode')
                    except:
                        pass

                    archives.append({
                        'filename': filename,
                        'timestamp': timestamp,
                        'display_time': display_time,
                        'drone_count': drone_count,
                        'mood': mood,
                        'decay_rate': decay_rate,
                        'sim_mode': sim_mode
                    })
                except (ValueError, IndexError):
                    continue

        # Sort by timestamp, newest first
        archives.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(archives)

    except Exception as e:
        print(f"Archive List Error: {e}")
        return jsonify([])

@app.route('/api/archive/<filename>')
def get_archive(filename):
    """Return contents of a specific archive file"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/archive/{filename}", timeout=10)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Archive Proxy Error: {e}")
            return jsonify({'error': str(e)}), 500

    # Local mode
    try:
        # Security: Validate filename pattern to prevent path traversal
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "snapshots", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(base_dir, "snapshots"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Archive not found'}), 404

        with open(file_path, 'r') as f:
            return json.load(f)

    except Exception as e:
        print(f"Archive Read Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/archive/<filename>', methods=['DELETE'])
def delete_archive(filename):
    """Delete an archived JSON snapshot"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.delete(f"{QUEEN_API_URL}/api/archive/{filename}", timeout=10)
            return jsonify(resp.json()), resp.status_code
        except Exception as e:
            print(f"Queen API Archive Delete Proxy Error: {e}")
            return jsonify({'error': str(e)}), 500

    # Local mode
    try:
        # Security: Validate filename pattern to prevent path traversal
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "snapshots", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(base_dir, "snapshots"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Archive not found'}), 404

        os.remove(file_path)
        return jsonify({'success': True, 'message': f'Deleted {filename}'})

    except Exception as e:
        print(f"Archive Delete Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/flight_logs')
def list_flight_logs():
    """List available flight log CSV files"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/flight_logs", timeout=5)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Flight Logs Proxy Error: {e}")
            return jsonify([])

    # Local mode
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(base_dir, "flight_logs")

        if not os.path.exists(logs_dir):
            return jsonify([])

        logs = []
        # Pattern: session_YYYY-MM-DD_HHMMSS.csv
        pattern = re.compile(r'^session_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.csv$')

        for filename in os.listdir(logs_dir):
            match = pattern.match(filename)
            if match:
                try:
                    import datetime
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    time_str = match.group(4)
                    hour = int(time_str[0:2])
                    minute = int(time_str[2:4])
                    second = int(time_str[4:6])

                    dt = datetime.datetime(year, month, day, hour, minute, second)
                    start_time = dt.timestamp()

                    # Get end time from file (last entry timestamp)
                    file_path = os.path.join(logs_dir, filename)
                    end_time = 0

                    with open(file_path, 'r') as f:
                        reader = csv.reader(f)
                        next(reader, None)  # Skip header
                        for row in reader:
                            if row:
                                try:
                                    end_time = float(row[0])
                                except:
                                    pass

                    logs.append({
                        'filename': filename,
                        'start_time': start_time,
                        'end_time': end_time
                    })
                except (ValueError, IndexError):
                    continue

        # Sort by start time, newest first
        logs.sort(key=lambda x: x['start_time'], reverse=True)
        return jsonify(logs)

    except Exception as e:
        print(f"Flight Log List Error: {e}")
        return jsonify([])

@app.route('/api/flight_log/<filename>')
def get_flight_log(filename):
    """Return contents of a specific flight log as JSON array"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/flight_log/{filename}", timeout=30)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Flight Log Proxy Error: {e}")
            return jsonify({'error': str(e)}), 500

    # Local mode
    try:
        # Security: Validate filename pattern
        pattern = re.compile(r'^session_\d{4}-\d{2}-\d{2}_\d{6}\.csv$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "flight_logs", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(base_dir, "flight_logs"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Flight log not found'}), 404

        data = []
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if row and len(row) >= 4:
                    try:
                        data.append({
                            'timestamp': float(row[0]),
                            'drone_id': row[1],
                            'x': int(row[2]),
                            'y': int(row[3]),
                            'intensity': int(row[4]) if len(row) > 4 else 0,
                            'rssi': int(row[5]) if len(row) > 5 else 0
                        })
                    except (ValueError, IndexError):
                        continue

        return jsonify(data)

    except Exception as e:
        print(f"Flight Log Read Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Print mode information
    if IS_REMOTE_MODE:
        print("/// DASHBOARD RUNNING IN REMOTE MODE ///")
        print(f"/// Queen API: {QUEEN_API_URL} ///")
        print(f"/// MQTT Broker: {MQTT_BROKER} ///")
    else:
        print("/// DASHBOARD RUNNING IN LOCAL MODE ///")

    # Start Camera Eye (only in local mode)
    if CAMERA_ENABLED:
        t = threading.Thread(target=camera_loop)
        t.daemon = True
        t.start()

    print(f"/// DASHBOARD SERVER STARTING ON PORT {DASHBOARD_PORT} ///")
    try:
        app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=False, threaded=True)
    except Exception as e:
        print(f"Flask Error: {e}")
    


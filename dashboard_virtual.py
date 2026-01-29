#!/usr/bin/env python3
"""
SlimeHive Virtual Dashboard
Standalone dashboard for MacBook virtual simulations - completely decoupled from Pi.
All data is read from and saved to the local directory.

Usage:
    python dashboard_virtual.py
    python dashboard_virtual.py --port 5051

This dashboard:
- Reads hive_state.json from local directory (written by simulate.py)
- Saves all snapshots and archives locally
- Never connects to or proxies from Pi
- No MQTT, no camera - pure virtual simulation viewer
"""

from flask import Flask, render_template, Response, request, jsonify
import json
import time
import io
import glob
import csv
import os
import re
import logging
import argparse

# --- BASE DIRECTORY ---
# All file operations are relative to this script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Dashboard port (default 5050 since macOS AirPlay uses 5000)
DEFAULT_PORT = 5050

# Silence the Flask access logs for /data polling
log = logging.getLogger('werkzeug')
class FilterDataLogs(logging.Filter):
    def filter(self, record):
        return "/data" not in record.getMessage()
log.addFilter(FilterDataLogs())

app = Flask(__name__)

# --- FILE PATHS (all local) ---
HIVE_STATE_FILE = os.path.join(BASE_DIR, "hive_state.json")
LIVE_CONFIG_FILE = os.path.join(BASE_DIR, "hive_config_live.json")
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "snapshots")
FLIGHT_LOGS_DIR = os.path.join(BASE_DIR, "flight_logs")


# --- PLACEHOLDER VIDEO FEED (no camera in virtual mode) ---
def gen_frames():
    """Generate placeholder frames (black image) for video feed compatibility"""
    from PIL import Image

    img = Image.new('RGB', (320, 240), color=(20, 20, 20))
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG')
    placeholder_frame = buffer.getvalue()

    while True:
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + placeholder_frame + b'\r\n')
        time.sleep(0.5)


@app.route('/')
def index():
    return render_template('live.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/data')
def data():
    """Read hive state from local file (written by simulate.py)"""
    try:
        with open(HIVE_STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"grid": [], "drones": {}, "mood": "NO_SIMULATION"}
    except Exception as e:
        print(f"Dashboard Read Error: {e}")
        return {"grid": [], "drones": {}, "mood": "ERROR"}

@app.route('/history_data')
def history_data():
    """Read flight history from local CSV files"""
    try:
        window = int(request.args.get('window', 60))
        now = time.time()
        cutoff = now - window

        # Find latest log file
        list_of_files = glob.glob(os.path.join(FLIGHT_LOGS_DIR, '*.csv'))
        if not list_of_files:
            return {}

        latest_file = max(list_of_files, key=os.path.getctime)

        history = {}  # {id: [[x,y], [x,y]]}

        with open(latest_file, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if not row:
                    continue
                # format: timestamp, drone_id, x, y, intensity, rssi
                try:
                    ts = float(row[0])
                    if ts > cutoff:
                        did = row[1]
                        x = int(row[2])
                        y = int(row[3])

                        if did not in history:
                            history[did] = []
                        history[did].append([x, y])
                except ValueError:
                    continue

        return history
    except Exception as e:
        print(f"History Error: {e}")
        return {}

@app.route('/set_mode')
def set_mode():
    """Mode control - no-op in virtual mode (simulation controls its own mode)"""
    mode = request.args.get('mode', 'RANDOM')
    print(f"/// Mode change requested (virtual): {mode} ///")
    return "OK"

@app.route('/set_virtual_swarm')
def set_virtual_swarm():
    """Virtual swarm control - no-op (use simulate.py CLI args)"""
    count = request.args.get('count', '0')
    print(f"/// Virtual swarm count requested: {count} (use simulate.py --drones instead) ///")
    return "OK"

@app.route('/reset_hive')
def reset_hive():
    """Reset hive - creates snapshot before clearing"""
    try:
        # Create snapshot before reset
        if os.path.exists(HIVE_STATE_FILE):
            os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

            from datetime import datetime
            import shutil

            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            archive_name = f"hive_state_ARCHIVE_{timestamp}.json"
            archive_path = os.path.join(SNAPSHOTS_DIR, archive_name)

            shutil.copy2(HIVE_STATE_FILE, archive_path)
            print(f"/// Snapshot saved: {archive_name} ///")

        return "OK"
    except Exception as e:
        print(f"Reset Error: {e}")
        return "ERROR"

# --- LIVE CONFIG ENDPOINT ---

@app.route('/config', methods=['POST'])
def update_config():
    """Update simulation config in real-time (picked up by simulate.py)"""
    try:
        config = request.get_json()
        if not config:
            return jsonify({'error': 'No config data'}), 400

        # Validate and sanitize config values
        death_mode = config.get('death_mode', 'no')
        if death_mode not in ['yes', 'no', 'respawn']:
            death_mode = 'no'

        live_config = {
            'decay_rate': max(0.1, min(1.0, float(config.get('decay_rate', 0.95)))),
            'deposit_amount': max(0, min(20, float(config.get('deposit_amount', 5.0)))),
            'ghost_deposit': max(0, min(5, float(config.get('ghost_deposit', 0.5)))),
            'detection_radius': max(5, min(50, int(config.get('detection_radius', 20)))),
            'pheromone_boost': max(1, min(10, float(config.get('pheromone_boost', 3.0)))),
            'death_mode': death_mode,
            'timestamp': time.time()
        }

        # Write to file for simulation to pick up
        with open(LIVE_CONFIG_FILE, 'w') as f:
            json.dump(live_config, f)

        print(f"/// CONFIG UPDATED: decay={live_config['decay_rate']}, deposit={live_config['deposit_amount']} ///")
        return jsonify({'success': True, 'config': live_config})

    except Exception as e:
        print(f"Config Update Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current live config"""
    try:
        if os.path.exists(LIVE_CONFIG_FILE):
            with open(LIVE_CONFIG_FILE, 'r') as f:
                return jsonify(json.load(f))
        else:
            # Return defaults
            return jsonify({
                'decay_rate': 0.95,
                'deposit_amount': 5.0,
                'ghost_deposit': 0.5,
                'detection_radius': 20,
                'pheromone_boost': 3.0,
                'death_mode': 'no'
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- PLAYBACK DASHBOARD ROUTES ---

@app.route('/playback')
def playback():
    return render_template('playback.html')

@app.route('/api/archives')
def list_archives():
    """List archived JSON snapshots from local snapshots/ directory"""
    try:
        if not os.path.exists(SNAPSHOTS_DIR):
            return jsonify([])

        archives = []
        # Pattern: hive_state_ARCHIVE_YYYY-MM-DD_HHMMSS.json
        pattern = re.compile(r'^hive_state_ARCHIVE_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.json$')

        for filename in os.listdir(SNAPSHOTS_DIR):
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
                    timestamp = dt.timestamp()
                    display_time = dt.strftime("%Y-%m-%d %H:%M:%S")

                    # Read archive file for metadata
                    file_path = os.path.join(SNAPSHOTS_DIR, filename)
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
    try:
        # Security: Validate filename pattern to prevent path traversal
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(SNAPSHOTS_DIR, filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(SNAPSHOTS_DIR)):
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
    try:
        # Security: Validate filename pattern to prevent path traversal
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(SNAPSHOTS_DIR, filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(SNAPSHOTS_DIR)):
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
    """List available flight log CSV files from local directory"""
    try:
        if not os.path.exists(FLIGHT_LOGS_DIR):
            return jsonify([])

        logs = []
        # Pattern: session_YYYY-MM-DD_HHMMSS.csv
        pattern = re.compile(r'^session_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.csv$')

        for filename in os.listdir(FLIGHT_LOGS_DIR):
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
                    file_path = os.path.join(FLIGHT_LOGS_DIR, filename)
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
    try:
        # Security: Validate filename pattern
        pattern = re.compile(r'^session_\d{4}-\d{2}-\d{2}_\d{6}\.csv$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(FLIGHT_LOGS_DIR, filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(FLIGHT_LOGS_DIR)):
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


def main():
    parser = argparse.ArgumentParser(description="SlimeHive Virtual Dashboard")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port to run dashboard on (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("    SLIMEHIVE VIRTUAL DASHBOARD")
    print("=" * 60)
    print(f"    Mode:       VIRTUAL (local files only)")
    print(f"    Base Dir:   {BASE_DIR}")
    print(f"    State File: {HIVE_STATE_FILE}")
    print(f"    Port:       {args.port}")
    print("=" * 60)
    print()
    print("    This dashboard reads from local hive_state.json")
    print("    Run simulate.py in another terminal to generate data")
    print()
    print(f"    Dashboard: http://localhost:{args.port}")
    print()

    try:
        app.run(host='0.0.0.0', port=args.port, debug=False, threaded=True)
    except Exception as e:
        print(f"Flask Error: {e}")


if __name__ == '__main__':
    main()

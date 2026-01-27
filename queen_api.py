"""
Queen API - Lightweight JSON API Server for Pi Zero
Serves hive data to remote dashboard clients.
Runs on port 5001 to avoid conflicts with other services.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import time
import glob
import csv
import os
import re
import datetime
import logging

# Silence Flask access logs for polling endpoints
log = logging.getLogger('werkzeug')
class FilterDataLogs(logging.Filter):
    def filter(self, record):
        return "/data" not in record.getMessage()
log.addFilter(FilterDataLogs())

app = Flask(__name__)
CORS(app)  # Enable cross-origin requests from MacBook dashboard

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@app.route('/data')
def data():
    """Return current hive state JSON"""
    try:
        json_path = os.path.join(BASE_DIR, "hive_state.json")
        with open(json_path, "r") as f:
            return jsonify(json.load(f))
    except Exception as e:
        print(f"Queen API Read Error: {e}")
        return jsonify({"grid": [], "drones": {}, "mood": "UNKNOWN"})


@app.route('/history_data')
def history_data():
    """Return filtered flight history for the given time window"""
    try:
        window = int(request.args.get('window', 60))
        now = time.time()
        cutoff = now - window

        # Find latest log file
        logs_dir = os.path.join(BASE_DIR, 'flight_logs')
        list_of_files = glob.glob(os.path.join(logs_dir, '*.csv'))
        if not list_of_files:
            return jsonify({})

        latest_file = max(list_of_files, key=os.path.getctime)

        history = {}  # {id: [[x,y], [x,y]]}

        with open(latest_file, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if not row:
                    continue
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

        return jsonify(history)
    except Exception as e:
        print(f"Queen API History Error: {e}")
        return jsonify({})


@app.route('/api/archives')
def list_archives():
    """List archived JSON snapshots from snapshots/ directory"""
    try:
        snapshots_dir = os.path.join(BASE_DIR, "snapshots")

        if not os.path.exists(snapshots_dir):
            return jsonify([])

        archives = []
        pattern = re.compile(r'^hive_state_ARCHIVE_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.json$')

        for filename in os.listdir(snapshots_dir):
            match = pattern.match(filename)
            if match:
                try:
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

                    archives.append({
                        'filename': filename,
                        'timestamp': timestamp,
                        'display_time': display_time
                    })
                except (ValueError, IndexError):
                    continue

        archives.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(archives)

    except Exception as e:
        print(f"Queen API Archive List Error: {e}")
        return jsonify([])


@app.route('/api/archive/<filename>')
def get_archive(filename):
    """Return contents of a specific archive file"""
    try:
        # Security: Validate filename pattern to prevent path traversal
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(BASE_DIR, "snapshots", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(BASE_DIR, "snapshots"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Archive not found'}), 404

        with open(file_path, 'r') as f:
            return jsonify(json.load(f))

    except Exception as e:
        print(f"Queen API Archive Read Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/archive/<filename>', methods=['DELETE'])
def delete_archive(filename):
    """Delete an archived JSON snapshot"""
    try:
        # Security: Validate filename pattern to prevent path traversal
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(BASE_DIR, "snapshots", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(BASE_DIR, "snapshots"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Archive not found'}), 404

        os.remove(file_path)
        return jsonify({'success': True, 'message': f'Deleted {filename}'})

    except Exception as e:
        print(f"Queen API Archive Delete Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/flight_logs')
def list_flight_logs():
    """List available flight log CSV files"""
    try:
        logs_dir = os.path.join(BASE_DIR, "flight_logs")

        if not os.path.exists(logs_dir):
            return jsonify([])

        logs = []
        pattern = re.compile(r'^session_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.csv$')

        for filename in os.listdir(logs_dir):
            match = pattern.match(filename)
            if match:
                try:
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
                        next(reader, None)
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

        logs.sort(key=lambda x: x['start_time'], reverse=True)
        return jsonify(logs)

    except Exception as e:
        print(f"Queen API Flight Log List Error: {e}")
        return jsonify([])


@app.route('/api/flight_log/<filename>')
def get_flight_log(filename):
    """Return contents of a specific flight log as JSON array"""
    try:
        # Security: Validate filename pattern
        pattern = re.compile(r'^session_\d{4}-\d{2}-\d{2}_\d{6}\.csv$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(BASE_DIR, "flight_logs", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(BASE_DIR, "flight_logs"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Flight log not found'}), 404

        data = []
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)
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
        print(f"Queen API Flight Log Read Error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'queen_api'})


if __name__ == '__main__':
    print("/// QUEEN API SERVER STARTING ///")
    print("/// Serving JSON data on port 5001 ///")
    print("/// Endpoints: /data, /api/archives, /api/flight_logs, /history_data ///")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)

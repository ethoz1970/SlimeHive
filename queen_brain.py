import paho.mqtt.client as mqtt
import numpy as np
import json
import time
import threading
import random
import shutil
import csv
import re
import glob
from datetime import datetime
from flask import Flask, jsonify, request

import os

# Suppress Flask request logging for cleaner output
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- CONFIGURATION ---
GRID_SIZE = 100  # Grid dimensions (100x100 = 10,000 cells)
MQTT_BROKER = "localhost"  # The Queen is the Broker

# Ensure we write to the same directory as the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, "hive_state.json")

SENSOR_POSITIONS = {
    "QUEEN": (10, 10),      # Bottom-left corner (with margin)
    "SENTINEL": (90, 90)    # Top-right corner (with margin)
}
VIRTUAL_PREFIX = "V-"

# --- OPERATIONAL BOUNDARY ---
# Drones must stay within the rectangle between Queen and Sentinel
# 10-unit margin on all sides prevents drones from hitting grid edges
BOUNDARY_MIN_X = 10
BOUNDARY_MIN_Y = 10
BOUNDARY_MAX_X = 90
BOUNDARY_MAX_Y = 90

# --- BIOLOGICAL PARAMETERS ---
# Decay Rate: How fast pheromones evaporate (0.0 to 1.0)
DECAY_RATE = 0.95  # Default to "Active/Day"
CURRENT_MOOD = "WAITING"
SIMULATION_MODE = "RANDOM" # Options: "RANDOM", "FIND_QUEEN"

# Virtual Drone Speed: Probability of moving each tick (0.0 to 1.0)
# 1.0 = move every tick (10/sec), 0.3 = move ~3/sec, 0.1 = move ~1/sec
VIRTUAL_DRONE_MOVE_CHANCE = 1.0

# --- STATE VARIABLES ---
# The Pheromone Grid (Float 0.0 - 255.0)
hive_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)

# The Ghost Grid (Long-Term Memory, No Decay)
ghost_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)

# Drone Registry: { "ID": {x, y, last_seen, rssi, trail} }
active_drones = {}

# RSSI Buffer for Triangulation: { "ID": { "QUEEN": [-50, -51], "SENTINEL": [-80], "last_update": t } }
rssi_buffer = {}

# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"/// HIVE MIND ONLINE /// Result: {rc}")
    # Subscribe to Drone Data AND Environmental Data
    client.subscribe("hive/deposit")
    client.subscribe("hive/environment")
    client.subscribe("hive/control/mode")
    client.subscribe("hive/control/virtual_swarm")
    client.subscribe("hive/control/reset")

def adjust_virtual_swarm(target_count):
    global active_drones
    
    # Count current virtual drones
    virtual_ids = [d_id for d_id in active_drones if d_id.startswith(VIRTUAL_PREFIX)]
    current_count = len(virtual_ids)
    
    print(f"/// ADJUSTING VIRTUAL SWARM: {current_count} -> {target_count} ///")
    
    if current_count < target_count:
        # Spawn new ones
        to_add = target_count - current_count
        for _ in range(to_add):
            # Find next available ID
            vid = 1
            while f"{VIRTUAL_PREFIX}{vid:02d}" in active_drones:
                vid += 1
            new_id = f"{VIRTUAL_PREFIX}{vid:02d}"

            # Spawn at random location within operational boundary
            active_drones[new_id] = {
                "x": random.randint(BOUNDARY_MIN_X, BOUNDARY_MAX_X),
                "y": random.randint(BOUNDARY_MIN_Y, BOUNDARY_MAX_Y),
                "rssi": -42, # The Answer
                "last_seen": time.time(),
                "trail": []
            }
            
    elif current_count > target_count:
        # Kill random ones
        to_remove = current_count - target_count
        for _ in range(to_remove):
            if not virtual_ids: break
            victim = random.choice(virtual_ids)
            del active_drones[victim]
            virtual_ids.remove(victim)

def reset_hive():
    global hive_grid, ghost_grid, active_drones, rssi_buffer
    print("/// RESETTING HIVE MEMORY ///")
    print(f"DEBUG: Attempting to archive to {os.path.join(BASE_DIR, 'snapshots')}")
    
    # 1. Archive Current State
    try:
        snapshot_dir = os.path.join(BASE_DIR, "snapshots")
        if not os.path.exists(snapshot_dir):
            os.makedirs(snapshot_dir)
            
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_path = os.path.join(snapshot_dir, f"hive_state_ARCHIVE_{timestamp}.json")
        
        print(f"DEBUG: Looking for source file at: {HISTORY_FILE}")
        if os.path.exists(HISTORY_FILE):
            shutil.copy2(HISTORY_FILE, backup_path)
            print(f"Archived state to: {backup_path}")
        else:
            print(f"DEBUG: Source file NOT FOUND! Cannot archive.")
    except Exception as e:
        print(f"Archive Error: {e}")
    
    # 2. Wipe Memory
    hive_grid.fill(0)
    ghost_grid.fill(0)
    # We might want to keep active drones but clear trails? 
    # User said "All remembered drones are removed".
    # But if we remove them, real ones will reappear on next ping.
    active_drones.clear()
    rssi_buffer.clear()

def calculate_gravity_position(drone_id):
    """
    Calculates the weighted center of gravity based on RSSI signal strength.
    Sensors pulling stronger (higher RSSI) attract the drone closer.
    Uses Moving Average for smoothing.
    """
    if drone_id not in rssi_buffer: return None
    
    total_weight = 0
    w_sum_x = 0
    w_sum_y = 0
    sensor_count = 0
    
    # Process each sensor we've heard from recently
    for sensor, rssi_list in rssi_buffer[drone_id].items():
        if sensor == "last_update": continue
        if sensor not in SENSOR_POSITIONS: continue
        
        # Calculate Average RSSI (Smoothing)
        if not rssi_list: continue
        if isinstance(rssi_list, list):
            avg_rssi = sum(rssi_list) / len(rssi_list)
        else:
            avg_rssi = rssi_list # Fallback for old data
        
        # Weight Logic: Map -90dB to 0.1, -30dB to 0.7
        weight = (100 + avg_rssi) / 100.0
        if weight < 0.01: weight = 0.01 
        
        px, py = SENSOR_POSITIONS[sensor]
        w_sum_x += px * weight
        w_sum_y += py * weight
        total_weight += weight
        sensor_count += 1
        
    if total_weight > 0 and sensor_count > 0:
        final_x = int(w_sum_x / total_weight)
        final_y = int(w_sum_y / total_weight)
        # DEBUG LOGGING
        print(f"[GRAVITY] {drone_id}: Sensors={sensor_count} W={total_weight:.2f} -> ({final_x}, {final_y})")
        return final_x, final_y, sensor_count
        
    return None

def on_message(client, userdata, msg):
    global hive_grid, ghost_grid, active_drones, DECAY_RATE, CURRENT_MOOD, SIMULATION_MODE, rssi_buffer
    
    try:
        # --- 0. CONTROL INPUT ---
        if msg.topic == "hive/control/mode":
            mode = msg.payload.decode().upper()
            SIMULATION_MODE = mode
            print(f"/// SWITCHING SIMULATION TO: {SIMULATION_MODE} ///")
            return
            
        if msg.topic == "hive/control/virtual_swarm":
            try:
                count = int(msg.payload.decode())
                adjust_virtual_swarm(count)
            except ValueError:
                print("Error: Invalid Virtual Swarm Count")
            return
            
        if msg.topic == "hive/control/reset":
            reset_hive()
            return

        # --- 1. SENSORY INPUT: VISUAL (ENVIRONMENT) ---
        if msg.topic == "hive/environment":
            brightness = int(msg.payload.decode())
            if brightness > 60:
                DECAY_RATE = 0.95
                if CURRENT_MOOD != "FRENZY":
                    print(f"/// SUNRISE ({brightness}) -> FRENZY ///")
                    CURRENT_MOOD = "FRENZY"
            else:
                DECAY_RATE = 0.60
                if CURRENT_MOOD != "SLEEP":
                    print(f"/// SUNSET ({brightness}) -> SLEEP ///")
                    CURRENT_MOOD = "SLEEP"
            return

        # --- 2. SENSORY INPUT: TACTILE (DRONE MOVEMENT) ---
        if msg.topic == "hive/deposit":
            # Format: EAR_ID, ID, X, Y, INT, RSSI
            payload = msg.payload.decode('utf-8')
            parts = payload.split(',')
            
            # Default values if legacy format
            ear_id = "UNKNOWN"
            if len(parts) == 6:
                ear_id = parts[0]
                drone_id = parts[1]
                x = int(parts[2])
                y = int(parts[3])
                intensity = int(parts[4])
                rssi = int(parts[5])
            elif len(parts) == 5:
                drone_id = parts[0]
                x = int(parts[1])
                y = int(parts[2])
                intensity = int(parts[3])
                rssi = int(parts[4])
            else:
                return

            # Update RSSI Buffer (With Moving Average)
            if drone_id not in rssi_buffer: rssi_buffer[drone_id] = {}
            
            # Initialize list if first time hearing from this sensor
            if ear_id not in rssi_buffer[drone_id]: 
                rssi_buffer[drone_id][ear_id] = []
            elif not isinstance(rssi_buffer[drone_id][ear_id], list): 
                # Handle legacy (float) data from old running instances
                rssi_buffer[drone_id][ear_id] = []
                
            # Add to buffer
            rssi_buffer[drone_id][ear_id].append(rssi)
            # Keep max 5 samples
            if len(rssi_buffer[drone_id][ear_id]) > 5:
                rssi_buffer[drone_id][ear_id].pop(0)
                
            rssi_buffer[drone_id]["last_update"] = time.time()

            # --- CALCULATE POSITION (ALWAYS ACTIVE FOR REAL DRONES) ---
            # Only apply physics if we have recent data
            if time.time() - rssi_buffer[drone_id]["last_update"] < 2.0:
                pos_data = calculate_gravity_position(drone_id)
                if pos_data:
                    tx, ty, s_count = pos_data
                    
                    # SINGLE NODE FIX: Only override if we have triangulation (2+ sensors)
                    if s_count >= 2:
                        # Bounds check
                        x = max(0, min(GRID_SIZE-1, tx))
                        y = max(0, min(GRID_SIZE-1, ty))
                    # Else: Trust the drone's self-reported X,Y (from payload)

            # A. Update Drone Registry (Where are they NOW?)
            active_drones[drone_id] = {
                "x": x, 
                "y": y, 
                "rssi": rssi,
                "last_seen": time.time(),
                "trail": active_drones.get(drone_id, {}).get("trail", [])
            }
            # Add to trail (Moved logic here to deduplicate)
            active_drones[drone_id]["trail"].append([x, y])
            if len(active_drones[drone_id]["trail"]) > 10:
                active_drones[drone_id]["trail"].pop(0)

            # B. Deposit Pheromones (Update the Map)
            if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
                # Active Grid (Decays)
                hive_grid[x][y] += (intensity / 10.0) 
                if hive_grid[x][y] > 255: hive_grid[x][y] = 255
                
                # Ghost Grid (Long Term Memory)
                ghost_grid[x][y] += 0.5
                if ghost_grid[x][y] > 255: ghost_grid[x][y] = 255

    except Exception as e:
        print(f"Sensory Error: {e}")

# --- PHYSICS ENGINE (Thread) ---
def physics_loop():
    global hive_grid, ghost_grid, active_drones, DECAY_RATE, CURRENT_MOOD, SIMULATION_MODE
    
    print("/// PHYSICS ENGINE STARTED ///")
    
    while True:
        # 1. Apply Natural Decay (Evaporation)
        # Only to the Active Grid! Ghost Grid never forgets.
        hive_grid *= DECAY_RATE
        
        # 2. Update Virtual Drones
        virtual_ids = [d for d in active_drones if d.startswith(VIRTUAL_PREFIX)]
        for v_id in virtual_ids:
            drone = active_drones[v_id]

            # Speed control: skip movement most ticks
            if random.random() > VIRTUAL_DRONE_MOVE_CHANCE:
                continue

            dx, dy = 0, 0

            # --- BEHAVIOR TREE ---
            if SIMULATION_MODE == "FIND_QUEEN":
                # Move towards Queen position (bottom-left corner)
                target_x, target_y = SENSOR_POSITIONS["QUEEN"]

                # Vector to target
                vx = target_x - drone["x"]
                vy = target_y - drone["y"]

                # Normalize (Sign) + Random Noise
                dx = int(np.sign(vx)) if abs(vx) > 0 else 0
                dy = int(np.sign(vy)) if abs(vy) > 0 else 0

                # Add randomness so they don't form a conga line
                if random.random() < 0.3:
                    dx = random.choice([-1, 0, 1])
                if random.random() < 0.3:
                    dy = random.choice([-1, 0, 1])

            elif SIMULATION_MODE == "PATROL":
                # Patrol around the perimeter of the operational boundary
                x, y = drone["x"], drone["y"]
                margin = 2  # Distance from boundary edge for patrol path

                # Determine which edge of boundary we're closest to and move clockwise
                at_left = x <= BOUNDARY_MIN_X + margin
                at_right = x >= BOUNDARY_MAX_X - margin
                at_bottom = y <= BOUNDARY_MIN_Y + margin
                at_top = y >= BOUNDARY_MAX_Y - margin

                if at_bottom and not at_right:
                    dx, dy = 1, 0  # Bottom edge: move right
                elif at_right and not at_top:
                    dx, dy = 0, 1  # Right edge: move up
                elif at_top and not at_left:
                    dx, dy = -1, 0  # Top edge: move left
                elif at_left and not at_bottom:
                    dx, dy = 0, -1  # Left edge: move down
                else:
                    # Not on perimeter, move toward nearest boundary edge
                    center_x = (BOUNDARY_MIN_X + BOUNDARY_MAX_X) // 2
                    dx = -1 if x > center_x else 1
                    dy = -1  # Head toward bottom edge

                # Add slight randomness
                if random.random() < 0.2:
                    dx += random.choice([-1, 0, 1])
                    dy += random.choice([-1, 0, 1])

            elif SIMULATION_MODE == "SWARM":
                # Flocking behavior: stay together as a group
                # Calculate center of mass of all virtual drones
                vdrones = [d for did, d in active_drones.items() if did.startswith(VIRTUAL_PREFIX)]
                if len(vdrones) > 1:
                    cx = sum(d["x"] for d in vdrones) / len(vdrones)
                    cy = sum(d["y"] for d in vdrones) / len(vdrones)

                    # Cohesion: move toward center of swarm
                    vx = cx - drone["x"]
                    vy = cy - drone["y"]

                    # Only apply cohesion if far from center
                    dist = (vx**2 + vy**2) ** 0.5
                    if dist > 5:
                        dx = int(np.sign(vx))
                        dy = int(np.sign(vy))
                    else:
                        # Close to swarm, random wander
                        dx = random.choice([-1, 0, 1])
                        dy = random.choice([-1, 0, 1])

                    # Add random movement to prevent stacking
                    if random.random() < 0.4:
                        dx = random.choice([-1, 0, 1])
                        dy = random.choice([-1, 0, 1])
                else:
                    dx = random.choice([-1, 0, 1])
                    dy = random.choice([-1, 0, 1])

            elif SIMULATION_MODE == "SCATTER":
                # Scatter: move away from boundary center toward edges
                center_x = (BOUNDARY_MIN_X + BOUNDARY_MAX_X) // 2
                center_y = (BOUNDARY_MIN_Y + BOUNDARY_MAX_Y) // 2
                vx = drone["x"] - center_x
                vy = drone["y"] - center_y

                # Move away from center
                dx = int(np.sign(vx)) if abs(vx) > 0 else random.choice([-1, 1])
                dy = int(np.sign(vy)) if abs(vy) > 0 else random.choice([-1, 1])

                # Add randomness
                if random.random() < 0.3:
                    dx = random.choice([-1, 0, 1])
                    dy = random.choice([-1, 0, 1])

            elif SIMULATION_MODE == "TRAIL_FOLLOW":
                # Follow pheromone trails in the ghost grid (within boundary)
                x, y = drone["x"], drone["y"]
                best_dx, best_dy = 0, 0
                best_pheromone = 0

                # Check all 8 neighbors + current (only within boundary)
                for check_dx in [-1, 0, 1]:
                    for check_dy in [-1, 0, 1]:
                        nx = x + check_dx
                        ny = y + check_dy
                        if BOUNDARY_MIN_X <= nx <= BOUNDARY_MAX_X and BOUNDARY_MIN_Y <= ny <= BOUNDARY_MAX_Y:
                            p = ghost_grid[nx][ny]
                            # Add randomness to break ties and explore
                            p += random.random() * 5
                            if p > best_pheromone:
                                best_pheromone = p
                                best_dx, best_dy = check_dx, check_dy

                dx, dy = best_dx, best_dy

                # If no pheromones nearby, random walk
                if best_pheromone < 1:
                    dx = random.choice([-1, 0, 1])
                    dy = random.choice([-1, 0, 1])

            else:  # RANDOM (Default)
                dx = random.choice([-1, 0, 1])
                dy = random.choice([-1, 0, 1])
            
            # Constrain to operational boundary
            new_x = int(max(BOUNDARY_MIN_X, min(BOUNDARY_MAX_X, drone["x"] + dx)))
            new_y = int(max(BOUNDARY_MIN_Y, min(BOUNDARY_MAX_Y, drone["y"] + dy)))
            
            # Update Position
            drone["x"] = new_x
            drone["y"] = new_y
            drone["last_seen"] = time.time()
            
            # Add to Trail
            drone["trail"].append([new_x, new_y])
            if len(drone["trail"]) > 10: drone["trail"].pop(0)
            
            # Deposit Pheromones (Virtual Drones affect the world!)
            intensity = 50 # Standard drone strength
            hive_grid[new_x][new_y] += (intensity / 10.0)
            if hive_grid[new_x][new_y] > 255: hive_grid[new_x][new_y] = 255

            ghost_grid[new_x][new_y] += 0.5
            if ghost_grid[new_x][new_y] > 255: ghost_grid[new_x][new_y] = 255

            # Publish to MQTT for logger to record
            rssi = drone.get("rssi", -50)
            client.publish("hive/deposit", f"VIRTUAL,{v_id},{new_x},{new_y},{intensity},{rssi}")
        
        # 3. Save State for Dashboard (The "Mental Image")
        # We convert numpy array to standard list for JSON
        state = {
            "grid": hive_grid.tolist(),
            "ghost_grid": ghost_grid.tolist(),
            "drones": active_drones,
            "mood": CURRENT_MOOD,
            "decay_rate": DECAY_RATE,
            "sim_mode": SIMULATION_MODE,
            "boundary": {
                "min_x": BOUNDARY_MIN_X,
                "min_y": BOUNDARY_MIN_Y,
                "max_x": BOUNDARY_MAX_X,
                "max_y": BOUNDARY_MAX_Y
            }
        }
        
        try:
            # Atomic Write: Write to .tmp then rename
            tmp_file = HISTORY_FILE + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump(state, f)
                f.flush()
                os.fsync(f.fileno()) # Ensure data is on disk
            
            # Atomic swap
            os.replace(tmp_file, HISTORY_FILE)
            
        except TypeError as te:
            print(f"JSON Serialization Error: {te}")
        except Exception as e:
            print(f"Memory Write Error: {e}")

        # Tick Rate (10Hz)
        time.sleep(0.1)
        
        # Heartbeat (approx every 2 seconds)
        if int(time.time()) % 2 == 0 and random.random() < 0.1:
             print("/// HIVE MEMORY SYNCED ///")

# --- API SERVER (For Remote Dashboard) ---
api_app = Flask(__name__)
API_PORT = 5001

@api_app.route('/data')
def api_data():
    """Return current hive state"""
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"grid": [], "drones": {}, "mood": "ERROR", "error": str(e)}

@api_app.route('/history_data')
def api_history_data():
    """Return drone movement history from flight logs"""
    try:
        window = int(request.args.get('window', 60))
        now = time.time()
        cutoff = now - window

        logs_dir = os.path.join(BASE_DIR, "flight_logs")
        list_of_files = glob.glob(os.path.join(logs_dir, '*.csv'))
        if not list_of_files:
            return jsonify({})

        latest_file = max(list_of_files, key=os.path.getctime)
        history = {}

        with open(latest_file, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)
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
        return jsonify({})

@api_app.route('/api/archives')
def api_list_archives():
    """List archived JSON snapshots"""
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
                    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    time_str = match.group(4)
                    hour, minute, second = int(time_str[0:2]), int(time_str[2:4]), int(time_str[4:6])
                    dt = datetime(year, month, day, hour, minute, second)
                    archives.append({
                        'filename': filename,
                        'timestamp': dt.timestamp(),
                        'display_time': dt.strftime("%Y-%m-%d %H:%M:%S")
                    })
                except (ValueError, IndexError):
                    continue

        archives.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(archives)
    except Exception as e:
        return jsonify([])

@api_app.route('/api/archive/<filename>')
def api_get_archive(filename):
    """Return contents of a specific archive file"""
    try:
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(BASE_DIR, "snapshots", filename)
        snapshots_dir = os.path.join(BASE_DIR, "snapshots")

        if not os.path.abspath(file_path).startswith(os.path.abspath(snapshots_dir)):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Archive not found'}), 404

        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_app.route('/api/archive/<filename>', methods=['DELETE'])
def api_delete_archive(filename):
    """Delete an archived JSON snapshot"""
    try:
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        file_path = os.path.join(BASE_DIR, "snapshots", filename)
        snapshots_dir = os.path.join(BASE_DIR, "snapshots")

        if not os.path.abspath(file_path).startswith(os.path.abspath(snapshots_dir)):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Archive not found'}), 404

        os.remove(file_path)
        return jsonify({'success': True, 'message': f'Deleted {filename}'})
    except Exception as e:
        print(f"Archive Delete Error: {e}")
        return jsonify({'error': str(e)}), 500

@api_app.route('/api/flight_logs')
def api_list_flight_logs():
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
                    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    time_str = match.group(4)
                    hour, minute, second = int(time_str[0:2]), int(time_str[2:4]), int(time_str[4:6])
                    dt = datetime(year, month, day, hour, minute, second)
                    start_time = dt.timestamp()

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
        return jsonify([])

@api_app.route('/api/flight_log/<filename>')
def api_get_flight_log(filename):
    """Return contents of a specific flight log as JSON array"""
    try:
        pattern = re.compile(r'^session_\d{4}-\d{2}-\d{2}_\d{6}\.csv$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        logs_dir = os.path.join(BASE_DIR, "flight_logs")
        file_path = os.path.join(logs_dir, filename)

        if not os.path.abspath(file_path).startswith(os.path.abspath(logs_dir)):
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
        return jsonify({'error': str(e)}), 500

def run_api_server():
    """Run Flask API server in background thread"""
    print(f"/// API SERVER STARTING ON PORT {API_PORT} ///")
    api_app.run(host='0.0.0.0', port=API_PORT, debug=False, threaded=True)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Start API Server in background
    api_thread = threading.Thread(target=run_api_server)
    api_thread.daemon = True
    api_thread.start()

    # Start Physics in background
    t = threading.Thread(target=physics_loop)
    t.daemon = True
    t.start()

    # Start MQTT Listener (The Ears)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, 1883, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n/// HIVE SHUTDOWN ///")
    except ConnectionRefusedError:
        print("ERROR: Could not connect to MQTT Broker. Is Mosquitto running?")
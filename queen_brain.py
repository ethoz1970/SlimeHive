import paho.mqtt.client as mqtt
import numpy as np
import json
import time
import threading
import random

# --- CONFIGURATION ---
GRID_SIZE = 50
MQTT_BROKER = "localhost"  # The Queen is the Broker
HISTORY_FILE = "hive_state.json"
SENSOR_POSITIONS = {
    "QUEEN": (25, 25),
    "SENTINEL": (10, 10)
}
VIRTUAL_PREFIX = "V-"

# --- BIOLOGICAL PARAMETERS ---
# --- BIOLOGICAL PARAMETERS ---
# Decay Rate: How fast pheromones evaporate (0.0 to 1.0)
DECAY_RATE = 0.95  # Default to "Active/Day"
CURRENT_MOOD = "WAITING"
SIMULATION_MODE = "RANDOM" # Options: "RANDOM", "FIND_QUEEN"

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
            
            # Spawn at random location
            active_drones[new_id] = {
                "x": random.randint(0, GRID_SIZE-1),
                "y": random.randint(0, GRID_SIZE-1),
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
        final_x = w_sum_x / total_weight
        final_y = w_sum_y / total_weight
        return int(final_x), int(final_y)
        
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
                pos = calculate_gravity_position(drone_id)
                if pos:
                    tx, ty = pos
                    # Bounds check
                    x = max(0, min(GRID_SIZE-1, tx))
                    y = max(0, min(GRID_SIZE-1, ty))

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
            
            dx, dy = 0, 0
            
            # --- BEHAVIOR TREE ---
            if SIMULATION_MODE == "FIND_QUEEN":
                # Move towards (25, 25)
                target_x, target_y = 25, 25
                
                # Vector to target
                vx = target_x - drone["x"]
                vy = target_y - drone["y"]
                
                # Normalize (Sign) + Random Noise
                # We want a chance to move closer
                dx = np.sign(vx) if abs(vx) > 0 else 0
                dy = np.sign(vy) if abs(vy) > 0 else 0
                
                # Add randomness so they don't form a conga line
                if random.random() < 0.3:
                    dx = random.choice([-1, 0, 1])
                if random.random() < 0.3:
                    dy = random.choice([-1, 0, 1])
                    
            else: # RANDOM (Default)
                dx = random.choice([-1, 0, 1])
                dy = random.choice([-1, 0, 1])
            
            new_x = max(0, min(GRID_SIZE-1, drone["x"] + dx))
            new_y = max(0, min(GRID_SIZE-1, drone["y"] + dy))
            
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
        
        # 3. Save State for Dashboard (The "Mental Image")
        # We convert numpy array to standard list for JSON
        state = {
            "grid": hive_grid.tolist(),
            "ghost_grid": ghost_grid.tolist(),
            "drones": active_drones,
            "mood": CURRENT_MOOD,
            "decay_rate": DECAY_RATE,
            "sim_mode": SIMULATION_MODE
        }
        
        try:
            # print("DEBUG: Writing state...")
            with open(HISTORY_FILE, "w") as f:
                json.dump(state, f)
                f.flush()
                # os.fsync(f.fileno()) # Optional, but good for safety
        except TypeError as te:
            print(f"JSON Serialization Error: {te}")
            # Debug: what exactly is wrong?
            # print(state)
        except Exception as e:
            print(f"Memory Write Error: {e}")

        # Tick Rate (10Hz)
        time.sleep(0.1)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
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
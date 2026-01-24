import paho.mqtt.client as mqtt
import numpy as np
import json
import time
import threading

# --- CONFIGURATION ---
GRID_SIZE = 50
MQTT_BROKER = "localhost"  # The Queen is the Broker
HISTORY_FILE = "hive_state.json"

# --- BIOLOGICAL PARAMETERS ---
# Decay Rate: How fast pheromones evaporate (0.0 to 1.0)
DECAY_RATE = 0.95  # Default to "Active/Day"
CURRENT_MOOD = "WAITING"
POSITION_MODE = "RANDOM" # Options: "RANDOM", "RSSI"

# --- STATE VARIABLES ---
# The Pheromone Grid (Float 0.0 - 255.0)
hive_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)

# Drone Registry: { "ID": {x, y, last_seen, rssi, trail} }
active_drones = {}

# RSSI Buffer for Triangulation: { "ID": { "QUEEN": -50, "SENTINEL": -80, "last_update": t } }
rssi_buffer = {}

# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"/// HIVE MIND ONLINE /// Result: {rc}")
    # Subscribe to Drone Data AND Environmental Data
    client.subscribe("hive/deposit")
    client.subscribe("hive/environment")
    client.subscribe("hive/control/mode")

def calculate_distance(rssi):
    # Rough approximation: -50dB = 1m, -6dB per doubling distance
    # Let's map RSSI (-30 to -90) to Grid Units (0 to 50)
    # -30 -> 1 unit
    # -90 -> 40 units
    dist = (abs(rssi) - 30) * 0.8
    if dist < 1: dist = 1
    return dist

def triangulation(d1, d2):
    # P1 (Queen) at (25, 25)
    # P2 (Sentinel) at (10, 10)
    p1 = np.array([25, 25])
    p2 = np.array([10, 10])
    
    # Distance between sensors
    d_sensors = np.linalg.norm(p1 - p2) # approx 21.2
    
    # 2D Trilateration logic (Simplified intersection of spheres)
    # x = (r1^2 - r2^2 + d^2) / (2d)
    # This finds the point along the line connecting P1-P2
    a = (d1**2 - d2**2 + d_sensors**2) / (2 * d_sensors)
    
    # Height h = sqrt(r1^2 - a^2)
    # If circles don't touch, just take the closest point
    term = d1**2 - a**2
    h = 0
    if term > 0:
        h = np.sqrt(term)
        
    # P2 relative to P1
    p2_p1 = p2 - p1
    
    # Point P3 (intersection center)
    x3 = p1[0] + a * (p2_p1[0] / d_sensors)
    y3 = p1[1] + a * (p2_p1[1] / d_sensors)
    
    # We pick one of the two intersections (ignoring h usually keeps us on the line, which is boring)
    # But for a demo, let's just return P3 to check logic, effective result is "Between" them
    # To be fancy, we add +h or -h. Let's add +h to X for bias.
    
    fx = x3 + h * (p2_p1[1] / d_sensors)
    fy = y3 - h * (p2_p1[0] / d_sensors)
    
    return int(fx), int(fy)

def on_message(client, userdata, msg):
    global hive_grid, active_drones, DECAY_RATE, CURRENT_MOOD, POSITION_MODE, rssi_buffer
    
    try:
        # --- 0. CONTROL INPUT ---
        if msg.topic == "hive/control/mode":
            mode = msg.payload.decode().upper()
            if mode in ["RANDOM", "RSSI"]:
                POSITION_MODE = mode
                print(f"/// SWITCHING NAVIGATION TO: {POSITION_MODE} ///")
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

            # Update RSSI Buffer
            if drone_id not in rssi_buffer: rssi_buffer[drone_id] = {}
            rssi_buffer[drone_id][ear_id] = rssi
            rssi_buffer[drone_id]["last_update"] = time.time()

            # --- CALCULATE POSITION ---
            if POSITION_MODE == "RSSI" and "QUEEN" in rssi_buffer[drone_id] and "SENTINEL" in rssi_buffer[drone_id]:
                # Triangulate
                d_q = calculate_distance(rssi_buffer[drone_id]["QUEEN"])
                d_s = calculate_distance(rssi_buffer[drone_id]["SENTINEL"])
                
                # Check latency (if data is stale > 2s, ignore)
                if time.time() - rssi_buffer[drone_id]["last_update"] < 2.0:
                    tx, ty = triangulation(d_q, d_s)
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
                hive_grid[x][y] += (intensity / 10.0) 
                if hive_grid[x][y] > 255: hive_grid[x][y] = 255

    except Exception as e:
        print(f"Sensory Error: {e}")

# --- PHYSICS ENGINE (Thread) ---
def physics_loop():
    global hive_grid, active_drones, DECAY_RATE, CURRENT_MOOD
    
    print("/// PHYSICS ENGINE STARTED ///")
    
    while True:
        # 1. Apply Natural Decay (Evaporation)
        # This is now controlled by the Camera!
        hive_grid *= DECAY_RATE
        
        # 2. Prune Dead Drones (Heartbeat Check)
        # DISABLED: check via Dashboard logic instead
        # now = time.time()
        # dead_ids = []
        # for d_id, data in active_drones.items():
        #     if now - data['last_seen'] > 5.0: # 5 seconds without signal = Dead
        #         dead_ids.append(d_id)
        # 
        # for d_id in dead_ids:
        #     del active_drones[d_id]
        #     # print(f"Lost contact with drone: {d_id}")

        # 3. Save State for Dashboard (The "Mental Image")
        # We convert numpy array to standard list for JSON
        state = {
            "grid": hive_grid.tolist(),
            "drones": active_drones,
            "mood": CURRENT_MOOD,
            "decay_rate": DECAY_RATE
        }
        
        try:
            with open(HISTORY_FILE, "w") as f:
                json.dump(state, f)
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
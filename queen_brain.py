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
# 0.99 = Lasts forever (Long term memory)
# 0.50 = Vanishes instantly (Short term memory)
DECAY_RATE = 0.95  # Default to "Active/Day"
CURRENT_MOOD = "WAITING"

# --- STATE VARIABLES ---
# The Pheromone Grid (Float 0.0 - 255.0)
hive_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)

# Drone Registry: { "ID": {x, y, last_seen, rssi} }
active_drones = {}

# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"/// HIVE MIND ONLINE /// Result: {rc}")
    # Subscribe to Drone Data AND Environmental Data
    client.subscribe("hive/deposit")
    client.subscribe("hive/environment")

def on_message(client, userdata, msg):
    global hive_grid, active_drones, DECAY_RATE, CURRENT_MOOD
    
    try:
        # --- 1. SENSORY INPUT: VISUAL (ENVIRONMENT) ---
        if msg.topic == "hive/environment":
            brightness = int(msg.payload.decode())
            
            # CIRCADIAN RHYTHM LOGIC
            # If the room is bright, the hive is "Awake" (High Memory)
            # If the room is dark, the hive is "Asleep" (Low Memory)
            if brightness > 60:
                DECAY_RATE = 0.95
                if CURRENT_MOOD != "FRENZY":
                    print(f"/// SUNRISE DETECTED ({brightness}) -> ENTERING FRENZY MODE ///")
                    CURRENT_MOOD = "FRENZY"
            else:
                DECAY_RATE = 0.60
                if CURRENT_MOOD != "SLEEP":
                    print(f"/// SUNSET DETECTED ({brightness}) -> ENTERING SLEEP MODE ///")
                    CURRENT_MOOD = "SLEEP"
            return

        # --- 2. SENSORY INPUT: TACTILE (DRONE MOVEMENT) ---
        if msg.topic == "hive/deposit":
            # Format: ID, X, Y, INTENSITY, RSSI
            payload = msg.payload.decode('utf-8')
            parts = payload.split(',')
            
            drone_id = parts[0]
            x = int(parts[1])
            y = int(parts[2])
            intensity = int(parts[3])
            rssi = int(parts[4])

            # A. Update Drone Registry (Where are they NOW?)
            # Retrieve existing trail or start new
            current_trail = []
            if drone_id in active_drones:
                current_trail = active_drones[drone_id].get("trail", [])
            
            current_trail.append([x, y])
            if len(current_trail) > 10: 
                current_trail.pop(0)

            active_drones[drone_id] = {
                "x": x, 
                "y": y, 
                "rssi": rssi,
                "last_seen": time.time(),
                "trail": current_trail
            }

            # B. Deposit Pheromones (Update the Map)
            # Add intensity to the current spot
            if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
                hive_grid[x][y] += (intensity / 10.0) 
                # Cap at 255
                if hive_grid[x][y] > 255: 
                    hive_grid[x][y] = 255

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
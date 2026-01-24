import paho.mqtt.client as mqtt
import numpy as np
import time
import json
import threading

# --- CONFIGURATION ---
GRID_SIZE = 50
DECAY_RATE = 0.99  # 0.99 = Long trails, 0.95 = Short comets
DIFFUSION_RATE = 0.05 # How much the scent spreads to neighbors

# The Grid (Float 32 for smooth decay)
hive_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32)

# Tracker { "28:AB": {"x": 10, "y": 10, "last_seen": 12345} }
active_drones = {}

def apply_physics():
    """Decays the scent and saves state for dashboard"""
    global hive_grid
    while True:
        # 1. Decay
        hive_grid *= DECAY_RATE
        
        # 2. Save State for Dashboard
        # We convert grid to list for JSON
        state = {
            "grid": hive_grid.tolist(),
            "drones": active_drones
        }
        with open("hive_state.json", "w") as f:
            json.dump(state, f)
            
        time.sleep(0.1)

def on_message(client, userdata, msg):
    global hive_grid, active_drones
    try:
        payload = msg.payload.decode('utf-8')
        parts = payload.split(',')
        
        # Parse: ID, X, Y, Intensity, RSSI
        drone_id = parts[0]
        x = int(parts[1])
        y = int(parts[2])
        strength = int(parts[3])
        rssi = int(parts[4])
        
        # Track the drone
        active_drones[drone_id] = {
            "x": x, 
            "y": y, 
            "rssi": rssi,
            "last_seen": time.time()
        }

        # Apply Scent (Physics)
        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
            # Signal Quality Penalty
            if rssi < -80: strength *= 0.5
            
            hive_grid[x, y] += strength
            
            # Clamp max value to prevent infinite white
            hive_grid[x, y] = min(hive_grid[x, y], 2000)

        print(f"[{drone_id}] Drop at {x},{y} ({rssi}dB)")

    except Exception as e:
        print(f"Error: {e}")

# --- START ENGINE ---
# Start Physics Thread
t = threading.Thread(target=apply_physics)
t.daemon = True
t.start()

# Start MQTT Listener
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)
client.subscribe("hive/deposit")
client.on_message = on_message

print("--- QUEEN BRAIN ONLINE (State Engine) ---")
client.loop_forever()
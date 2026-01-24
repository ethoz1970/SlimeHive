import paho.mqtt.client as mqtt
import numpy as np
import time
import json
import threading

# --- CONFIGURATION ---
GRID_SIZE = 50
DECAY_RATE = 0.99 
hive_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=np.float32)
active_drones = {}

def apply_physics():
    global hive_grid
    while True:
        hive_grid *= DECAY_RATE
        state = {
            "grid": hive_grid.tolist(),
            "drones": active_drones
        }
        try:
            with open("hive_state.json", "w") as f:
                json.dump(state, f)
        except:
            pass
        time.sleep(0.1)

def on_message(client, userdata, msg):
    global hive_grid, active_drones
    try:
        # 1. DECODE RAW DATA
        payload = msg.payload.decode('utf-8')
        parts = payload.split(',')
        
        # 2. DEBUG PRINT (See exactly what we got)
        # print(f"DEBUG RECEIVE: {parts} (Length: {len(parts)})") 

        # 3. SMART PARSING (Handle any length)
        
        # --- NEW FORMAT (ID, X, Y, Int, RSSI) ---
        if len(parts) == 5:
            drone_id = parts[0]
            x = int(parts[1])
            y = int(parts[2])
            strength = int(parts[3])
            rssi = int(parts[4])
            
        # --- OLD FORMAT (X, Y, Int) ---
        elif len(parts) == 3:
            drone_id = "UNKNOWN"
            x = int(parts[0])
            y = int(parts[1])
            strength = int(parts[2])
            rssi = -50 # Fake strong signal
            
        # --- WEIRD/BROKEN DATA ---
        else:
            print(f" ! SKIPPING INVALID DATA (Len {len(parts)}): {payload}")
            return

        # 4. UPDATE HIVE MIND
        active_drones[drone_id] = {
            "x": x, "y": y, "rssi": rssi, "last_seen": time.time()
        }

        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
            if rssi < -80: strength *= 0.5
            hive_grid[x, y] += strength
            # Cap the max brightness
            hive_grid[x, y] = min(hive_grid[x, y], 2000)

        # Success message
        print(f"[{drone_id}] Drop at {x},{y} ({rssi}dB)")

    except Exception as e:
        # If it still crashes, tell us exactly why
        print(f"CRITICAL ERROR: {e} | Raw Payload: {msg.payload}")

# --- START ENGINE ---
t = threading.Thread(target=apply_physics)
t.daemon = True
t.start()

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)
client.subscribe("hive/deposit")
client.on_message = on_message

print("--- QUEEN BRAIN ONLINE (Debug Mode) ---")
client.loop_forever()
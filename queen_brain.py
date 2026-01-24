#new code

import time
import json
import numpy as np
import paho.mqtt.client as mqtt
from scipy.signal import convolve2d

# --- HIVE CONFIGURATION ---
GRID_SIZE = 50
DECAY_RATE = 1.995  # How fast scent fades (Lower = faster fade)
DIFFUSION_KERNEL = np.array([[0.05, 0.1, 0.05],
                             [0.1,  0.4, 0.1 ],
                             [0.05, 0.1, 0.05]])

# MQTT SETTINGS
BROKER_ADDRESS = "localhost"
TOPIC_DEPOSIT = "hive/deposit"

# --- INITIALIZATION ---
# Create the empty 50x50 grid
hive_grid = np.zeros((GRID_SIZE, GRID_SIZE))

# --- MQTT FUNCTIONS ---
def on_connect(client, userdata, flags, rc):
    print(f"Connected to Internal Broker (Code {rc})")
    client.subscribe(TOPIC_DEPOSIT)

def on_message(client, userdata, msg):
    """
    Triggered when the Pico sends a "Deposit" message.
    Payload format expected: "x,y,intensity" OR "x,y,intensity,rssi"
    """
    global hive_grid
    try:
        payload = msg.payload.decode('utf-8')
        data_parts = list(map(int, payload.split(',')))
        
        # Default values
        rssi = -50  # Assume strong signal if not provided
        
        # Handle variable data length (Backwards compatibility)
        if len(data_parts) == 3:
            x, y, strength = data_parts
        elif len(data_parts) == 4:
            x, y, strength, rssi = data_parts
        else:
            print(f" ! FORMAT ERROR: {payload}")
            return

        # --- PHYSICS: SIGNAL QUALITY ---
        # If the drone is far away (low RSSI), the "data integrity" drops.
        # RSSI is usually -30 (close) to -90 (far).
        # We will reduce the strength of the drop if the signal is weak.
        if rssi < -80:
            strength *= 0.5  # 50% penalty for bad signal
            print(f" > GHOST DROP (Weak Signal {rssi}dB): +{strength} at [{x}, {y}]")
        else:
            print(f" > DROP: +{strength} at [{x}, {y}] (Signal {rssi}dB)")

        # Apply to grid
        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
            hive_grid[x, y] += strength
            
    except ValueError:
        print(f" ! DATA ERROR: Could not parse '{msg.payload}'")
    except Exception as e:
        print(f" ! ERROR: {e}")

# --- SETUP CLIENT ---
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

# Connect to the local Mosquitto service
try:
    client.connect(BROKER_ADDRESS, 1883, 60)
except Exception as e:
    print(f"CRITICAL: Could not connect to Mosquitto. Is it running? ({e})")
    exit(1)

# Start the listener in the background
client.loop_start()

print("--- QUEEN BRAIN ACTIVE ---")
print("1. Listening for Pico Drones...")
print("2. Simulating Physics...")
print("3. Writing Data for Dashboard...")

# --- MAIN PHYSICS LOOP ---
try:
    while True:
        # 1. DIFFUSION (Spread the scent)
        # "boundary='symm'" allows scent to bounce off the walls rather than vanish
        hive_grid = convolve2d(hive_grid, DIFFUSION_KERNEL, mode='same', boundary='symm')
        
        # 2. DECAY (Fade the scent)
        hive_grid *= DECAY_RATE
        
        # 3. EXPORT DATA (For the Web Dashboard)
        # We use a try/except block here so file access errors don't kill the Queen
        try:
            # Create the packet
            data_packet = {
                "grid": np.round(hive_grid, 1).tolist(), # Round to 1 decimal to save speed
                "peak": float(np.max(hive_grid))         # Highest value currently on the map
            }
            
            # Write to file
            with open("hive_state.json", "w") as f:
                json.dump(data_packet, f)
                
        except Exception as e:
            print(f"Write Error: {e}")

        # 4. TICK RATE
        time.sleep(0.1) # Run the physics update 10 times a second

except KeyboardInterrupt:
    print("\nStopping Brain...")
    client.loop_stop()
    print("Queen Sleeping.")

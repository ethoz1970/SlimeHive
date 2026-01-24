import paho.mqtt.client as mqtt
import time
import csv
import os
from datetime import datetime

# --- CONFIGURATION ---
LOG_DIR = "flight_logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Generate filename based on start time (e.g., flight_logs/session_2026-01-23_1430.csv)
filename = f"{LOG_DIR}/session_{datetime.now().strftime('%Y-%m-%d_%H%M')}.csv"

# Initialize CSV
with open(filename, "w", newline='') as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "drone_id", "x", "y", "intensity", "rssi"])

print(f"--- SCRIBE ONLINE ---")
print(f"Recording to: {filename}")

def on_message(client, userdata, msg):
    try:
        # Decode the message
        payload = msg.payload.decode('utf-8')
        parts = payload.split(',')
        
        # Ensure we have clean data
        if len(parts) == 5:
            # Add a precise timestamp (when we received it)
            timestamp = time.time()
            
            # Append to file immediately (flush so we don't lose data if power cuts)
            with open(filename, "a", newline='') as f:
                writer = csv.writer(f)
                # Row: [170604123.45, "28:AB", 10, 20, 50, -45]
                writer.writerow([timestamp] + parts)
                
            # Print a dot to show activity without spamming
            print(".", end="", flush=True)

    except Exception as e:
        print(f"Error: {e}")

# --- START LISTENER ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)
client.subscribe("hive/deposit")
client.on_message = on_message

try:
    client.loop_forever()
except KeyboardInterrupt:
    print(f"\nLog saved: {filename}")
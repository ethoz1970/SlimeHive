import paho.mqtt.client as mqtt
import time
import csv
import os
from datetime import datetime

# --- CONFIGURATION ---
LOG_DIR = "flight_logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Global file handle
current_file = None
current_filename = None

def start_new_log():
    global current_file, current_filename
    
    # Close existing if open
    if current_file:
        current_file.close()
        print(f"Closed log: {current_filename}")
        
    # Generate new filename
    current_filename = f"{LOG_DIR}/session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv"
    
    # Open new file
    current_file = open(current_filename, "w", newline='')
    writer = csv.writer(current_file)
    writer.writerow(["timestamp", "ear_id", "drone_id", "x", "y", "intensity", "rssi"])
    current_file.flush()
    
    print(f"--- SCRIBE ONLINE ---")
    print(f"Recording to: {current_filename}")

# Initial Start
start_new_log()

def on_message(client, userdata, msg):
    global current_file
    
    try:
        # --- RESET COMMAND ---
        if msg.topic == "hive/control/reset":
            print("\n/// ROTATING LOGS ///")
            start_new_log()
            return

        # --- DATA LOGGING ---
        # Decode the message
        payload = msg.payload.decode('utf-8')
        parts = payload.split(',')
        
        # Ensure we have clean data
        row_data = []
        if len(parts) == 6:
            # New Format: EAR_ID, ID, X, Y, INT, RSSI
            row_data = parts
        elif len(parts) == 5:
            # Old Format: ID, X, Y, INT, RSSI
            row_data = ["UNKNOWN"] + parts
        
        if row_data:
            # Add a precise timestamp (when we received it)
            timestamp = time.time()
            
            # Write to GLOBAL file handle
            if current_file:
                writer = csv.writer(current_file)
                writer.writerow([timestamp] + row_data)
                current_file.flush() # Ensure data is safe
                
            # Print a dot to show activity without spamming
            print(".", end="", flush=True)

    except Exception as e:
        print(f"Error: {e}")

# --- START LISTENER ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)
client.subscribe("hive/deposit")
client.subscribe("hive/control/reset") # Listen for reset
client.on_message = on_message

try:
    client.loop_forever()
except KeyboardInterrupt:
    if current_file:
        current_file.close()
    print(f"\nLog saved.")
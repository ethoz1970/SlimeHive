import paho.mqtt.client as mqtt
import time
import csv
import sys

# --- CONFIGURATION ---
# Usage: python3 hive_replay.py flight_logs/session_XXXX.csv
if len(sys.argv) < 2:
    print("Usage: python3 hive_replay.py <filename>")
    sys.exit(1)

filename = sys.argv[1]

# Connect to Brain
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)

print(f"--- REPLAYING SESSION: {filename} ---")
print("Press Ctrl+C to cancel")

try:
    with open(filename, "r") as f:
        reader = csv.reader(f)
        header = next(reader) # Skip header row
        
        rows = list(reader)
        if not rows:
            print("File is empty!")
            sys.exit()

        # Calibration: Get the start time of the recording
        start_time_log = float(rows[0][0])
        start_time_real = time.time()

        for row in rows:
            # Parse row
            # CSV: timestamp, drone_id, x, y, intensity, rssi
            log_ts = float(row[0])
            drone_id = row[1]
            x, y, intensity, rssi = row[2], row[3], row[4], row[5]

            # Calculate how long to wait to match the original rhythm
            # Target Time = (Log Time - Log Start)
            target_delay = log_ts - start_time_log
            
            # Current Time = (Real Time - Real Start)
            current_elapsed = time.time() - start_time_real
            
            wait_time = target_delay - current_elapsed
            
            if wait_time > 0:
                time.sleep(wait_time)

            # Reconstruct the message
            msg = f"{drone_id},{x},{y},{intensity},{rssi}"
            
            # Inject into the Hive
            client.publish("hive/deposit", msg)
            
            # Visual feedback
            print(f"\rReplay: [{drone_id}] at {x},{y}", end="")

    print("\n--- REPLAY COMPLETE ---")

except FileNotFoundError:
    print("File not found.")
except KeyboardInterrupt:
    print("\nReplay stopped.")
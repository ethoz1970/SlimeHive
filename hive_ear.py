import asyncio
from bleak import BleakScanner
import paho.mqtt.client as mqtt
import struct

# MQTT Setup (Updated for new API)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)
client.loop_start()

def detection_callback(device, advertisement_data):
    # Filter for our Drone ID (0xFFFF)
    if 0xFFFF in advertisement_data.manufacturer_data:
        data = advertisement_data.manufacturer_data[0xFFFF]
        
        if len(data) == 4:
            x, y, intensity = struct.unpack('<BBH', data)
            
            # --- NEW: GET PHYSICAL DISTANCE (RSSI) ---
            rssi = advertisement_data.rssi  # This is the signal strength (e.g., -55)
            
            # Print it so we can see the physics in action
            print(f"Drone at [{x},{y}] | Signal: {rssi}dBm")
            
            # We append the RSSI to the message so the Brain can use it
            client.publish("hive/deposit", f"{x},{y},{intensity},{rssi}")

async def main():
    print("--- HIVE EAR LISTENING (With RSSI) ---")
    scanner = BleakScanner(detection_callback)
    await scanner.start()
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
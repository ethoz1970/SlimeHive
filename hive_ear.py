import asyncio
from bleak import BleakScanner
import paho.mqtt.client as mqtt
import struct

# MQTT Setup
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect("localhost", 1883, 60)
client.loop_start()

def detection_callback(device, advertisement_data):
    # Filter for our Hive ID (0xFFFF)
    if 0xFFFF in advertisement_data.manufacturer_data:
        data = advertisement_data.manufacturer_data[0xFFFF]
        
        if len(data) == 4:
            x, y, intensity = struct.unpack('<BBH', data)
            rssi = advertisement_data.rssi
            
            # 1. Identify the Drone (Last 5 chars of MAC)
            drone_id = device.address[-5:]
            
            # 2. Print to Terminal (So you know it's working)
            print(f"[{drone_id}] Pos: [{x},{y}] | Signal: {rssi}dBm")
            
            # 3. SEND TO BRAIN (Crucial Fix: Include drone_id)
            # Format: ID, X, Y, Intensity, RSSI
            msg = f"{drone_id},{x},{y},{intensity},{rssi}"
            client.publish("hive/deposit", msg)

async def main():
    print("--- HIVE EAR LISTENING (Swarm ID Mode) ---")
    scanner = BleakScanner(detection_callback)
    await scanner.start()
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
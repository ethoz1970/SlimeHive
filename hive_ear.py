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
            
            # --- NEW: IDENTIFY THE DRONE ---
            # device.address is the MAC address (e.g., AA:BB:CC:11:22:33)
            # We take the last 5 chars to make a short name like "22:33"
            drone_id = device.address[-5:]
            
            print(f"[{drone_id}] Pos: [{x},{y}] | Signal: {rssi}dBm")
            
            # We send the ID to the brain too, just in case
            client.publish("hive/deposit", f"{x},{y},{intensity},{rssi}")

async def main():
    print("--- HIVE EAR LISTENING (Swarm Mode) ---")
    scanner = BleakScanner(detection_callback)
    await scanner.start()
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
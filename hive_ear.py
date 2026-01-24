import asyncio
from bleak import BleakScanner
import paho.mqtt.client as mqtt
import struct

# MQTT Setup
client = mqtt.Client()
client.connect("localhost", 1883, 60)
client.loop_start()

def detection_callback(device, advertisement_data):
    """
    Called every time the Bluetooth radio hears a shout.
    """
    # Filter: Only listen to our specific Manufacturer ID (0xFFFF)
    if 0xFFFF in advertisement_data.manufacturer_data:
        data = advertisement_data.manufacturer_data[0xFFFF]
        
        if len(data) == 4: # We expect 4 bytes (x, y, intensity_low, intensity_high)
            # Unpack the bytes back into numbers
            x, y, intensity = struct.unpack('<BBH', data)
            
            # Print for debug
            print(f"Heard Drone: [{x}, {y}] Int: {intensity}")
            
            # Publish to the Brain (Brain doesn't know it's Bluetooth!)
            client.publish("hive/deposit", f"{x},{y},{intensity}")

async def main():
    print("--- HIVE EAR LISTENING (Bluetooth) ---")
    scanner = BleakScanner(detection_callback)
    await scanner.start()
    
    # Keep scanning forever
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped.")
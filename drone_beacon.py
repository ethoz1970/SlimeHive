import os
import time
import struct

# --- CONFIGURATION ---
# This script turns the Pi Zero into a BLE Beacon
# It broadcasts Manufacturer Data: 0xFFFF + [X, Y, Intensity]
# X/Y are dummy variables (0,0) because the Brain calculates Position.

def set_advertising_data():
    print("Configuring BLE Beacon...")
    
    # 1. Reset Device
    os.system("sudo hciconfig hci0 down")
    os.system("sudo hciconfig hci0 up")
    
    # 2. Packet Structure construction
    # Header: 0x1E (Length 30), 0xFF (Manufacturer Specific)
    # Company ID: 0xFF 0xFF (Testing ID)
    # Data: X(0), Y(0), Intensity(255 -> 0xFF 0x00)
    # Format for 'hcitool -i hci0 cmd ...' needs hex bytes
    
    # Let's construct it manually to be safe
    # Command: OGF=0x08, OCF=0x0008 (LE Set Advertising Data)
    # Param: Length (31), Data...
    
    # Actually, simpler method: using hcitool cmd
    # We want: 
    # Length: 0x07 (Total data length)
    # Type: 0xFF (Manufacturer)
    # ID: 0xFF 0xFF
    # Payload: 0x00 0x00 0xFF 0x00 (4 bytes)
    # Total payload: 7 bytes.
    
    # Valid hcitool string:
    # 08 0008 (Set Data)
    # 1f (31 bytes max)
    # 07 (Length of element)
    # ff (Type)
    # ff ff (Company)
    # 00 00 ff 00 (Payload)
    # ... padding zeros ...
    
    cmd = "sudo hcitool -i hci0 cmd 0x08 0x0008 1f 07 ff ff ff 00 00 ff 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
    os.system(cmd)
    
    # 3. Set Advertising Parameters (Interval)
    # Min Interval: 100ms (0x00A0), Max: 100ms
    os.system("sudo hcitool -i hci0 cmd 0x08 0x0006 A0 00 A0 00 03 00 00 00 00 00 00 00 07 00")
    
    # 4. Enable Advertising
    os.system("sudo hcitool -i hci0 cmd 0x08 0x000a 01")
    
    print("/// DRONE BEACON ACTIVE ///")
    print("Broadcasting ID: 0xFFFF Payload: [0,0,255]")

if __name__ == "__main__":
    try:
        set_advertising_data()
        while True:
            # Keep script alive, though `hcitool` sets the state in kernel
            time.sleep(10)
    except KeyboardInterrupt:
        print("Stopping Beacon...")
        os.system("sudo hciconfig hci0 noleadv")

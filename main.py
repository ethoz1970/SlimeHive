import bluetooth
import time
import struct
import machine
import random

# --- CONFIGURATION (THE QUEEN BEE) ---
GRID_SIZE = 100
current_x = GRID_SIZE // 2
current_y = GRID_SIZE // 2
led = machine.Pin("LED", machine.Pin.OUT)

# Initialize Bluetooth
ble = bluetooth.BLE()
ble.active(True)

def virtual_move():
    global current_x, current_y
    direction = random.randint(0, 3)
    
    # Standard Movement
    if direction == 0 and current_y < GRID_SIZE - 1:
        current_y += 1
    elif direction == 1 and current_y > 0:
        current_y -= 1
    elif direction == 2 and current_x > 0:
        current_x -= 1
    elif direction == 3 and current_x < GRID_SIZE - 1:
        current_x += 1
    return current_x, current_y

def advertise(x, y, intensity):
    payload = struct.pack('<BBH', x, y, intensity)
    adv_data = b'\x02\x01\x06' + b'\x07\xFF\xFF\xFF' + payload
    ble.gap_advertise(100000, adv_data)
    led.toggle()

print("--- QUEEN BEE ACTIVE (MAX INTENSITY) ---")

try:
    while True:
        new_x, new_y = virtual_move()
        
        # --- THE GOLDEN TOUCH ---
        # No 10% chance here. 
        # ALWAYS broadcast at SUPER INTENSITY (2000)
        # This will turn the map pixels White immediately.
        intensity = 2000 
        
        advertise(new_x, new_y, intensity)
        
        # Slightly slower/more majestic speed? (Optional)
        time.sleep(0.2) 

except Exception as e:
    machine.reset()


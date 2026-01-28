# P2P Neighbor Awareness for Pico 2W Drones

## Overview

This document outlines a plan to add peer-to-peer (P2P) neighbor detection to the SlimeHive drone swarm. Currently, drones only communicate through the Queen (centralized). This upgrade would allow drones to directly sense other nearby drones via BLE scanning.

**Status:** Planning phase - drones are currently stationary (untethered but not mobile)

---

## Current Architecture

### Communication Flow (Centralized)
```
Pico 2W Drones (BLE Advertise)
        ↓
   Ears (BLE Scan)
        ↓ MQTT: hive/deposit
   Queen Brain
        ↓
   Pheromone Grids
```

### Current Drone Firmware (`main.py`)
- Random walk simulation (virtual position)
- BLE advertising every 200ms
- Payload: `[X, Y, Intensity]` with manufacturer ID `0xFFFF`
- No scanning capability
- No awareness of other drones

---

## Proposed Architecture

### Communication Flow (Hybrid P2P + Centralized)
```
┌─────────────────────────────────────────────────────────┐
│                    PICO 2W DRONE                        │
│                                                         │
│   ┌───────────────┐         ┌───────────────┐          │
│   │   ADVERTISE   │         │     SCAN      │          │
│   │   (ongoing)   │         │  (periodic)   │          │
│   │               │         │               │          │
│   │ Broadcasts:   │         │ Detects:      │          │
│   │ - Position    │         │ - Other drones│          │
│   │ - Intensity   │         │ - Their RSSI  │          │
│   │ - Neighbor #  │◄───────►│               │          │
│   └───────────────┘         └───────┬───────┘          │
│                                     │                  │
│                            ┌────────▼────────┐         │
│                            │   neighbors{}   │         │
│                            │  {id: rssi, ..} │         │
│                            └────────┬────────┘         │
│                                     │                  │
│                            ┌────────▼────────┐         │
│                            │ LOCAL BEHAVIOR  │         │
│                            │ (when mobile)   │         │
│                            └─────────────────┘         │
└─────────────────────────────────────────────────────────┘
        ↓ (BLE Advertisement)
   Ears (existing) → Queen Brain (existing)
```

---

## How Real Ants Handle Proximity

For biological inspiration:

| Mechanism | Description | Analogue in SlimeHive |
|-----------|-------------|----------------------|
| **Antennation** | Physical touch with antennae to identify nestmates | RSSI > -30 dBm (very close) |
| **Pheromone density** | Sensing local concentration indicates crowding | Neighbor count in advertisement |
| **Stridulation** | Body vibrations for short-range alarm signals | Could use intensity field as "alarm" |
| **Trail following** | Follow chemical gradients left by others | Already implemented via ghost grid |

### Key Insight
Ants don't just follow pheromone trails - they actively sense nearby ants and adjust:
- **Too crowded?** Move to less dense area
- **Neighbor alarmed?** Heighten alertness
- **Isolated?** Seek out others

---

## Implementation Plan

### Phase 1: Add Scanning to Drones

#### Updated `main.py` Structure

```python
import bluetooth
import time
import struct
import machine
import random

# --- CONFIGURATION ---
GRID_SIZE = 100
SCAN_DURATION_MS = 2000      # Scan for 2 seconds
SCAN_INTERVAL_MS = 10000     # Every 10 seconds
HIVE_MFG_ID = b'\xFF\xFF'    # Our hive identifier

# --- STATE ---
current_x = GRID_SIZE // 2
current_y = GRID_SIZE // 2
neighbors = {}               # {drone_id_hex: rssi}
last_scan_time = 0
led = machine.Pin("LED", machine.Pin.OUT)

# --- BLE SETUP ---
ble = bluetooth.BLE()
ble.active(True)

# --- IRQ HANDLER (for scan results) ---
_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6

def ble_irq(event, data):
    global neighbors

    if event == _IRQ_SCAN_RESULT:
        addr_type, addr, adv_type, rssi, adv_data = data

        # Check for our hive's manufacturer ID
        if HIVE_MFG_ID in bytes(adv_data):
            # Use last 2 bytes of MAC as drone ID
            drone_id = bytes(addr[-2:]).hex()

            # Don't count ourselves (though we shouldn't see our own ads)
            # Update neighbor with latest RSSI
            neighbors[drone_id] = rssi

    elif event == _IRQ_SCAN_DONE:
        # Scan complete - neighbors dict is now current
        pass

ble.irq(ble_irq)

# --- SCANNING ---
def scan_for_neighbors():
    """Start a BLE scan to detect nearby drones"""
    global neighbors
    neighbors = {}  # Clear old data

    # gap_scan(duration_ms, interval_us, window_us)
    # Scan for 2 seconds with continuous window
    ble.gap_scan(SCAN_DURATION_MS, 30000, 30000)

# --- ADVERTISING ---
def advertise(x, y, intensity, neighbor_count):
    """Broadcast our position and neighbor count"""
    # Pack: X(1), Y(1), Intensity(2), NeighborCount(1)
    payload = struct.pack('<BBHB', x, y, intensity, neighbor_count)

    # BLE advertisement structure:
    # 02 01 06 = Flags (LE General Discoverable)
    # 08 FF FF FF = Length(8), Type(Manufacturer), Company(0xFFFF)
    # + payload (5 bytes)
    adv_data = b'\x02\x01\x06' + bytes([len(payload)+3, 0xFF, 0xFF, 0xFF]) + payload

    ble.gap_advertise(100000, adv_data)  # 100ms interval
    led.toggle()

# --- MOVEMENT (virtual for now) ---
def virtual_move():
    """Random walk - replace with real movement when mobile"""
    global current_x, current_y
    direction = random.randint(0, 3)

    if direction == 0 and current_y < GRID_SIZE - 1:
        current_y += 1
    elif direction == 1 and current_y > 0:
        current_y -= 1
    elif direction == 2 and current_x > 0:
        current_x -= 1
    elif direction == 3 and current_x < GRID_SIZE - 1:
        current_x += 1

    return current_x, current_y

# --- NEIGHBOR-AWARE MOVEMENT (for future) ---
def neighbor_aware_move():
    """
    Movement decisions based on nearby drones.
    PLACEHOLDER - implement when drones are mobile.
    """
    global current_x, current_y

    if not neighbors:
        # No neighbors detected - random walk
        return virtual_move()

    # Find closest neighbor (highest RSSI = closest)
    closest_id = max(neighbors, key=neighbors.get)
    closest_rssi = neighbors[closest_id]

    # RSSI thresholds (approximate):
    # > -30 dBm = very close (< 0.5m) - AVOID
    # -30 to -50 = close (0.5-2m) - comfortable
    # -50 to -70 = medium (2-5m) - could approach
    # < -70 = far (> 5m) - seek if flocking

    if closest_rssi > -30:
        # Too close! Move away (opposite of approach)
        # This is a placeholder - real implementation needs
        # to know DIRECTION of neighbor, not just distance
        pass
    elif closest_rssi < -70 and len(neighbors) < 2:
        # Isolated - seek others (flocking behavior)
        pass
    else:
        # Comfortable distance - random walk
        return virtual_move()

    return current_x, current_y

# --- MAIN LOOP ---
print("--- DRONE ACTIVE (P2P AWARE) ---")

try:
    while True:
        current_time = time.ticks_ms()

        # Periodic scanning
        if time.ticks_diff(current_time, last_scan_time) > SCAN_INTERVAL_MS:
            scan_for_neighbors()
            last_scan_time = current_time
            print(f"Neighbors: {neighbors}")

        # Movement (virtual for now)
        new_x, new_y = virtual_move()

        # Advertise with neighbor count
        intensity = 2000
        neighbor_count = min(len(neighbors), 255)
        advertise(new_x, new_y, intensity, neighbor_count)

        time.sleep(0.2)

except Exception as e:
    print(f"Error: {e}")
    machine.reset()
```

### Phase 2: Update Advertisement Payload

#### Current Payload (4 bytes)
```
[X:1][Y:1][Intensity:2]
```

#### New Payload (5 bytes)
```
[X:1][Y:1][Intensity:2][NeighborCount:1]
```

The ears and Queen Brain can parse this to know how "crowded" each drone feels.

### Phase 3: Queen Brain Updates (Optional)

If we want the Queen to track neighbor relationships:

```python
# In queen_brain.py - add to on_message()

# Parse neighbor count from deposit message
# Updated format: EAR_ID,DRONE_ID,X,Y,INTENSITY,RSSI,NEIGHBOR_COUNT
parts = msg.split(',')
if len(parts) >= 7:
    neighbor_count = int(parts[6])
    active_drones[drone_id]['neighbors'] = neighbor_count
```

---

## Local Behaviors (When Mobile)

### Behavior 1: Collision Avoidance
```python
if closest_rssi > -30:  # Very close
    # Move in random direction away
    # (Without knowing neighbor direction, random escape is best)
    move_random()
```

### Behavior 2: Flocking / Cohesion
```python
if len(neighbors) == 0:
    # Isolated - slow down, wait for others
    speed = SLOW_SPEED
elif avg_rssi < -60:
    # Neighbors are far - move more to find them
    speed = FAST_SPEED
```

### Behavior 3: Alarm Cascade
```python
# If a neighbor suddenly disappears (was close, now gone)
if drone_id in previous_neighbors and drone_id not in neighbors:
    if previous_neighbors[drone_id] > -40:  # Was very close
        alarm_state = True
        intensity = MAX_INTENSITY  # Signal alarm to others
```

### Behavior 4: Density Regulation
```python
if len(neighbors) > 3:
    # Crowded - move to less dense area
    # Random walk with bias away from center
    bias_outward()
elif len(neighbors) < 1:
    # Too sparse - move toward center
    bias_inward()
```

---

## Performance Considerations

### BLE Radio Time-Sharing

The Pico 2W's CYW43439 can handle concurrent advertising and scanning, but there are tradeoffs:

| Parameter | Value | Notes |
|-----------|-------|-------|
| Advertise interval | 100ms | Current setting |
| Scan duration | 2000ms | Long enough to catch neighbors |
| Scan interval | 10000ms | Balance freshness vs. battery |
| Scan window | 30ms | How long radio listens per interval |

### Power Consumption (Estimated)

| Mode | Current Draw |
|------|--------------|
| Advertise only (current) | ~25mA average |
| Advertise + periodic scan | ~35mA average |
| Continuous scan | ~80mA (not recommended) |

### CPU Usage

- Advertising: Negligible (hardware handles it)
- Scanning: Low (IRQ-driven, hardware filters)
- Processing neighbors: Minimal (dictionary operations)

**Dual-core advantage:** Could dedicate Core 1 to BLE operations.

---

## Testing Plan

### Phase 1: Verify Scanning Works
1. Flash two Picos with P2P firmware
2. Check that each detects the other
3. Verify RSSI values are sensible
4. Confirm advertising still works (ears can see both)

### Phase 2: Test Neighbor Count Propagation
1. Add neighbor count to advertisement
2. Update ear parsing (if needed)
3. Verify Queen sees neighbor counts in dashboard

### Phase 3: Behavior Testing (When Mobile)
1. Place two mobile drones close together
2. Verify avoidance behavior triggers
3. Test flocking when separated
4. Measure response latency

---

## Future Enhancements

### Directional Awareness
Current limitation: RSSI only tells us distance, not direction. Options:
- Multiple BLE antennas (hardware change)
- Triangulation from movement (if neighbor RSSI changes as we move)
- UWB modules for precise ranging (hardware upgrade)

### Mesh Networking
Beyond neighbor detection, drones could relay messages:
- Drone A tells Drone B about Drone C
- Extends effective range of swarm awareness
- Requires more complex protocol

### Neighbor Identification
Currently we identify neighbors by MAC address suffix. Could add:
- Role identification (scout, worker, queen)
- State sharing (alarmed, exploring, returning)
- Task coordination (you go left, I'll go right)

---

## Hardware Requirements

| Component | Current | With P2P |
|-----------|---------|----------|
| Pico 2W | Yes | Yes (no change) |
| Battery | Required | Same (slightly more drain) |
| Motors/wheels | No | Required for mobile behaviors |
| Additional sensors | No | Optional (for direction sensing) |

---

## Summary

Adding P2P neighbor awareness transforms the swarm from purely Queen-coordinated to having local intelligence. This mirrors how real ant colonies work - global coordination through pheromones (our grid) combined with local awareness of immediate neighbors.

**Key benefits:**
- Collision avoidance without Queen involvement
- Faster local reactions (no network round-trip)
- Swarm resilience if Queen connection is lost
- More natural, emergent swarm behaviors

**Implementation complexity:** Low-Medium
- Firmware changes are straightforward
- BLE hardware supports it natively
- Main challenge is designing effective local behaviors

**Recommended next step:** Test scanning capability on two stationary drones before adding mobility.

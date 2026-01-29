# Playback Enhancement Plan

## Current Problem
- Playback shows only a static snapshot of the archive
- Play button is disabled when no matching flight log CSV exists
- Old archives have no recorded flight data
- Virtual drones weren't publishing to MQTT (just fixed)

## Current Architecture
```
Archive (snapshot)     Flight Log (CSV)
├── grid[][]           ├── timestamp
├── ghost_grid[][]     ├── drone_id
├── drones{}           ├── x, y
│   ├── x, y           ├── intensity
│   ├── trail[]        └── rssi
│   └── last_seen
└── mood, decay_rate
```

## Proposed Solution

### Option A: Always Enable Playback with Fallback Simulation
When no flight log exists, generate simulated movement based on archive data.

**How it works:**
1. If flight log exists → use real recorded data (current behavior)
2. If no flight log → generate synthetic animation:
   - Use drone positions from archive as starting points
   - Simulate random walks or trail-based movement
   - Animate pheromone grid decay over time
   - Show "SIMULATED" indicator

### Option B: Flight Log Selection List
Instead of auto-matching, show a dropdown of all available flight logs and let user pick one to replay.

**How it works:**
1. Load any archive for the grid/pheromone state
2. Show list of all flight logs (not just matching ones)
3. User selects which session to replay
4. Play selected flight log over the archive visualization

## Recommended: Hybrid Approach (A + B)

### Changes to Playback UI
1. **Play button always enabled** - never disabled
2. **Mode selector**:
   - "RECORDED" - use matched flight log (if available)
   - "SIMULATE" - generate movement from archive state
   - Dropdown of all flight logs to manually select
3. **Timeline shows**: data points for recorded, simulated duration for simulate mode
4. **Visual indicator**: "SIMULATED" or "RECORDED" badge during playback

### Implementation Steps

1. **Modify `checkFlightLog()`**:
   - Don't disable button if no match
   - Set `playbackMode` variable: "recorded", "simulated", or "manual"
   - Store list of all flight logs for dropdown

2. **Add flight log dropdown**:
   - Show all available flight logs
   - Allow manual selection regardless of timestamp matching

3. **Add `generateSimulatedData()` function**:
   - Takes archive drones as input
   - Generates N frames of simulated movement
   - Drones do random walks from their positions
   - Returns array matching flightData format

4. **Modify `startPlayback()`**:
   - If recorded mode: use flightData (current)
   - If simulated mode: call generateSimulatedData()

5. **Add visual indicators**:
   - Badge showing "SIMULATED" vs "RECORDED"
   - Different timeline color for simulated

### Simulated Movement Algorithm
```javascript
function generateSimulatedData(drones, frameCount = 200) {
    const data = [];
    const positions = {};

    // Initialize positions from archive
    for (const [id, drone] of Object.entries(drones)) {
        positions[id] = { x: drone.x, y: drone.y };
    }

    // Generate frames
    for (let frame = 0; frame < frameCount; frame++) {
        const timestamp = Date.now()/1000 + frame * 0.1;

        for (const [id, pos] of Object.entries(positions)) {
            // Random walk
            pos.x += Math.floor(Math.random() * 3) - 1;
            pos.y += Math.floor(Math.random() * 3) - 1;
            pos.x = Math.max(0, Math.min(gridSize-1, pos.x));
            pos.y = Math.max(0, Math.min(gridSize-1, pos.y));

            data.push({
                timestamp,
                drone_id: id,
                x: pos.x,
                y: pos.y,
                intensity: 50,
                rssi: -50
            });
        }
    }
    return data;
}
```

## Files to Modify
- `dashboard_hud.py`: PLAYBACK_TEMPLATE section
  - Add mode selector/dropdown
  - Add generateSimulatedData() function
  - Modify checkFlightLog() to not disable button
  - Add visual indicators

## Effort Estimate
- Small/Medium change - mostly JavaScript in the playback template

---

# Plan: End Simulation When All Drones Die

## Goal
End the simulation early if all drones die (when death_mode is "yes"), rather than continuing to run with zero drones.

## Changes Required

### 1. Modify `run()` in simulate.py

Add a check after `self.tick()` in the simulation loop:

```python
# Simulation loop
for tick in range(total_ticks):
    tick_start = time.time()

    # Run simulation tick
    self.tick()

    # Check for extinction (all drones dead)
    if len(self.drones) == 0:
        print()
        print("  !!! ALL DRONES HAVE DIED - SIMULATION ENDING !!!")
        break

    # ... rest of loop
```

### 2. Update final report

Add indication that simulation ended due to extinction vs normal completion:

```python
# After the loop
if len(self.drones) == 0:
    print("    Ended:               EXTINCTION (all drones died)")
else:
    print("    Ended:               COMPLETED")
```

## Files to Modify
- `simulate.py`: Add extinction check in `run()` loop and final report

## Testing

```bash
python simulate.py --mode FORAGE --food-sources 0 --drones 5 --duration 30 --hunger-decay 2 --death-mode yes --no-live
```

Expected: Simulation should end around tick 200 with extinction message instead of running full 30 seconds.

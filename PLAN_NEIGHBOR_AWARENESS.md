# Plan: Add Neighbor Awareness to Virtual Drones

## Goal
Give virtual drones the same neighbor awareness capabilities we're planning for real Pico 2W drones, allowing us to test P2P behaviors in simulation before deploying to hardware.

---

## Current State

### Virtual Drone Behavior Modes (`queen_brain.py:332-454`)
| Mode | Description | Neighbor Aware? |
|------|-------------|-----------------|
| FIND_QUEEN | Move toward Queen position | No |
| PATROL | Walk perimeter clockwise | No |
| SWARM | Move toward center of mass | Partial (global, not local) |
| SCATTER | Move away from center | No |
| TRAIL_FOLLOW | Follow pheromone gradients | No (grid-aware, not drone-aware) |
| RANDOM | Random walk | No |

### What's Missing
1. **Individual neighbor detection** - "Which drones are within N units of me?"
2. **Collision avoidance** - Drones can stack on same cell
3. **Local density sensing** - "Am I crowded or isolated?"
4. **Alarm cascade** - React when neighbor disappears
5. **Neighbor-influenced movement** - Attract/repel based on proximity

---

## Implementation Plan

### Step 1: Add `get_neighbors()` Helper Function

Calculate neighbors for any drone based on distance:

```python
def get_neighbors(drone_id, max_distance=5):
    """
    Find all drones within max_distance of the given drone.
    Returns: {neighbor_id: {"distance": float, "x": int, "y": int}}
    """
    drone = active_drones.get(drone_id)
    if not drone:
        return {}

    neighbors = {}
    my_x, my_y = drone["x"], drone["y"]

    for other_id, other in active_drones.items():
        if other_id == drone_id:
            continue

        dx = other["x"] - my_x
        dy = other["y"] - my_y
        dist = (dx**2 + dy**2) ** 0.5

        if dist <= max_distance:
            neighbors[other_id] = {
                "distance": dist,
                "dx": dx,  # Direction to neighbor
                "dy": dy,
                "x": other["x"],
                "y": other["y"]
            }

    return neighbors
```

### Step 2: Add Neighbor Data to Drone State

Update drone registry to track neighbor info:

```python
# In active_drones[drone_id], add:
{
    "x": 50,
    "y": 50,
    "neighbors": {"V-1": 3.2, "V-2": 4.5},  # NEW: {id: distance}
    "neighbor_count": 2,                      # NEW
    "isolated": False,                        # NEW (no neighbors within range)
    "crowded": False,                         # NEW (>3 neighbors very close)
    ...
}
```

### Step 3: New Behavior Mode - "BOIDS"

Classic Boids algorithm with three rules:

```python
elif SIMULATION_MODE == "BOIDS":
    neighbors = get_neighbors(v_id, max_distance=15)

    # Initialize movement vectors
    sep_x, sep_y = 0, 0  # Separation
    coh_x, coh_y = 0, 0  # Cohesion
    ali_x, ali_y = 0, 0  # Alignment

    close_neighbors = {k: v for k, v in neighbors.items() if v["distance"] < 3}

    # RULE 1: SEPARATION - Avoid crowding neighbors
    if close_neighbors:
        for nid, ndata in close_neighbors.items():
            # Vector pointing AWAY from neighbor
            sep_x -= ndata["dx"]
            sep_y -= ndata["dy"]

    # RULE 2: COHESION - Steer toward average position of neighbors
    if neighbors:
        avg_x = sum(n["x"] for n in neighbors.values()) / len(neighbors)
        avg_y = sum(n["y"] for n in neighbors.values()) / len(neighbors)
        coh_x = avg_x - drone["x"]
        coh_y = avg_y - drone["y"]

    # RULE 3: ALIGNMENT - Match velocity with neighbors
    # (Requires tracking previous positions - see Step 4)

    # Combine forces with weights
    dx = int(np.sign(sep_x * 2.0 + coh_x * 0.5 + ali_x * 1.0))
    dy = int(np.sign(sep_y * 2.0 + coh_y * 0.5 + ali_y * 1.0))

    # Add randomness to prevent deadlock
    if random.random() < 0.2:
        dx += random.choice([-1, 0, 1])
        dy += random.choice([-1, 0, 1])
```

### Step 4: Track Velocity for Alignment

Add velocity tracking to drones:

```python
# When updating position, calculate velocity
drone["prev_x"] = drone.get("x", new_x)
drone["prev_y"] = drone.get("y", new_y)
drone["x"] = new_x
drone["y"] = new_y
drone["vx"] = new_x - drone["prev_x"]
drone["vy"] = new_y - drone["prev_y"]
```

Then alignment becomes:

```python
# RULE 3: ALIGNMENT - Match velocity with neighbors
if neighbors:
    avg_vx = sum(active_drones[nid].get("vx", 0) for nid in neighbors) / len(neighbors)
    avg_vy = sum(active_drones[nid].get("vy", 0) for nid in neighbors) / len(neighbors)
    ali_x = avg_vx
    ali_y = avg_vy
```

### Step 5: Add "AVOID" Mode (Separation Only)

Pure collision avoidance for testing:

```python
elif SIMULATION_MODE == "AVOID":
    neighbors = get_neighbors(v_id, max_distance=5)

    if neighbors:
        # Find closest neighbor
        closest_id = min(neighbors, key=lambda k: neighbors[k]["distance"])
        closest = neighbors[closest_id]

        if closest["distance"] < 2:
            # Too close! Move directly away
            dx = -int(np.sign(closest["dx"]))
            dy = -int(np.sign(closest["dy"]))
        else:
            # Comfortable distance, random walk
            dx = random.choice([-1, 0, 1])
            dy = random.choice([-1, 0, 1])
    else:
        # No neighbors, random walk
        dx = random.choice([-1, 0, 1])
        dy = random.choice([-1, 0, 1])
```

### Step 6: Add "FLOCK" Mode (Cohesion + Separation)

Balanced flocking:

```python
elif SIMULATION_MODE == "FLOCK":
    neighbors = get_neighbors(v_id, max_distance=10)

    dx, dy = 0, 0

    # If isolated, move toward swarm center
    if len(neighbors) == 0:
        all_drones = [d for did, d in active_drones.items() if did.startswith(VIRTUAL_PREFIX)]
        if len(all_drones) > 1:
            cx = sum(d["x"] for d in all_drones) / len(all_drones)
            cy = sum(d["y"] for d in all_drones) / len(all_drones)
            dx = int(np.sign(cx - drone["x"]))
            dy = int(np.sign(cy - drone["y"]))
    else:
        # Separation from close neighbors
        close = {k: v for k, v in neighbors.items() if v["distance"] < 3}
        if close:
            for ndata in close.values():
                dx -= int(np.sign(ndata["dx"]))
                dy -= int(np.sign(ndata["dy"]))
        else:
            # Cohesion toward neighbor center
            avg_x = sum(n["x"] for n in neighbors.values()) / len(neighbors)
            avg_y = sum(n["y"] for n in neighbors.values()) / len(neighbors)
            dx = int(np.sign(avg_x - drone["x"]))
            dy = int(np.sign(avg_y - drone["y"]))

    # Randomness
    if random.random() < 0.3:
        dx = random.choice([-1, 0, 1])
        dy = random.choice([-1, 0, 1])
```

---

## Dashboard Updates

### Add New Modes to Mode Selector

In `live.html` or dashboard, add the new modes:

```html
<select id="mode-select">
    <option value="RANDOM">RANDOM</option>
    <option value="FIND_QUEEN">FIND QUEEN</option>
    <option value="PATROL">PATROL</option>
    <option value="SWARM">SWARM</option>
    <option value="SCATTER">SCATTER</option>
    <option value="TRAIL_FOLLOW">TRAIL FOLLOW</option>
    <!-- NEW MODES -->
    <option value="BOIDS">BOIDS (Full)</option>
    <option value="AVOID">AVOID (Separation)</option>
    <option value="FLOCK">FLOCK (Cohesion+Sep)</option>
</select>
```

### Visualize Neighbor Connections (Optional)

Show lines between neighboring drones:

```javascript
// In dashboard rendering, after drawing drones:
if (showNeighborConnections) {
    for (const [id, drone] of Object.entries(data.drones)) {
        if (drone.neighbors) {
            for (const [neighborId, distance] of Object.entries(drone.neighbors)) {
                const neighbor = data.drones[neighborId];
                if (neighbor) {
                    const alpha = Math.max(0.1, 1 - distance / 10);
                    ctx.strokeStyle = `rgba(255, 255, 255, ${alpha})`;
                    ctx.beginPath();
                    ctx.moveTo(drone.x * scale, drone.y * scale);
                    ctx.lineTo(neighbor.x * scale, neighbor.y * scale);
                    ctx.stroke();
                }
            }
        }
    }
}
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `queen_brain.py` | Add `get_neighbors()`, new behavior modes (BOIDS, AVOID, FLOCK), velocity tracking |
| `templates/live.html` | Add new mode options to dropdown |
| `static/js/live.js` | (Optional) Visualize neighbor connections |

---

## Implementation Order

1. **Add `get_neighbors()` function** - Core utility (~10 lines)
2. **Add AVOID mode** - Simplest test of neighbor awareness
3. **Test AVOID mode** - Verify drones spread out
4. **Add FLOCK mode** - Cohesion + separation
5. **Add velocity tracking** - Required for alignment
6. **Add BOIDS mode** - Full implementation
7. **Update dashboard dropdown** - Expose new modes
8. **(Optional) Neighbor visualization** - Debug/demo feature

---

## Testing Scenarios

### Test 1: Collision Avoidance (AVOID mode)
1. Set mode to AVOID
2. Spawn 5 virtual drones with `/set_virtual_swarm?count=5`
3. Observe: drones should NOT stack on same cells
4. Expected: drones maintain ~2-3 cell separation

### Test 2: Cohesion (FLOCK mode)
1. Set mode to FLOCK
2. Spawn drones spread across the grid
3. Observe: isolated drones move toward others
4. Expected: drones form loose cluster

### Test 3: Boids Behavior (BOIDS mode)
1. Set mode to BOIDS
2. Spawn 10+ virtual drones
3. Observe: swarm should move together, avoiding collisions
4. Expected: natural-looking flock movement

### Test 4: Density Regulation
1. Set mode to FLOCK
2. Spawn 20 drones in center
3. Observe: drones spread until comfortable density
4. Expected: even distribution across operational area

---

## Comparison with Pico 2W Implementation

| Feature | Virtual (queen_brain.py) | Pico 2W (main.py) |
|---------|--------------------------|-------------------|
| Neighbor detection | Queen calculates distances | BLE RSSI scanning |
| Distance metric | Euclidean (exact) | RSSI (approximate) |
| Update rate | 10Hz (physics loop) | Every 10s (scan interval) |
| Direction to neighbor | Known (dx, dy) | Unknown (RSSI only) |
| Processing | Central (Queen) | Local (each Pico) |

**Key insight:** Virtual drones have MORE information (exact positions, directions) than real drones will have (just RSSI). Behaviors that work in simulation should work even better on real hardware, not worse.

---

## Success Criteria

1. [ ] `get_neighbors()` function returns correct neighbor lists
2. [ ] AVOID mode prevents drones from occupying same cell
3. [ ] FLOCK mode creates cohesive groups that don't stack
4. [ ] BOIDS mode produces natural swarm movement
5. [ ] New modes selectable from dashboard
6. [ ] No performance degradation with 20+ virtual drones
7. [ ] Behaviors match P2P_NEIGHBOR_AWARENESS.md specification

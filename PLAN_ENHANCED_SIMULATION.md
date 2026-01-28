# Plan: Enhanced Simulation Mode for MacBook

## Goal
Create a high-performance simulation environment that leverages the M3 Pro's power for swarm behavior research, while maintaining connection to the main project.

---

## Features

### 1. Higher Performance
| Parameter | Current | Enhanced |
|-----------|---------|----------|
| Tick rate | 10 Hz | 30-60 Hz |
| Max drones | ~20 | 200+ |
| Grid size | 100x100 | Up to 500x500 |

### 2. Research Metrics
- Average neighbor distance
- Clustering coefficient
- Swarm cohesion score
- Collision count
- Coverage percentage
- Velocity alignment

### 3. Batch Experiments
- Run multiple simulations with varying parameters
- Compare behavior modes automatically
- Export CSV results for analysis

### 4. Session Recording
- Record simulation sessions
- Replay on dashboard
- Export configs to real hardware

---

## Implementation

### File Structure
```
SlimeHive/
├── simulate.py              # NEW: Enhanced simulation runner
├── config/
│   └── simulation.json      # NEW: Simulation parameters
├── queen_brain.py           # Existing (shared behavior logic)
└── analysis/                # NEW: Output directory
    ├── metrics/
    └── sessions/
```

### New Files to Create

1. **`config/simulation.json`** - Configuration
2. **`simulate.py`** - Enhanced simulation runner
3. **`analysis/`** - Output directory for results

---

## config/simulation.json

```json
{
    "simulation": {
        "tick_rate": 30,
        "duration_seconds": 300,
        "grid_size": 100,
        "headless": false
    },
    "drones": {
        "count": 50,
        "spawn_pattern": "random",
        "behavior_mode": "BOIDS"
    },
    "behavior_params": {
        "separation_distance": 3,
        "separation_weight": 2.0,
        "cohesion_weight": 0.5,
        "alignment_weight": 1.0,
        "neighbor_radius": 15,
        "move_probability": 1.0
    },
    "metrics": {
        "enabled": true,
        "sample_rate": 1,
        "export_csv": true
    },
    "recording": {
        "enabled": true,
        "output_dir": "analysis/sessions"
    }
}
```

---

## simulate.py

```python
#!/usr/bin/env python3
"""
Enhanced Simulation Runner for SlimeHive
Optimized for M3 Pro - high tick rate, many drones, metrics collection
"""

import numpy as np
import json
import time
import os
import csv
import argparse
from datetime import datetime
from collections import defaultdict

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config", "simulation.json")
DEFAULT_CONFIG = {
    "simulation": {"tick_rate": 30, "duration_seconds": 60, "grid_size": 100, "headless": False},
    "drones": {"count": 20, "spawn_pattern": "random", "behavior_mode": "BOIDS"},
    "behavior_params": {
        "separation_distance": 3, "separation_weight": 2.0,
        "cohesion_weight": 0.5, "alignment_weight": 1.0,
        "neighbor_radius": 15, "move_probability": 1.0
    },
    "metrics": {"enabled": True, "sample_rate": 1, "export_csv": True},
    "recording": {"enabled": False, "output_dir": "analysis/sessions"}
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG

# --- STATE ---
config = load_config()
GRID_SIZE = config["simulation"]["grid_size"]
hive_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)
ghost_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)
drones = {}
metrics_history = []

# --- NEIGHBOR DETECTION ---
def get_neighbors(drone_id, max_distance):
    drone = drones.get(drone_id)
    if not drone:
        return {}

    neighbors = {}
    my_x, my_y = drone["x"], drone["y"]

    for other_id, other in drones.items():
        if other_id == drone_id:
            continue
        dx = other["x"] - my_x
        dy = other["y"] - my_y
        dist = (dx**2 + dy**2) ** 0.5
        if 0 < dist <= max_distance:
            neighbors[other_id] = {"distance": dist, "dx": dx, "dy": dy}

    return neighbors

# --- BEHAVIOR MODES ---
def calculate_movement(drone_id, mode, params):
    drone = drones[drone_id]
    neighbors = get_neighbors(drone_id, params["neighbor_radius"])

    dx, dy = 0, 0

    if mode == "RANDOM":
        dx = np.random.choice([-1, 0, 1])
        dy = np.random.choice([-1, 0, 1])

    elif mode == "AVOID":
        if neighbors:
            closest_id = min(neighbors, key=lambda k: neighbors[k]["distance"])
            closest = neighbors[closest_id]
            if closest["distance"] < params["separation_distance"]:
                dx = -int(np.sign(closest["dx"])) if closest["dx"] != 0 else np.random.choice([-1, 1])
                dy = -int(np.sign(closest["dy"])) if closest["dy"] != 0 else np.random.choice([-1, 1])
            else:
                dx, dy = np.random.choice([-1, 0, 1]), np.random.choice([-1, 0, 1])
        else:
            dx, dy = np.random.choice([-1, 0, 1]), np.random.choice([-1, 0, 1])

    elif mode == "FLOCK":
        if not neighbors:
            # Move toward center
            all_x = [d["x"] for d in drones.values()]
            all_y = [d["y"] for d in drones.values()]
            cx, cy = np.mean(all_x), np.mean(all_y)
            dx = int(np.sign(cx - drone["x"]))
            dy = int(np.sign(cy - drone["y"]))
        else:
            close = {k: v for k, v in neighbors.items() if v["distance"] < params["separation_distance"]}
            if close:
                for ndata in close.values():
                    dx -= int(np.sign(ndata["dx"])) if ndata["dx"] != 0 else 0
                    dy -= int(np.sign(ndata["dy"])) if ndata["dy"] != 0 else 0
                dx, dy = int(np.sign(dx)), int(np.sign(dy))
            else:
                avg_dx = np.mean([n["dx"] for n in neighbors.values()])
                avg_dy = np.mean([n["dy"] for n in neighbors.values()])
                dx, dy = int(np.sign(avg_dx)), int(np.sign(avg_dy))

    elif mode == "BOIDS":
        sep_x, sep_y = 0, 0
        coh_x, coh_y = 0, 0
        ali_x, ali_y = 0, 0

        if neighbors:
            # Separation
            close = {k: v for k, v in neighbors.items() if v["distance"] < params["separation_distance"] + 1}
            for ndata in close.values():
                weight = 1.0 / max(ndata["distance"], 0.5)
                sep_x -= ndata["dx"] * weight
                sep_y -= ndata["dy"] * weight

            # Cohesion
            coh_x = np.mean([n["dx"] for n in neighbors.values()])
            coh_y = np.mean([n["dy"] for n in neighbors.values()])

            # Alignment
            vx_sum = sum(drones[nid].get("vx", 0) for nid in neighbors)
            vy_sum = sum(drones[nid].get("vy", 0) for nid in neighbors)
            ali_x = vx_sum / len(neighbors)
            ali_y = vy_sum / len(neighbors)

            # Combine
            total_x = sep_x * params["separation_weight"] + coh_x * params["cohesion_weight"] + ali_x * params["alignment_weight"]
            total_y = sep_y * params["separation_weight"] + coh_y * params["cohesion_weight"] + ali_y * params["alignment_weight"]

            dx = int(np.sign(total_x)) if abs(total_x) > 0.1 else 0
            dy = int(np.sign(total_y)) if abs(total_y) > 0.1 else 0
        else:
            dx, dy = np.random.choice([-1, 0, 1]), np.random.choice([-1, 0, 1])

    return dx, dy

# --- METRICS ---
def calculate_metrics():
    if len(drones) < 2:
        return {}

    # Average neighbor distance
    all_distances = []
    for did in drones:
        neighbors = get_neighbors(did, 100)  # All neighbors
        if neighbors:
            all_distances.extend([n["distance"] for n in neighbors.values()])

    avg_neighbor_dist = np.mean(all_distances) if all_distances else 0

    # Clustering coefficient (how close are nearest neighbors)
    nearest_distances = []
    for did in drones:
        neighbors = get_neighbors(did, 100)
        if neighbors:
            nearest = min(n["distance"] for n in neighbors.values())
            nearest_distances.append(nearest)

    avg_nearest = np.mean(nearest_distances) if nearest_distances else 0

    # Swarm center and spread
    xs = [d["x"] for d in drones.values()]
    ys = [d["y"] for d in drones.values()]
    center_x, center_y = np.mean(xs), np.mean(ys)
    spread = np.std(xs) + np.std(ys)

    # Velocity alignment
    vxs = [d.get("vx", 0) for d in drones.values()]
    vys = [d.get("vy", 0) for d in drones.values()]
    avg_vx, avg_vy = np.mean(vxs), np.mean(vys)
    alignment = (avg_vx**2 + avg_vy**2) ** 0.5  # Magnitude of average velocity

    # Collision count (drones on same cell)
    positions = [(d["x"], d["y"]) for d in drones.values()]
    unique_positions = len(set(positions))
    collisions = len(positions) - unique_positions

    # Grid coverage
    covered_cells = np.sum(ghost_grid > 0)
    coverage_pct = (covered_cells / (GRID_SIZE * GRID_SIZE)) * 100

    return {
        "avg_neighbor_distance": round(avg_neighbor_dist, 2),
        "avg_nearest_neighbor": round(avg_nearest, 2),
        "swarm_spread": round(spread, 2),
        "swarm_center": (round(center_x, 1), round(center_y, 1)),
        "velocity_alignment": round(alignment, 3),
        "collisions": collisions,
        "coverage_percent": round(coverage_pct, 2)
    }

# --- SIMULATION LOOP ---
def spawn_drones(count, pattern="random"):
    margin = 10
    for i in range(count):
        did = f"S-{i:03d}"
        if pattern == "random":
            x = np.random.randint(margin, GRID_SIZE - margin)
            y = np.random.randint(margin, GRID_SIZE - margin)
        elif pattern == "center":
            x = GRID_SIZE // 2 + np.random.randint(-5, 5)
            y = GRID_SIZE // 2 + np.random.randint(-5, 5)
        elif pattern == "corners":
            corner = i % 4
            if corner == 0: x, y = margin, margin
            elif corner == 1: x, y = GRID_SIZE - margin, margin
            elif corner == 2: x, y = margin, GRID_SIZE - margin
            else: x, y = GRID_SIZE - margin, GRID_SIZE - margin
            x += np.random.randint(-3, 3)
            y += np.random.randint(-3, 3)
        else:
            x = np.random.randint(margin, GRID_SIZE - margin)
            y = np.random.randint(margin, GRID_SIZE - margin)

        drones[did] = {"x": x, "y": y, "vx": 0, "vy": 0, "trail": []}

def run_simulation():
    global hive_grid, ghost_grid, metrics_history

    sim_config = config["simulation"]
    drone_config = config["drones"]
    behavior_params = config["behavior_params"]
    metrics_config = config["metrics"]

    tick_rate = sim_config["tick_rate"]
    duration = sim_config["duration_seconds"]
    total_ticks = tick_rate * duration
    tick_interval = 1.0 / tick_rate

    mode = drone_config["behavior_mode"]

    print(f"/// ENHANCED SIMULATION STARTING ///")
    print(f"    Mode: {mode}")
    print(f"    Drones: {drone_config['count']}")
    print(f"    Grid: {GRID_SIZE}x{GRID_SIZE}")
    print(f"    Tick Rate: {tick_rate} Hz")
    print(f"    Duration: {duration}s ({total_ticks} ticks)")
    print()

    # Spawn drones
    spawn_drones(drone_config["count"], drone_config["spawn_pattern"])

    # Simulation loop
    start_time = time.time()
    margin = 10

    for tick in range(total_ticks):
        tick_start = time.time()

        # Update each drone
        for did, drone in drones.items():
            if np.random.random() > behavior_params["move_probability"]:
                continue

            dx, dy = calculate_movement(did, mode, behavior_params)

            new_x = int(max(margin, min(GRID_SIZE - margin, drone["x"] + dx)))
            new_y = int(max(margin, min(GRID_SIZE - margin, drone["y"] + dy)))

            drone["vx"] = new_x - drone["x"]
            drone["vy"] = new_y - drone["y"]
            drone["x"] = new_x
            drone["y"] = new_y

            # Deposit pheromones
            hive_grid[new_x][new_y] = min(255, hive_grid[new_x][new_y] + 5)
            ghost_grid[new_x][new_y] = min(255, ghost_grid[new_x][new_y] + 0.5)

        # Decay
        hive_grid *= 0.95

        # Collect metrics
        if metrics_config["enabled"] and tick % metrics_config["sample_rate"] == 0:
            metrics = calculate_metrics()
            metrics["tick"] = tick
            metrics["time"] = round(time.time() - start_time, 2)
            metrics_history.append(metrics)

            # Progress report every second
            if tick % tick_rate == 0:
                elapsed = time.time() - start_time
                print(f"  Tick {tick}/{total_ticks} | "
                      f"Spread: {metrics['swarm_spread']:.1f} | "
                      f"Collisions: {metrics['collisions']} | "
                      f"Coverage: {metrics['coverage_percent']:.1f}%")

        # Maintain tick rate
        elapsed = time.time() - tick_start
        if elapsed < tick_interval:
            time.sleep(tick_interval - elapsed)

    total_time = time.time() - start_time
    print()
    print(f"/// SIMULATION COMPLETE ///")
    print(f"    Actual duration: {total_time:.2f}s")
    print(f"    Effective tick rate: {total_ticks / total_time:.1f} Hz")

    # Export metrics
    if metrics_config["export_csv"]:
        export_metrics()

def export_metrics():
    os.makedirs(os.path.join(BASE_DIR, "analysis", "metrics"), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    filename = os.path.join(BASE_DIR, "analysis", "metrics", f"sim_{timestamp}.csv")

    if metrics_history:
        keys = metrics_history[0].keys()
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(metrics_history)
        print(f"    Metrics exported: {filename}")

# --- MAIN ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SlimeHive Enhanced Simulation")
    parser.add_argument("--drones", type=int, help="Number of drones")
    parser.add_argument("--mode", type=str, help="Behavior mode (RANDOM, AVOID, FLOCK, BOIDS)")
    parser.add_argument("--duration", type=int, help="Duration in seconds")
    parser.add_argument("--tick-rate", type=int, help="Ticks per second")
    args = parser.parse_args()

    # Override config with CLI args
    if args.drones:
        config["drones"]["count"] = args.drones
    if args.mode:
        config["drones"]["behavior_mode"] = args.mode
    if args.duration:
        config["simulation"]["duration_seconds"] = args.duration
    if args.tick_rate:
        config["simulation"]["tick_rate"] = args.tick_rate

    run_simulation()
```

---

## Usage Examples

### Basic Run
```bash
python simulate.py
```

### Custom Parameters
```bash
# 100 drones, BOIDS mode, 60 seconds
python simulate.py --drones 100 --mode BOIDS --duration 60

# High-speed stress test
python simulate.py --drones 200 --tick-rate 60 --duration 30
```

### Batch Experiments
```bash
# Compare modes
for mode in RANDOM AVOID FLOCK BOIDS; do
    python simulate.py --drones 50 --mode $mode --duration 120
done
```

---

## Metrics Output

CSV output in `analysis/metrics/sim_YYYY-MM-DD_HHMMSS.csv`:

| tick | time | avg_neighbor_distance | avg_nearest_neighbor | swarm_spread | collisions | coverage_percent | velocity_alignment |
|------|------|----------------------|---------------------|--------------|------------|------------------|-------------------|
| 0 | 0.0 | 15.2 | 3.1 | 24.5 | 2 | 0.5 | 0.0 |
| 30 | 1.0 | 12.8 | 4.2 | 18.3 | 0 | 1.2 | 0.45 |
| ... | ... | ... | ... | ... | ... | ... | ... |

---

## Future Enhancements

1. **Live Dashboard Connection** - Stream state to dashboard_hud.py via HTTP/WebSocket
2. **Parameter Sweep** - Automatically test ranges of parameters
3. **GPU Acceleration** - Use Metal/NumPy for large grids
4. **Behavior Comparison Charts** - Auto-generate graphs comparing modes
5. **Export to Real Hardware** - Save optimal configs for Pico drones

---

## Files to Create

1. `config/simulation.json` - Configuration file
2. `simulate.py` - Main simulation script
3. `analysis/` - Output directory (auto-created)

---

## Implementation Order

1. Create `config/` directory and `simulation.json`
2. Create `simulate.py` with core simulation loop
3. Add metrics collection
4. Add CSV export
5. Test with various drone counts and modes
6. (Optional) Add live dashboard connection

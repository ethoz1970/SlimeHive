#!/usr/bin/env python3
"""
SlimeHive Enhanced Simulation Runner
Optimized for M3 Pro - high tick rate, many drones, metrics collection

Usage:
    python simulate.py
    python simulate.py --drones 100 --mode BOIDS --duration 120
    python simulate.py --drones 200 --tick-rate 60 --duration 30
"""

import numpy as np
import json
import time
import os
import csv
import argparse
from datetime import datetime

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config", "simulation.json")

DEFAULT_CONFIG = {
    "simulation": {
        "tick_rate": 30,
        "duration_seconds": 60,
        "grid_size": 100,
        "headless": False
    },
    "drones": {
        "count": 20,
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
    "pheromones": {
        "deposit_amount": 5.0,
        "ghost_deposit": 0.5,
        "decay_rate": 0.95
    },
    "metrics": {
        "enabled": True,
        "sample_rate": 1,
        "export_csv": True
    },
    "recording": {
        "enabled": False,
        "output_dir": "analysis/sessions"
    }
}


def deep_merge(base, override):
    """Deep merge two dictionaries"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """Load configuration from file, falling back to defaults"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            file_config = json.load(f)
            return deep_merge(DEFAULT_CONFIG, file_config)
    return DEFAULT_CONFIG.copy()


class Simulation:
    """Enhanced SlimeHive Simulation Engine"""

    def __init__(self, config):
        self.config = config
        self.grid_size = config["simulation"]["grid_size"]
        self.margin = 10

        # Grids
        self.hive_grid = np.zeros((self.grid_size, self.grid_size), dtype=float)
        self.ghost_grid = np.zeros((self.grid_size, self.grid_size), dtype=float)

        # Drones
        self.drones = {}

        # Metrics
        self.metrics_history = []
        self.start_time = None

    def get_neighbors(self, drone_id, max_distance):
        """Find all drones within max_distance of the given drone"""
        drone = self.drones.get(drone_id)
        if not drone:
            return {}

        neighbors = {}
        my_x, my_y = drone["x"], drone["y"]

        for other_id, other in self.drones.items():
            if other_id == drone_id:
                continue

            dx = other["x"] - my_x
            dy = other["y"] - my_y
            dist = (dx**2 + dy**2) ** 0.5

            if 0 < dist <= max_distance:
                neighbors[other_id] = {
                    "distance": dist,
                    "dx": dx,
                    "dy": dy
                }

        return neighbors

    def calculate_movement(self, drone_id):
        """Calculate movement based on behavior mode"""
        drone = self.drones[drone_id]
        params = self.config["behavior_params"]
        mode = self.config["drones"]["behavior_mode"]
        neighbors = self.get_neighbors(drone_id, params["neighbor_radius"])

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
                # Move toward swarm center
                all_x = [d["x"] for d in self.drones.values()]
                all_y = [d["y"] for d in self.drones.values()]
                if all_x and all_y:
                    cx, cy = np.mean(all_x), np.mean(all_y)
                    dx = int(np.sign(cx - drone["x"]))
                    dy = int(np.sign(cy - drone["y"]))
            else:
                close = {k: v for k, v in neighbors.items()
                        if v["distance"] < params["separation_distance"]}
                if close:
                    # Separation
                    for ndata in close.values():
                        dx -= int(np.sign(ndata["dx"])) if ndata["dx"] != 0 else 0
                        dy -= int(np.sign(ndata["dy"])) if ndata["dy"] != 0 else 0
                    dx, dy = int(np.sign(dx)) if dx != 0 else 0, int(np.sign(dy)) if dy != 0 else 0
                else:
                    # Cohesion
                    avg_dx = np.mean([n["dx"] for n in neighbors.values()])
                    avg_dy = np.mean([n["dy"] for n in neighbors.values()])
                    dx, dy = int(np.sign(avg_dx)), int(np.sign(avg_dy))

            # Add randomness
            if np.random.random() < 0.25:
                dx, dy = np.random.choice([-1, 0, 1]), np.random.choice([-1, 0, 1])

        elif mode == "BOIDS":
            sep_x, sep_y = 0, 0
            coh_x, coh_y = 0, 0
            ali_x, ali_y = 0, 0

            if neighbors:
                # Separation
                sep_dist = params["separation_distance"] + 1
                close = {k: v for k, v in neighbors.items() if v["distance"] < sep_dist}
                for ndata in close.values():
                    weight = 1.0 / max(ndata["distance"], 0.5)
                    sep_x -= ndata["dx"] * weight
                    sep_y -= ndata["dy"] * weight

                # Cohesion
                coh_x = np.mean([n["dx"] for n in neighbors.values()])
                coh_y = np.mean([n["dy"] for n in neighbors.values()])

                # Alignment
                vx_sum = sum(self.drones[nid].get("vx", 0) for nid in neighbors)
                vy_sum = sum(self.drones[nid].get("vy", 0) for nid in neighbors)
                ali_x = vx_sum / len(neighbors)
                ali_y = vy_sum / len(neighbors)

                # Combine with weights
                total_x = (sep_x * params["separation_weight"] +
                          coh_x * params["cohesion_weight"] +
                          ali_x * params["alignment_weight"])
                total_y = (sep_y * params["separation_weight"] +
                          coh_y * params["cohesion_weight"] +
                          ali_y * params["alignment_weight"])

                dx = int(np.sign(total_x)) if abs(total_x) > 0.1 else 0
                dy = int(np.sign(total_y)) if abs(total_y) > 0.1 else 0
            else:
                dx, dy = np.random.choice([-1, 0, 1]), np.random.choice([-1, 0, 1])

            # Slight randomness
            if np.random.random() < 0.15:
                dx += np.random.choice([-1, 0, 1])
                dy += np.random.choice([-1, 0, 1])
                dx = int(np.sign(dx)) if dx != 0 else 0
                dy = int(np.sign(dy)) if dy != 0 else 0

        elif mode == "SWARM":
            # Move toward center of mass
            all_drones = list(self.drones.values())
            if len(all_drones) > 1:
                cx = sum(d["x"] for d in all_drones) / len(all_drones)
                cy = sum(d["y"] for d in all_drones) / len(all_drones)

                vx = cx - drone["x"]
                vy = cy - drone["y"]
                dist = (vx**2 + vy**2) ** 0.5

                if dist > 5:
                    dx = int(np.sign(vx))
                    dy = int(np.sign(vy))
                else:
                    dx = np.random.choice([-1, 0, 1])
                    dy = np.random.choice([-1, 0, 1])

                if np.random.random() < 0.4:
                    dx = np.random.choice([-1, 0, 1])
                    dy = np.random.choice([-1, 0, 1])
            else:
                dx, dy = np.random.choice([-1, 0, 1]), np.random.choice([-1, 0, 1])

        elif mode == "SCATTER":
            # Move away from center
            center_x = self.grid_size // 2
            center_y = self.grid_size // 2
            vx = drone["x"] - center_x
            vy = drone["y"] - center_y

            dx = int(np.sign(vx)) if vx != 0 else np.random.choice([-1, 1])
            dy = int(np.sign(vy)) if vy != 0 else np.random.choice([-1, 1])

            if np.random.random() < 0.3:
                dx = np.random.choice([-1, 0, 1])
                dy = np.random.choice([-1, 0, 1])

        return dx, dy

    def calculate_metrics(self):
        """Calculate swarm metrics"""
        if len(self.drones) < 2:
            return {}

        # Collect all neighbor distances
        all_distances = []
        nearest_distances = []

        for did in self.drones:
            neighbors = self.get_neighbors(did, 100)
            if neighbors:
                distances = [n["distance"] for n in neighbors.values()]
                all_distances.extend(distances)
                nearest_distances.append(min(distances))

        avg_neighbor_dist = np.mean(all_distances) if all_distances else 0
        avg_nearest = np.mean(nearest_distances) if nearest_distances else 0

        # Swarm spread
        xs = [d["x"] for d in self.drones.values()]
        ys = [d["y"] for d in self.drones.values()]
        center_x, center_y = np.mean(xs), np.mean(ys)
        spread = np.std(xs) + np.std(ys)

        # Velocity alignment
        vxs = [d.get("vx", 0) for d in self.drones.values()]
        vys = [d.get("vy", 0) for d in self.drones.values()]
        avg_vx, avg_vy = np.mean(vxs), np.mean(vys)
        alignment = (avg_vx**2 + avg_vy**2) ** 0.5

        # Collision count
        positions = [(d["x"], d["y"]) for d in self.drones.values()]
        unique_positions = len(set(positions))
        collisions = len(positions) - unique_positions

        # Grid coverage
        covered_cells = np.sum(self.ghost_grid > 0)
        coverage_pct = (covered_cells / (self.grid_size * self.grid_size)) * 100

        return {
            "avg_neighbor_distance": round(avg_neighbor_dist, 2),
            "avg_nearest_neighbor": round(avg_nearest, 2),
            "swarm_spread": round(spread, 2),
            "center_x": round(center_x, 1),
            "center_y": round(center_y, 1),
            "velocity_alignment": round(alignment, 3),
            "collisions": collisions,
            "coverage_percent": round(coverage_pct, 2),
            "drone_count": len(self.drones)
        }

    def spawn_drones(self):
        """Spawn drones based on configuration"""
        count = self.config["drones"]["count"]
        pattern = self.config["drones"]["spawn_pattern"]

        for i in range(count):
            did = f"S-{i:03d}"

            if pattern == "random":
                x = np.random.randint(self.margin, self.grid_size - self.margin)
                y = np.random.randint(self.margin, self.grid_size - self.margin)
            elif pattern == "center":
                x = self.grid_size // 2 + np.random.randint(-5, 6)
                y = self.grid_size // 2 + np.random.randint(-5, 6)
            elif pattern == "corners":
                corner = i % 4
                if corner == 0:
                    x, y = self.margin + 5, self.margin + 5
                elif corner == 1:
                    x, y = self.grid_size - self.margin - 5, self.margin + 5
                elif corner == 2:
                    x, y = self.margin + 5, self.grid_size - self.margin - 5
                else:
                    x, y = self.grid_size - self.margin - 5, self.grid_size - self.margin - 5
                x += np.random.randint(-3, 4)
                y += np.random.randint(-3, 4)
            elif pattern == "line":
                x = self.margin + (i * (self.grid_size - 2 * self.margin) // max(count - 1, 1))
                y = self.grid_size // 2
            else:
                x = np.random.randint(self.margin, self.grid_size - self.margin)
                y = np.random.randint(self.margin, self.grid_size - self.margin)

            self.drones[did] = {
                "x": int(x),
                "y": int(y),
                "vx": 0,
                "vy": 0,
                "trail": []
            }

    def update_drone(self, drone_id):
        """Update a single drone's position"""
        drone = self.drones[drone_id]
        params = self.config["behavior_params"]
        pheromone_config = self.config["pheromones"]

        # Check move probability
        if np.random.random() > params["move_probability"]:
            return

        # Calculate movement
        dx, dy = self.calculate_movement(drone_id)

        # Calculate new position
        new_x = int(max(self.margin, min(self.grid_size - self.margin, drone["x"] + dx)))
        new_y = int(max(self.margin, min(self.grid_size - self.margin, drone["y"] + dy)))

        # Update velocity
        drone["vx"] = new_x - drone["x"]
        drone["vy"] = new_y - drone["y"]

        # Update position
        drone["x"] = new_x
        drone["y"] = new_y

        # Update trail
        drone["trail"].append([new_x, new_y])
        if len(drone["trail"]) > 10:
            drone["trail"].pop(0)

        # Deposit pheromones
        self.hive_grid[new_x][new_y] = min(255,
            self.hive_grid[new_x][new_y] + pheromone_config["deposit_amount"])
        self.ghost_grid[new_x][new_y] = min(255,
            self.ghost_grid[new_x][new_y] + pheromone_config["ghost_deposit"])

    def tick(self):
        """Run one simulation tick"""
        # Update all drones
        for drone_id in list(self.drones.keys()):
            self.update_drone(drone_id)

        # Apply decay
        decay_rate = self.config["pheromones"]["decay_rate"]
        self.hive_grid *= decay_rate

    def export_metrics(self):
        """Export metrics to CSV"""
        if not self.metrics_history:
            return

        metrics_dir = os.path.join(BASE_DIR, "analysis", "metrics")
        os.makedirs(metrics_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        mode = self.config["drones"]["behavior_mode"]
        count = self.config["drones"]["count"]
        filename = os.path.join(metrics_dir, f"sim_{mode}_{count}drones_{timestamp}.csv")

        keys = self.metrics_history[0].keys()
        with open(filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(self.metrics_history)

        print(f"    Metrics exported: {filename}")

    def export_final_state(self):
        """Export final state as JSON (compatible with dashboard)"""
        sessions_dir = os.path.join(BASE_DIR, "analysis", "sessions")
        os.makedirs(sessions_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        mode = self.config["drones"]["behavior_mode"]
        filename = os.path.join(sessions_dir, f"state_{mode}_{timestamp}.json")

        state = {
            "grid": self.hive_grid.tolist(),
            "ghost_grid": self.ghost_grid.tolist(),
            "drones": self.drones,
            "config": self.config,
            "metrics_summary": self.metrics_history[-1] if self.metrics_history else {}
        }

        with open(filename, 'w') as f:
            json.dump(state, f, indent=2)

        print(f"    State exported: {filename}")

    def run(self):
        """Run the full simulation"""
        sim_config = self.config["simulation"]
        metrics_config = self.config["metrics"]

        tick_rate = sim_config["tick_rate"]
        duration = sim_config["duration_seconds"]
        total_ticks = tick_rate * duration
        tick_interval = 1.0 / tick_rate

        mode = self.config["drones"]["behavior_mode"]
        drone_count = self.config["drones"]["count"]

        print()
        print("=" * 60)
        print("    SLIMEHIVE ENHANCED SIMULATION")
        print("=" * 60)
        print(f"    Mode:       {mode}")
        print(f"    Drones:     {drone_count}")
        print(f"    Grid:       {self.grid_size}x{self.grid_size}")
        print(f"    Tick Rate:  {tick_rate} Hz")
        print(f"    Duration:   {duration}s ({total_ticks} ticks)")
        print(f"    Spawn:      {self.config['drones']['spawn_pattern']}")
        print("=" * 60)
        print()

        # Spawn drones
        self.spawn_drones()
        self.start_time = time.time()

        # Simulation loop
        for tick in range(total_ticks):
            tick_start = time.time()

            # Run simulation tick
            self.tick()

            # Collect metrics
            if metrics_config["enabled"] and tick % metrics_config["sample_rate"] == 0:
                metrics = self.calculate_metrics()
                metrics["tick"] = tick
                metrics["time"] = round(time.time() - self.start_time, 2)
                self.metrics_history.append(metrics)

                # Progress report every second
                if tick % tick_rate == 0 and tick > 0:
                    elapsed = time.time() - self.start_time
                    pct = (tick / total_ticks) * 100
                    print(f"  [{pct:5.1f}%] Tick {tick:5d} | "
                          f"Spread: {metrics['swarm_spread']:5.1f} | "
                          f"Nearest: {metrics['avg_nearest_neighbor']:4.1f} | "
                          f"Collisions: {metrics['collisions']:2d} | "
                          f"Coverage: {metrics['coverage_percent']:5.1f}%")

            # Maintain tick rate
            elapsed = time.time() - tick_start
            if elapsed < tick_interval:
                time.sleep(tick_interval - elapsed)

        # Final report
        total_time = time.time() - self.start_time
        effective_rate = total_ticks / total_time

        print()
        print("=" * 60)
        print("    SIMULATION COMPLETE")
        print("=" * 60)
        print(f"    Actual duration:     {total_time:.2f}s")
        print(f"    Effective tick rate: {effective_rate:.1f} Hz")

        if self.metrics_history:
            final = self.metrics_history[-1]
            print(f"    Final spread:        {final['swarm_spread']:.1f}")
            print(f"    Final collisions:    {final['collisions']}")
            print(f"    Final coverage:      {final['coverage_percent']:.1f}%")

        print("=" * 60)

        # Export results
        if metrics_config["export_csv"]:
            self.export_metrics()

        if self.config["recording"]["enabled"]:
            self.export_final_state()

        print()


def main():
    parser = argparse.ArgumentParser(
        description="SlimeHive Enhanced Simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simulate.py
  python simulate.py --drones 100 --mode BOIDS
  python simulate.py --drones 200 --tick-rate 60 --duration 30
  python simulate.py --mode FLOCK --spawn center

Available modes: RANDOM, AVOID, FLOCK, BOIDS, SWARM, SCATTER
Spawn patterns: random, center, corners, line
        """
    )

    parser.add_argument("--drones", type=int, help="Number of drones")
    parser.add_argument("--mode", type=str, help="Behavior mode")
    parser.add_argument("--duration", type=int, help="Duration in seconds")
    parser.add_argument("--tick-rate", type=int, help="Ticks per second")
    parser.add_argument("--spawn", type=str, help="Spawn pattern")
    parser.add_argument("--grid-size", type=int, help="Grid size (NxN)")
    parser.add_argument("--save-state", action="store_true", help="Save final state as JSON")

    args = parser.parse_args()

    # Load config
    config = load_config()

    # Override with CLI args
    if args.drones:
        config["drones"]["count"] = args.drones
    if args.mode:
        config["drones"]["behavior_mode"] = args.mode.upper()
    if args.duration:
        config["simulation"]["duration_seconds"] = args.duration
    if args.tick_rate:
        config["simulation"]["tick_rate"] = args.tick_rate
    if args.spawn:
        config["drones"]["spawn_pattern"] = args.spawn
    if args.grid_size:
        config["simulation"]["grid_size"] = args.grid_size
    if args.save_state:
        config["recording"]["enabled"] = True

    # Run simulation
    sim = Simulation(config)
    sim.run()


if __name__ == "__main__":
    main()

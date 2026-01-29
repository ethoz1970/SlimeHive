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
import gzip
import copy
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import LinearSegmentedColormap

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config", "simulation.json")
LIVE_CONFIG_FILE = os.path.join(BASE_DIR, "hive_config_live.json")

HISTORY_FILE = os.path.join(BASE_DIR, "hive_state.json")

DEFAULT_CONFIG = {
    "simulation": {
        "tick_rate": 30,
        "duration_seconds": 60,
        "grid_size": 100,
        "live_view": True
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
        "output_dir": "analysis/sessions",
        "save_screenshot": True
    },
    "hunger": {
        "enabled": True,
        "decay_interval": 10,  # Hunger decreases every N ticks (~33 seconds at 30 Hz)
        "desperate_threshold": 20,  # Below this, drone becomes desperate
        "death_mode": "no"  # "yes" = die, "no" = freeze only, "respawn" = die and respawn at queen
    },
    "hoppers": {
        "count": 0,
        "hop_distance": 15,
        "hunger_decay_multiplier": 0.25,  # 4x slower hunger decay
        "ghost_deposit_multiplier": 10.0,  # 10x larger ghost deposit on food find
        "cooldown_ticks": 50  # Ticks between jumps
    },
    "queen": {
        "x": 10,
        "y": 10
    }
}


class SimulationRecorder:
    """Records simulation keyframes for playback"""

    def __init__(self, keyframe_interval=1.0):
        self.keyframe_interval = keyframe_interval
        self.keyframes = []
        self.events = []
        self.metadata = {}
        self.initial_state = {}
        self.start_time = None
        self.last_keyframe_time = -999

    def start(self, sim):
        """Initialize recording"""
        self.start_time = time.time()
        self.metadata = {
            "timestamp": int(self.start_time),
            "tick_rate": sim.config["simulation"]["tick_rate"],
            "drone_count": sim.config["drones"]["count"],
            "mode": sim.config["drones"]["behavior_mode"],
            "grid_size": sim.grid_size,
            "food_enabled": sim.config.get("food", {}).get("enabled", False),
            "hunger_enabled": sim.config.get("hunger", {}).get("enabled", True)
        }
        self.initial_state = {
            "food_sources": copy.deepcopy(sim.food_sources),
            "queen_pos": list(sim.queen_pos),
            "boundary": {
                "min_x": sim.margin, "min_y": sim.margin,
                "max_x": sim.grid_size - sim.margin,
                "max_y": sim.grid_size - sim.margin
            }
        }

    def record_tick(self, sim, elapsed_time, tick):
        """Capture keyframe if interval elapsed"""
        if elapsed_time - self.last_keyframe_time >= self.keyframe_interval:
            self._capture_keyframe(sim, elapsed_time, tick)
            self.last_keyframe_time = elapsed_time

    def _capture_keyframe(self, sim, elapsed_time, tick):
        """Capture current state as keyframe"""
        drones = {}
        for did, d in sim.drones.items():
            drones[did] = {
                "x": d["x"], "y": d["y"],
                "hunger": d.get("hunger", 100),
                "state": d.get("state", "searching"),
                "type": d.get("type", "worker")
            }

        food_state = []
        for f in sim.food_sources:
            food_state.append({
                "id": f["id"],
                "amount": round(f["amount"], 1),
                "consumed": f["consumed"]
            })

        self.keyframes.append({
            "t": round(elapsed_time, 2),
            "tick": tick,
            "drones": drones,
            "food_state": food_state,
            "metrics": {
                "queen_food": round(sim.queen_food, 1),
                "trips_completed": sim.trips_completed,
                "drone_count": len(sim.drones)
            }
        })

    def record_event(self, event_type, elapsed_time, **data):
        """Record discrete event"""
        self.events.append({"t": round(elapsed_time, 2), "type": event_type, **data})

    def save(self, sim, filepath):
        """Save recording to file"""
        self.metadata["duration_seconds"] = round(time.time() - self.start_time, 1)

        recording = {
            "version": "1.0",
            "metadata": self.metadata,
            "initial_state": self.initial_state,
            "keyframes": self.keyframes,
            "events": self.events,
            "final_grids": {
                "ghost_grid": sim.ghost_grid.tolist()
            }
        }

        json_str = json.dumps(recording, separators=(',', ':'))

        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            f.write(json_str)

        print(f"    Recording saved: {filepath}")


class VideoRecorder:
    """Records simulation frames to MP4 video"""

    def __init__(self, fps=10, resolution=(800, 800)):
        self.fps = fps
        self.resolution = resolution
        self.frames = []
        self.frame_interval = 1.0 / fps
        self.last_frame_time = -999
        self.start_time = None

    def start(self):
        """Initialize video recording"""
        self.start_time = time.time()
        self.frames = []
        self.last_frame_time = -999

    def should_capture(self, elapsed_time):
        """Check if we should capture a frame at this time"""
        return elapsed_time - self.last_frame_time >= self.frame_interval

    def capture_frame(self, sim, elapsed_time):
        """Capture current simulation state as a frame"""
        if not self.should_capture(elapsed_time):
            return

        self.last_frame_time = elapsed_time

        # Create figure
        dpi = 100
        fig_size = (self.resolution[0] / dpi, self.resolution[1] / dpi)
        fig, ax = plt.subplots(figsize=fig_size, dpi=dpi)

        # Black background
        ax.set_facecolor('black')

        # Pheromone heatmap
        colors = [
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (1.0, 0.78, 0.0),
            (1.0, 1.0, 1.0)
        ]
        cmap = LinearSegmentedColormap.from_list('pheromone', colors, N=256)

        grid_max = max(sim.ghost_grid.max(), 1)
        normalized_grid = sim.ghost_grid.T / grid_max
        ax.imshow(normalized_grid, cmap=cmap, origin='lower',
                  extent=[0, sim.grid_size, 0, sim.grid_size])

        # Boundary
        boundary_rect = patches.Rectangle(
            (sim.margin, sim.margin),
            sim.grid_size - 2 * sim.margin,
            sim.grid_size - 2 * sim.margin,
            linewidth=1, edgecolor='white', facecolor='none',
            linestyle='--', alpha=0.5
        )
        ax.add_patch(boundary_rect)

        # Food sources
        for food in sim.food_sources:
            if food["consumed"]:
                color = 'gray'
                alpha = 0.5
            else:
                ratio = food["amount"] / food["max_amount"]
                color = (1 - ratio, ratio, 0)
                alpha = 0.8

            food_rect = patches.Rectangle(
                (food["x"] - food["radius"], food["y"] - food["radius"]),
                food["radius"] * 2, food["radius"] * 2,
                linewidth=1, edgecolor='white', facecolor=color, alpha=alpha
            )
            ax.add_patch(food_rect)

        # Death markers
        for marker in sim.death_markers:
            ax.plot(marker["x"], marker["y"], 'x', color='red',
                    markersize=6, markeredgewidth=2)

        # Food markers (hopper finds)
        for marker in sim.food_markers:
            ax.plot(marker["x"], marker["y"], 'x', color='yellow',
                    markersize=5, markeredgewidth=1.5)

        # Smell markers
        for marker in sim.smell_markers:
            ax.plot(marker["x"], marker["y"], 'x', color='white',
                    markersize=4, markeredgewidth=1, alpha=0.7)

        # Queen
        qx, qy = sim.queen_pos
        ax.plot(qx, qy, 'D', color='white', markersize=10,
                markeredgecolor='gold', markeredgewidth=2)

        # Sentinel
        sentinel_x = sim.grid_size - sim.margin
        sentinel_y = sim.grid_size - sim.margin
        ax.plot(sentinel_x, sentinel_y, '^', color='blue', markersize=8,
                markeredgecolor='cyan', markeredgewidth=1)

        # Drones
        for drone_id, drone in sim.drones.items():
            hue = (hash(drone_id) % 360) / 360.0
            if hue < 1/6:
                r, g, b = 1, hue * 6, 0
            elif hue < 2/6:
                r, g, b = 1 - (hue - 1/6) * 6, 1, 0
            elif hue < 3/6:
                r, g, b = 0, 1, (hue - 2/6) * 6
            elif hue < 4/6:
                r, g, b = 0, 1 - (hue - 3/6) * 6, 1
            elif hue < 5/6:
                r, g, b = (hue - 4/6) * 6, 0, 1
            else:
                r, g, b = 1, 0, 1 - (hue - 5/6) * 6

            if drone.get("type") == "hopper":
                ax.plot(drone["x"], drone["y"], 's', color=(r, g, b),
                        markersize=6, markeredgecolor='white', markeredgewidth=0.5)
            else:
                ax.plot(drone["x"], drone["y"], 'o', color=(r, g, b),
                        markersize=5, markeredgecolor='white', markeredgewidth=0.5)

        # Configure axes
        ax.set_xlim(0, sim.grid_size)
        ax.set_ylim(0, sim.grid_size)
        ax.set_aspect('equal')
        ax.axis('off')

        # Add timestamp overlay
        ax.text(5, sim.grid_size - 5, f"t={elapsed_time:.1f}s",
                color='white', fontsize=10, verticalalignment='top',
                fontfamily='monospace', alpha=0.8)

        # Convert figure to numpy array
        fig.tight_layout(pad=0)
        fig.canvas.draw()

        # Get the RGBA buffer
        buf = fig.canvas.buffer_rgba()
        frame = np.asarray(buf)

        # Convert RGBA to RGB
        frame_rgb = frame[:, :, :3].copy()

        self.frames.append(frame_rgb)
        plt.close(fig)

    def save(self, filepath):
        """Save frames to MP4 video file"""
        if not self.frames:
            print("    No frames to save")
            return

        try:
            import imageio.v3 as iio
        except ImportError:
            try:
                import imageio as iio
            except ImportError:
                print("    ERROR: imageio not installed. Run: pip install imageio imageio-ffmpeg")
                return

        print(f"    Encoding {len(self.frames)} frames to video...")

        try:
            # Use imageio to write MP4
            iio.imwrite(filepath, self.frames, fps=self.fps, codec='libx264',
                        plugin='pyav', options={'crf': '23'})
        except Exception as e:
            # Fallback to basic imageio if pyav not available
            try:
                iio.imwrite(filepath, self.frames, fps=self.fps)
            except Exception as e2:
                print(f"    Video save error: {e2}")
                print("    Try: pip install imageio-ffmpeg")
                return

        print(f"    Video saved: {filepath}")
        print(f"    Duration: {len(self.frames) / self.fps:.1f}s @ {self.fps} FPS")


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

        # Food sources
        self.food_sources = []

        # Queen position and food storage (for FEED_QUEEN mode)
        queen_config = config.get("queen", {})
        self.queen_pos = (queen_config.get("x", 10), queen_config.get("y", 10))
        self.queen_food = 0
        self.trips_completed = 0

        # Death markers (where drones died)
        self.death_markers = []

        # Food markers (where hoppers found food)
        self.food_markers = []

        # Smell markers (where hoppers detected food nearby but didn't eat)
        self.smell_markers = []

        # Dead drones (for registry display)
        self.dead_drones = {}

        # Metrics
        self.metrics_history = []
        self.start_time = None

        # Tick counter for hunger decay
        self.tick_counter = 0

        # Live config tracking
        self.last_config_check = 0
        self.config_check_interval = 0.5  # Check every 0.5 seconds

        # Recording
        self.recorder = None
        self.video_recorder = None

    def load_live_config(self):
        """Load live config changes from dashboard"""
        now = time.time()
        if now - self.last_config_check < self.config_check_interval:
            return  # Don't check too frequently

        self.last_config_check = now

        try:
            if os.path.exists(LIVE_CONFIG_FILE):
                with open(LIVE_CONFIG_FILE, 'r') as f:
                    live_config = json.load(f)

                # Apply pheromone config
                if 'decay_rate' in live_config:
                    self.config["pheromones"]["decay_rate"] = live_config['decay_rate']
                if 'deposit_amount' in live_config:
                    self.config["pheromones"]["deposit_amount"] = live_config['deposit_amount']
                if 'ghost_deposit' in live_config:
                    self.config["pheromones"]["ghost_deposit"] = live_config['ghost_deposit']

                # Apply food config
                if "food" not in self.config:
                    self.config["food"] = {}
                if 'detection_radius' in live_config:
                    self.config["food"]["detection_radius"] = live_config['detection_radius']
                if 'pheromone_boost' in live_config:
                    self.config["food"]["pheromone_boost"] = live_config['pheromone_boost']

                # Apply hunger config
                if "hunger" not in self.config:
                    self.config["hunger"] = {}
                if 'death_mode' in live_config:
                    self.config["hunger"]["death_mode"] = live_config['death_mode']

        except Exception as e:
            pass  # Don't crash simulation if config read fails

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

    # --- BEHAVIOR COMPONENTS (return velocity vectors) ---

    def _behavior_avoid(self, drone, neighbors, params):
        """Avoid nearby drones - separation behavior"""
        vx, vy = 0.0, 0.0
        if neighbors:
            for ndata in neighbors.values():
                if ndata["distance"] < params["separation_distance"] + 2:
                    weight = 1.0 / max(ndata["distance"], 0.5)
                    vx -= ndata["dx"] * weight
                    vy -= ndata["dy"] * weight
        return vx, vy

    def _behavior_flock(self, drone, neighbors, params):
        """Move toward neighbors - cohesion behavior"""
        vx, vy = 0.0, 0.0
        if neighbors:
            avg_dx = np.mean([n["dx"] for n in neighbors.values()])
            avg_dy = np.mean([n["dy"] for n in neighbors.values()])
            vx, vy = avg_dx * 0.5, avg_dy * 0.5
        else:
            # Move toward swarm center if no neighbors
            all_x = [d["x"] for d in self.drones.values()]
            all_y = [d["y"] for d in self.drones.values()]
            if all_x and all_y:
                cx, cy = np.mean(all_x), np.mean(all_y)
                vx = (cx - drone["x"]) * 0.3
                vy = (cy - drone["y"]) * 0.3
        return vx, vy

    def _behavior_align(self, drone, neighbors, params):
        """Align velocity with neighbors"""
        vx, vy = 0.0, 0.0
        if neighbors:
            vx_sum = sum(self.drones[nid].get("vx", 0) for nid in neighbors)
            vy_sum = sum(self.drones[nid].get("vy", 0) for nid in neighbors)
            vx = vx_sum / len(neighbors)
            vy = vy_sum / len(neighbors)
        return vx, vy

    def _behavior_forage(self, drone, neighbors, params):
        """Move toward food sources - behavior scales with hunger/desperation"""
        vx, vy = 0.0, 0.0

        # Calculate desperation (0.0 = full, 1.0 = starving)
        desperation = self.get_desperation(drone)

        # Increase detection radius based on desperation (up to 1.5x)
        food_config = self.config.get("food", {})
        base_radius = food_config.get("detection_radius", 20)
        detection_radius = base_radius * (1 + desperation * 0.5)

        nearby_food = self.detect_food(drone, detection_radius)

        if nearby_food:
            closest = nearby_food[0]
            vx = closest["direction_x"]
            vy = closest["direction_y"]
            # Normalize and scale speed by desperation (speed 2 to 3)
            mag = max((vx**2 + vy**2) ** 0.5, 1)
            speed = 2 + desperation  # Faster when hungry
            vx, vy = vx / mag * speed, vy / mag * speed
        else:
            # Erratic movement scales with desperation (more frantic searching)
            if np.random.random() < desperation * 0.5:
                vx = np.random.choice([-1, 0, 1]) * (1 + desperation)
                vy = np.random.choice([-1, 0, 1]) * (1 + desperation)
            else:
                # Follow pheromone trails
                best_pheromone = 0
                for check_dx in [-1, 0, 1]:
                    for check_dy in [-1, 0, 1]:
                        if check_dx == 0 and check_dy == 0:
                            continue
                        nx = drone["x"] + check_dx
                        ny = drone["y"] + check_dy
                        if self.margin <= nx < self.grid_size - self.margin and \
                           self.margin <= ny < self.grid_size - self.margin:
                            p = self.ghost_grid[nx][ny]
                            if p > best_pheromone:
                                best_pheromone = p
                                vx, vy = check_dx * 0.5, check_dy * 0.5
        return vx, vy

    def _behavior_scatter(self, drone, neighbors, params):
        """Move away from grid center"""
        center_x = self.grid_size // 2
        center_y = self.grid_size // 2
        vx = drone["x"] - center_x
        vy = drone["y"] - center_y
        mag = max((vx**2 + vy**2) ** 0.5, 1)
        return vx / mag, vy / mag

    def _behavior_swarm(self, drone, neighbors, params):
        """Move toward swarm center of mass"""
        vx, vy = 0.0, 0.0
        all_drones = list(self.drones.values())
        if len(all_drones) > 1:
            cx = sum(d["x"] for d in all_drones) / len(all_drones)
            cy = sum(d["y"] for d in all_drones) / len(all_drones)
            vx = cx - drone["x"]
            vy = cy - drone["y"]
            mag = max((vx**2 + vy**2) ** 0.5, 1)
            vx, vy = vx / mag, vy / mag
        return vx, vy

    def _behavior_random(self, drone, neighbors, params):
        """Random movement"""
        return np.random.choice([-1, 0, 1]), np.random.choice([-1, 0, 1])

    def _behavior_feed_queen(self, drone, neighbors, params):
        """FEED_QUEEN specific: return to queen when carrying"""
        vx, vy = 0.0, 0.0
        state = drone.get("state", "searching")

        if state == "carrying":
            # Head back to Queen
            qx, qy = self.queen_pos
            vx = qx - drone["x"]
            vy = qy - drone["y"]
            mag = max((vx**2 + vy**2) ** 0.5, 1)
            vx, vy = vx / mag * 3, vy / mag * 3  # Strong pull to queen
        else:
            # Use forage behavior when searching
            vx, vy = self._behavior_forage(drone, neighbors, params)

        return vx, vy

    # --- MAIN MOVEMENT CALCULATOR ---

    def calculate_movement(self, drone_id):
        """Calculate movement based on behavior mode(s) - supports combining modes"""
        drone = self.drones[drone_id]
        params = self.config["behavior_params"]
        mode_str = self.config["drones"]["behavior_mode"]
        neighbors = self.get_neighbors(drone_id, params["neighbor_radius"])

        # Parse modes (comma-separated)
        modes = [m.strip().upper() for m in mode_str.split(",")]

        # PRIORITY: If drone is carrying food in FEED_QUEEN mode, ONLY go to queen
        # Other behaviors are ignored when carrying - delivery is the priority
        if "FEED_QUEEN" in modes and drone.get("state") == "carrying":
            qx, qy = self.queen_pos
            dir_x = qx - drone["x"]
            dir_y = qy - drone["y"]
            dx = int(np.sign(dir_x)) if dir_x != 0 else 0
            dy = int(np.sign(dir_y)) if dir_y != 0 else 0
            # Slight randomness for natural movement
            if np.random.random() < 0.1:
                dx += np.random.choice([-1, 0, 1])
                dy += np.random.choice([-1, 0, 1])
                dx = int(np.sign(dx)) if dx != 0 else 0
                dy = int(np.sign(dy)) if dy != 0 else 0
            return dx, dy

        # Behavior weights (can be customized in config later)
        weights = {
            "AVOID": params.get("avoid_weight", 2.0),
            "FLOCK": params.get("flock_weight", 1.0),
            "ALIGN": params.get("align_weight", 0.5),
            "FORAGE": params.get("forage_weight", 2.0),
            "SCATTER": params.get("scatter_weight", 1.0),
            "SWARM": params.get("swarm_weight", 1.0),
            "RANDOM": params.get("random_weight", 0.3),
            "FEED_QUEEN": params.get("feed_queen_weight", 3.0),
            "BOIDS": 1.0,  # BOIDS combines avoid+flock+align internally
        }

        total_vx, total_vy = 0.0, 0.0

        # Calculate desperation for hunger-based weight modification
        desperation = self.get_desperation(drone)

        for mode in modes:
            vx, vy = 0.0, 0.0
            w = weights.get(mode, 1.0)

            if mode == "AVOID":
                # Reduce avoidance as hunger drops (desperate drones ignore personal space)
                w = w * (1 - desperation)
                vx, vy = self._behavior_avoid(drone, neighbors, params)
            elif mode == "FLOCK":
                vx, vy = self._behavior_flock(drone, neighbors, params)
            elif mode == "ALIGN":
                vx, vy = self._behavior_align(drone, neighbors, params)
            elif mode == "FORAGE":
                vx, vy = self._behavior_forage(drone, neighbors, params)
            elif mode == "SCATTER":
                vx, vy = self._behavior_scatter(drone, neighbors, params)
            elif mode == "SWARM":
                vx, vy = self._behavior_swarm(drone, neighbors, params)
            elif mode == "RANDOM":
                vx, vy = self._behavior_random(drone, neighbors, params)
            elif mode == "FEED_QUEEN":
                vx, vy = self._behavior_feed_queen(drone, neighbors, params)
            elif mode == "BOIDS":
                # BOIDS is a preset combination
                av_x, av_y = self._behavior_avoid(drone, neighbors, params)
                fl_x, fl_y = self._behavior_flock(drone, neighbors, params)
                al_x, al_y = self._behavior_align(drone, neighbors, params)
                vx = av_x * params["separation_weight"] + fl_x * params["cohesion_weight"] + al_x * params["alignment_weight"]
                vy = av_y * params["separation_weight"] + fl_y * params["cohesion_weight"] + al_y * params["alignment_weight"]

            total_vx += vx * w
            total_vy += vy * w

        # Add slight randomness for natural movement
        if np.random.random() < 0.15:
            total_vx += np.random.choice([-0.5, 0, 0.5])
            total_vy += np.random.choice([-0.5, 0, 0.5])

        # Convert to discrete movement
        dx = int(np.sign(total_vx)) if abs(total_vx) > 0.1 else 0
        dy = int(np.sign(total_vy)) if abs(total_vy) > 0.1 else 0

        # If no movement, add random step to prevent stalling
        if dx == 0 and dy == 0 and np.random.random() < 0.5:
            dx = np.random.choice([-1, 0, 1])
            dy = np.random.choice([-1, 0, 1])

        return dx, dy

    def calculate_metrics(self):
        """Calculate swarm metrics"""
        if len(self.drones) == 0:
            # All drones dead - return zeroed metrics
            return {
                "avg_neighbor_distance": 0,
                "avg_nearest_neighbor": 0,
                "swarm_spread": 0,
                "center_x": 0,
                "center_y": 0,
                "velocity_alignment": 0,
                "collisions": 0,
                "coverage_percent": 0,
                "drone_count": 0,
                "food_remaining": 0,
                "food_depleted": 0,
                "food_consumed_pct": 0,
                "queen_food": round(self.queen_food, 1),
                "carriers": 0,
                "trips_completed": self.trips_completed,
                "avg_hunger": 0,
                "min_hunger": 0,
                "starving": 0,
                "desperate": 0
            }

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

        # Food metrics
        food_remaining = 0
        food_depleted = 0
        total_food_capacity = 0

        if self.food_sources:
            for food in self.food_sources:
                total_food_capacity += food["max_amount"]
                if food["consumed"]:
                    food_depleted += 1
                else:
                    food_remaining += food["amount"]

        # FEED_QUEEN metrics
        carriers = sum(1 for d in self.drones.values() if d.get("state") == "carrying")

        # Hunger metrics
        hunger_values = [d.get("hunger", 100) for d in self.drones.values()]
        avg_hunger = np.mean(hunger_values) if hunger_values else 100
        min_hunger = min(hunger_values) if hunger_values else 100
        starving_count = sum(1 for h in hunger_values if h <= 0)
        desperate_count = sum(1 for h in hunger_values if 0 < h <= 20)

        return {
            "avg_neighbor_distance": round(avg_neighbor_dist, 2),
            "avg_nearest_neighbor": round(avg_nearest, 2),
            "swarm_spread": round(spread, 2),
            "center_x": round(center_x, 1),
            "center_y": round(center_y, 1),
            "velocity_alignment": round(alignment, 3),
            "collisions": collisions,
            "coverage_percent": round(coverage_pct, 2),
            "drone_count": len(self.drones),
            "food_remaining": round(food_remaining, 1),
            "food_depleted": food_depleted,
            "food_consumed_pct": round((1 - food_remaining / total_food_capacity) * 100, 1) if total_food_capacity > 0 else 0,
            "queen_food": round(self.queen_food, 1),
            "carriers": carriers,
            "trips_completed": self.trips_completed,
            "avg_hunger": round(avg_hunger, 1),
            "min_hunger": min_hunger,
            "starving": starving_count,
            "desperate": desperate_count
        }

    def is_too_close_to_food(self, x, y, min_distance=10):
        """Check if position is within min_distance of any food source"""
        for food in self.food_sources:
            dist = ((food["x"] - x)**2 + (food["y"] - y)**2) ** 0.5
            if dist < min_distance:
                return True
        return False

    def spawn_drones(self):
        """Spawn drones based on configuration (at least 10 cells from food)"""
        count = self.config["drones"]["count"]
        pattern = self.config["drones"]["spawn_pattern"]
        max_attempts = 50  # Prevent infinite loop if grid is too crowded

        for i in range(count):
            did = f"S-{i:03d}"

            for attempt in range(max_attempts):
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
                elif pattern == "queen":
                    # Spawn at queen's location with slight spread
                    qx, qy = self.queen_pos
                    x = qx + np.random.randint(-3, 4)
                    y = qy + np.random.randint(-3, 4)
                else:
                    x = np.random.randint(self.margin, self.grid_size - self.margin)
                    y = np.random.randint(self.margin, self.grid_size - self.margin)

                # Check if too close to food (only if food exists)
                if not self.food_sources or not self.is_too_close_to_food(x, y, min_distance=10):
                    break  # Good position found

            self.drones[did] = {
                "x": int(x),
                "y": int(y),
                "vx": 0,
                "vy": 0,
                "trail": [],
                "rssi": -50,  # Simulated signal strength
                "last_seen": time.time(),
                "state": "searching",  # For FEED_QUEEN: searching, carrying
                "carrying": 0,  # Amount of food being carried
                "hunger": 100,  # Current hunger level (0-100)
                "max_hunger": 100,  # Maximum hunger
                "type": "worker"  # Drone type: worker or hopper
            }

    def spawn_hoppers(self):
        """Spawn hopper scout drones"""
        hopper_config = self.config.get("hoppers", {})
        count = hopper_config.get("count", 0)

        if count == 0:
            return

        qx, qy = self.queen_pos

        for i in range(count):
            hid = f"H-{i:03d}"

            # Spawn near queen
            x = qx + np.random.randint(-3, 4)
            y = qy + np.random.randint(-3, 4)

            # Keep within bounds
            x = max(self.margin, min(self.grid_size - self.margin, x))
            y = max(self.margin, min(self.grid_size - self.margin, y))

            self.drones[hid] = {
                "x": int(x),
                "y": int(y),
                "vx": 0,
                "vy": 0,
                "trail": [],
                "rssi": -50,
                "last_seen": time.time(),
                "state": "scouting",
                "carrying": 0,
                "hunger": 100,
                "max_hunger": 100,
                "type": "hopper",
                "hop_cooldown": 0
            }

    def spawn_food(self):
        """Spawn food sources based on configuration"""
        food_config = self.config.get("food", {})
        if not food_config.get("enabled", False):
            return

        count = food_config.get("sources", 5)
        spread = food_config.get("spread", "scattered")
        amount = food_config.get("amount", 100)
        radius = food_config.get("radius", 3)

        for i in range(count):
            if spread == "scattered":
                x = np.random.randint(self.margin + 5, self.grid_size - self.margin - 5)
                y = np.random.randint(self.margin + 5, self.grid_size - self.margin - 5)

            elif spread == "clustered":
                cx, cy = self.grid_size // 2, self.grid_size // 2
                x = cx + np.random.randint(-20, 21)
                y = cy + np.random.randint(-20, 21)

            elif spread == "corners":
                corner = i % 4
                if corner == 0:
                    x, y = self.margin + 10, self.margin + 10
                elif corner == 1:
                    x, y = self.grid_size - self.margin - 10, self.margin + 10
                elif corner == 2:
                    x, y = self.margin + 10, self.grid_size - self.margin - 10
                else:
                    x, y = self.grid_size - self.margin - 10, self.grid_size - self.margin - 10
                x += np.random.randint(-5, 6)
                y += np.random.randint(-5, 6)

            elif spread == "center":
                x = self.grid_size // 2 + np.random.randint(-10, 11)
                y = self.grid_size // 2 + np.random.randint(-10, 11)

            elif spread == "perimeter":
                edge = i % 4
                if edge == 0:
                    x = np.random.randint(self.margin, self.grid_size - self.margin)
                    y = self.margin + 5
                elif edge == 1:
                    x = self.grid_size - self.margin - 5
                    y = np.random.randint(self.margin, self.grid_size - self.margin)
                elif edge == 2:
                    x = np.random.randint(self.margin, self.grid_size - self.margin)
                    y = self.grid_size - self.margin - 5
                else:
                    x = self.margin + 5
                    y = np.random.randint(self.margin, self.grid_size - self.margin)

            else:  # Default to scattered
                x = np.random.randint(self.margin + 5, self.grid_size - self.margin - 5)
                y = np.random.randint(self.margin + 5, self.grid_size - self.margin - 5)

            self.food_sources.append({
                "id": f"F-{i:03d}",
                "x": int(x),
                "y": int(y),
                "amount": float(amount),
                "max_amount": float(amount),
                "radius": radius,
                "consumed": False
            })

    def detect_food(self, drone, detection_radius=None):
        """Find food sources within detection radius of drone (measured from food edge)"""
        food_config = self.config.get("food", {})
        if detection_radius is None:
            detection_radius = food_config.get("detection_radius", 20)

        detected = []
        dx, dy = drone["x"], drone["y"]

        for food in self.food_sources:
            if food["consumed"]:
                continue

            dist_to_center = ((food["x"] - dx)**2 + (food["y"] - dy)**2) ** 0.5
            dist_to_edge = max(0, dist_to_center - food["radius"])

            if dist_to_edge <= detection_radius:
                detected.append({
                    "food": food,
                    "distance": dist_to_edge,
                    "direction_x": food["x"] - dx,
                    "direction_y": food["y"] - dy
                })

        return sorted(detected, key=lambda f: f["distance"])

    def consume_food(self, drone):
        """Drone consumes nearby food (within 1 cell of food edge)"""
        food_config = self.config.get("food", {})
        consumption_rate = food_config.get("consumption_rate", 0.5)

        dx, dy = drone["x"], drone["y"]

        for food in self.food_sources:
            if food["consumed"]:
                continue

            dist_to_center = ((food["x"] - dx)**2 + (food["y"] - dy)**2) ** 0.5
            dist_to_edge = max(0, dist_to_center - food["radius"])

            # Within 1 cell of food edge
            if dist_to_edge <= 1:
                consume_amount = consumption_rate * (1 - dist_to_edge / 2)
                food["amount"] -= consume_amount

                if food["amount"] <= 0:
                    food["amount"] = 0
                    food["consumed"] = True

                return True  # Drone found food

        return False

    def is_inside_food(self, x, y):
        """Check if position is inside any food source"""
        for food in self.food_sources:
            if food["consumed"]:
                continue
            dist = ((food["x"] - x)**2 + (food["y"] - y)**2) ** 0.5
            if dist < food["radius"]:
                return True
        return False

    def get_desperation(self, drone):
        """Calculate desperation factor (0.0 = full, 1.0 = starving)"""
        hunger = drone.get("hunger", 100)
        return 1.0 - (hunger / 100.0)

    def update_drone(self, drone_id):
        """Update a single drone's position"""
        drone = self.drones[drone_id]
        params = self.config["behavior_params"]
        pheromone_config = self.config["pheromones"]

        # Starving drones freeze/slow down (90% chance to skip movement)
        hunger_config = self.config.get("hunger", {})
        if hunger_config.get("enabled", True) and drone.get("hunger", 100) <= 0:
            if np.random.random() > 0.1:
                return

        # Check move probability
        if np.random.random() > params["move_probability"]:
            return

        # Calculate movement
        dx, dy = self.calculate_movement(drone_id)

        # Calculate new position
        new_x = int(max(self.margin, min(self.grid_size - self.margin, drone["x"] + dx)))
        new_y = int(max(self.margin, min(self.grid_size - self.margin, drone["y"] + dy)))

        # Block movement into food squares - drones stay at edge
        if self.is_inside_food(new_x, new_y):
            # Try moving only in x direction
            if not self.is_inside_food(drone["x"] + dx, drone["y"]):
                new_x = int(max(self.margin, min(self.grid_size - self.margin, drone["x"] + dx)))
                new_y = drone["y"]
            # Try moving only in y direction
            elif not self.is_inside_food(drone["x"], drone["y"] + dy):
                new_x = drone["x"]
                new_y = int(max(self.margin, min(self.grid_size - self.margin, drone["y"] + dy)))
            else:
                # Can't move - stay in place
                new_x = drone["x"]
                new_y = drone["y"]

        # Update velocity
        drone["vx"] = new_x - drone["x"]
        drone["vy"] = new_y - drone["y"]

        # Update position
        drone["x"] = new_x
        drone["y"] = new_y

        # Update last_seen for dashboard compatibility
        drone["last_seen"] = time.time()

        # Update trail
        drone["trail"].append([new_x, new_y])
        if len(drone["trail"]) > 10:
            drone["trail"].pop(0)

        # Deposit pheromones (stronger when carrying food - creates trail back to food)
        deposit = pheromone_config["deposit_amount"]
        ghost_deposit = pheromone_config["ghost_deposit"]

        if drone.get("carrying", 0) > 0:
            # Carrying food - leave strong trail for others to follow
            deposit *= 4.0
            ghost_deposit *= 4.0

        self.hive_grid[new_x][new_y] = min(255, self.hive_grid[new_x][new_y] + deposit)
        self.ghost_grid[new_x][new_y] = min(255, self.ghost_grid[new_x][new_y] + ghost_deposit)

    def update_hopper(self, drone_id):
        """Update a hopper scout drone - jumps long distances looking for food"""
        drone = self.drones[drone_id]
        hopper_config = self.config.get("hoppers", {})
        hop_distance = hopper_config.get("hop_distance", 5)
        cooldown_ticks = hopper_config.get("cooldown_ticks", 3)
        ghost_multiplier = hopper_config.get("ghost_deposit_multiplier", 10.0)

        # Starving hoppers freeze
        hunger_config = self.config.get("hunger", {})
        if hunger_config.get("enabled", True) and drone.get("hunger", 100) <= 0:
            if np.random.random() > 0.1:
                return

        # Cooldown check - hopper rests between jumps
        if drone.get("hop_cooldown", 0) > 0:
            drone["hop_cooldown"] -= 1
            return

        # Pick random direction and jump
        angle = np.random.random() * 2 * np.pi
        dx = int(np.cos(angle) * hop_distance)
        dy = int(np.sin(angle) * hop_distance)

        # Calculate new position
        new_x = max(self.margin, min(self.grid_size - self.margin, drone["x"] + dx))
        new_y = max(self.margin, min(self.grid_size - self.margin, drone["y"] + dy))

        # Update velocity (for trail visualization)
        drone["vx"] = new_x - drone["x"]
        drone["vy"] = new_y - drone["y"]

        # Update position
        drone["x"] = new_x
        drone["y"] = new_y
        drone["last_seen"] = time.time()
        drone["hop_cooldown"] = cooldown_ticks

        # Update trail (hoppers have longer trails to show jumps)
        drone["trail"].append([new_x, new_y])
        if len(drone["trail"]) > 20:
            drone["trail"].pop(0)

        # Check if hopper can smell food nearby
        nearby_food = self.detect_food(drone, detection_radius=hop_distance + 2)

        # Check if landed near food and can eat
        if self.consume_food(drone):
            # Actually ate food! Reset hunger and drop beacon
            drone["hunger"] = 100

            base_ghost = self.config["pheromones"]["ghost_deposit"]
            beacon_deposit = base_ghost * ghost_multiplier

            # Add visual food marker (yellow X) only when actually eating
            self.food_markers.append({
                "x": new_x,
                "y": new_y,
                "drone_id": drone_id,
                "tick": self.tick_counter
            })

            # Deposit beacon at current position
            self.ghost_grid[new_x][new_y] = min(255, self.ghost_grid[new_x][new_y] + beacon_deposit)

            # Also deposit in surrounding cells for visibility
            for ox in range(-2, 3):
                for oy in range(-2, 3):
                    bx = max(0, min(self.grid_size - 1, new_x + ox))
                    by = max(0, min(self.grid_size - 1, new_y + oy))
                    falloff = beacon_deposit * (1 - (abs(ox) + abs(oy)) / 6)
                    self.ghost_grid[bx][by] = min(255, self.ghost_grid[bx][by] + falloff)
        elif nearby_food:
            # Smelled food but didn't eat - add white X marker
            self.smell_markers.append({
                "x": new_x,
                "y": new_y,
                "drone_id": drone_id,
                "tick": self.tick_counter,
                "distance": nearby_food[0]["distance"]
            })

            # Drop 25% strength ghost deposit to guide other drones
            base_ghost = self.config["pheromones"]["ghost_deposit"]
            smell_deposit = base_ghost * ghost_multiplier * 0.25

            self.ghost_grid[new_x][new_y] = min(255, self.ghost_grid[new_x][new_y] + smell_deposit)

            # Smaller spread for smell markers
            for ox in range(-1, 2):
                for oy in range(-1, 2):
                    bx = max(0, min(self.grid_size - 1, new_x + ox))
                    by = max(0, min(self.grid_size - 1, new_y + oy))
                    falloff = smell_deposit * (1 - (abs(ox) + abs(oy)) / 4)
                    self.ghost_grid[bx][by] = min(255, self.ghost_grid[bx][by] + falloff)

    def tick(self):
        """Run one simulation tick"""
        # Check for live config updates from dashboard
        self.load_live_config()

        # Increment tick counter
        self.tick_counter += 1

        food_config = self.config.get("food", {})
        food_enabled = food_config.get("enabled", False)
        pheromone_boost = food_config.get("pheromone_boost", 3.0)
        mode = self.config["drones"]["behavior_mode"]
        modes = [m.strip().upper() for m in mode.split(",")]

        # Hunger decay configuration
        hunger_config = self.config.get("hunger", {})
        hunger_enabled = hunger_config.get("enabled", True)
        hunger_decay_interval = hunger_config.get("decay_interval", 10)
        hopper_config = self.config.get("hoppers", {})
        hopper_hunger_mult = hopper_config.get("hunger_decay_multiplier", 0.25)

        # Apply hunger decay to all drones
        if hunger_enabled and self.tick_counter % hunger_decay_interval == 0:
            for drone in self.drones.values():
                if drone.get("type") == "hopper":
                    # Hoppers decay hunger slower (probabilistic)
                    if np.random.random() < hopper_hunger_mult:
                        drone["hunger"] = max(0, drone.get("hunger", 100) - 1)
                else:
                    drone["hunger"] = max(0, drone.get("hunger", 100) - 1)

        # Handle drone death/respawn based on death_mode
        death_mode = hunger_config.get("death_mode", "no")
        if hunger_enabled and death_mode != "no":
            dead_drones = [(did, d) for did, d in self.drones.items() if d.get("hunger", 100) <= 0]
            for drone_id, drone in dead_drones:
                # Record death location
                self.death_markers.append({
                    "x": drone["x"],
                    "y": drone["y"],
                    "drone_id": drone_id,
                    "tick": self.tick_counter,
                    "type": drone.get("type", "worker")
                })

                # Record death event for playback
                if self.recorder:
                    elapsed = time.time() - self.start_time if self.start_time else 0
                    self.recorder.record_event("death", elapsed,
                        drone=drone_id, x=drone["x"], y=drone["y"])

                if death_mode == "yes":
                    # Permanent death - move to dead_drones for registry display
                    drone["dead"] = True
                    drone["death_tick"] = self.tick_counter
                    self.dead_drones[drone_id] = drone.copy()
                    del self.drones[drone_id]
                elif death_mode == "respawn":
                    # Respawn at queen with full hunger, preserving type
                    qx, qy = self.queen_pos
                    drone_type = drone.get("type", "worker")
                    self.drones[drone_id] = {
                        "x": qx + np.random.randint(-2, 3),
                        "y": qy + np.random.randint(-2, 3),
                        "vx": 0,
                        "vy": 0,
                        "trail": [],
                        "rssi": -50,
                        "last_seen": time.time(),
                        "state": "scouting" if drone_type == "hopper" else "searching",
                        "carrying": 0,
                        "hunger": 100,
                        "max_hunger": 100,
                        "type": drone_type,
                        "hop_cooldown": 0 if drone_type == "hopper" else None
                    }

        # Update all drones
        for drone_id in list(self.drones.keys()):
            drone = self.drones[drone_id]

            # Route to correct update method based on type
            if drone.get("type") == "hopper":
                self.update_hopper(drone_id)
            else:
                self.update_drone(drone_id)

            # Skip FEED_QUEEN logic for hoppers (they're scouts, not carriers)
            if "FEED_QUEEN" in modes and food_enabled and drone.get("type") != "hopper":
                # FEED_QUEEN mode: pickup and dropoff logic
                if drone.get("state") == "searching":
                    # Check if at food edge - pickup food
                    for food in self.food_sources:
                        if food["consumed"]:
                            continue
                        dist = ((food["x"] - drone["x"])**2 + (food["y"] - drone["y"])**2) ** 0.5
                        if dist <= food["radius"] + 2:  # At edge of food
                            # Pickup food
                            pickup_amount = min(2.0, food["amount"])
                            if pickup_amount > 0:
                                food["amount"] -= pickup_amount
                                drone["carrying"] = pickup_amount
                                drone["state"] = "carrying"
                                drone["hunger"] = 100  # Reset hunger on food pickup
                                if food["amount"] <= 0:
                                    food["amount"] = 0
                                    food["consumed"] = True
                            break

                elif drone.get("state") == "carrying":
                    # Check if at Queen - dropoff food
                    qx, qy = self.queen_pos
                    dist_to_queen = ((qx - drone["x"])**2 + (qy - drone["y"])**2) ** 0.5
                    if dist_to_queen <= 3:  # Close enough to Queen
                        # Dropoff food
                        self.queen_food += drone["carrying"]
                        drone["carrying"] = 0
                        drone["state"] = "searching"
                        self.trips_completed += 1

            elif food_enabled and "FEED_QUEEN" not in modes and drone.get("type") != "hopper":
                # FORAGE mode - consume food in place (only if NOT in FEED_QUEEN mode)
                # Hoppers handle eating in update_hopper()
                if self.consume_food(drone):
                    drone["hunger"] = 100  # Reset hunger on food consumption
                    # Deposit extra pheromones near food (recruitment)
                    x, y = drone["x"], drone["y"]
                    boost = self.config["pheromones"]["deposit_amount"] * pheromone_boost
                    self.hive_grid[x][y] = min(255, self.hive_grid[x][y] + boost)
                    self.ghost_grid[x][y] = min(255, self.ghost_grid[x][y] + boost * 0.5)

        # Apply decay
        decay_rate = self.config["pheromones"]["decay_rate"]
        self.hive_grid *= decay_rate

        # Write state for live dashboard viewing
        if self.config["simulation"].get("live_view", True):
            self.write_live_state()

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

    def write_live_state(self):
        """Write current state to hive_state.json for dashboard viewing"""
        food_config = self.config.get("food", {})

        state = {
            "grid": self.hive_grid.tolist(),
            "ghost_grid": self.ghost_grid.tolist(),
            "drones": {k: {**v, "trail": v.get("trail", [])} for k, v in self.drones.items()},
            "food_sources": self.food_sources,
            "death_markers": self.death_markers,
            "food_markers": self.food_markers,
            "smell_markers": self.smell_markers,
            "dead_drones": self.dead_drones,
            "queen": {
                "x": self.queen_pos[0],
                "y": self.queen_pos[1],
                "food": round(self.queen_food, 1),
                "trips": self.trips_completed
            },
            "mood": "SIMULATION",
            "decay_rate": self.config["pheromones"]["decay_rate"],
            "sim_mode": self.config["drones"]["behavior_mode"],
            "boundary": {
                "min_x": self.margin,
                "min_y": self.margin,
                "max_x": self.grid_size - self.margin,
                "max_y": self.grid_size - self.margin
            },
            "live_config": {
                "decay_rate": self.config["pheromones"]["decay_rate"],
                "deposit_amount": self.config["pheromones"]["deposit_amount"],
                "ghost_deposit": self.config["pheromones"]["ghost_deposit"],
                "detection_radius": food_config.get("detection_radius", 20),
                "pheromone_boost": food_config.get("pheromone_boost", 3.0),
                "death_mode": self.config.get("hunger", {}).get("death_mode", "no")
            }
        }

        try:
            tmp_file = HISTORY_FILE + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump(state, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, HISTORY_FILE)
        except Exception as e:
            pass  # Don't crash simulation if write fails

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
            "food_sources": self.food_sources,
            "config": self.config,
            "metrics_summary": self.metrics_history[-1] if self.metrics_history else {}
        }

        with open(filename, 'w') as f:
            json.dump(state, f, indent=2)

        print(f"    State exported: {filename}")

    def render_final_map_image(self):
        """Render and save a PNG screenshot of the final map state"""
        # Create screenshots directory
        screenshots_dir = os.path.join(BASE_DIR, "analysis", "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        mode = self.config["drones"]["behavior_mode"].replace(",", "-")
        count = self.config["drones"]["count"]
        filename = os.path.join(screenshots_dir, f"map_{mode}_{count}drones_{timestamp}.png")

        # Create figure with 800x800 pixels
        dpi = 100
        fig, ax = plt.subplots(figsize=(8, 8), dpi=dpi)

        # 1. Black background
        ax.set_facecolor('black')

        # 2. Pheromone heatmap - combine ghost_grid for visualization
        # Create custom colormap: black → red → orange → yellow → white
        colors = [
            (0.0, 0.0, 0.0),      # Black at 0
            (1.0, 0.0, 0.0),      # Red at 0.33
            (1.0, 0.78, 0.0),     # Orange/Yellow at 0.66
            (1.0, 1.0, 1.0)       # White at 1.0
        ]
        cmap = LinearSegmentedColormap.from_list('pheromone', colors, N=256)

        # Normalize ghost_grid for display (transpose to match canvas orientation)
        grid_max = max(self.ghost_grid.max(), 1)
        normalized_grid = self.ghost_grid.T / grid_max

        ax.imshow(normalized_grid, cmap=cmap, origin='lower', extent=[0, self.grid_size, 0, self.grid_size])

        # 3. Operational boundary - dashed rectangle (10,10) to (90,90)
        boundary_rect = patches.Rectangle(
            (self.margin, self.margin),
            self.grid_size - 2 * self.margin,
            self.grid_size - 2 * self.margin,
            linewidth=1,
            edgecolor='white',
            facecolor='none',
            linestyle='--',
            alpha=0.5
        )
        ax.add_patch(boundary_rect)

        # 4. Food sources - colored squares based on consumption state
        for food in self.food_sources:
            if food["consumed"]:
                color = 'gray'
                alpha = 0.5
            else:
                # Green to red based on remaining amount
                ratio = food["amount"] / food["max_amount"]
                color = (1 - ratio, ratio, 0)  # Red when low, green when full
                alpha = 0.8

            food_rect = patches.Rectangle(
                (food["x"] - food["radius"], food["y"] - food["radius"]),
                food["radius"] * 2,
                food["radius"] * 2,
                linewidth=1,
                edgecolor='white',
                facecolor=color,
                alpha=alpha
            )
            ax.add_patch(food_rect)

        # 5. Death markers - red X marks at drone death locations
        for marker in self.death_markers:
            ax.plot(marker["x"], marker["y"], 'x', color='red', markersize=6, markeredgewidth=2)

        # 6. Food markers - yellow X marks where hoppers found food
        for marker in self.food_markers:
            ax.plot(marker["x"], marker["y"], 'x', color='yellow', markersize=5, markeredgewidth=1.5)

        # 7. Smell markers - white X marks where hoppers detected food
        for marker in self.smell_markers:
            ax.plot(marker["x"], marker["y"], 'x', color='white', markersize=4, markeredgewidth=1, alpha=0.7)

        # 8. Queen - white diamond at (10,10)
        qx, qy = self.queen_pos
        ax.plot(qx, qy, 'D', color='white', markersize=10, markeredgecolor='gold', markeredgewidth=2)

        # 9. Sentinel - blue triangle at (90,90)
        sentinel_x = self.grid_size - self.margin
        sentinel_y = self.grid_size - self.margin
        ax.plot(sentinel_x, sentinel_y, '^', color='blue', markersize=8, markeredgecolor='cyan', markeredgewidth=1)

        # 10. Drones - colored circles at current positions
        for i, (drone_id, drone) in enumerate(self.drones.items()):
            # Generate color based on drone ID (simple hash to HSL-like color)
            hue = (hash(drone_id) % 360) / 360.0
            # Convert hue to RGB (simplified)
            if hue < 1/6:
                r, g, b = 1, hue * 6, 0
            elif hue < 2/6:
                r, g, b = 1 - (hue - 1/6) * 6, 1, 0
            elif hue < 3/6:
                r, g, b = 0, 1, (hue - 2/6) * 6
            elif hue < 4/6:
                r, g, b = 0, 1 - (hue - 3/6) * 6, 1
            elif hue < 5/6:
                r, g, b = (hue - 4/6) * 6, 0, 1
            else:
                r, g, b = 1, 0, 1 - (hue - 5/6) * 6

            # Different marker for hoppers vs workers
            if drone.get("type") == "hopper":
                ax.plot(drone["x"], drone["y"], 's', color=(r, g, b), markersize=6, markeredgecolor='white', markeredgewidth=0.5)
            else:
                ax.plot(drone["x"], drone["y"], 'o', color=(r, g, b), markersize=5, markeredgecolor='white', markeredgewidth=0.5)

        # Configure axes
        ax.set_xlim(0, self.grid_size)
        ax.set_ylim(0, self.grid_size)
        ax.set_aspect('equal')
        ax.axis('off')

        # Save figure
        plt.tight_layout(pad=0)
        plt.savefig(filename, facecolor='black', edgecolor='none', bbox_inches='tight', pad_inches=0)
        plt.close(fig)

        print(f"    Screenshot saved: {filename}")

    def run(self):
        """Run the full simulation"""
        sim_config = self.config["simulation"]
        metrics_config = self.config["metrics"]

        tick_rate = sim_config["tick_rate"]
        duration = sim_config["duration_seconds"]
        total_ticks = tick_rate * duration
        tick_interval = 1.0 / tick_rate

        mode = self.config["drones"]["behavior_mode"]
        modes = [m.strip().upper() for m in mode.split(",")]
        drone_count = self.config["drones"]["count"]

        # Default to queen spawn for FEED_QUEEN mode (unless explicitly set)
        if "FEED_QUEEN" in modes and self.config["drones"].get("spawn_pattern") == "random":
            self.config["drones"]["spawn_pattern"] = "queen"

        hopper_count = self.config.get("hoppers", {}).get("count", 0)

        print()
        print("=" * 60)
        print("    SLIMEHIVE ENHANCED SIMULATION")
        print("=" * 60)
        print(f"    Mode:       {mode}")
        print(f"    Drones:     {drone_count}" + (f" + {hopper_count} hoppers" if hopper_count > 0 else ""))
        print(f"    Grid:       {self.grid_size}x{self.grid_size}")
        print(f"    Tick Rate:  {tick_rate} Hz")
        print(f"    Duration:   {duration}s ({total_ticks} ticks)")
        print(f"    Spawn:      {self.config['drones']['spawn_pattern']}")
        print(f"    Live View:  {self.config['simulation'].get('live_view', True)}")

        # Food info
        food_config = self.config.get("food", {})
        if food_config.get("enabled", False):
            print(f"    Food:       {food_config.get('sources', 5)} sources ({food_config.get('spread', 'scattered')})")
        else:
            print(f"    Food:       Disabled")

        # Hunger info
        hunger_config = self.config.get("hunger", {})
        if hunger_config.get("enabled", True):
            decay_interval = hunger_config.get("decay_interval", 10)
            starvation_time = (100 * decay_interval) / tick_rate
            print(f"    Hunger:     Decay every {decay_interval} ticks (~{starvation_time:.0f}s to starve)")
        else:
            print(f"    Hunger:     Disabled")

        print("=" * 60)
        if self.config["simulation"].get("live_view", True):
            print("    Dashboard: http://localhost:5050")
            print("    Run in another terminal: python dashboard_virtual.py")
        print()

        # Spawn food first (so drones can avoid spawning near it)
        self.spawn_food()

        # Spawn drones (at least 10 cells from food)
        self.spawn_drones()

        # Spawn hopper scouts
        self.spawn_hoppers()

        self.start_time = time.time()

        # Start recording if enabled
        if self.config.get("recording", {}).get("keyframe_recording", False):
            keyframe_interval = self.config["recording"].get("keyframe_interval", 1.0)
            self.recorder = SimulationRecorder(keyframe_interval)
            self.recorder.start(self)

        # Start video recording if enabled
        if self.config.get("recording", {}).get("video_enabled", False):
            video_fps = self.config["recording"].get("video_fps", 10)
            video_resolution = self.config["recording"].get("video_resolution", (800, 800))
            self.video_recorder = VideoRecorder(fps=video_fps, resolution=video_resolution)
            self.video_recorder.start()
            print(f"    Video recording: {video_fps} FPS")

        # Simulation loop
        extinction = False
        for tick in range(total_ticks):
            tick_start = time.time()

            # Run simulation tick
            self.tick()

            # Check for extinction (all drones dead)
            if len(self.drones) == 0:
                print()
                print("  !!! ALL DRONES HAVE DIED - SIMULATION ENDING !!!")
                extinction = True
                break

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
                    base_msg = (f"  [{pct:5.1f}%] Tick {tick:5d} | "
                               f"Spread: {metrics['swarm_spread']:5.1f} | "
                               f"Nearest: {metrics['avg_nearest_neighbor']:4.1f} | "
                               f"Collisions: {metrics['collisions']:2d}")

                    # Add hunger indicator if enabled
                    hunger_info = ""
                    if self.config.get("hunger", {}).get("enabled", True):
                        hunger_info = f" | Hunger: {metrics['avg_hunger']:.0f}%"
                        if metrics['starving'] > 0:
                            hunger_info += f" ({metrics['starving']} starving)"
                        elif metrics['desperate'] > 0:
                            hunger_info += f" ({metrics['desperate']} desperate)"

                    # Add mode-specific info
                    if "FEED_QUEEN" in modes and self.food_sources:
                        print(f"{base_msg} | Queen: {metrics['queen_food']:.0f} | Trips: {metrics['trips_completed']}{hunger_info}")
                    elif self.food_sources:
                        print(f"{base_msg} | Food: {metrics['food_consumed_pct']:.0f}% consumed{hunger_info}")
                    else:
                        print(f"{base_msg} | Coverage: {metrics['coverage_percent']:5.1f}%{hunger_info}")

            # Record keyframe for playback
            if self.recorder:
                elapsed = time.time() - self.start_time
                self.recorder.record_tick(self, elapsed, tick)

            # Capture video frame
            if self.video_recorder:
                elapsed = time.time() - self.start_time
                self.video_recorder.capture_frame(self, elapsed)

            # Maintain tick rate
            elapsed = time.time() - tick_start
            if elapsed < tick_interval:
                time.sleep(tick_interval - elapsed)

        # Final report
        total_time = time.time() - self.start_time
        effective_rate = total_ticks / total_time

        print()
        print("=" * 60)
        if extinction:
            print("    SIMULATION ENDED - EXTINCTION")
        else:
            print("    SIMULATION COMPLETE")
        print("=" * 60)
        print(f"    Actual duration:     {total_time:.2f}s")
        print(f"    Effective tick rate: {effective_rate:.1f} Hz")
        if extinction:
            print(f"    Cause:               All drones died")

        if self.metrics_history:
            final = self.metrics_history[-1]
            print(f"    Final spread:        {final['swarm_spread']:.1f}")
            print(f"    Final collisions:    {final['collisions']}")
            print(f"    Final coverage:      {final['coverage_percent']:.1f}%")

            # Food summary if enabled
            if self.food_sources:
                print(f"    Food consumed:       {final['food_consumed_pct']:.1f}%")
                print(f"    Food depleted:       {final['food_depleted']}/{len(self.food_sources)} sources")

            # FEED_QUEEN summary
            if "FEED_QUEEN" in modes:
                print(f"    Queen food:          {final['queen_food']:.1f}")
                print(f"    Trips completed:     {final['trips_completed']}")
                print(f"    Active carriers:     {final['carriers']}")

            # Hunger summary if enabled
            if self.config.get("hunger", {}).get("enabled", True):
                print(f"    Final avg hunger:    {final['avg_hunger']:.1f}%")
                print(f"    Starving drones:     {final['starving']}")
                print(f"    Desperate drones:    {final['desperate']}")

        print("=" * 60)

        # Export results
        if metrics_config["export_csv"]:
            self.export_metrics()

        if self.config["recording"]["enabled"]:
            self.export_final_state()

        # Save final map screenshot
        if self.config["recording"].get("save_screenshot", True):
            self.render_final_map_image()

        # Save keyframe recording for playback
        if self.recorder:
            recordings_dir = os.path.join(BASE_DIR, "recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            mode = self.config["drones"]["behavior_mode"].replace(",", "-")
            drone_count = self.config["drones"]["count"]
            filename = f"sim_{mode}_{drone_count}drones_{timestamp}.slimehive"
            self.recorder.save(self, os.path.join(recordings_dir, filename))

        # Save video recording
        if self.video_recorder:
            recordings_dir = os.path.join(BASE_DIR, "recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            mode = self.config["drones"]["behavior_mode"].replace(",", "-")
            drone_count = self.config["drones"]["count"]
            filename = f"sim_{mode}_{drone_count}drones_{timestamp}.mp4"
            self.video_recorder.save(os.path.join(recordings_dir, filename))

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
  python simulate.py --mode FORAGE --food-sources 5 --food-spread scattered
  python simulate.py --mode "FORAGE,AVOID" --food-sources 5 --drones 40
  python simulate.py --video --video-fps 15 --duration 30
  python simulate.py --queen-x 50 --queen-y 50 --mode FEED_QUEEN

Available modes: RANDOM, AVOID, FLOCK, ALIGN, BOIDS, SWARM, SCATTER, FORAGE, FEED_QUEEN
  - Combine modes with commas: --mode "FORAGE,AVOID" or --mode "FLOCK,AVOID"
  - BOIDS = preset combo of AVOID+FLOCK+ALIGN
Spawn patterns: random, center, corners, line, queen
Food spread: scattered, clustered, corners, center, perimeter
Video: --video enables MP4 recording (requires: pip install imageio imageio-ffmpeg)
        """
    )

    parser.add_argument("--drones", type=int, help="Number of drones")
    parser.add_argument("--mode", type=str, help="Behavior mode")
    parser.add_argument("--duration", type=int, help="Duration in seconds")
    parser.add_argument("--tick-rate", type=int, help="Ticks per second")
    parser.add_argument("--spawn", type=str, help="Spawn pattern")
    parser.add_argument("--grid-size", type=int, help="Grid size (NxN)")
    parser.add_argument("--save-state", action="store_true", help="Save final state as JSON")
    parser.add_argument("--no-live", action="store_true", help="Disable live dashboard updates")
    parser.add_argument("--no-screenshot", action="store_true", help="Disable final map screenshot")

    # Food arguments
    parser.add_argument("--food-sources", type=int, help="Number of food sources (enables food)")
    parser.add_argument("--food-amount", type=int, help="Starting amount per food source")
    parser.add_argument("--food-spread", type=str, help="Food distribution (scattered/clustered/corners/center/perimeter)")
    parser.add_argument("--food-radius", type=int, help="Size of each food patch")
    parser.add_argument("--food-detection", type=int, help="How far drones can smell food (default: 20)")

    # Hunger arguments
    parser.add_argument("--hunger-decay", type=int, help="Ticks between hunger decrements (default: 10)")
    parser.add_argument("--no-hunger", action="store_true", help="Disable hunger system")
    parser.add_argument("--death-mode", type=str, choices=["yes", "no", "respawn"],
                        help="What happens when drones starve: yes=die, no=freeze, respawn=die and respawn at queen")

    # Hopper arguments
    parser.add_argument("--hoppers", type=int, help="Number of hopper scout drones")
    parser.add_argument("--hop-distance", type=int, help="How far hoppers jump (default: 5)")

    # Queen position arguments
    parser.add_argument("--queen-x", type=int, help="Queen X position (default: 10)")
    parser.add_argument("--queen-y", type=int, help="Queen Y position (default: 10)")

    # Recording arguments
    parser.add_argument("--record", action="store_true",
        help="Enable keyframe recording for playback")
    parser.add_argument("--keyframe-interval", type=float, default=1.0,
        help="Seconds between keyframes (default: 1.0)")

    # Video recording arguments
    parser.add_argument("--video", action="store_true",
        help="Record simulation as MP4 video")
    parser.add_argument("--video-fps", type=int, default=10,
        help="Video frames per second (default: 10)")
    parser.add_argument("--video-resolution", type=int, default=800,
        help="Video resolution in pixels (default: 800x800)")

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
    if args.no_live:
        config["simulation"]["live_view"] = False
    if args.no_screenshot:
        config["recording"]["save_screenshot"] = False

    # Food configuration overrides
    if args.food_sources:
        if "food" not in config:
            config["food"] = {}
        config["food"]["enabled"] = True
        config["food"]["sources"] = args.food_sources
    if args.food_amount:
        if "food" not in config:
            config["food"] = {}
        config["food"]["amount"] = args.food_amount
    if args.food_spread:
        if "food" not in config:
            config["food"] = {}
        config["food"]["spread"] = args.food_spread.lower()
    if args.food_radius:
        if "food" not in config:
            config["food"] = {}
        config["food"]["radius"] = args.food_radius
    if args.food_detection:
        if "food" not in config:
            config["food"] = {}
        config["food"]["detection_radius"] = args.food_detection

    # Hunger configuration overrides
    if args.hunger_decay:
        if "hunger" not in config:
            config["hunger"] = {}
        config["hunger"]["decay_interval"] = args.hunger_decay
    if args.no_hunger:
        if "hunger" not in config:
            config["hunger"] = {}
        config["hunger"]["enabled"] = False
    if args.death_mode:
        if "hunger" not in config:
            config["hunger"] = {}
        config["hunger"]["death_mode"] = args.death_mode

    # Hopper configuration overrides
    if args.hoppers:
        if "hoppers" not in config:
            config["hoppers"] = {}
        config["hoppers"]["count"] = args.hoppers
    if args.hop_distance:
        if "hoppers" not in config:
            config["hoppers"] = {}
        config["hoppers"]["hop_distance"] = args.hop_distance

    # Queen position overrides
    if args.queen_x is not None:
        if "queen" not in config:
            config["queen"] = {}
        config["queen"]["x"] = args.queen_x
    if args.queen_y is not None:
        if "queen" not in config:
            config["queen"] = {}
        config["queen"]["y"] = args.queen_y

    # Recording configuration overrides
    if args.record:
        if "recording" not in config:
            config["recording"] = {}
        config["recording"]["keyframe_recording"] = True
    if args.keyframe_interval:
        if "recording" not in config:
            config["recording"] = {}
        config["recording"]["keyframe_interval"] = args.keyframe_interval

    # Video configuration overrides
    if args.video:
        if "recording" not in config:
            config["recording"] = {}
        config["recording"]["video_enabled"] = True
        config["recording"]["video_fps"] = args.video_fps
        config["recording"]["video_resolution"] = (args.video_resolution, args.video_resolution)

    # Run simulation
    sim = Simulation(config)
    sim.run()


if __name__ == "__main__":
    main()

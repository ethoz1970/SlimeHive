# Project Hive Mind: Distributed Artificial Life Research Platform
**Version:** 1.0 (Phase: Phototaxis & Environmental Coupling)  
**Date:** January 24, 2026  
**Primary Researcher:** Ethoz2000

---

## 1. Abstract
Hive Mind is a physical simulation platform designed to study **Stigmergy** (indirect coordination) and **Emergent Behavior** in decentralized robotic swarms. Unlike traditional simulations, this project bridges the gap between digital "hive memory" and physical "ground truth" by integrating a distributed sensor network with optical verification.

The system consists of autonomous agents ("Drones") that broadcast virtual pheromones via Bluetooth Low Energy (BLE). A central node ("The Queen") aggregates these signals into a dynamic heatmap, simulating a biological memory that decays over time. The system features **Environmental Coupling**, where the hive's internal physics (memory persistence) are biologically linked to real-world stimuli (light cycles), creating a primitive circadian rhythm.

---

## 2. Hardware Architecture

### The Swarm (Agents)
* **Hardware:** Raspberry Pi Pico 2 W (x5)
* **Power:** 3.7V LiPo Batteries (Individual)
* **Role:** Autonomous movement and pheromone broadcasting.
* **Configuration:**
    * **4x Worker Drones:** Standard broadcast intensity (Red/Orange heatmap signature).
    * **1x Queen Drone:** Maximum broadcast intensity (White/Hot heatmap signature).

### The Brain (Central Processing)
* **Hardware:** Raspberry Pi Zero W ("The Queen")
* **Sensors:** * **Radio:** Onboard Bluetooth (RSSI tracking).
    * **Optical:** Raspberry Pi Camera Module (Legacy Interface).
* **Role:** MQTT Broker, Physics Engine, Web Server, Visual Cortex.

### The Sentry (Optional Extended Range)
* **Hardware:** Raspberry Pi Zero W ("Sentry 02")
* **Role:** Secondary listening post for stereo-triangulation and range extension.

---

## 3. Software Stack

### A. Firmware: `drone_flight.py` (MicroPython)
Runs on the Pico 2 Ws.
* **Virtual Physics:** Each drone simulates movement on a 50x50 internal grid.
* **Broadcasting:** Updates position (X, Y) and Intensity via BLE Manufacturer Data packets.
* **Chaos Factor:** Random walk algorithms with boundary checking.

### B. Core Logic: `queen_brain.py` (Python 3)
Runs on the Pi Zero. The central nervous system.
* **Aggregator:** Listens to `hive/deposit` MQTT topics.
* **Physics Engine:** Manages the `hive_grid` (50x50 numpy array). Applies `DECAY_RATE` to simulate pheromone evaporation.
* **Circadian Logic:** Listens to `hive/environment` to adjust physics based on real-world light levels.
    * **FRENZY MODE:** High Light = Low Decay (Trails persist).
    * **SLEEP MODE:** Low Light = High Decay (Trails evaporate instantly).

### C. Visualizer: `dashboard_hud.py` (Flask/Python)
Runs on the Pi Zero.
* **Dual-View Interface:**
    1.  **Optical Sensor:** Live MJPEG stream from the physical camera.
    2.  **Telemetry Map:** Real-time canvas rendering of the pheromone grid.
* **Optical Cortex:** Analyzes video frame brightness in real-time and publishes to `hive/environment`.

---

## 4. Setup & Operation Sequence

### 1. Power the Brain
SSH into the Queen (`10.42.0.1`) and launch the nervous system.
```bash
# Terminal 1: The Brain
python3 queen_brain.py

# Terminal 2: The Eyes & Dashboard
python3 dashboard_hud.py
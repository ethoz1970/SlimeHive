# HIVE MIND: Slime Intelligence Swarm 🐝🦠

> **"Biological Logic for Digital Swarms."**

Hive Mind is an open-source experimental framework for controlling and visualizing decentralized drone swarms. Inspired by **Slime Mold (Physarum polycephalum)** and **Ant Colony Optimization**, it uses a "Pheromone Grid" to map the world, creating a shared memory enabling emergent behavior in simple agents.

![Dashboard Preview](dashboard_preview.png)
*(Note: Add a screenshot of your dashboard here!)*

## 🧠 The Concept

Most drone swarms rely on precise GPS and rigid formation algorithms. **Hive Mind** goes the opposite direction:
*   **Decentralized Sensing**: Drones blindly broadcast their existence (BLE Beacons).
*   **The Queen**: A central "Brain" node aggregates these faint signals.
*   **Gravity Physics**: Instead of triangulation, position is calculated using a weighted "Gravity Model" where sensors pull the drone based on Signal Strength (RSSI).
*   **Ghost Layer**: The system remembers *everywhere* a drone has been, building a long-term "Ghost Map" that serves as the swarm's collective memory.

## ✨ Features

-   **Hybrid Swarm**: Seamlessly mixes **Real Physical Drones** (Pi Zero/Pico) with **Virtual Drones** in the same simulation.
-   **Biomimetic Moods**: The Hive reacts to environmental light sensors, shifting between "SLEEP" (Night) and "FRENZY" (Day/Sunrise).
-   **Gravity Positioning**: A robust, noise-tolerant positioning system that turns RSSI values into physical forces.
-   **Visual History**: A `dashboard_hud` that renders live positions, flight trails, and the "Ghost Fog" of long-term history.
-   **Session Archiving**: Full CSV flight logs and JSON memory snapshots are archived on every reset.

## 🛠️ Architecture

The system consists of 4 biological components:

1.  **Queen Brain (`queen_brain.py`)**: The Cortex. Runs the physics loop, decays pheromones, and manages the state (`hive_state.json`).
2.  **The Ears (`hive_ear.py`)**: Distributed sensor nodes (Queen, Sentinel, etc.) that listen for BLE signals and forward them via MQTT.
3.  **The Eyes (`dashboard_hud.py`)**: A Flask-based HUD visualizing the swarm in real-time.
4.  **The Scribe (`hive_logger.py`)**: Records every heartbeat and position to CSV for analysis.

## 🚀 Getting Started

### Prerequisites
*   Python 3.9+
*   Mosquitto MQTT Broker (`brew install mosquitto` or `apt install mosquitto`)
*   Raspberry Pi (for Drones/Ears) or Mac/Linux (for Queen/Dashboard)

### Installation

1.  **Clone the Hive:**
    ```bash
    git clone https://github.com/yourusername/hive-mind.git
    cd hive-mind
    ```

2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Start the Brain (Localhost):**
    ```bash
    # Terminal 1
    python3 queen_brain.py
    ```

4.  **Start the Dashboard:**
    ```bash
    # Terminal 2
    python3 dashboard_hud.py
    ```
    *Open `http://localhost:5000` in your browser.*

5.  **Start the Ears (If using Real Drones):**
    ```bash
    # Terminal 3
    sudo python3 hive_ear.py
    ```

## 🤝 Contributing & Funding

We are building the future of **Low-Cost Swarm Intelligence**.
We need help with:
*   **Hardware Integration**: ESP32 / nRF52 porting.
*   **AI**: Replacing the "Gravity Model" with a Neural Network.
*   **Visuals**: WebGL/Three.js 3D visualizations.

**Support the Hive:**
[Link to your Sponsor/Patreon/OpenCollective]

## 📜 License

MIT License. swarm freely.

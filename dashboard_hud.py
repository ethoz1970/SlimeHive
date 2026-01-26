from flask import Flask, render_template_string, Response, request, jsonify
import json
import time
import io
import subprocess
import paho.mqtt.client as mqtt
from PIL import Image
import glob
import csv
import os
import re
import threading
import logging
import requests

# --- REMOTE QUEEN CONFIGURATION ---
# Set QUEEN_IP environment variable to connect to remote Pi
# Example: export QUEEN_IP=192.168.1.100
QUEEN_IP = os.environ.get('QUEEN_IP', None)
QUEEN_API_URL = f"http://{QUEEN_IP}:5001" if QUEEN_IP else None
IS_REMOTE_MODE = QUEEN_IP is not None

# Dashboard port (default 5000, but macOS AirPlay uses 5000)
DASHBOARD_PORT = int(os.environ.get('DASHBOARD_PORT', 5050 if IS_REMOTE_MODE else 5000))

# Silence the Flask access logs for /data polling
log = logging.getLogger('werkzeug')
class FilterDataLogs(logging.Filter):
    def filter(self, record):
        return "/data" not in record.getMessage() and "/video_feed" not in record.getMessage()
log.addFilter(FilterDataLogs())

app = Flask(__name__)

# --- CONFIGURATION ---
MQTT_BROKER = QUEEN_IP if QUEEN_IP else "localhost"
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    if IS_REMOTE_MODE:
        print(f"/// MQTT Connected to Queen at {MQTT_BROKER} ///")
except:
    print(f"Warning: Brain not found (MQTT Disconnected at {MQTT_BROKER})")

# --- CAMERA SYSTEM ---
# Camera is only available on Pi, disabled in remote mode
latest_frame = None
CAMERA_ENABLED = not IS_REMOTE_MODE

def get_camera_command():
    return [
        "rpicam-still", "--width", "320", "--height", "240", # Lower res for speed
        "--encoding", "jpg", "--output", "-", "--timeout", "1", "--nopreview"
    ]

def camera_loop():
    global latest_frame
    if not CAMERA_ENABLED:
        print("/// CAMERA DISABLED (Remote Mode) ///")
        return

    print("/// CAMERA SENSOR ONLINE ///")

    while True:
        try:
            # 1. Capture Frame
            result = subprocess.run(get_camera_command(), capture_output=True)

            if result.stdout:
                img_data = result.stdout
                latest_frame = img_data

                # --- OPTICAL CORTEX ANALYSIS ---
                try:
                    image = Image.open(io.BytesIO(img_data))
                    # Resize to 1x1 pixel to get average brightness instantly
                    avg_color = image.resize((1, 1)).getpixel((0, 0))
                    # Handle grayscale (int) or RGB (tuple)
                    brightness = avg_color if isinstance(avg_color, int) else sum(avg_color) / 3

                    # Publish to Hive Mind
                    client.publish("hive/environment", int(brightness))
                except:
                    pass
                # -------------------------------
            else:
                if result.stderr:
                    print(f"Cam Error: {result.stderr.decode('utf-8')}")

            time.sleep(0.5) # 2 FPS is plenty for "Eye" function

        except Exception as e:
            print(f"Cam Exception: {e}")
            time.sleep(1)

def gen_frames():
    global latest_frame
    while True:
        if latest_frame:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        else:
            # Return a placeholder frame in remote mode
            yield (b'--frame\r\n'
                   b'Content-Type: text/plain\r\n\r\nNo camera feed\r\n')
        time.sleep(0.1)

# --- (Keep your existing HTML Template below this line) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>HIVE RESEARCH TERMINAL</title>
    <style>
        body {
            background-color: #000; color: #0f0;
            font-family: 'Courier New', monospace;
            margin: 0; padding: 20px;
            overflow: hidden;
        }
        h2 { border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }
        .container { display: flex; gap: 0; height: 90vh; }
        .panel { border: 1px solid #333; background: #050505; position: relative; overflow: hidden; }
        .panel-left { width: 20%; min-width: 150px; max-width: 50%; }
        .panel-right { flex: 1; }
        .resizer {
            width: 8px;
            background: #222;
            cursor: col-resize;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }
        .resizer:hover, .resizer.dragging { background: #0f0; }
        .resizer::after { content: "⋮"; color: #666; font-size: 16px; }
        .panel-header { background: #111; color: #aaa; padding: 5px; font-size: 12px; border-bottom: 1px solid #333; }
        img.feed { width: 100%; height: auto; display: block; opacity: 0.9; }
        #map-container { position: relative; width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; }
        canvas { border: 1px solid #222; }
        .drone-label { position: absolute; color: white; font-weight: bold; font-size: 10px; text-shadow: 0 0 2px #000; pointer-events: none; }
    </style>
</head>
<body>
    <h2>
        /// HIVE MIND: RESEARCH TERMINAL ///
        <a href="/playback" style="float:right; font-size: 14px; color:#0af; text-decoration:none; margin-left: 20px; border: 1px solid #0af; padding: 2px 8px;">[PLAYBACK]</a>
        <span style="float:right; font-size: 14px; margin-left: 10px;">
            <span style="color:#aaa;">SIMULATION:</span>
            <select id="mode-select" onchange="setMode()" style="background:#000; color:#f0f; border:1px solid #333; font-family:monospace; padding:2px;">
                <option value="RANDOM" selected>RANDOM WALK</option>
                <option value="FIND_QUEEN">FIND THE QUEEN</option>
            </select>
        </span>
        <span style="float:right; font-size: 14px; margin-left: 10px;">
            <span style="color:#aaa;">V-DRONES:</span>
            <input type="number" id="v-count" value="0" min="0" max="50" style="width:40px; background:#000; color:#fff; border:1px solid #333;">
            <button onclick="setVirtualSwarm()" style="background:#222; color:#fff; border:1px solid #333; cursor:pointer;">SET</button>
        </span>
        <span style="float:right; font-size: 14px; margin-left: 20px;">
            <select id="time-filter" style="background:#000; color:#0f0; border:1px solid #333; font-family:monospace; padding:2px;">
                <option value="live">LIVE (10s)</option>
                <option value="60">1 Minute</option>
                <option value="600">10 Minutes</option>
                <option value="3600">1 Hour</option>
                <option value="14400">4 Hours</option>
            </select>
        </span>
        <span style="float:right; font-size: 14px; margin-left: 10px;">
            <select id="drone-filter" style="background:#000; color:#0f0; border:1px solid #333; font-family:monospace; padding:2px;">
                <option value="ALL">ALL DRONES</option>
            </select>
        </span>
        <span style="float:right; font-size: 14px; margin-left: 20px;">
            <button onclick="resetHive()" style="color:#f44; border:1px solid #f44; background:#000; cursor:pointer; font-weight:bold;">RESET HIVE</button>
        </span>
        <span id="sun-status" style="float:right; font-size: 14px; color: #888;">SUN: SYNCING...</span>
    </h2>
    <div class="container">
        <div class="panel panel-left" id="panel-left">
            <div class="panel-header">Optical Sensor (Live Analysis)</div>
            <img class="feed" src="/video_feed">
            <div class="panel-header" style="border-top: 1px solid #333; margin-top: 0;">Drone Registry</div>
            <div id="drone-registry" style="padding: 10px; font-size: 12px; height: 150px; overflow-y: auto;"></div>
        </div>
        <div class="resizer" id="resizer"></div>
        <div class="panel panel-right">
            <div class="panel-header">Swarm Telemetry <span style="float:right; color: #fff;">Active Drones: <span id="drone-counter" style="color: #f00">0</span></span></div>
            <div id="map-container">
                <canvas id="hiveMap" width="800" height="800"></canvas>
                <div id="overlays"></div>
            </div>
        </div>
    </div>
    <script>
        const canvas = document.getElementById('hiveMap');
        const ctx = canvas.getContext('2d');
        const overlays = document.getElementById('overlays');
        const droneCounter = document.getElementById('drone-counter');
        const timeFilter = document.getElementById('time-filter');
        let gridSize = 100;  // Default, updated from data
        let scale = 800 / gridSize; 

        function stringToHue(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                hash = str.charCodeAt(i) + ((hash << 5) - hash);
            }
            return Math.abs(hash % 360);
        }

        function getColor(value) {
            if (value < 5) return `rgb(0,0,0)`;
            if (value < 50) return `rgb(${value*5}, 0, 0)`; 
            if (value < 150) return `rgb(255, ${value}, 0)`; 
            return `rgb(255, 255, ${Math.min(255, value-100)})`;
        }

        async function fetchState() {
            try {
                // If filtering history, don't spam the status endpoint for map data
                // checking value...
                const window = timeFilter.value;

                // 1. Always get live mood/count data (lightweight)
                const response = await fetch('/data');
                const data = await response.json();

                // Update grid size from actual data
                if (data.grid && data.grid.length > 0) {
                    gridSize = data.grid.length;
                    scale = 800 / gridSize;
                }

                updateSunStatus(data.mood);

                // 2. Decide what to draw
                drawMap(data.grid, data.ghost_grid);
                drawQueen();
                drawSentinel();
                
                if (window === "live") {
                    drawDrones(data.drones);
                } else {
                    // Fetch and draw history
                    fetchHistory(window);
                    // Still show current active count but maybe indicate it's history view?
                    // Actually, let's keep the drone list live, but the MAP shows history.
                     drawDrones(data.drones, true); // Pass true to hide standard trails/dots to avoid clutter?
                }
                
            } catch (e) { console.error("Fetch Error:", e); }
        }
        
        function updateSunStatus(mood) {
             const sunStatus = document.getElementById('sun-status');
            if (mood === "FRENZY") {
                sunStatus.innerText = "SUN: DAY";
                sunStatus.style.color = "#ff0";
            } else if (mood === "SLEEP") {
                sunStatus.innerText = "SUN: NIGHT";
                sunStatus.style.color = "#44f";
            }
        }

        async function setMode() {
            const mode = document.getElementById('mode-select').value;
            await fetch(`/set_mode?mode=${mode}`);
        }

        async function setVirtualSwarm() {
            const count = document.getElementById('v-count').value;
            await fetch(`/set_virtual_swarm?count=${count}`);
        }
        
        function resetHive() {
            if (confirm("WARNING: This will wipe all hive memory and learned trails. Proceed?")) {
                fetch('/reset_hive'); // Non-blocking
                // Force Reload to clear frontend state and reconnect to new log
                setTimeout(() => location.reload(), 1000);
            }
        }

        async function fetchHistory(window) {
             try {
                const res = await fetch(`/history_data?window=${window}`);
                const history = await res.json();
                updateDroneFilter(Object.keys(history));
                drawHistoryTrails(history);
            } catch(e) {}
        }

        function updateDroneFilter(droneIds) {
            const select = document.getElementById('drone-filter');
            const current = select.value;
            
            // Only update if count changed (simple heuristic to avoid DOM thrashing)
            if (select.options.length === droneIds.length + 1) return;

            select.innerHTML = '<option value="ALL">ALL DRONES</option>';
            droneIds.sort().forEach(id => {
                const opt = document.createElement('option');
                opt.value = id;
                opt.innerText = id;
                if (id === current) opt.selected = true;
                select.appendChild(opt);
            });
        }
        
        function drawHistoryTrails(history) {
            const filter = document.getElementById('drone-filter').value;
            
            // Draw long trails
            for (const [id, points] of Object.entries(history)) {
                if (points.length < 2) continue;
                if (filter !== "ALL" && id !== filter) continue;
                
                const hue = stringToHue(id);
                const color = `hsl(${hue}, 100%, 50%)`;
                
                ctx.beginPath();
                ctx.strokeStyle = color; 
                ctx.globalAlpha = (filter === "ALL") ? 0.3 : 0.8; // Bright if single selected
                ctx.lineWidth = (filter === "ALL") ? 1 : 2;
                
                // Draw path
                const startX = points[0][0] * scale + scale/2;
                const startY = (gridSize - 1 - points[0][1]) * scale + scale/2;
                
                ctx.moveTo(startX, startY);
                for (let i = 1; i < points.length; i++) {
                     ctx.lineTo(points[i][0] * scale + scale/2, (gridSize - 1 - points[i][1]) * scale + scale/2);
                }
                ctx.stroke();
                
                // Draw Start Marker (Circle)
                ctx.beginPath();
                ctx.strokeStyle = color;
                ctx.lineWidth = 1;
                ctx.arc(startX, startY, 3, 0, 2 * Math.PI);
                ctx.stroke();

                // Draw End Marker (X)
                const endX = points[points.length-1][0] * scale + scale/2;
                const endY = (gridSize - 1 - points[points.length-1][1]) * scale + scale/2;
                
                ctx.beginPath();
                ctx.moveTo(endX - 3, endY - 3);
                ctx.lineTo(endX + 3, endY + 3);
                ctx.moveTo(endX + 3, endY - 3);
                ctx.lineTo(endX - 3, endY + 3);
                ctx.stroke();
                
                ctx.globalAlpha = 1.0;
            }
        }

        function drawMap(grid, ghost_grid) {
            if (!grid || grid.length < gridSize) return;
            // Ghost grid might be undefined initially if old brain running
            const hasGhost = ghost_grid && ghost_grid.length === gridSize;

            for (let x = 0; x < gridSize; x++) {
                for (let y = 0; y < gridSize; y++) {
                    const active = grid[x][y];
                    
                    if (active > 5) {
                        ctx.fillStyle = getColor(active);
                        ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
                    } else if (hasGhost) {
                        const ghost = ghost_grid[x][y];
                        if (ghost > 10) {
                            // Render Ghost Memory (White/Grey Fog)
                            const g = Math.min(255, Math.floor(ghost));
                            // Use low opacity white for a "fog" effect
                            ctx.fillStyle = `rgba(255, 255, 255, ${g/400})`; 
                            // Or simple Solid Grey if opacity is tricky on black
                            // ctx.fillStyle = `rgb(${Math.floor(g/3)}, ${Math.floor(g/3)}, ${Math.floor(g/3)})`;
                            ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
                        }
                    }
                }
            }
        }

        function drawQueen() {
            // The Queen sits at the center
            const x = gridSize / 2;
            const y = gridSize / 2;
            const px = x * scale;
            const py = (gridSize - 1 - y) * scale;

            // Draw Icon (Diamond)
            ctx.fillStyle = '#fff';
            ctx.beginPath();
            ctx.moveTo(px, py - 8);
            ctx.lineTo(px + 8, py);
            ctx.lineTo(px, py + 8);
            ctx.lineTo(px - 8, py);
            ctx.closePath();
            ctx.fill();

            // Overlay Label
            ctx.fillStyle = '#000';
            ctx.font = 'bold 10px monospace';
            ctx.fillText("Q", px - 3.5, py + 3.5);
        }

        function drawSentinel() {
            // The Sentinel sits at 10, 10
            const x = 10;
            const y = 10;
            const px = x * scale;
            const py = (gridSize - 1 - y) * scale;

            // Draw Icon (Blue Triangle)
            ctx.fillStyle = '#0af'; // Bright Blue
            ctx.beginPath();
            ctx.moveTo(px, py - 8);     // Top
            ctx.lineTo(px + 8, py + 8); // Bottom Right
            ctx.lineTo(px - 8, py + 8); // Bottom Left
            ctx.closePath();
            ctx.fill();

            // Overlay Label
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 10px monospace';
            ctx.fillText("S", px - 3.5, py + 6);
        }

        let tickCounter = 0;

        function drawDrones(drones, historyMode=false) {
            // updateDroneFilter(Object.keys(drones)); // Moved to throttled block below
            overlays.innerHTML = ''; 
            const now = Date.now() / 1000;
            let activeCount = 0;
            
            const filter = document.getElementById('drone-filter').value;
            
            for (const [id, drone] of Object.entries(drones)) {
                // FILTER LOGIC
                if (filter !== "ALL" && id !== filter) continue;

                // ... (Logic to count active/warning/red) ...
                const diff = now - drone.last_seen;
                
                // Color Generation
                const hue = stringToHue(id);
                let lightness = 50; // Active
                let alpha = 1.0;

                if (diff < 10) { activeCount++; }
                else if (diff <= 30) { lightness = 30; } // Warning
                else { lightness = 20; alpha = 0.5; } // Old/Ghostly
                
                // Virtual Drones: Shift towards Cyan/Blue range?
                // Actually, let's keep it purely hash based for uniqueness, 
                // but maybe add a border or shape later. 
                // Ensuring Virtual Drones are distinct:
                if (id.startsWith("V-")) {
                    // Force high saturation, specific lightness?
                    // Let's just use the hash. It's fine.
                }

                const color = `hsla(${hue}, 100%, ${lightness}%, ${alpha})`;
                
                // Always add label to overlay
                const el = document.createElement('div');
                el.className = 'drone-label';
                el.style.left = (drone.x * scale + 10) + 'px';
                el.style.top = ((gridSize - 1 - drone.y) * scale - 10) + 'px';
                el.innerHTML = `[${id}]<br><span style="color:#888">${drone.rssi}dB</span>`;
                el.style.color = color; 
                overlays.appendChild(el);
                
                // Draw Current Position Dot
                ctx.strokeStyle = color; 
                ctx.fillStyle = color;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.arc(drone.x * scale + scale/2, (gridSize - 1 - drone.y) * scale + scale/2, 8, 0, 2 * Math.PI); // Larger dots for larger map
                ctx.fill(); // Solid dot for visibility
                ctx.stroke();

                // Draw Live Trail (Last 10 steps) ONLY if NOT in History Mode
                if (!historyMode && drone.trail && drone.trail.length > 1) {
                    ctx.beginPath();
                    ctx.strokeStyle = color; 
                    ctx.globalAlpha = 0.4; 
                    ctx.moveTo(drone.trail[0][0] * scale + scale/2, (gridSize - 1 - drone.trail[0][1]) * scale + scale/2);
                    for (let i = 1; i < drone.trail.length; i++) {
                        ctx.lineTo(drone.trail[i][0] * scale + scale/2, (gridSize - 1 - drone.trail[i][1]) * scale + scale/2);
                    }
                    ctx.stroke();
                    ctx.globalAlpha = 1.0; 
                }
            }
            
            if (activeCount !== parseInt(droneCounter.innerText)) {
                droneCounter.innerText = activeCount;
                droneCounter.style.color = activeCount > 0 ? '#0f0' : '#f00';
            }
            
            // FLICKER FIX: Update List only every 10 ticks (1 sec)
            tickCounter++;
            if (tickCounter % 10 === 0) {
                updateDroneList(drones);
            }
            // DROPDOWN FIX: Update Filter only every 50 ticks (5 sec) to allow selection
            if (tickCounter % 50 === 0) {
                 updateDroneFilter(Object.keys(drones));
            }
        }

        function updateDroneList(drones) {
            const list = document.getElementById('drone-registry');
            // Optimizing this list is harder because times change every tick.
            // Leaving as is for now, but could be optimized if needed.
            list.innerHTML = ''; 
            // ... (rest of function)
            const now = Date.now() / 1000;
            const sortedIds = Object.keys(drones).sort();
            
            for (const id of sortedIds) {
                const drone = drones[id];
                const diff = now - drone.last_seen;
                // ... (rebuild items)
                 const item = document.createElement('div');
                item.style.marginBottom = '4px';
                const hue = stringToHue(id);
                item.style.color = `hsl(${hue}, 100%, 60%)`;
                item.innerText = `> [${id}] RSSI:${drone.rssi}dB (${Math.round(diff)}s ago)`;
                list.appendChild(item);
            }
        }
        
        let previousDroneListJson = "";

        function updateDroneFilter(droneIds) {
            const select = document.getElementById('drone-filter');
            droneIds.sort();
            const currentJson = JSON.stringify(droneIds);
            
            // DEBOUNCE: Only rebuild if the LIST CONTENT actually changed
            if (currentJson === previousDroneListJson) return;
            previousDroneListJson = currentJson;

            const currentSelection = select.value;
            select.innerHTML = '<option value="ALL">ALL DRONES</option>';
            
            droneIds.forEach(id => {
                const opt = document.createElement('option');
                opt.value = id;
                opt.innerText = id;
                if (id === currentSelection) opt.selected = true;
                select.appendChild(opt);
            });
        }
        setInterval(fetchState, 100);

        // --- RESIZER FUNCTIONALITY ---
        const resizer = document.getElementById('resizer');
        const panelLeft = document.getElementById('panel-left');
        let isResizing = false;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            resizer.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const containerRect = document.querySelector('.container').getBoundingClientRect();
            let newWidth = e.clientX - containerRect.left;
            // Clamp between min and max
            newWidth = Math.max(150, Math.min(newWidth, containerRect.width * 0.5));
            panelLeft.style.width = newWidth + 'px';
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                resizer.classList.remove('dragging');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
        });
    </script>
</body>
</html>
"""

PLAYBACK_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>HIVE PLAYBACK TERMINAL</title>
    <style>
        body {
            background-color: #000; color: #0f0;
            font-family: 'Courier New', monospace;
            margin: 0; padding: 20px;
            overflow: hidden;
        }
        h2 { border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }
        .container { display: grid; grid-template-columns: 280px 1fr; gap: 20px; height: 85vh; }
        .panel { border: 1px solid #333; background: #050505; }
        .panel-header { background: #111; color: #aaa; padding: 8px; font-size: 12px; border-bottom: 1px solid #333; }
        .archive-list { height: calc(100% - 250px); overflow-y: auto; padding: 10px; }
        .archive-item {
            padding: 8px; margin: 4px 0; cursor: pointer;
            border: 1px solid #222; transition: all 0.2s;
        }
        .archive-item:hover { border-color: #0f0; background: #111; }
        .archive-item.selected { border-color: #0f0; background: #0f02; }
        .metadata { padding: 10px; font-size: 12px; border-top: 1px solid #333; }
        .metadata-row { margin: 4px 0; }
        .metadata-label { color: #888; }
        #map-container { position: relative; display: flex; justify-content: center; align-items: center; height: calc(100% - 80px); }
        canvas { border: 1px solid #222; max-width: 100%; max-height: 100%; }
        .controls { padding: 10px; display: flex; gap: 10px; align-items: center; border-top: 1px solid #333; }
        .controls button {
            background: #111; color: #0f0; border: 1px solid #333;
            padding: 5px 15px; cursor: pointer; font-family: monospace;
        }
        .controls button:hover { border-color: #0f0; }
        .controls button:disabled { color: #555; cursor: not-allowed; }
        .controls select {
            background: #000; color: #0f0; border: 1px solid #333;
            padding: 5px; font-family: monospace;
        }
        #timeline { flex: 1; height: 20px; background: #111; cursor: pointer; }
        #timeline-progress { height: 100%; background: #0f03; width: 0%; }
        #timestamp { color: #888; font-size: 11px; min-width: 160px; }
        .no-csv { color: #666; font-style: italic; }
        .drone-label { position: absolute; color: white; font-weight: bold; font-size: 10px; text-shadow: 0 0 2px #000; pointer-events: none; }
    </style>
</head>
<body>
    <h2>
        /// HIVE MIND: PLAYBACK TERMINAL ///
        <a href="/" style="float:right; font-size: 14px; color:#0f0; text-decoration:none; margin-left: 20px; border: 1px solid #0f0; padding: 2px 8px;">[LIVE DASHBOARD]</a>
    </h2>
    <div class="container">
        <div class="panel">
            <div class="panel-header">ARCHIVED SESSIONS</div>
            <div class="archive-list" id="archive-list">
                <div style="color:#666;">Loading archives...</div>
            </div>
            <div class="metadata" id="metadata">
                <div class="panel-header" style="margin: -10px -10px 10px -10px; padding: 8px;">METADATA</div>
                <div class="metadata-row"><span class="metadata-label">Mood:</span> <span id="meta-mood">-</span></div>
                <div class="metadata-row"><span class="metadata-label">Decay:</span> <span id="meta-decay">-</span></div>
                <div class="metadata-row"><span class="metadata-label">Sim Mode:</span> <span id="meta-mode">-</span></div>
                <div class="metadata-row"><span class="metadata-label">Drones:</span> <span id="meta-drones">-</span></div>
                <div class="metadata-row"><span class="metadata-label">Archived:</span> <span id="meta-time">-</span></div>
            </div>
        </div>
        <div class="panel">
            <div class="panel-header">SNAPSHOT VISUALIZATION</div>
            <div id="map-container">
                <canvas id="hiveMap" width="800" height="800"></canvas>
                <div id="overlays"></div>
            </div>
            <div class="controls" id="playback-controls">
                <button id="play-btn" onclick="togglePlayback()" disabled>PLAY SESSION</button>
                <select id="speed-select" onchange="setSpeed()">
                    <option value="0.5">0.5x</option>
                    <option value="1" selected>1x</option>
                    <option value="2">2x</option>
                    <option value="4">4x</option>
                </select>
                <div id="timeline" onclick="seekTimeline(event)">
                    <div id="timeline-progress"></div>
                </div>
                <span id="timestamp">No session loaded</span>
            </div>
        </div>
    </div>
    <script>
        const canvas = document.getElementById('hiveMap');
        const ctx = canvas.getContext('2d');
        const overlays = document.getElementById('overlays');
        let gridSize = 100;  // Default, updated from archive data
        let scale = 800 / gridSize;

        let archives = [];
        let currentArchive = null;
        let flightData = null;
        let isPlaying = false;
        let playbackSpeed = 1;
        let playbackIndex = 0;
        let animationId = null;
        let lastFrameTime = 0;

        function stringToHue(str) {
            let hash = 0;
            for (let i = 0; i < str.length; i++) {
                hash = str.charCodeAt(i) + ((hash << 5) - hash);
            }
            return Math.abs(hash % 360);
        }

        function getColor(value) {
            if (value < 5) return `rgb(0,0,0)`;
            if (value < 50) return `rgb(${value*5}, 0, 0)`;
            if (value < 150) return `rgb(255, ${value}, 0)`;
            return `rgb(255, 255, ${Math.min(255, value-100)})`;
        }

        async function loadArchives() {
            try {
                const res = await fetch('/api/archives');
                archives = await res.json();
                renderArchiveList();
            } catch(e) {
                document.getElementById('archive-list').innerHTML = '<div style="color:#f00;">Error loading archives</div>';
            }
        }

        function renderArchiveList() {
            const list = document.getElementById('archive-list');
            if (archives.length === 0) {
                list.innerHTML = '<div style="color:#666;">No archived sessions found</div>';
                return;
            }

            list.innerHTML = archives.map((a, i) => `
                <div class="archive-item" onclick="selectArchive(${i})" id="archive-${i}">
                    <div style="color:#0f0;">> ${a.display_time}</div>
                    <div style="color:#666; font-size:11px; margin-top:4px;">${a.filename}</div>
                </div>
            `).join('');
        }

        async function selectArchive(index) {
            // Update selection UI
            document.querySelectorAll('.archive-item').forEach(el => el.classList.remove('selected'));
            document.getElementById(`archive-${index}`).classList.add('selected');

            const archive = archives[index];

            try {
                // Load archive data
                const res = await fetch(`/api/archive/${archive.filename}`);
                currentArchive = await res.json();

                // Update metadata
                document.getElementById('meta-mood').innerText = currentArchive.mood || 'UNKNOWN';
                document.getElementById('meta-mood').style.color = currentArchive.mood === 'FRENZY' ? '#ff0' : '#44f';
                document.getElementById('meta-decay').innerText = currentArchive.decay_rate || '-';
                document.getElementById('meta-mode').innerText = currentArchive.mode || '-';
                document.getElementById('meta-drones').innerText = Object.keys(currentArchive.drones || {}).length;
                document.getElementById('meta-time').innerText = archive.display_time;

                // Render static snapshot
                renderSnapshot();

                // Check for matching flight log
                await checkFlightLog(archive.timestamp);

            } catch(e) {
                console.error('Error loading archive:', e);
            }
        }

        async function checkFlightLog(timestamp) {
            const playBtn = document.getElementById('play-btn');
            const timestampEl = document.getElementById('timestamp');

            try {
                const res = await fetch('/api/flight_logs');
                const logs = await res.json();

                // Find matching log (within same session - check if timestamp is within log range)
                const matchingLog = logs.find(log => {
                    // Check if archive timestamp falls within this log's timeframe
                    return log.start_time <= timestamp && (log.end_time >= timestamp || log.end_time === 0);
                });

                if (matchingLog) {
                    // Load the flight data
                    const dataRes = await fetch(`/api/flight_log/${matchingLog.filename}`);
                    flightData = await dataRes.json();

                    playBtn.disabled = false;
                    timestampEl.innerText = `Flight data: ${flightData.length} points`;
                } else {
                    flightData = null;
                    playBtn.disabled = true;
                    timestampEl.innerHTML = '<span class="no-csv">No flight data available</span>';
                }
            } catch(e) {
                flightData = null;
                playBtn.disabled = true;
                timestampEl.innerHTML = '<span class="no-csv">No flight data available</span>';
            }
        }

        function renderSnapshot() {
            if (!currentArchive) return;

            // Update grid size from archive data
            if (currentArchive.grid && currentArchive.grid.length > 0) {
                gridSize = currentArchive.grid.length;
                scale = 800 / gridSize;
            }

            // Clear canvas
            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Draw heat map
            drawMap(currentArchive.grid, currentArchive.ghost_grid);

            // Draw queen
            drawQueen();

            // Draw sentinel
            drawSentinel();

            // Draw drones at their final positions
            drawDrones(currentArchive.drones);
        }

        function drawMap(grid, ghost_grid) {
            if (!grid || grid.length < gridSize) return;
            const hasGhost = ghost_grid && ghost_grid.length === gridSize;

            for (let x = 0; x < gridSize; x++) {
                for (let y = 0; y < gridSize; y++) {
                    const active = grid[x][y];

                    if (active > 5) {
                        ctx.fillStyle = getColor(active);
                        ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
                    } else if (hasGhost) {
                        const ghost = ghost_grid[x][y];
                        if (ghost > 10) {
                            const g = Math.min(255, Math.floor(ghost));
                            ctx.fillStyle = `rgba(255, 255, 255, ${g/400})`;
                            ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
                        }
                    }
                }
            }
        }

        function drawQueen() {
            const x = gridSize / 2;
            const y = gridSize / 2;
            const px = x * scale;
            const py = (gridSize - 1 - y) * scale;

            ctx.fillStyle = '#fff';
            ctx.beginPath();
            ctx.moveTo(px, py - 8);
            ctx.lineTo(px + 8, py);
            ctx.lineTo(px, py + 8);
            ctx.lineTo(px - 8, py);
            ctx.closePath();
            ctx.fill();

            ctx.fillStyle = '#000';
            ctx.font = 'bold 10px monospace';
            ctx.fillText("Q", px - 3.5, py + 3.5);
        }

        function drawSentinel() {
            const x = 10;
            const y = 10;
            const px = x * scale;
            const py = (gridSize - 1 - y) * scale;

            ctx.fillStyle = '#0af';
            ctx.beginPath();
            ctx.moveTo(px, py - 8);
            ctx.lineTo(px + 8, py + 8);
            ctx.lineTo(px - 8, py + 8);
            ctx.closePath();
            ctx.fill();

            ctx.fillStyle = '#fff';
            ctx.font = 'bold 10px monospace';
            ctx.fillText("S", px - 3.5, py + 6);
        }

        function drawDrones(drones, positions = null) {
            overlays.innerHTML = '';

            for (const [id, drone] of Object.entries(drones || {})) {
                const hue = stringToHue(id);
                const color = `hsl(${hue}, 100%, 50%)`;

                // Use provided positions or drone's stored position
                const x = positions && positions[id] ? positions[id].x : drone.x;
                const y = positions && positions[id] ? positions[id].y : drone.y;

                // Draw label
                const el = document.createElement('div');
                el.className = 'drone-label';
                el.style.left = (x * scale + 10) + 'px';
                el.style.top = ((gridSize - 1 - y) * scale - 10) + 'px';
                el.innerHTML = `[${id}]`;
                el.style.color = color;
                overlays.appendChild(el);

                // Draw dot
                ctx.fillStyle = color;
                ctx.strokeStyle = color;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.arc(x * scale + scale/2, (gridSize - 1 - y) * scale + scale/2, 8, 0, 2 * Math.PI);
                ctx.fill();
                ctx.stroke();
            }
        }

        function togglePlayback() {
            if (isPlaying) {
                stopPlayback();
            } else {
                startPlayback();
            }
        }

        function startPlayback() {
            if (!flightData || flightData.length === 0) return;

            isPlaying = true;
            document.getElementById('play-btn').innerText = 'PAUSE';
            playbackIndex = 0;
            lastFrameTime = performance.now();
            animate();
        }

        function stopPlayback() {
            isPlaying = false;
            document.getElementById('play-btn').innerText = 'PLAY SESSION';
            if (animationId) {
                cancelAnimationFrame(animationId);
                animationId = null;
            }
            // Return to static snapshot
            renderSnapshot();
        }

        function setSpeed() {
            playbackSpeed = parseFloat(document.getElementById('speed-select').value);
        }

        function seekTimeline(event) {
            if (!flightData || flightData.length === 0) return;

            const timeline = document.getElementById('timeline');
            const rect = timeline.getBoundingClientRect();
            const pct = (event.clientX - rect.left) / rect.width;
            playbackIndex = Math.floor(pct * flightData.length);

            if (!isPlaying) {
                // Show single frame at seek position
                renderFrame(playbackIndex);
            }
        }

        function animate() {
            if (!isPlaying) return;

            const now = performance.now();
            const delta = now - lastFrameTime;

            // Advance based on speed (assuming ~100ms between original data points)
            if (delta > (100 / playbackSpeed)) {
                lastFrameTime = now;
                playbackIndex++;

                if (playbackIndex >= flightData.length) {
                    stopPlayback();
                    return;
                }

                renderFrame(playbackIndex);
            }

            animationId = requestAnimationFrame(animate);
        }

        function renderFrame(index) {
            if (!flightData || !currentArchive) return;

            // Clear and draw base map
            ctx.fillStyle = '#000';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            drawMap(currentArchive.grid, currentArchive.ghost_grid);
            drawQueen();
            drawSentinel();

            // Build current positions from flight data up to this point
            const positions = {};
            const trails = {};

            // Look back through recent history for trails
            const trailLength = 20;
            const startIdx = Math.max(0, index - trailLength);

            for (let i = startIdx; i <= index; i++) {
                const point = flightData[i];
                if (!point) continue;

                const id = point.drone_id;
                positions[id] = { x: point.x, y: point.y };

                if (!trails[id]) trails[id] = [];
                trails[id].push([point.x, point.y]);
            }

            // Draw trails
            for (const [id, trail] of Object.entries(trails)) {
                if (trail.length < 2) continue;

                const hue = stringToHue(id);
                ctx.beginPath();
                ctx.strokeStyle = `hsl(${hue}, 100%, 50%)`;
                ctx.globalAlpha = 0.4;
                ctx.lineWidth = 2;

                ctx.moveTo(trail[0][0] * scale + scale/2, (gridSize - 1 - trail[0][1]) * scale + scale/2);
                for (let i = 1; i < trail.length; i++) {
                    ctx.lineTo(trail[i][0] * scale + scale/2, (gridSize - 1 - trail[i][1]) * scale + scale/2);
                }
                ctx.stroke();
                ctx.globalAlpha = 1.0;
            }

            // Draw drones at current positions
            drawDrones(currentArchive.drones, positions);

            // Update timeline and timestamp
            const pct = (index / flightData.length) * 100;
            document.getElementById('timeline-progress').style.width = pct + '%';

            const point = flightData[index];
            if (point) {
                const date = new Date(point.timestamp * 1000);
                document.getElementById('timestamp').innerText = date.toLocaleTimeString() + ` (${index}/${flightData.length})`;
            }
        }

        // Initialize
        loadArchives();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/data')
def data():
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/data", timeout=2)
            return resp.json()
        except Exception as e:
            print(f"Queen API Proxy Error: {e}")
            return {"grid": [], "drones": {}, "mood": "DISCONNECTED"}

    # Local mode: read directly from file
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "hive_state.json")
        with open(json_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Dashboard Read Error: {e}")
        return {"grid": [], "drones": {}}

@app.route('/history_data')
def history_data():
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            window = request.args.get('window', 60)
            resp = requests.get(f"{QUEEN_API_URL}/history_data?window={window}", timeout=5)
            return resp.json()
        except Exception as e:
            print(f"Queen API History Proxy Error: {e}")
            return {}

    # Local mode: read directly from files
    try:
        window = int(request.args.get('window', 60))
        now = time.time()
        cutoff = now - window

        # Find latest log file
        list_of_files = glob.glob('flight_logs/*.csv')
        if not list_of_files:
            return {}

        latest_file = max(list_of_files, key=os.path.getctime)

        history = {} # {id: [[x,y], [x,y]]}

        with open(latest_file, 'r') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            for row in reader:
                if not row: continue
                # format: timestamp, drone_id, x, y, intensity, rssi
                try:
                    ts = float(row[0])
                    if ts > cutoff:
                        did = row[1]
                        x = int(row[2])
                        y = int(row[3])

                        if did not in history:
                            history[did] = []
                        history[did].append([x,y])
                except ValueError:
                    continue

        return history
    except Exception as e:
        print(f"History Error: {e}")
        return {}

@app.route('/set_mode')
def set_mode():
    mode = request.args.get('mode', 'RANDOM')
    client.publish("hive/control/mode", mode)
    return "OK"

@app.route('/set_virtual_swarm')
def set_virtual_swarm():
    count = request.args.get('count', '0')
    client.publish("hive/control/virtual_swarm", count)
    return "OK"

@app.route('/reset_hive')
def reset_hive():
    client.publish("hive/control/reset", "1")
    return "OK"

# --- PLAYBACK DASHBOARD ROUTES ---

@app.route('/playback')
def playback():
    return render_template_string(PLAYBACK_TEMPLATE)

@app.route('/api/archives')
def list_archives():
    """List archived JSON snapshots from snapshots/ directory"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/archives", timeout=5)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Archives Proxy Error: {e}")
            return jsonify([])

    # Local mode
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        snapshots_dir = os.path.join(base_dir, "snapshots")

        if not os.path.exists(snapshots_dir):
            return jsonify([])

        archives = []
        # Pattern: hive_state_ARCHIVE_YYYY-MM-DD_HHMMSS.json
        pattern = re.compile(r'^hive_state_ARCHIVE_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.json$')

        for filename in os.listdir(snapshots_dir):
            match = pattern.match(filename)
            if match:
                # Parse timestamp from groups: year, month, day, time
                try:
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    time_str = match.group(4)
                    hour = int(time_str[0:2])
                    minute = int(time_str[2:4])
                    second = int(time_str[4:6])

                    import datetime
                    dt = datetime.datetime(year, month, day, hour, minute, second)
                    timestamp = dt.timestamp()
                    display_time = dt.strftime("%Y-%m-%d %H:%M:%S")

                    archives.append({
                        'filename': filename,
                        'timestamp': timestamp,
                        'display_time': display_time
                    })
                except (ValueError, IndexError):
                    continue

        # Sort by timestamp, newest first
        archives.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify(archives)

    except Exception as e:
        print(f"Archive List Error: {e}")
        return jsonify([])

@app.route('/api/archive/<filename>')
def get_archive(filename):
    """Return contents of a specific archive file"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/archive/{filename}", timeout=10)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Archive Proxy Error: {e}")
            return jsonify({'error': str(e)}), 500

    # Local mode
    try:
        # Security: Validate filename pattern to prevent path traversal
        pattern = re.compile(r'^hive_state_ARCHIVE_\d{4}-\d{2}-\d{2}_\d{6}\.json$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "snapshots", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(base_dir, "snapshots"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Archive not found'}), 404

        with open(file_path, 'r') as f:
            return json.load(f)

    except Exception as e:
        print(f"Archive Read Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/flight_logs')
def list_flight_logs():
    """List available flight log CSV files"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/flight_logs", timeout=5)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Flight Logs Proxy Error: {e}")
            return jsonify([])

    # Local mode
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logs_dir = os.path.join(base_dir, "flight_logs")

        if not os.path.exists(logs_dir):
            return jsonify([])

        logs = []
        # Pattern: session_YYYY-MM-DD_HHMMSS.csv
        pattern = re.compile(r'^session_(\d{4})-(\d{2})-(\d{2})_(\d{6})\.csv$')

        for filename in os.listdir(logs_dir):
            match = pattern.match(filename)
            if match:
                try:
                    import datetime
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    time_str = match.group(4)
                    hour = int(time_str[0:2])
                    minute = int(time_str[2:4])
                    second = int(time_str[4:6])

                    dt = datetime.datetime(year, month, day, hour, minute, second)
                    start_time = dt.timestamp()

                    # Get end time from file (last entry timestamp)
                    file_path = os.path.join(logs_dir, filename)
                    end_time = 0

                    with open(file_path, 'r') as f:
                        reader = csv.reader(f)
                        next(reader, None)  # Skip header
                        for row in reader:
                            if row:
                                try:
                                    end_time = float(row[0])
                                except:
                                    pass

                    logs.append({
                        'filename': filename,
                        'start_time': start_time,
                        'end_time': end_time
                    })
                except (ValueError, IndexError):
                    continue

        # Sort by start time, newest first
        logs.sort(key=lambda x: x['start_time'], reverse=True)
        return jsonify(logs)

    except Exception as e:
        print(f"Flight Log List Error: {e}")
        return jsonify([])

@app.route('/api/flight_log/<filename>')
def get_flight_log(filename):
    """Return contents of a specific flight log as JSON array"""
    # In remote mode, proxy from Queen API
    if IS_REMOTE_MODE:
        try:
            resp = requests.get(f"{QUEEN_API_URL}/api/flight_log/{filename}", timeout=30)
            return jsonify(resp.json())
        except Exception as e:
            print(f"Queen API Flight Log Proxy Error: {e}")
            return jsonify({'error': str(e)}), 500

    # Local mode
    try:
        # Security: Validate filename pattern
        pattern = re.compile(r'^session_\d{4}-\d{2}-\d{2}_\d{6}\.csv$')
        if not pattern.match(filename):
            return jsonify({'error': 'Invalid filename'}), 400

        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, "flight_logs", filename)

        # Additional security check
        if not os.path.abspath(file_path).startswith(os.path.abspath(os.path.join(base_dir, "flight_logs"))):
            return jsonify({'error': 'Invalid path'}), 400

        if not os.path.exists(file_path):
            return jsonify({'error': 'Flight log not found'}), 404

        data = []
        with open(file_path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if row and len(row) >= 4:
                    try:
                        data.append({
                            'timestamp': float(row[0]),
                            'drone_id': row[1],
                            'x': int(row[2]),
                            'y': int(row[3]),
                            'intensity': int(row[4]) if len(row) > 4 else 0,
                            'rssi': int(row[5]) if len(row) > 5 else 0
                        })
                    except (ValueError, IndexError):
                        continue

        return jsonify(data)

    except Exception as e:
        print(f"Flight Log Read Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Print mode information
    if IS_REMOTE_MODE:
        print("/// DASHBOARD RUNNING IN REMOTE MODE ///")
        print(f"/// Queen API: {QUEEN_API_URL} ///")
        print(f"/// MQTT Broker: {MQTT_BROKER} ///")
    else:
        print("/// DASHBOARD RUNNING IN LOCAL MODE ///")

    # Start Camera Eye (only in local mode)
    if CAMERA_ENABLED:
        t = threading.Thread(target=camera_loop)
        t.daemon = True
        t.start()

    print(f"/// DASHBOARD SERVER STARTING ON PORT {DASHBOARD_PORT} ///")
    try:
        app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=False, threaded=True)
    except Exception as e:
        print(f"Flask Error: {e}")
    


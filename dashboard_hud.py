from flask import Flask, render_template_string, Response, request
import json
import time
import io
import subprocess
import paho.mqtt.client as mqtt
from PIL import Image
import glob
import csv
import glob
import csv
import os  # The new eye
import threading

app = Flask(__name__)

# --- CONFIGURATION ---
MQTT_BROKER = "localhost"
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
except:
    print("Warning: Brain not found (MQTT Disconnected)")

# --- CAMERA SYSTEM ---
latest_frame = None

def get_camera_command():
    return [
        "rpicam-still", "--width", "320", "--height", "240", # Lower res for speed
        "--encoding", "jpg", "--output", "-", "--timeout", "1", "--nopreview"
    ]

def camera_loop():
    global latest_frame
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
        .container { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; height: 90vh; }
        .panel { border: 1px solid #333; background: #050505; position: relative; }
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
        <span style="float:right; font-size: 14px; margin-left: 20px;">
            <button onclick="resetHive()" style="color:#f44; border:1px solid #f44; background:#000; cursor:pointer; font-weight:bold;">RESET HIVE</button>
        </span>
        <span id="sun-status" style="float:right; font-size: 14px; color: #888;">SUN: SYNCING...</span>
    </h2>
    <div class="container">
        <div class="panel">
            <div class="panel-header">Optical Sensor (Live Analysis)</div>
            <img class="feed" src="/video_feed">
            <div class="panel-header" style="border-top: 1px solid #333; margin-top: 0;">Drone Registry</div>
            <div id="drone-registry" style="padding: 10px; font-size: 12px; height: 150px; overflow-y: auto;"></div>
        </div>
        <div class="panel">
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
        const gridSize = 50;
        const scale = 800 / gridSize; 

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
        
        async function resetHive() {
            if (confirm("WARNING: This will wipe all hive memory and learned trails. Proceed?")) {
                await fetch('/reset_hive');
            }
        }

        async function fetchHistory(window) {
             try {
                const res = await fetch(`/history_data?window=${window}`);
                const history = await res.json();
                drawHistoryTrails(history);
            } catch(e) {}
        }
        
        function drawHistoryTrails(history) {
            // Draw long trails
            for (const [id, points] of Object.entries(history)) {
                if (points.length < 2) continue;
                
                ctx.beginPath();
                ctx.strokeStyle = '#0f0'; // Default history color
                ctx.globalAlpha = 0.3;
                ctx.lineWidth = 1;
                
                ctx.moveTo(points[0][0] * scale + scale/2, (gridSize - 1 - points[0][1]) * scale + scale/2);
                for (let i = 1; i < points.length; i++) {
                     ctx.lineTo(points[i][0] * scale + scale/2, (gridSize - 1 - points[i][1]) * scale + scale/2);
                }
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

        function drawDrones(drones, historyMode=false) {
            overlays.innerHTML = ''; 
            const now = Date.now() / 1000;
            let activeCount = 0;
            
            for (const [id, drone] of Object.entries(drones)) {
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
                ctx.fill(); # Solid dot for visibility
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
            
            droneCounter.innerText = activeCount;
            droneCounter.style.color = activeCount > 0 ? '#0f0' : '#f00';
            updateDroneList(drones);
        }

        function updateDroneList(drones) {
            const list = document.getElementById('drone-registry');
            list.innerHTML = '';
            const now = Date.now() / 1000;
            
            // Sort by ID for stability
            const sortedIds = Object.keys(drones).sort();
            
            for (const id of sortedIds) {
                const drone = drones[id];
                const diff = now - drone.last_seen;
                let color = '#f00'; // > 30s
                
                if (diff < 10) color = '#0f0'; // < 10s
                else if (diff <= 30) color = '#ff0'; // 10-30s
                
                const item = document.createElement('div');
                item.style.marginBottom = '4px';
                // item.style.color = color; // Use the unique color!
                const hue = stringToHue(id);
                item.style.color = `hsl(${hue}, 100%, 60%)`;
                
                item.innerText = `> [${id}] RSSI:${drone.rssi}dB (${Math.round(diff)}s ago)`;
                list.appendChild(item);
            }
        }
        setInterval(fetchState, 100);
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
    try:
        with open("hive_state.json", "r") as f:
            return json.load(f)
    except Exception as e:
        # print(f"Dashboard Read Error: {e}") # Uncomment if needed
        return {"grid": [], "drones": {}}

@app.route('/history_data')
def history_data():
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

if __name__ == '__main__':
    # Start Camera Eye
    t = threading.Thread(target=camera_loop)
    t.daemon = True
    t.start()
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
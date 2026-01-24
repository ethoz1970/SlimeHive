from flask import Flask, render_template_string, Response
import json
import time
import io
import subprocess
import paho.mqtt.client as mqtt
from PIL import Image  # The new eye

app = Flask(__name__)

# --- CONFIGURATION ---
MQTT_BROKER = "localhost"
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
try:
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
except:
    print("Warning: Brain not found (MQTT Disconnected)")

def get_camera_command():
    return [
        "rpicam-still", "--width", "320", "--height", "240", # Lower res for speed
        "--encoding", "jpg", "--output", "-", "--timeout", "1", "--nopreview"
    ]

def gen_frames():
    while True:
        try:
            # 1. Capture Frame
            result = subprocess.run(get_camera_command(), capture_output=True)
            
            if result.stdout:
                img_data = result.stdout
                
                # --- OPTICAL CORTEX ANALYSIS ---
                # Check brightness without melting the CPU
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

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + img_data + b'\r\n')
            
            time.sleep(0.1) # Observation frequency
            
        except Exception as e:
            time.sleep(1)

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
    <h2>/// HIVE MIND: RESEARCH TERMINAL ///</h2>
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
                <canvas id="hiveMap" width="500" height="500"></canvas>
                <div id="overlays"></div>
            </div>
        </div>
    </div>
    <script>
        const canvas = document.getElementById('hiveMap');
        const ctx = canvas.getContext('2d');
        const overlays = document.getElementById('overlays');
        const droneCounter = document.getElementById('drone-counter');
        const gridSize = 50;
        const scale = 500 / gridSize; 

        function getColor(value) {
            if (value < 5) return `rgb(0,0,0)`;
            if (value < 50) return `rgb(${value*5}, 0, 0)`; 
            if (value < 150) return `rgb(255, ${value}, 0)`; 
            return `rgb(255, 255, ${Math.min(255, value-100)})`;
        }

        async function fetchState() {
            try {
                const response = await fetch('/data');
                const data = await response.json();
                drawMap(data.grid);
                drawDrones(data.drones);
            } catch (e) { }
        }

        function drawMap(grid) {
            for (let x = 0; x < gridSize; x++) {
                for (let y = 0; y < gridSize; y++) {
                    ctx.fillStyle = getColor(grid[x][y]);
                    ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
                }
            }
        }

        function drawDrones(drones) {
            overlays.innerHTML = ''; 
            const now = Date.now() / 1000;
            let activeCount = 0;
            
            for (const [id, drone] of Object.entries(drones)) {
                if (now - drone.last_seen > 10) continue;
                
                activeCount++;
                const el = document.createElement('div');
                el.className = 'drone-label';
                el.style.left = (drone.x * scale + 10) + 'px';
                el.style.top = ((gridSize - 1 - drone.y) * scale - 10) + 'px';
                el.innerHTML = `[${id}]<br><span style="color:#888">${drone.rssi}dB</span>`;
                overlays.appendChild(el);
                
                ctx.strokeStyle = '#0f0';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.arc(drone.x * scale + scale/2, (gridSize - 1 - drone.y) * scale + scale/2, 5, 0, 2 * Math.PI);
                ctx.stroke();
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
                item.style.color = color;
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
    except:
        return {"grid": [], "drones": {}}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
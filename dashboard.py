from flask import Flask, render_template_string
import json
import time

app = Flask(__name__)

# HTML Template with Auto-Refresh JS and Canvas Rendering
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>HIVE COMMAND</title>
    <style>
        body { background-color: #000; color: #0f0; font-family: monospace; text-align: center; }
        #map-container { position: relative; display: inline-block; margin-top: 20px; }
        canvas { border: 2px solid #333; box-shadow: 0 0 20px #111; }
        .drone-label { 
            position: absolute; color: white; font-weight: bold; font-size: 12px; 
            text-shadow: 0 0 4px #000; pointer-events: none;
        }
        #stats { margin-top: 10px; color: #666; }
    </style>
</head>
<body>
    <h2>/// HIVE MIND VISUALIZER ///</h2>
    <div id="map-container">
        <canvas id="hiveMap" width="600" height="600"></canvas>
        <div id="overlays"></div>
    </div>
    <div id="stats">Active Nodes: <span id="node-count">0</span></div>

    <script>
        const canvas = document.getElementById('hiveMap');
        const ctx = canvas.getContext('2d');
        const overlays = document.getElementById('overlays');
        const gridSize = 50;
        const scale = canvas.width / gridSize;

        function getColor(value) {
            // "Inferno" style heat map (Black -> Red -> Yellow -> White)
            if (value < 5) return `rgb(0,0,0)`;
            if (value < 50) return `rgb(${value*5}, 0, 20)`; // Deep Red
            if (value < 150) return `rgb(255, ${value}, 0)`; // Orange/Yellow
            return `rgb(255, 255, ${Math.min(255, value-100)})`; // White Hot
        }

        async function fetchState() {
            try {
                const response = await fetch('/data');
                const data = await response.json();
                drawMap(data.grid);
                drawDrones(data.drones);
                document.getElementById('node-count').innerText = Object.keys(data.drones).length;
            } catch (e) { console.log("Sync error"); }
        }

        function drawMap(grid) {
            // Draw pixel by pixel (we let CSS smooth it if we wanted, but explicit is better)
            for (let x = 0; x < gridSize; x++) {
                for (let y = 0; y < gridSize; y++) {
                    ctx.fillStyle = getColor(grid[x][y]);
                    // Flip Y axis to match standard graph
                    ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
                }
            }
        }

        function drawDrones(drones) {
            overlays.innerHTML = ''; // Clear old labels
            const now = Date.now() / 1000;

            for (const [id, drone] of Object.entries(drones)) {
                // Ignore drones not seen in 10 seconds
                if (now - drone.last_seen > 10) continue;

                // Create Label
                const el = document.createElement('div');
                el.className = 'drone-label';
                // Flip Y coordinate
                const screenX = drone.x * scale + 10; 
                const screenY = (gridSize - 1 - drone.y) * scale - 10;
                
                el.style.left = screenX + 'px';
                el.style.top = screenY + 'px';
                el.innerHTML = `✛ ${id}<br><span style="font-size:9px;color:#aaa">${drone.rssi}dB</span>`;
                
                overlays.appendChild(el);
                
                // Draw Target Circle on Canvas
                ctx.strokeStyle = '#00FFFF';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(drone.x * scale + scale/2, (gridSize - 1 - drone.y) * scale + scale/2, 6, 0, 2 * Math.PI);
                ctx.stroke();
            }
        }

        // Refresh at 10Hz (Smooth)
        setInterval(fetchState, 100);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/data')
def data():
    try:
        with open("hive_state.json", "r") as f:
            return json.load(f)
    except:
        return {"grid": [], "drones": {}}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
from flask import Flask, jsonify, render_template_string
import json
import os

app = Flask(__name__)

# The HTML Template (embedded for simplicity)
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>SlimeHive Monitor</title>
    <style>
        body { background: #111; color: #0f0; font-family: monospace; text-align: center; }
        #hive-map { border: 2px solid #333; margin-top: 20px; }
        .cell { width: 10px; height: 10px; display: inline-block; }
    </style>
</head>
<body>
    <h1>HIVE MIND STATUS</h1>
    <h2 id="peak-display">Peak Signal: 0</h2>
    <canvas id="hive-map" width="500" height="500"></canvas>

    <script>
        const canvas = document.getElementById('hive-map');
        const ctx = canvas.getContext('2d');
        const scale = 10; // 50x10 = 500px

        function fetchState() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('peak-display').innerText = "Peak Signal: " + data.peak;
                    drawGrid(data.grid);
                });
        }

        function drawGrid(grid) {
            ctx.clearRect(0, 0, 500, 500);
            for (let y = 0; y < 50; y++) {
                for (let x = 0; x < 50; x++) {
                    let val = grid[x][y];
                    if (val > 1) {
                        // Green intensity based on value
                        let brightness = Math.min(255, val * 3); 
                        ctx.fillStyle = `rgb(0, ${brightness}, 0)`;
                        ctx.fillRect(y * scale, x * scale, scale, scale);
                    }
                }
            }
        }

        setInterval(fetchState, 500); // Refresh every 0.5s
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/data')
def get_data():
    try:
        with open("hive_state.json", "r") as f:
            return json.load(f)
    except:
        return jsonify({"grid": [], "peak": 0})

if __name__ == '__main__':
    # Listen on ALL interfaces (0.0.0.0) so MacBook can see it
    app.run(host='0.0.0.0', port=5000)

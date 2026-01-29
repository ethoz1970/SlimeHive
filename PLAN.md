# Plan: Virtual Dashboard Decoupling

## Problem

Currently when running virtual simulations on MacBook:
- `dashboard_hud.py` in remote mode proxies requests to Pi, so snapshots/archives end up on Pi
- `simulate.py` saves recordings locally, but there's no way to create snapshots locally
- No clear separation between "Pi + real drones" and "MacBook pure virtual" workflows

## Solution

Create `dashboard_virtual.py` - a standalone dashboard for pure virtual simulations that:
1. **No MQTT** - No connection to queen_brain
2. **No Camera** - No rpicam dependency
3. **No Remote Proxy** - All data is local
4. **Local Snapshots** - Archive to local `snapshots/` directory
5. **Local Recordings** - Already handled by simulate.py

## Architecture

```
Pi (Physical)                         MacBook (Virtual)
┌─────────────────────┐              ┌─────────────────────┐
│ queen_brain.py      │              │ simulate.py         │
│ dashboard_hud.py    │              │ dashboard_virtual.py│
│ snapshots/          │              │ snapshots/          │
│ recordings/         │              │ recordings/         │
└─────────────────────┘              └─────────────────────┘
     ↑                                    ↑
     │                                    │
  Real drones                      Virtual drones only
  + MQTT                           No MQTT needed
```

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `dashboard_virtual.py` | Create | Standalone virtual simulation dashboard |
| `templates/live_virtual.html` | Create | Template with snapshot button (no camera feed) |

## Implementation Details

### dashboard_virtual.py

Stripped-down version of `dashboard_hud.py`:
- No MQTT client (`paho.mqtt` not imported)
- No camera system (no `rpicam`, no `PIL` for camera)
- No remote mode/proxy (no `QUEEN_IP` handling)
- All file paths are local to script directory
- New `POST /snapshot` endpoint to create local archives

```python
# Key endpoints:
GET  /              → Serve live_virtual.html
GET  /data          → Read local hive_state.json
POST /snapshot      → Create archive in local snapshots/
GET  /api/archives  → List local snapshots/
GET  /api/archive/<file> → Load specific archive
DELETE /api/archive/<file> → Delete archive
POST /config        → Update hive_config_live.json
GET  /config        → Get current config
GET  /playback      → Serve playback.html
```

### New Snapshot Endpoint

```python
@app.route('/snapshot', methods=['POST'])
def create_snapshot():
    """Create archive of current simulation state"""
    try:
        # Read current state
        with open(HISTORY_FILE, 'r') as f:
            state = json.load(f)

        # Create snapshot directory
        snapshots_dir = os.path.join(BASE_DIR, "snapshots")
        os.makedirs(snapshots_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"hive_state_ARCHIVE_{timestamp}.json"
        filepath = os.path.join(snapshots_dir, filename)

        # Save snapshot
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)

        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### live_virtual.html

Based on `live.html` with these changes:
1. Remove camera feed section (or replace with placeholder)
2. Add SNAPSHOT button in control panel
3. Remove MQTT-dependent controls that don't work without queen_brain
4. Keep simulation controls that work via `hive_config_live.json`

```html
<!-- Add to control panel -->
<button onclick="createSnapshot()" class="btn btn-snapshot">SNAPSHOT</button>

<script>
async function createSnapshot() {
    try {
        const res = await fetch('/snapshot', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showNotification('Snapshot saved: ' + data.filename);
        } else {
            showNotification('Error: ' + data.error, 'error');
        }
    } catch (e) {
        showNotification('Snapshot failed', 'error');
    }
}
</script>
```

## Workflow

**Virtual Simulation on MacBook:**
```bash
# Terminal 1: Run simulation with recording
python simulate.py --mode BOIDS --drones 50 --duration 60 --record

# Terminal 2: View in dashboard
python dashboard_virtual.py
# Open http://localhost:5050

# Click SNAPSHOT button anytime to save current state locally
# Recording auto-saves to recordings/ when simulation ends
```

**Pi with Real Drones:**
```bash
# On Pi - unchanged workflow
python queen_brain.py
python dashboard_hud.py  # Local mode
```

## Port Configuration

- `dashboard_virtual.py` defaults to port 5050
- Same as remote `dashboard_hud.py` for consistency
- Avoids conflict with macOS AirPlay on port 5000

## Key Differences Summary

| Feature | dashboard_hud.py | dashboard_virtual.py |
|---------|------------------|---------------------|
| MQTT | Yes (queen_brain) | No |
| Camera | Yes (Pi only) | No |
| Remote proxy | Yes (QUEEN_IP) | No |
| Snapshots | On Pi (via MQTT reset) | Local (direct button) |
| Dependencies | paho-mqtt, PIL, requests | Flask only |
| Port | 5000 (Pi) / 5050 (remote) | 5050 |

## Verification

1. Run `python simulate.py --record --drones 20 --duration 30`
2. Run `python dashboard_virtual.py` in another terminal
3. Open http://localhost:5050
4. Verify live view shows simulation
5. Click SNAPSHOT - verify file in local `snapshots/`
6. Go to /playback - verify local archives listed
7. Verify recording saved to local `recordings/` after simulation ends
8. All files should be in MacBook's SlimeHive directory, not Pi

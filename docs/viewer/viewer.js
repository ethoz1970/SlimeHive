// Configuration - UPDATE THESE FOR YOUR REPO
const GITHUB_OWNER = 'ethoz1970';
const GITHUB_REPO = 'SlimeHive';
const RELEASE_TAG = 'recordings';

// State
let recording = null;
let currentTime = 0;
let isPlaying = false;
let playbackSpeed = 1;
let lastFrameTime = 0;
let animationId = null;

// Canvas
const canvas = document.getElementById('hiveMap');
const ctx = canvas.getContext('2d');
const GRID_SIZE = 100;
const CELL_SIZE = canvas.width / GRID_SIZE;

// --- GITHUB INTEGRATION ---

async function loadAvailableRecordings() {
    const listEl = document.getElementById('recording-list');

    try {
        const response = await fetch(
            `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/tags/${RELEASE_TAG}`
        );

        if (!response.ok) {
            listEl.innerHTML = '<div style="color: var(--dim);">No recordings found. Upload with publish_recording.py</div>';
            return;
        }

        const release = await response.json();
        const recordings = (release.assets || [])
            .filter(a => a.name.endsWith('.slimehive'))
            .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

        if (recordings.length === 0) {
            listEl.innerHTML = '<div style="color: var(--dim);">No recordings in release</div>';
            return;
        }

        listEl.innerHTML = recordings.map(r => `
            <div class="recording-item" onclick="loadRecording('${r.url}')">
                <div>${r.name}</div>
                <div style="color: var(--dim); font-size: 0.9em;">${new Date(r.created_at).toLocaleString()}</div>
            </div>
        `).join('');

    } catch (e) {
        listEl.innerHTML = `<div style="color: #ff3333;">Error: ${e.message}</div>`;
    }
}

async function loadRecording(url) {
    document.getElementById('recording-list').innerHTML = '<div>Loading...</div>';

    try {
        console.log('Fetching:', url);

        // Use Accept header for GitHub API URLs to get raw asset
        const isGitHubApi = url.includes('api.github.com');
        const fetchOptions = isGitHubApi
            ? { headers: { 'Accept': 'application/octet-stream' } }
            : {};

        const response = await fetch(url, fetchOptions);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.arrayBuffer();
        console.log('Received bytes:', data.byteLength);

        // Decompress if gzipped
        let jsonStr;
        const bytes = new Uint8Array(data);
        if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
            console.log('Decompressing gzip...');
            jsonStr = pako.inflate(bytes, { to: 'string' });
        } else {
            jsonStr = new TextDecoder().decode(data);
        }

        console.log('Parsing JSON, length:', jsonStr.length);
        recording = JSON.parse(jsonStr);
        console.log('Recording loaded:', recording.metadata);
        initPlayback();

    } catch (e) {
        console.error('Load error:', e);
        alert('Failed to load recording: ' + e.message);
        loadAvailableRecordings();
    }
}

function loadFromUrl() {
    const url = document.getElementById('url-input').value.trim();
    if (url) loadRecording(url);
}

function loadFromFile() {
    const file = document.getElementById('file-input').files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const bytes = new Uint8Array(e.target.result);
            let jsonStr;
            if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
                jsonStr = pako.inflate(bytes, { to: 'string' });
            } else {
                jsonStr = new TextDecoder().decode(bytes);
            }
            recording = JSON.parse(jsonStr);
            initPlayback();
        } catch (e) {
            alert('Failed to parse file: ' + e.message);
        }
    };
    reader.readAsArrayBuffer(file);
}

// --- PLAYBACK ---

function initPlayback() {
    currentTime = 0;
    isPlaying = false;

    // Update metadata
    document.getElementById('meta-mode').textContent = recording.metadata.mode;
    document.getElementById('meta-drones').textContent = recording.metadata.drone_count;
    document.getElementById('meta-duration').textContent = formatTime(recording.metadata.duration_seconds);

    // Show viewer
    document.getElementById('loading-panel').style.display = 'none';
    document.getElementById('viewer-panel').style.display = 'block';

    renderFrame(0);
    updateTimeline();
}

function togglePlay() {
    if (isPlaying) {
        isPlaying = false;
        document.getElementById('play-btn').textContent = 'PLAY';
        cancelAnimationFrame(animationId);
    } else {
        if (currentTime >= recording.metadata.duration_seconds) {
            currentTime = 0;
        }
        isPlaying = true;
        document.getElementById('play-btn').textContent = 'PAUSE';
        lastFrameTime = performance.now();
        animationId = requestAnimationFrame(animate);
    }
}

function setSpeed(speed) {
    playbackSpeed = parseFloat(speed);
}

function seek(event) {
    const rect = event.target.getBoundingClientRect();
    const pct = (event.clientX - rect.left) / rect.width;
    currentTime = pct * recording.metadata.duration_seconds;
    renderFrame(currentTime);
    updateTimeline();
}

function backToList() {
    document.getElementById('loading-panel').style.display = 'block';
    document.getElementById('viewer-panel').style.display = 'none';
    recording = null;
    isPlaying = false;
    loadAvailableRecordings();
}

function animate(timestamp) {
    const delta = (timestamp - lastFrameTime) / 1000 * playbackSpeed;
    lastFrameTime = timestamp;

    currentTime += delta;

    if (currentTime >= recording.metadata.duration_seconds) {
        currentTime = recording.metadata.duration_seconds;
        isPlaying = false;
        document.getElementById('play-btn').textContent = 'PLAY';
    }

    renderFrame(currentTime);
    updateTimeline();

    if (isPlaying) {
        animationId = requestAnimationFrame(animate);
    }
}

function updateTimeline() {
    const pct = (currentTime / recording.metadata.duration_seconds) * 100;
    document.getElementById('timeline-progress').style.width = pct + '%';
    document.getElementById('timestamp').textContent =
        formatTime(currentTime) + ' / ' + formatTime(recording.metadata.duration_seconds);
}

function formatTime(secs) {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return m + ':' + s.toString().padStart(2, '0');
}

// --- INTERPOLATION ---

function getInterpolatedState(time) {
    const keyframes = recording.keyframes;
    if (keyframes.length === 0) return null;

    // Find surrounding keyframes
    let kf1 = keyframes[0];
    let kf2 = keyframes[keyframes.length - 1];

    for (let i = 0; i < keyframes.length - 1; i++) {
        if (keyframes[i].t <= time && keyframes[i + 1].t > time) {
            kf1 = keyframes[i];
            kf2 = keyframes[i + 1];
            break;
        }
    }

    // If at or past last keyframe
    if (time >= kf2.t) {
        return { drones: kf2.drones, food_state: kf2.food_state, metrics: kf2.metrics };
    }

    // Interpolation factor
    const duration = kf2.t - kf1.t;
    const t = duration > 0 ? (time - kf1.t) / duration : 0;

    // Interpolate drone positions
    const drones = {};
    for (const [id, d1] of Object.entries(kf1.drones)) {
        const d2 = kf2.drones[id];
        if (d2) {
            drones[id] = {
                x: d1.x + (d2.x - d1.x) * t,
                y: d1.y + (d2.y - d1.y) * t,
                hunger: d1.hunger,
                state: d1.state,
                type: d1.type,
                trail: d1.trail || []
            };
        }
    }

    return { drones, food_state: kf1.food_state, metrics: kf1.metrics };
}

// --- RENDERING ---

function renderFrame(time) {
    const state = getInterpolatedState(time);
    if (!state) return;

    // Clear
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Ghost grid (fade in based on progress)
    if (recording.final_grids?.ghost_grid) {
        const progress = time / recording.metadata.duration_seconds;
        drawGhostGrid(recording.final_grids.ghost_grid, progress * 0.5);
    }

    // Boundary
    drawBoundary(recording.initial_state.boundary);

    // Food
    drawFood(state.food_state);

    // Queen
    drawQueen(recording.initial_state.queen_pos);

    // Sentinel
    drawSentinel();

    // Death markers (accumulated)
    drawDeathMarkers(time);

    // Draw trails first (behind drones)
    for (const [id, drone] of Object.entries(state.drones)) {
        const trail = drone.trail || [];
        if (trail.length >= 2) {
            const hue = stringToHue(id);
            ctx.strokeStyle = `hsla(${hue}, 70%, 50%, 0.4)`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(trail[0][0] * CELL_SIZE, (GRID_SIZE - trail[0][1]) * CELL_SIZE);
            for (let i = 1; i < trail.length; i++) {
                ctx.lineTo(trail[i][0] * CELL_SIZE, (GRID_SIZE - trail[i][1]) * CELL_SIZE);
            }
            ctx.stroke();
        }
    }

    // Drones
    for (const [id, drone] of Object.entries(state.drones)) {
        const cx = drone.x * CELL_SIZE;
        const cy = (GRID_SIZE - drone.y) * CELL_SIZE;

        if (drone.type === 'hopper') {
            // Cyan triangle for hoppers
            ctx.fillStyle = '#0ff';
            ctx.beginPath();
            ctx.moveTo(cx, cy - 5);
            ctx.lineTo(cx + 4, cy + 3);
            ctx.lineTo(cx - 4, cy + 3);
            ctx.closePath();
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 0.5;
            ctx.stroke();
        } else {
            // Colored circle for workers
            const hue = stringToHue(id);
            const color = `hsl(${hue}, 70%, 50%)`;
            ctx.beginPath();
            ctx.arc(cx, cy, 4, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 0.5;
            ctx.stroke();
        }

        // Carrying indicator - green ring
        if (drone.state === 'carrying') {
            ctx.beginPath();
            ctx.arc(cx, cy, 6, 0, Math.PI * 2);
            ctx.strokeStyle = '#0f0';
            ctx.lineWidth = 2;
            ctx.stroke();
        }
    }

    // Stats overlay
    drawStatsOverlay(state, time);
}

function drawGhostGrid(grid, alpha) {
    for (let x = 0; x < GRID_SIZE; x++) {
        for (let y = 0; y < GRID_SIZE; y++) {
            const val = grid[x][y];
            if (val > 0.1) {
                const intensity = Math.min(val / 50, 1);
                ctx.fillStyle = getHeatColor(intensity, alpha);
                ctx.fillRect(x * CELL_SIZE, (GRID_SIZE - 1 - y) * CELL_SIZE, CELL_SIZE, CELL_SIZE);
            }
        }
    }
}

function getHeatColor(value, alpha) {
    let r, g, b;
    if (value < 0.33) {
        r = Math.floor(255 * (value / 0.33));
        g = 0; b = 0;
    } else if (value < 0.66) {
        r = 255;
        g = Math.floor(200 * ((value - 0.33) / 0.33));
        b = 0;
    } else {
        r = 255;
        g = 200 + Math.floor(55 * ((value - 0.66) / 0.34));
        b = Math.floor(255 * ((value - 0.66) / 0.34));
    }
    return `rgba(${r},${g},${b},${alpha})`;
}

function drawBoundary(boundary) {
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(
        boundary.min_x * CELL_SIZE,
        (GRID_SIZE - boundary.max_y) * CELL_SIZE,
        (boundary.max_x - boundary.min_x) * CELL_SIZE,
        (boundary.max_y - boundary.min_y) * CELL_SIZE
    );
    ctx.setLineDash([]);
}

function drawFood(foodState) {
    for (const food of recording.initial_state.food_sources) {
        const state = foodState.find(f => f.id === food.id) || food;
        const cx = food.x * CELL_SIZE;
        const cy = (GRID_SIZE - food.y) * CELL_SIZE;
        const r = (food.radius || 3) * CELL_SIZE;

        if (state.consumed) {
            ctx.fillStyle = 'rgba(100,100,100,0.5)';
        } else {
            const ratio = state.amount / food.amount;
            ctx.fillStyle = `rgba(${Math.floor(255*(1-ratio))},${Math.floor(255*ratio)},0,0.7)`;
        }

        ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1;
        ctx.strokeRect(cx - r, cy - r, r * 2, r * 2);

        // Food amount text
        if (!state.consumed) {
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 10px monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(Math.floor(state.amount), cx, cy);
        }
    }
}

function drawQueen(pos) {
    const cx = pos[0] * CELL_SIZE;
    const cy = (GRID_SIZE - pos[1]) * CELL_SIZE;
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.moveTo(cx, cy - 8);
    ctx.lineTo(cx + 6, cy);
    ctx.lineTo(cx, cy + 8);
    ctx.lineTo(cx - 6, cy);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#ffd700';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Queen label
    ctx.fillStyle = '#000';
    ctx.font = 'bold 8px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Q', cx, cy);
}

function drawSentinel() {
    const cx = 90 * CELL_SIZE;
    const cy = (GRID_SIZE - 90) * CELL_SIZE;
    ctx.fillStyle = '#00f';
    ctx.beginPath();
    ctx.moveTo(cx, cy - 6);
    ctx.lineTo(cx + 5, cy + 4);
    ctx.lineTo(cx - 5, cy + 4);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#0ff';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Sentinel label
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 8px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('S', cx, cy);
}

function drawDeathMarkers(upToTime) {
    const events = (recording.events || []).filter(e => e.type === 'death' && e.t <= upToTime);
    ctx.strokeStyle = '#f00';
    ctx.lineWidth = 2;
    for (const e of events) {
        const cx = e.x * CELL_SIZE;
        const cy = (GRID_SIZE - e.y) * CELL_SIZE;
        const size = e.drone_type === 'hopper' ? 6 : 4;  // Larger for hoppers
        ctx.beginPath();
        ctx.moveTo(cx - size, cy - size);
        ctx.lineTo(cx + size, cy + size);
        ctx.moveTo(cx + size, cy - size);
        ctx.lineTo(cx - size, cy + size);
        ctx.stroke();
    }
}

function drawStatsOverlay(state, time) {
    const droneCount = Object.keys(state.drones).length;
    const queenFood = state.metrics?.queen_food || 0;
    const text = `t=${time.toFixed(1)}s | ${droneCount} drones | Queen: ${Math.floor(queenFood)}`;

    ctx.fillStyle = 'rgba(255,255,255,0.8)';
    ctx.font = '12px monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(text, 8, 8);
}

function stringToHue(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return Math.abs(hash) % 360;
}

// --- INIT ---
loadAvailableRecordings();

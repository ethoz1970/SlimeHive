/**
 * HIVE PLAYBACK - Playback dashboard logic
 */

// DOM Elements
const canvas = document.getElementById('hiveMap');
const ctx = canvas.getContext('2d');
const overlays = document.getElementById('overlays');

// State
let archives = [];
let currentArchive = null;
let expandedArchives = new Set(); // Track which archives are expanded
let flightData = null;
let simulatedData = null;
let playbackMode = 'simulate';
let hasRecordedData = false;
let isPlaying = false;
let playbackSpeed = 1;
let playbackIndex = 0;
let animationId = null;
let lastFrameTime = 0;

/**
 * Load available archives from server
 */
async function loadArchives() {
    try {
        const res = await fetch('/api/archives');
        archives = await res.json();
        renderArchiveList();
    } catch (e) {
        document.getElementById('archive-list').innerHTML = '<div style="color:#f00;">Error loading archives</div>';
    }
}

/**
 * Toggle archive expand/collapse state
 * @param {number} index - Archive index
 * @param {Event} event - Click event
 */
function toggleArchiveExpand(index, event) {
    event.stopPropagation();
    if (expandedArchives.has(index)) {
        expandedArchives.delete(index);
    } else {
        expandedArchives.clear(); // Close all others first
        expandedArchives.add(index);
    }
    renderArchiveList();
}

/**
 * Render the archive list in sidebar
 */
function renderArchiveList() {
    const list = document.getElementById('archive-list');

    let html = `
        <div class="archive-item live-item" onclick="loadLiveState()" id="archive-live">
            <div class="archive-header">
                <span class="archive-title live-title">> CURRENT LIVE STATE</span>
            </div>
        </div>
    `;

    if (archives.length === 0) {
        html += '<div style="color:#666; padding: 10px;">No archived sessions found.<br><br><span style="color:#888;">Click RESET HIVE on the live dashboard to create archives.</span></div>';
    } else {
        html += archives.map((a, i) => {
            const isExpanded = expandedArchives.has(i);
            const metaLine = `${a.drone_count || 0} drones • ${a.mood || '?'} • decay:${a.decay_rate || '?'} • ${a.sim_mode || '?'}`;
            return `
                <div class="archive-item ${isExpanded ? 'expanded' : ''}" id="archive-${i}">
                    <div class="archive-header">
                        <span class="expand-toggle" onclick="toggleArchiveExpand(${i}, event)">${isExpanded ? '▼' : '▶'}</span>
                        <span class="archive-title" onclick="selectArchive(${i})">${a.display_time}</span>
                    </div>
                    ${isExpanded ? `
                        <div class="archive-details">
                            <div class="archive-metadata">${metaLine}</div>
                            <div class="archive-filename">${a.filename}</div>
                            <button class="delete-btn" onclick="deleteArchive('${a.filename}', event)">DELETE</button>
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    }

    list.innerHTML = html;
}

/**
 * Delete an archive file
 * @param {string} filename - Archive filename to delete
 * @param {Event} event - Click event
 */
async function deleteArchive(filename, event) {
    event.stopPropagation();
    if (!confirm('Delete this archive?')) return;

    try {
        await fetch(`/api/archive/${filename}`, { method: 'DELETE' });
        await loadArchives();
    } catch (e) {
        console.error('Error deleting archive:', e);
    }
}

/**
 * Load current live state
 */
async function loadLiveState() {
    console.log('loadLiveState called');
    document.querySelectorAll('.archive-item').forEach(el => el.classList.remove('selected'));
    document.getElementById('archive-live').classList.add('selected');

    try {
        const res = await fetch('/data');
        currentArchive = await res.json();
        console.log('Loaded currentArchive:', currentArchive);

        // Update metadata
        document.getElementById('meta-mood').innerText = currentArchive.mood || 'UNKNOWN';
        document.getElementById('meta-mood').style.color = currentArchive.mood === 'FRENZY' ? '#ff0' : '#44f';
        document.getElementById('meta-decay').innerText = currentArchive.decay_rate || '-';
        document.getElementById('meta-mode').innerText = currentArchive.sim_mode || '-';
        document.getElementById('meta-drones').innerText = Object.keys(currentArchive.drones || {}).length;
        document.getElementById('meta-time').innerText = 'LIVE (now)';

        renderSnapshot();

        flightData = null;
        hasRecordedData = false;
        document.getElementById('play-btn').disabled = false;
        updatePlaybackUI();

    } catch (e) {
        console.error('Error loading live state:', e);

        currentArchive = {
            grid: Array(gridSize).fill(null).map(() => Array(gridSize).fill(0)),
            ghost_grid: Array(gridSize).fill(null).map(() => Array(gridSize).fill(0)),
            drones: {},
            mood: 'FRENZY'
        };

        document.getElementById('meta-mood').innerText = 'SIMULATED';
        document.getElementById('meta-drones').innerText = '0 (will generate)';
        document.getElementById('meta-time').innerText = 'Empty Hive';

        renderSnapshot();
        flightData = null;
        hasRecordedData = false;
        document.getElementById('play-btn').disabled = false;
        updatePlaybackUI();
    }
}

/**
 * Select and load an archive
 * @param {number} index - Archive index
 */
async function selectArchive(index) {
    document.querySelectorAll('.archive-item').forEach(el => el.classList.remove('selected'));
    document.getElementById(`archive-${index}`).classList.add('selected');

    const archive = archives[index];

    try {
        const res = await fetch(`/api/archive/${archive.filename}`);
        currentArchive = await res.json();

        document.getElementById('meta-mood').innerText = currentArchive.mood || 'UNKNOWN';
        document.getElementById('meta-mood').style.color = currentArchive.mood === 'FRENZY' ? '#ff0' : '#44f';
        document.getElementById('meta-decay').innerText = currentArchive.decay_rate || '-';
        document.getElementById('meta-mode').innerText = currentArchive.mode || '-';
        document.getElementById('meta-drones').innerText = Object.keys(currentArchive.drones || {}).length;
        document.getElementById('meta-time').innerText = archive.display_time;

        renderSnapshot();
        await checkFlightLog(archive.timestamp);

    } catch (e) {
        console.error('Error loading archive:', e);
    }
}

/**
 * Generate simulated movement data
 * @param {Object} drones - Drone positions from archive
 * @param {number} frameCount - Number of frames to generate
 * @returns {Array} Simulated data points
 */
function generateSimulatedData(drones, frameCount = 300) {
    const data = [];
    const positions = {};

    for (const [id, drone] of Object.entries(drones || {})) {
        positions[id] = { x: drone.x, y: drone.y };
    }

    if (Object.keys(positions).length === 0) {
        for (let i = 0; i < 3; i++) {
            const id = `SIM-${i}`;
            positions[id] = {
                x: Math.floor(Math.random() * gridSize),
                y: Math.floor(Math.random() * gridSize)
            };
        }
    }

    const baseTime = Date.now() / 1000;

    for (let frame = 0; frame < frameCount; frame++) {
        const timestamp = baseTime + frame * 0.1;

        for (const [id, pos] of Object.entries(positions)) {
            pos.x += Math.floor(Math.random() * 3) - 1;
            pos.y += Math.floor(Math.random() * 3) - 1;
            pos.x = Math.max(0, Math.min(gridSize - 1, pos.x));
            pos.y = Math.max(0, Math.min(gridSize - 1, pos.y));

            data.push({
                timestamp,
                drone_id: id,
                x: pos.x,
                y: pos.y,
                intensity: 50,
                rssi: -50
            });
        }
    }

    return data;
}

/**
 * Set playback mode (simulate/recorded)
 */
function setPlaybackMode() {
    const modeSelect = document.getElementById('mode-select');
    playbackMode = modeSelect.value;
    updatePlaybackUI();
}

/**
 * Update playback UI based on current state
 */
function updatePlaybackUI() {
    const modeSelect = document.getElementById('mode-select');
    const timestampEl = document.getElementById('timestamp');
    const recordedOption = modeSelect.querySelector('option[value="recorded"]');

    if (hasRecordedData) {
        recordedOption.disabled = false;
        if (playbackMode === 'recorded') {
            timestampEl.innerText = `Flight data: ${flightData.length} points`;
        } else {
            timestampEl.innerText = `Simulation ready (${Object.keys(currentArchive?.drones || {}).length} drones)`;
        }
    } else {
        recordedOption.disabled = true;
        modeSelect.value = 'simulate';
        playbackMode = 'simulate';
        timestampEl.innerHTML = '<span class="no-csv">No recorded data - using simulation</span>';
    }
}

/**
 * Check for matching flight log
 * @param {number} timestamp - Archive timestamp
 */
async function checkFlightLog(timestamp) {
    const playBtn = document.getElementById('play-btn');

    try {
        const res = await fetch('/api/flight_logs');
        const logs = await res.json();

        const matchingLog = logs.find(log => {
            return log.start_time <= timestamp && (log.end_time >= timestamp || log.end_time === 0);
        });

        if (matchingLog) {
            const dataRes = await fetch(`/api/flight_log/${matchingLog.filename}`);
            flightData = await dataRes.json();
            hasRecordedData = true;
        } else {
            flightData = null;
            hasRecordedData = false;
        }
    } catch (e) {
        flightData = null;
        hasRecordedData = false;
    }

    playBtn.disabled = false;
    updatePlaybackUI();
}

/**
 * Render static snapshot of archive state
 */
function renderSnapshot() {
    if (!currentArchive) return;

    if (currentArchive.grid && currentArchive.grid.length > 0) {
        updateGridSize(currentArchive.grid.length);
    }

    clearCanvas(ctx, canvas);
    drawMap(ctx, currentArchive.grid, currentArchive.ghost_grid);
    drawBoundary(ctx, currentArchive.boundary, '#8C92AC', 'rgba(0, 255, 0, 0.05)');
    drawQueen(ctx);
    drawSentinel(ctx);
    drawDrones(currentArchive.drones);
}

/**
 * Draw drones at positions
 * @param {Object} drones - Drone data from archive
 * @param {Object} positions - Optional position overrides
 */
function drawDrones(drones, positions = null) {
    overlays.innerHTML = '';

    const allDroneIds = new Set([
        ...Object.keys(drones || {}),
        ...Object.keys(positions || {})
    ]);

    for (const id of allDroneIds) {
        const drone = (drones || {})[id] || {};
        const hue = stringToHue(id);
        const color = `hsl(${hue}, 100%, 50%)`;

        const x = positions && positions[id] ? positions[id].x : (drone.x || 0);
        const y = positions && positions[id] ? positions[id].y : (drone.y || 0);

        const el = document.createElement('div');
        el.className = 'drone-label';
        el.style.left = (x * scale + 10) + 'px';
        el.style.top = ((gridSize - 1 - y) * scale - 10) + 'px';
        el.innerHTML = `[${id}]`;
        el.style.color = color;
        overlays.appendChild(el);

        ctx.fillStyle = color;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(x * scale + scale / 2, (gridSize - 1 - y) * scale + scale / 2, 8, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
    }
}

/**
 * Toggle playback state
 */
function togglePlayback() {
    if (isPlaying) {
        stopPlayback();
    } else {
        startPlayback();
    }
}

/**
 * Start playback
 */
function startPlayback() {
    console.log('startPlayback called');
    console.log('currentArchive:', currentArchive);
    console.log('playbackMode:', playbackMode);

    const badge = document.getElementById('playback-badge');
    const timelineProgress = document.getElementById('timeline-progress');

    let dataToUse;
    if (playbackMode === 'recorded' && hasRecordedData && flightData) {
        dataToUse = flightData;
        badge.innerText = 'RECORDED';
        badge.style.background = '#0a0';
        badge.style.color = '#fff';
        timelineProgress.classList.remove('simulated');
    } else {
        console.log('Generating simulated data for drones:', currentArchive?.drones);
        if (!simulatedData || simulatedData.length === 0) {
            simulatedData = generateSimulatedData(currentArchive?.drones || {});
        }
        console.log('Generated simulatedData length:', simulatedData?.length);
        dataToUse = simulatedData;
        badge.innerText = 'SIMULATED';
        badge.style.background = '#f80';
        badge.style.color = '#000';
        timelineProgress.classList.add('simulated');
    }

    if (!dataToUse || dataToUse.length === 0) {
        console.error('No playback data available');
        return;
    }

    window.activePlaybackData = dataToUse;
    badge.style.display = 'inline';

    isPlaying = true;
    document.getElementById('play-btn').innerText = 'PAUSE';
    playbackIndex = 0;
    lastFrameTime = performance.now();
    animate();
}

/**
 * Stop playback
 */
function stopPlayback() {
    isPlaying = false;
    document.getElementById('play-btn').innerText = 'PLAY SESSION';
    document.getElementById('playback-badge').style.display = 'none';
    document.getElementById('timeline-progress').classList.remove('simulated');
    if (animationId) {
        cancelAnimationFrame(animationId);
        animationId = null;
    }
    simulatedData = null;
    window.activePlaybackData = null;
    renderSnapshot();
}

/**
 * Set playback speed
 */
function setSpeed() {
    playbackSpeed = parseFloat(document.getElementById('speed-select').value);
}

/**
 * Seek to position in timeline
 * @param {MouseEvent} event - Click event
 */
function seekTimeline(event) {
    const data = window.activePlaybackData;
    if (!data || data.length === 0) return;

    const timeline = document.getElementById('timeline');
    const rect = timeline.getBoundingClientRect();
    const pct = (event.clientX - rect.left) / rect.width;
    playbackIndex = Math.floor(pct * data.length);

    if (!isPlaying) {
        renderFrame(playbackIndex);
    }
}

/**
 * Animation loop
 */
function animate() {
    if (!isPlaying) return;

    const data = window.activePlaybackData;
    if (!data) return;

    const now = performance.now();
    const delta = now - lastFrameTime;

    if (delta > (100 / playbackSpeed)) {
        lastFrameTime = now;
        playbackIndex++;

        if (playbackIndex >= data.length) {
            stopPlayback();
            return;
        }

        renderFrame(playbackIndex);
    }

    animationId = requestAnimationFrame(animate);
}

/**
 * Render a single frame
 * @param {number} index - Frame index
 */
function renderFrame(index) {
    const data = window.activePlaybackData;
    if (!data || !currentArchive) return;

    clearCanvas(ctx, canvas);
    drawMap(ctx, currentArchive.grid, currentArchive.ghost_grid);
    drawBoundary(ctx, currentArchive.boundary, '#8C92AC', 'rgba(0, 255, 0, 0.05)');
    drawQueen(ctx);
    drawSentinel(ctx);

    // Build positions and trails
    const positions = {};
    const trails = {};
    const trailLength = 20;
    const startIdx = Math.max(0, index - trailLength);

    for (let i = startIdx; i <= index; i++) {
        const point = data[i];
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

        ctx.moveTo(trail[0][0] * scale + scale / 2, (gridSize - 1 - trail[0][1]) * scale + scale / 2);
        for (let i = 1; i < trail.length; i++) {
            ctx.lineTo(trail[i][0] * scale + scale / 2, (gridSize - 1 - trail[i][1]) * scale + scale / 2);
        }
        ctx.stroke();
        ctx.globalAlpha = 1.0;
    }

    drawDrones(currentArchive.drones, positions);

    // Update timeline
    const pct = (index / data.length) * 100;
    document.getElementById('timeline-progress').style.width = pct + '%';

    const point = data[index];
    if (point) {
        const date = new Date(point.timestamp * 1000);
        document.getElementById('timestamp').innerText = date.toLocaleTimeString() + ` (${index}/${data.length})`;
    }
}

// Initialize
loadArchives();

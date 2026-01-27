/**
 * HIVE LIVE - Live dashboard logic
 */

// DOM Elements
const canvas = document.getElementById('hiveMap');
const ctx = canvas.getContext('2d');
const overlays = document.getElementById('overlays');
const droneCounter = document.getElementById('drone-counter');
const timeFilter = document.getElementById('time-filter');

// State
let tickCounter = 0;
let previousDroneListJson = "";
let lastDroneSort = 0;
let sortedDroneOrder = [];

/**
 * Main polling loop - fetches state and updates display
 */
async function fetchState() {
    try {
        const window = timeFilter.value;

        // Get live data
        const response = await fetch('/data');
        const data = await response.json();

        // Update grid size from actual data
        if (data.grid && data.grid.length > 0) {
            updateGridSize(data.grid.length);
        }

        updateSunStatus(data.mood);

        // Draw the map layers
        drawMap(ctx, data.grid, data.ghost_grid);
        drawBoundary(ctx, data.boundary);
        drawQueen(ctx);
        drawSentinel(ctx);

        if (window === "live") {
            drawDrones(data.drones);
        } else {
            // Fetch and draw history
            fetchHistory(window);
            drawDrones(data.drones, true);
        }

    } catch (e) {
        console.error("Fetch Error:", e);
    }
}

/**
 * Update sun status indicator
 * @param {string} mood - Current hive mood (FRENZY/SLEEP)
 */
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

/**
 * Set simulation mode
 */
async function setMode() {
    const mode = document.getElementById('mode-select').value;
    await fetch(`/set_mode?mode=${mode}`);
}

/**
 * Set virtual swarm count
 */
async function setVirtualSwarm() {
    const count = document.getElementById('v-count').value;
    await fetch(`/set_virtual_swarm?count=${count}`);
}

/**
 * Reset hive (with confirmation)
 */
function resetHive() {
    if (confirm("WARNING: This will wipe all hive memory and learned trails. Proceed?")) {
        fetch('/reset_hive');
        setTimeout(() => location.reload(), 1000);
    }
}

/**
 * Fetch history data for timeline view
 * @param {string} window - Time window in seconds
 */
async function fetchHistory(window) {
    try {
        const res = await fetch(`/history_data?window=${window}`);
        const history = await res.json();
        updateDroneFilter(Object.keys(history));
        drawHistoryTrails(history);
    } catch (e) {
        console.error("History fetch error:", e);
    }
}

/**
 * Update drone filter dropdown
 * @param {string[]} droneIds - List of drone IDs
 */
function updateDroneFilter(droneIds) {
    const select = document.getElementById('drone-filter');
    droneIds.sort();
    const currentJson = JSON.stringify(droneIds);

    // Debounce: only rebuild if content changed
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

/**
 * Draw history trails on the map
 * @param {Object} history - History data {id: [[x,y], ...]}
 */
function drawHistoryTrails(history) {
    const filter = document.getElementById('drone-filter').value;

    for (const [id, points] of Object.entries(history)) {
        if (points.length < 2) continue;
        if (filter !== "ALL" && id !== filter) continue;

        const hue = stringToHue(id);
        const color = `hsl(${hue}, 100%, 50%)`;

        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.globalAlpha = (filter === "ALL") ? 0.3 : 0.8;
        ctx.lineWidth = (filter === "ALL") ? 1 : 2;

        // Draw path
        const startX = points[0][0] * scale + scale / 2;
        const startY = (gridSize - 1 - points[0][1]) * scale + scale / 2;

        ctx.moveTo(startX, startY);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i][0] * scale + scale / 2, (gridSize - 1 - points[i][1]) * scale + scale / 2);
        }
        ctx.stroke();

        // Start marker (circle)
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.arc(startX, startY, 3, 0, 2 * Math.PI);
        ctx.stroke();

        // End marker (X)
        const endX = points[points.length - 1][0] * scale + scale / 2;
        const endY = (gridSize - 1 - points[points.length - 1][1]) * scale + scale / 2;

        ctx.beginPath();
        ctx.moveTo(endX - 3, endY - 3);
        ctx.lineTo(endX + 3, endY + 3);
        ctx.moveTo(endX + 3, endY - 3);
        ctx.lineTo(endX - 3, endY + 3);
        ctx.stroke();

        ctx.globalAlpha = 1.0;
    }
}

/**
 * Draw drones on the map
 * @param {Object} drones - Drone data {id: {x, y, rssi, last_seen, trail}}
 * @param {boolean} historyMode - If true, skip live trails
 */
function drawDrones(drones, historyMode = false) {
    const now = Date.now() / 1000;
    let activeCount = 0;

    const filter = document.getElementById('drone-filter').value;

    for (const [id, drone] of Object.entries(drones)) {
        if (filter !== "ALL" && id !== filter) continue;

        const diff = now - drone.last_seen;

        // Color generation based on status
        const hue = stringToHue(id);
        let lightness = 50;
        let alpha = 1.0;

        if (diff < 10) {
            activeCount++;
        } else if (diff <= 30) {
            lightness = 30;
        } else {
            lightness = 20;
            alpha = 0.5;
        }

        const color = `hsla(${hue}, 100%, ${lightness}%, ${alpha})`;

        // Draw position dot
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(drone.x * scale + scale / 2, (gridSize - 1 - drone.y) * scale + scale / 2, 8, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();

        // Draw live trail (skip in history mode)
        if (!historyMode && drone.trail && drone.trail.length > 1) {
            ctx.beginPath();
            ctx.strokeStyle = color;
            ctx.globalAlpha = 0.4;
            ctx.moveTo(drone.trail[0][0] * scale + scale / 2, (gridSize - 1 - drone.trail[0][1]) * scale + scale / 2);
            for (let i = 1; i < drone.trail.length; i++) {
                ctx.lineTo(drone.trail[i][0] * scale + scale / 2, (gridSize - 1 - drone.trail[i][1]) * scale + scale / 2);
            }
            ctx.stroke();
            ctx.globalAlpha = 1.0;
        }
    }

    // Update counter
    if (activeCount !== parseInt(droneCounter.innerText)) {
        droneCounter.innerText = activeCount;
        droneCounter.style.color = activeCount > 0 ? '#8C92AC' : '#f00';
    }

    // Throttled updates
    tickCounter++;
    if (tickCounter % 10 === 0) {
        updateDroneList(drones);
    }
    if (tickCounter % 50 === 0) {
        updateDroneFilter(Object.keys(drones));
    }
}

/**
 * Update drone registry list
 * Resorts every 30 seconds, moving inactive drones (no signal in 30s) to bottom
 * @param {Object} drones - Drone data
 */
function updateDroneList(drones) {
    const list = document.getElementById('drone-registry');
    list.innerHTML = '';
    const now = Date.now() / 1000;
    const droneIds = Object.keys(drones);

    // Re-sort every 30 seconds
    if (now - lastDroneSort >= 30) {
        lastDroneSort = now;

        // Sort: active drones first (seen in last 30s), then inactive
        // Within each group, sort alphabetically
        sortedDroneOrder = droneIds.sort((a, b) => {
            const diffA = now - drones[a].last_seen;
            const diffB = now - drones[b].last_seen;
            const activeA = diffA <= 30;
            const activeB = diffB <= 30;

            // Active drones come first
            if (activeA && !activeB) return -1;
            if (!activeA && activeB) return 1;

            // Within same activity status, sort alphabetically
            return a.localeCompare(b);
        });
    } else {
        // Add any new drones that aren't in the sorted order yet
        for (const id of droneIds) {
            if (!sortedDroneOrder.includes(id)) {
                sortedDroneOrder.push(id);
            }
        }
        // Remove drones that no longer exist
        sortedDroneOrder = sortedDroneOrder.filter(id => droneIds.includes(id));
    }

    for (const id of sortedDroneOrder) {
        const drone = drones[id];
        if (!drone) continue;

        const diff = now - drone.last_seen;
        const item = document.createElement('div');
        item.style.marginBottom = '4px';
        const hue = stringToHue(id);

        // Dim inactive drones
        const isActive = diff <= 30;
        const lightness = isActive ? 60 : 35;
        item.style.color = `hsl(${hue}, 100%, ${lightness}%)`;
        item.innerText = `> [${id}] RSSI:${drone.rssi}dB (${Math.round(diff)}s ago)`;
        list.appendChild(item);
    }
}

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

// Start polling
setInterval(fetchState, 100);

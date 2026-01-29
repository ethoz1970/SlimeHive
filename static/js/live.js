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
let vizMode = 'fuzzy';  // Visualization mode: fuzzy, hard, ghost, heat
let configUpdateLock = false;  // Prevents config inputs from being overwritten after apply

/**
 * Set visualization mode
 */
function setVizMode() {
    vizMode = document.getElementById('viz-mode').value;
}

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

        // Clear canvas before drawing
        clearCanvas(ctx, canvas);

        // Draw the map layers
        drawMap(ctx, data.grid, data.ghost_grid);
        drawBoundary(ctx, data.boundary);
        drawFood(ctx, data.food_sources);
        drawDeathMarkers(ctx, data.death_markers);
        drawFoodMarkers(ctx, data.food_markers);
        drawSmellMarkers(ctx, data.smell_markers);
        drawQueen(ctx);
        drawSentinel(ctx);

        if (window === "live") {
            drawDrones(data.drones, false, data.dead_drones);
        } else {
            // Fetch and draw history
            fetchHistory(window);
            drawDrones(data.drones, true, data.dead_drones);
        }

        // Update parameters panel
        updateParametersPanel(data);

    } catch (e) {
        console.error("Fetch Error:", e);
    }
}

/**
 * Update parameters panel with simulation data
 * @param {Object} data - State data from server
 */
function updateParametersPanel(data) {
    // Mode
    const modeEl = document.getElementById('param-mode');
    if (modeEl) modeEl.innerText = data.sim_mode || data.mood || '--';

    // Drone count
    const dronesEl = document.getElementById('param-drones');
    if (dronesEl) dronesEl.innerText = data.drones ? Object.keys(data.drones).length : '--';

    // Grid size
    const gridEl = document.getElementById('param-grid');
    if (gridEl && data.grid) gridEl.innerText = `${data.grid.length}x${data.grid.length}`;

    // Queen food (for FEED_QUEEN mode)
    const queenFoodEl = document.getElementById('param-queen-food');
    if (queenFoodEl) {
        if (data.queen && data.queen.food !== undefined) {
            queenFoodEl.innerText = data.queen.food.toFixed(1);
            queenFoodEl.style.color = '#0f0';
        } else {
            queenFoodEl.innerText = '--';
            queenFoodEl.style.color = '#0af';
        }
    }

    // Trips completed
    const tripsEl = document.getElementById('param-trips');
    if (tripsEl) {
        if (data.queen && data.queen.trips !== undefined) {
            tripsEl.innerText = data.queen.trips;
        } else {
            tripsEl.innerText = '--';
        }
    }

    // Food sources
    const foodEl = document.getElementById('param-food-sources');
    if (foodEl) {
        if (data.food_sources && data.food_sources.length > 0) {
            const active = data.food_sources.filter(f => !f.consumed).length;
            foodEl.innerText = `${active}/${data.food_sources.length}`;
            foodEl.style.color = active > 0 ? '#0f0' : '#f00';
        } else {
            foodEl.innerText = '--';
            foodEl.style.color = '#0af';
        }
    }

    // Update config inputs from server state (only if not focused)
    if (data.live_config) {
        const cfg = data.live_config;
        updateConfigInput('cfg-decay-rate', cfg.decay_rate);
        updateConfigInput('cfg-deposit-amount', cfg.deposit_amount);
        updateConfigInput('cfg-ghost-deposit', cfg.ghost_deposit);
        updateConfigInput('cfg-detection-radius', cfg.detection_radius);
        updateConfigInput('cfg-pheromone-boost', cfg.pheromone_boost);
        updateConfigInput('cfg-death-mode', cfg.death_mode);
    }
}

/**
 * Check if any config input is currently focused
 */
function isEditingConfig() {
    const configInputs = [
        'cfg-decay-rate',
        'cfg-deposit-amount',
        'cfg-ghost-deposit',
        'cfg-detection-radius',
        'cfg-pheromone-boost',
        'cfg-death-mode'
    ];
    const activeId = document.activeElement ? document.activeElement.id : null;
    return configInputs.includes(activeId);
}

/**
 * Update config input if not editing any config and not locked
 */
function updateConfigInput(id, value) {
    const el = document.getElementById(id);
    if (el && value !== undefined && !configUpdateLock && !isEditingConfig()) {
        el.value = value;
    }
}

/**
 * Apply configuration changes to simulation
 */
async function applyConfig() {
    // Lock IMMEDIATELY to prevent race conditions
    configUpdateLock = true;

    // Now safely read the values
    const config = {
        decay_rate: parseFloat(document.getElementById('cfg-decay-rate').value),
        deposit_amount: parseFloat(document.getElementById('cfg-deposit-amount').value),
        ghost_deposit: parseFloat(document.getElementById('cfg-ghost-deposit').value),
        detection_radius: parseInt(document.getElementById('cfg-detection-radius').value),
        pheromone_boost: parseFloat(document.getElementById('cfg-pheromone-boost').value),
        death_mode: document.getElementById('cfg-death-mode').value
    };

    try {
        const response = await fetch('/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (response.ok) {
            // Flash the button green to confirm
            const btn = document.getElementById('apply-config-btn');
            btn.style.background = '#0f0';
            btn.style.color = '#000';
            btn.innerText = 'APPLIED!';
            setTimeout(() => {
                btn.style.background = '#020';
                btn.style.color = '#0f0';
                btn.innerText = 'APPLY';
            }, 1000);

            // Unlock after simulation has had time to pick up the new config
            setTimeout(() => {
                configUpdateLock = false;
            }, 1000);
        } else {
            configUpdateLock = false;
        }
    } catch (e) {
        console.error('Config apply error:', e);
        configUpdateLock = false;
    }
}

/**
 * Reset configuration to defaults
 */
async function resetConfig() {
    const defaults = {
        decay_rate: 0.95,
        deposit_amount: 5.0,
        ghost_deposit: 0.5,
        detection_radius: 20,
        pheromone_boost: 3.0,
        death_mode: 'no'
    };

    // Update input fields
    document.getElementById('cfg-decay-rate').value = defaults.decay_rate;
    document.getElementById('cfg-deposit-amount').value = defaults.deposit_amount;
    document.getElementById('cfg-ghost-deposit').value = defaults.ghost_deposit;
    document.getElementById('cfg-detection-radius').value = defaults.detection_radius;
    document.getElementById('cfg-pheromone-boost').value = defaults.pheromone_boost;
    document.getElementById('cfg-death-mode').value = defaults.death_mode;

    try {
        const response = await fetch('/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(defaults)
        });

        if (response.ok) {
            // Flash the button to confirm
            const btn = document.getElementById('reset-config-btn');
            btn.style.background = '#f80';
            btn.style.color = '#000';
            btn.innerText = 'OK';
            setTimeout(() => {
                btn.style.background = '#200';
                btn.style.color = '#f80';
                btn.innerText = 'RST';
            }, 1000);
        }
    } catch (e) {
        console.error('Config reset error:', e);
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
 * @param {Object} deadDrones - Dead drone data for registry display
 */
function drawDrones(drones, historyMode = false, deadDrones = {}) {
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
        const canvasX = drone.x * scale + scale / 2;
        const canvasY = (gridSize - 1 - drone.y) * scale + scale / 2;

        // Get trail for visualization modes that need it
        const trail = drone.trail || [[drone.x, drone.y]];

        // Check if this is a hopper
        const isHopper = drone.type === "hopper";

        // Draw based on drone type and visualization mode
        if (isHopper) {
            // Hoppers are always cyan triangles
            drawHopper(ctx, canvasX, canvasY, 10, alpha);

            // Draw hopper jump trail (dotted line)
            if (trail.length > 1) {
                ctx.beginPath();
                ctx.strokeStyle = 'rgba(0, 255, 255, 0.5)';
                ctx.setLineDash([3, 3]);
                ctx.lineWidth = 2;
                ctx.moveTo(trail[0][0] * scale + scale / 2, (gridSize - 1 - trail[0][1]) * scale + scale / 2);
                for (let i = 1; i < trail.length; i++) {
                    ctx.lineTo(trail[i][0] * scale + scale / 2, (gridSize - 1 - trail[i][1]) * scale + scale / 2);
                }
                ctx.stroke();
                ctx.setLineDash([]);
            }
        } else {
            // Regular drones - draw based on visualization mode
            switch (vizMode) {
                case 'fuzzy':
                    drawFuzzyDrone(ctx, canvasX, canvasY, color, 12, 4);
                    break;
                case 'hard':
                    drawHardDrone(ctx, canvasX, canvasY, color, 8);
                    break;
                case 'ghost':
                    drawGhostDrone(ctx, trail, hue);
                    break;
                case 'heat':
                    drawHeatTrail(ctx, trail, hue);
                    break;
                default:
                    drawFuzzyDrone(ctx, canvasX, canvasY, color, 12, 4);
            }
        }

        // Draw carrying indicator (green glow) for FEED_QUEEN mode (skip for heat mode)
        if (vizMode !== 'heat' && drone.state === "carrying" && drone.carrying > 0) {
            // Bright green outer ring
            ctx.beginPath();
            ctx.arc(canvasX, canvasY, 8, 0, 2 * Math.PI);
            ctx.strokeStyle = 'rgba(0, 255, 100, 0.9)';
            ctx.lineWidth = 3;
            ctx.stroke();

            // Small green square in center (the food)
            ctx.fillStyle = 'rgba(0, 255, 100, 0.8)';
            ctx.fillRect(canvasX - 3, canvasY - 3, 6, 6);
        }

        // Draw live trail for fuzzy and hard modes (skip in history mode)
        if (!historyMode && (vizMode === 'fuzzy' || vizMode === 'hard') && drone.trail && drone.trail.length > 1) {
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
        updateDroneList(drones, deadDrones);
    }
    if (tickCounter % 50 === 0) {
        updateDroneFilter(Object.keys(drones));
    }
}

/**
 * Update drone registry list
 * Resorts every 30 seconds, moving inactive drones (no signal in 30s) to bottom
 * Dead drones appear at the very bottom in red
 * @param {Object} drones - Drone data
 * @param {Object} deadDrones - Dead drone data
 */
function updateDroneList(drones, deadDrones = {}) {
    const list = document.getElementById('drone-registry');
    list.innerHTML = '';
    const now = Date.now() / 1000;
    const droneIds = Object.keys(drones);
    const deadIds = Object.keys(deadDrones || {});

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
        // Remove drones that no longer exist (but not dead ones)
        sortedDroneOrder = sortedDroneOrder.filter(id => droneIds.includes(id));
    }

    // Display live drones
    for (const id of sortedDroneOrder) {
        const drone = drones[id];
        if (!drone) continue;

        const diff = now - drone.last_seen;
        const item = document.createElement('div');
        item.style.marginBottom = '4px';
        const hue = stringToHue(id);

        // Check if hopper
        const isHopper = drone.type === "hopper";

        // Dim inactive drones
        const isActive = diff <= 30;
        const lightness = isActive ? 60 : 35;

        // Hoppers are cyan, regular drones use their hue
        if (isHopper) {
            item.style.color = isActive ? '#0ff' : '#066';
        } else {
            item.style.color = `hsl(${hue}, 100%, ${lightness}%)`;
        }

        // Build hunger display with color coding
        let hungerText = '';
        const hunger = drone.hunger !== undefined ? drone.hunger : 100;
        if (hunger <= 0) {
            hungerText = ' <span style="color:#f00;font-weight:bold">☠STARVING</span>';
        } else if (hunger <= 20) {
            hungerText = ` <span style="color:#f00">H:${hunger}%</span>`;
        } else if (hunger <= 50) {
            hungerText = ` <span style="color:#ff0">H:${hunger}%</span>`;
        } else {
            hungerText = ` <span style="color:#0f0">H:${hunger}%</span>`;
        }

        // Show status based on drone type
        let statusText;
        if (isHopper) {
            statusText = `> [${id}]${hungerText} <span style="color:#0ff">SCOUTING</span>`;
        } else {
            statusText = `> [${id}]${hungerText} RSSI:${drone.rssi}dB`;
        }
        if (drone.state === "carrying") {
            statusText = `> [${id}]${hungerText} <span style="color:#00ff64">CARRYING</span>`;
        }
        item.innerHTML = statusText;
        list.appendChild(item);
    }

    // Display dead drones at the bottom in red
    if (deadIds.length > 0) {
        // Add separator if there are dead drones
        const separator = document.createElement('div');
        separator.style.borderTop = '1px solid #600';
        separator.style.margin = '6px 0';
        list.appendChild(separator);

        for (const id of deadIds.sort()) {
            const drone = deadDrones[id];
            if (!drone) continue;

            const item = document.createElement('div');
            item.style.marginBottom = '4px';
            item.style.color = '#f00';

            const isHopper = drone.type === "hopper";
            const typeLabel = isHopper ? 'HOPPER' : 'DRONE';

            item.innerHTML = `> [${id}] <span style="font-weight:bold">☠ DEAD</span> <span style="color:#888">(${typeLabel})</span>`;
            list.appendChild(item);
        }
    }
}

// --- RESIZER FUNCTIONALITY ---
const resizer = document.getElementById('resizer');
const resizerRight = document.getElementById('resizer-right');
const panelLeft = document.getElementById('panel-left');
const panelRight = document.getElementById('panel-right');
let isResizingLeft = false;
let isResizingRight = false;

// Left resizer
resizer.addEventListener('mousedown', (e) => {
    isResizingLeft = true;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
});

// Right resizer
if (resizerRight) {
    resizerRight.addEventListener('mousedown', (e) => {
        isResizingRight = true;
        resizerRight.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });
}

document.addEventListener('mousemove', (e) => {
    const containerRect = document.querySelector('.container').getBoundingClientRect();

    if (isResizingLeft) {
        let newWidth = e.clientX - containerRect.left;
        newWidth = Math.max(150, Math.min(newWidth, 400));
        panelLeft.style.flex = 'none';  // Override flex when manually resizing
        panelLeft.style.width = newWidth + 'px';
    }

    if (isResizingRight && panelRight) {
        let newWidth = containerRect.right - e.clientX;
        newWidth = Math.max(150, Math.min(newWidth, 400));
        panelRight.style.flex = 'none';  // Override flex when manually resizing
        panelRight.style.width = newWidth + 'px';
    }
});

document.addEventListener('mouseup', () => {
    if (isResizingLeft) {
        isResizingLeft = false;
        resizer.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }
    if (isResizingRight && resizerRight) {
        isResizingRight = false;
        resizerRight.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    }
});

// Lock config on mousedown to prevent race condition (before input loses focus)
document.getElementById('apply-config-btn')?.addEventListener('mousedown', () => {
    configUpdateLock = true;
});

// Start polling
setInterval(fetchState, 100);

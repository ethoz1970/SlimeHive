/**
 * HIVE CORE - Shared utilities and canvas rendering
 */

// Default grid configuration
let gridSize = 100;
let scale = 800 / gridSize;

/**
 * Update grid dimensions
 * @param {number} newSize - New grid size
 */
function updateGridSize(newSize) {
    gridSize = newSize;
    scale = 800 / gridSize;
}

/**
 * Generate consistent hue from string (for drone colors)
 * @param {string} str - Input string (drone ID)
 * @returns {number} Hue value (0-360)
 */
function stringToHue(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return Math.abs(hash % 360);
}

/**
 * Get heatmap color for pheromone intensity
 * @param {number} value - Pheromone intensity
 * @returns {string} RGB color string
 */
function getColor(value) {
    if (value < 5) return `rgb(0,0,0)`;
    if (value < 50) return `rgb(${value * 5}, 0, 0)`;
    if (value < 150) return `rgb(255, ${value}, 0)`;
    return `rgb(255, 255, ${Math.min(255, value - 100)})`;
}

/**
 * Draw pheromone heat map
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number[][]} grid - Active pheromone grid
 * @param {number[][]} ghostGrid - Ghost memory grid
 */
function drawMap(ctx, grid, ghostGrid) {
    if (!grid || grid.length < gridSize) return;
    const hasGhost = ghostGrid && ghostGrid.length === gridSize;

    for (let x = 0; x < gridSize; x++) {
        for (let y = 0; y < gridSize; y++) {
            const active = grid[x][y];

            if (active > 5) {
                ctx.fillStyle = getColor(active);
                ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
            } else if (hasGhost) {
                const ghost = ghostGrid[x][y];
                if (ghost > 10) {
                    const g = Math.min(255, Math.floor(ghost));
                    ctx.fillStyle = `rgba(255, 255, 255, ${g / 400})`;
                    ctx.fillRect(x * scale, (gridSize - 1 - y) * scale, scale, scale);
                }
            }
        }
    }
}

/**
 * Draw Queen icon at bottom-left
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 */
function drawQueen(ctx) {
    const x = 10;
    const y = 10;
    const px = x * scale;
    const py = (gridSize - 1 - y) * scale;

    // Diamond shape
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.moveTo(px, py - 8);
    ctx.lineTo(px + 8, py);
    ctx.lineTo(px, py + 8);
    ctx.lineTo(px - 8, py);
    ctx.closePath();
    ctx.fill();

    // Label
    ctx.fillStyle = '#000';
    ctx.font = 'bold 10px monospace';
    ctx.fillText("Q", px - 3.5, py + 3.5);
}

/**
 * Draw Sentinel icon at top-right
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 */
function drawSentinel(ctx) {
    const x = 90;
    const y = 90;
    const px = x * scale;
    const py = (gridSize - 1 - y) * scale;

    // Triangle shape
    ctx.fillStyle = '#0af';
    ctx.beginPath();
    ctx.moveTo(px, py - 8);
    ctx.lineTo(px + 8, py + 8);
    ctx.lineTo(px - 8, py + 8);
    ctx.closePath();
    ctx.fill();

    // Label
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 10px monospace';
    ctx.fillText("S", px - 3.5, py + 6);
}

/**
 * Draw operational boundary rectangle
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {Object} boundary - Boundary coordinates {min_x, min_y, max_x, max_y}
 * @param {string} [strokeColor='#333'] - Stroke color
 * @param {string} [fillColor='rgba(255, 255, 255, 0.03)'] - Fill color
 */
function drawBoundary(ctx, boundary, strokeColor = '#333', fillColor = 'rgba(255, 255, 255, 0.03)') {
    if (!boundary) {
        boundary = { min_x: 10, min_y: 10, max_x: 90, max_y: 90 };
    }

    const x1 = boundary.min_x * scale;
    const y1 = (gridSize - 1 - boundary.max_y) * scale;
    const width = (boundary.max_x - boundary.min_x) * scale;
    const height = (boundary.max_y - boundary.min_y) * scale;

    // Dashed rectangle outline
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.strokeRect(x1, y1, width, height);
    ctx.setLineDash([]);

    // Subtle fill
    ctx.fillStyle = fillColor;
    ctx.fillRect(x1, y1, width, height);
}

/**
 * Convert grid coordinates to canvas pixels
 * @param {number} gridX - Grid X coordinate
 * @param {number} gridY - Grid Y coordinate
 * @returns {{x: number, y: number}} Canvas pixel coordinates
 */
function gridToCanvas(gridX, gridY) {
    return {
        x: gridX * scale + scale / 2,
        y: (gridSize - 1 - gridY) * scale + scale / 2
    };
}

/**
 * Convert canvas pixels to grid coordinates
 * @param {number} canvasX - Canvas X pixel
 * @param {number} canvasY - Canvas Y pixel
 * @returns {{x: number, y: number}} Grid coordinates
 */
function canvasToGrid(canvasX, canvasY) {
    return {
        x: Math.floor(canvasX / scale),
        y: gridSize - 1 - Math.floor(canvasY / scale)
    };
}

/**
 * Clear canvas with black background
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {HTMLCanvasElement} canvas - Canvas element
 */
function clearCanvas(ctx, canvas) {
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
}

/**
 * Draw fuzzy pheromone-like drone representation
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} canvasX - Canvas X position
 * @param {number} canvasY - Canvas Y position
 * @param {string} color - HSL/HSLA color string
 * @param {number} radius - Outer radius of fuzzy glow
 * @param {number} coreRadius - Inner core radius
 */
function drawFuzzyDrone(ctx, canvasX, canvasY, color, radius = 12, coreRadius = 4) {
    const hslMatch = color.match(/hsla?\((\d+),\s*(\d+)%,\s*(\d+)%(?:,\s*([\d.]+))?\)/);
    if (!hslMatch) {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(canvasX, canvasY, 8, 0, 2 * Math.PI);
        ctx.fill();
        return;
    }

    const [, hue, sat, light, baseAlpha = 1.0] = hslMatch;

    const gradient = ctx.createRadialGradient(canvasX, canvasY, 0, canvasX, canvasY, radius);
    gradient.addColorStop(0, `hsla(${hue}, ${sat}%, ${light}%, ${baseAlpha})`);
    gradient.addColorStop(coreRadius / radius, `hsla(${hue}, ${sat}%, ${light}%, ${baseAlpha * 0.8})`);
    gradient.addColorStop(0.6, `hsla(${hue}, ${sat}%, ${light}%, ${baseAlpha * 0.3})`);
    gradient.addColorStop(1.0, `hsla(${hue}, ${sat}%, ${light}%, 0)`);

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(canvasX, canvasY, radius, 0, 2 * Math.PI);
    ctx.fill();
}

// Export for module usage (if needed)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        updateGridSize,
        stringToHue,
        getColor,
        drawMap,
        drawQueen,
        drawSentinel,
        drawBoundary,
        gridToCanvas,
        canvasToGrid,
        clearCanvas,
        drawFuzzyDrone
    };
}

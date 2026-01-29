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
 * Draw food sources on the canvas (squares to differentiate from drone circles)
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {Array} foodSources - Array of food source objects
 */
function drawFood(ctx, foodSources) {
    if (!foodSources || foodSources.length === 0) return;

    for (const food of foodSources) {
        const canvasX = food.x * scale + scale / 2;
        const canvasY = (gridSize - 1 - food.y) * scale + scale / 2;
        const size = food.radius * scale * 2;

        if (food.consumed) {
            // Draw depleted food as light gray outline
            ctx.strokeStyle = '#888';
            ctx.lineWidth = 2;
            ctx.strokeRect(canvasX - size / 2, canvasY - size / 2, size, size);
            continue;
        }

        // Color based on remaining amount (green -> yellow -> red)
        const ratio = food.amount / food.max_amount;
        const hue = ratio * 120; // 120 = green, 0 = red

        // Draw outer glow (square)
        const glowSize = size * 1.4;
        ctx.fillStyle = `hsla(${hue}, 100%, 50%, 0.2)`;
        ctx.fillRect(canvasX - glowSize / 2, canvasY - glowSize / 2, glowSize, glowSize);

        // Draw core square
        ctx.fillStyle = `hsla(${hue}, 100%, 50%, 0.7)`;
        ctx.fillRect(canvasX - size / 2, canvasY - size / 2, size, size);

        // Draw border
        ctx.strokeStyle = `hsl(${hue}, 100%, 30%)`;
        ctx.lineWidth = 2;
        ctx.strokeRect(canvasX - size / 2, canvasY - size / 2, size, size);

        // Draw amount indicator (small text)
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 8px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(Math.round(food.amount), canvasX, canvasY + 3);
    }
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

/**
 * Draw hard solid drone circle
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} canvasX - Canvas X position
 * @param {number} canvasY - Canvas Y position
 * @param {string} color - Color string
 * @param {number} radius - Circle radius
 */
function drawHardDrone(ctx, canvasX, canvasY, color, radius = 8) {
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(canvasX, canvasY, radius, 0, 2 * Math.PI);
    ctx.fill();
    ctx.stroke();
}

/**
 * Draw heat trail visualization (additive blending for glow effect)
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {Array} trail - Trail points [[x,y], ...]
 * @param {number} hue - Color hue
 */
function drawHeatTrail(ctx, trail, hue) {
    if (trail.length < 2) return;

    ctx.globalCompositeOperation = 'lighter';
    ctx.strokeStyle = `hsla(${hue}, 100%, 50%, 0.3)`;
    ctx.lineWidth = 6;
    ctx.lineCap = 'round';

    ctx.beginPath();
    ctx.moveTo(trail[0][0] * scale + scale / 2, (gridSize - 1 - trail[0][1]) * scale + scale / 2);
    for (let i = 1; i < trail.length; i++) {
        ctx.lineTo(trail[i][0] * scale + scale / 2, (gridSize - 1 - trail[i][1]) * scale + scale / 2);
    }
    ctx.stroke();
    ctx.globalCompositeOperation = 'source-over';
}

/**
 * Draw ghost drone visualization with faded afterimages
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {Array} trail - Trail points [[x,y], ...]
 * @param {number} hue - Color hue
 */
function drawGhostDrone(ctx, trail, hue) {
    const trailLen = trail.length;
    for (let i = 0; i < trailLen; i++) {
        const age = (trailLen - i) / trailLen;
        const alpha = age * 0.6;
        const radius = 4 + age * 4;

        const x = trail[i][0] * scale + scale / 2;
        const y = (gridSize - 1 - trail[i][1]) * scale + scale / 2;

        ctx.fillStyle = `hsla(${hue}, 100%, 50%, ${alpha})`;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, 2 * Math.PI);
        ctx.fill();
    }
}

/**
 * Draw death markers (red X where drones died)
 * Hoppers get a larger X (2x size)
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {Array} deathMarkers - Array of death marker objects {x, y, drone_id, tick, type}
 */
function drawDeathMarkers(ctx, deathMarkers) {
    if (!deathMarkers || deathMarkers.length === 0) return;

    ctx.strokeStyle = '#f00';

    for (const marker of deathMarkers) {
        const canvasX = marker.x * scale + scale / 2;
        const canvasY = (gridSize - 1 - marker.y) * scale + scale / 2;

        // Hoppers get 2x size
        const isHopper = marker.type === "hopper";
        const size = isHopper ? 12 : 6;
        ctx.lineWidth = isHopper ? 3 : 2;

        // Draw X
        ctx.beginPath();
        ctx.moveTo(canvasX - size, canvasY - size);
        ctx.lineTo(canvasX + size, canvasY + size);
        ctx.moveTo(canvasX + size, canvasY - size);
        ctx.lineTo(canvasX - size, canvasY + size);
        ctx.stroke();
    }
}

/**
 * Draw food markers (yellow X where hoppers found food)
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {Array} foodMarkers - Array of food marker objects {x, y, drone_id, tick}
 */
function drawFoodMarkers(ctx, foodMarkers) {
    if (!foodMarkers || foodMarkers.length === 0) return;

    ctx.strokeStyle = '#ff0';  // Yellow
    ctx.lineWidth = 3;

    for (const marker of foodMarkers) {
        const canvasX = marker.x * scale + scale / 2;
        const canvasY = (gridSize - 1 - marker.y) * scale + scale / 2;
        const size = 10;  // Larger than death markers

        // Draw X
        ctx.beginPath();
        ctx.moveTo(canvasX - size, canvasY - size);
        ctx.lineTo(canvasX + size, canvasY + size);
        ctx.moveTo(canvasX + size, canvasY - size);
        ctx.lineTo(canvasX - size, canvasY + size);
        ctx.stroke();
    }
}

/**
 * Draw smell markers (white X where hoppers detected food but didn't eat)
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {Array} smellMarkers - Array of smell marker objects {x, y, drone_id, tick, distance}
 */
function drawSmellMarkers(ctx, smellMarkers) {
    if (!smellMarkers || smellMarkers.length === 0) return;

    ctx.strokeStyle = '#fff';  // White
    ctx.lineWidth = 2;

    for (const marker of smellMarkers) {
        const canvasX = marker.x * scale + scale / 2;
        const canvasY = (gridSize - 1 - marker.y) * scale + scale / 2;
        const size = 6;  // Smaller than food markers

        // Draw X
        ctx.beginPath();
        ctx.moveTo(canvasX - size, canvasY - size);
        ctx.lineTo(canvasX + size, canvasY + size);
        ctx.moveTo(canvasX + size, canvasY - size);
        ctx.lineTo(canvasX - size, canvasY + size);
        ctx.stroke();
    }
}

/**
 * Draw hopper scout drone (cyan triangle)
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} canvasX - Canvas X position
 * @param {number} canvasY - Canvas Y position
 * @param {number} size - Triangle size
 * @param {number} alpha - Opacity (0-1)
 */
function drawHopper(ctx, canvasX, canvasY, size = 10, alpha = 1.0) {
    ctx.save();
    ctx.globalAlpha = alpha;

    // Outer glow
    ctx.fillStyle = 'rgba(0, 255, 255, 0.3)';
    ctx.beginPath();
    ctx.moveTo(canvasX, canvasY - size * 1.5);
    ctx.lineTo(canvasX + size * 1.2, canvasY + size);
    ctx.lineTo(canvasX - size * 1.2, canvasY + size);
    ctx.closePath();
    ctx.fill();

    // Main triangle (cyan)
    ctx.fillStyle = '#0ff';
    ctx.beginPath();
    ctx.moveTo(canvasX, canvasY - size);
    ctx.lineTo(canvasX + size * 0.8, canvasY + size * 0.6);
    ctx.lineTo(canvasX - size * 0.8, canvasY + size * 0.6);
    ctx.closePath();
    ctx.fill();

    // Border
    ctx.strokeStyle = '#0aa';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.restore();
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
        drawFood,
        drawDeathMarkers,
        gridToCanvas,
        canvasToGrid,
        clearCanvas,
        drawFuzzyDrone
    };
}

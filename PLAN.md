# Plan: Save Final Map Image on Simulation End

## Goal
Automatically save a PNG image of the final map state when a simulation ends.

---

## Options

### Option A: Python-side Rendering (Recommended)
Generate the image directly in Python using PIL/Pillow when simulation ends.

**Pros:**
- Works without dashboard running
- Self-contained in simulate.py
- No browser dependencies

**Cons:**
- Need to replicate drawing logic in Python
- May not be pixel-perfect match to dashboard

### Option B: Dashboard-triggered Save
Have the dashboard detect simulation end and save canvas as PNG.

**Pros:**
- Exact visual match to dashboard
- No code duplication

**Cons:**
- Requires dashboard to be running
- Need IPC between simulation and dashboard

### Option C: Headless Browser
Use Puppeteer/Playwright to screenshot dashboard.

**Pros:**
- Exact match

**Cons:**
- Heavy dependency
- Complex setup

---

## Recommended: Option A (Python PIL)

### Implementation

#### 1. Add PIL dependency

Already available in most Python environments, or:
```bash
pip install Pillow
```

#### 2. Create `save_final_image()` method in Simulation class

```python
from PIL import Image, ImageDraw

def save_final_image(self, filename=None):
    """Save final map state as PNG image"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        mode = self.config["drones"]["behavior_mode"]
        filename = os.path.join(BASE_DIR, "analysis", "screenshots",
                                f"final_{mode}_{timestamp}.png")

    os.makedirs(os.path.dirname(filename), exist_ok=True)

    # Image size (match dashboard: 800x800)
    size = 800
    scale = size / self.grid_size

    # Create black background
    img = Image.new('RGB', (size, size), color='black')
    draw = ImageDraw.Draw(img)

    # Draw pheromone grid (ghost_grid)
    for x in range(self.grid_size):
        for y in range(self.grid_size):
            ghost = self.ghost_grid[x][y]
            if ghost > 10:
                intensity = min(255, int(ghost))
                alpha = intensity // 2
                # White with varying intensity
                px = int(x * scale)
                py = int((self.grid_size - 1 - y) * scale)
                draw.rectangle([px, py, px + scale, py + scale],
                              fill=(intensity, intensity, intensity))

    # Draw food sources
    for food in self.food_sources:
        px = int(food["x"] * scale)
        py = int((self.grid_size - 1 - food["y"]) * scale)
        radius = int(food["radius"] * scale)

        if food["consumed"]:
            # Gray outline for depleted
            draw.rectangle([px - radius, py - radius, px + radius, py + radius],
                          outline='#888888', width=2)
        else:
            # Color based on amount (green -> red)
            ratio = food["amount"] / food["max_amount"]
            r = int(255 * (1 - ratio))
            g = int(255 * ratio)
            draw.rectangle([px - radius, py - radius, px + radius, py + radius],
                          fill=(r, g, 0), outline=(r//2, g//2, 0), width=2)

    # Draw death markers (red X)
    for marker in self.death_markers:
        px = int(marker["x"] * scale)
        py = int((self.grid_size - 1 - marker["y"]) * scale)
        size_x = 12 if marker.get("type") == "hopper" else 6
        draw.line([px - size_x, py - size_x, px + size_x, py + size_x], fill='red', width=2)
        draw.line([px + size_x, py - size_x, px - size_x, py + size_x], fill='red', width=2)

    # Draw food markers (yellow X)
    for marker in self.food_markers:
        px = int(marker["x"] * scale)
        py = int((self.grid_size - 1 - marker["y"]) * scale)
        draw.line([px - 10, py - 10, px + 10, py + 10], fill='yellow', width=3)
        draw.line([px + 10, py - 10, px - 10, py + 10], fill='yellow', width=3)

    # Draw smell markers (white X)
    for marker in self.smell_markers:
        px = int(marker["x"] * scale)
        py = int((self.grid_size - 1 - marker["y"]) * scale)
        draw.line([px - 6, py - 6, px + 6, py + 6], fill='white', width=2)
        draw.line([px + 6, py - 6, px - 6, py + 6], fill='white', width=2)

    # Draw Queen (white diamond)
    qx = int(self.queen_pos[0] * scale)
    qy = int((self.grid_size - 1 - self.queen_pos[1]) * scale)
    draw.polygon([(qx, qy-8), (qx+8, qy), (qx, qy+8), (qx-8, qy)], fill='white')

    # Draw remaining drones
    for drone_id, drone in self.drones.items():
        px = int(drone["x"] * scale)
        py = int((self.grid_size - 1 - drone["y"]) * scale)

        if drone.get("type") == "hopper":
            # Cyan triangle for hoppers
            draw.polygon([(px, py-8), (px+6, py+6), (px-6, py+6)], fill='cyan')
        else:
            # Circle for regular drones
            draw.ellipse([px-4, py-4, px+4, py+4], fill='lime')

    # Draw dead drones (dimmer)
    for drone_id, drone in self.dead_drones.items():
        px = int(drone["x"] * scale)
        py = int((self.grid_size - 1 - drone["y"]) * scale)
        draw.ellipse([px-3, py-3, px+3, py+3], fill='#440000')

    # Save image
    img.save(filename)
    print(f"    Final image saved: {filename}")
    return filename
```

#### 3. Call from `run()` at end of simulation

```python
def run(self):
    # ... simulation loop ...

    # After final report
    if self.config.get("save_image", True):
        self.save_final_image()
```

#### 4. Add CLI argument

```python
parser.add_argument("--no-save-image", action="store_true",
                    help="Don't save final map image")

# In config application:
if args.no_save_image:
    config["save_image"] = False
```

---

## Files to Modify

1. **simulate.py**
   - Add `from PIL import Image, ImageDraw` import
   - Add `save_final_image()` method
   - Call from `run()` after simulation ends
   - Add CLI argument `--no-save-image`

2. **requirements.txt** (if exists)
   - Add `Pillow` if not already present

---

## Output Location

Images saved to: `analysis/screenshots/final_{MODE}_{TIMESTAMP}.png`

Example: `analysis/screenshots/final_FORAGE_2024-01-29_143052.png`

---

## Testing

```bash
# Run simulation - image auto-saved
python simulate.py --mode FORAGE --food-sources 3 --drones 10 --duration 30

# Check output
ls -la analysis/screenshots/

# Disable image saving
python simulate.py --mode FORAGE --drones 10 --no-save-image
```

---

## Future Enhancements

- Add boundary rectangle to image
- Add text overlay with stats (drone count, food consumed, etc.)
- Option to save at regular intervals (timelapse)
- Save as animated GIF of simulation

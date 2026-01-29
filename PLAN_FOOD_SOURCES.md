# Plan: Food Sources for Simulation

## Goal
Add food sources that drones can discover, consume, and deplete - creating foraging behavior patterns similar to real ant colonies.

---

## Concept

### Food Source Properties
| Property | Description |
|----------|-------------|
| Position | (x, y) on grid |
| Amount | How much food remains (0-100) |
| Radius | Size of the food patch |
| Decay Rate | How fast drones consume it |

### Drone Behavior with Food
1. **Detection** - Drones sense food within a radius
2. **Attraction** - Drones move toward detected food
3. **Consumption** - Food depletes when drones are on/near it
4. **Communication** - Drones leave stronger pheromones near food (recruit others)

---

## CLI Parameters

```bash
python simulate.py --drones 50 --mode FORAGE \
    --food-sources 5 \
    --food-amount 100 \
    --food-spread clustered
```

| Parameter | Values | Description |
|-----------|--------|-------------|
| `--food-sources` | 1-20 | Number of food patches |
| `--food-amount` | 10-500 | Starting amount per source |
| `--food-spread` | `clustered`, `scattered`, `corners`, `center` | Distribution pattern |
| `--food-radius` | 1-10 | Size of each food patch |
| `--food-regen` | true/false | Whether food regrows over time |

---

## Implementation

### 1. Food Data Structure

```python
# In simulate.py
food_sources = []

# Each food source:
{
    "id": "F-001",
    "x": 45,
    "y": 67,
    "amount": 100.0,       # Current amount (depletes)
    "max_amount": 100.0,   # Starting amount
    "radius": 3,           # Detection/consumption radius
    "consumed": False      # Disappears when True
}
```

### 2. Food Grid Layer

```python
# New grid for food visualization
food_grid = np.zeros((GRID_SIZE, GRID_SIZE), dtype=float)

# Food sources paint onto this grid
for food in food_sources:
    if not food["consumed"]:
        # Paint circle of food onto grid
        for dx in range(-food["radius"], food["radius"] + 1):
            for dy in range(-food["radius"], food["radius"] + 1):
                if dx*dx + dy*dy <= food["radius"]**2:
                    fx, fy = food["x"] + dx, food["y"] + dy
                    if 0 <= fx < GRID_SIZE and 0 <= fy < GRID_SIZE:
                        food_grid[fx][fy] = food["amount"] / food["max_amount"]
```

### 3. Food Spawning

```python
def spawn_food(count, spread, amount, radius):
    """Spawn food sources based on spread pattern"""
    food_sources = []

    for i in range(count):
        if spread == "scattered":
            x = np.random.randint(margin, grid_size - margin)
            y = np.random.randint(margin, grid_size - margin)

        elif spread == "clustered":
            # All food near center with some variance
            cx, cy = grid_size // 2, grid_size // 2
            x = cx + np.random.randint(-20, 20)
            y = cy + np.random.randint(-20, 20)

        elif spread == "corners":
            corner = i % 4
            if corner == 0: x, y = margin + 10, margin + 10
            elif corner == 1: x, y = grid_size - margin - 10, margin + 10
            elif corner == 2: x, y = margin + 10, grid_size - margin - 10
            else: x, y = grid_size - margin - 10, grid_size - margin - 10
            x += np.random.randint(-5, 5)
            y += np.random.randint(-5, 5)

        elif spread == "perimeter":
            # Food along edges
            edge = i % 4
            if edge == 0: x, y = np.random.randint(margin, grid_size - margin), margin + 5
            elif edge == 1: x, y = grid_size - margin - 5, np.random.randint(margin, grid_size - margin)
            elif edge == 2: x, y = np.random.randint(margin, grid_size - margin), grid_size - margin - 5
            else: x, y = margin + 5, np.random.randint(margin, grid_size - margin)

        food_sources.append({
            "id": f"F-{i:03d}",
            "x": int(x),
            "y": int(y),
            "amount": float(amount),
            "max_amount": float(amount),
            "radius": radius,
            "consumed": False
        })

    return food_sources
```

### 4. Food Detection (Drone Sensing)

```python
def detect_food(drone, food_sources, detection_radius=15):
    """Find food sources within detection radius"""
    detected = []
    dx, dy = drone["x"], drone["y"]

    for food in food_sources:
        if food["consumed"]:
            continue

        dist = ((food["x"] - dx)**2 + (food["y"] - dy)**2) ** 0.5
        if dist <= detection_radius:
            detected.append({
                "food": food,
                "distance": dist,
                "direction_x": food["x"] - dx,
                "direction_y": food["y"] - dy
            })

    return sorted(detected, key=lambda f: f["distance"])
```

### 5. Food Consumption

```python
def consume_food(drone, food_sources, consumption_rate=1.0):
    """Drones near food consume it"""
    dx, dy = drone["x"], drone["y"]

    for food in food_sources:
        if food["consumed"]:
            continue

        dist = ((food["x"] - dx)**2 + (food["y"] - dy)**2) ** 0.5

        # Within consumption radius (smaller than detection)
        if dist <= food["radius"] + 1:
            # Consume based on distance (closer = faster)
            consume_amount = consumption_rate * (1 - dist / (food["radius"] + 2))
            food["amount"] -= consume_amount

            if food["amount"] <= 0:
                food["amount"] = 0
                food["consumed"] = True
                print(f"    Food {food['id']} depleted!")

            return True  # Drone found food

    return False
```

### 6. New Behavior Mode: FORAGE

```python
elif mode == "FORAGE":
    # Detect nearby food
    nearby_food = detect_food(drone, food_sources, detection_radius=20)

    if nearby_food:
        # Move toward closest food
        closest = nearby_food[0]
        dx = int(np.sign(closest["direction_x"]))
        dy = int(np.sign(closest["direction_y"]))

        # Deposit extra pheromones when near food (recruitment)
        if closest["distance"] < 5:
            pheromone_boost = 3.0
    else:
        # No food detected - follow pheromone trails or random walk
        # Check ghost_grid for existing trails
        best_pheromone = 0
        for check_dx in [-1, 0, 1]:
            for check_dy in [-1, 0, 1]:
                nx = drone["x"] + check_dx
                ny = drone["y"] + check_dy
                if 0 <= nx < grid_size and 0 <= ny < grid_size:
                    p = ghost_grid[nx][ny] + np.random.random() * 2
                    if p > best_pheromone:
                        best_pheromone = p
                        dx, dy = check_dx, check_dy

        # If no trails, random walk
        if best_pheromone < 1:
            dx = np.random.choice([-1, 0, 1])
            dy = np.random.choice([-1, 0, 1])
```

### 7. Tick Update with Food

```python
def tick(self):
    # Update all drones
    for drone_id in list(self.drones.keys()):
        self.update_drone(drone_id)

        # Consume food if near
        consume_food(self.drones[drone_id], self.food_sources)

    # Apply decay
    self.hive_grid *= self.config["pheromones"]["decay_rate"]

    # Update food grid for visualization
    self.update_food_grid()

    # Write state for dashboard
    if self.config["simulation"].get("live_view", True):
        self.write_live_state()
```

---

## Dashboard Visualization

### Food Layer on Canvas

```javascript
// In hive-core.js or live.js
function drawFood(ctx, foodSources) {
    for (const food of foodSources) {
        if (food.consumed) continue;

        const x = food.x * scale + scale / 2;
        const y = (gridSize - 1 - food.y) * scale + scale / 2;
        const radius = food.radius * scale;

        // Color based on remaining amount (green -> yellow -> red)
        const ratio = food.amount / food.max_amount;
        const hue = ratio * 120; // 120 = green, 0 = red

        ctx.fillStyle = `hsla(${hue}, 100%, 50%, 0.6)`;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, 2 * Math.PI);
        ctx.fill();

        // Border
        ctx.strokeStyle = `hsl(${hue}, 100%, 30%)`;
        ctx.lineWidth = 2;
        ctx.stroke();
    }
}
```

### State JSON Update

```python
# In write_live_state()
state = {
    "grid": self.hive_grid.tolist(),
    "ghost_grid": self.ghost_grid.tolist(),
    "drones": {...},
    "food_sources": self.food_sources,  # NEW
    "mood": "SIMULATION",
    ...
}
```

---

## Config Addition

```json
{
    "food": {
        "enabled": true,
        "sources": 5,
        "amount": 100,
        "spread": "scattered",
        "radius": 3,
        "consumption_rate": 1.0,
        "detection_radius": 20,
        "pheromone_boost": 3.0,
        "regenerate": false,
        "regen_rate": 0.1
    }
}
```

---

## Metrics to Track

| Metric | Description |
|--------|-------------|
| `food_remaining` | Total food left across all sources |
| `food_depleted` | Number of fully consumed sources |
| `foraging_efficiency` | Food consumed per tick per drone |
| `discovery_time` | Ticks until first food found |
| `recruitment_success` | Do pheromone trails lead others to food? |

---

## Example Scenarios

### Scenario 1: Scattered Foraging
```bash
python simulate.py --drones 30 --mode FORAGE \
    --food-sources 10 --food-spread scattered
```
Drones must explore to find food, pheromones help recruit.

### Scenario 2: Clustered Resource Competition
```bash
python simulate.py --drones 50 --mode FORAGE \
    --food-sources 3 --food-spread center --food-amount 200
```
Many drones compete for few resources.

### Scenario 3: Corner Caches
```bash
python simulate.py --drones 20 --mode FORAGE \
    --spawn center --food-sources 4 --food-spread corners
```
Drones start in center, must find food in corners.

---

## Files to Modify

| File | Changes |
|------|---------|
| `simulate.py` | Add food spawning, detection, consumption, FORAGE mode |
| `config/simulation.json` | Add food configuration section |
| `static/js/hive-core.js` | Add `drawFood()` function |
| `static/js/live.js` | Call `drawFood()` in render loop |

---

## Implementation Order

1. Add food data structure and spawning
2. Add FORAGE behavior mode
3. Add food consumption logic
4. Update state JSON to include food
5. Add food visualization to dashboard
6. Add CLI arguments
7. Add metrics tracking
8. Test scenarios

---

## Future Enhancements

1. **Food Types** - Different colors/values
2. **Nest Location** - Drones carry food back to nest
3. **Food Regeneration** - Sources slowly refill
4. **Seasonal Variation** - Food availability changes over time
5. **Toxicity** - Some food is harmful (drones learn to avoid)

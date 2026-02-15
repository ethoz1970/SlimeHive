# Plan: Add Section Headers to Drone Registry

## Summary
Update the dashboard's drone registry in virtualization mode to show section headers with colored separator lines for HOPPERS, WORKERS, and RIP (dead drones).

## Current State
- Living drones are mixed together, sorted by activity then alphabetically
- Hoppers appear at top (due to sorting behavior)
- Dead drones appear at bottom with a red separator line

## Target Layout
```
HOPPERS ──────────────── (cyan line)
> [hopper_001] H:85% SCOUTING
> [hopper_002] H:72% SCOUTING

WORKERS ──────────────── (cyan line)
> [drone_001] H:90% RSSI:-45dB
> [drone_002] H:65% CARRYING

RIP ──────────────────── (red line)
> [drone_003] ☠ DEAD (WORKER)
> [hopper_003] ☠ DEAD (HOPPER)
```

## File to Modify
- `/Users/zeeggemorhead/sites/HiveMind/SlimeHive/static/js/live.js` - `updateDroneList()` function (lines 520-631)

## Implementation

### Changes to `updateDroneList()` function

1. **Separate drones by type first** - Split living drones into hoppers and workers arrays

2. **Create helper function for section headers**
```javascript
function createSectionHeader(text, color) {
    const header = document.createElement('div');
    header.style.cssText = `
        color: ${color};
        font-weight: bold;
        margin: 8px 0 4px 0;
        padding-bottom: 4px;
        border-bottom: 1px solid ${color};
        font-size: 10px;
        letter-spacing: 1px;
    `;
    header.textContent = text;
    return header;
}
```

3. **Update rendering order**:
   - Add "HOPPERS" header (cyan: `#0aa`) if any hoppers exist
   - Render all living hoppers
   - Add "WORKERS" header (cyan: `#0aa`) if any workers exist
   - Render all living workers
   - Add "RIP" header (red: `#a00`) if any dead drones exist
   - Render all dead drones

4. **Sorting within sections**:
   - Hoppers: active first, then inactive, alphabetically within each group
   - Workers: active first, then inactive, alphabetically within each group
   - Dead: alphabetically by ID

## Verification
1. Run simulation with hoppers enabled: `python simulate.py --hoppers 3`
2. Open dashboard at http://localhost:5050
3. Verify:
   - HOPPERS section appears with cyan header and line
   - WORKERS section appears with cyan header and line
   - RIP section appears when drones die with red header and line
   - Drones are correctly categorized by type
   - Inactive drones still appear dimmed within their sections

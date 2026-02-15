# SlimeHive — Next Steps for Physical Drone Integration

## Phase 1 — Motor Primitives (Standalone Testing)

### 1. Flash Pico 2W
- Copy `main.py` and `config_drone.py` to the Pico 2W
- Install `umqtt.simple` via `mip`: `import mip; mip.install("umqtt.simple")`
- Edit `config_drone.py` with your WiFi SSID/password and Queen Pi IP

### 2. Verify Motor Wiring
- Power up with motors disconnected first — confirm no smoke from L298N
- Connect motors, run manual test: `mosquitto_pub -t "hive/drone/P-01/move" -m '{"dx":1,"dy":0,"seq":1}'`
- Confirm both motors spin forward, reverse, and pivot correctly
- If a motor spins the wrong direction, swap its IN1/IN2 pin values in `config_drone.py`

### 3. Verify Encoders
- Spin each wheel by hand, check serial output for encoder tick counts
- If ticks don't increment, check pull-up resistors and encoder wiring
- Confirm left/right encoders are on the correct pins (GP14/GP15)

### 4. Calibrate Constants
- **`TICKS_PER_GRID_UNIT`**: Mark a known distance on the floor (e.g. 10cm = 1 grid unit), drive forward, count ticks. Adjust until one move command = one grid unit of real travel
- **`TURN_DURATION_MS`**: Send a 90-degree turn command, measure actual rotation with a protractor or by eye. Adjust until pivot is accurate
- **`DUTY_FORWARD` / `DUTY_TURN`**: Start low (30000), increase until motors move reliably without being too fast to control
- Test diagonal moves — they should travel ~1.41x the straight distance

## Phase 2 — MQTT Integration (Manual Commands)

### 5. Test Move Commands
- Start Mosquitto broker on the Queen Pi
- Send individual move commands and verify the drone responds:
  ```
  mosquitto_pub -t "hive/drone/P-01/move" -m '{"dx":1,"dy":0,"seq":1}'
  mosquitto_pub -t "hive/drone/P-01/move" -m '{"dx":0,"dy":1,"seq":2}'
  mosquitto_pub -t "hive/drone/P-01/move" -m '{"dx":-1,"dy":-1,"seq":3}'
  ```
- Verify sequence deduplication: resend seq=3, drone should ignore it

### 6. Test Position Reporting
- Subscribe to position topic: `mosquitto_sub -t "hive/drone/P-01/position"`
- Confirm reports arrive every ~500ms with x, y, heading, encoder counts
- Verify dead-reckoned position updates after each move

### 7. Test E-Stop
- Send `mosquitto_pub -t "hive/drone/P-01/estop" -m "STOP"` while motors are running
- Confirm immediate motor stop

### 8. Test Safety Mechanisms
- Kill the MQTT broker while drone is connected — motors should stop within 2s
- Disconnect WiFi (move out of range) — motors should stop, drone should attempt reconnect
- Send rapid duplicate commands — only the first with a new seq should execute

## Phase 3 — Queen Integration

### 9. Run Queen with Physical Drone
- Start `queen_brain.py` with virtual swarm (e.g. 10 virtual drones)
- Power on one physical drone (P-01)
- Confirm P-01 appears in the dashboard alongside virtual drones
- Confirm P-01 receives behavior commands and moves according to the active mode (BOIDS, FLOCK, etc.)

### 10. Verify Coexistence
- Physical drones should affect virtual drone behavior (show up as neighbors in BOIDS separation/cohesion)
- Virtual drones should affect physical drone behavior (physical drone avoids virtual neighbors)
- Pheromone trails from physical drones should appear on the hive grid

### 11. Multi-Drone Test
- Flash a second Pico as P-02 (change `DRONE_ID` and `START_X/Y` in its `config_drone.py`)
- Run both physical drones alongside virtual swarm
- Verify both appear on dashboard, both receive independent commands

## Phase 4 — Safety Polish

### 12. Motor Stall Detection
- If encoder ticks stop incrementing during a forward move but the motor is still running, the wheels are stalled
- Add stall detection: if no ticks for 500ms during a move, stop motors and report error
- Consider publishing a status message to `hive/drone/{id}/status` with `{"status": "stalled"}`

### 13. Battery Monitoring (Optional)
- Read ADC on a voltage divider from the battery
- Publish battery level in position reports
- Queen could recall low-battery drones toward a charging station

### 14. Compass Module (Optional)
- Dead-reckoning heading drifts over time
- Add an HMC5883L or similar I2C compass module
- Replace dead-reckoned heading with actual magnetic heading after each pivot
- This makes the drone self-correcting for heading errors

### 15. PID Motor Control (Optional)
- Current turn timing is open-loop (time-based)
- Use encoder feedback during turns for closed-loop PID control
- Left/right encoder tick differential = actual rotation angle
- This significantly improves turn accuracy on uneven surfaces

## Known Limitations
- Dead-reckoning position drifts — the drone thinks it's at (52, 53) but may actually be at (51, 54). Compass + better encoders help
- Turn calibration is surface-dependent — carpet vs hardwood vs tile will need different `TURN_DURATION_MS`
- No obstacle avoidance — the drone will drive into walls. Add ultrasonic or IR sensors for future collision avoidance
- Single-threaded MicroPython means MQTT messages are only processed between moves, not during. Long moves block message handling

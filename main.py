# main.py — SlimeHive Physical Drone (Pico 2W)
# Motor-controlled MQTT drone with encoder feedback
# Flash this + config_drone.py to your Pico 2W

import machine
import network
import time
import json
import math
from machine import Pin, PWM

# Import drone-specific config
from config_drone import (
    WIFI_SSID, WIFI_PASSWORD,
    MQTT_BROKER, MQTT_PORT,
    DRONE_ID, START_X, START_Y,
    MOTOR1_IN1, MOTOR1_IN2, MOTOR1_EN,
    MOTOR2_IN1, MOTOR2_IN2, MOTOR2_EN,
    ENCODER_LEFT, ENCODER_RIGHT,
    PWM_FREQ, DUTY_FORWARD, DUTY_TURN,
    TICKS_PER_GRID_UNIT, TURN_DURATION_MS, MOVE_TIMEOUT_MS,
    COMMAND_TIMEOUT_MS, POSITION_REPORT_MS,
)

# umqtt.simple must be installed on the Pico (via mip or manually)
from umqtt.simple import MQTTClient

# --- LED ---
led = Pin("LED", Pin.OUT)

# --- MOTOR SETUP ---
# Motor 1 (Left)
m1_in1 = Pin(MOTOR1_IN1, Pin.OUT)
m1_in2 = Pin(MOTOR1_IN2, Pin.OUT)
m1_en = PWM(Pin(MOTOR1_EN))
m1_en.freq(PWM_FREQ)

# Motor 2 (Right)
m2_in1 = Pin(MOTOR2_IN1, Pin.OUT)
m2_in2 = Pin(MOTOR2_IN2, Pin.OUT)
m2_en = PWM(Pin(MOTOR2_EN))
m2_en.freq(PWM_FREQ)

# --- ENCODER SETUP ---
enc_left_count = 0
enc_right_count = 0

enc_left_pin = Pin(ENCODER_LEFT, Pin.IN, Pin.PULL_UP)
enc_right_pin = Pin(ENCODER_RIGHT, Pin.IN, Pin.PULL_UP)

def enc_left_irq(pin):
    global enc_left_count
    enc_left_count += 1

def enc_right_irq(pin):
    global enc_right_count
    enc_right_count += 1

enc_left_pin.irq(trigger=Pin.IRQ_RISING, handler=enc_left_irq)
enc_right_pin.irq(trigger=Pin.IRQ_RISING, handler=enc_right_irq)

# --- STATE ---
pos_x = START_X
pos_y = START_Y
heading = 0              # Degrees, 0=East, 90=North, 180=West, 270=South
last_command_time = 0    # For command timeout safety
last_seq = -1            # Sequence number deduplication
moving = False           # Currently executing a move

# --- MOTOR PRIMITIVES ---
def motor_stop():
    """Stop both motors immediately."""
    m1_in1.value(0)
    m1_in2.value(0)
    m1_en.duty_u16(0)
    m2_in1.value(0)
    m2_in2.value(0)
    m2_en.duty_u16(0)

def motor_forward(duty=DUTY_FORWARD):
    """Drive both motors forward."""
    m1_in1.value(1)
    m1_in2.value(0)
    m1_en.duty_u16(duty)
    m2_in1.value(1)
    m2_in2.value(0)
    m2_en.duty_u16(duty)

def motor_reverse(duty=DUTY_FORWARD):
    """Drive both motors in reverse."""
    m1_in1.value(0)
    m1_in2.value(1)
    m1_en.duty_u16(duty)
    m2_in1.value(0)
    m2_in2.value(1)
    m2_en.duty_u16(duty)

def motor_turn_left(duty=DUTY_TURN):
    """Pivot left in place (right forward, left reverse)."""
    m1_in1.value(0)
    m1_in2.value(1)
    m1_en.duty_u16(duty)
    m2_in1.value(1)
    m2_in2.value(0)
    m2_en.duty_u16(duty)

def motor_turn_right(duty=DUTY_TURN):
    """Pivot right in place (left forward, right reverse)."""
    m1_in1.value(1)
    m1_in2.value(0)
    m1_en.duty_u16(duty)
    m2_in1.value(0)
    m2_in2.value(1)
    m2_en.duty_u16(duty)

# --- HEADING / NAVIGATION ---

# Direction vectors for the 8 possible (dx,dy) movements
# Maps (dx, dy) -> target heading in degrees
DIRECTION_TO_HEADING = {
    ( 1,  0): 0,     # East
    ( 1,  1): 45,    # NE
    ( 0,  1): 90,    # North
    (-1,  1): 135,   # NW
    (-1,  0): 180,   # West
    (-1, -1): 225,   # SW
    ( 0, -1): 270,   # South
    ( 1, -1): 315,   # SE
}

def shortest_turn(current, target):
    """
    Calculate shortest turn from current to target heading.
    Returns signed degrees: positive = left (CCW), negative = right (CW).
    """
    diff = (target - current) % 360
    if diff > 180:
        diff -= 360
    return diff

def pivot_to_heading(target_heading):
    """Pivot in place to face target_heading."""
    global heading
    turn = shortest_turn(heading, target_heading)

    if abs(turn) < 10:
        # Close enough, no pivot needed
        return

    # Calculate turn duration proportional to angle
    duration = int(abs(turn) / 90.0 * TURN_DURATION_MS)

    if turn > 0:
        motor_turn_left()
    else:
        motor_turn_right()

    time.sleep_ms(duration)
    motor_stop()

    # Update heading (dead reckoning — no compass)
    heading = target_heading % 360

def drive_forward_one_unit(diagonal=False):
    """
    Drive forward one grid unit using encoder feedback.
    diagonal=True scales distance by sqrt(2).
    Returns True if completed, False if timed out.
    """
    global enc_left_count, enc_right_count

    target_ticks = TICKS_PER_GRID_UNIT
    if diagonal:
        target_ticks = int(target_ticks * 1.414)

    # Reset encoder counts for this move
    enc_left_count = 0
    enc_right_count = 0

    motor_forward()
    start = time.ticks_ms()

    while True:
        avg_ticks = (enc_left_count + enc_right_count) / 2
        if avg_ticks >= target_ticks:
            motor_stop()
            return True

        if time.ticks_diff(time.ticks_ms(), start) > MOVE_TIMEOUT_MS:
            motor_stop()
            print("WARN: Move timed out")
            return False

        time.sleep_ms(5)

def execute_move(dx, dy):
    """
    Execute a single grid move: pivot to face (dx,dy) direction, then drive forward.
    Updates dead-reckoned position.
    """
    global pos_x, pos_y, moving

    if dx == 0 and dy == 0:
        return

    moving = True

    # Look up target heading
    target = DIRECTION_TO_HEADING.get((dx, dy))
    if target is None:
        # Clamp to sign values for safety
        dx = max(-1, min(1, dx))
        dy = max(-1, min(1, dy))
        target = DIRECTION_TO_HEADING.get((dx, dy))
        if target is None:
            moving = False
            return

    # Step 1: Pivot to face target direction
    pivot_to_heading(target)

    # Step 2: Drive forward one grid unit
    diagonal = (dx != 0 and dy != 0)
    drive_forward_one_unit(diagonal=diagonal)

    # Step 3: Update dead-reckoned position
    pos_x += dx
    pos_y += dy

    moving = False

# --- WIFI ---
def connect_wifi():
    """Connect to WiFi, retrying until successful."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print(f"WiFi already connected: {wlan.ifconfig()}")
        return wlan

    print(f"Connecting to WiFi: {WIFI_SSID}")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    max_wait = 20
    while max_wait > 0:
        status = wlan.status()
        if status < 0 or status >= 3:
            break
        max_wait -= 1
        led.toggle()
        time.sleep(0.5)

    if not wlan.isconnected():
        raise RuntimeError(f"WiFi connection failed, status={wlan.status()}")

    led.on()
    ip = wlan.ifconfig()[0]
    print(f"WiFi connected: {ip}")
    return wlan

# --- MQTT ---
mqtt_client = None

def mqtt_callback(topic, msg):
    """Handle incoming MQTT messages."""
    global last_command_time, last_seq

    topic = topic.decode()
    last_command_time = time.ticks_ms()

    # E-STOP: immediate motor kill
    if topic == f"hive/drone/{DRONE_ID}/estop":
        motor_stop()
        print("!!! ESTOP RECEIVED !!!")
        return

    # MOVE COMMAND
    if topic == f"hive/drone/{DRONE_ID}/move":
        try:
            cmd = json.loads(msg)
            dx = cmd.get("dx", 0)
            dy = cmd.get("dy", 0)
            seq = cmd.get("seq", 0)

            # Sequence deduplication
            if seq <= last_seq:
                return
            last_seq = seq

            # Don't queue moves while one is executing
            if moving:
                return

            execute_move(dx, dy)

        except (ValueError, KeyError) as e:
            print(f"Bad move cmd: {e}")

def connect_mqtt():
    """Connect to MQTT broker and subscribe to command topics."""
    global mqtt_client

    client_id = f"drone_{DRONE_ID}"
    mqtt_client = MQTTClient(client_id, MQTT_BROKER, port=MQTT_PORT)
    mqtt_client.set_callback(mqtt_callback)
    mqtt_client.connect()
    print(f"MQTT connected to {MQTT_BROKER}")

    # Subscribe to command topics
    mqtt_client.subscribe(f"hive/drone/{DRONE_ID}/move")
    mqtt_client.subscribe(f"hive/drone/{DRONE_ID}/estop")
    print(f"Subscribed: hive/drone/{DRONE_ID}/move, estop")

    return mqtt_client

def publish_position():
    """Publish current position + encoder data to queen."""
    if mqtt_client is None:
        return

    payload = json.dumps({
        "x": pos_x,
        "y": pos_y,
        "heading": heading,
        "enc_l": enc_left_count,
        "enc_r": enc_right_count,
    })
    mqtt_client.publish(f"hive/drone/{DRONE_ID}/position", payload)

# --- MAIN LOOP ---
def main():
    global last_command_time

    # Safety: stop motors on boot
    motor_stop()
    print(f"--- SLIMEHIVE DRONE [{DRONE_ID}] BOOT ---")
    print(f"Start pos: ({pos_x}, {pos_y}), heading: {heading}")

    # Phase 1: Connect WiFi
    wlan = connect_wifi()

    # Phase 2: Connect MQTT
    connect_mqtt()
    last_command_time = time.ticks_ms()

    # Phase 3: Main loop
    last_position_report = time.ticks_ms()

    print(f"--- DRONE [{DRONE_ID}] ONLINE ---")

    while True:
        # Check for incoming MQTT messages (non-blocking)
        try:
            mqtt_client.check_msg()
        except OSError as e:
            print(f"MQTT error: {e}, reconnecting...")
            motor_stop()
            time.sleep(2)
            try:
                connect_mqtt()
                last_command_time = time.ticks_ms()
            except Exception:
                print("MQTT reconnect failed, resetting...")
                machine.reset()

        # Command timeout safety: stop if no commands for too long
        if time.ticks_diff(time.ticks_ms(), last_command_time) > COMMAND_TIMEOUT_MS:
            if moving:
                motor_stop()
                print("WARN: Command timeout, motors stopped")

        # Periodic position report
        if time.ticks_diff(time.ticks_ms(), last_position_report) >= POSITION_REPORT_MS:
            publish_position()
            last_position_report = time.ticks_ms()
            led.toggle()

        # WiFi watchdog
        if not wlan.isconnected():
            print("WiFi lost! Stopping motors...")
            motor_stop()
            time.sleep(2)
            try:
                wlan = connect_wifi()
                connect_mqtt()
                last_command_time = time.ticks_ms()
            except Exception:
                print("Reconnect failed, resetting...")
                machine.reset()

        time.sleep_ms(10)

# --- ENTRY POINT ---
# Wrap everything in try/except so motors always stop on crash
try:
    main()
except KeyboardInterrupt:
    motor_stop()
    print("--- DRONE SHUTDOWN (keyboard) ---")
except Exception as e:
    motor_stop()
    print(f"FATAL: {e}")
    time.sleep(5)
    machine.reset()

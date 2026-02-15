# config_drone.py — Pico 2W Drone Configuration
# Flash this alongside main.py to your Pico 2W
# Edit these values per-drone before flashing

# --- WIFI ---
WIFI_SSID = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"

# --- MQTT ---
MQTT_BROKER = "192.168.1.100"  # Queen Pi IP address
MQTT_PORT = 1883

# --- DRONE IDENTITY ---
DRONE_ID = "P-01"              # Unique ID, P- prefix = physical drone
START_X = 50                   # Starting grid position
START_Y = 50

# --- MOTOR PINS (L298N H-Bridge) ---
# Motor 1 (Left)
MOTOR1_IN1 = 21               # Direction pin A
MOTOR1_IN2 = 20               # Direction pin B
MOTOR1_EN = 17                 # Enable (PWM speed control)

# Motor 2 (Right)
MOTOR2_IN1 = 19               # Direction pin A
MOTOR2_IN2 = 18               # Direction pin B
MOTOR2_EN = 16                 # Enable (PWM speed control)

# --- ENCODER PINS ---
ENCODER_LEFT = 14
ENCODER_RIGHT = 15

# --- CALIBRATION ---
PWM_FREQ = 1000                # Motor PWM frequency (Hz)
DUTY_FORWARD = 45000           # PWM duty for forward drive (0-65535)
DUTY_TURN = 40000              # PWM duty for pivot turns
TICKS_PER_GRID_UNIT = 20       # Encoder ticks per 1 grid unit of travel
TURN_DURATION_MS = 300         # Milliseconds to pivot 90 degrees
MOVE_TIMEOUT_MS = 3000         # Max time for a single forward move
COMMAND_TIMEOUT_MS = 2000      # Stop motors if no command received
POSITION_REPORT_MS = 500       # How often to report position

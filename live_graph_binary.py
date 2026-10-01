import serial
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# CONFIGURATION
PORT = 'COM9'   # Change this to your ESP32-S3 COM port
BAUD = 921600
MAX_PACKETS_PER_SEC = 200  # Set top speed of the gauge (tweak if needed)

# Connect to ESP32-S3
try:
    ser = serial.Serial(PORT, BAUD, timeout=0.05)
    print(f"Connected to ESP32-S3 on {PORT} at {BAUD} baud.")
except Exception as e:
    print(f"Error opening serial port: {e}")
    exit()

# State tracking for packet rate
packet_counter = 0
last_rate_calc = time.time()
current_pps = 0.0

# Set up Matplotlib Polar Figure for the Gauge
fig, ax = plt.subplots(figsize=(7, 5), subplot_kw={'projection': 'polar'})
fig.canvas.manager.set_window_title("Wi-Fi Airwave Activity Speedometer")

def draw_gauge_background():
    ax.clear()
    ax.set_theta_direction(-1)   # Clockwise
    ax.set_theta_offset(np.pi)    # Start at 9 o'clock (left)
    
    # Half-circle gauge from 0 to pi (180 degrees)
    ax.set_thetamin(0)
    ax.set_thetamax(180)
    
    # Colored Zones: Green (Quiet), Yellow (Moderate), Red (Congested)
    theta_green = np.linspace(0, np.pi * 0.45, 100)
    theta_yellow = np.linspace(np.pi * 0.45, np.pi * 0.75, 100)
    theta_red = np.linspace(np.pi * 0.75, np.pi, 100)
    
    ax.fill_between(theta_green, 0.8, 1.0, color='#4CAF50', alpha=0.8, label="Quiet")
    ax.fill_between(theta_yellow, 0.8, 1.0, color='#FFEB3B', alpha=0.8, label="Moderate")
    ax.fill_between(theta_red, 0.8, 1.0, color='#F44336', alpha=0.8, label="Heavy Traffic")
    
    # Hide radar grid lines and ticks
    ax.set_yticklabels([])
    ax.set_xticklabels([])
    ax.spines['polar'].set_visible(False)
    ax.grid(False)

def update(frame):
    global packet_counter, last_rate_calc, current_pps
    
    # Read incoming binary stream from ESP32-S3
    while ser.in_waiting > 0:
        header = ser.read(4)
        if header == b'\xAA\xBB\xCC\xDD':
            len_bytes = ser.read(2)
            if len(len_bytes) == 2:
                pkt_len = int.from_bytes(len_bytes, byteorder='little')
                ser.read(pkt_len) # Read full packet payload
                packet_counter += 1

    # Calculate packets per second (PPS) every 0.3 seconds
    now = time.time()
    dt = now - last_rate_calc
    if dt >= 0.3:
        current_pps = packet_counter / dt
        packet_counter = 0
        last_rate_calc = now

    # Map PPS to gauge angle (0 to pi radians)
    ratio = min(current_pps / MAX_PACKETS_PER_SEC, 1.0)
    needle_angle = ratio * np.pi

    # Redraw Gauge
    draw_gauge_background()
    
    # Draw Speedometer Needle
    ax.annotate(
        '',
        xy=(needle_angle, 0.85),
        xytext=(0, 0),
        arrowprops=dict(arrowstyle="->", color="black", lw=3.5)
    )
    
    # Center Pin
    ax.plot(0, 0, marker='o', markersize=10, color='black')
    
    # Dynamic status text depending on zone
    if ratio < 0.45:
        status_text = "STATUS: QUIET"
        status_color = "#2E7D32"
    elif ratio < 0.75:
        status_text = "STATUS: MODERATE"
        status_color = "#F57F17"
    else:
        status_text = "STATUS: HEAVY TRAFFIC"
        status_color = "#C62828"

    # Display Text Metrics
    ax.text(np.pi / 2, 0.45, f"{int(current_pps)} Pkts/sec", 
            ha='center', va='center', fontsize=18, fontweight='bold')
    ax.text(np.pi / 2, 0.2, status_text, 
            ha='center', va='center', fontsize=12, fontweight='bold', color=status_color)
    ax.set_title("Wi-Fi Airwave Density Meter", fontsize=15, pad=20, fontweight='bold')

# Run real-time animation loop
ani = animation.FuncAnimation(fig, update, interval=100, cache_frame_data=False)
plt.show()

ser.close()
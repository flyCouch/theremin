# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-12
# Time:    08:15:00
# Compiled on: 2026-05-12 08:15:00
# Description: V25.2 - Optimized Waveform Core + 100% Vol Calibration
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. CONFIGURATION ---
SAMPLE_RATE = 96000
MAX_VOICE_VOL = 32768  
VOL_CURVE = 1.5        # Log-style power curve

# --- 2. BOOT SEQUENCE ---
print("\n" + "="*60)
print("PROJECT: TIM'S THEREMIN (V25.2)")
print("COMPILE DATE: 2026-05-12 08:15:00")
print("STATUS: OPTIMIZED WAVEFORM ENGINE ONLINE...")
print("="*60 + "\n")

# --- 3. PIN MAPPING ---
i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
audio_l_pwm = machine.PWM(machine.Pin(16)); audio_r_pwm = machine.PWM(machine.Pin(17))

led_r = machine.PWM(machine.Pin(18))
led_g = machine.PWM(machine.Pin(19))
led_b = machine.PWM(machine.Pin(20))
for p in [led_r, led_g, led_b]: p.freq(1000)

joy_lx = machine.ADC(26); joy_ly = machine.ADC(27)
joy_rx = machine.ADC(28); joy_ry = machine.ADC(29)
sw_l = machine.Pin(22, machine.Pin.IN, machine.Pin.PULL_UP)
sw_r = machine.Pin(21, machine.Pin.IN, machine.Pin.PULL_UP)

# --- 4. SHARED STATE ---
state = {
    "f_l": 432.0, "f_r": 432.0,
    "v_l": 0.0,   "v_r": 0.0,
    "w_l": 0,     "w_r": 0,
    "smoothing": 0.32,
    "gate": 7500,
    "ready": False
}

# --- 5. AUDIO CORE WORKER (Optimized for speed) ---
def audio_worker(shared_state):
    # Pre-import and pre-bind for maximum loop speed
    from math import pi, sin
    l_out = machine.PWM(machine.Pin(16))
    r_out = machine.PWM(machine.Pin(17))
    l_out.freq(1000000); r_out.freq(1000000) # 1MHz Carrier
    
    # Helper outside the loop
    def get_sample(p, w):
        if w == 1: return 0.9 if p < pi else -0.9       # Square
        if w == 2: return (p / pi) - 1.0                # Saw
        if w == 3: return (abs((p / pi) - 1.0) * 2.0) - 1.0 # Tri
        return sin(p)                                   # Sine

    while not shared_state["ready"]: utime.sleep_ms(20)
    
    p_l = 0.0; p_r = 0.0
    TWO_PI = 2 * pi
    
    while True:
        # Calculate Phase
        p_l = (p_l + (TWO_PI * shared_state["f_l"] / SAMPLE_RATE)) % TWO_PI
        p_r = (p_r + (TWO_PI * shared_state["f_r"] / SAMPLE_RATE)) % TWO_PI
        
        # Pull values once per sample to ensure consistency
        v_l = shared_state["v_l"]
        v_r = shared_state["v_r"]
        w_l = shared_state["w_l"]
        w_r = shared_state["w_r"]

        # Final PWM Output
        l_out.duty_u16(int(32768 + (get_sample(p_l, w_l) * v_l)))
        r_out.duty_u16(int(32768 + (get_sample(p_r, w_r) * v_r)))

_thread.start_new_thread(audio_worker, (state,))

# --- 6. HARDWARE INIT ---
HAS_OLED = False
try:
    import ssd1306
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.write_cmd(0xA1); oled.write_cmd(0xC8); oled.invert(1)
    HAS_OLED = True
except: pass

state["ready"] = True
last_sw_l_time = 0; last_sw_r_time = 0; last_display_update = 0

# --- 7. MAIN LOOP ---
while True:
    s = state["smoothing"]
    now = utime.ticks_ms()
    wave_names = ["SINE", "SQUARE", "SAW", "TRI"]
    
    # 1. Inputs
    raw_lx, raw_ly = joy_lx.read_u16(), joy_ly.read_u16()
    raw_rx, raw_ry = joy_rx.read_u16(), joy_ry.read_u16()
    
    # 2. Wave Cycling
    if sw_l.value() == 0 and utime.ticks_diff(now, last_sw_l_time) > 250:
        state["w_l"] = (state["w_l"] + 1) % 4
        last_sw_l_time = now
    if sw_r.value() == 0 and utime.ticks_diff(now, last_sw_r_time) > 250:
        state["w_r"] = (state["w_r"] + 1) % 4
        last_sw_r_time = now

    # 3. Frequency Math
    t_f_l = 108.0 * (pow(480.0, (raw_lx / 65535)))
    t_f_r = 108.0 * (pow(480.0, (raw_rx / 65535)))
    
    # 4. Log-Volume Normalization (Ensuring 100% Reach)
    dist_l, dist_r = abs(raw_ly - 32767), abs(raw_ry - 32767)
    
    # Calibration: ensure we reach 1.0 even if joystick isn't perfectly at the physical limit
    range_max = 28500 - state["gate"] 
    norm_l = min(1.0, max(0, (dist_l - state["gate"]) / range_max))
    norm_r = min(1.0, max(0, (dist_r - state["gate"]) / range_max))
    
    # Volume Curve Calculation
    t_v_l = (norm_l ** VOL_CURVE) * MAX_VOICE_VOL
    t_v_r = (norm_r ** VOL_CURVE) * MAX_VOICE_VOL
    
    # Apply Smoothing
    state["f_l"] = (state["f_l"] * (1 - s)) + (t_f_l * s)
    state["f_r"] = (state["f_r"] * (1 - s)) + (t_f_r * s)
    state["v_l"] = (state["v_l"] * (1 - s)) + (t_v_l * s)
    state["v_r"] = (state["v_r"] * (1 - s)) + (t_v_r * s)
    
    # 5. Visuals
    led_r.duty_u16(int(raw_lx)); led_g.duty_u16(int(raw_rx))
    led_b.duty_u16(int((state["v_l"] + state["v_r"]) / 2))
    
    # 6. OLED (Reverted Layout)
    if HAS_OLED and utime.ticks_diff(now, last_display_update) > 100:
        oled.fill(0)
        oled.text("LYTTLE reSearch", 5, 0)
        oled.text(f"L : {int(state['f_l'])}Hz {wave_names[state['w_l']]}", 0, 18)
        oled.text(f"R : {int(state['f_r'])}Hz {wave_names[state['w_r']]}", 0, 34)
        oled.text(f"VOL: L{int(norm_l*100)}% R{int(norm_r*100)}%", 0, 52)
        oled.show()
        last_display_update = now
    
    utime.sleep(0.01)

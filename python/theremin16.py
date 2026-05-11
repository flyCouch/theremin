# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-11
# Time:    17:00:00
# Compiled on: 2026-05-11 17:00:00
# Description: V25.1 - 100% Vol Range + Optimized Log Scaling
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. CONFIGURATION ---
SAMPLE_RATE = 96000
MAX_VOICE_VOL = 32768  # Absolute max headroom for 5V rail
VOL_CURVE = 1.5        # Pro-audio Log slope

# --- 2. BOOT SEQUENCE ---
print("\n" + "="*60)
print("PROJECT: TIM'S THEREMIN (V25.1)")
print("COMPILE DATE: 2026-05-11 17:00:00")
print("STATUS: LOG VOLUME SCALING CALIBRATED...")
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
    "gate": 500,     # Slightly wider active range
    "ready": False
}

# --- 5. AUDIO CORE WORKER ---
def audio_worker(shared_state):
    import math
    import utime
    l_out = machine.PWM(machine.Pin(16)); r_out = machine.PWM(machine.Pin(17))
    l_out.freq(1000000); r_out.freq(1000000)
    
    while not shared_state["ready"]: utime.sleep_ms(20)
    
    p_l = 0.0; p_r = 0.0
    while True:
        p_l = (p_l + (2 * math.pi * shared_state["f_l"] / SAMPLE_RATE)) % (2 * math.pi)
        p_r = (p_r + (2 * math.pi * shared_state["f_r"] / SAMPLE_RATE)) % (2 * math.pi)
        
        def get_sample(p, w):
            if w == 1: return 0.6 if p < math.pi else -0.6
            if w == 2: return (p / math.pi) - 1.0
            if w == 3: return (abs((p / math.pi) - 1.0) * 2.0) - 1.0
            return math.sin(p)

        s_l = get_sample(p_l, shared_state["w_l"])
        s_r = get_sample(p_r, shared_state["w_r"])

        l_out.duty_u16(int(32768 + (s_l * shared_state["v_l"])))
        r_out.duty_u16(int(32768 + (s_r * shared_state["v_r"])))

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
    raw_lx = joy_lx.read_u16() 
    raw_ly = joy_ly.read_u16() 
    raw_rx = joy_rx.read_u16()
    raw_ry = joy_ry.read_u16()
    
    # 2. Wave Cycling
    if sw_l.value() == 0 and utime.ticks_diff(now, last_sw_l_time) > 250:
        state["w_l"] = (state["w_l"] + 1) % 4
        last_sw_l_time = now
    if sw_r.value() == 0 and utime.ticks_diff(now, last_sw_r_time) > 250:
        state["w_r"] = (state["w_r"] + 1) % 4
        last_sw_r_time = now

    # 3. Frequency Math
    t_f_l = 108.0 * (math.pow(480.0, (raw_lx / 65535)))
    t_f_r = 108.0 * (math.pow(480.0, (raw_rx / 65535)))
    
    # 4. Corrected Log-Volume Calibration
    dist_l = abs(raw_ly - 32767)
    dist_r = abs(raw_ry - 32767)
    
    # Calculate Normalized distance (0.0 to 1.0)
    # Using a max divisor of ~30000 to ensure we can hit 1.0 even if stick doesn't reach absolute 65535
    range_max = 32767 - state["gate"]
    norm_l = min(1.0, max(0, (dist_l - state["gate"]) / range_max))
    norm_r = min(1.0, max(0, (dist_r - state["gate"]) / range_max))
    
    # Apply Log Curve for Audio
    t_v_l = (norm_l ** VOL_CURVE) * MAX_VOICE_VOL
    t_v_r = (norm_r ** VOL_CURVE) * MAX_VOICE_VOL
    
    state["v_l"] = (state["v_l"] * (1 - s)) + (t_v_l * s)
    state["v_r"] = (state["v_r"] * (1 - s)) + (t_v_r * s)
    state["f_l"] = (state["f_l"] * (1 - s)) + (t_f_l * s)
    state["f_r"] = (state["f_r"] * (1 - s)) + (t_f_r * s)
    
    # 5. Visuals
    led_r.duty_u16(int(raw_lx)); led_g.duty_u16(int(raw_rx))
    led_b.duty_u16(int((state["v_l"] + state["v_r"]) / 2))
    
    # 6. OLED (Showing raw percentage for clarity)
    if HAS_OLED and utime.ticks_diff(now, last_display_update) > 100:
        oled.fill(0)
        oled.text("LYTTLE reSearch", 5, 0)
        oled.text(f"L : {int(state['f_l'])}Hz {wave_names[state['w_l']]}", 0, 18)
        oled.text(f"R : {int(state['f_r'])}Hz {wave_names[state['w_r']]}", 0, 34)
        oled.text(f"VOL: L{int(norm_l*100)}% R{int(norm_r*100)}%", 0, 52)
        oled.show()
        last_display_update = now
    
    utime.sleep(0.01)
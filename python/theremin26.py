# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-12
# Time:    12:15:00
# Compiled on: 2026-05-12 12:15:00
# Description: V26.2 - ADC Oversampling + Deadzone Logic for Noise Reduction
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. CONFIGURATION ---
SAMPLE_RATE = 96000
MAX_VOICE_VOL = 32768  
VOL_CURVE = 1.5        
TABLE_SIZE = 1024  
ADC_DEADZONE = 400     # Ignore jitter within this range of "rest"

# --- 2. BOOT SEQUENCE ---
SINE_TABLE = [math.sin(2 * math.pi * i / TABLE_SIZE) for i in range(TABLE_SIZE)]

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
    "gate": 3000,     
    "ready": False
}

# --- 5. AUDIO CORE WORKER ---
def audio_worker(shared_state, sine_table):
    l_out = machine.PWM(machine.Pin(16)); r_out = machine.PWM(machine.Pin(17))
    l_out.freq(1000000); r_out.freq(1000000)
    step_const = TABLE_SIZE / SAMPLE_RATE
    while not shared_state["ready"]: utime.sleep_ms(20)
    p_l = 0.0; p_r = 0.0
    while True:
        p_l = (p_l + (shared_state["f_l"] * step_const)) % TABLE_SIZE
        p_r = (p_r + (shared_state["f_r"] * step_const)) % TABLE_SIZE
        def get_sample(idx, p, w):
            if w == 1: return 0.9 if p < (TABLE_SIZE/2) else -0.9 
            if w == 2: return (p / (TABLE_SIZE/2)) - 1.0          
            if w == 3: return (abs((p / (TABLE_SIZE/2)) - 1.0) * 2.0) - 1.0 
            return sine_table[idx]                                
        l_out.duty_u16(int(32768 + (get_sample(int(p_l), p_l, shared_state["w_l"]) * shared_state["v_l"])))
        r_out.duty_u16(int(32768 + (get_sample(int(p_r), p_r, shared_state["w_r"]) * shared_state["v_r"])))

_thread.start_new_thread(audio_worker, (state, SINE_TABLE))

# --- 6. HELPERS ---
def read_smooth(adc_pin):
    # Oversampling: Read 4 times and average to kill spikes
    return (adc_pin.read_u16() + adc_pin.read_u16() + adc_pin.read_u16() + adc_pin.read_u16()) >> 2

# --- 7. HARDWARE INIT ---
HAS_OLED = False
try:
    import ssd1306
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    HAS_OLED = True
except: pass

state["ready"] = True
last_sw_l_time = 0; last_display_update = 0

# --- 8. MAIN LOOP ---
while True:
    s = state["smoothing"]
    now = utime.ticks_ms()
    wave_names = ["SINE", "SQUARE", "SAW", "TRI"]
    
    # 1. Inputs with Oversampling
    raw_lx, raw_ly = read_smooth(joy_lx), read_smooth(joy_ly)
    raw_rx, raw_ry = read_smooth(joy_rx), read_smooth(joy_ry)
    
    # 2. Wave Cycling (Buttons)
    if sw_l.value() == 0 and utime.ticks_diff(now, last_sw_l_time) > 250:
        state["w_l"] = (state["w_l"] + 1) % 4
        last_sw_l_time = now
    if sw_r.value() == 0 and utime.ticks_diff(now, last_sw_l_time) > 250: # shared debounce timer is fine
        state["w_r"] = (state["w_r"] + 1) % 4
        last_sw_l_time = now

    # 3. Frequency Math (X-Axis)
    t_f_l = 108.0 * (pow(480.0, (raw_lx / 65535)))
    t_f_r = 108.0 * (pow(480.0, (raw_rx / 65535)))
    
    # 4. Volume Scaling (Y-Axis) with Deadzone
    dist_l = abs(raw_ly - 32767)
    dist_r = abs(raw_ry - 32767)
    
    # If the distance from center is less than ADC_DEADZONE, force it to 0
    norm_l_raw = (dist_l - state["gate"]) / (28000 - state["gate"])
    norm_r_raw = (dist_r - state["gate"]) / (28000 - state["gate"])
    
    norm_l = min(1.0, max(0, norm_l_raw)) if dist_l > (state["gate"] + ADC_DEADZONE) else 0
    norm_r = min(1.0, max(0, norm_r_raw)) if dist_r > (state["gate"] + ADC_DEADZONE) else 0
    
    # 5. Update State
    state["v_l"] = (state["v_l"] * (1-s)) + ((norm_l**VOL_CURVE) * MAX_VOICE_VOL * s)
    state["v_r"] = (state["v_r"] * (1-s)) + ((norm_r**VOL_CURVE) * MAX_VOICE_VOL * s)
    state["f_l"] = (state["f_l"] * (1-s)) + (t_f_l * s)
    state["f_r"] = (state["f_r"] * (1-s)) + (t_f_r * s)
    
    # 6. Visuals & OLED
    led_r.duty_u16(int((raw_lx / 65535) * norm_l * 65535))
    led_b.duty_u16(int((raw_rx / 65535) * norm_r * 65535))
    led_g.duty_u16(int(((norm_l + norm_r) / 2) * 65535))
    
    if HAS_OLED and utime.ticks_diff(now, last_display_update) > 100:
        oled.fill(0)
        oled.text("tim's THEREMIN", 7, 0)
        oled.text(f"L: {int(state['f_l'])}Hz {wave_names[state['w_l']]}", 0, 18)
        oled.text(f"R: {int(state['f_r'])}Hz {wave_names[state['w_r']]}", 0, 34)
        oled.text(f"VOL: L{int(norm_l*100)}% R{int(norm_r*100)}%", 0, 52)
        oled.show()
        last_display_update = now
    
    utime.sleep(0.01)


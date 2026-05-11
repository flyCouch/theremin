# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-11
# Time:    13:15:00
# Compiled on: 2026-05-11 13:15:00
# Description: V24.7 - Full UI Recovery (OLED+1602) + Restore Pro-Audio Core
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. CONFIGURATION ---
SAMPLE_RATE = 96000
MAX_VOICE_VOL = 34000  
VOL_CURVE = 1.5        

# --- 2. BOOT SEQUENCE ---
print("\n" + "="*60)
print("PROJECT: TIM'S THEREMIN (V24.7)")
print("COMPILE DATE: 2026-05-11 13:15:00")
print("STATUS: DUAL-DISPLAY UI RESTORED...")
print("="*60 + "\n")

# --- 3. PIN MAPPING ---
i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
audio_l_pwm = machine.PWM(machine.Pin(16))
audio_r_pwm = machine.PWM(machine.Pin(17))

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
    "gate": 8500,
    "ready": False
}

# --- 5. AUDIO CORE WORKER ---
def audio_worker(shared_state):
    import math
    import utime
    l_out = machine.PWM(machine.Pin(16)); r_out = machine.PWM(machine.Pin(17))
    l_out.freq(100000); r_out.freq(100000)
    
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

# --- 6. HARDWARE INIT (OLED & 1602) ---
HAS_OLED = False
try:
    import ssd1306
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.write_cmd(0xA1); oled.write_cmd(0xC8); oled.invert(1)
    HAS_OLED = True
except: print("OLED Init Failed")

HAS_1602 = False
try:
    from machine_i2c_lcd import I2cLcd
    lcd = I2cLcd(i2c, 0x27, 2, 16)
    lcd.clear()
    HAS_1602 = True
except: print("1602 LCD Init Failed")

state["ready"] = True
last_sw_l_time, last_sw_r_time = 0, 0

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

    # 3. Frequency & Log-Volume Math
    t_f_l = 108.0 * (math.pow(256.0, (raw_lx / 65535)))
    t_f_r = 108.0 * (math.pow(256.0, (raw_rx / 65535)))
    
    dist_l, dist_r = abs(raw_ly - 32767), abs(raw_ry - 32767)
    norm_l = (dist_l - state["gate"]) / (32767 - state["gate"]) if dist_l > state["gate"] else 0
    norm_r = (dist_r - state["gate"]) / (32767 - state["gate"]) if dist_r > state["gate"] else 0
    
    t_v_l = (max(0, norm_l) ** VOL_CURVE) * MAX_VOICE_VOL
    t_v_r = (max(0, norm_r) ** VOL_CURVE) * MAX_VOICE_VOL
    
    # 4. Smoothing
    state["f_l"] = (state["f_l"] * (1 - s)) + (t_f_l * s)
    state["f_r"] = (state["f_r"] * (1 - s)) + (t_f_r * s)
    state["v_l"] = (state["v_l"] * (1 - s)) + (t_v_l * s)
    state["v_r"] = (state["v_r"] * (1 - s)) + (t_v_r * s)
    
    # 5. Visuals
    led_r.duty_u16(int(raw_lx)); led_g.duty_u16(int(raw_rx))
    led_b.duty_u16(int((state["v_l"] + state["v_r"]) / 2))
    
    # 6. DISPLAY UPDATES
    if HAS_OLED:
        oled.fill(0)
        oled.text("LYTTLE reSearch", 5, 0)
        oled.text(f"L: {int(state['f_l'])}Hz {wave_names[state['w_l']]}", 0, 18)
        oled.text(f"R: {int(state['f_r'])}Hz {wave_names[state['w_r']]}", 0, 34)
        oled.text(f"VOL: L{int(norm_l*100)}% R{int(norm_r*100)}%", 0, 52)
        oled.show()
        
    if HAS_1602:
        lcd.move_to(0, 0); lcd.putstr("tim's THEREMIN  ")
        lcd.move_to(0, 1); lcd.putstr(f"L{int(state['f_l']):4} R{int(state['f_r']):4}  ")
    
    utime.sleep(0.05)
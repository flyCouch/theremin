# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-11
# Time:    11:00:00
# Compiled on: 2026-05-11 11:00:00
# Description: V23.4 - Hi-Fi 44.1kHz + Center-Rest Volume + 4-Line UI
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. BOOT SEQUENCE ---
print("\n" + "="*60)
print("PROJECT: TIM'S THEREMIN (V23.4)")
print("COMPILE DATE: 2026-05-11 11:00:00")
print("STATUS: HI-FI AUDIO CORE ONLINE...")
print("="*60 + "\n")

# --- 2. PIN MAPPING ---
i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
audio_l_pwm = machine.PWM(machine.Pin(16))
audio_r_pwm = machine.PWM(machine.Pin(17))

# RGB LED (Visualizing the sound/axes)
led_r = machine.PWM(machine.Pin(18))
led_g = machine.PWM(machine.Pin(19))
led_b = machine.PWM(machine.Pin(20))
for p in [led_r, led_g, led_b]: p.freq(1000)

# Joysticks (GP26/27 = Left, GP28/29 = Right)
joy_lx = machine.ADC(26); joy_ly = machine.ADC(27)
joy_rx = machine.ADC(28); joy_ry = machine.ADC(29)

# Joystick Switches (GP22 = Left SW, GP21 = Right SW)
sw_l = machine.Pin(22, machine.Pin.IN, machine.Pin.PULL_UP)
sw_r = machine.Pin(21, machine.Pin.IN, machine.Pin.PULL_UP)

# --- 3. SHARED STATE ---
state = {
    "f_l": 432.0, "f_r": 432.0,
    "v_l": 0.0,   "v_r": 0.0,
    "w_l": 0,     "w_r": 0,     # 0:Sine, 1:Sq, 2:Saw, 3:Tri
    "smoothing": 0.32,          # Snappier response
    "gate": 9000,               # Solid deadzone for silence
    "ready": False
}

# --- 4. AUDIO CORE WORKER (CORE 1) ---
def audio_worker(shared_state):
    import math
    import utime
    SAMPLE_RATE = 96000  # Hi-Fi Sample Rate
    l_out = machine.PWM(machine.Pin(16)); r_out = machine.PWM(machine.Pin(17))
    l_out.freq(100000); r_out.freq(100000)
    
    while not shared_state["ready"]: utime.sleep_ms(20)
    
    p_l = 0.0; p_r = 0.0
    while True:
        p_l = (p_l + (2 * math.pi * shared_state["f_l"] / SAMPLE_RATE)) % (2 * math.pi)
        p_r = (p_r + (2 * math.pi * shared_state["f_r"] / SAMPLE_RATE)) % (2 * math.pi)
        
        # Wave Generation Logic
        # Left
        wl = shared_state["w_l"]
        if wl == 1: s_l = 0.6 if p_l < math.pi else -0.6
        elif wl == 2: s_l = (p_l / math.pi) - 1.0
        elif wl == 3: s_l = (abs((p_l / math.pi) - 1.0) * 2.0) - 1.0
        else: s_l = math.sin(p_l)

        # Right
        wr = shared_state["w_r"]
        if wr == 1: s_r = 0.6 if p_r < math.pi else -0.6
        elif wr == 2: s_r = (p_r / math.pi) - 1.0
        elif wr == 3: s_r = (abs((p_r / math.pi) - 1.0) * 2.0) - 1.0
        else: s_r = math.sin(p_r)

        l_out.duty_u16(int(32768 + (s_l * shared_state["v_l"])))
        r_out.duty_u16(int(32768 + (s_r * shared_state["v_r"])))

_thread.start_new_thread(audio_worker, (state,))

# --- 5. HARDWARE INIT ---
HAS_OLED = False
try:
    import ssd1306
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.write_cmd(0xA1); oled.write_cmd(0xC8); oled.invert(1)
    HAS_OLED = True
except: print("OLED Missing")

try:
    from machine_i2c_lcd import I2cLcd
    lcd = I2cLcd(i2c, 0x27, 2, 16)
    lcd.clear()
    HAS_1602 = True
except: HAS_1602 = False

state["ready"] = True
last_sw_l_time = 0
last_sw_r_time = 0

# --- 6. MAIN LOOP ---
while True:
    s = state["smoothing"]
    gate = state["gate"]
    wave_names = ["SINE", "SQUARE", "SAW", "TRI"]
    now = utime.ticks_ms()
    
    # 1. Inputs (Frequency on X, Volume on Y)
    raw_lx = joy_lx.read_u16() 
    raw_ly = joy_ly.read_u16() 
    raw_rx = joy_rx.read_u16()
    raw_ry = joy_ry.read_u16()
    
    # 2. Independent Wave Cycling via JS Switches
    if sw_l.value() == 0 and utime.ticks_diff(now, last_sw_l_time) > 250:
        state["w_l"] = (state["w_l"] + 1) % 4
        last_sw_l_time = now
    
    if sw_r.value() == 0 and utime.ticks_diff(now, last_sw_r_time) > 250:
        state["w_r"] = (state["w_r"] + 1) % 4
        last_sw_r_time = now

    # 3. Frequency & Center-Silence Calculations
    t_f_l = 108.0 * (math.pow(480.0, (raw_lx / 65535)))
    t_f_r = 108.0 * (math.pow(480.0, (raw_rx / 65535)))
    
    dist_l = abs(raw_ly - 32767)
    dist_r = abs(raw_ry - 32767)
    t_v_l = ((dist_l / 32767) * 44000) if dist_l > gate else 0
    t_v_r = ((dist_r / 32767) * 44000) if dist_r > gate else 0
    
    # 4. Apply Smoothing to Shared State
    state["f_l"] = (state["f_l"] * (1 - s)) + (t_f_l * s)
    state["f_r"] = (state["f_r"] * (1 - s)) + (t_f_r * s)
    state["v_l"] = (state["v_l"] * (1 - s)) + (t_v_l * s)
    state["v_r"] = (state["v_r"] * (1 - s)) + (t_v_r * s)
    
    # 5. Visuals (RGB LED follows Joystick position)
    led_r.duty_u16(int(raw_lx))
    led_g.duty_u16(int(raw_rx))
    led_b.duty_u16(int((state["v_l"] + state["v_r"]) / 2))
    
    # 6. Display Updates
    if HAS_OLED:
        oled.fill(0)
        oled.text("LYTTLE reSearch", 5, 0)
        oled.text(f"L : {int(state['f_l'])}Hz {wave_names[state['w_l']]}", 0, 18)
        oled.text(f"R : {int(state['f_r'])}Hz {wave_names[state['w_r']]}", 0, 34)
        oled.text(f"VOL: L{int(state['v_l']/340)}% R{int(state['v_r']/340)}%", 0, 52)
        oled.show()
        
    if HAS_1602:
        lcd.move_to(0, 0); lcd.putstr(f"L:{wave_names[state['w_l']][:3]} R:{wave_names[state['w_r']][:3]}  ")
        lcd.move_to(0, 1); lcd.putstr(f"L{int(state['f_l']):4} R{int(state['f_r']):4}  ")
    
    utime.sleep(0.01)
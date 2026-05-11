# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-11
# Time:    09:45:00
# Compiled on: 2026-05-11 09:45:00
# Description: V22.6 - Center-Out Volume (Rest = Silence) + Full UI
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. BOOT HEADER ---
print("\n" + "="*60)
print("PROJECT: TIM'S THEREMIN (V22.6)")
print("COMPILE DATE: 2026-05-11 09:45:00")
print("STATUS: CENTER-SILENCE CALIBRATED...")
print("="*60 + "\n")

# --- 2. PIN MAPPING ---
i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
audio_l_pwm = machine.PWM(machine.Pin(16))
audio_r_pwm = machine.PWM(machine.Pin(17))

# RGB LED
led_r = machine.PWM(machine.Pin(18))
led_g = machine.PWM(machine.Pin(19))
led_b = machine.PWM(machine.Pin(20))
for p in [led_r, led_g, led_b]: p.freq(1000)

# Keypad Matrix
row_pins = [machine.Pin(p, machine.Pin.OUT) for p in [6, 7, 8, 9]]
col_pins = [machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_DOWN) for p in [10, 11, 12, 13]]
key_map = [["1","2","3","4"],["5","6","7","18"],["9","10","11","12"],["13","14","15","16"]]

# Joysticks
joy_lx = machine.ADC(26); joy_ly = machine.ADC(27)
joy_rx = machine.ADC(28); joy_ry = machine.ADC(29)

# --- 3. SHARED STATE ---
state = {
    "f_l": 432.0, "f_r": 432.0,
    "v_l": 0.0,   "v_r": 0.0,
    "wave": 0,
    "smoothing": 0.22, # Slightly higher smoothing for cleaner volume swells
    "gate": 8000,      # Increased gate for a solid "dead center" silence
    "ready": False
}

# --- 4. AUDIO CORE WORKER (CORE 1) ---
def audio_worker(shared_state):
    import math
    import utime
    SAMPLE_RATE = 22050
    l_out = machine.PWM(machine.Pin(16)); r_out = machine.PWM(machine.Pin(17))
    l_out.freq(100000); r_out.freq(100000)
    
    while not shared_state["ready"]: utime.sleep_ms(20)
    
    p_l = 0.0; p_r = 0.0
    while True:
        p_l = (p_l + (2 * math.pi * shared_state["f_l"] / SAMPLE_RATE)) % (2 * math.pi)
        p_r = (p_r + (2 * math.pi * shared_state["f_r"] / SAMPLE_RATE)) % (2 * math.pi)
        
        w = shared_state["wave"]
        if w == 1: # SQUARE
            s_l, s_r = (0.6, 0.6) if p_l < math.pi else (-0.6, -0.6)
        elif w == 2: # SAW
            s_l, s_r = (p_l / math.pi) - 1.0, (p_r / math.pi) - 1.0
        elif w == 3: # TRI
            s_l = (abs((p_l / math.pi) - 1.0) * 2.0) - 1.0
            s_r = (abs((p_r / math.pi) - 1.0) * 2.0) - 1.0
        else: # SINE
            s_l, s_r = math.sin(p_l), math.sin(p_r)

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

def get_key():
    for r in range(4):
        row_pins[r].value(1)
        for c in range(4):
            if col_pins[c].value():
                row_pins[r].value(0)
                return key_map[r][c]
        row_pins[r].value(0)
    return None

state["ready"] = True

# --- 6. MAIN LOOP ---
while True:
    s = state["smoothing"]
    gate = state["gate"]
    
    # 1. Inputs (Standard reads, no inversion needed for distance math)
    raw_lx = 65535 - joy_lx.read_u16() 
    raw_ly = joy_ly.read_u16() 
    raw_rx = joy_rx.read_u16()
    raw_ry = joy_ry.read_u16()
    
    # 2. Freq Targets (X-Axis)
    t_f_l = 108.0 * (math.pow(64.0, (raw_lx / 65535)))
    t_f_r = 108.0 * (math.pow(64.0, (raw_rx / 65535)))
    
    # 3. Volume Targets (Distance from Center Math)
    # 32767 is center. we find absolute distance from it.
    dist_l = abs(raw_ly - 32767)
    dist_r = abs(raw_ry - 32767)
    
    # If distance is small (near center), keep it 0. Otherwise scale to max volume.
    t_v_l = ((dist_l / 32767) * 28000) if dist_l > gate else 0
    t_v_r = ((dist_r / 32767) * 28000) if dist_r > gate else 0
    
    # 4. Smoothing
    state["f_l"] = (state["f_l"] * (1 - s)) + (t_f_l * s)
    state["f_r"] = (state["f_r"] * (1 - s)) + (t_f_r * s)
    state["v_l"] = (state["v_l"] * (1 - s)) + (t_v_l * s)
    state["v_r"] = (state["v_r"] * (1 - s)) + (t_v_r * s)
    
    # 5. Visuals
    led_r.duty_u16(int(raw_lx))
    led_g.duty_u16(int(raw_rx))
    led_b.duty_u16(int((state["v_l"] + state["v_r"]) / 2))
    
    # 6. Keypad
    key = get_key()
    if key == "1": state["wave"] = 0 
    if key == "5": state["wave"] = 1 
    if key == "9": state["wave"] = 2 
    if key == "13": state["wave"] = 3 

    # 7. Displays
    wave_names = ["SINE", "SQUARE", "SAW", "TRI"]
    if HAS_OLED:
        oled.fill(0)
        oled.text("LYTTLE reSearch", 5, 0)
        oled.text(f"L:{int(state['f_l'])}Hz V:{int(state['v_l']/280)}%", 0, 22)
        oled.text(f"R:{int(state['f_r'])}Hz V:{int(state['v_r']/280)}%", 0, 40)
        oled.text(f"MODE: {wave_names[state['wave']]}", 0, 56)
        oled.show()
        
    if HAS_1602:
        lcd.move_to(0, 0); lcd.putstr("TIM'S THEREMIN  ")
        lcd.move_to(0, 1); lcd.putstr(f"L{int(state['f_l']):4} R{int(state['f_r']):4}  ")
    
    utime.sleep(0.05)
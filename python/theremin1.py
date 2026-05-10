# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-10
# Time:    19:30:00
# Compiled on: 2026-05-10 19:30:00
# Description: Multi-Tone Engine with Keypad Control & Dual Displays
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. PIN MAPPING ---
i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)
audio_l_pwm = machine.PWM(machine.Pin(16))
audio_r_pwm = machine.PWM(machine.Pin(17))

# RGB LED
led_r = machine.PWM(machine.Pin(18))
led_g = machine.PWM(machine.Pin(19))
led_b = machine.PWM(machine.Pin(20))
for p in [led_r, led_g, led_b]: p.freq(1000)

# Keypad Matrix (Rows: 6-9, Cols: 10-13)
row_pins = [machine.Pin(p, machine.Pin.OUT) for p in [6, 7, 8, 9]]
col_pins = [machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_DOWN) for p in [10, 11, 12, 13]]
key_map = [["1","2","3","A"],["4","5","6","B"],["7","8","9","C"],["*","0","#","D"]]

# --- 2. SHARED STATE ---
state = {
    "f_l": 432.0, "f_r": 432.0,
    "wave": 0, # 0:Sine, 1:Square, 2:Saw, 3:Tri
    "ready": False
}

# --- 3. AUDIO WORKER (CORE 1) ---
def audio_worker():
    global state
    while not state["ready"]: utime.sleep_ms(20)
    audio_l_pwm.freq(100000); audio_r_pwm.freq(100000)
    p_l = 0.0; p_r = 0.0
    while True:
        p_l = (p_l + (2 * math.pi * state["f_l"] / 11025)) % (2 * math.pi)
        p_r = (p_r + (2 * math.pi * state["f_r"] / 11025)) % (2 * math.pi)
        
        w = state["wave"]
        if w == 1: # SQUARE
            s_l = 0.6 if p_l < math.pi else -0.6
            s_r = 0.6 if p_r < math.pi else -0.6
        elif w == 2: # SAW
            s_l = (p_l / math.pi) - 1.0
            s_r = (p_r / math.pi) - 1.0
        elif w == 3: # TRI
            s_l = (abs((p_l / math.pi) - 1.0) * 2.0) - 1.0
            s_r = (abs((p_r / math.pi) - 1.0) * 2.0) - 1.0
        else: # SINE
            s_l, s_r = math.sin(p_l), math.sin(p_r)

        audio_l_pwm.duty_u16(int(32768 + (s_l * 24000)))
        audio_r_pwm.duty_u16(int(32768 + (s_r * 24000)))

_thread.start_new_thread(audio_worker, ())

# --- 4. HARDWARE INIT ---
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
    lcd.putstr("TIM'S THEREMIN\nINIT COMPLETE")
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

# --- 5. MAIN LOOP ---
while True:
    # 1. Update Frequencies
    raw_l, raw_r = machine.ADC(26).read_u16(), machine.ADC(28).read_u16()
    state["f_l"] = 108.0 * (math.pow(16.0, (raw_l / 65535)))
    state["f_r"] = 108.0 * (math.pow(16.0, (raw_r / 65535)))
    
    # 2. RGB Visuals
    led_r.duty_u16(raw_l); led_g.duty_u16(raw_r); led_b.duty_u16(int((raw_l+raw_r)/4))
    
    # 3. Keypad Input (Wave Selection)
    key = get_key()
    if key == "1": state["wave"] = 0 # Sine
    if key == "2": state["wave"] = 1 # Square
    if key == "3": state["wave"] = 2 # Saw
    if key == "4": state["wave"] = 3 # Tri

    # 4. Display Updates
    wave_names = ["SINE", "SQUARE", "SAW", "TRI"]
    if HAS_OLED:
        oled.fill(0)
        oled.text(f"MODE: {wave_names[state['wave']]}", 0, 0)
        oled.text(f"L: {int(state['f_l'])}Hz", 0, 25)
        oled.text(f"R: {int(state['f_r'])}Hz", 0, 45)
        oled.show()
        
    # 5. DRAW TO 1602 LCD
    if HAS_1602:
        lcd.move_to(0, 1)
        lcd.putstr(f"L{int(state['f_l']):4} R{int(state['f_r']):4}  ")
    
    utime.sleep(0.05)
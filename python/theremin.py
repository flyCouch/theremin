# **************************************************************************
# Project: Tim's Theremin (Lyttle reSearch Unified)
# File:    main.py
# Date:    2026-05-10
# Time:    23:45:00
# Compiled on: 2026-05-10 23:45:00
# Description: Full Production Logic - Dual Screen + RGB LED + Multi-Core
# **************************************************************************

import machine
import utime
import math
import _thread

# --- 1. BOOT SEQUENCE ---
print("\n" + "="*60)
print("PROJECT: TIM'S THEREMIN")
print("COMPILE DATE: 2026-05-10 23:45:00")
print("STATUS: HARDWARE DEPLOYMENT...")
print("="*60 + "\n")

# --- 2. PIN MAPPING ---
# I2C (Screens)
i2c = machine.I2C(0, sda=machine.Pin(4), scl=machine.Pin(5), freq=400000)

# Audio (Speakers)
audio_l_pwm = machine.PWM(machine.Pin(16))
audio_r_pwm = machine.PWM(machine.Pin(17))

# RGB LED (Pins 18, 19, 20)
led_r = machine.PWM(machine.Pin(18))
led_g = machine.PWM(machine.Pin(19))
led_b = machine.PWM(machine.Pin(20))
for p in [led_r, led_g, led_b]: p.freq(1000)

# Joysticks (ADC)
joy_lx = machine.ADC(26)
joy_rx = machine.ADC(28)

# --- 3. SHARED STATE ---
state = {
    "f_l": 432.0, "f_r": 432.0,
    "v_ll": 1.0,  "v_rr": 1.0,
    "ready": False
}

# --- 3. SHARED STATE (Add wave type) ---
state = {
    "f_l": 432.0, "f_r": 432.0,
    "v_ll": 1.0,  "v_rr": 1.0,
    "wave": 1,    # 0:Sine, 1:Square, 2:Saw, 3:Tri
    "ready": False
}

# --- 4. AUDIO CORE WORKER (CORE 1) ---
def audio_worker():
    global state, audio_l_pwm, audio_r_pwm
    while not state["ready"]: utime.sleep_ms(20)
    
    audio_l_pwm.freq(100000); audio_r_pwm.freq(100000)
    p_l = 0.0; p_r = 0.0
    
    while True:
        # Increment phases
        p_l = (p_l + (2 * math.pi * state["f_l"] / 11025)) % (2 * math.pi)
        p_r = (p_r + (2 * math.pi * state["f_r"] / 11025)) % (2 * math.pi)
        
        # Generator Selection
        w = state["wave"]
        
        if w == 0: # SINE
            s_l, s_r = math.sin(p_l), math.sin(p_r)
            
        elif w == 1: # SQUARE
            s_l = 0.8 if p_l < math.pi else -0.8
            s_r = 0.8 if p_r < math.pi else -0.8
            
        elif w == 2: # SAWTOOTH
            s_l = (p_l / math.pi) - 1.0
            s_r = (p_r / math.pi) - 1.0
            
        elif w == 3: # TRIANGLE
            s_l = (abs((p_l / math.pi) - 1.0) * 2.0) - 1.0
            s_r = (abs((p_r / math.pi) - 1.0) * 2.0) - 1.0
            
        else: # Default back to Sine
            s_l, s_r = math.sin(p_l), math.sin(p_r)
        
        # Output to PWM
        audio_l_pwm.duty_u16(int(32768 + (s_l * 24000)))
        audio_r_pwm.duty_u16(int(32768 + (s_r * 24000)))        

_thread.start_new_thread(audio_worker, ())

# --- 5. MAIN ENGINE (CORE 0) ---
HAS_OLED = False
HAS_1602 = False

try:
    import ssd1306
    oled = ssd1306.SSD1306_I2C(128, 64, i2c)
    oled.write_cmd(0xA1); oled.write_cmd(0xC8) # Rotate 180
    oled.invert(1)
    HAS_OLED = True
except: print("OLED not detected.")

try:
    from machine_i2c_lcd import I2cLcd
    lcd = I2cLcd(i2c, 0x27, 2, 16) # Address 0x27
    lcd.clear()
    lcd.putstr("TIM'S THEREMIN\nINIT COMPLETE")
    HAS_1602 = True
except: print("1602 not detected.")

state["ready"] = True
print("Employer Ready. Worker node active.")

while True:
    # 1. Read Inputs
    raw_l = joy_lx.read_u16()
    raw_r = joy_rx.read_u16()

    # 2. Update frequencies
    state["f_l"] = 108.0 * (math.pow(16.0, (raw_l / 65535)))
    state["f_r"] = 108.0 * (math.pow(16.0, (raw_r / 65535)))
    
    # 3. Update RGB LED 
    # Left frequency maps to Red, Right to Green. Blue is a mix.
    led_r.duty_u16(raw_l)
    led_g.duty_u16(raw_r)
    led_b.duty_u16(int((raw_l + raw_r) / 2))
    
    # 4. DRAW TO OLED
    if HAS_OLED:
        oled.fill(0) # Clear the inverted background
        oled.text("TIM'S THEREMIN", 8, 0)
        oled.text(f"LEFT: {int(state['f_l'])}Hz", 0, 25)
        oled.text(f"RGHT: {int(state['f_r'])}Hz", 0, 45)
        oled.show() 

    # 5. DRAW TO 1602 LCD
    if HAS_1602:
        lcd.move_to(0, 1)
        lcd.putstr(f"L{int(state['f_l']):4} R{int(state['f_r']):4}  ")

    utime.sleep(0.05)
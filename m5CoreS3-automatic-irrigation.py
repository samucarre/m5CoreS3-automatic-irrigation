# 💧 M5CoreS3 Automatic Irrigation System
#
# This project implements a remote-controlled, offline-friendly automatic irrigation system
# utilizing the M5Stack CoreS3 as the central controller. It features a web interface,
# hosted directly on the device, for easy configuration of irrigation schedules and manual controls.
# The system is designed to manage a solar-powered water pump based on user-defined settings
# stored locally. It also integrates with an external Real-Time Clock (RTC HYM8563) for reliable
# timekeeping, ensuring accurate irrigation cycles even when the device is powered off or
# loses Wi-Fi connectivity.
#
# Key Features:
# - Configurable irrigation start hour (09:00 - 20:00).
# - Adjustable irrigation duration (5 - 60 minutes, in 5-minute increments).
# - Manual test irrigation mode accessible via the web interface.
# - Real-time status monitoring of RTC, relay, and Wi-Fi Access Point on the M5CoreS3 screen.
# - Operates autonomously using Access Point mode, requiring no external internet connection for basic functionality.
# - Persistent configuration storage in a local 'config.json' file.

# === IMPORTS AND INITIAL SETUP ===
import M5
from M5 import *
import time
import network
import socket
import ujson
from machine import I2C, Pin
import _thread

# === GENERAL CONFIGURATION ===
CONFIG_FILE = 'config.json'
RELAY_PIN = Pin(5, Pin.OUT)  # GPIO 5 confirmado, hace clic
RTC_I2C_ADDR = 0x51

# Initialize I2C bus
i2c = I2C(1, scl=Pin(1), sda=Pin(2))

# === GLOBAL VARIABLES ===
title0 = labelInfo = labelInfo2 = labelStatus = labelRelay = labelWifi = None
rtcStatus = relayStatus =  None
systemOn = False
startTime = 0
rtc_ok = None
labelWifiStatus = None
testMode = False
cancelled = False

# === HTML FOR WEB INTERFACE ===

def generate_html(current_time, config, show_stream=False):
    hour_options = "\n".join("<option value='{:02}:00'>{:02}:00</option>".format(h, h) for h in range(9, 21))
    duration_options = "\n".join("<option value='{0}'>{0} min</option>".format(i) for i in range(5, 65, 5))
    hour_text = config['hora'] if config['hora'] else "Off"
    duration_text = f"{config['duracion']} min" if config['duracion'] else "Off"

    return f"""<!DOCTYPE html><html><head><title>Irrigation Settings</title>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <style>
    body {{ font-family: Arial; background: #eef; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .form-container {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.15); text-align: center; width: 90%; max-width: 320px; }}
    h2 {{ color: #006699; font-size: 18px; margin-bottom: 15px; }}
    .info, .new-config {{ font-size: 13px; margin-bottom: 15px; color: #333; line-height: 1.5; }}
    .bold {{ font-weight: bold; margin-top: 10px; margin-bottom: 5px; font-size: 14px; color: #222; }}
    label {{ display: block; font-size: 14px; margin: 10px 0 4px; }}
    select, input[type='submit'], button {{ font-size: 14px; padding: 5px; width: 100%; border-radius: 4px; border: 1px solid #ccc; text-align: center; margin-bottom: 12px; }}
    input[type='submit'], button {{ color: white; border: none; padding: 8px; font-size: 14px; cursor: pointer; margin-top: 8px; }}
    .stop {{ background-color: #cc0000; }} .test {{ background-color: #009900; }} .stream {{ background-color: #006699; }}
    </style>

    </head><body>
    <div class='form-container'>
      <h2>Irrigation Settings</h2>
      <div class='info'>
        <div class='bold'>Current Configuration:</div>
        Current time: {current_time}<br>
        Scheduled time: {hour_text}<br>
        Duration: {duration_text}
        <form method='POST'><input type='hidden' name='apagar' value='1'><button type='submit' class='stop'>Turn off irrigation system</button></form>
        <form method='POST'><input type='hidden' name='probar' value='1'><button type='submit' class='test'>Test irrigation system</button></form>

      </div>
      <div class='new-config'>
        <div class='bold'>New Configuration:</div>
        <form method='POST'>
          <label for='hora'>Time:</label>
          <select name='hora' required>{hour_options}</select>
          <label for='duracion'>Duration (minutes):</label>
          <select name='duracion' required>{duration_options}</select>
          <input type='submit' value='Save'>
        </form>
      </div>
    </div></body></html>"""

# === CONFIGURATION ===
def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return ujson.load(f)
    except:
        return {'hora': '07:00', 'duracion': 10}

def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        ujson.dump(data, f)

# === RELAY CONTROL ===
def relay_on():
    try:
        RELAY_PIN.on()
        print("[RELE] ACTIVADO")  # debug
        relayStatus.setText("ON")
        relayStatus.setColor(0x009900, 0xffffff)
    except Exception as e:
        print("[RELE] ERROR AL ACTIVAR:", e)
        relayStatus.setText("ERROR")
        relayStatus.setColor(0xcc0000, 0xffffff)

def relay_off():
    try:
        RELAY_PIN.off()
        print("[RELE] DESACTIVADO")  # debug
        relayStatus.setText("OFF")
        relayStatus.setColor(0xcc0000, 0xffffff)
    except Exception as e:
        print("[RELE] ERROR AL DESACTIVAR:", e)
        relayStatus.setText("ERROR")
        relayStatus.setColor(0xcc0000, 0xffffff)

# === RTC CHECK ===
def get_rtc_time():
    global rtc_ok
    try:
        # Leer desde el registro 0x02 (segundos) hasta 0x08 (año) - 7 bytes
        data = i2c.readfrom_mem(RTC_I2C_ADDR, 0x02, 7)

        def bcd2dec(bcd):  # Conversión BCD a decimal
            return (bcd >> 4) * 10 + (bcd & 0x0F)

        seconds = bcd2dec(data[0] & 0x7F)
        minutes = bcd2dec(data[1] & 0x7F)
        hours = bcd2dec(data[2] & 0x3F)
        day = bcd2dec(data[3] & 0x3F)
        weekday = bcd2dec(data[4] & 0x07)
        month = bcd2dec(data[5] & 0x1F)
        year = bcd2dec(data[6]) + 2000

        if rtc_ok is not True:
            rtcStatus.setText("ON")
            rtcStatus.setColor(0x009900, 0xffffff)
            rtc_ok = True

        return hours, minutes  # Lo que usa la web

    except:
        if rtc_ok is not False:
            rtcStatus.setText("OFF")
            rtcStatus.setColor(0xcc0000, 0xffffff)
            rtc_ok = False
        return None

# === TEST IRRIGATION FUNCTION ===
def test_irrigation_async():
    global testMode, startTime, systemOn
    print("[TEST] Iniciando test de riego manual desde web")
    systemOn = True
    testMode = True
    startTime = time.time()
    relay_on()  # <-- activa el relé directamente aquí

# === HTTP REQUEST HANDLING ===
def handle_client(conn):
    req = conn.recv(1024)
    req_str = req.decode('utf-8')
    config = load_config()
    show_stream = False

    if 'POST' in req_str:
        body = req_str.split('\r\n\r\n')[1]
        params = {}
        for p in body.split('&'):
            if '=' in p:
                k, v = p.split('=', 1)
                params[k] = v
        if 'apagar' in params:
          print("[HTTP] Apagar sistema solicitado")
          config = {'hora': '', 'duracion': 0}
          save_config(config)
          relay_off()
          systemOn = False
          testMode = False
          global cancelled
          cancelled = True  # <- cancela el test manual
        elif 'probar' in params:
            print("[HTTP] Test irrigation system solicitado")
            _thread.start_new_thread(test_irrigation_async, ())
        else:
            hora = params.get('hora', '').replace('%3A', ':')
            duracion = int(params.get('duracion', 0))
            config = {'hora': hora, 'duracion': duracion}
            save_config(config)

    now = get_rtc_time()
    current_time = "--:--" if not now else '{:02}:{:02}'.format(now[0], now[1])
    html = generate_html(current_time, config, show_stream=show_stream)
    conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\n\n' + html)
    conn.close()

def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid='RIEGO_M5', password='Samuel123', authmode=3)
    while not ap.active():
        time.sleep(1)

    ip = ap.ifconfig()[0]

    labelWifi.setText("WIFI:\n          IP: {}".format(ip))
    labelWifi.setColor(0x000000, 0xffffff)  # Black text

    labelWifiStatus.setText("ON")
    labelWifiStatus.setColor(0x009900, 0xffffff)  # Green for "ON" only

    labelInfo.setText("SSID: RIEGO_M5")
    labelInfo2.setText("PASS: Samuel123")


# === WEB SERVER ===
def run_server():
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    try:
        s.bind(addr)
    except OSError:
        print("Server already running")
        return
    s.listen(1)
    s.settimeout(0.1)  # << more responsive
    while True:
        try:
            cl, addr = s.accept()
            handle_client(cl)
        except:
            pass  # No new connection, continue loop

# === INITIAL SCREEN SETUP ===
def setup():
    global title0, labelInfo, labelInfo2, labelStatus, labelRelay, labelWifi, rtcStatus, relayStatus, labelWifiStatus
    M5.begin()
    Widgets.fillScreen(0xffffff)
    title0 = Widgets.Title("Solar Irrigation", 3, 0xffffff, 0x00aaff, Widgets.FONTS.DejaVu18)
    labelWifi = Widgets.Label("WIFI:", 10, 40, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelWifiStatus = Widgets.Label("OFF", 65, 40, 1.0, 0xcc0000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelInfo = Widgets.Label("SSID: -", 10, 70, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelInfo2 = Widgets.Label("PASS: -", 10, 100, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelStatus = Widgets.Label("RTC:", 10, 130, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    rtcStatus = Widgets.Label("OFF", 60, 130, 1.0, 0xcc0000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelRelay = Widgets.Label("RELAY:", 10, 160, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    relayStatus = Widgets.Label("OFF", 81, 160, 1.0, 0xcc0000, 0xffffff, Widgets.FONTS.DejaVu18)
    start_ap()
    _thread.start_new_thread(run_server, ())

# === MAIN LOOP ===
def loop():
    global systemOn, startTime, testMode, cancelled
    M5.update()
    now = get_rtc_time()

    if now and not testMode:
        config = load_config()
        current_time = '{:02}:{:02}'.format(now[0], now[1])
        if current_time == config['hora'] and not systemOn:
            relay_on()
            startTime = time.time()
            systemOn = True

    if systemOn:
        if cancelled:
            relay_off()
            systemOn = False
            testMode = False
            cancelled = False  # resetea la bandera
            return

        relay_on()
        duration = 60 if testMode else load_config()['duracion'] * 60
        if time.time() - startTime > duration:
            relay_off()
            systemOn = False
            testMode = False

    time.sleep(1)

# === MAIN PROGRAM ===
if __name__ == '__main__':
    try:
        setup()
        while True:
            loop()
    except Exception as e:
        try:
            from utility import print_error_msg
            print_error_msg(e)
        except:
            print("Error: ", e)
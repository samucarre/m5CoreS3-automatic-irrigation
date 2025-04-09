# === IMPORTS Y CONFIGURACION INICIAL ===
import os, sys, io
import M5
from M5 import *
import time
import network
import socket
import ujson
from machine import I2C, Pin
import _thread
import urequests

# === CONFIGURACION GENERAL ===
CONFIG_FILE = 'config.json'
RELAY_I2C_ADDR = 0x26
RTC_I2C_ADDR = 0x68
CAMERA_I2C_ADDR = 0x3C
SERVIDOR_IP = '192.168.1.100'  # IP del servidor Flask en tu red

# Inicializar el bus I2C
i2c = I2C(1, scl=Pin(1), sda=Pin(2))

# === VARIABLES GLOBALES ===
title0 = labelInfo = labelInfo2 = labelStatus = labelRele = labelWifi = None
rtcEstado = releEstado = camEstado = labelCamara = None
estado = False
inicio = 0
rtc_ok = None
cam_ok = None

# === FUNCIONES ADICIONALES ===
def debo_enviar_stream():
    try:
        r = urequests.get("http://{}:5000/debo_enviar".format(SERVIDOR_IP))
        res = r.text
        r.close()
        return res.strip() == '1'
    except:
        return False

def capturar_y_enviar_imagen():
    try:
        import camera
        camera.init(0, format=camera.JPEG)
        img = camera.capture()
        r = urequests.post("http://{}:5000/upload".format(SERVIDOR_IP), files={"foto": img})
        r.close()
        camera.deinit()
    except Exception as e:
        print("Error al enviar imagen:", e)

# === HTML PARA LA INTERFAZ WEB ===
def generar_html(hora_actual, config, mostrar_stream=False):
    opciones_hora = "\n".join("<option value='{:02}:00'>{:02}:00</option>".format(h, h) for h in range(9, 21))
    opciones_duracion = "\n".join("<option value='{0}'>{0} min</option>".format(i) for i in range(5, 65, 5))
    texto_hora = config['hora'] if config['hora'] else "Apagado"
    texto_duracion = f"{config['duracion']} min" if config['duracion'] else "Apagado"

    stream_html = ""
    if mostrar_stream:
        stream_html = """
        <div class='bold'>Camara en vivo:</div>
        <div style='width:100%; height:200px; background:#ccc; border:1px solid #888; margin-bottom:10px; display:flex; align-items:center; justify-content:center;'>
            <span style='color:#666;'>Mostrando camara (o ha fallado la conexion)</span>
        </div>
        <form method='POST'>
            <input type='hidden' name='pararstream' value='1'>
            <button type='submit' class='apagar'>Terminar stream</button>
        </form>
        """

    return f"""<!DOCTYPE html><html><head><title>Configuracion Riego</title>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <style>
    body {{ font-family: Arial; background: #eef; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
    .form-container {{ background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.15); text-align: center; width: 90%; max-width: 320px; }}
    h2 {{ color: #006699; font-size: 18px; margin-bottom: 15px; }}
    .info, .nuevo {{ font-size: 13px; margin-bottom: 15px; color: #333; line-height: 1.5; }}
    .bold {{ font-weight: bold; margin-top: 10px; margin-bottom: 5px; font-size: 14px; color: #222; }}
    label {{ display: block; font-size: 14px; margin: 10px 0 4px; }}
    select, input[type='submit'], button {{ font-size: 14px; padding: 5px; width: 100%; border-radius: 4px; border: 1px solid #ccc; text-align: center; margin-bottom: 12px; }}
    input[type='submit'], button {{ color: white; border: none; padding: 8px; font-size: 14px; cursor: pointer; margin-top: 8px; }}
    .apagar {{ background-color: #cc0000; }} .probar {{ background-color: #009900; }} .stream {{ background-color: #006699; }}
    </style>
    <script>
    function mostrarMensajeCarga() {{
        document.getElementById("streamStatus").style.display = "block";
        fetch("http://192.168.1.115:5000/ping")
        .then(resp => {{
            if (resp.ok) {{
                setTimeout(() => {{
                    document.getElementById("enlaceStream").style.display = "block";
                }}, 3000);
            }} else {{
                document.getElementById("streamStatus").innerText = "Servidor no disponible";
            }}
        }}).catch(() => {{
            document.getElementById("streamStatus").innerText = "Servidor no disponible";
        }});
    }}
    </script>
    </head><body>
    <div class='form-container'>
      <h2>Configuracion de Riego</h2>
      <div class='info'>
        <div class='bold'>Configuracion actual:</div>
        Hora actual: {hora_actual}<br>
        Hora programada: {texto_hora}<br>
        Duracion: {texto_duracion}
        <form method='POST'><input type='hidden' name='apagar' value='1'><button type='submit' class='apagar'>Apagar sistema de riego</button></form>
        <form method='POST'><input type='hidden' name='probar' value='1'><button type='submit' class='probar'>Probar sistema de riego</button></form>

        <div id="streamStatus" style="display:none; font-size:13px; color:#555; margin-top:10px;">
          Cargando camara en vivo, por favor espera...
        </div>

        <form method="POST" onsubmit="mostrarMensajeCarga();">
          <input type="hidden" name="verstream" value="1">
          <button type="submit" class="stream">Ver camara en vivo</button>
        </form>

        <div id="enlaceStream" style="display:none; margin-top:10px;">
          <a href="http://192.168.1.115:5000/stream" target="_blank" style="font-size:14px; color:#006699;">Ir al stream de la camara</a>
        </div>

        {stream_html}
      </div>
      <div class='nuevo'>
        <div class='bold'>Nueva configuracion:</div>
        <form method='POST'>
          <label for='hora'>Hora:</label>
          <select name='hora' required>{opciones_hora}</select>
          <label for='duracion'>Duracion (minutos):</label>
          <select name='duracion' required>{opciones_duracion}</select>
          <input type='submit' value='Guardar'>
        </form>
      </div>
    </div></body></html>"""

# === CONFIGURACION ===
def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return ujson.load(f)
    except:
        return {'hora': '07:00', 'duracion': 10}

def save_config(data):
    with open(CONFIG_FILE, 'w') as f:
        ujson.dump(data, f)

# === CONTROL DEL RELÉ ===
def relay_on():
    try:
        i2c.writeto(RELAY_I2C_ADDR, b'\x01')
        releEstado.setText("ON")
        releEstado.setColor(0x009900, 0xffffff)
    except:
        releEstado.setText("ERROR")
        releEstado.setColor(0xcc0000, 0xffffff)

def relay_off():
    try:
        i2c.writeto(RELAY_I2C_ADDR, b'\x00')
        releEstado.setText("OFF")
        releEstado.setColor(0xcc0000, 0xffffff)
    except:
        releEstado.setText("ERROR")
        releEstado.setColor(0xcc0000, 0xffffff)

# === VERIFICACION DE RTC ===
def get_rtc_time():
    global rtc_ok
    try:
        data = i2c.readfrom_mem(RTC_I2C_ADDR, 0x00, 7)
        h = int((data[2] >> 4) * 10 + (data[2] & 0x0F))
        m = int((data[1] >> 4) * 10 + (data[1] & 0x0F))
        if rtc_ok is not True:
            rtcEstado.setText("ON")
            rtcEstado.setColor(0x009900, 0xffffff)
            rtc_ok = True
        return h, m
    except:
        if rtc_ok is not False:
            rtcEstado.setText("OFF")
            rtcEstado.setColor(0xcc0000, 0xffffff)
            rtc_ok = False
        return None

# === VERIFICACION DE CAMARA ===
def check_camera():
    global cam_ok
    try:
        i2c.readfrom(CAMERA_I2C_ADDR, 1)
        if cam_ok is not True:
            camEstado.setText("ON")
            camEstado.setColor(0x009900, 0xffffff)
            cam_ok = True
    except:
        if cam_ok is not False:
            camEstado.setText("OFF")
            camEstado.setColor(0xcc0000, 0xffffff)
            cam_ok = False

# === FUNCION DE PRUEBA DE RIEGO ===
def probar_riego_async():
    relay_on()
    time.sleep(60)
    relay_off()

# === ENVIO DE IMAGEN SI HAY STREAM ACTIVADO ===
def debo_enviar_stream():
    try:
        r = urequests.get("http://{}:5000/debo_enviar".format(SERVIDOR_IP))
        res = r.text
        r.close()
        return res.strip() == '1'
    except:
        return False

def capturar_y_enviar_imagen():
    try:
        import camera
        camera.init(0, format=camera.JPEG)
        img = camera.capture()
        r = urequests.post("http://{}:5000/upload".format(SERVIDOR_IP), files={"foto": img})
        r.close()
        camera.deinit()
    except Exception as e:
        print("Error al enviar imagen:", e)

# === MANEJO DE PETICIONES HTTP ===
def handle_client(conn):
    req = conn.recv(1024)
    req_str = req.decode('utf-8')
    config = load_config()
    mostrar_stream = False

    if 'POST' in req_str:
        body = req_str.split('\r\n\r\n')[1]
        params = {}
        for p in body.split('&'):
            if '=' in p:
                k, v = p.split('=', 1)
                params[k] = v
        if 'apagar' in params:
            config = {'hora': '', 'duracion': 0}
            save_config(config)
            relay_off()
        elif 'probar' in params:
            _thread.start_new_thread(probar_riego_async, ())
        elif 'verstream' in params:
            try:
                urequests.get("http://{}:5000/activar_stream".format(SERVIDOR_IP))
            except:
                print("Error al activar stream")
            mostrar_stream = True
        elif 'pararstream' in params:
            try:
                urequests.get("http://{}:5000/parar_stream".format(SERVIDOR_IP))
            except:
                print("Error al parar stream")
            mostrar_stream = False
        else:
            hora = params.get('hora', '').replace('%3A', ':')
            duracion = int(params.get('duracion', 0))
            config = {'hora': hora, 'duracion': duracion}
            save_config(config)

    now = get_rtc_time()
    hora_actual = "--:--" if not now else '{:02}:{:02}'.format(now[0], now[1])
    html = generar_html(hora_actual, config, mostrar_stream=mostrar_stream)
    conn.send('HTTP/1.1 200 OK\nContent-Type: text/html\n\n' + html)
    conn.close()

# === INICIO DE MODO AP Y WIFI ===
def start_ap():
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(essid='RIEGO_M5', password='Samuel123', authmode=3)
    while not ap.active():
        time.sleep(1)
    ip = ap.ifconfig()[0]
    labelWifi.setText("WIFI: ON\n     IP: {}".format(ip))
    labelInfo.setText("SSID: RIEGO_M5")
    labelInfo2.setText("PASS: Samuel123")

# === SERVIDOR WEB ===
def run_server():
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    s = socket.socket()
    try:
        s.bind(addr)
    except OSError:
        print("Servidor ya en ejecucion")
        return
    s.listen(1)
    s.settimeout(0.1)  # << más ágil
    while True:
        try:
            cl, addr = s.accept()
            handle_client(cl)
        except:
            pass  # Sin conexión nueva, seguimos el bucle

# === CONFIGURACION INICIAL DE LA PANTALLA ===
def setup():
    global title0, labelInfo, labelInfo2, labelStatus, labelRele, labelWifi, rtcEstado, releEstado, labelCamara, camEstado
    M5.begin()
    Widgets.fillScreen(0xffffff)
    title0 = Widgets.Title("Riego Solar", 3, 0xffffff, 0x00aaff, Widgets.FONTS.DejaVu18)
    labelWifi = Widgets.Label("WIFI: OFF", 10, 40, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelInfo = Widgets.Label("SSID: -", 10, 70, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelInfo2 = Widgets.Label("PASS: -", 10, 100, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelStatus = Widgets.Label("RTC:", 10, 130, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    rtcEstado = Widgets.Label("OFF", 60, 130, 1.0, 0xcc0000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelRele = Widgets.Label("RELE:", 10, 160, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    releEstado = Widgets.Label("OFF", 69, 160, 1.0, 0xcc0000, 0xffffff, Widgets.FONTS.DejaVu18)
    labelCamara = Widgets.Label("CAMERA:", 10, 190, 1.0, 0x000000, 0xffffff, Widgets.FONTS.DejaVu18)
    camEstado = Widgets.Label("OFF", 103, 190, 1.0, 0xcc0000, 0xffffff, Widgets.FONTS.DejaVu18)
    start_ap()
    _thread.start_new_thread(run_server, ())

# === LOOP PRINCIPAL ===
def loop():
    global estado, inicio
    M5.update()
    now = get_rtc_time()
    check_camera()
    if now:
        config = load_config()
        hora_actual = '{:02}:{:02}'.format(now[0], now[1])
        if hora_actual == config['hora'] and not estado:
            relay_on()
            inicio = time.time()
            estado = True
    if estado and time.time() - inicio > config['duracion'] * 60:
        relay_off()
        estado = False
    if debo_enviar_stream():
        capturar_y_enviar_imagen()
    time.sleep(1)

# === PROGRAMA PRINCIPAL ===
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
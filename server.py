from flask import Flask, request, send_from_directory, render_template_string
import os
from datetime import datetime

app = Flask(__name__)

# === CONFIGURACION ===
UPLOAD_FOLDER = "imagenes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
stream_activo = False

# === PAGINA PRINCIPAL ===
@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html><html>
    <head>
        <meta charset="utf-8">
        <title>Servidor de Riego</title>
        <style>
            body { font-family: sans-serif; background: #eef; text-align: center; padding: 40px; }
            h2 { color: #006699; }
            .boton { padding: 10px 20px; margin: 5px 0; border: none; border-radius: 5px; font-size: 16px; color: white; cursor: pointer; width: 220px; }
            .start { background-color: #009900; }
            .stop { background-color: #cc0000; }
            .ver { background-color: #006699; }
        </style>
        <script>
            function activarStream() {
                fetch('/activar_stream').then(() => location.reload());
            }
            function pararStream() {
                fetch('/parar_stream').then(() => location.reload());
            }
        </script>
    </head>
    <body>
        <h2>Servidor de Riego Activo</h2>
        <p>Estado del stream: <strong>{{ 'ACTIVO' if activo else 'INACTIVO' }}</strong></p>
        <div style="margin-top: 20px;">
            <button class="boton start" onclick="activarStream()">Activar Stream</button>
        </div>
        <div style="margin-top: 10px;">
            <button class="boton stop" onclick="pararStream()">Parar Stream</button>
        </div>
        {% if activo %}
        <div style="margin-top: 15px;">
            <a href="/stream" class="boton ver">Ver Cámara en Vivo</a>
        </div>
        {% else %}
        <div style="margin-top: 15px; color: #666;">
            El stream no está activo.
        </div>
        {% endif %}
    </body>
    </html>
    """, activo=stream_activo)

# === ACTIVAR / PARAR STREAM desde el M5Stack ===
@app.route("/activar_stream")
def activar_stream():
    global stream_activo
    stream_activo = True
    return "OK"

@app.route("/parar_stream")
def parar_stream():
    global stream_activo
    stream_activo = False
    return "OK"

@app.route("/debo_enviar")
def debo_enviar():
    return "1" if stream_activo else "0"

# === RECIBIR IMAGEN DEL M5Stack ===
@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("foto")
    if file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}.jpg"
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        # Guardamos una copia temporal para mostrar como "stream"
        with open(path, "rb") as f:
            with open(os.path.join(UPLOAD_FOLDER, "ultima.jpg"), "wb") as last:
                last.write(f.read())
        print(f"Imagen recibida y guardada: {filename}")
        return "OK"
    return "No se recibió imagen", 400

# === MOSTRAR STREAM (imagen actualizada) ===
@app.route("/stream")
def stream():
    return render_template_string("""
    <html><head><title>Stream en Vivo</title>
    <meta http-equiv="refresh" content="2">
    <style>body { font-family: sans-serif; text-align: center; background: #eef; }</style>
    </head>
    <body>
    <h2>Stream de la Cámara</h2>
    <img src="/imagenes/ultima.jpg" width="80%" style="border:1px solid #999; box-shadow: 0 0 10px #aaa;">
    <p><a href="/">Volver</a></p>
    </body></html>
    """)

# === SERVIR ARCHIVOS DE IMAGEN ===
@app.route("/imagenes/<path:filename>")
def imagenes(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# === INICIAR SERVIDOR ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
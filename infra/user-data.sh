#!/bin/bash

# Detener el script si ocurre un error, falta una variable
# o falla una parte de una tubería.
set -euxo pipefail

# Amazon Linux usa dnf para instalar programas.
dnf install -y python3

# Esta carpeta contendrá la aplicación dentro de la instancia.
install -d -m 755 /opt/autoscaling-app

# El bloque entre PYTHON crea el servidor en la instancia.
cat > /opt/autoscaling-app/server.py <<'PYTHON'
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
from datetime import datetime, timezone


HOST = "0.0.0.0"
PORT = 8080


class ApplicationHandler(BaseHTTPRequestHandler):
    def send_response_body(self, status, content_type, body):
        encoded_body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded_body)))
        self.end_headers()
        self.wfile.write(encoded_body)

    def do_GET(self):
        if self.path == "/health":
            self.send_response_body(
                HTTPStatus.OK,
                "text/plain; charset=utf-8",
                "OK",
            )
            return

        if self.path == "/":
            hostname = socket.gethostname()
            current_time = datetime.now(timezone.utc).isoformat()

            body = f"""<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Auto-Scaling Controller</title>
</head>
<body>
    <h1>Aplicación disponible</h1>
    <p>Instancia: <strong>{hostname}</strong></p>
    <p>Hora UTC: {current_time}</p>
</body>
</html>
"""

            self.send_response_body(
                HTTPStatus.OK,
                "text/html; charset=utf-8",
                body,
            )
            return

        self.send_response_body(
            HTTPStatus.NOT_FOUND,
            "text/plain; charset=utf-8",
            "Not Found",
        )

    def log_message(self, format, *args):
        print(
            f"{self.client_address[0]} - "
            f"{format % args}",
            flush=True,
        )


def main():
    server = ThreadingHTTPServer(
        (HOST, PORT),
        ApplicationHandler,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
PYTHON

# Damos la propiedad del archivo al usuario normal de Amazon Linux.
chown -R ec2-user:ec2-user /opt/autoscaling-app

# Este bloque define un servicio que inicia la aplicación automáticamente.
cat > /etc/systemd/system/autoscaling-app.service <<'SERVICE'
[Unit]
Description=Aplicacion web del reto de auto-scaling
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/autoscaling-app
ExecStart=/usr/bin/python3 /opt/autoscaling-app/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

# Informamos a systemd del servicio nuevo.
systemctl daemon-reload

# Lo habilitamos para futuros arranques y lo iniciamos ahora.
systemctl enable --now autoscaling-app.service
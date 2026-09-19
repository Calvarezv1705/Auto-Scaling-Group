# HTTPStatus contiene nombres legibles para códigos como 200 y 404.
from http import HTTPStatus

# Estas clases implementan un servidor HTTP básico.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# socket permite obtener el nombre de la máquina.
import socket

# datetime permite mostrar la hora de la respuesta.
from datetime import datetime, timezone


# La aplicación escuchará en este puerto.
HOST = "0.0.0.0"
PORT = 8080


class ApplicationHandler(BaseHTTPRequestHandler):
    # Esta función común envía el estado, encabezados y contenido.
    def send_response_body(self, status, content_type, body):
        # Convertimos el texto a bytes porque HTTP envía datos binarios.
        encoded_body = body.encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded_body)))
        self.end_headers()
        self.wfile.write(encoded_body)

    # do_GET maneja las solicitudes GET del navegador y del ALB.
    def do_GET(self):
        # El balanceador usará esta ruta para comprobar la salud.
        if self.path == "/health":
            self.send_response_body(
                HTTPStatus.OK,
                "text/plain; charset=utf-8",
                "OK",
            )
            return

        # La página principal muestra qué instancia respondió.
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

        # Cualquier ruta desconocida responde con código 404.
        self.send_response_body(
            HTTPStatus.NOT_FOUND,
            "text/plain; charset=utf-8",
            "Not Found",
        )

    # Registramos cada solicitud en la terminal.
    def log_message(self, format, *args):
        print(
            f"{self.client_address[0]} - "
            f"{format % args}"
        )


def main():
    # ThreadingHTTPServer permite atender solicitudes concurrentes.
    server = ThreadingHTTPServer(
        (HOST, PORT),
        ApplicationHandler,
    )

    print(f"Aplicación disponible en http://localhost:{PORT}")
    print("Detén el servidor con Control + C")

    # El servidor continúa atendiendo hasta que lo detengamos.
    server.serve_forever()


if __name__ == "__main__":
    main()
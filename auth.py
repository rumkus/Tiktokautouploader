"""
TikTok OAuth2 Authentication Script
Ejecuta este script UNA VEZ para autorizar tu cuenta de TikTok.
El token se guardara en token.json y se renovara automaticamente.
"""

import json
import os
import sys
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

# Directorio base del script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"


def load_config():
    """Carga la configuracion desde config.json"""
    if not os.path.exists(CONFIG_FILE):
        print("ERROR: No se encontro config.json")
        print("Copia config.json y agrega tu Client Key y Client Secret.")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    if config.get("client_key") == "TU_CLIENT_KEY_AQUI":
        print("ERROR: Debes editar config.json con tus credenciales reales.")
        print("Abre config.json y reemplaza los valores de ejemplo.")
        sys.exit(1)

    return config


def save_token(token_data):
    """Guarda el token en token.json"""
    token_data["obtained_at"] = int(time.time())
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(token_data, f, indent=2)
    print(f"Token guardado en {TOKEN_FILE}")


def refresh_token(config):
    """Renueva el access token usando el refresh token"""
    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        token_data = json.load(f)

    refresh_tok = token_data.get("refresh_token")
    if not refresh_tok:
        return None

    print("Renovando access token...")
    response = requests.post(
        TIKTOK_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config["client_key"],
            "client_secret": config["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
        },
    )

    if response.status_code == 200:
        data = response.json()
        if "access_token" in data.get("data", {}):
            save_token(data["data"])
            print("Token renovado exitosamente.")
            return data["data"]

    print("No se pudo renovar el token. Necesitas autenticarte de nuevo.")
    return None


def get_valid_token(config):
    """Obtiene un token valido, renovandolo si es necesario"""
    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        token_data = json.load(f)

    # Verificar si el token ha expirado
    obtained_at = token_data.get("obtained_at", 0)
    expires_in = token_data.get("expires_in", 0)

    if time.time() > obtained_at + expires_in - 300:  # 5 min de margen
        return refresh_token(config)

    return token_data


class CallbackHandler(BaseHTTPRequestHandler):
    """Servidor local para recibir el callback de OAuth"""

    auth_code = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Autorizacion exitosa!</h1>"
                b"<p>Puedes cerrar esta ventana.</p></body></html>"
            )
        elif "error" in params:
            error = params.get("error_description", params.get("error", ["Desconocido"]))
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h1>Error</h1><p>{error}</p></body></html>".encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Silenciar logs del servidor


def authenticate(config):
    """Flujo completo de autenticacion OAuth2"""
    redirect_uri = f"http://localhost:{config.get('redirect_port', 8585)}/callback"
    port = config.get("redirect_port", 8585)

    # Construir URL de autorizacion
    scopes = "user.info.basic,video.publish"
    auth_url = (
        f"{TIKTOK_AUTH_URL}"
        f"?client_key={config['client_key']}"
        f"&scope={scopes}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&state=tiktok_auto_uploader"
    )

    print("=" * 50)
    print("AUTENTICACION DE TIKTOK")
    print("=" * 50)
    print()
    print("Se abrira tu navegador para autorizar la app.")
    print("Si no se abre, copia y pega esta URL:")
    print()
    print(auth_url)
    print()

    # Iniciar servidor local para recibir el callback
    server = HTTPServer(("localhost", port), CallbackHandler)
    server.timeout = 120  # 2 minutos de timeout

    # Abrir navegador
    webbrowser.open(auth_url)
    print(f"Esperando autorizacion (timeout: 2 minutos)...")

    # Esperar el callback
    CallbackHandler.auth_code = None
    while CallbackHandler.auth_code is None:
        server.handle_request()

    server.server_close()
    auth_code = CallbackHandler.auth_code

    if not auth_code:
        print("ERROR: No se recibio el codigo de autorizacion.")
        sys.exit(1)

    print("Codigo recibido. Obteniendo access token...")

    # Intercambiar codigo por token
    response = requests.post(
        TIKTOK_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config["client_key"],
            "client_secret": config["client_secret"],
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )

    if response.status_code != 200:
        print(f"ERROR: Respuesta {response.status_code}")
        print(response.text)
        sys.exit(1)

    data = response.json()

    if "data" not in data or "access_token" not in data.get("data", {}):
        print(f"ERROR: Respuesta inesperada de TikTok:")
        print(json.dumps(data, indent=2))
        sys.exit(1)

    token_data = data["data"]
    save_token(token_data)

    print()
    print("Autenticacion completada exitosamente!")
    print(f"Open ID: {token_data.get('open_id', 'N/A')}")
    print(f"Token expira en: {token_data.get('expires_in', 0) // 3600} horas")
    print()
    print("Ya puedes ejecutar: python tiktok_uploader.py")


if __name__ == "__main__":
    config = load_config()

    # Verificar si ya hay un token valido
    existing = get_valid_token(config)
    if existing:
        print("Ya tienes un token valido.")
        resp = input("Quieres re-autenticarte? (s/n): ").strip().lower()
        if resp != "s":
            print("Token actual sigue siendo valido. No se hicieron cambios.")
            sys.exit(0)

    authenticate(config)

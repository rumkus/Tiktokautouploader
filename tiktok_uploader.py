"""
TikTok Auto Uploader - Monitor de Carpeta
==========================================
Vigila una carpeta y sube automaticamente cualquier video nuevo a TikTok.

Uso:
    python tiktok_uploader.py

Archivos de descripcion:
    Para agregar titulo/hashtags a un video, crea un archivo .txt con el
    mismo nombre. Ejemplo:
        mi_video.mp4       <- el video
        mi_video.txt       <- contiene "Mi video increible #viral #fyp"

    Si no hay .txt, se usa el nombre del archivo como titulo.
"""

import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ============================================================
# CONFIGURACION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
LOG_FILE = os.path.join(BASE_DIR, "upload_log.txt")

SUPPORTED_FORMATS = {".mp4", ".mov", ".webm", ".avi"}
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4 GB (limite de TikTok)

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================
# FUNCIONES DE CONFIGURACION Y TOKEN
# ============================================================


def load_config():
    """Carga config.json"""
    if not os.path.exists(CONFIG_FILE):
        logger.error("No se encontro config.json. Ejecuta primero la configuracion.")
        sys.exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_access_token(config):
    """Obtiene un access token valido, renovandolo si es necesario"""
    if not os.path.exists(TOKEN_FILE):
        logger.error("No se encontro token.json. Ejecuta primero: python auth.py")
        sys.exit(1)

    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        token_data = json.load(f)

    obtained_at = token_data.get("obtained_at", 0)
    expires_in = token_data.get("expires_in", 0)

    # Si el token expiro o esta por expirar (5 min de margen)
    if time.time() > obtained_at + expires_in - 300:
        logger.info("Token expirado. Renovando...")
        token_data = _refresh_token(config, token_data)

    return token_data["access_token"]


def _refresh_token(config, token_data):
    """Renueva el access token"""
    response = requests.post(
        f"{TIKTOK_API_BASE.replace('/v2', '')}/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config["client_key"],
            "client_secret": config["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
        },
    )

    if response.status_code == 200:
        data = response.json().get("data", {})
        if "access_token" in data:
            data["obtained_at"] = int(time.time())
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info("Token renovado exitosamente.")
            return data

    logger.error("No se pudo renovar el token. Ejecuta de nuevo: python auth.py")
    sys.exit(1)


# ============================================================
# FUNCIONES DE SUBIDA A TIKTOK
# ============================================================


def get_video_description(video_path):
    """
    Busca un archivo .txt con el mismo nombre para usar como descripcion.
    Si no existe, usa el nombre del archivo.
    """
    txt_path = video_path.rsplit(".", 1)[0] + ".txt"
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            description = f.read().strip()
        logger.info(f"Descripcion cargada desde: {os.path.basename(txt_path)}")
        return description

    # Usar nombre del archivo sin extension como titulo
    name = os.path.splitext(os.path.basename(video_path))[0]
    # Limpiar guiones bajos y guiones
    name = name.replace("_", " ").replace("-", " ")
    return name


def upload_video(config, video_path):
    """
    Sube un video a TikTok usando la Content Posting API.
    Retorna True si fue exitoso, False si fallo.
    """
    file_size = os.path.getsize(video_path)
    filename = os.path.basename(video_path)

    # Validaciones
    if file_size > MAX_FILE_SIZE:
        logger.error(f"'{filename}' excede el limite de 4GB ({file_size / 1e9:.1f}GB)")
        return False

    if file_size == 0:
        logger.error(f"'{filename}' esta vacio.")
        return False

    description = get_video_description(video_path)
    access_token = get_access_token(config)
    privacy = config.get("default_privacy", "SELF_ONLY")

    logger.info(f"Subiendo: {filename} ({file_size / 1e6:.1f} MB)")
    logger.info(f"Descripcion: {description}")
    logger.info(f"Privacidad: {privacy}")

    try:
        # Paso 1: Iniciar la subida
        init_response = requests.post(
            f"{TIKTOK_API_BASE}/post/publish/video/init/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": {
                    "title": description[:150],  # TikTok limita a 150 chars
                    "privacy_level": privacy,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": file_size,
                    "chunk_size": file_size,  # Subida en un solo chunk
                    "total_chunk_count": 1,
                },
            },
        )

        if init_response.status_code != 200:
            logger.error(f"Error al iniciar subida: {init_response.status_code}")
            logger.error(init_response.text)
            return False

        init_data = init_response.json()

        if init_data.get("error", {}).get("code") != "ok":
            error_msg = init_data.get("error", {}).get("message", "Error desconocido")
            logger.error(f"TikTok rechazo la solicitud: {error_msg}")
            return False

        upload_url = init_data["data"]["upload_url"]
        publish_id = init_data["data"].get("publish_id", "N/A")

        logger.info(f"URL de subida obtenida. Publish ID: {publish_id}")

        # Paso 2: Subir el archivo de video
        with open(video_path, "rb") as video_file:
            upload_response = requests.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                    "Content-Type": "video/mp4",
                },
                data=video_file,
            )

        if upload_response.status_code in (200, 201):
            logger.info(f"Video '{filename}' subido exitosamente!")
            return True
        else:
            logger.error(f"Error al subir video: {upload_response.status_code}")
            logger.error(upload_response.text)
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexion: {e}")
        return False
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return False


def move_to_done(video_path, config):
    """Mueve el video a la carpeta 'subidos' despues de subirlo"""
    done_folder = os.path.join(
        config.get("watch_folder", os.path.join(BASE_DIR, "videos_para_subir")),
        "subidos",
    )
    os.makedirs(done_folder, exist_ok=True)

    filename = os.path.basename(video_path)
    dest = os.path.join(done_folder, filename)

    # Si ya existe, agregar timestamp
    if os.path.exists(dest):
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(done_folder, f"{name}_{timestamp}{ext}")

    os.rename(video_path, dest)
    logger.info(f"Movido a: {dest}")

    # Mover tambien el .txt si existe
    txt_path = video_path.rsplit(".", 1)[0] + ".txt"
    if os.path.exists(txt_path):
        txt_dest = dest.rsplit(".", 1)[0] + ".txt"
        os.rename(txt_path, txt_dest)


# ============================================================
# MONITOR DE CARPETA
# ============================================================


class VideoHandler(FileSystemEventHandler):
    """Detecta nuevos videos en la carpeta monitoreada"""

    def __init__(self, config):
        self.config = config
        self.processing = set()  # Evitar procesar el mismo archivo dos veces

    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        ext = os.path.splitext(filepath)[1].lower()

        if ext not in SUPPORTED_FORMATS:
            return

        if filepath in self.processing:
            return

        self.processing.add(filepath)

        # Esperar a que el archivo termine de copiarse
        logger.info(f"Nuevo video detectado: {os.path.basename(filepath)}")
        logger.info("Esperando a que termine de copiarse...")

        if not self._wait_for_file_ready(filepath):
            logger.error(f"El archivo no se completo: {filepath}")
            self.processing.discard(filepath)
            return

        # Subir el video
        success = upload_video(self.config, filepath)

        if success and self.config.get("move_after_upload", True):
            move_to_done(filepath, self.config)

        self.processing.discard(filepath)

    def _wait_for_file_ready(self, filepath, timeout=120):
        """Espera hasta que el archivo deje de cambiar de tamano"""
        last_size = -1
        stable_count = 0

        for _ in range(timeout):
            try:
                current_size = os.path.getsize(filepath)
            except OSError:
                return False

            if current_size == last_size and current_size > 0:
                stable_count += 1
                if stable_count >= 3:  # 3 segundos sin cambios
                    return True
            else:
                stable_count = 0

            last_size = current_size
            time.sleep(1)

        return False


def process_existing_videos(config, watch_folder):
    """Procesa videos que ya estaban en la carpeta al iniciar"""
    existing = []
    for f in os.listdir(watch_folder):
        ext = os.path.splitext(f)[1].lower()
        if ext in SUPPORTED_FORMATS:
            existing.append(os.path.join(watch_folder, f))

    if not existing:
        return

    logger.info(f"Se encontraron {len(existing)} video(s) existente(s).")

    for video_path in sorted(existing):
        filename = os.path.basename(video_path)
        logger.info(f"Procesando video existente: {filename}")

        success = upload_video(config, video_path)

        if success and config.get("move_after_upload", True):
            move_to_done(video_path, config)

        # Pausa entre subidas para no saturar la API
        delay = config.get("delay_between_uploads", 10)
        if existing.index(video_path) < len(existing) - 1:
            logger.info(f"Esperando {delay}s antes del siguiente video...")
            time.sleep(delay)


# ============================================================
# MAIN
# ============================================================


def main():
    config = load_config()

    # Carpeta a monitorear
    watch_folder = config.get(
        "watch_folder", os.path.join(BASE_DIR, "videos_para_subir")
    )
    os.makedirs(watch_folder, exist_ok=True)

    # Verificar que hay un token
    if not os.path.exists(TOKEN_FILE):
        logger.error("No se encontro token.json")
        logger.error("Ejecuta primero: python auth.py")
        sys.exit(1)

    print()
    print("=" * 55)
    print("   TIKTOK AUTO UPLOADER - Monitor de Carpeta")
    print("=" * 55)
    print()
    print(f"   Carpeta vigilada : {watch_folder}")
    print(f"   Formatos         : {', '.join(SUPPORTED_FORMATS)}")
    print(f"   Privacidad       : {config.get('default_privacy', 'SELF_ONLY')}")
    print(f"   Mover al subir   : {'Si' if config.get('move_after_upload', True) else 'No'}")
    print()
    print("   Deja videos en la carpeta y se subiran solos.")
    print("   Presiona Ctrl+C para detener.")
    print()
    print("=" * 55)
    print()

    # Procesar videos que ya estaban en la carpeta
    if config.get("process_existing", True):
        process_existing_videos(config, watch_folder)

    # Iniciar monitoreo
    event_handler = VideoHandler(config)
    observer = Observer()
    observer.schedule(event_handler, watch_folder, recursive=False)
    observer.start()

    logger.info("Monitor activo. Esperando nuevos videos...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Deteniendo monitor...")
        observer.stop()

    observer.join()
    logger.info("Monitor detenido.")


if __name__ == "__main__":
    main()

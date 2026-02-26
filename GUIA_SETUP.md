# Guia de Configuracion - TikTok Auto Uploader

## Paso 1: Crear cuenta de desarrollador en TikTok

1. Ve a **https://developers.tiktok.com/** e inicia sesion con tu cuenta de TikTok
2. Haz clic en **"Manage apps"** en el menu superior
3. Haz clic en **"Connect an app"**
4. Completa el formulario:
   - **App name**: (ej. "Mi Auto Uploader")
   - **Description**: Herramienta personal para subir videos
   - **App icon**: Sube cualquier imagen de 100x100px
   - **Category**: Entertainment
   - **Platform**: Web

## Paso 2: Configurar permisos

1. En tu app, ve a la seccion **"Manage products"** o **"Add products"**
2. Activa **"Content Posting API"**
3. Solicita el scope: `video.publish`
4. TikTok revisara tu solicitud (puede tardar 1-5 dias habiles)

## Paso 3: Obtener credenciales

Una vez aprobada tu app, ve a la seccion de tu app y copia:
- **Client Key** (tambien llamado client_id)
- **Client Secret**

## Paso 4: Configurar el proyecto

1. Instala Python 3.9+ desde https://python.org (marca "Add to PATH" al instalar)
2. Abre una terminal (cmd o PowerShell) en la carpeta del proyecto
3. Ejecuta:
   ```
   pip install requests watchdog
   ```
4. Edita `config.json` con tus credenciales (Client Key y Client Secret)

## Paso 5: Autenticarte

1. Ejecuta:
   ```
   python auth.py
   ```
2. Se abrira tu navegador para que autorices la app con tu cuenta de TikTok
3. El token se guardara automaticamente en `token.json`

## Paso 6: Iniciar el monitor de carpeta

1. Ejecuta:
   ```
   python tiktok_uploader.py
   ```
2. El script vigilara la carpeta `videos_para_subir/`
3. Cualquier video (.mp4, .mov, .webm) que dejes ahi se subira automaticamente

## Notas importantes

- El access token expira. El script lo renueva automaticamente.
- Los videos deben cumplir las politicas de TikTok (max 10 min, formatos soportados).
- Puedes crear un archivo .txt con el mismo nombre que el video para incluir la descripcion.
  Ejemplo: `mi_video.mp4` + `mi_video.txt` (con el titulo y hashtags).
- Para detener el script, presiona Ctrl+C en la terminal.

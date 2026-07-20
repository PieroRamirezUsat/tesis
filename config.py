import os
from dotenv import load_dotenv

# Cargar variables del archivo .env automáticamente
load_dotenv()

class Config:
    # ⚠️  Producción (Railway): define SECRET_KEY como variable de entorno con
    #     un valor largo y aleatorio. El default solo sirve para desarrollo local.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-in-production-tutormath2026")

    # ── Base de datos ───────────────────────────────────────────────
    # Railway y Render inyectan DATABASE_URL automáticamente.
    # En local usa el valor por defecto si no hay .env configurado.
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:hola1@localhost:5432/bd_ejemplo"
    )

    # ==============================================================
    #  🖼️ Carpeta de imágenes de desarrollos del alumno
    #  Si las imágenes se guardan en un proyecto API separado,
    #  apunta esta variable a esa carpeta.
    #  Se puede sobreescribir con la variable de entorno
    #  DESARROLLOS_ALUMNO_PATH en producción.
    # ==============================================================
    # En local (Windows) apunta a la carpeta de la API.
    # En Railway/Linux se sobreescribe con la variable de entorno.
    _default_path = (
        r"D:\Tesis\TODO\API_RESTFUL\API_COMERCIAL\static\desarrollos_alumno"
        if os.name == "nt"                 # nt = Windows
        else "/app/static/desarrollos_alumno"
    )
    DESARROLLOS_ALUMNO_PATH = os.environ.get("DESARROLLOS_ALUMNO_PATH", _default_path)

    # ====================================================
    #  🔑 Código de registro exclusivo para docentes
    #  Solo quien tenga este código puede crear una cuenta
    #  de docente. Cámbialo por uno seguro y compártelo
    #  únicamente con el personal autorizado.
    #  Sobreescribible con la variable CODIGO_REGISTRO_DOCENTE.
    # ====================================================
    CODIGO_REGISTRO_DOCENTE = os.environ.get(
        "CODIGO_REGISTRO_DOCENTE",
        "TUTOR-2026"          # ← cámbialo por uno más secreto
    )

    # ====================================================
    #  🔗 URL base de la API REST (para imágenes cross-servicio en Railway)
    #  En local no hace falta si los archivos están accesibles por filesystem.
    #  En Railway, ponla con el dominio público de la API, ej:
    #  https://api-tesis-production.up.railway.app
    # ====================================================
    API_BASE_URL = os.environ.get("API_BASE_URL", "")

    # ====================================================
    #  📱 URL de descarga del APK de la app móvil
    #  ⚠️ Apuntar SIEMPRE al alias fijo "TutorMath-latest.apk" del release
    #  de GitHub (no a un nombre versionado tipo "TutorMath-v1.4.apk"):
    #  cada APK nuevo sobrescribe ese mismo archivo, así esta variable
    #  (configurada en Railway) no hay que volver a tocarla nunca.
    # ====================================================
    APK_DOWNLOAD_URL = os.environ.get(
        "APK_DOWNLOAD_URL",
        "#descargar"          # ← reemplaza con tu enlace real
    )

    # ============================
    #  📧 Configuración de correo
    # ============================
    # ⚠️  NUNCA pongas credenciales reales aquí (pueden quedar en Git).
    #     Defínelas en .env (local) o como variables de entorno en Railway.
    #     MAIL_PASSWORD debe ser un App Password de Gmail (no la contraseña
    #     principal). Generarlo en: myaccount.google.com → Seguridad → App passwords.
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 465
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = MAIL_USERNAME

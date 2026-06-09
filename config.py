import os
from dotenv import load_dotenv

# Cargar variables del archivo .env automáticamente
load_dotenv()

class Config:
    SECRET_KEY   = os.environ.get("SECRET_KEY", "dev-key")
    DATABASE_URL = os.environ.get("DATABASE_URL")

    # ===========================================
    #  🔗 Cadena de conexión a la base de datos
    #  En local usa el valor por defecto.
    #  En Render usa la variable DATABASE_URL
    # ===========================================
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
    #  📱 URL de descarga del APK de la app móvil
    #  Cámbiala por el enlace real de GitHub Releases u
    #  otro servidor cuando subas el APK.
    # ====================================================
    APK_DOWNLOAD_URL = os.environ.get(
        "APK_DOWNLOAD_URL",
        "#descargar"          # ← reemplaza con tu enlace real
    )

    # ============================
    #  📧 Configuración de correo
    # ============================
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 465
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "ww.sco.lol@gmail.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "hgzm kujp blfu sczr")
    MAIL_DEFAULT_SENDER = MAIL_USERNAME

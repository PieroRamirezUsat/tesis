"""
util_cloudinary.py  —  Subida de imágenes a Cloudinary (TutorMath / Web App)

Configuración (variables de entorno):
  CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
  ─── O por separado ───
  CLOUDINARY_CLOUD_NAME=tu_cloud
  CLOUDINARY_API_KEY=123456
  CLOUDINARY_API_SECRET=abc...

Si ninguna variable está definida, `cloudinary_configurado()` retorna False
y los uploads vuelven al modo local (filesystem).
"""
import os
import cloudinary
import cloudinary.uploader
import cloudinary.utils


def _configurar():
    if os.environ.get("CLOUDINARY_URL"):
        return
    cloudinary.config(
        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
        api_key    = os.environ.get("CLOUDINARY_API_KEY",    ""),
        api_secret = os.environ.get("CLOUDINARY_API_SECRET", ""),
        secure     = True,
    )


_configurar()


def cloudinary_configurado() -> bool:
    cfg = cloudinary.config()
    return bool(cfg.cloud_name and cfg.api_key and cfg.api_secret)


def subir_imagen(archivo, public_id: str) -> str:
    """
    Sube `archivo` a Cloudinary. Retorna URL HTTPS permanente.
    Lanza Exception si la subida falla.
    """
    resultado = cloudinary.uploader.upload(
        archivo,
        public_id     = public_id,
        overwrite     = True,
        invalidate    = True,   # purga el CDN al reemplazar (evita fotos viejas cacheadas)
        resource_type = "image",
        format        = "jpg",
    )
    # secure_url incluye la versión (…/v123456/…): úsala al mostrar para
    # que navegadores y CDN no sirvan la imagen anterior.
    return resultado["secure_url"]
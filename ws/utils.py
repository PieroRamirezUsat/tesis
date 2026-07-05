import os
from flask import url_for

DEFAULT_AVATAR = (
    "https://lh3.googleusercontent.com/aida-public/"
    "AB6AXuAMcTpY7WPWyqTFerHL4BxjKgr5N_14O8GAKfI7r_NIgzL0NKqd-48r2aSd0Y5m4DgWy0lnuHKz49QTvCVhQfKWBsIo8x1LNHu7-x49dAG8TtGPDSXo-enbcuPi6-6SPDGTeiPfbbv2ql13IwnPZmaA5VIlHM7l2zOTM0796EiGKjSNDHHHM2K-qvsgadUZEcjlzhlAkQEQEwvmnTPculFqkF2t2UWnHpAyZsmsZrPJ_oxzxjw1Z0TkFHtNW4UQsUbbU_ZwFVKhcI"
)


def calcular_progreso(nivel_actual: int, promedio_puntaje: float = 0) -> int:
    """
    Calcula el porcentaje de progreso en una competencia.

    nivel_actual : nivel adaptativo del estudiante (1–7).
    Meta: nivel 6. Fórmula: (min(nivel, 6) - 1) / 5 × 100
      nivel 1 → 0 %, nivel 2 → 20 %, …, nivel 6 → 100 %, nivel 7 → 100 %
    """
    pct = (min(nivel_actual, 6) - 1) / 5 * 100
    return max(0, min(100, int(round(pct))))


def url_foto_usuario(root_path: str, id_usuario: int) -> str:
    """
    Devuelve la URL de la foto de perfil del usuario.

    Orden de búsqueda:
      1. usuarios.foto_perfil (URL de Cloudinary CON versión, guardada al subir).
         La versión en la URL es lo que evita que el CDN y el navegador
         sigan mostrando la foto anterior tras un reemplazo.
      2. Cloudinary sin versión (fotos subidas antes de guardar la URL en BD).
      3. Archivo local en static/fotos_perfil/user_<id>.jpg (desarrollo local).
      4. Avatar por defecto.
    """
    try:
        from db import get_db
        cur = get_db().cursor()
        cur.execute(
            "SELECT foto_perfil FROM usuarios WHERE id_usuario = %s",
            (id_usuario,),
        )
        row = cur.fetchone()
        cur.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass

    try:
        from util_cloudinary import cloudinary_configurado
        if cloudinary_configurado():
            import cloudinary.utils as cld_utils
            url, _ = cld_utils.cloudinary_url(
                f"tutormath/fotos_perfil/user_{id_usuario}",
                resource_type="image",
                format="jpg",
                secure=True,
            )
            return url
    except Exception:
        pass

    # Modo local
    fs_path = os.path.join(root_path, "static", "fotos_perfil", f"user_{id_usuario}.jpg")
    if os.path.exists(fs_path):
        return url_for("static", filename=f"fotos_perfil/user_{id_usuario}.jpg")
    return DEFAULT_AVATAR

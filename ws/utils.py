import os
from flask import url_for

DEFAULT_AVATAR = (
    "https://lh3.googleusercontent.com/aida-public/"
    "AB6AXuAMcTpY7WPWyqTFerHL4BxjKgr5N_14O8GAKfI7r_NIgzL0NKqd-48r2aSd0Y5m4DgWy0lnuHKz49QTvCVhQfKWBsIo8x1LNHu7-x49dAG8TtGPDSXo-enbcuPi6-6SPDGTeiPfbbv2ql13IwnPZmaA5VIlHM7l2zOTM0796EiGKjSNDHHHM2K-qvsgadUZEcjlzhlAkQEQEwvmnTPculFqkF2t2UWnHpAyZsmsZrPJ_oxzxjw1Z0TkFHtNW4UQsUbbU_ZwFVKhcI"
)


def calcular_progreso(nivel_actual: int, promedio_puntaje: float) -> int:
    """
    Calcula el porcentaje de progreso en una competencia.

    nivel_actual     : nivel adaptativo del estudiante (1–7).
    promedio_puntaje : promedio de puntaje en ejercicios de esa competencia (0–100).

    Fórmula:
        porcentaje = ((nivel_actual - 1) / 6) * 70   ← peso del nivel  (70 %)
                   + (promedio_puntaje / 100)  * 30   ← peso del puntaje (30 %)
    """
    pct = ((nivel_actual - 1) / 6) * 70 + (promedio_puntaje / 100) * 30
    return max(0, min(100, int(round(pct))))


def url_foto_usuario(root_path: str, id_usuario: int) -> str:
    """
    Devuelve la URL de la foto de perfil del usuario.
    Busca en static/fotos_perfil/user_<id>.jpg; retorna el avatar por defecto si no existe.
    """
    fs_path = os.path.join(root_path, "static", "fotos_perfil", f"user_{id_usuario}.jpg")
    if os.path.exists(fs_path):
        return url_for("static", filename=f"fotos_perfil/user_{id_usuario}.jpg")
    return DEFAULT_AVATAR

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
    Busca en static/fotos_perfil/user_<id>.jpg; retorna el avatar por defecto si no existe.
    """
    fs_path = os.path.join(root_path, "static", "fotos_perfil", f"user_{id_usuario}.jpg")
    if os.path.exists(fs_path):
        return url_for("static", filename=f"fotos_perfil/user_{id_usuario}.jpg")
    return DEFAULT_AVATAR

import os
from flask import url_for

# ═══════════════════════════════════════════════════════════════════════════
#  Validación central de imágenes subidas (perfil, estudiantes, ejercicios)
# ═══════════════════════════════════════════════════════════════════════════
# Un archivo renombrado (p. ej. un .exe llamado foto.jpg) pasa el filtro de
# extensión pero no el de firma binaria. Cloudinary igual lo rechazaría,
# pero validar aquí da un mensaje claro al docente en vez de un error críptico.

IMG_EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".jfif", ".gif", ".bmp"}
IMG_MAX_MB = 5

# Firmas binarias reales (magic bytes) de cada formato aceptado
_FIRMAS_IMG = (
    b"\xff\xd8\xff",        # JPEG / JFIF
    b"\x89PNG\r\n\x1a\n",   # PNG
    b"GIF8",                # GIF
    b"BM",                  # BMP
)


def validar_imagen(archivo, max_mb: int = IMG_MAX_MB):
    """
    Valida un FileStorage de Flask antes de subirlo a Cloudinary/disco.
    Devuelve (True, None) si es válida, o (False, "motivo") si no.
    Deja el puntero del archivo al inicio para que pueda subirse después.
    """
    if archivo is None or not archivo.filename:
        return False, "No se seleccionó ningún archivo."

    ext = os.path.splitext(archivo.filename)[1].lower()
    if ext not in IMG_EXTENSIONES:
        permitidas = ", ".join(sorted(e.lstrip(".").upper() for e in IMG_EXTENSIONES))
        return False, (f"'{archivo.filename}' tiene un formato no permitido. "
                       f"Usa: {permitidas}.")

    # Tamaño real (seek al final, luego volver al inicio)
    archivo.seek(0, os.SEEK_END)
    tam = archivo.tell()
    archivo.seek(0)
    if tam == 0:
        return False, "El archivo está vacío."
    if tam > max_mb * 1024 * 1024:
        return False, (f"La imagen pesa {tam / 1024 / 1024:.1f} MB y el máximo "
                       f"es {max_mb} MB. Redúcela e inténtalo de nuevo.")

    # Contenido real: los primeros bytes deben ser de una imagen de verdad
    cabecera = archivo.read(16)
    archivo.seek(0)
    es_imagen = any(cabecera.startswith(f) for f in _FIRMAS_IMG)
    # WEBP: "RIFF....WEBP"
    if not es_imagen and cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        es_imagen = True
    if not es_imagen:
        return False, (f"'{archivo.filename}' no es una imagen válida "
                       "(el contenido no corresponde a un formato de imagen).")

    return True, None


def validar_url_material(url: str):
    """
    Valida la URL de un material de estudio: debe ser http(s) y sin espacios.
    La app móvil la abre tal cual — una URL rota deja al alumno sin refuerzo.
    Devuelve (True, url_limpia) o (False, "motivo").
    """
    u = (url or "").strip()
    if not u:
        return False, "La URL es obligatoria."
    if " " in u:
        return False, "La URL no puede contener espacios."
    if not (u.startswith("http://") or u.startswith("https://")):
        return False, "La URL debe empezar con http:// o https:// (cópiala completa desde el navegador)."
    if len(u) > 255:
        # la columna material_estudio.url es VARCHAR(255): más largo = error de BD
        return False, "La URL es demasiado larga (máximo 255 caracteres). Usa un enlace más corto."
    return True, u


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


# ═══════════════════════════════════════════════════════════════════════════
#  🔤 ESCALA LITERAL MINEDU (secundaria) — la que usan los docentes
# ═══════════════════════════════════════════════════════════════════════════
#  El colegio califica con LETRAS, no con números:
#    AD  Logro destacado   (vigesimal 18-20)
#    A   Logrado           (14-17)
#    B   En proceso        (11-13)
#    C   En inicio         (0-10)
#
#  El motor adaptativo trabaja internamente con niveles 1-7 y score 0-100; las
#  letras son solo la capa que ve/usa el docente. Mapeo nivel interno → letra:
#    1,2 → C · 3,4 → B · 5,6 → A · 7 → AD
#
#  Diagnóstico: cuando el docente elige una letra, se guarda un "score semilla"
#  (0-100) equivalente al punto medio vigesimal de esa letra, para que el tutor
#  arranque en la dificultad correcta:
#    C → 25 · B → 60 · A → 78 · AD → 95
# ═══════════════════════════════════════════════════════════════════════════

LETRA_NOMBRE = {
    "AD": "Logro destacado",
    "A":  "Logrado",
    "B":  "En proceso",
    "C":  "En inicio",
}
LETRA_VIGESIMAL = {"AD": "18-20", "A": "14-17", "B": "11-13", "C": "0-10"}
LETRA_ORDEN     = {"C": 0, "B": 1, "A": 2, "AD": 3}   # para comparar mejoras
_LETRA_SCORE_SEMILLA = {"C": 25, "B": 60, "A": 78, "AD": 95}


def nivel_to_letra(nivel_actual: int) -> str:
    """Nivel interno 1-7 → letra MINEDU (AD/A/B/C)."""
    n = int(nivel_actual or 1)
    if n >= 7:
        return "AD"
    if n >= 5:
        return "A"
    if n >= 3:
        return "B"
    return "C"


def letra_to_score(letra: str):
    """Letra MINEDU → score semilla 0-100 (para el diagnóstico). None si inválida."""
    return _LETRA_SCORE_SEMILLA.get((letra or "").strip().upper())


def letra_nombre(letra: str) -> str:
    return LETRA_NOMBRE.get((letra or "").strip().upper(), "—")


def score_to_letra(score) -> str:
    """Score 0-100 → letra MINEDU (pasando por el nivel 1-7)."""
    s = max(0.0, min(100.0, float(score or 0)))
    nivel = _score_to_nivel(s)
    return nivel_to_letra(nivel)


def _score_to_nivel(score) -> int:
    """Tabla score→nivel compartida con la API (SCORE_BRACKETS)."""
    s = max(0.0, min(100.0, float(score or 0)))
    # Mismo bug que en la API (models/scoring.py): los tramos son enteros
    # (0-21, 22-35...) pero el score real puede ser fraccionario. "lo <= s
    # <= hi" dejaba un hueco de 1 punto entre tramos (21 y 22, 35 y 36...)
    # que caia al `return 7` de emergencia -- un alumno con score 21.9 se
    # reportaba como nivel 7 "Maestro" al docente. Los tramos son
    # ascendentes y contiguos, asi que basta el primer techo no superado.
    for lo, hi, n in [(0,21,1),(22,35,2),(36,49,3),(50,64,4),(65,78,5),(79,92,6),(93,100,7)]:
        if s <= hi:
            return n
    return 7


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

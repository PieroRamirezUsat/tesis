# ═══════════════════════════════════════════════════════════════════════════
#  📚 GUÍA DE ESTUDIO — CONEXIÓN A LA BASE DE DATOS (WEB)
# ═══════════════════════════════════════════════════════════════════════════
#  A diferencia de la API (que crea una conexión por endpoint), aquí se usa
#  el patrón de Flask: UNA conexión por request guardada en `g`, que se
#  cierra sola al terminar (app.teardown_appcontext en app.py).
#
#  ⚠️ OJO: este proyecto usa psycopg v3 y las filas llegan como TUPLAS
#  (row[0], row[1]...). La API usa psycopg2+RealDictCursor y las filas son
#  DICCIONARIOS (row["columna"]). Si copias SQL de un proyecto al otro,
#  adapta la forma de leer las filas.
# ═══════════════════════════════════════════════════════════════════════════
import psycopg
from flask import g
from config import Config


def get_db():
    """
    Devuelve una única conexión a la BD por request.
    - LOCAL   : sin SSL (localhost)
    - RAILWAY / RENDER / cualquier nube: con sslmode='require'
    """
    if "db_conn" not in g:
        url = Config.DATABASE_URL
        if not url:
            raise RuntimeError("DATABASE_URL no está configurada")

        # Usa SSL cuando la URL no apunta a localhost / 127.0.0.1
        es_local = "localhost" in url or "127.0.0.1" in url
        if es_local:
            g.db_conn = psycopg.connect(url)
        else:
            g.db_conn = psycopg.connect(url, sslmode="require")

    return g.db_conn


def close_db(e=None):
    db_conn = g.pop("db_conn", None)
    if db_conn is not None:
        db_conn.close()
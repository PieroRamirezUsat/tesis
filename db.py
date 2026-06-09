import psycopg
from flask import g
from config import Config

def get_db():
    if "db_conn" not in g:
        if not Config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL no está configurada")

        # ✅ En local no necesita SSL, en Render sí
        # Si la URL ya trae sslmode en el string, psycopg lo respeta
        # Si no, detectamos si estamos en Render por la URL
        url = Config.DATABASE_URL
        es_render = "render.com" in url or "onrender.com" in url

        if es_render:
            g.db_conn = psycopg.connect(url, sslmode="require")
        else:
            # Local — sin SSL
            g.db_conn = psycopg.connect(url)

    return g.db_conn


def close_db(e=None):
    db_conn = g.pop("db_conn", None)
    if db_conn is not None:
        db_conn.close()
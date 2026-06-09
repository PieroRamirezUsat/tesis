# extensions.py
# Instancias de extensiones Flask que necesitan ser importadas
# tanto en app.py (init_app) como en los blueprints (decoradores).

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ── Rate Limiting ────────────────────────────────────────────────────────────
# key_func=get_remote_address  →  limita por IP del cliente.
# storage_uri="memory://"      →  almacenamiento en RAM (por proceso).
#   ✅ OK para una instancia en Railway.
#   ⚠️  Si escalas a múltiples instancias, cambia a Redis:
#       storage_uri = os.environ.get("REDIS_URL", "memory://")
# default_limits=[]            →  sin límite global; solo se aplica donde
#                                  pongas el decorador @limiter.limit(...)
# ─────────────────────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
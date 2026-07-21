# extensions.py
# Instancias de extensiones Flask que necesitan ser importadas
# tanto en app.py (init_app) como en los blueprints (decoradores).

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ── Rate Limiting ────────────────────────────────────────────────────────────
# key_func=get_remote_address  →  limita por IP del cliente.
# storage_uri="memory://"      →  almacenamiento en RAM, UN SOLO proceso.
#   ⚠️  memory:// NO se comparte entre procesos gunicorn distintos: con
#       --workers 2 cada worker llevaba su propio contador y el límite real
#       nunca se alcanzaba (confirmado con una prueba en vivo: 6 intentos de
#       login seguidos, cero 429). Por eso el Procfile usa
#       --workers 1 --threads 8 --worker-class gthread: un solo proceso (así
#       memory:// sí es un contador único y real) con hilos para no perder
#       concurrencia. Si el tráfico crece y hace falta más de un proceso,
#       ESTO hay que cambiarlo a un backend compartido:
#       storage_uri = os.environ.get("REDIS_URL", "memory://")
# default_limits=[]            →  sin límite global; solo se aplica donde
#                                  pongas el decorador @limiter.limit(...)
# ─────────────────────────────────────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri="memory://",
)
# ═══════════════════════════════════════════════════════════════════════════
#  📚 GUÍA DE ESTUDIO — PUNTO DE ENTRADA DEL PORTAL WEB (DOCENTE)
# ═══════════════════════════════════════════════════════════════════════════
#  Este proyecto es el PORTAL DEL DOCENTE (login con sesión de Flask +
#  cookies, NO con JWT — eso es de la API móvil). Comparte la base Postgres
#  con la API, pero es un servidor independiente.
#
#  Patrón usado: "application factory" — create_app() arma la aplicación:
#  · CSRFProtect: todo formulario POST necesita el token csrf (los templates
#    del panel lo inyectan por JS desde el <meta> de docente_base.html).
#  · limiter: máx. 5 intentos de login por minuto (anti fuerza bruta).
#  · context_processor foto_usuario_sidebar(): pone la foto del docente
#    (Cloudinary → local → avatar) disponible en TODOS los templates.
#  · register_blueprints(app) (ws/__init__.py) conecta todas las secciones:
#      ws/auth.py                 → /login /register /logout /forgot-password
#      ws/docentes.py             → /docente/dashboard y /docente/perfil
#      ws/gestionar_estudiante.py → alumnos + DIAGNÓSTICO MINEDU ⭐
#      ws/salones.py, ws/temas.py, ws/ejercicios.py, ws/reportes.py,
#      ws/evaluaciones.py         → cada sección del menú lateral
#  · La ruta "/" es la landing pública con el botón de descarga del APK
#    (URL en la variable APK_DOWNLOAD_URL de Railway).
#
#  Los templates viven en templates/ y TODOS los del panel heredan de
#  docente_base.html (sidebar + estilos + responsive). Despliegue: gunicorn
#  app:app (Procfile), Root Directory vacío en Railway.
# ═══════════════════════════════════════════════════════════════════════════
from flask import Flask, jsonify, redirect, url_for, render_template, request, flash
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from db import get_db, close_db
from ws import register_blueprints
from flask_wtf.csrf import CSRFProtect, CSRFError
from extensions import limiter

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── Confiar en el proxy de Railway ──────────────────────────────────────
    # Sin esto, request.remote_addr es la IP del propio proxy de Railway
    # (Hikari), no la del cliente real -- y varía según por qué nodo de borde
    # entra cada petición. Flask-Limiter usa remote_addr para el rate limit
    # por IP (login, registro, forgot-password); con la IP "equivocada" y
    # cambiante, el contador nunca junta las peticiones de un mismo cliente y
    # el límite nunca se activa (confirmado en vivo: 15 intentos de login
    # seguidos, cero 429). x_for=1 confía en UN salto de proxy — el de
    # Railway — y toma la IP real del header X-Forwarded-For que ese proxy
    # agrega.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

    # ── Extensiones ──────────────────────────────────────────────────────────
    # CSRF: protege todos los formularios POST automáticamente.
    #   Los templates deben incluir {{ csrf_token() }} en cada <form method="post">.
    #   Los templates que extienden docente_base.html lo reciben vía JS auto-inject.
    csrf.init_app(app)

    # Rate Limiter: se aplica por ruta con @limiter.limit(...)
    limiter.init_app(app)

    # Límite global de subida: ninguna petición puede pesar más de 12 MB.
    # Sin esto, un archivo gigante (video, ZIP...) ocupa el worker de
    # gunicorn hasta agotar memoria. Las imágenes válidas pesan < 5 MB.
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

    # ── Manejadores de error personalizados ──────────────────────────────────
    @app.errorhandler(413)
    def archivo_muy_grande(e):
        """El navegador envió más de MAX_CONTENT_LENGTH → aviso amigable."""
        flash("El archivo es demasiado grande (máximo 12 MB por envío). "
              "Si es una imagen, redúcela e inténtalo de nuevo.", "danger")
        return redirect(request.referrer or url_for("auth.login")), 302

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        """Formulario expirado o token inválido → volver al origen con aviso."""
        flash("El formulario expiró o es inválido. Recarga la página e intenta de nuevo.", "danger")
        return redirect(request.referrer or url_for("auth.login")), 400

    @app.errorhandler(429)
    def rate_limit_error(e):
        """Demasiados intentos → mostrar login con mensaje de error."""
        return render_template(
            "login.html",
            errores={"general": "Demasiados intentos fallidos. Espera 1 minuto antes de volver a intentar."}
        ), 429

    # Cerrar conexión a la BD al final de cada request
    app.teardown_appcontext(close_db)

    # ── Cabeceras de seguridad básicas ────────────────────────────────────────
    # Sin librería extra: evita que el panel del docente se pueda incrustar en
    # un <iframe> ajeno (clickjacking) y que el navegador "adivine" el tipo de
    # un archivo subido como si fuera ejecutable.
    @app.after_request
    def cabeceras_seguridad(response):
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Foto de perfil del usuario en sesión, disponible en todos los templates
    # (docente_base.html la usa en el sidebar). Resuelve Cloudinary → local → avatar.
    @app.context_processor
    def inject_foto_sidebar():
        from flask import session
        from ws.utils import url_foto_usuario
        def foto_usuario_sidebar():
            uid = session.get("user_id")
            if not uid:
                return ""
            try:
                return url_foto_usuario(app.root_path, uid)
            except Exception:
                return ""
        return {"foto_usuario_sidebar": foto_usuario_sidebar}

    # Registrar todos tus blueprints (auth, docentes, etc.)
    register_blueprints(app)

    @app.route("/ping-db")
    def ping_db():
        """
        Ruta de diagnóstico: verifica que la BD responde.
        Solo accesible en modo DEBUG o con la clave de entorno PING_SECRET.
        En producción (Railway) esta ruta responde 403 sin la clave.
        """
        import os as _os_ping
        from flask import request as _req
        debug_ok  = app.debug
        secret    = _os_ping.environ.get("PING_SECRET", "")
        clave_req = _req.args.get("key", "")
        if not debug_ok and (not secret or clave_req != secret):
            return jsonify({"error": "Forbidden"}), 403

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        cur.close()
        return jsonify({"db_version": version})

    @app.route("/")
    def index():
        """
        Landing page: muestra presentación de la app móvil
        con botón de descarga del APK antes del login.
        Actualiza APK_DOWNLOAD_URL en config.py o variable de entorno.
        """
        apk_url = app.config.get("APK_DOWNLOAD_URL", "#descargar")
        return render_template("landing.html", apk_url=apk_url)

    return app

# Instancia global que usará gunicorn: app:app
app = create_app()

if __name__ == "__main__":
    import os as _os
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=_os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )

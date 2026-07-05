from flask import Flask, jsonify, redirect, url_for, render_template, request, flash
from config import Config
from db import get_db, close_db
from ws import register_blueprints
from flask_wtf.csrf import CSRFProtect, CSRFError
from extensions import limiter

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ── Extensiones ──────────────────────────────────────────────────────────
    # CSRF: protege todos los formularios POST automáticamente.
    #   Los templates deben incluir {{ csrf_token() }} en cada <form method="post">.
    #   Los templates que extienden docente_base.html lo reciben vía JS auto-inject.
    csrf.init_app(app)

    # Rate Limiter: se aplica por ruta con @limiter.limit(...)
    limiter.init_app(app)

    # ── Manejadores de error personalizados ──────────────────────────────────
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

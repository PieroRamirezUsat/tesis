from flask import Flask, jsonify, redirect, url_for
from config import Config
from db import get_db, close_db
from ws import register_blueprints

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Cerrar conexión a la BD al final de cada request
    app.teardown_appcontext(close_db)

    # Registrar todos tus blueprints (auth, docentes, etc.)
    register_blueprints(app)

    @app.route("/ping-db")
    def ping_db():
        """
        Ruta de prueba para ver si la BD responde.
        """
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        cur.close()
        return jsonify({"db_version": version})

    @app.route("/")
    def index():
        # Redirige al login de tu sistema
        return redirect(url_for("auth.login"))

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

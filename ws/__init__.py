# ws/__init__.py

from .auth import bp_auth
from .docentes import bp_docentes
from .salones import bp_salones
from .temas import bp_temas
from .ejercicios import bp_ejercicios
from .reportes import bp_reportes
from .evaluaciones import bp_evaluaciones

def register_blueprints(app):
    """Registra todos los blueprints de la aplicación."""
    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_docentes)
    app.register_blueprint(bp_salones)
    app.register_blueprint(bp_temas)
    app.register_blueprint(bp_ejercicios)
    app.register_blueprint(bp_reportes)
    app.register_blueprint(bp_evaluaciones)
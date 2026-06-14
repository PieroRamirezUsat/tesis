"""
conftest.py — Configuración global de pruebas para TutorMath Web (Flask)
=========================================================================
Estrategia
──────────
• El web usa psycopg (v3) + flask.g.  Se parchea db.get_db() con un mock.
• Se deshabilita CSRF (WTF_CSRF_ENABLED=False) para tests HTTP.
• Se deshabilita el rate limiter (RATELIMIT_ENABLED=False).
• El fixture mock_db configura el cursor antes de cada test.
• Las sesiones de docente se inyectan con client.session_transaction().
"""

import sys
import os
import pytest
from unittest.mock import MagicMock
from werkzeug.security import generate_password_hash

# ──────────────────────────────────────────────────────────────────────────────
# PYTHONPATH
# ──────────────────────────────────────────────────────────────────────────────
WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, WEB_DIR)

# ──────────────────────────────────────────────────────────────────────────────
# Mock de psycopg v3 (puede no estar instalado en el entorno de tests API)
# ──────────────────────────────────────────────────────────────────────────────
_psycopg_mock = MagicMock()
sys.modules.setdefault('psycopg', _psycopg_mock)

# ──────────────────────────────────────────────────────────────────────────────
# Cursor y conexión falsos
# ──────────────────────────────────────────────────────────────────────────────
_WEB_CURSOR = MagicMock(name='web_cursor')
_WEB_CURSOR.fetchone.return_value  = None
_WEB_CURSOR.fetchall.return_value  = []
_WEB_CURSOR.rowcount               = 1

_WEB_CONN = MagicMock(name='web_conn')
_WEB_CONN.cursor.return_value      = _WEB_CURSOR
_WEB_CONN.commit   = MagicMock()
_WEB_CONN.rollback = MagicMock()
_WEB_CONN.close    = MagicMock()

# ──────────────────────────────────────────────────────────────────────────────
# Crear la app Flask con configuración de test
# ──────────────────────────────────────────────────────────────────────────────
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost/testdb')
os.environ.setdefault('SECRET_KEY',   'test-secret-web-tutormath-2026')
os.environ.setdefault('CODIGO_REGISTRO_DOCENTE', 'TEST_COD')

from app import create_app  # noqa: E402
from extensions import limiter as _web_limiter  # noqa: E402

_web_app = create_app()
_web_app.config.update({
    'TESTING':            True,
    'WTF_CSRF_ENABLED':   False,
    'RATELIMIT_ENABLED':  False,
    'SECRET_KEY':         'test-secret-web-tutormath-2026',
    'SERVER_NAME':        'localhost',
})
# flask-limiter 4.x caches self.enabled at init_app() via setdefault — parchear directo
_web_limiter.enabled = False


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures globales
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def app():
    return _web_app


@pytest.fixture(scope='session')
def client(app):
    return app.test_client()


@pytest.fixture
def mock_db(mocker):
    """
    Parchea get_db() en el módulo db Y en cada blueprint.
    Todos usan 'from db import get_db', por lo que parchear solo db.get_db
    no afecta las referencias ya importadas — hay que parchear cada módulo.
    """
    _WEB_CURSOR.reset_mock()
    _WEB_CURSOR.fetchone.return_value  = None
    _WEB_CURSOR.fetchone.side_effect   = None
    _WEB_CURSOR.fetchall.return_value  = []
    _WEB_CURSOR.fetchall.side_effect   = None
    _WEB_CURSOR.rowcount               = 1
    mocker.patch('db.get_db', return_value=_WEB_CONN)
    for mod in ('ws.auth', 'ws.docentes', 'ws.gestionar_estudiante',
                'ws.salones', 'ws.temas', 'ws.ejercicios',
                'ws.evaluaciones', 'ws.reportes'):
        mocker.patch(f'{mod}.get_db', return_value=_WEB_CONN)
    yield _WEB_CURSOR
    _WEB_CURSOR.reset_mock()
    _WEB_CURSOR.fetchone.side_effect = None
    _WEB_CURSOR.fetchall.side_effect = None


@pytest.fixture
def docente_session(client):
    """Inyecta una sesión de docente autenticado en el cliente de test."""
    with client.session_transaction() as sess:
        sess['user_id']     = 1
        sess['user_name']   = 'Prof Ríos'
        sess['user_rol']    = 'docente'
        sess['user_correo'] = 'prof@test.com'
        sess['user_foto']   = None
        sess['id_docente']  = 5
    yield client
    with client.session_transaction() as sess:
        sess.clear()


@pytest.fixture(scope='session')
def docente_row():
    """Fila de docente para mock de BD."""
    return (1, 'Prof', 'Ríos', 'prof@test.com', 'docente', 5,
            generate_password_hash('docpass'))


@pytest.fixture(scope='session')
def estudiante_row():
    return (10, 'Ana', 'García', 3, 40.0, 'activo', 5)
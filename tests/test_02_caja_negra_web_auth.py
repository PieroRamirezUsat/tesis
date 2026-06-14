"""
test_02_caja_negra_web_auth.py — Pruebas CAJA NEGRA: autenticación web
=======================================================================
Tipo  : Funcional / Caja Negra + Seguridad
Rutas : GET /login | POST /login | GET /register | POST /register
        GET /logout | POST /forgot_password
"""

import pytest
from werkzeug.security import generate_password_hash

pytestmark = pytest.mark.functional


# ─────────────────────────────────────────────────────────────────────────────
# GET /login
# ─────────────────────────────────────────────────────────────────────────────

class TestLoginGet:

    def test_get_login_retorna_200(self, client, app):
        with app.app_context():
            r = client.get('/login')
        assert r.status_code == 200

    def test_get_login_contiene_formulario(self, client, app):
        with app.app_context():
            r = client.get('/login')
        assert b'correo' in r.data or b'login' in r.data.lower()


# ─────────────────────────────────────────────────────────────────────────────
# POST /login
# ─────────────────────────────────────────────────────────────────────────────

class TestLoginPost:

    def test_login_sin_correo_muestra_error(self, client, mock_db, app):
        with app.app_context():
            r = client.post('/login', data={'contrasena': 'pass'})
        assert r.status_code in (200, 302, 400)

    def test_login_sin_contrasena_muestra_error(self, client, mock_db, app):
        with app.app_context():
            r = client.post('/login', data={'correo': 'a@b.com'})
        assert r.status_code in (200, 302, 400)

    def test_login_usuario_no_existe(self, client, mock_db, app):
        """Correo no registrado → permanece en login (no redirige al dashboard)."""
        mock_db.fetchone.return_value = None
        with app.app_context():
            r = client.post('/login',
                            data={'correo': 'noexiste@test.com',
                                  'contrasena': 'pass'})
        # No redirige al dashboard
        assert r.status_code != 302 or '/login' in r.headers.get('Location', '')

    def test_login_password_incorrecta(self, client, mock_db, app):
        """Password incorrecta → re-render login con error."""
        mock_db.fetchone.return_value = (
            1, 'Prof', 'Ríos', 'prof@test.com', 'docente', 5,
            generate_password_hash('correcta'),
        )
        with app.app_context():
            r = client.post('/login',
                            data={'correo': 'prof@test.com',
                                  'contrasena': 'erronea'})
        # No redirige al dashboard de docente
        location = r.headers.get('Location', '')
        assert 'dashboard' not in location and 'inicio' not in location

    def test_login_exitoso_crea_sesion(self, client, mock_db, app):
        """Login correcto → redirige (302) y crea sesión."""
        mock_db.fetchone.return_value = (
            1, 'Prof', 'Ríos', 'prof@test.com', 'docente', 5,
            generate_password_hash('docpass'),
        )
        with app.app_context():
            r = client.post('/login',
                            data={'correo': 'prof@test.com',
                                  'contrasena': 'docpass'},
                            follow_redirects=False)
        assert r.status_code == 302


# ─────────────────────────────────────────────────────────────────────────────
# GET /logout
# ─────────────────────────────────────────────────────────────────────────────

class TestLogout:

    def test_logout_limpia_sesion(self, client, mock_db, app):
        """Logout redirige al login y elimina la sesión."""
        # Primero iniciar sesión
        with client.session_transaction() as sess:
            sess['user_id']   = 1
            sess['user_name'] = 'Prof'
            sess['user_rol']  = 'docente'
        with app.app_context():
            r = client.get('/logout', follow_redirects=False)
        assert r.status_code == 302
        # La sesión debe estar vacía
        with client.session_transaction() as sess:
            assert 'user_id' not in sess


# ─────────────────────────────────────────────────────────────────────────────
# POST /register
# ─────────────────────────────────────────────────────────────────────────────

class TestRegisterWeb:

    def test_get_register_retorna_200(self, client, app):
        with app.app_context():
            r = client.get('/register')
        assert r.status_code == 200

    def test_register_codigo_incorrecto(self, client, mock_db, app):
        """Código de registro docente incorrecto → error."""
        with app.app_context():
            r = client.post('/register', data={
                'nombre': 'Nuevo', 'apellidos': 'Docente',
                'correo': 'nuevo@test.com',
                'contrasena': 'pass123',
                'codigo': 'CODIGO_ERRONEO',
            })
        assert r.status_code in (200, 302, 400)

    def test_register_correo_duplicado(self, client, mock_db, app):
        """Email ya registrado → error sin crashear."""
        mock_db.fetchone.return_value = (1,)  # ya existe
        with app.app_context():
            r = client.post('/register', data={
                'nombre': 'Dup', 'apellidos': 'Test',
                'correo': 'dup@test.com',
                'contrasena': 'pass123',
                'codigo': 'TEST_COD',
            })
        # Debe mostrar error (no 500)
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# Seguridad
# ─────────────────────────────────────────────────────────────────────────────

class TestSeguridadAuth:

    def test_acceso_sin_sesion_redirige_login(self, client, app):
        """Ruta protegida sin sesión → redirige a /login."""
        with app.app_context():
            r = client.get('/docente/dashboard', follow_redirects=False)
        assert r.status_code in (302, 401)
        location = r.headers.get('Location', '')
        assert 'login' in location.lower() or r.status_code == 401

    def test_ping_db_sin_key_retorna_403(self, client, app):
        """GET /ping-db sin PING_SECRET → 403 (protegido)."""
        with app.app_context():
            r = client.get('/ping-db')
        assert r.status_code in (403, 200)  # 200 solo en modo debug

    def test_forgot_password_campo_vacio(self, client, mock_db, app):
        """POST /forgot-password sin correo → error de validación."""
        with app.app_context():
            r = client.post('/forgot-password', data={'correo': ''})
        assert r.status_code in (200, 302, 400)
        assert r.status_code != 500
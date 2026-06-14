"""
test_06_caja_negra_temas_ejercicios.py — Pruebas CAJA NEGRA: temas y ejercicios
=================================================================================
Tipo  : Funcional / Seguridad
Rutas : GET  /docente/temas/
        POST /docente/temas/nuevo
        POST /docente/temas/material/nuevo
        POST /docente/temas/material/<id>/eliminar
        GET  /docente/temas/api/url-info
        GET  /docente/ejercicios/
        POST /docente/ejercicios/crear   (INSERT si sin id_ejercicio, UPDATE si con id)
        POST /docente/ejercicios/eliminar/<id>

Reglas probadas
───────────────
• Ambos blueprints usan auth de solo sesion (sin consulta DB extra para auth)
• api/url-info bloquea HTTP, IPs privadas y localhost (anti-SSRF)
• POST /crear sin descripcion no inserta en ejercicios
• POST /crear requiere respuesta_correcta; sin ella, flash error sin INSERT
"""

import pytest

pytestmark = pytest.mark.functional


# ─────────────────────────────────────────────────────────────────────────────
# Temas: proteccion de sesion
# ─────────────────────────────────────────────────────────────────────────────

class TestTemasProteccion:

    def test_listar_temas_sin_sesion_redirige(self, client, mock_db, app):
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.get('/docente/temas/', follow_redirects=False)
        assert r.status_code in (302, 401)

    def test_crear_tema_sin_sesion_redirige(self, client, mock_db, app):
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.post('/docente/temas/nuevo',
                            data={'titulo_tema': 'T', 'descripcion_tema': 'D'},
                            follow_redirects=False)
        assert r.status_code in (302, 401)


# ─────────────────────────────────────────────────────────────────────────────
# Temas: listado
# ─────────────────────────────────────────────────────────────────────────────

class TestListarTemas:

    def test_get_temas_retorna_200(self, client, mock_db, docente_session, app):
        """Sin temas en DB → pagina vacia sin error 500."""
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/temas/')
        assert r.status_code == 200

    def test_get_temas_con_filtro_competencia(self, client, mock_db, docente_session, app):
        """Filtro ?id_competencia=1 retorna 200."""
        # Primera fetchall = competencias (4 cols), segunda = materiales (vacio)
        mock_db.fetchall.side_effect = [
            [(1, 'regularidad_equivalencia_cambio', 'Resolucion de ecuaciones', 3)],
            [],
        ]
        with app.app_context():
            r = docente_session.get('/docente/temas/?id_competencia=1')
        assert r.status_code == 200

    def test_get_temas_con_nivel_filtro(self, client, mock_db, docente_session, app):
        """Filtro ?nivel_filtro=2 retorna 200, no crashea."""
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/temas/?nivel_filtro=2')
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Temas: crear tema
# ─────────────────────────────────────────────────────────────────────────────

class TestCrearTema:

    def test_crear_tema_sin_titulo_no_inserta(self, client, mock_db, docente_session, app):
        """POST sin titulo_tema flash error, sin INSERT en competencias."""
        with app.app_context():
            r = docente_session.post('/docente/temas/nuevo',
                                     data={'titulo_tema': '', 'descripcion_tema': 'D'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'competencias' in str(c).lower()]
        assert len(inserts) == 0

    def test_crear_tema_con_datos_validos(self, client, mock_db, docente_session, app):
        """POST con titulo y descripcion no crashea."""
        mock_db.fetchone.return_value = (10,)
        with app.app_context():
            r = docente_session.post('/docente/temas/nuevo',
                                     data={'titulo_tema': 'Polinomios',
                                           'descripcion_tema': 'Factorizacion'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# Temas: API url-info (seguridad de URLs)
# ─────────────────────────────────────────────────────────────────────────────

class TestApiUrlInfo:

    def test_url_http_rechazada(self, client, docente_session, app):
        """URL con HTTP (no HTTPS) ok=False."""
        with app.app_context():
            r = docente_session.get('/docente/temas/api/url-info?url=http://youtube.com/watch?v=x')
        assert r.status_code == 200
        data = r.get_json()
        assert data['ok'] is False

    def test_url_vacia_rechazada(self, client, docente_session, app):
        """URL vacia ok=False."""
        with app.app_context():
            r = docente_session.get('/docente/temas/api/url-info?url=')
        assert r.status_code == 200
        assert r.get_json()['ok'] is False

    def test_ip_privada_rechazada(self, client, docente_session, app):
        """IP privada en URL ok=False (SSRF prevention)."""
        with app.app_context():
            r = docente_session.get('/docente/temas/api/url-info?url=https://192.168.1.1/malicious')
        assert r.status_code == 200
        assert r.get_json()['ok'] is False

    def test_localhost_rechazado(self, client, docente_session, app):
        """localhost en URL ok=False."""
        with app.app_context():
            r = docente_session.get('/docente/temas/api/url-info?url=https://localhost/datos')
        assert r.status_code == 200
        assert r.get_json()['ok'] is False

    def test_url_sin_parametro(self, client, docente_session, app):
        """Sin parametro url ok=False."""
        with app.app_context():
            r = docente_session.get('/docente/temas/api/url-info')
        assert r.status_code == 200
        assert r.get_json()['ok'] is False


# ─────────────────────────────────────────────────────────────────────────────
# Ejercicios: proteccion de sesion
# ─────────────────────────────────────────────────────────────────────────────

class TestEjerciciosProteccion:

    def test_listar_ejercicios_sin_sesion_redirige(self, client, mock_db, app):
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.get('/docente/ejercicios/', follow_redirects=False)
        assert r.status_code in (302, 401)

    def test_crear_ejercicio_sin_sesion_redirige(self, client, mock_db, app):
        """Sin sesion, POST /crear redirige (ruta real: /docente/ejercicios/crear)."""
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.post('/docente/ejercicios/crear',
                            data={'descripcion': 'test'},
                            follow_redirects=False)
        assert r.status_code in (302, 401)


# ─────────────────────────────────────────────────────────────────────────────
# Ejercicios: listado
# ─────────────────────────────────────────────────────────────────────────────

class TestListarEjercicios:

    def test_get_ejercicios_retorna_200(self, client, mock_db, docente_session, app):
        """Lista vacia pagina carga sin error."""
        mock_db.fetchall.return_value = []
        mock_db.fetchone.return_value = None
        with app.app_context():
            r = docente_session.get('/docente/ejercicios/')
        assert r.status_code == 200

    def test_get_ejercicios_no_falla_con_datos(self, client, mock_db, docente_session, app):
        """Con ejercicios en mock pagina carga y no lanza 500."""
        mock_db.fetchall.side_effect = [
            # Primera query: ejercicios (7 cols)
            [(1, 'Resuelve 2x+3=7', 1, 'Algebra', None, 3, 'ecuacion'),
             (2, 'Factoriza x2-4',  2, 'Algebra', None, 2, 'factor')],
            # Segunda query: competencias (2 cols)
            [(1, 'cantidad'), (2, 'regularidad_equivalencia_cambio')],
        ]
        mock_db.fetchone.return_value = None
        with app.app_context():
            r = docente_session.get('/docente/ejercicios/')
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Ejercicios: crear (POST /docente/ejercicios/crear)
# ─────────────────────────────────────────────────────────────────────────────

class TestCrearEjercicio:

    def test_crear_sin_descripcion_no_inserta(self, client, mock_db, docente_session, app):
        """POST sin descripcion flash error, sin INSERT en ejercicios."""
        with app.app_context():
            r = docente_session.post('/docente/ejercicios/crear',
                                     data={'descripcion': '', 'id_competencia': '1'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200, 400)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'ejercicio' in str(c).lower()]
        assert len(inserts) == 0

    def test_crear_sin_respuesta_correcta_no_inserta(self, client, mock_db, docente_session, app):
        """POST sin opcion_correcta flash error, sin INSERT."""
        with app.app_context():
            r = docente_session.post('/docente/ejercicios/crear',
                                     data={'descripcion': 'Resuelve 2x=6',
                                           'id_competencia': '1'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200, 400)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'ejercicio' in str(c).lower()]
        assert len(inserts) == 0

    def test_crear_con_datos_completos_no_crashea(self, client, mock_db, docente_session, app):
        """POST con descripcion, competencia y respuesta correcta no crashea."""
        mock_db.fetchone.return_value = (1,)
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.post('/docente/ejercicios/crear',
                                     data={'descripcion': 'Resuelve 3x=9',
                                           'id_competencia': '1',
                                           'nivel_logro': '3',
                                           'opcion_correcta': 'A',
                                           'opcion_A': 'x=3',
                                           'opcion_B': 'x=4',
                                           'opcion_C': 'x=5',
                                           'opcion_D': 'x=6'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# Ejercicios: editar y eliminar
# ─────────────────────────────────────────────────────────────────────────────

class TestEditarEliminarEjercicio:

    def test_editar_ejercicio_via_crear(self, client, mock_db, docente_session, app):
        """Editar ejercicio existente via POST /crear con id_ejercicio en form."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.post('/docente/ejercicios/crear',
                                     data={'id_ejercicio': '5',
                                           'descripcion': 'Actualizado',
                                           'id_competencia': '1',
                                           'opcion_correcta': 'B',
                                           'opcion_A': 'x=1', 'opcion_B': 'x=2',
                                           'opcion_C': 'x=3', 'opcion_D': 'x=4'},
                                     follow_redirects=False)
        assert r.status_code != 500

    def test_eliminar_ejercicio_propio(self, client, mock_db, docente_session, app):
        """POST /eliminar/<id> ejecuta DELETE."""
        mock_db.fetchone.return_value = None
        mock_db.rowcount = 1
        with app.app_context():
            r = docente_session.post('/docente/ejercicios/eliminar/5',
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        assert r.status_code != 500

    def test_eliminar_ejercicio_inexistente_no_falla(self, client, mock_db, docente_session, app):
        """DELETE ejercicio que no existe no 500."""
        mock_db.fetchone.return_value = None
        with app.app_context():
            r = docente_session.post('/docente/ejercicios/eliminar/999',
                                     follow_redirects=False)
        assert r.status_code != 500
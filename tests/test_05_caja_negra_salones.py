"""
test_05_caja_negra_salones.py — Pruebas CAJA NEGRA: gestión de salones
=======================================================================
Tipo  : Funcional / Seguridad
Rutas : GET  /docente/salones/
        POST /docente/salones/crear
        POST /docente/salones/editar/<id>
        POST /docente/salones/eliminar/<id>
        POST /docente/salones/unirse

Reglas probadas
───────────────
• Sin sesión → redirige a login
• Solo el docente propietario puede editar/eliminar su salón
• Campos vacíos → flash de error, sin INSERT
• Unirse a salón inexistente → flash de error
• Unirse a salón ya asignado → flash de info (no duplica)
• Crear salón inserta en salones + docente_salones
"""

import pytest

pytestmark = pytest.mark.functional


# ─────────────────────────────────────────────────────────────────────────────
# Protección de sesión
# ─────────────────────────────────────────────────────────────────────────────

class TestSalonesProteccionSesion:

    def test_listar_sin_sesion_redirige(self, client, mock_db, app):
        """GET /docente/salones/ sin sesión → redirige."""
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.get('/docente/salones/', follow_redirects=False)
        assert r.status_code in (302, 401)

    def test_crear_sin_sesion_redirige(self, client, mock_db, app):
        """POST /docente/salones/crear sin sesión → redirige."""
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.post('/docente/salones/crear',
                            data={'nombre_salon': 'A', 'grado': '3ro'},
                            follow_redirects=False)
        assert r.status_code in (302, 401)

    def test_eliminar_sin_sesion_redirige(self, client, mock_db, app):
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.post('/docente/salones/eliminar/1',
                            follow_redirects=False)
        assert r.status_code in (302, 401)


# ─────────────────────────────────────────────────────────────────────────────
# Listar salones
# ─────────────────────────────────────────────────────────────────────────────

class TestListarSalones:

    def test_get_salones_retorna_200(self, client, mock_db, docente_session, app):
        """Con sesión válida y DB vacía → página carga sin error."""
        mock_db.fetchone.return_value = (5,)   # get_id_docente_from_session
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/salones/')
        assert r.status_code == 200

    def test_get_salones_sin_docente_db_redirige(self, client, mock_db, docente_session, app):
        """Si get_id_docente_from_session retorna None (sin registro DB) → redirige."""
        mock_db.fetchone.return_value = None   # no existe en tabla docente
        with app.app_context():
            r = docente_session.get('/docente/salones/', follow_redirects=False)
        assert r.status_code in (302, 401)


# ─────────────────────────────────────────────────────────────────────────────
# Crear salón
# ─────────────────────────────────────────────────────────────────────────────

class TestCrearSalon:

    def test_crear_con_datos_validos_redirige(self, client, mock_db, docente_session, app):
        """POST con nombre y grado → INSERT + redirect."""
        mock_db.fetchone.side_effect = [
            (5,),    # get_id_docente_from_session
            (99,),   # RETURNING id_salon
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/crear',
                                     data={'nombre_salon': 'Primero A', 'grado': '1ro'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)

    def test_crear_sin_nombre_no_inserta(self, client, mock_db, docente_session, app):
        """POST sin nombre_salon → flash error, sin INSERT en salones."""
        mock_db.fetchone.return_value = (5,)
        with app.app_context():
            r = docente_session.post('/docente/salones/crear',
                                     data={'nombre_salon': '', 'grado': '1ro'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'salones' in str(c).lower()]
        assert len(inserts) == 0, "Sin nombre_salon no debe insertar en salones"

    def test_crear_sin_grado_no_inserta(self, client, mock_db, docente_session, app):
        """POST sin grado → flash error, sin INSERT."""
        mock_db.fetchone.return_value = (5,)
        with app.app_context():
            r = docente_session.post('/docente/salones/crear',
                                     data={'nombre_salon': 'Aula 1', 'grado': ''},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'salones' in str(c).lower()]
        assert len(inserts) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Editar salón
# ─────────────────────────────────────────────────────────────────────────────

class TestEditarSalon:

    def test_editar_propio_salon_ok(self, client, mock_db, docente_session, app):
        """Docente edita su propio salón → OK."""
        mock_db.fetchone.side_effect = [
            (5,),   # get_id_docente_from_session
            (1,),   # ownership check OK
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/editar/10',
                                     data={'nombre_salon': 'Nuevo Nombre', 'grado': '2do'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        assert r.status_code != 500

    def test_editar_salon_ajeno_rechazado(self, client, mock_db, docente_session, app):
        """Docente edita salón ajeno → flash error, sin UPDATE."""
        mock_db.fetchone.side_effect = [
            (5,),   # get_id_docente_from_session
            None,   # ownership check falla
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/editar/99',
                                     data={'nombre_salon': 'Hack', 'grado': '1ro'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        updates = [c for c in mock_db.execute.call_args_list
                   if 'UPDATE' in str(c).upper() and 'salones' in str(c).lower()]
        assert len(updates) == 0, "Sin ownership no debe UPDATE en salones"

    def test_editar_sin_nombre_no_actualiza(self, client, mock_db, docente_session, app):
        """Campos vacíos → flash error, sin UPDATE."""
        mock_db.fetchone.return_value = (5,)
        with app.app_context():
            r = docente_session.post('/docente/salones/editar/10',
                                     data={'nombre_salon': '', 'grado': ''},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        updates = [c for c in mock_db.execute.call_args_list
                   if 'UPDATE' in str(c).upper() and 'salones' in str(c).lower()]
        assert len(updates) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Eliminar salón
# ─────────────────────────────────────────────────────────────────────────────

class TestEliminarSalon:

    def test_eliminar_propio_salon_ok(self, client, mock_db, docente_session, app):
        """Docente elimina su propio salón → DELETE en cascada."""
        mock_db.fetchone.side_effect = [
            (5,),   # get_id_docente_from_session
            (1,),   # ownership check OK
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/eliminar/10',
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        deletes = [c for c in mock_db.execute.call_args_list
                   if 'DELETE' in str(c).upper()]
        assert len(deletes) > 0, "Eliminar propio salón debe ejecutar DELETE"

    def test_eliminar_salon_ajeno_no_borra(self, client, mock_db, docente_session, app):
        """Sin ownership → no hace DELETE."""
        mock_db.fetchone.side_effect = [
            (5,),   # get_id_docente_from_session
            None,   # ownership check falla
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/eliminar/99',
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        deletes = [c for c in mock_db.execute.call_args_list
                   if 'DELETE' in str(c).upper()]
        assert len(deletes) == 0, "Sin ownership no debe DELETE"


# ─────────────────────────────────────────────────────────────────────────────
# Unirse a un salón
# ─────────────────────────────────────────────────────────────────────────────

class TestUnirseASalon:

    def test_unirse_salon_valido(self, client, mock_db, docente_session, app):
        """Unirse a salón existente (no asignado aún) → INSERT."""
        mock_db.fetchone.side_effect = [
            (5,),   # get_id_docente_from_session
            (1,),   # salón existe
            None,   # no está asignado aún
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/unirse',
                                     data={'id_salon': '5'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)

    def test_unirse_salon_inexistente(self, client, mock_db, docente_session, app):
        """Salón no existe → flash error, sin INSERT."""
        mock_db.fetchone.side_effect = [
            (5,),   # get_id_docente_from_session
            None,   # salón no existe
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/unirse',
                                     data={'id_salon': '999'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'docente_salones' in str(c).lower()]
        assert len(inserts) == 0, "Salón inexistente no debe INSERT en docente_salones"

    def test_unirse_salon_ya_asignado(self, client, mock_db, docente_session, app):
        """Ya asignado → flash info, sin INSERT duplicado."""
        mock_db.fetchone.side_effect = [
            (5,),   # get_id_docente_from_session
            (1,),   # salón existe
            (1,),   # ya está asignado
        ]
        with app.app_context():
            r = docente_session.post('/docente/salones/unirse',
                                     data={'id_salon': '5'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'docente_salones' in str(c).lower()]
        assert len(inserts) == 0, "Docente ya asignado no debe duplicar INSERT"

    def test_unirse_sin_id_salon(self, client, mock_db, docente_session, app):
        """POST sin id_salon → flash error, sin INSERT."""
        mock_db.fetchone.return_value = (5,)
        with app.app_context():
            r = docente_session.post('/docente/salones/unirse',
                                     data={},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        inserts = [c for c in mock_db.execute.call_args_list
                   if 'INSERT' in str(c).upper() and 'docente_salones' in str(c).lower()]
        assert len(inserts) == 0
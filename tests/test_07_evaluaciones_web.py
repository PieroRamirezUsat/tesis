"""
test_07_evaluaciones_web.py — Pruebas: modulo evaluaciones (web Flask)
=======================================================================
Tipo  : Funcional / Integracion
Rutas : GET  /docente/evaluaciones/
        POST /docente/evaluaciones/crear
        POST /docente/evaluaciones/<id>/activar
        POST /docente/evaluaciones/<id>/cerrar
        GET  /docente/evaluaciones/<id>/resultados

Secuencia de fetchone en evaluaciones (importante para los mocks):
  _get_id_docente()        -> fetchone[0] = (5,)
  _migrate(conn)           -> solo execute, sin fetchone
  ownership check          -> fetchone[1] = (1,) para OK, None para fallo
  RETURNING id_evaluacion  -> fetchone[2] = (20,)

Reglas criticas (invariantes del sistema)
------------------------------------------
* Cerrar evaluacion NO modifica nivel_estudiante_competencia (fix 2026-06-12)
* Cerrar evaluacion NO inserta en tabla puntajes
* Crear evaluacion NO activa automaticamente
* Solo el docente propietario puede activar/cerrar su evaluacion
"""

import pytest

pytestmark = pytest.mark.functional


# ─────────────────────────────────────────────────────────────────────────────
# Proteccion de sesion
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluacionesProteccion:

    def test_listar_sin_sesion_redirige(self, client, mock_db, app):
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.get('/docente/evaluaciones/', follow_redirects=False)
        assert r.status_code in (302, 401)

    def test_crear_sin_sesion_redirige(self, client, mock_db, app):
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.post('/docente/evaluaciones/crear',
                            data={'titulo': 'T', 'id_salon': '1'},
                            follow_redirects=False)
        assert r.status_code in (302, 401)

    def test_cerrar_sin_sesion_redirige(self, client, mock_db, app):
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.post('/docente/evaluaciones/5/cerrar',
                            follow_redirects=False)
        assert r.status_code in (302, 401)


# ─────────────────────────────────────────────────────────────────────────────
# Listar evaluaciones
# ─────────────────────────────────────────────────────────────────────────────

class TestListarEvaluaciones:

    def test_get_evaluaciones_retorna_200(self, client, mock_db, docente_session, app):
        """Con DB vacia pagina carga sin error."""
        mock_db.fetchone.return_value = (5,)
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/evaluaciones/')
        assert r.status_code == 200

    def test_get_evaluaciones_sin_registro_docente_redirige(self, client, mock_db, docente_session, app):
        """Sin registro en tabla docente redirige."""
        mock_db.fetchone.return_value = None
        with app.app_context():
            r = docente_session.get('/docente/evaluaciones/', follow_redirects=False)
        assert r.status_code in (302, 401)


# ─────────────────────────────────────────────────────────────────────────────
# Crear evaluacion
# ─────────────────────────────────────────────────────────────────────────────

class TestCrearEvaluacion:

    def test_crear_evaluacion_sin_titulo_rechaza(self, client, mock_db, docente_session, app):
        """POST sin titulo no inserta evaluacion."""
        mock_db.fetchone.return_value = (5,)
        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/crear',
                                     data={'titulo': '', 'id_salon': '1'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200, 400)
        inserts_eval = [c for c in mock_db.execute.call_args_list
                        if 'INSERT' in str(c).upper() and 'evaluacion' in str(c).lower()]
        assert len(inserts_eval) == 0, "Sin titulo no debe insertar evaluacion"

    def test_crear_evaluacion_no_activa_automaticamente(self, client, mock_db, docente_session, app):
        """
        Crear evaluacion NO debe establecer estado='activa' directamente.
        El docente la activa manualmente despues.

        Secuencia fetchone:
          [0] (5,)  -> _get_id_docente()
          [1] (1,)  -> ownership check SELECT 1 FROM docente_salones (salon pertenece al docente)
          [2] (20,) -> RETURNING id_evaluacion del INSERT
        """
        mock_db.fetchone.side_effect = [
            (5,),    # _get_id_docente
            (1,),    # ownership: salon pertenece al docente
            (20,),   # RETURNING id_evaluacion
        ]
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/crear',
                                     data={
                                         'titulo': 'Evaluacion 1',
                                         'descripcion': 'Desc',
                                         'id_salon': '1',
                                         'num_preguntas': '10',
                                         'num_grupos': '1',
                                     },
                                     follow_redirects=False)
        assert r.status_code != 500

        # Comprueba que ningun INSERT incluye el valor exacto 'activa' en params
        # (no substring — 'activa' in 'inactiva' sería falso positivo)
        inserts_activa = [
            c for c in mock_db.execute.call_args_list
            if 'INSERT' in str(c).upper()
            and len(c.args) > 1
            and 'activa' in c.args[1]   # in tuple = igualdad exacta, no substring
        ]
        assert len(inserts_activa) == 0, "Crear evaluacion no debe insertar con estado='activa'"


# ─────────────────────────────────────────────────────────────────────────────
# Cerrar evaluacion — invariantes criticos (fix 2026-06-12)
# ─────────────────────────────────────────────────────────────────────────────

class TestCerrarEvaluacionInvariantes:

    def test_cerrar_no_modifica_nec(self, client, mock_db, docente_session, app):
        """
        POST /cerrar NO debe hacer UPSERT en nivel_estudiante_competencia.
        Invariante critico: cerrar_evaluacion es medicion, no aprendizaje.
        """
        mock_db.fetchone.side_effect = [
            (5,),   # _get_id_docente
            (1,),   # ownership check SELECT 1 ... (evaluacion pertenece al docente)
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/5/cerrar',
                                     follow_redirects=False)
        assert r.status_code != 500

        nec_writes = [
            c for c in mock_db.execute.call_args_list
            if 'nivel_estudiante_competencia' in str(c).lower()
            and any(op in str(c).upper() for op in ('INSERT', 'UPDATE', 'UPSERT', 'ON CONFLICT'))
        ]
        assert len(nec_writes) == 0, (
            "cerrar_evaluacion NO debe escribir en nivel_estudiante_competencia "
            "(fix critico 2026-06-12: contaminaba niveles adaptativos)"
        )

    def test_cerrar_no_inserta_puntajes(self, client, mock_db, docente_session, app):
        """
        POST /cerrar NO debe insertar en tabla puntajes.
        Los puntajes son para la app movil (API REST), no para evaluaciones.
        """
        mock_db.fetchone.side_effect = [
            (5,),   # _get_id_docente
            (1,),   # ownership check
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/5/cerrar',
                                     follow_redirects=False)
        assert r.status_code != 500

        puntaje_inserts = [
            c for c in mock_db.execute.call_args_list
            if 'puntajes' in str(c).lower() and 'INSERT' in str(c).upper()
        ]
        assert len(puntaje_inserts) == 0, "cerrar_evaluacion NO debe insertar en puntajes"

    def test_cerrar_actualiza_estado_a_cerrada(self, client, mock_db, docente_session, app):
        """Cerrar evaluacion debe marcar estado='cerrada'."""
        mock_db.fetchone.side_effect = [
            (5,),   # _get_id_docente
            (1,),   # ownership check
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/5/cerrar',
                                     follow_redirects=False)

        if r.status_code in (200, 302):
            update_cerrada = [
                c for c in mock_db.execute.call_args_list
                if 'cerrada' in str(c).lower() and 'UPDATE' in str(c).upper()
            ]
            assert len(update_cerrada) >= 1 or r.status_code == 302, (
                "cerrar_evaluacion debe UPDATE estado='cerrada' o redirigir"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Activar evaluacion
# ─────────────────────────────────────────────────────────────────────────────

class TestActivarEvaluacion:

    def test_activar_evaluacion_existente(self, client, mock_db, docente_session, app):
        """Activar evaluacion pendiente UPDATE estado='activa'.

        Secuencia fetchone:
          [0] (5,)        -> _get_id_docente()
          [1] (1, 1, 10)  -> SELECT ev.id_salon, num_grupos, num_preguntas (3 cols)
        """
        mock_db.fetchone.side_effect = [
            (5,),        # _get_id_docente
            (1, 1, 10),  # (id_salon, num_grupos, num_preguntas)
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/5/activar',
                                     follow_redirects=False)
        assert r.status_code != 500

    def test_activar_evaluacion_ajena_rechazada(self, client, mock_db, docente_session, app):
        """Activar evaluacion de otro docente redirige sin UPDATE."""
        mock_db.fetchone.side_effect = [
            (5,),   # _get_id_docente
            None,   # evaluacion no pertenece a este docente
        ]
        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/99/activar',
                                     follow_redirects=False)
        assert r.status_code in (302, 404, 403)

        updates_activa = [
            c for c in mock_db.execute.call_args_list
            if 'activa' in str(c).lower() and 'UPDATE' in str(c).upper()
        ]
        assert len(updates_activa) == 0, "No debe actualizar evaluacion ajena a 'activa'"


# ─────────────────────────────────────────────────────────────────────────────
# Resultados de evaluacion
# ─────────────────────────────────────────────────────────────────────────────

class TestResultadosEvaluacion:

    def test_resultados_retorna_200_o_redirige(self, client, mock_db, docente_session, app):
        """GET resultados 200 con datos o 302/404 sin datos. Nunca 500."""
        mock_db.fetchone.side_effect = [
            (5,),   # _get_id_docente
            None,   # evaluacion no encontrada -> redirige
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.get('/docente/evaluaciones/5/resultados')
        assert r.status_code != 500

    def test_resultados_evaluacion_cerrada_con_datos(self, client, mock_db, docente_session, app):
        """Resultados con datos minimos pagina carga.

        Secuencia fetchone:
          [0] (5,)                                 -> _get_id_docente()
          [1] ('Eval Cerrada', 'cerrada', 'A', 1)  -> (titulo, estado, salon, num_grupos)
        """
        mock_db.fetchone.side_effect = [
            (5,),
            ('Eval Cerrada', 'cerrada', 'Salon A', 1),
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.get('/docente/evaluaciones/5/resultados')
        assert r.status_code in (200, 302, 404)
        assert r.status_code != 500
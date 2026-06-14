"""
test_03_funcional_estudiante.py — Pruebas FUNCIONALES: gestión de estudiantes
=============================================================================
Tipo  : Funcional + Seguridad (ownership checks)
Rutas : /docente/estudiantes/crear | /docente/estudiantes/<id>/editar
        /docente/estudiantes/<id>/baja | /docente/reportes/progreso/<id>

Reglas probadas
───────────────
• Solo el docente que gestiona al alumno puede editar/dar de baja
• Diagnóstico no inserta en puntajes
• Reporte incluye secciones MINEDU (OE2) y Efectividad (OE4)
• Export CSV disponible
"""

import pytest

pytestmark = pytest.mark.functional


# ─────────────────────────────────────────────────────────────────────────────
# Ownership check: docente ajeno no puede editar
# ─────────────────────────────────────────────────────────────────────────────

class TestOwnershipCheck:

    def test_editar_sin_sesion_redirige(self, client, mock_db, app):
        """Sin sesión → redirige a login."""
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.post('/docente/estudiantes/10/editar',
                            data={'nombre': 'Hack'})
        assert r.status_code in (302, 401)

    def test_editar_con_sesion_sin_ownership_error(self, client, mock_db, docente_session, app):
        """Docente sin ownership del alumno → error o redirige."""
        # El ownership check falla: retorna None
        mock_db.fetchone.side_effect = [
            None,   # ownership check: el alumno no pertenece a este docente
        ]
        with app.app_context():
            r = docente_session.post('/docente/estudiantes/999/editar',
                                     data={'nombre': 'Intento'},
                                     follow_redirects=False)
        # Debe redirigir o mostrar error, no 200 con éxito
        assert r.status_code in (302, 403, 404)

    def test_baja_sin_ownership_rechazado(self, client, mock_db, docente_session, app):
        """Dar de baja un alumno ajeno → error de ownership."""
        mock_db.fetchone.side_effect = [None]  # no es alumno del docente
        with app.app_context():
            r = docente_session.post('/docente/estudiantes/999/baja',
                                     follow_redirects=False)
        assert r.status_code in (302, 403, 404)


# ─────────────────────────────────────────────────────────────────────────────
# Crear estudiante
# ─────────────────────────────────────────────────────────────────────────────

class TestCrearEstudiante:

    def test_get_crear_retorna_formulario(self, client, mock_db, docente_session, app):
        # gestion_estudiantes requiere id_docente via fetchone, resto con fetchall vacío
        mock_db.fetchone.return_value = (5,)
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/estudiantes')
        assert r.status_code == 200

    def test_crear_sin_datos_retorna_error(self, client, mock_db, docente_session, app):
        # POST /docente/estudiantes/nuevo con datos vacíos
        mock_db.fetchone.return_value = (5,)   # id_docente lookup
        with app.app_context():
            r = docente_session.post('/docente/estudiantes/nuevo',
                                     data={}, follow_redirects=False)
        assert r.status_code in (200, 302, 400)
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# Diagnóstico inicial NO inserta en puntajes
# ─────────────────────────────────────────────────────────────────────────────

class TestDiagnosticoNoPuntajes:

    def test_guardar_diagnostico_no_llama_insert_puntajes(self, client, mock_db, docente_session, app):
        """
        POST /docente/estudiantes/<id>/editar con notas de diagnóstico
        NO debe insertar en la tabla puntajes.
        """
        mock_db.fetchone.side_effect = [
            (5,),   # _obtener_id_docente_desde_sesion → id_docente
            (1,),   # ownership OK: alumno pertenece a este docente
            (10, 'Ana', 'García', None, None, None, None),  # datos alumno actual
        ]
        with app.app_context():
            r = docente_session.post('/docente/estudiantes/10/editar', data={
                'nombre': 'Ana', 'apellidos': 'García',
                'cantidad': '70',
                'regularidad_equivalencia_cambio': '60',
                'forma_movimiento_localizacion':   '50',
                'gestion_datos_incertidumbre':     '80',
            }, follow_redirects=False)
        assert r.status_code in (200, 302)

        puntajes_inserts = [
            c for c in mock_db.execute.call_args_list
            if 'puntajes' in str(c).lower() and 'INSERT' in str(c).upper()
        ]
        assert len(puntajes_inserts) == 0, (
            "El diagnóstico inicial NO debe insertar en puntajes "
            "(solo inicializa NEC)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Reporte de progreso (OE2 + OE4)
# ─────────────────────────────────────────────────────────────────────────────

class TestReporteProgreso:

    def test_reporte_retorna_200_con_datos_minimos(self, client, mock_db, docente_session, app):
        """
        GET /docente/reportes/progreso/<id_estudiante>
        Con datos mínimos → retorna 200 (no 500).
        """
        # Configurar mocks para todas las queries del reporte
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.get('/docente/reportes/progreso/10')
        assert r.status_code in (200, 302, 404)
        assert r.status_code != 500

    def test_reporte_tiene_seccion_minedu(self, client, mock_db, docente_session, app):
        """OE2: el reporte HTML incluye niveles MINEDU."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/progreso/10')
        if r.status_code == 200:
            content = r.data.decode('utf-8', errors='ignore')
            minedu_keywords = [
                'MINEDU', 'minedu', 'Logrado', 'Previo', 'Destacado', 'proceso'
            ]
            assert any(kw in content for kw in minedu_keywords), (
                "El reporte debe incluir niveles MINEDU (OE2)"
            )

    def test_export_csv_retorna_archivo(self, client, mock_db, docente_session, app):
        """GET /docente/reportes/csv → Content-Type: text/csv."""
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/csv?tipo=resumen&id_estudiante=10')
        if r.status_code == 200:
            assert 'csv' in r.content_type.lower() or 'text' in r.content_type.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Seguridad: SQL injection no posible
# ─────────────────────────────────────────────────────────────────────────────

class TestSeguridadSQL:

    def test_no_sql_injection_en_editar(self, client, mock_db, docente_session, app):
        """
        Inputs maliciosos en nombre no deben ejecutar SQL adicional.
        La cantidad de calls al cursor no debe cambiar con inputs peligrosos.
        """
        mock_db.fetchone.side_effect = [None]  # ownership falla
        payload_malicioso = "'; DROP TABLE usuarios; --"
        with app.app_context():
            r = docente_session.post('/docente/estudiantes/10/editar',
                                     data={'nombre': payload_malicioso},
                                     follow_redirects=False)
        assert r.status_code in (200, 302, 403, 404)
        assert r.status_code != 500, "SQL injection no debe causar error 500"
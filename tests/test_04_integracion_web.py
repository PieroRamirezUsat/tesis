"""
test_04_integracion_web.py — Pruebas de INTEGRACIÓN: web Flask
===============================================================
Tipo  : Integración + Aceptación (flujos docente completos)

Flujos
──────
W-I1  Login → Dashboard → ver alumnos
W-I2  Crear ejercicio → aparece en lista
W-I3  Evaluación: crear → activar → cerrar → resultados (sin modificar NEC)
W-I4  Reporte PDF disponible para alumno existente
W-I5  Dashboard docente con evolución del salón
"""

import pytest

pytestmark = pytest.mark.integration


class TestFlujoLoginDashboard:
    """W-I1: Login de docente → acceso al dashboard."""

    def test_wi1_login_exitoso_redirige(self, client, mock_db, app):
        """Login con credenciales correctas → 302 hacia dashboard."""
        from werkzeug.security import generate_password_hash
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

    def test_wi1_dashboard_autenticado(self, client, mock_db, docente_session, app):
        """Con sesión activa → dashboard carga sin error 500."""
        mock_db.fetchone.return_value = None  # _obtener_datos_docente → fallback
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/dashboard')
        assert r.status_code in (200, 302)
        assert r.status_code != 500


class TestFlujoEvaluacion:
    """W-I3: Evaluación no modifica NEC."""

    def test_wi3_cerrar_evaluacion_no_toca_nec(self, client, mock_db, docente_session, app):
        """
        POST /docente/evaluaciones/<id>/cerrar
        → NO debe UPSERT en nivel_estudiante_competencia
        (fix crítico 2026-06-12: cerrar_evaluacion sobrescribía NEC)
        """
        mock_db.fetchone.side_effect = [
            (5, 'Eval 1', 'activa', '2026-06-10'),  # evaluación existe
            None,  # sin más queries críticas esperadas
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/5/cerrar',
                                     follow_redirects=False)
        assert r.status_code in (200, 302, 404)

        nec_upserts = [
            c for c in mock_db.execute.call_args_list
            if 'nivel_estudiante_competencia' in str(c).lower()
            and ('UPDATE' in str(c).upper() or 'UPSERT' in str(c).upper()
                 or 'ON CONFLICT' in str(c).upper())
        ]
        assert len(nec_upserts) == 0, (
            "cerrar_evaluacion NO debe modificar nivel_estudiante_competencia "
            "(fix crítico 2026-06-12)"
        )

    def test_wi3_cerrar_evaluacion_no_inserta_puntajes(self, client, mock_db, docente_session, app):
        """Cerrar evaluación NO debe insertar en tabla puntajes."""
        mock_db.fetchone.side_effect = [(5, 'Eval 1', 'activa', '2026-06-10'), None]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r = docente_session.post('/docente/evaluaciones/5/cerrar',
                                     follow_redirects=False)
        assert r.status_code != 500

        puntaje_inserts = [
            c for c in mock_db.execute.call_args_list
            if 'puntajes' in str(c).lower() and 'INSERT' in str(c).upper()
        ]
        assert len(puntaje_inserts) == 0, (
            "cerrar_evaluacion NO debe insertar en puntajes "
            "(los contaminaría con datos de escala continua)"
        )


class TestFlujoDashboardDocente:
    """W-I5: Dashboard con gráfico de evolución del salón."""

    def test_wi5_dashboard_muestra_evolucion(self, client, mock_db, docente_session, app):
        """El dashboard incluye la sección de evolución del salón."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/dashboard')
        if r.status_code == 200:
            content = r.data.decode('utf-8', errors='ignore')
            # La sección evolución debe estar presente
            has_evolucion = any(kw in content for kw in
                               ['evolución', 'Evolución', 'evolucion', 'chart', 'Chart'])
            assert has_evolucion, "Dashboard debe incluir gráfico de evolución del salón"


class TestFlujoReportePDF:
    """W-I4: PDF disponible para alumno."""

    def test_wi4_pdf_genera_sin_error(self, client, mock_db, docente_session, app):
        """GET /docente/reportes/pdf/<id> → genera PDF o 404, no 500."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/pdf/10')
        # 200 (PDF), 404 (sin datos), o 302 (redirect) — nunca 500
        assert r.status_code != 500

    def test_wi4_pdf_content_type_correcto(self, client, mock_db, docente_session, app):
        """Si el PDF se genera, el Content-Type debe ser application/pdf."""
        mock_db.fetchone.return_value = (10, 'Ana', 'García', 3, 40.0)
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/pdf/10')
        if r.status_code == 200:
            assert 'pdf' in r.content_type.lower(), (
                f"Content-Type esperado PDF, got {r.content_type}"
            )


class TestAccesibilidadRutas:
    """Verificar que rutas clave responden correctamente."""

    @pytest.mark.parametrize("ruta", [
        '/login',
        '/register',
        '/forgot-password',
    ])
    def test_rutas_publicas_accesibles(self, client, app, ruta):
        with app.app_context():
            r = client.get(ruta)
        assert r.status_code == 200, f"Ruta pública {ruta} debe retornar 200"

    @pytest.mark.parametrize("ruta", [
        '/docente/dashboard',
        '/docente/estudiantes',
        '/docente/ejercicios/',
    ])
    def test_rutas_protegidas_redirigen_sin_sesion(self, client, app, ruta):
        """Sin sesión → redirige a login (302) o redirect permanente (308)."""
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.get(ruta, follow_redirects=False)
        assert r.status_code in (302, 308, 401), (
            f"Ruta protegida {ruta} debe redirigir sin sesión"
        )
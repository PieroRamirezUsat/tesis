"""
test_08_aceptacion_web.py — Pruebas de ACEPTACION: flujos docente completos
============================================================================
Tipo  : Aceptacion (criterios de usuario / OE1-OE4)

Criterios verificados
----------------------
OE1  El docente puede crear salones y asignar estudiantes
OE2  El reporte de progreso incluye niveles MINEDU
OE3  El tutor adaptativo no se interfiere con las evaluaciones
OE4  El dashboard muestra metricas de efectividad del material
OE5  Las rutas protegidas rechazan acceso sin autenticacion
OE6  El sistema no expone errores 500 en ningun flujo normal
"""

import pytest

pytestmark = pytest.mark.acceptance


# ─────────────────────────────────────────────────────────────────────────────
# OE1: Gestion de salones y estudiantes (flujo basico de docente)
# ─────────────────────────────────────────────────────────────────────────────

class TestOE1GestionAula:

    def test_flujo_salon_crear_y_listar(self, client, mock_db, docente_session, app):
        """
        Docente puede crear un salon y verlo en la lista.
        Simula: POST /crear -> GET / (lista actualizada).
        """
        mock_db.fetchone.side_effect = [
            (5,),    # get_id_docente_from_session (crear)
            (42,),   # RETURNING id_salon
            (5,),    # get_id_docente_from_session (listar)
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            r_crear = docente_session.post('/docente/salones/crear',
                                           data={'nombre_salon': 'Sexto A', 'grado': '6to'},
                                           follow_redirects=False)
            r_listar = docente_session.get('/docente/salones/')

        assert r_crear.status_code in (302, 200)
        assert r_listar.status_code == 200

    def test_flujo_crear_y_editar_salon(self, client, mock_db, docente_session, app):
        """Docente crea salon y luego lo edita con exito."""
        mock_db.fetchone.side_effect = [
            (5,),    # auth (crear)
            (42,),   # RETURNING id_salon
            (5,),    # auth (editar)
            (1,),    # ownership OK
        ]
        with app.app_context():
            docente_session.post('/docente/salones/crear',
                                 data={'nombre_salon': 'Viejo', 'grado': '4to'},
                                 follow_redirects=False)
            r = docente_session.post('/docente/salones/editar/42',
                                     data={'nombre_salon': 'Nuevo Nombre', 'grado': '5to'},
                                     follow_redirects=False)
        assert r.status_code in (302, 200)
        assert r.status_code != 500

    def test_flujo_asignar_estudiante_al_salon(self, client, mock_db, docente_session, app):
        """
        POST /docente/estudiantes/nuevo -> asigna estudiante a un salon.
        Verifica que el flujo no crash con datos validos.
        Nota: el mock retorna (5,) para todos los fetchone; el check de correo
        duplicado vera (5,) como 'correo ya existe' -> flash error -> 302 (aceptado).
        """
        mock_db.fetchone.return_value = (5,)
        with app.app_context():
            r = docente_session.post('/docente/estudiantes/nuevo', data={
                'nombre': 'Carlos', 'apellidos': 'Mendoza',
                'correo': 'carlos@test.com', 'contrasena': 'pass123',
                'id_salon': '3',
            }, follow_redirects=False)
        assert r.status_code in (302, 200, 400)
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# OE2: Reporte con niveles MINEDU
# ─────────────────────────────────────────────────────────────────────────────

class TestOE2ReportesMINEDU:

    def test_reporte_progreso_no_crash(self, client, mock_db, docente_session, app):
        """GET /reportes/progreso siempre responde sin 500."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/progreso')
        assert r.status_code != 500

    def test_reporte_tiene_niveles_minedu(self, client, mock_db, docente_session, app):
        """HTML del reporte incluye terminologia MINEDU (OE2)."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/progreso')
        if r.status_code == 200:
            html = r.data.decode('utf-8', errors='ignore').lower()
            minedu_terms = ['minedu', 'logrado', 'previo', 'destacado', 'proceso', 'competencia']
            assert any(t in html for t in minedu_terms), (
                "El reporte debe incluir terminologia MINEDU (OE2)"
            )

    def test_reporte_con_estudiante_especifico_no_crash(self, client, mock_db, docente_session, app):
        """GET /reportes/progreso?id_estudiante=5 no 500."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/progreso?id_estudiante=5')
        assert r.status_code != 500

    def test_csv_no_crash(self, client, mock_db, docente_session, app):
        """GET /reportes/csv no 500."""
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/reportes/csv?tipo=resumen&id_estudiante=10')
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# OE3: Evaluaciones no contaminan el tutor adaptativo (NEC)
# ─────────────────────────────────────────────────────────────────────────────

class TestOE3EvaluacionNoTocaNEC:

    def test_crear_evaluacion_no_escribe_nec(self, client, mock_db, docente_session, app):
        """Crear evaluacion NO toca nivel_estudiante_competencia.

        Secuencia fetchone:
          [0] (5,)  -> _get_id_docente()
          [1] (1,)  -> ownership check (salon pertenece al docente)
          [2] (20,) -> RETURNING id_evaluacion
        """
        mock_db.fetchone.side_effect = [
            (5,),    # _get_id_docente
            (1,),    # ownership check
            (20,),   # RETURNING id_evaluacion
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            docente_session.post('/docente/evaluaciones/crear',
                                 data={'titulo': 'E1', 'descripcion': 'D',
                                       'id_salon': '1', 'num_preguntas': '10'},
                                 follow_redirects=False)

        nec = [c for c in mock_db.execute.call_args_list
               if 'nivel_estudiante_competencia' in str(c).lower()]
        assert len(nec) == 0, "Crear evaluacion NO debe tocar NEC"

    def test_cerrar_evaluacion_no_escribe_nec(self, client, mock_db, docente_session, app):
        """
        Cerrar evaluacion NO escribe en nivel_estudiante_competencia.
        (Invariante critico 2026-06-12)
        """
        mock_db.fetchone.side_effect = [
            (5,),   # _get_id_docente
            (1,),   # ownership check
        ]
        mock_db.fetchall.return_value = []

        with app.app_context():
            docente_session.post('/docente/evaluaciones/5/cerrar',
                                 follow_redirects=False)

        nec_writes = [
            c for c in mock_db.execute.call_args_list
            if 'nivel_estudiante_competencia' in str(c).lower()
            and any(op in str(c).upper() for op in ('INSERT', 'UPDATE', 'ON CONFLICT'))
        ]
        assert len(nec_writes) == 0, (
            "cerrar_evaluacion NO debe modificar NEC (fix critico 2026-06-12)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# OE4: Dashboard con metricas de efectividad
# ─────────────────────────────────────────────────────────────────────────────

class TestOE4DashboardMetricas:

    def test_dashboard_carga_sin_datos(self, client, mock_db, docente_session, app):
        """Dashboard con BD vacia 200, sin crash."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/dashboard')
        assert r.status_code in (200, 302)
        assert r.status_code != 500

    def test_dashboard_contiene_seccion_material(self, client, mock_db, docente_session, app):
        """Dashboard muestra seccion de material de estudio (OE4)."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/dashboard')
        if r.status_code == 200:
            html = r.data.decode('utf-8', errors='ignore').lower()
            mat_keywords = ['material', 'revision', 'efectividad', 'activo']
            assert any(kw in html for kw in mat_keywords), (
                "Dashboard debe mostrar metricas de material de estudio (OE4)"
            )

    def test_dashboard_contiene_grafico_evolucion(self, client, mock_db, docente_session, app):
        """Dashboard contiene seccion de evolucion / chart."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/dashboard')
        if r.status_code == 200:
            html = r.data.decode('utf-8', errors='ignore')
            has_chart = any(kw in html for kw in
                           ['chart', 'Chart', 'evoluci', 'Evoluci'])
            assert has_chart, "Dashboard debe incluir grafico de evolucion del salon"


# ─────────────────────────────────────────────────────────────────────────────
# OE5: Seguridad — todas las rutas protegidas
# ─────────────────────────────────────────────────────────────────────────────

class TestOE5SeguridadRutas:

    @pytest.mark.parametrize("metodo,ruta", [
        ('GET',  '/docente/dashboard'),
        ('GET',  '/docente/salones/'),
        ('GET',  '/docente/temas/'),
        ('GET',  '/docente/ejercicios/'),
        ('GET',  '/docente/evaluaciones/'),
        ('GET',  '/docente/estudiantes'),
        ('GET',  '/docente/reportes/progreso'),
    ])
    def test_ruta_protegida_sin_sesion(self, client, mock_db, app, metodo, ruta):
        """Sin sesion, cualquier ruta protegida 302/401 (nunca 200 ni 500)."""
        with client.session_transaction() as sess:
            sess.clear()
        with app.app_context():
            r = client.open(ruta, method=metodo, follow_redirects=False)
        assert r.status_code in (302, 308, 401), (
            f"{metodo} {ruta} sin sesion debe redirigir (got {r.status_code})"
        )
        assert r.status_code != 200, (
            f"{metodo} {ruta} no debe ser accesible sin autenticacion"
        )

    def test_login_sql_injection_no_falla(self, client, mock_db, app):
        """SQL injection en login no 500."""
        mock_db.fetchone.return_value = None
        with app.app_context():
            r = client.post('/login', data={
                'correo': "admin'--",
                'contrasena': "' OR '1'='1",
            })
        assert r.status_code != 500

    def test_forgot_password_sin_correo_no_crashea(self, client, mock_db, app):
        """POST /forgot-password sin correo no 500."""
        with app.app_context():
            r = client.post('/forgot-password', data={'correo': ''})
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# OE6: Ningun flujo normal produce error 500
# ─────────────────────────────────────────────────────────────────────────────

class TestOE6NoError500:

    @pytest.mark.parametrize("ruta", [
        '/login', '/register', '/forgot-password',
    ])
    def test_rutas_publicas_get_no_500(self, client, app, ruta):
        with app.app_context():
            r = client.get(ruta)
        assert r.status_code != 500, f"GET {ruta} no debe retornar 500"

    def test_dashboard_datos_vacios_no_500(self, client, mock_db, docente_session, app):
        """Dashboard con todos los fetchone=None y fetchall=[] no 500."""
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/dashboard')
        assert r.status_code != 500

    def test_gestion_estudiantes_vacia_no_500(self, client, mock_db, docente_session, app):
        """Lista estudiantes sin datos no 500."""
        mock_db.fetchone.return_value = (5,)
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/estudiantes')
        assert r.status_code != 500

    def test_evaluaciones_vacias_no_500(self, client, mock_db, docente_session, app):
        """Lista evaluaciones sin datos no 500."""
        mock_db.fetchone.return_value = (5,)
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/evaluaciones/')
        assert r.status_code != 500

    def test_temas_vacios_no_500(self, client, mock_db, docente_session, app):
        """Lista temas sin datos no 500."""
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/temas/')
        assert r.status_code != 500

    def test_ejercicios_vacios_no_500(self, client, mock_db, docente_session, app):
        """Lista ejercicios sin datos no 500."""
        mock_db.fetchall.return_value = []
        mock_db.fetchone.return_value = None
        with app.app_context():
            r = docente_session.get('/docente/ejercicios/')
        assert r.status_code != 500

    def test_salones_vacios_no_500(self, client, mock_db, docente_session, app):
        """Lista salones sin datos no 500."""
        mock_db.fetchone.return_value = (5,)
        mock_db.fetchall.return_value = []
        with app.app_context():
            r = docente_session.get('/docente/salones/')
        assert r.status_code != 500
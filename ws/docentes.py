# ws/docentes.py
from flask import (
    Blueprint,
    render_template,
    session,
    redirect,
    url_for,
    request,
    flash,
    current_app,
)
from db import get_db
import os
from ws.utils import url_foto_usuario

bp_docentes = Blueprint("docentes", __name__, url_prefix="/docente")


# -------------------------------------------------------------------
# Utilidades de foto de perfil
# -------------------------------------------------------------------
def _fs_path_foto_usuario(id_usuario: int) -> str:
    """Ruta física de la foto: static/fotos_perfil/user_<id>.jpg"""
    base_path = os.path.join(current_app.root_path, "static", "fotos_perfil")
    os.makedirs(base_path, exist_ok=True)
    return os.path.join(base_path, f"user_{id_usuario}.jpg")


def _url_foto_usuario(id_usuario: int) -> str:
    return url_foto_usuario(current_app.root_path, id_usuario)


# -------------------------------------------------------------------
# Consultar información base del docente
# -------------------------------------------------------------------
def _obtener_datos_docente(id_usuario: int):
    """
    Obtiene nombre, apellidos, correo y especialidad del docente
    usando TUS tablas actuales (usuarios + docente) sin modificarlas.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.nombre,
               u.apellidos,
               u.correo,
               COALESCE(d.especialidad, 'Álgebra'),
               d.id_docente
        FROM usuarios u
        JOIN docente d ON d.id_usuario = u.id_usuario
        WHERE u.id_usuario = %s
        """,
        (id_usuario,),
    )
    fila = cur.fetchone()
    cur.close()

    if fila:
        return {
            "nombre": fila[0],
            "apellidos": fila[1],
            "correo": fila[2],
            "especialidad": fila[3],
            "id_docente": fila[4],
        }

    # Fallback raro (no debería pasar)
    return {
        "nombre": "",
        "apellidos": "",
        "correo": "",
        "especialidad": "Álgebra",
        "id_docente": None,
    }


# -------------------------------------------------------------------
# Métricas del dashboard (todas con tu BD actual)
# -------------------------------------------------------------------
def _metricas_dashboard(id_usuario: int):
    """
    Calcula las métricas que necesita el panel de control del docente,
    usando la estructura REAL de tu base de datos.
    """

    conn = get_db()
    cur = conn.cursor()

    # ==========================================================
    # 0) Obtener id_docente a partir del id_usuario en sesión
    # ==========================================================
    cur.execute(
        "SELECT id_docente FROM docente WHERE id_usuario = %s",
        (id_usuario,),
    )
    row = cur.fetchone()
    if not row:
        # Si por alguna razón no existe registro en docente, devolvemos todo en 0
        cur.close()
        return {
            "total_estudiantes": 0,
            "porc_avanzado": 0,
            "porc_en_progreso": 0,
            "porc_necesita_ayuda": 0,
            "salones": [],
            "temas": [],
            "estudiantes_atencion": [],
            "avanzados": 0,
            "en_progreso": 0,
            "necesita_ayuda": 0,
        }

    id_docente = row[0]

    # ==========================================================
    # 1) Totales y porcentajes por nivel de desempeño
    #    Usa la misma fórmula adaptativa que el gráfico y reportes:
    #    progreso = ((nivel-1)/6)*70 + (puntaje/100)*30
    #    >=70 → avanzado | 40-69 → en progreso | <40 → necesita ayuda
    # ==========================================================
    cur.execute(
        """
        SELECT
            COUNT(*)                                                           AS total,
            SUM(CASE WHEN progreso >= 70              THEN 1 ELSE 0 END)      AS avanzados,
            SUM(CASE WHEN progreso >= 40 AND progreso < 70 THEN 1 ELSE 0 END) AS en_progreso,
            SUM(CASE WHEN progreso < 40               THEN 1 ELSE 0 END)      AS necesita_ayuda
        FROM (
            SELECT
                e.id_estudiante,
                COALESCE(ROUND(AVG(
                    ((nec.nivel_actual::float - 1) / 6.0) * 70.0 +
                    (nec.promedio_puntaje / 100.0) * 30.0
                ))::int, 0) AS progreso
            FROM estudiante e
            JOIN estudiante_salones es ON es.id_estudiante = e.id_estudiante
            JOIN docente_salones ds    ON ds.id_salon      = es.id_salon
            LEFT JOIN nivel_estudiante_competencia nec ON nec.id_estudiante = e.id_estudiante
            WHERE ds.id_docente = %s
            GROUP BY e.id_estudiante
        ) subq
        """,
        (id_docente,),
    )
    band_row = cur.fetchone()
    total_estudiantes = int(band_row[0] or 0)
    avanzados         = int(band_row[1] or 0)
    en_progreso       = int(band_row[2] or 0)
    necesita_ayuda    = int(band_row[3] or 0)

    if total_estudiantes > 0:
        porc_avanzado      = round(avanzados      * 100 / total_estudiantes)
        porc_en_progreso   = round(en_progreso    * 100 / total_estudiantes)
        porc_necesita_ayuda= round(necesita_ayuda * 100 / total_estudiantes)
    else:
        porc_avanzado = porc_en_progreso = porc_necesita_ayuda = 0

    porc_avanzado       = max(0, min(100, porc_avanzado))
    porc_en_progreso    = max(0, min(100, porc_en_progreso))
    porc_necesita_ayuda = max(0, min(100, porc_necesita_ayuda))

    # ==========================================================
    # 2) Salones con mayor actividad
    #    Promedio del progreso_general por salón del docente
    # ==========================================================
    cur.execute(
        """
        SELECT 
            s.nombre_salon,
            COUNT(es.id_estudiante) AS num_estudiantes,
            COALESCE(ROUND(AVG(e.progreso_general), 0), 0) AS progreso_promedio
        FROM salones s
        JOIN docente_salones ds ON ds.id_salon = s.id_salon
        LEFT JOIN estudiante_salones es ON es.id_salon = s.id_salon
        LEFT JOIN estudiante e ON e.id_estudiante = es.id_estudiante
        WHERE ds.id_docente = %s
        GROUP BY s.nombre_salon
        ORDER BY progreso_promedio DESC
        """,
        (id_docente,),
    )
    salones_rows = cur.fetchall()
    salones = [
        {
            "salon": row[0],
            "num_estudiantes": row[1],
            "progreso_promedio": int(row[2]),
        }
        for row in salones_rows
    ]

    # ==========================================================
    # 3) Rendimiento promedio por tema (competencias.area)
    #    Usamos la tabla puntajes (0–100) y promediamos por área.
    #    Resultado SIEMPRE entre 0 y 100.
    # ==========================================================
    cur.execute(
        """
        SELECT
            c.area,
            COALESCE(AVG(p.puntaje), 0) AS promedio_pct
        FROM puntajes p
        JOIN competencias c ON c.id_competencia = p.id_competencia
        WHERE p.id_estudiante IN (
            SELECT DISTINCT es.id_estudiante
            FROM docente_salones ds
            JOIN estudiante_salones es ON es.id_salon = ds.id_salon
            WHERE ds.id_docente = %s
        )
        GROUP BY c.area
        ORDER BY promedio_pct DESC
        LIMIT 4
        """,
        (id_docente,),
    )
    temas_rows = cur.fetchall()
    temas = []
    for row in temas_rows:
        pct = row[1] or 0
        pct = int(round(float(pct)))
        pct = max(0, min(100, pct))  # clamp 0–100
        temas.append(
            {
                "area": row[0],
                "porcentaje": pct,
            }
        )

    # ==========================================================
    # 4) Estudiantes que requieren atención
    #    Los 3 con peor promedio en competencias.
    #    Incluimos id_estudiante e id_salon para enlazar a Reportes.
    # ==========================================================
    cur.execute(
        """
        SELECT
            e.id_estudiante,
            MIN(es.id_salon)                            AS id_salon,
            u.nombre,
            u.apellidos,
            COALESCE(
                ROUND(AVG(
                    ((nec.nivel_actual::float - 1) / 6.0) * 70.0 +
                    (nec.promedio_puntaje / 100.0) * 30.0
                ))::int, 0
            )                                           AS progreso_general,
            (
                SELECT c2.area
                FROM nivel_estudiante_competencia nec2
                JOIN competencias c2 ON c2.id_competencia = nec2.id_competencia
                WHERE nec2.id_estudiante = e.id_estudiante
                ORDER BY (
                    ((nec2.nivel_actual::float - 1) / 6.0) * 70.0 +
                    (nec2.promedio_puntaje / 100.0) * 30.0
                ) ASC
                LIMIT 1
            )                                           AS peor_area,
            (
                SELECT COALESCE(
                    ROUND(
                        ((nec2.nivel_actual::float - 1) / 6.0) * 70.0 +
                        (nec2.promedio_puntaje / 100.0) * 30.0
                    )::int, 0)
                FROM nivel_estudiante_competencia nec2
                WHERE nec2.id_estudiante = e.id_estudiante
                ORDER BY (
                    ((nec2.nivel_actual::float - 1) / 6.0) * 70.0 +
                    (nec2.promedio_puntaje / 100.0) * 30.0
                ) ASC
                LIMIT 1
            )                                           AS peor_progreso
        FROM estudiante e
        JOIN usuarios u ON u.id_usuario = e.id_usuario
        JOIN estudiante_salones es ON es.id_estudiante = e.id_estudiante
        JOIN docente_salones ds ON ds.id_salon = es.id_salon
        LEFT JOIN nivel_estudiante_competencia nec ON nec.id_estudiante = e.id_estudiante
        WHERE ds.id_docente = %s
        GROUP BY e.id_estudiante, u.nombre, u.apellidos
        ORDER BY progreso_general ASC
        LIMIT 3
        """,
        (id_docente,),
    )
    _ETIQUETAS_AREA = {
        "cantidad":                       "Resuelve problemas de cantidad",
        "regularidad_equivalencia_cambio": "Regularidad, equiv. y cambio",
        "forma_movimiento_localizacion":   "Forma, movimiento y localiz.",
        "gestion_datos_incertidumbre":     "Gestión de datos e incert.",
    }
    est_rows = cur.fetchall()
    estudiantes_atencion = [
        {
            "id_estudiante":  row[0],
            "id_salon":       row[1],
            "nombre_completo": f"{row[2]} {row[3]}",
            "peor_area":      row[5],
            "peor_progreso":  int(row[6]) if row[6] is not None else 0,
            "peor_etiqueta":  _ETIQUETAS_AREA.get(row[5], "Competencias de álgebra") if row[5] else "Sin datos de competencia",
        }
        for row in est_rows
    ]

    # ==========================================================
    # 5) Todos los estudiantes con su progreso (para el gráfico)
    #    Usa la misma fórmula adaptativa que la página de Reportes:
    #    porcentaje = ((nivel_actual-1)/6)*70 + (promedio_puntaje/100)*30
    # ==========================================================
    cur.execute(
        """
        SELECT
            u.nombre || ' ' || u.apellidos AS nombre_completo,
            COALESCE(
                ROUND(
                    AVG(
                        ((nec.nivel_actual::float - 1) / 6.0) * 70.0 +
                        (nec.promedio_puntaje / 100.0) * 30.0
                    )
                )::int,
                0
            ) AS progreso,
            e.id_estudiante,
            MIN(es.id_salon) AS id_salon
        FROM estudiante e
        JOIN usuarios u                ON u.id_usuario     = e.id_usuario
        JOIN estudiante_salones es     ON es.id_estudiante = e.id_estudiante
        JOIN docente_salones ds        ON ds.id_salon      = es.id_salon
        LEFT JOIN nivel_estudiante_competencia nec
                                       ON nec.id_estudiante = e.id_estudiante
        WHERE ds.id_docente = %s
        GROUP BY e.id_estudiante, u.nombre, u.apellidos
        ORDER BY progreso ASC, u.apellidos
        """,
        (id_docente,),
    )
    estudiantes_chart = [
        {"nombre": r[0], "progreso": r[1], "id_estudiante": r[2], "id_salon": r[3]}
        for r in cur.fetchall()
    ]

    cur.close()

    return {
        "total_estudiantes": total_estudiantes,
        "porc_avanzado": porc_avanzado,
        "porc_en_progreso": porc_en_progreso,
        "porc_necesita_ayuda": porc_necesita_ayuda,
        "salones": salones,
        "temas": temas,
        "estudiantes_atencion": estudiantes_atencion,
        "avanzados": avanzados,
        "en_progreso": en_progreso,
        "necesita_ayuda": necesita_ayuda,
        "estudiantes_chart": estudiantes_chart,
    }


# -------------------------------------------------------------------
# RUTAS
# -------------------------------------------------------------------
@bp_docentes.route("/dashboard")
def dashboard():
    """
    Panel de control del docente:
    Usa las métricas calculadas arriba y el mismo menú lateral
    que el perfil.
    """
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    id_usuario = session["user_id"]
    datos = _obtener_datos_docente(id_usuario)
    met = _metricas_dashboard(id_usuario)
    foto_url = _url_foto_usuario(id_usuario)
    nombre_completo = f"{datos['nombre']} {datos['apellidos']}".strip()

    # Para el gráfico donut necesitamos offsets acumulados
    offset_progreso = met["porc_avanzado"]
    offset_ayuda = met["porc_avanzado"] + met["porc_en_progreso"]

    return render_template(
        "docente_dashboard.html",
        titulo="Panel de Control - Sistema de Álgebra Inteligente",
        # datos de usuario
        nombre=datos["nombre"],
        apellidos=datos["apellidos"],
        correo=datos["correo"],
        especialidad=datos["especialidad"],
        foto_url=foto_url,
        nombre_completo=nombre_completo,
        # métricas
        total_estudiantes=met["total_estudiantes"],
        porc_avanzado=met["porc_avanzado"],
        porc_en_progreso=met["porc_en_progreso"],
        porc_necesita_ayuda=met["porc_necesita_ayuda"],
        avanzados=met["avanzados"],
        en_progreso=met["en_progreso"],
        necesita_ayuda=met["necesita_ayuda"],
        salones=met["salones"],
        temas=met["temas"],
        estudiantes_atencion=met["estudiantes_atencion"],
        estudiantes_chart=met["estudiantes_chart"],
        offset_progreso=offset_progreso,
        offset_ayuda=offset_ayuda,
        active_page="dashboard",
    )


@bp_docentes.route("/perfil", methods=["GET", "POST"])
def perfil():
    """
    Muestra y permite editar el perfil del docente.
    """
    # Validar que esté logueado y sea docente
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    id_usuario = session["user_id"]

    if request.method == "POST":
        # 1. Leer datos del formulario
        nombre = request.form.get("nombre", "").strip()
        apellidos = request.form.get("apellidos", "").strip()
        especialidad = request.form.get("especialidad", "").strip()

        # 2. Validaciones básicas
        if not nombre or not apellidos:
            flash("Nombre y apellidos son obligatorios.", "danger")
        else:
            conn = get_db()
            cur = conn.cursor()
            # Actualizar tabla usuarios
            cur.execute(
                """
                UPDATE usuarios
                SET nombre = %s, apellidos = %s
                WHERE id_usuario = %s
                """,
                (nombre, apellidos, id_usuario),
            )
            # Actualizar tabla docente (solo especialidad)
            cur.execute(
                """
                UPDATE docente
                SET especialidad = %s
                WHERE id_usuario = %s
                """,
                (especialidad if especialidad else "Álgebra", id_usuario),
            )
            conn.commit()
            cur.close()

            # Actualizar también los datos en sesión
            session["user_nombre"] = nombre
            session["user_apellidos"] = apellidos

            flash("Perfil actualizado correctamente.", "success")

        # 3. Procesar foto (si viene archivo)
        foto = request.files.get("foto")
        if foto and foto.filename:
            try:
                fs_path = _fs_path_foto_usuario(id_usuario)
                foto.save(fs_path)
                flash("Foto de perfil actualizada.", "success")
            except Exception as e:
                print("Error guardando foto:", e)
                flash("No se pudo guardar la foto de perfil.", "danger")

        return redirect(url_for("docentes.perfil"))

    # GET
    datos = _obtener_datos_docente(id_usuario)
    foto_url = _url_foto_usuario(id_usuario)
    nombre_completo = f"{datos['nombre']} {datos['apellidos']}".strip()

    return render_template(
        "docente_perfil.html",
        active_page="perfil",
        titulo="Perfil del Profesor - Sistema de Álgebra Inteligente",
        nombre=datos["nombre"],
        apellidos=datos["apellidos"],
        correo=datos["correo"],
        especialidad=datos["especialidad"],
        foto_url=foto_url,
        nombre_completo=nombre_completo,
    )


# Importa las rutas de gestión de estudiantes
from . import gestionar_estudiante

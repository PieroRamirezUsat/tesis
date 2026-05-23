from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from db import get_db
import json, random

# Tabla score→nivel compartida con la API REST y gestionar_estudiante
_BRACKETS = [(0,21,1),(22,35,2),(36,49,3),(50,64,4),(65,78,5),(79,92,6),(93,100,7)]

def _score_to_nivel(score):
    s = max(0.0, min(100.0, float(score or 0)))
    for lo, hi, nivel in _BRACKETS:
        if lo <= s <= hi:
            return nivel
    return 7


def _format_duracion_seg(segundos) -> str:
    """Convierte segundos a '4m 32s'. Retorna '—' si es None o negativo."""
    if segundos is None or segundos < 0:
        return "—"
    segundos = int(segundos)
    minutos = segundos // 60
    seg = segundos % 60
    if minutos >= 60:
        h = minutos // 60
        m = minutos % 60
        return f"{h}h {m}m"
    if minutos == 0:
        return f"{seg}s"
    return f"{minutos}m {seg}s"

bp_evaluaciones = Blueprint("evaluaciones", __name__, url_prefix="/docente/evaluaciones")

LETRAS_GRUPO = ['A', 'B', 'C', 'D', 'E', 'F']


def _get_id_docente():
    if "user_id" not in session or session.get("user_rol") != "docente":
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id_docente FROM docente WHERE id_usuario = %s", (session["user_id"],))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None


def _migrate(conn):
    """Auto-migrate columns and tables for evaluaciones."""
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE evaluaciones ADD COLUMN IF NOT EXISTS num_preguntas INTEGER DEFAULT 10")
        cur.execute("ALTER TABLE evaluaciones ADD COLUMN IF NOT EXISTS num_grupos INTEGER DEFAULT 1")
        cur.execute("ALTER TABLE evaluaciones ADD COLUMN IF NOT EXISTS ejercicios_grupos TEXT")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evaluacion_grupos (
                id_evaluacion INTEGER NOT NULL,
                id_estudiante INTEGER NOT NULL,
                grupo         VARCHAR(5) NOT NULL,
                PRIMARY KEY (id_evaluacion, id_estudiante)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evaluacion_respuestas (
                id              SERIAL PRIMARY KEY,
                id_evaluacion   INTEGER NOT NULL,
                id_estudiante   INTEGER NOT NULL,
                id_ejercicio    INTEGER NOT NULL,
                id_opcion       INTEGER,
                es_correcta     BOOLEAN DEFAULT FALSE,
                fecha           TIMESTAMP DEFAULT NOW(),
                UNIQUE (id_evaluacion, id_estudiante, id_ejercicio)
            )
        """)
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()


def _asignar_grupos(conn, id_evaluacion, id_salon, num_grupos, num_preguntas):
    """Assign students to groups A/B/C and pre-select exercises per group."""
    cur = conn.cursor()
    try:
        # Students in salon ordered alphabetically
        cur.execute(
            """
            SELECT e.id_estudiante
            FROM estudiante e
            JOIN estudiante_salones es ON es.id_estudiante = e.id_estudiante
            JOIN usuarios u ON u.id_usuario = e.id_usuario
            WHERE es.id_salon = %s
            ORDER BY u.apellidos, u.nombre
            """,
            (id_salon,),
        )
        students = [r[0] for r in cur.fetchall()]

        if not students:
            cur.close()
            return

        letras = LETRAS_GRUPO[:num_grupos]

        # Delete previous assignments for this evaluation
        cur.execute("DELETE FROM evaluacion_grupos WHERE id_evaluacion = %s", (id_evaluacion,))

        # Round-robin assignment
        for i, id_est in enumerate(students):
            grupo = letras[i % num_grupos]
            cur.execute(
                """
                INSERT INTO evaluacion_grupos (id_evaluacion, id_estudiante, grupo)
                VALUES (%s, %s, %s)
                ON CONFLICT (id_evaluacion, id_estudiante) DO UPDATE SET grupo = EXCLUDED.grupo
                """,
                (id_evaluacion, id_est, grupo),
            )

        # Pre-select exercises per group (different exercises to prevent copying)
        cur.execute("SELECT id_ejercicio FROM ejercicios")
        all_ids = [r[0] for r in cur.fetchall()]
        random.shuffle(all_ids)

        ejercicios_grupos = {}
        for idx, letra in enumerate(letras):
            pool = []
            for j in range(num_preguntas):
                pool.append(all_ids[(idx * num_preguntas + j) % max(1, len(all_ids))])
            ejercicios_grupos[letra] = pool

        cur.execute(
            "UPDATE evaluaciones SET ejercicios_grupos = %s WHERE id_evaluacion = %s",
            (json.dumps(ejercicios_grupos), id_evaluacion),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()


@bp_evaluaciones.route("/")
def gestion_evaluaciones():
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    _migrate(conn)
    cur = conn.cursor()

    # Salones del docente
    cur.execute(
        """
        SELECT s.id_salon, s.nombre_salon
        FROM salones s
        JOIN docente_salones ds ON ds.id_salon = s.id_salon
        WHERE ds.id_docente = %s
        ORDER BY s.nombre_salon
        """,
        (id_docente,),
    )
    salones = [{"id_salon": r[0], "nombre": r[1]} for r in cur.fetchall()]
    id_salones = [s["id_salon"] for s in salones]

    # Evaluación activa por salón (para advertencia)
    activa_por_salon = {}
    if id_salones:
        cur.execute(
            """
            SELECT id_salon, id_evaluacion, titulo
            FROM evaluaciones
            WHERE estado = 'activa' AND id_salon = ANY(%s)
            """,
            (id_salones,),
        )
        for r in cur.fetchall():
            activa_por_salon[str(r[0])] = {"id": r[1], "titulo": r[2]}

    # Lista de evaluaciones
    cur.execute(
        """
        SELECT
            ev.id_evaluacion, ev.titulo, ev.descripcion, ev.estado,
            ev.fecha_inicio, ev.fecha_fin, s.id_salon, s.nombre_salon,
            COUNT(DISTINCT er.id_estudiante) AS num_completadas,
            COALESCE(ev.num_preguntas, 10)   AS num_preguntas,
            COALESCE(ev.num_grupos, 1)        AS num_grupos
        FROM evaluaciones ev
        JOIN salones s ON s.id_salon = ev.id_salon
        JOIN docente_salones ds ON ds.id_salon = ev.id_salon
        LEFT JOIN evaluacion_resultados er
            ON er.id_evaluacion = ev.id_evaluacion AND er.estado = 'completado'
        WHERE ds.id_docente = %s
        GROUP BY ev.id_evaluacion, ev.titulo, ev.descripcion, ev.estado,
                 ev.fecha_inicio, ev.fecha_fin, s.id_salon, s.nombre_salon,
                 ev.num_preguntas, ev.num_grupos
        ORDER BY ev.fecha_inicio DESC NULLS LAST, ev.id_evaluacion DESC
        """,
        (id_docente,),
    )
    evaluaciones = [
        {
            "id_evaluacion": r[0], "titulo": r[1], "descripcion": r[2],
            "estado": r[3], "fecha_inicio": r[4], "fecha_fin": r[5],
            "id_salon": r[6], "nombre_salon": r[7],
            "num_completadas": r[8], "num_preguntas": r[9], "num_grupos": r[10],
        }
        for r in cur.fetchall()
    ]
    cur.close()

    return render_template(
        "docente_evaluaciones.html",
        titulo_pagina="Gestión de Evaluaciones",
        active_page="evaluaciones",
        salones=salones,
        evaluaciones=evaluaciones,
        activa_por_salon=activa_por_salon,
    )


@bp_evaluaciones.route("/crear", methods=["POST"])
def crear_evaluacion():
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    titulo       = request.form.get("titulo", "").strip()
    descripcion  = request.form.get("descripcion", "").strip()
    id_salon     = request.form.get("id_salon", type=int)
    fecha_inicio = request.form.get("fecha_inicio") or None
    fecha_fin    = request.form.get("fecha_fin") or None
    activar      = request.form.get("activar_al_crear") == "1"

    try:
        num_preguntas = max(1, min(50, int(request.form.get("num_preguntas") or 10)))
    except (ValueError, TypeError):
        num_preguntas = 10

    try:
        num_grupos = max(1, min(6, int(request.form.get("num_grupos") or 1)))
    except (ValueError, TypeError):
        num_grupos = 1

    if not titulo or not id_salon:
        flash("El título y el salón son obligatorios.", "danger")
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    conn = get_db()
    _migrate(conn)
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM docente_salones WHERE id_docente = %s AND id_salon = %s",
        (id_docente, id_salon),
    )
    if not cur.fetchone():
        flash("El salón seleccionado no te pertenece.", "danger")
        cur.close()
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    # Solo puede haber una evaluación activa por salón
    if activar:
        cur.execute(
            "UPDATE evaluaciones SET estado = 'inactiva' WHERE id_salon = %s AND estado = 'activa'",
            (id_salon,),
        )

    estado = "activa" if activar else "inactiva"
    id_evaluacion = None
    try:
        cur.execute(
            """
            INSERT INTO evaluaciones
                (titulo, descripcion, estado, fecha_inicio, fecha_fin, id_salon, num_preguntas, num_grupos)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id_evaluacion
            """,
            (titulo, descripcion or None, estado, fecha_inicio, fecha_fin,
             id_salon, num_preguntas, num_grupos),
        )
        id_evaluacion = cur.fetchone()[0]
        conn.commit()
    except Exception:
        conn.rollback()
        cur.execute(
            """
            INSERT INTO evaluaciones (titulo, descripcion, estado, fecha_inicio, fecha_fin, id_salon)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id_evaluacion
            """,
            (titulo, descripcion or None, estado, fecha_inicio, fecha_fin, id_salon),
        )
        id_evaluacion = cur.fetchone()[0]
        conn.commit()

    cur.close()

    # Asignar grupos si la evaluación se activa con grupos
    if activar and num_grupos > 1 and id_evaluacion:
        try:
            _asignar_grupos(conn, id_evaluacion, id_salon, num_grupos, num_preguntas)
        except Exception:
            pass

    flash(f"Evaluación '{titulo}' creada {'y activada' if activar else ''}.", "success")
    return redirect(url_for("evaluaciones.gestion_evaluaciones"))


@bp_evaluaciones.route("/<int:id_evaluacion>/activar", methods=["POST"])
def activar_evaluacion(id_evaluacion):
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    _migrate(conn)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT ev.id_salon, COALESCE(ev.num_grupos, 1), COALESCE(ev.num_preguntas, 10)
        FROM evaluaciones ev
        JOIN docente_salones ds ON ds.id_salon = ev.id_salon
        WHERE ev.id_evaluacion = %s AND ds.id_docente = %s
        """,
        (id_evaluacion, id_docente),
    )
    row = cur.fetchone()
    if not row:
        flash("Evaluación no encontrada.", "danger")
        cur.close()
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    id_salon, num_grupos, num_preguntas = row

    # Desactivar otras evaluaciones activas del mismo salón
    cur.execute(
        """
        UPDATE evaluaciones SET estado = 'inactiva'
        WHERE id_salon = %s AND estado = 'activa' AND id_evaluacion != %s
        """,
        (id_salon, id_evaluacion),
    )
    cur.execute(
        "UPDATE evaluaciones SET estado = 'activa' WHERE id_evaluacion = %s",
        (id_evaluacion,),
    )
    conn.commit()
    cur.close()

    # Asignar grupos y ejercicios pre-seleccionados
    if num_grupos > 1:
        try:
            _asignar_grupos(conn, id_evaluacion, id_salon, num_grupos, num_preguntas)
        except Exception:
            pass

    flash("Evaluación activada. Los estudiantes del salón ya pueden verla.", "success")
    return redirect(url_for("evaluaciones.gestion_evaluaciones"))


@bp_evaluaciones.route("/<int:id_evaluacion>/cerrar", methods=["POST"])
def cerrar_evaluacion(id_evaluacion):
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    # Verificar que la evaluación pertenece al docente
    cur.execute(
        """
        SELECT 1 FROM evaluaciones ev
        JOIN docente_salones ds ON ds.id_salon = ev.id_salon
        WHERE ev.id_evaluacion = %s AND ds.id_docente = %s
        """,
        (id_evaluacion, id_docente),
    )
    if not cur.fetchone():
        flash("Evaluación no encontrada.", "danger")
        cur.close()
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    cur.execute(
        "UPDATE evaluaciones SET estado = 'cerrada' WHERE id_evaluacion = %s",
        (id_evaluacion,),
    )

    # Sincronizar puntajes por competencia → nivel_estudiante_competencia
    # Para cada estudiante que completó la evaluación, calculamos su % correcto
    # por competencia basándonos en las respuestas registradas.
    cur.execute(
        """
        SELECT
            er.id_estudiante,
            ej.id_competencia,
            COUNT(*) FILTER (WHERE ev_r.es_correcta = TRUE)  AS correctas,
            COUNT(*)                                          AS total
        FROM evaluacion_respuestas ev_r
        JOIN ejercicios ej ON ej.id_ejercicio = ev_r.id_ejercicio
        JOIN evaluacion_resultados er
            ON er.id_evaluacion = ev_r.id_evaluacion
           AND er.id_estudiante = ev_r.id_estudiante
           AND er.estado = 'completado'
        WHERE ev_r.id_evaluacion = %s
          AND ej.id_competencia IS NOT NULL
        GROUP BY er.id_estudiante, ej.id_competencia
        """,
        (id_evaluacion,),
    )
    filas_comp = cur.fetchall()

    for id_est, id_comp, correctas, total in filas_comp:
        puntaje = round(correctas / total * 100) if total else 0
        nivel = _score_to_nivel(puntaje)
        cur.execute(
            """
            INSERT INTO nivel_estudiante_competencia
                (id_estudiante, id_competencia, nivel_actual,
                 promedio_puntaje, ejercicios_considerados, fecha_ultimo_update)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (id_estudiante, id_competencia) DO UPDATE SET
                nivel_actual            = EXCLUDED.nivel_actual,
                promedio_puntaje        = EXCLUDED.promedio_puntaje,
                ejercicios_considerados = EXCLUDED.ejercicios_considerados,
                fecha_ultimo_update     = EXCLUDED.fecha_ultimo_update
            """,
            (id_est, id_comp, nivel, float(puntaje), total),
        )
        cur.execute(
            """
            INSERT INTO puntajes (puntaje, id_competencia, id_estudiante)
            VALUES (%s, %s, %s)
            """,
            (puntaje, id_comp, id_est),
        )

    conn.commit()
    cur.close()
    flash("Evaluación cerrada.", "success")
    return redirect(url_for("evaluaciones.gestion_evaluaciones"))


@bp_evaluaciones.route("/<int:id_evaluacion>/editar", methods=["POST"])
def editar_evaluacion(id_evaluacion):
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    titulo       = request.form.get("titulo", "").strip()
    descripcion  = request.form.get("descripcion", "").strip()
    id_salon     = request.form.get("id_salon", type=int)
    fecha_inicio = request.form.get("fecha_inicio") or None
    fecha_fin    = request.form.get("fecha_fin") or None

    try:
        num_preguntas = max(1, min(50, int(request.form.get("num_preguntas") or 10)))
    except (ValueError, TypeError):
        num_preguntas = 10

    try:
        num_grupos = max(1, min(6, int(request.form.get("num_grupos") or 1)))
    except (ValueError, TypeError):
        num_grupos = 1

    if not titulo or not id_salon:
        flash("El título y el salón son obligatorios.", "danger")
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    conn = get_db()
    _migrate(conn)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE evaluaciones
            SET titulo = %s, descripcion = %s, id_salon = %s,
                fecha_inicio = %s, fecha_fin = %s,
                num_preguntas = %s, num_grupos = %s
            WHERE id_evaluacion = %s
              AND id_salon IN (SELECT id_salon FROM docente_salones WHERE id_docente = %s)
            """,
            (titulo, descripcion or None, id_salon, fecha_inicio, fecha_fin,
             num_preguntas, num_grupos, id_evaluacion, id_docente),
        )
    except Exception:
        conn.rollback()
        cur.execute(
            """
            UPDATE evaluaciones
            SET titulo = %s, descripcion = %s, id_salon = %s,
                fecha_inicio = %s, fecha_fin = %s
            WHERE id_evaluacion = %s
              AND id_salon IN (SELECT id_salon FROM docente_salones WHERE id_docente = %s)
            """,
            (titulo, descripcion or None, id_salon, fecha_inicio, fecha_fin,
             id_evaluacion, id_docente),
        )
    conn.commit()
    cur.close()
    flash("Evaluación actualizada.", "success")
    return redirect(url_for("evaluaciones.gestion_evaluaciones"))


@bp_evaluaciones.route("/<int:id_evaluacion>/eliminar", methods=["POST"])
def eliminar_evaluacion(id_evaluacion):
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()
    try:
        # Verificar que la evaluación pertenece a un salón del docente
        cur.execute(
            """
            SELECT id_evaluacion FROM evaluaciones
            WHERE id_evaluacion = %s
              AND id_salon IN (SELECT id_salon FROM docente_salones WHERE id_docente = %s)
            """,
            (id_evaluacion, id_docente),
        )
        if not cur.fetchone():
            flash("No tienes permiso para eliminar esta evaluación.", "danger")
            return redirect(url_for("evaluaciones.gestion_evaluaciones"))

        # Borrar registros dependientes antes de eliminar la evaluación
        cur.execute("DELETE FROM evaluacion_respuestas WHERE id_evaluacion = %s", (id_evaluacion,))
        cur.execute("DELETE FROM evaluacion_resultados  WHERE id_evaluacion = %s", (id_evaluacion,))
        cur.execute("DELETE FROM evaluacion_grupos       WHERE id_evaluacion = %s", (id_evaluacion,))
        cur.execute("DELETE FROM evaluaciones            WHERE id_evaluacion = %s", (id_evaluacion,))

        conn.commit()
        flash("Evaluación eliminada.", "success")
    except Exception as e:
        conn.rollback()
        print("ERROR eliminar evaluacion:", e)
        flash("No se pudo eliminar la evaluación.", "danger")
    finally:
        cur.close()

    return redirect(url_for("evaluaciones.gestion_evaluaciones"))


@bp_evaluaciones.route("/<int:id_evaluacion>/resultados")
def resultados_evaluacion(id_evaluacion):
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    _migrate(conn)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT ev.titulo, ev.estado, s.nombre_salon,
               COALESCE(ev.num_grupos, 1) AS num_grupos
        FROM evaluaciones ev
        JOIN salones s ON s.id_salon = ev.id_salon
        JOIN docente_salones ds ON ds.id_salon = ev.id_salon
        WHERE ev.id_evaluacion = %s AND ds.id_docente = %s
        """,
        (id_evaluacion, id_docente),
    )
    ev = cur.fetchone()
    if not ev:
        flash("Evaluación no encontrada.", "danger")
        cur.close()
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    titulo, estado, nombre_salon, num_grupos = ev

    # Resultados con grupo asignado
    try:
        cur.execute(
            """
            SELECT
                er.id_estudiante,
                u.nombre || ' ' || u.apellidos AS nombre_completo,
                er.estado,
                er.total_correctas,
                er.total_preguntas,
                er.puntaje_total,
                er.fecha_fin,
                COALESCE(eg.grupo, '—') AS grupo
            FROM evaluacion_resultados er
            JOIN estudiante e ON e.id_estudiante = er.id_estudiante
            JOIN usuarios u ON u.id_usuario = e.id_usuario
            LEFT JOIN evaluacion_grupos eg
                ON eg.id_evaluacion = er.id_evaluacion
               AND eg.id_estudiante = er.id_estudiante
            WHERE er.id_evaluacion = %s
            ORDER BY er.puntaje_total DESC NULLS LAST, u.apellidos
            """,
            (id_evaluacion,),
        )
    except Exception:
        cur.execute(
            """
            SELECT
                er.id_estudiante,
                u.nombre || ' ' || u.apellidos AS nombre_completo,
                er.estado, er.total_correctas, er.total_preguntas,
                er.puntaje_total, er.fecha_fin, '—' AS grupo
            FROM evaluacion_resultados er
            JOIN estudiante e ON e.id_estudiante = er.id_estudiante
            JOIN usuarios u ON u.id_usuario = e.id_usuario
            WHERE er.id_evaluacion = %s
            ORDER BY er.puntaje_total DESC NULLS LAST, u.apellidos
            """,
            (id_evaluacion,),
        )

    resultados = [
        {
            "id_estudiante": r[0], "nombre": r[1], "estado": r[2],
            "correctas": r[3], "total": r[4], "puntaje": r[5],
            "fecha_fin": r[6], "grupo": r[7],
        }
        for r in cur.fetchall()
    ]

    # Duración: suma del tiempo_respuesta por alumno en modo evaluación
    student_ids = [r["id_estudiante"] for r in resultados]
    duraciones = {}
    if student_ids:
        cur.execute(
            """
            SELECT id_estudiante,
                   SUM(COALESCE(tiempo_respuesta, 0))::int AS total_seg
            FROM respuestas_estudiantes
            WHERE id_estudiante = ANY(%s) AND modo = 'evaluacion'
            GROUP BY id_estudiante
            """,
            (student_ids,),
        )
        for row in cur.fetchall():
            duraciones[row[0]] = row[1]
    for r in resultados:
        r["duracion"] = _format_duracion_seg(duraciones.get(r["id_estudiante"]))

    cur.close()

    return render_template(
        "docente_evaluaciones.html",
        titulo_pagina="Resultados de Evaluación",
        active_page="evaluaciones",
        evaluacion_detalle={
            "id_evaluacion": id_evaluacion,
            "titulo": titulo, "estado": estado,
            "salon": nombre_salon, "num_grupos": num_grupos,
        },
        resultados=resultados,
        salones=[], evaluaciones=[], activa_por_salon={},
    )


@bp_evaluaciones.route("/<int:id_evaluacion>/ejercicios")
def ejercicios_evaluacion(id_evaluacion):
    """Vista para que el docente vea los ejercicios asignados a cada grupo."""
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    _migrate(conn)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT ev.titulo, ev.estado, ev.ejercicios_grupos,
               COALESCE(ev.num_grupos, 1)    AS num_grupos,
               COALESCE(ev.num_preguntas, 10) AS num_preguntas,
               s.nombre_salon
        FROM evaluaciones ev
        JOIN salones s ON s.id_salon = ev.id_salon
        JOIN docente_salones ds ON ds.id_salon = ev.id_salon
        WHERE ev.id_evaluacion = %s AND ds.id_docente = %s
        """,
        (id_evaluacion, id_docente),
    )
    ev = cur.fetchone()
    if not ev:
        flash("Evaluación no encontrada.", "danger")
        cur.close()
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    titulo, estado, ejercicios_grupos_json, num_grupos, num_preguntas, nombre_salon = ev

    # Todos los ejercicios del catálogo
    cur.execute(
        """
        SELECT ej.id_ejercicio, ej.descripcion,
               COALESCE(c.area, 'Sin competencia') AS nombre_competencia,
               ej.imagen_url
        FROM ejercicios ej
        LEFT JOIN competencias c ON c.id_competencia = ej.id_competencia
        ORDER BY c.area NULLS LAST, ej.id_ejercicio
        """
    )
    catalogo = {r[0]: {"id": r[0], "descripcion": r[1], "competencia": r[2], "imagen_url": r[3]} for r in cur.fetchall()}
    cur.close()

    # Ejercicios por grupo (si ya fueron pre-asignados al activar)
    ejercicios_por_grupo = {}
    if ejercicios_grupos_json:
        try:
            grupos_ids = json.loads(ejercicios_grupos_json)
            for letra, ids in grupos_ids.items():
                ejercicios_por_grupo[letra] = [
                    catalogo.get(i, {"id": i, "descripcion": "—", "competencia": "—"})
                    for i in ids
                ]
        except Exception:
            pass

    # Si no hay asignación por grupo, mostramos num_preguntas ejercicios aleatorios
    pool = list(catalogo.values())
    random.shuffle(pool)
    muestra_aleatoria = pool[:num_preguntas]

    return render_template(
        "docente_evaluaciones.html",
        titulo_pagina="Ejercicios de Evaluación",
        active_page="evaluaciones",
        evaluacion_ejercicios={
            "titulo": titulo, "estado": estado, "salon": nombre_salon,
            "num_grupos": num_grupos, "num_preguntas": num_preguntas,
        },
        ejercicios_por_grupo=ejercicios_por_grupo,
        todos_ejercicios=muestra_aleatoria,
        salones=[], evaluaciones=[], activa_por_salon={},
    )


@bp_evaluaciones.route("/<int:id_evaluacion>/estudiante/<int:id_estudiante>")
def detalle_estudiante_evaluacion(id_evaluacion, id_estudiante):
    """Muestra por ejercicio cómo le fue a un estudiante en la evaluación."""
    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    _migrate(conn)
    cur = conn.cursor()

    # Datos de la evaluación
    cur.execute(
        """
        SELECT ev.titulo, ev.estado, s.nombre_salon,
               COALESCE(ev.num_grupos, 1) AS num_grupos
        FROM evaluaciones ev
        JOIN salones s ON s.id_salon = ev.id_salon
        JOIN docente_salones ds ON ds.id_salon = ev.id_salon
        WHERE ev.id_evaluacion = %s AND ds.id_docente = %s
        """,
        (id_evaluacion, id_docente),
    )
    ev = cur.fetchone()
    if not ev:
        flash("Evaluación no encontrada.", "danger")
        cur.close()
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))

    titulo_ev, estado_ev, nombre_salon, num_grupos = ev

    # Nombre del estudiante
    cur.execute(
        """
        SELECT u.nombre || ' ' || u.apellidos
        FROM estudiante e
        JOIN usuarios u ON u.id_usuario = e.id_usuario
        WHERE e.id_estudiante = %s
        """,
        (id_estudiante,),
    )
    row_est = cur.fetchone()
    nombre_estudiante = row_est[0] if row_est else "Estudiante"

    # Grupo del estudiante en esta evaluación
    cur.execute(
        "SELECT grupo FROM evaluacion_grupos WHERE id_evaluacion = %s AND id_estudiante = %s",
        (id_evaluacion, id_estudiante),
    )
    row_grupo = cur.fetchone()
    grupo_estudiante = row_grupo[0] if row_grupo else None

    # Resumen de evaluación_resultados
    cur.execute(
        """
        SELECT estado, total_correctas, total_preguntas, puntaje_total, fecha_fin
        FROM evaluacion_resultados
        WHERE id_evaluacion = %s AND id_estudiante = %s
        """,
        (id_evaluacion, id_estudiante),
    )
    row_res = cur.fetchone()
    resumen = None
    if row_res:
        resumen = {
            "estado": row_res[0],
            "correctas": row_res[1],
            "total": row_res[2],
            "puntaje": row_res[3],
            "fecha_fin": row_res[4],
        }

    # Respuestas por ejercicio — primero desde evaluacion_respuestas (flujo web)
    cur.execute(
        """
        SELECT
            ej.descripcion,
            oe.descripcion AS texto_opcion,
            er.es_correcta,
            er.fecha,
            (SELECT oe2.descripcion FROM opciones_ejercicio oe2
             WHERE oe2.id_ejercicio = ej.id_ejercicio AND oe2.es_correcta = TRUE
             LIMIT 1) AS respuesta_correcta,
            (SELECT rs.id_respuesta FROM respuestas_estudiantes rs
             WHERE rs.id_ejercicio = er.id_ejercicio
               AND rs.id_estudiante = er.id_estudiante
               AND rs.desarrollo_url IS NOT NULL
             ORDER BY rs.fecha DESC LIMIT 1) AS id_respuesta_dev
        FROM evaluacion_respuestas er
        JOIN ejercicios ej ON ej.id_ejercicio = er.id_ejercicio
        LEFT JOIN opciones_ejercicio oe ON oe.id_opcion = er.id_opcion
        WHERE er.id_evaluacion = %s AND er.id_estudiante = %s
        ORDER BY er.fecha ASC
        """,
        (id_evaluacion, id_estudiante),
    )
    rows_ev = cur.fetchall()

    # Fallback Android: respuestas_estudiantes con modo='evaluacion'
    if not rows_ev:
        cur.execute(
            """
            SELECT
                ej.descripcion,
                oe.descripcion AS texto_opcion,
                oe.es_correcta,
                r.fecha,
                (SELECT oe2.descripcion FROM opciones_ejercicio oe2
                 WHERE oe2.id_ejercicio = ej.id_ejercicio AND oe2.es_correcta = TRUE
                 LIMIT 1) AS respuesta_correcta,
                CASE WHEN r.desarrollo_url IS NOT NULL THEN r.id_respuesta ELSE NULL END
                    AS id_respuesta_dev
            FROM respuestas_estudiantes r
            JOIN ejercicios ej ON ej.id_ejercicio = r.id_ejercicio
            LEFT JOIN opciones_ejercicio oe ON oe.id_opcion = r.id_opcion
            WHERE r.id_estudiante = %s AND r.modo = 'evaluacion'
            ORDER BY r.fecha ASC
            """,
            (id_estudiante,),
        )
        rows_ev = cur.fetchall()

    respuestas = [
        {
            "ejercicio":          r[0] or "—",
            "opcion_elegida":     r[1] or "Sin respuesta",
            "es_correcta":        bool(r[2]),
            "fecha":              r[3],
            "respuesta_correcta": r[4] or "—",
            "id_respuesta_dev":   r[5],
        }
        for r in rows_ev
    ]
    cur.close()

    return render_template(
        "docente_evaluaciones.html",
        titulo_pagina="Detalle de Evaluación",
        active_page="evaluaciones",
        evaluacion_detalle_est={
            "id_evaluacion": id_evaluacion,
            "id_estudiante": id_estudiante,
            "titulo": titulo_ev,
            "estado": estado_ev,
            "salon": nombre_salon,
            "nombre_estudiante": nombre_estudiante,
            "grupo": grupo_estudiante,
            "resumen": resumen,
        },
        respuestas_est=respuestas,
        salones=[], evaluaciones=[], activa_por_salon={},
    )


@bp_evaluaciones.route("/<int:id_evaluacion>/estudiante/<int:id_estudiante>/desarrollos-pdf")
def desarrollos_evaluacion_pdf(id_evaluacion, id_estudiante):
    """PDF con los desarrollos (fotos de trabajo) del estudiante en esta evaluación."""
    from flask import send_file, current_app
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer, Image, HRFlowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    from datetime import datetime
    import os

    id_docente = _get_id_docente()
    if not id_docente:
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    # Datos de la evaluación y del estudiante
    cur.execute(
        """
        SELECT ev.titulo, s.nombre_salon
        FROM evaluaciones ev
        JOIN salones s ON s.id_salon = ev.id_salon
        JOIN docente_salones ds ON ds.id_salon = ev.id_salon
        WHERE ev.id_evaluacion = %s AND ds.id_docente = %s
        """,
        (id_evaluacion, id_docente),
    )
    ev = cur.fetchone()
    if not ev:
        flash("Evaluación no encontrada.", "danger")
        cur.close()
        return redirect(url_for("evaluaciones.gestion_evaluaciones"))
    titulo_ev, nombre_salon = ev

    cur.execute(
        "SELECT u.nombre || ' ' || u.apellidos FROM estudiante e JOIN usuarios u ON u.id_usuario = e.id_usuario WHERE e.id_estudiante = %s",
        (id_estudiante,),
    )
    row = cur.fetchone()
    nombre_est = row[0] if row else "Estudiante"

    # Respuestas con desarrollo: primero evaluacion_respuestas + join, luego fallback Android
    # Usamos subquery escalar para desarrollo_url para evitar filas duplicadas cuando
    # el estudiante tiene múltiples intentos en respuestas_estudiantes para el mismo ejercicio.
    cur.execute(
        """
        SELECT ej.descripcion, oe.es_correcta, er.fecha,
               (SELECT rs.desarrollo_url
                FROM respuestas_estudiantes rs
                WHERE rs.id_ejercicio = er.id_ejercicio
                  AND rs.id_estudiante = er.id_estudiante
                  AND rs.desarrollo_url IS NOT NULL
                ORDER BY rs.fecha DESC
                LIMIT 1) AS desarrollo_url
        FROM evaluacion_respuestas er
        JOIN ejercicios ej ON ej.id_ejercicio = er.id_ejercicio
        LEFT JOIN opciones_ejercicio oe ON oe.id_opcion = er.id_opcion
        WHERE er.id_evaluacion = %s AND er.id_estudiante = %s
          AND EXISTS (
              SELECT 1 FROM respuestas_estudiantes rs2
              WHERE rs2.id_ejercicio = er.id_ejercicio
                AND rs2.id_estudiante = er.id_estudiante
                AND rs2.desarrollo_url IS NOT NULL
          )
        ORDER BY er.fecha ASC
        """,
        (id_evaluacion, id_estudiante),
    )
    respuestas = cur.fetchall()

    if not respuestas:
        cur.execute(
            """
            SELECT ej.descripcion, oe.es_correcta, r.fecha, r.desarrollo_url
            FROM respuestas_estudiantes r
            JOIN ejercicios ej ON ej.id_ejercicio = r.id_ejercicio
            LEFT JOIN opciones_ejercicio oe ON oe.id_opcion = r.id_opcion
            WHERE r.id_estudiante = %s AND r.modo = 'evaluacion'
              AND r.desarrollo_url IS NOT NULL
            ORDER BY oe.es_correcta DESC NULLS LAST, r.fecha ASC
            """,
            (id_estudiante,),
        )
        respuestas = cur.fetchall()
    cur.close()

    # ---- Helpers PDF ----
    PAGE_W = A4[0] - 4 * cm
    AZUL   = colors.HexColor("#1A5276")
    VERDE  = colors.HexColor("#1E8449")
    ROJO   = colors.HexColor("#C0392B")
    CELDA  = colors.HexColor("#BDC3C7")
    VERDE_SUAVE = colors.HexColor("#D5F5E3")
    ROJO_SUAVE  = colors.HexColor("#FADBD8")

    def st(name, **kw):
        d = dict(fontName="Helvetica", fontSize=9, textColor=colors.black, leading=12)
        d.update(kw)
        return ParagraphStyle(name, **d)

    st_titulo = st("t",  fontSize=13, fontName="Helvetica-Bold", textColor=AZUL)
    st_subtit = st("s",  fontSize=10, fontName="Helvetica-Bold", textColor=AZUL)
    st_normal = st("n")
    st_pie    = st("p",  fontSize=7, textColor=colors.HexColor("#7F8C8D"), alignment=TA_CENTER)
    st_center = st("c",  alignment=TA_CENTER)

    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
    story = []

    logo_path = os.path.join(current_app.root_path, "static", "logo_colegio.png")

    texto_cab = Table(
        [
            [Paragraph("INSTITUCIÓN EDUCATIVA \"27 DE DICIEMBRE\"", st_titulo)],
            [Paragraph(f"Informe de Desarrollos — Evaluación: {titulo_ev}", st_subtit)],
            [Paragraph(f"Estudiante: {nombre_est}  ·  Salón: {nombre_salon}  ·  {fecha_hoy}", st_normal)],
        ],
        colWidths=[PAGE_W - (3.2 * cm if os.path.exists(logo_path) else 0)],
    )
    texto_cab.setStyle(TableStyle([
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("TOPPADDING",    (0,0),(-1,-1), 1),
        ("BOTTOMPADDING", (0,0),(-1,-1), 1),
    ]))
    if os.path.exists(logo_path):
        img_logo = Image(logo_path, width=2.8*cm, height=2.8*cm)
        cab = Table([[img_logo, texto_cab]], colWidths=[3.2*cm, PAGE_W-3.2*cm])
    else:
        cab = Table([[texto_cab]], colWidths=[PAGE_W])
    cab.setStyle(TableStyle([
        ("VALIGN",      (0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING", (0,0),(-1,-1), 0),
        ("RIGHTPADDING",(0,0),(-1,-1), 0),
        ("TOPPADDING",  (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    story.append(cab)
    story.append(HRFlowable(width=PAGE_W, thickness=2, color=ROJO, spaceAfter=10))

    from ws.reportes import _resolver_imagen

    def agregar_grupo(lista, es_correcto):
        if not lista:
            return
        titulo_sec = "✓  RESPUESTAS CORRECTAS" if es_correcto else "✗  RESPUESTAS INCORRECTAS"
        color_fondo = VERDE_SUAVE if es_correcto else ROJO_SUAVE
        color_texto = VERDE if es_correcto else ROJO
        sec_h = Table([[Paragraph(titulo_sec, ParagraphStyle(
            "sh", fontSize=11, fontName="Helvetica-Bold", textColor=color_texto, leading=14))]],
            colWidths=[PAGE_W])
        sec_h.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), color_fondo),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("BOX",           (0,0),(-1,-1), 0.5, CELDA),
        ]))
        story.append(sec_h)
        story.append(Spacer(1, 8))
        for desc, _, fecha_r, dev_url in lista:
            fecha_str = fecha_r.strftime("%d/%m/%Y %H:%M") if fecha_r else "—"
            info = Table(
                [[Paragraph(f"<b>{desc or '—'}</b>", st_normal),
                  Paragraph(fecha_str, ParagraphStyle("fd", fontSize=8, textColor=colors.HexColor("#555"), alignment=TA_CENTER))]],
                colWidths=[PAGE_W - 4*cm, 4*cm])
            info.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), color_fondo),
                ("BOX",           (0,0),(-1,-1), 0.5, CELDA),
                ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                ("LEFTPADDING",   (0,0),(-1,-1), 8),
                ("RIGHTPADDING",  (0,0),(-1,-1), 8),
                ("TOPPADDING",    (0,0),(-1,-1), 5),
                ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ]))
            story.append(info)
            dev_path = _resolver_imagen(current_app, dev_url) if dev_url else None
            if dev_path:
                try:
                    rl_img = Image(dev_path)
                    scale = min((PAGE_W) / rl_img.drawWidth, (12*cm) / rl_img.drawHeight)
                    rl_img.drawWidth *= scale
                    rl_img.drawHeight *= scale
                    wrapper = Table([[rl_img]], colWidths=[PAGE_W])
                    wrapper.setStyle(TableStyle([
                        ("ALIGN",(0,0),(-1,-1),"CENTER"),
                        ("LEFTPADDING",(0,0),(-1,-1),0),
                        ("RIGHTPADDING",(0,0),(-1,-1),0),
                        ("TOPPADDING",(0,0),(-1,-1),4),
                        ("BOTTOMPADDING",(0,0),(-1,-1),4),
                        ("BOX",(0,0),(-1,-1),0.3,CELDA),
                    ]))
                    story.append(wrapper)
                except Exception:
                    story.append(Paragraph("(imagen no disponible)", st_normal))
            else:
                story.append(Paragraph("Sin imagen de desarrollo.", st_normal))
            story.append(Spacer(1, 10))

    correctas   = [r for r in respuestas if r[1]]
    incorrectas = [r for r in respuestas if not r[1]]
    agregar_grupo(correctas,   True)
    if correctas and incorrectas:
        story.append(Spacer(1, 6))
    agregar_grupo(incorrectas, False)

    if not respuestas:
        story.append(Paragraph("Este estudiante no tiene desarrollos guardados para esta evaluación.", st_center))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width=PAGE_W, thickness=0.5, color=CELDA, spaceAfter=4))
    story.append(Paragraph(
        f"Informe de evaluación generado el {fecha_hoy} — Sistema Tutor Adaptativo · I.E. \"27 de Diciembre\"",
        st_pie,
    ))

    buf = BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        title=f"Desarrollos Evaluación - {nombre_est}",
    ).build(story)
    buf.seek(0)
    return send_file(
        buf, mimetype="application/pdf", as_attachment=True,
        download_name=f"desarrollos_eval_{nombre_est.replace(' ','_')}_{datetime.now().strftime('%Y%m%d')}.pdf",
    )

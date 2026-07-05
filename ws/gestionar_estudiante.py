import os
from flask import render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from db import get_db
from .docentes import bp_docentes  # usamos el mismo Blueprint

# Tabla score→nivel compartida con la API REST (fórmula unificada)
_BRACKETS = [(0,21,1),(22,35,2),(36,49,3),(50,64,4),(65,78,5),(79,92,6),(93,100,7)]

def _score_to_nivel(score):
    s = max(0.0, min(100.0, float(score or 0)))
    for lo, hi, nivel in _BRACKETS:
        if lo <= s <= hi:
            return nivel
    return 7


def _obtener_id_docente_desde_sesion():
    """
    Usa session['user_id'] para obtener id_docente.
    """
    if "user_id" not in session or session.get("user_rol") != "docente":
        return None

    id_usuario = session["user_id"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id_docente FROM docente WHERE id_usuario = %s",
        (id_usuario,),
    )
    row = cur.fetchone()
    cur.close()

    if not row:
        return None

    return row[0]


@bp_docentes.route("/estudiantes")
def gestion_estudiantes():
    id_docente = _obtener_id_docente_desde_sesion()
    if id_docente is None:
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    # ============================
    # Estudiantes de los salones
    # ============================
    cur.execute(
        """
        SELECT
            e.id_estudiante,
            u.id_usuario,
            u.nombre,
            u.apellidos,
            u.correo,
            e.grado,
            e.estado_estudiante,
            s.nombre_salon,

            -- Niveles diagnósticos iniciales MINEDU (0 a 100)
            COALESCE(e.cantidad, 0)                          AS comp_cantidad,
            COALESCE(e.regularidad_equivalencia_cambio, 0)   AS comp_regularidad,
            COALESCE(e.forma_movimiento_localizacion, 0)     AS comp_forma,
            COALESCE(e.gestion_datos_incertidumbre, 0)       AS comp_datos,

            -- Progreso general: (min(nivel,6)-1)*20 promediado en las 4 competencias
            COALESCE(
                (SELECT ROUND(AVG((LEAST(nec.nivel_actual, 6) - 1) * 20.0))::int
                 FROM nivel_estudiante_competencia nec
                 WHERE nec.id_estudiante = e.id_estudiante
                   AND nec.id_competencia BETWEEN 1 AND 4),
                0
            ) AS progreso_general,

            -- Sin diagnóstico: ninguna de las 4 notas fue asignada todavía
            (e.cantidad IS NULL
             AND e.regularidad_equivalencia_cambio IS NULL
             AND e.forma_movimiento_localizacion   IS NULL
             AND e.gestion_datos_incertidumbre     IS NULL) AS sin_diagnostico,

            -- Diagnóstico bloqueado: el alumno ya tiene respuestas registradas
            EXISTS(
                SELECT 1 FROM respuestas_estudiantes r
                WHERE r.id_estudiante = e.id_estudiante
            ) AS diag_bloqueado

        FROM docente_salones ds
        JOIN salones s             ON s.id_salon = ds.id_salon
        JOIN estudiante_salones es ON es.id_salon = s.id_salon
        JOIN estudiante e          ON e.id_estudiante = es.id_estudiante
        JOIN usuarios u            ON u.id_usuario = e.id_usuario
        WHERE ds.id_docente = %s AND e.estado_estudiante = 'activo'
        ORDER BY u.apellidos, u.nombre
        """,
        (id_docente,),
    )

    rows = cur.fetchall()

    estudiantes = [
        {
            "id_estudiante":    r[0],
            "id_usuario":       r[1],
            "nombre":           r[2],
            "apellidos":        r[3],
            "correo":           r[4],
            "grado":            r[5],
            "estado_estudiante":r[6],
            "nombre_salon":     r[7],
            "comp_cantidad":    r[8],
            "comp_regularidad": r[9],
            "comp_forma":       r[10],
            "comp_datos":       r[11],
            "progreso_general": r[12],
            "sin_diagnostico":  bool(r[13]),
            "diag_bloqueado":   bool(r[14]),
            "nombre_completo":  f"{r[3]}, {r[2]}",
        }
        for r in rows
    ]

    # ============================
    # Usuarios que ya son alumnos
    # ============================
    cur.execute(
        """
        SELECT
            u.id_usuario,
            u.nombre,
            u.apellidos,
            u.correo,
            COALESCE(e.grado, '') AS grado
        FROM usuarios u
        LEFT JOIN estudiante e ON e.id_usuario = u.id_usuario
        WHERE u.rol = 'estudiante'
        ORDER BY u.apellidos, u.nombre
        """
    )
    usuarios_rows = cur.fetchall()
    usuarios_estudiantes = [
        {
            "id_usuario": r[0],
            "nombre": r[1],
            "apellidos": r[2],
            "correo": r[3],
            "grado": r[4],
            "nombre_completo": f"{r[1]} {r[2]}",
        }
        for r in usuarios_rows
    ]

    # ============================
    # Salones del docente (para select Grado/Sección dinámico + distribución)
    # ============================
    cur.execute(
        """
        SELECT s.nombre_salon,
               COUNT(DISTINCT es.id_estudiante) FILTER (WHERE e.estado_estudiante = 'activo') AS total_activos
        FROM salones s
        JOIN docente_salones ds    ON ds.id_salon = s.id_salon
        LEFT JOIN estudiante_salones es ON es.id_salon = s.id_salon
        LEFT JOIN estudiante e     ON e.id_estudiante = es.id_estudiante
        WHERE ds.id_docente = %s
        GROUP BY s.nombre_salon
        ORDER BY s.nombre_salon
        """,
        (id_docente,),
    )
    salones_rows = cur.fetchall()
    salones_docente = [r[0] for r in salones_rows]
    distribucion_salones = [
        {"nombre": r[0], "total": r[1] or 0}
        for r in salones_rows
    ]

    # ============================
    # Estudiantes dados de baja (inactivos) — invisibles en la tabla principal
    # ============================
    cur.execute(
        """
        SELECT
            u.nombre,
            u.apellidos,
            u.correo,
            e.grado,
            s.nombre_salon
        FROM docente_salones ds
        JOIN salones s              ON s.id_salon      = ds.id_salon
        JOIN estudiante_salones es  ON es.id_salon     = s.id_salon
        JOIN estudiante e           ON e.id_estudiante = es.id_estudiante
        JOIN usuarios u             ON u.id_usuario    = e.id_usuario
        WHERE ds.id_docente = %s AND e.estado_estudiante = 'inactivo'
        ORDER BY u.apellidos, u.nombre
        LIMIT 15
        """,
        (id_docente,),
    )
    estudiantes_inactivos = [
        {
            "nombre_completo": f"{r[1]}, {r[0]}",
            "correo": r[2],
            "grado": r[3],
            "nombre_salon": r[4],
        }
        for r in cur.fetchall()
    ]

    cur.close()

    return render_template(
        "docente_gestion_estudiantes.html",
        titulo_pagina="Gestión de Estudiantes",
        active_page="estudiantes",
        estudiantes=estudiantes,
        usuarios_estudiantes=usuarios_estudiantes,
        salones_docente=salones_docente,
        distribucion_salones=distribucion_salones,
        estudiantes_inactivos=estudiantes_inactivos,
    )


@bp_docentes.route("/estudiantes/nuevo", methods=["POST"])
def crear_estudiante():
    id_docente = _obtener_id_docente_desde_sesion()
    if id_docente is None:
        return redirect(url_for("auth.login"))

    # Puede venir un usuario ya existente
    id_usuario_existente = request.form.get("id_usuario_existente", type=int)

    nombre = request.form.get("nombre", "").strip()
    apellidos = request.form.get("apellidos", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    grado = request.form.get("grado", "").strip()  # 3ro A, 3ro B, 3ro C
    contrasena = request.form.get("contrasena", "")
    contrasena_confirm = request.form.get("contrasena_confirm", "")

    conn = get_db()
    cur = conn.cursor()

    # M10: usar el salón que el docente eligió en el formulario — el select
    # "Grado / Sección" muestra los nombres de SUS salones, así que se busca
    # el id_salon cuyo nombre coincide. Antes se ignoraba la elección y el
    # alumno iba siempre al primer salón del docente (LIMIT 1).
    cur.execute(
        """
        SELECT s.id_salon
        FROM salones s
        JOIN docente_salones ds ON ds.id_salon = s.id_salon
        WHERE ds.id_docente = %s AND s.nombre_salon = %s
        LIMIT 1
        """,
        (id_docente, grado),
    )
    row_salon = cur.fetchone()
    if not row_salon:
        # Fallback (grado no coincide con ningún salón): primer salón del docente
        cur.execute(
            """
            SELECT id_salon
            FROM docente_salones
            WHERE id_docente = %s
            LIMIT 1
            """,
            (id_docente,),
        )
        row_salon = cur.fetchone()
    if not row_salon:
        flash(
            "No tienes salones asignados. No se puede crear el estudiante.",
            "error",
        )
        cur.close()
        return redirect(url_for("docentes.gestion_estudiantes"))

    id_salon = row_salon[0]

    # =========================================
    # OPCIÓN 1: usar usuario existente
    # =========================================
    if id_usuario_existente:
        # Verificar que exista y sea rol estudiante
        cur.execute(
            """
            SELECT id_usuario, nombre, apellidos, correo
            FROM usuarios
            WHERE id_usuario = %s AND rol = 'estudiante'
            """,
            (id_usuario_existente,),
        )
        u = cur.fetchone()
        if not u:
            flash("El usuario seleccionado no es válido.", "error")
            cur.close()
            return redirect(url_for("docentes.gestion_estudiantes"))

        # Ver si ya tiene registro en estudiante
        cur.execute(
            "SELECT id_estudiante FROM estudiante WHERE id_usuario = %s",
            (id_usuario_existente,),
        )
        row_est = cur.fetchone()
        if row_est:
            id_estudiante = row_est[0]
            # Reactivar si estaba de baja y actualizar grado
            cur.execute(
                "UPDATE estudiante SET grado = %s, estado_estudiante = 'activo' WHERE id_estudiante = %s",
                (grado, id_estudiante),
            )
        else:
            # Crear registro de estudiante
            cur.execute(
                """
                INSERT INTO estudiante (grado, id_usuario)
                VALUES (%s, %s)
                RETURNING id_estudiante
                """,
                (grado, id_usuario_existente),
            )
            id_estudiante = cur.fetchone()[0]

        # Asociar al salón si no está ya
        cur.execute(
            """
            SELECT 1
            FROM estudiante_salones
            WHERE id_estudiante = %s AND id_salon = %s
            """,
            (id_estudiante, id_salon),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO estudiante_salones (id_estudiante, id_salon)
                VALUES (%s, %s)
                """,
                (id_estudiante, id_salon),
            )

        conn.commit()
        cur.close()
        flash("Estudiante asociado correctamente a tu salón.", "success")
        return redirect(url_for("docentes.gestion_estudiantes"))

    # =========================================
    # OPCIÓN 2: crear usuario nuevo
    # =========================================
    if not nombre or not apellidos or not correo or not contrasena:
        flash("Todos los campos obligatorios deben estar completos.", "error")
        cur.close()
        return redirect(url_for("docentes.gestion_estudiantes"))

    if contrasena != contrasena_confirm:
        flash("Las contraseñas no coinciden.", "error")
        cur.close()
        return redirect(url_for("docentes.gestion_estudiantes"))

    # Validar que el correo no exista
    cur.execute("SELECT id_usuario FROM usuarios WHERE correo = %s", (correo,))
    if cur.fetchone():
        flash("El correo ya está registrado.", "error")
        cur.close()
        return redirect(url_for("docentes.gestion_estudiantes"))

    # Crear usuario
    hash_pwd = generate_password_hash(contrasena)
    cur.execute(
        """
        INSERT INTO usuarios (nombre, apellidos, correo, contrasena, rol)
        VALUES (%s, %s, %s, %s, 'estudiante')
        RETURNING id_usuario
        """,
        (nombre, apellidos, correo, hash_pwd),
    )
    id_usuario = cur.fetchone()[0]

    # Crear estudiante (sin niveles iniciales por ahora)
    cur.execute(
        """
        INSERT INTO estudiante (grado, id_usuario)
        VALUES (%s, %s)
        RETURNING id_estudiante
        """,
        (grado, id_usuario),
    )
    id_estudiante = cur.fetchone()[0]

    # Asociar a salón del docente
    cur.execute(
        """
        INSERT INTO estudiante_salones (id_estudiante, id_salon)
        VALUES (%s, %s)
        """,
        (id_estudiante, id_salon),
    )

    conn.commit()
    cur.close()

    flash("Estudiante creado correctamente.", "success")
    return redirect(url_for("docentes.gestion_estudiantes"))


@bp_docentes.route("/estudiantes/<int:id_estudiante>/editar", methods=["POST"])
def editar_estudiante(id_estudiante):
    id_docente = _obtener_id_docente_desde_sesion()
    if id_docente is None:
        return redirect(url_for("auth.login"))

    id_usuario = request.form.get("id_usuario", type=int)
    nombre = request.form.get("nombre", "").strip()
    apellidos = request.form.get("apellidos", "").strip()
    correo = request.form.get("correo", "").strip().lower()
    grado = request.form.get("grado", "").strip()
    estado_estudiante = request.form.get("estado_estudiante", "activo").strip().lower()
    contrasena = request.form.get("contrasena", "")
    contrasena_confirm = request.form.get("contrasena_confirm", "")

    # Niveles diagnósticos por competencia (0..100)
    def _parse_int(name):
        val = request.form.get(name, "").strip()
        if not val:
            return None
        try:
            n = int(val)
            return max(0, min(100, n))
        except ValueError:
            return None

    comp_cantidad = _parse_int("comp_cantidad")
    comp_regularidad = _parse_int("comp_regularidad")
    comp_forma = _parse_int("comp_forma")
    comp_datos = _parse_int("comp_datos")

    if not nombre or not apellidos or not correo:
        flash("Nombre, apellidos y correo son obligatorios.", "error")
        return redirect(url_for("docentes.gestion_estudiantes"))

    if contrasena or contrasena_confirm:
        if contrasena != contrasena_confirm:
            flash("Las contraseñas no coinciden.", "error")
            return redirect(url_for("docentes.gestion_estudiantes"))

    conn = get_db()
    cur = conn.cursor()

    # Verificar que el estudiante pertenece a un salón de ESTE docente
    cur.execute(
        """
        SELECT 1 FROM estudiante_salones es
        JOIN docente_salones ds ON ds.id_salon = es.id_salon
        WHERE es.id_estudiante = %s AND ds.id_docente = %s
        """,
        (id_estudiante, id_docente),
    )
    if not cur.fetchone():
        cur.close()
        flash("No tienes permiso para editar a este estudiante.", "danger")
        return redirect(url_for("docentes.gestion_estudiantes"))

    # Validar correo único
    cur.execute(
        "SELECT id_usuario FROM usuarios WHERE correo = %s AND id_usuario <> %s",
        (correo, id_usuario),
    )
    if cur.fetchone():
        flash("El correo ya está registrado por otro usuario.", "error")
        cur.close()
        return redirect(url_for("docentes.gestion_estudiantes"))

    # Actualizar usuario
    cur.execute(
        """
        UPDATE usuarios
        SET nombre = %s, apellidos = %s, correo = %s
        WHERE id_usuario = %s
        """,
        (nombre, apellidos, correo, id_usuario),
    )

    # ¿El alumno ya tiene actividad? → diagnóstico queda bloqueado
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM respuestas_estudiantes WHERE id_estudiante = %s) AS tiene",
        (id_estudiante,),
    )
    diag_bloqueado = bool((cur.fetchone() or (False,))[0])

    if diag_bloqueado:
        # Solo actualizar datos personales y grado/estado — NO el diagnóstico
        cur.execute(
            """
            UPDATE estudiante
            SET grado = %s, estado_estudiante = %s
            WHERE id_estudiante = %s
            """,
            (grado, estado_estudiante, id_estudiante),
        )
        if (comp_cantidad is not None or comp_regularidad is not None
                or comp_forma is not None or comp_datos is not None):
            flash(
                "Los datos personales fueron actualizados. "
                "Las notas de diagnóstico no se pueden modificar porque "
                "el alumno ya ha realizado actividades en la aplicación.",
                "warning",
            )
        else:
            flash("Estudiante actualizado correctamente.", "success")
    else:
        # Sin actividad → se puede actualizar el diagnóstico completo
        cur.execute(
            """
            UPDATE estudiante
            SET grado = %s,
                estado_estudiante              = %s,
                cantidad                       = COALESCE(%s, cantidad),
                regularidad_equivalencia_cambio= COALESCE(%s, regularidad_equivalencia_cambio),
                forma_movimiento_localizacion  = COALESCE(%s, forma_movimiento_localizacion),
                gestion_datos_incertidumbre    = COALESCE(%s, gestion_datos_incertidumbre)
            WHERE id_estudiante = %s
            """,
            (grado, estado_estudiante,
             comp_cantidad, comp_regularidad, comp_forma, comp_datos,
             id_estudiante),
        )

        # Sincronizar → NEC diagnóstico
        # NOTA: puntajes NO recibe el score del diagnóstico porque usa escala
        # continua 0-100 (docente), mientras que todo el historial de práctica
        # es binario 0/100.  El nivel inicial queda registrado en NEC, que es
        # la fuente autoritativa que lee leer_nec() en el módulo tutor.
        comp_map = [
            (1, comp_cantidad),
            (2, comp_regularidad),
            (3, comp_forma),
            (4, comp_datos),
        ]
        for id_comp, score in comp_map:
            # Si el docente no envió esta nota (campo vacío) NO tocar el NEC —
            # misma semántica que el COALESCE del UPDATE estudiante. Antes se
            # reseteaba a 0/nivel 1 al editar cualquier dato del alumno.
            if score is None:
                continue
            s = score
            nivel_actual = _score_to_nivel(s)
            cur.execute(
                """
                INSERT INTO nivel_estudiante_competencia
                    (id_estudiante, id_competencia, nivel_actual,
                     promedio_puntaje, ejercicios_considerados, fecha_ultimo_update)
                VALUES (%s, %s, %s, %s, 0, NOW())
                ON CONFLICT (id_estudiante, id_competencia) DO UPDATE SET
                    nivel_actual        = EXCLUDED.nivel_actual,
                    promedio_puntaje    = EXCLUDED.promedio_puntaje,
                    fecha_ultimo_update = EXCLUDED.fecha_ultimo_update
                """,
                (id_estudiante, id_comp, nivel_actual, float(s)),
            )
        flash("Estudiante actualizado correctamente.", "success")

    # Contraseña (siempre permitida)
    if contrasena:
        hash_pwd = generate_password_hash(contrasena)
        cur.execute(
            "UPDATE usuarios SET contrasena = %s WHERE id_usuario = %s",
            (hash_pwd, id_usuario),
        )

    conn.commit()
    cur.close()
    return redirect(url_for("docentes.gestion_estudiantes"))


@bp_docentes.route("/estudiantes/<int:id_estudiante>/baja", methods=["POST"])
def baja_estudiante(id_estudiante):
    id_docente = _obtener_id_docente_desde_sesion()
    if id_docente is None:
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    # Verificar que el estudiante pertenece a un salón de ESTE docente
    cur.execute(
        """
        SELECT 1 FROM estudiante_salones es
        JOIN docente_salones ds ON ds.id_salon = es.id_salon
        WHERE es.id_estudiante = %s AND ds.id_docente = %s
        """,
        (id_estudiante, id_docente),
    )
    if not cur.fetchone():
        cur.close()
        flash("No tienes permiso para dar de baja a este estudiante.", "danger")
        return redirect(url_for("docentes.gestion_estudiantes"))

    cur.execute(
        "UPDATE estudiante SET estado_estudiante = 'inactivo' WHERE id_estudiante = %s",
        (id_estudiante,),
    )
    conn.commit()
    cur.close()

    flash("Estudiante dado de baja.", "success")
    return redirect(url_for("docentes.gestion_estudiantes"))


@bp_docentes.route("/estudiantes/baja-seleccion", methods=["POST"])
def baja_seleccion_estudiantes():
    id_docente = _obtener_id_docente_desde_sesion()
    if id_docente is None:
        return redirect(url_for("auth.login"))

    baja_todos = request.form.get("baja_todos") == "1"
    ids_raw = request.form.getlist("ids[]")

    conn = get_db()
    cur = conn.cursor()

    try:
        if baja_todos:
            cur.execute(
                """
                SELECT DISTINCT e.id_estudiante
                FROM estudiante e
                JOIN estudiante_salones es ON es.id_estudiante = e.id_estudiante
                JOIN docente_salones ds    ON ds.id_salon      = es.id_salon
                WHERE ds.id_docente = %s AND e.estado_estudiante = 'activo'
                """,
                (id_docente,),
            )
            ids = [r[0] for r in cur.fetchall()]
        else:
            ids = [int(i) for i in ids_raw if str(i).strip().isdigit()]

        if not ids:
            flash("No se seleccionó ningún estudiante activo.", "warning")
            cur.close()
            return redirect(url_for("docentes.gestion_estudiantes"))

        cur.execute(
            "UPDATE estudiante SET estado_estudiante = 'inactivo' WHERE id_estudiante = ANY(%s)",
            (ids,),
        )
        conn.commit()

        n = len(ids)
        msg = (
            f"Se dieron de baja todos los estudiantes ({n})."
            if baja_todos
            else f"Se dieron de baja {n} estudiante(s)."
        )
        flash(msg, "success")
    except Exception as e:
        conn.rollback()
        print("ERROR baja selección estudiantes:", e)
        flash("Error al dar de baja los estudiantes.", "danger")
    finally:
        cur.close()

    return redirect(url_for("docentes.gestion_estudiantes"))


@bp_docentes.route("/estudiantes/<int:id_estudiante>/foto", methods=["POST"])
def subir_foto_estudiante(id_estudiante):
    id_docente = _obtener_id_docente_desde_sesion()
    if id_docente is None:
        return redirect(url_for("auth.login"))

    foto = request.files.get("foto_estudiante")
    if not foto or not foto.filename:
        flash("No se seleccionó ninguna imagen.", "warning")
        return redirect(url_for("docentes.gestion_estudiantes"))

    ext = os.path.splitext(secure_filename(foto.filename))[1].lower()
    if ext not in {".jpg", ".jpeg", ".png"}:
        flash("Solo se permiten imágenes JPG o PNG.", "danger")
        return redirect(url_for("docentes.gestion_estudiantes"))

    conn = get_db()
    cur = conn.cursor()

    # Verificar que el estudiante pertenece a un salón de ESTE docente
    cur.execute(
        """
        SELECT 1 FROM estudiante_salones es
        JOIN docente_salones ds ON ds.id_salon = es.id_salon
        WHERE es.id_estudiante = %s AND ds.id_docente = %s
        """,
        (id_estudiante, id_docente),
    )
    if not cur.fetchone():
        cur.close()
        flash("No tienes permiso para modificar a este estudiante.", "danger")
        return redirect(url_for("docentes.gestion_estudiantes"))

    cur.execute(
        "SELECT e.id_estudiante, u.id_usuario FROM estudiante e JOIN usuarios u ON u.id_usuario = e.id_usuario WHERE e.id_estudiante = %s",
        (id_estudiante,),
    )
    row = cur.fetchone()
    cur.close()

    if not row:
        flash("Estudiante no encontrado.", "danger")
        return redirect(url_for("docentes.gestion_estudiantes"))

    id_usuario = row[1]
    fotos_dir = os.path.join(current_app.root_path, "static", "fotos_perfil")
    os.makedirs(fotos_dir, exist_ok=True)
    ruta_destino = os.path.join(fotos_dir, f"user_{id_usuario}.jpg")

    try:
        from util_cloudinary import cloudinary_configurado, subir_imagen
        if cloudinary_configurado():
            public_id = f"tutormath/fotos_perfil/user_{id_usuario}"
            url_versionada = subir_imagen(foto, public_id)
            # URL con versión → el CDN/navegador no sirven la foto anterior
            conn = get_db()
            cur2 = conn.cursor()
            cur2.execute(
                "UPDATE usuarios SET foto_perfil = %s WHERE id_usuario = %s",
                (url_versionada, id_usuario),
            )
            conn.commit()
            cur2.close()
        else:
            foto.save(ruta_destino)
        flash("Foto del estudiante actualizada.", "success")
    except Exception as e:
        print("Error guardando foto estudiante:", e)
        flash("No se pudo guardar la imagen.", "danger")

    return redirect(url_for("docentes.gestion_estudiantes"))

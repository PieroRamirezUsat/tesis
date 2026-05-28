import os
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session,
)
from werkzeug.utils import secure_filename
from db import get_db

bp_ejercicios = Blueprint("ejercicios", __name__, url_prefix="/docente/ejercicios")

UPLOAD_FOLDER = "static/ejercicios_ayuda"
ALLOWED = {"png", "jpg", "jpeg"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED


def _migrate_nivel_logro(conn):
    """Agrega columnas nivel_logro y palabras_clave a ejercicios si no existen."""
    cur = conn.cursor()
    try:
        cur.execute(
            "ALTER TABLE ejercicios ADD COLUMN IF NOT EXISTS nivel_logro SMALLINT"
        )
        cur.execute(
            "ALTER TABLE ejercicios "
            "ADD COLUMN IF NOT EXISTS palabras_clave VARCHAR(200)"
        )
        cur.execute(
            "ALTER TABLE material_estudio "
            "ADD COLUMN IF NOT EXISTS id_ejercicio INTEGER "
            "REFERENCES ejercicios(id_ejercicio) ON DELETE SET NULL"
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()


# ===================== LISTADO =====================
@bp_ejercicios.route("/")
def gestion_ejercicios():
    # 🔒 Solo docentes
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    conn = get_db()
    _migrate_nivel_logro(conn)
    cur = conn.cursor()

    # Ejercicios con su competencia
    cur.execute(
        """
        SELECT
            e.id_ejercicio,       -- 0
            e.descripcion,        -- 1
            e.id_competencia,     -- 2
            c.descripcion AS nombre_competencia,  -- 3
            e.imagen_url,         -- 4
            e.nivel_logro,        -- 5
            e.palabras_clave      -- 6
        FROM ejercicios e
        JOIN competencias c ON c.id_competencia = e.id_competencia
        ORDER BY e.id_ejercicio DESC
        """
    )
    filas_ej = cur.fetchall()

    ejercicios = [
        {
            "id_ejercicio":      f[0],
            "descripcion":       f[1],
            "id_competencia":    f[2],
            "nombre_competencia":f[3],
            "imagen_url":        f[4],
            "nivel_logro":       f[5],
            "palabras_clave":    f[6],
        }
        for f in filas_ej
    ]

    # Lista de competencias para los combos
    cur.execute(
        """
        SELECT id_competencia, area
        FROM competencias
        ORDER BY id_competencia
        """
    )
    filas_comp = cur.fetchall()
    _AREA_LABELS = {
        "cantidad": "Resuelve problemas de cantidad",
        "regularidad_equivalencia_cambio": "Regularidad, equivalencia y cambio",
        "forma_movimiento_localizacion": "Forma, movimiento y localización",
        "gestion_datos_incertidumbre": "Gestión de datos e incertidumbre",
    }
    competencias = [
        {
            "id_competencia": f[0],
            "area": f[1],
            "nombre": _AREA_LABELS.get(f[1], f[1].replace("_", " ").title()),
        }
        for f in filas_comp
    ]

    cur.close()

    return render_template(
        "docente_gestion_ejercicios.html",
        ejercicios=ejercicios,
        competencias=competencias,
        titulo_pagina="Gestión de Ejercicios",
        active_page="ejercicios",
    )

# ===================== CREAR / ACTUALIZAR =====================
@bp_ejercicios.route("/crear", methods=["POST"])
def crear_ejercicio():
    """
    Si viene id_ejercicio vacío -> INSERT (nuevo ejercicio)
    Si viene id_ejercicio con valor -> UPDATE (editar ejercicio)
    """
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    id_ejercicio_raw = request.form.get("id_ejercicio", "").strip()
    descripcion    = request.form.get("descripcion", "").strip()
    id_competencia = request.form.get("id_competencia")
    pista          = request.form.get("pista", "").strip()
    palabras_clave = request.form.get("palabras_clave", "").strip() or None
    nivel_logro_raw = request.form.get("nivel_logro", "").strip()
    nivel_logro = int(nivel_logro_raw) if nivel_logro_raw.isdigit() and 1 <= int(nivel_logro_raw) <= 7 else None

    # Letra A/B/C/D marcada como correcta
    respuesta = request.form.get("opcion_correcta")

    archivo = request.files.get("imagen_ejercicio")  # nombre del input del HTML

    if not descripcion or not id_competencia:
        flash("Ingresa al menos la descripción y la competencia.", "danger")
        return redirect(url_for("ejercicios.gestion_ejercicios"))

    conn = get_db()
    cur = conn.cursor()

    es_update = bool(id_ejercicio_raw)
    id_ej = None

    try:
        # --------- Validar respuesta correcta ----------
        if not respuesta:
            # Si es edición, intentamos conservar la anterior
            if es_update:
                cur.execute(
                    "SELECT respuesta_correcta FROM ejercicios WHERE id_ejercicio = %s",
                    (int(id_ejercicio_raw),),
                )
                fila_resp = cur.fetchone()
                if fila_resp:
                    respuesta = fila_resp[0]

            # Si sigue sin haber respuesta, no continuamos
            if not respuesta:
                flash("Debes marcar cuál opción es la correcta (A, B, C o D).", "danger")
                conn.rollback()
                cur.close()
                return redirect(url_for("ejercicios.gestion_ejercicios"))

        # --------- INSERT o UPDATE de ejercicios ----------
        if es_update:
            id_ej = int(id_ejercicio_raw)
            cur.execute(
                """
                UPDATE ejercicios
                SET descripcion        = %s,
                    respuesta_correcta = %s,
                    id_competencia     = %s,
                    pista              = %s,
                    nivel_logro        = %s,
                    palabras_clave     = %s
                WHERE id_ejercicio = %s
                """,
                (descripcion, respuesta, id_competencia,
                 pista, nivel_logro, palabras_clave, id_ej),
            )
        else:
            cur.execute(
                """
                INSERT INTO ejercicios
                    (descripcion, respuesta_correcta, id_competencia,
                     pista, nivel_logro, palabras_clave)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id_ejercicio
                """,
                (descripcion, respuesta, id_competencia,
                 pista, nivel_logro, palabras_clave),
            )
            id_ej = cur.fetchone()[0]

        # ---------- Guardar imagen si viene ----------
        if archivo and allowed_file(archivo.filename):
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            filename = secure_filename(f"ej_{id_ej}.jpg")
            ruta = os.path.join(UPLOAD_FOLDER, filename)
            archivo.save(ruta)

            img_url = f"/static/ejercicios_ayuda/{filename}"
            cur.execute(
                "UPDATE ejercicios SET imagen_url = %s WHERE id_ejercicio = %s",
                (img_url, id_ej),
            )

        # ---------- GUARDAR / ACTUALIZAR OPCIONES A–D ----------
        opciones = {
            "A": request.form.get("opcion_A", "").strip(),
            "B": request.form.get("opcion_B", "").strip(),
            "C": request.form.get("opcion_C", "").strip(),
            "D": request.form.get("opcion_D", "").strip(),
        }

        # Traer qué letras ya existen para este ejercicio
        cur.execute(
            "SELECT letra FROM opciones_ejercicio WHERE id_ejercicio = %s",
            (id_ej,),
        )
        letras_existentes = {fila[0] for fila in cur.fetchall()}  # {'A','B',...}

        for letra, texto in opciones.items():
            es_corr = (letra == respuesta)

            if letra in letras_existentes:
                # Ya existe: solo actualizamos texto y es_correcta
                cur.execute(
                    """
                    UPDATE opciones_ejercicio
                    SET descripcion = %s,
                        es_correcta = %s
                    WHERE id_ejercicio = %s
                      AND letra = %s
                    """,
                    (texto, es_corr, id_ej, letra),
                )
            else:
                # No existe para este ejercicio: la insertamos si tiene texto
                if texto != "":
                    cur.execute(
                        """
                        INSERT INTO opciones_ejercicio (letra, descripcion, es_correcta, id_ejercicio)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (letra, texto, es_corr, id_ej),
                    )
                # Si no hay texto y no existía, no insertamos nada

        # ---------- COMMIT ----------
        conn.commit()

        if es_update:
            flash("Ejercicio actualizado correctamente.", "success")
        else:
            flash("Ejercicio creado correctamente.", "success")

    except Exception as e:
        conn.rollback()
        print("ERROR crear/actualizar ejercicio:", e)
        flash("Ocurrió un error al guardar el ejercicio.", "danger")
    finally:
        cur.close()

    return redirect(url_for("ejercicios.gestion_ejercicios"))


# ===================== ELIMINAR =====================
@bp_ejercicios.route("/eliminar/<int:id_ejercicio>", methods=["POST"])
def eliminar_ejercicio(id_ejercicio):
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    try:
        # Borrar opciones asociadas
        cur.execute(
            "DELETE FROM opciones_ejercicio WHERE id_ejercicio = %s",
            (id_ejercicio,),
        )

        # Borrar imagen si existe
        ruta = os.path.join(UPLOAD_FOLDER, f"ej_{id_ejercicio}.jpg")
        if os.path.exists(ruta):
            os.remove(ruta)

        # Borrar ejercicio
        cur.execute("DELETE FROM ejercicios WHERE id_ejercicio = %s", (id_ejercicio,))
        conn.commit()
        flash("Ejercicio eliminado.", "success")
    except Exception as e:
        conn.rollback()
        print("ERROR eliminar ejercicio:", e)
        flash("No se pudo eliminar el ejercicio.", "danger")
    finally:
        cur.close()

    return redirect(url_for("ejercicios.gestion_ejercicios"))

# ===================== ELIMINAR SELECCIÓN / TODOS =====================
@bp_ejercicios.route("/eliminar-seleccion", methods=["POST"])
def eliminar_seleccion():
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    eliminar_todos = request.form.get("eliminar_todos") == "1"
    ids_raw = request.form.getlist("ids[]")

    conn = get_db()
    cur = conn.cursor()

    try:
        if eliminar_todos:
            cur.execute("SELECT id_ejercicio FROM ejercicios")
            ids = [r[0] for r in cur.fetchall()]
        else:
            ids = [int(i) for i in ids_raw if str(i).strip().isdigit()]

        if not ids:
            flash("No se seleccionó ningún ejercicio.", "warning")
            cur.close()
            return redirect(url_for("ejercicios.gestion_ejercicios"))

        cur.execute(
            "DELETE FROM opciones_ejercicio WHERE id_ejercicio = ANY(%s)", (ids,)
        )
        for id_ej in ids:
            ruta = os.path.join(UPLOAD_FOLDER, f"ej_{id_ej}.jpg")
            if os.path.exists(ruta):
                os.remove(ruta)
        cur.execute("DELETE FROM ejercicios WHERE id_ejercicio = ANY(%s)", (ids,))
        conn.commit()

        n = len(ids)
        msg = f"Se eliminaron todos los ejercicios ({n})." if eliminar_todos else f"Se eliminaron {n} ejercicio(s)."
        flash(msg, "success")
    except Exception as e:
        conn.rollback()
        print("ERROR eliminar selección:", e)
        flash("Error al eliminar los ejercicios.", "danger")
    finally:
        cur.close()

    return redirect(url_for("ejercicios.gestion_ejercicios"))


# ===================== DETALLE JSON (para EDITAR) =====================
@bp_ejercicios.route("/detalle/<int:id_ejercicio>")
def detalle_ejercicio_json(id_ejercicio):
    if "user_id" not in session or session.get("user_rol") != "docente":
        return jsonify({"error": "No autorizado"}), 401

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            id_ejercicio,
            descripcion,
            id_competencia,
            respuesta_correcta,
            pista,
            nivel_logro,
            palabras_clave
        FROM ejercicios
        WHERE id_ejercicio = %s
        """,
        (id_ejercicio,),
    )
    ej = cur.fetchone()

    if not ej:
        cur.close()
        return jsonify({"error": "Ejercicio no encontrado"}), 404

    # Opciones A–D
    cur.execute(
        """
        SELECT letra, descripcion
        FROM opciones_ejercicio
        WHERE id_ejercicio = %s
        ORDER BY letra
        """,
        (id_ejercicio,),
    )
    filas_opt = cur.fetchall()
    cur.close()

    opciones = {fila[0]: fila[1] for fila in filas_opt}

    data = {
        "id_ejercicio":      ej[0],
        "descripcion":       ej[1],
        "id_competencia":    ej[2],
        "respuesta_correcta":ej[3],
        "pista":             ej[4],
        "nivel_logro":       ej[5],
        "palabras_clave":    ej[6],
        "opciones":          opciones,
    }

    return jsonify(data)

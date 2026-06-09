# ws/temas.py
import json
import re
from urllib.request import urlopen
from urllib.request import Request as URequest
from urllib.parse import urlparse

from flask import (
    Blueprint,
    jsonify,
    render_template,
    session,
    redirect,
    url_for,
    request,
    flash,
)
from db import get_db

bp_temas = Blueprint("temas", __name__, url_prefix="/docente/temas")

# IDs de las 4 competencias base del MINEDU (ajusta si tus IDs son otros)
BASE_COMPETENCIAS_IDS = {1, 2, 3, 4}


# ================= API: OBTENER INFO DE URL =================
@bp_temas.route("/api/url-info", methods=["GET"])
def api_url_info():
    """Detecta tipo y obtiene metadatos de una URL via oEmbed (YouTube / Vimeo)."""
    url = (request.args.get("url") or "").strip()

    if not url:
        return jsonify({"ok": False, "mensaje": "URL vacía."})

    try:
        parsed = urlparse(url)
    except Exception:
        return jsonify({"ok": False, "mensaje": "URL con formato inválido."})

    if parsed.scheme != "https":
        return jsonify({"ok": False, "mensaje": "Solo se aceptan URLs con HTTPS."})

    hostname = (parsed.hostname or "").lower()
    if not hostname or "." not in hostname:
        return jsonify({"ok": False, "mensaje": "Dominio inválido."})

    # Bloquear direcciones locales / privadas
    private = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if hostname in private or re.match(
        r"^(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+$", hostname
    ):
        return jsonify({"ok": False, "mensaje": "URL no permitida."})

    # Detectar tipo
    tipo = "link"
    oembed_url = None

    if hostname in ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"):
        tipo = "video"
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    elif hostname in ("vimeo.com", "www.vimeo.com"):
        tipo = "video"
        oembed_url = f"https://vimeo.com/api/oembed.json?url={url}"
    elif parsed.path.lower().endswith(".pdf"):
        tipo = "pdf"

    titulo = ""
    duracion_minutos = None

    if oembed_url:
        try:
            req = URequest(oembed_url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
            with urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            titulo = data.get("title", "")
            dur_seg = data.get("duration")  # Vimeo devuelve duración en segundos
            if dur_seg and isinstance(dur_seg, (int, float)):
                duracion_minutos = max(1, round(int(dur_seg) / 60))
        except Exception:
            pass  # El usuario completa el título manualmente

    return jsonify({"ok": True, "tipo": tipo, "titulo": titulo, "duracion_minutos": duracion_minutos})


# ================= LISTAR TEMAS Y MATERIALES =================
@bp_temas.route("/", methods=["GET"])
def gestion_temas():
    """
    Muestra la pantalla de Gestión de Temas.
    Opcionalmente puede filtrar por:
      - id_competencia -> tema seleccionado
      - nivel_filtro   -> nivel de materiales (1,2,3) o todos
    """

    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    # ---- filtro de tema ----
    id_comp_raw = request.args.get("id_competencia")
    filtro_comp = None
    if id_comp_raw:
        try:
            filtro_comp = int(id_comp_raw)
        except ValueError:
            filtro_comp = None

    # ---- filtro de nivel de materiales ----
    nivel_filtro_raw = request.args.get("nivel_filtro", "").strip()
    nivel_filtro = None
    if nivel_filtro_raw in ("1", "2", "3"):
        nivel_filtro = int(nivel_filtro_raw)

    # ---- lista de competencias ----
    cur.execute(
        """
        SELECT id_competencia, area, descripcion, nivel
        FROM competencias
        ORDER BY id_competencia
        """
    )
    rows = cur.fetchall()

    temas = [
        {
            "id_competencia": r[0],
            "area": r[1],
            "descripcion": r[2],
            "nivel": r[3],
        }
        for r in rows
    ]

    # ---- tema activo ----
    tema_activo = None
    if filtro_comp is not None:
        for t in temas:
            if t["id_competencia"] == filtro_comp:
                tema_activo = t
                break
    else:
        if temas:
            tema_activo = temas[0]

    # ---- materiales del tema activo ----
    materiales = []
    if tema_activo:
        sql = """
            SELECT id_material, titulo, tipo, url, tiempo_estimado, nivel
            FROM material_estudio
            WHERE id_competencia = %s
        """
        params = [tema_activo["id_competencia"]]

        # si hay nivel_filtro, filtramos por ese nivel
        if nivel_filtro in (1, 2, 3):
            sql += " AND nivel = %s"
            params.append(nivel_filtro)

        sql += " ORDER BY id_material"
        cur.execute(sql, params)

        mat_rows = cur.fetchall()
        materiales = [
            {
                "id_material": m[0],
                "titulo": m[1],
                "tipo": m[2],
                "url": m[3],
                "tiempo_estimado": m[4],
                "nivel": m[5],
            }
            for m in mat_rows
        ]

    cur.close()

    return render_template(
        "docente_gestion_temas.html",
        temas=temas,
        tema_activo=tema_activo,
        materiales=materiales,
        base_competencias_ids=BASE_COMPETENCIAS_IDS,
        nivel_filtro=nivel_filtro,
        titulo_pagina="Gestión de Temas de Álgebra",
        active_page="temas",
    )


# ================= CREAR NUEVO TEMA =================
@bp_temas.route("/nuevo", methods=["POST"])
def crear_tema():
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    titulo = (request.form.get("titulo_tema") or "").strip()
    descripcion = (request.form.get("descripcion_tema") or "").strip()

    if not titulo:
        flash("El título del tema es obligatorio.", "error")
        return redirect(url_for("temas.gestion_temas"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO competencias (descripcion, area, nivel)
        VALUES (%s, %s, %s)
        RETURNING id_competencia
        """,
        (descripcion, titulo, 1),   # nivel=1 (Fácil) por defecto; editable después
    )
    nuevo_id = cur.fetchone()[0]
    conn.commit()
    cur.close()

    flash("Tema creado correctamente.", "success")
    return redirect(url_for("temas.gestion_temas", id_competencia=nuevo_id))


# ================= ACTUALIZAR TEMA =================
@bp_temas.route("/<int:id_competencia>/actualizar", methods=["POST"])
def actualizar_tema(id_competencia):
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    titulo = (request.form.get("titulo_tema") or "").strip()
    descripcion = (request.form.get("descripcion_tema") or "").strip()

    if not titulo:
        flash("El título del tema es obligatorio.", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE competencias
        SET area = %s,
            descripcion = %s
        WHERE id_competencia = %s
        """,
        (titulo, descripcion, id_competencia),
    )
    conn.commit()
    cur.close()

    flash("Tema actualizado correctamente.", "success")
    return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))


# ================= ELIMINAR TEMA =================
@bp_temas.route("/<int:id_competencia>/eliminar", methods=["POST"])
def eliminar_tema(id_competencia):
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    if id_competencia in BASE_COMPETENCIAS_IDS:
        flash(
            "Este tema forma parte de las competencias base del MINEDU y no puede eliminarse.",
            "error",
        )
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM material_estudio WHERE id_competencia = %s",
        (id_competencia,),
    )
    tiene_materiales = cur.fetchone()[0] > 0

    if tiene_materiales:
        cur.close()
        flash(
            "No se puede eliminar un tema que tiene materiales asociados. "
            "Elimina los materiales primero.",
            "error",
        )
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    cur.execute(
        "DELETE FROM competencias WHERE id_competencia = %s",
        (id_competencia,),
    )
    conn.commit()
    cur.close()

    flash("Tema eliminado correctamente.", "success")
    return redirect(url_for("temas.gestion_temas"))


# ================= CREAR MATERIAL =================
@bp_temas.route("/<int:id_competencia>/material/nuevo", methods=["POST"])
def crear_material(id_competencia):
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    titulo = (request.form.get("titulo_material") or "").strip()
    tipo = (request.form.get("tipo") or "").strip().lower()
    url_mat = (request.form.get("url") or "").strip()
    tiempo_str = request.form.get("tiempo_estimado", "").strip()
    nivel_str = request.form.get("nivel_material", "").strip()

    try:
        tiempo = int(tiempo_str) if tiempo_str else 0
    except ValueError:
        tiempo = 0

    try:
        nivel_material = int(nivel_str) if nivel_str else None
    except ValueError:
        nivel_material = None

    if nivel_material not in (1, 2, 3, None):
        nivel_material = None

    if not titulo or not tipo or not url_mat:
        flash("Título, tipo y URL del material son obligatorios.", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    if not url_mat.startswith("https://"):
        flash("La URL debe comenzar con https://", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    if tipo not in ("video", "pdf", "link"):
        flash("Tipo de material inválido.", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    if nivel_material not in (1, 2, 3):
        flash("El nivel del material es obligatorio.", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO material_estudio (titulo, tipo, url, tiempo_estimado, nivel, id_competencia)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (titulo, tipo, url_mat, tiempo, nivel_material, id_competencia),
    )
    conn.commit()
    cur.close()

    flash("Material añadido correctamente.", "success")
    return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))


# ================= EDITAR MATERIAL =================
@bp_temas.route("/material/<int:id_material>/editar", methods=["POST"])
def editar_material(id_material):
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    titulo = (request.form.get("titulo_material") or "").strip()
    tipo = (request.form.get("tipo") or "").strip().lower()
    url_mat = (request.form.get("url") or "").strip()
    tiempo_str = request.form.get("tiempo_estimado", "").strip()
    nivel_str = request.form.get("nivel_material", "").strip()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT id_competencia FROM material_estudio WHERE id_material = %s",
        (id_material,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        flash("El material no existe.", "error")
        return redirect(url_for("temas.gestion_temas"))

    id_competencia = row[0]

    try:
        tiempo = int(tiempo_str) if tiempo_str else 0
    except ValueError:
        tiempo = 0

    try:
        nivel_material = int(nivel_str) if nivel_str else None
    except ValueError:
        nivel_material = None

    if nivel_material not in (1, 2, 3, None):
        nivel_material = None

    if not titulo or not tipo or not url_mat:
        cur.close()
        flash("Título, tipo y URL del material son obligatorios.", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    if not url_mat.startswith("https://"):
        cur.close()
        flash("La URL debe comenzar con https://", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    if tipo not in ("video", "pdf", "link"):
        cur.close()
        flash("Tipo de material inválido.", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    if nivel_material not in (1, 2, 3):
        cur.close()
        flash("El nivel del material es obligatorio.", "error")
        return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

    cur.execute(
        """
        UPDATE material_estudio
        SET titulo = %s,
            tipo = %s,
            url = %s,
            tiempo_estimado = %s,
            nivel = %s
        WHERE id_material = %s
        """,
        (titulo, tipo, url_mat, tiempo, nivel_material, id_material),
    )
    conn.commit()
    cur.close()

    flash("Material actualizado correctamente.", "success")
    return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))


# ================= ELIMINAR MATERIAL =================
@bp_temas.route("/material/<int:id_material>/eliminar", methods=["POST"])
def eliminar_material(id_material):
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT id_competencia FROM material_estudio WHERE id_material = %s",
        (id_material,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        flash("El material ya no existe.", "error")
        return redirect(url_for("temas.gestion_temas"))

    id_competencia = row[0]

    cur.execute(
        "DELETE FROM material_estudio WHERE id_material = %s",
        (id_material,),
    )
    conn.commit()
    cur.close()

    flash("Material eliminado correctamente.", "success")
    return redirect(url_for("temas.gestion_temas", id_competencia=id_competencia))

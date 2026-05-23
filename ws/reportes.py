# ws/reportes.py
from flask import (
    Blueprint, render_template, session, redirect,
    url_for, request, flash, send_file, current_app
)
from db import get_db
import os
from io import BytesIO
from datetime import datetime
from ws.utils import calcular_progreso, url_foto_usuario


def _resolver_imagen(app, desarrollo_url: str) -> str | None:
    """
    Devuelve la ruta absoluta de la imagen de desarrollo buscando en:
    1. static/desarrollos_alumno/ del proyecto web (por si se copia allí)
    2. La carpeta configurada en DESARROLLOS_ALUMNO_PATH (proyecto API externo)
    Retorna None si no se encuentra en ningún lugar.
    """
    if not desarrollo_url:
        return None

    # Extraer solo el nombre de archivo de la URL
    filename = os.path.basename(desarrollo_url.replace("\\", "/"))
    if not filename:
        return None

    lugares = [
        # Carpeta local del proyecto web
        os.path.join(app.root_path, "static", "desarrollos_alumno", filename),
        # Carpeta externa configurada (API_RESTFUL u otro proyecto)
        os.path.join(
            app.config.get("DESARROLLOS_ALUMNO_PATH", ""),
            filename
        ),
    ]

    for ruta in lugares:
        if ruta and os.path.isfile(ruta):
            return ruta

    return None

bp_reportes = Blueprint(
    "reportes",
    __name__,
    url_prefix="/docente/reportes"
)


@bp_reportes.route("/progreso", methods=["GET"])
def reporte_progreso():
    """
    Reporte de progreso del estudiante.
    - Filtros de salón y estudiante
    - Progreso general (ponderado, igual que /progreso/resumen)
    - Progreso por competencia (ponderado, igual que /progreso/por_competencia)
    - Historial de actividades
    - Datos para gráfico histórico tipo heatmap
    """
    # Solo docentes
    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    # 1) Salones asignados al docente
    cur.execute(
        """
        SELECT s.id_salon, s.nombre_salon
        FROM salones s
        JOIN docente_salones ds ON ds.id_salon = s.id_salon
        JOIN docente d         ON d.id_docente = ds.id_docente
        WHERE d.id_usuario = %s
        ORDER BY s.nombre_salon
        """,
        (session["user_id"],),
    )
    salones_rows = cur.fetchall()
    salones = [
        {"id_salon": r[0], "nombre": r[1]}
        for r in salones_rows
    ]

    if not salones:
        cur.close()
        return render_template(
            "docente_reporte_progreso.html",
            titulo_pagina="Reportes Detallados",
            active_page="reportes",
            salones=[],
            estudiantes=[],
            salon_seleccionado=None,
            estudiante_seleccionado=None,
            salon_actual=None,
            estudiante_actual=None,
            progreso_general=0,
            progreso_competencias={},
            historial=[],
            valores_heatmap=[0] * 28,
        )

    # 2) Salón seleccionado
    id_salon_sel = request.args.get("id_salon", type=int)
    if not id_salon_sel:
        id_salon_sel = salones[0]["id_salon"]

    # 3) Estudiantes del salón
    cur.execute(
        """
        SELECT e.id_estudiante,
               u.id_usuario,
               u.nombre || ' ' || u.apellidos AS nombre_completo
        FROM estudiante e
        JOIN usuarios u             ON u.id_usuario = e.id_usuario
        JOIN estudiante_salones es  ON es.id_estudiante = e.id_estudiante
        WHERE es.id_salon = %s AND e.estado_estudiante = 'activo'
        ORDER BY nombre_completo
        """,
        (id_salon_sel,),
    )
    est_rows = cur.fetchall()
    estudiantes = [
        {"id_estudiante": r[0], "id_usuario": r[1], "nombre": r[2]}
        for r in est_rows
    ]

    if not estudiantes:
        cur.close()
        return render_template(
            "docente_reporte_progreso.html",
            titulo_pagina="Reportes Detallados",
            active_page="reportes",
            salones=salones,
            estudiantes=[],
            salon_seleccionado=id_salon_sel,
            estudiante_seleccionado=None,
            salon_actual=None,
            estudiante_actual=None,
            progreso_general=0,
            progreso_competencias={},
            historial=[],
            valores_heatmap=[0] * 28,
        )

    # 4) Estudiante seleccionado – validamos que pertenezca al salón del docente
    id_est_sel = request.args.get("id_estudiante", type=int)
    ids_validos = {e["id_estudiante"] for e in estudiantes}
    if not id_est_sel or id_est_sel not in ids_validos:
        id_est_sel = estudiantes[0]["id_estudiante"]

    # Objetos "actuales" para la tarjeta de arriba
    salon_actual = next(
        (s for s in salones if s["id_salon"] == id_salon_sel),
        None
    )
    estudiante_actual = next(
        (e for e in estudiantes if e["id_estudiante"] == id_est_sel),
        None
    )

    # Foto de perfil del estudiante seleccionado
    id_usuario_est = estudiante_actual["id_usuario"] if estudiante_actual else 0
    foto_url_estudiante = url_foto_usuario(current_app.root_path, id_usuario_est)

    # ======================================================
    # 5+6) Progreso por competencia usando modelo adaptativo
    #      y fórmula: ((nivel-1)/6)*70 + (puntaje/100)*30
    # ======================================================
    cur.execute(
        """
        SELECT
            c.area,
            COALESCE(nec.nivel_actual, 1)::int     AS nivel_actual,
            COALESCE(nec.promedio_puntaje, 0)::float AS promedio_puntaje
        FROM competencias c
        LEFT JOIN nivel_estudiante_competencia nec
            ON nec.id_estudiante  = %s
           AND nec.id_competencia = c.id_competencia
        WHERE c.id_competencia BETWEEN 1 AND 4
        ORDER BY c.id_competencia
        """,
        (id_est_sel,),
    )

    progreso_competencias = {}
    for fila in cur.fetchall():
        area    = fila[0]
        nivel   = int(fila[1])
        puntaje = float(fila[2])
        progreso_competencias[area] = calcular_progreso(nivel, puntaje)

    progreso_general = (
        int(round(sum(progreso_competencias.values()) / len(progreso_competencias)))
        if progreso_competencias else 0
    )

    # ======================================================
    # 7a) Ejercicios deduplicados para la tabla de historial
    # ======================================================
    cur.execute(
        """
        SELECT
            e.descripcion,
            COUNT(r.id_respuesta)       AS intentos,
            BOOL_OR(opt.es_correcta)    AS alguna_correcta,
            MAX(r.fecha)                AS ultima_fecha,
            (SELECT r2.id_respuesta
             FROM respuestas_estudiantes r2
             WHERE r2.id_ejercicio = e.id_ejercicio
               AND r2.id_estudiante = %s
               AND r2.desarrollo_url IS NOT NULL
             ORDER BY r2.fecha DESC LIMIT 1) AS id_respuesta_dev
        FROM ejercicios e
        JOIN respuestas_estudiantes r
            ON r.id_ejercicio = e.id_ejercicio AND r.id_estudiante = %s
        LEFT JOIN opciones_ejercicio opt ON opt.id_opcion = r.id_opcion
        GROUP BY e.id_ejercicio, e.descripcion
        ORDER BY ultima_fecha DESC NULLS LAST
        LIMIT 15
        """,
        (id_est_sel, id_est_sel),
    )
    hist_ejercicios = []
    for r in cur.fetchall():
        intentos = r[1] or 1
        correcta = bool(r[2])
        # Puntaje baja con cada intento; mínimo 10%
        puntaje = max(10, round(100 / intentos)) if correcta else 0
        hist_ejercicios.append({
            "nombre":          r[0] or "—",
            "tipo":            "Ejercicio",
            "intentos":        intentos,
            "puntaje":         puntaje,
            "correcta":        correcta,
            "ultima_fecha":    r[3],
            "tiene_desarrollo": r[4] is not None,
            "id_respuesta":    r[4],
        })

    # ======================================================
    # 7b) Materiales recientes
    # ======================================================
    cur.execute(
        """
        SELECT m.titulo, m.tipo,
               h.estado = 'completado' AS completado,
               h.fecha_acceso
        FROM historial_material_estudio h
        JOIN material_estudio m ON m.id_material = h.id_material
        WHERE h.id_estudiante = %s
        ORDER BY h.fecha_acceso DESC
        LIMIT 5
        """,
        (id_est_sel,),
    )
    hist_materiales = [
        {
            "nombre":          r[0] or "—",
            "tipo":            r[1] or "Material",
            "intentos":        1,
            "puntaje":         100 if bool(r[2]) else None,
            "correcta":        bool(r[2]),
            "ultima_fecha":    r[3],
            "tiene_desarrollo": False,
            "id_respuesta":    None,
        }
        for r in cur.fetchall()
    ]

    # ======================================================
    # 7c) Datos para gráfico de líneas: % correcto agrupado por día
    # ======================================================
    cur.execute(
        """
        SELECT
            TO_CHAR(DATE_TRUNC('hour', r.fecha), 'DD/MM HH24h') AS hora_str,
            ROUND(
                COUNT(CASE WHEN opt.es_correcta THEN 1 END) * 100.0
                / NULLIF(COUNT(*), 0)
            )::int AS pct_correcto
        FROM respuestas_estudiantes r
        LEFT JOIN opciones_ejercicio opt ON opt.id_opcion = r.id_opcion
        WHERE r.id_estudiante = %s
        GROUP BY DATE_TRUNC('hour', r.fecha)
        ORDER BY DATE_TRUNC('hour', r.fecha) ASC
        LIMIT 60
        """,
        (id_est_sel,),
    )
    datos_chart = [
        {"fecha": r[0] or "", "puntaje": int(r[1] or 0)}
        for r in cur.fetchall()
    ]

    # Foco: ejercicios fallados en la competencia más débil (viene del dashboard)
    foco = request.args.get("foco", "").strip()
    ejercicios_foco = []
    _ETIQUETAS_AREA = {
        "cantidad":                        "Resuelve problemas de cantidad",
        "regularidad_equivalencia_cambio":  "Regularidad, equiv. y cambio",
        "forma_movimiento_localizacion":    "Forma, movimiento y localiz.",
        "gestion_datos_incertidumbre":      "Gestión de datos e incert.",
    }
    foco_etiqueta = _ETIQUETAS_AREA.get(foco, foco.replace("_", " ").title()) if foco else ""

    if foco:
        try:
            cur.execute(
                """
                SELECT
                    e.descripcion,
                    COUNT(r.id_respuesta)              AS intentos,
                    BOOL_OR(opt.es_correcta)           AS alguna_correcta,
                    MAX(r.fecha)                       AS ultima_fecha,
                    (SELECT r2.id_respuesta
                     FROM respuestas_estudiantes r2
                     WHERE r2.id_ejercicio  = e.id_ejercicio
                       AND r2.id_estudiante = %s
                       AND r2.desarrollo_url IS NOT NULL
                     ORDER BY r2.fecha DESC LIMIT 1)   AS id_respuesta_dev
                FROM ejercicios e
                JOIN respuestas_estudiantes r
                    ON r.id_ejercicio = e.id_ejercicio AND r.id_estudiante = %s
                LEFT JOIN opciones_ejercicio opt ON opt.id_opcion = r.id_opcion
                JOIN competencias c ON c.id_competencia = e.id_competencia
                WHERE c.area = %s
                GROUP BY e.id_ejercicio, e.descripcion
                ORDER BY BOOL_OR(opt.es_correcta) ASC NULLS FIRST,
                         COUNT(r.id_respuesta) DESC
                LIMIT 10
                """,
                (id_est_sel, id_est_sel, foco),
            )
            for row in cur.fetchall():
                intentos = row[1] or 1
                correcta = bool(row[2])
                puntaje  = max(10, round(100 / intentos)) if correcta else 0
                ejercicios_foco.append({
                    "nombre":           row[0] or "—",
                    "intentos":         intentos,
                    "correcta":         correcta,
                    "puntaje":          puntaje,
                    "ultima_fecha":     row[3],
                    "tiene_desarrollo": row[4] is not None,
                    "id_respuesta":     row[4],
                })
        except Exception:
            cur.execute("ROLLBACK")

    cur.close()

    from datetime import datetime as _dt
    historial = sorted(
        hist_ejercicios + hist_materiales,
        key=lambda x: x["ultima_fecha"] or _dt.min,
        reverse=True,
    )

    return render_template(
        "docente_reporte_progreso.html",
        titulo_pagina="Reportes Detallados",
        active_page="reportes",
        salones=salones,
        estudiantes=estudiantes,
        salon_seleccionado=id_salon_sel,
        estudiante_seleccionado=id_est_sel,
        salon_actual=salon_actual,
        estudiante_actual=estudiante_actual,
        foto_url_estudiante=foto_url_estudiante,
        progreso_general=progreso_general,
        progreso_competencias=progreso_competencias,
        historial=historial,
        datos_chart=datos_chart,
        foco=foco,
        foco_etiqueta=foco_etiqueta,
        ejercicios_foco=ejercicios_foco,
    )


@bp_reportes.route("/respuesta/<int:id_respuesta>/imagen")
def ver_imagen_respuesta(id_respuesta):
    """
    Abre el desarrollo del estudiante.
    Si la respuesta tiene 'desarrollo_url', redirigimos allí (archivo en /static).
    Si no, probamos con respuesta_imagen (legacy). Si nada, mensaje de error.
    """
    from flask import send_file, redirect
    import io

    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT desarrollo_url, respuesta_imagen
        FROM respuestas_estudiantes
        WHERE id_respuesta = %s
        """,
        (id_respuesta,),
    )
    row = cur.fetchone()
    cur.close()

    if not row:
        flash("No se encontró la respuesta.", "error")
        return redirect(url_for("reportes.reporte_progreso"))

    desarrollo_url, respuesta_imagen = row

    # 1) Nuevo flujo: busca el archivo en las carpetas conocidas (web o API externa)
    if desarrollo_url:
        ruta = _resolver_imagen(current_app, desarrollo_url)
        if ruta:
            return send_file(ruta, mimetype="image/jpeg")
        flash("Imagen de desarrollo no encontrada en el servidor.", "error")
        return redirect(url_for("reportes.reporte_progreso"))

    # 2) Flujo legacy: imagen almacenada como bytea en la BD
    if respuesta_imagen:
        return send_file(io.BytesIO(bytes(respuesta_imagen)), mimetype="image/png")

    flash("Esta respuesta no tiene desarrollo asociado.", "error")
    return redirect(url_for("reportes.reporte_progreso"))


@bp_reportes.route("/progreso/pdf")
def exportar_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer, Image, HRFlowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    conn = get_db()
    cur = conn.cursor()

    # --- mismos datos que reporte_progreso ---
    cur.execute(
        """
        SELECT s.id_salon, s.nombre_salon
        FROM salones s
        JOIN docente_salones ds ON ds.id_salon = s.id_salon
        JOIN docente d         ON d.id_docente = ds.id_docente
        WHERE d.id_usuario = %s
        ORDER BY s.nombre_salon
        """,
        (session["user_id"],),
    )
    salones = [{"id_salon": r[0], "nombre": r[1]} for r in cur.fetchall()]

    id_salon_sel = request.args.get("id_salon", type=int)
    if not id_salon_sel and salones:
        id_salon_sel = salones[0]["id_salon"]

    cur.execute(
        """
        SELECT e.id_estudiante,
               u.nombre || ' ' || u.apellidos AS nombre_completo
        FROM estudiante e
        JOIN usuarios u             ON u.id_usuario = e.id_usuario
        JOIN estudiante_salones es  ON es.id_estudiante = e.id_estudiante
        WHERE es.id_salon = %s AND e.estado_estudiante = 'activo'
        ORDER BY nombre_completo
        """,
        (id_salon_sel,),
    )
    estudiantes = [{"id_estudiante": r[0], "nombre": r[1]} for r in cur.fetchall()]

    ids_validos_pdf = {e["id_estudiante"] for e in estudiantes}
    id_est_sel = request.args.get("id_estudiante", type=int)
    if not id_est_sel or id_est_sel not in ids_validos_pdf:
        id_est_sel = estudiantes[0]["id_estudiante"] if estudiantes else None

    salon_actual = next((s for s in salones if s["id_salon"] == id_salon_sel), None)
    estudiante_actual = next((e for e in estudiantes if e["id_estudiante"] == id_est_sel), None)

    # Progreso por competencia con modelo adaptativo
    cur.execute(
        """
        SELECT
            c.area,
            COALESCE(nec.nivel_actual, 1)::int       AS nivel_actual,
            COALESCE(nec.promedio_puntaje, 0)::float  AS promedio_puntaje
        FROM competencias c
        LEFT JOIN nivel_estudiante_competencia nec
            ON nec.id_estudiante  = %s
           AND nec.id_competencia = c.id_competencia
        WHERE c.id_competencia BETWEEN 1 AND 4
        ORDER BY c.id_competencia
        """,
        (id_est_sel,),
    )
    ETIQUETAS = {
        "cantidad": "Resuelve problemas de cantidad",
        "regularidad_equivalencia_cambio": "Regularidad, equivalencia y cambio",
        "forma_movimiento_localizacion": "Forma, movimiento y localización",
        "gestion_datos_incertidumbre": "Gestión de datos e incertidumbre",
    }
    progreso_competencias = {}
    for fila in cur.fetchall():
        area    = fila[0]
        nivel   = int(fila[1])
        puntaje = float(fila[2])
        progreso_competencias[ETIQUETAS.get(area, area)] = calcular_progreso(nivel, puntaje)

    progreso_general = (
        int(round(sum(progreso_competencias.values()) / len(progreso_competencias)))
        if progreso_competencias else 0
    )

    # Ejercicios deduplicados: una fila por ejercicio único, con resumen de intentos
    cur.execute(
        """
        SELECT
            e.id_ejercicio,
            e.descripcion,
            COUNT(r.id_respuesta)                                     AS total_intentos,
            BOOL_OR(opt.es_correcta)                                  AS alguna_correcta,
            MAX(r.fecha)                                              AS ultima_fecha,
            (SELECT r2.desarrollo_url
             FROM respuestas_estudiantes r2
             WHERE r2.id_ejercicio = e.id_ejercicio
               AND r2.id_estudiante = %s
               AND r2.desarrollo_url IS NOT NULL
             ORDER BY r2.fecha DESC
             LIMIT 1)                                                 AS desarrollo_url
        FROM ejercicios e
        JOIN respuestas_estudiantes r
            ON r.id_ejercicio = e.id_ejercicio AND r.id_estudiante = %s
        LEFT JOIN opciones_ejercicio opt ON opt.id_opcion = r.id_opcion
        GROUP BY e.id_ejercicio, e.descripcion
        ORDER BY ultima_fecha DESC NULLS LAST
        LIMIT 10
        """,
        (id_est_sel, id_est_sel),
    )
    ejercicios_hist = [
        {
            "descripcion":   r[1] or "—",
            "intentos":      r[2] or 1,
            "correcta":      bool(r[3]),
            "fecha":         r[4],
            "desarrollo_url": r[5],
        }
        for r in cur.fetchall()
    ]
    cur.close()

    # ---- Ancho útil de página ----
    # A4 = 595.28 pts; márgenes 2cm cada lado → 595.28 - 4*cm ≈ 481.9 pts
    PAGE_W = A4[0] - 4 * cm

    # ---- Colores ----
    AZUL  = colors.HexColor("#1A5276")
    ROJO  = colors.HexColor("#C0392B")
    VERDE = colors.HexColor("#27AE60")
    GRIS  = colors.HexColor("#F2F3F4")
    CELDA = colors.HexColor("#BDC3C7")

    # ---- Estilos de texto ----
    def st(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=9,
                        textColor=colors.black, leading=12)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    st_colegio  = st("colegio",  fontSize=13, fontName="Helvetica-Bold", textColor=AZUL, leading=16)
    st_lugar    = st("lugar",    fontSize=9,  textColor=colors.HexColor("#555555"))
    st_titulo_r = st("tituloR",  fontSize=10, fontName="Helvetica-Bold", textColor=ROJO)
    st_lbl      = st("lbl",      fontName="Helvetica-Bold", textColor=AZUL)
    st_val      = st("val")
    st_sec      = st("sec",      fontSize=10, fontName="Helvetica-Bold",
                     textColor=colors.white, leading=13)
    st_ch       = st("ch",       fontSize=8,  fontName="Helvetica-Bold",
                     textColor=colors.white, alignment=TA_CENTER)
    st_cell     = st("cell",     fontSize=8,  leading=10)

    st_pie      = st("pie",      fontSize=7,  textColor=colors.HexColor("#7F8C8D"),
                     alignment=TA_CENTER)

    # ---- Helper: encabezado de sección ----
    def seccion(texto):
        t = Table([[Paragraph(texto, st_sec)]], colWidths=[PAGE_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), AZUL),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    # ---- Helper: barra de progreso ----
    def barra_progreso(pct, ancho):
        # llena + vacia == ancho siempre (sin overflow)
        llena = max(1, min(ancho - 1, round(pct / 100 * ancho)))
        vacia = ancho - llena
        color_b = VERDE if pct >= 70 else (colors.orange if pct >= 40 else ROJO)
        t = Table([["", ""]], colWidths=[llena, vacia], rowHeights=[12])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, 0), color_b),
            ("BACKGROUND",    (1, 0), (1, 0), colors.HexColor("#E8F4FD")),
            ("BOX",           (0, 0), (-1, -1), 0.5, CELDA),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    story = []
    nombre_est = estudiante_actual["nombre"] if estudiante_actual else "—"
    nombre_sal = salon_actual["nombre"]       if salon_actual       else "—"
    fecha_hoy  = datetime.now().strftime("%d/%m/%Y %H:%M")

    # ================================================================
    # CABECERA: logo + nombre del colegio
    # ================================================================
    logo_path = os.path.join(current_app.root_path, "static", "logo_colegio.png")
    LOGO_W = 3 * cm
    TEXT_W = PAGE_W - LOGO_W

    texto_header = Table(
        [
            [Paragraph("INSTITUCIÓN EDUCATIVA \"27 DE DICIEMBRE\"", st_colegio)],
            [Paragraph("Lambayeque — Perú",                         st_lugar)],
            [Paragraph("REPORTE DE PROGRESO DEL ESTUDIANTE",        st_titulo_r)],
        ],
        colWidths=[TEXT_W],
    )
    texto_header.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    if os.path.exists(logo_path):
        logo_img = Image(logo_path, width=LOGO_W - 0.2 * cm, height=LOGO_W - 0.2 * cm)
        cab_data = [[logo_img, texto_header]]
    else:
        cab_data = [[texto_header]]
        texto_header = Table(
            [
                [Paragraph("INSTITUCIÓN EDUCATIVA \"27 DE DICIEMBRE\"", st_colegio)],
                [Paragraph("Lambayeque — Perú",                         st_lugar)],
                [Paragraph("REPORTE DE PROGRESO DEL ESTUDIANTE",        st_titulo_r)],
            ],
            colWidths=[PAGE_W],
        )
        story.append(texto_header)
        story.append(HRFlowable(width=PAGE_W, thickness=2, color=ROJO, spaceAfter=8))
        cab_data = None

    if cab_data is not None:
        cab = Table(cab_data, colWidths=[LOGO_W, TEXT_W])
        cab.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(cab)
        story.append(HRFlowable(width=PAGE_W, thickness=2, color=ROJO, spaceAfter=8))

    # ================================================================
    # FICHA DEL ESTUDIANTE
    # ================================================================
    # Anchos: lbl1=3cm  val1=8cm  lbl2=2.5cm  val2=3.5cm  → 17cm
    C1, C2, C3, C4 = 3*cm, 8*cm, 2.5*cm, 3.5*cm
    info = Table(
        [
            [Paragraph("<b>Estudiante:</b>", st_lbl), Paragraph(nombre_est, st_val),
             Paragraph("<b>Fecha:</b>",      st_lbl), Paragraph(fecha_hoy,  st_val)],
            [Paragraph("<b>Salón:</b>",      st_lbl), Paragraph(nombre_sal, st_val),
             Paragraph("", st_val),                   Paragraph("",         st_val)],
        ],
        colWidths=[C1, C2, C3, C4],
    )
    info.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.8, CELDA),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, CELDA),
        ("BACKGROUND",    (0, 0), (0, -1),  GRIS),
        ("BACKGROUND",    (2, 0), (2, -1),  GRIS),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info)
    story.append(Spacer(1, 10))

    # ================================================================
    # PROGRESO GENERAL
    # ================================================================
    story.append(seccion("Progreso General"))
    story.append(Spacer(1, 6))

    color_pct_gral = VERDE if progreso_general >= 70 else (colors.orange if progreso_general >= 40 else ROJO)
    pg_table = Table(
        [[
            Paragraph(f"<b>{progreso_general}%</b>",
                      st("pg_num", fontSize=26, fontName="Helvetica-Bold",
                         textColor=color_pct_gral, alignment=TA_CENTER)),
            barra_progreso(progreso_general, PAGE_W - 3 * cm),
        ]],
        colWidths=[3 * cm, PAGE_W - 3 * cm],
        rowHeights=[30],
    )
    pg_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(pg_table)
    story.append(Spacer(1, 10))

    # ================================================================
    # PROGRESO POR COMPETENCIA
    # ================================================================
    story.append(seccion("Progreso por Competencia"))
    story.append(Spacer(1, 6))

    # Anchos: competencia=10cm  pct=2cm  barra=5cm  → 17cm
    CW_COMP = [10 * cm, 2 * cm, 5 * cm]
    BAR_COL = CW_COMP[2]

    comp_rows = [[
        Paragraph("<b>Competencia</b>",  st_ch),
        Paragraph("<b>%</b>",            st_ch),
        Paragraph("<b>Progreso</b>",     st_ch),
    ]]
    for etiqueta, pct in progreso_competencias.items():
        col_p = VERDE if pct >= 70 else (colors.orange if pct >= 40 else ROJO)
        comp_rows.append([
            Paragraph(etiqueta, st_cell),
            Paragraph(f"<b>{pct}%</b>",
                      st(f"cp{pct}", fontSize=9, fontName="Helvetica-Bold",
                         textColor=col_p, alignment=TA_CENTER)),
            barra_progreso(pct, BAR_COL),
        ])

    comp_table = Table(comp_rows, colWidths=CW_COMP)
    comp_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, GRIS]),
        ("BOX",           (0, 0), (-1, -1), 0.8, CELDA),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, CELDA),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        # Columna de barra (índice 2): sin padding horizontal para que no se desborde
        ("LEFTPADDING",   (2, 1), (2, -1),  0),
        ("RIGHTPADDING",  (2, 1), (2, -1),  0),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 10))

    # ================================================================
    # EJERCICIOS REALIZADOS (últimas 10 únicas, con desarrollo)
    # ================================================================
    story.append(seccion("Ejercicios Realizados (últimas 10, un resumen por ejercicio)"))
    story.append(Spacer(1, 6))

    # Anchos: ejercicio=9cm  intentos=2cm  puntaje=2.5cm  fecha=3.5cm → 17cm
    CW_EJ = [9 * cm, 2 * cm, 2.5 * cm, 3.5 * cm]

    ej_rows = [[
        Paragraph("<b>Ejercicio</b>",    st_ch),
        Paragraph("<b>Intentos</b>",     st_ch),
        Paragraph("<b>Puntaje</b>",      st_ch),
        Paragraph("<b>Última vez</b>",   st_ch),
    ]]
    # "data" para filas de ejercicio, "dev" para filas de imagen de desarrollo
    row_meta = []

    for idx, ej in enumerate(ejercicios_hist):
        intentos = ej["intentos"]
        # Puntaje disminuye con cada intento adicional
        puntaje = int(round(100 / intentos)) if ej["correcta"] else 0
        col_p = VERDE if puntaje >= 70 else (colors.orange if puntaje >= 40 else ROJO)
        fecha_str = ej["fecha"].strftime("%d/%m/%Y") if ej["fecha"] else "—"

        ej_rows.append([
            Paragraph(ej["descripcion"], st_cell),
            Paragraph(
                str(intentos),
                st(f"nt{idx}", fontSize=8, fontName="Helvetica-Bold",
                   alignment=TA_CENTER),
            ),
            Paragraph(
                f"<b>{puntaje}%</b>",
                st(f"ep{idx}", fontSize=9, fontName="Helvetica-Bold",
                   textColor=col_p, alignment=TA_CENTER),
            ),
            Paragraph(fecha_str, st_cell),
        ])
        row_meta.append("data")

        # Imagen del desarrollo si existe (busca en web y en API externa)
        dev_url = ej["desarrollo_url"]
        dev_path = _resolver_imagen(current_app, dev_url) if dev_url else None

        if dev_path:
            try:
                rl_img = Image(dev_path)
                max_w = PAGE_W - 0.5 * cm
                max_h = 8 * cm
                if rl_img.drawWidth > 0 and rl_img.drawHeight > 0:
                    scale = min(max_w / rl_img.drawWidth,
                                max_h / rl_img.drawHeight)
                    rl_img.drawWidth  *= scale
                    rl_img.drawHeight *= scale
                ej_rows.append([rl_img, "", "", ""])
                row_meta.append("dev")
            except Exception:
                pass

    if len(ej_rows) == 1:
        ej_rows.append([
            Paragraph("Sin ejercicios registrados", st_cell),
            Paragraph("", st_cell), Paragraph("", st_cell), Paragraph("", st_cell),
        ])
        row_meta.append("data")

    # Construir estilos dinámicamente para distinguir filas de datos y de desarrollo
    ej_style = [
        ("BACKGROUND",    (0, 0), (-1, 0),  AZUL),
        ("BOX",           (0, 0), (-1, -1), 0.8, CELDA),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, CELDA),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    data_count = 0
    for i, meta in enumerate(row_meta, start=1):
        if meta == "dev":
            ej_style += [
                ("SPAN",          (0, i), (-1, i)),
                ("ALIGN",         (0, i), (0, i), "CENTER"),
                ("VALIGN",        (0, i), (0, i), "MIDDLE"),
                ("BACKGROUND",    (0, i), (-1, i), colors.HexColor("#EBF5FB")),
                ("TOPPADDING",    (0, i), (-1, i), 6),
                ("BOTTOMPADDING", (0, i), (-1, i), 6),
            ]
        else:
            bg = colors.white if data_count % 2 == 0 else GRIS
            ej_style.append(("BACKGROUND", (0, i), (-1, i), bg))
            data_count += 1

    ej_table = Table(ej_rows, colWidths=CW_EJ)
    ej_table.setStyle(TableStyle(ej_style))
    story.append(ej_table)

    # ================================================================
    # PIE
    # ================================================================
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width=PAGE_W, thickness=0.5, color=CELDA, spaceAfter=4))
    story.append(Paragraph(
        f"Generado el {fecha_hoy} — Sistema Tutor Adaptativo · I.E. \"27 de Diciembre\" · Lambayeque",
        st_pie,
    ))

    # ================================================================
    # CONSTRUIR Y ENVIAR
    # ================================================================
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        title=f"Reporte - {nombre_est}",
    )
    doc.build(story)
    buf.seek(0)

    nombre_archivo = (
        f"reporte_{nombre_est.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    )
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nombre_archivo,
    )


@bp_reportes.route("/progreso/desarrollos-pdf")
def exportar_desarrollos_pdf():
    """
    PDF con todos los desarrollos (fotos de trabajo) del estudiante.
    Primero los correctos (resaltados), luego los incorrectos.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer, Image, HRFlowable, PageBreak
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    if "user_id" not in session or session.get("user_rol") != "docente":
        return redirect(url_for("auth.login"))

    id_salon_sel    = request.args.get("id_salon",      type=int)
    id_est_sel      = request.args.get("id_estudiante", type=int)

    if not id_est_sel:
        flash("Selecciona un estudiante primero.", "error")
        return redirect(url_for("reportes.reporte_progreso"))

    conn = get_db()
    cur  = conn.cursor()

    # Datos del estudiante y salón
    cur.execute(
        """
        SELECT u.nombre || ' ' || u.apellidos
        FROM estudiante est
        JOIN usuarios u ON u.id_usuario = est.id_usuario
        WHERE est.id_estudiante = %s
        """, (id_est_sel,)
    )
    row_est = cur.fetchone()
    nombre_est = row_est[0] if row_est else "Estudiante"

    cur.execute(
        """
        SELECT s.nombre_salon FROM salones s WHERE s.id_salon = %s
        """, (id_salon_sel,)
    ) if id_salon_sel else None
    row_sal = cur.fetchone() if id_salon_sel else None
    nombre_sal = row_sal[0] if row_sal else "—"

    # Respuestas con desarrollo_url, separadas en correctas e incorrectas
    cur.execute(
        """
        SELECT r.id_respuesta,
               e.descripcion,
               opt.es_correcta,
               r.fecha,
               r.desarrollo_url
        FROM respuestas_estudiantes r
        JOIN ejercicios e ON e.id_ejercicio = r.id_ejercicio
        LEFT JOIN opciones_ejercicio opt ON opt.id_opcion = r.id_opcion
        WHERE r.id_estudiante = %s
          AND r.desarrollo_url IS NOT NULL
        ORDER BY opt.es_correcta DESC NULLS LAST, r.fecha DESC
        """,
        (id_est_sel,),
    )
    respuestas = cur.fetchall()
    cur.close()

    correctas   = [r for r in respuestas if r[2]]
    incorrectas = [r for r in respuestas if not r[2]]

    # ---- Construir PDF ----
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

    st_titulo   = st("t",  fontSize=14, fontName="Helvetica-Bold", textColor=AZUL)
    st_subtit   = st("s",  fontSize=10, fontName="Helvetica-Bold", textColor=AZUL)
    st_normal   = st("n")
    st_pie      = st("p",  fontSize=7,  textColor=colors.HexColor("#7F8C8D"), alignment=TA_CENTER)
    st_ch_v     = st("chv",fontSize=9,  fontName="Helvetica-Bold", textColor=VERDE)
    st_ch_r     = st("chr",fontSize=9,  fontName="Helvetica-Bold", textColor=ROJO)
    st_center   = st("c",  alignment=TA_CENTER)

    fecha_hoy = datetime.now().strftime("%d/%m/%Y %H:%M")
    story = []

    # --- Cabecera ---
    logo_path = os.path.join(current_app.root_path, "static", "logo_colegio.png")

    def hacer_cabecera():
        texto = Table(
            [
                [Paragraph("INSTITUCIÓN EDUCATIVA \"27 DE DICIEMBRE\"", st_titulo)],
                [Paragraph(f"Informe de Desarrollos — {nombre_est} · {nombre_sal}", st_subtit)],
                [Paragraph(f"Generado: {fecha_hoy}", st_normal)],
            ],
            colWidths=[PAGE_W - (3.2 * cm if os.path.exists(logo_path) else 0)],
        )
        texto.setStyle(TableStyle([
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("TOPPADDING",    (0,0),(-1,-1), 1),
            ("BOTTOMPADDING", (0,0),(-1,-1), 1),
        ]))
        if os.path.exists(logo_path):
            img = Image(logo_path, width=2.8*cm, height=2.8*cm)
            cab = Table([[img, texto]], colWidths=[3.2*cm, PAGE_W - 3.2*cm])
        else:
            cab = Table([[texto]], colWidths=[PAGE_W])
        cab.setStyle(TableStyle([
            ("VALIGN",      (0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING", (0,0),(-1,-1), 0),
            ("RIGHTPADDING",(0,0),(-1,-1), 0),
            ("TOPPADDING",  (0,0),(-1,-1), 0),
            ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ]))
        return cab

    story.append(hacer_cabecera())
    story.append(HRFlowable(width=PAGE_W, thickness=2,
                            color=colors.HexColor("#C0392B"), spaceAfter=10))

    def agregar_grupo(lista, es_correcto):
        if not lista:
            return
        titulo = "✓  RESPUESTAS CORRECTAS" if es_correcto else "✗  RESPUESTAS INCORRECTAS"
        color_fondo = VERDE_SUAVE if es_correcto else ROJO_SUAVE
        color_texto = VERDE if es_correcto else ROJO
        etiq_style  = st_ch_v if es_correcto else st_ch_r

        sec_header = Table(
            [[Paragraph(titulo, ParagraphStyle(
                "sh", fontSize=11, fontName="Helvetica-Bold",
                textColor=color_texto, leading=14,
            ))]],
            colWidths=[PAGE_W],
        )
        sec_header.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), color_fondo),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("BOX",           (0,0),(-1,-1), 0.5, CELDA),
        ]))
        story.append(sec_header)
        story.append(Spacer(1, 8))

        for resp in lista:
            _, descripcion, _, fecha_resp, dev_url = resp
            fecha_str = fecha_resp.strftime("%d/%m/%Y %H:%M") if fecha_resp else "—"

            # Tarjeta de info del ejercicio
            info = Table(
                [[
                    Paragraph(f"<b>{descripcion or '—'}</b>", st_normal),
                    Paragraph(fecha_str, st(f"f{id(resp)}", fontSize=8,
                              textColor=colors.HexColor("#555555"), alignment=TA_CENTER)),
                ]],
                colWidths=[PAGE_W - 4*cm, 4*cm],
            )
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

            # Imagen del desarrollo (busca en web y en API externa)
            dev_path = _resolver_imagen(current_app, dev_url) if dev_url else None

            if dev_path:
                try:
                    rl_img = Image(dev_path)
                    max_w = PAGE_W
                    max_h = 12 * cm
                    if rl_img.drawWidth > 0 and rl_img.drawHeight > 0:
                        scale = min(max_w / rl_img.drawWidth,
                                    max_h / rl_img.drawHeight)
                        rl_img.drawWidth  *= scale
                        rl_img.drawHeight *= scale
                    img_wrapper = Table(
                        [[rl_img]],
                        colWidths=[PAGE_W],
                    )
                    img_wrapper.setStyle(TableStyle([
                        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
                        ("LEFTPADDING",   (0,0),(-1,-1), 0),
                        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
                        ("TOPPADDING",    (0,0),(-1,-1), 4),
                        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
                        ("BOX",           (0,0),(-1,-1), 0.3, CELDA),
                    ]))
                    story.append(img_wrapper)
                except Exception:
                    story.append(Paragraph("(imagen no disponible)", st_normal))
            else:
                story.append(Paragraph("Sin imagen de desarrollo guardada.", st_normal))

            story.append(Spacer(1, 10))

    agregar_grupo(correctas,   es_correcto=True)
    if correctas and incorrectas:
        story.append(Spacer(1, 6))
    agregar_grupo(incorrectas, es_correcto=False)

    if not correctas and not incorrectas:
        story.append(Paragraph(
            "Este estudiante aún no tiene desarrollos guardados.",
            st_center,
        ))

    story.append(Spacer(1, 12))
    story.append(HRFlowable(width=PAGE_W, thickness=0.5,
                            color=CELDA, spaceAfter=4))
    story.append(Paragraph(
        f"Informe de desarrollos generado el {fecha_hoy} — "
        f"Sistema Tutor Adaptativo · I.E. \"27 de Diciembre\"",
        st_pie,
    ))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        title=f"Desarrollos - {nombre_est}",
    )
    doc.build(story)
    buf.seek(0)

    nombre_archivo = (
        f"desarrollos_{nombre_est.replace(' ', '_')}"
        f"_{datetime.now().strftime('%Y%m%d')}.pdf"
    )
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nombre_archivo,
    )

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from db import get_db
from config import Config
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import limiter
import secrets
import smtplib
import ssl
from email.message import EmailMessage

bp_auth = Blueprint("auth", __name__)


# ============== POLÍTICA DE PRIVACIDAD ==============
@bp_auth.route("/privacidad")
def privacidad():
    """Página pública: qué datos se guardan y cómo pedir su eliminación."""
    return render_template("privacidad.html")


# ============== LOGIN ==============
@bp_auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])   # ← máx. 5 intentos/min por IP
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip()
        contrasena = request.form.get("contrasena", "").strip()

        errores = {}
        if not correo:
            errores["correo"] = "El correo es obligatorio."
        if not contrasena:
            errores["contrasena"] = "La contraseña es obligatoria."

        if errores:
            return render_template("login.html", errores=errores, correo=correo)

        db = get_db()
        cur = db.cursor()

        try:
            cur.execute("""
                SELECT 
                    u.id_usuario,      -- 0
                    u.nombre,          -- 1
                    u.apellidos,       -- 2
                    u.correo,          -- 3
                    u.rol,             -- 4
                    COALESCE(d.id_docente, NULL) AS id_docente,  -- 5
                    u.contrasena       -- 6
                FROM usuarios u
                LEFT JOIN docente d ON d.id_usuario = u.id_usuario
                WHERE u.correo = %s
                  AND u.estado_usuario = 'activo'
            """, (correo,))
            row = cur.fetchone()

            # No hay usuario o la contraseña no coincide con el hash
            if (not row) or (not row[6]) or (not check_password_hash(row[6], contrasena)):
                errores["general"] = "Correo o contraseña incorrectos."
                return render_template("login.html", errores=errores, correo=correo)

            # Autenticación correcta: crear sesión
            session.clear()
            session["user_id"] = row[0]
            session["user_name"] = f"{row[1]} {row[2]}"
            session["user_rol"] = row[4]
            session["user_correo"] = row[3]
            session["user_foto"] = None  # por ahora no hay columna foto_perfil

            # Redirigir según rol (por ahora ambos al dashboard de docente)
            if row[4] == "docente":
                return redirect(url_for("docentes.dashboard"))
            else:
                return redirect(url_for("docentes.dashboard"))

        except Exception as e:
            print("ERROR LOGIN WEB:", e)
            errores["general"] = "Ocurrió un error en el servidor."
            return render_template("login.html", errores=errores, correo=correo)
        finally:
            cur.close()
    else:
        return render_template("login.html")

# ============== LOGOUT ==============
@bp_auth.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "success")
    return redirect(url_for("auth.login"))

# ============== REGISTRO DOCENTE ==============
@bp_auth.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])    # ← máx. 10 registros/hora por IP
def register():
    if request.method == "POST":
        nombre           = request.form.get("nombre", "").strip()
        apellidos        = request.form.get("apellidos", "").strip()
        correo           = request.form.get("correo", "").strip()
        contrasena       = request.form.get("contrasena", "")
        confirmar        = request.form.get("confirmar_contrasena", "")
        codigo_registro  = request.form.get("codigo_registro", "").strip()
        rol = "docente"

        errores = []

        # ── Validación del código de institución ──────────────────
        # Solo docentes con el código correcto pueden registrarse.
        # Esto impide que alumnos u otros usuarios creen cuentas web.
        if not codigo_registro:
            errores.append("Debes ingresar el código de institución.")
        elif codigo_registro != Config.CODIGO_REGISTRO_DOCENTE:
            errores.append("El código de institución no es válido.")

        if not nombre:
            errores.append("Debes ingresar el nombre.")
        if not apellidos:
            errores.append("Debes ingresar los apellidos.")
        if not correo:
            errores.append("Debes ingresar el correo.")
        if not contrasena:
            errores.append("Debes ingresar una contraseña.")
        if contrasena and len(contrasena) < 6:
            errores.append("La contraseña debe tener al menos 6 caracteres.")
        if contrasena != confirmar:
            errores.append("Las contraseñas no coinciden.")

        conn = get_db()
        cur = conn.cursor()

        # ¿Correo ya existe?
        cur.execute("SELECT 1 FROM usuarios WHERE correo = %s", (correo,))
        if cur.fetchone():
            errores.append("El correo ya está registrado.")

        if errores:
            for e in errores:
                flash(e, "danger")
            cur.close()
            # 👇 aquí SI mandamos form_data para que el template rellene los campos
            return render_template("register.html", form_data=request.form)

        # 🔐 Encriptar contraseña
        hash_contra = generate_password_hash(contrasena)

        # Insertar usuario
        cur.execute(
            """
            INSERT INTO usuarios (nombre, apellidos, correo, contrasena, rol)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id_usuario
            """,
            (nombre, apellidos, correo, hash_contra, rol),
        )
        id_usuario = cur.fetchone()[0]

        # Insertar registro en docente
        cur.execute(
            "INSERT INTO docente (especialidad, id_usuario) VALUES (%s, %s)",
            ("Álgebra", id_usuario),
        )
        conn.commit()
        cur.close()

        flash("Usuario registrado correctamente. Ahora puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    # GET  👇 AQUI ESTABA EL PROBLEMA
    # Siempre mandamos form_data vacío para que el template no falle
    return render_template("register.html", form_data={})



# ============== OLVIDÉ MI CONTRASEÑA ==============
@bp_auth.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3 per 10 minutes", methods=["POST"])  # ← máx. 3 correos/10 min por IP
def forgot_password():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip()
        if not correo:
            flash("Debes ingresar un correo.", "danger")
            return render_template("forgot_password.html")

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id_usuario, nombre, apellidos, correo
            FROM usuarios
            WHERE correo = %s
              AND estado_usuario = 'activo'
            """,
            (correo,),
        )
        user = cur.fetchone()

        if not user:
            cur.close()
            flash("No se encontró un usuario con ese correo.", "danger")
            return render_template("forgot_password.html")

        id_usuario, nombre, apellidos, correo_db = user

        # Generar nueva contraseña temporal (texto plano solo para el correo)
        nueva_contra_plana = secrets.token_urlsafe(8)

        # 🔐 Construir el correo ANTES de tocar la BD.
        #    Si el envío falla, la contraseña del usuario NO cambia.
        msg = EmailMessage()
        msg["Subject"] = "Recuperación de contraseña - TutorMath"
        msg["From"] = Config.MAIL_DEFAULT_SENDER
        msg["To"] = correo_db

        msg.set_content(
            f"""
Hola {nombre} {apellidos},

Se ha generado una nueva contraseña temporal para tu cuenta en TutorMath:

    {nueva_contra_plana}

Te recomendamos iniciar sesión y cambiarla lo antes posible en tu perfil.

Saludos,
Sistema Tutor Adaptativo de Álgebra
"""
        )

        # Intentar enviar primero; solo si el correo sale bien actualizamos la BD
        if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
            cur.close()
            flash(
                "El sistema de correo no está configurado. Contacta al administrador.",
                "danger",
            )
            return render_template("forgot_password.html")

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL(
                Config.MAIL_SERVER, Config.MAIL_PORT, context=context
            ) as server:
                server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
                server.send_message(msg)
        except Exception as e:
            print("Error enviando correo de recuperación:", e)
            cur.close()
            flash(
                "No se pudo enviar el correo de recuperación. "
                "Verifica tu dirección o intenta más tarde.",
                "danger",
            )
            return render_template("forgot_password.html")

        # El correo salió OK → ahora sí actualizamos la contraseña
        hash_contra = generate_password_hash(nueva_contra_plana)
        cur.execute(
            "UPDATE usuarios SET contrasena = %s WHERE id_usuario = %s",
            (hash_contra, id_usuario),
        )
        conn.commit()
        cur.close()

        flash(
            "Se ha enviado una nueva contraseña a tu correo electrónico.",
            "success",
        )
        return redirect(url_for("auth.login"))

    # GET
    return render_template("forgot_password.html")

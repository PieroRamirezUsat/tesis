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

        # login.html solo sabe mostrar flash messages (no un dict "errores"
        # aparte) — antes esto se guardaba en "errores" y el template lo
        # ignoraba por completo: un correo/contraseña malo no mostraba NADA,
        # solo se quedaba en la misma pantalla sin explicación.
        if not correo:
            flash("El correo es obligatorio.", "danger")
            return render_template("login.html", correo=correo)
        if not contrasena:
            flash("La contraseña es obligatoria.", "danger")
            return render_template("login.html", correo=correo)

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
                flash("Correo o contraseña incorrectos.", "danger")
                return render_template("login.html", correo=correo)

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
            flash("Ocurrió un error en el servidor. Intenta de nuevo.", "danger")
            return render_template("login.html", correo=correo)
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
        cur.close()

        # Enlace de un solo uso, firmado y con expiración — no se toca la BD
        # hasta que el docente realmente elija su nueva contraseña en el link.
        token = _serializador_reset().dumps(id_usuario)
        enlace = url_for("auth.reset_password", token=token, _external=True)

        msg = EmailMessage()
        msg["Subject"] = "Recuperación de contraseña - TutorMath"
        msg["From"] = Config.MAIL_DEFAULT_SENDER
        msg["To"] = correo_db

        msg.set_content(
            f"""
Hola {nombre} {apellidos},

Recibimos una solicitud para restablecer tu contraseña en TutorMath. Abre este enlace para elegir una nueva (válido por {RESET_TOKEN_MAX_AGE // 60} minutos):

    {enlace}

Si no fuiste tú quien lo pidió, puedes ignorar este correo: tu contraseña actual sigue funcionando.

Saludos,
Sistema Tutor Adaptativo de Álgebra
"""
        )

        if not Config.MAIL_USERNAME or not Config.MAIL_PASSWORD:
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
            flash(
                "No se pudo enviar el correo de recuperación. "
                "Verifica tu dirección o intenta más tarde.",
                "danger",
            )
            return render_template("forgot_password.html")

        flash(
            "Te enviamos un enlace para restablecer tu contraseña. Revisa tu correo.",
            "success",
        )
        return redirect(url_for("auth.login"))

    # GET
    return render_template("forgot_password.html")


# ============== RESTABLECER CONTRASEÑA (enlace del correo) ==============
RESET_TOKEN_MAX_AGE = 30 * 60  # 30 minutos


def _serializador_reset():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(Config.SECRET_KEY, salt="reset-password")


@bp_auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    from itsdangerous import BadSignature, SignatureExpired

    try:
        id_usuario = _serializador_reset().loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except SignatureExpired:
        flash("El enlace ya expiró. Solicita uno nuevo.", "danger")
        return redirect(url_for("auth.forgot_password"))
    except BadSignature:
        flash("El enlace no es válido.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        nueva = request.form.get("nueva_contrasena", "")
        confirmar = request.form.get("confirmar_contrasena", "")

        if len(nueva) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return render_template("reset_password.html", token=token)
        if nueva != confirmar:
            flash("Las contraseñas no coinciden.", "danger")
            return render_template("reset_password.html", token=token)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE usuarios SET contrasena = %s WHERE id_usuario = %s AND estado_usuario = 'activo'",
            (generate_password_hash(nueva), id_usuario),
        )
        actualizado = cur.rowcount
        conn.commit()
        cur.close()

        if not actualizado:
            flash("No se pudo actualizar la contraseña. Intenta de nuevo.", "danger")
            return redirect(url_for("auth.forgot_password"))

        flash("Contraseña actualizada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)

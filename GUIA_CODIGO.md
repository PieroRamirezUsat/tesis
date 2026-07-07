# 📚 Guía de código — Portal Web del Docente (TutorMath)

> Guía de estudio para entender, defender y modificar este proyecto.
> Los archivos clave también tienen un bloque "GUÍA DE ESTUDIO" al inicio.

## Qué es este proyecto

Portal Flask para el **docente**: dashboard con métricas del aula, gestión de
estudiantes (incluido el **diagnóstico MINEDU**), salones, catálogo de temas y
materiales, banco de ejercicios, reportes PDF/CSV y evaluaciones. Además sirve
la **landing pública** con el botón de descarga del APK.

Autenticación por **sesión de Flask** (cookies + CSRF), distinta del JWT de la
API móvil. Comparte la base Postgres y el Cloudinary con la API.

```
Navegador docente ── sesión+CSRF ──► este portal ──► Postgres (Railway)
                                          │
                                          └──► Cloudinary (fotos, imágenes de ejercicios)
```

## Mapa de archivos

| Ruta | Qué contiene | Cuándo tocarlo |
|---|---|---|
| `app.py` | Factory `create_app()`: CSRF, limiter, blueprints, landing | Configuración global |
| `db.py` | Conexión por request (psycopg v3 → filas como **tuplas**) | Casi nunca |
| `config.py` | Variables: DATABASE_URL, CODIGO_REGISTRO_DOCENTE, APK_DOWNLOAD_URL… | Nuevas variables |
| `ws/auth.py` | Login/registro (código de institución), recuperar contraseña | Seguridad |
| `ws/docentes.py` | ⭐ Dashboard (1 consulta SQL por tarjeta) + perfil | Métricas nuevas |
| `ws/gestionar_estudiante.py` | ⭐ Alta de alumnos + **diagnóstico MINEDU → NEC** | El puente con el tutor |
| `ws/salones.py` | CRUD de salones y matrículas | |
| `ws/temas.py` | Catálogo de materiales por competencia/nivel | |
| `ws/ejercicios.py` | Banco de ejercicios + subida de imagen a Cloudinary | |
| `ws/reportes.py` | Reportes detallados + PDF (reportlab) | |
| `ws/evaluaciones.py` | Exámenes: crear, activar, resultados | |
| `ws/utils.py` | `url_foto_usuario` (Cloudinary→local→avatar), score→progreso | |
| `util_cloudinary.py` | Subida a Cloudinary (overwrite+invalidate, URL versionada) | |
| `templates/docente_base.html` | ⭐ Layout maestro: sidebar, tema oscuro, responsive, CSRF | Todo el look & feel |
| `templates/*.html` | Una vista por sección (heredan de la base) | |
| `scripts_seed/` | Scripts idempotentes del aula 3° E (¡no subir a repos públicos!) | Repetir seed |
| `tests/` | Suite pytest (145 tests) con la BD mockeada | Antes de cambios grandes |

## Flujos que debes poder explicar

1. **Login**: `ws/auth.py` compara el hash (nunca hay contraseñas en claro),
   guarda `user_id`/`user_rol` en la sesión; cada vista del panel valida
   `session.get('user_rol') == 'docente'`.
2. **Diagnóstico MINEDU** (`ws/gestionar_estudiante.py::editar_estudiante`):
   nota 0-100 por competencia → nivel 1-7 (misma tabla de brackets que la API)
   → se escribe en `nivel_estudiante_competencia`. La app parte de ahí.
   Si el alumno ya practicó, el diagnóstico se bloquea (no pisa su progreso).
3. **Dashboard**: `_metricas_dashboard()` en `ws/docentes.py` — el progreso de
   un alumno = promedio de sus 4 competencias con `(min(nivel,6)−1)×20`.
4. **Imágenes**: siempre Cloudinary en producción; se guarda la URL **con
   versión** (`/v123.../`) para que el CDN/navegador no sirvan la vieja.

## Producción (Railway)

- `Procfile` → `gunicorn app:app`; Root Directory vacío.
- Variables: `DATABASE_URL`, `SECRET_KEY`, `CODIGO_REGISTRO_DOCENTE`,
  `API_BASE_URL`, `APK_DOWNLOAD_URL`, `CLOUDINARY_URL`, `MAIL_*`.
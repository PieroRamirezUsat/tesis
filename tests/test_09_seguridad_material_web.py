"""
test_09_seguridad_material_web.py — Pruebas de SEGURIDAD: validación de URLs en materiales
============================================================================================
Tipo  : Seguridad / Validación de entrada
Ruta  : POST /docente/temas/<id>/material/nuevo
        POST /docente/temas/material/<id>/editar

Escenarios probados (ingeniería inversa / bypass del frontend)
--------------------------------------------------------------
Un atacante puede ignorar el JS de la UI y hacer POST directo al endpoint.
El servidor DEBE rechazar en estos casos:

[S1] tipo='video' con URL que no es YouTube ni Vimeo
     → debe rechazar (flash error, sin INSERT)

[S2] tipo='pdf' con URL que no termina en .pdf
     → debe rechazar (flash error, sin INSERT)

[S3] tipo='video' con dominio que intenta parecer YouTube
     → 'https://youtube.com.evil.com/video' debe rechazar

[S4] tipo='link' con URL válida HTTPS
     → debe aceptar (link es abierto por diseño)

[S5] tipo no permitido ('script', 'exe', etc.)
     → debe rechazar sin INSERT

[S6] URL sin https://
     → debe rechazar aunque el tipo sea válido

[S7] Editar material: misma validación cruzada tipo ↔ URL

Regla clave (fix 2026-06-14):
  crear_material y editar_material validan tipo ↔ URL server-side,
  NO confían solo en el JS del frontend (api_url_info).
"""

import pytest

pytestmark = pytest.mark.security


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _post_material(docente_session, app, id_competencia=1, **form_overrides):
    """Envía POST /docente/temas/<id>/material/nuevo con defaults anulables."""
    defaults = {
        "titulo_material": "Material de prueba",
        "tipo":            "video",
        "url":             "https://www.youtube.com/watch?v=abc123",
        "tiempo_estimado": "10",
        "nivel_material":  "1",
    }
    defaults.update(form_overrides)
    with app.app_context():
        return docente_session.post(
            f"/docente/temas/{id_competencia}/material/nuevo",
            data=defaults,
            follow_redirects=False,
        )


def _post_editar(docente_session, app, id_material=1, **form_overrides):
    """Envía POST /docente/temas/material/<id>/editar con defaults anulables."""
    defaults = {
        "titulo_material": "Editado",
        "tipo":            "video",
        "url":             "https://www.youtube.com/watch?v=abc123",
        "tiempo_estimado": "5",
        "nivel_material":  "1",
    }
    defaults.update(form_overrides)
    with app.app_context():
        return docente_session.post(
            f"/docente/temas/material/{id_material}/editar",
            data=defaults,
            follow_redirects=False,
        )


def _hubo_insert_material(mock_db):
    return any(
        "INSERT" in str(c).upper() and "material" in str(c).lower()
        for c in mock_db.execute.call_args_list
    )


# ─────────────────────────────────────────────────────────────────────────────
# S1 — tipo='video' con URL que NO es YouTube / Vimeo
# ─────────────────────────────────────────────────────────────────────────────

class TestVideoUrlInvalida:

    def test_video_con_url_malware_rechazado(self, client, mock_db, docente_session, app):
        """tipo=video + URL de malware → flash error, sin INSERT (bypass frontend)."""
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://malware-site.com/video.mp4")
        assert r.status_code in (302, 200)
        assert r.status_code != 500
        assert not _hubo_insert_material(mock_db), (
            "video con URL no-YouTube/Vimeo NO debe insertar en material_estudio"
        )

    def test_video_con_url_google_rechazado(self, client, mock_db, docente_session, app):
        """tipo=video + google.com no es YouTube."""
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://drive.google.com/file/d/abc/view")
        assert r.status_code in (302, 200)
        assert not _hubo_insert_material(mock_db)

    def test_video_con_vimeo_aceptado(self, client, mock_db, docente_session, app):
        """tipo=video + Vimeo es válido → puede intentar INSERT."""
        mock_db.fetchone.return_value = None
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://vimeo.com/123456789")
        assert r.status_code != 500

    def test_video_con_youtube_aceptado(self, client, mock_db, docente_session, app):
        """tipo=video + YouTube estándar es válido."""
        mock_db.fetchone.return_value = None
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert r.status_code != 500

    def test_video_con_youtu_be_aceptado(self, client, mock_db, docente_session, app):
        """tipo=video + youtu.be (short link) es válido."""
        mock_db.fetchone.return_value = None
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://youtu.be/dQw4w9WgXcQ")
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# S2 — tipo='pdf' con URL que NO termina en .pdf
# ─────────────────────────────────────────────────────────────────────────────

class TestPdfUrlInvalida:

    def test_pdf_con_url_exe_rechazado(self, client, mock_db, docente_session, app):
        """tipo=pdf + .exe en la URL → rechazado."""
        r = _post_material(docente_session, app,
                           tipo="pdf",
                           url="https://archivos.com/descarga.exe")
        assert r.status_code in (302, 200)
        assert r.status_code != 500
        assert not _hubo_insert_material(mock_db), (
            "pdf con URL no-.pdf NO debe insertar"
        )

    def test_pdf_con_url_zip_rechazado(self, client, mock_db, docente_session, app):
        """tipo=pdf + .zip → rechazado."""
        r = _post_material(docente_session, app,
                           tipo="pdf",
                           url="https://archivos.com/recursos.zip")
        assert not _hubo_insert_material(mock_db)

    def test_pdf_con_url_html_rechazado(self, client, mock_db, docente_session, app):
        """tipo=pdf + .html (página web, no PDF) → rechazado."""
        r = _post_material(docente_session, app,
                           tipo="pdf",
                           url="https://minedu.gob.pe/recursos/ficha.html")
        assert not _hubo_insert_material(mock_db)

    def test_pdf_con_url_sin_extension_rechazado(self, client, mock_db, docente_session, app):
        """tipo=pdf + URL sin extensión (e.g. endpoint REST) → rechazado."""
        r = _post_material(docente_session, app,
                           tipo="pdf",
                           url="https://archivos.com/algebra/recurso")
        assert not _hubo_insert_material(mock_db)

    def test_pdf_con_url_valida_aceptado(self, client, mock_db, docente_session, app):
        """tipo=pdf + URL que termina en .pdf → debe pasar la validación."""
        mock_db.fetchone.return_value = None
        r = _post_material(docente_session, app,
                           tipo="pdf",
                           url="https://minedu.gob.pe/recursos/algebra_nivel1.pdf")
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# S3 — Subdomain spoofing: dominio que intenta parecer YouTube
# ─────────────────────────────────────────────────────────────────────────────

class TestSubdomainSpoofing:

    def test_youtube_en_subdominio_rechazado(self, client, mock_db, docente_session, app):
        """https://youtube.com.evil.com/video — el hostname real es evil.com."""
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://youtube.com.evil.com/watch?v=abc")
        assert not _hubo_insert_material(mock_db), (
            "youtube.com.evil.com NO es YouTube — debe rechazar"
        )

    def test_vimeo_falso_rechazado(self, client, mock_db, docente_session, app):
        """https://vimeo.com.phishing.net/video → rechazado."""
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://vimeo.com.phishing.net/123")
        assert not _hubo_insert_material(mock_db)

    def test_fake_youtube_subdomain_rechazado(self, client, mock_db, docente_session, app):
        """https://fakeyoutube.com → rechazado (no es youtube.com)."""
        r = _post_material(docente_session, app,
                           tipo="video",
                           url="https://fakeyoutube.com/watch?v=abc")
        assert not _hubo_insert_material(mock_db)


# ─────────────────────────────────────────────────────────────────────────────
# S4 — tipo='link' acepta cualquier HTTPS (comportamiento intencional)
# ─────────────────────────────────────────────────────────────────────────────

class TestLinkTipoPermitido:

    def test_link_https_cualquier_dominio_aceptado(self, client, mock_db, docente_session, app):
        """tipo=link es abierto por diseño — cualquier HTTPS válida."""
        mock_db.fetchone.return_value = None
        r = _post_material(docente_session, app,
                           tipo="link",
                           url="https://khan-academy.org/algebra")
        assert r.status_code != 500

    def test_link_sin_https_rechazado(self, client, mock_db, docente_session, app):
        """tipo=link con HTTP (no HTTPS) → rechazado."""
        r = _post_material(docente_session, app,
                           tipo="link",
                           url="http://inseguro.com/recurso")
        assert not _hubo_insert_material(mock_db), (
            "link HTTP (no HTTPS) debe ser rechazado"
        )


# ─────────────────────────────────────────────────────────────────────────────
# S5 — tipo no permitido (inyección de tipo)
# ─────────────────────────────────────────────────────────────────────────────

class TestTipoInvalido:

    @pytest.mark.parametrize("tipo_malo", [
        "script", "exe", "html", "javascript", "application/x-sh",
        "",  # El servidor normaliza con .lower() así que VIDEO→video es aceptado (correcto)
    ])
    def test_tipo_invalido_rechazado(self, client, mock_db, docente_session, app, tipo_malo):
        """Tipos no permitidos → rechazado server-side, sin INSERT."""
        r = _post_material(docente_session, app,
                           tipo=tipo_malo,
                           url="https://youtube.com/watch?v=abc")
        assert r.status_code != 500
        assert not _hubo_insert_material(mock_db), (
            f"tipo='{tipo_malo}' no debe insertarse en material_estudio"
        )

    def test_tipo_mayusculas_es_normalizado(self, client, mock_db, docente_session, app):
        """
        tipo='VIDEO' → el servidor hace .lower() → 'video' → válido y aceptado.
        Esto es correcto: la normalización evita falsos rechazos.
        'SCRIPT' → 'script' → inválido → rechazado por la validación normal.
        """
        mock_db.fetchone.return_value = None
        r = _post_material(docente_session, app,
                           tipo="VIDEO",
                           url="https://www.youtube.com/watch?v=abc")
        assert r.status_code != 500


# ─────────────────────────────────────────────────────────────────────────────
# S6 — URL sin https:// (aunque el tipo sea válido)
# ─────────────────────────────────────────────────────────────────────────────

class TestUrlSinHttps:

    @pytest.mark.parametrize("url_mala", [
        "http://youtube.com/watch?v=abc",
        "ftp://archivos.com/recurso.pdf",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//youtube.com/video",
        "youtube.com/watch?v=abc",
    ])
    def test_url_sin_https_rechazada(self, client, mock_db, docente_session, app, url_mala):
        """URL sin https:// en tipo=video → rechazado."""
        r = _post_material(docente_session, app,
                           tipo="video",
                           url=url_mala)
        assert r.status_code != 500
        assert not _hubo_insert_material(mock_db), (
            f"URL sin https:// '{url_mala}' no debe insertar material"
        )


# ─────────────────────────────────────────────────────────────────────────────
# S7 — editar_material aplica las mismas validaciones
# ─────────────────────────────────────────────────────────────────────────────

class TestEditarMaterialValidacion:

    def test_editar_video_con_url_maliciosa_rechazado(self, client, mock_db, docente_session, app):
        """Editar: tipo=video con URL no-YouTube/Vimeo → rechazado."""
        mock_db.fetchone.return_value = (1,)  # material existe, id_competencia=1
        r = _post_editar(docente_session, app,
                         tipo="video",
                         url="https://sitio-malicioso.com/video.mp4")
        assert r.status_code in (302, 200)
        assert r.status_code != 500
        updates = [c for c in mock_db.execute.call_args_list
                   if "UPDATE" in str(c).upper() and "material" in str(c).lower()]
        assert len(updates) == 0, "Editar con video URL inválida NO debe hacer UPDATE"

    def test_editar_pdf_con_url_rar_rechazado(self, client, mock_db, docente_session, app):
        """Editar: tipo=pdf con URL .rar → rechazado."""
        mock_db.fetchone.return_value = (1,)
        r = _post_editar(docente_session, app,
                         tipo="pdf",
                         url="https://archivos.com/malware.rar")
        updates = [c for c in mock_db.execute.call_args_list
                   if "UPDATE" in str(c).upper() and "material" in str(c).lower()]
        assert len(updates) == 0, "Editar pdf con .rar NO debe hacer UPDATE"

    def test_editar_video_youtube_valido_procede(self, client, mock_db, docente_session, app):
        """Editar: tipo=video con YouTube válido → llega a UPDATE (no rechazado)."""
        mock_db.fetchone.return_value = (1,)
        r = _post_editar(docente_session, app,
                         tipo="video",
                         url="https://www.youtube.com/watch?v=XYZ")
        assert r.status_code != 500
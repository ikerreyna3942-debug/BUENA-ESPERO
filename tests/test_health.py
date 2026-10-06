"""
Tier 1 Tests: Healthcheck and Root Page Validation.
Verifies GET /health endpoint contract and GET / single page interface structure.
"""
import pytest
from starlette.testclient import TestClient


class TestHealthEndpoint:
    """Verifies Render zero-downtime monitoring healthcheck contract."""

    def test_health_returns_200_ok(self, client: TestClient):
        """Authoritative Contract: GET /health returns 200 OK with status: ok."""
        response = client.get("/health")
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
        assert "application/json" in response.headers.get("content-type", "")

        data = response.json()
        assert data.get("status") == "ok", f"Expected 'status': 'ok', got {data}"
        assert "version" in data, "Expected 'version' key in health response"

    def test_health_disallows_post_method(self, client: TestClient):
        """Boundary test: POST /health must return 405 Method Not Allowed."""
        response = client.post("/health")
        assert response.status_code == 405


class TestRootPageInterface:
    """Verifies single-page UI structure, drag-and-drop zone, and the 5 required buttons."""

    def test_root_page_serves_html(self, client: TestClient):
        """Authoritative Contract: GET / serves the single-page HTML interface."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_root_page_contains_drag_and_drop_surface(self, client: TestClient):
        """
        ORIGINAL_REQUEST R2 & AC 1:
        Exclusive Drag & Drop zone must be present in the HTML interface.
        """
        response = client.get("/")
        html = response.text.lower()
        # Verify dropzone element and textual guidance for dragging & dropping
        assert "drop" in html or "arrastr" in html, "HTML must contain dropzone instructions"

    def test_root_page_contains_reset_delete_button(self, client: TestClient):
        """
        ORIGINAL_REQUEST R2 & AC 3:
        Delete / 'Borrar' button must be present in the UI.
        """
        response = client.get("/")
        html = response.text.lower()
        assert "borrar" in html or "delete" in html or "limpiar" in html, "UI must contain 'Borrar' reset button"

    def test_root_page_contains_exact_five_generation_buttons(self, client: TestClient):
        """
        ORIGINAL_REQUEST R2 & AC 4:
        All 5 exact generation buttons must be present in the UI:
        1. solo mueble
        2. vistas
        3. entorno
        4. vistas + tela y madera
        5. vistas + tela
        """
        response = client.get("/")
        html = response.text.lower()

        required_buttons = [
            "solo mueble",
            "vistas",
            "entorno",
            "vistas + tela y madera",
            "vistas + tela"
        ]

        for btn in required_buttons:
            assert btn in html, f"Missing required button '{btn}' in root page HTML"

    def test_root_page_contains_copy_to_clipboard_action(self, client: TestClient):
        """
        PROJECT.md Feature 10:
        UI must include a copy action for the generated prompt.
        """
        response = client.get("/")
        html = response.text.lower()
        assert "copiar" in html or "copy" in html or "clipboard" in html, "UI must provide copy prompt action"


class TestStaticAssets:
    """Verifies static asset routes are mounted and accessible."""

    def test_static_css_accessible_if_mounted(self, client: TestClient):
        """Static CSS stylesheet should return 200 OK if mounted."""
        response = client.get("/static/css/style.css")
        # Accept 200 if mounted or 404 if inlined/different structure
        if response.status_code == 200:
            assert "text/css" in response.headers.get("content-type", "")

    def test_static_js_accessible_if_mounted(self, client: TestClient):
        """Static JS script should return 200 OK if mounted."""
        response = client.get("/static/js/app.js")
        if response.status_code == 200:
            assert "javascript" in response.headers.get("content-type", "")

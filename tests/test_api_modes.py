"""
Tier 1 & 2 Tests: Prompt Generation API Validation.
Verifies POST /api/generate for all 5 modes, file validations, parameter checks,
error responses, and API key failure handling.
"""
import io
import pytest
from starlette.testclient import TestClient

VALID_MODES = [
    "solo mueble",
    "vistas",
    "entorno",
    "vistas + tela y madera",
    "vistas + tela"
]


class TestApiModesHappyPath:
    """Verifies successful prompt generation for all 5 required modes."""

    @pytest.mark.parametrize("mode", VALID_MODES)
    def test_all_five_modes_generate_prompt_successfully(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes,
        mode: str
    ):
        """
        ORIGINAL_REQUEST R2 & AC 4:
        Each of the 5 modes must activate prompt generation and return success.
        """
        files = {
            "image": ("furniture.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {
            "mode": mode
        }

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200, f"Mode '{mode}' failed with status {response.status_code}: {response.text}"

        res_json = response.json()
        assert res_json.get("success") is True, f"Response 'success' must be True for mode '{mode}'"
        assert res_json.get("mode") == mode, f"Returned mode '{res_json.get('mode')}' does not match requested '{mode}'"

        # Check prompt content presence (either prompt or master_prompt)
        prompt_text = res_json.get("prompt") or res_json.get("data", {}).get("master_prompt")
        assert prompt_text and isinstance(prompt_text, str) and len(prompt_text) > 10, (
            f"Expected non-empty prompt text for mode '{mode}', got: {prompt_text}"
        )

    def test_mode_vistas_returns_view_prompts_and_environment(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes
    ):
        """
        ORIGINAL_REQUEST R2 & R3:
        'vistas' mode must provide multi-angle perspective prompts and environment metadata.
        """
        files = {
            "image": ("armchair.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {
            "mode": "vistas"
        }

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200
        res_json = response.json()

        # Check view_prompts existence
        view_prompts = res_json.get("view_prompts") or res_json.get("data", {}).get("view_prompts")
        assert view_prompts is not None, "Mode 'vistas' must return 'view_prompts'"

        # Check environment existence
        env = res_json.get("environment") or res_json.get("random_environment")
        assert env is not None, "Mode 'vistas' must return 'environment' metadata"

    def test_mode_with_png_format(
        self,
        client: TestClient,
        sample_png_bytes: bytes
    ):
        """Verifies PNG formatted image upload is supported."""
        files = {
            "image": ("sofa.png", sample_png_bytes, "image/png")
        }
        data = {"mode": "solo mueble"}

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200
        assert response.json().get("success") is True

    def test_mode_with_rgba_transparent_png(
        self,
        client: TestClient,
        sample_rgba_png_bytes: bytes
    ):
        """
        Verifies RGBA images with transparency are handled safely without crash
        (flattened on solid white background in memory).
        """
        files = {
            "image": ("table_alpha.png", sample_rgba_png_bytes, "image/png")
        }
        data = {"mode": "entorno"}

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200
        assert response.json().get("success") is True

    def test_mode_with_user_notes(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes
    ):
        """Verifies optional 'notes' field is accepted and processed."""
        files = {
            "image": ("chair.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {
            "mode": "vistas + tela y madera",
            "notes": "Madera de nogal oscuro con tapizado de lino marfil texturizado"
        }

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200
        assert response.json().get("success") is True

    def test_large_image_memory_guard(
        self,
        client: TestClient,
        sample_large_jpeg_bytes: bytes
    ):
        """
        Boundary Test: High-resolution image (2400x2400) triggers Pillow memory guard
        and processes successfully without exceeding memory constraints.
        """
        files = {
            "image": ("large_furniture_4k.jpg", sample_large_jpeg_bytes, "image/jpeg")
        }
        data = {"mode": "solo mueble"}

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200
        assert response.json().get("success") is True

    def test_tiny_image_boundary(
        self,
        client: TestClient,
        sample_tiny_jpeg_bytes: bytes
    ):
        """Boundary Test: 1x1 pixel image is processed without exception."""
        files = {
            "image": ("tiny.jpg", sample_tiny_jpeg_bytes, "image/jpeg")
        }
        data = {"mode": "vistas + tela"}

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200
        assert response.json().get("success") is True


class TestApiModesValidationAndErrors:
    """Verifies input validation, boundary errors, and error contracts."""

    def test_missing_image_file_returns_400(
        self,
        client: TestClient
    ):
        """
        Authoritative Contract: Missing image file returns 400 Bad Request
        (or 422 Unprocessable Entity in standard FastAPI form validation).
        """
        data = {"mode": "solo mueble"}
        response = client.post("/api/generate", data=data)
        assert response.status_code in (400, 422)
        res_json = response.json()
        assert res_json.get("success") is False or "detail" in res_json

    def test_empty_image_file_returns_400(
        self,
        client: TestClient,
        empty_file_bytes: bytes
    ):
        """Boundary Test: 0-byte uploaded file returns 400 Bad Request."""
        files = {
            "image": ("empty.jpg", empty_file_bytes, "image/jpeg")
        }
        data = {"mode": "solo mueble"}
        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 400
        res_json = response.json()
        assert res_json.get("success") is False

    def test_corrupted_image_file_returns_400(
        self,
        client: TestClient,
        corrupted_image_bytes: bytes
    ):
        """Adversarial Test: Corrupted/garbage binary file returns 400 Bad Request."""
        files = {
            "image": ("corrupted.jpg", corrupted_image_bytes, "image/jpeg")
        }
        data = {"mode": "vistas"}
        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 400
        res_json = response.json()
        assert res_json.get("success") is False

    def test_missing_mode_returns_400(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes
    ):
        """Boundary Test: Missing mode parameter returns 400 or 422."""
        files = {
            "image": ("furniture.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        response = client.post("/api/generate", files=files)
        assert response.status_code in (400, 422)
        res_json = response.json()
        assert res_json.get("success") is False or "detail" in res_json

    @pytest.mark.parametrize("invalid_mode", [
        "invalid_mode_name",
        "SOLO MUEBLE",      # Case sensitive
        "vistas_3d",
        "",
        "vistas+tela",      # Missing spaces
        "render 3d",
        "extract"
    ])
    def test_invalid_mode_value_returns_400(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes,
        invalid_mode: str
    ):
        """
        Category-Partition: Any mode outside the exact 5 allowed strings must be rejected with 400.
        """
        files = {
            "image": ("furniture.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {"mode": invalid_mode}
        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 400
        res_json = response.json()
        assert res_json.get("success") is False
        assert "error" in res_json

    def test_unsupported_file_extension_returns_400(
        self,
        client: TestClient
    ):
        """Adversarial Test: Submitting a non-image text file must return 400."""
        files = {
            "image": ("exploit.txt", b"plain text data", "text/plain")
        }
        data = {"mode": "solo mueble"}
        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 400
        res_json = response.json()
        assert res_json.get("success") is False


class TestApiKeyConfigurationAndFallback:
    """Verifies missing API key behavior and Gemini fallback cascade."""

    def test_missing_gemini_api_key_returns_500(
        self,
        client_no_api_key: TestClient,
        sample_jpeg_bytes: bytes
    ):
        """
        Authoritative Contract: Missing GEMINI_API_KEY returns 500 with guidance error.
        """
        files = {
            "image": ("furniture.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {"mode": "solo mueble"}
        response = client_no_api_key.post("/api/generate", files=files, data=data)
        assert response.status_code == 500
        res_json = response.json()
        assert res_json.get("success") is False
        assert "GEMINI_API_KEY" in res_json.get("error", "") or "api_key" in res_json.get("error", "").lower()

    def test_model_fallback_cascade_on_error(
        self,
        client: TestClient,
        mock_gemini_fallback,
        sample_jpeg_bytes: bytes
    ):
        """
        PROJECT.md Feature 15:
        If gemini-2.5-pro fails, fallback cascade catches error and uses fallback model (e.g. gemini-2.0-flash).
        """
        files = {
            "image": ("furniture.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {"mode": "vistas"}

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 200
        res_json = response.json()
        assert res_json.get("success") is True
        # Verify fallback model was called or returned
        assert mock_gemini_fallback.models.generate_content.call_count >= 2

    def test_all_models_fail_returns_500(
        self,
        client: TestClient,
        mock_gemini_all_fail,
        sample_jpeg_bytes: bytes
    ):
        """
        If all models in cascade fail, returns structured 500 response without unhandled crash.
        """
        files = {
            "image": ("furniture.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {"mode": "solo mueble"}

        response = client.post("/api/generate", files=files, data=data)
        assert response.status_code == 500
        res_json = response.json()
        assert res_json.get("success") is False
        assert "error" in res_json

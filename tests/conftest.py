"""
Pytest configuration and shared fixtures for the Furniture Prompt Generator E2E test suite.
Provides synthetic test images, mock Gemini AI client, and FastAPI TestClient fixtures.
"""
import io
import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Synthetic Test Image Generators (Pillow)
# ---------------------------------------------------------------------------

def create_synthetic_image(
    format: str = "JPEG",
    size: tuple[int, int] = (400, 300),
    color: tuple[int, ...] = (180, 140, 100),
    mode: str = "RGB"
) -> bytes:
    """Creates an in-memory synthetic image of specified mode, size, and format."""
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


@pytest.fixture(scope="session")
def sample_jpeg_bytes() -> bytes:
    """Standard synthetic RGB JPEG image (400x300)."""
    return create_synthetic_image(format="JPEG", size=(400, 300), color=(195, 155, 110), mode="RGB")


@pytest.fixture(scope="session")
def sample_png_bytes() -> bytes:
    """Standard synthetic RGB PNG image (400x300)."""
    return create_synthetic_image(format="PNG", size=(400, 300), color=(140, 160, 180), mode="RGB")


@pytest.fixture(scope="session")
def sample_rgba_png_bytes() -> bytes:
    """Synthetic RGBA PNG image with transparent alpha channel (300x300)."""
    return create_synthetic_image(format="PNG", size=(300, 300), color=(200, 100, 50, 128), mode="RGBA")


@pytest.fixture(scope="session")
def sample_large_jpeg_bytes() -> bytes:
    """Large synthetic image (2400x2400) to stress-test Pillow memory downscale guard (>1600px)."""
    return create_synthetic_image(format="JPEG", size=(2400, 2400), color=(120, 100, 80), mode="RGB")


@pytest.fixture(scope="session")
def sample_boundary_1600_jpeg_bytes() -> bytes:
    """Image at exact boundary (1600x1600) for Boundary Value Analysis."""
    return create_synthetic_image(format="JPEG", size=(1600, 1600), color=(100, 120, 140), mode="RGB")


@pytest.fixture(scope="session")
def sample_tiny_jpeg_bytes() -> bytes:
    """Minimal boundary image (1x1 pixel) for Boundary Value Analysis."""
    return create_synthetic_image(format="JPEG", size=(1, 1), color=(255, 255, 255), mode="RGB")


@pytest.fixture(scope="session")
def corrupted_image_bytes() -> bytes:
    """Invalid byte stream simulating a corrupted image upload."""
    return b"NOT_A_VALID_IMAGE_DATA_STREAM_CORRUPT_0xDEADBEEF"


@pytest.fixture(scope="session")
def empty_file_bytes() -> bytes:
    """0-byte empty file."""
    return b""


# ---------------------------------------------------------------------------
# Standard Mock Gemini AI Responses
# ---------------------------------------------------------------------------

DEFAULT_MOCK_GEMINI_ANALYSIS = {
    "furniture_analysis": {
        "furniture_type": "Nordic Minimalist Oak Armchair",
        "geometry_topology": "Curved bentwood backrest, cylindrical tapered oak legs, recessed cushion seat",
        "color_palette": "Natural white oak #E3D9CE, warm biscuit oatmeal #D9C8B4",
        "materials_texture": "Dense textured bouclé fabric with 2.5mm nubby loops; satin oiled European white oak",
        "lighting_optics": "Soft studio strobe 5500K, diffused contact ambient occlusion under legs"
    },
    "master_prompt": "Ultra-realistic commercial product photograph of a Nordic Minimalist Oak Armchair. The armchair features a curved bentwood backrest and warm oatmeal bouclé upholstery with satin oiled white oak legs. Hasselblad H6D-100c, 120mm macro lens, f/11 studio lighting on pure white seamless background.",
    "negative_prompt": "shadows, drop shadows, floor reflections, studio background, room, interior, changed geometry, changed color, text, watermark, CGI, 3D render",
    "view_prompts": {
        "vista_frente_0deg": "Eye-level frontal 0-degree view of Nordic Minimalist Oak Armchair, isolated on white background, f/11 studio strobe.",
        "vista_lateral_90deg": "Orthogonal side 90-degree profile view highlighting the graceful taper and joinery of the solid oak legs.",
        "vista_3_4_izquierda": "3/4 isometric perspective at 45-degree angle from the left, emphasizing cushion curvature and texture.",
        "vista_desde_arriba": "Top-down 90-degree zenith view capturing seat cushion proportions and armrest symmetry.",
        "vista_3_4_posterior": "Rear 3/4 isometric perspective at 135-degree angle showcasing backrest curvature and wood joinery."
    },
    "environment_notes": "Minimalist Japandi with warm hinoki cypress slats, lime-wash beige plaster, and tatami accents"
}


class MockGeminiGenerateResponse:
    """Simulates google.genai response object returned by generate_content."""
    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self._data = data or DEFAULT_MOCK_GEMINI_ANALYSIS
        self.text = json.dumps(self._data)

    @property
    def parsed(self):
        return self._data


# ---------------------------------------------------------------------------
# Gemini API Mock Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_gemini_client():
    """
    Hermetic mock fixture for Google GenAI client (`google.genai.Client`).
    Intercepts calls to `client.models.generate_content(...)` and returns
    structured Art Director response without external network requests.
    """
    with patch("google.genai.Client") as mock_client_cls:
        instance = MagicMock()
        mock_response = MockGeminiGenerateResponse()
        instance.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_gemini_fallback():
    """
    Simulates a model fallback cascade:
    1st call (gemini-2.5-pro): Raises an exception (simulating 429 quota or 503 unavailable).
    2nd call (gemini-2.0-flash): Successfully returns content.
    """
    from google.genai.errors import APIError

    with patch("google.genai.Client") as mock_client_cls:
        instance = MagicMock()
        mock_response = MockGeminiGenerateResponse()

        # Create dummy APIError for failure on first attempt
        error_response = MagicMock()
        error_response.status_code = 429
        error_response.json.return_value = {"error": {"message": "Resource exhausted"}}
        api_error = APIError(code=429, response_json={"error": {"message": "Resource exhausted: 429 Quota Exceeded"}}, response=error_response)

        instance.models.generate_content.side_effect = [
            api_error,
            mock_response
        ]
        mock_client_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_gemini_all_fail():
    """
    Simulates total failure where all models in the cascade fail.
    """
    from google.genai.errors import APIError

    with patch("google.genai.Client") as mock_client_cls:
        instance = MagicMock()
        error_response = MagicMock()
        error_response.status_code = 503
        error_response.json.return_value = {"error": {"message": "Service unavailable"}}
        api_error = APIError(code=503, response_json={"error": {"message": "Service unavailable: 503"}}, response=error_response)

        instance.models.generate_content.side_effect = api_error
        mock_client_cls.return_value = instance
        yield instance


# ---------------------------------------------------------------------------
# Application & TestClient Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def test_env(monkeypatch):
    """Sets standard mock environment variables for testing."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key-12345")
    monkeypatch.setenv("PORT", "8000")
    return {"GEMINI_API_KEY": "test-api-key-12345", "PORT": "8000"}


@pytest.fixture
def client(test_env, mock_gemini_client):
    """
    Provides a FastAPI TestClient configured with mock environment and mocked Gemini client.
    """
    from starlette.testclient import TestClient
    try:
        from app import app
    except ImportError as e:
        pytest.fail(f"Could not import 'app' from app.py: {e}")

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_no_api_key(monkeypatch):
    """
    Provides a FastAPI TestClient without any GEMINI_API_KEY or GOOGLE_API_KEY in environment.
    """
    from starlette.testclient import TestClient
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    try:
        from app import app
    except ImportError as e:
        pytest.fail(f"Could not import 'app' from app.py: {e}")

    with TestClient(app) as test_client:
        yield test_client

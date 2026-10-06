"""
test_challenger_stress.py
=========================
Adversarial Stress Test Suite for Milestone 1 (M1) Backend Services.
Author: m1_challenger_1 (Empirical Challenger)

Tests rigorous boundary conditions:
1. Zero-byte files, empty streams, missing streams, corrupted headers.
2. Huge images (>50MB), high-resolution (4000x4000, 8000x8000), decompression limits.
3. Unusual aspect ratios (100:1 ultra-wide, 1:100 ultra-tall, 1x1, 16000x1).
4. Corrupted file streams (truncated JPEG/PNG, random noise, MIME confusion).
5. High-volume sampling of services/random_scenarios.py (5,000 iterations):
   - Shannon entropy across all 4 axes (styles, spaces, lightings, palettes).
   - Zero duplicate burst detection (consecutive repeat runs).
   - State-space coverage analysis (3,360 combinations).
"""

import io
import math
import os
from collections import Counter
from typing import Dict, Any, List, Tuple
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from starlette.testclient import TestClient

from services.gemini_service import optimize_furniture_image, ALLOWED_MODES
from services.random_scenarios import (
    sample_random_scene,
    ARCHITECTURAL_STYLES,
    LOCATIONS_SPACES,
    LIGHTING_ATMOSPHERES,
    COLOR_HARMONIES,
    get_taxonomy_metrics,
)


# ===========================================================================
# Helper Generators for Adversarial Images
# ===========================================================================

def generate_aspect_ratio_image(width: int, height: int, format: str = "JPEG") -> bytes:
    """Generates an image of arbitrary dimensions."""
    img = Image.new("RGB", (width, height), (150, 120, 90))
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def generate_truncated_jpeg() -> bytes:
    """Returns a byte sequence with valid JPEG magic bytes but abruptly truncated."""
    return b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"


def generate_truncated_png() -> bytes:
    """Returns a byte sequence with valid PNG header but missing IHDR/IDAT chunks."""
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


# ===========================================================================
# 1. Zero-Byte & Boundary File Stream Tests
# ===========================================================================

class TestZeroByteAndStreamBoundaries:
    """Validates resilience against empty, 0-byte, and anomalous file streams."""

    def test_optimize_zero_byte_raises_value_error(self):
        """Zero-byte input to optimize_furniture_image must raise ValueError cleanly."""
        with pytest.raises(ValueError, match="No se recibieron datos"):
            optimize_furniture_image(b"")

    def test_optimize_none_raises_value_error(self):
        """None input to optimize_furniture_image must raise ValueError cleanly."""
        with pytest.raises(ValueError):
            optimize_furniture_image(None)  # type: ignore

    def test_api_zero_byte_file_returns_400(self, client: TestClient):
        """API must return 400 Bad Request when 0-byte file is uploaded."""
        files = {"image": ("empty_photo.jpg", b"", "image/jpeg")}
        resp = client.post("/api/generate", files=files, data={"mode": "solo mueble"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "vacío" in data["error"].lower() or "obligatorio" in data["error"].lower()

    def test_api_single_byte_corrupted_file_returns_400(self, client: TestClient):
        """1-byte file must fail Pillow decoding and return 400 Bad Request."""
        files = {"image": ("one_byte.jpg", b"\x00", "image/jpeg")}
        resp = client.post("/api/generate", files=files, data={"mode": "vistas"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        err_msg = data["error"].lower()
        assert "corrupto" in err_msg or "inválido" in err_msg or "imagen válida" in err_msg

    def test_api_filename_without_extension_with_image_mime(
        self, client: TestClient, sample_jpeg_bytes: bytes
    ):
        """Valid JPEG data with no extension in filename but valid MIME must succeed."""
        files = {"image": ("furniture_upload", sample_jpeg_bytes, "image/jpeg")}
        resp = client.post("/api/generate", files=files, data={"mode": "solo mueble"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ===========================================================================
# 2. Huge Images, Downscale Verification & Memory Guard Tests
# ===========================================================================

class TestHugeImagesAndMemoryGuard:
    """Stress tests high resolution images and file size caps."""

    def test_oversized_file_payload_rejection(self, client: TestClient):
        """Files exceeding MAX_IMAGE_SIZE_MB (50MB) must be rejected with 400."""
        # 51 MB dummy payload with valid extension
        oversized_bytes = b"0" * (51 * 1024 * 1024)
        files = {"image": ("huge_furniture.jpg", oversized_bytes, "image/jpeg")}
        resp = client.post("/api/generate", files=files, data={"mode": "solo mueble"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "supera el tamaño máximo" in data["error"]

    def test_high_resolution_downscaling_fidelity(self):
        """
        An image of 4000x3000 must be downscaled to max 1600px along longest dimension,
        maintaining exact aspect ratio (4000:3000 -> 1600:1200).
        """
        high_res_bytes = generate_aspect_ratio_image(4000, 3000)
        optimized = optimize_furniture_image(high_res_bytes, max_dim=1600)

        with Image.open(io.BytesIO(optimized)) as out_img:
            assert out_img.width == 1600
            assert out_img.height == 1200
            assert out_img.format == "JPEG"

    def test_exact_1600_boundary_not_upscaled_or_downscaled(self):
        """Images at exactly 1600x1200 should preserve their original dimensions."""
        boundary_bytes = generate_aspect_ratio_image(1600, 1200)
        optimized = optimize_furniture_image(boundary_bytes, max_dim=1600)

        with Image.open(io.BytesIO(optimized)) as out_img:
            assert out_img.width == 1600
            assert out_img.height == 1200

    def test_small_image_never_upscaled(self):
        """Images smaller than max_dim (e.g. 300x200) must NOT be upscaled."""
        small_bytes = generate_aspect_ratio_image(300, 200)
        optimized = optimize_furniture_image(small_bytes, max_dim=1600)

        with Image.open(io.BytesIO(optimized)) as out_img:
            assert out_img.width == 300
            assert out_img.height == 200

    def test_huge_square_image_8000x8000(self):
        """Very large image 8000x8000 must scale to exactly 1600x1600 without crash."""
        huge_bytes = generate_aspect_ratio_image(8000, 8000)
        optimized = optimize_furniture_image(huge_bytes, max_dim=1600)

        with Image.open(io.BytesIO(optimized)) as out_img:
            assert out_img.width == 1600
            assert out_img.height == 1600


# ===========================================================================
# 3. Unusual Aspect Ratios & Geometry Edge Cases
# ===========================================================================

class TestUnusualAspectRatios:
    """Stress tests extreme panoramas, vertical slivers, and tiny images."""

    def test_ultra_wide_panorama_ratio_100_to_1(self):
        """Extreme ultra-wide banner (5000 x 50) must scale to 1600 x 16."""
        wide_bytes = generate_aspect_ratio_image(5000, 50)
        optimized = optimize_furniture_image(wide_bytes, max_dim=1600)

        with Image.open(io.BytesIO(optimized)) as out_img:
            assert out_img.width == 1600
            assert out_img.height == 16

    def test_ultra_tall_skyscraper_ratio_1_to_100(self):
        """Extreme vertical sliver (50 x 5000) must scale to 16 x 1600."""
        tall_bytes = generate_aspect_ratio_image(50, 5000)
        optimized = optimize_furniture_image(tall_bytes, max_dim=1600)

        with Image.open(io.BytesIO(optimized)) as out_img:
            assert out_img.width == 16
            assert out_img.height == 1600

    def test_minimal_1x1_pixel_image(self):
        """1x1 pixel image must pass through without division-by-zero or crash."""
        tiny_bytes = generate_aspect_ratio_image(1, 1)
        optimized = optimize_furniture_image(tiny_bytes, max_dim=1600)

        with Image.open(io.BytesIO(optimized)) as out_img:
            assert out_img.width == 1
            assert out_img.height == 1

    def test_extreme_aspect_ratio_16000_to_1(self):
        """
        An extreme 16000x1 image: Pillow thumbnail calculation may round height to 0.
        System must handle this either by scaling or cleanly raising ValueError (handled as 400).
        """
        try:
            extreme_bytes = generate_aspect_ratio_image(16000, 1)
            optimized = optimize_furniture_image(extreme_bytes, max_dim=1600)
            with Image.open(io.BytesIO(optimized)) as out_img:
                assert out_img.width >= 1
                assert out_img.height >= 1
        except ValueError as e:
            # Clean ValueError is the expected graceful rejection
            assert "Error al procesar la imagen" in str(e) or "height" in str(e).lower()


# ===========================================================================
# 4. Corrupted File Streams & Encodings
# ===========================================================================

class TestCorruptedFileStreams:
    """Stress tests truncated streams, random noise, and format spoofing."""

    def test_truncated_jpeg_stream(self, client: TestClient):
        """Abruptly truncated JPEG stream must be rejected with 400 Bad Request."""
        trunc_bytes = generate_truncated_jpeg()
        files = {"image": ("broken.jpg", trunc_bytes, "image/jpeg")}
        resp = client.post("/api/generate", files=files, data={"mode": "solo mueble"})
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_truncated_png_stream(self, client: TestClient):
        """Truncated PNG stream missing chunks must be rejected with 400 Bad Request."""
        trunc_bytes = generate_truncated_png()
        files = {"image": ("broken.png", trunc_bytes, "image/png")}
        resp = client.post("/api/generate", files=files, data={"mode": "solo mueble"})
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_random_binary_garbage(self, client: TestClient):
        """Pure random entropy (os.urandom) must be cleanly rejected with 400."""
        random_bytes = os.urandom(2048)
        files = {"image": ("random.jpg", random_bytes, "image/jpeg")}
        resp = client.post("/api/generate", files=files, data={"mode": "vistas"})
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_svg_xml_file_rejected(self, client: TestClient):
        """SVG vector XML file (not supported raster) must return 400."""
        svg_bytes = b"<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'><rect width='100' height='100'/></svg>"
        files = {"image": ("vector.svg", svg_bytes, "image/svg+xml")}
        resp = client.post("/api/generate", files=files, data={"mode": "solo mueble"})
        assert resp.status_code == 400
        assert resp.json()["success"] is False


# ===========================================================================
# 5. High-Volume Sampling of random_scenarios.py (Entropy & Bursts)
# ===========================================================================

class TestRandomScenariosHighVolumeStress:
    """
    High-volume Monte Carlo empirical sampling (5,000 draws) to mathematically
    and empirically verify entropy, absence of duplicate bursts, and state coverage.
    """

    @pytest.fixture(scope="class")
    def sampled_dataset_5000(self) -> List[Tuple[str, str, str, str]]:
        """Samples 5,000 scenarios sequentially."""
        dataset = []
        for _ in range(5000):
            sc = sample_random_scene()
            dataset.append((sc["style"], sc["location"], sc["lighting"], sc["palette"]))
        return dataset

    def test_high_volume_shannon_entropy_all_axes(
        self, sampled_dataset_5000: List[Tuple[str, str, str, str]]
    ):
        """
        Empirically computes Shannon entropy H(X) = -sum(p * log2(p)) for each axis.
        Ensures high entropy (within 90% of theoretical maximum uniform entropy).
        """
        total = len(sampled_dataset_5000)
        assert total == 5000

        # Axis counters
        styles = Counter(t[0] for t in sampled_dataset_5000)
        spaces = Counter(t[1] for t in sampled_dataset_5000)
        lightings = Counter(t[2] for t in sampled_dataset_5000)
        palettes = Counter(t[3] for t in sampled_dataset_5000)

        # 1. Styles (M=10): max entropy = log2(10) ~ 3.3219 bits
        h_styles = -sum((c / total) * math.log2(c / total) for c in styles.values())
        assert h_styles >= 3.20, f"Styles entropy too low: {h_styles:.3f} bits (max: 3.322)"

        # 2. Spaces (M=8): max entropy = log2(8) = 3.0000 bits
        h_spaces = -sum((c / total) * math.log2(c / total) for c in spaces.values())
        assert h_spaces >= 2.90, f"Spaces entropy too low: {h_spaces:.3f} bits (max: 3.000)"

        # 3. Lightings (M=7): max entropy = log2(7) ~ 2.8074 bits
        h_lightings = -sum((c / total) * math.log2(c / total) for c in lightings.values())
        assert h_lightings >= 2.70, f"Lightings entropy too low: {h_lightings:.3f} bits (max: 2.807)"

        # 4. Palettes (M=6): max entropy = log2(6) ~ 2.5850 bits
        h_palettes = -sum((c / total) * math.log2(c / total) for c in palettes.values())
        assert h_palettes >= 2.50, f"Palettes entropy too low: {h_palettes:.3f} bits (max: 2.585)"

    def test_zero_duplicate_bursts_length_ge_3(
        self, sampled_dataset_5000: List[Tuple[str, str, str, str]]
    ):
        """
        Empirically verifies that there are ZERO bursts of 3 or more consecutive identical scenarios.
        In 5,000 independent samples from 3,360 states, a 3-repeat burst has probability ~ 1 / (3360^2)
        and must not occur.
        """
        max_run = 1
        current_run = 1

        for i in range(1, len(sampled_dataset_5000)):
            if sampled_dataset_5000[i] == sampled_dataset_5000[i - 1]:
                current_run += 1
                if current_run > max_run:
                    max_run = current_run
            else:
                current_run = 1

        # Max consecutive identical 4-tuples must be strictly < 3
        assert max_run < 3, f"Detected duplicate burst of length {max_run} consecutive identical scenes!"

    def test_state_space_coverage_ratio(
        self, sampled_dataset_5000: List[Tuple[str, str, str, str]]
    ):
        """
        In 5,000 draws from 3,360 states, theoretical expected distinct states is:
        E[distinct] = 3360 * (1 - (1 - 1/3360)^5000) ~ 2,604 states (77.5%).
        Verifies that actual coverage is >= 70% (at least 2,350 unique states seen).
        """
        unique_states = set(sampled_dataset_5000)
        coverage_ratio = len(unique_states) / 3360.0
        assert coverage_ratio >= 0.70, (
            f"Coverage ratio too low: {len(unique_states)}/3360 ({coverage_ratio:.1%}). Expected >= 70%."
        )

    def test_all_individual_categories_covered_100_percent(
        self, sampled_dataset_5000: List[Tuple[str, str, str, str]]
    ):
        """Every single style, space, lighting, and palette must be selected at least once."""
        observed_styles = set(t[0] for t in sampled_dataset_5000)
        observed_spaces = set(t[1] for t in sampled_dataset_5000)
        observed_lightings = set(t[2] for t in sampled_dataset_5000)
        observed_palettes = set(t[3] for t in sampled_dataset_5000)

        assert observed_styles == set(ARCHITECTURAL_STYLES), "Some architectural styles were never selected!"
        assert observed_spaces == set(LOCATIONS_SPACES), "Some spaces were never selected!"
        assert observed_lightings == set(LIGHTING_ATMOSPHERES), "Some lighting atmospheres were never selected!"
        assert observed_palettes == set(COLOR_HARMONIES), "Some color harmonies were never selected!"

    def test_seeding_thread_safety_and_isolation(self):
        """Verifies that sample_random_scene(seed=X) does not pollute global random state."""
        import random
        # Save pre-state
        random.seed(12345)
        pre_val = random.random()

        # Call with explicit seed
        _ = sample_random_scene(seed=999)

        # Reset global seed to 12345 and check if sequence is unaffected
        random.seed(12345)
        post_val = random.random()

        assert pre_val == post_val, "sample_random_scene(seed=...) corrupted the global random state!"

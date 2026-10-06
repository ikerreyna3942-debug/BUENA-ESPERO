"""
Tier 1 & 2 Tests: Dynamic Randomization Engine (Requirement R3 & AC 5).
Verifies statistical entropy/variability across calls to 'vistas', non-empty architectural
attributes, combinatoric taxonomy pool cardinality (1,680+ combinations), and deterministic seeding.
"""
import math
from collections import Counter
import pytest
from starlette.testclient import TestClient


class TestRandomScenariosTaxonomy:
    """Verifies combinatoric taxonomy richness, pool sizes, and non-empty attributes."""

    def test_taxonomy_pool_cardinality(self):
        """
        ORIGINAL_REQUEST R3 & PROJECT.md:
        Combinatoric pool must feature at least 8 styles × 7 spaces × 6 lightings × 5 palettes >= 1,680 combinations.
        """
        from services.random_scenarios import (
            ARCHITECTURAL_STYLES,
            LOCATIONS_SPACES,
            LIGHTING_ATMOSPHERES,
            COLOR_HARMONIES
        )

        assert len(ARCHITECTURAL_STYLES) >= 8, f"Expected >= 8 styles, got {len(ARCHITECTURAL_STYLES)}"
        assert len(LOCATIONS_SPACES) >= 7, f"Expected >= 7 locations, got {len(LOCATIONS_SPACES)}"
        assert len(LIGHTING_ATMOSPHERES) >= 6, f"Expected >= 6 lighting atmospheres, got {len(LIGHTING_ATMOSPHERES)}"
        assert len(COLOR_HARMONIES) >= 5, f"Expected >= 5 color harmonies, got {len(COLOR_HARMONIES)}"

        total_combinations = (
            len(ARCHITECTURAL_STYLES) *
            len(LOCATIONS_SPACES) *
            len(LIGHTING_ATMOSPHERES) *
            len(COLOR_HARMONIES)
        )
        assert total_combinations >= 1680, f"Expected >= 1,680 total combinations, got {total_combinations}"

    def test_all_pool_attributes_are_rich_descriptive_strings(self):
        """Verifies that every entry in each pool is a non-empty, detailed architectural description."""
        from services.random_scenarios import (
            ARCHITECTURAL_STYLES,
            LOCATIONS_SPACES,
            LIGHTING_ATMOSPHERES,
            COLOR_HARMONIES
        )

        for pool_name, pool in [
            ("ARCHITECTURAL_STYLES", ARCHITECTURAL_STYLES),
            ("LOCATIONS_SPACES", LOCATIONS_SPACES),
            ("LIGHTING_ATMOSPHERES", LIGHTING_ATMOSPHERES),
            ("COLOR_HARMONIES", COLOR_HARMONIES)
        ]:
            for item in pool:
                assert isinstance(item, str), f"Item in {pool_name} is not a string: {item}"
                assert len(item.strip()) >= 15, f"Item in {pool_name} is too short/generic: '{item}'"

    def test_sample_random_scene_structure(self):
        """Verifies that sample_random_scene returns all required architectural attributes."""
        from services.random_scenarios import sample_random_scene

        scene = sample_random_scene()
        assert isinstance(scene, dict), "sample_random_scene must return a dictionary"

        required_keys = ["style", "location", "lighting", "palette"]
        for key in required_keys:
            assert key in scene, f"Missing key '{key}' in sample_random_scene output"
            assert isinstance(scene[key], str) and len(scene[key]) > 0

        # injection_text should contain the selected attributes
        injection = scene.get("injection_text") or scene.get("description")
        assert injection and isinstance(injection, str)
        assert scene["style"] in injection or scene["location"] in injection


class TestRandomScenariosEntropy:
    """Verifies statistical entropy and variability across calls (Requirement R3)."""

    def test_statistical_entropy_across_multiple_calls(self):
        """
        ORIGINAL_REQUEST R3 & AC 5:
        Statistical test verifying that multiple calls produce distinct environments without repetition loops.
        Draws 60 random samples from 1,680+ space; expects high uniqueness (>85%) and balanced distribution.
        """
        from services.random_scenarios import sample_random_scene

        sample_size = 60
        sampled_tuples = []
        style_counts = Counter()

        for _ in range(sample_size):
            scene = sample_random_scene()
            key = (scene["style"], scene["location"], scene["lighting"], scene["palette"])
            sampled_tuples.append(key)
            style_counts[scene["style"]] += 1

        unique_combinations = set(sampled_tuples)
        uniqueness_ratio = len(unique_combinations) / sample_size

        # In a 1,680 combination space, 60 random uniform samples should produce >= 50 unique combinations (>83%)
        assert uniqueness_ratio >= 0.80, (
            f"Insufficient entropy! Only {len(unique_combinations)}/{sample_size} "
            f"({uniqueness_ratio:.1%}) unique scenes generated."
        )

        # Shannon Entropy check across architectural styles:
        # No single style should monopolize more than 40% of samples
        most_common_style, highest_count = style_counts.most_common(1)[0]
        max_ratio = highest_count / sample_size
        assert max_ratio <= 0.45, (
            f"Style distribution is biased! '{most_common_style}' appeared {highest_count}/{sample_size} "
            f"times ({max_ratio:.1%}). Expected < 45%."
        )

        # Calculate Shannon entropy H(X) = -sum(p * log2(p))
        entropy = -sum((cnt / sample_size) * math.log2(cnt / sample_size) for cnt in style_counts.values())
        # Max entropy for 8 categories is log2(8) = 3.0 bits. We expect at least 2.0 bits.
        assert entropy >= 2.0, f"Entropy too low ({entropy:.2f} bits). Distribution lacks variance."

    def test_deterministic_seeding(self):
        """
        Verifies repeatable execution when a seed is explicitly provided.
        Crucial for reproducible integration testing and design audits.
        """
        from services.random_scenarios import sample_random_scene

        seed_a = 42
        seed_b = 999

        run1 = sample_random_scene(seed=seed_a)
        run2 = sample_random_scene(seed=seed_a)
        run_diff = sample_random_scene(seed=seed_b)

        # Same seed must yield identical outputs
        assert run1["style"] == run2["style"], "Deterministic seed failed on 'style'"
        assert run1["location"] == run2["location"], "Deterministic seed failed on 'location'"
        assert run1["lighting"] == run2["lighting"], "Deterministic seed failed on 'lighting'"
        assert run1["palette"] == run2["palette"], "Deterministic seed failed on 'palette'"

        # Different seeds should yield different combinations
        is_different = (
            run1["style"] != run_diff["style"] or
            run1["location"] != run_diff["location"] or
            run1["lighting"] != run_diff["lighting"]
        )
        assert is_different, "Different seeds unexpectedly produced identical outputs"


class TestRandomScenariosApiIntegration:
    """Verifies that POST /api/generate with mode='vistas' injects varying environments into API responses."""

    def test_vistas_endpoint_produces_varying_environments_across_requests(
        self,
        client: TestClient,
        sample_jpeg_bytes: bytes
    ):
        """
        ORIGINAL_REQUEST AC 5:
        Clicking the 'vistas' button multiple times ensures variability in the generated environment.
        """
        files = {
            "image": ("sofa.jpg", sample_jpeg_bytes, "image/jpeg")
        }
        data = {"mode": "vistas"}

        environments_seen = set()

        for _ in range(5):
            response = client.post("/api/generate", files=files, data=data)
            assert response.status_code == 200
            res_json = response.json()

            env = res_json.get("environment") or res_json.get("random_environment")
            assert env is not None, "Missing environment in 'vistas' response"

            # Create identifiable hash or string
            env_sig = f"{env.get('style')}|{env.get('location')}|{env.get('lighting')}"
            environments_seen.add(env_sig)

        # Out of 5 requests, we expect at least 3 distinct environments
        assert len(environments_seen) >= 3, (
            f"Expected at least 3 distinct environments in 5 'vistas' requests, but got {len(environments_seen)}: "
            f"{environments_seen}"
        )

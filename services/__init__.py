"""
services package initialization.
"""

from .gemini_service import (
    GeminiService,
    get_gemini_service,
    optimize_furniture_image,
    ALLOWED_MODES,
    MODEL_FALLBACK_CASCADE,
)
from .random_scenarios import (
    sample_random_scene,
    get_taxonomy_metrics,
    get_all_categories,
    ARCHITECTURAL_STYLES,
    LOCATIONS_SPACES,
    SPACES_LOCATIONS,
    LIGHTING_ATMOSPHERES,
    COLOR_HARMONIES,
)

__all__ = [
    "GeminiService",
    "get_gemini_service",
    "optimize_furniture_image",
    "ALLOWED_MODES",
    "MODEL_FALLBACK_CASCADE",
    "sample_random_scene",
    "get_taxonomy_metrics",
    "get_all_categories",
    "ARCHITECTURAL_STYLES",
    "LOCATIONS_SPACES",
    "SPACES_LOCATIONS",
    "LIGHTING_ATMOSPHERES",
    "COLOR_HARMONIES",
]

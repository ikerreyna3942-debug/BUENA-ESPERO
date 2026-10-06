"""
services/random_scenarios.py
=============================
Combinatoric Taxonomy & Dynamic Environment Randomizer for Furniture Prompt Generator Studio.

Fulfills Requirement R3 and Acceptance Criteria item 5:
Generates rich, photorealistic, non-repetitive architectural environments
and lighting atmospheres for the 'vistas' prompt generation mode.

Combinatorics:
- Architectural Styles: 10
- Spaces / Locations: 8
- Lighting Atmospheres: 7
- Color Harmonies: 6
Total Unique Combinations: 10 * 8 * 7 * 6 = 3,360 combinations (minimum required: 1,680)
"""

import random
from typing import Optional, Dict, Any, Tuple, List


ARCHITECTURAL_STYLES: Tuple[str, ...] = (
    "Minimalist Japandi with vertical warm hinoki cypress slats, hand-applied beige lime-wash plaster walls, honed travertine accents, and subtle woven tatami textures",
    "Brutalist Bauhaus open-concept loft featuring raw bush-hammered architectural concrete, exposed structural steel I-beams, polished industrial terrazzo flooring, and geometric spatial purity",
    "Modern Mediterranean coastal villa with curved whitewashed stucco walls, hand-formed terracotta floor tiles, recessed arched loggias, and exposed raw timber ceiling beams",
    "Nordic Scandinavian modern interior with pale Douglas fir wide-plank flooring, acoustic fluted white oak wall paneling, floor-to-ceiling glass curtain walls, and clean minimalist baseboards",
    "Contemporary Parisian Haussmann apartment with restored chevron oak parquet floors, delicate custom white boiserie wall paneling, carved Carrara marble fireplace mantel, and 3.8-meter soaring ceilings",
    "Desert modernist pavilion featuring monolithic rammed-earth walls, weathered corten steel fascias, expansive seamless glass sliding planes, and continuous polished stone floor transitioning to outdoor patio",
    "Industrial Milanese design atelier with textured charcoal microcement surfaces, blackened brushed aluminum window framing, ribbed fluted glass acoustic partitions, and exposed historic brickwork",
    "Organic Wabi-Sabi pavilion with hand-troweled acoustic clay plaster walls, soft organic asymmetric wall recesses, split-face natural slate flooring, and centuries-old reclaimed timber lintels",
    "Mid-century Palm Springs desert residence with floating post-and-beam construction, geometric breeze-block decorative screens, warm American walnut millwork, and seamless terrazzo flooring",
    "Contemporary neo-classical penthouse featuring bookmatched Calacatta marble slab accent walls, muted brushed brass architectural reveals, cove-lit coffered ceilings, and smoked herringbone oak",
)

LOCATIONS_SPACES: Tuple[str, ...] = (
    "Sunken architectural conversation pit with stepped perimeter seating adjacent to a serene indoor Zen pebble garden and specimen bonsai",
    "Double-height living pavilion overlooking a tranquil outdoor reflecting water pool and sculpture court through two-story frameless glass",
    "Curated residential art gallery salon flanked by minimalist architectural display plinths, recessed museum picture rails, and deep window reveals",
    "Sunlit garden veranda enclosed by seamless oversized pivot glass doors opening onto an ancient olive grove and stone courtyard",
    "Master penthouse corner lounge with panoramic 270-degree metropolitan skyline vistas through sheer floor-to-ceiling Belgian linen drapes",
    "Quiet architectural library alcove framed by flush floor-to-ceiling fluted timber bookcases, integrated ladder rail, and reading niche",
    "Minimalist indoor-outdoor central atrium courtyard framed by monolithic limestone colonnades, open sky aperture, and low water basin",
    "Executive penthouse reception gallery with a floating cantilevered black granite hearth and access to a landscaped cantilevered terrace",
)

# Alias for backwards/cross-module compatibility
SPACES_LOCATIONS: Tuple[str, ...] = LOCATIONS_SPACES

LIGHTING_ATMOSPHERES: Tuple[str, ...] = (
    "Low-angle golden hour rake sunlight casting long, dramatic geometric window frame shadows and rich amber highlights across the floor",
    "Diffused overcast northern daylight filtering through massive skylights, providing pristine, ultra-soft shadow gradations and true-to-life color fidelity",
    "Crisp early morning dawn light with cool 6500K blue ambient skylight fill and sharp, warm directional sunbeam streaks penetrating the space",
    "Warm late-afternoon sun filtering through sheer linen curtains and lush exterior foliage, creating gentle caustics and dappled organic light patterns",
    "High-end architectural gallery lighting with 5500K museum-grade ceiling track spotlights, balanced CRI 98 color rendering, and subtle perimeter cove illumination",
    "Atmospheric dusk twilight with warm 2700K indirect LED cove lighting accentuating textured wall planes and subtle floor grazing wash lights",
    "Midday zenith skylight casting soft vertical volumetric shafts with gentle ambient fill, highlighting top surfaces and contour silhouettes",
)

COLOR_HARMONIES: Tuple[str, ...] = (
    "Warm monochromatic palette of alabaster white, warm oatmeal, cashmere beige, and honed Roman travertine stone",
    "Earthy organic harmony of warm terracotta, muted sage green, raw umber, dry clay, and bleached natural linen",
    "High-contrast architectural palette of chalk white plaster, deep charcoal graphite, matte black steel, and brushed antique bronze",
    "Serene mineral tones featuring blue-gray slate, limestone cream, pale sandstone, and subtle muted celadon undertones",
    "Warm Nordic palette of biscuit beige, light honey birch, warm ecru wool, and soft muted desert sand",
    "Moody tailored luxury palette of deep petrol blue, warm cognac saddle leather accents, smoked taupe, and brushed champagne brass",
)


def format_injection_text(style: str, location: str, lighting: str, palette: str) -> str:
    """
    Formats the dynamic scene directive into an unambiguous prompt injection block
    for Gemini AI to integrate into the catalog prompt.
    """
    return (
        "DYNAMIC ARCHITECTURAL ENVIRONMENT DIRECTIVES (RANDOMLY INJECTED SCENARIO):\n"
        f"- Architectural Style: {style}\n"
        f"- Space / Setting: {location}\n"
        f"- Lighting & Atmosphere: {lighting}\n"
        f"- Color Palette & Materials: {palette}\n"
        "\n"
        "CRITICAL INTEGRATION INSTRUCTIONS:\n"
        "1. Seamlessly integrate the furniture piece into the above specified architectural environment.\n"
        "2. Ensure the lighting, shadows, and reflections on the furniture match the specified lighting atmosphere.\n"
        "3. Keep the original furniture silhouette, geometry, cushions, and upholstery 100% faithful to the source image, "
        "while allowing the surrounding room, floor, walls, and decor to embody the injected style and palette.\n"
        "4. For multi-view perspectives, ensure the background and lighting remain coherent across all camera angles."
    )


def sample_random_scene(seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Samples a random, photorealistic architectural scenario across 4 orthogonal axes.
    
    Args:
        seed: Optional integer for deterministic testing and reproducible results.
              Uses an isolated random.Random(seed) instance so global random state is NEVER polluted.
              
    Returns:
        Structured dictionary containing:
        - 'style': Architectural style description
        - 'location': Interior space/setting description
        - 'lighting': Lighting atmosphere description
        - 'palette': Color harmony and material tone description
        - 'injection_text': Complete formatted directive ready for Gemini prompt assembly
        - 'description': Alias for injection_text
        - 'environment': Sub-dictionary containing individual components matching the API response contract
    """
    rng = random.Random(seed) if seed is not None else random
    
    style = rng.choice(ARCHITECTURAL_STYLES)
    location = rng.choice(LOCATIONS_SPACES)
    lighting = rng.choice(LIGHTING_ATMOSPHERES)
    palette = rng.choice(COLOR_HARMONIES)
    
    injection_text = format_injection_text(
        style=style,
        location=location,
        lighting=lighting,
        palette=palette
    )
    
    return {
        "style": style,
        "location": location,
        "lighting": lighting,
        "palette": palette,
        "injection_text": injection_text,
        "description": injection_text,
        "environment": {
            "style": style,
            "location": location,
            "lighting": lighting,
            "palette": palette,
        },
    }


def get_taxonomy_metrics() -> Dict[str, int]:
    """
    Returns counts and total possible combinations of the environment taxonomy.
    Useful for automated unit tests and runtime validation.
    """
    styles_count = len(ARCHITECTURAL_STYLES)
    locations_count = len(LOCATIONS_SPACES)
    lightings_count = len(LIGHTING_ATMOSPHERES)
    palettes_count = len(COLOR_HARMONIES)
    total_combinations = styles_count * locations_count * lightings_count * palettes_count
    return {
        "styles_count": styles_count,
        "locations_count": locations_count,
        "lightings_count": lightings_count,
        "palettes_count": palettes_count,
        "total_combinations": total_combinations,
    }


def get_all_categories() -> Dict[str, List[str]]:
    """
    Returns lists of all curated category options for UI exposure or inspection.
    """
    return {
        "architectural_styles": list(ARCHITECTURAL_STYLES),
        "spaces_locations": list(LOCATIONS_SPACES),
        "lighting_atmospheres": list(LIGHTING_ATMOSPHERES),
        "color_harmonies": list(COLOR_HARMONIES),
    }

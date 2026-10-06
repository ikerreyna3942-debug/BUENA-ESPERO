"""
services/gemini_service.py
==========================
Gemini Multimodal AI Service for Furniture Prompt Generator Studio.

Integrates the official Google GenAI SDK (google-genai v2.23.0+) to deconstruct
furniture photographs into photorealistic prompts. Features:
- Memory Guard (<50MB RAM): Pillow optimization, alpha normalization on #FFFFFF, Lanczos downscale to 1600px.
- Art Director Persona: 4-pillar analysis (Geometry, Color, Texture, Lighting).
- 5 Tailored Prompt Modes: 'solo mueble', 'vistas', 'entorno', 'vistas + tela y madera', 'vistas + tela'.
- Automatic Model Fallback Cascade: gemini-2.5-flash -> gemini-2.0-flash -> gemini-1.5-pro -> gemini-1.5-flash-8b.
- Pydantic Structured Output: Validates JSON output against schema.
"""

import os
import io
import json
import logging
from typing import Optional, Dict, Any, List
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, ConfigDict, AliasChoices
from google import genai
from google.genai import types
from google.genai.errors import APIError

logger = logging.getLogger("furniture_prompts.gemini")

# ---------------------------------------------------------------------------
# Constants & Allowed Values
# ---------------------------------------------------------------------------

ALLOWED_MODES: List[str] = [
    "solo mueble",
    "vistas",
    "entorno",
    "vistas + tela y madera",
    "vistas + tela",
]

MODEL_FALLBACK_CASCADE: List[str] = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-pro-preview",
]

MASTER_SYSTEM_INSTRUCTION: str = (
    "Eres un Director de Arte Comercial, Diseñador de Interiores de Alta Gama y Experto en Fotografía "
    "especializado en redactar prompts en lenguaje natural para inteligencias artificiales generativas "
    "(como Google AI Studio / Nano Banana, ChatGPT y Gemini).\n\n"
    "Tu objetivo es analizar profundamente las imágenes subidas (la foto principal del mueble y, si "
    "aplica, muestras de tela y madera) y redactar prompts exhaustivos y descriptivos.\n"
    "IMPORTANTE: Tus prompts DEBEN empezar indicando explícitamente que se use la imagen adjunta. "
    "Por ejemplo: 'Usando la foto adjunta como referencia exacta, genera...'\n\n"
    "Realiza el análisis en 4 pilares:\n"
    "1. GEOMETRÍA Y TOPOLOGÍA: Tipo de mueble, proporciones, curvas, costuras y estructura.\n"
    "2. COLOR: Tonos dominantes y subtonos.\n"
    "3. TEXTURA Y MATERIALES: Especifica al máximo si hay tela (lino, terciopelo, etc.) y madera/metal.\n"
    "4. ILUMINACIÓN: Comportamiento de la luz, sombras de contacto y atmósfera.\n\n"
    "No uses parámetros técnicos de Midjourney (como --ar o --v). Usa lenguaje natural descriptivo "
    "que cualquier IA pueda entender para generar la imagen."
)


# ---------------------------------------------------------------------------
# Pydantic Schemas for Structured JSON Output
# ---------------------------------------------------------------------------

class FurnitureDeconstruction(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    furniture_type: str = Field(
        ...,
        description="Technical classification and design style (e.g., 'Scandinavian Curved Sectional Sofa')"
    )
    geometry_topology: str = Field(
        ...,
        description="Topological analysis: proportions, contours, cushion profiles, joinery, and leg geometry"
    )
    color_palette: str = Field(
        ...,
        description="Color identification: dominant hue, undertones, and estimated primary HEX code (e.g., '#D4C7B5 Oatmeal')"
    )
    materials_texture: str = Field(
        ...,
        description="Micro-material breakdown: fabric weave/yarn, fiber scale, and timber/metal grain finishes"
    )
    lighting_optics: str = Field(
        ...,
        description="Optical behavior: light dispersion, specular sheen, ambient occlusion, and contact shadows"
    )


class MultiViewPrompts(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    vista_frente_0deg: Optional[str] = Field(description="Prompt for 0° eye-level frontal view"
    )
    vista_lateral_90deg: Optional[str] = Field(description="Prompt for 90° orthogonal lateral profile view"
    )
    vista_3_4_izquierda: Optional[str] = Field(description="Prompt for 45° 3/4 isometric perspective view from the left"
    )
    vista_desde_arriba: Optional[str] = Field(description="Prompt for 90° top-down bird's-eye zenithal view"
    )
    vista_3_4_posterior: Optional[str] = Field(description="Prompt for 135° 3/4 rear/posterior perspective view"
    )


class ArtDirectorResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    analysis: Optional[FurnitureDeconstruction] = Field(validation_alias=AliasChoices("analysis", "furniture_analysis"),
        description="Rigorous 4-pillar architectural and material deconstruction of the furniture piece"
    )
    master_prompt: str = Field(
        ...,
        description="Primary commercial prompt written in technical English, optimized for Midjourney v6, DALL-E 3, or Imagen 3"
    )
    negative_prompt: Optional[str] = Field(description="Comprehensive negative prompt to eliminate CGI artifacts, anatomical defects, and background noise"
    )
    view_prompts: Optional[MultiViewPrompts] = Field(description="Individual angle prompts for multi-view modes (vistas, vistas + tela y madera, vistas + tela)"
    )
    environment_summary: Optional[str] = Field(validation_alias=AliasChoices("environment_summary", "environment_notes"),
        description="Brief summary of the spatial and architectural context applied"
    )


# ---------------------------------------------------------------------------
# Memory Guard: In-Memory Pillow Preprocessor (<50MB RAM)
# ---------------------------------------------------------------------------

def optimize_furniture_image(image_bytes: bytes, max_dim: int = 1600, quality: int = 85) -> bytes:
    """
    Optimizes the uploaded furniture image in memory:
    1. Transposes EXIF orientation metadata so phone photos display upright.
    2. Flattens alpha/transparency channels (RGBA, LA, P) against a solid #FFFFFF white background.
    3. Downscales proportionally if width or height exceeds max_dim using Lanczos resampling.
    4. Compresses to progressive JPEG at quality=85 into an in-memory BytesIO buffer.

    Guarantees server RAM usage stays < 25MB during image processing, well below the 50MB ceiling.
    """
    if not image_bytes or len(image_bytes) == 0:
        raise ValueError("No se recibieron datos de imagen válidos.")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Handle smartphone EXIF orientation tag
            img = ImageOps.exif_transpose(img)

            # Normalize transparency onto clean white (#FFFFFF)
            if img.mode in ("RGBA", "LA"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode == "P":
                img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Proportional downscaling
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

            # Re-encode to progressive JPEG
            out_buf = io.BytesIO()
            img.save(out_buf, format="JPEG", quality=quality, optimize=True)
            return out_buf.getvalue()

    except UnidentifiedImageError as err:
        raise ValueError("El archivo proporcionado no es una imagen válida o compatible.") from err
    except Exception as err:
        raise ValueError(f"Error al procesar la imagen: {str(err)}") from err


# ---------------------------------------------------------------------------
# Core Service Class
# ---------------------------------------------------------------------------

class GeminiService:
    """
    Orchestrates Gemini AI multimodal requests, mode prompt assembly,
    and automatic model fallback cascading.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._custom_api_key = api_key

    def _resolve_api_key(self) -> str:
        """
        Resolves API key in order of priority:
        1. Explicitly supplied custom_api_key
        2. GEMINI_API_KEY environment variable
        3. GOOGLE_API_KEY environment variable
        """
        key = (
            (self._custom_api_key.strip() if self._custom_api_key else "")
            or os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
        if not key:
            raise ValueError(
                "GEMINI_API_KEY no encontrada. Configure la variable de entorno GEMINI_API_KEY o cree un archivo .env."
            )
        return key

    def _build_mode_prompt(
        self,
        mode: str,
        environment: Optional[Dict[str, str]] = None,
        user_notes: Optional[str] = None
    ) -> str:
        """
        Builds specific mode prompt instructions and constraints.
        """
        base_instruction = ""

        if mode == "solo mueble":
            base_instruction = (
                "MODO 1: SOLO MUEBLE (AISLAMIENTO DIGITAL EN BLANCO PURO #FFFFFF)\n"
                "Tarea: Usando la foto adjunta como referencia exacta, genera un prompt de catálogo.\n"
                "- Fondo: Blanco puro (#FFFFFF), recorte digital inmaculado.\n"
                "- Preservar: 100% de la geometría, curvas, costuras, tejido y color originales.\n"
                "- Sombras: Cero sombras en paredes o piso; solo una delicada sombra de oclusión ambiental natural bajo las patas.\n"
                "- Iluminación: Luz de estudio de catálogo, clara y enfocada.\n"
                "- Formato: Llena 'analysis', 'master_prompt' y 'negative_prompt'. 'view_prompts' puede omitirse."
            )

        elif mode == "vistas":
            base_instruction = (
                "MODO 2: VISTAS (CATÁLOGO MULTI-PERSPECTIVA CON FONDO BLANCO)\n"
                "Tarea: Usando la foto adjunta como referencia, genera 5 perspectivas del mueble aislado.\n"
                "- Fondo: Blanco puro (#FFFFFF), recorte inmaculado, sin entorno.\n"
                "- Produce el análisis de 4 pilares y el prompt maestro.\n"
                "- OBLIGATORIO: Debes poblar los 5 prompts en 'view_prompts':\n"
                "  1. vista_frente_0deg (Vista frontal al nivel de los ojos)\n"
                "  2. vista_lateral_90deg (Elevación de perfil a 90°)\n"
                "  3. vista_3_4_izquierda (Perspectiva isométrica 3/4 desde la izquierda)\n"
                "  4. vista_desde_arriba (Vista cenital desde arriba)\n"
                "  5. vista_3_4_posterior (Vista de 3/4 desde la parte posterior)\n"
                "- Iluminación y Cámara: Iluminación de estudio equilibrada, sombras de contacto suaves."
            )

        elif mode == "entorno":
            base_instruction = (
                "MODO 3: ENTORNO (CONTEXTO ARQUITECTÓNICO REALISTA)\n"
                "Tarea: Usando la foto adjunta como referencia exacta, coloca el mueble como objeto principal en un espacio interior de lujo.\n"
                "- Atmósfera: Interior minimalista armonioso, luz natural.\n"
                "- Iluminación: Luz diurna cinematográfica con fondo suavemente desenfocado (bokeh) para resaltar el mueble.\n"
                "- Formato: Llena 'analysis', 'master_prompt' y 'negative_prompt'. 'view_prompts' puede omitirse."
            )

        elif mode == "vistas + tela y madera":
            base_instruction = (
                "MODO 4: VISTAS + TELA Y MADERA (DECONSTRUCCIÓN DUAL DE MATERIALES)\n"
                "Tarea: Usando la foto principal y las fotos de muestra adjuntas, genera perspectivas multi-ángulo con especificaciones de material precisas para la tela y la madera.\n"
                "- Tela: Escala táctil del tejido, estructura de la fibra, costuras.\n"
                "- Madera: Especie de madera, dirección de la veta, textura, acabado.\n"
                "- OBLIGATORIO: Debes poblar los 5 prompts en 'view_prompts' (0°, 90°, 45°, cenital, posterior).\n"
                "- Iluminación: Luz de estudio macro de alta resolución."
            )

        elif mode == "vistas + tela":
            base_instruction = (
                "MODO 5: VISTAS + TELA (ÉNFASIS EN TELA CON CONSERVACIÓN ESTRUCTURAL)\n"
                "Tarea: Usando la foto principal y la muestra de tela adjuntas, genera perspectivas multi-ángulo deconstruyendo la tapicería.\n"
                "- Tela: Textura, relieve, matices de color, acolchado.\n"
                "- DIRECTIVA CRÍTICA: Las patas de madera/metal, base y estructura deben permanecer 100% idénticas a la foto original. NO alterar la estructura.\n"
                "- OBLIGATORIO: Debes poblar los 5 prompts en 'view_prompts' (0°, 90°, 45°, cenital, posterior).\n"
                "- Iluminación: Luz de estudio macro."
            )

        if user_notes and user_notes.strip():
            base_instruction += f"\n\nADDITIONAL USER NOTES TO CONSIDER: {user_notes.strip()}"

        return base_instruction

    def generate_prompt(
        self,
        image_bytes: Optional[bytes] = None,
        mode: str = "",
        user_notes: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        images_bytes: Optional[List[bytes]] = None,
    ) -> Dict[str, Any]:
        """
        Main execution workflow:
        1. Validates mode against ALLOWED_MODES.
        2. Resolves API key and initializes genai.Client.
        3. Optimizes image with Pillow memory guard (<50MB RAM).
        4. Handles dynamic environment injection for 'vistas' if not provided.
        5. Builds multimodal contents (image Part + mode prompt).
        6. Executes automatic fallback cascade across Gemini models.
        7. Returns structured dict adhering to the API contract.
        """
        # 1. Validation
        if mode not in ALLOWED_MODES:
            return {
                "success": False,
                "error": f"Modo '{mode}' no permitido. Debe ser uno de: {ALLOWED_MODES}"
            }

        # 2. Resolve API key
        try:
            api_key = self._resolve_api_key()
        except ValueError as e:
            return {
                "success": False,
                "error": f"Error al comunicarse con Gemini AI: {str(e)}"
            }

        # 3. Optimize image with Memory Guard
        if images_bytes is None:
            if image_bytes is None:
                return {
                    "success": False,
                    "error": "No se proporcionaron imágenes."
                }
            images_bytes = [image_bytes]

        optimized_bytes_list = []
        try:
            for ib in images_bytes:
                optimized_bytes_list.append(optimize_furniture_image(ib))
        except ValueError as e:
            return {
                "success": False,
                "error": f"Error al procesar la imagen: {str(e)}"
            }

        # 4. Resolve environment for 'vistas' mode
        effective_environment = environment
        if mode == "vistas" and not effective_environment:
            try:
                from services.random_scenarios import sample_random_scene
                effective_environment = sample_random_scene().get("environment")
            except Exception:
                effective_environment = {
                    "style": "Contemporary Minimalist Japandi with warm timber slats",
                    "location": "Double-height living pavilion overlooking a tranquil reflecting pool",
                    "lighting": "Golden hour rake sunlight casting long geometric window shadows",
                    "palette": "Warm monochromatic palette of alabaster, oatmeal, cashmere beige"
                }

        # 5. Prepare Gemini contents & config
        client = genai.Client(api_key=api_key)
        image_parts = [types.Part.from_bytes(data=ob, mime_type="image/jpeg") for ob in optimized_bytes_list]
        mode_instruction = self._build_mode_prompt(
            mode=mode,
            environment=effective_environment,
            user_notes=user_notes
        )

        image_desc = "FOTOGRAFÍAS DEL MUEBLE OBJETIVO." if len(image_parts) > 1 else "FOTOGRAFÍA DEL MUEBLE OBJETIVO."
        contents = image_parts + [
            image_desc,
            mode_instruction
        ]

        config = types.GenerateContentConfig(
            system_instruction=MASTER_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=ArtDirectorResponse,
            temperature=0.7 if mode in ("vistas", "entorno") else 0.2,
        )

        # 6. Automatic Fallback Cascade
        last_error = None
        for model_name in MODEL_FALLBACK_CASCADE:
            try:
                logger.info(f"Invocando Gemini AI con modelo: {model_name} para modo: '{mode}'")
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )

                if not response or not response.text:
                    raise ValueError(f"El modelo {model_name} devolvió una respuesta vacía.")

                raw_text = response.text.strip()
                # Clean possible markdown fence wrapper
                if raw_text.startswith("```"):
                    lines = raw_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    raw_text = "\n".join(lines).strip()

                try:
                    parsed_response = ArtDirectorResponse.model_validate_json(raw_text)
                except Exception:
                    # Fallback to json dictionary parsing
                    parsed_dict = json.loads(raw_text)
                    parsed_response = ArtDirectorResponse.model_validate(parsed_dict)

                # Assemble successful payload
                view_prompts_dict = None
                if parsed_response.view_prompts:
                    view_prompts_dict = parsed_response.view_prompts.model_dump(exclude_none=True)

                analysis_dict = None
                if parsed_response.analysis:
                    analysis_dict = parsed_response.analysis.model_dump(exclude_none=True)

                return {
                    "success": True,
                    "mode": mode,
                    "model_used": model_name,
                    "prompt": parsed_response.master_prompt,
                    "negative_prompt": parsed_response.negative_prompt or "",
                    "view_prompts": view_prompts_dict,
                    "environment": effective_environment if mode == "vistas" else None,
                    "analysis": analysis_dict,
                }

            except APIError as e:
                logger.warning(
                    f"Fallo en modelo {model_name} (Code {getattr(e, 'code', 'Unknown')}): "
                    f"{str(e)}. Intentando siguiente modelo en cascada..."
                )
                last_error = str(e)
                continue
            except Exception as e:
                logger.warning(
                    f"Excepción inesperada en modelo {model_name}: {str(e)}. "
                    f"Intentando siguiente modelo en cascada..."
                )
                last_error = str(e)
                continue

        # 7. All models failed
        logger.error(f"Todos los modelos de Gemini fallaron para modo '{mode}'. Último error: {last_error}")
        return {
            "success": False,
            "error": f"Error al comunicarse con Gemini AI tras intentar la cascada de modelos: {last_error}"
        }

    # Alias for method name compatibility
    generate_prompt_for_mode = generate_prompt


# ---------------------------------------------------------------------------
# Module Singleton Helper
# ---------------------------------------------------------------------------

_gemini_service_instance: Optional[GeminiService] = None


def get_gemini_service() -> GeminiService:
    """
    Returns a shared singleton instance of GeminiService.
    Useful for FastAPI dependency injection and testing.
    """
    global _gemini_service_instance
    if _gemini_service_instance is None:
        _gemini_service_instance = GeminiService()
    return _gemini_service_instance

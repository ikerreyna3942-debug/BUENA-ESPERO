import os
import io
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from PIL import Image
from pydantic import BaseModel, Field

# Modelos Pydantic para Structured Outputs Avanzados
class MaterialAnalysisV5(BaseModel):
    name: str = Field(description="Nombre comercial corto y premium (ej. Heathered Salt-and-Pepper Bouclé)")
    color_description: str = Field(description="Descripción cromática exacta (RGB/Hex conceptual, tono exacto y subtonos)")
    texture_detail: str = Field(description="Estructura micro-textil (ej. dense nubby loops over cool grey under-weave)")
    light_interaction: str = Field(description="Cómo interactúa con la luz (ej. absorbs light, highly reflective, matte satin sheen)")

class FurnitureAnalysisV5(BaseModel):
    furniture_item: str = Field(description="Nombre y estilo arquitectónico (ej. mid-century modern curved modular sofa)")
    camera_angle: str = Field(description="Ángulo de cámara en grados y perspectiva geométrica (ej. 45-degree elevated isometric, strict 0-degree frontal)")
    lighting_direction: str = Field(description="Dirección exacta de la luz y tipo de sombra (ej. Key light from top-left, soft diffuse fill)")
    geometric_structure: str = Field(description="Descripción topológica de la forma (ej. sharp 90-degree corners, sweeping organic curves)")
    existing_materials: str = Field(description="Tapicería y partes rígidas actuales con su color y textura exacta")

class AIPromptServiceV5:
    def __init__(self):
        self.default_api_key = os.getenv("GEMINI_API_KEY", "").strip()

    def get_api_key(self, custom_key: Optional[str] = None) -> str:
        if custom_key and custom_key.strip():
            return custom_key.strip()
        try:
            import streamlit as st
            if "GEMINI_API_KEY" in st.secrets:
                return st.secrets["GEMINI_API_KEY"].strip()
        except Exception:
            pass
        return os.getenv("GEMINI_API_KEY", self.default_api_key).strip()

    def _call_gemini(self, client, contents, config=None):
        """Llama a Gemini con lista de modelos activos y fallback automático."""
        models_to_try = [
            "gemini-flash-latest",
            "gemini-2.5-flash",
            "gemini-flash-lite-latest",
            "gemini-3-flash-preview",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]
        last_err = None
        for m in models_to_try:
            try:
                return client.models.generate_content(model=m, contents=contents, config=config)
            except Exception as e:
                last_err = e
                continue
        raise last_err if last_err else RuntimeError("No se pudo conectar con Gemini API")

    def _prepare_image(self, img_bytes: bytes, max_dim: int = 800) -> Image.Image:
        """Optimiza y redimensiona imágenes para envío ultra-rápido a Gemini."""
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        return img

    def analyze_material(self, sample_bytes: bytes, api_key: Optional[str] = None, material_type: str = "auto") -> Dict[str, Any]:
        key = self.get_api_key(api_key)
        if not key:
            return MaterialAnalysisV5(
                name=f"Premium Material ({material_type})",
                color_description="true neutral color",
                texture_detail="ultra-detailed high-res texture",
                light_interaction="matte finish"
            ).model_dump()
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            img = self._prepare_image(sample_bytes)
            
            prompt = f"""You are an expert materials engineer and luxury product photographer.
Analyze this material sample ({material_type}) with microscopic precision.
Pay special attention to how light hits the threads/wood grain, color saturation, weave pattern, and exact tones."""
            
            res = self._call_gemini(
                client=client,
                contents=[prompt, img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MaterialAnalysisV5,
                    temperature=0.1
                )
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"[AIPromptServiceV5] Error analyzing material: {e}")
            return MaterialAnalysisV5(
                name=f"Fallback Material ({material_type})",
                color_description="detected color",
                texture_detail="detected texture",
                light_interaction="satin"
            ).model_dump()

    def analyze_furniture_for_enhancement(self, furniture_bytes, api_key: Optional[str] = None) -> Dict[str, Any]:
        key = self.get_api_key(api_key)
        if not key:
            return FurnitureAnalysisV5(
                furniture_item="furniture product",
                camera_angle="original camera angle",
                lighting_direction="soft studio lighting",
                geometric_structure="original geometry",
                existing_materials="original materials"
            ).model_dump()
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            prompt = """You are an expert architectural visualizer and commercial photographer.
Analyze this furniture image mathematically. Identify the exact camera angle, lighting direction, and 3D topology of the object. 
CRITICAL: You MUST accurately describe the EXACT color (name, shade, and hex estimate) and texture of the upholstery in the 'existing_materials' field."""
            
            contents = [prompt]
            if isinstance(furniture_bytes, list):
                for fb in furniture_bytes:
                    contents.append(self._prepare_image(fb))
            else:
                contents.append(self._prepare_image(furniture_bytes))
                
            res = self._call_gemini(
                client=client,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FurnitureAnalysisV5,
                    temperature=0.1
                )
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"[AIPromptServiceV5] Error analyzing furniture: {e}")
            return FurnitureAnalysisV5(
                furniture_item="furniture piece",
                camera_angle="original perspective",
                lighting_direction="original lighting",
                geometric_structure="original shape",
                existing_materials="original fabric and wood"
            ).model_dump()

    def _build_photo_hardware_str(self) -> str:
        return "Shot on Hasselblad H6D-100c medium format, 120mm macro lens, f/11 aperture for maximum sharp depth of field, 8k resolution, raw hyper-realistic commercial catalog photography, focus stacking, crisp architectural clarity."

    def _build_white_isolation_str(self) -> str:
        return "ENVIRONMENT: Isolate the furniture piece on a pure seamless solid white background (#FFFFFF), with zero floor shadows, no drop shadows, and no harsh reflections. CRITICAL: DO NOT include any text, typography, watermark, letters, numbers, color chips, or palettes."

    def generate_individual_perspectives_v5(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Genera los 5 PROMPTS INDIVIDUALES para generar 5 FOTOS SEPARADAS (1 foto por ángulo):
        1. 3/4 Isométrica mirando a la derecha
        2. Lateral estricta (90°)
        3. Frontal directa (0°)
        4. 3/4 Picada alta / semi-arriba (60°-70°)
        5. Cenital superior (90° desde arriba)
        """
        ma = furniture_analysis or {}
        furn_item = ma.get("furniture_item", furniture_name)
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials")
        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()

        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""
===================================================================
⚡ MANDATORY USER CUSTOM DIRECTIVES (HIGHEST PRIORITY):
{user_notes_clean}
* Strictly incorporate every detail requested above without exceptions.
==================================================================="""
        else:
            user_directives_block = ""

        vistas_specs = [
            {
                "id": "vista_1_3_4_derecha",
                "label": "Vista 1: 3/4 Isométrica (Mirando a la Derecha)",
                "icon": "📐",
                "angle_desc": "3/4 isometric perspective at a 45-degree angle, with the furniture facing toward the right. Elevated 15 degrees to display depth, front-right profile, seat cushions, and leg construction clearly.",
                "dalle_angle": "3/4 isometric angle looking towards the right side at 45 degrees, slightly elevated."
            },
            {
                "id": "vista_2_lateral",
                "label": "Vista 2: Perfil Lateral Estricto (90°)",
                "icon": "➡️",
                "angle_desc": "Strict 90-degree orthogonal lateral side profile view. Full silhouette from front edge to back edge with zero perspective vanishing points.",
                "dalle_angle": "Pure 90-degree side profile orthogonal view, perfectly flat side elevation."
            },
            {
                "id": "vista_3_frente",
                "label": "Vista 3: Elevación Frontal Directa (0°)",
                "icon": "🖼️",
                "angle_desc": "Direct flat 0-degree front elevation view. Camera placed directly in front of the furniture at exact center-line eye level, zero perspective vanishing distortion.",
                "dalle_angle": "Direct flat front view at 0 degrees, pure eye-level frontal elevation."
            },
            {
                "id": "vista_4_3_4_arriba",
                "label": "Vista 4: 3/4 Picada Alta Semi-Cenital (60°-70°)",
                "icon": "🔍",
                "angle_desc": "High-angle elevated 3/4 semi-top perspective shot at 60 to 70 degrees looking down at the front. Clearly displays top surface/cushion depth while preserving front silhouette and legs.",
                "dalle_angle": "Elevated 3/4 high-angle shot from above at 65 degrees looking down at the front."
            },
            {
                "id": "vista_5_cenital",
                "label": "Vista 5: Cenital Superior Directo (90° desde arriba)",
                "icon": "🔝",
                "angle_desc": "Direct 90-degree top-down cenital bird's-eye view. Camera positioned directly overhead pointing straight down. Shows pure geometric top footprint and proportions.",
                "dalle_angle": "Direct 90-degree bird's-eye top-down view pointing straight down from above."
            }
        ]

        results = []
        for v in vistas_specs:
            # Prompt para Google AI Studio / Gemini (1 sola foto individual)
            prompt_ai_studio = f"""SYSTEM: You are a World-Class Master Commercial Product Photographer and AI Visual Director.
IMAGE IDENTIFICATION:
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
{user_directives_block}

TASK: Generate ONE SINGLE INDIVIDUAL COMMERCIAL CATALOG PHOTOGRAPH of the target furniture item ({furn_item}), isolated as a single object centered in the frame. DO NOT generate multiple items, do not generate a collage, do not generate a contact sheet. Only ONE single standalone furniture piece.

MANDATORY CAMERA PERSPECTIVE:
- {v['angle_desc']}

MATERIAL & GEOMETRIC FIDELITY:
- 100% exact original upholstery color, textile weave, and wooden/metal finishes from TARGET FURNITURE: [{existing_mats}].
- Topology & Geometry: {geom_struct}.

{white_bg}
HARDWARE & RENDERING:
{hardware_str}
{"USER SPECIFIC OVERRIDES: " + user_notes_clean if user_notes_clean else ""}

Negative Prompt: collage, contact sheet, multiple views, multiple furniture pieces, grid, split screen, side-by-side, CGI, 3D render, cartoon, plastic, floor shadows, grey backdrop, room, text, watermark."""

            # Prompt para ChatGPT / DALL-E 3 (1 sola foto individual)
            prompt_dalle = f"""[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography, Real-world textile micro-imperfections]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ONE single standalone commercial catalog photo of a {furn_item} ('{furniture_name}'), exact original materials preserved ({existing_mats}).
Camera Angle: {v['dalle_angle']}
CRITICAL: Only 1 single furniture object centered in the image. No multiple angles, no contact sheet, no collage.
Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}"""

            results.append({
                "id": v["id"],
                "label": v["label"],
                "icon": v["icon"],
                "google_ai_studio": prompt_ai_studio,
                "chatgpt_dalle3": prompt_dalle
            })

        return results

    def generate_vistas_2_1_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> Dict[str, Any]:
        """
        Genera los prompts para el set 'Vistas (2.1)' con las 4 vistas canónicas exactas de catálogo:
        1. Frontal Directa (0°)
        2. 3/4 en Perspectiva (45°)
        3. Lateral Estricta (90°)
        4. Vista Superior / Cenital (Top-Down)
        """
        ma = furniture_analysis or {}
        furn_item = ma.get("furniture_item", furniture_name)
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials")
        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()

        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""
===================================================================
⚡ MANDATORY USER CUSTOM DIRECTIVES (HIGHEST PRIORITY):
{user_notes_clean}
* Strictly incorporate every detail requested above without exceptions.
==================================================================="""
        else:
            user_directives_block = ""

        vistas_2_1_specs = [
            {
                "id": "vista_2_1_frontal",
                "label": "Vista 1: Frontal Directa (0°)",
                "icon": "🖼️",
                "angle_desc": "Direct flat 0-degree frontal elevation view. Camera placed directly in front of the furniture piece at eye-level center. Zero perspective tilt, pure architectural straight-on view displaying the full front facade, drawer faces, integrated accent lighting if present, and base support.",
                "dalle_angle": "Pure direct 0-degree straight-on front elevation view, eye-level, perfectly centered."
            },
            {
                "id": "vista_2_1_tres_cuartos",
                "label": "Vista 2: 3/4 en Perspectiva (45°)",
                "icon": "📐",
                "angle_desc": "Classic commercial 3/4 perspective view shot at a 45-degree angle. Camera positioned at slight eye-level elevation to simultaneously capture front drawers, side profile depth, cantilevered architecture, and top surface edge.",
                "dalle_angle": "Commercial 3/4 perspective shot at 45 degrees, revealing front facade and side depth with natural shadow drop."
            },
            {
                "id": "vista_2_1_lateral",
                "label": "Vista 3: Lateral Estricta (90°)",
                "icon": "➡️",
                "angle_desc": "Strict 90-degree orthogonal side profile elevation. Perfectly flat side view capturing the exact vertical silhouette, thickness of panels, open shelf cavity, and bottom base footprint with zero perspective convergence.",
                "dalle_angle": "Strict 90-degree side profile orthogonal view, perfectly flat lateral elevation."
            },
            {
                "id": "vista_2_1_superior_cenital",
                "label": "Vista 4: Superior Cenital (Top-Down)",
                "icon": "🔝",
                "angle_desc": "High-angle top-down cenital perspective view looking directly down from above. Captures the rich wood grain on the entire top flat surface, rounded corner radii, and lower protruding shelf structure with its ambient warm glow.",
                "dalle_angle": "Direct high-angle top-down shot from above, showcasing top wood surface grain and lower shelf footprint."
            }
        ]

        individual_results = []
        for v in vistas_2_1_specs:
            # Prompt individual para Google AI Studio (Nano Banana 2.1 & Pro)
            prompt_ais = f"""SYSTEM: You are a World-Class Master Commercial Product Photographer and AI Visual Director.
IMAGE IDENTIFICATION:
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
{user_directives_block}

TASK: Generate ONE SINGLE INDIVIDUAL COMMERCIAL CATALOG PHOTOGRAPH of the target furniture item ({furn_item}), isolated as a single object centered in the frame. DO NOT generate multiple items, do not generate a collage, do not generate a contact sheet. Only ONE single standalone furniture piece.

MANDATORY CAMERA PERSPECTIVE:
- {v['angle_desc']}

MATERIAL & GEOMETRIC FIDELITY:
- 100% exact original wood grain flow, joinery details, warm integrated LED channels (if visible), and finish from TARGET FURNITURE: [{existing_mats}].
- Topology & Geometry: {geom_struct}.

{white_bg}
HARDWARE & RENDERING:
{hardware_str}
{"USER SPECIFIC OVERRIDES: " + user_notes_clean if user_notes_clean else ""}

Negative Prompt: collage, contact sheet, multiple views, multiple furniture pieces, grid, split screen, side-by-side, CGI, 3D render, cartoon, plastic, floor shadows, grey backdrop, room, text, watermark."""

            # Prompt individual para ChatGPT / DALL-E 3
            prompt_dal = f"""[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography, Real-world timber micro-imperfections]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ONE single standalone commercial catalog photo of a {furn_item} ('{furniture_name}'), exact original materials preserved ({existing_mats}).
Camera Angle: {v['dalle_angle']}
CRITICAL: Only 1 single furniture object centered in the image. No multiple angles, no contact sheet, no collage.
Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}"""

            individual_results.append({
                "id": v["id"],
                "label": v["label"],
                "icon": v["icon"],
                "google_ai_studio": prompt_ais,
                "chatgpt_dalle3": prompt_dal
            })

        # Prompt maestro unificado para Vistas (2.1)
        prompt_maestro_ais = f"""SYSTEM: You are a World-Class Master Commercial Product Photographer and AI Visual Director.
IMAGE IDENTIFICATION:
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
{user_directives_block}

TASK: Generate ALL 4 CANONICAL COMMERCIAL CATALOG VIEWS of the target furniture item ({furn_item}) in a single ultra-high-definition multi-angle master render / contact grid:
1. VIEW 1 - DIRECT FLAT FRONT ELEVATION (0° front view).
2. VIEW 2 - 3/4 PERSPECTIVE VIEW (45° angle showing front and side depth).
3. VIEW 3 - STRICT ORTHOGONAL LATERAL PROFILE (90° side elevation).
4. VIEW 4 - HIGH-ANGLE TOP-DOWN CENITAL VIEW (overhead view showing top surface and bottom base).

MATERIAL APPLICATION:
- Maintain 100% exact original materials, wood tone, grain structure, and warm ambient LED glow from TARGET FURNITURE: [{existing_mats}].
- Topology & Geometry: {geom_struct}.

{white_bg}
HARDWARE & RENDERING:
{hardware_str}
{"USER SPECIFIC OVERRIDES: " + user_notes_clean if user_notes_clean else ""}

Negative Prompt: CGI, 3D render, cartoon, plastic, floor shadows, grey backdrop, room reflections, clutter, text, letters, numbers, watermark."""

        prompt_maestro_dal = f"""[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate a hyper-realistic commercial furniture catalog multi-view contact sheet displaying the 4 CANONICAL ANGLES of a {furn_item} ('{furniture_name}'):
1. Front View (0° flat elevation).
2. 3/4 Perspective View (45° depth angle).
3. Side View (90° orthogonal profile).
4. Top-Down Cenital View (overhead angle).
Topological Geometry: {geom_struct}. Exact materials: {existing_mats}.
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows."""

        return {
            "google_ai_studio": prompt_maestro_ais,
            "chatgpt_dalle3": prompt_maestro_dal,
            "midjourney_v6": f"Commercial catalog 4-view sheet of {furn_item}, {geom_struct}, white background #FFFFFF --ar 16:9 --v 6.1 --style raw",
            "individual_vistas": individual_results
        }

    def generate_all_in_one_multi_view_prompt(
        self,
        mode: str,
        furniture_name: str,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> Dict[str, Any]:
        """
        Genera tanto los 5 PROMPTS INDIVIDUALES (fotos separadas) como el PROMPT MAESTRO COMBINADO.
        """
        fa = fabric_analysis or {}
        wa = wood_analysis or {}
        ma = furniture_analysis or {}
        
        f_name = fa.get("name", "Fabric")
        f_color = fa.get("color_description", "")
        f_texture = fa.get("texture_detail", "")
        f_light = fa.get("light_interaction", "")
        
        w_name = wa.get("name", "Wood")
        w_color = wa.get("color_description", "")
        w_texture = wa.get("texture_detail", "")
        w_light = wa.get("light_interaction", "")

        furn_item = ma.get("furniture_item", furniture_name)
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials")

        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()

        # Directivas de usuario fuertemente integradas
        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""
===================================================================
⚡ MANDATORY USER CUSTOM DIRECTIVES (HIGHEST PRIORITY):
{user_notes_clean}
* Strictly incorporate every detail requested above without exceptions.
==================================================================="""
        else:
            user_directives_block = ""

        # Definición de materiales según el modo
        if mode == "dual":
            mat_instruction = f"""- UPHOLSTERY FABRIC: Meticulously apply the exact material from FABRIC SWATCH ('{f_name}'). Color tone & shade: {f_color}. Weave pattern & micro-texture: {f_texture}. Light interaction: {f_light}. Texture scale: 98% reduced for macroscopic ultra-high fidelity realism. Zero chromatic drift.
- WOOD COMPONENTS: Apply the exact material from WOOD SAMPLE ('{w_name}'). Wood tone & color: {w_color}. Grain structure & pores: {w_texture}. Sheen: {w_light}. Ensure natural anatomical grain flow along legs, armrests, and base frames."""
            order_independent_block = f"""IMAGE IDENTIFICATION (Order-Independent):
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
- FABRIC SWATCH: Locate the image containing the fabric swatch ('{f_name}').
- WOOD SAMPLE: Locate the image containing the wood texture sample ('{w_name}')."""
            mat_summary = f"upholstered in {f_name} ({f_color}, {f_texture}) and base/legs carved from {w_name} ({w_color}, {w_texture})"

        elif mode == "fabric_only":
            mat_instruction = f"""- UPHOLSTERY FABRIC: Meticulously apply the exact material from FABRIC SWATCH ('{f_name}'). Color tone: {f_color}. Weave: {f_texture}. Light interaction: {f_light}. Scale down texture 98% for macro realism. Lock exact hue.
- WOOD / METAL BASE: Strictly preserve the original legs, frame, and non-upholstered parts exactly as shown in the TARGET FURNITURE reference."""
            order_independent_block = f"""IMAGE IDENTIFICATION (Order-Independent):
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
- FABRIC SWATCH: Locate the image containing the fabric swatch ('{f_name}')."""
            mat_summary = f"upholstered in {f_name} ({f_color}, {f_texture}), original wooden/metal legs preserved"

        elif mode == "wood_only":
            mat_instruction = f"""- WOOD COMPONENTS: Apply the exact material from WOOD SAMPLE ('{w_name}'). Tone: {w_color}. Grain: {w_texture}. Sheen: {w_light}. Anatomical grain flow.
- UPHOLSTERY FABRIC: Strictly preserve the original fabric upholstery, cushions, and seams exactly as shown in the TARGET FURNITURE reference ({existing_mats})."""
            order_independent_block = f"""IMAGE IDENTIFICATION (Order-Independent):
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
- WOOD SAMPLE: Locate the image containing the wood texture sample ('{w_name}')."""
            mat_summary = f"original upholstery preserved, wooden components replaced with {w_name} ({w_color}, {w_texture})"

        else: # solo_mueble / original
            mat_instruction = f"""- ORIGINAL FIDELITY: Maintain 100% exact original upholstery color, textile weave, and wooden/metal finishes from the TARGET FURNITURE reference: [{existing_mats}]. Zero alteration to materials or tones."""
            order_independent_block = f"""IMAGE IDENTIFICATION (Order-Independent):
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}')."""
            mat_summary = f"exact original materials preserved ({existing_mats})"

        # PROMPT COMBINADO 1: GOOGLE AI STUDIO / GEMINI (Hoja de contacto multi-ángulo)
        prompt_ai_studio = f"""SYSTEM: You are a World-Class Master Commercial Product Photographer and AI Visual Director.
{order_independent_block}
{user_directives_block}

TASK: Generate ALL 5 CANONICAL COMMERCIAL CATALOG VIEWS of the target furniture item ({furn_item}) in a single ultra-high-definition multi-angle master render / contact grid, maintaining 100% structural topology ({geom_struct}) and 100% material fidelity across all angles.

CANONICAL PERSPECTIVES REQUIRED (Render all 5 distinct camera angles):
1. VIEW 1 - 3/4 ISOMETRIC PERSPECTIVE FACING RIGHT:
   - Classic commercial 3/4 angle viewed at 45 degrees, object facing toward the right. Elevated 15 degrees to clearly reveal depth, seat cushion thickness, side contours, and front-right armrest.
2. VIEW 2 - STRICT ORTHOGONAL LATERAL PROFILE (SIDE VIEW):
   - Strict 90-degree lateral side view. Full silhouette profile from front edge to back edge with zero perspective vanishing points.
3. VIEW 3 - DIRECT FLAT FRONT ELEVATION (0-DEGREE FRONT VIEW):
   - Camera perfectly level at eye-line, pointing dead-center at the front of the furniture. Zero perspective distortion, pure architectural 2D-style frontal elevation.
4. VIEW 4 - HIGH-ANGLE ELEVATED SEMI-TOP PERSPECTIVE (3/4 PICADA ALTA):
   - Elevated camera angle at approximately 60 to 70 degrees looking down at the front of the furniture. Shows the top seat cushion geometry and depth while maintaining clear visibility of the front elevation, front legs, and silhouette.
5. VIEW 5 - DIRECT TOP-DOWN CENITAL BIRD'S-EYE VIEW (90-DEGREE TOP VIEW):
   - Camera positioned directly above looking straight down at 90 degrees. True geometric top footprint, showing cushion layout and proportions from above.

MATERIAL APPLICATION:
{mat_instruction}

{white_bg}
HARDWARE & RENDERING:
{hardware_str}
{"USER SPECIFIC OVERRIDES: " + user_notes_clean if user_notes_clean else ""}

Negative Prompt: CGI, 3D render, cartoon, plastic, generic fabric, loss of weave texture, suede, velvet, leather, color drift, shifted hue, distorted geometry, warped proportions, missing legs, floor shadows, grey backdrop, room reflections, clutter, text, letters, numbers, watermark, labels."""

        # PROMPT COMBINADO 2: CHATGPT (DALL-E 3)
        dalle_defense = "[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography, Real-world textile micro-imperfections]"
        dalle_shadows = "[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]"

        prompt_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a hyper-realistic commercial furniture catalog multi-view contact sheet displaying ALL 5 CANONICAL ANGLES of a {furn_item} ('{furniture_name}'), {mat_summary}.
{user_directives_block if user_notes_clean else ""}
Topological Geometry: {geom_struct}.

THE 5 REQUIRED PERSPECTIVES IN A SINGLE COMPREHENSIVE COMPOSITION:
1. 3/4 Isometric Perspective Facing Right (45° angle, elevated 15°).
2. Strict Lateral Side Profile (90° orthogonal side view).
3. Direct Front View (0° flat frontal elevation).
4. High-Angle Semi-Top Perspective (60°-70° elevated front view showing top depth and front legs).
5. Direct Top-Down Cenital View (90° bird's-eye footprint from above).

Materials & Finish:
{mat_instruction}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}"""

        # PROMPT COMBINADO 3: MIDJOURNEY V6.1
        prompt_mj = f"""Commercial luxury furniture catalog multi-angle sheet, 5 comprehensive views (3/4 right view, orthogonal side profile, direct front elevation, high-angle semi-top 3/4 view, top-down bird's-eye view) of a {furn_item}, {geom_struct}. {mat_summary}. Pure seamless solid white background #FFFFFF, {hardware_str} {("DIRECTIVES: " + user_notes_clean) if user_notes_clean else ""} --no floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic, text, watermark --ar 16:9 --v 6.1 --style raw --c 5"""

        individual_vistas = self.generate_individual_perspectives_v5(
            furniture_name=furniture_name,
            furniture_analysis=furniture_analysis,
            notas_usuario=notas_usuario
        )

        return {
            "google_ai_studio": prompt_ai_studio,
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_mj,
            "individual_vistas": individual_vistas
        }

ai_prompt_service_v5 = AIPromptServiceV5()

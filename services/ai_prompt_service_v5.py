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
    existing_materials: str = Field(description="Tapicería y partes rígidas actuales con su color y textura exacta, veta de madera y tonos")

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

    def analyze_furniture_for_enhancement(
        self, 
        furniture_bytes, 
        reference_bytes: Optional[List[bytes]] = None, 
        notas_usuario: str = "",
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analiza conjuntamente la foto actual del mueble, las fotos de referencia (vistas y geometría 360°)
        y las notas obligatorias del usuario.
        """
        key = self.get_api_key(api_key)
        if not key:
            notes_desc = f" with adjustments: {notas_usuario.strip()}" if notas_usuario else ""
            return FurnitureAnalysisV5(
                furniture_item="furniture product" + notes_desc,
                camera_angle="original camera angle",
                lighting_direction="soft studio lighting",
                geometric_structure="original geometry and 360 reference topology",
                existing_materials="original materials and wood finish"
            ).model_dump()
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            prompt = """You are an expert architectural visualizer, 3D furniture engineer, and commercial photographer.
Analyze all provided images to deconstruct the furniture piece completely:
1. Identify the furniture type, style, exact proportions, joinery, and 3D silhouette.
2. Cross-reference the CURRENT TAKEN PHOTO with the REFERENCE PHOTOS (which show the design angles, views, and details).
3. Identify the EXACT materials: wood tone/finish/species, fabric weave and color (estimate hex code and natural color name).
4. MANDATORY USER NOTES: You MUST prioritize any explicit notes provided by the user below."""
            
            if notas_usuario and notas_usuario.strip():
                prompt += f"\n\nUSER MANDATORY DIRECTIVES (STRICT OVERRIDE):\n{notas_usuario.strip()}"
            
            contents = [prompt]
            
            # Agregar fotos actuales
            if isinstance(furniture_bytes, list):
                for fb in furniture_bytes:
                    if fb:
                        contents.append(self._prepare_image(fb))
            elif furniture_bytes:
                contents.append(self._prepare_image(furniture_bytes))
                
            # Agregar fotos de referencia
            if reference_bytes and isinstance(reference_bytes, list):
                for rb in reference_bytes:
                    if rb:
                        contents.append(self._prepare_image(rb))
                
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
            notes_desc = f" with directives: {notas_usuario.strip()}" if notas_usuario else ""
            return FurnitureAnalysisV5(
                furniture_item="furniture piece" + notes_desc,
                camera_angle="original perspective",
                lighting_direction="original lighting",
                geometric_structure="original shape and 360-degree reference structure",
                existing_materials="original fabric and wood finish"
            ).model_dump()

    def _build_photo_hardware_str(self) -> str:
        return "Shot on Hasselblad H6D-100c medium format, 120mm macro lens, f/11 aperture for maximum sharp depth of field, 8k resolution, raw hyper-realistic commercial catalog photography, focus stacking, crisp architectural clarity."

    def _build_white_isolation_str(self) -> str:
        return "ENVIRONMENT: Isolate the furniture piece on a pure seamless solid white background (#FFFFFF), with zero floor shadows, no drop shadows, and no harsh reflections. CRITICAL: DO NOT include any text, typography, watermark, letters, numbers, color chips, or palettes."

    def generate_vistas_1_1_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> Dict[str, Any]:
        """
        Genera el set 'Vistas (1.1)' con las 5 vistas canónicas completas:
        1. 3/4 Isométrica mirando a la derecha (45°, elevación 15°)
        2. Lateral estricta (90°)
        3. Frontal directa (0°)
        4. 3/4 Picada alta / semi-arriba (60°-70°)
        5. Cenital superior (90° desde arriba)
        
        Optimizado para:
        - Google AI Studio (Nano Banana): Protocolo secuencial paso a paso con la palabra clave 'foto'.
        - ChatGPT (DALL-E 3): Generación secuencial completa de todas las fotos.
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
⚡ MANDATORY USER CUSTOM DIRECTIVES (EMBEDDED ARCHITECTURAL & MATERIAL OVERRIDES):
{user_notes_clean}
* Strictest adherence required: Ensure every specification, color, material change, and detail above is natively integrated into each view render without exceptions.
==================================================================="""
            materials_with_notes = f"{existing_mats} (User mandatory note applied: {user_notes_clean})"
        else:
            user_directives_block = ""
            materials_with_notes = existing_mats

        vistas_specs = [
            {
                "id": "vista_1_3_4_derecha",
                "label": "Vista 1: 3/4 Isométrica (Mirando a la Derecha)",
                "short_name": "3/4 Isométrica Derecha",
                "icon": "📐",
                "angle_desc": "3/4 isometric perspective at a 45-degree angle, with the furniture facing toward the right. Elevated 15 degrees to display depth, front-right profile, seat cushions, and leg construction clearly.",
                "dalle_angle": "3/4 isometric angle looking towards the right side at 45 degrees, slightly elevated."
            },
            {
                "id": "vista_2_lateral",
                "label": "Vista 2: Perfil Lateral Estricto (90°)",
                "short_name": "Lateral 90°",
                "icon": "➡️",
                "angle_desc": "Strict 90-degree orthogonal lateral side profile view. Full silhouette from front edge to back edge with zero perspective vanishing points.",
                "dalle_angle": "Pure 90-degree side profile orthogonal view, perfectly flat side elevation."
            },
            {
                "id": "vista_3_frente",
                "label": "Vista 3: Elevación Frontal Directa (0°)",
                "short_name": "Frontal 0°",
                "icon": "🖼️",
                "angle_desc": "Direct flat 0-degree front elevation view. Camera placed directly in front of the furniture at exact center-line eye level, zero perspective vanishing distortion.",
                "dalle_angle": "Direct flat front view at 0 degrees, pure eye-level frontal elevation."
            },
            {
                "id": "vista_4_3_4_arriba",
                "label": "Vista 4: 3/4 Picada Alta Semi-Cenital (60°-70°)",
                "short_name": "3/4 Picada Alta",
                "icon": "🔍",
                "angle_desc": "High-angle elevated 3/4 semi-top perspective shot at 60 to 70 degrees looking down at the front. Clearly displays top surface/cushion depth while preserving front silhouette and legs.",
                "dalle_angle": "Elevated 3/4 high-angle shot from above at 65 degrees looking down at the front."
            },
            {
                "id": "vista_5_cenital",
                "label": "Vista 5: Cenital Superior Directo (90° desde arriba)",
                "short_name": "Cenital 90°",
                "icon": "🔝",
                "angle_desc": "Direct 90-degree top-down cenital bird's-eye view. Camera positioned directly overhead pointing straight down. Shows pure geometric top footprint and proportions.",
                "dalle_angle": "Direct 90-degree bird's-eye top-down view pointing straight down from above."
            }
        ]

        individual_results = []
        for v in vistas_specs:
            # Prompt individual para Google AI Studio
            prompt_ai_studio = f"""SYSTEM: You are a World-Class Master Commercial Product Photographer and AI Visual Director.
IMAGE IDENTIFICATION:
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
{user_directives_block}

TASK: Generate ONE SINGLE INDIVIDUAL COMMERCIAL CATALOG PHOTOGRAPH of the target furniture item ({furn_item}), isolated as a single object centered in the frame. DO NOT generate multiple items, do not generate a collage, do not generate a contact sheet. Only ONE single standalone furniture piece.

MANDATORY CAMERA PERSPECTIVE:
- {v['angle_desc']}

MATERIAL & GEOMETRIC FIDELITY:
- 100% exact fidelity to materials: [{materials_with_notes}].
- Topology & Geometry: {geom_struct}.

{white_bg}
HARDWARE & RENDERING:
{hardware_str}

Negative Prompt: collage, contact sheet, multiple views, multiple furniture pieces, grid, split screen, side-by-side, CGI, 3D render, cartoon, plastic, floor shadows, grey backdrop, room, text, watermark."""

            # Prompt individual para ChatGPT / DALL-E 3
            prompt_dalle = f"""[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography, Real-world micro-imperfections]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ONE single standalone commercial catalog photo of a {furn_item} ('{furniture_name}'), materials: ({materials_with_notes}).
Camera Angle: {v['dalle_angle']}
CRITICAL: Only 1 single furniture object centered in the image. No multiple angles, no contact sheet, no collage.
Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}"""

            individual_results.append({
                "id": v["id"],
                "label": v["label"],
                "short_name": v["short_name"],
                "icon": v["icon"],
                "google_ai_studio": prompt_ai_studio,
                "chatgpt_dalle3": prompt_dalle
            })

        # 1 SOLO PROMPT MAESTRO PARA GOOGLE AI STUDIO (Nano Banana 2.1 & Pro)
        # Configurado con protocolo conversacional que avanza foto por foto con la palabra clave 'foto'
        prompt_maestro_ais = f"""SYSTEM: You are a World-Class Master Commercial Product Photographer and AI Visual Director for Luxury Furniture Catalogs.
IMAGE IDENTIFICATION & VISUAL MEMORY:
- TARGET FURNITURE: Lock onto the uploaded photograph(s) of '{furniture_name}' and all reference photos.
- 360-DEGREE TOPOLOGY: Study the reference photos to understand the full 3D geometry from every angle.
{user_directives_block}

CRITICAL EXECUTION PROTOCOL (INTERACTIVE TURN-BY-TURN GENERATION WITH TRIGGER WORD 'foto'):
You must generate the 5 required catalog perspectives ONE BY ONE in sequence. Since Google AI Studio outputs one image per turn, follow this strict interactive protocol:

1. CURRENT TURN (IMAGE 1):
   - GENERATE ONLY THE FIRST VIEW: Vista 1 (3/4 Isométrica mirando a la derecha a 45°, elevación 15°).
   - Angle details: 3/4 isometric perspective at 45 degrees, facing toward the right. Elevated 15 degrees to show depth, front-right profile, seat thickness, and leg geometry.
   - STOP IMMEDIATELY after generating Image 1. DO NOT generate View 2 yet.
   - At the bottom of your response, indicate: "📸 Vista 1 generada. Escribe 'foto' para generar la Vista 2 (Perfil Lateral 90°)."

2. TURN 2 (TRIGGERED ONLY WHEN THE USER TYPES 'foto'):
   - Generate ONLY Vista 2: Strict 90-degree orthogonal lateral side profile. Full silhouette from front edge to back edge with zero perspective vanishing points.
   - End with: "📸 Vista 2 generada. Escribe 'foto' para la Vista 3 (Elevación Frontal 0°)."

3. TURN 3 (TRIGGERED BY 'foto'):
   - Generate ONLY Vista 3: Direct flat 0-degree front elevation view. Camera level at eye-line pointing directly dead-center.
   - End with: "📸 Vista 3 generada. Escribe 'foto' para la Vista 4 (3/4 Picada Alta)."

4. TURN 4 (TRIGGERED BY 'foto'):
   - Generate ONLY Vista 4: High-angle elevated 3/4 semi-top perspective shot at 60-70 degrees looking down at the front.
   - End with: "📸 Vista 4 generada. Escribe 'foto' para la Vista 5 (Cenital Superior 90°)."

5. TURN 5 (TRIGGERED BY 'foto'):
   - Generate ONLY Vista 5: Direct 90-degree top-down cenital bird's-eye view pointing straight down from above.

ABSOLUTE CONSISTENCY IN ALL 5 VIEWS:
- WOOD & FINISH LOCK: Lock the EXACT SAME wood species, warm tone, grain direction, and satin sheen in every single view.
- FABRIC & COLOR LOCK: Lock the EXACT SAME fabric weave texture, color, and softness.
- TOPOLOGY & GEOMETRY LOCK: Lock the exact furniture proportions, cushions, armrests, and leg joinery ({geom_struct}).
- MATERIALS: [{materials_with_notes}].

{white_bg}
HARDWARE & RENDERING:
{hardware_str}

Negative Prompt: collage, contact sheet, grid, multi-image strip, split screen, CGI, 3D render, cartoon, plastic, floor shadows, grey backdrop, text, labels, watermark."""

        # 1 SOLO PROMPT MAESTRO PARA CHATGPT / DALL-E 3 (Generación secuencial completa de las 5 fotos)
        prompt_maestro_dal = f"""[COMMAND: MULTI-IMAGE SEQUENTIAL GENERATION FOR COMMERCIAL CATALOG]
[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ALL 5 SEPARATE STANDALONE commercial catalog photos in sequence for a {furn_item} ('{furniture_name}'), materials: ({materials_with_notes}).
CRITICAL EXECUTION: Execute the image tool separately for EACH view below so they are outputted as 5 distinct, separate image files. DO NOT combine them into a collage or split canvas.

1. FIRST IMAGE (View 1): 3/4 Isometric Perspective Facing Right (45° angle, elevated 15° to reveal front-right silhouette and depth).
2. SECOND IMAGE (View 2): Strict Lateral Side Profile (90° orthogonal side view from edge to edge).
3. THIRD IMAGE (View 3): Direct Front View (0° flat frontal elevation at eye-level center).
4. FOURTH IMAGE (View 4): High-Angle Semi-Top Perspective (60°-70° elevated front view showing seat cushion and top surface).
5. FIFTH IMAGE (View 5): Direct Top-Down Cenital View (90° overhead bird's-eye geometric footprint).

Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}"""

        return {
            "google_ai_studio": prompt_maestro_ais,
            "chatgpt_dalle3": prompt_maestro_dal,
            "midjourney_v6": f"5 commercial luxury catalog shots (3/4 right, lateral 90, front 0, high-angle semi-top, top-down) of {furn_item}, {geom_struct}, materials: {materials_with_notes}, white background #FFFFFF, {hardware_str} --ar 16:9 --v 6.1 --style raw",
            "individual_vistas": individual_results
        }

    def generate_vistas_2_1_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> Dict[str, Any]:
        """
        Genera el set 'Vistas (2.1)' con las 4 vistas canónicas exactas de catálogo (Frontal, 3/4 Perspectiva, Lateral 90°, Superior Cenital):
        
        Optimizado para:
        - Google AI Studio (Nano Banana): Protocolo secuencial paso a paso con la palabra clave 'foto'.
        - ChatGPT (DALL-E 3): Generación secuencial completa de todas las 4 fotos.
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
⚡ MANDATORY USER CUSTOM DIRECTIVES (EMBEDDED ARCHITECTURAL & MATERIAL OVERRIDES):
{user_notes_clean}
* Strictest adherence required: Ensure every specification, color, material change, and detail above is natively integrated into each view render without exceptions.
==================================================================="""
            materials_with_notes = f"{existing_mats} (User mandatory note applied: {user_notes_clean})"
        else:
            user_directives_block = ""
            materials_with_notes = existing_mats

        vistas_2_1_specs = [
            {
                "id": "vista_2_1_frontal",
                "label": "Vista 1: Frontal Directa (0°)",
                "short_name": "Frontal 0°",
                "icon": "🖼️",
                "angle_desc": "Direct flat 0-degree frontal elevation view. Camera placed directly in front of the furniture piece at eye-level center. Zero perspective tilt, pure architectural straight-on view displaying the full front facade, drawer faces, integrated accent lighting if present, and base support.",
                "dalle_angle": "Pure direct 0-degree straight-on front elevation view, eye-level, perfectly centered."
            },
            {
                "id": "vista_2_1_tres_cuartos",
                "label": "Vista 2: 3/4 en Perspectiva (45°)",
                "short_name": "3/4 Perspectiva",
                "icon": "📐",
                "angle_desc": "Classic commercial 3/4 perspective view shot at a 45-degree angle. Camera positioned at slight eye-level elevation to simultaneously capture front drawers, side profile depth, cantilevered architecture, and top surface edge.",
                "dalle_angle": "Commercial 3/4 perspective shot at 45 degrees, revealing front facade and side depth with natural shadow drop."
            },
            {
                "id": "vista_2_1_lateral",
                "label": "Vista 3: Lateral Estricta (90°)",
                "short_name": "Lateral 90°",
                "icon": "➡️",
                "angle_desc": "Strict 90-degree orthogonal side profile elevation. Perfectly flat side view capturing the exact vertical silhouette, thickness of panels, open shelf cavity, and bottom base footprint with zero perspective convergence.",
                "dalle_angle": "Strict 90-degree side profile orthogonal view, perfectly flat lateral elevation."
            },
            {
                "id": "vista_2_1_superior_cenital",
                "label": "Vista 4: Superior Cenital (Top-Down)",
                "short_name": "Superior Cenital",
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
- 100% exact fidelity to materials: [{materials_with_notes}].
- Topology & Geometry: {geom_struct}.

{white_bg}
HARDWARE & RENDERING:
{hardware_str}

Negative Prompt: collage, contact sheet, multiple views, multiple furniture pieces, grid, split screen, side-by-side, CGI, 3D render, cartoon, plastic, floor shadows, grey backdrop, room, text, watermark."""

            # Prompt individual para ChatGPT / DALL-E 3
            prompt_dal = f"""[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography, Real-world timber micro-imperfections]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ONE single standalone commercial catalog photo of a {furn_item} ('{furniture_name}'), materials: ({materials_with_notes}).
Camera Angle: {v['dalle_angle']}
CRITICAL: Only 1 single furniture object centered in the image. No multiple angles, no contact sheet, no collage.
Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}"""

            individual_results.append({
                "id": v["id"],
                "label": v["label"],
                "short_name": v["short_name"],
                "icon": v["icon"],
                "google_ai_studio": prompt_ais,
                "chatgpt_dalle3": prompt_dal
            })

        # 1 SOLO PROMPT MAESTRO PARA GOOGLE AI STUDIO (Nano Banana 2.1 & Pro)
        # Configurado con protocolo interactivo secuencial con la palabra clave 'foto'
        prompt_maestro_ais = f"""SYSTEM: You are a World-Class Master Commercial Product Photographer and AI Visual Director for Luxury Furniture Catalogs.
IMAGE IDENTIFICATION & VISUAL MEMORY:
- TARGET FURNITURE: Lock onto the uploaded photograph(s) of '{furniture_name}' and all reference photos.
- 360-DEGREE TOPOLOGY: Study the reference photos to understand the full 3D geometry from every angle.
{user_directives_block}

CRITICAL EXECUTION PROTOCOL (INTERACTIVE TURN-BY-TURN GENERATION WITH TRIGGER WORD 'foto'):
You must generate the 4 canonical catalog perspectives ONE BY ONE in sequence. Since Google AI Studio outputs one image per turn, follow this strict interactive protocol:

1. CURRENT TURN (IMAGE 1):
   - GENERATE ONLY THE FIRST VIEW: Vista 1 (Direct Flat Front Elevation 0°).
   - Angle details: Camera perfectly level at eye-line pointing dead-center at front facade, displaying drawer faces, clean joinery, and lower structure.
   - STOP IMMEDIATELY after generating Image 1. DO NOT generate View 2 yet.
   - At the bottom of your response, indicate: "📸 Vista 1 generada. Escribe 'foto' para generar la Vista 2 (3/4 Perspectiva 45°)."

2. TURN 2 (TRIGGERED ONLY WHEN THE USER TYPES 'foto'):
   - Generate ONLY Vista 2: 3/4 Commercial Perspective shot at 45 degrees revealing front facade, side depth, cantilevered architecture, and top surface edge.
   - End with: "📸 Vista 2 generada. Escribe 'foto' para la Vista 3 (Lateral Estricta 90°)."

3. TURN 3 (TRIGGERED BY 'foto'):
   - Generate ONLY Vista 3: Strict orthogonal 90-degree lateral side profile elevation. Perfectly flat side view capturing vertical silhouette and panel thickness.
   - End with: "📸 Vista 3 generada. Escribe 'foto' para la Vista 4 (Superior Cenital)."

4. TURN 4 (TRIGGERED BY 'foto'):
   - Generate ONLY Vista 4: High-angle top-down cenital view from above showcasing top wood surface grain flow, rounded edge radii, and lower base.

ABSOLUTE CONSISTENCY IN ALL 4 VIEWS:
- WOOD & FINISH LOCK: Maintain 100% exact original materials, wood tone, grain structure, and warm ambient LED glow from TARGET FURNITURE in every single view.
- FABRIC & COLOR LOCK: Lock the EXACT SAME fabric weave texture, color, and softness.
- TOPOLOGY & GEOMETRY LOCK: Lock the exact proportions, joinery, and cantilevered architecture ({geom_struct}).
- MATERIALS: [{materials_with_notes}].

{white_bg}
HARDWARE & RENDERING:
{hardware_str}

Negative Prompt: collage, contact sheet, grid, multi-image strip, split screen, CGI, 3D render, cartoon, plastic, floor shadows, grey backdrop, text, labels, watermark."""

        # 1 SOLO PROMPT MAESTRO PARA CHATGPT / DALL-E 3 (Generación completa de las 4 fotos)
        prompt_maestro_dal = f"""[COMMAND: MULTI-IMAGE SEQUENTIAL GENERATION FOR COMMERCIAL CATALOG]
[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ALL 4 SEPARATE STANDALONE commercial catalog photos in sequence for a {furn_item} ('{furniture_name}'), materials: ({materials_with_notes}).
CRITICAL EXECUTION: Execute the image tool separately for EACH view below so they are outputted as 4 distinct, separate image files. DO NOT combine them into a collage or split canvas.

1. FIRST IMAGE (View 1): Front View (0° flat eye-level elevation showing facade and joinery).
2. SECOND IMAGE (View 2): 3/4 Perspective View (45° angle showing front and side depth).
3. THIRD IMAGE (View 3): Side Profile (90° orthogonal flat lateral elevation).
4. FOURTH IMAGE (View 4): Top-Down Cenital View (overhead angle showing top surface wood grain and lower base).

Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}"""

        return {
            "google_ai_studio": prompt_maestro_ais,
            "chatgpt_dalle3": prompt_maestro_dal,
            "midjourney_v6": f"Commercial catalog 4 separate shots of {furn_item}, {geom_struct}, materials: {materials_with_notes}, white background #FFFFFF, {hardware_str} --ar 16:9 --v 6.1 --style raw",
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
        """Redirige al generador canónico de Vistas 1.1"""
        return self.generate_vistas_1_1_prompts(
            furniture_name=furniture_name,
            furniture_analysis=furniture_analysis,
            notas_usuario=notas_usuario
        )

ai_prompt_service_v5 = AIPromptServiceV5()

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
    geometric_structure: str = Field(description="Descripción topológica de la forma, silueta y ensambles 360°")
    wood_and_finish_analysis: str = Field(description="Especie exacta de madera, tonalidad, veta, calidez y acabado superficial (ej. Roble Blanco natural con veta sutil mate, #D2B48C). Si se subieron muestras de madera, basarse prioritariamente en ellas.")
    upholstery_analysis: str = Field(description="Detalle micro-textil y color de tapicería si aplica (ej. lino crudo beige, bouclé, o 'Sin tapicería' si es 100% madera)")
    existing_materials: str = Field(description="Descripción técnica integral consolidada de todos los materiales, madera y tapicería")
    wood_details: Optional[str] = Field(default="", description="Detalle específico de la madera detectada")

class AIPromptServiceV5:
    def __init__(self):
        self.default_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self._clients: Dict[str, Any] = {}

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

    def get_client(self, api_key: Optional[str] = None):
        """Reutiliza el cliente con conexión Keep-Alive para evitar renegociación SSL."""
        key = self.get_api_key(api_key)
        if not key:
            return None
        if key in self._clients:
            return self._clients[key]
        try:
            from google import genai
            client = genai.Client(api_key=key)
            self._clients[key] = client
            return client
        except Exception as e:
            print(f"[AIPromptServiceV5] Error instanciando cliente: {e}")
            return None

    def _call_gemini(self, client, contents, config=None):
        """Llama a Gemini priorizando modelos oficiales rápidos existentes sin fallos 404."""
        models_to_try = [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-2.0-flash-lite",
        ]
        last_err = None
        for m in models_to_try:
            try:
                return client.models.generate_content(model=m, contents=contents, config=config)
            except Exception as e:
                last_err = e
                continue
        raise last_err if last_err else RuntimeError("No se pudo conectar con Gemini API")

    def _prepare_image(self, img_bytes: bytes, max_dim: int = 512) -> Image.Image:
        """Optimiza y comprime en memoria imágenes a 512px y JPEG 75 para envío ultra-rápido (<50KB)."""
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75, optimize=True)
        buf.seek(0)
        return Image.open(buf)

    def analyze_material(self, sample_bytes: bytes, api_key: Optional[str] = None, material_type: str = "auto") -> Dict[str, Any]:
        key = self.get_api_key(api_key)
        default_material = MaterialAnalysisV5(
            name="Roble Claro Natural / Natural Honey Oak",
            color_description="warm light honey wood tone (#D5A869) with soft amber undertones",
            texture_detail="fine continuous horizontal wood grain pores, smooth satin texture",
            light_interaction="matte satin sheen without glare"
        ).model_dump()

        if not key:
            return default_material
            
        try:
            from google import genai
            from google.genai import types
            
            client = self.get_client(key)
            if not client:
                return default_material
            img = self._prepare_image(sample_bytes, max_dim=512)
            
            prompt = f"""You are an expert materials engineer, timber technologist, and luxury product photographer.
Analyze this material sample ({material_type}) with microscopic precision:
1. Identify the exact timber species (e.g. Roble Claro Natural / Natural Light Oak, Nogal / American Walnut, Encino, Fresno, Teca).
2. Report the exact color description with estimated Hex code (e.g. #D5A869), warmth, and undertones.
3. Report wood grain flow, pore openness, and texture.
4. Report light interaction and surface sheen (matte, low lustre satin)."""
            
            res = self._call_gemini(
                client=client,
                contents=[prompt, img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MaterialAnalysisV5,
                    temperature=0.1
                )
            )
            data = json.loads(res.text)
            c_desc = data.get("color_description", "")
            if not c_desc or "detected" in c_desc.lower():
                data["color_description"] = "warm light honey natural oak tone (#D5A869) with subtle amber undertones"
            return data
        except Exception as e:
            print(f"[AIPromptServiceV5] Error analyzing material: {e}")
            return default_material

    def analyze_furniture_for_enhancement(
        self, 
        furniture_bytes, 
        reference_bytes: Optional[List[bytes]] = None, 
        wood_bytes: Optional[List[bytes]] = None,
        notas_usuario: str = "",
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analiza conjuntamente en 1 sola llamada rápida la foto del mueble, muestras de madera/color,
        referencias 360° y notas del usuario, evitando OOM y caídas de servidor.
        """
        key = self.get_api_key(api_key)
        if not key:
            notes_clean = notas_usuario.strip() if notas_usuario else ""
            inferred_type = "mid-century modern wooden furniture piece"
            lower_notes = notes_clean.lower()
            if any(w in lower_notes for w in ["buro", "buró", "noche", "mesita", "velador", "cajon", "cajón"]):
                inferred_type = "mid-century modern wooden nightstand / buró with fluted drawer"
            elif "cama" in lower_notes:
                inferred_type = "minimalist low-profile platform bed frame"
            elif any(w in lower_notes for w in ["sofa", "sofá", "sillon", "sillón"]):
                inferred_type = "contemporary modular sofa"
            elif "mesa" in lower_notes:
                inferred_type = "architectural wooden table"

            return FurnitureAnalysisV5(
                furniture_item=inferred_type,
                camera_angle="0-degree frontal and 3/4 perspective",
                lighting_direction="soft studio lighting with subtle fill",
                geometric_structure="clean geometric joinery and exact proportional dimensions as specified by user",
                wood_and_finish_analysis="warm natural honey oak (#D5A869) with continuous horizontal grain flow and satin finish",
                upholstery_analysis="none (100% solid wood construction)",
                existing_materials="monolithic natural light oak wood with continuous horizontal grain"
            ).model_dump()
            
        try:
            from google.genai import types
            
            client = self.get_client(key)
            if not client:
                raise RuntimeError("No se pudo inicializar el cliente de Gemini API")
            
            # 1. Preparar imágenes del mueble (Casilla 1) - max 2 para ligereza
            actual_imgs = []
            if isinstance(furniture_bytes, list):
                for fb in furniture_bytes[:2]:
                    if fb:
                        actual_imgs.append(self._prepare_image(fb, max_dim=512))
            elif furniture_bytes:
                actual_imgs.append(self._prepare_image(furniture_bytes, max_dim=512))

            # 2. Preparar imágenes de muestra de madera / color (Casilla 2) - max 2
            wood_imgs = []
            if wood_bytes and isinstance(wood_bytes, list):
                for wb in wood_bytes[:2]:
                    if wb:
                        wood_imgs.append(self._prepare_image(wb, max_dim=512))
            elif wood_bytes:
                wood_imgs.append(self._prepare_image(wood_bytes, max_dim=512))

            # 3. Preparar imágenes de referencia (Casilla 3) - max 2
            ref_imgs = []
            if reference_bytes and isinstance(reference_bytes, list):
                for rb in reference_bytes[:2]:
                    if rb:
                        ref_imgs.append(self._prepare_image(rb, max_dim=512))
            elif reference_bytes:
                ref_imgs.append(self._prepare_image(reference_bytes, max_dim=512))

            has_wood = bool(wood_imgs)
            if has_wood:
                prompt = """You are an elite furniture materials engineer, 3D architectural visualizer, and commercial product photographer.
Analyze the provided images to create an exhaustive, production-grade technical specification for this furniture piece:

1. WOOD SAMPLE IMAGE(S) PROVIDED (ABSOLUTE PRIORITY & TRUTH FOR TIMBER / COLOR):
   - Analyze the wood / color sample photos first.
   - Identify the exact timber species (e.g. White Oak / Roble Blanco, American Walnut / Nogal, Ash / Fresno, Teak / Teca, Bleached Pine / Pino, etc.).
   - Specify the exact grain direction, pore openness, warmth/undertones, and sheen (matte, satin).
   - This exact wood species and finish MUST be assigned to all wooden surfaces of the furniture across all catalog renders!

2. FURNITURE PHOTO(S) & 360° REFERENCES (GEOMETRY & TOPOLOGY):
   - Identify the furniture item type and design style (e.g. mid-century modern curved wooden armchair).
   - Detail the 3D topology, proportions, joinery, leg construction, and backrest angle across the views.
   - Describe any upholstery, cushions, fabric weave, and color.
   - Identify the observed camera angle and studio lighting."""
            else:
                prompt = """You are an elite furniture materials engineer, 3D architectural visualizer, and commercial product photographer.
Analyze the provided furniture and reference images to create an exhaustive, production-grade technical specification:

1. FURNITURE TOPOLOGY & GEOMETRY:
   - Identify the furniture item type and design style (e.g. mid-century modern, Japandi, contemporary sculptural).
   - Detail the 3D topology, silhouette, joints, leg construction, and proportions across all provided angles.
   - Identify the observed camera angle and studio lighting.

2. MATERIALS & COLOR FIDELITY:
   - Describe the exact wood species, grain flow, stain tone, and surface sheen visible in the photos.
   - Describe any upholstery, cushion fabric, weave texture, and exact color."""

            if notas_usuario and notas_usuario.strip():
                prompt += f"\n\nUSER MANDATORY DIRECTIVES (STRICT OVERRIDE):\n{notas_usuario.strip()}"

            contents = [prompt] + wood_imgs + (actual_imgs or ref_imgs)
            if ref_imgs and actual_imgs:
                contents += ref_imgs[:1]

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=FurnitureAnalysisV5,
                temperature=0.1
            )

            res = self._call_gemini(client=client, contents=contents, config=config)
            furniture_data = json.loads(res.text)

            if "existing_materials" not in furniture_data or not furniture_data["existing_materials"]:
                w = furniture_data.get("wood_and_finish_analysis", "")
                u = furniture_data.get("upholstery_analysis", "")
                furniture_data["existing_materials"] = f"{w}, {u}".strip(", ")

            furniture_data["has_wood_sample"] = has_wood
            return furniture_data

        except Exception as e:
            print(f"[AIPromptServiceV5] Error analyzing furniture: {e}")
            notes_clean = notas_usuario.strip() if notas_usuario else ""
            inferred_type = "mid-century modern wooden furniture piece"
            lower_notes = notes_clean.lower()
            if any(w in lower_notes for w in ["buro", "buró", "noche", "mesita", "velador", "cajon", "cajón"]):
                inferred_type = "mid-century modern wooden nightstand / buró with fluted drawer"
            elif "cama" in lower_notes:
                inferred_type = "minimalist low-profile platform bed frame"
            elif any(w in lower_notes for w in ["sofa", "sofá", "sillon", "sillón"]):
                inferred_type = "contemporary modular sofa"
            elif "mesa" in lower_notes:
                inferred_type = "architectural wooden table"

            return FurnitureAnalysisV5(
                furniture_item=inferred_type,
                camera_angle="0-degree frontal and 3/4 perspective",
                lighting_direction="soft studio lighting with subtle fill",
                geometric_structure="clean geometric joinery and exact proportional dimensions as specified by user",
                wood_and_finish_analysis="warm natural honey oak (#D5A869) with continuous horizontal grain flow and satin finish",
                upholstery_analysis="none (100% solid wood construction)",
                existing_materials="monolithic natural light oak wood with continuous horizontal grain"
            ).model_dump()

    def _build_photo_hardware_str(self) -> str:
        return "Optics: 100MP medium format RAW, 80mm lens, f/11 aperture, ISO 64, studio strobe lighting with soft diffuse octabox fill. Razor-sharp micro-textures."

    def _build_white_isolation_str(self) -> str:
        return "Solid pure seamless white background (#FFFFFF), 0% floor shadows, 0% drop shadows, zero reflections. No typography, no watermarks."

    def generate_vistas_1_1_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filenames: Optional[List[str]] = None,
        reference_filenames: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Genera el set 'Vistas (1.1)' con las 5 vistas canónicas completas con arquitectura de Alta Densidad de Tokens.
        """
        ma = furniture_analysis or {}
        fa = fabric_analysis or {}
        wa = wood_analysis or {}

        furn_item = ma.get("furniture_item", furniture_name)
        if "directives:" in furn_item:
            furn_item = furn_item.split("directives:")[0].strip()
        if not furn_item:
            furn_item = furniture_name
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials")
        if "original fabric and wood finish" in existing_mats or "original materials" in existing_mats:
            existing_mats = "monolithic natural light honey oak (#D5A869) with continuous horizontal grain flow"
        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()

        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""[MANDATORY USER OVERRIDE DIRECTIVES]:
* {user_notes_clean}
* Strictest adherence required: Ensure every specification, dimension, color tone, and material above is natively integrated without exceptions."""
            materials_with_notes = f"{existing_mats} (User note: {user_notes_clean})"
        else:
            user_directives_block = ""
            materials_with_notes = existing_mats

        # Construcción de nombres de archivos para identificación transparente de tokens
        furn_file_str = ", ".join(f"'{fn}'" for fn in furniture_filenames) if furniture_filenames else f"'{furniture_name}'"
        wood_file_str = ", ".join(f"'{fn}'" for fn in wood_filenames) if wood_filenames else ""
        ref_file_str = ", ".join(f"'{fn}'" for fn in reference_filenames) if reference_filenames else ""

        # Identificación de imágenes y candados de material con Alta Densidad de Tokens
        mat_rules = []
        id_blocks = [
            f"- IMAGE 1 (TARGET FURNITURE) [File: {furn_file_str}]: Reference for 3D model, proportions, silhouette, and joinery ('{furn_item}')."
        ]

        has_wood_sample = bool(wa) or ma.get("has_wood_sample", False)
        if has_wood_sample:
            w_name = wa.get("name", "Roble Claro Natural / White Oak Swatch") if wa else "Roble Claro Natural / White Oak Swatch"
            w_color = wa.get("color_description", materials_with_notes) if wa else materials_with_notes
            w_texture = wa.get("texture_detail", "authentic wood grain pores") if wa else "authentic wood grain pores"
            w_light = wa.get("light_interaction", "satin matte sheen") if wa else "satin matte sheen"

            if "fallback" in w_name.lower() or "detected" in str(w_color).lower() or not w_color:
                w_name = "Roble Claro Natural / White Oak Swatch"
                w_color = "warm light honey natural timber tone (#D5A869) with subtle amber undertones"
                w_texture = "fine continuous horizontal wood grain pores, smooth satin finish"
                w_light = "matte satin sheen"

            wood_label = f" [File: {wood_file_str}]" if wood_file_str else ""
            id_blocks.append(
                f"- IMAGE 2 (WOOD / FINISH SWATCH) [100% GROUND TRUTH]{wood_label}: Primary source of truth for wood species, continuous grain flow, stain tone, warmth, and surface sheen ('{w_name}': {w_color}, {w_texture}, {w_light})."
            )
            mat_rules.append(f"""[CRITICAL MATERIAL & WOOD GRAIN LOCK]:
* 100% UNIFORM MONOLITHIC FINISH: The entire furniture piece—front drawer faces, circular handles, outer casing, side panels, top surface, and legs—MUST be crafted from the EXACT SAME SINGLE BATCH OF WOOD from IMAGE 2.
* ZERO TWO-TONE ACCENTS: STRICTLY FORBIDDEN to render drawer faces in dark walnut, black, or contrasting wood. All surfaces share identical grain flow, color saturation, and satin matte sheen.
* CONTINUOUS GRAIN FLOW: Natural horizontal grain continuity across drawer faces and top surface.""")

        if fa:
            f_name = fa.get("name", "Fabric Sample")
            f_color = fa.get("color_description", "")
            f_texture = fa.get("texture_detail", "")
            f_light = fa.get("light_interaction", "")
            id_blocks.append(
                f"- IMAGE 3 (FABRIC SWATCH REFERENCE): Reference for upholstery textile weave and color ('{f_name}': {f_color}, {f_texture}, {f_light})."
            )
            mat_rules.append(f"""[UPHOLSTERY FABRIC LOCK]:
* Apply exact upholstery weave and color from FABRIC SWATCH ('{f_name}'). Micro-texture realism, 0% color shift.""")

        if ref_file_str:
            id_blocks.append(
                f"- AUXILIARY REFERENCES [Files: {ref_file_str}]: Auxiliary reference views for rear joints and hidden structural angles."
            )

        if not mat_rules:
            mat_rules.append(f"[MATERIAL PRESERVATION LOCK]:\n* Lock 100% authentic original materials, finishes, and wood grain from TARGET FURNITURE: [{materials_with_notes}].")

        # Candado de medidas y proporciones 3D
        proportions_lock = f"""[3D TURNTABLE SCALE & PROPORTIONAL LOCK]:
* Rotate the exact same frozen physical prototype ({geom_struct}). Proportions, drawer heights, and circular handle diameter are strictly locked 1:1. Zero distortion, zero leg stretching."""

        materials_final_block = "\n".join(mat_rules) + "\n" + proportions_lock
        image_id_final_block = "[INPUT IMAGE REFERENCES]:\n" + "\n".join(id_blocks)

        vistas_specs = [
            {
                "id": "vista_1_3_4_derecha",
                "label": "Vista 1: 3/4 Isométrica (Mirando a la Derecha)",
                "short_name": "3/4 Isométrica Derecha",
                "icon": "📐",
                "angle_desc": "3/4 isometric perspective at a 45-degree angle, with the furniture facing toward the right. Elevated 15 degrees to display depth, front-right profile, seat/top contours, and leg construction clearly.",
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
                "angle_desc": "Direct 0-degree front elevation view. Camera level with furniture center pointing directly dead-on, showcasing facade, drawer/cushion proportions, and bottom symmetry.",
                "dalle_angle": "Direct flat 0-degree frontal view, eye-level lens, centered horizon."
            },
            {
                "id": "vista_4_picada",
                "label": "Vista 4: 3/4 Picada Alta / Semi-Arriba (60°-70°)",
                "short_name": "3/4 Picada Alta",
                "icon": "↗️",
                "angle_desc": "High-angle elevated 3/4 semi-top perspective shot at 60-70 degrees looking down at the front. Emphasizes top surface textures, seat cushion planes, and upper contours.",
                "dalle_angle": "Elevated 3/4 high-angle shot from above at 65 degrees looking down at the front."
            },
            {
                "id": "vista_5_cenital",
                "label": "Vista 5: Cenital Superior Plano Directo (90° desde arriba)",
                "short_name": "Cenital 90°",
                "icon": "🔝",
                "angle_desc": "Strict 90-degree orthogonal overhead flat top-down view (plan view). The camera points vertically straight down from the ceiling directly perpendicular to the flat top wooden surface (camera pitch: -90 degrees). The rectangular top wooden surface fills the frame, showcasing the rich continuous horizontal wood grain patterns and edge joins. Zero camera tilt: do NOT angle the camera, do NOT show the front facade, and do NOT show the drawer faces. Pure flat overhead view.",
                "dalle_angle": "Pure 90-degree orthogonal flat overhead top-down view looking straight down at the top surface, flat rectangular wood grain plan view, zero front facade visible, no drawers visible."
            }
        ]

        if has_wood_sample:
            gen_directive_ais = f"""[MANDATORY GENERATION DIRECTIVE - MATERIAL TRANSFER]:
Generate and photograph the {furn_item} ('{furniture_name}') isolated as a master commercial catalog photograph with strict material replacement:
* 100% UNIFORM MONOLITHIC WOOD LOCK: Transform all wooden components (front drawer faces, circular handles, outer casing, side panels, top surface, legs) using the exact timber species, continuous grain flow, and stain tone from IMAGE 2 ('{w_name}': {w_color}, {w_texture}). Zero two-tone mismatch, zero walnut contrast.
* PROPORTIONS & JOINERY: Preserve 100% exact 3D geometry and dimensions ({geom_struct}) from IMAGE 1.
* EXECUTION DIRECTIVE: Immediately render and output the photographic image. Do not output text-only descriptions or commentary."""
        else:
            gen_directive_ais = f"""[MANDATORY GENERATION DIRECTIVE]:
Generate and photograph the {furn_item} ('{furniture_name}') isolated as a master commercial catalog photograph:
* MATERIALS & TEXTURES: Preserve 100% exact original wood grain, timber species, stain tone, and textures ({materials_with_notes}).
* PROPORTIONS & JOINERY: Preserve 100% exact 3D geometry and dimensions ({geom_struct}) from IMAGE 1.
* EXECUTION DIRECTIVE: Immediately render and output the photographic image. Do not output text-only descriptions or commentary."""

        user_notes_ais = f"\n* DIRECTIVA OBLIGATORIA: {user_notes_clean}" if user_notes_clean else ""
        wood_ais_lock = f"Apply 100% monolithic wood from Image 2 ('{w_name}': {w_color}, {w_texture}) across all parts (drawers, circular handles, chassis, top, sides, legs). Continuous horizontal grain flow. ZERO two-tone contrast; NO dark walnut drawers." if has_wood_sample else f"Preserve 100% original authentic wood materials and finishes ({materials_with_notes})."

        individual_results = []
        for v in vistas_specs:
            extra_neg = ", tilted camera, downward perspective, 3/4 high angle, visible drawer faces, visible front facade" if "cenital" in v["id"] else ""
            
            # Prompt individual conciso y ultra-específico para Google AI Studio (Nano Banana 2.1 / Pro)
            prompt_ai_studio = f"""[MODEL: GEMINI NANO BANANA 2.1 / PRO | COMMERCIAL PHOTOGRAPHY]
• Image 1 (Target Furniture): 3D model, joinery, and 1:1 scale of '{furn_item}'.
• Image 2 (Wood Swatch - Ground Truth): Exact wood species, grain, and stain tone ('{w_name}': {w_color}, {w_texture}).

DIRECTIVES:
1. 100% MONOLITHIC WOOD LOCK: {wood_ais_lock}
2. 3D GEOMETRY: Preserve 100% exact dimensions and physical proportions ({geom_struct}) from Image 1.{user_notes_ais}
3. VIEW: {v['label']} - {v['angle_desc']}
4. STUDIO: Pure seamless solid white background (#FFFFFF), studio softbox lighting, 0% ground shadows, razor-sharp 8K commercial photo.

Negative Prompt: two-tone drawers, contrasting dark drawers, walnut drawer faces, wrong wood color, mismatched grain, altered proportions, resized handles, collage, grid, multi-image strip, CGI, render, shadows, backdrop, watermark{extra_neg}."""

            # Prompt individual token-optimizado para ChatGPT / DALL-E 3
            prompt_dalle = f"""[COMMAND: COMMERCIAL PRODUCT PHOTOGRAPHY | 35MM RAW MEDIUM FORMAT]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Photograph ONE single standalone commercial catalog photo of {furn_item} ('{furniture_name}').
Camera Angle: {v['dalle_angle']}
CRITICAL: Only 1 single furniture object centered in the image. No multiple angles, no contact sheet, no collage.
Topological Geometry: {geom_struct}.
Materials & Monolithic Lock:
{materials_final_block}
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}
Negative Prompt: two-tone drawers, contrasting drawer wood, dark walnut drawers, misaligned grain, collage, contact sheet, grid, split view, 3d render, cartoon{extra_neg}."""

            individual_results.append({
                "id": v["id"],
                "label": v["label"],
                "short_name": v["short_name"],
                "icon": v["icon"],
                "google_ai_studio": prompt_ai_studio,
                "chatgpt_dalle3": prompt_dalle
            })

        # 1 SOLO PROMPT MAESTRO TOKEN-OPTIMIZADO PARA GOOGLE AI STUDIO (Nano Banana 2.1 / Pro)
        prompt_maestro_ais = f"""[MODEL: GEMINI NANO BANANA 2.1 / PRO | 5-VIEW COMMERCIAL CATALOG]
• Image 1 (Target Furniture): 3D model, joinery, and 1:1 scale of '{furn_item}'.
• Image 2 (Wood Swatch - Ground Truth): Exact wood species, grain, and stain tone ('{w_name}': {w_color}, {w_texture}).

DIRECTIVES:
1. 100% MONOLITHIC WOOD LOCK: {wood_ais_lock}
2. 3D GEOMETRY: Preserve 100% exact dimensions and physical proportions ({geom_struct}) from Image 1.{user_notes_ais}
3. STUDIO: Pure seamless solid white background (#FFFFFF), studio softbox lighting, 0% ground shadows, razor-sharp 8K commercial photo.

EXECUTION (TURN-BY-TURN):
Generate ONE single standalone photo per turn.
- CURRENT TURN: Generate ONLY Vista 1 (3/4 Isométrica Derecha 45°: elevated 15° showing front-right depth, contour, and legs).
Conclude your response with: "📸 Vista 1 generada. Escribe 'foto' para generar la Vista 2 (Perfil Lateral 90°)."
- Subsequent views (triggered ONLY by typing 'foto'):
  2. Vista 2: Lateral Perfil Estricto 90° (orthogonal side profile).
  3. Vista 3: Elevación Frontal Directa 0° (flat eye-level front view).
  4. Vista 4: 3/4 Picada Alta 65° (high angle showing top surface textures and front depth).
  5. Vista 5: Cenital Superior Plano 90° (strict perpendicular overhead view, top wood surface only, zero front drawers visible).

Negative Prompt: two-tone drawers, contrasting dark drawers, walnut drawer faces, wrong wood color, mismatched grain, altered proportions, resized handles, collage, grid, multi-image strip, CGI, render, shadows, backdrop, watermark."""

        # 1 SOLO PROMPT MAESTRO PARA CHATGPT / DALL-E 3
        wood_dal_maestro = f" Apply exact wood species, grain flow, and stain tone from the wood sample reference: ({materials_with_notes})." if has_wood_sample else f", materials: ({materials_with_notes})"
        prompt_maestro_dal = f"""[COMMAND: MULTI-IMAGE SEQUENTIAL GENERATION FOR COMMERCIAL CATALOG]
[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ALL 5 SEPARATE STANDALONE commercial catalog photos in sequence for a {furn_item} ('{furniture_name}'){wood_dal_maestro}.

[IMAGE REFERENCES & GROUND TRUTH]:
- Target Furniture: 3D model and facade proportions from '{furniture_name}'.
- Wood / Color Sample: Exact wood species, continuous grain flow, and stain tone from wood reference ('{w_name}': {w_color}, {w_texture}).

[CRITICAL MONOLITHIC WOOD LOCK]:
* 100% UNIFORM MONOLITHIC WOOD: Entire unit (front drawer faces, circular handles, chassis, side panels, top surface, legs) must share the identical wood finish and grain from the wood swatch.
* ZERO TWO-TONE FINISH: Do NOT make drawer faces dark walnut or contrasting color.

CRITICAL EXECUTION: Execute the image tool separately for EACH view below so they are outputted as 5 distinct, separate image files. DO NOT combine them into a collage or split canvas.

1. FIRST IMAGE (View 1): 3/4 Isometric Perspective Facing Right (45° angle, elevated 15° to reveal front-right silhouette and depth).
2. SECOND IMAGE (View 2): Strict Lateral Side Profile (90° orthogonal side view from edge to edge).
3. THIRD IMAGE (View 3): Direct Front View (0° flat frontal elevation at eye-level center).
4. FOURTH IMAGE (View 4): High-Angle Semi-Top Perspective (60°-70° elevated front view showing seat cushion and top surface).
5. FIFTH IMAGE (View 5): Pure 90-Degree Orthogonal Flat Overhead Top-Down View (camera perpendicular looking straight down at the top wooden surface, plan view, zero front facade visible, no drawers visible).

Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}
Negative Prompt: two-tone drawers, contrasting drawer wood, dark walnut drawers, misaligned grain, collage, contact sheet, grid, split view, 3d render, cartoon."""

        return {
            "google_ai_studio": prompt_maestro_ais,
            "chatgpt_dalle3": prompt_maestro_dal,
            "midjourney_v6": f"5 commercial luxury catalog shots of {furn_item}, {geom_struct}, white background #FFFFFF, {hardware_str} --ar 16:9 --v 6.1 --style raw",
            "individual_vistas": individual_results
        }

    def generate_vistas_2_1_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filenames: Optional[List[str]] = None,
        reference_filenames: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Genera el set 'Vistas (2.1)' con las 4 vistas canónicas exactas de catálogo con arquitectura de Alta Densidad de Tokens.
        """
        ma = furniture_analysis or {}
        fa = fabric_analysis or {}
        wa = wood_analysis or {}

        furn_item = ma.get("furniture_item", furniture_name)
        if "directives:" in furn_item.lower():
            furn_item = furniture_name
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials")
        if "original fabric and wood finish" in existing_mats or "original materials" in existing_mats:
            existing_mats = "monolithic natural light honey oak (#D5A869) with continuous horizontal grain flow"
        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()

        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""[MANDATORY USER OVERRIDE DIRECTIVES]:
* {user_notes_clean}
* Strictest adherence required: Ensure every specification, dimension, color tone, and material above is natively integrated without exceptions."""
            materials_with_notes = f"{existing_mats} (User note: {user_notes_clean})"
        else:
            user_directives_block = ""
            materials_with_notes = existing_mats

        # Construcción de nombres de archivos para identificación transparente de tokens
        furn_file_str = ", ".join(f"'{fn}'" for fn in furniture_filenames) if furniture_filenames else f"'{furniture_name}'"
        wood_file_str = ", ".join(f"'{fn}'" for fn in wood_filenames) if wood_filenames else ""
        ref_file_str = ", ".join(f"'{fn}'" for fn in reference_filenames) if reference_filenames else ""

        # Identificación de imágenes y candados de material con Alta Densidad de Tokens
        mat_rules = []
        id_blocks = [
            f"- IMAGE 1 (TARGET FURNITURE) [File: {furn_file_str}]: Reference for 3D model, proportions, silhouette, and joinery ('{furn_item}')."
        ]

        has_wood_sample = bool(wa) or ma.get("has_wood_sample", False)
        if has_wood_sample:
            w_name = wa.get("name", "Roble Claro Natural / White Oak Swatch") if wa else "Roble Claro Natural / White Oak Swatch"
            w_color = wa.get("color_description", materials_with_notes) if wa else materials_with_notes
            w_texture = wa.get("texture_detail", "authentic wood grain pores") if wa else "authentic wood grain pores"
            w_light = wa.get("light_interaction", "satin matte sheen") if wa else "satin matte sheen"

            if "fallback" in w_name.lower() or "detected" in str(w_color).lower() or not w_color:
                w_name = "Roble Claro Natural / White Oak Swatch"
                w_color = "warm light honey natural timber tone (#D5A869) with subtle amber undertones"
                w_texture = "fine continuous horizontal wood grain pores, smooth satin finish"
                w_light = "matte satin sheen"

            wood_label = f" [File: {wood_file_str}]" if wood_file_str else ""
            id_blocks.append(
                f"- IMAGE 2 (WOOD / FINISH SWATCH) [100% GROUND TRUTH]{wood_label}: Primary source of truth for wood species, continuous grain flow, stain tone, warmth, and surface sheen ('{w_name}': {w_color}, {w_texture}, {w_light})."
            )
            mat_rules.append(f"""[CRITICAL MATERIAL & WOOD GRAIN LOCK]:
* 100% UNIFORM MONOLITHIC FINISH: The entire furniture piece—front drawer faces, circular handles, outer casing, side panels, top surface, and legs—MUST be crafted from the EXACT SAME SINGLE BATCH OF WOOD from IMAGE 2.
* ZERO TWO-TONE ACCENTS: STRICTLY FORBIDDEN to render drawer faces in dark walnut, black, or contrasting wood. All surfaces share identical grain flow, color saturation, and satin matte sheen.
* CONTINUOUS GRAIN FLOW: Natural horizontal grain continuity across drawer faces and top surface.""")

        if fa:
            f_name = fa.get("name", "Fabric Sample")
            f_color = fa.get("color_description", "")
            f_texture = fa.get("texture_detail", "")
            f_light = fa.get("light_interaction", "")
            id_blocks.append(
                f"- IMAGE 3 (FABRIC SWATCH REFERENCE): Reference for upholstery textile weave and color ('{f_name}': {f_color}, {f_texture}, {f_light})."
            )
            mat_rules.append(f"""[UPHOLSTERY FABRIC LOCK]:
* Apply exact upholstery weave and color from FABRIC SWATCH ('{f_name}'). Micro-texture realism, 0% color shift.""")

        if ref_file_str:
            id_blocks.append(
                f"- AUXILIARY REFERENCES [Files: {ref_file_str}]: Auxiliary reference views for rear joints and hidden structural angles."
            )

        if not mat_rules:
            mat_rules.append(f"[MATERIAL PRESERVATION LOCK]:\n* Lock 100% authentic original materials, finishes, and wood grain from TARGET FURNITURE: [{materials_with_notes}].")

        # Candado de medidas y proporciones 3D
        proportions_lock = f"""[3D TURNTABLE SCALE & PROPORTIONAL LOCK]:
* Rotate the exact same frozen physical prototype ({geom_struct}). Proportions, drawer heights, and circular handle diameter are strictly locked 1:1. Zero distortion, zero leg stretching."""

        materials_final_block = "\n".join(mat_rules) + "\n" + proportions_lock
        image_id_final_block = "[INPUT IMAGE REFERENCES]:\n" + "\n".join(id_blocks)

        vistas_2_1_specs = [
            {
                "id": "vista_2_1_frontal",
                "label": "Vista 1: Frontal Directa (0°)",
                "short_name": "Frontal 0°",
                "icon": "🖼️",
                "angle_desc": "Direct flat 0-degree front elevation view. Camera level with furniture center at eye-line pointing directly dead-on at front facade, displaying drawer faces, circular handles, clean joinery, and lower structure.",
                "dalle_angle": "Direct flat 0-degree frontal view, eye-level lens, centered horizon showing facade and joinery."
            },
            {
                "id": "vista_2_1_perspectiva",
                "label": "Vista 2: 3/4 Perspectiva (45°)",
                "short_name": "3/4 Perspectiva 45°",
                "icon": "📐",
                "angle_desc": "Commercial 3/4 perspective shot at a 45-degree angle. Displays front facade, side depth, cantilevered architecture, and top surface edge in three-dimensional clarity.",
                "dalle_angle": "3/4 commercial perspective angle looking at front and side depth at 45 degrees."
            },
            {
                "id": "vista_2_1_lateral",
                "label": "Vista 3: Lateral Perfil Estricto (90°)",
                "short_name": "Lateral 90°",
                "icon": "➡️",
                "angle_desc": "Strict orthogonal 90-degree lateral side profile view. Full silhouette from front edge to back edge with zero perspective vanishing points, showcasing vertical silhouette, panel thickness, and structure.",
                "dalle_angle": "Strict 90-degree side profile orthogonal view, perfectly flat lateral elevation."
            },
            {
                "id": "vista_2_1_picada_frontal",
                "label": "Vista 4: Picada Alta / Semi-Cenital Frontal (60°-70°)",
                "short_name": "Picada Alta 65°",
                "icon": "↗️",
                "angle_desc": "High-angle elevated 3/4 semi-top perspective shot at 60°-70° looking down at the front. The top wooden surface AND front facade with drawers and circular handles are clearly visible with three-dimensional depth and rich wood grain.",
                "dalle_angle": "Elevated high-angle shot from above at 65 degrees looking down at the front, showing both the top wooden surface and front drawers in depth."
            },
            {
                "id": "vista_2_1_superior_cenital",
                "label": "Vista 5: Superior Cenital Plano Directo (90° Desde Arriba)",
                "short_name": "Superior Cenital 90°",
                "icon": "🔝",
                "angle_desc": "Strict 90-degree orthogonal overhead flat top-down view (plan view). The camera points vertically straight down from the ceiling directly perpendicular to the flat top wooden surface (camera pitch: -90 degrees). The rectangular top wooden surface fills the frame, showcasing the rich continuous horizontal wood grain patterns and edge joins. Zero camera tilt: do NOT angle the camera, do NOT show the front facade, and do NOT show the drawer faces. Pure flat overhead view.",
                "dalle_angle": "Pure 90-degree orthogonal flat overhead top-down view looking straight down at the top surface, flat rectangular wood grain plan view, zero front facade visible, no drawers visible."
            }
        ]

        if has_wood_sample:
            gen_directive_ais = f"""[MANDATORY GENERATION DIRECTIVE - MATERIAL TRANSFER]:
Generate and photograph the {furn_item} ('{furniture_name}') isolated as a master commercial catalog photograph with strict material replacement:
* 100% UNIFORM MONOLITHIC WOOD LOCK: Transform all wooden components (front drawer faces, circular handles, outer casing, side panels, top surface, legs) using the exact timber species, continuous grain flow, and stain tone from IMAGE 2 ('{w_name}': {w_color}, {w_texture}). Zero two-tone mismatch, zero walnut contrast.
* PROPORTIONS & JOINERY: Preserve 100% exact 3D geometry and dimensions ({geom_struct}) from IMAGE 1.
* EXECUTION DIRECTIVE: Immediately render and output the photographic image. Do not output text-only descriptions or commentary."""
        else:
            gen_directive_ais = f"""[MANDATORY GENERATION DIRECTIVE]:
Generate and photograph the {furn_item} ('{furniture_name}') isolated as a master commercial catalog photograph:
* MATERIALS & TEXTURES: Preserve 100% exact original wood grain, timber species, stain tone, and textures ({materials_with_notes}).
* PROPORTIONS & JOINERY: Preserve 100% exact 3D geometry and dimensions ({geom_struct}) from IMAGE 1.
* EXECUTION DIRECTIVE: Immediately render and output the photographic image. Do not output text-only descriptions or commentary."""

        user_notes_ais = f"\n* DIRECTIVA OBLIGATORIA: {user_notes_clean}" if user_notes_clean else ""
        wood_ais_lock_21 = f"Apply 100% monolithic wood from Image 2 ('{w_name}': {w_color}, {w_texture}) across all parts (drawers, circular handles, chassis, top, sides, legs). Continuous horizontal grain flow. ZERO two-tone contrast; NO dark walnut drawers." if has_wood_sample else f"Preserve 100% original authentic wood materials and finishes ({materials_with_notes})."

        individual_results = []
        for v in vistas_2_1_specs:
            extra_neg = ", tilted camera, downward perspective, 3/4 high angle, visible drawer faces, visible front facade" if "cenital" in v["id"] else ""
            
            # Prompt individual conciso y ultra-específico para Google AI Studio (Nano Banana 2.1 / Pro)
            prompt_ais = f"""[MODEL: GEMINI NANO BANANA 2.1 / PRO | COMMERCIAL PHOTOGRAPHY]
• Image 1 (Target Furniture): 3D model, joinery, and 1:1 scale of '{furn_item}'.
• Image 2 (Wood Swatch - Ground Truth): Exact wood species, grain, and stain tone ('{w_name}': {w_color}, {w_texture}).

DIRECTIVES:
1. 100% MONOLITHIC WOOD LOCK: {wood_ais_lock_21}
2. 3D GEOMETRY: Preserve 100% exact dimensions and physical proportions ({geom_struct}) from Image 1.{user_notes_ais}
3. VIEW: {v['label']} - {v['angle_desc']}
4. STUDIO: Pure seamless solid white background (#FFFFFF), studio softbox lighting, 0% ground shadows, razor-sharp 8K commercial photo.

Negative Prompt: two-tone drawers, contrasting dark drawers, walnut drawer faces, wrong wood color, mismatched grain, altered proportions, resized handles, collage, grid, multi-image strip, CGI, render, shadows, backdrop, watermark{extra_neg}."""

            # Prompt individual token-optimizado para ChatGPT / DALL-E 3
            prompt_dal = f"""[COMMAND: COMMERCIAL PRODUCT PHOTOGRAPHY | 35MM RAW MEDIUM FORMAT]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ONE single standalone commercial catalog photo of a {furn_item} ('{furniture_name}').
Camera Angle: {v['dalle_angle']}
CRITICAL: Only 1 single furniture object centered in the image. No multiple angles, no contact sheet, no collage.
Topological Geometry: {geom_struct}.
Materials & Monolithic Lock:
{materials_final_block}
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}
Negative Prompt: two-tone drawers, contrasting drawer wood, dark walnut drawers, misaligned grain, collage, contact sheet, grid, split view, 3d render, cartoon{extra_neg}."""

            individual_results.append({
                "id": v["id"],
                "label": v["label"],
                "short_name": v["short_name"],
                "icon": v["icon"],
                "google_ai_studio": prompt_ais,
                "chatgpt_dalle3": prompt_dal
            })

        # 1 SOLO PROMPT MAESTRO TOKEN-OPTIMIZADO PARA GOOGLE AI STUDIO (Nano Banana 2.1 / Pro)
        prompt_maestro_ais = f"""[MODEL: GEMINI NANO BANANA 2.1 / PRO | 5-VIEW COMMERCIAL CATALOG]
• Image 1 (Target Furniture): 3D model, joinery, and 1:1 scale of '{furn_item}'.
• Image 2 (Wood Swatch - Ground Truth): Exact wood species, grain, and stain tone ('{w_name}': {w_color}, {w_texture}).

DIRECTIVES:
1. 100% MONOLITHIC WOOD LOCK: {wood_ais_lock_21}
2. 3D GEOMETRY: Preserve 100% exact dimensions and physical proportions ({geom_struct}) from Image 1.{user_notes_ais}
3. STUDIO: Pure seamless solid white background (#FFFFFF), studio softbox lighting, 0% ground shadows, razor-sharp 8K commercial photo.

EXECUTION (TURN-BY-TURN):
Generate ONE single standalone photo per turn.
- CURRENT TURN: Generate ONLY Vista 1 (Frontal Directa 0°: flat eye-level elevation showing facade, drawers, circular handles, and joinery).
Conclude your response with: "📸 Vista 1 generada. Escribe 'foto' para generar la Vista 2 (3/4 Perspectiva 45°)."
- Subsequent views (triggered ONLY by typing 'foto'):
  2. Vista 2: 3/4 Perspectiva 45° (front facade, side depth).
  3. Vista 3: Lateral Perfil Estricto 90° (flat side elevation).
  4. Vista 4: Picada Alta / Semi-Cenital 65° (high angle showing top surface AND front drawers/handles in depth).
  5. Vista 5: Superior Cenital Plano 90° (strict perpendicular overhead view, top wood surface only, zero front drawers visible).

Negative Prompt: two-tone drawers, contrasting dark drawers, walnut drawer faces, wrong wood color, mismatched grain, altered proportions, resized handles, collage, grid, multi-image strip, CGI, render, shadows, backdrop, watermark."""

        # 1 SOLO PROMPT MAESTRO PARA CHATGPT / DALL-E 3
        wood_dal_maestro_21 = f" Apply exact wood species, grain flow, and stain tone from the wood sample reference: ({materials_with_notes})." if has_wood_sample else f", materials: ({materials_with_notes})"
        prompt_maestro_dal = f"""[COMMAND: MULTI-IMAGE SEQUENTIAL GENERATION FOR COMMERCIAL CATALOG]
[ENGINE: Disable CGI, Disable Octane Render, Force 35mm Medium Format RAW Photography]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate ALL 5 SEPARATE STANDALONE commercial catalog photos in sequence for a {furn_item} ('{furniture_name}'){wood_dal_maestro_21}.

[IMAGE REFERENCES & GROUND TRUTH]:
- Target Furniture: 3D model and facade proportions from '{furniture_name}'.
- Wood / Color Sample: Exact wood species, continuous grain flow, and stain tone from wood reference ('{w_name}': {w_color}, {w_texture}).

[CRITICAL MONOLITHIC WOOD LOCK]:
* 100% UNIFORM MONOLITHIC WOOD: Entire unit (front drawer faces, circular handles, chassis, side panels, top surface, legs) must share the identical wood finish and grain from the wood swatch.
* ZERO TWO-TONE FINISH: Do NOT make drawer faces dark walnut or contrasting color.

CRITICAL EXECUTION: Execute the image tool separately for EACH view below so they are outputted as 5 distinct, separate image files. DO NOT combine them into a collage or split canvas.

1. FIRST IMAGE (View 1): Front View (0° flat eye-level elevation showing facade and joinery).
2. SECOND IMAGE (View 2): 3/4 Perspective View (45° angle showing front and side depth).
3. THIRD IMAGE (View 3): Side Profile (90° orthogonal flat lateral elevation).
4. FOURTH IMAGE (View 4): Elevated High-Angle Semi-Top View (65° shot showing top surface AND front drawers in depth).
5. FIFTH IMAGE (View 5): Pure 90-Degree Orthogonal Flat Overhead Top-Down View (camera perpendicular looking straight down at the top wooden surface, plan view, zero front facade visible, no drawers visible).

Topological Geometry: {geom_struct}.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}
Negative Prompt: two-tone drawers, contrasting drawer wood, dark walnut drawers, misaligned grain, collage, contact sheet, grid, split view, 3d render, cartoon."""

        return {
            "google_ai_studio": prompt_maestro_ais,
            "chatgpt_dalle3": prompt_maestro_dal,
            "midjourney_v6": f"Commercial catalog 5 separate shots of {furn_item}, {geom_struct}, white background #FFFFFF, {hardware_str} --ar 16:9 --v 6.1 --style raw",
            "individual_vistas": individual_results
        }

    def generate_material_swap_prompts(
        self,
        mode: str,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filenames: Optional[List[str]] = None,
        fabric_filenames: Optional[List[str]] = None,
        reference_filenames: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Genera prompts individuales para CAMBIO DE MATERIAL (Madera, Tela, o Dual)
        con alta densidad de tokens, compatible con Google AI Studio, ChatGPT (DALL-E 3) y Midjourney.
        """
        ma = furniture_analysis or {}
        fa = fabric_analysis or {}
        wa = wood_analysis or {}

        furn_item = ma.get("furniture_item", furniture_name)
        if "directives:" in str(furn_item).lower():
            furn_item = furniture_name
        if not furn_item:
            furn_item = furniture_name
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials")
        camera_angle = ma.get("camera_angle", "0-degree frontal and 3/4 perspective")
        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()

        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""[MANDATORY USER OVERRIDE DIRECTIVES]:
* {user_notes_clean}
* Strictest adherence required: Ensure every specification, dimension, color tone, and material above is natively integrated without exceptions."""
            materials_with_notes = f"{existing_mats} (User note: {user_notes_clean})"
        else:
            user_directives_block = ""
            materials_with_notes = existing_mats

        furn_file_str = ", ".join(f"'{fn}'" for fn in furniture_filenames) if furniture_filenames else f"'{furniture_name}'"
        wood_file_str = ", ".join(f"'{fn}'" for fn in wood_filenames) if wood_filenames else ""
        fab_file_str = ", ".join(f"'{fn}'" for fn in fabric_filenames) if fabric_filenames else ""

        w_name = wa.get("name", "Roble Claro Natural / White Oak Swatch") if wa else "Roble Claro Natural / White Oak Swatch"
        w_color = wa.get("color_description", materials_with_notes) if wa else materials_with_notes
        w_texture = wa.get("texture_detail", "authentic wood grain pores") if wa else "authentic wood grain pores"
        w_light = wa.get("light_interaction", "satin matte sheen") if wa else "satin matte sheen"

        if "fallback" in w_name.lower() or "detected" in str(w_color).lower() or not w_color:
            w_name = "Roble Claro Natural / White Oak Swatch"
            w_color = "warm light honey natural timber tone (#D5A869) with subtle amber undertones"
            w_texture = "fine continuous horizontal wood grain pores, smooth satin finish"
            w_light = "matte satin sheen"

        f_name = fa.get("name", "Fabric Sample") if fa else "Fabric Sample"
        f_color = fa.get("color_description", "true-to-life textile color") if fa else "true-to-life textile color"
        f_texture = fa.get("texture_detail", "dense textured textile weave") if fa else "dense textured textile weave"
        f_light = fa.get("light_interaction", "matte fabric surface") if fa else "matte fabric surface"

        if mode == "dual":
            wood_label = f" [File: {wood_file_str}]" if wood_file_str else ""
            fab_label = f" [File: {fab_file_str}]" if fab_file_str else ""
            id_block = f"""[INPUT IMAGE REFERENCES]:
- IMAGE 1 (TARGET FURNITURE) [File: {furn_file_str}]: Reference for 3D model, contours, joinery, and proportions ('{furn_item}').
- IMAGE 2 (WOOD SAMPLE){wood_label}: Reference for wood species, continuous grain flow, warmth, and stain tone ('{w_name}': {w_color}, {w_texture}, {w_light}).
- IMAGE 3 (FABRIC SWATCH){fab_label}: Reference for upholstery textile weave, density, and hue ('{f_name}': {f_color}, {f_texture}, {f_light})."""

            prompt_ais = f"""[TASK: COMMERCIAL PRODUCT PHOTOGRAPHY | 8K RAW | STUDIO ISOLATION]
{id_block}

[MANDATORY GENERATION COMMAND]:
Generate and photograph the {furn_item} ('{furniture_name}') isolated as a master e-commerce commercial catalog photograph with strict material replacement:
* UPHOLSTERY FABRIC LOCK: Accurately replace all upholstery fabric with the exact textile weave pattern and chromatic hue from FABRIC SWATCH ('{f_name}': {f_color}, {f_texture}, {f_light}). Scale down weave pattern for macroscopic realism without solid flat washes.
* 100% UNIFORM MONOLITHIC WOOD LOCK: Replace all wooden components (legs, frame, casing, drawers) using the exact timber species, grain pattern, and stain tone from WOOD SAMPLE ('{w_name}': {w_color}, {w_texture}, {w_light}). Natural continuous anatomical grain flow. Zero two-tone mismatch.
* TOPOLOGICAL & GEOMETRIC LOCK: Strictly preserve the exact 3D geometry ({geom_struct}), cushions, armrests, seams, and proportions from TARGET FURNITURE. Zero distortion, zero leg stretching.
* EXECUTION DIRECTIVE: Immediately render and output the photographic image. Do not output text-only descriptions or commentary.

{user_directives_block if user_notes_clean else ""}

[ENVIRONMENT & HARDWARE]:
- {white_bg}
- {hardware_str}

Negative Prompt: CGI, 3D render, cartoon, plastic, two-tone drawers, wrong wood color, dark drawers, mismatched grain, wrong fabric color, generic fabric, loss of weave, faded texture, altered geometry, perspective distortion, floor shadows, drop shadows, grey backdrop, room, text, labels, watermark."""

            prompt_dalle = f"""[COMMAND: ULTRA-HD RAW COMMERCIAL PHOTOGRAPHY]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate a photorealistic, ultra-high-definition e-commerce catalog image of a {furn_item} ('{furniture_name}').
Crucial Structure: {geom_struct}.
Material Design: The upholstery must be a highly detailed {f_name} ({f_texture}) in {f_color}. The wooden components (legs, frame, casing) must be 100% monolithic {w_name} ({w_texture}) with {w_color} and {w_light}. Zero two-tone drawers.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}
Negative Prompt: CGI, 3D render, shadows, room, two-tone drawers, dark walnut drawers, text, watermark."""

            prompt_mj = f"Commercial product photography, {furn_item} isolated on pure solid white background #FFFFFF, {geom_struct}, upholstered in {f_color} {f_texture}, {w_name} wooden legs and frame ({w_color}, {w_texture}). {hardware_str} --no shadows, room, CGI, text --ar 1:1 --v 6.1 --style raw"

        elif mode == "fabric_only":
            fab_label = f" [File: {fab_file_str}]" if fab_file_str else ""
            id_block = f"""[INPUT IMAGE REFERENCES]:
- IMAGE 1 (TARGET FURNITURE) [File: {furn_file_str}]: Reference for 3D model, contours, joinery, and proportions ('{furn_item}').
- IMAGE 2 (FABRIC SWATCH){fab_label}: Reference for upholstery textile weave, yarn density, and hue ('{f_name}': {f_color}, {f_texture}, {f_light})."""

            prompt_ais = f"""[TASK: COMMERCIAL PRODUCT PHOTOGRAPHY | 8K RAW | STUDIO ISOLATION]
{id_block}

[MANDATORY GENERATION COMMAND]:
Generate and photograph the {furn_item} ('{furniture_name}') isolated as a master e-commerce commercial catalog photograph with strict material replacement:
* UPHOLSTERY FABRIC LOCK: Accurately replace all upholstery fabric with the exact textile weave pattern and chromatic hue from FABRIC SWATCH ('{f_name}': {f_color}, {f_texture}, {f_light}). Scale down weave pattern for macroscopic realism without solid flat washes.
* WOOD PRESERVATION LOCK: Strictly preserve the original wooden components (legs, frame) from TARGET FURNITURE without altering their original grain or finish.
* TOPOLOGICAL & GEOMETRIC LOCK: Strictly preserve the exact 3D geometry ({geom_struct}), cushions, armrests, seams, and proportions from TARGET FURNITURE. Zero distortion, zero leg stretching.
* EXECUTION DIRECTIVE: Immediately render and output the photographic image. Do not output text-only descriptions or commentary.

{user_directives_block if user_notes_clean else ""}

[ENVIRONMENT & HARDWARE]:
- {white_bg}
- {hardware_str}

Negative Prompt: CGI, 3D render, cartoon, plastic, altered wood, changed legs, wrong fabric color, generic fabric, loss of weave, faded texture, altered geometry, perspective distortion, floor shadows, drop shadows, grey backdrop, room, text, labels, watermark."""

            prompt_dalle = f"""[COMMAND: ULTRA-HD RAW COMMERCIAL PHOTOGRAPHY]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate a photorealistic catalog image of a {furn_item} ('{furniture_name}').
Structure: {geom_struct}. Original wooden parts strictly preserved.
Material: Upholstery meticulously crafted from {f_name} ({f_texture}, {f_color}).
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}
Negative Prompt: CGI, 3D render, shadows, room, altered wood, text, watermark."""

            prompt_mj = f"Commercial product photography, {furn_item} isolated on pure solid white background #FFFFFF, {geom_struct}, upholstered in {f_name} ({f_color}, {f_texture}), original wooden legs preserved. {hardware_str} --no shadows, room, CGI, text --ar 1:1 --v 6.1 --style raw"

        else: # wood_only
            wood_label = f" [File: {wood_file_str}]" if wood_file_str else ""
            id_block = f"""[INPUT IMAGE REFERENCES]:
- IMAGE 1 (TARGET FURNITURE) [File: {furn_file_str}]: Reference for 3D model, contours, joinery, and proportions ('{furn_item}').
- IMAGE 2 (WOOD SAMPLE){wood_label}: Reference for wood species, continuous anatomical grain flow, warmth, and stain tone ('{w_name}': {w_color}, {w_texture}, {w_light})."""

            prompt_ais = f"""[TASK: COMMERCIAL PRODUCT PHOTOGRAPHY | 8K RAW | STUDIO ISOLATION]
{id_block}

[MANDATORY GENERATION COMMAND]:
Generate and photograph the {furn_item} ('{furniture_name}') isolated as a master e-commerce commercial catalog photograph with strict material replacement:
* 100% UNIFORM MONOLITHIC WOOD LOCK: Replace all wooden components (front drawer faces, circular handles, outer casing, side panels, top surface, legs) using the exact timber species, grain pattern, and stain tone from WOOD SAMPLE ('{w_name}': {w_color}, {w_texture}, {w_light}). Natural continuous horizontal grain flow. Zero two-tone mismatch, zero dark walnut contrast.
* FABRIC PRESERVATION LOCK: Strictly preserve the original upholstery fabric, color, and weave from TARGET FURNITURE without altering cushions or textile parts.
* TOPOLOGICAL & GEOMETRIC LOCK: Strictly preserve the exact 3D geometry ({geom_struct}), contours, seams, and proportions from TARGET FURNITURE. Zero distortion, zero leg stretching.
* EXECUTION DIRECTIVE: Immediately render and output the photographic image. Do not output text-only descriptions or commentary.

{user_directives_block if user_notes_clean else ""}

[ENVIRONMENT & HARDWARE]:
- {white_bg}
- {hardware_str}

Negative Prompt: CGI, 3D render, cartoon, plastic, two-tone drawers, wrong wood color, dark drawers, walnut drawer faces, mismatched grain, altered fabric, changed upholstery, altered geometry, perspective distortion, floor shadows, drop shadows, grey backdrop, room, text, labels, watermark."""

            prompt_dalle = f"""[COMMAND: ULTRA-HD RAW COMMERCIAL PHOTOGRAPHY]
[SHADOWS: 0% ground shadows, 0% drop shadows, pure #FFFFFF digital cutout]
Generate a photorealistic catalog image of a {furn_item} ('{furniture_name}').
Structure: {geom_struct}. Original upholstery strictly preserved.
Wood Material: Wooden components (legs, frame, casing, drawer faces, top) crafted 100% monolithically from {w_name} ({w_texture}, {w_color}, {w_light}). Zero two-tone finish, zero dark walnut drawer contrast.
{user_directives_block if user_notes_clean else ""}
Environment: Pure seamless solid white background (#FFFFFF) with zero shadows.
Camera: {hardware_str}
Negative Prompt: CGI, 3D render, shadows, room, two-tone drawers, dark walnut drawers, altered fabric, text, watermark."""

            prompt_mj = f"Commercial product photography, {furn_item} isolated on pure solid white background #FFFFFF, {geom_struct}, original upholstery preserved, wooden components replaced with {w_name} ({w_color}, {w_texture}, {w_light}). {hardware_str} --no shadows, room, CGI, altered fabric, two-tone drawers, text --ar 1:1 --v 6.1 --style raw"

        return {
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_mj,
            "individual_vistas": []
        }

    def generate_extraction_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> Dict[str, Any]:
        """
        Genera prompts para EXTRAER MUEBLE (FONDO BLANCO):
        - Mueble centrado en la foto.
        - Fondo blanco puro seamless (#FFFFFF).
        - CERO sombras (0% ground shadows, 0% drop shadows, sin reflejos).
        - Máxima fidelidad de materiales, colores y geometría.
        """
        ma = furniture_analysis or {}
        furn_item = ma.get("furniture_item", furniture_name)
        if "directives:" in furn_item.lower():
            furn_item = furniture_name
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials and colors")
        hardware_str = self._build_photo_hardware_str()
        
        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""
MANDATORY DIRECTIVES APPLIED:
{user_notes_clean}
* Strictly incorporate all user specifications without altering core geometry."""
            materials_with_notes = f"{existing_mats} (User note: {user_notes_clean})"
        else:
            user_directives_block = ""
            materials_with_notes = existing_mats

        has_wood_sample = ma.get("has_wood_sample", False)
        if has_wood_sample:
            preservation_block = f"""PRESERVATION LOCK (WOOD SAMPLE & GEOMETRY FIDELITY):
- WOOD FINISH TRANSFER: Faithfully apply the exact wood species, authentic grain flow, stain tone, warmth, and texture from the wood reference photo ({materials_with_notes}) to all wooden surfaces.
- GEOMETRY & TOPOLOGY: Retain 100% exact structural geometry, leg joinery, cushion contours, armrests, and proportions ({geom_struct}).
- ZERO REDESIGN: Do not modify, reinterpret, or stylize the furniture piece."""
        else:
            preservation_block = f"""PRESERVATION LOCK (CASILLA 1 FIDELITY):
- MATERIALS & TEXTURES: Lock exact wood finish, species, authentic grain flow, stain tone, and fabric weave texture ({materials_with_notes}).
- GEOMETRY & TOPOLOGY: Retain 100% exact structural geometry, leg joinery, cushion contours, armrests, and proportions ({geom_struct}).
- ZERO REDESIGN: Do not modify, reinterpret, or stylize the furniture piece."""

        # Prompt para Google AI Studio / Imagen 3
        prompt_ais = f"""[TASK: ISOLATED PRODUCT PHOTOGRAPHY - PURE WHITE BACKGROUND CUTOUT]
Photograph the {furn_item} ('{furniture_name}') shown in the reference image, isolated as a clean digital commercial catalog cutout.

CRITICAL POSITIONING & ISOLATION:
- SUBJECT POSITION: The furniture piece must be placed dead-center in the composition with balanced margins.
- BACKGROUND: Pure solid seamless white background (#FFFFFF) across the entire frame.
- ZERO SHADOWS MANDATE: 0% ground shadows, 0% drop shadows, 0% contact floor shadows, 0% cast shadows. Zero floor reflections. Clean crisp edges with absolute isolation from any background elements.
- NO PROPS: No walls, no floors, no interior decor, no studio equipment, no backdrop stands.

{preservation_block}

{user_directives_block if user_notes_clean else ""}
CAMERA & HARDWARE:
{hardware_str}

Negative Prompt: ground shadows, floor shadows, drop shadows, cast shadow, ambient occlusion shadow, grey backdrop, gradient background, floor texture, room interior, wall, floorboards, text, labels, watermark, brand logo, border, frame, altered geometry, altered wood color, CGI, 3D render, cartoon, oversmoothed."""

        # Prompt para ChatGPT / DALL-E 3
        prompt_dalle = f"""[COMMAND: COMMERCIAL ISOLATED FURNITURE CUTOUT ON PURE WHITE BACKGROUND]
[SHADOWS: 0% GROUND SHADOWS, 0% DROP SHADOWS, 0% CONTACT SHADOWS, ZERO REFLECTIONS]
[BACKGROUND: Pure solid clean #FFFFFF seamless white background, no floor, no wall]
Photograph the exact {furn_item} ('{furniture_name}') perfectly centered in the frame.
Materials: {materials_with_notes}.
Topological Geometry: {geom_struct}.
Camera: Level commercial eye-line perspective, perfectly balanced centering.
Execution: Clean commercial product cutout. Keep every cushion, leg, wood grain line, and fabric fiber 100% identical to the reference image. Zero floor shadows underneath.
{user_directives_block if user_notes_clean else ""}
Negative Prompt: shadows, drop shadows, floor shadows, grey gradient, studio floor, room scene, 3D render, text, watermark."""

        # Prompt para Midjourney
        prompt_mj = f"Commercial luxury catalog shot of {furn_item}, perfectly centered on pure seamless white background #FFFFFF, 0% floor shadows, zero drop shadows, materials: {materials_with_notes}, {geom_struct}, {hardware_str} --ar 1:1 --v 6.1 --style raw --no shadows, drop shadow, floor, floorboards, grey backdrop"

        return {
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_mj,
            "individual_vistas": []
        }

    def generate_hd_enhancement_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> Dict[str, Any]:
        """
        Genera prompts para MEJORA HD (SIN CAMBIO DE COLOR, TEXTURA O GEOMETRÍA):
        - Remasterización comercial 8K macro.
        - Elimina pixelado, compresión y borrosidad.
        - CANDADO ESTRICTO: 100% fidelidad de color, grano de madera, tela y topología.
        - Enfoque apilado (focus stacking) con nitidez cristalina en cada poro y fibra.
        """
        ma = furniture_analysis or {}
        furn_item = ma.get("furniture_item", furniture_name)
        if "directives:" in furn_item.lower():
            furn_item = furniture_name
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        existing_mats = ma.get("existing_materials", "original materials and exact colors")
        hardware_str = self._build_photo_hardware_str()

        user_notes_clean = notas_usuario.strip() if notas_usuario else ""
        if user_notes_clean:
            user_directives_block = f"""
MANDATORY QUALITY DIRECTIVES:
{user_notes_clean}
* Strictly maintain all specifications above while maximizing photographic sharpness."""
            materials_with_notes = f"{existing_mats} (Note: {user_notes_clean})"
        else:
            user_directives_block = ""
            materials_with_notes = existing_mats

        has_wood_sample = ma.get("has_wood_sample", False)
        wood_hd_directive = f"- TEXTURE & WOOD LOCK: Faithfully remaster and transfer the authentic wood species grain pattern from the wood reference photo ({materials_with_notes})." if has_wood_sample else f"- TEXTURE LOCK: Strictly retain the authentic wood species grain pattern ({materials_with_notes}). Do not replace with generic synthetic wood or fake flat veneer."

        prompt_ais = f"""[TASK: 8K COMMERCIAL RESTORATION & ULTRA-HD MACRO CLARITY REMASTER]
Generate a hyper-sharp, razor-focused, master-quality catalog commercial photograph of the {furn_item} ('{furniture_name}') from the reference image.

CRITICAL CLARITY DIRECTIVE (ZERO PIXELATION, ZERO BLUR):
- ULTRA-RESOLUTION DETAIL: Completely eliminate all blur, noise, compression artifacts, and pixelation.
- SHARPNESS & TEXTURE ENHANCEMENT: Render every individual wood fiber, finger-joint seam, butcher-block union, pore, satin sheen, and fabric weave thread in ultra-high tactile optical clarity.
- FOCUS STACKING: Deep field-of-depth focus stacking (f/11). From front edge to back contours, every single plane is tack-sharp and crystalline.

STRICT PRESERVATION LOCK (ABSOLUTELY NO GEOMETRY OR COLOR DRIFT):
- COLOR LOCK: Preserve the 100% exact original color hue, warmth, and saturation without cooling, warming, or tint shifts.
{wood_hd_directive}
- GEOMETRY LOCK: Lock the exact physical dimensions, joinery, bevels, cushions, and silhouette ({geom_struct}). Do not redesign, reshape, or reconfigure any element.

{user_directives_block if user_notes_clean else ""}
ENVIRONMENT: Pristine solid pure white catalog studio background (#FFFFFF) with balanced soft studio fill.
CAMERA & OPTICS:
{hardware_str}

Negative Prompt: blurry, out of focus, motion blur, soft focus, pixelated, low resolution, jpeg compression artifacts, noise, grain noise, flat wash, oversmoothed, plastic texture, fake wood, cartoon, CGI, 3D render, redesign, changed shape, altered colors, shifted tones, desaturated, discolored, warped lines, watermark, text, labels."""

        prompt_dalle = f"""[COMMAND: ULTRA-HD 8K COMMERCIAL PRODUCT REMASTER]
[ENGINE: Disable CGI, Disable Octane Render, Medium Format Commercial RAW Photography]
[FIDELITY MANDATE: ZERO color drift, ZERO geometry changes, ZERO texture loss]
Create an ultra-sharp, high-definition catalog photograph remaster of the {furn_item} ('{furniture_name}').
Optical details: Focus stacking, crystal-clear micro-texture showing authentic wood grain seams, pores, and fabric weave threads in razor-sharp focus.
Materials: {materials_with_notes}.
Geometry: {geom_struct}.
Environment: Pure seamless white studio background (#FFFFFF).
{user_directives_block if user_notes_clean else ""}
Negative Prompt: pixelated, blurry, low-res, compression noise, smoothed texture, plastic, altered color, redesigned geometry, 3d render, cartoon, watermark, text."""

        prompt_mj = f"8k commercial catalog hyper-detailed photograph of {furn_item}, {geom_struct}, authentic wood grain micro-texture, tack-sharp macro focus, zero blur, materials: {materials_with_notes}, solid white background #FFFFFF, {hardware_str} --ar 1:1 --v 6.1 --style raw --no blur, pixelated, noise, smooth plastic, altered geometry, text"

        return {
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_mj,
            "individual_vistas": []
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
            wood_analysis=wood_analysis,
            fabric_analysis=fabric_analysis,
            notas_usuario=notas_usuario
        )

ai_prompt_service_v5 = AIPromptServiceV5()

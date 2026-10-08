import os
import io
import json
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from PIL import Image
from pydantic import BaseModel, Field

# Modelos Pydantic para Structured Outputs Avanzados
class MaterialAnalysisV3(BaseModel):
    name: str = Field(description="Nombre comercial corto y premium (ej. Heathered Salt-and-Pepper Bouclé)")
    color_description: str = Field(description="Descripción cromática exacta (RGB/Hex conceptual) y subtonos")
    texture_detail: str = Field(description="Estructura micro-textil (ej. dense nubby loops over cool grey under-weave)")
    light_interaction: str = Field(description="Cómo interactúa con la luz (ej. absorbs light, highly reflective, matte satin sheen)")

class FurnitureAnalysisV3(BaseModel):
    furniture_item: str = Field(description="Nombre y estilo arquitectónico (ej. mid-century modern curved modular sofa)")
    camera_angle: str = Field(description="Ángulo de cámara en grados y perspectiva geométrica (ej. 45-degree elevated isometric, strict 0-degree frontal)")
    lighting_direction: str = Field(description="Dirección exacta de la luz y tipo de sombra (ej. Key light from top-left, soft diffuse fill)")
    geometric_structure: str = Field(description="Descripción topológica de la forma (ej. sharp 90-degree corners, sweeping organic curves)")
    existing_materials: str = Field(description="Tapicería y partes rígidas actuales con su color y textura exacta")

class AIPromptServiceV3:
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
            return MaterialAnalysisV3(
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
                    response_schema=MaterialAnalysisV3,
                    temperature=0.1
                )
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"[AIPromptServiceV3] Error analyzing material: {e}")
            return MaterialAnalysisV3(
                name=f"Fallback Material ({material_type})",
                color_description="detected color",
                texture_detail="detected texture",
                light_interaction="satin"
            ).model_dump()

    def analyze_furniture_for_enhancement(self, furniture_bytes, api_key: Optional[str] = None) -> Dict[str, Any]:
        key = self.get_api_key(api_key)
        if not key:
            return FurnitureAnalysisV3(
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
                    response_schema=FurnitureAnalysisV3,
                    temperature=0.1
                )
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"[AIPromptServiceV3] Error analyzing furniture: {e}")
            return FurnitureAnalysisV3(
                furniture_item="furniture piece",
                camera_angle="original perspective",
                lighting_direction="original lighting",
                geometric_structure="original shape",
                existing_materials="original fabric and wood"
            ).model_dump()

    def get_img_refs(self, start_idx: int, count: int) -> str:
        if count <= 1: return f"Image {start_idx}"
        if count == 2: return f"Images {start_idx} and {start_idx + 1}"
        nums = list(range(start_idx, start_idx + count))
        return "Images " + ", ".join(map(str, nums[:-1])) + f", and {nums[-1]}"

    def _build_photo_hardware_str(self) -> str:
        return "Shot on Hasselblad H6D-100c medium format, 120mm macro lens, f/11 aperture for maximum sharp depth of field, 8k resolution, raw hyper-realistic commercial catalog photography, focus stacking, crisp architectural clarity."

    def _build_white_isolation_str(self) -> str:
        return "ENVIRONMENT: Extract ONLY the furniture piece. Preserve its exact color, texture, and geometry (wood, metal, and fabric completely intact). Place it perfectly CENTERED on a pure seamless solid white background (#FFFFFF), with zero floor shadows, no drop shadows, and no harsh reflections. CRITICAL: DO NOT include any text, typography, watermark, letters, numbers, color chips, or palettes."

    def generate_extraction_prompt(self, furniture_name: str, analysis: Optional[Dict[str, Any]] = None, notas_usuario: str = "") -> Dict[str, str]:
        ma = analysis or {}
        furn_item = ma.get("furniture_item", furniture_name)
        geom_struct = ma.get("geometric_structure", "original geometry")
        camera_angle = ma.get("camera_angle", "original perspective")
        mats = ma.get("existing_materials", "original fabric and wood")
        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()

        notes_part = f"\nSPECIAL USER DIRECTIVES: {notas_usuario}" if notas_usuario and notas_usuario.strip() else ""

        prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Image Editor.
TASK: Cleanly extract ONLY the furniture piece ({furn_item}) from Image 1.
CRITICAL CHROMATIC & TEXTURAL FIDELITY:
- Maintain 100% exact original upholstery color (hue, saturation, brightness) and textile weave: [{mats}].
- Maintain 100% exact wooden/metal leg finish, tone, and grain.
- Do NOT shift colors, do NOT desaturate, and do NOT alter tones.
GEOMETRY & CAMERA:
- Strictly lock camera to {camera_angle}.
- Preserve exact structural topology, cushions, seams, and proportions: {geom_struct}.
{white_bg}
HARDWARE: {hardware_str}{notes_part}

Negative Prompt: shadows, drop shadows, floor shadows, reflections, room background, dark background, altered color, color shift, changed texture, altered geometry, text, letters, numbers, watermark, labels."""

        prompt_dalle = f"""Generate a hyper-realistic commercial catalog photograph of a {furn_item}.
Camera/Geometry: Strict {camera_angle}, preserving {geom_struct}.
Materials: The exact original materials ({mats}) must be preserved with microscopic fidelity and ZERO color shift.
Environment: Digitally isolated on a pure seamless solid white background (#FFFFFF) with zero shadows.{notes_part}
Hardware: {hardware_str}"""

        prompt_mj = f"""Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}. Exact materials and color preserved: {mats}. Shot at {camera_angle}. {hardware_str}{notes_part} --no shadows, drop shadows, grey background, room, text, labels, watermark, CGI --ar 1:1 --v 6.1 --style raw"""

        return {
            "google_ai_studio": prompt_ai_studio,
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_mj
        }

    def generate_material_swap_prompt_v3(
        self,
        mode: str,
        furniture_name: str,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        num_furniture_images: int = 1,
        notas_usuario: str = ""
    ) -> Dict[str, str]:
        
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
        camera_angle = ma.get("camera_angle", "original perspective")
        lighting_dir = ma.get("lighting_direction", "studio lighting")
        geom_struct = ma.get("geometric_structure", "original structural geometry")

        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()
        notes_part = f"\nSPECIAL USER DIRECTIVES: {notas_usuario}" if notas_usuario and notas_usuario.strip() else ""

        dalle_defense = "[ENGINE: Disable CGI, Disable Octane Render, Disable 3D Models, Force 35mm RAW Photography, Force real-world textile micro-imperfections]"
        dalle_shadows = "[SHADOWS: 0% ground shadows, 0% drop shadows, strict digital cutout]"

        if mode == "dual":
            prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Editor.
IMAGE IDENTIFICATION (Order-Independent):
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
- FABRIC SWATCH: Locate the image containing the fabric swatch ('{f_name}').
- WOOD SAMPLE: Locate the image containing the wood texture sample ('{w_name}').

TASK: Accurately replace BOTH the fabric upholstery AND the wooden components on the TARGET FURNITURE using the samples provided.
TARGET ITEM: {furn_item}.
GEOMETRY & CAMERA: Strictly lock camera to {camera_angle}. Preserve exact topology: {geom_struct}. Replicate original lighting: {lighting_dir}.
{white_bg}
HARDWARE: {hardware_str}
FABRIC APPLICATION: Apply the exact material from FABRIC SWATCH ('{f_name}'). Color: {f_color}. Texture: {f_texture}. Interaction: {f_light}. Scale down texture dramatically (98% reduction) for macroscopic realism. Preserve exact fabric hue with zero color drift.
WOOD APPLICATION: Apply the exact material from WOOD SAMPLE ('{w_name}'). Color: {w_color}. Grain: {w_texture}. Interaction: {w_light}. Anatomical grain flow.{notes_part}

Negative Prompt: CGI, 3D render, plastic, generic fabric, loss of weave, suede, velvet, leather, flat wood, altered geometry, perspective distortion, floor shadows, grey background, text, letters, numbers."""

            prompt_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a hyper-realistic commercial catalog photograph of a {furn_item} ('{furniture_name}').
Camera/Geometry: Locked at {camera_angle}. Structural topology: {geom_struct}.
Lighting: {lighting_dir}.
Materials: The upholstery is meticulously crafted from {f_name} ({f_texture}, {f_color}, {f_light}). The wooden base/legs are carved from {w_name} ({w_texture}, {w_color}, {w_light}).
Environment: {white_bg}{notes_part}
Hardware constraints: {hardware_str}"""

            prompt_mj = f"""Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}. Upholstered in {f_name} ({f_color}, {f_texture}), wooden components are {w_name} ({w_color}, {w_texture}). Shot at {camera_angle}, {lighting_dir}. {hardware_str}{notes_part} --no floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic, suede, velvet, leather, text --ar 1:1 --v 6.1 --style raw --c 5"""

        elif mode == "fabric_only":
            prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Editor.
IMAGE IDENTIFICATION (Order-Independent):
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
- FABRIC SWATCH: Locate the image containing the fabric swatch ('{f_name}').

TASK: Accurately replace the fabric upholstery on the TARGET FURNITURE using the FABRIC SWATCH.
TARGET ITEM: {furn_item}.
GEOMETRY & CAMERA: Strictly lock camera to {camera_angle}. Preserve exact topology: {geom_struct}. Replicate original lighting: {lighting_dir}. Preserve original wood/legs.
{white_bg}
HARDWARE: {hardware_str}
FABRIC APPLICATION: Apply the exact material from FABRIC SWATCH ('{f_name}'). Color: {f_color}. Texture: {f_texture}. Interaction: {f_light}. Scale down texture dramatically (98% reduction) for macroscopic realism. Strictly lock hue and saturation to reference.{notes_part}

Negative Prompt: CGI, 3D render, plastic, generic fabric, loss of weave, suede, velvet, leather, color shift, altered geometry, perspective distortion, floor shadows, grey background, text, numbers."""

            prompt_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a hyper-realistic commercial catalog photograph of a {furn_item} ('{furniture_name}').
Camera/Geometry: Locked at {camera_angle}. Structural topology: {geom_struct}.
Lighting: {lighting_dir}. Preserve original wooden components precisely.
Materials: The upholstery is meticulously crafted from {f_name} ({f_texture}, {f_color}, {f_light}).
Environment: {white_bg}{notes_part}
Hardware constraints: {hardware_str}"""

            prompt_mj = f"""Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}. Upholstered in {f_name} ({f_color}, {f_texture}), original wooden legs preserved. Shot at {camera_angle}, {lighting_dir}. {hardware_str}{notes_part} --no floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic, suede, velvet, leather, text --ar 1:1 --v 6.1 --style raw --c 5"""

        else: # wood_only
            prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Editor.
IMAGE IDENTIFICATION (Order-Independent):
- TARGET FURNITURE: Locate the image containing the furniture piece ('{furniture_name}').
- WOOD SAMPLE: Locate the image containing the wood texture sample ('{w_name}').

TASK: Accurately replace ONLY the wooden components (legs, frame, base) on the TARGET FURNITURE using the WOOD SAMPLE.
TARGET ITEM: {furn_item}.
GEOMETRY & CAMERA: Strictly lock camera to {camera_angle}. Preserve exact topology: {geom_struct}. Replicate original lighting: {lighting_dir}. Preserve original fabric perfectly.
{white_bg}
HARDWARE: {hardware_str}
WOOD APPLICATION: Apply the exact material from WOOD SAMPLE ('{w_name}'). Color: {w_color}. Grain: {w_texture}. Interaction: {w_light}. Anatomical grain flow.{notes_part}

Negative Prompt: altered fabric, changed upholstery, CGI, 3D render, plastic, flat wood, altered geometry, perspective distortion, floor shadows, grey background, text, numbers."""

            prompt_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a hyper-realistic commercial catalog photograph of a {furn_item} ('{furniture_name}').
Camera/Geometry: Locked at {camera_angle}. Structural topology: {geom_struct}.
Lighting: {lighting_dir}. Preserve original fabric upholstery perfectly.
Materials: The wooden base/legs/frame are carved from {w_name} ({w_texture}, {w_color}, {w_light}).
Environment: {white_bg}{notes_part}
Hardware constraints: {hardware_str}"""

            prompt_mj = f"""Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}. Original upholstery preserved perfectly, wooden components replaced with {w_name} ({w_color}, {w_texture}). Shot at {camera_angle}, {lighting_dir}. {hardware_str}{notes_part} --no altered fabric, floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic, text --ar 1:1 --v 6.1 --style raw --c 5"""

        return {
            "google_ai_studio": prompt_ai_studio,
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_mj
        }

    def generate_multi_perspective_prompts_v3(
        self,
        furniture_name: str,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = ""
    ) -> Dict[str, Dict[str, str]]:
        
        fa = fabric_analysis or {}
        ma = furniture_analysis or {}
        
        f_name = fa.get("name", "Original Fabric")
        f_color = fa.get("color_description", "original color")
        f_texture = fa.get("texture_detail", "original texture")
        f_light = fa.get("light_interaction", "natural reflection")
        
        furn_item = ma.get("furniture_item", furniture_name)
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        hardware_str = self._build_photo_hardware_str()
        white_bg = self._build_white_isolation_str()
        notes_part = f"\nSPECIAL USER DIRECTIVES: {notas_usuario}" if notas_usuario and notas_usuario.strip() else ""
        
        dalle_defense = "[ENGINE: Disable CGI, Force 35mm RAW Photography]"
        dalle_shadows = "[SHADOWS: 0% ground shadows, pure digital cutout]"

        if fa and fa.get("name"):
            mat_str = f"Upholstery must perfectly replicate {f_name} ({f_color}, {f_texture}, {f_light}). Preserve exact hue."
        else:
            mat_str = "Upholstery and materials must strictly replicate the authentic fabric weave, texture, and original color of the furniture in the reference image with 0% color change."

        def build_prompts(
            angle_desc: str,
            geo_constraint: str,
            neg_extras: str,
            environment: Optional[str] = None
        ):
            prompt_environment = environment or white_bg
            mj_environment = (
                "isolated on a pure solid white background #FFFFFF"
                if not environment
                else environment.removeprefix("ENVIRONMENT: ")
            )
            background_negatives = "" if environment else ", background objects, room"
            p_ai = f"""SYSTEM: You are an Architectural Visualization Expert and Master Commercial Photographer.
TASK: Generate a mathematically precise {angle_desc} of the target item.
TARGET ITEM: {furn_item}.
TOPOLOGY: {geom_struct}.
CAMERA/GEOMETRY CONSTRAINT: {geo_constraint}
{prompt_environment}
MATERIALS: {mat_str} Preserve all wooden/metal parts exactly.
HARDWARE: {hardware_str}{notes_part}

Negative Prompt: CGI, plastic, {neg_extras}, perspective distortion, floor shadows{background_negatives}, text, letters, numbers."""

            p_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a mathematically precise {angle_desc} photograph of a {furn_item}.
TOPOLOGY: {geom_struct}.
CAMERA/GEOMETRY CONSTRAINT: {geo_constraint}
MATERIALS: {mat_str}
ENVIRONMENT: {prompt_environment}{notes_part}
HARDWARE: {hardware_str}"""

            p_mj = f"""Commercial luxury product photography, {angle_desc} of {furn_item}, {geom_struct}. {mat_str} {geo_constraint} {hardware_str} {mj_environment}{notes_part} --no {neg_extras}, perspective distortion, floor shadows{background_negatives}, CGI, 3D render, text --ar 1:1 --v 6.1 --style raw"""
            
            return {
                "google_ai_studio": p_ai,
                "chatgpt_dalle3": p_dalle,
                "midjourney_v6": p_mj
            }

        return {
            "vista_de_frente": build_prompts(
                "STRICT DIRECT FRONT VIEW (0-DEGREE FLAT ELEVATION)",
                "Camera perfectly level at eye-line, pointing directly at the front center of the furniture. Zero perspective distortion, pure flat 2D elevation.",
                "angled, isometric, 3/4 view, side view, back view, top view"
            ),
            "vista_lateral": build_prompts(
                "STRICT ORTHOGONAL SIDE PROFILE (90-DEGREE LATERAL VIEW)",
                "Camera positioned at a strict 90-degree angle from the side. Full silhouette profile from side edge to side edge. Zero vanishing points.",
                "front view, 3/4 view, back view, top view, perspective distortion"
            ),
            "vista_lateral_derecha": build_prompts(
                "STRICT ORTHOGONAL RIGHT SIDE PROFILE",
                "Camera positioned perpendicular to the furniture's right side, showing its full right-side silhouette with zero perspective distortion.",
                "front view, left side view, 3/4 view, back view, top view"
            ),
            "vista_lateral_izquierda": build_prompts(
                "STRICT ORTHOGONAL LEFT SIDE PROFILE",
                "Camera positioned perpendicular to the furniture's left side, showing its full left-side silhouette with zero perspective distortion.",
                "front view, right side view, 3/4 view, back view, top view"
            ),
            "vista_3_4_izquierda": build_prompts(
                "3/4 ISOMETRIC PERSPECTIVE FACING LEFT",
                "Classic commercial catalog 3/4 perspective angled 45 degrees, object facing toward the left. Elevated 15 degrees to show depth, seat cushion, and left armrest clearly.",
                "flat front view, strict side view, back view, top view"
            ),
            "vista_3_4_derecha": build_prompts(
                "3/4 ISOMETRIC PERSPECTIVE FACING RIGHT",
                "Classic commercial catalog 3/4 perspective angled 45 degrees, object facing toward the right. Elevated 15 degrees to show depth, seat cushion, and right armrest clearly.",
                "flat front view, strict side view, back view, top view"
            ),
            "vista_desde_arriba": build_prompts(
                "DIRECT TOP-DOWN CENITAL BIRD'S-EYE VIEW",
                "Camera positioned directly above the furniture looking straight down at 90 degrees. True geometric top footprint, showing cushions and depth from above.",
                "front view, side view, legs visible from front, angled view"
            ),
            "vista_3_4_posterior": build_prompts(
                "3/4 REAR ISOMETRIC PERSPECTIVE (BACK 3/4 VIEW)",
                "Commercial catalog 3/4 angle viewed from the rear/back corner at 45 degrees, clearly showing the backrest structure, rear tailoring, and back legs.",
                "front view, front cushions, direct front, top-down"
            ),
            "vista_lifestyle": build_prompts(
                "LIFESTYLE CATALOG VIEW IN A NATURAL ROOM",
                "Show the complete furniture in a believable, tastefully styled luxury interior while preserving its exact identity, proportions, and original colors.",
                "isolated white background, cutout, unrelated furniture, clutter, text",
                environment="ENVIRONMENT: Place the furniture in a refined, realistic interior appropriate to its use, with subtle decor, natural soft daylight, and architectural room context."
            )
        }

    def generate_dynamic_gemini_clone_prompt(self, ref_bytes: bytes, view_bytes: bytes, api_key: Optional[str] = None, notas_usuario: str = "") -> Dict[str, str]:
        key = self.get_api_key(api_key)
        notes_part = f"\nSPECIAL USER DIRECTIVES: {notas_usuario}" if notas_usuario and notas_usuario.strip() else ""
        local_prompt = (
            "Use Image 1 as the exact upholstery color and texture reference, and edit Image 2. "
            "Preserve the furniture identity, geometry, proportions, camera angle, seams, folds, "
            "and lighting in Image 2. Reupholster only the upholstered surfaces to match Image 1 with 0% color change; "
            "make the texture follow the furniture's perspective and contours naturally. "
            "Place the furniture on a pure seamless white background (#FFFFFF) without shadows. "
            "Render as a photorealistic commercial catalog photograph." + notes_part
        )
        if not key:
            return {
                "google_ai_studio": local_prompt,
                "chatgpt_dalle3": local_prompt,
                "midjourney_v6": local_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            img_ref = self._prepare_image(ref_bytes)
            img_view = self._prepare_image(view_bytes)
            
            sys_prompt = f"""You are a Master Prompt Engineer specializing in Generative AI for e-commerce furniture photography.
I am providing you with two images: 
1. Image 1 (Reference): A piece of furniture with the EXACT CORRECT COLOR and TEXTURE.
2. Image 2 (Target View): A different angle of the furniture that has the WRONG COLOR, but the CORRECT GEOMETRY.

Your task is to write the absolute BEST, highly-detailed text prompt to feed into a Diffusion Model (like Google AI Studio / Gemini Image Generation or DALL-E) to recolor Image 2 using the exact color and texture of Image 1.

Perform a DEEP ANALYSIS of Image 1: Extract the precise color tone, fabric weave, and lighting reflection.
Perform a DEEP ANALYSIS of Image 2: Identify camera angle, structural geometry, and folds.

Write a prompt that explicitly commands the AI to:
- Keep the exact geometric structure and camera angle of Image 2.
- Upholster the furniture in Image 2 using the exact color and texture extracted from Image 1 with ZERO color shift.
- Realistically wrap texture around 3D curves and folds.
- Place the furniture centered on a pure seamless white background (#FFFFFF) with zero shadows.
- DO NOT include any text, letters, numbers, watermark, or color palettes.{notes_part}

Output ONLY the prompt text."""

            res = self._call_gemini(
                client=client,
                contents=[sys_prompt, img_ref, img_view],
                config=types.GenerateContentConfig(temperature=0.4)
            )
            
            generated_prompt = res.text.strip()
            
            return {
                "google_ai_studio": generated_prompt,
                "chatgpt_dalle3": generated_prompt,
                "midjourney_v6": generated_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }
        except Exception as e:
            print(f"[AIPromptServiceV3] Error generating dynamic prompt: {e}")
            return {
                "google_ai_studio": local_prompt,
                "chatgpt_dalle3": local_prompt,
                "midjourney_v6": local_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }

    def generate_dynamic_fabric_view_prompt(
        self, fabric_bytes: bytes, view_bytes: bytes, api_key: Optional[str] = None, notas_usuario: str = ""
    ) -> Dict[str, str]:
        key = self.get_api_key(api_key)
        notes_part = f"\nSPECIAL USER DIRECTIVES: {notas_usuario}" if notas_usuario and notas_usuario.strip() else ""
        local_prompt = (
            "Use Image 1 as the exact fabric color, weave, and texture reference. Edit only the "
            "upholstery on the furniture in Image 2. Preserve its identity, geometry, proportions, "
            "camera angle, seams, folds, and lighting. Apply the fabric realistically, following "
            "the furniture's curves and perspective with 0% hue change. "
            "Use a pure seamless white background (#FFFFFF) without shadows. "
            "Render as a photorealistic commercial catalog photograph." + notes_part
        )
        if not key:
            return {
                "google_ai_studio": local_prompt,
                "chatgpt_dalle3": local_prompt,
                "midjourney_v6": local_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            img_fab = self._prepare_image(fabric_bytes)
            img_view = self._prepare_image(view_bytes)
            
            sys_prompt = f"""You are a Master Prompt Engineer specializing in Generative AI for e-commerce photography.
I am providing you with two images: 
1. Image 1 (Fabric Sample): A swatch of fabric that contains the EXACT COLOR and TEXTURE.
2. Image 2 (Furniture View): A specific angle of a piece of furniture.

Your task is to write a highly-detailed text prompt to apply the fabric from Image 1 onto the furniture in Image 2.
Commands:
- Keep the exact geometric structure and camera angle of Image 2.
- Apply the fabric from Image 1 with exact color fidelity and texture scale.
- Pure seamless white background (#FFFFFF) without shadows.
- No text, letters, numbers, or labels.{notes_part}

Output ONLY the prompt text."""

            res = self._call_gemini(
                client=client,
                contents=[sys_prompt, img_fab, img_view],
                config=types.GenerateContentConfig(temperature=0.4)
            )
            
            generated_prompt = res.text.strip()
            
            return {
                "google_ai_studio": generated_prompt,
                "chatgpt_dalle3": generated_prompt,
                "midjourney_v6": generated_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }
        except Exception as e:
            print(f"[AIPromptServiceV3] Error generating dynamic fabric prompt: {e}")
            return {
                "google_ai_studio": local_prompt,
                "chatgpt_dalle3": local_prompt,
                "midjourney_v6": local_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }

    def generate_minimalist_environment_prompt_v3(
        self,
        furniture_name: str,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        num_furniture_images: int = 1,
        tipo_mueble_usuario: str = "",
        medidas_usuario: str = "",
        lugar_casa_usuario: str = "",
        notas_usuario: str = "",
        api_key: Optional[str] = None
    ) -> Dict[str, str]:
        key = self.get_api_key(api_key)
        fa = fabric_analysis or {}
        ma = furniture_analysis or {}
        f_name = fa.get("name")
        f_color = fa.get("color_description")
        f_texture = fa.get("texture_detail")
        
        furn_item = ma.get("furniture_item", furniture_name)
        if tipo_mueble_usuario and tipo_mueble_usuario.strip():
            furn_item = f"{tipo_mueble_usuario.strip()} ({furn_item})"
            
        geom_struct = ma.get("geometric_structure", "original geometric structure")
        camera_angle = ma.get("camera_angle", "original perspective")
        existing_materials = ma.get("existing_materials", "original materials and color")

        if not f_name:
            f_name = "its original upholstery material"
        if not f_color:
            f_color = "its authentic original color"
        if not f_texture:
            f_texture = existing_materials

        hardware_str = self._build_photo_hardware_str()
        target_imgs = self.get_img_refs(2 if (fa and fa.get("name")) else 1, num_furniture_images)
        
        lightings = [
            "soft morning daylight streaming in through sheer floor-to-ceiling linen drapes",
            "golden hour warm sunlight casting delicate linear shadows",
            "soft diffused overcast architectural light with even, flattering illumination",
            "gentle indirect afternoon light accentuating textures without harsh specular glare"
        ]
        architectures = [
            "an open-concept Japandi living space with warm oak slatted accents and polished light microcement floor",
            "a high-end minimalist Scandinavian interior with chalky limestone walls and herringbone natural wood flooring",
            "a luxury contemporary Mediterranean residence with soft textured plaster walls and a subtle arched entryway",
            "an architectural minimalist salon with organic curved walls and neutral sand tones"
        ]
        props = [
            "a large minimalist sculptural ceramic vase with dry botanical branches in the background",
            "a curated low travertine coffee table and subtle architectural olive tree in a matte pot",
            "a sleek minimalist brass arc floor lamp and architectural design monograph",
            "a textured abstract neutral wall canvas and soft woven wool area rug"
        ]
        
        chosen_arch = random.choice(architectures)
        chosen_light = random.choice(lightings)
        chosen_prop = random.choice(props)
        random_style = f"{chosen_arch}, illuminated by {chosen_light}. Complementary styling: {chosen_prop}."

        room_context = lugar_casa_usuario.strip() if lugar_casa_usuario and lugar_casa_usuario.strip() else "a luxurious, high-end living area appropriate for this piece"
        proportions = medidas_usuario.strip() if medidas_usuario and medidas_usuario.strip() else "exact true-to-scale real-world proportions"
        notes_part = f"\nSPECIAL USER INSTRUCTIONS: {notas_usuario}" if notas_usuario and notas_usuario.strip() else ""

        local_prompt = f"""SYSTEM: You are a World-Class Interior Designer and Architectural Photographer.
TASK: Place the furniture piece from Image 1 into a breathtaking architectural lifestyle environment.
TARGET FURNITURE: {furn_item}.
PRESERVATION MANDATE:
- Maintain EXACT geometry, shape, proportions ({proportions}), and structure: {geom_struct}.
- Preserve the EXACT upholstery color ({f_color}) and texture ({f_texture}) with ZERO color alteration.
- Preserve all wooden/metal frames and legs.
SETTING & STYLING:
- Location: {room_context}.
- Atmosphere: {random_style}.
- Lighting: {chosen_light}.
- Composition: Wide-angle interior catalog shot, furniture perfectly grounded on the floor, 40% soft background bokeh (f/2.8 lens).
HARDWARE: {hardware_str}{notes_part}

Negative Prompt: altered furniture color, changed upholstery tone, deformed furniture, fake CGI look, floating furniture, cluttered room, neon lighting, oversaturated colors, text, watermark."""

        if not key:
            return {
                "google_ai_studio": local_prompt,
                "chatgpt_dalle3": local_prompt,
                "midjourney_v6": local_prompt + " --ar 16:9 --v 6.1 --style raw"
            }
        
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            
            sys_prompt = f"""You are a Master Prompt Engineer specializing in Generative AI for luxury interior design and furniture photography.
Your task is to write a highly-detailed text prompt to generate an architectural interior image containing the {furn_item} seen in {target_imgs}.

CRITICAL CONSTRAINTS:
1. GEOMETRY & IDENTITY: Maintain EXACTLY the {geom_struct} and {camera_angle} from the reference images. DO NOT alter the shape, dimensions, or design of the furniture.
2. MATERIAL & COLOR FIDELITY: The upholstery/material MUST be {f_name} ({f_color}, {f_texture}). Do NOT modify the color or texture (0% hue drift).
3. PERSPECTIVE: Wide architectural shot, grounded realistically on the floor with natural ambient contact shadows.
4. ENVIRONMENT: Hyper-realistic luxury minimalist interior:
   - Setting: {room_context}
   - Style: {random_style}
   - Proportions: {proportions}
   - Neutral complementary palette that highlights the furniture without clashing.
5. LIGHTING: {chosen_light}.
6. DEPTH OF FIELD: Soft background blur (f/2.8 lens effect), furniture razor sharp in focus.{notes_part}

Output ONLY the clean prompt text for Google AI Studio / Gemini."""

            res = self._call_gemini(
                client=client,
                contents=[sys_prompt],
                config=types.GenerateContentConfig(temperature=0.7)
            )
            
            generated_prompt = res.text.strip()
            
            return {
                "google_ai_studio": f"SYSTEM: You are a Master Commercial Product Photographer and Interior Art Director.\nTASK: Place the furniture into a luxury architectural space.\n\n" + generated_prompt,
                "chatgpt_dalle3": generated_prompt,
                "midjourney_v6": generated_prompt + " --ar 16:9 --v 6.1 --style raw"
            }
        except Exception as e:
            print(f"[AIPromptServiceV3] Error generating minimalist prompt: {e}")
            return {
                "google_ai_studio": local_prompt,
                "chatgpt_dalle3": local_prompt,
                "midjourney_v6": local_prompt + " --ar 16:9 --v 6.1 --style raw"
            }

ai_prompt_service_v3 = AIPromptServiceV3()

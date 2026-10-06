import os
import io
import json
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
    lighting_direction: str = Field(description="Dirección exacta de la luz y tipo de sombra (ej. Key light from top-left, soft diffuse fill, gentle drop shadow)")
    geometric_structure: str = Field(description="Descripción topológica de la forma (ej. sharp 90-degree corners, sweeping organic curves)")
    existing_materials: str = Field(description="Tapicería y partes rígidas actuales")

class AIPromptServiceV3:
    def __init__(self):
        self.default_api_key = "AIzaSyDlWM2_lrP-x-GP2wQrgmLL76Ouz9w7How"

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
        models_to_try = ["gemini-3.5-flash", "gemini-3.1-pro-preview"]
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
Pay special attention to how light hits the threads/wood grain."""
            
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
        return "Shot on Hasselblad H6D-100c medium format, 120mm macro lens, f/11 aperture for maximum sharp depth of field, 8k resolution, raw hyper-realistic commercial photography, focus stacking, crisp architectural clarity."

    def _build_white_isolation_str(self, fondo_blanco: bool = True, hd: bool = False) -> str:
        if fondo_blanco:
            return "ENVIRONMENT: extract ONLY the furniture, do NOT modify its color, texture, or geometry (wood and fabric must be intact), place it perfectly CENTERED on a pure white background, completely eliminate shadows, and remove any studio lighting reflections from the wood and fabric. CRITICAL: DO NOT include any text, numbers, color names, or color palettes in the image."
        else:
            return "ENVIRONMENT: maintain original background."


    def generate_extraction_prompt(self, furniture_name: str, analysis: dict) -> dict:
        prompt_base = f"""INSTRUCTION: Use the provided image of the '{furniture_name}' as the absolute single truth reference.
        
CRITICAL CONSTRAINT: You must ONLY extract the furniture. Keep the exact structural integrity, shape, geometry, legs, cushions, folds, and proportions identical to the original image.
Keep wood and fabric texture and color exactly the same. Do NOT modify the color or texture.
Put the furniture perfectly CENTERED on a pure white background. NO shadows. REMOVE all studio lighting/reflections from the materials.
CRITICAL: DO NOT include any text, numbers, color names, or color palettes in the image.

Negative Prompt:
shadows, drop shadows, reflections, studio lighting, dark background, room environment, changed geometry, changed color, changed texture, text, typography, letters, numbers."""
        return {
            "google_ai_studio": prompt_base,
            "midjourney_v6": prompt_base,
            "chatgpt_dalle3": prompt_base
        }

    def generate_material_swap_prompt_v3(
        self,
        mode: str,
        furniture_name: str,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        num_furniture_images: int = 1,
        fondo_blanco: bool = True,
        hd: bool = False
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
        if hd:
            hardware_str += " High Definition, 8k, extremely detailed, highly realistic"
        white_bg = self._build_white_isolation_str(fondo_blanco)

        # DALL-E 3 Anti-Plástico
        dalle_defense = "[ENGINE: Disable CGI, Disable Octane Render, Disable 3D Models, Force 35mm RAW Photography, Force real-world textile micro-imperfections]"
        dalle_shadows = "[SHADOWS: 0% ground shadows, 0% drop shadows, strict digital cutout]"

        if mode == "dual":
            target_imgs = self.get_img_refs(3, num_furniture_images)
            
            prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Editor.
TASK: Accurately replace BOTH the fabric upholstery AND the wooden components in {target_imgs}.
TARGET ITEM: {furn_item}.
GEOMETRY & CAMERA: Strictly lock camera to {camera_angle}. Preserve exact topology: {geom_struct}. Replicate original lighting: {lighting_dir}.
{white_bg}
HARDWARE: {hardware_str}
FABRIC (From Image 1): Apply {f_name}. Color: {f_color}. Texture: {f_texture}. Interaction: {f_light}. Scale down texture dramatically (98% reduction) for macroscopic realism.
WOOD (From Image 2): Apply {w_name}. Color: {w_color}. Grain: {w_texture}. Interaction: {w_light}. Anatomical grain flow.

Negative Prompt: CGI, 3D render, plastic, generic fabric, loss of weave, suede, velvet, leather, flat wood, altered geometry, perspective distortion, floor shadows, grey background."""

            prompt_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a hyper-realistic commercial catalog photograph of a {furn_item}.
Camera/Geometry: Locked at {camera_angle}. Structural topology: {geom_struct}.
Lighting: {lighting_dir}.
Materials: The upholstery is meticulously crafted from {f_name} ({f_texture}, {f_color}, {f_light}). The wooden base/legs are carved from {w_name} ({w_texture}, {w_color}, {w_light}).
Environment: {white_bg}
Hardware constraints: {hardware_str}"""

            prompt_mj = f"""Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}. Upholstered in {f_name} ({f_color}, {f_texture}), wooden components are {w_name} ({w_color}, {w_texture}). Shot at {camera_angle}, {lighting_dir}. {hardware_str} --no floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic, suede, velvet, leather --ar 1:1 --v 6.1 --style raw --c 5"""

        elif mode == "fabric_only":
            target_imgs = self.get_img_refs(2, num_furniture_images)
            
            prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Editor.
TASK: Accurately replace the fabric upholstery in {target_imgs}.
TARGET ITEM: {furn_item}.
GEOMETRY & CAMERA: Strictly lock camera to {camera_angle}. Preserve exact topology: {geom_struct}. Replicate original lighting: {lighting_dir}. Preserve original wood/legs.
{white_bg}
HARDWARE: {hardware_str}
FABRIC (From Image 1): Apply {f_name}. Color: {f_color}. Texture: {f_texture}. Interaction: {f_light}. Scale down texture dramatically (98% reduction) for macroscopic realism.

Negative Prompt: CGI, 3D render, plastic, generic fabric, loss of weave, suede, velvet, leather, color shift, altered geometry, perspective distortion, floor shadows, grey background."""

            prompt_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a hyper-realistic commercial catalog photograph of a {furn_item}.
Camera/Geometry: Locked at {camera_angle}. Structural topology: {geom_struct}.
Lighting: {lighting_dir}. Preserve original wooden components precisely.
Materials: The upholstery is meticulously crafted from {f_name} ({f_texture}, {f_color}, {f_light}).
Environment: {white_bg}
Hardware constraints: {hardware_str}"""

            prompt_mj = f"""Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}. Upholstered in {f_name} ({f_color}, {f_texture}), original wooden legs preserved. Shot at {camera_angle}, {lighting_dir}. {hardware_str} --no floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic, suede, velvet, leather --ar 1:1 --v 6.1 --style raw --c 5"""

        else: # wood_only
            target_imgs = self.get_img_refs(2, num_furniture_images)
            
            prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Editor.
TASK: Accurately replace ONLY the wooden components (legs, frame, base) in {target_imgs}.
TARGET ITEM: {furn_item}.
GEOMETRY & CAMERA: Strictly lock camera to {camera_angle}. Preserve exact topology: {geom_struct}. Replicate original lighting: {lighting_dir}. Preserve original fabric perfectly.
{white_bg}
HARDWARE: {hardware_str}
WOOD (From Image 1): Apply {w_name}. Color: {w_color}. Grain: {w_texture}. Interaction: {w_light}. Anatomical grain flow.

Negative Prompt: altered fabric, changed upholstery, CGI, 3D render, plastic, flat wood, altered geometry, perspective distortion, floor shadows, grey background."""

            prompt_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a hyper-realistic commercial catalog photograph of a {furn_item}.
Camera/Geometry: Locked at {camera_angle}. Structural topology: {geom_struct}.
Lighting: {lighting_dir}. Preserve original fabric upholstery perfectly.
Materials: The wooden base/legs/frame are carved from {w_name} ({w_texture}, {w_color}, {w_light}).
Environment: {white_bg}
Hardware constraints: {hardware_str}"""

            prompt_mj = f"""Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}. Original upholstery preserved perfectly, wooden components replaced with {w_name} ({w_color}, {w_texture}). Shot at {camera_angle}, {lighting_dir}. {hardware_str} --no altered fabric, floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic --ar 1:1 --v 6.1 --style raw --c 5"""

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
        fondo_blanco: bool = True,
        hd: bool = False
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
        if hd:
            hardware_str += " High Definition, 8k, extremely detailed, highly realistic"
        white_bg = self._build_white_isolation_str(fondo_blanco)
        
        dalle_defense = "[ENGINE: Disable CGI, Force 35mm RAW Photography]"
        dalle_shadows = "[SHADOWS: 0% ground shadows, pure digital cutout]"

        if fa and fa.get("name"):
            mat_str = f"Upholstery must perfectly replicate {f_name} ({f_color}, {f_texture}, {f_light})."
        else:
            mat_str = "Upholstery and materials must strictly replicate the authentic fabric weave, texture, and original color of the furniture in the reference image."

        def build_prompts(angle_desc: str, geo_constraint: str, neg_extras: str):
            p_ai = f"""SYSTEM: You are an Architectural Visualization Expert and Master Commercial Photographer.
TASK: Generate a mathematically precise {angle_desc} of the target item.
TARGET ITEM: {furn_item}.
TOPOLOGY: {geom_struct}.
CAMERA/GEOMETRY CONSTRAINT: {geo_constraint}
{white_bg}
MATERIALS: {mat_str} Preserve all wooden parts.
HARDWARE: {hardware_str}

Negative Prompt: CGI, plastic, {neg_extras}, perspective distortion, floor shadows, background objects."""

            p_dalle = f"""{dalle_defense}
{dalle_shadows}
Generate a mathematically precise {angle_desc} photograph of a {furn_item}.
TOPOLOGY: {geom_struct}.
CAMERA/GEOMETRY CONSTRAINT: {geo_constraint}
MATERIALS: {mat_str}
ENVIRONMENT: {white_bg}
HARDWARE: {hardware_str}"""

            p_mj = f"""Commercial luxury product photography, {angle_desc} of {furn_item}, {geom_struct}. {mat_str} {geo_constraint} {hardware_str} isolated on pure solid white background #FFFFFF --no {neg_extras}, perspective distortion, floor shadows, background objects, CGI, 3D render --ar 1:1 --v 6.1 --style raw"""
            
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
            "vista_3_4_izquierda": build_prompts(
                "3/4 ISOMETRIC PERSPECTIVE FACING LEFT",
                "Classic commercial catalog 3/4 perspective angled 45 degrees, object facing toward the left. Elevated 15 degrees to show depth, seat cushion, and left armrest clearly.",
                "flat front, flat side, facing right, rear view, bird's-eye"
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
            )
        }


    def generate_clone_views_prompt_v3(self, target_name: str, furniture_analysis: Optional[Dict[str, Any]] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
        ma = furniture_analysis or {}
        furn_item = ma.get("furniture_item", "furniture")
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        materials = ma.get("existing_materials", "original materials")
        
        white_bg = self._build_white_isolation_str(fondo_blanco)
        hardware_str = self._build_photo_hardware_str()
        if hd:
            hardware_str += " High Definition, 8k, extremely detailed, highly realistic"
        
        prompt_ai_studio = f"""SYSTEM: You are a Master Commercial Product Photographer and AI Image Editor.
TASK: Re-color and re-upholster the Target View Image ('{target_name}'). The Target View Image contains a sofa with the wrong color. You must change its color to match the PERFECT Reference Image (Image 1).
TARGET GEOMETRY: You MUST preserve the exact geometry, structural shape, and camera angle of the Target View Image (Image 2). Do NOT modify the furniture's physical structure. It is a {furn_item}.
{white_bg}
HARDWARE: {hardware_str}
CRITICAL COLOR/TEXTURE CONSTRAINT: The furniture in the Target View Image MUST be changed to match this exact material: [{materials}]. Paint over the white/wrong color of the Target View Image with the exact hex color, thread pattern, and material finish from Image 1. They must look like the exact same physical product.

Negative Prompt: altered geometry, changed structure, mismatched texture, shadows, drop shadows, floor shadows, background, CGI, plastic, 3D render, generic fabric, keeping the original color of image 2, white color."""

        return {
            "google_ai_studio": prompt_ai_studio,
            "chatgpt_dalle3": f"""Generate a hyper-realistic commercial catalog photograph of a {furn_item}.
Camera/Geometry: Preserve the exact structural topology of the Target View Image.
Lighting: Professional studio lighting.
Materials: The upholstery MUST be meticulously crafted exactly as: {materials}.
Environment: {white_bg}
Hardware constraints: {hardware_str}""",
            "midjourney_v6": f"Commercial luxury product photography, {furn_item} isolated on a pure solid white background #FFFFFF. Upholstered exactly in {materials}. {hardware_str} --no floor shadows, drop shadows, grey background, room, CGI, 3D render, plastic --ar 1:1 --v 6.1 --style raw --cw 100"
        }



    def generate_dynamic_gemini_clone_prompt(self, ref_bytes: bytes, view_bytes: bytes, api_key: Optional[str] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
        if not key:
            fallback = "Please set GEMINI_API_KEY to generate dynamic prompts."
            return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}
            
        try:
            from google import genai
            from google.genai import types
            import io
            from PIL import Image
            
            client = genai.Client(api_key=key)
            img_ref = self._prepare_image(ref_bytes)
            img_view = self._prepare_image(view_bytes)
            
            sys_prompt = """You are a Master Prompt Engineer specializing in Generative AI for e-commerce photography.
I am providing you with two images: 
1. Image 1 (Reference): A piece of furniture with the EXACT CORRECT COLOR and TEXTURE.
2. Image 2 (Target View): A different angle of the furniture that has the WRONG COLOR, but the CORRECT GEOMETRY.

Your task is to write the absolute BEST, highly-detailed text prompt to feed into a Diffusion Model (like Google AI Studio/Imagen 3 or DALL-E) to recolor Image 2 using the color and texture of Image 1.

Perform a DEEP ANALYSIS of Image 1 right now: Extract the precise hex color tone, the fabric type, the weave, and the lighting interaction.
Perform a DEEP ANALYSIS of Image 2 right now: Identify the exact camera angle, structural geometry, and folds.

Now, WRITE A GENERIC BUT HIGHLY SPECIFIC PROMPT.
The prompt must explicitly command the AI to:
- Keep the exact geometric structure and camera angle of Image 2.
- Forcefully upholster the furniture in Image 2 using the deep analysis color/texture you extracted from Image 1.
- CRITICAL FOR TEXTURE: Explicitly command the AI to wrap the texture realistically around the 3D geometry. The texture must follow the perspective, curves, folds, and lighting of the object perfectly.
- CRITICAL FOR LIGHTING: Preserve all highlights, midtones, and deep shadows of the furniture's original folds so the fabric doesn't look flat or like a 2D overlay.
- {'Ensure a pure white background with zero shadows, extracting the furniture perfectly centered. DO NOT include any text, numbers, or color palettes.' if fondo_blanco else 'Maintain the original background environment.'}
- Be extremely descriptive about the color and material finish so the AI has no choice but to use it.

Output ONLY the text of the prompt. Do not include introductory text or explanations. Do not use quotes around the entire prompt."""

            res = self._call_gemini(
                client=client,
                contents=[sys_prompt, img_ref, img_view],
                config=types.GenerateContentConfig(
                    temperature=0.7
                )
            )
            
            generated_prompt = res.text.strip()
            
            return {
                "google_ai_studio": generated_prompt,
                "chatgpt_dalle3": generated_prompt,
                "midjourney_v6": generated_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }
        except Exception as e:
            print(f"[AIPromptServiceV3] Error generating dynamic prompt: {e}")
            fallback = f"Error generating dynamic prompt with Gemini: {str(e)}"
            return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}



    def generate_dynamic_fabric_view_prompt(
        self, fabric_bytes: bytes, view_bytes: bytes, api_key: Optional[str] = None, fondo_blanco: bool = True, hd: bool = False) -> Dict[str, str]:
        key = self.get_api_key(api_key)
        if not key:
            fallback = "Please set GEMINI_API_KEY to generate dynamic prompts."
            return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}
            
        try:
            from google import genai
            from google.genai import types
            import io
            from PIL import Image
            
            client = genai.Client(api_key=key)
            img_fab = self._prepare_image(fabric_bytes)
            img_view = self._prepare_image(view_bytes)
            
            sys_prompt = """You are a Master Prompt Engineer specializing in Generative AI for e-commerce photography.
I am providing you with two images: 
1. Image 1 (Fabric Sample): A macro shot or swatch of a fabric that contains the EXACT COLOR and TEXTURE to be used.
2. Image 2 (Furniture View): A specific angle of a piece of furniture.

Your task is to write the absolute BEST, highly-detailed text prompt to feed into a Diffusion Model (like Google AI Studio/Imagen 3 or DALL-E) to apply the fabric from Image 1 onto the furniture in Image 2.

Perform a DEEP ANALYSIS of Image 1 right now: Extract the precise hex color tone, the fabric type, the weave, and the lighting interaction.
Perform a DEEP ANALYSIS of Image 2 right now: Identify the exact camera angle, structural geometry, and folds.

Now, WRITE A GENERIC BUT HIGHLY SPECIFIC PROMPT.
The prompt must explicitly command the AI to:
- Keep the exact geometric structure and camera angle of Image 2.
- Forcefully upholster the furniture in Image 2 using the deep analysis color/texture you extracted from Image 1.
- CRITICAL FOR TEXTURE: Explicitly command the AI to wrap the texture realistically around the 3D geometry. The texture must follow the perspective, curves, folds, and lighting of the object perfectly.
- CRITICAL FOR LIGHTING: Preserve all highlights, midtones, and deep shadows of the furniture's original folds so the fabric doesn't look flat or like a 2D overlay.
- {'Ensure a pure white background with zero shadows, extracting the furniture perfectly centered. DO NOT include any text, numbers, or color palettes.' if fondo_blanco else 'Maintain the original background environment.'}
- Be extremely descriptive about the color and material finish so the AI has no choice but to use it.

Output ONLY the text of the prompt."""

            res = self._call_gemini(
                client=client,
                contents=[sys_prompt, img_fab, img_view],
                config=types.GenerateContentConfig(
                    temperature=0.7
                )
            )
            
            generated_prompt = res.text.strip()
            
            return {
                "google_ai_studio": generated_prompt,
                "chatgpt_dalle3": generated_prompt,
                "midjourney_v6": generated_prompt + " --iw 2.0 --style raw --stylize 0 --v 6.1"
            }
        except Exception as e:
            print(f"[AIPromptServiceV3] Error generating dynamic prompt: {e}")
            fallback = f"Error generating dynamic prompt with Gemini: {str(e)}"
            return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}

    def generate_minimalist_environment_prompt_v3(
        self,
        furniture_name: str,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        num_furniture_images: int = 1,
        tipo_mueble_usuario: str = "",
        api_key: Optional[str] = None,
        hd: bool = False
    ) -> Dict[str, str]:
        key = self.get_api_key(api_key)
        if not key:
            fallback = "Please set GEMINI_API_KEY to generate minimalist prompts."
            return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}
            
        fa = fabric_analysis or {}
        ma = furniture_analysis or {}
        f_name = fa.get("name")
        f_color = fa.get("color_description")
        f_texture = fa.get("texture_detail")
        
        # Merge AI analysis with user's specific furniture type
        furn_item = ma.get("furniture_item", furniture_name)
        if tipo_mueble_usuario and tipo_mueble_usuario.strip():
            furn_item = f"{tipo_mueble_usuario.strip()} ({furn_item})"
            
        geom_struct = ma.get("geometric_structure", "original geometric structure")
        camera_angle = ma.get("camera_angle", "original perspective")
        existing_materials = ma.get("existing_materials", "original materials and color")

        # Fallback to extracted existing materials if no specific fabric sample is provided
        if not f_name:
            f_name = "its original upholstery material"
        if not f_color:
            f_color = "its original color"
        if not f_texture:
            f_texture = existing_materials

        hardware_str = self._build_photo_hardware_str()
        if hd:
            hardware_str += " High Definition, 8k, extremely detailed, highly realistic"
        target_imgs = self.get_img_refs(2, num_furniture_images)
        
        # Combinatorial random seeds for infinite non-repetitive variety
        import random
        lightings = [
            "soft morning sunlight casting subtle branch shadows",
            "golden hour light filtering through sheer linen curtains",
            "diffused overcast daylight for ultra-soft, even illumination",
            "warm afternoon sunlight creating elegant geometric shadows"
        ]
        architectures = [
            "organic curved plaster walls with a microcement floor",
            "a minimalist Mediterranean space with a large arched window",
            "a Japandi interior with light oak wood panels and warm beige tones",
            "a high-end Scandinavian loft with floor-to-ceiling glass and soft gray tones",
            "a Wabi-Sabi inspired room with raw, textured clay walls and neutral earthy tones"
        ]
        props = [
            "a subtle potted olive tree in the background",
            "an artisanal wabi-sabi ceramic vase with dry branches",
            "a sleek, minimalist brass floor lamp",
            "a curated stack of design books on a low travertine plinth",
            "a moody, minimalist abstract textured painting on the wall"
        ]
        
        random_style = f"{random.choice(architectures)}, illuminated by {random.choice(lightings)}. Subtle background decor: {random.choice(props)}."
        
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            
            sys_prompt = f"""You are a Master Prompt Engineer specializing in Generative AI for luxury furniture photography.
Your task is to write a highly-detailed text prompt to generate an image of the {furn_item} seen in {target_imgs}.

CRITICAL CONSTRAINTS:
1. GEOMETRY & IDENTITY: Maintain EXACTLY the {geom_struct} and {camera_angle} from the reference images. DO NOT alter the shape, dimensions, or design of the furniture.
2. MATERIAL: The upholstery/material MUST be {f_name} ({f_color}, {f_texture}). Do NOT modify the color or texture.
3. PERSPECTIVE: The camera must be at a far distance (wide shot, distant perspective) perfect for a high-end furniture catalog.
4. ENVIRONMENT (DYNAMIC & CREATIVE): Create a hyper-realistic, high-end minimalist architectural interior setting. 
   - BASE STYLE FOR THIS GENERATION: {random_style}
   - Use warm, neutral, earthy tones (beige, taupe, soft gray, warm plaster, microcement).
   - Place the {furn_item} in its CORRECT NATURAL ROOM (e.g., a dining chair belongs in a dining room, a sofa in a living room, a bed in a bedroom).
   - The environment colors must elegantly contrast with the furniture's color ({f_color} / {existing_materials}) to make the furniture pop.
5. LIGHTING & CINEMATOGRAPHY: Strictly incorporate the lighting style specified in the BASE STYLE above. Use cinematic descriptions to make it look incredibly realistic.
6. DEPTH OF FIELD: The background must be 40% blurred (moderate bokeh, f/2.8 lens effect), keeping the furniture perfectly sharp and in focus.

Write a prompt that can be used in DALL-E, Midjourney, or Google AI Studio. Be extremely descriptive.
Output ONLY the text of the prompt without quotes or introductions."""

            res = self._call_gemini(
                client=client,
                contents=[sys_prompt],
                config=types.GenerateContentConfig(
                    temperature=0.8
                )
            )
            
            generated_prompt = res.text.strip()
            
            return {
                "google_ai_studio": f"SYSTEM: You are a Master Commercial Product Photographer and AI Editor.\nTASK: Place the furniture from {target_imgs} into a new environment according to the prompt.\n\n" + generated_prompt,
                "chatgpt_dalle3": generated_prompt,
                "midjourney_v6": generated_prompt + " --ar 16:9 --v 6.1 --style raw"
            }
        except Exception as e:
            print(f"[AIPromptServiceV3] Error generating minimalist prompt: {e}")
            fallback = f"Error generating prompt: {str(e)}"
            return {"google_ai_studio": fallback, "chatgpt_dalle3": fallback, "midjourney_v6": fallback}

ai_prompt_service_v3 = AIPromptServiceV3()


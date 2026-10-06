import os
import io
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from PIL import Image
from pydantic import BaseModel, Field

# Modelos Pydantic para Structured Outputs
class MaterialAnalysis(BaseModel):
    name: str = Field(description="Nombre comercial corto (ej. Bouclé Gris Sal y Pimienta, Roble Miel, Baker Linen)")
    color_description: str = Field(description="Descripción cromática detallada del tono, subtonos y brillos en español")
    texture_detail: str = Field(description="Descripción de la estructura de la textura en inglés (ej. dense nubby loops, straight vertical grain)")
    finish_type: str = Field(description="Tipo de acabado: Mate, Semi-brillante (Satin), o Brillante (Glossy)")

class FurnitureAnalysis(BaseModel):
    furniture_item: str = Field(description="Nombre específico y ángulo del mueble (ej. curved bouclé sofa in 3/4 perspective, wooden dining armchair)")
    camera_angle: str = Field(description="Perspectiva exacta y encuadre (ej. strict horizontal eye-level side profile, 45-degree elevated isometric)")
    geometric_structure: str = Field(description="Descripción exacta de la forma estructural (ej. straight 4-seater modular with square edges)")
    existing_materials: str = Field(description="Descripción de la tapicería y partes de madera existentes")
    lighting_type: str = Field(description="Iluminación actual de la foto")

class AIPromptServiceV2:
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
            "gemini-2.5-pro"
        ]
        last_err = None
        for m in models_to_try:
            try:
                return client.models.generate_content(model=m, contents=contents, config=config)
            except Exception as e:
                last_err = e
                continue
        raise last_err if last_err else RuntimeError("No se pudo conectar con Gemini API")

    def _prepare_image(self, img_bytes: bytes, max_dim: int = 1024) -> Image.Image:
        """Optimiza y redimensiona imágenes para envío ultra-rápido a Gemini."""
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        return img

    def analyze_material(self, sample_bytes: bytes, api_key: Optional[str] = None, material_type: str = "auto") -> Dict[str, Any]:
        """Analiza una muestra de material usando Structured Outputs (Pydantic)."""
        key = self.get_api_key(api_key)
        if not key:
            return MaterialAnalysis(
                name=f"Muestra ({material_type})",
                color_description="tono natural de la muestra",
                texture_detail="realistic micro-texture",
                finish_type="Satin"
            ).model_dump()
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            img = self._prepare_image(sample_bytes)
            
            prompt = f"Analyze this material sample ({material_type}) for luxury furniture product photography."
            
            res = self._call_gemini(
                client=client,
                contents=[prompt, img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MaterialAnalysis,
                    temperature=0.2
                )
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"[AIPromptServiceV2] Error analyzing material: {e}")
            return MaterialAnalysis(
                name=f"Muestra Error ({material_type})",
                color_description="color detectado",
                texture_detail="texture detected",
                finish_type="Matte"
            ).model_dump()

    def analyze_furniture_for_enhancement(self, furniture_bytes, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Analiza el mueble usando Structured Outputs."""
        key = self.get_api_key(api_key)
        if not key:
            return FurnitureAnalysis(
                furniture_item="furniture product",
                camera_angle="same camera angle",
                geometric_structure="same geometry",
                existing_materials="original materials",
                lighting_type="neutral lighting"
            ).model_dump()
            
        try:
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=key)
            prompt = "Analyze this furniture image to describe its exact physical properties for 3D preservation."
            
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
                    response_schema=FurnitureAnalysis,
                    temperature=0.2
                )
            )
            return json.loads(res.text)
        except Exception as e:
            print(f"[AIPromptServiceV2] Error analyzing furniture: {e}")
            return FurnitureAnalysis(
                furniture_item="furniture piece",
                camera_angle="original perspective",
                geometric_structure="original structural shape",
                existing_materials="original fabric and wood",
                lighting_type="studio lighting"
            ).model_dump()

    def get_img_refs(self, start_idx: int, count: int) -> str:
        if count <= 1: return f"Image {start_idx}"
        if count == 2: return f"Images {start_idx} and {start_idx + 1}"
        nums = list(range(start_idx, start_idx + count))
        return "Images " + ", ".join(map(str, nums[:-1])) + f", and {nums[-1]}"

    def _build_white_background_enforcement(self, fondo_blanco: bool = True) -> str:
        if fondo_blanco:
            return "ENVIRONMENT CONSTRAINT: extract ONLY the furniture, do NOT modify its color, texture, or geometry (wood and fabric must be intact), place it perfectly CENTERED on a pure white background, completely eliminate shadows, and remove any studio lighting reflections from the wood and fabric. CRITICAL: DO NOT include any text, numbers, color names, or color palettes in the image."
        else:
            return "ENVIRONMENT CONSTRAINT: maintain original background."

    def generate_material_swap_prompt_v2(
        self,
        mode: str,
        furniture_name: str,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        num_furniture_images: int = 1,
        fondo_blanco: bool = True
    ) -> Dict[str, str]:
        
        fa = fabric_analysis or {}
        wa = wood_analysis or {}
        ma = furniture_analysis or {}
        
        f_name = fa.get("name", "Fabric")
        f_color = fa.get("color_description", "")
        f_texture = fa.get("texture_detail", "")
        
        w_name = wa.get("name", "Wood")
        w_color = wa.get("color_description", "")
        w_texture = wa.get("texture_detail", "")
        w_finish = wa.get("finish_type", "")

        furn_item = ma.get("furniture_item", furniture_name)
        camera_angle = ma.get("camera_angle", "original perspective")
        geom_struct = ma.get("geometric_structure", "original structural geometry")

        # White Background String
        white_bg = self._build_white_background_enforcement(fondo_blanco)
        bg_neg = "shadows, drop shadows, dark background, black background, grey background, original background, room environment, floor reflection" if fondo_blanco else "changed background, altered environment, changed camera angle, top-down view"

        if mode == "dual":
            target_imgs = self.get_img_refs(3, num_furniture_images)
            task_desc = f"replace BOTH the fabric upholstery AND the wooden components of the furniture in {target_imgs}"
            mat_desc = f"Fabric from Image 1 ({f_name}: {f_color}, {f_texture}). Wood from Image 2 ({w_name}: {w_color}, {w_texture}, {w_finish})."
            
            # Prompts adaptados
            prompt_ai_studio = f"""SYSTEM INSTRUCTION: You are an expert e-commerce product photographer and AI image editor.
TASK: Accurately {task_desc} using the exact macro textures provided.
TARGET ITEM: {furn_item}.
GEOMETRY PRESERVATION: Strictly preserve the exact shape, structural geometry ({geom_struct}), and contours. Camera must be locked to {camera_angle}.
{white_bg}
FABRIC APPLICATION: Apply the precise weave pattern and thread colors from Image 1. Scale down this macro texture dramatically (97% reduction) so it looks like realistic, finely woven fabric from a distance.
WOOD APPLICATION: Apply the precise wood grain flow, pores, and color from Image 2 to all legs, frames, and wooden bases. Ensure grain follows natural anatomical direction.

Negative Prompt: generic fabric, solid color, loss of weave pattern, suede, velvet, leather, flat wood colors, color shift, altered geometry, perspective distortion, {bg_neg}"""

        elif mode == "fabric_only":
            target_imgs = self.get_img_refs(2, num_furniture_images)
            task_desc = f"replace the fabric of the main furniture piece in {target_imgs}"
            mat_desc = f"Fabric from Image 1 ({f_name}: {f_color}, {f_texture})."
            
            prompt_ai_studio = f"""SYSTEM INSTRUCTION: You are an expert e-commerce product photographer and AI image editor.
TASK: Accurately {task_desc} using the exact texture analyzed from Image 1.
TARGET ITEM: {furn_item}.
GEOMETRY PRESERVATION: Strictly preserve the exact shape, structural geometry ({geom_struct}), and contours of the wooden parts and cushions. Camera must be locked to {camera_angle}.
{white_bg}
MATERIAL APPLICATION: Apply the precise weave pattern ({f_texture}) and thread colors ({f_color}) from Image 1. You must scale down this macro texture dramatically (97% reduction). Retain the dense micro-thread details without turning into a flat color.

Negative Prompt: generic fabric, solid color, flat texture, loss of weave pattern, suede, velvet, leather, color shift, altered geometry, perspective distortion, {bg_neg}"""

        else: # wood_only
            target_imgs = self.get_img_refs(2, num_furniture_images)
            task_desc = f"replace ONLY the wooden components (legs, frame, base) of the furniture in {target_imgs}"
            mat_desc = f"Wood from Image 1 ({w_name}: {w_color}, {w_texture}, {w_finish})."
            
            prompt_ai_studio = f"""SYSTEM INSTRUCTION: You are an expert e-commerce product photographer and AI image editor.
TASK: Accurately {task_desc} using the exact wood grain, finish, and tone analyzed from Image 1.
TARGET ITEM: {furn_item}.
GEOMETRY PRESERVATION: Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, and original fabric upholstery. Camera locked to {camera_angle}.
{white_bg}
MATERIAL APPLICATION: Apply the precise wood grain flow, pores, and color ({w_color}) from Image 1. Ensure grain follows natural anatomical direction (vertical on legs, horizontal on rails).

Negative Prompt: altered fabric, changed upholstery, color shift, flat colors, changed geometry, {bg_neg}"""

        # Adaptaciones por Modelo
        
        # 1. Google AI Studio (Imagen 3) / Gemini Pro
        # Imagen 3 prefiere prompts claros y directos.
        
        # 2. ChatGPT (DALL-E 3)
        # DALL-E 3 no lee las imágenes 1 y 2 literalmente como un ID, así que el prompt debe describir textualmente
        prompt_dalle = f"""Generate a photorealistic, ultra-high-definition e-commerce catalog image of a {furn_item}. 
Crucial Structure: The furniture features {geom_struct} viewed from a {camera_angle}. 
Material Design: The upholstery must be a highly detailed {f_name} ({f_texture}) in {f_color}. The wooden components (legs, frame) must be {w_name} ({w_texture}) with a {w_finish} finish. 
Environment: {white_bg} Do not add any shadows under the furniture. It must look digitally isolated on absolute white."""

        # 3. Midjourney v6.1 (Bonus)
        prompt_mj = f"""Commercial product photography, {furn_item} isolated on a pure solid white background #FFFFFF, {geom_struct}, upholstered in {f_color} {f_texture}, {w_name} wooden legs and frame with {w_finish} finish. Shot from {camera_angle}, studio lighting, highly detailed macro texture, 8k resolution, photorealistic, catalog style --no {bg_neg}, suede, velvet, leather, shadows --ar 1:1 --v 6.1 --style raw"""

        return {
            "google_ai_studio": prompt_ai_studio, # Usable también para Gemini Pro
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_mj
        }


    def generate_enhance_prompt(self, furniture_name: str, analysis: Dict[str, Any]) -> Dict[str, str]:
        furn_item = analysis.get("furniture_item", furniture_name)
        geom_struct = analysis.get("geometric_structure", "original structural geometry")
        mats = analysis.get("existing_materials", "original materials")
        
        white_bg = self._build_white_background_enforcement()
        
        prompt_ai_studio = f"""SYSTEM INSTRUCTION: You are an expert e-commerce product photographer and AI image editor specializing in non-destructive super-resolution.
TASK: Analyze the provided image ('{furniture_name}') very carefully. This is a product photo that must be enlarged and sharpened without changing ANY detail. Perform an ultra-faithful super-resolution upscale.
TARGET ITEM: {furn_item}.
PRESERVATION CONSTRAINT: Preserve 100% the original composition, geometry ({geom_struct}), layout, edges, and proportions. Maintain the exact original color palette with absolutely no color shift, no warming, no cooling, no desaturation, and no brightness drift.
MATERIAL CONSTRAINT: Preserve and enhance the existing materials and textures ({mats}) exactly as they appear. Sharpen and clarify the real texture, individual fibers or grains without inventing a new pattern. 
{white_bg}
Keep the subject looking like the exact same product, not a redesigned version. Enhance only existing detail. Do not stylize. Do not regenerate.

Negative Prompt: do not redesign, do not reinterpret, no new pattern, no color shift, no altered tone, no oversmoothing, no blur, no melted texture, no fake detail, no geometry changes, no fold changes, changed background."""

        prompt_dalle = f"""Generate a photorealistic, ultra-high-definition e-commerce catalog image of a {furn_item}. 
Crucial Structure: {geom_struct}. 
Material Design: The exact materials ({mats}) must be preserved with ultra-sharp detail and NO color shift from the original intent. 
Environment: {white_bg}"""

        return {
            "google_ai_studio": prompt_ai_studio,
            "chatgpt_dalle3": prompt_dalle,
            "midjourney_v6": prompt_ai_studio
        }

    def generate_multi_perspective_prompts(self, mode: str, furniture_name: str, fabric_analysis: Optional[Dict[str, Any]] = None, wood_analysis: Optional[Dict[str, Any]] = None, furniture_analysis: Optional[Dict[str, Any]] = None, num_furniture_images: int = 1, fondo_blanco: bool = True) -> Dict[str, Dict[str, str]]:
        fa = fabric_analysis or {}
        ma = furniture_analysis or {}
        f_name = fa.get("name", "Fabric")
        f_color = fa.get("color_description", "original color")
        f_texture = fa.get("texture_detail", "original texture")
        furn_item = ma.get("furniture_item", furniture_name)
        geom_struct = ma.get("geometric_structure", "original structural geometry")
        
        mat_instruction = f"Perfectly replicate the original materials ({f_texture}). Maintain the exact original color palette ({f_color}) with absolutely NO color shift. Explicitly retain the specific weave, grain, and textile texture without redesigning."
        white_bg = self._build_white_background_enforcement(fondo_blanco)
        
        base_prompt = f"""SYSTEM INSTRUCTION: You are an expert e-commerce product photographer.
TARGET ITEM: {furn_item}.
GEOMETRY CONSTRAINT: Strictly preserve the original structural design ({geom_struct}), silhouette, armrest shape, and proportions. Do not invent new structural elements.
MATERIAL CONSTRAINT: {mat_instruction}"""

        # Vista de frente
        p_frontal = f"""{base_prompt}
GENERATE: An absolute, strict ORTHOGONAL front profile view (0-degree elevation).
CAMERA CONSTRAINT: Perpendicular to the exact front center. ZERO perspective distortion, ZERO visibility of sides or top.
{white_bg}
Negative Prompt: 3/4 view, side view, angled view, perspective, isometric, depth distortion, visible sides, suede, velvet, generic fabric, color shift."""

        # Vista lateral derecha
        p_lateral_der = f"""{base_prompt}
GENERATE: A flawless, straight-on lateral profile view (90-degree side view facing right).
CAMERA CONSTRAINT: Strict 90-degree side profile from edge to edge. Zero vanishing points.
{white_bg}
Negative Prompt: 3/4 view, front view, top view, perspective distortion, suede, velvet, generic fabric, color shift."""

        # Vista lateral izquierda
        p_lateral_izq = f"""{base_prompt}
GENERATE: A flawless, straight-on lateral profile view (90-degree side view facing left).
CAMERA CONSTRAINT: Strict 90-degree side profile from edge to edge. Zero vanishing points.
{white_bg}
Negative Prompt: 3/4 view, front view, top view, perspective distortion, suede, velvet, generic fabric, color shift."""

        # Vista 3/4 mirando a la izquierda
        p_3_4_izq = f"""{base_prompt}
GENERATE: A flawless 3/4 isometric commercial catalog view, object facing toward the left.
CAMERA CONSTRAINT: Classic 45-degree angle showing volume, depth, and front/left side geometry clearly. Elevated 15 degrees.
{white_bg}
Negative Prompt: flat front, flat side, facing right, rear view, top-down view, perspective distortion."""

        # Vista 3/4 mirando a la derecha
        p_3_4_der = f"""{base_prompt}
GENERATE: A flawless 3/4 isometric commercial catalog view, object facing toward the right.
CAMERA CONSTRAINT: Classic 45-degree angle showing volume, depth, and front/right side geometry clearly. Elevated 15 degrees.
{white_bg}
Negative Prompt: flat front, flat side, facing left, rear view, top-down view, perspective distortion."""

        # Vista desde arriba
        p_cenital = f"""{base_prompt}
GENERATE: A strict direct top-down bird's-eye flat lay view (cenital).
CAMERA CONSTRAINT: Camera directly above the furniture looking straight down at 90 degrees.
{white_bg}
Negative Prompt: front view, side view, isometric, visible legs from front, angled view."""

        # Vista 3/4 posterior
        p_3_4_post = f"""{base_prompt}
GENERATE: A commercial catalog 3/4 rear isometric view (viewed from the back corner).
CAMERA CONSTRAINT: 45-degree angle from the rear, clearly showing backrest tailoring and rear structure.
{white_bg}
Negative Prompt: front view, front cushions, direct front, top-down."""

        # Vista macro detalle
        p_macro = f"""{base_prompt}
GENERATE: A hyper-detailed macro close-up view of the upholstery and stitching.
CAMERA CONSTRAINT: Extreme close-up shot focusing on the transition between the fabric and wooden components, displaying micro-texture and grain.
{white_bg}
Negative Prompt: full view, wide shot, distant camera."""

        # Vista ambientado
        p_lifestyle = f"""{base_prompt}
GENERATE: Place the {furn_item} into a realistic, medium-luxury minimalist interior environment, as if staged in a high-end modern client's home. SIEMPRE cambia de lugar las cosas, la decoración y los muebles de alrededor para que no se vea genérico. Aleatoriza la disposición y varía la composición.
CAMERA CONSTRAINT: Depth of field effect. Foreground macro-sharp, background blurred 60% bokeh. No white background.
Negative Prompt: white background, studio shot, floating furniture, changed texture, changed color."""

        def build_dict(p_str, title):
            return {
                "titulo": title,
                "google_ai_studio": p_str,
                "chatgpt_dalle3": p_str,
                "flux_midjourney": p_str
            }
            
        return {
            "vista_de_frente": build_dict(p_frontal, "vista de frente"),
            "vista_lateral_derecha": build_dict(p_lateral_der, "vista lateral (derecha)"),
            "vista_lateral_izquierda": build_dict(p_lateral_izq, "vista lateral (izquierda)"),
            "vista_3_4_izquierda": build_dict(p_3_4_izq, "vista 3/4 mirando a la izquierda"),
            "vista_3_4_derecha": build_dict(p_3_4_der, "vista 3/4 mirando a la derecha"),
            "vista_desde_arriba": build_dict(p_cenital, "vista desde arriba"),
            "vista_3_4_posterior": build_dict(p_3_4_post, "vista 3/4 posterior"),
            "vista_detalle_macro": build_dict(p_macro, "vista detalle macro"),
            "vista_lifestyle_ambientado": build_dict(p_lifestyle, "vista lifestyle (ambientado)")
        }


ai_prompt_service_v2 = AIPromptServiceV2()

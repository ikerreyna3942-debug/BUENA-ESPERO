import os

import io

import json

from pathlib import Path

from typing import Optional, Dict, Any

from PIL import Image



class AIPromptService:

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
        """Llama a Gemini con lista de modelos activos y fallback automÃ¡tico."""
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
        """Optimiza y redimensiona imÃ¡genes para envÃ­o ultra-rÃ¡pido a Gemini."""
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        return img

    def analyze_material(self, sample_bytes: bytes, api_key: Optional[str] = None, material_type: str = "auto") -> Dict[str, Any]:
        """Analiza una muestra de material (tela o madera) para fotografÃ­a comercial de muebles de lujo."""
        key = self.get_api_key(api_key)
        if not key:
            return {
                "name": f"Muestra ({material_type})",
                "color_description": "tono y matiz natural de la muestra",
                "texture_detail": "fine realistic micro-weave texture with authentic depth",
                "finish_type": "Semi-gloss satin"
            }

        try:
            from google import genai
            client = genai.Client(api_key=key)
            img = self._prepare_image(sample_bytes)
            prompt = f"""Analyze this material sample ({material_type}) for luxury furniture product photography.
Respond strictly in JSON with these keys:
{{
  "name": "Short commercial name (e.g. Heathered Salt-and-Pepper BouclÃ©, Warm Honey Oak Habano, Baker Linen)",
  "color_description": "Detailed chromatic description of the exact hue, undertones, and flecks in Spanish",
  "texture_detail": "Detailed texture structure description in English (e.g. dense nubby loops over cool grey under-weave / straight vertical grain)",
  "finish_type": "Semi-gloss satin or Matte or Glossy"
}}"""
            res = self._call_gemini(client=client, contents=[prompt, img])

            text = res.text.strip()

            if "```json" in text:

                text = text.split("```json")[1].split("```")[0].strip()

            elif "```" in text:

                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)

        except Exception as e:

            print(f"[AIPromptService] Error analyzing material: {e}")

            return {

                "name": f"Muestra ({material_type})",

                "color_description": "tono y matiz idÃ©nticos a la imagen de muestra",

                "texture_detail": "fine realistic micro-weave texture with authentic depth",

                "finish_type": "Semi-gloss satin"

            }



    def analyze_furniture_for_enhancement(self, furniture_bytes, api_key: Optional[str] = None) -> Dict[str, Any]:

        """Analiza el mueble para generar un prompt de ultra nitidez y desborrosamiento sin alterar color ni geometrÃ­a."""

        key = self.get_api_key(api_key)

        if not key:

            return {

                "furniture_item": "furniture product shown in Image 1",

                "existing_materials": "original fabric upholstery and original wooden legs/base",

                "lighting_type": "neutral soft commercial studio lighting"

            }

        try:

            from google import genai

            client = genai.Client(api_key=key)

            prompt = """Analyze this furniture image for commercial catalog HD upscaling and material swapping.

Respond strictly in valid JSON:

{

  "furniture_item": "Specific furniture piece name and angle (e.g. curved bouclÃ© sofa in 3/4 perspective, wooden dining armchair)",

  "camera_angle": "Exact camera perspective and framing (e.g. strict horizontal eye-level side profile, 45-degree elevated isometric view, low-angle frontal shot)",

  "geometric_structure": "Exact structural shape description (e.g. straight 4-seater modular with square edges, curved L-shape sectional with round armrests, armchair with thin metal legs)",

  "existing_materials": "Description of existing upholstery fabric and wooden parts/feet",

  "lighting_type": "Soft studio ambient lighting"

}"""

            contents = [prompt]
            if isinstance(furniture_bytes, list):
                for fb in furniture_bytes:
                    contents.append(self._prepare_image(fb))
            else:
                contents.append(self._prepare_image(furniture_bytes))

            res = self._call_gemini(client=client, contents=contents)

            text = res.text.strip()

            if "```json" in text:

                text = text.split("```json")[1].split("```")[0].strip()

            elif "```" in text:

                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)

        except Exception as e:

            print(f"[AIPromptService] Error analyzing furniture: {e}")

            return {

                "furniture_item": "furniture product shown in Image 1",

                "camera_angle": "exact same camera perspective as the original photo",

                "geometric_structure": "exact same geometry and structural shape as the original photo",

                "existing_materials": "original fabric upholstery and original wooden legs/base",

                "lighting_type": "neutral soft commercial studio lighting"

            }





    def generate_enhance_prompt(self, furniture_name: str, analysis: Dict[str, Any], fondo_blanco_sin_sombras: bool = True) -> Dict[str, str]:
        item_type = analysis.get("item_type", "furniture")
        f_color = analysis.get("exact_color_palette", "original color")
        hex_code = analysis.get("hex_code", "")
        mats = analysis.get("existing_materials", "original materials")
        
        prompt_base = f"""INSTRUCTION: Use the provided image of the '{furniture_name}' as the absolute single truth reference. This is NOT a re-creation or generation task. This is a faithful image restoration and super-resolution upscale task ONLY.

CRITICAL CONSTRAINT: Do NOT modify the furniture in any way. The structural integrity, shape, geometry, legs, cushions, folds, and proportions must remain EXACTLY identical to the original image. 
Maintain the exact original color palette ({f_color} / hex {hex_code}) with absolutely no color shift, no warming, no cooling, no desaturation, and no brightness drift.

MATERIAL CONSTRAINT: Preserve and enhance the existing materials and textures ({mats}). Sharpen and clarify the real texture, individual fibers or grains, and surface depth without inventing a new pattern. Enhance ONLY existing detail. Do not stylize. Keep it visually identical to the source, only sharper and higher resolution.

Negative Prompt:
do not modify furniture, do not redesign, do not reinterpret, no new pattern, no color shift, no altered tone, no oversmoothing, no blur, no melted texture, no fake detail, no geometry changes, no fold changes, no extra shadows, no added text, changed background."""

        mj_prompt = prompt_base + " --iw 2.0 --style raw --stylize 0 --v 6.1"

        return {
            "google_ai_studio": prompt_base,
            "flux_midjourney": mj_prompt,
            "dalle_chatgpt": prompt_base
        }




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
            "flux_midjourney": prompt_base,
            "dalle_chatgpt": prompt_base
        }

    def generate_material_swap_prompt(

        self,

        mode: str,

        furniture_name: str,

        fabric_name: str = "",

        fabric_analysis: Optional[Dict[str, Any]] = None,

        wood_name: str = "",

        wood_analysis: Optional[Dict[str, Any]] = None,

        fondo_blanco_sin_sombras: bool = True,

        num_furniture_images: int = 1,

        furniture_analysis: Optional[Dict[str, Any]] = None

    ) -> Dict[str, str]:

        fabric_analysis = fabric_analysis or {}

        wood_analysis = wood_analysis or {}

        furniture_analysis = furniture_analysis or {}

        

        f_name = fabric_analysis.get("name", fabric_name.replace(".", " "))

        f_color = fabric_analysis.get("color_description", "true-to-life chromatic profile from sample")

        f_texture = fabric_analysis.get("texture_detail", "dense textured loops and yarn weave")

        

        w_name = wood_analysis.get("name", wood_name.replace(".", " "))

        w_color = wood_analysis.get("color_description", "tono natural de madera de la muestra")

        w_texture = wood_analysis.get("texture_detail", "natural anatomical wood grain flow")

        w_finish = wood_analysis.get("finish_type", "Semi-gloss satin")



        furn_item = furniture_analysis.get("furniture_item", furniture_name)

        camera_angle = furniture_analysis.get("camera_angle", "the exact same camera angle as the original photo")

        geom_struct = furniture_analysis.get("geometric_structure", "the exact same geometry and structural shape")



        def get_img_refs(start_idx, count):

            if count <= 1: return f"Image {start_idx}"

            if count == 2: return f"Images {start_idx} and {start_idx + 1}"

            nums = list(range(start_idx, start_idx + count))

            return "Images " + ", ".join(map(str, nums[:-1])) + f", and {nums[-1]}"



        piece_str = "piece" if num_furniture_images == 1 else "pieces"

        photo_str = "photo" if num_furniture_images == 1 else "photos"

        

        if fondo_blanco_sin_sombras:

            scene_str = f"Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, folds, and lighting of the furniture. CAMERA CONSTRAINT: You MUST lock the camera to {camera_angle}. ENVIRONMENT CONSTRAINT: extract ONLY the furniture, do NOT modify its color, texture, or geometry (wood and fabric must be intact), place it perfectly CENTERED on a pure white background, completely eliminate shadows, and remove any studio lighting reflections from the wood and fabric. CRITICAL: DO NOT include any text, numbers, color names, or color palettes in the image. Do not alter the furniture's physical design."

            bg_neg = "shadows, drop shadows, dark background, black background, grey background, original background, room environment,"

        else:

            scene_str = f"Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, folds, lighting, shadows, and surrounding background of the furniture {photo_str}. CAMERA CONSTRAINT: You MUST lock the camera to {camera_angle}. Do not alter the room or the furniture's physical design."

            bg_neg = "changed background, altered environment, changed camera angle, top-down view,"



        if mode == "dual":

            target_imgs = get_img_refs(3, num_furniture_images)

            prompt = f"""INSTRUCTION: Meticulously analyze the source fabric macro texture in Image 1 ({f_name}: {f_color}, {f_texture}), the source wood macro texture in Image 2 ({w_name}: {w_color}, {w_texture}, {w_finish}), and the target furniture {piece_str} in {target_imgs} ('{furn_item}').

GENERATE: Accurately replace BOTH the fabric upholstery AND the wooden components of the furniture in {target_imgs} using the exact textures from Image 1 and Image 2.

GEOMETRY & SCENE CONSTRAINT: {scene_str}

FABRIC CONSTRAINT: Apply the precise weave pattern and thread colors from Image 1. CRITICAL: Scale down this macro texture dramatically (approx. 97% reduction) so it looks like realistic, finely woven fabric from a distance without losing micro-thread details.

WOOD CONSTRAINT: Apply the precise wood grain flow, pores, and color from Image 2 to all legs, frames, and wooden bases. Ensure the grain follows the natural anatomical direction (vertical on legs, horizontal on rails).



Negative Prompt:

generic fabric, solid color, loss of weave pattern, suede, velvet, leather, flat wood colors, color shift, altered geometry, perspective distortion, {bg_neg}"""

        elif mode == "fabric_only":

            target_imgs = get_img_refs(2, num_furniture_images)

            prompt = f"""INSTRUCTION: First, meticulously analyze the source fabric macro texture in Image 1 ({f_name}: {f_color}, {f_texture}) and the target furniture {piece_str} in {target_imgs} ('{furn_item}').

GENERATE: Accurately replace the fabric of the main furniture piece in {target_imgs} using the exact texture analyzed from Image 1.

GEOMETRY & SCENE CONSTRAINT: {scene_str}

MATERIAL & SCALING CONSTRAINT: Apply the precise weave pattern ({f_texture}), thread colors ({f_color}), and textile characteristics from Image 1. CRITICAL: You must scale down this macro texture dramatically (approx. 97% reduction). The final result must look like realistic, finely woven fabric viewed from a distance, explicitly retaining the dense micro-thread details without turning into a flat, solid color or an oversized pattern.



Negative Prompt:

generic fabric, solid color, flat texture, loss of weave pattern, suede, velvet, leather, melted textures, color shift, altered geometry, perspective distortion, text, watermark, poster, collage, infographic, multiple furniture pieces, {bg_neg}"""

        else:

            target_imgs = get_img_refs(2, num_furniture_images)

            prompt = f"""INSTRUCTION: Meticulously analyze the source wood macro texture in Image 1 ({w_name}: {w_color}, {w_texture}, {w_finish}) and the target furniture {piece_str} in {target_imgs} ('{furn_item}').

GENERATE: Accurately replace ONLY the wooden components (legs, frame, base) of the furniture in {target_imgs} using the exact wood grain, finish, and tone analyzed from Image 1.

GEOMETRY & SCENE CONSTRAINT: {scene_str}

MATERIAL CONSTRAINT: Apply the precise wood grain flow, pores, and color ({w_color}) from Image 1. Ensure the grain follows the natural anatomical direction of the furniture parts (vertical on legs, horizontal on rails).



Negative Prompt:

altered fabric, changed upholstery, color shift, flat colors, changed geometry, {bg_neg}"""



        return {

            "google_ai_studio": prompt,

            "flux_midjourney": prompt,

            "dalle_chatgpt": prompt

        }



    def generate_multi_perspective_prompts(

        self,

        mode: str,

        furniture_name: str,

        fabric_name: str = "",

        fabric_analysis: Optional[Dict[str, Any]] = None,

        wood_name: str = "",

        wood_analysis: Optional[Dict[str, Any]] = None,

        furniture_analysis: Optional[Dict[str, Any]] = None,

        analysis: Optional[Dict[str, Any]] = None,

        fondo_blanco_sin_sombras: bool = True,

        num_furniture_images: int = 1

    ) -> Dict[str, Dict[str, str]]:

        

        f_analysis = furniture_analysis or analysis or {}

        fabric_analysis = fabric_analysis or {}

        

        f_name = fabric_analysis.get("name", fabric_name.replace(".", " "))

        f_color = fabric_analysis.get("color_description", f_analysis.get("exact_color_palette", "original color"))

        f_texture = fabric_analysis.get("texture_detail", f_analysis.get("existing_materials", "original materials"))

        

        mat_instruction = f"Perfectly replicate the original materials ({f_texture}). Maintain the exact original color palette ({f_color}) with absolutely NO color shift, no warming, and no cooling. Explicitly retain the specific weave, grain, and textile texture without redesigning. Treat the reference images as the single truth for color and texture."

        

        def get_img_refs(start_idx, count):

            if count <= 1: return "all provided reference images"

            if count == 2: return f"Images {start_idx} and {start_idx + 1}"

            nums = list(range(start_idx, start_idx + count))

            return "Images " + ", ".join(map(str, nums[:-1])) + f", and {nums[-1]}"

            

        ref_imgs = get_img_refs(1, num_furniture_images)

        

        p_lateral = f"""INSTRUCTION: First, thoroughly analyze {ref_imgs} of '{furniture_name}' to synthesize its exact 3D geometry, proportions, and material properties.

GENERATE: A flawless, photorealistic, straight-on lateral profile view (side view) of this exact same furniture piece, facing right.

GEOMETRY CONSTRAINT: Strictly preserve the original structural design, silhouette, armrest shape, backrest angle, and leg dimensions seen in the references. Do not invent new structural elements.

MATERIAL CONSTRAINT: {mat_instruction}

ENVIRONMENT: Professional commercial catalog style. Clean, neutral studio lighting. Solid white or soft light-gray seamless background. Ensure the lighting highlights the true texture of the fabric without washing out the color or creating harsh shadows. High-end architectural visualization quality, 8k resolution.



Negative Prompt:

suede, velvet, smooth surface, generic fabric, leather, melted textures, loss of weave pattern, color shift, darkening, altered geometry, wrong proportions, different furniture design, perspective distortion, 3/4 view, front view, top view, cluttered background, lifestyle background, noisy shadows."""



        p_lateral_left = f"""INSTRUCTION: First, thoroughly analyze {ref_imgs} of '{furniture_name}' to synthesize its exact 3D geometry, proportions, and material properties.

GENERATE: A flawless, photorealistic, straight-on lateral profile view (side view) of this exact same furniture piece, explicitly facing left.

GEOMETRY CONSTRAINT: Strictly preserve the original structural design, silhouette, armrest shape, backrest angle, and leg dimensions seen in the references. Ensure the perspective is completely flipped to show the exact left profile.

MATERIAL CONSTRAINT: {mat_instruction}

ENVIRONMENT: Professional commercial catalog style. Clean, neutral studio lighting. Solid white background. 8k resolution.



Negative Prompt:

right-facing, right profile, suede, velvet, smooth surface, generic fabric, leather, melted textures, loss of weave pattern, color shift, darkening, altered geometry, wrong proportions, perspective distortion, 3/4 view, front view."""



        p_frontal = f"""INSTRUCTION: Meticulously cross-reference and analyze {ref_imgs} of '{furniture_name}' to synthesize its exact 3D geometry and materials.

GENERATE: An absolute, strict ORTHOGONAL front profile view (architectural flat front elevation) of this exact furniture piece.

CAMERA & GEOMETRY CONSTRAINT: The camera angle must be perfectly perpendicular to the exact front center of the furniture. There must be ZERO perspective distortion, ZERO vanishing points, and absolutely ZERO visibility of the sides or top faces. It must be a completely flat, 2D-style strict frontal projection.

MATERIAL CONSTRAINT: {mat_instruction}

ENVIRONMENT: Professional commercial catalog style. Clean, neutral, even studio lighting. Solid white seamless background. Photorealistic, 8k resolution.



Negative Prompt:

3/4 view, side view, angled view, perspective, isometric, depth distortion, vanishing points, visible sides, visible top, suede, velvet, smooth surface, generic fabric, loss of weave pattern, altered geometry, asymmetric."""



        p_3_4 = f"""INSTRUCTION: Meticulously cross-reference and analyze {ref_imgs} of '{furniture_name}' to synthesize its exact 3D volume, depth, and materials.

GENERATE: A flawless, photorealistic 3/4 perspective view (isometric commercial product angle) of this exact furniture piece, oriented facing the LEFT side of the frame.

GEOMETRY CONSTRAINT: The angle must clearly show the front, one side, and the top surfaces to perfectly illustrate the 3D volume of the piece. Strictly preserve the original structural proportions and silhouette.

MATERIAL CONSTRAINT: {mat_instruction}

ENVIRONMENT: Professional commercial catalog style. Clean, neutral studio lighting designed to highlight volume and textile texture. Solid white seamless background. Photorealistic, 8k resolution.



Negative Prompt:

right-facing, right orientation, flat elevation, strict front view, strict side view, top-down view, perspective distortion, distorted proportions, suede, velvet, generic fabric, smooth surface, messy background."""



        p_superior = f"""INSTRUCTION: Meticulously cross-reference and analyze {ref_imgs} of '{furniture_name}' to synthesize its exact 3D geometry, overall footprint, proportions, and material properties.

GENERATE: A flawless, photorealistic, strict direct top-down view (bird's-eye view / flat lay from above) of this exact same furniture piece.

GEOMETRY CONSTRAINT: Strictly preserve the original structural design. The silhouette, cushions, armrests, and overall footprint seen from above must be mathematically accurate. Do not invent new structural elements.

MATERIAL CONSTRAINT: {mat_instruction}

ENVIRONMENT: Professional commercial catalog style. Clean, neutral, even studio lighting from directly above to avoid long unnatural shadows. Solid white seamless background. Photorealistic, 8k resolution.



Negative Prompt:

angled view, perspective view, 3/4 view, side view, front view, isometric, perspective distortion, visible legs, suede, velvet, generic fabric, loss of weave pattern, color shift, altered geometry, wrong proportions, harsh directional shadows."""



        p_lifestyle = f"""INSTRUCTION: Analyze {ref_imgs} of '{furniture_name}' to identify its exact category, precise structural geometry, physical materials, and color.

GENERATE: Place this exact, unmodified furniture piece into a realistic, medium-luxury minimalist interior environment, as if staged in a high-end modern client's home. The furniture must serve as the absolute central focal point of the composition. SIEMPRE cambia de lugar las cosas, la decoraciÃ³n y los muebles de alrededor para que no se vea genÃ©rico. Aleatoriza la disposiciÃ³n y varÃ­a la composiciÃ³n.

ENVIRONMENT & LIGHTING: The surrounding room should feature clean architectural lines, neutral tones, subtle elegant decor, and soft natural lighting coming from large windows.

CAMERA & LENS EFFECT: Apply a strong depth of field effect simulating a high-end photography lens. The foreground (the furniture piece) must be macro-sharp and perfectly defined, preserving its exact original fabric texture ({f_texture}). The background environment must be out of focus, blurred by approximately 60% (smooth, beautiful bokeh effect) to strongly separate the furniture from the room. Photorealistic, 8k, architectural digest editorial style.



Negative Prompt:

altered furniture design, changed texture, changed color, wrong proportions, messy room, cluttered background, cheap decor, overly opulent/baroque decor, sharp background, deep depth of field, flat lighting, artificial studio lighting, 3d render look, plastic look, floating furniture."""



        return {

            "lateral_derecha": {

                "titulo": "?? 1. Vista Lateral (Derecha)",

                "google_ai_studio": p_lateral,

                "dalle_chatgpt": p_lateral,

                "flux_midjourney": p_lateral

            },

            "lateral_izquierda": {

                "titulo": "?? 2. Vista Lateral (Izquierda)",

                "google_ai_studio": p_lateral_left,

                "dalle_chatgpt": p_lateral_left,

                "flux_midjourney": p_lateral_left

            },

            "frontal_ortogonal": {

                "titulo": "?? 3. Vista Frontal Ortogonal",

                "google_ai_studio": p_frontal,

                "dalle_chatgpt": p_frontal,

                "flux_midjourney": p_frontal

            },

            "tres_cuartos": {

                "titulo": "?? 4. Vista 3/4 (Comercial)",

                "google_ai_studio": p_3_4,

                "dalle_chatgpt": p_3_4,

                "flux_midjourney": p_3_4

            },

            "cenital": {

                "titulo": "?? 5. Vista Superior (Top-Down)",

                "google_ai_studio": p_superior,

                "dalle_chatgpt": p_superior,

                "flux_midjourney": p_superior

            },

            "lifestyle": {

                "titulo": "??? 6. Entorno Lifestyle (Fondo Desenfocado)",

                "google_ai_studio": p_lifestyle,

                "dalle_chatgpt": p_lifestyle,

                "flux_midjourney": p_lifestyle

            }

        }



ai_prompt_service = AIPromptService()



ai_prompt_service = AIPromptService()




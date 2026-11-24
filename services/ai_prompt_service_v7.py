"""
Motor de Prompts V7 · Studio Maestro (Todo en Uno).

Unifica y mejora todas las capacidades de V1–V6 sin modificar las versiones anteriores:
  * 9 modos completos: catalogo (7 imágenes), vista_suelta (11 ángulos), material (madera/tela/dual),
    entorno (casa de cliente inteligente por categoría + habitación), plano (dibujo técnico CAD),
    extraer (fondo blanco #FFFFFF), hd (remaster 8K), vistas_tela (lote multi-vista),
    clonar_color (lote clonar color/material de referencia a múltiples vistas).
  * Mapeo dinámico y exacto de ranuras de imagen (Image 1, Image 2, Image 3...) para que el ancla
    de Vista 1 nunca choque con muestras de madera o tela adjuntas.
  * Prompts modernizados, limpios (sin ruido de nombres de archivo crudos), con encuadre calibrado,
    reglas anti-alucinación por categoría y soporte opcional de madera/tela en cualquier modo.
"""

from __future__ import annotations

import base64
from collections import deque
import concurrent.futures
import io
import json
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self) -> Dict[str, Any]:
            return dict(self.__dict__)

    def Field(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        return kwargs.get("default", None)


class MaterialAnalysisV7(BaseModel):
    name: str = Field(description="Nombre comercial corto y premium del material")
    color_description: str = Field(description="Descripción cromática orgánica exacta, calidez y subtonos")
    texture_detail: str = Field(description="Micro-textura, veta o tramado textil")
    light_interaction: str = Field(description="Respuesta ante la luz: mate, satinado, brillo suave")


class FurnitureAnalysisV7(BaseModel):
    furniture_item: str = Field(description="Tipo de mueble y estilo arquitectónico")
    camera_angle: str = Field(description="Ángulo de cámara observado")
    lighting_direction: str = Field(description="Dirección de iluminación")
    geometric_structure: str = Field(description="Topología 3D, silueta, ensambles y estructura")
    wood_and_finish_analysis: str = Field(description="Especie de madera, veta y acabado")
    upholstery_analysis: str = Field(description="Tapicería y color o 'Sin tapicería'")
    existing_materials: str = Field(description="Resumen técnico integral de materiales")
    wood_details: Optional[str] = Field(default="", description="Detalle específico de madera")


MODES: Dict[str, str] = {
    "catalogo": "7 Vistas",
    "vista_suelta": "1 Vista",
    "material": "Tela / Madera",
    "entorno": "Entorno",
    "plano": "Plano",
    "extraer": "Fondo Blanco",
    "hd": "HD 8K",
    "vistas_tela": "Lote Tela",
    "clonar_color": "Clonar Color",
}

VIEW_IDS: List[str] = [
    "vista_frontal",
    "vista_perspectiva_3_4",
    "vista_lateral",
    "vista_picada_alta",
    "vista_superior_cenital",
    "vista_plano_tecnico",
    "vista_entorno_cliente",
]

ALL_SINGLE_VIEWS: Dict[str, Dict[str, str]] = {
    "vista_frontal": {"label": "1 · Frontal 0°", "short": "Frontal 0°", "icon": "🖼️"},
    "vista_perspectiva_3_4": {"label": "2 · 3/4 (45°)", "short": "3/4 (45°)", "icon": "📐"},
    "vista_lateral": {"label": "3 · Lateral 90°", "short": "Lateral 90°", "icon": "➡️"},
    "vista_picada_alta": {"label": "4 · Picada 65°", "short": "Picada 65°", "icon": "↗️"},
    "vista_superior_cenital": {"label": "5 · Superior 90°", "short": "Superior 90°", "icon": "🔝"},
    "vista_plano_tecnico": {"label": "6 · Plano Medidas", "short": "Plano", "icon": "📏"},
    "vista_entorno_cliente": {"label": "7 · Entorno", "short": "Entorno", "icon": "🏡"},
    "vista_3_4_izquierda": {"label": "3/4 Izquierda", "short": "3/4 Izq.", "icon": "↙️"},
    "vista_3_4_derecha": {"label": "3/4 Derecha", "short": "3/4 Der.", "icon": "↘️"},
    "vista_lateral_izquierda": {"label": "Lateral Izquierda", "short": "Lateral Izq.", "icon": "⬅️"},
    "vista_3_4_posterior": {"label": "3/4 Posterior", "short": "3/4 Trasera", "icon": "🔄"},
}

ANCHOR_VIEWS = {
    "vista_perspectiva_3_4",
    "vista_lateral",
    "vista_picada_alta",
    "vista_superior_cenital",
    "vista_entorno_cliente",
    "vista_3_4_izquierda",
    "vista_3_4_derecha",
    "vista_lateral_izquierda",
    "vista_3_4_posterior",
}

_COMMON_CHECKS = [
    "¿Es exactamente el MISMO mueble (silueta, proporciones, color y textura) que la foto original?",
    "¿Se aplicó exactamente la misma textura y tono de la tela en todo el casco (respaldo, brazos, faldón) y cojines a escala real?",
    "¿Se respetaron todos los detalles sin inventar patas, puertas, cajones ni molduras inexistentes?",
]
_WHITE_CHECKS = [
    "¿Fondo blanco puro (#FFFFFF), centrado con márgenes parejos, sin piso, 0% sombras y 0% reflejos?",
]

CHECKLISTS: Dict[str, List[str]] = {
    "vista_frontal": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Está totalmente de frente (0°), nivelado y centrado?"],
    "vista_perspectiva_3_4": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Cambió el ángulo a 3/4 (~45°) mostrando frente y profundidad lateral?"],
    "vista_lateral": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Es un perfil lateral estricto a 90° (sin ángulo 3/4)?"],
    "vista_lateral_izquierda": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Es un perfil lateral izquierdo estricto a 90°?"],
    "vista_3_4_izquierda": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Muestra el ángulo 3/4 orientado hacia la izquierda?"],
    "vista_3_4_derecha": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Muestra el ángulo 3/4 orientado hacia la derecha, en 2054×2054 y con 0% sombras?"],
    "vista_3_4_posterior": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Muestra correctamente la parte trasera y el perfil 3/4 posterior?"],
    "vista_picada_alta": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Se ve desde arriba en ángulo elevado (60°–70°) y no horizontal?"],
    "vista_superior_cenital": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Es vista cenital estricta a 90° (plana desde arriba)?"],
    "vista_plano_tecnico": [
        "¿Son exclusivamente líneas negras (#000000) sobre blanco (#FFFFFF), sin color, sombras ni texturas?",
        "¿Muestra únicamente las cotas solicitadas con flechas limpias y números legibles en cm?",
        "¿Los números coinciden exactamente con las medidas confirmadas?",
    ],
    "vista_entorno_cliente": [
        "¿Toma arquitectónica lejana mostrando la habitación completa?",
        "¿El mueble tiene escala 1:1 coherente frente al tapete, muro y muebles acompañantes?",
        "¿La paleta del cuarto contrasta con el mueble para que destaque sin camuflarse?",
        "¿Coincide con la habitación y categoría del mueble?",
    ],
    "extraer": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Centrado al ~70% del lienzo con márgenes blancos parejos?"],
    "hd": _COMMON_CHECKS + ["¿Mayor nitidez en vetas/tejido SIN cambiar tono, forma ni geometría?"],
    "material": [
        "¿La forma, proporciones y costuras/ensambles del mueble permanecieron intactos?",
        "¿La misma textura y tono exacto de la tela cubrió al 100% todo el casco (respaldo, brazos, base/faldón) y cojines?",
        "¿La trama textil se ve a escala real de mueble (no macro agrandada ni lisa como pintura)?",
    ],
    "vistas_tela": _COMMON_CHECKS + [
        "¿Conservó el ángulo exacto de cada vista y aplicó la misma textura de tela en todo el casco y cojines?"
    ],
    "clonar_color": _COMMON_CHECKS + [
        "¿Clonó el color y acabado exacto de la foto referencia manteniendo el ángulo de cada vista?"
    ],
}

ROOM_PRESETS: List[str] = [
    "Automático",
    "Sala",
    "Comedor",
    "Recámara",
    "Recibidor",
    "Estudio",
    "Terraza",
]


class AIPromptServiceV7:
    _BUILTIN_KEY_B64 = "QVEuQWI4Uk42TDJjOXI4b01jb1RvQTlJR1pTcGxFaDU2R3M5UzFBQ3JZQWRqN2thRkZWSFE="

    def __init__(self) -> None:
        self._builtin_key = base64.b64decode(self._BUILTIN_KEY_B64).decode("utf-8")
        self.default_api_key = self._builtin_key
        self._clients: Dict[str, Any] = {}
        self._preferred_model: Optional[str] = None
        self._img_quota_exhausted_until: float = 0.0
        self.last_image_error: Optional[str] = None

    def get_api_key(self, custom_key: Optional[str] = None) -> str:
        from services.gemini_runtime import is_key_rejected

        if custom_key and custom_key.strip():
            return custom_key.strip()
        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as ef:
                    for line in ef:
                        line_s = line.strip()
                        if line_s.startswith("GEMINI_API_KEY="):
                            val = line_s.split("=", 1)[1].strip().strip('"').strip("'")
                            if val and not is_key_rejected(val):
                                return val
        except Exception:
            pass
        try:
            import streamlit as st
            if "GEMINI_API_KEY" in st.secrets:
                s_val = str(st.secrets["GEMINI_API_KEY"]).strip()
                if s_val and not is_key_rejected(s_val):
                    return s_val
        except Exception:
            pass
        env_val = os.getenv("GEMINI_API_KEY", "").strip()
        if env_val and not is_key_rejected(env_val):
            return env_val
        return self._builtin_key

    @staticmethod
    def format_gemini_error(err: Exception) -> str:
        txt = str(err)
        up = txt.upper()
        if "LEAKED" in up:
            return (
                "Tu GEMINI_API_KEY actual fue bloqueada por Google porque se detectó filtrada públicamente (Error 403). "
                "Genera una llave nueva en Google AI Studio y pégala en el botón '🔑 API Key' del encabezado (o en Render > Environment)."
            )
        if "API_KEY_INVALID" in up or "API KEY NOT VALID" in up or "UNAUTHENTICATED" in up or "401" in up:
            return "La GEMINI_API_KEY no es válida. Verifica la clave en '🔑 API Key'."
        if "RESOURCE_EXHAUSTED" in up or "429" in up or "QUOTA" in up:
            return "Límite de cuota alcanzado en Gemini API (429). Espera unos segundos o usa una cuenta con facturación activa para generación masiva."
        return f"Aviso de Gemini API: {txt[:220]}"

    def get_client(self, api_key: Optional[str] = None) -> Any:
        from services.gemini_runtime import build_genai_client

        key = self.get_api_key(api_key)
        if not key:
            return None
        if key in self._clients:
            return self._clients[key]
        try:
            client = build_genai_client(key)
            if client is not None:
                self._clients[key] = client
            return client
        except Exception as e:
            print(f"[AIPromptServiceV7] Error instanciando cliente: {e}")
            return None

    @staticmethod
    def _pil_to_b64_jpeg(img: Image.Image, quality: int = 85) -> str:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _call_gemini(
        self,
        client: Any,
        contents: Any,
        config: Any = None,
        api_key: Optional[str] = None,
    ) -> Any:
        from services.gemini_runtime import call_gemini_fast, get_last_vision_meta

        active_key = (api_key or "").strip() or self.get_api_key()
        res = call_gemini_fast(
            client=client,
            contents=contents,
            config=config,
            api_key=active_key,
            fallback_key=self._builtin_key if active_key != self._builtin_key else "",
        )
        meta = get_last_vision_meta()
        if meta.get("model"):
            self._preferred_model = meta["model"]
        return res

    def _prepare_image(self, img_bytes: bytes, max_dim: int = 512) -> Image.Image:
        with Image.open(io.BytesIO(img_bytes)) as src:
            img = ImageOps.exif_transpose(src)
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                alpha = img.split()[-1] if "A" in img.getbands() else None
                bg.paste(img, mask=alpha)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            if max(img.size) > max_dim:
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=78, optimize=True)
        buf.seek(0)
        with Image.open(buf) as compressed:
            compressed.load()
            return compressed.copy()

    # ------------------------------------------------------------------
    # ANÁLISIS DE VISIÓN (CON FALLBACK LOCAL INTELIGENTE)
    # ------------------------------------------------------------------
    def analyze_material(
        self,
        sample_bytes: bytes,
        api_key: Optional[str] = None,
        material_type: str = "auto",
        sample_name: str = "",
    ) -> Dict[str, Any]:
        key = self.get_api_key(api_key)
        mtype = (material_type or "auto").strip().lower()
        is_fabric = any(k in mtype for k in ("fabric", "tela", "textil", "upholstery", "tapiz"))
        is_wood = any(k in mtype for k in ("wood", "madera", "timber"))

        clean_label = (sample_name or "").rsplit(".", 1)[0].replace("_", " ").strip()
        if is_fabric:
            default_material = MaterialAnalysisV7(
                name=clean_label or "Lino / Bouclé Tejido Natural",
                color_description="exact hue, tonal warmth, and woven thread undertones visible in the attached fabric swatch",
                texture_detail="fine intertwined upholstery textile weave with realistic tactile thread density",
                light_interaction="soft matte textile light absorption without synthetic glare",
            ).model_dump()
            instructions = (
                "Analyze this upholstery fabric sample with surgical precision for luxury furniture photography: "
                "identify the weave family, exact hue, undertones, AND multi-tone flecks/threads (color_description), "
                "exact weave structure, yarn thickness, and under-weave contrast in English (texture_detail, e.g. 'dense nubby loops over cool grey under-weave'), "
                "and surface light response (light_interaction: Matte, Soft matte textile, Directional sheen, or Semi-gloss satin)."
            )
        elif is_wood:
            default_material = MaterialAnalysisV7(
                name=clean_label or "Madera Natural Seleccionada",
                color_description="exact timber stain hue, warmth, and natural grain contrast visible in the attached wood sample",
                texture_detail="continuous natural wood grain pores and realistic timber surface fibers",
                light_interaction="soft satin-matte timber sheen without plastic glare",
            ).model_dump()
            instructions = (
                "Analyze this timber / wood sample with precision: identify species/stain family, exact color warmth and undertones "
                "(without generic hex codes), grain flow/pore openness, and surface sheen (matte, low-lustre satin)."
            )
        else:
            default_material = MaterialAnalysisV7(
                name=clean_label or "Material Natural Seleccionado",
                color_description="exact surface tone and undertones visible in the attached material reference",
                texture_detail="authentic natural grain or woven surface structure",
                light_interaction="soft natural satin-matte light response",
            ).model_dump()
            instructions = f"Analyze this material sample ({material_type}) with precision: name, color description, texture detail, light interaction."

        if not key or not sample_bytes:
            return default_material

        try:
            from google.genai import types

            client = self.get_client(key)
            if not client:
                return default_material
            img = self._prepare_image(sample_bytes, max_dim=1024 if is_fabric else 768)
            res = self._call_gemini(
                client=client,
                contents=[f"You are an expert luxury furniture materials engineer. {instructions}", img],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MaterialAnalysisV7,
                    temperature=0.1,
                ),
                api_key=key,
            )
            data = json.loads(res.text)
            if clean_label and (not data.get("name") or "fallback" in data.get("name", "").lower()):
                data["name"] = clean_label
            return data
        except Exception as e:
            print(f"[AIPromptServiceV7] Error analyzing material: {e}")
            return default_material

    def analyze_furniture_for_enhancement(
        self,
        furniture_bytes: Any,
        reference_bytes: Optional[List[bytes]] = None,
        wood_bytes: Optional[List[bytes]] = None,
        fabric_bytes: Optional[List[bytes]] = None,
        notas_usuario: str = "",
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        notes_clean = (notas_usuario or "").strip()
        lower_notes = notes_clean.lower()
        inferred_type = "contemporary architectural furniture piece"
        if any(w in lower_notes for w in ("espejo", "mirror", "luna")):
            inferred_type = "minimalist wooden wall mirror with reflective glass"
        elif any(w in lower_notes for w in ("buro", "buró", "noche", "velador", "nightstand")):
            inferred_type = "modern wooden nightstand / buró"
        elif "cama" in lower_notes or "bed" in lower_notes:
            inferred_type = "minimalist low-profile platform bed frame"
        elif any(w in lower_notes for w in ("sofa", "sofá", "sillon", "sillón", "silla", "butaca")):
            inferred_type = "contemporary upholstered seating piece"
        elif any(w in lower_notes for w in ("mesa", "table", "escritorio", "comedor", "consola")):
            inferred_type = "architectural table"
        elif any(w in lower_notes for w in ("credenza", "aparador", "comoda", "cómoda", "librero")):
            inferred_type = "architectural storage credenza / dresser"

        fallback = FurnitureAnalysisV7(
            furniture_item=inferred_type,
            camera_angle="reference angle in attached photo",
            lighting_direction="balanced soft studio fill",
            geometric_structure="exact 3D silhouette, joinery, leg architecture, and physical proportions directly from the attached furniture photo",
            wood_and_finish_analysis="authentic timber tone, grain, and surface sheen from the attached reference",
            upholstery_analysis="authentic textile weave and tone from the attached reference",
            existing_materials="authentic materials, colors, and surface finishes directly from the attached reference",
        ).model_dump()
        fallback["has_wood_sample"] = bool(wood_bytes)
        fallback["has_fabric_sample"] = bool(fabric_bytes)

        key = self.get_api_key(api_key)
        if not key:
            return fallback

        try:
            from google.genai import types

            client = self.get_client(key)
            if not client:
                return fallback

            actual_imgs: List[Image.Image] = []
            for fb in (furniture_bytes if isinstance(furniture_bytes, list) else [furniture_bytes])[:2]:
                if fb:
                    actual_imgs.append(self._prepare_image(fb, max_dim=768))

            wood_imgs: List[Image.Image] = []
            for wb in (wood_bytes or [])[:1]:
                if wb:
                    wood_imgs.append(self._prepare_image(wb, max_dim=768))

            fab_imgs: List[Image.Image] = []
            for tb in (fabric_bytes or [])[:1]:
                if tb:
                    fab_imgs.append(self._prepare_image(tb, max_dim=1024))

            ref_imgs: List[Image.Image] = []
            for rb in (reference_bytes or [])[:1]:
                if rb:
                    ref_imgs.append(self._prepare_image(rb, max_dim=512))

            prompt = (
                "You are an expert furniture visualizer and commercial product photographer. "
                "Analyze the furniture photo(s) (and any attached material swatches) to produce a concise, accurate "
                "3D geometric & camera specification: item type/style, EXACT camera_angle and framing "
                "(e.g. 'strict eye-level 3/4 view facing right', 'horizontal side profile'), "
                "exact geometric_structure (silhouette, cushions, seams, folds, legs/base), "
                "lighting_direction, wood_and_finish_analysis, and upholstery_analysis."
            )
            if wood_imgs:
                prompt += "\nA wood sample image is attached as ground truth for all wooden components."
            if fab_imgs:
                prompt += "\nA fabric swatch image is attached as ground truth for all upholstered components."
            if notes_clean:
                prompt += f"\n\nUSER CONTEXT:\n{notes_clean}"

            contents: List[Any] = [prompt] + actual_imgs + wood_imgs + fab_imgs + ref_imgs
            res = self._call_gemini(
                client=client,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=FurnitureAnalysisV7,
                    temperature=0.1,
                ),
                api_key=key,
            )
            data = json.loads(res.text)
            if not data.get("existing_materials"):
                w = data.get("wood_and_finish_analysis", "")
                u = data.get("upholstery_analysis", "")
                data["existing_materials"] = f"{w}, {u}".strip(", ")
            data["has_wood_sample"] = bool(wood_imgs)
            data["has_fabric_sample"] = bool(fab_imgs)
            return data
        except Exception as e:
            print(f"[AIPromptServiceV7] Error analyzing furniture: {e}")
            return fallback

    def analyze_all_parallel(
        self,
        furniture_bytes: Optional[List[bytes]] = None,
        wood_bytes: Optional[bytes] = None,
        wood_name: str = "",
        fabric_bytes: Optional[bytes] = None,
        fabric_name: str = "",
        notas_ia: str = "",
        skip_furniture: bool = False,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Ejecuta en paralelo el análisis de visión de mueble, tela y madera (~1.1s total)."""
        f_ana: Dict[str, Any] = {}
        w_ana: Optional[Dict[str, Any]] = None
        t_ana: Optional[Dict[str, Any]] = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            fut_f = (
                ex.submit(
                    self.analyze_furniture_for_enhancement,
                    furniture_bytes=furniture_bytes,
                    wood_bytes=[wood_bytes] if wood_bytes else None,
                    fabric_bytes=[fabric_bytes] if fabric_bytes else None,
                    notas_usuario=notas_ia,
                )
                if (furniture_bytes and not skip_furniture)
                else None
            )
            fut_w = (
                ex.submit(self.analyze_material, wood_bytes, material_type="wood", sample_name=wood_name)
                if wood_bytes
                else None
            )
            fut_t = (
                ex.submit(self.analyze_material, fabric_bytes, material_type="fabric", sample_name=fabric_name)
                if fabric_bytes
                else None
            )

            if fut_f is not None:
                f_ana = fut_f.result()
            if fut_w is not None:
                w_ana = fut_w.result()
            if fut_t is not None:
                t_ana = fut_t.result()

        return f_ana, w_ana, t_ana

    # ------------------------------------------------------------------
    # PERFIL, DIMENSIONES Y DETECCIÓN DE SUB-CATEGORÍA
    # ------------------------------------------------------------------
    def detect_furniture_profile(
        self, furn_item: str, user_notes: str = "", geom_struct: str = ""
    ) -> Dict[str, Any]:
        text_to_search = f"{furn_item} {user_notes} {geom_struct}".lower()

        category = "general"
        sub_category = "general"
        if any(w in text_to_search for w in ("espejo", "mirror", "luna", "cristal de espejo")):
            category = "mirror"
            sub_category = "mirror"
        elif any(w in text_to_search for w in ("cama", "bed", "cabecera", "headboard", "somier")):
            category = "bed"
            sub_category = "bed"
        elif any(w in text_to_search for w in ("silla", "chair", "sillon", "sillón", "sofa", "sofá", "banca", "bench", "banqueta", "stool", "butaca", "poltrona")):
            category = "seating"
            if any(w in text_to_search for w in ("sofa", "sofá", "loveseat", "modular")):
                sub_category = "sofa"
            elif any(w in text_to_search for w in ("silla", "chair")):
                sub_category = "chair"
            else:
                sub_category = "armchair"
        elif any(w in text_to_search for w in ("mesa", "table", "escritorio", "desk", "comedor", "consola", "arrimo", "bureau")):
            category = "table"
            if any(w in text_to_search for w in ("lateral", "auxiliar", "esquin", "side", "end table")):
                sub_category = "side_table"
            elif any(w in text_to_search for w in ("centro", "coffee", "ratona")):
                sub_category = "coffee_table"
            elif any(w in text_to_search for w in ("comedor", "dining")):
                sub_category = "dining_table"
            elif any(w in text_to_search for w in ("consola", "arrimo", "recibidor")):
                sub_category = "console_table"
            elif any(w in text_to_search for w in ("escritorio", "desk")):
                sub_category = "desk"
            else:
                sub_category = "table"
        elif any(w in text_to_search for w in ("buro", "buró", "noche", "velador", "cajon", "cajón", "comoda", "cómoda", "credenza", "aparador", "librero", "armario", "closet", "buffet", "gabinete", "nightstand", "dresser")):
            category = "storage"
            if any(w in text_to_search for w in ("buro", "buró", "noche", "velador", "nightstand")):
                sub_category = "nightstand"
            else:
                sub_category = "storage"

        height_cm: Optional[float] = None
        width_cm: Optional[float] = None
        depth_cm: Optional[float] = None
        diam_cm: Optional[float] = None

        m_diam_h = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:cm)?\s*(?:diam|di[aá]metro)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)",
            text_to_search,
        )
        if m_diam_h:
            diam_cm = float(m_diam_h.group(1))
            height_cm = float(m_diam_h.group(2))
        else:
            m_diam = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*(?:cm)?\s*(?:diam(?:etro)?|di[aá]metro)(?![a-z])"
                r"|(?:^|[\s,(x*])(?:d\.|diam\.?|di[aá]metro|ø)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)",
                text_to_search,
            )
            if m_diam:
                diam_cm = float(m_diam.group(1) or m_diam.group(2))

        m_w_bef = re.search(
            r"(?<![A-Za-z0-9.])([0-9]+(?:\.[0-9]+)?)\s*(?:cm|m)?\s*(?:frente|ancho|largo|width)(?![a-z])",
            text_to_search,
        )
        if m_w_bef:
            width_cm = float(m_w_bef.group(1))
        m_d_bef = re.search(
            r"(?<![A-Za-z0-9.])([0-9]+(?:\.[0-9]+)?)\s*(?:cm|m)?\s*(?:fondo|profundidad|prof|depth)(?![a-z])",
            text_to_search,
        )
        if m_d_bef:
            depth_cm = float(m_d_bef.group(1))
        m_h_bef = re.search(
            r"(?<![A-Za-z0-9.])([0-9]+(?:\.[0-9]+)?)\s*(?:cm|m)?\s*(?:alto|altura|height)(?![a-z])",
            text_to_search,
        )
        if m_h_bef:
            height_cm = float(m_h_bef.group(1))

        if not width_cm:
            m_w_aft = re.search(r"(?:frente|ancho|largo|width)[\s:]*([0-9]+(?:\.[0-9]+)?)", text_to_search)
            if m_w_aft:
                width_cm = float(m_w_aft.group(1))
        if not depth_cm:
            m_d_aft = re.search(r"(?:fondo|profundidad|prof|depth)[\s:]*([0-9]+(?:\.[0-9]+)?)", text_to_search)
            if m_d_aft:
                depth_cm = float(m_d_aft.group(1))
        if not height_cm:
            m_h_aft = re.search(r"(?:alto|altura|height)[\s:]*([0-9]+(?:\.[0-9]+)?)", text_to_search)
            if m_h_aft:
                height_cm = float(m_h_aft.group(1))

        if not (width_cm and depth_cm and height_cm) and not diam_cm:
            m_triplet = re.search(
                r"([0-9]+(?:\.[0-9]+)?)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)\s*[xX*]\s*([0-9]+(?:\.[0-9]+)?)",
                text_to_search,
            )
            if m_triplet:
                width_cm, depth_cm, height_cm = (
                    float(m_triplet.group(1)),
                    float(m_triplet.group(2)),
                    float(m_triplet.group(3)),
                )

        if category == "mirror" and width_cm and depth_cm and height_cm:
            real_h = max(depth_cm, height_cm)
            real_t = min(depth_cm, height_cm)
            height_cm, depth_cm = real_h, real_t

        dims: List[str] = []
        if diam_cm:
            dims.append(f"Diameter: {self._fmt_num(diam_cm)} cm")
        if width_cm:
            dims.append(f"Width/Frente: {self._fmt_num(width_cm)} cm")
        if depth_cm:
            dims.append(f"{'Thickness/Grosor' if category == 'mirror' else 'Depth/Fondo'}: {self._fmt_num(depth_cm)} cm")
        if height_cm:
            dims.append(f"Height/Alto: {self._fmt_num(height_cm)} cm")

        dimensions_rule = ""
        if dims:
            dim_str = ", ".join(dims)
            aspect_note = ""
            if category == "mirror":
                aspect_note = (
                    f" (Flat vertical wall-mounted mirror: {self._fmt_num(width_cm or 0)} cm wide x "
                    f"{self._fmt_num(height_cm or 0)} cm tall x {self._fmt_num(depth_cm or 0)} cm slim thickness; "
                    f"NOT a table, NOT a credenza)"
                )
            elif height_cm and width_cm:
                ratio = width_cm / height_cm
                if ratio > 2.0:
                    aspect_note = " (Low-profile elongated horizontal proportions; low to the ground, NOT a tall cabinet or console)"
                elif ratio < 0.8:
                    aspect_note = " (Tall slender vertical silhouette)"
            dimensions_rule = (
                f"Real-world 1:1 scale ({dim_str}){aspect_note}. "
                "Preserve exact physical proportions, leg-to-body ratio, and joinery from the reference without stretching."
            )

        # Configuración específica por categoría
        if category == "mirror":
            parts_str = "perimeter wood frame, curved corner radii, outer border profile, inner bevel, and edge joinery"
            mirror_optics = (
                "Reflective Mirror Glass Physics: The central pane must be authentic 4mm silvered reflective glass "
                "with a subtle soft studio highlight gradient (no room or window reflections) and a crisp inner perimeter bevel."
            )
            geometry_rule = (
                "Keep the exact organic asymmetric or curved silhouette, slim frame depth, and natural orientation "
                "from the reference. Do NOT make it round/oval/rectangular if it is organic, and do NOT add legs, "
                "shelves, shadowbox ledges, doors, or drawers."
            )
            neg_add = ", two-tone frame, interior shelf, shadowbox, drawers, handles, legs, opaque grey glass, room reflection"
            angles = {
                "vista_frontal": "Direct 0-degree flat front elevation view, camera dead-center level with the mirror, displaying the full perimeter frame and reflective glass.",
                "vista_perspectiva_3_4": "Commercial 3/4 perspective at a 45-degree angle showing front frame, slim side depth, corner curvature, and subtle glass sheen.",
                "vista_lateral": "Strict 90-degree orthogonal lateral side profile showing the slim vertical frame thickness from front edge to wall-mount back.",
                "vista_lateral_izquierda": "Strict 90-degree orthogonal left lateral side profile showing the slim vertical thickness and edge grain.",
                "vista_3_4_izquierda": "Commercial 3/4 perspective at 45 degrees angled toward the left, highlighting left frame thickness and bevel depth.",
                "vista_3_4_derecha": "Commercial 3/4 perspective at 45 degrees angled toward the right, highlighting right frame thickness and bevel depth.",
                "vista_3_4_posterior": "Elevated 3/4 rear angle showing the clean backing panel, wall-mount cleats/hardware, and outer wood frame joinery.",
                "vista_picada_alta": "High-angle elevated 3/4 view at 65 degrees looking down at the upper frame rail and glass highlight.",
                "vista_superior_cenital": "Strict 90-degree orthogonal overhead plan view (camera pitch -90°) pointing straight down at the slim top wooden edge; zero front face visible.",
            }
        elif category == "seating":
            parts_str = "wooden legs, armrests, backrest structure, seat chassis, and exposed joinery"
            mirror_optics = ""
            geometry_rule = (
                f"Preserve the exact chair/sofa silhouette, backrest rake, cushion thickness, armrest curve, and leg stance ({geom_struct}). "
                "Do NOT invent extra buttons, tufting, drawers, or different legs."
            )
            neg_add = ", invented drawers, altered leg count, mismatched cushions, distorted seat rake"
            angles = {
                "vista_frontal": "Direct 0-degree eye-level front elevation showcasing front legs, seat cushion width, armrests, and backrest symmetry.",
                "vista_perspectiva_3_4": "Commercial 3/4 perspective at a 45-degree angle displaying seat depth, side profile, armrest curve, and leg splay.",
                "vista_lateral": "Strict 90-degree orthogonal lateral side profile showing backrest incline, seat angle, and front-to-back leg stance.",
                "vista_lateral_izquierda": "Strict 90-degree orthogonal left lateral side profile showing full backrest and seat contour.",
                "vista_3_4_izquierda": "Commercial 3/4 perspective angled toward the left, showcasing front-left silhouette and cushion volume.",
                "vista_3_4_derecha": "Commercial 3/4 perspective angled toward the right, showcasing front-right silhouette and cushion volume.",
                "vista_3_4_posterior": "Clean 3/4 rear perspective showcasing the back of the backrest, rear joinery, and rear leg construction.",
                "vista_picada_alta": "High-angle 65-degree semi-top view looking down at the seat cushion plane, armrests, and upper backrest joinery.",
                "vista_superior_cenital": "Strict 90-degree orthogonal overhead plan view looking vertically straight down onto the seat cushion and top backrest edge.",
            }
        elif category == "table":
            parts_str = "tabletop surface, perimeter edge profile, under-structure, and legs/pedestal/sculptural base"
            mirror_optics = ""
            geometry_rule = (
                f"Preserve the exact tabletop shape (round/oval/rectangular/organic), edge thickness, and base/leg architecture ({geom_struct}). "
                "Do NOT redesign the base, do NOT add drawers, cabinet doors, or aprons that do not exist."
            )
            neg_add = ", altered tabletop shape, redesigned base, invented drawers, cabinet doors, unwanted wooden apron"
            angles = {
                "vista_frontal": "Direct 0-degree front elevation at eye level showcasing tabletop edge thickness, full base/pedestal silhouette, and floor stance.",
                "vista_perspectiva_3_4": "Commercial 3/4 perspective at a 45-degree angle displaying tabletop surface, side depth, and full 3D base/leg architecture.",
                "vista_lateral": "Strict 90-degree orthogonal lateral side profile showing tabletop side thickness, overhang, and base silhouette.",
                "vista_lateral_izquierda": "Strict 90-degree orthogonal left lateral side profile showing tabletop overhang and under-structure.",
                "vista_3_4_izquierda": "Commercial 3/4 perspective angled toward the left showing tabletop grain/finish and base proportions.",
                "vista_3_4_derecha": "Commercial 3/4 perspective angled toward the right showing tabletop grain/finish and base proportions.",
                "vista_3_4_posterior": "Clean 3/4 rear perspective confirming consistent under-structure and back-side joinery.",
                "vista_picada_alta": "High-angle 65-degree semi-top view looking down across the tabletop surface, perimeter edge, and visible base below.",
                "vista_superior_cenital": "Strict 90-degree orthogonal overhead plan view pointing vertically straight down at the tabletop surface, showing true perimeter contour and surface grain/veining.",
            }
        elif category == "bed":
            parts_str = "headboard panel, side rails, footboard, platform base, legs, and joinery"
            mirror_optics = ""
            geometry_rule = (
                f"Preserve the exact bed frame silhouette, headboard height/proportions, and platform clearance ({geom_struct}). "
                "Do NOT add unrequested bedding/pillows in studio product cutouts unless already present in Image 1."
            )
            neg_add = ", mismatched rails, altered headboard height, unrequested clutter"
            angles = {
                "vista_frontal": "Direct 0-degree front elevation from the foot of the bed showing footboard, side rail alignment, and headboard elevation.",
                "vista_perspectiva_3_4": "Commercial 3/4 perspective at 45 degrees showing headboard depth, side rail length, platform deck, and legs.",
                "vista_lateral": "Strict 90-degree orthogonal lateral side profile showing headboard vertical angle, side rail thickness, and under-bed clearance.",
                "vista_lateral_izquierda": "Strict 90-degree orthogonal left lateral side profile showing full frame depth and clearance.",
                "vista_3_4_izquierda": "Commercial 3/4 perspective angled toward the left showing headboard and left rail joinery.",
                "vista_3_4_derecha": "Commercial 3/4 perspective angled toward the right showing headboard and right rail joinery.",
                "vista_3_4_posterior": "Clean 3/4 rear perspective displaying the back of the headboard panel and rear frame joinery.",
                "vista_picada_alta": "High-angle 65-degree semi-top view looking down at the headboard face, platform deck, and perimeter rails.",
                "vista_superior_cenital": "Strict 90-degree orthogonal overhead plan view looking vertically straight down at the full bed frame rectangle.",
            }
        elif category == "storage":
            parts_str = "drawer and door faces, handles/pulls, outer chassis, side panels, top surface, and legs"
            mirror_optics = ""
            geometry_rule = (
                f"Preserve the exact cabinet dimensions, drawer/door count, handle style and placement, and leg height ({geom_struct}). "
                "Keep all panels unified without inventing two-tone contrast unless present in Image 1."
            )
            neg_add = ", extra drawers, missing handles, altered leg height, unintended two-tone drawer fronts"
            angles = {
                "vista_frontal": "Direct 0-degree flat front elevation centered dead-on, displaying exact drawer/door alignment, handles, and base legs.",
                "vista_perspectiva_3_4": "Commercial 3/4 perspective at 45 degrees showing front facade, side panel depth, top surface, and leg stance.",
                "vista_lateral": "Strict 90-degree orthogonal lateral side profile showing full depth from front drawer face to back panel.",
                "vista_lateral_izquierda": "Strict 90-degree orthogonal left lateral side profile showing side panel grain and leg alignment.",
                "vista_3_4_izquierda": "Commercial 3/4 perspective angled toward the left showing front-left corner joinery and drawer faces.",
                "vista_3_4_derecha": "Commercial 3/4 perspective angled toward the right showing front-right corner joinery and drawer faces.",
                "vista_3_4_posterior": "Clean 3/4 rear perspective showing neat back panel finishing and rear leg joinery.",
                "vista_picada_alta": "High-angle 65-degree semi-top view looking down at the top surface and front drawer facade simultaneously.",
                "vista_superior_cenital": "Strict 90-degree orthogonal overhead plan view (camera pitch -90°) pointing straight down at the flat top surface only; zero front drawer faces visible.",
            }
        else:
            parts_str = "all exposed wooden/structural surfaces, panels, frame, and joinery"
            mirror_optics = ""
            geometry_rule = f"Strictly preserve the exact 3D silhouette, joinery, and natural orientation ({geom_struct}) from the reference."
            neg_add = ", altered silhouette, invented hardware, mismatched finish"
            angles = {
                "vista_frontal": "Direct 0-degree flat front elevation centered dead-on.",
                "vista_perspectiva_3_4": "Commercial 3/4 perspective at 45 degrees showing front and side depth clearly.",
                "vista_lateral": "Strict 90-degree orthogonal lateral side profile from front edge to rear edge.",
                "vista_lateral_izquierda": "Strict 90-degree orthogonal left lateral side profile.",
                "vista_3_4_izquierda": "Commercial 3/4 perspective angled toward the left.",
                "vista_3_4_derecha": "Commercial 3/4 perspective angled toward the right.",
                "vista_3_4_posterior": "Clean 3/4 rear perspective showing back-side construction.",
                "vista_picada_alta": "High-angle 65-degree semi-top perspective looking down at the top and front.",
                "vista_superior_cenital": "Strict 90-degree orthogonal overhead plan view looking straight down at the top surface.",
            }

        return {
            "category": category,
            "sub_category": sub_category,
            "parts_str": parts_str,
            "mirror_optics": mirror_optics,
            "geometry_rule": geometry_rule,
            "dimensions_rule": dimensions_rule,
            "width_cm": width_cm,
            "depth_cm": depth_cm,
            "height_cm": height_cm,
            "diam_cm": diam_cm,
            "neg_add": neg_add,
            "angles": angles,
        }

    @staticmethod
    def _fmt_num(val: float) -> str:
        return str(int(val)) if float(val).is_integer() else f"{float(val):g}"

    def parse_dimensions(self, tipo_mueble: str, medidas_texto: str) -> Dict[str, Any]:
        p = self.detect_furniture_profile(tipo_mueble or "", medidas_texto or "", "")
        return {
            "category": p["category"],
            "sub_category": p["sub_category"],
            "width_cm": p.get("width_cm"),
            "depth_cm": p.get("depth_cm"),
            "height_cm": p.get("height_cm"),
            "diam_cm": p.get("diam_cm"),
        }

    def compose_dimensions_text(
        self, width: float = 0, depth: float = 0, height: float = 0, diam: float = 0
    ) -> str:
        parts: List[str] = []
        if diam:
            parts.append(f"{self._fmt_num(diam)} cm diam")
        if width:
            parts.append(f"{self._fmt_num(width)} cm frente")
        if depth:
            parts.append(f"{self._fmt_num(depth)} cm fondo")
        if height:
            parts.append(f"{self._fmt_num(height)} cm alto")
        return " x ".join(parts)

    def sanity_warnings(
        self, category: str, width: float, depth: float, height: float, diam: float
    ) -> List[str]:
        w: List[str] = []
        if not any([width, depth, height, diam]):
            w.append("No hay medidas confirmadas: el plano técnico y el entorno saldrán sin escala real.")
            return w
        if category == "mirror":
            if height and height < 20:
                w.append("Un espejo con alto menor a 20 cm es raro: confirma que el alto no sea el grosor.")
            if width and height and height < width * 0.4 and depth and depth > height:
                w.append("Las medidas parecen invertidas (alto y grosor). Revisa los campos.")
        elif category in ("table", "seating", "storage", "bed"):
            if height and height < 15:
                w.append("El alto es menor a 15 cm para un mueble de piso: revisa si es correcto.")
        if category == "general":
            w.append("Tipo de mueble genérico: especifica el tipo (ej. mesa de centro, espejo, silla, buró) para reglas óptimas.")
        return w

    # ------------------------------------------------------------------
    # MAPEO DINÁMICO DE RANURAS DE IMAGEN (ADIÓS ERROR DE "Image 2")
    # ------------------------------------------------------------------
    def _build_image_slots(
        self,
        furn_item: str,
        has_wood: bool,
        wood_label: str,
        has_fabric: bool,
        fabric_label: str,
        has_ref: bool,
        include_anchor: bool = False,
        classic_numbering: bool = False,
    ) -> Dict[str, Any]:
        """Calcula el índice exacto (Image 1, Image 2...) de cada archivo adjunto."""
        slots: List[str] = []
        guide: List[str] = []
        idx = 1

        slots.append(f"- Image {idx} (PRIMARY FURNITURE REFERENCE): Exact 3D silhouette, joinery, and proportions of '{furn_item}'.")
        guide.append(f"Image {idx}: Foto original del mueble")
        idx += 1

        wood_idx: Optional[int] = None
        if has_wood:
            wood_idx = 2 if classic_numbering else idx
            slots.append(f"- Image {wood_idx} (WOOD SAMPLE GROUND TRUTH): Exact wood species, continuous grain, and stain tone ({wood_label}).")
            guide.append(f"Image {wood_idx}: Muestra de madera ({wood_label})")
            if not classic_numbering:
                idx += 1

        fabric_idx: Optional[int] = None
        if has_fabric:
            fabric_idx = (3 if has_wood else 2) if classic_numbering else idx
            slots.append(f"- Image {fabric_idx} (FABRIC SWATCH GROUND TRUTH): Exact textile weave, fiber thickness, and color ({fabric_label}).")
            guide.append(f"Image {fabric_idx}: Muestra de tela ({fabric_label})")
            if not classic_numbering:
                idx += 1

        ref_idx: Optional[int] = None
        if has_ref and not classic_numbering:
            ref_idx = idx
            slots.append(f"- Image {ref_idx} (AUXILIARY ANGLE REFERENCE): Supplementary structural angle details.")
            guide.append(f"Image {ref_idx}: Referencia auxiliar de ángulo")
            idx += 1

        anchor_idx: Optional[int] = None
        if include_anchor:
            anchor_idx = idx
            slots.append(
                f"- Image {anchor_idx} (APPROVED VISTA 1 ANCHOR — WHEN ATTACHED): Use as visual lock for exact outline, color, and finish; change ONLY camera angle."
            )
            guide.append(f"Image {anchor_idx} (recomendada): Tu render aprobado de Vista 1")

        return {
            "header_block": "ATTACHED REFERENCE IMAGES:\n" + "\n".join(slots),
            "guide": guide,
            "wood_idx": wood_idx,
            "fabric_idx": fabric_idx,
            "ref_idx": ref_idx,
            "anchor_idx": anchor_idx,
        }

    @staticmethod
    def _fabric_negative_terms(fa: Optional[Dict[str, Any]] = None, fabric_label: str = "") -> str:
        """Términos negativos probados de V1 para evitar tela plana, gamuza o pérdida de tramado."""
        fa = fa or {}
        combined = f"{fabric_label} {fa.get('name', '')} {fa.get('texture_detail', '')}".lower()
        base = [
            "generic fabric",
            "solid color",
            "flat texture",
            "loss of weave pattern",
            "melted textures",
            "oversized macro weave",
            "leftover old fabric on casco",
            "color shift",
            "altered geometry",
            "perspective distortion",
        ]
        if not any(w in combined for w in ("suede", "gamuza")):
            base.append("suede")
        if not any(w in combined for w in ("velvet", "terciopelo", "pana")):
            base.append("velvet")
        if not any(w in combined for w in ("leather", "piel", "cuero", "nubuck")):
            base.append("leather")
        return ", ".join(base)

    def _build_material_lock_text(
        self,
        profile: Dict[str, Any],
        furn_item: str,
        existing_mats: str,
        wa: Dict[str, Any],
        fa: Dict[str, Any],
        wood_idx: Optional[int],
        fabric_idx: Optional[int],
        has_wood: bool,
        has_fabric: bool,
    ) -> Tuple[str, str]:
        """Devuelve (bloque_para_AI_Studio, bloque_para_DALLE)."""
        ais_parts: List[str] = []
        dal_parts: List[str] = []

        if has_wood:
            w_name = wa.get("name") or "Selected Wood Sample"
            w_color = wa.get("color_description") or "warm natural timber tone from the wood sample"
            w_tex = wa.get("texture_detail") or "fine continuous wood grain pores"
            w_light = wa.get("light_interaction") or "soft satin-matte timber sheen"
            src = f"Image {wood_idx}" if wood_idx else "the wood sample"
            ais_parts.append(
                f"- MONOLITHIC WOOD FINISH LOCK (from {src} — '{w_name}'): Apply this exact timber species, {w_color}, "
                f"{w_tex}, and {w_light} uniformly across all wooden parts ({profile['parts_str']}). "
                "Ensure natural anatomical grain flow (vertical on legs, horizontal on rails); zero unintended two-tone contrast or bleached patches."
            )
            dal_parts.append(
                f"Wooden components ({profile['parts_str']}) finished monolithically in {w_name} ({w_color}, {w_tex}, {w_light}) matching {src}."
            )
        else:
            ais_parts.append(
                f"- ORIGINAL WOOD / SURFACE PRESERVATION (from Image 1): Faithfully preserve the authentic surface materials, "
                f"dual-tones, stone/metal/wood contrast, and color saturation of '{furn_item}' ({existing_mats}) without artificial uniformization."
            )
            dal_parts.append(
                f"Faithfully preserve all authentic materials, finishes, and natural contrasts directly from Image 1 ({existing_mats})."
            )

        if has_fabric:
            f_name = fa.get("name") or "Selected Fabric Swatch"
            f_color = fa.get("color_description") or "exact hue, undertones, and flecks from the fabric swatch"
            f_tex = fa.get("texture_detail") or "dense realistic woven upholstery fibers and loops"
            f_light = fa.get("light_interaction") or "soft matte textile sheen"
            src = f"Image {fabric_idx}" if fabric_idx else "the fabric swatch"
            ais_parts.append(
                f"- FULL CASCO & CUSHIONS FABRIC TEXTURE LOCK (V1+V7 from {src} — '{f_name}'): "
                f"First, meticulously analyze the source fabric macro texture in {src} ({f_name}: {f_color}; {f_tex}; {f_light}). "
                f"Apply this EXACT weave pattern, multi-tone thread colors/flecks, and tactile textile structure uniformly across "
                f"100% of the upholstered body shell (EL CASCO COMPLETO: outer & inner backrest, armrests/descansabrazos, "
                f"upholstered lower base rail/faldón, side panels, headboard/rails if bed) AND all upholstered seat/back cushions. "
                f"Follow original seams, piping/welting, pleats, folds, and taut upholstery tension with 0% color/hue shift. "
                f"CRITICAL SCALING CONSTRAINT (~97% macro reduction): {src} is a close-up macro swatch — you MUST scale down this macro texture "
                f"dramatically (approx. 97% reduction) so the final result looks like realistic, finely woven fabric viewed from furniture distance, "
                f"explicitly retaining dense micro-thread details on both the casco and cushions without turning into a flat solid color, suede/velvet, "
                f"or an oversized pattern, and NEVER leaving any part of the casco in the old fabric. "
                f"Strictly protect all non-upholstered parts (exposed wooden legs, wooden plinths/frames, metal hardware, glass, stone)."
            )
            dal_parts.append(
                f"100% of the upholstered body shell (casco: backrest, armrests, upholstered base rail/sides) AND all cushions crafted uniformly in "
                f"{f_name} (weave: {f_tex}; colors/flecks: {f_color}; finish: {f_light}) matching {src} with approx. 97% macro-to-furniture scale reduction, "
                "explicitly retaining dense micro-thread weave without turning into flat solid color, preserving original seams, piping, folds, and non-upholstered wood/metal parts."
            )
        elif not has_wood:
            # Ya cubierto arriba por la preservación integral de Image 1
            pass
        else:
            ais_parts.append(
                "- NON-WOOD / UPHOLSTERY PRESERVATION (from Image 1): Keep any fabric, cushions, metal, stone, or glass strictly identical to Image 1."
            )
            dal_parts.append("All non-wooden surfaces (upholstery, cushions, metal, stone, glass) remain strictly identical to Image 1.")

        return "\n".join(ais_parts), " ".join(dal_parts)

    def _build_environment_room_context(
        self, profile: Dict[str, Any], furn_item: str, lugar_casa: str
    ) -> Tuple[str, str]:
        """Genera contexto de habitación realista adaptado al tipo de mueble y lugar elegido."""
        sub = profile.get("sub_category", "general")
        cat = profile.get("category", "general")
        custom_room = (lugar_casa or "").strip()
        if custom_room.lower().startswith("automático"):
            custom_room = ""

        if custom_room:
            room_intro = f"in a sophisticated luxury residential space: {custom_room}"
        elif cat == "mirror":
            room_intro = "mounted cleanly on a textured architectural plaster/limewash wall in a serene luxury entryway or dressing salon"
        elif cat == "bed":
            room_intro = "as the centerpiece of a calm, sunlit luxury master bedroom"
        elif sub == "dining_table":
            room_intro = "centered inside an airy, high-ceiling residential dining room"
        elif sub == "side_table" or sub == "nightstand":
            room_intro = "positioned naturally beside a neutral contemporary sofa armrest or upholstered bed edge in a lived-in client residence"
        elif sub == "coffee_table":
            room_intro = "centered on a woven wool area rug in front of a low-profile neutral sofa in a sunlit client living room"
        elif cat == "seating":
            room_intro = "styled as the hero seating piece in a warm, sunlit contemporary client living room"
        elif cat == "storage":
            room_intro = "positioned flush against a refined architectural wall in a contemporary client residence"
        else:
            room_intro = "placed naturally inside a bright, lived-in luxury client home interior"

        if cat == "mirror":
            companions = (
                "Below or beside the wall-mounted mirror, place a sleek minimalist console or bench with subtle ceramic decor, "
                "wide-plank flooring, and soft indirect daylight from sheer floor-to-ceiling linen drapes. "
                "The mirror glass reflects only soft neutral architectural depth without distracting clutter."
            )
        elif cat == "bed":
            companions = (
                "Dressed neatly with breathable neutral Belgian linen bedding, flanked by understated bedside tables, "
                "warm architectural sconces, a textured wool rug underneath, and sheer linen curtains diffusing morning sunlight."
            )
        elif sub == "dining_table":
            companions = (
                "Surrounded by complementary minimalist dining chairs tucked naturally around the table, "
                "anchored on warm wide-plank flooring or a low-pile woven rug, with a sculptural pendant lamp above and soft linen drapery."
            )
        elif sub == "coffee_table":
            companions = (
                "Paired with a soft neutral-toned contemporary sofa, an accent lounge chair in the background, "
                "an indoor olive tree in a matte ceramic planter, and subtle minimalist decor (one art book, one small ceramic vessel) that leaves >80% of the tabletop clearly visible."
            )
        elif sub in ("side_table", "nightstand"):
            companions = (
                "Resting naturally on a textured neutral rug right next to a soft neutral sofa or bed, "
                "with a warm table lamp or small ceramic object resting neatly on top, leaving the silhouette and joinery completely unobstructed."
            )
        elif cat == "seating":
            companions = (
                "Grounded on an organic woven wool rug, accompanied by a clean minimalist side table, soft neutral plaster walls, "
                "large-scale subtle textured wall art, and gentle indoor botanical greenery."
            )
        else:
            companions = (
                "Grounded on natural flooring and a textured neutral rug, accompanied by understated residential furniture, "
                "architectural wall paneling, and sheer linen window drapes."
            )

        return room_intro, companions

    # ------------------------------------------------------------------
    # CONSTRUCCIÓN DE VISTAS INDIVIDUALES Y CATÁLOGO
    # ------------------------------------------------------------------
    def _build_single_studio_view_prompt(
        self,
        view_id: str,
        furn_item: str,
        furniture_name: str,
        profile: Dict[str, Any],
        geom_struct: str,
        existing_mats: str,
        wa: Dict[str, Any],
        fa: Dict[str, Any],
        has_wood: bool,
        has_fabric: bool,
        has_ref: bool,
        wood_label: str,
        fabric_label: str,
        user_notes_clean: str,
        white_bg_enabled: bool,
        classic_numbering: bool,
        use_anchor: bool,
    ) -> Dict[str, Any]:
        meta = ALL_SINGLE_VIEWS[view_id]
        angle_desc = profile["angles"][view_id]
        slots = self._build_image_slots(
            furn_item=furn_item,
            has_wood=has_wood,
            wood_label=wood_label,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            has_ref=has_ref,
            include_anchor=use_anchor,
            classic_numbering=classic_numbering,
        )
        mat_ais, mat_dal = self._build_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            wood_idx=slots["wood_idx"],
            fabric_idx=slots["fabric_idx"],
            has_wood=has_wood,
            has_fabric=has_fabric,
        )

        anchor_ais = ""
        anchor_dal = ""
        if use_anchor and slots["anchor_idx"]:
            a_idx = slots["anchor_idx"]
            anchor_ais = (
                f"\n- ANCHOR CONSISTENCY (Image {a_idx} when attached): Image {a_idx} is the approved Vista 1 render. "
                f"Match its exact silhouette, proportions, color saturation, and finish 100%, rotating ONLY the camera to {meta['short']}. "
                "Do NOT repeat the camera angle of Image 1 or the anchor."
            )
            anchor_dal = (
                f" Use Image {a_idx} (if attached) as exact identity lock for silhouette, color, and grain, changing only the camera perspective."
            )

        bg_ais = (
            "Pure seamless solid digital white background (#FFFFFF), 0% ground shadows, 0% drop shadows, "
            "0% floor reflections, clean isolated e-commerce cutout."
            if white_bg_enabled
            else "Clean soft neutral studio backdrop with natural subtle contact grounding and balanced studio lighting."
        )
        bg_dal = (
            "pure seamless solid white background (#FFFFFF) with zero ground shadows, zero drop shadows, and zero reflections"
            if white_bg_enabled
            else "clean soft neutral commercial studio backdrop with subtle natural contact shadow"
        )

        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" Mandatory user directives: {user_notes_clean}." if user_notes_clean else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""

        fab_neg = f", {self._fabric_negative_terms(fa, fabric_label)}" if has_fabric else ""

        prompt_ais = (
            f"[COMMERCIAL PRODUCT PHOTOGRAPHY · {meta['label'].upper()}]\n"
            f"TASK: Generate ONE standalone high-resolution commercial catalog photograph of '{furn_item}' ('{furniture_name}') "
            f"from the exact requested camera perspective.\n\n"
            f"{slots['header_block']}\n\n"
            f"CAMERA & FRAMING:\n"
            f"- PERSPECTIVE: {angle_desc}\n"
            f"- FRAMING: Single centered furniture object occupying ~72% of the canvas with balanced ~14% margins on all sides. Zero cropping, no collage.\n\n"
            f"MATERIAL & GEOMETRY LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY RULE: {profile['geometry_rule']}{dim_ais}{mirror_ais}{anchor_ais}{notes_ais}\n\n"
            f"STUDIO & OPTICS:\n"
            f"- BACKGROUND: {bg_ais}\n"
            f"- PHOTOGRAPHY: Shot on 100MP medium-format camera, 80mm prime lens at f/11, balanced 5400K softbox studio lighting, edge-to-edge tack-sharp micro-texture.\n\n"
            f"Exclude: collage, split screen, multiple objects, text, labels, watermark, CGI plastic sheen"
            f"{', ground shadows, drop shadows, floor reflections, grey backdrop' if white_bg_enabled else ''}{fab_neg}{profile['neg_add']}."
        )

        prompt_dal = (
            f"Standalone 8K commercial catalog photograph of a single {furn_item} ('{furniture_name}').\n"
            f"Camera Perspective: {angle_desc} Centered with generous clean margins, single object only (no collage or split frame).\n"
            f"Materials: {mat_dal}\n"
            f"Structure & Proportions: {profile['geometry_rule']} {profile['dimensions_rule']}{anchor_dal}{notes_dal}\n"
            f"Studio & Lighting: Set against a {bg_dal}. Balanced 5400K commercial studio lighting, 80mm f/11 medium-format clarity.\n"
            f"Avoid: collage, text, watermarks, CGI plastic look{', shadows, reflections, room interior' if white_bg_enabled else ''}{fab_neg}{profile['neg_add']}."
        )

        prompt_mj = (
            f"Commercial luxury product photography of {furn_item}, {angle_desc}, {geom_struct}, "
            f"{'isolated on pure solid white background #FFFFFF, zero ground shadows, ' if white_bg_enabled else 'clean neutral studio, '}"
            f"80mm lens f/11 5400K studio lighting --ar 1:1 --v 6.1 --style raw "
            f"--no collage, text, watermark, CGI{', shadow, reflection, room' if white_bg_enabled else ''}"
        )

        return {
            "id": view_id,
            "label": meta["label"],
            "short_name": meta["short"],
            "icon": meta["icon"],
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "checklist": CHECKLISTS.get(view_id, _COMMON_CHECKS),
            "needs_anchor": use_anchor,
            "attachment_guide": slots["guide"],
        }

    def _build_blueprint_item(
        self,
        furn_item: str,
        furniture_name: str,
        profile: Dict[str, Any],
        medidas_usuario: str,
        user_notes_clean: str,
    ) -> Dict[str, Any]:
        w_val = profile.get("width_cm")
        d_val = profile.get("depth_cm")
        h_val = profile.get("height_cm")
        diam_val = profile.get("diam_cm")
        is_mirror = profile.get("category") == "mirror"

        dim_lines: List[str] = []
        if diam_val:
            dim_lines.append(f"Diámetro Ø: {self._fmt_num(diam_val)} cm (along the top/front width)")
        if h_val:
            dim_lines.append(f"Alto: {self._fmt_num(h_val)} cm (vertical arrow on the LEFT side)")
        if w_val:
            dim_lines.append(f"Ancho: {self._fmt_num(w_val)} cm (horizontal arrow along the BOTTOM front)")
        if d_val:
            label_d = "Grosor" if is_mirror else "Fondo"
            dim_lines.append(f"{label_d}: {self._fmt_num(d_val)} cm (angled arrow along the LOWER-LEFT depth edge)")
        if not dim_lines and medidas_usuario:
            dim_lines.append(f"Exact measurements: {medidas_usuario.strip()}")
        elif not dim_lines:
            dim_lines = [
                "Alto: [Match Image 1 proportion]",
                "Ancho: [Match Image 1 proportion]",
                "Fondo: [Match Image 1 proportion]",
            ]

        dim_block = "\n".join(f"  * {line}" for line in dim_lines)
        dim_summary = ", ".join(line.split(" (")[0] for line in dim_lines)
        notes_line = f"\n- Additional geometry note: {user_notes_clean}" if user_notes_clean else ""

        prompt_ais = (
            "[TECHNICAL ISOMETRIC CAD LINE-ART BLUEPRINT WITH DIMENSIONS]\n"
            f"TASK: Generate a pure, crisp minimalist black-and-white isometric technical CAD line drawing with dimension arrows "
            f"of the EXACT '{furn_item}' ('{furniture_name}') from Image 1.\n\n"
            "ATTACHED REFERENCE:\n"
            "- Image 1: Furniture photo whose exact 3D silhouette, proportions, and details must be drawn as clean technical line art.\n\n"
            "LINE-ART & CANVAS RULES:\n"
            "- STYLE: Pure minimalist 2D isometric architectural CAD line art. Crisp uniform black ink lines (#000000) ONLY.\n"
            "- CANVAS: Square 1:1 composition on pure solid white background (#FFFFFF). Center the furniture with ~25% clean white margin on every side.\n"
            "- VIEWPOINT: Clean isometric 3/4 view elevated ~25° so width, depth, and height edges are all clearly measurable.\n"
            "- STRICTLY NO FILL: 0% color, 0% wood/fabric textures, 0% shading, 0% gradients, 0% floor shadows.\n\n"
            "DIMENSION ARROWS & LABELS (ONLY THESE EXACT MEASUREMENTS):\n"
            f"{dim_block}\n"
            "- ARROWS: Double-headed crisp black extension/dimension arrows (#000000), parallel to each measured edge, spaced cleanly outside the silhouette.\n"
            "- NUMBERS: Clean horizontal sans-serif numerals in pure black (#000000), positioned cleanly beside/centered on each arrow (never overlapping lines). "
            "Do NOT invent extra dimensions, title blocks, legends, or extra text.{notes_line}\n\n"
            "Exclude: color, photorealism, 3D shading, gradients, wood texture, fabric texture, shadows, grid lines, extra numbers, watermark."
        ).replace("{notes_line}", notes_line)

        prompt_dal = (
            f"Minimalist black-and-white technical isometric CAD blueprint line drawing of the {furn_item} ('{furniture_name}') from Image 1.\n"
            "Pure solid white background (#FFFFFF), uniform crisp black (#000000) technical outlines only — zero color, zero shading, zero textures, zero shadows.\n"
            "Centered in a square frame with ~25% white margin on all sides.\n"
            f"Include clean double-headed black dimension arrows parallel to the edges showing ONLY: {dim_summary}.\n"
            "Horizontal legible black sans-serif numerals cleanly separated from the object lines. No title block or extra text."
        )

        prompt_mj = (
            f"Minimalist black and white technical isometric CAD line drawing blueprint of {furn_item}, "
            "thin uniform black lines on pure solid white background #FFFFFF, architectural dimension arrows, "
            "zero shading, zero color --ar 1:1 --v 6.1 --style raw --no color, shading, 3d render, photo, texture, shadows"
        )

        return {
            "id": "vista_plano_tecnico",
            "label": ALL_SINGLE_VIEWS["vista_plano_tecnico"]["label"],
            "short_name": ALL_SINGLE_VIEWS["vista_plano_tecnico"]["short"],
            "icon": ALL_SINGLE_VIEWS["vista_plano_tecnico"]["icon"],
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "checklist": CHECKLISTS["vista_plano_tecnico"],
            "needs_anchor": False,
            "attachment_guide": ["Image 1: Foto original del mueble"],
        }

    def _build_environment_item(
        self,
        furn_item: str,
        furniture_name: str,
        profile: Dict[str, Any],
        geom_struct: str,
        existing_mats: str,
        wa: Dict[str, Any],
        fa: Dict[str, Any],
        has_wood: bool,
        has_fabric: bool,
        has_ref: bool,
        wood_label: str,
        fabric_label: str,
        lugar_casa: str,
        user_notes_clean: str,
        classic_numbering: bool,
        use_anchor: bool,
    ) -> Dict[str, Any]:
        slots = self._build_image_slots(
            furn_item=furn_item,
            has_wood=has_wood,
            wood_label=wood_label,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            has_ref=has_ref,
            include_anchor=use_anchor,
            classic_numbering=classic_numbering,
        )
        mat_ais, mat_dal = self._build_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            wood_idx=slots["wood_idx"],
            fabric_idx=slots["fabric_idx"],
            has_wood=has_wood,
            has_fabric=has_fabric,
        )
        room_intro, companions = self._build_environment_room_context(profile, furn_item, lugar_casa)
        dim_summary = profile["dimensions_rule"] or "Preserve true-to-life furniture scale relative to surrounding architecture and rugs."

        anchor_ais = ""
        if use_anchor and slots["anchor_idx"]:
            a_idx = slots["anchor_idx"]
            anchor_ais = (
                f"\n- ANCHOR CONSISTENCY (Image {a_idx} when attached): Keep the furniture's exact silhouette, color, "
                f"and finish locked to Image {a_idx}."
            )

        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" User directives: {user_notes_clean}." if user_notes_clean else ""

        prompt_ais = (
            "[ARCHITECTURAL INTERIOR PHOTOGRAPHY · CLIENT HOME ENVIRONMENT (WIDE DISTANT SHOT)]\n"
            f"TASK: Photograph '{furn_item}' ('{furniture_name}') placed authentically {room_intro}, "
            "captured as a wide, distant architectural interior photograph.\n\n"
            f"{slots['header_block']}\n\n"
            "ENVIRONMENT & COMPOSITION:\n"
            "- DISTANT WIDE SHOT (VISTA DE LEJOS): Shot with a 35mm wide architectural lens from across the room so the full surrounding interior space is visible, not a tight close-up.\n"
            f"- REAL-WORLD 1:1 SCALE: {dim_summary}\n"
            "- DELIBERATE CONTRASTING ROOM PALETTE: Choose wall paint, flooring, and rug tones that clearly CONTRAST with the furniture's color and finish so the product stands out sharply without blending into the wall or floor.\n"
            f"- AUTHENTIC CLIENT HOME STYLING: {companions}\n\n"
            "FURNITURE IDENTITY LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY RULE: {profile['geometry_rule']}{anchor_ais}{notes_ais}\n\n"
            "LIGHTING & REALISM:\n"
            "- Soft natural morning daylight streaming through sheer floor-to-ceiling linen curtains, creating soft realistic contact shadows grounding the piece naturally on the floor/rug.\n"
            "- Shot on medium format 35mm lens at f/8, photorealistic residential architectural digest photography.\n\n"
            "Exclude: CGI, 3D render, cartoon, distorted giant or miniature scale, matching wall colors that camouflage the furniture, heavy clutter, blur, text, watermark."
        )

        prompt_dal = (
            f"Wide-angle distant architectural interior photograph of a luxury client residence ({room_intro}), featuring the exact {furn_item} ('{furniture_name}') from Image 1.\n"
            f"Scale & Placement: {dim_summary} {companions}\n"
            f"Contrast Mandate: Surrounding walls, rug, and floor use complementary neutral tones that deliberately contrast with the furniture so it stands out prominently.\n"
            f"Materials & Structure: {mat_dal} {profile['geometry_rule']}{notes_dal}\n"
            "Lighting: Soft natural daylight through sheer linen drapes, gentle natural contact shadows grounding the piece, 35mm architectural lens, photorealistic editorial quality.\n"
            "Avoid: tight close-up, distorted scale, camouflaged colors, CGI look, text, watermark."
        )

        prompt_mj = (
            f"Wide-angle distant architectural interior photograph, {furn_item} {room_intro}, "
            "contrasting neutral walls and woven wool rug, natural morning daylight through sheer linen curtains, "
            "35mm architectural lens f/8, photorealistic editorial interior --ar 16:9 --v 6.1 --style raw "
            "--no close-up, CGI, distorted scale, text, watermark"
        )

        return {
            "id": "vista_entorno_cliente",
            "label": ALL_SINGLE_VIEWS["vista_entorno_cliente"]["label"],
            "short_name": ALL_SINGLE_VIEWS["vista_entorno_cliente"]["short"],
            "icon": ALL_SINGLE_VIEWS["vista_entorno_cliente"]["icon"],
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "checklist": CHECKLISTS["vista_entorno_cliente"],
            "needs_anchor": use_anchor,
            "attachment_guide": slots["guide"],
        }

    # ------------------------------------------------------------------
    # MODOS EXTRA: MATERIAL, EXTRAER, HD, LOTE VISTAS+TELA, LOTE CLONAR
    # ------------------------------------------------------------------
    def _build_material_swap_item(
        self,
        material_mode: str,
        furn_item: str,
        furniture_name: str,
        profile: Dict[str, Any],
        geom_struct: str,
        existing_mats: str,
        wa: Dict[str, Any],
        fa: Dict[str, Any],
        wood_label: str,
        fabric_label: str,
        user_notes_clean: str,
        white_bg_enabled: bool,
        classic_numbering: bool,
        camera_angle: str = "",
    ) -> Dict[str, Any]:
        _ = classic_numbering
        has_wood = material_mode in ("wood_only", "dual")
        has_fabric = material_mode in ("fabric_only", "dual")

        # Orden probado de V1: primero las muestras macro (Tela / Madera) y al final el mueble objetivo
        slot_lines: List[str] = []
        guide: List[str] = []
        idx = 1
        fabric_idx: Optional[int] = None
        wood_idx: Optional[int] = None

        if has_fabric:
            fabric_idx = idx
            slot_lines.append(
                f"- Image {fabric_idx} (FABRIC SWATCH GROUND TRUTH): Source fabric macro texture, exact weave pattern, multi-tone flecks, and color ({fabric_label})."
            )
            guide.append(f"Image {fabric_idx}: Muestra de tela ({fabric_label})")
            idx += 1
        if has_wood:
            wood_idx = idx
            slot_lines.append(
                f"- Image {wood_idx} (WOOD SAMPLE GROUND TRUTH): Exact wood species, continuous grain flow, and stain tone ({wood_label})."
            )
            guide.append(f"Image {wood_idx}: Muestra de madera ({wood_label})")
            idx += 1

        furn_idx = idx
        slot_lines.append(
            f"- Image {furn_idx} (TARGET FURNITURE PIECE): Original '{furn_item}' ('{furniture_name}') — preserve exact silhouette, seams, folds, and camera angle."
        )
        guide.append(f"Image {furn_idx}: Foto original del mueble")
        header_block = "ATTACHED IMAGES:\n" + "\n".join(slot_lines)

        f_name = fa.get("name") or fabric_label or "Selected Fabric Swatch"
        f_color = fa.get("color_description") or "true-to-life chromatic profile, undertones, and flecks from sample"
        f_texture = fa.get("texture_detail") or "dense textured loops and realistic yarn weave"
        f_light = fa.get("light_interaction") or "soft matte textile sheen"

        w_name = wa.get("name") or wood_label or "Selected Wood Sample"
        w_color = wa.get("color_description") or "natural timber tone from sample"
        w_texture = wa.get("texture_detail") or "natural anatomical wood grain flow"
        w_light = wa.get("light_interaction") or "soft satin-matte timber sheen"

        cam_lock = (camera_angle or "").strip() or "the exact same camera angle and framing as the original photo"
        dim_line = f" SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        mirror_line = f" {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        notes_ais = f"\n\nUSER SPECIAL DIRECTIVES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" Mandatory user directives: {user_notes_clean}." if user_notes_clean else ""

        if white_bg_enabled:
            scene_str = (
                f"Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, seams, piping, folds, and proportions of the furniture in Image {furn_idx}. "
                f"{profile['geometry_rule']}{dim_line}{mirror_line} "
                f"CAMERA CONSTRAINT: You MUST lock the camera to {cam_lock}. "
                f"ENVIRONMENT CONSTRAINT: Extract ONLY the furniture onto a pure seamless solid white background (#FFFFFF, RGB 255,255,255) centered with balanced margins; "
                "completely eliminate ALL shadows (0% ground shadow, 0% contact shadow under legs, 0% drop shadow, 0% floor reflections), and remove harsh studio lighting glare/reflections from wood and fabric. "
                "CRITICAL: DO NOT include any text, numbers, color names, or color palettes in the image."
            )
            bg_neg = "shadows, drop shadows, contact shadows, floor reflections, dark background, black background, grey background, original background, room environment,"
            bg_dal = "pure seamless solid white background (#FFFFFF) with 0% ground/contact/drop shadows and 0% reflections"
        else:
            scene_str = (
                f"Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, seams, piping, folds, lighting, shadows, and surrounding background of Image {furn_idx}. "
                f"{profile['geometry_rule']}{dim_line}{mirror_line} "
                f"CAMERA CONSTRAINT: You MUST lock the camera to {cam_lock}. Do not alter the room or the furniture's physical design."
            )
            bg_neg = "changed background, altered environment, changed camera angle, top-down view,"
            bg_dal = "keep the original scene lighting, shadows, and background intact"

        fab_neg = self._fabric_negative_terms(fa, fabric_label)

        if material_mode == "dual":
            prompt_ais = (
                f"INSTRUCTION: First, meticulously analyze the source fabric macro texture in Image {fabric_idx} ({f_name}: {f_color}; {f_texture}; {f_light}), "
                f"the source wood macro texture in Image {wood_idx} ({w_name}: {w_color}; {w_texture}; {w_light}), "
                f"and the target furniture piece in Image {furn_idx} ('{furn_item}').\n\n"
                f"{header_block}\n\n"
                f"GENERATE: Accurately replace BOTH 100% of the fabric upholstery AND all wooden components of the furniture in Image {furn_idx} "
                f"using the exact textures analyzed from Image {fabric_idx} and Image {wood_idx}.\n\n"
                f"GEOMETRY & SCENE CONSTRAINT: {scene_str}\n\n"
                f"FABRIC & CASCO CONSTRAINT (FULL CASCO + CUSHIONS · 97% MACRO REDUCTION): "
                f"Apply the precise weave pattern ({f_texture}), multi-tone thread colors/flecks ({f_color}), and surface response ({f_light}) from Image {fabric_idx} "
                f"uniformly across 100% of the upholstered body shell (EL CASCO COMPLETO: outer & inner backrest, armrests/descansabrazos, upholstered base rail/faldón, side panels) "
                f"AND all seat/back cushions with 0% hue shift. "
                f"CRITICAL: You must scale down this macro texture dramatically (approx. 97% reduction) so it looks like realistic, finely woven fabric viewed from furniture distance, "
                f"explicitly retaining dense micro-thread details on both the casco and cushions without turning into a flat solid color, leaving the casco in the old fabric, or creating an oversized pattern.\n\n"
                f"WOOD CONSTRAINT: Apply the precise wood grain flow, pores, finish ({w_light}), and color ({w_color}) from Image {wood_idx} monolithically to all legs, frames, and wooden bases. "
                f"Ensure the grain follows the natural anatomical direction (vertical on legs, horizontal on rails) with zero unintended two-tone contrast.{notes_ais}\n\n"
                f"Negative Prompt:\n"
                f"{fab_neg}, flat wood colors, bleached patches, text, watermark, poster, collage, infographic, multiple furniture pieces, {bg_neg}{profile['neg_add']}"
            )
            mat_dal = (
                f"100% of the upholstered body shell (casco: backrest, armrests, upholstered base rail/sides) AND all cushions reupholstered in "
                f"{f_name} ({f_color}; {f_texture}; {f_light}) from Image {fabric_idx} with approx. 97% macro weave scale reduction (preserving micro-threads, never flat color); "
                f"all wooden parts finished monolithically in {w_name} ({w_color}; {w_texture}; {w_light}) from Image {wood_idx}."
            )
        elif material_mode == "fabric_only":
            prompt_ais = (
                f"INSTRUCTION: First, meticulously analyze the source fabric macro texture in Image {fabric_idx} ({f_name}: {f_color}; {f_texture}; {f_light}) "
                f"and the target furniture piece in Image {furn_idx} ('{furn_item}').\n\n"
                f"{header_block}\n\n"
                f"GENERATE: Accurately replace ONLY the upholstery fabric of the furniture piece in Image {furn_idx} using the exact texture analyzed from Image {fabric_idx}.\n\n"
                f"GEOMETRY & SCENE CONSTRAINT: {scene_str}\n\n"
                f"MATERIAL & SCALING CONSTRAINT (FULL CASCO + CUSHIONS · 97% MACRO REDUCTION): "
                f"Apply the precise weave pattern ({f_texture}), multi-tone thread colors/flecks ({f_color}), and textile light response ({f_light}) from Image {fabric_idx} "
                f"uniformly across 100% of the upholstered body shell (EL CASCO COMPLETO: outer & inner backrest, armrests/descansabrazos, upholstered lower base rail/faldón, side panels, headboard/rails) "
                f"AND all upholstered seat/back cushions, following original seams, piping, and folds with 0% color/hue shift. "
                f"CRITICAL: You must scale down this macro texture dramatically (approx. 97% reduction). The final result must look like realistic, finely woven fabric viewed from a distance, "
                f"explicitly retaining the dense micro-thread details on both the casco and cushions without turning into a flat, solid color, leaving the casco in the old fabric, or creating an oversized pattern. "
                f"Strictly protect all non-upholstered parts (exposed wooden legs, wooden plinths/frames, metal hardware, glass, stone) identical to Image {furn_idx}.{notes_ais}\n\n"
                f"Negative Prompt:\n"
                f"{fab_neg}, altered wood legs, changed wood color, text, watermark, poster, collage, infographic, multiple furniture pieces, {bg_neg}{profile['neg_add']}"
            )
            mat_dal = (
                f"100% of the upholstered body shell (casco: backrest, armrests, upholstered base rail/sides) AND all cushions reupholstered in "
                f"{f_name} ({f_color}; {f_texture}; {f_light}) from Image {fabric_idx} with approx. 97% macro weave scale reduction (preserving micro-threads, never flat solid color); "
                f"all exposed wooden legs, frames, and metal parts preserved strictly identical to Image {furn_idx}."
            )
        else:  # wood_only
            prompt_ais = (
                f"INSTRUCTION: First, meticulously analyze the source wood macro texture in Image {wood_idx} ({w_name}: {w_color}; {w_texture}; {w_light}) "
                f"and the target furniture piece in Image {furn_idx} ('{furn_item}').\n\n"
                f"{header_block}\n\n"
                f"GENERATE: Accurately replace ONLY the wooden components ({profile['parts_str']}) of the furniture in Image {furn_idx} "
                f"using the exact wood grain, finish, and tone analyzed from Image {wood_idx}.\n\n"
                f"GEOMETRY & SCENE CONSTRAINT: {scene_str}\n\n"
                f"MATERIAL CONSTRAINT: Apply the precise wood grain flow, pores, finish ({w_light}), and color ({w_color}) from Image {wood_idx} monolithically. "
                f"Ensure the grain follows the natural anatomical direction of the furniture parts (vertical on legs, horizontal on rails) with zero two-tone contrast or bleached patches. "
                f"Keep any upholstery, cushions, metal, stone, or glass strictly identical to Image {furn_idx}.{notes_ais}\n\n"
                f"Negative Prompt:\n"
                f"altered fabric, changed upholstery, color shift, flat colors, two-tone wood mismatch, changed geometry, text, watermark, {bg_neg}{profile['neg_add']}"
            )
            mat_dal = (
                f"Wooden components ({profile['parts_str']}) finished monolithically in {w_name} ({w_color}; {w_texture}; {w_light}) matching Image {wood_idx}; "
                f"all non-wooden surfaces preserved identical to Image {furn_idx}."
            )

        prompt_dal = (
            f"Precision material-swap product photograph of the exact {furn_item} ('{furniture_name}') in Image {furn_idx} (do NOT redesign geometry or camera angle: {cam_lock}).\n"
            f"Materials: {mat_dal}\n"
            f"Structure & Folds: Preserve exact contours, seams, piping, and folds. {profile['geometry_rule']} {profile['dimensions_rule']}{notes_dal}\n"
            f"Background: {bg_dal}.\n"
            f"Avoid: {fab_neg if has_fabric else 'flat colors, altered upholstery'}, altered geometry, perspective distortion, text, watermark{profile['neg_add']}."
        )

        prompt_mj = (
            f"Commercial catalog photography of {furn_item}, {geom_struct}, {mat_dal}, "
            f"{'pure solid white background #FFFFFF, zero shadows, ' if white_bg_enabled else ''}"
            "--ar 1:1 --v 6.1 --style raw --no generic fabric, flat texture, suede, velvet, altered geometry, text, watermark"
        )

        return {
            "id": "material",
            "label": "🎨 Cambio de Material",
            "short_name": "Material",
            "icon": "🎨",
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "checklist": CHECKLISTS["material"],
            "needs_anchor": False,
            "attachment_guide": guide,
        }

    def _build_extraction_item(
        self,
        furn_item: str,
        furniture_name: str,
        profile: Dict[str, Any],
        geom_struct: str,
        existing_mats: str,
        wa: Dict[str, Any],
        fa: Dict[str, Any],
        has_wood: bool,
        has_fabric: bool,
        wood_label: str,
        fabric_label: str,
        user_notes_clean: str,
        classic_numbering: bool,
    ) -> Dict[str, Any]:
        slots = self._build_image_slots(
            furn_item=furn_item,
            has_wood=has_wood,
            wood_label=wood_label,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            has_ref=False,
            include_anchor=False,
            classic_numbering=classic_numbering,
        )
        mat_ais, mat_dal = self._build_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            wood_idx=slots["wood_idx"],
            fabric_idx=slots["fabric_idx"],
            has_wood=has_wood,
            has_fabric=has_fabric,
        )
        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""

        prompt_ais = (
            "[ISOLATED COMMERCIAL PRODUCT CUTOUT · PURE WHITE #FFFFFF]\n"
            f"TASK: Cleanly extract and isolate '{furn_item}' ('{furniture_name}') from Image 1 onto a pure solid white background (#FFFFFF).\n\n"
            f"{slots['header_block']}\n\n"
            "ISOLATION & FRAMING:\n"
            "- POSITION: Place the furniture dead-center occupying ~72% of the canvas with balanced margins on all sides.\n"
            "- BACKGROUND: Pure seamless solid digital white (#FFFFFF). 0% ground shadows, 0% drop shadows, 0% floor contact shadows, 0% reflections.\n"
            "- NO PROPS: Remove all walls, floors, rugs, decor, and background clutter completely.\n\n"
            "PRESERVATION LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY LOCK: {profile['geometry_rule']}{dim_ais}{mirror_ais}{notes_ais}\n"
            "- OPTICS: 100MP medium-format 80mm f/11 crisp edges and authentic micro-texture.\n\n"
            f"Exclude: ground shadows, floor shadows, drop shadows, reflections, grey floor, room, props, altered color, text, watermark{profile['neg_add']}."
        )

        prompt_dal = (
            f"Clean commercial e-commerce cutout of the exact {furn_item} ('{furniture_name}') from Image 1, "
            "centered on a pure seamless solid white background (#FFFFFF) with 0% ground shadows, 0% drop shadows, and 0% reflections.\n"
            f"Materials: {mat_dal}\n"
            f"Geometry: {profile['geometry_rule']} {profile['dimensions_rule']}\n"
            f"{'User directives: ' + user_notes_clean if user_notes_clean else ''}\n"
            "Avoid: shadows, grey backdrop, room, altered geometry, text, watermark."
        )

        prompt_mj = (
            f"Isolated commercial product cutout of {furn_item}, centered on pure seamless solid white background #FFFFFF, "
            f"zero shadows, {geom_struct}, {existing_mats}, 80mm f/11 --ar 1:1 --v 6.1 --style raw --no shadow, floor, wall, room, text"
        )

        return {
            "id": "extraer",
            "label": "⬜ Extraer Mueble (Fondo Blanco #FFFFFF)",
            "short_name": "Extraer",
            "icon": "⬜",
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "checklist": CHECKLISTS["extraer"],
            "needs_anchor": False,
            "attachment_guide": slots["guide"],
        }

    def _build_hd_item(
        self,
        furn_item: str,
        furniture_name: str,
        profile: Dict[str, Any],
        geom_struct: str,
        existing_mats: str,
        wa: Dict[str, Any],
        fa: Dict[str, Any],
        has_wood: bool,
        has_fabric: bool,
        wood_label: str,
        fabric_label: str,
        user_notes_clean: str,
        white_bg_enabled: bool,
        classic_numbering: bool,
    ) -> Dict[str, Any]:
        slots = self._build_image_slots(
            furn_item=furn_item,
            has_wood=has_wood,
            wood_label=wood_label,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            has_ref=False,
            include_anchor=False,
            classic_numbering=classic_numbering,
        )
        mat_ais, mat_dal = self._build_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            wood_idx=slots["wood_idx"],
            fabric_idx=slots["fabric_idx"],
            has_wood=has_wood,
            has_fabric=has_fabric,
        )
        bg_line = (
            "Pure seamless solid white catalog studio background (#FFFFFF) with zero drop shadows."
            if white_bg_enabled
            else "Preserve the exact original background, scene lighting, and framing from Image 1 while upgrading sharpness to 8K."
        )
        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""

        prompt_ais = (
            "[8K ULTRA-HD COMMERCIAL RESTORATION · ZERO COLOR OR GEOMETRY DRIFT]\n"
            f"TASK: Remaster '{furn_item}' ('{furniture_name}') from Image 1 into ultra-sharp 8K medium-format clarity "
            "without altering color, tone, material identity, or silhouette.\n\n"
            f"{slots['header_block']}\n\n"
            "CLARITY & RESTORATION:\n"
            "- ELIMINATE ARTIFACTS: Remove pixelation, blur, compression noise, and softness completely.\n"
            "- MACRO TEXTURE: Restore crisp wood grain pores, joinery seams, and individual textile threads naturally without plastic smoothing.\n"
            "- FOCUS STACKING: Deep f/11 edge-to-edge sharpness from foreground edge to rear contours.\n\n"
            "STRICT PRESERVATION LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY LOCK: {profile['geometry_rule']}{dim_ais}{mirror_ais}{notes_ais}\n"
            f"- BACKGROUND: {bg_line}\n\n"
            f"Exclude: blurry, pixelated, jpeg artifacts, plastic smoothing, color shift, hue change, redesigned silhouette, CGI look, text, watermark{profile['neg_add']}."
        )

        prompt_dal = (
            f"8K Ultra-HD photographic remaster of the exact {furn_item} ('{furniture_name}') from Image 1.\n"
            "Remove all blur, pixelation, and compression artifacts while preserving 100% identical color, warmth, wood grain, fabric weave, and geometry.\n"
            f"Materials: {mat_dal}\n"
            f"Geometry: {profile['geometry_rule']} {profile['dimensions_rule']}\n"
            f"Environment: {bg_line}\n"
            f"{'User directives: ' + user_notes_clean if user_notes_clean else ''}\n"
            "Avoid: blur, compression noise, color shift, plastic skin/wood, redesigned shape, text, watermark."
        )

        prompt_mj = (
            f"8k ultra-sharp commercial catalog remaster of {furn_item}, {geom_struct}, {existing_mats}, "
            f"{'pure solid white background #FFFFFF, ' if white_bg_enabled else ''}"
            "focus stacking f/11 100MP medium format --ar 1:1 --v 6.1 --style raw --no blur, pixelated, noise, altered color"
        )

        return {
            "id": "hd",
            "label": "✨ Mejora HD 8K",
            "short_name": "Mejora HD",
            "icon": "✨",
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "checklist": CHECKLISTS["hd"],
            "needs_anchor": False,
            "attachment_guide": slots["guide"],
        }

    # ------------------------------------------------------------------
    # LOTE MULTI-VISTA (DE V4 MEJORADO): APLICAR TELA / CLONAR COLOR
    # ------------------------------------------------------------------
    def _generate_batch_view_prompt(
        self,
        batch_mode: str,
        ref_bytes: bytes,
        view_bytes: bytes,
        view_name: str,
        furn_item: str,
        medidas_texto: str,
        user_notes_clean: str,
        white_bg_enabled: bool,
        ref_label: str = "",
        fabric_analysis: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, str]:
        fa = fabric_analysis or {}
        bg_clause = (
            "pure seamless solid white background (#FFFFFF) with 0% ground shadows, 0% drop shadows, and 0% floor reflections"
            if white_bg_enabled
            else "the exact original background and natural lighting of Image 2"
        )
        notes_part = f"\n- MANDATORY NOTES: {user_notes_clean}" if user_notes_clean else ""
        dims_part = f"\n- REAL-WORLD SCALE: {medidas_texto}" if medidas_texto else ""

        if batch_mode == "vistas_tela":
            f_name = fa.get("name") or ref_label or "Fabric Swatch"
            f_color = fa.get("color_description") or "exact hue, undertones, and multi-tone flecks from Image 1"
            f_tex = fa.get("texture_detail") or "dense realistic woven upholstery fibers and loops"
            f_light = fa.get("light_interaction") or "soft matte textile sheen"
            fab_neg = self._fabric_negative_terms(fa, ref_label)

            local_ais = (
                f"INSTRUCTION: First, meticulously analyze the source fabric macro texture in Image 1 ({f_name}: {f_color}; {f_tex}; {f_light}) "
                f"and the target furniture view '{view_name}' in Image 2 ('{furn_item}').\n\n"
                "ATTACHED IMAGES:\n"
                f"- Image 1 (FABRIC SWATCH GROUND TRUTH): Exact color, flecks, thread thickness, and textile weave ({f_name}).\n"
                "- Image 2 (TARGET VIEW): Keep the EXACT camera angle, 3D silhouette, proportions, seams, piping, folds, and wooden/metal parts.\n\n"
                f"GENERATE: Accurately replace ONLY the upholstery fabric of the furniture piece in Image 2 using the exact texture analyzed from Image 1.\n\n"
                "GEOMETRY & SCENE CONSTRAINT: Strictly preserve the exact camera angle, shape, contours, seams, piping, folds, and non-upholstered wood/metal parts of Image 2. "
                f"ENVIRONMENT: {bg_clause}. Do NOT include text, labels, or watermarks.{dims_part}{notes_part}\n\n"
                "MATERIAL & SCALING CONSTRAINT (FULL CASCO + CUSHIONS · 97% MACRO REDUCTION): "
                f"Apply the precise weave pattern ({f_tex}), multi-tone thread colors/flecks ({f_color}), and surface response ({f_light}) from Image 1 "
                "uniformly across 100% of the upholstered body shell (EL CASCO COMPLETO: outer & inner backrest, armrests/descansabrazos, upholstered base rail/faldón, sides) "
                "AND all cushions with 0% hue shift. "
                "CRITICAL: Scale down this macro texture dramatically (approx. 97% reduction) so it looks like finely woven fabric from furniture distance, "
                "explicitly retaining dense micro-thread details without turning into a flat solid color, leaving the casco in the old fabric, or creating oversized loops.\n\n"
                f"Negative Prompt:\n{fab_neg}, altered camera angle, altered wood legs, text, watermark, collage."
            )
            vision_task = (
                f"Image 1 is a close-up FABRIC SWATCH ({f_name}: {f_color}; {f_tex}; {f_light}). "
                f"Image 2 is a TARGET FURNITURE VIEW '{view_name}' (exact geometry and camera angle).\n"
                "Write a surgical image-editing prompt in the exact V1+V7 style (INSTRUCTION -> GENERATE -> GEOMETRY & SCENE CONSTRAINT -> CAMERA CONSTRAINT -> "
                "MATERIAL & SCALING CONSTRAINT -> Negative Prompt) commanding the model to lock Image 2's exact camera angle, silhouette, seams, folds, and wooden/metal parts "
                "while replacing 100% of BOTH the upholstered casco (backrest, armrests, upholstered base rail/sides) AND all cushions with Image 1's exact weave and undertones "
                f"(~97% macro-to-furniture reduction, 0% hue shift, never flat solid color, never suede/velvet unless specified), on {bg_clause}."
            )
        else:  # clonar_color
            local_ais = (
                f"[BATCH VIEW COLOR & FINISH CLONE · {view_name}]\n"
                f"TASK: Clone the exact color, wood/fabric finish, and surface texture from Image 1 onto the furniture '{furn_item}' in Image 2.\n\n"
                "ATTACHED IMAGES:\n"
                "- Image 1 (COLOR & MATERIAL MASTER REFERENCE): Source of truth for exact hue, timber/fabric texture, and sheen.\n"
                "- Image 2 (TARGET VIEW TO RECOLOR): Keep the EXACT camera angle, 3D silhouette, joinery, folds, and proportions.\n\n"
                "RULES:\n"
                "- Transfer Image 1's exact color tone and surface finish onto Image 2 cleanly with 0% hue drift.\n"
                "- Strictly preserve Image 2's camera angle and physical geometry.\n"
                f"- BACKGROUND: {bg_clause}.{dims_part}{notes_part}\n\n"
                "Exclude: repeating Image 1's camera angle, altered silhouette, mismatched tone, text, watermark."
            )
            vision_task = (
                "Image 1 is a COLOR & FINISH MASTER REFERENCE (correct color/material). Image 2 is a TARGET FURNITURE VIEW (correct camera angle & geometry, wrong color).\n"
                "Write a crisp, production-grade image-generation prompt commanding the model to keep Image 2's EXACT camera angle and 3D geometry "
                "while transferring Image 1's exact color, grain/weave, and finish with 0% hue shift, on "
                f"{bg_clause}."
            )

        local_dal = local_ais.replace("[", "").replace("]", "")
        local_mj = (
            f"Commercial product photography of {furn_item}, preserving exact angle and geometry, "
            f"{'pure white background #FFFFFF, zero shadows, ' if white_bg_enabled else ''}"
            "80mm f/11 --ar 1:1 --v 6.1 --style raw --no altered angle, generic fabric, flat texture, text, watermark"
        )

        key = self.get_api_key(api_key)
        if not key or not ref_bytes or not view_bytes:
            return {
                "google_ai_studio": local_ais,
                "chatgpt_dalle3": local_dal,
                "midjourney_v6": local_mj,
            }

        try:
            from google.genai import types

            client = self.get_client(key)
            if not client:
                return {"google_ai_studio": local_ais, "chatgpt_dalle3": local_dal, "midjourney_v6": local_mj}
            img1 = self._prepare_image(ref_bytes, max_dim=1024 if batch_mode == "vistas_tela" else 768)
            img2 = self._prepare_image(view_bytes, max_dim=768)
            sys_prompt = (
                f"You are an expert commercial furniture prompt engineer.\n{vision_task}\n"
                f"Furniture item: {furn_item}.{dims_part}{notes_part}\n"
                "Explicitly forbid any text, watermarks, or camera angle drift. Output ONLY the final prompt text."
            )
            res = self._call_gemini(
                client=client,
                contents=[sys_prompt, img1, img2],
                config=types.GenerateContentConfig(temperature=0.2),
                api_key=key,
            )
            txt = (res.text or "").strip() or local_ais
            return {
                "google_ai_studio": txt,
                "chatgpt_dalle3": txt,
                "midjourney_v6": local_mj,
            }
        except Exception as e:
            print(f"[AIPromptServiceV7] Error en batch view prompt: {e}")
            return {
                "google_ai_studio": local_ais,
                "chatgpt_dalle3": local_dal,
                "midjourney_v6": local_mj,
            }

    # ------------------------------------------------------------------
    # PUNTO DE ENTRADA ÚNICO V7
    # ------------------------------------------------------------------
    def build_prompts(
        self,
        mode: str,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = "",
        tipo_mueble: str = "",
        medidas_texto: str = "",
        lugar_casa: str = "",
        vista_id: str = "vista_frontal",
        material_mode: str = "wood_only",
        wood_label: str = "",
        fabric_label: str = "",
        has_reference_imgs: bool = False,
        white_bg_enabled: bool = True,
        classic_numbering: bool = False,
        # Parámetros exclusivos para los 2 modos de lote (V4 mejorado):
        batch_ref_bytes: Optional[bytes] = None,
        batch_views: Optional[List[Tuple[str, bytes]]] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"Modo V7 desconocido: {mode}")

        ma = furniture_analysis or {}
        wa = wood_analysis or {}
        fa = fabric_analysis or {}

        furn_item = (tipo_mueble or "").strip() or ma.get("furniture_item") or furniture_name or "Furniture Piece"
        geom_struct = ma.get("geometric_structure") or "exact 3D silhouette, proportions, and joinery from the reference"
        existing_mats = ma.get("existing_materials") or "authentic materials, tones, and finishes from the reference"

        clean_notes_parts: List[str] = []
        if notas_usuario and notas_usuario.strip():
            clean_notes_parts.append(notas_usuario.strip())
        user_notes_clean = " | ".join(clean_notes_parts)

        profile_search = f"{furn_item} {medidas_texto} {user_notes_clean}"
        profile = self.detect_furniture_profile(furn_item, profile_search, geom_struct)

        has_wood = bool(wa) or bool(wood_label)
        has_fabric = bool(fa) or bool(fabric_label)
        w_label = wood_label or wa.get("name") or "Muestra de madera"
        f_label = fabric_label or fa.get("name") or "Muestra de tela"

        items: List[Dict[str, Any]] = []
        master_ais = ""
        master_dal = ""
        midjourney = ""

        if mode == "catalogo":
            for vid in VIEW_IDS:
                if vid == "vista_plano_tecnico":
                    items.append(
                        self._build_blueprint_item(
                            furn_item=furn_item,
                            furniture_name=furniture_name,
                            profile=profile,
                            medidas_usuario=medidas_texto,
                            user_notes_clean=user_notes_clean,
                        )
                    )
                elif vid == "vista_entorno_cliente":
                    items.append(
                        self._build_environment_item(
                            furn_item=furn_item,
                            furniture_name=furniture_name,
                            profile=profile,
                            geom_struct=geom_struct,
                            existing_mats=existing_mats,
                            wa=wa,
                            fa=fa,
                            has_wood=has_wood,
                            has_fabric=has_fabric,
                            has_ref=has_reference_imgs,
                            wood_label=w_label,
                            fabric_label=f_label,
                            lugar_casa=lugar_casa,
                            user_notes_clean=user_notes_clean,
                            classic_numbering=classic_numbering,
                            use_anchor=True,
                        )
                    )
                else:
                    items.append(
                        self._build_single_studio_view_prompt(
                            view_id=vid,
                            furn_item=furn_item,
                            furniture_name=furniture_name,
                            profile=profile,
                            geom_struct=geom_struct,
                            existing_mats=existing_mats,
                            wa=wa,
                            fa=fa,
                            has_wood=has_wood,
                            has_fabric=has_fabric,
                            has_ref=has_reference_imgs,
                            wood_label=w_label,
                            fabric_label=f_label,
                            user_notes_clean=user_notes_clean,
                            white_bg_enabled=True,
                            classic_numbering=classic_numbering,
                            use_anchor=(vid != "vista_frontal"),
                        )
                    )

            slots_master = self._build_image_slots(
                furn_item=furn_item,
                has_wood=has_wood,
                wood_label=w_label,
                has_fabric=has_fabric,
                fabric_label=f_label,
                has_ref=has_reference_imgs,
                include_anchor=False,
                classic_numbering=classic_numbering,
            )
            mat_ais, mat_dal = self._build_material_lock_text(
                profile=profile,
                furn_item=furn_item,
                existing_mats=existing_mats,
                wa=wa,
                fa=fa,
                wood_idx=slots_master["wood_idx"],
                fabric_idx=slots_master["fabric_idx"],
                has_wood=has_wood,
                has_fabric=has_fabric,
            )
            room_intro, companions = self._build_environment_room_context(profile, furn_item, lugar_casa)
            dims_bp = []
            if profile.get("diam_cm"):
                dims_bp.append(f"Diámetro Ø: {self._fmt_num(profile['diam_cm'])} cm")
            if profile.get("height_cm"):
                dims_bp.append(f"Alto: {self._fmt_num(profile['height_cm'])} cm")
            if profile.get("width_cm"):
                dims_bp.append(f"Ancho: {self._fmt_num(profile['width_cm'])} cm")
            if profile.get("depth_cm"):
                dims_bp.append(
                    f"{'Grosor' if profile['category'] == 'mirror' else 'Fondo'}: {self._fmt_num(profile['depth_cm'])} cm"
                )
            dims_summary = ", ".join(dims_bp) if dims_bp else (medidas_texto or "Exact proportions from Image 1")

            angles = profile["angles"]
            notes_block = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
            dim_line = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
            mirror_line = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""

            fab_neg_master = f", {self._fabric_negative_terms(fa, f_label)}" if has_fabric else ""

            master_ais = (
                "[COMMERCIAL 7-IMAGE CATALOG SERIES · TURN-BY-TURN SEQUENTIAL GENERATION]\n"
                f"TASK: Generate a complete 7-piece commercial catalog sequence for '{furn_item}' ('{furniture_name}'): "
                "5 studio cutouts on pure white (#FFFFFF), 1 isometric technical CAD blueprint, and 1 wide client home interior photo.\n\n"
                f"{slots_master['header_block']}\n\n"
                "FROZEN IDENTITY & MATERIALS:\n"
                f"{mat_ais}\n"
                f"- GEOMETRY RULE: {profile['geometry_rule']}{dim_line}{mirror_line}{notes_block}\n\n"
                "STUDIO STANDARDS (VIEWS 1 TO 6):\n"
                "- Pure seamless solid white background (#FFFFFF), 0% ground shadows, 0% drop shadows, 0% reflections.\n"
                "- Views 1–5: 100MP medium-format 80mm f/11 commercial photography, centered at ~72% of canvas.\n\n"
                "TURN-BY-TURN EXECUTION PROTOCOL:\n"
                "Output ONE single standalone image per turn. Never reply with text only.\n"
                "CRITICAL ROTATION RULE: Orbit the camera cleanly to each new requested angle; never repeat the previous angle or re-output Image 1 as-is.\n"
                f"- CURRENT TURN -> Generate ONLY Vista 1 (Frontal 0°): {angles['vista_frontal']}\n"
                "Conclude with: \"📸 Vista 1 generada. Escribe 'foto' para generar la Vista 2 (3/4 Perspectiva 45°).\"\n"
                "- Subsequent turns (triggered ONLY when user types 'foto', one view per message):\n"
                f"  2. Vista 2 (3/4 Perspectiva 45°): {angles['vista_perspectiva_3_4']}\n"
                f"  3. Vista 3 (Lateral 90°): {angles['vista_lateral']}\n"
                f"  4. Vista 4 (Picada Alta 65°): {angles['vista_picada_alta']}\n"
                f"  5. Vista 5 (Superior Cenital 90°): {angles['vista_superior_cenital']}\n"
                f"  6. Vista 6 (Plano Técnico Isométrico): Minimalist black (#000000) CAD line art only on #FFFFFF, zero color/shading, showing ONLY: {dims_summary}.\n"
                f"  7. Vista 7 (Entorno Casa Cliente): Wide distant 35mm interior shot {room_intro}; {companions} Deliberate contrasting room palette so the piece stands out.\n\n"
                f"Exclude: collage, text/watermarks, ground shadows in views 1-6, CGI plastic sheen{fab_neg_master}{profile['neg_add']}."
            )

            master_dal = (
                f"Generate 7 separate standalone commercial images in sequence (do NOT combine into a grid or collage) for '{furn_item}' ('{furniture_name}'):\n"
                f"1. Direct Front View (0°): {angles['vista_frontal']}\n"
                f"2. 3/4 Perspective (45°): {angles['vista_perspectiva_3_4']}\n"
                f"3. Strict Lateral Profile (90°): {angles['vista_lateral']}\n"
                f"4. Elevated High-Angle (65°): {angles['vista_picada_alta']}\n"
                f"5. Overhead Plan View (90°): {angles['vista_superior_cenital']}\n"
                f"6. Technical Isometric CAD Blueprint: Pure black line art on #FFFFFF, zero shading/color, dimension arrows for: {dims_summary}.\n"
                f"7. Client Home Interior (Distant Wide Shot): Placed {room_intro}; {companions} Contrasting neutral palette.\n\n"
                f"Materials & Structure: {mat_dal} {profile['geometry_rule']} {profile['dimensions_rule']}"
                f"{' User notes: ' + user_notes_clean if user_notes_clean else ''}\n"
                "Views 1–6 on pure solid white #FFFFFF with 0% ground/drop shadows."
            )
            midjourney = (
                f"Commercial luxury catalog photography of {furn_item}, {geom_struct}, pure solid white background #FFFFFF, "
                "zero ground shadows, 80mm f/11 5400K studio lighting --ar 1:1 --v 6.1 --style raw --no shadow, collage, text"
            )

        elif mode == "vista_suelta":
            if vista_id not in ALL_SINGLE_VIEWS:
                vista_id = "vista_frontal"
            if vista_id == "vista_plano_tecnico":
                it = self._build_blueprint_item(furn_item, furniture_name, profile, medidas_texto, user_notes_clean)
            elif vista_id == "vista_entorno_cliente":
                it = self._build_environment_item(
                    furn_item, furniture_name, profile, geom_struct, existing_mats,
                    wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                    lugar_casa, user_notes_clean, classic_numbering, use_anchor=True,
                )
            else:
                it = self._build_single_studio_view_prompt(
                    vista_id, furn_item, furniture_name, profile, geom_struct, existing_mats,
                    wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                    user_notes_clean, white_bg_enabled, classic_numbering,
                    use_anchor=(vista_id in ANCHOR_VIEWS),
                )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "material":
            it = self._build_material_swap_item(
                material_mode, furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, w_label, f_label, user_notes_clean, white_bg_enabled, classic_numbering,
                camera_angle=ma.get("camera_angle", ""),
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "entorno":
            it = self._build_environment_item(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                lugar_casa, user_notes_clean, classic_numbering, use_anchor=False,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "plano":
            it = self._build_blueprint_item(furn_item, furniture_name, profile, medidas_texto, user_notes_clean)
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "extraer":
            it = self._build_extraction_item(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, w_label, f_label, user_notes_clean, classic_numbering,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "hd":
            it = self._build_hd_item(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, w_label, f_label,
                user_notes_clean, white_bg_enabled, classic_numbering,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        else:  # vistas_tela | clonar_color
            views = batch_views or []
            if not views:
                raise ValueError("Sube al menos una vista objetivo para procesar el lote.")
            ref_b = batch_ref_bytes or b""
            ref_lbl = f_label if mode == "vistas_tela" else "Foto referencia color"
            guide = (
                [f"Image 1: Muestra de tela ({ref_lbl})", "Image 2: La vista objetivo correspondiente"]
                if mode == "vistas_tela"
                else ["Image 1: Foto del mueble con el color/acabado correcto", "Image 2: La vista objetivo a recolorear"]
            )

            def _run(pair: Tuple[str, bytes]) -> Tuple[str, bytes, Dict[str, str]]:
                vname, vbytes = pair
                return vname, vbytes, self._generate_batch_view_prompt(
                    batch_mode=mode,
                    ref_bytes=ref_b,
                    view_bytes=vbytes,
                    view_name=vname,
                    furn_item=furn_item,
                    medidas_texto=medidas_texto,
                    user_notes_clean=user_notes_clean,
                    white_bg_enabled=white_bg_enabled,
                    ref_label=ref_lbl,
                    fabric_analysis=fa if mode == "vistas_tela" else None,
                    api_key=api_key,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                batch_results = list(executor.map(_run, views))

            for idx, (vname, vbytes, pdict) in enumerate(batch_results, start=1):
                items.append({
                    "id": f"{mode}_{idx}",
                    "label": f"Vista {idx}: {vname}",
                    "short_name": f"Vista {idx}",
                    "icon": "🧵" if mode == "vistas_tela" else "🧬",
                    "google_ai_studio": pdict["google_ai_studio"],
                    "chatgpt_dalle3": pdict["chatgpt_dalle3"],
                    "midjourney_v6": pdict["midjourney_v6"],
                    "checklist": CHECKLISTS[mode],
                    "needs_anchor": False,
                    "attachment_guide": guide,
                    "preview_bytes": vbytes,
                })
            master_ais = "\n\n".join(f"=== {it['label'].upper()} ===\n{it['google_ai_studio']}" for it in items)
            master_dal = "\n\n".join(f"=== {it['label'].upper()} ===\n{it['chatgpt_dalle3']}" for it in items)
            midjourney = items[0]["midjourney_v6"] if items else ""

        clean_base_name = os.path.splitext(str(furniture_name or "Mueble").strip())[0].strip() or "Mueble"
        for idx_it, it in enumerate(items, start=1):
            if mode in ("vistas_tela", "clonar_color") and batch_views and idx_it <= len(batch_views):
                v_stem = os.path.splitext(str(batch_views[idx_it - 1][0] or clean_base_name).strip())[0].strip() or clean_base_name
                out_fname = f"{v_stem}.png"
            elif len(items) == 1 or idx_it == 1:
                out_fname = f"{clean_base_name}.png"
            else:
                out_fname = f"{clean_base_name}_{idx_it}.png"
            it["output_filename"] = out_fname
            name_note = (
                f"\nOUTPUT FILE NAME: {out_fname} "
                "(keep this exact original photo filename for delivery/saving; do NOT render any filename text inside the image)."
            )
            if it.get("google_ai_studio") and "OUTPUT FILE NAME:" not in it["google_ai_studio"]:
                it["google_ai_studio"] = it["google_ai_studio"].rstrip() + name_note
            if it.get("chatgpt_dalle3") and "OUTPUT FILE NAME:" not in it["chatgpt_dalle3"]:
                it["chatgpt_dalle3"] = it["chatgpt_dalle3"].rstrip() + name_note

        dims_summary_dict = {
            "category": profile["category"],
            "sub_category": profile["sub_category"],
            "width_cm": profile.get("width_cm"),
            "depth_cm": profile.get("depth_cm"),
            "height_cm": profile.get("height_cm"),
            "diam_cm": profile.get("diam_cm"),
        }
        warnings = self.sanity_warnings(
            profile["category"],
            profile.get("width_cm") or 0,
            profile.get("depth_cm") or 0,
            profile.get("height_cm") or 0,
            profile.get("diam_cm") or 0,
        )

        return {
            "mode": mode,
            "items": items,
            "master_ais": master_ais,
            "master_dal": master_dal,
            "midjourney": midjourney,
            "dims": dims_summary_dict,
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # BOTÓN DIRECTO: 3/4 MIRANDO A LA DERECHA · BLANCO SIN SOMBRA · 2054×2054
    # ------------------------------------------------------------------
    def build_34_derecha_2054_prompts(
        self,
        furniture_name: str,
        furniture_analysis: Optional[Dict[str, Any]] = None,
        wood_analysis: Optional[Dict[str, Any]] = None,
        fabric_analysis: Optional[Dict[str, Any]] = None,
        notas_usuario: str = "",
        tipo_mueble: str = "",
        medidas_texto: str = "",
        wood_label: str = "",
        fabric_label: str = "",
        has_reference_imgs: bool = False,
        classic_numbering: bool = False,
    ) -> Dict[str, Any]:
        ma = furniture_analysis or {}
        wa = wood_analysis or {}
        fa = fabric_analysis or {}

        clean_base_name = os.path.splitext(str(furniture_name or "Mueble").strip())[0].strip() or "Mueble"
        out_fname = f"{clean_base_name}.png"
        furn_item = (tipo_mueble or "").strip() or ma.get("furniture_item") or clean_base_name or "Furniture Piece"
        geom_struct = ma.get("geometric_structure") or "exact 3D silhouette, proportions, and joinery from the reference"
        existing_mats = ma.get("existing_materials") or "authentic materials, tones, and finishes from the reference"
        user_notes_clean = (notas_usuario or "").strip()

        profile_search = f"{furn_item} {medidas_texto} {user_notes_clean}"
        profile = self.detect_furniture_profile(furn_item, profile_search, geom_struct)

        has_wood = bool(wa) or bool(wood_label)
        has_fabric = bool(fa) or bool(fabric_label)
        w_label = wood_label or wa.get("name") or "Muestra de madera"
        f_label = fabric_label or fa.get("name") or "Muestra de tela"

        slots = self._build_image_slots(
            furn_item=furn_item,
            has_wood=has_wood,
            wood_label=w_label,
            has_fabric=has_fabric,
            fabric_label=f_label,
            has_ref=has_reference_imgs,
            include_anchor=False,
            classic_numbering=classic_numbering,
        )
        mat_ais, mat_dal = self._build_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            wood_idx=slots["wood_idx"],
            fabric_idx=slots["fabric_idx"],
            has_wood=has_wood,
            has_fabric=has_fabric,
        )

        angle_right_ais = (
            "Strict commercial 3/4 perspective at a 45-degree angle with the furniture FACING TOWARD THE RIGHT "
            "(front facade oriented toward the right side of the frame, left side panel/armrest receding cleanly in 3D depth), "
            "camera slightly elevated 12°–15° at studio eye-line."
        )
        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" Mandatory user directives: {user_notes_clean}." if user_notes_clean else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        fab_neg_34 = f", {self._fabric_negative_terms(fa, f_label)}" if has_fabric else ""
        name_note = (
            f"\nOUTPUT FILE NAME: {out_fname} "
            "(keep this exact original photo filename for delivery/saving; do NOT render any filename text inside the image)."
        )

        prompt_ais = (
            "[COMMERCIAL MASTER CUTOUT · 3/4 FACING RIGHT · PURE WHITE #FFFFFF · ZERO SHADOWS · 2054x2054 PX]\n"
            f"TASK: Generate ONE standalone ultra-sharp commercial catalog photograph of '{furn_item}' ('{clean_base_name}') "
            "in a 3/4 perspective facing toward the RIGHT, isolated on pure solid white (#FFFFFF) with ABSOLUTELY ZERO SHADOWS, "
            "formatted at exact 1:1 square 2054x2054 px proportions.\n\n"
            f"{slots['header_block']}\n\n"
            "CAMERA, ORIENTATION & 2054x2054 SQUARE CANVAS:\n"
            f"- 3/4 RIGHT-FACING ANGLE: {angle_right_ais}\n"
            "- EXACT RESOLUTION & FRAMING: Square 1:1 canvas (2054 x 2054 pixels). Center the single furniture piece occupying ~74% of the frame with clean balanced ~13% pure white margins on all 4 sides. Zero cropping, no collage.\n\n"
            "PURE WHITE BACKGROUND & STRICT ZERO-SHADOW MANDATE:\n"
            "- BACKGROUND: 100% pure seamless solid digital white (#FFFFFF, RGB 255,255,255) everywhere around and beneath the legs/base.\n"
            "- ABSOLUTELY NO SHADOWS (0% SOMBRAS): 0% ground shadow, 0% contact shadow under legs, 0% drop shadow, 0% ambient floor shadow, 0% floor reflection, 0% studio horizon line.\n\n"
            "MATERIAL, CASCO FABRIC TEXTURE & GEOMETRY LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY RULE: {profile['geometry_rule']}{dim_ais}{mirror_ais}{notes_ais}\n"
            "- OPTICS: 100MP medium-format camera, 80mm prime lens at f/11, even shadowless 5400K wrap-around softbox lighting, tack-sharp micro-texture edge-to-edge.\n\n"
            "Exclude: ground shadow, contact shadow, drop shadow, cast shadow, under-furniture shadow, floor reflection, grey floor, studio backdrop gradient, facing left, frontal 0-degree flat angle, collage, text, watermark, CGI plastic sheen"
            f"{fab_neg_34}{profile['neg_add']}."
            f"{name_note}"
        )

        prompt_dal = (
            f"Standalone 2054x2054 px (1:1 square) commercial catalog photograph of a single {furn_item} ('{clean_base_name}').\n"
            f"Camera & Orientation: {angle_right_ais} Centered in a 1:1 square 2054x2054 frame with balanced white margins.\n"
            "Background & Zero-Shadow Rule: Pure seamless solid digital white (#FFFFFF, RGB 255,255,255) with ABSOLUTELY ZERO SHADOWS — 0% ground shadow, 0% leg contact shadow, 0% drop shadow, and 0% floor reflection.\n"
            f"Materials & Casco Texture: {mat_dal}\n"
            f"Structure & Proportions: {profile['geometry_rule']} {profile['dimensions_rule']}{notes_dal}\n"
            f"Avoid: any shadows, contact shadow, floor line, reflections, facing left, collage, text, watermarks, CGI plastic look{fab_neg_34}{profile['neg_add']}."
            f"{name_note}"
        )

        prompt_mj = (
            f"Commercial luxury product photography of {furn_item}, 3/4 perspective at 45 degrees facing toward the right, "
            f"{geom_struct}, {mat_dal}, centered 1:1 square 2054x2054 composition, isolated on pure solid white background #FFFFFF, "
            "strictly zero shadows, zero contact shadow, zero reflection, 80mm lens f/11 even 5400K wrap-around lighting "
            "--ar 1:1 --v 6.1 --style raw --no shadow, ground shadow, drop shadow, contact shadow, reflection, floor, room, collage, text, watermark"
        )

        item = {
            "id": "vista_3_4_derecha_2054",
            "label": "3/4 Derecha · Blanco Sin Sombra · 2054×2054",
            "short_name": "3/4 Der · 2054×2054",
            "icon": "↘️",
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "output_filename": out_fname,
            "checklist": [
                "¿Está en posición 3/4 mirando hacia la derecha?",
                "¿Fondo blanco puro (#FFFFFF) y 0% sombras (ni debajo de las patas ni alrededor)?",
                "¿La misma textura y color de la tela se aplicó en todo el casco y cojines a escala real?",
                "¿La imagen final mide exactamente 2054 × 2054 px?",
            ],
            "needs_anchor": False,
            "attachment_guide": slots["guide"],
            "is_2054_special": True,
        }

        dims_summary_dict = {
            "category": profile["category"],
            "sub_category": profile["sub_category"],
            "width_cm": profile.get("width_cm"),
            "depth_cm": profile.get("depth_cm"),
            "height_cm": profile.get("height_cm"),
            "diam_cm": profile.get("diam_cm"),
        }
        warnings = self.sanity_warnings(
            profile["category"],
            profile.get("width_cm") or 0,
            profile.get("depth_cm") or 0,
            profile.get("height_cm") or 0,
            profile.get("diam_cm") or 0,
        )

        return {
            "mode": "vista_34_der_2054",
            "items": [item],
            "master_ais": "",
            "master_dal": "",
            "midjourney": prompt_mj,
            "dims": dims_summary_dict,
            "warnings": warnings,
        }

    @staticmethod
    def format_image_2054_white(
        raw_bytes: bytes,
        target_px: int = 2054,
        pure_white_border: bool = True,
    ) -> Dict[str, Any]:
        """
        Normaliza cualquier imagen a un lienzo cuadrado exacto de 2054×2054 px.
        Cuando pure_white_border=True, limpia el fondo exterior a blanco puro (#FFFFFF, RGB 255,255,255).
        """
        with Image.open(io.BytesIO(raw_bytes)) as src:
            img = ImageOps.exif_transpose(src)
            if img.mode in ("RGBA", "LA", "P"):
                if img.mode == "P":
                    img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                alpha = img.split()[-1] if "A" in img.getbands() else None
                bg.paste(img.convert("RGB"), mask=alpha)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            else:
                img = img.copy()

        w0, h0 = img.size
        if w0 != h0:
            if pure_white_border:
                side = max(w0, h0)
                sq = Image.new("RGB", (side, side), (255, 255, 255))
                sq.paste(img, ((side - w0) // 2, (side - h0) // 2))
                img = sq
            else:
                img = ImageOps.fit(img, (target_px, target_px), method=Image.Resampling.LANCZOS)

        if img.size != (target_px, target_px):
            img = img.resize((target_px, target_px), Image.Resampling.LANCZOS)

        if pure_white_border:
            px = img.load()
            W, H = img.size
            visited = bytearray(W * H)
            q: deque[Tuple[int, int]] = deque()

            def _is_near_white(r: int, g: int, b: int) -> bool:
                return min(r, g, b) >= 245 and (max(r, g, b) - min(r, g, b)) <= 8

            for x in range(W):
                for y in (0, H - 1):
                    idx = y * W + x
                    if not visited[idx] and _is_near_white(*px[x, y]):
                        visited[idx] = 1
                        q.append((x, y))
            for y in range(H):
                for x in (0, W - 1):
                    idx = y * W + x
                    if not visited[idx] and _is_near_white(*px[x, y]):
                        visited[idx] = 1
                        q.append((x, y))

            while q:
                cx, cy = q.popleft()
                px[cx, cy] = (255, 255, 255)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < W and 0 <= ny < H:
                        nidx = ny * W + nx
                        if not visited[nidx] and _is_near_white(*px[nx, ny]):
                            visited[nidx] = 1
                            q.append((nx, ny))

        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG", optimize=True)
        jpg_buf = io.BytesIO()
        img.save(jpg_buf, format="JPEG", quality=96, subsampling=0, optimize=True)

        return {
            "png": png_buf.getvalue(),
            "jpg": jpg_buf.getvalue(),
            "width": img.size[0],
            "height": img.size[1],
        }

    def generate_catalog_photo(
        self,
        prompt_text: str,
        primary_bytes: bytes,
        wood_bytes: Optional[bytes] = None,
        fabric_bytes: Optional[bytes] = None,
        ref_bytes: Optional[List[bytes]] = None,
        anchor_bytes: Optional[bytes] = None,
        pure_white_border: bool = True,
        preferred_image_model: str = "gemini-nano-banana-2.1",
        api_key: Optional[str] = None,
        flux_fallback_prompt: str = "",
        allow_flux_fallback: bool = True,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Motor universal de generación directa de fotografías de catálogo en 2054×2054 px:
        1) Intenta Gemini Nano Banana multimodal (clonado 1:1 de píxeles de mueble + tela en casco).
        2) Si la API key está en capa gratuita sin cuota de imagen (429), entra al instante al
           motor gratuito FLUX alimentado con el análisis visual exacto de Gemini Vision.
        """
        if not primary_bytes:
            return None, "Falta la imagen base para generar la fotografía."

        key = self.get_api_key(api_key)
        client = self.get_client(key) if key else None
        last_err_msg = ""

        if client and time.time() >= self._img_quota_exhausted_until:
            try:
                from google.genai import types

                contents_img: List[Any] = [
                    prompt_text,
                    self._prepare_image(primary_bytes, max_dim=1024),
                ]
                if wood_bytes:
                    contents_img.append(self._prepare_image(wood_bytes, max_dim=768))
                if fabric_bytes:
                    contents_img.append(self._prepare_image(fabric_bytes, max_dim=768))
                for rb in (ref_bytes or [])[:1]:
                    if rb:
                        contents_img.append(self._prepare_image(rb, max_dim=768))
                if anchor_bytes:
                    contents_img.append(self._prepare_image(anchor_bytes, max_dim=1024))

                base_chain = ["gemini-nano-banana-2.1", "gemini-3-pro-image"]
                img_models = [preferred_image_model] + [m for m in base_chain if m != preferred_image_model]

                for m in img_models:
                    try:
                        resp = client.models.generate_content(
                            model=m,
                            contents=contents_img,
                            config=types.GenerateContentConfig(
                                response_modalities=["IMAGE", "TEXT"],
                            ),
                        )
                        raw_out: Optional[bytes] = None
                        for cand in getattr(resp, "candidates", None) or []:
                            content_obj = getattr(cand, "content", None)
                            for part in getattr(content_obj, "parts", None) or []:
                                inl = getattr(part, "inline_data", None)
                                data_val = getattr(inl, "data", None) if inl is not None else None
                                if data_val:
                                    raw_out = base64.b64decode(data_val) if isinstance(data_val, str) else bytes(data_val)
                                    break
                            if raw_out:
                                break
                        if raw_out:
                            formatted = self.format_image_2054_white(
                                raw_out,
                                target_px=2054,
                                pure_white_border=pure_white_border,
                            )
                            formatted["model"] = m
                            formatted["is_fallback"] = False
                            return formatted, None
                    except Exception as e:
                        err_up = str(e).upper()
                        last_err_msg = self.format_gemini_error(e)
                        print(f"[AIPromptServiceV7] Aviso generación de imagen ({m}): {e}")
                        if any(tok in err_up for tok in ("429", "RESOURCE_EXHAUSTED", "QUOTA")):
                            self._img_quota_exhausted_until = time.time() + 300.0
                            break
                        if any(tok in err_up for tok in ("LEAKED", "API_KEY_INVALID", "API KEY NOT VALID", "401", "403")):
                            break
                        continue
            except Exception as e_outer:
                last_err_msg = self.format_gemini_error(e_outer)

        if allow_flux_fallback:
            try:
                from services.free_image_service import free_image_service

                visual_prompt = (flux_fallback_prompt or prompt_text).strip()
                raw_flux = free_image_service.generate_flux_image(
                    visual_prompt,
                    width=768,
                    height=768,
                )
                formatted = self.format_image_2054_white(
                    raw_flux,
                    target_px=2054,
                    pure_white_border=pure_white_border,
                )
                formatted["model"] = "flux-studio-fallback"
                formatted["is_fallback"] = True
                return formatted, None
            except Exception as e_flux:
                last_err_msg = f"{last_err_msg} | Respaldo FLUX: {e_flux}".strip(" |")

        return None, (last_err_msg or "No se recibió imagen de salida.")

    def generate_image_34_derecha_2054(
        self,
        prompt_text: str,
        furniture_bytes: bytes,
        wood_bytes: Optional[bytes] = None,
        fabric_bytes: Optional[bytes] = None,
        ref_bytes: Optional[List[bytes]] = None,
        preferred_image_model: str = "gemini-nano-banana-2.1",
        api_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Genera directamente la fotografía 3/4 derecha sin sombras con Gemini Nano Banana
        y la entrega en 2054×2054 px exactos (#FFFFFF). Guarda cualquier error en self.last_image_error.
        """
        img_dict, err_msg = self.generate_catalog_photo(
            prompt_text=prompt_text,
            primary_bytes=furniture_bytes,
            wood_bytes=wood_bytes,
            fabric_bytes=fabric_bytes,
            ref_bytes=ref_bytes,
            pure_white_border=True,
            preferred_image_model=preferred_image_model,
            api_key=api_key,
        )
        self.last_image_error = err_msg
        return img_dict


ai_prompt_service_v7 = AIPromptServiceV7()

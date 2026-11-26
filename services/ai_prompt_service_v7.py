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

from PIL import Image, ImageOps, ImageStat

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

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
    name: str = Field(description="Nombre comercial corto y preciso del material, tejido o patrón")
    color_description: str = Field(description="Descripción cromática exacta: color base, colores secundarios de figuras/hilos, calidez y subtonos")
    texture_detail: str = Field(description="Estructura física 3D del tejido, grosor de hilo, relieve o veta en inglés")
    light_interaction: str = Field(description="Respuesta ante la luz: mate, satinado, brillo suave o pelo direccional")
    pattern_and_figures: Optional[str] = Field(
        default="",
        description="Descripción exacta de figuras, dibujos, motivos jacquard, rayas, cuadros, espiga/herringbone o 'Unpatterned uniform textile weave'",
    )
    has_visible_pattern: Optional[bool] = Field(
        default=False,
        description="True si la muestra tiene figuras, dibujos, motivos jacquard, rayas, cuadros, espiga, pata de gallo o diseño gráfico",
    )


class FurnitureAnalysisV7(BaseModel):
    furniture_item: str = Field(description="Tipo de mueble y estilo, o descripción de la muestra plana si es textura/tela/madera")
    camera_angle: str = Field(description="Ángulo de cámara observado")
    lighting_direction: str = Field(description="Dirección de iluminación")
    geometric_structure: str = Field(description="Topología 3D, silueta y estructura, o textura plana 2D de borde a borde si es muestra")
    wood_and_finish_analysis: str = Field(description="Especie de madera, veta y acabado")
    upholstery_analysis: str = Field(description="Tapicería y color o 'Sin tapicería'")
    existing_materials: str = Field(description="Resumen técnico integral de materiales")
    wood_details: Optional[str] = Field(default="", description="Detalle específico de madera")
    is_material_swatch: Optional[bool] = Field(
        default=False,
        description="True únicamente si la imagen principal es una muestra/textura plana de material (tela, madera, piel, piedra) sin un mueble 3D",
    )


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
                "Genera una llave nueva en Google AI Studio y configúrala en la variable de entorno GEMINI_API_KEY (Render > Environment o .env)."
            )
        if "API_KEY_INVALID" in up or "API KEY NOT VALID" in up or "UNAUTHENTICATED" in up or "401" in up:
            return "La GEMINI_API_KEY no es válida. Verifica la variable de entorno GEMINI_API_KEY en Render > Environment o en tu archivo .env."
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

    def _prepare_image(self, img_bytes: bytes, max_dim: int = 512, lossless: bool = False) -> Image.Image:
        with Image.open(io.BytesIO(img_bytes)) as src:
            fmt = (src.format or "").upper()
            orientation = 1
            try:
                exif = src.getexif()
                if exif:
                    orientation = int(exif.get(274, 1) or 1)
            except Exception:
                orientation = 1
            if not lossless and fmt in ("JPEG", "JPG") and max(src.size) > max_dim:
                try:
                    src.draft("RGB", (max_dim * 2, max_dim * 2))
                except Exception:
                    pass
            img = src
            if not lossless and max(img.size) > max_dim * 2:
                img = img.reduce(max(2, max(img.size) // (max_dim * 2)))
            if orientation not in (None, 1):
                try:
                    img = ImageOps.exif_transpose(img)
                except Exception:
                    pass
            if max(img.size) > max_dim:
                img = img.copy()
                img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            if img.mode in ("RGBA", "LA", "P"):
                rgba = img.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            else:
                img = img.copy()
            # Como en V1: para muestras de tela/madera enviamos la imagen RGB sin pérdida (sin submuestreo JPEG 4:2:0)
            if lossless:
                return img
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82)
        buf.seek(0)
        with Image.open(buf) as compressed:
            compressed.load()
            return compressed.copy()

    _PATTERN_KEYWORDS: Tuple[str, ...] = (
        "jacquard", "espiga", "herringbone", "raya", "rayas", "stripe", "striped", "ticking",
        "cuadro", "cuadros", "plaid", "tartan", "check", "gingham",
        "pata de gallo", "houndstooth", "rombo", "rombos", "chevron", "zigzag", "greca",
        "flor", "flores", "floral", "botanic", "botánico", "hoja", "hojas",
        "geom", "estampad", "print", "figura", "figuras", "patron", "patrón", "motif",
        "ikat", "kilim", "damasco", "damask", "brocado", "paisley", "lunar", "lunares",
    )

    @classmethod
    def _analyze_fabric_pixels_local(cls, sample_bytes: Optional[bytes], sample_name: str = "") -> Dict[str, Any]:
        """Extrae en <2 ms el perfil cromático real y si existen figuras/contraste de patrón a partir de los píxeles de la tela."""
        clean_label = (sample_name or "").rsplit(".", 1)[0].replace("_", " ").strip()
        lower_lbl = clean_label.lower()
        kw_pattern = any(k in lower_lbl for k in cls._PATTERN_KEYWORDS)

        color_desc = "tono, saturación, subtonos e hilos exactos visibles en la foto de la muestra de tela"
        tex_desc = "authentic woven upholstery yarn structure with crisp tactile micro-thread depth"
        light_desc = "Soft matte textile"
        pattern_desc = (
            f"visible woven/printed pattern and figures matching '{clean_label}' from the swatch photo"
            if kw_pattern
            else "Unpatterned uniform textile weave — micro-thread texture only unless subtle figures appear in the swatch photo"
        )
        has_pat = kw_pattern

        if any(w in lower_lbl for w in ("terciopelo", "velvet")):
            tex_desc = "plush dense directional velvet pile with fine micro-nap"
            light_desc = "Directional velvet sheen"
        elif any(w in lower_lbl for w in ("pana", "corduroy")):
            tex_desc = "distinct parallel ribbed corduroy wales with soft tactile pile"
            light_desc = "Soft matte textile"
        elif any(w in lower_lbl for w in ("boucle", "bouclé")):
            tex_desc = "dense nubby curled bouclé loops over structured woven backing"
        elif any(w in lower_lbl for w in ("lino", "linen")):
            tex_desc = "crisp natural slubbed linen basketweave with organic yarn thickness variation"
        elif any(w in lower_lbl for w in ("chenille", "chenilla")):
            tex_desc = "plush soft-spun chenille caterpillars intertwined in tight upholstery weave"

        if not sample_bytes or not isinstance(sample_bytes, (bytes, bytearray)) or len(sample_bytes) < 64:
            return MaterialAnalysisV7(
                name=clean_label or "Muestra de Tela Seleccionada",
                color_description=color_desc,
                texture_detail=tex_desc,
                light_interaction=light_desc,
                pattern_and_figures=pattern_desc,
                has_visible_pattern=has_pat,
            ).model_dump()

        def _tone_label(r_v: float, g_v: float, b_v: float) -> str:
            lum_v = 0.299 * r_v + 0.587 * g_v + 0.114 * b_v
            ch_v = max(r_v, g_v, b_v) - min(r_v, g_v, b_v)
            wm_v = r_v - b_v
            if ch_v < 16:
                if lum_v >= 222:
                    return "blanco marfil muy claro (crisp off-white / ivory)"
                if lum_v >= 185:
                    return "gris perla claro (light pearl grey)" if wm_v < 4 else "crema avena cálido (warm cream / oat)"
                if lum_v >= 135:
                    return "gris piedra neutro (medium stone grey)" if abs(wm_v) <= 5 else "taupe / greige cálido (warm greige / taupe)"
                if lum_v >= 75:
                    return "gris grafito / carbón medio (charcoal grey)"
                return "negro antracita profundo (deep charcoal / black)"
            if r_v >= g_v and r_v >= b_v:
                if (r_v - g_v) >= 38:
                    return "terracota / ladrillo cálido (terracotta / rust / brick)" if wm_v > 25 else "rosa palo / borgoña (dusty rose / burgundy)"
                if g_v > b_v + 18 and lum_v > 145:
                    return "beige arena / avena cálido (warm sand beige / oatmeal)" if ch_v < 45 else "mostaza / ocre dorado (warm ochre / mustard)"
                if g_v > b_v + 12 and lum_v <= 145:
                    return "café caramelo / tabaco / nogal (warm cognac / camel brown)"
                if (r_v - g_v) > 20:
                    return "terracota suave / arcilla (soft terracotta / clay)" if wm_v > 20 else "rosa viejo / malva (dusty mauve / rose)"
                return "arena cálido / topo natural (warm sand / natural taupe)"
            if g_v >= r_v and g_v >= b_v:
                return "verde salvia / oliva orgánico (sage / olive green)" if r_v >= b_v else "verde esmeralda / bosque (emerald / forest green)"
            return "azul marino / petróleo profundo (deep navy / petrol blue)" if lum_v < 115 else "azul pizarra / cielo agrisado (slate / dusty blue)"

        try:
            with Image.open(io.BytesIO(sample_bytes)) as src:
                im = src.convert("RGB").resize((96, 96), Image.Resampling.LANCZOS)
            st = ImageStat.Stat(im)
            mr, mg, mb = st.mean
            sr, sg, sb = st.stddev
            max_std = max(sr, sg, sb)
            base_tone = _tone_label(mr, mg, mb)

            cells = [
                ImageStat.Stat(im.crop((gx * 12, gy * 12, (gx + 1) * 12, (gy + 1) * 12))).mean
                for gy in range(8)
                for gx in range(8)
            ]
            adj_diffs = []
            for gy in range(8):
                for gx in range(7):
                    a = cells[gy * 8 + gx]
                    b = cells[gy * 8 + gx + 1]
                    adj_diffs.append(max(abs(a[c] - b[c]) for c in range(3)))
            for gy in range(7):
                for gx in range(8):
                    a = cells[gy * 8 + gx]
                    b = cells[(gy + 1) * 8 + gx]
                    adj_diffs.append(max(abs(a[c] - b[c]) for c in range(3)))
            max_adj = max(adj_diffs) if adj_diffs else 0.0

            if kw_pattern or max_adj >= 22.0 or max_std >= 24.0:
                has_pat = True
                sorted_cells = sorted(cells, key=lambda c: 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])
                dark_grp = sorted_cells[:24]
                light_grp = sorted_cells[-24:]
                dr = sum(c[0] for c in dark_grp) / len(dark_grp)
                dg = sum(c[1] for c in dark_grp) / len(dark_grp)
                db = sum(c[2] for c in dark_grp) / len(dark_grp)
                lr = sum(c[0] for c in light_grp) / len(light_grp)
                lg = sum(c[1] for c in light_grp) / len(light_grp)
                lb = sum(c[2] for c in light_grp) / len(light_grp)
                light_tone = _tone_label(lr, lg, lb)
                dark_tone = _tone_label(dr, dg, db)
                pattern_desc = (
                    "Distinct visible figures, motifs, stripes, or multi-color woven jacquard/pattern directly visible in the swatch photo — "
                    "must be replicated 1:1 with exact figure shapes, repeat spacing, and multi-tone contrast"
                )
                if light_tone != dark_tone:
                    color_desc = (
                        f"combinación exacta a la muestra: fondo/tonos claros en {light_tone} (~RGB {int(round(lr))},{int(round(lg))},{int(round(lb))}) "
                        f"con figuras/motivos e hilos en {dark_tone} (~RGB {int(round(dr))},{int(round(dg))},{int(round(db))})"
                    )
                else:
                    color_desc = (
                        f"base {base_tone} con figuras/motivos en relieve exactamente iguales a la foto de la muestra "
                        f"(~RGB {int(round(mr))},{int(round(mg))},{int(round(mb))})"
                    )
            elif max_std >= 11.0:
                color_desc = (
                    f"{base_tone} jaspeado multi-hilo con subtonos y motas entretejidas exactas a la muestra "
                    f"(~RGB {int(round(mr))},{int(round(mg))},{int(round(mb))})"
                )
            else:
                color_desc = (
                    f"{base_tone} uniforme con el matiz y subtono exacto de la foto de la muestra "
                    f"(~RGB {int(round(mr))},{int(round(mg))},{int(round(mb))})"
                )
        except Exception:
            pass

        return MaterialAnalysisV7(
            name=clean_label or "Muestra de Tela Seleccionada",
            color_description=color_desc,
            texture_detail=tex_desc,
            light_interaction=light_desc,
            pattern_and_figures=pattern_desc,
            has_visible_pattern=has_pat,
        ).model_dump()

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
            default_material = self._analyze_fabric_pixels_local(sample_bytes, sample_name=clean_label)
            instructions = (
                "Analyze this upholstery fabric swatch photo with surgical 1:1 visual precision (V1+V7 commercial standard) so an image model can replicate its EXACT figures/patterns, colors, and 3D weave:\n"
                "1) name: Short accurate commercial fabric name reflecting its exact weave, pattern, and color (e.g. 'Geometric Terracotta & Cream Jacquard', 'Heathered Salt-and-Pepper Bouclé', 'Olive Slubbed Basketweave Linen').\n"
                "2) color_description: Exhaustive chromatic description in Spanish + English of the exact background/base hue, exact undertones (warm/cool/neutral), brightness, AND the exact color of every figure, motif, stripe, check, or multi-tone fleck thread visible in the photo.\n"
                "3) has_visible_pattern & pattern_and_figures: Inspect carefully whether the fabric has ANY figures, drawings, motifs, stripes (rayas), checks/plaid (cuadros), herringbone (espiga), houndstooth (pata de gallo), diamonds/chevrons, floral/botanical shapes, or jacquard patterns. "
                "If YES, set has_visible_pattern=true and describe in pattern_and_figures (in detailed English) the exact figure geometry, motif proportions, orientation (vertical/horizontal/diagonal), repeat spacing, and figure-to-ground contrast. "
                "If NO (solid, melange, heathered, plain bouclé/linen/velvet), set has_visible_pattern=false and set pattern_and_figures='Unpatterned uniform textile weave — micro-thread texture only, zero figures or prints'.\n"
                "4) texture_detail: Detailed 3D physical weave & yarn structure in English (e.g. 'raised woven jacquard motifs over tight linen ground', 'dense nubby bouclé loops over cool grey under-weave', 'distinct parallel corduroy wales', 'plush directional velvet pile', 'crisp slubbed basketweave').\n"
                "5) light_interaction: Surface sheen ('Dead-matte natural fiber', 'Soft matte textile', 'Subtle satin jacquard sheen', or 'Directional velvet sheen')."
            )
        elif is_wood:
            default_material = MaterialAnalysisV7(
                name=clean_label or "Madera Natural Seleccionada",
                color_description="exact timber stain hue, warmth, and natural grain contrast visible in the attached wood sample",
                texture_detail="continuous natural wood grain pores and realistic timber surface fibers",
                light_interaction="soft satin-matte timber sheen without plastic glare",
                pattern_and_figures="Natural anatomical wood grain flow",
                has_visible_pattern=False,
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
                pattern_and_figures="",
                has_visible_pattern=False,
            ).model_dump()
            instructions = f"Analyze this material sample ({material_type}) with precision: name, color description, texture detail, light interaction."

        if not key or not sample_bytes:
            return default_material

        try:
            from google.genai import types

            client = self.get_client(key)
            if not client:
                return default_material
            # Igual que en V1: imagen RGB 1024px sin compresión con pérdida para captar hilos, colores y figuras exactas
            img = self._prepare_image(sample_bytes, max_dim=1024, lossless=True)
            res = self._call_gemini(
                client=client,
                contents=[f"You are an expert luxury furniture materials and textile engineer. {instructions}", img],
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
            if is_fabric:
                if not data.get("pattern_and_figures"):
                    data["pattern_and_figures"] = default_material.get("pattern_and_figures", "")
                if any(k in clean_label.lower() for k in self._PATTERN_KEYWORDS):
                    data["has_visible_pattern"] = True
                else:
                    data["has_visible_pattern"] = bool(data.get("has_visible_pattern", False))
            return data
        except Exception as e:
            print(f"[AIPromptServiceV7] Error analyzing material: {e}")
            return default_material

    _FURNITURE_KEYWORDS: Tuple[str, ...] = (
        "espejo", "mirror", "luna",
        "buro", "buró", "noche", "velador", "nightstand",
        "cama", "bed", "cabecera", "headboard",
        "sofa", "sofá", "sillon", "sillón", "silla", "chair", "butaca", "poltrona", "banca", "bench", "banqueta", "stool", "taburete",
        "mesa", "table", "escritorio", "desk", "comedor", "consola", "arrimo",
        "credenza", "aparador", "comoda", "cómoda", "librero", "armario", "gabinete", "buffet", "dresser",
    )
    _SWATCH_KEYWORDS: Tuple[str, ...] = (
        "muestra", "swatch", "textura", "tramado", "tejido plano",
        "fabric sample", "wood sample", "solo tela", "solo madera",
    )

    @staticmethod
    def _is_flat_swatch_image(img_bytes: Optional[bytes]) -> bool:
        """Detecta localmente (<2 ms) si una imagen es una muestra/textura plana de borde a borde (tela, madera, piel, piedra) y no un mueble 3D."""
        if not img_bytes or not isinstance(img_bytes, (bytes, bytearray)) or len(img_bytes) < 64:
            return False
        try:
            with Image.open(io.BytesIO(img_bytes)) as src:
                im = src.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
            max_std = max(ImageStat.Stat(im).stddev)
            # Descarta lienzos sintéticos de 1 solo color plano (<0.8) o escenas de alto contraste (>32)
            if max_std < 0.8 or max_std >= 32.0:
                return False

            border_r, border_g, border_b = 0.0, 0.0, 0.0
            border_n = 0
            white_b = 0
            dark_b = 0
            center_r, center_g, center_b = 0.0, 0.0, 0.0
            center_n = 0

            for y in range(64):
                for x in range(64):
                    r, g, b = im.getpixel((x, y))
                    if x < 4 or x >= 60 or y < 4 or y >= 60:
                        border_r += r
                        border_g += g
                        border_b += b
                        border_n += 1
                        if r > 240 and g > 240 and b > 240:
                            white_b += 1
                        elif r < 18 and g < 18 and b < 18:
                            dark_b += 1
                    elif 16 <= x < 48 and 16 <= y < 48:
                        center_r += r
                        center_g += g
                        center_b += b
                        center_n += 1

            if border_n == 0 or center_n == 0:
                return False
            if (white_b / border_n) >= 0.20 or (dark_b / border_n) >= 0.20:
                return False

            center_mean = (center_r / center_n, center_g / center_n, center_b / center_n)
            border_mean = (border_r / border_n, border_g / border_n, border_b / border_n)
            center_border_diff = max(abs(center_mean[c] - border_mean[c]) for c in range(3))
            if center_border_diff >= 22.0:
                return False

            cell_means = [
                ImageStat.Stat(im.crop((gx * 16, gy * 16, (gx + 1) * 16, (gy + 1) * 16))).mean
                for gy in range(4)
                for gx in range(4)
            ]
            grid_max_diff = max(
                abs(a[c] - b[c])
                for a in cell_means
                for b in cell_means
                for c in range(3)
            )
            return grid_max_diff < 68.0
        except Exception:
            return False

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

        raw_list = furniture_bytes if isinstance(furniture_bytes, list) else [furniture_bytes]
        primary_fb = next((fb for fb in raw_list if isinstance(fb, (bytes, bytearray)) and fb), None)

        explicit_furn = any(w in lower_notes for w in self._FURNITURE_KEYWORDS)
        explicit_swatch = any(w in lower_notes for w in self._SWATCH_KEYWORDS)
        local_swatch = (not explicit_furn) and (explicit_swatch or self._is_flat_swatch_image(primary_fb))

        if local_swatch:
            fallback = FurnitureAnalysisV7(
                furniture_item="flat close-up material / textile texture swatch",
                camera_angle="flat full-bleed 90° macro top-down view",
                lighting_direction="even diffused macro surface lighting",
                geometric_structure="flat full-bleed 2D surface texture filling 100% of the frame from edge to edge with zero 3D furniture objects",
                wood_and_finish_analysis="as shown in the flat surface sample",
                upholstery_analysis="authentic woven fibers, threads, and color undertones directly from the flat swatch",
                existing_materials="exact authentic surface weave, grain, fibers, and color tones directly from the attached swatch",
                is_material_swatch=True,
            ).model_dump()
        else:
            inferred_type = "exact subject shown in the attached photo"
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
                geometric_structure="exact 3D silhouette, contours, structure, and physical proportions directly from the attached photo",
                wood_and_finish_analysis="authentic surface tone, grain, and sheen from the attached reference",
                upholstery_analysis="authentic textile weave and tone from the attached reference",
                existing_materials="authentic materials, colors, and surface finishes directly from the attached reference",
                is_material_swatch=False,
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
            for fb in raw_list[:2]:
                if fb:
                    actual_imgs.append(self._prepare_image(fb, max_dim=768))

            wood_imgs: List[Image.Image] = []
            for wb in (wood_bytes or [])[:1]:
                if wb:
                    wood_imgs.append(self._prepare_image(wb, max_dim=1024, lossless=True))

            fab_imgs: List[Image.Image] = []
            for tb in (fabric_bytes or [])[:1]:
                if tb:
                    fab_imgs.append(self._prepare_image(tb, max_dim=1024, lossless=True))

            ref_imgs: List[Image.Image] = []
            for rb in (reference_bytes or [])[:1]:
                if rb:
                    ref_imgs.append(self._prepare_image(rb, max_dim=512))

            prompt = (
                "You are an expert furniture visualizer, materials specialist, and commercial product photographer. "
                "IMPORTANT FIRST STEP: Check whether the primary image shows a 3D piece of furniture/decor OR a flat close-up "
                "material swatch / surface texture sample (e.g. fabric weave close-up, wood grain board, leather or stone texture "
                "filling the frame from edge to edge with NO 3D furniture object). "
                "If it is a flat material swatch/texture with no 3D furniture piece, set is_material_swatch=true, describe the exact "
                "material/weave/grain in furniture_item (e.g. 'flat beige woven upholstery fabric swatch'), set camera_angle='flat full-bleed 90° macro top-down view', "
                "and set geometric_structure='flat full-bleed 2D surface texture filling 100% of the frame edge-to-edge with zero 3D furniture objects'. "
                "Otherwise set is_material_swatch=false and produce a concise, accurate 3D geometric & camera specification: "
                "item type/style, EXACT camera_angle and framing (e.g. 'strict eye-level 3/4 view facing right', 'horizontal side profile'), "
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
            if explicit_furn:
                data["is_material_swatch"] = False
            elif explicit_swatch:
                data["is_material_swatch"] = True
            else:
                data["is_material_swatch"] = bool(data.get("is_material_swatch", False))
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
        """Ejecuta en paralelo el análisis separado de mueble, tela y madera (como en V1, sin contaminar la geometría del mueble con las muestras)."""
        f_ana: Dict[str, Any] = {}
        w_ana: Optional[Dict[str, Any]] = None
        t_ana: Optional[Dict[str, Any]] = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            fut_f = (
                ex.submit(
                    self.analyze_furniture_for_enhancement,
                    furniture_bytes=furniture_bytes,
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
                f_ana["has_wood_sample"] = bool(wood_bytes)
                f_ana["has_fabric_sample"] = bool(fabric_bytes)
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
    # MAPEO DINÁMICO DE RANURAS DE IMAGEN CON NOMBRE EXACTO DE FOTO COPIADA
    # ------------------------------------------------------------------
    @staticmethod
    def _canonical_photo_filename(raw_name: str, fallback: str = "foto.png") -> str:
        """Normaliza el nombre de foto exactamente igual que el botón Copiar foto."""
        raw = str(raw_name or "").strip().replace("\\", "/")
        base = raw.rsplit("/", 1)[-1].strip() if raw else ""
        if not base:
            base = str(fallback or "foto.png").strip() or "foto.png"
        dl_name = base if "." in base else f"{base}.png"
        clean = dl_name.replace("\\", "_").replace('"', "").replace("'", "").strip()
        return clean or "foto.png"

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
        furniture_name: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
    ) -> Dict[str, Any]:
        """Calcula el índice exacto (Image 1, Image 2...) y el nombre exacto de cada foto copiada."""
        slots: List[str] = []
        guide: List[str] = []
        dal_parts: List[str] = []
        idx = 1

        raw_furn_list = [str(x).strip() for x in (furniture_filenames or []) if str(x or "").strip()]
        if not raw_furn_list:
            raw_furn_list = [furniture_name or furn_item or "mueble.png"]
        furn_files = [self._canonical_photo_filename(fn, f"mueble_{i + 1}.png") for i, fn in enumerate(raw_furn_list)]
        primary_furn_file = furn_files[0]

        slots.append(
            f'- Image {idx} (PRIMARY FURNITURE REFERENCE · FILE: "{primary_furn_file}"): '
            f'Take the furniture piece strictly from photo "{primary_furn_file}" — exact 3D silhouette, joinery, and proportions of \'{furn_item}\'.'
        )
        guide.append(f'Image {idx}: Foto original del mueble ("{primary_furn_file}")')
        dal_parts.append(f'Image {idx} = "{primary_furn_file}" (furniture piece)')
        idx += 1

        extra_furn_indices: List[int] = []
        for extra_file in furn_files[1:]:
            extra_furn_indices.append(idx)
            slots.append(
                f'- Image {idx} (ADDITIONAL FURNITURE ANGLE · FILE: "{extra_file}"): '
                f'Supplementary angle of the same furniture piece from photo "{extra_file}".'
            )
            guide.append(f'Image {idx}: Vista adicional del mueble ("{extra_file}")')
            dal_parts.append(f'Image {idx} = "{extra_file}" (extra furniture angle)')
            idx += 1

        wood_idx: Optional[int] = None
        wood_file = ""
        if has_wood:
            wood_idx = 2 if classic_numbering else idx
            wood_file = self._canonical_photo_filename(wood_filename or wood_label, "madera.png")
            slots.append(
                f'- Image {wood_idx} (WOOD SAMPLE GROUND TRUTH · FILE: "{wood_file}"): '
                f'Take exact wood species, continuous grain, and stain tone from photo "{wood_file}" ({wood_label}).'
            )
            guide.append(f'Image {wood_idx}: Muestra de madera ("{wood_file}")')
            dal_parts.append(f'Image {wood_idx} = "{wood_file}" (wood sample)')
            if not classic_numbering:
                idx += 1

        fabric_idx: Optional[int] = None
        fabric_file = ""
        if has_fabric:
            fabric_idx = (3 if has_wood else 2) if classic_numbering else idx
            fabric_file = self._canonical_photo_filename(fabric_filename or fabric_label, "tela.png")
            slots.append(
                f'- Image {fabric_idx} (FABRIC SWATCH GROUND TRUTH · FILE: "{fabric_file}"): '
                f'Absolute 1:1 pixel truth for upholstery — copy exact figures/patterns, exact thread colors/undertones, and 3D textile weave strictly from photo "{fabric_file}" ({fabric_label}).'
            )
            guide.append(f'Image {fabric_idx}: Muestra de tela ("{fabric_file}")')
            dal_parts.append(f'Image {fabric_idx} = "{fabric_file}" (fabric swatch — single truth for figures, color & weave)')
            if not classic_numbering:
                idx += 1

        ref_idx: Optional[int] = None
        if has_ref and not classic_numbering:
            ref_idx = idx
            slots.append(f"- Image {ref_idx} (AUXILIARY ANGLE REFERENCE): Supplementary structural angle details.")
            guide.append(f"Image {ref_idx}: Referencia auxiliar de ángulo")
            dal_parts.append(f"Image {ref_idx} = auxiliary angle reference")
            idx += 1

        anchor_idx: Optional[int] = None
        if include_anchor:
            anchor_idx = idx
            slots.append(
                f"- Image {anchor_idx} (APPROVED VISTA 1 ANCHOR — WHEN ATTACHED): Use as visual lock for exact outline, color, and finish; change ONLY camera angle."
            )
            guide.append(f"Image {anchor_idx} (recomendada): Tu render aprobado de Vista 1")
            dal_parts.append(f"Image {anchor_idx} (optional) = approved Vista 1 anchor")

        match_rule = (
            "PHOTO IDENTIFICATION RULE: Match every attached image by its exact copied file name above "
            "(or by attachment order Image 1, Image 2, ... if pasted from clipboard); NEVER confuse which photo is the target furniture vs a material swatch."
        )

        return {
            "header_block": "ATTACHED REFERENCE IMAGES:\n" + "\n".join(slots) + "\n" + match_rule,
            "dal_photo_map": "Attached Photos Map (identify by exact copied filename or order): " + " | ".join(dal_parts) + ".",
            "guide": guide,
            "wood_idx": wood_idx,
            "fabric_idx": fabric_idx,
            "ref_idx": ref_idx,
            "anchor_idx": anchor_idx,
            "primary_furn_file": primary_furn_file,
            "furn_files": furn_files,
            "extra_furn_indices": extra_furn_indices,
            "wood_file": wood_file,
            "fabric_file": fabric_file,
        }

    @classmethod
    def _is_patterned_fabric(cls, fa: Optional[Dict[str, Any]] = None, fabric_label: str = "") -> bool:
        """Determina si la tela tiene figuras, dibujos, rayas, cuadros, espiga o motivos jacquard."""
        fa = fa or {}
        if bool(fa.get("has_visible_pattern")):
            return True
        pat_txt = str(fa.get("pattern_and_figures") or "").strip().lower()
        if pat_txt and not any(
            u in pat_txt
            for u in ("unpatterned", "zero figures", "sin figuras", "no pattern", "solid weave")
        ):
            return True
        combined = f"{fabric_label} {fa.get('name', '')} {fa.get('texture_detail', '')} {pat_txt}".lower()
        return any(k in combined for k in cls._PATTERN_KEYWORDS)

    @classmethod
    def _fabric_negative_terms(cls, fa: Optional[Dict[str, Any]] = None, fabric_label: str = "") -> str:
        """Términos negativos probados de V1 + protección de figuras, color exacto y casco completo."""
        fa = fa or {}
        combined = f"{fabric_label} {fa.get('name', '')} {fa.get('texture_detail', '')} {fa.get('pattern_and_figures', '')}".lower()
        base = [
            "generic fabric",
            "solid color",
            "flat texture",
            "loss of weave pattern",
            "melted textures",
            "oversized macro weave",
            "leftover old fabric on casco",
            "leftover old upholstery color",
            "mismatched casco and cushions",
            "color shift",
            "altered geometry",
            "perspective distortion",
        ]
        if cls._is_patterned_fabric(fa, fabric_label):
            base.extend([
                "erased pattern",
                "missing fabric figures",
                "simplified motif",
                "plain unpatterned substitute",
            ])
        if not any(w in combined for w in ("suede", "gamuza")):
            base.append("suede")
        if not any(w in combined for w in ("velvet", "terciopelo", "pana", "corduroy")):
            base.append("velvet")
        if not any(w in combined for w in ("leather", "piel", "cuero", "nubuck")):
            base.append("leather")
        return ", ".join(base)

    def _build_fabric_spec_blocks(
        self,
        fa: Optional[Dict[str, Any]],
        fabric_label: str,
        src_ref: str,
        protect_non_upholstered_from: str = "",
    ) -> Tuple[str, str]:
        """Construye las directivas quirúrgicas V1+V7 para replicar figuras, colores y texturas de la tela al 100%."""
        fa = fa or {}
        f_name = fa.get("name") or fabric_label or "Selected Fabric Swatch"
        f_color = fa.get("color_description") or f"exact hue, undertones, and multi-tone yarn threads directly from {src_ref}"
        f_tex = fa.get("texture_detail") or "dense realistic woven upholstery yarn structure"
        f_light = fa.get("light_interaction") or "soft matte textile sheen"
        f_pattern = str(fa.get("pattern_and_figures") or "").strip()
        has_pat = self._is_patterned_fabric(fa, fabric_label)

        if has_pat:
            pat_detail = f_pattern or f"exact figures, motifs, stripes, checks, or jacquard drawings visible in {src_ref}"
            pattern_ais = (
                f"1:1 FIGURES, MOTIFS & PATTERN REPLICATION: {src_ref} contains visible figures/patterns ({pat_detail}). "
                f"Copy with surgical fidelity EVERY figure, motif shape, stripe, check, herringbone, or jacquard drawing from {src_ref}, "
                "preserving exact figure-to-ground color contrast, motif proportions, repeat spacing, and natural directional alignment wrapping smoothly around cushion curves, seams, and armrests — "
                "NEVER erase, simplify, blur, or replace the figures with a plain solid cloth. "
            )
            pattern_dal = f"exact 1:1 figures/motifs ({pat_detail}), "
        else:
            pattern_ais = (
                f"EXACT SURFACE & THREAD FIDELITY: Inspect {src_ref} pixel-by-pixel as the single visual truth — if any subtle stripe, herringbone, jacquard figure, or directional rib appears in {src_ref}, replicate it 100%; "
                "otherwise keep it free of invented prints while faithfully reproducing every multi-tone yarn fleck, slub, and interlocking thread. "
            )
            pattern_dal = ""

        protect_tail = (
            f" Strictly protect all non-upholstered parts (exposed wooden legs, wooden plinths/frames, metal hardware, glass, stone) identical to {protect_non_upholstered_from}."
            if protect_non_upholstered_from
            else " Strictly protect all non-upholstered parts (exposed wooden legs, wooden plinths/frames, metal hardware, glass, stone)."
        )

        ais_txt = (
            f"Treat {src_ref} ('{f_name}') as the absolute single truth for upholstery figures, color, and texture. "
            f"First, meticulously analyze the source fabric swatch in {src_ref} ({f_name} — Colors: {f_color}; Weave/Relief: {f_tex}; Sheen: {f_light}"
            f"{'; Figures/Pattern: ' + f_pattern if f_pattern else ''}). "
            f"{pattern_ais}"
            f"COLOR & UNDERTONE LOCK (0% DRIFT): Maintain the exact original color palette ({f_color}) from {src_ref} with 0% color/hue shift, no warming, no cooling, no desaturation, and 0% color bleed from the old furniture upholstery. "
            f"FULL CASCO & CUSHIONS UNIFORMITY: Apply this exact fabric uniformly across 100% of the upholstered body shell "
            f"(EL CASCO COMPLETO: outer & inner backrest, armrests/descansabrazos, upholstered lower base rail/faldón, side panels, headboard/rails if bed) "
            f"AND all upholstered seat/back cushions, following original seams, piping/welting, pleats, and taut folds (NEVER leaving any part of the casco in the old fabric). "
            f"CRITICAL SCALING CONSTRAINT (~97% macro reduction): Because {src_ref} is a close-up swatch photo, scale down this close-up macro zoom dramatically (approx. 97% reduction) "
            f"to true real-world furniture viewing distance, explicitly retaining crisp micro-thread weave ({f_tex}), tactile yarn depth, and clear pattern/figure legibility without turning into a flat solid color, plastic paint, or oversized macro loops.{protect_tail}"
        )

        dal_txt = (
            f"100% of the upholstered body shell (EL CASCO COMPLETO: backrest, armrests, upholstered base rail/sides) AND all cushions reupholstered uniformly in "
            f"{f_name} ({pattern_dal}colors: {f_color}; 3D weave: {f_tex}; sheen: {f_light}) using {src_ref} as the absolute single visual truth "
            "with approx. 97% close-up-to-furniture scale calibration, 0% color shift, 0% old-fabric color bleed, and crisp micro-thread/figure definition (never flat solid paint)"
        )
        return ais_txt, dal_txt

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
        primary_furn_file: str = "",
        wood_file: str = "",
        fabric_file: str = "",
    ) -> Tuple[str, str]:
        """Devuelve (bloque_para_AI_Studio, bloque_para_DALLE)."""
        ais_parts: List[str] = []
        dal_parts: List[str] = []
        furn_ref = f'Image 1 ("{primary_furn_file}")' if primary_furn_file else "Image 1"

        if has_wood:
            w_name = wa.get("name") or "Selected Wood Sample"
            w_color = wa.get("color_description") or "warm natural timber tone from the wood sample"
            w_tex = wa.get("texture_detail") or "fine continuous wood grain pores"
            w_light = wa.get("light_interaction") or "soft satin-matte timber sheen"
            src_base = f"Image {wood_idx}" if wood_idx else "the wood sample"
            src = f'{src_base} ("{wood_file}")' if wood_file else src_base
            ais_parts.append(
                f"- MONOLITHIC WOOD FINISH LOCK (from {src} — '{w_name}'): Apply this exact timber species, {w_color}, "
                f"{w_tex}, and {w_light} uniformly across all wooden parts ({profile['parts_str']}). "
                "Ensure natural anatomical grain flow (vertical on legs, horizontal on rails); zero unintended two-tone contrast or bleached patches."
            )
            dal_parts.append(
                f"Wooden components ({profile['parts_str']}) finished monolithically in {w_name} ({w_color}, {w_tex}, {w_light}) matching {src}."
            )
        elif has_fabric:
            # Crítico: cuando hay muestra de tela nueva, prohibir arrastrar el color/tapiz viejo de Image 1
            ais_parts.append(
                f"- NON-UPHOLSTERED PARTS PRESERVATION & 100% OLD-FABRIC ERASURE (from {furn_ref}): "
                f"Preserve ONLY the non-upholstered structural components (exposed wooden legs, wooden plinths/frames, metal hardware, glass, or stone) strictly identical to {furn_ref}. "
                f"Completely DISCARD and OVERWRITE 100% of the old upholstery color, pattern, and fabric from {furn_ref} — allow ZERO color bleed or tint carry-over from the old fabric."
            )
            dal_parts.append(
                f"All non-upholstered structural parts (exposed wooden legs/frames, metal, glass, stone) preserved strictly identical to {furn_ref}, while 100% of the old upholstery color/fabric from {furn_ref} is completely discarded and replaced."
            )
        else:
            ais_parts.append(
                f"- ORIGINAL WOOD / SURFACE PRESERVATION (from {furn_ref}): Faithfully preserve the authentic surface materials, "
                f"dual-tones, stone/metal/wood contrast, and color saturation of '{furn_item}' ({existing_mats}) without artificial uniformization."
            )
            dal_parts.append(
                f"Faithfully preserve all authentic materials, finishes, and natural contrasts directly from {furn_ref} ({existing_mats})."
            )

        if has_fabric:
            clean_fab_lbl = os.path.splitext(fabric_file)[0].replace("_", " ").strip()
            f_name = fa.get("name") or clean_fab_lbl or "Selected Fabric Swatch"
            src_base = f"Image {fabric_idx}" if fabric_idx else "the fabric swatch"
            src = f'{src_base} ("{fabric_file}")' if fabric_file else src_base
            fab_ais, fab_dal = self._build_fabric_spec_blocks(
                fa=fa,
                fabric_label=f_name,
                src_ref=src,
                protect_non_upholstered_from="" if has_wood else furn_ref,
            )
            ais_parts.append(f"- FULL CASCO & CUSHIONS FABRIC TEXTURE LOCK (V1+V7 from {src} — '{f_name}'): {fab_ais}")
            dal_parts.append(f"{fab_dal}.")
        elif not has_wood:
            pass
        else:
            ais_parts.append(
                f"- NON-WOOD / UPHOLSTERY PRESERVATION (from {furn_ref}): Keep any fabric, cushions, metal, stone, or glass strictly identical to {furn_ref}."
            )
            dal_parts.append(f"All non-wooden surfaces (upholstery, cushions, metal, stone, glass) remain strictly identical to {furn_ref}.")

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
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
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
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            wood_filename=wood_filename,
            fabric_filename=fabric_filename,
        )
        primary_furn_file = slots["primary_furn_file"]
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
            primary_furn_file=primary_furn_file,
            wood_file=slots["wood_file"],
            fabric_file=slots["fabric_file"],
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
            f'TASK: Generate ONE standalone high-resolution commercial catalog photograph of \'{furn_item}\' (\'{furniture_name}\'), '
            f'taking the furniture piece from Image 1 ("{primary_furn_file}"), from the exact requested camera perspective.\n\n'
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
            f'Standalone 8K commercial catalog photograph of a single {furn_item} (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}").\n'
            f"{slots['dal_photo_map']}\n"
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
        furniture_filenames: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        raw_furn = [str(x).strip() for x in (furniture_filenames or []) if str(x or "").strip()]
        primary_furn_file = self._canonical_photo_filename(
            raw_furn[0] if raw_furn else (furniture_name or furn_item or "mueble.png"),
            "mueble.png",
        )
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
            f'TASK: Generate a pure, crisp minimalist black-and-white isometric technical CAD line drawing with dimension arrows '
            f'of the EXACT \'{furn_item}\' (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}").\n\n'
            "ATTACHED REFERENCE:\n"
            f'- Image 1 (PRIMARY FURNITURE REFERENCE · FILE: "{primary_furn_file}"): Take the furniture photo "{primary_furn_file}" whose exact 3D silhouette, proportions, and details must be drawn as clean technical line art.\n\n'
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
            f'Minimalist black-and-white technical isometric CAD blueprint line drawing of the {furn_item} (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}").\n'
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
            "attachment_guide": [f'Image 1: Foto original del mueble ("{primary_furn_file}")'],
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
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
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
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            wood_filename=wood_filename,
            fabric_filename=fabric_filename,
        )
        primary_furn_file = slots["primary_furn_file"]
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
            primary_furn_file=primary_furn_file,
            wood_file=slots["wood_file"],
            fabric_file=slots["fabric_file"],
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
            f'TASK: Photograph \'{furn_item}\' (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}"), placed authentically {room_intro}, '
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
            f'Wide-angle distant architectural interior photograph of a luxury client residence ({room_intro}), featuring the exact {furn_item} (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}").\n'
            f"{slots['dal_photo_map']}\n"
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
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
    ) -> Dict[str, Any]:
        _ = classic_numbering
        has_wood = material_mode in ("wood_only", "dual")
        has_fabric = material_mode in ("fabric_only", "dual")

        raw_furn_list = [str(x).strip() for x in (furniture_filenames or []) if str(x or "").strip()]
        if not raw_furn_list:
            raw_furn_list = [furniture_name or furn_item or "mueble.png"]
        furn_files = [self._canonical_photo_filename(fn, f"mueble_{i + 1}.png") for i, fn in enumerate(raw_furn_list)]
        primary_furn_file = furn_files[0]
        fabric_file = self._canonical_photo_filename(fabric_filename or fabric_label, "tela.png") if has_fabric else ""
        wood_file = self._canonical_photo_filename(wood_filename or wood_label, "madera.png") if has_wood else ""

        # Orden probado de V1: primero las muestras macro (Tela / Madera) y al final el mueble objetivo
        slot_lines: List[str] = []
        guide: List[str] = []
        dal_parts: List[str] = []
        idx = 1
        fabric_idx: Optional[int] = None
        wood_idx: Optional[int] = None

        if has_fabric:
            fabric_idx = idx
            slot_lines.append(
                f'- Image {fabric_idx} (FABRIC SWATCH GROUND TRUTH · FILE: "{fabric_file}"): '
                f'Absolute 1:1 pixel truth for upholstery — copy exact figures/patterns, exact thread colors/undertones, and 3D textile weave strictly from photo "{fabric_file}" ({fabric_label}).'
            )
            guide.append(f'Image {fabric_idx}: Muestra de tela ("{fabric_file}")')
            dal_parts.append(f'Image {fabric_idx} = "{fabric_file}" (fabric swatch — single truth for figures, color & weave)')
            idx += 1
        if has_wood:
            wood_idx = idx
            slot_lines.append(
                f'- Image {wood_idx} (WOOD SAMPLE GROUND TRUTH · FILE: "{wood_file}"): '
                f'Take exact wood species, continuous grain flow, and stain tone strictly from photo "{wood_file}" ({wood_label}).'
            )
            guide.append(f'Image {wood_idx}: Muestra de madera ("{wood_file}")')
            dal_parts.append(f'Image {wood_idx} = "{wood_file}" (wood sample)')
            idx += 1

        furn_idx = idx
        slot_lines.append(
            f'- Image {furn_idx} (TARGET FURNITURE PIECE · FILE: "{primary_furn_file}"): '
            f'Take ONLY the 3D silhouette, proportions, seams, folds, and camera angle of \'{furn_item}\' (\'{furniture_name}\') from photo "{primary_furn_file}" (completely overwrite its old replaced material/color).'
        )
        guide.append(f'Image {furn_idx}: Foto original del mueble ("{primary_furn_file}")')
        dal_parts.append(f'Image {furn_idx} = "{primary_furn_file}" (target furniture piece)')
        idx += 1

        for extra_file in furn_files[1:]:
            slot_lines.append(
                f'- Image {idx} (ADDITIONAL FURNITURE ANGLE · FILE: "{extra_file}"): '
                f'Supplementary reference angle of the target furniture from photo "{extra_file}".'
            )
            guide.append(f'Image {idx}: Vista adicional del mueble ("{extra_file}")')
            dal_parts.append(f'Image {idx} = "{extra_file}" (extra furniture angle)')
            idx += 1

        match_rule = (
            "PHOTO IDENTIFICATION RULE: Match every attached image by its exact copied file name above "
            "(or by attachment order Image 1, Image 2, ... if pasted from clipboard); NEVER confuse which photo is the target furniture vs a material swatch."
        )
        header_block = "ATTACHED IMAGES:\n" + "\n".join(slot_lines) + "\n" + match_rule
        dal_photo_map = "Attached Photos Map (identify by exact copied filename or order): " + " | ".join(dal_parts) + "."

        f_name = fa.get("name") or fabric_label or "Selected Fabric Swatch"
        f_color = fa.get("color_description") or "true-to-life chromatic profile, undertones, and flecks from sample"
        f_texture = fa.get("texture_detail") or "dense textured loops and realistic yarn weave"
        f_light = fa.get("light_interaction") or "soft matte textile sheen"
        f_pattern = str(fa.get("pattern_and_figures") or "").strip()

        w_name = wa.get("name") or wood_label or "Selected Wood Sample"
        w_color = wa.get("color_description") or "natural timber tone from sample"
        w_texture = wa.get("texture_detail") or "natural anatomical wood grain flow"
        w_light = wa.get("light_interaction") or "soft satin-matte timber sheen"

        furn_ref = f'Image {furn_idx} ("{primary_furn_file}")'
        fab_ref = f'Image {fabric_idx} ("{fabric_file}")' if fabric_idx else ""
        wood_ref = f'Image {wood_idx} ("{wood_file}")' if wood_idx else ""

        cam_lock = (camera_angle or "").strip() or "the exact same camera angle and framing as the original photo"
        dim_line = f" SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        mirror_line = f" {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        notes_ais = f"\n\nUSER SPECIAL DIRECTIVES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" Mandatory user directives: {user_notes_clean}." if user_notes_clean else ""

        if white_bg_enabled:
            scene_str = (
                f"Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, seams, piping, folds, and proportions of the furniture in {furn_ref}. "
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
                f"Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, seams, piping, folds, lighting, shadows, and surrounding background of {furn_ref}. "
                f"{profile['geometry_rule']}{dim_line}{mirror_line} "
                f"CAMERA CONSTRAINT: You MUST lock the camera to {cam_lock}. Do not alter the room or the furniture's physical design."
            )
            bg_neg = "changed background, altered environment, changed camera angle, top-down view,"
            bg_dal = "keep the original scene lighting, shadows, and background intact"

        fab_neg = self._fabric_negative_terms(fa, fabric_label)
        pat_summary = f"; Figures/Pattern: {f_pattern}" if f_pattern else ""

        if material_mode == "dual":
            fab_spec_ais, fab_spec_dal = self._build_fabric_spec_blocks(
                fa=fa,
                fabric_label=fabric_label,
                src_ref=fab_ref,
                protect_non_upholstered_from="",
            )
            prompt_ais = (
                f"INSTRUCTION: First, meticulously analyze the source fabric swatch in {fab_ref} ({f_name}: {f_color}; {f_texture}; {f_light}{pat_summary}), "
                f"the source wood sample in {wood_ref} ({w_name}: {w_color}; {w_texture}; {w_light}), "
                f"and the target furniture piece in {furn_ref} ('{furn_item}').\n\n"
                f"{header_block}\n\n"
                f"GENERATE: Completely discard the old upholstery fabric/color and old wood finish of {furn_ref}, and accurately replace BOTH 100% of the fabric upholstery "
                f"AND all wooden components using the exact visual truth from {fab_ref} and {wood_ref}.\n\n"
                f"GEOMETRY & SCENE CONSTRAINT: {scene_str}\n\n"
                f"FABRIC, FIGURES & CASCO CONSTRAINT (FULL CASCO + CUSHIONS · 97% MACRO REDUCTION): {fab_spec_ais}\n\n"
                f"WOOD CONSTRAINT: Apply the precise wood grain flow, pores, finish ({w_light}), and color ({w_color}) from {wood_ref} monolithically to all legs, frames, and wooden bases. "
                f"Ensure the grain follows the natural anatomical direction (vertical on legs, horizontal on rails) with zero unintended two-tone contrast.{notes_ais}\n\n"
                f"Negative Prompt:\n"
                f"{fab_neg}, flat wood colors, bleached patches, text, watermark, poster, collage, infographic, multiple furniture pieces, {bg_neg}{profile['neg_add']}"
            )
            mat_dal = (
                f"{fab_spec_dal}; "
                f"all wooden parts finished monolithically in {w_name} ({w_color}; {w_texture}; {w_light}) from {wood_ref}."
            )
        elif material_mode == "fabric_only":
            fab_spec_ais, fab_spec_dal = self._build_fabric_spec_blocks(
                fa=fa,
                fabric_label=fabric_label,
                src_ref=fab_ref,
                protect_non_upholstered_from=furn_ref,
            )
            prompt_ais = (
                f"INSTRUCTION: First, meticulously analyze the source fabric macro texture, colors, and figures in {fab_ref} ({f_name}: {f_color}; {f_texture}; {f_light}{pat_summary}) "
                f"and the target furniture piece in {furn_ref} ('{furn_item}').\n\n"
                f"{header_block}\n\n"
                f"GENERATE: Completely discard 100% of the old upholstery color and fabric on {furn_ref}, and accurately reupholster the furniture piece in {furn_ref} "
                f"using the exact figures/patterns, colors, and 3D textile weave analyzed from {fab_ref}.\n\n"
                f"GEOMETRY & SCENE CONSTRAINT: {scene_str}\n\n"
                f"MATERIAL, FIGURES & SCALING CONSTRAINT (FULL CASCO + CUSHIONS · 97% MACRO REDUCTION): {fab_spec_ais}{notes_ais}\n\n"
                f"Negative Prompt:\n"
                f"{fab_neg}, altered wood legs, changed wood color, text, watermark, poster, collage, infographic, multiple furniture pieces, {bg_neg}{profile['neg_add']}"
            )
            mat_dal = (
                f"{fab_spec_dal}; "
                f"all exposed wooden legs, frames, and metal parts preserved strictly identical to {furn_ref}."
            )
        else:  # wood_only
            prompt_ais = (
                f"INSTRUCTION: First, meticulously analyze the source wood macro texture in {wood_ref} ({w_name}: {w_color}; {w_texture}; {w_light}) "
                f"and the target furniture piece in {furn_ref} ('{furn_item}').\n\n"
                f"{header_block}\n\n"
                f"GENERATE: Accurately replace ONLY the wooden components ({profile['parts_str']}) of the furniture in {furn_ref} "
                f"using the exact wood grain, finish, and tone analyzed from {wood_ref}.\n\n"
                f"GEOMETRY & SCENE CONSTRAINT: {scene_str}\n\n"
                f"MATERIAL CONSTRAINT: Apply the precise wood grain flow, pores, finish ({w_light}), and color ({w_color}) from {wood_ref} monolithically. "
                f"Ensure the grain follows the natural anatomical direction of the furniture parts (vertical on legs, horizontal on rails) with zero two-tone contrast or bleached patches. "
                f"Keep any upholstery, cushions, metal, stone, or glass strictly identical to {furn_ref}.{notes_ais}\n\n"
                f"Negative Prompt:\n"
                f"altered fabric, changed upholstery, color shift, flat colors, two-tone wood mismatch, changed geometry, text, watermark, {bg_neg}{profile['neg_add']}"
            )
            mat_dal = (
                f"Wooden components ({profile['parts_str']}) finished monolithically in {w_name} ({w_color}; {w_texture}; {w_light}) matching {wood_ref}; "
                f"all non-wooden surfaces preserved identical to {furn_ref}."
            )

        prompt_dal = (
            f"Precision material-swap product photograph of the exact {furn_item} ('{furniture_name}') taken from {furn_ref} (do NOT redesign geometry or camera angle: {cam_lock}).\n"
            f"{dal_photo_map}\n"
            f"Materials: {mat_dal}\n"
            f"Structure & Folds: Preserve exact contours, seams, piping, and folds. {profile['geometry_rule']} {profile['dimensions_rule']}{notes_dal}\n"
            f"Background: {bg_dal}.\n"
            f"Avoid: {fab_neg if has_fabric else 'flat colors, altered upholstery'}, altered geometry, perspective distortion, text, watermark{profile['neg_add']}."
        )

        mj_neg = f"{fab_neg}, text, watermark" if has_fabric else "altered upholstery, flat colors, altered geometry, text, watermark"
        prompt_mj = (
            f"Commercial catalog photography of {furn_item}, {geom_struct}, {mat_dal}, "
            f"{'pure solid white background #FFFFFF, zero shadows, ' if white_bg_enabled else ''}"
            f"--ar 1:1 --v 6.1 --style raw --no {mj_neg}"
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
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
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
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            wood_filename=wood_filename,
            fabric_filename=fabric_filename,
        )
        primary_furn_file = slots["primary_furn_file"]
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
            primary_furn_file=primary_furn_file,
            wood_file=slots["wood_file"],
            fabric_file=slots["fabric_file"],
        )
        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""

        prompt_ais = (
            "[ISOLATED COMMERCIAL PRODUCT CUTOUT · PURE WHITE #FFFFFF]\n"
            f'TASK: Cleanly extract and isolate \'{furn_item}\' (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}") onto a pure solid white background (#FFFFFF).\n\n'
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
            f'Clean commercial e-commerce cutout of the exact {furn_item} (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}"), '
            "centered on a pure seamless solid white background (#FFFFFF) with 0% ground shadows, 0% drop shadows, and 0% reflections.\n"
            f"{slots['dal_photo_map']}\n"
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
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
        is_material_swatch: bool = False,
    ) -> Dict[str, Any]:
        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""

        if is_material_swatch:
            raw_furn = [str(x).strip() for x in (furniture_filenames or []) if str(x or "").strip()]
            primary_furn_file = self._canonical_photo_filename(
                raw_furn[0] if raw_furn else (furniture_name or "muestra.png"),
                "muestra.png",
            )
            swatch_desc = (
                furn_item
                if furn_item and "exact subject" not in furn_item.lower()
                else "flat close-up material / textile texture swatch"
            )
            mat_desc = existing_mats or "authentic woven fibers, threads, grain, and color undertones from Image 1"

            prompt_ais = (
                "[8K ULTRA-HD MACRO SWATCH & TEXTURE SUPER-RESOLUTION · STRICT 1:1 IMAGE LOCK]\n"
                f'TASK: Upscale and remaster the EXACT flat material / surface swatch shown in Image 1 ("{primary_furn_file}") '
                f"('{furniture_name}' — {swatch_desc}) into razor-sharp 8K macro photographic clarity, preserving 100% of its "
                "full-bleed framing, weave/grain structure, and exact color tones.\n\n"
                "ATTACHED SOURCE IMAGE:\n"
                f'- Image 1 (SOURCE MATERIAL SWATCH · FILE: "{primary_furn_file}"): Exact flat surface/textile/material sample '
                f'("{primary_furn_file}") to deblur and upscale 1:1.\n\n'
                "CRITICAL ANTI-HALLUCINATION LOCK (DO NOT INVENT FURNITURE):\n"
                "- FLAT 2D SWATCH ONLY: Image 1 is a flat close-up material/texture sample, NOT a 3D piece of furniture.\n"
                "- STRICTLY FORBIDDEN: Do NOT generate, invent, or render any chair, armchair, sofa, table, bed, cushion, "
                "wooden frame, joinery, legs, 3D object, room scene, or white studio border (#FFFFFF).\n"
                "- FULL-BLEED 1:1 FRAMING: Keep the flat surface texture filling 100% of the canvas from edge to edge at the exact "
                "same zoom scale, camera angle, and thread/grain alignment as Image 1.\n\n"
                "8K MACRO CLARITY & COLOR FIDELITY:\n"
                "- ELIMINATE ARTIFACTS: Completely remove pixelation, low-resolution screenshot blur, compression blocks, and digital noise.\n"
                f"- MICRO-TEXTURE RECONSTRUCTION: Restore crisp individual woven yarn threads, micro-fibers, pores, or natural grain relief ({mat_desc}) "
                "at tack-sharp f/11 macro focus without plastic smoothing or artificial sharpening halos.\n"
                "- ZERO COLOR DRIFT: Preserve the 100% exact original hue, warmth, brightness, and subtle multi-tone thread/grain flecks "
                f"visible in Image 1 with 0% tint shift.{notes_ais}\n\n"
                "Exclude: furniture, chair, armchair, sofa, table, cushions, wooden frame, joinery, legs, 3D object, room background, "
                "white border, studio backdrop, drop shadow, blur, pixelation, jpeg artifacts, plastic smoothing, color shift, text, watermark."
            )

            prompt_dal = (
                f'8K Ultra-HD 1:1 macro super-resolution remaster of the exact flat material/textile swatch in Image 1 ("{primary_furn_file}" · \'{furniture_name}\').\n'
                f'Attached Source: Image 1 = "{primary_furn_file}" (flat full-bleed surface swatch — NOT a piece of furniture).\n'
                "CRITICAL RULE: Do NOT generate or invent any chair, armchair, sofa, table, cushion, wooden frame, legs, 3D object, or white studio background. "
                "Keep the flat texture filling 100% of the frame from edge to edge exactly like Image 1.\n"
                f"Remove all blur, pixelation, and screenshot compression while reconstructing crisp 8K micro-fibers/grain ({mat_desc}) with 0% color or warmth shift.\n"
                f"{'User directives: ' + user_notes_clean if user_notes_clean else ''}\n"
                "Avoid: furniture, chair, sofa, wooden frame, 3d object, white border, blur, pixelation, color shift, text, watermark."
            )

            prompt_mj = (
                f"8k ultra-sharp macro top-down flat full-bleed texture remaster of {swatch_desc}, {mat_desc}, "
                "edge-to-edge flat surface sample, tack-sharp micro fibers and weave, f/11 macro 100MP --ar 1:1 --v 6.1 --style raw "
                "--no furniture, chair, armchair, sofa, table, wooden frame, legs, cushions, white background, room, blur, pixelated, color shift"
            )

            return {
                "id": "hd",
                "label": "✨ Mejora HD 8K",
                "short_name": "Mejora HD",
                "icon": "✨",
                "google_ai_studio": prompt_ais,
                "chatgpt_dalle3": prompt_dal,
                "midjourney_v6": prompt_mj,
                "checklist": [
                    "¿Se conservó como muestra/textura plana de borde a borde SIN inventar ningún mueble ni margen blanco?",
                    "¿Aumentó la nitidez real del tejido o veta a 8K eliminando el pixelado/borrosidad?",
                    "¿Se mantuvo exactamente el mismo tono, calidez y escala del tramado original?",
                ],
                "needs_anchor": False,
                "attachment_guide": [f'Image 1: Muestra / textura original a mejorar en 8K ("{primary_furn_file}")'],
            }

        slots = self._build_image_slots(
            furn_item=furn_item,
            has_wood=has_wood,
            wood_label=wood_label,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            has_ref=False,
            include_anchor=False,
            classic_numbering=classic_numbering,
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            wood_filename=wood_filename,
            fabric_filename=fabric_filename,
        )
        primary_furn_file = slots["primary_furn_file"]
        if has_wood or has_fabric:
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
                primary_furn_file=primary_furn_file,
                wood_file=slots["wood_file"],
                fabric_file=slots["fabric_file"],
            )
        else:
            mat_ais = (
                f'- ORIGINAL SURFACE & MATERIAL LOCK (from Image 1 ("{primary_furn_file}")): Faithfully preserve ONLY the exact '
                f"authentic materials, textures, colors, and surface finishes actually visible in Image 1 ({existing_mats}) "
                "with 0% color/hue shift and without inventing wood, stone, or metal parts that are not present."
            )
            mat_dal = (
                f'Faithfully preserve ONLY the exact authentic materials, textures, and color tones visible in Image 1 ("{primary_furn_file}") ({existing_mats}).'
            )

        bg_line = (
            "Pure seamless solid white catalog studio background (#FFFFFF) with zero drop shadows."
            if white_bg_enabled
            else (
                f'Preserve the exact original background, scene lighting, and framing from Image 1 ("{primary_furn_file}") '
                "(if Image 1 already has a white studio background, keep pure solid #FFFFFF; otherwise preserve its exact original "
                "background and framing without replacing or cropping it) while upgrading sharpness to 8K."
            )
        )
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""

        prompt_ais = (
            "[8K ULTRA-HD COMMERCIAL RESTORATION · ZERO COLOR OR GEOMETRY DRIFT]\n"
            f'TASK: Remaster \'{furn_item}\' (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}") into ultra-sharp 8K medium-format clarity '
            "without altering color, tone, material identity, framing, or silhouette.\n\n"
            f"{slots['header_block']}\n\n"
            "CLARITY & RESTORATION:\n"
            "- ELIMINATE ARTIFACTS: Remove pixelation, blur, compression noise, and softness completely.\n"
            "- MACRO TEXTURE: Sharpen only the authentic surface micro-textures actually visible in Image 1 "
            "(textile weave threads, seam stitching, wood grain pores, or smooth surfaces) naturally without plastic smoothing or inventing materials.\n"
            "- FOCUS STACKING: Deep f/11 edge-to-edge sharpness from foreground edge to rear contours.\n\n"
            "STRICT PRESERVATION LOCK:\n"
            f'- STRICT 1:1 SUBJECT LOCK: Enhance ONLY what actually exists inside Image 1 ("{primary_furn_file}"). '
            "NEVER invent, add, or substitute furniture frames, wooden legs, joinery, cushions, or props that are not visible in Image 1.\n"
            f"{mat_ais}\n"
            f"- GEOMETRY LOCK: {profile['geometry_rule']}{dim_ais}{mirror_ais}{notes_ais}\n"
            f"- BACKGROUND: {bg_line}\n\n"
            f"Exclude: blurry, pixelated, jpeg artifacts, plastic smoothing, color shift, hue change, redesigned silhouette, invented furniture parts, CGI look, text, watermark{profile['neg_add']}."
        )

        prompt_dal = (
            f'8K Ultra-HD 1:1 photographic remaster of the exact {furn_item} (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}").\n'
            f"{slots['dal_photo_map']}\n"
            "Enhance ONLY what actually exists inside Image 1 — NEVER invent new furniture frames, legs, joinery, or objects. "
            "Remove all blur, pixelation, and compression artifacts while preserving 100% identical color, warmth, surface micro-texture, and geometry.\n"
            f"Materials: {mat_dal}\n"
            f"Geometry: {profile['geometry_rule']} {profile['dimensions_rule']}\n"
            f"Environment: {bg_line}\n"
            f"{'User directives: ' + user_notes_clean if user_notes_clean else ''}\n"
            "Avoid: blur, compression noise, color shift, plastic smoothing, redesigned shape, invented furniture parts, text, watermark."
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
        ref_filename: str = "",
        fabric_analysis: Optional[Dict[str, Any]] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, str]:
        fa = fabric_analysis or {}
        view_file = self._canonical_photo_filename(view_name, "vista.png")
        ref_file = self._canonical_photo_filename(
            ref_filename or ref_label,
            "tela.png" if batch_mode == "vistas_tela" else "referencia_color.png",
        )
        bg_clause = (
            "pure seamless solid white background (#FFFFFF) with 0% ground shadows, 0% drop shadows, and 0% floor reflections"
            if white_bg_enabled
            else f'the exact original background and natural lighting of Image 2 ("{view_file}")'
        )
        notes_part = f"\n- MANDATORY NOTES: {user_notes_clean}" if user_notes_clean else ""
        dims_part = f"\n- REAL-WORLD SCALE: {medidas_texto}" if medidas_texto else ""

        match_rule = (
            "PHOTO IDENTIFICATION RULE: Match every attached image by its exact copied file name above "
            "(or by attachment order Image 1, Image 2 if pasted from clipboard); NEVER swap Image 1 and Image 2."
        )

        if batch_mode == "vistas_tela":
            f_name = fa.get("name") or ref_label or "Fabric Swatch"
            f_color = fa.get("color_description") or f'exact hue, undertones, and multi-tone flecks from Image 1 ("{ref_file}")'
            f_tex = fa.get("texture_detail") or "dense realistic woven upholstery fibers and loops"
            f_light = fa.get("light_interaction") or "soft matte textile sheen"
            f_pattern = str(fa.get("pattern_and_figures") or "").strip()
            pat_summary = f"; Figures/Pattern: {f_pattern}" if f_pattern else ""
            fab_neg = self._fabric_negative_terms(fa, ref_label)

            view_cam = "the exact same camera angle and framing as Image 2"
            view_geom = "the exact 3D silhouette, contours, seams, piping, and folds"
            key = self.get_api_key(api_key)
            if key and view_bytes and len(view_bytes) >= 64:
                try:
                    v_ana = self.analyze_furniture_for_enhancement(view_bytes, api_key=key)
                    if v_ana.get("camera_angle") and "reference angle" not in str(v_ana.get("camera_angle", "")).lower():
                        view_cam = str(v_ana["camera_angle"]).strip()
                    if v_ana.get("geometric_structure") and "attached photo" not in str(v_ana.get("geometric_structure", "")).lower():
                        view_geom = str(v_ana["geometric_structure"]).strip()
                except Exception as e_va:
                    print(f"[AIPromptServiceV7] Aviso analizando ángulo de vista lote: {e_va}")

            batch_header = (
                "ATTACHED IMAGES:\n"
                f'- Image 1 (FABRIC SWATCH GROUND TRUTH · FILE: "{ref_file}"): Absolute 1:1 pixel truth for upholstery — copy exact figures/patterns, exact thread colors/undertones, and 3D textile weave strictly from photo "{ref_file}" ({f_name}).\n'
                f'- Image 2 (TARGET VIEW · FILE: "{view_file}"): Take ONLY the camera angle ({view_cam}), 3D silhouette ({view_geom}), proportions, seams, piping, folds, and non-upholstered wood/metal parts from photo "{view_file}" (completely overwrite its old upholstery fabric/color).\n'
                f"{match_rule}"
            )
            fab_spec_ais, fab_spec_dal = self._build_fabric_spec_blocks(
                fa=fa,
                fabric_label=ref_label or f_name,
                src_ref=f'Image 1 ("{ref_file}")',
                protect_non_upholstered_from=f'Image 2 ("{view_file}")',
            )

            local_ais = (
                f'INSTRUCTION: First, meticulously analyze the source fabric macro texture, colors, and figures in Image 1 ("{ref_file}" — {f_name}: {f_color}; {f_tex}; {f_light}{pat_summary}) '
                f'and the target furniture view in Image 2 ("{view_file}" — \'{furn_item}\').\n\n'
                f"{batch_header}\n\n"
                f'GENERATE: Completely discard 100% of the old upholstery color and fabric on Image 2 ("{view_file}"), and accurately reupholster the furniture piece in Image 2 ("{view_file}") '
                f'using the exact figures/patterns, colors, and 3D textile weave analyzed from Image 1 ("{ref_file}").\n\n'
                f'GEOMETRY & SCENE CONSTRAINT: Strictly preserve the exact camera angle ({view_cam}), shape ({view_geom}), contours, seams, piping, folds, and non-upholstered wood/metal parts of Image 2 ("{view_file}"). '
                f"ENVIRONMENT: {bg_clause}. Do NOT include text, labels, or watermarks.{dims_part}{notes_part}\n\n"
                f"MATERIAL, FIGURES & SCALING CONSTRAINT (FULL CASCO + CUSHIONS · 97% MACRO REDUCTION): {fab_spec_ais}\n\n"
                f"Negative Prompt:\n{fab_neg}, altered camera angle, altered wood legs, text, watermark, collage."
            )
            local_dal = (
                f'Precision upholstery replacement on target view Image 2 ("{view_file}" — {furn_item}, lock exact camera angle: {view_cam}).\n'
                f'Attached Photos Map: Image 1 = "{ref_file}" (fabric swatch — single truth for figures, color & weave) | Image 2 = "{view_file}" (target view).\n'
                f"Materials: {fab_spec_dal}; preserve exposed wood/metal parts identical to Image 2.\n"
                f"Environment: {bg_clause}.{dims_part}{notes_part}\n"
                f"Avoid: {fab_neg}, altered camera angle, altered wood legs, text, watermark, collage."
            )
            local_mj = (
                f"Commercial product photography of {furn_item}, {view_cam}, {fab_spec_dal}, "
                f"{'pure white background #FFFFFF, zero shadows, ' if white_bg_enabled else ''}"
                f"80mm f/11 --ar 1:1 --v 6.1 --style raw --no {fab_neg}, altered angle, text, watermark"
            )
            return {
                "google_ai_studio": local_ais,
                "chatgpt_dalle3": local_dal,
                "midjourney_v6": local_mj,
            }

        # clonar_color
        batch_header = (
            "ATTACHED IMAGES:\n"
            f'- Image 1 (COLOR & MATERIAL MASTER REFERENCE · FILE: "{ref_file}"): Take exact hue, timber/fabric texture, and sheen strictly from photo "{ref_file}".\n'
            f'- Image 2 (TARGET VIEW TO RECOLOR · FILE: "{view_file}"): Take the target furniture view strictly from photo "{view_file}" — keep its EXACT camera angle, 3D silhouette, joinery, folds, and proportions.\n'
            f"{match_rule}"
        )
        local_ais = (
            f"[BATCH VIEW COLOR & FINISH CLONE · {view_file}]\n"
            f'TASK: Clone the exact color, wood/fabric finish, and surface texture from Image 1 ("{ref_file}") onto the furniture \'{furn_item}\' in Image 2 ("{view_file}").\n\n'
            f"{batch_header}\n\n"
            "RULES:\n"
            f'- Transfer Image 1 ("{ref_file}") exact color tone and surface finish onto Image 2 ("{view_file}") cleanly with 0% hue drift.\n'
            f'- Strictly preserve Image 2 ("{view_file}") camera angle and physical geometry.\n'
            f"- BACKGROUND: {bg_clause}.{dims_part}{notes_part}\n\n"
            "Exclude: repeating Image 1's camera angle, altered silhouette, mismatched tone, text, watermark."
        )
        vision_task = (
            f'Image 1 (FILE: "{ref_file}") is a COLOR & FINISH MASTER REFERENCE (correct color/material). '
            f'Image 2 (FILE: "{view_file}") is a TARGET FURNITURE VIEW (correct camera angle & geometry, wrong color).\n'
            "Write a crisp, production-grade image-generation prompt explicitly naming BOTH exact photo files "
            f'("{ref_file}" for Image 1 and "{view_file}" for Image 2) and commanding the model to keep Image 2\'s EXACT camera angle and 3D geometry '
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
            img1 = self._prepare_image(ref_bytes, max_dim=1024, lossless=True)
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
            if ref_file not in txt or view_file not in txt:
                txt = f"{batch_header}\n\n{txt}"
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
        # Nombres exactos de archivos de fotos copiadas/cargadas:
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
        batch_ref_filename: str = "",
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

        has_wood = bool(wa) or bool(wood_label) or bool(wood_filename)
        has_fabric = bool(fa) or bool(fabric_label) or bool(fabric_filename)
        w_label = wood_label or wood_filename or wa.get("name") or "Muestra de madera"
        f_label = fabric_label or fabric_filename or fa.get("name") or "Muestra de tela"
        w_file_arg = wood_filename or wood_label
        f_file_arg = fabric_filename or fabric_label

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
                            furniture_filenames=furniture_filenames,
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
                            furniture_filenames=furniture_filenames,
                            wood_filename=w_file_arg,
                            fabric_filename=f_file_arg,
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
                            furniture_filenames=furniture_filenames,
                            wood_filename=w_file_arg,
                            fabric_filename=f_file_arg,
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
                furniture_name=furniture_name,
                furniture_filenames=furniture_filenames,
                wood_filename=w_file_arg,
                fabric_filename=f_file_arg,
            )
            primary_furn_file = slots_master["primary_furn_file"]
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
                primary_furn_file=primary_furn_file,
                wood_file=slots_master["wood_file"],
                fabric_file=slots_master["fabric_file"],
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
                f'TASK: Generate a complete 7-piece commercial catalog sequence for \'{furn_item}\' (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}"): '
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
                f'Generate 7 separate standalone commercial images in sequence (do NOT combine into a grid or collage) for \'{furn_item}\' (\'{furniture_name}\') taken from Image 1 ("{primary_furn_file}"):\n'
                f"{slots_master['dal_photo_map']}\n"
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
                it = self._build_blueprint_item(
                    furn_item, furniture_name, profile, medidas_texto, user_notes_clean,
                    furniture_filenames=furniture_filenames,
                )
            elif vista_id == "vista_entorno_cliente":
                it = self._build_environment_item(
                    furn_item, furniture_name, profile, geom_struct, existing_mats,
                    wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                    lugar_casa, user_notes_clean, classic_numbering, use_anchor=True,
                    furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                )
            else:
                it = self._build_single_studio_view_prompt(
                    vista_id, furn_item, furniture_name, profile, geom_struct, existing_mats,
                    wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                    user_notes_clean, white_bg_enabled, classic_numbering,
                    use_anchor=(vista_id in ANCHOR_VIEWS),
                    furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "material":
            it = self._build_material_swap_item(
                material_mode, furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, w_label, f_label, user_notes_clean, white_bg_enabled, classic_numbering,
                camera_angle=ma.get("camera_angle", ""),
                furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "entorno":
            it = self._build_environment_item(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                lugar_casa, user_notes_clean, classic_numbering, use_anchor=False,
                furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "plano":
            it = self._build_blueprint_item(
                furn_item, furniture_name, profile, medidas_texto, user_notes_clean,
                furniture_filenames=furniture_filenames,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "extraer":
            it = self._build_extraction_item(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, w_label, f_label, user_notes_clean, classic_numbering,
                furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "hd":
            explicit_furn_hd = any(
                w in f"{tipo_mueble or ''} {user_notes_clean}".lower()
                for w in self._FURNITURE_KEYWORDS
            )
            explicit_swatch_hd = any(
                w in f"{tipo_mueble or ''} {furniture_name or ''} {user_notes_clean}".lower()
                for w in self._SWATCH_KEYWORDS
            )
            ai_swatch_flag = bool(ma.get("is_material_swatch")) or any(
                t in f"{ma.get('furniture_item', '')} {ma.get('geometric_structure', '')}".lower()
                for t in (
                    "material swatch",
                    "fabric swatch",
                    "texture swatch",
                    "wood sample",
                    "flat full-bleed 2d",
                    "zero 3d furniture",
                )
            )
            is_hd_swatch = (not explicit_furn_hd) and (explicit_swatch_hd or ai_swatch_flag)
            it = self._build_hd_item(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, w_label, f_label,
                user_notes_clean, white_bg_enabled, classic_numbering,
                furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                is_material_swatch=is_hd_swatch,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        else:  # vistas_tela | clonar_color
            views = batch_views or []
            if not views:
                raise ValueError("Sube al menos una vista objetivo para procesar el lote.")
            ref_b = batch_ref_bytes or b""
            ref_lbl = f_label if mode == "vistas_tela" else (batch_ref_filename or (furniture_filenames[0] if furniture_filenames else "") or "Foto referencia color")
            ref_fname = (
                f_file_arg
                if mode == "vistas_tela"
                else (batch_ref_filename or (furniture_filenames[0] if furniture_filenames else "") or furniture_name)
            )
            ref_file_canon = self._canonical_photo_filename(
                ref_fname or ref_lbl,
                "tela.png" if mode == "vistas_tela" else "referencia_color.png",
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
                    ref_filename=ref_file_canon,
                    fabric_analysis=fa if mode == "vistas_tela" else None,
                    api_key=api_key,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                batch_results = list(executor.map(_run, views))

            for idx, (vname, vbytes, pdict) in enumerate(batch_results, start=1):
                v_file_canon = self._canonical_photo_filename(vname, f"vista_{idx}.png")
                item_guide = (
                    [f'Image 1: Muestra de tela ("{ref_file_canon}")', f'Image 2: Vista objetivo ("{v_file_canon}")']
                    if mode == "vistas_tela"
                    else [f'Image 1: Foto base de color/acabado ("{ref_file_canon}")', f'Image 2: Vista objetivo a recolorear ("{v_file_canon}")']
                )
                items.append({
                    "id": f"{mode}_{idx}",
                    "label": f"Vista {idx}: {v_file_canon}",
                    "short_name": f"Vista {idx}",
                    "icon": "🧵" if mode == "vistas_tela" else "🧬",
                    "google_ai_studio": pdict["google_ai_studio"],
                    "chatgpt_dalle3": pdict["chatgpt_dalle3"],
                    "midjourney_v6": pdict["midjourney_v6"],
                    "checklist": CHECKLISTS[mode],
                    "needs_anchor": False,
                    "attachment_guide": item_guide,
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
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
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

        has_wood = bool(wa) or bool(wood_label) or bool(wood_filename)
        has_fabric = bool(fa) or bool(fabric_label) or bool(fabric_filename)
        w_label = wood_label or wood_filename or wa.get("name") or "Muestra de madera"
        f_label = fabric_label or fabric_filename or fa.get("name") or "Muestra de tela"
        w_file_arg = wood_filename or wood_label
        f_file_arg = fabric_filename or fabric_label

        slots = self._build_image_slots(
            furn_item=furn_item,
            has_wood=has_wood,
            wood_label=w_label,
            has_fabric=has_fabric,
            fabric_label=f_label,
            has_ref=has_reference_imgs,
            include_anchor=False,
            classic_numbering=classic_numbering,
            furniture_name=clean_base_name,
            furniture_filenames=furniture_filenames,
            wood_filename=w_file_arg,
            fabric_filename=f_file_arg,
        )
        primary_furn_file = slots["primary_furn_file"]
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
            primary_furn_file=primary_furn_file,
            wood_file=slots["wood_file"],
            fabric_file=slots["fabric_file"],
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
            f'TASK: Generate ONE standalone ultra-sharp commercial catalog photograph of \'{furn_item}\' (\'{clean_base_name}\') taken from Image 1 ("{primary_furn_file}") '
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
            f'Standalone 2054x2054 px (1:1 square) commercial catalog photograph of a single {furn_item} (\'{clean_base_name}\') taken from Image 1 ("{primary_furn_file}").\n'
            f"{slots['dal_photo_map']}\n"
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
                    contents_img.append(self._prepare_image(wood_bytes, max_dim=1024, lossless=True))
                if fabric_bytes:
                    contents_img.append(self._prepare_image(fabric_bytes, max_dim=1024, lossless=True))
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

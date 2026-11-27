"""
Motor de Prompts e Imagen Multimodal V8 · Estudio IA V8.

Extiende las capacidades de V7 sin modificar ninguna línea de V1–V7:
  * Seguridad estricta: lee GEMINI_API_KEY / GOOGLE_API_KEY únicamente de argumento explícito,
    variables de entorno, .env o streamlit.secrets (cero llaves codificadas en código fuente V8).
  * Generación multimodal real: allow_flux_fallback=False por defecto y prioridad a modelos reales
    de imagen Gemini (gemini-2.5-flash-image, gemini-3.1-flash-image-preview, gemini-3-pro-image-preview)
    con guardia de pureza de borde blanco #FFFFFF (5% exterior >= 95%).
  * Análisis policromático V8 pre-calibrado +30%: ejecuta extract_clean_swatch_roi_v8 +
    calibrate_fabric_lightness_v8(boost=0.30) + analyze_fabric_multitone_v8 antes de Vision.
  * Paquete único sincronizado de referencias (build_v8_reference_pack): alinea exactamente
    Image 1..N entre prompts (AI Studio, ChatGPT, Midjourney), attachment_guide, tira 76x76 px y ZIP.
"""

from __future__ import annotations

import base64
import concurrent.futures
import io
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from services.ai_prompt_service_v7 import (
    ALL_SINGLE_VIEWS,
    ANCHOR_VIEWS,
    CHECKLISTS,
    MODES,
    ROOM_PRESETS,
    VIEW_IDS,
    AIPromptServiceV7,
    FurnitureAnalysisV7,
    MaterialAnalysisV7,
    _COMMON_CHECKS,
)
from services.fabric_composer_v8 import (
    V8ConditioningArtifacts,
    _apply_ratio_preserving_rgb_ceiling,
    analyze_fabric_multitone_v8,
    build_v8_conditioning_canvas,
    calibrate_fabric_lightness_v8,
    clean_v8_ai_furniture_item,
    compose_view_with_precomputed_tile_v8,
    compute_v8_tile_px,
    extract_clean_swatch_roi_v8,
    infer_furniture_width_cm_v8,
    make_toroidal_seamless_tile_v8,
    make_v8_canvas_filename,
    make_v8_mosaic_filename,
    make_v8_swatch_filename,
    resolve_v8_furniture_type_hint,
)

CATALOG_7_VIEWS: List[str] = list(VIEW_IDS)
MATERIAL_SUBMODES: Dict[str, str] = {
    "Solo tela": "fabric_only",
    "Solo madera": "wood_only",
    "Tela + madera": "dual",
}

DEFAULT_V8_IMAGE_MODELS: List[str] = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "gemini-nano-banana-2.1",
    "gemini-3-pro-image",
]


class AIPromptServiceV8(AIPromptServiceV7):
    """Servicio multimodal y constructor de prompts de Estudio IA V8 (cero secretos embebidos)."""

    _BUILTIN_KEY_B64 = ""

    def __init__(self) -> None:
        self._builtin_key = ""
        self.default_api_key = ""
        self._clients: Dict[str, Any] = {}
        self._preferred_model: Optional[str] = None
        self._img_quota_exhausted_until: float = 0.0
        self.last_image_error: Optional[str] = None

    def get_api_key(self, custom_key: Optional[str] = None) -> str:
        """
        Obtiene la llave de Gemini exclusivamente desde:
          1) argumento explícito custom_key
          2) variables de entorno GEMINI_API_KEY / GOOGLE_API_KEY
          3) archivo local .env (ignorado en git)
          4) streamlit.secrets
        Jamás utiliza llaves codificadas o hardcodeadas en el código fuente.
        """
        from services.gemini_runtime import is_key_rejected

        if custom_key and custom_key.strip():
            cand = custom_key.strip()
            if not is_key_rejected(cand):
                return cand

        for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            env_val = os.environ.get(env_name, "").strip()
            if env_val and not is_key_rejected(env_val):
                return env_val

        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as ef:
                    for raw_line in ef:
                        line_s = raw_line.strip()
                        if not line_s or line_s.startswith("#") or "=" not in line_s:
                            continue
                        k_name, k_val = line_s.split("=", 1)
                        if k_name.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                            val = k_val.strip().strip('"').strip("'")
                            if val and not is_key_rejected(val):
                                return val
        except Exception:
            pass

        try:
            import streamlit as st
            for sec_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                if sec_name in st.secrets:
                    s_val = str(st.secrets[sec_name]).strip()
                    if s_val and not is_key_rejected(s_val):
                        return s_val
        except Exception:
            pass

        return ""

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
            fallback_key="",
        )
        meta = get_last_vision_meta()
        if meta.get("model"):
            self._preferred_model = meta["model"]
        return res

    # ------------------------------------------------------------------
    # ANÁLISIS POLICROMÁTICO V8 PRE-CALIBRADO (+30% CIELAB, <= 243 RGB)
    # ------------------------------------------------------------------
    @classmethod
    def analyze_fabric_v8_local(
        cls,
        sample_bytes: Optional[bytes],
        sample_name: str = "",
        boost: float = 0.30,
    ) -> Dict[str, Any]:
        """
        Ejecuta localmente (< 80 ms) la extracción limpia de ROI + calibración perceptual +30% +
        espectro multitono de 7 bandas para poblar MaterialAnalysisV7 con los tonos calibrados reales.
        """
        clean_label = (sample_name or "").rsplit(".", 1)[0].replace("_", " ").strip()
        if not sample_bytes or not isinstance(sample_bytes, (bytes, bytearray)) or len(sample_bytes) < 64:
            base_v7 = cls._analyze_fabric_pixels_local(sample_bytes, sample_name=clean_label)
            base_v7["v8_calibrated_boost"] = boost
            base_v7["v8_multitone_bands"] = []
            base_v7["v8_has_multitone_alternation"] = False
            return base_v7

        roi = extract_clean_swatch_roi_v8(bytes(sample_bytes))
        cal_roi = calibrate_fabric_lightness_v8(roi.crop, boost=boost, max_rgb=243)
        mt = analyze_fabric_multitone_v8(cal_roi, raw_bytes=bytes(sample_bytes), sample_name=clean_label)

        has_pat = bool(
            mt.has_multitone_alternation
            or len(mt.bands) >= 2
            or any(k in clean_label.lower() for k in cls._PATTERN_KEYWORDS)
        )
        out = MaterialAnalysisV7(
            name=clean_label or "Muestra de Tela Calibrada V8 (+30%)",
            color_description=mt.color_description,
            texture_detail=mt.texture_detail,
            light_interaction=mt.light_interaction,
            pattern_and_figures=mt.pattern_and_figures,
            has_visible_pattern=has_pat,
        ).model_dump()
        out["v8_calibrated_boost"] = boost
        out["v8_mean_rgb"] = mt.mean_rgb
        out["v8_mean_hex"] = mt.mean_hex
        out["v8_multitone_bands"] = mt.bands
        out["v8_has_multitone_alternation"] = mt.has_multitone_alternation
        out["v8_motif_period_px"] = mt.motif_period_px
        out["v8_roi_bbox"] = roi.bbox
        return out

    def analyze_material(
        self,
        sample_bytes: bytes,
        api_key: Optional[str] = None,
        material_type: str = "auto",
        sample_name: str = "",
    ) -> Dict[str, Any]:
        mtype = (material_type or "auto").strip().lower()
        is_fabric = any(k in mtype for k in ("fabric", "tela", "textil", "upholstery", "tapiz"))
        if not is_fabric:
            return super().analyze_material(
                sample_bytes=sample_bytes,
                api_key=api_key,
                material_type=material_type,
                sample_name=sample_name,
            )

        clean_label = (sample_name or "").rsplit(".", 1)[0].replace("_", " ").strip()
        det = self.analyze_fabric_v8_local(sample_bytes, sample_name=clean_label, boost=0.30)
        key = self.get_api_key(api_key)
        if not key or not sample_bytes or len(sample_bytes) < 64:
            return det

        try:
            from google.genai import types

            client = self.get_client(key)
            if not client:
                return det

            roi = extract_clean_swatch_roi_v8(sample_bytes)
            cal_roi = calibrate_fabric_lightness_v8(roi.crop, boost=0.30, max_rgb=243)
            instructions = (
                "Analyze this studio-calibrated (+30% perceptual CIELAB) upholstery fabric swatch crop:\n"
                "1) name: Concise commercial fabric name.\n"
                "2) color_description: Multi-tone chromatic description of the raised figures, crown highlights, warm/cool threads, and recessed valleys.\n"
                "3) has_visible_pattern & pattern_and_figures: Describe the 3D woven figure geometry, motif rhythm, and multi-tone yarn alternation.\n"
                "4) texture_detail: Precise 3D yarn & weave physical structure in English.\n"
                "5) light_interaction: Surface sheen ('Dead-matte natural fiber', 'Soft matte textile', 'Subtle satin jacquard sheen', or 'Directional velvet sheen')."
            )
            res = self._call_gemini(
                client=client,
                contents=[f"You are an expert luxury upholstery textile engineer. {instructions}", cal_roi],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MaterialAnalysisV7,
                    temperature=0.1,
                ),
                api_key=key,
            )
            vis_data = json.loads(res.text)
            merged = dict(det)
            if vis_data.get("name") and "fallback" not in str(vis_data.get("name", "")).lower():
                merged["name"] = clean_label or str(vis_data["name"]).strip()
            if vis_data.get("texture_detail"):
                merged["texture_detail"] = str(vis_data["texture_detail"]).strip()
            if vis_data.get("light_interaction"):
                merged["light_interaction"] = str(vis_data["light_interaction"]).strip()
            # Siempre conservar el espectro determinista +30% calibrado para impedir regresiones a RGB 177,174,171
            if vis_data.get("pattern_and_figures") and "unpatterned" not in str(vis_data["pattern_and_figures"]).lower():
                merged["pattern_and_figures"] = f"{det['pattern_and_figures']} | Vision: {vis_data['pattern_and_figures']}"
            merged["has_visible_pattern"] = bool(det.get("has_visible_pattern") or vis_data.get("has_visible_pattern"))
            return merged
        except Exception as e:
            print(f"[AIPromptServiceV8] Aviso en análisis Vision de tela calibrada: {e}")
            return det

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
        """Ejecuta en paralelo con ThreadPoolExecutor el análisis de mueble, madera y tela calibrada V8."""
        f_ana: Dict[str, Any] = {}
        w_ana: Optional[Dict[str, Any]] = None
        t_ana: Optional[Dict[str, Any]] = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            fut_f = (
                executor.submit(
                    self.analyze_furniture_for_enhancement,
                    furniture_bytes,
                    None,
                    None,
                    None,
                    notas_ia,
                )
                if (furniture_bytes and not skip_furniture)
                else None
            )
            fut_w = (
                executor.submit(self.analyze_material, wood_bytes, None, "wood", wood_name)
                if wood_bytes
                else None
            )
            fut_t = (
                executor.submit(self.analyze_material, fabric_bytes, None, "fabric", fabric_name)
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
    # PAQUETE ÚNICO SINCRONIZADO DE REFERENCIAS V8 (Image 1..N)
    # ------------------------------------------------------------------
    def build_v8_reference_pack(
        self,
        mode: str = "catalogo",
        material_mode: str = "fabric_only",
        furniture_name: str = "Mueble",
        furniture_filenames: Optional[List[str]] = None,
        furniture_bytes_list: Optional[List[bytes]] = None,
        furniture_source: str = "",
        fabric_label: str = "",
        fabric_filename: str = "",
        fabric_bytes: Optional[bytes] = None,
        wood_label: str = "",
        wood_filename: str = "",
        wood_bytes: Optional[bytes] = None,
        batch_views: Optional[List[Tuple[str, bytes]]] = None,
        batch_ref_filename: str = "",
        batch_ref_bytes: Optional[bytes] = None,
        target_view: Optional[Tuple[str, bytes]] = None,
        tipo_mueble: str = "",
        medidas_texto: str = "",
        has_ref: bool = False,
        include_anchor: bool = False,
        is_hd_swatch: bool = False,
        boost: float = 0.30,
        vista_id: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Fuente única de verdad que devuelve la lista ordenada exacta de adjuntos V8:
          [{"slot_index": 1..N, "filename": ..., "label": ..., "bytes": ..., "role": ...,
            "guide_line": ..., "ais_slot_line": ..., "dal_slot_part": ...}, ...]
        Garantiza alineación 1-a-1 entre prompts, attachment_guide, tira 76x76 px y ZIP.
        """
        pack: List[Dict[str, Any]] = []
        furn_src_badge = f"Mueble · {furniture_source}" if furniture_source else "Mueble"

        raw_fnames = [str(x).strip() for x in (furniture_filenames or []) if str(x or "").strip()]
        f_bytes_seq = list(furniture_bytes_list or [])
        if not raw_fnames and f_bytes_seq:
            raw_fnames = [f"mueble_{i + 1}.png" for i in range(len(f_bytes_seq))]
        if not raw_fnames:
            raw_fnames = [furniture_name or "mueble.png"]
        canon_furn_files = [self._canonical_photo_filename(fn, f"mueble_{i + 1}.png") for i, fn in enumerate(raw_fnames)]
        primary_furn_file = canon_furn_files[0]
        primary_furn_bytes = f_bytes_seq[0] if f_bytes_seq else b""

        # 1. Caso muestra plana HD 8K (sin mueble 3D)
        if mode == "hd" and is_hd_swatch:
            sw_file = primary_furn_file
            sw_bytes = primary_furn_bytes or fabric_bytes or wood_bytes or b""
            sw_badge = "Tela" if fabric_bytes else ("Madera" if wood_bytes else "Muestra")
            pack.append({
                "slot_index": 1,
                "filename": sw_file,
                "label": f"Image 1 · {sw_badge}",
                "bytes": sw_bytes,
                "role": "swatch_hd",
                "guide_line": f'Image 1: Muestra / textura original a mejorar en 8K ("{sw_file}")',
                "ais_slot_line": f'- Image 1 (SOURCE MATERIAL SWATCH · FILE: "{sw_file}"): Exact flat surface/textile/material sample ("{sw_file}") to deblur and upscale 1:1.',
                "dal_slot_part": f'Image 1 = "{sw_file}" (flat full-bleed surface swatch)',
            })
            return pack

        # 2. Caso Plano Técnico CAD: exclusivamente Image 1 (jamás adjuntar mosaico de tela)
        if mode == "plano" or (mode == "vista_suelta" and vista_id == "vista_plano_tecnico"):
            pack.append({
                "slot_index": 1,
                "filename": primary_furn_file,
                "label": f"Image 1 · {furn_src_badge}",
                "bytes": primary_furn_bytes,
                "role": "primary_furniture",
                "guide_line": f'Image 1: Foto original del mueble ("{primary_furn_file}")',
                "ais_slot_line": f'- Image 1 (PRIMARY FURNITURE REFERENCE · FILE: "{primary_furn_file}"): Take the furniture photo "{primary_furn_file}" whose exact 3D silhouette and proportions must be drawn as clean technical CAD line art.',
                "dal_slot_part": f'Image 1 = "{primary_furn_file}" (furniture blueprint reference)',
            })
            return pack

        # 3. Caso Lote Clonar Color
        if mode == "clonar_color":
            base_file = self._canonical_photo_filename(batch_ref_filename or primary_furn_file, "referencia_color.png")
            base_b = batch_ref_bytes or primary_furn_bytes
            pack.append({
                "slot_index": 1,
                "filename": base_file,
                "label": "Image 1 · Color base",
                "bytes": base_b,
                "role": "color_master",
                "guide_line": f'Image 1: Foto base de color/acabado ("{base_file}")',
                "ais_slot_line": f'- Image 1 (COLOR & MATERIAL MASTER REFERENCE · FILE: "{base_file}"): Take exact hue, timber/fabric texture, and sheen strictly from photo "{base_file}".',
                "dal_slot_part": f'Image 1 = "{base_file}" (color & finish master)',
            })
            if target_view is not None:
                v_file = self._canonical_photo_filename(target_view[0], "vista.png")
                pack.append({
                    "slot_index": 2,
                    "filename": v_file,
                    "label": "Image 2 · Vista objetivo",
                    "bytes": target_view[1] or b"",
                    "role": "target_view",
                    "guide_line": f'Image 2: Vista objetivo a recolorear ("{v_file}")',
                    "ais_slot_line": f'- Image 2 (TARGET VIEW TO RECOLOR · FILE: "{v_file}"): Keep EXACT camera angle, 3D silhouette, joinery, and proportions from photo "{v_file}".',
                    "dal_slot_part": f'Image 2 = "{v_file}" (target view)',
                })
            else:
                for idx_v, (vn, vb) in enumerate(batch_views or [], start=1):
                    v_file = self._canonical_photo_filename(vn, f"vista_{idx_v}.png")
                    pack.append({
                        "slot_index": 2,
                        "filename": v_file,
                        "label": f"Image 2 · Vista {idx_v}",
                        "bytes": vb or b"",
                        "role": "target_view",
                        "guide_line": f'Image 2: Vista objetivo {idx_v} ("{v_file}")',
                        "ais_slot_line": f'- Image 2 (TARGET VIEW · FILE: "{v_file}"): Target view "{v_file}".',
                        "dal_slot_part": f'Image 2 = "{v_file}" (target view)',
                    })
            return pack

        # 4. Caso Lote Vistas + Tela (vistas_tela)
        if mode == "vistas_tela":
            eff_fab_bytes = fabric_bytes or batch_ref_bytes
            eff_fab_name = fabric_filename or fabric_label or batch_ref_filename or "tela.png"
            has_fab_vt = bool(eff_fab_bytes or fabric_filename or fabric_label or batch_ref_filename)
            swatch_v8_file = make_v8_swatch_filename(eff_fab_name)
            vt_primary_fn = (
                target_view[0]
                if target_view is not None
                else (batch_views[0][0] if batch_views else primary_furn_file)
            )
            eff_tipo_vt = resolve_v8_furniture_type_hint(
                tipo_mueble=tipo_mueble,
                furniture_name=furniture_name,
                primary_filename=vt_primary_fn,
            )
            w_cm_vt = infer_furniture_width_cm_v8(None, eff_tipo_vt, medidas_texto)

            cal_sw_bytes = b""
            seamless_tile_vt: Optional[Image.Image] = None
            tile_px_vt, grid_n_vt = compute_v8_tile_px(1280, furniture_width_cm=w_cm_vt, furniture_type=eff_tipo_vt)
            if eff_fab_bytes and len(eff_fab_bytes) >= 64:
                try:
                    roi_vt = extract_clean_swatch_roi_v8(eff_fab_bytes)
                    cal_vt = calibrate_fabric_lightness_v8(roi_vt.crop, boost=boost, max_rgb=243)
                    seamless_tile_vt = make_toroidal_seamless_tile_v8(cal_vt, tile_px=tile_px_vt, max_rgb=243)
                    sw_im = (
                        cal_vt
                        if min(cal_vt.size) >= 256
                        else _apply_ratio_preserving_rgb_ceiling(
                            cal_vt.resize((256, 256), Image.Resampling.LANCZOS),
                            max_rgb=243,
                        )
                    )
                    buf_sw = io.BytesIO()
                    sw_im.save(buf_sw, format="PNG", compress_level=4)
                    cal_sw_bytes = buf_sw.getvalue()
                except Exception:
                    cal_sw_bytes = eff_fab_bytes or b""

            views_to_build = [target_view] if target_view is not None else list(batch_views or [])
            if target_view is not None or len(views_to_build) <= 1:
                v_pair = views_to_build[0] if views_to_build else ("vista_1.png", b"")
                v_file = self._canonical_photo_filename(v_pair[0], "vista_1.png")
                v_bytes = v_pair[1] or b""
                pack.append({
                    "slot_index": 1,
                    "filename": v_file,
                    "label": "Image 1 · Vista objetivo",
                    "bytes": v_bytes,
                    "role": "primary_furniture",
                    "guide_line": f'Image 1: Vista original del mueble ("{v_file}")',
                    "ais_slot_line": f'- Image 1 (TARGET FURNITURE VIEW HD ANCHOR · FILE: "{v_file}"): Take ONLY exact camera angle, 3D silhouette, seams, folds, and non-upholstered wood/metal parts from "{v_file}" (100% erase old fabric).',
                    "dal_slot_part": f'Image 1 = "{v_file}" (target furniture view)',
                })
                if has_fab_vt:
                    canv_file = make_v8_canvas_filename(v_file)
                    canv_bytes = b""
                    if v_bytes and len(v_bytes) >= 64 and seamless_tile_vt is not None:
                        try:
                            canv_file, canv_bytes, _ = compose_view_with_precomputed_tile_v8(
                                view_bytes=v_bytes,
                                seamless_tile=seamless_tile_vt,
                                tile_px=tile_px_vt,
                                grid_n=grid_n_vt,
                                view_name=v_file,
                            )
                        except Exception:
                            canv_bytes = b""
                    pack.append({
                        "slot_index": 2,
                        "filename": canv_file,
                        "label": "Image 2 · Lienzo Escala V8",
                        "bytes": canv_bytes,
                        "role": "v8_scale_canvas",
                        "guide_line": f'Image 2: Lienzo Maestro de Escala V8 ("{canv_file}")',
                        "ais_slot_line": f'- Image 2 (V8 MASTER SCALE CONDITIONING CANVAS · FILE: "{canv_file}"): Stepped-back view surrounded by {grid_n_vt * grid_n_vt} seamless reduced +30% fabric tiles — use for EXACT 1:1 physical motif scale (~97% macro reduction). NEVER copy the tiled background into output.',
                        "dal_slot_part": f'Image 2 = "{canv_file}" (V8 1:1 scale conditioning canvas — do NOT render tiled background)',
                    })
                    pack.append({
                        "slot_index": 3,
                        "filename": swatch_v8_file,
                        "label": "Image 3 · Tela +30% V8",
                        "bytes": cal_sw_bytes,
                        "role": "v8_calibrated_swatch",
                        "guide_line": f'Image 3: Muestra limpia pre-calibrada +30% V8 ("{swatch_v8_file}")',
                        "ais_slot_line": f'- Image 3 (V8 +30% PRE-CALIBRATED MULTI-TONE SWATCH · FILE: "{swatch_v8_file}"): Clean shadow-free +30% pre-calibrated swatch showing exact 7-band multi-tone figure alternation and 3D yarn relief (0% additional tone drift).',
                        "dal_slot_part": f'Image 3 = "{swatch_v8_file}" (V8 +30% calibrated multi-tone swatch)',
                    })
                return pack

            # Tira previa multi-vista en UI antes de pulsar ir: muestra cada vista + su lienzo V8 + la tela +30%
            for idx_v, (vn, vb) in enumerate(views_to_build, start=1):
                v_file = self._canonical_photo_filename(vn, f"vista_{idx_v}.png")
                pack.append({
                    "slot_index": 1,
                    "filename": v_file,
                    "label": f"Image 1 · Vista {idx_v}",
                    "bytes": vb or b"",
                    "role": "primary_furniture",
                    "guide_line": f'Image 1: Vista {idx_v} ("{v_file}")',
                    "ais_slot_line": "",
                    "dal_slot_part": "",
                })
                if has_fab_vt and vb and len(vb) >= 64 and seamless_tile_vt is not None:
                    try:
                        c_fn, c_b, _ = compose_view_with_precomputed_tile_v8(
                            view_bytes=vb,
                            seamless_tile=seamless_tile_vt,
                            tile_px=tile_px_vt,
                            grid_n=grid_n_vt,
                            view_name=v_file,
                        )
                        pack.append({
                            "slot_index": 2,
                            "filename": c_fn,
                            "label": f"Image 2 · Lienzo V{idx_v}",
                            "bytes": c_b,
                            "role": "v8_scale_canvas",
                            "guide_line": f'Image 2: Lienzo Maestro V8 ("{c_fn}")',
                            "ais_slot_line": "",
                            "dal_slot_part": "",
                        })
                    except Exception:
                        pass
            if has_fab_vt:
                pack.append({
                    "slot_index": 3,
                    "filename": swatch_v8_file,
                    "label": "Image 3 · Tela +30% V8",
                    "bytes": cal_sw_bytes,
                    "role": "v8_calibrated_swatch",
                    "guide_line": f'Image 3: Muestra limpia +30% V8 ("{swatch_v8_file}")',
                    "ais_slot_line": "",
                    "dal_slot_part": "",
                })
            return pack

        # 5. Modos estándar (catalogo, vista_suelta, material, entorno, extraer, hd, vista_34_der_2054)
        use_fabric = bool(fabric_bytes or fabric_filename or fabric_label) and (
            mode != "material" or material_mode in ("fabric_only", "dual")
        )
        use_wood = bool(wood_bytes or wood_filename or wood_label) and (
            mode != "material" or material_mode in ("wood_only", "dual")
        )

        slot = 1
        pack.append({
            "slot_index": slot,
            "filename": primary_furn_file,
            "label": f"Image {slot} · {furn_src_badge}",
            "bytes": primary_furn_bytes,
            "role": "primary_furniture",
            "guide_line": f'Image {slot}: Foto original HD del mueble ("{primary_furn_file}")',
            "ais_slot_line": (
                f'- Image {slot} (PRIMARY FURNITURE HD ANCHOR · FILE: "{primary_furn_file}"): '
                f'Exact 3D silhouette, proportions, seams, cushion count, and non-upholstered wood/metal leg structure from "{primary_furn_file}"'
                + (" (completely erase and overwrite 100% of its old upholstery color/fabric)." if use_fabric else ".")
            ),
            "dal_slot_part": f'Image {slot} = "{primary_furn_file}" (original furniture HD geometry anchor)',
        })
        slot += 1

        for idx_ex, extra_fn in enumerate(canon_furn_files[1:], start=2):
            ex_bytes = f_bytes_seq[idx_ex - 1] if idx_ex - 1 < len(f_bytes_seq) else b""
            pack.append({
                "slot_index": slot,
                "filename": extra_fn,
                "label": f"Image {slot} · Mueble #{idx_ex}",
                "bytes": ex_bytes,
                "role": "extra_furniture",
                "guide_line": f'Image {slot}: Vista adicional del mueble ("{extra_fn}")',
                "ais_slot_line": f'- Image {slot} (ADDITIONAL FURNITURE ANGLE · FILE: "{extra_fn}"): Supplementary angle of the same furniture piece from "{extra_fn}".',
                "dal_slot_part": f'Image {slot} = "{extra_fn}" (extra furniture angle)',
            })
            slot += 1

        if use_fabric:
            raw_fab_ref = fabric_filename or fabric_label or "tela.png"
            canvas_file = make_v8_canvas_filename(primary_furn_file)
            swatch_file = make_v8_swatch_filename(raw_fab_ref)
            eff_tipo_std = resolve_v8_furniture_type_hint(
                tipo_mueble=tipo_mueble,
                furniture_name=furniture_name,
                primary_filename=primary_furn_file,
            )
            w_cm = infer_furniture_width_cm_v8(None, eff_tipo_std, medidas_texto)
            _, grid_est = compute_v8_tile_px(1280, furniture_width_cm=w_cm, furniture_type=eff_tipo_std)
            total_tiles_est = grid_est * grid_est

            canvas_bytes = b""
            swatch_bytes = b""
            artifacts: Optional[V8ConditioningArtifacts] = None
            if primary_furn_bytes and len(primary_furn_bytes) >= 64 and fabric_bytes and len(fabric_bytes) >= 64:
                try:
                    artifacts = build_v8_conditioning_canvas(
                        furniture_bytes=primary_furn_bytes,
                        fabric_bytes=fabric_bytes,
                        sample_name=raw_fab_ref,
                        furniture_name=primary_furn_file,
                        furniture_width_cm=w_cm,
                        furniture_type=eff_tipo_std,
                        boost=boost,
                    )
                    canvas_bytes = artifacts.canvas_png
                    swatch_bytes = artifacts.calibrated_swatch_png
                    canvas_file = artifacts.canvas_filename
                    swatch_file = artifacts.calibrated_swatch_filename
                    total_tiles_est = artifacts.total_tiles
                except Exception:
                    artifacts = None
            elif fabric_bytes and len(fabric_bytes) >= 64:
                try:
                    roi_only = extract_clean_swatch_roi_v8(fabric_bytes)
                    cal_only = calibrate_fabric_lightness_v8(roi_only.crop, boost=boost, max_rgb=243)
                    sw_im = (
                        cal_only
                        if min(cal_only.size) >= 256
                        else _apply_ratio_preserving_rgb_ceiling(
                            cal_only.resize((256, 256), Image.Resampling.LANCZOS),
                            max_rgb=243,
                        )
                    )
                    bsw = io.BytesIO()
                    sw_im.save(bsw, format="PNG", compress_level=4)
                    swatch_bytes = bsw.getvalue()
                except Exception:
                    swatch_bytes = fabric_bytes

            pack.append({
                "slot_index": slot,
                "filename": canvas_file,
                "label": f"Image {slot} · Lienzo Escala V8",
                "bytes": canvas_bytes,
                "role": "v8_scale_canvas",
                "total_tiles": total_tiles_est,
                "artifacts": artifacts,
                "guide_line": f'Image {slot}: Lienzo Maestro de Escala V8 ("{canvas_file}")',
                "ais_slot_line": (
                    f'- Image {slot} (V8 MASTER SCALE CONDITIONING CANVAS · FILE: "{canvas_file}"): '
                    f'Stepped-back furniture (~58%) with crisp #FFFFFF isolation halo/border surrounded by {total_tiles_est} seamless reduced +30% fabric tiles. '
                    f'Use "{canvas_file}" as the EXACT 1:1 physical motif/figure scale reference (~97% macro-to-furniture area reduction). '
                    f'CRITICAL: NEVER keep or render the tiled fabric background wall in the final output!'
                ),
                "dal_slot_part": f'Image {slot} = "{canvas_file}" (V8 1:1 miniature scale conditioning canvas — NEVER copy tiled background into output)',
            })
            slot += 1

            pack.append({
                "slot_index": slot,
                "filename": swatch_file,
                "label": f"Image {slot} · Tela +30% V8",
                "bytes": swatch_bytes,
                "role": "v8_calibrated_swatch",
                "guide_line": f'Image {slot}: Muestra limpia pre-calibrada +30% V8 ("{swatch_file}")',
                "ais_slot_line": (
                    f'- Image {slot} (V8 +30% PRE-CALIBRATED CLEAN SWATCH GROUND TRUTH · FILE: "{swatch_file}"): '
                    f'Artifact-free clean swatch ALREADY pre-calibrated +30% lighter in CIELAB (max RGB <= 243). '
                    f'Use "{swatch_file}" for crisp 7-band multi-tone figure alternation, yarn micro-relief, and 0% additional color/hue/brightness drift.'
                ),
                "dal_slot_part": f'Image {slot} = "{swatch_file}" (V8 +30% pre-calibrated multi-tone swatch — 0% additional tone shift)',
            })
            slot += 1

        if use_wood:
            w_canon = self._canonical_photo_filename(wood_filename or wood_label, "madera.png")
            w_lbl_txt = wood_label or os.path.splitext(w_canon)[0]
            pack.append({
                "slot_index": slot,
                "filename": w_canon,
                "label": f"Image {slot} · Madera",
                "bytes": wood_bytes or b"",
                "role": "wood_sample",
                "guide_line": f'Image {slot}: Muestra de madera ("{w_canon}")',
                "ais_slot_line": (
                    f'- Image {slot} (WOOD SAMPLE GROUND TRUTH · FILE: "{w_canon}"): '
                    f'Take exact wood species, continuous anatomical grain flow, and stain tone strictly from "{w_canon}" ({w_lbl_txt}).'
                ),
                "dal_slot_part": f'Image {slot} = "{w_canon}" (wood sample)',
            })
            slot += 1

        if has_ref:
            pack.append({
                "slot_index": slot,
                "filename": f"ref_angulo_{slot}.png",
                "label": f"Image {slot} · Ref. Ángulo",
                "bytes": b"",
                "role": "aux_ref",
                "guide_line": f"Image {slot}: Referencia auxiliar de ángulo",
                "ais_slot_line": f"- Image {slot} (AUXILIARY ANGLE REFERENCE): Supplementary structural angle details.",
                "dal_slot_part": f"Image {slot} = auxiliary angle reference",
            })
            slot += 1

        if include_anchor:
            pack.append({
                "slot_index": slot,
                "filename": "",
                "label": f"Image {slot} · Ancla Vista 1",
                "bytes": b"",
                "role": "vista1_anchor",
                "guide_line": f"Image {slot} (recomendada): Tu render aprobado de Vista 1",
                "ais_slot_line": (
                    f"- Image {slot} (APPROVED VISTA 1 ANCHOR — WHEN ATTACHED): "
                    "Use as visual lock for exact outline, multi-tone upholstery, and wood finish; rotate ONLY the camera angle."
                ),
                "dal_slot_part": f"Image {slot} (optional) = approved Vista 1 anchor",
            })
            slot += 1

        return pack

    def _slots_from_v8_pack(self, pack: List[Dict[str, Any]]) -> Dict[str, Any]:
        slot_lines = [p["ais_slot_line"] for p in pack if p.get("ais_slot_line")]
        guide = [p["guide_line"] for p in pack if p.get("guide_line")]
        dal_parts = [p["dal_slot_part"] for p in pack if p.get("dal_slot_part")]

        primary_furn = next((p for p in pack if p["role"] == "primary_furniture"), pack[0] if pack else {"filename": "mueble.png", "slot_index": 1})
        canvas_slot = next((p for p in pack if p["role"] == "v8_scale_canvas"), None)
        swatch_slot = next((p for p in pack if p["role"] == "v8_calibrated_swatch"), None)
        wood_slot = next((p for p in pack if p["role"] == "wood_sample"), None)
        ref_slot = next((p for p in pack if p["role"] == "aux_ref"), None)
        anchor_slot = next((p for p in pack if p["role"] == "vista1_anchor"), None)
        extra_furn = [p["slot_index"] for p in pack if p["role"] == "extra_furniture"]

        order_str = ", ".join(f"Image {p['slot_index']}" for p in pack) if pack else "Image 1"
        canvas_tail = (
            "NEVER confuse the conditioning scale canvas with the final output background."
            if canvas_slot
            else "NEVER invent unattached material references."
        )
        match_rule = (
            "PHOTO IDENTIFICATION RULE: Match every attached image by its exact copied file name above "
            f"(or by attachment order {order_str} if pasted from clipboard); {canvas_tail}"
        )
        return {
            "header_block": "ATTACHED REFERENCE IMAGES (V8 MULTI-SLOT CONDITIONING):\n" + "\n".join(slot_lines) + "\n" + match_rule,
            "dal_photo_map": "Attached Photos Map (identify by exact copied filename or order): " + " | ".join(dal_parts) + ".",
            "guide": guide,
            "primary_furn_idx": primary_furn["slot_index"],
            "primary_furn_file": primary_furn["filename"],
            "furn_files": [p["filename"] for p in pack if p["role"] in ("primary_furniture", "extra_furniture")],
            "extra_furn_indices": extra_furn,
            "canvas_idx": canvas_slot["slot_index"] if canvas_slot else None,
            "canvas_file": canvas_slot["filename"] if canvas_slot else "",
            "total_tiles": canvas_slot.get("total_tiles", 196) if canvas_slot else 0,
            "fabric_idx": swatch_slot["slot_index"] if swatch_slot else None,
            "fabric_file": swatch_slot["filename"] if swatch_slot else "",
            "wood_idx": wood_slot["slot_index"] if wood_slot else None,
            "wood_file": wood_slot["filename"] if wood_slot else "",
            "ref_idx": ref_slot["slot_index"] if ref_slot else None,
            "anchor_idx": anchor_slot["slot_index"] if anchor_slot else None,
        }

    # ------------------------------------------------------------------
    # BLOQUES DE REALISMO 3D, ESCALA 1:1 Y MULTITONO +30% V8
    # ------------------------------------------------------------------
    def _build_v8_fabric_mandate_blocks(
        self,
        fa: Optional[Dict[str, Any]],
        fabric_label: str,
        canvas_idx: Optional[int],
        canvas_file: str,
        swatch_idx: Optional[int],
        swatch_file: str,
        total_tiles: int,
        protect_non_upholstered_from: str = "",
        reframe_white_bg: bool = True,
        is_room_scene: bool = False,
    ) -> Tuple[str, str]:
        fa = fa or {}
        f_name = fa.get("name") or fabric_label or "Muestra de Tela Calibrada V8"
        f_color = fa.get("color_description") or "paleta policromática pre-calibrada +30% en CIELAB (max RGB <= 243)"
        f_tex = fa.get("texture_detail") or "raised 3D woven multi-yarn figures over tight recessed interstitial valleys"
        f_light = fa.get("light_interaction") or "Soft matte textile"
        f_pat = str(fa.get("pattern_and_figures") or "").strip()
        bands = fa.get("v8_multitone_bands") or []

        canvas_ref = f'Image {canvas_idx} ("{canvas_file}")' if canvas_idx else f'"{canvas_file}"'
        swatch_ref = f'Image {swatch_idx} ("{swatch_file}")' if swatch_idx else f'"{swatch_file}"'
        n_tiles = total_tiles or 196

        if bands and len(bands) >= 2:
            band_lines = ", ".join(
                f"{b.get('name_en') or b.get('name')} {b['hex']} (RGB {b['rgb'][0]},{b['rgb'][1]},{b['rgb'][2]}, {b['share_pct']}% — {b.get('role', '')})"
                for b in bands[:7]
            )
            multitone_ais = (
                f"ANTI-MONOCHROME 7-BAND MULTI-TONE FIGURE MANDATE: Replicate the exact polychromatic yarn & figure alternation from {swatch_ref} "
                f"({band_lines}). STRICTLY FORBID flat single-HEX monochrome painting — adjacent miniature woven figures across every cushion and casco panel "
                "must organically alternate bright ivory crowns, warm camel/oatmeal figure bodies, subtle rosy-taupe/stone threads, cool ash counter-threads, and recessed relief valleys. "
            )
            multitone_dal = f"polychromatic multi-tone figure alternation ({', '.join(b['hex'] for b in bands[:7])}; NEVER flat monochrome fill), "
        else:
            multitone_ais = (
                f"1:1 FIGURES, MOTIFS & MULTI-YARN FIDELITY: Copy every figure, motif, and subtle multi-yarn tone variation from {swatch_ref} ({f_color}; {f_pat or f_tex}) "
                "without collapsing the weave into flat plastic single-color paint. "
            )
            multitone_dal = f"exact 1:1 figures & weave ({f_color}), "

        if is_room_scene:
            reframe_ais = (
                f"CONDITIONING BACKGROUND REMOVAL (ROOM INTEGRATION): Treat the tiled fabric mosaic surrounding the stepped-back furniture in {canvas_ref} "
                "STRICTLY as a spatial 1:1 scale guide — NEVER render tiled fabric wallpaper on room walls or floors! Integrate the finished reupholstered furniture naturally into the wide client interior scene."
            )
            reframe_dal = f"NEVER render the tiled mosaic background from {canvas_ref}; place the finished piece naturally inside the client room interior"
        elif reframe_white_bg:
            reframe_ais = (
                f"COMMERCIAL RE-FRAMING & PURE #FFFFFF ISOLATION (NEVER KEEP TILED BACKGROUND): Treat the surrounding {n_tiles} reduced fabric tiles in {canvas_ref} "
                "STRICTLY as an input spatial scale reference — NEVER keep tiled fabric background in output and NEVER render mosaic wallpaper behind the furniture! "
                "Re-frame the finished reupholstered furniture to commercial catalog scale (~74% of frame, centered with clean balanced margins) isolated on 100% pure solid white #FFFFFF (RGB 255,255,255) with 0% ground shadow, 0% contact shadow, 0% drop shadow, and 0% reflection."
            )
            reframe_dal = (
                f"NEVER keep tiled fabric background from {canvas_ref} in output; re-frame the finished furniture (~74% of canvas) on pure solid #FFFFFF (RGB 255,255,255) with 0% shadows and 0% reflections"
            )
        else:
            reframe_ais = (
                f"CONDITIONING BACKGROUND REMOVAL: Treat {canvas_ref} strictly as an input 1:1 motif-scale guide — NEVER keep tiled fabric background in output; preserve the clean scene background of Image 1."
            )
            reframe_dal = f"NEVER keep tiled fabric background from {canvas_ref} in output"

        protect_clause = (
            f" Strictly protect all non-upholstered structural components (exposed wooden legs, wooden plinths/bases/frames, metal hardware, glass, stone) identical to {protect_non_upholstered_from} with 0% fabric bleed onto legs."
            if protect_non_upholstered_from
            else " Strictly protect all exposed wooden legs, wooden bases/frames, and metal hardware with 0% fabric bleed."
        )

        ais_txt = (
            f"1) EXACT 1:1 MINIATURE SCALE FROM V8 CONDITIONING CANVAS: Use {canvas_ref} (where the stepped-back furniture sits directly beside {n_tiles} seamless reduced tiles) "
            f"to lock exact 1:1 physical miniature figure & weave scale (~97% macro-to-furniture area reduction) so raised figures appear at authentic real-world viewing distance (never giant macro loops). "
            f"2) +30% PRE-CALIBRATED BRIGHTNESS LOCK (0% CAMBIO DE TONO ADICIONAL): Both {canvas_ref} and {swatch_ref} ('{f_name}') are ALREADY pre-calibrated +30% lighter in CIELAB (max RGB <= 243) to compensate macro camera underexposure. "
            f"Lock 0% additional color, hue, or brightness drift relative to {swatch_ref} ({f_color}; Sheen: {f_light}) — no darkening back to dark taupe/greige, no warming/cooling, and no highlight clipping to #FFFFFF. "
            f"3) {multitone_ais}"
            f"4) FULL CASCO & CUSHIONS 3D UPHOLSTERY REALISM (100% EL CASCO COMPLETO + COJINES): Completely discard 100% of the old upholstery color/fabric (100% OLD-FABRIC ERASURE) and wrap this exact V8 fabric uniformly across "
            f"100% of EL CASCO COMPLETO (respaldo exterior/interior, descansabrazos, faldón/base tapizada, laterales, cabecera/rieles si aplica) AND all seat/back cushions with photorealistic 3D upholstery physics "
            f"(realistic fabric surface tension around curves, crisp seam puckering, taut piping/welting wraps, natural cushion pleats, and subtle inter-figure micro-valley self-shading: {f_tex}).{protect_clause} "
            f"5) {reframe_ais}"
        )

        dal_txt = (
            f"100% of EL CASCO COMPLETO (backrest, armrests, lower base rail/faldón, side panels) AND all cushions reupholstered uniformly in '{f_name}' "
            f"({multitone_dal}3D weave: {f_tex}; sheen: {f_light}) using {canvas_ref} for exact 1:1 miniature motif scale (~97% macro reduction) and {swatch_ref} "
            f"(already pre-calibrated +30% lighter, max RGB <= 243) with 0% additional color/hue/brightness drift, realistic 3D seam/piping/pleat draping, protected wood/metal legs, and {reframe_dal}"
        )
        return ais_txt, dal_txt

    @classmethod
    def _fabric_negative_terms(cls, fa: Optional[Dict[str, Any]] = None, fabric_label: str = "") -> str:
        base = super()._fabric_negative_terms(fa, fabric_label)
        v8_extra = (
            "tiled fabric background, mosaic wallpaper background, fabric grid in background, "
            "monochrome flat paint, single-color flat fill, dark uncalibrated taupe shift, fabric bleed on wooden legs"
        )
        return f"{base}, {v8_extra}"

    def _build_v8_material_lock_text(
        self,
        profile: Dict[str, Any],
        furn_item: str,
        existing_mats: str,
        wa: Dict[str, Any],
        fa: Dict[str, Any],
        slots_meta: Dict[str, Any],
        has_wood: bool,
        has_fabric: bool,
        fabric_label: str = "",
        reframe_white_bg: bool = True,
        is_room_scene: bool = False,
    ) -> Tuple[str, str]:
        ais_parts: List[str] = []
        dal_parts: List[str] = []
        primary_furn_file = slots_meta["primary_furn_file"]
        furn_ref = f'Image {slots_meta["primary_furn_idx"]} ("{primary_furn_file}")'

        if has_wood:
            w_name = wa.get("name") or "Selected Wood Sample"
            w_color = wa.get("color_description") or "warm natural timber tone from the wood sample"
            w_tex = wa.get("texture_detail") or "fine continuous wood grain pores"
            w_light = wa.get("light_interaction") or "soft satin-matte timber sheen"
            w_idx = slots_meta.get("wood_idx")
            w_file = slots_meta.get("wood_file") or ""
            src = f'Image {w_idx} ("{w_file}")' if (w_idx and w_file) else (f"Image {w_idx}" if w_idx else "the wood sample")
            ais_parts.append(
                f"- MONOLITHIC WOOD FINISH LOCK (from {src} — '{w_name}'): Apply this exact timber species, {w_color}, "
                f"{w_tex}, and {w_light} uniformly across all wooden parts ({profile['parts_str']}). "
                "Ensure natural anatomical grain flow (vertical on legs, horizontal on rails); zero unintended two-tone contrast or fabric bleed."
            )
            dal_parts.append(
                f"Wooden components ({profile['parts_str']}) finished monolithically in {w_name} ({w_color}, {w_tex}, {w_light}) matching {src}."
            )
        elif has_fabric:
            ais_parts.append(
                f"- NON-UPHOLSTERED PARTS PROTECTION & 100% OLD-FABRIC ERASURE (from {furn_ref}): "
                f"Preserve ONLY the non-upholstered structural components (exposed wooden legs, wooden plinths/frames, metal hardware, glass, stone) strictly identical to {furn_ref}. "
                f"Completely DISCARD and OVERWRITE 100% of the old upholstery color, pattern, and fabric from {furn_ref} — ZERO old-fabric tint bleed."
            )
            dal_parts.append(
                f"All non-upholstered wooden/metal legs and frames preserved strictly identical to {furn_ref}, while 100% of the old upholstery fabric/color from {furn_ref} is erased."
            )
        else:
            ais_parts.append(
                f"- ORIGINAL WOOD / SURFACE PRESERVATION (from {furn_ref}): Faithfully preserve the authentic surface materials, "
                f"finishes, and color saturation of '{furn_item}' ({existing_mats}) without artificial alteration."
            )
            dal_parts.append(
                f"Faithfully preserve all authentic materials and finishes directly from {furn_ref} ({existing_mats})."
            )

        if has_fabric:
            fab_ais, fab_dal = self._build_v8_fabric_mandate_blocks(
                fa=fa,
                fabric_label=fabric_label,
                canvas_idx=slots_meta.get("canvas_idx"),
                canvas_file=slots_meta.get("canvas_file", ""),
                swatch_idx=slots_meta.get("fabric_idx"),
                swatch_file=slots_meta.get("fabric_file", ""),
                total_tiles=slots_meta.get("total_tiles", 196),
                protect_non_upholstered_from="" if has_wood else furn_ref,
                reframe_white_bg=reframe_white_bg,
                is_room_scene=is_room_scene,
            )
            ais_parts.append(f"- V8 SCALE-CALIBRATED (+30%) MULTI-TONE CASCO & CUSHIONS UPHOLSTERY LOCK: {fab_ais}")
            dal_parts.append(f"{fab_dal}.")
        elif has_wood:
            ais_parts.append(
                f"- NON-WOOD / UPHOLSTERY PRESERVATION (from {furn_ref}): Keep any existing fabric, cushions, metal, stone, or glass strictly identical to {furn_ref}."
            )
            dal_parts.append(f"All non-wooden surfaces remain strictly identical to {furn_ref}.")

        return "\n".join(ais_parts), " ".join(dal_parts)

    # ------------------------------------------------------------------
    # CONSTRUCTORES DE ÍTEMS POR MODO (SINCRONIZADOS CON build_v8_reference_pack)
    # ------------------------------------------------------------------
    def _build_single_studio_view_prompt_v8(
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
        use_anchor: bool,
        medidas_texto: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
    ) -> Dict[str, Any]:
        meta = ALL_SINGLE_VIEWS[view_id]
        angle_desc = profile["angles"][view_id]
        pack = self.build_v8_reference_pack(
            mode="vista_suelta",
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            fabric_label=fabric_label if has_fabric else "",
            fabric_filename=fabric_filename if has_fabric else "",
            wood_label=wood_label if has_wood else "",
            wood_filename=wood_filename if has_wood else "",
            tipo_mueble=furn_item,
            medidas_texto=medidas_texto,
            has_ref=has_ref,
            include_anchor=use_anchor,
        )
        slots = self._slots_from_v8_pack(pack)
        primary_furn_file = slots["primary_furn_file"]

        mat_ais, mat_dal = self._build_v8_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            slots_meta=slots,
            has_wood=has_wood,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            reframe_white_bg=white_bg_enabled,
            is_room_scene=False,
        )

        anchor_ais = ""
        anchor_dal = ""
        if use_anchor and slots["anchor_idx"]:
            a_idx = slots["anchor_idx"]
            anchor_ais = (
                f"\n- ANCHOR CONSISTENCY (Image {a_idx} when attached): Image {a_idx} is the approved Vista 1 render. "
                f"Match its exact silhouette, proportions, +30% multi-tone upholstery, and wood finish 100%, rotating ONLY the camera to {meta['short']}."
            )
            anchor_dal = f" Use Image {a_idx} (if attached) as exact identity lock, changing only camera perspective."

        bg_ais = (
            "Pure seamless solid digital white background (#FFFFFF, RGB 255,255,255), 0% ground shadow, 0% contact shadow, "
            "0% drop shadow, 0% floor reflection, exact 2054 x 2054 px commercial studio cutout (NEVER keep tiled fabric background in output)."
            if white_bg_enabled
            else "Clean soft neutral studio backdrop with subtle natural contact grounding (NEVER keep tiled fabric background in output)."
        )
        bg_dal = (
            "pure seamless solid white background (#FFFFFF, RGB 255,255,255) with 0% ground/contact/drop shadows, 0% reflections, exact 2054 x 2054 px square output"
            if white_bg_enabled
            else "clean soft neutral commercial studio backdrop"
        )

        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" Mandatory user directives: {user_notes_clean}." if user_notes_clean else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        fab_neg = f", {self._fabric_negative_terms(fa, fabric_label)}" if has_fabric else ""

        prompt_ais = (
            f"[V8 COMMERCIAL PRODUCT PHOTOGRAPHY · {meta['label'].upper()} · 2054x2054 PX]\n"
            f"TASK: Generate ONE standalone high-resolution commercial catalog photograph of '{furn_item}' ('{furniture_name}'), "
            f'taking the 3D furniture geometry from Image 1 ("{primary_furn_file}"), from the exact requested camera perspective.\n\n'
            f"{slots['header_block']}\n\n"
            f"CAMERA & COMMERCIAL RE-FRAMING:\n"
            f"- PERSPECTIVE: {angle_desc}\n"
            f"- FRAMING & RESOLUTION: Exact 2054 x 2054 px square composition; single centered furniture piece re-framed to ~74% of canvas with clean balanced ~13% margins on all 4 sides. Zero cropping, no collage.\n\n"
            f"MATERIAL, V8 SCALE & GEOMETRY LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY RULE: {profile['geometry_rule']}{dim_ais}{mirror_ais}{anchor_ais}{notes_ais}\n\n"
            f"STUDIO & OPTICS:\n"
            f"- BACKGROUND: {bg_ais}\n"
            f"- PHOTOGRAPHY: Shot on 100MP medium-format camera, 80mm prime lens at f/11, balanced 5400K wrap-around softbox lighting, tack-sharp yarn & grain micro-texture.\n\n"
            f"Exclude: collage, split screen, multiple objects, text, labels, watermark, CGI plastic sheen"
            f"{', ground shadows, contact shadows, drop shadows, floor reflections, grey backdrop' if white_bg_enabled else ''}{fab_neg}{profile['neg_add']}."
        )

        prompt_dal = (
            f"Standalone 2054 x 2054 px commercial catalog photograph of a single {furn_item} ('{furniture_name}') taken from Image 1 (\"{primary_furn_file}\").\n"
            f"{slots['dal_photo_map']}\n"
            f"Camera Perspective: {angle_desc} Re-framed at ~74% commercial catalog scale with clean margins, single object only.\n"
            f"Materials: {mat_dal}\n"
            f"Structure & Proportions: {profile['geometry_rule']} {profile['dimensions_rule']}{anchor_dal}{notes_dal}\n"
            f"Studio & Lighting: Set against a {bg_dal}. Balanced 5400K studio lighting, 80mm f/11 medium-format clarity.\n"
            f"Avoid: collage, text, watermarks, CGI plastic look{', shadows, reflections, room interior' if white_bg_enabled else ''}{fab_neg}{profile['neg_add']}."
        )

        prompt_mj = (
            f"Commercial luxury product photography of {furn_item}, {angle_desc}, {geom_struct}, {mat_dal}, "
            f"{'isolated on pure solid white background #FFFFFF RGB 255 255 255, 0% shadows, 2054x2054, ' if white_bg_enabled else 'clean neutral studio, '}"
            f"80mm lens f/11 5400K studio lighting --ar 1:1 --v 6.1 --style raw "
            f"--no collage, text, watermark, CGI, tiled background{', shadow, reflection, room' if white_bg_enabled else ''}"
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

    def _build_environment_item_v8(
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
        use_anchor: bool,
        medidas_texto: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
    ) -> Dict[str, Any]:
        pack = self.build_v8_reference_pack(
            mode="entorno",
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            fabric_label=fabric_label if has_fabric else "",
            fabric_filename=fabric_filename if has_fabric else "",
            wood_label=wood_label if has_wood else "",
            wood_filename=wood_filename if has_wood else "",
            tipo_mueble=furn_item,
            medidas_texto=medidas_texto,
            has_ref=has_ref,
            include_anchor=use_anchor,
        )
        slots = self._slots_from_v8_pack(pack)
        primary_furn_file = slots["primary_furn_file"]

        mat_ais, mat_dal = self._build_v8_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            slots_meta=slots,
            has_wood=has_wood,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            reframe_white_bg=False,
            is_room_scene=True,
        )
        room_intro, companions = self._build_environment_room_context(profile, furn_item, lugar_casa)
        dim_summary = profile["dimensions_rule"] or "Preserve true-to-life furniture scale relative to surrounding architecture and rugs."

        anchor_ais = ""
        if use_anchor and slots["anchor_idx"]:
            a_idx = slots["anchor_idx"]
            anchor_ais = f"\n- ANCHOR CONSISTENCY (Image {a_idx} when attached): Keep the furniture's exact silhouette, +30% multi-tone fabric, and wood finish locked to Image {a_idx}."

        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" User directives: {user_notes_clean}." if user_notes_clean else ""
        fab_neg = f", {self._fabric_negative_terms(fa, fabric_label)}" if has_fabric else ""

        prompt_ais = (
            "[V8 ARCHITECTURAL INTERIOR PHOTOGRAPHY · CLIENT HOME ENVIRONMENT (WIDE DISTANT SHOT)]\n"
            f"TASK: Photograph '{furn_item}' ('{furniture_name}') taken from Image 1 (\"{primary_furn_file}\"), placed authentically {room_intro}, "
            "captured as a wide, distant architectural interior photograph (NEVER keep tiled fabric conditioning background on walls or floors).\n\n"
            f"{slots['header_block']}\n\n"
            "ENVIRONMENT & COMPOSITION:\n"
            "- DISTANT WIDE SHOT (VISTA DE LEJOS): Shot with a 35mm wide architectural lens from across the room so the full surrounding interior space is visible.\n"
            f"- REAL-WORLD 1:1 SCALE: {dim_summary}\n"
            "- DELIBERATE CONTRASTING ROOM PALETTE: Choose wall paint, flooring, and rug tones that clearly CONTRAST with the furniture's +30% calibrated upholstery/wood so the product stands out sharply without blending into walls or rugs.\n"
            f"- AUTHENTIC CLIENT HOME STYLING: {companions}\n\n"
            "FURNITURE IDENTITY & V8 UPHOLSTERY LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY RULE: {profile['geometry_rule']}{anchor_ais}{notes_ais}\n\n"
            "LIGHTING & REALISM:\n"
            "- Soft natural morning daylight streaming through sheer floor-to-ceiling linen curtains, creating natural realistic contact shadows grounding the piece on the floor/rug.\n"
            "- Shot on medium-format 35mm lens at f/8, photorealistic residential architectural photography.\n\n"
            f"Exclude: CGI, 3D render, cartoon, distorted scale, matching wall colors that camouflage the furniture, tiled wallpaper artifacts, text, watermark{fab_neg}."
        )

        prompt_dal = (
            f"Wide-angle distant architectural interior photograph of a luxury client residence ({room_intro}), featuring the exact {furn_item} ('{furniture_name}') from Image 1 (\"{primary_furn_file}\").\n"
            f"{slots['dal_photo_map']}\n"
            f"Scale & Placement: {dim_summary} {companions}\n"
            "Contrast Mandate: Surrounding walls, rug, and floor use complementary tones that deliberately contrast with the furniture.\n"
            f"Materials & Structure: {mat_dal} {profile['geometry_rule']}{notes_dal}\n"
            "Lighting: Soft natural daylight through sheer linen drapes, gentle natural room grounding shadows, 35mm architectural lens.\n"
            f"Avoid: tight close-up, distorted scale, camouflaged colors, tiled fabric background, CGI look, text, watermark{fab_neg}."
        )

        prompt_mj = (
            f"Wide-angle distant architectural interior photograph, {furn_item} {room_intro}, {mat_dal}, "
            "contrasting architectural walls and woven wool rug, natural morning daylight through sheer linen curtains, "
            "35mm architectural lens f/8, photorealistic editorial interior --ar 16:9 --v 6.1 --style raw "
            "--no close-up, CGI, distorted scale, tiled background, text, watermark"
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

    def _build_material_swap_item_v8(
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
        camera_angle: str = "",
        medidas_texto: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
        has_wood: bool = True,
        has_fabric: bool = True,
        has_ref: bool = False,
    ) -> Dict[str, Any]:
        eff_has_wood = bool(has_wood and (wa or wood_label or wood_filename)) and material_mode in ("wood_only", "dual")
        eff_has_fabric = bool(has_fabric and (fa or fabric_label or fabric_filename)) and material_mode in ("fabric_only", "dual")

        pack = self.build_v8_reference_pack(
            mode="material",
            material_mode=material_mode,
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            fabric_label=fabric_label if eff_has_fabric else "",
            fabric_filename=fabric_filename if eff_has_fabric else "",
            wood_label=wood_label if eff_has_wood else "",
            wood_filename=wood_filename if eff_has_wood else "",
            tipo_mueble=furn_item,
            medidas_texto=medidas_texto,
            has_ref=has_ref,
        )
        slots = self._slots_from_v8_pack(pack)
        primary_furn_file = slots["primary_furn_file"]
        furn_ref = f'Image {slots["primary_furn_idx"]} ("{primary_furn_file}")'

        mat_ais, mat_dal = self._build_v8_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            slots_meta=slots,
            has_wood=eff_has_wood,
            has_fabric=eff_has_fabric,
            fabric_label=fabric_label if eff_has_fabric else "",
            reframe_white_bg=white_bg_enabled,
            is_room_scene=False,
        )

        cam_lock = (camera_angle or "").strip() or "the exact same camera angle as Image 1"
        dim_line = f" SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        mirror_line = f" {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        ref_ais = (
            f"\n- AUXILIARY ANGLE REFERENCE (Image {slots['ref_idx']}): Use Image {slots['ref_idx']} for supplementary structural angle details."
            if slots.get("ref_idx")
            else ""
        )
        ref_dal = f" Use Image {slots['ref_idx']} for supplementary structural angle details." if slots.get("ref_idx") else ""
        notes_ais = f"\n\nUSER SPECIAL DIRECTIVES: {user_notes_clean}" if user_notes_clean else ""
        notes_dal = f" Mandatory user directives: {user_notes_clean}." if user_notes_clean else ""

        if white_bg_enabled:
            no_tile_ais = " CRITICAL: NEVER keep tiled fabric background in output!" if eff_has_fabric else ""
            no_tile_dal = " (NEVER keep tiled fabric background)" if eff_has_fabric else ""
            scene_str = (
                f"Strictly preserve the exact shape, 3D structural geometry ({geom_struct}), contours, seams, piping, folds, and proportions of {furn_ref}. "
                f"{profile['geometry_rule']}{dim_line}{mirror_line} "
                f"CAMERA CONSTRAINT: Lock the camera angle strictly to {cam_lock}. "
                "COMMERCIAL OUTPUT RE-FRAMING & #FFFFFF ISOLATION: Re-frame the finished furniture to commercial catalog scale (~74% of canvas, exact 2054 x 2054 px) "
                "on a 100% pure seamless solid white background (#FFFFFF, RGB 255,255,255) with 0% ground shadow, 0% contact shadow under legs, 0% drop shadow, and 0% floor reflections."
                f"{no_tile_ais}"
            )
            bg_neg = "shadows, drop shadows, contact shadows, ground shadows, floor reflections, dark background, grey background, room environment,"
            if eff_has_fabric:
                bg_neg = "tiled background, mosaic wallpaper, " + bg_neg
            bg_dal = f"pure seamless solid white background (#FFFFFF, RGB 255,255,255) at exact 2054 x 2054 px with 0% ground/contact/drop shadows and 0% reflections{no_tile_dal}"
        else:
            no_tile_scene = " (NEVER keep tiled fabric conditioning mosaic in output)" if eff_has_fabric else ""
            scene_str = (
                f"Strictly preserve the exact shape, structural geometry ({geom_struct}), contours, seams, piping, folds, lighting, and original background of {furn_ref}{no_tile_scene}. "
                f"{profile['geometry_rule']}{dim_line}{mirror_line} "
                f"CAMERA CONSTRAINT: Lock the camera angle strictly to {cam_lock}."
            )
            bg_neg = ("tiled fabric background, mosaic wallpaper, " if eff_has_fabric else "") + "changed camera angle,"
            bg_dal = f"preserve original scene background from {furn_ref}" + (
                " (NEVER keep tiled fabric conditioning background)" if eff_has_fabric else ""
            )

        fab_neg = self._fabric_negative_terms(fa, fabric_label) if eff_has_fabric else "altered upholstery, flat wood colors, two-tone mismatch"

        prompt_ais = (
            f"INSTRUCTION (V8 SCALE-CONDITIONED MATERIAL ENGINE): Meticulously analyze the attached reference pack for '{furn_item}' ('{furniture_name}').\n\n"
            f"{slots['header_block']}\n\n"
            f"GENERATE: Produce a photorealistic 2054 x 2054 px commercial catalog render of {furn_ref} applying the exact V8 material locks below.\n\n"
            f"GEOMETRY, CAMERA & #FFFFFF SCENE CONSTRAINT:\n{scene_str}\n\n"
            f"V8 MATERIAL, 1:1 SCALE & CASCO LOCK:\n{mat_ais}{ref_ais}{notes_ais}\n\n"
            f"Negative Prompt:\n"
            f"{fab_neg}, altered wood legs, text, watermark, poster, collage, infographic, multiple furniture pieces, {bg_neg}{profile['neg_add']}"
        )

        prompt_dal = (
            f"Precision V8 material-swap 2054 x 2054 px commercial photograph of the exact {furn_item} ('{furniture_name}') from {furn_ref} (camera lock: {cam_lock}).\n"
            f"{slots['dal_photo_map']}\n"
            f"Materials: {mat_dal}\n"
            f"Structure & Draping: Preserve exact contours, seams, piping, and folds. {profile['geometry_rule']} {profile['dimensions_rule']}{ref_dal}{notes_dal}\n"
            f"Background: {bg_dal}.\n"
            f"Avoid: {fab_neg}, altered geometry, perspective distortion, text, watermark{profile['neg_add']}."
        )

        prompt_mj = (
            f"Commercial catalog photography of {furn_item}, {geom_struct}, {mat_dal}, "
            f"{'pure solid white background #FFFFFF RGB 255 255 255, 0% shadows, 2054x2054, ' if white_bg_enabled else ''}"
            f"--ar 1:1 --v 6.1 --style raw --no {fab_neg}, text, watermark"
        )

        return {
            "id": "material",
            "label": "🎨 Cambio de Material V8",
            "short_name": "Material",
            "icon": "🎨",
            "google_ai_studio": prompt_ais,
            "chatgpt_dalle3": prompt_dal,
            "midjourney_v6": prompt_mj,
            "checklist": CHECKLISTS["material"],
            "needs_anchor": False,
            "attachment_guide": slots["guide"],
        }

    def _build_extraction_item_v8(
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
        medidas_texto: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
        has_ref: bool = False,
    ) -> Dict[str, Any]:
        pack = self.build_v8_reference_pack(
            mode="extraer",
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            fabric_label=fabric_label if has_fabric else "",
            fabric_filename=fabric_filename if has_fabric else "",
            wood_label=wood_label if has_wood else "",
            wood_filename=wood_filename if has_wood else "",
            tipo_mueble=furn_item,
            medidas_texto=medidas_texto,
            has_ref=has_ref,
        )
        slots = self._slots_from_v8_pack(pack)
        primary_furn_file = slots["primary_furn_file"]

        mat_ais, mat_dal = self._build_v8_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            slots_meta=slots,
            has_wood=has_wood,
            has_fabric=has_fabric,
            fabric_label=fabric_label,
            reframe_white_bg=True,
            is_room_scene=False,
        )
        ref_ais = (
            f"\n- AUXILIARY ANGLE REFERENCE (Image {slots['ref_idx']}): Supplementary structural angle details from Image {slots['ref_idx']}."
            if slots.get("ref_idx")
            else ""
        )
        ref_dal = f" Use Image {slots['ref_idx']} for supplementary structural angle details." if slots.get("ref_idx") else ""
        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        fab_neg = f", {self._fabric_negative_terms(fa, fabric_label)}" if has_fabric else ""

        prompt_ais = (
            "[V8 ISOLATED COMMERCIAL PRODUCT CUTOUT · PURE WHITE #FFFFFF · 0% SHADOWS · 2054x2054 PX]\n"
            f"TASK: Cleanly extract and isolate '{furn_item}' ('{furniture_name}') taken from Image 1 (\"{primary_furn_file}\") onto pure solid white (#FFFFFF, RGB 255,255,255) at 2054 x 2054 px.\n\n"
            f"{slots['header_block']}\n\n"
            "ISOLATION & COMMERCIAL RE-FRAMING:\n"
            "- POSITION & RESOLUTION: Exact 2054 x 2054 px square canvas; place the single furniture piece dead-center occupying ~74% of the frame with clean balanced margins.\n"
            "- BACKGROUND: Pure seamless solid digital white (#FFFFFF, RGB 255,255,255). 0% ground shadow, 0% drop shadow, 0% contact shadow, 0% floor reflections"
            + (" (NEVER keep tiled fabric background in output).\n" if has_fabric else ".\n")
            + "- NO PROPS: Remove all walls, floors, rugs, and background clutter completely.\n\n"
            "V8 MATERIAL & GEOMETRY LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY LOCK: {profile['geometry_rule']}{dim_ais}{mirror_ais}{ref_ais}{notes_ais}\n"
            "- OPTICS: 100MP medium-format 80mm f/11 crisp edges and authentic micro-texture.\n\n"
            f"Exclude: ground shadows, floor shadows, drop shadows, contact shadows, reflections, grey floor, room, props, text, watermark{fab_neg}{profile['neg_add']}."
        )

        prompt_dal = (
            f"Clean 2054 x 2054 px commercial cutout of the exact {furn_item} ('{furniture_name}') from Image 1 (\"{primary_furn_file}\"), "
            "centered at ~74% commercial scale on pure solid white (#FFFFFF, RGB 255,255,255) with 0% ground/contact/drop shadows and 0% reflections.\n"
            f"{slots['dal_photo_map']}\n"
            f"Materials: {mat_dal}\n"
            f"Geometry: {profile['geometry_rule']} {profile['dimensions_rule']}{ref_dal}\n"
            f"{'User directives: ' + user_notes_clean if user_notes_clean else ''}\n"
            f"Avoid: shadows, grey backdrop, room, altered geometry, text, watermark{fab_neg}."
        )

        prompt_mj = (
            f"Isolated commercial product cutout of {furn_item}, centered on pure seamless solid white background #FFFFFF RGB 255 255 255, "
            f"0% shadows, 2054x2054, {geom_struct}, {mat_dal}, 80mm f/11 --ar 1:1 --v 6.1 --style raw --no shadow, floor, wall, room, text"
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

    def _build_hd_item_v8(
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
        medidas_texto: str = "",
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
        is_material_swatch: bool = False,
        has_ref: bool = False,
    ) -> Dict[str, Any]:
        if is_material_swatch:
            return super()._build_hd_item(
                furn_item=furn_item,
                furniture_name=furniture_name,
                profile=profile,
                geom_struct=geom_struct,
                existing_mats=existing_mats,
                wa=wa,
                fa=fa,
                has_wood=has_wood,
                has_fabric=has_fabric,
                wood_label=wood_label,
                fabric_label=fabric_label,
                user_notes_clean=user_notes_clean,
                white_bg_enabled=white_bg_enabled,
                classic_numbering=False,
                furniture_filenames=furniture_filenames,
                wood_filename=wood_filename,
                fabric_filename=fabric_filename,
                is_material_swatch=True,
            )

        pack = self.build_v8_reference_pack(
            mode="hd",
            furniture_name=furniture_name,
            furniture_filenames=furniture_filenames,
            fabric_label=fabric_label if has_fabric else "",
            fabric_filename=fabric_filename if has_fabric else "",
            wood_label=wood_label if has_wood else "",
            wood_filename=wood_filename if has_wood else "",
            tipo_mueble=furn_item,
            medidas_texto=medidas_texto,
            has_ref=has_ref,
        )
        slots = self._slots_from_v8_pack(pack)
        primary_furn_file = slots["primary_furn_file"]

        if has_wood or has_fabric:
            mat_ais, mat_dal = self._build_v8_material_lock_text(
                profile=profile,
                furn_item=furn_item,
                existing_mats=existing_mats,
                wa=wa,
                fa=fa,
                slots_meta=slots,
                has_wood=has_wood,
                has_fabric=has_fabric,
                fabric_label=fabric_label,
                reframe_white_bg=white_bg_enabled,
                is_room_scene=False,
            )
        else:
            mat_ais = (
                f'- ORIGINAL SURFACE & MATERIAL LOCK (from Image 1 ("{primary_furn_file}")): Faithfully preserve ONLY the exact '
                f"authentic materials, textures, colors, and surface finishes visible in Image 1 ({existing_mats}) with 0% color shift."
            )
            mat_dal = f'Faithfully preserve ONLY the authentic materials and tones visible in Image 1 ("{primary_furn_file}") ({existing_mats}).'

        no_tile_hd = " (NEVER keep tiled fabric background in output)" if has_fabric else ""
        bg_line = (
            f"Pure seamless solid white catalog studio background (#FFFFFF, RGB 255,255,255) with 0% ground/contact/drop shadows, exact 2054 x 2054 px{no_tile_hd}."
            if white_bg_enabled
            else (
                f'Preserve the exact original background, scene lighting, and framing from Image 1 ("{primary_furn_file}") '
                + (
                    "(if Image 1 already has a white studio background, keep pure solid #FFFFFF; NEVER keep tiled fabric conditioning background in output) while upgrading sharpness to 8K."
                    if has_fabric
                    else "(if Image 1 already has a white studio background, keep pure solid #FFFFFF) while upgrading sharpness to 8K."
                )
            )
        )
        ref_ais = (
            f"\n- AUXILIARY ANGLE REFERENCE (Image {slots['ref_idx']}): Supplementary structural angle details from Image {slots['ref_idx']}."
            if slots.get("ref_idx")
            else ""
        )
        ref_dal = f" Use Image {slots['ref_idx']} for supplementary structural angle details." if slots.get("ref_idx") else ""
        notes_ais = f"\n- MANDATORY USER NOTES: {user_notes_clean}" if user_notes_clean else ""
        dim_ais = f"\n- SCALE & PROPORTIONS: {profile['dimensions_rule']}" if profile["dimensions_rule"] else ""
        mirror_ais = f"\n- {profile['mirror_optics']}" if profile["mirror_optics"] else ""
        fab_neg = f", {self._fabric_negative_terms(fa, fabric_label)}" if has_fabric else ""

        prompt_ais = (
            "[V8 8K ULTRA-HD COMMERCIAL RESTORATION · ZERO GEOMETRY DRIFT]\n"
            f"TASK: Remaster '{furn_item}' ('{furniture_name}') taken from Image 1 (\"{primary_furn_file}\") into ultra-sharp 8K medium-format clarity.\n\n"
            f"{slots['header_block']}\n\n"
            "CLARITY & RESTORATION:\n"
            "- ELIMINATE ARTIFACTS: Remove pixelation, blur, compression noise, and softness completely.\n"
            "- MACRO TEXTURE: Reconstruct crisp woven yarn threads, raised multi-tone figures, seam stitching, and wood grain pores at f/11 focus.\n\n"
            "STRICT PRESERVATION & V8 MATERIAL LOCK:\n"
            f'- STRICT 1:1 SUBJECT LOCK: Enhance ONLY what actually exists inside Image 1 ("{primary_furn_file}"). NEVER invent new furniture parts or props.\n'
            f"{mat_ais}\n"
            f"- GEOMETRY LOCK: {profile['geometry_rule']}{dim_ais}{mirror_ais}{ref_ais}{notes_ais}\n"
            f"- BACKGROUND: {bg_line}\n\n"
            f"Exclude: blurry, pixelated, jpeg artifacts, plastic smoothing, redesigned silhouette, invented furniture parts, CGI look, text, watermark{fab_neg}{profile['neg_add']}."
        )

        prompt_dal = (
            f"8K Ultra-HD 1:1 photographic remaster of the exact {furn_item} ('{furniture_name}') taken from Image 1 (\"{primary_furn_file}\").\n"
            f"{slots['dal_photo_map']}\n"
            "Enhance ONLY what exists inside Image 1 — remove blur and compression while preserving exact geometry.\n"
            f"Materials: {mat_dal}\n"
            f"Geometry: {profile['geometry_rule']} {profile['dimensions_rule']}{ref_dal}\n"
            f"Background: {bg_line}\n"
            f"Avoid: blur, pixelation, plastic smoothing, text, watermark{fab_neg}."
        )

        prompt_mj = (
            f"8k ultra-sharp commercial product restoration of {furn_item}, {geom_struct}, {mat_dal}, "
            f"{'pure white background #FFFFFF RGB 255 255 255, 0% shadows, 2054x2054, ' if white_bg_enabled else 'exact original framing and background, '}"
            "80mm f/11 --ar 1:1 --v 6.1 --style raw --no blur, pixelated, text, watermark"
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

    def _generate_batch_view_prompt_v8(
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
    ) -> Tuple[Dict[str, str], List[str]]:
        dims_part = f"\n- REAL-WORLD SCALE: {medidas_texto}" if medidas_texto else ""
        notes_part = f"\n- MANDATORY NOTES: {user_notes_clean}" if user_notes_clean else ""

        if batch_mode == "clonar_color":
            pack_cc = self.build_v8_reference_pack(
                mode="clonar_color",
                batch_ref_filename=ref_filename or ref_label,
                batch_ref_bytes=ref_bytes,
                target_view=(view_name, view_bytes),
            )
            slots_cc = self._slots_from_v8_pack(pack_cc)
            ref_file_cc = pack_cc[0]["filename"] if pack_cc else "referencia_color.png"
            view_file_cc = pack_cc[1]["filename"] if len(pack_cc) > 1 else self._canonical_photo_filename(view_name, "vista.png")

            view_cam_cc = "the exact same camera angle and framing as Image 2"
            view_geom_cc = "the exact 3D silhouette, contours, joinery, seams, and proportions"
            key_cc = self.get_api_key(api_key)
            if key_cc and view_bytes and len(view_bytes) >= 64:
                try:
                    v_ana_cc = self.analyze_furniture_for_enhancement(view_bytes, api_key=key_cc)
                    if v_ana_cc.get("camera_angle") and "reference angle" not in str(v_ana_cc.get("camera_angle", "")).lower():
                        view_cam_cc = str(v_ana_cc["camera_angle"]).strip()
                    if v_ana_cc.get("geometric_structure") and "attached photo" not in str(v_ana_cc.get("geometric_structure", "")).lower():
                        view_geom_cc = str(v_ana_cc["geometric_structure"]).strip()
                except Exception:
                    pass

            bg_clause_cc = (
                "pure seamless solid white background (#FFFFFF, RGB 255,255,255) at exact 2054 x 2054 px with 0% ground shadow, 0% contact shadow, 0% drop shadow, and 0% floor reflections"
                if white_bg_enabled
                else f'the exact original background and natural lighting of Image 2 ("{view_file_cc}")'
            )
            local_ais_cc = (
                f"[V8 BATCH VIEW COLOR & FINISH CLONE · {'2054x2054 PX · ' if white_bg_enabled else ''}{view_file_cc}]\n"
                f'TASK: Clone the exact color, wood/fabric finish, and surface micro-texture from Image 1 ("{ref_file_cc}") onto the furniture \'{furn_item}\' in Image 2 ("{view_file_cc}").\n\n'
                f"{slots_cc['header_block']}\n\n"
                "RULES:\n"
                f'- Transfer Image 1 ("{ref_file_cc}") exact hue, undertone, grain/weave texture, and sheen onto Image 2 ("{view_file_cc}") cleanly with 0% hue or brightness drift.\n'
                f'- Strictly preserve Image 2 ("{view_file_cc}") camera angle ({view_cam_cc}) and physical 3D geometry ({view_geom_cc}).\n'
                f"- BACKGROUND & RESOLUTION: {bg_clause_cc}.{dims_part}{notes_part}\n\n"
                "Exclude: repeating Image 1's camera angle, altered silhouette, mismatched tone, shadows, reflections, text, watermark."
            )
            local_dal_cc = (
                f'Precision V8 batch color & finish clone on target view Image 2 ("{view_file_cc}" — {furn_item}, camera lock: {view_cam_cc}).\n'
                f"{slots_cc['dal_photo_map']}\n"
                f'Transfer exact hue, texture, and finish from Image 1 ("{ref_file_cc}") onto Image 2 ("{view_file_cc}") with 0% color shift.\n'
                f"Background: {bg_clause_cc}.{dims_part}{notes_part}\n"
                "Avoid: altered camera angle, altered silhouette, shadows, reflections, text, watermark."
            )
            local_mj_cc = (
                f"Commercial product photography of {furn_item}, {view_cam_cc}, exact color and finish match, "
                f"{'pure white background #FFFFFF RGB 255 255 255, 0% shadows, 2054x2054, ' if white_bg_enabled else ''}"
                "80mm f/11 --ar 1:1 --v 6.1 --style raw --no altered angle, shadows, reflections, text, watermark"
            )
            return (
                {"google_ai_studio": local_ais_cc, "chatgpt_dalle3": local_dal_cc, "midjourney_v6": local_mj_cc},
                slots_cc["guide"],
            )

        # Modo vistas_tela en V8 con paquete sincronizado (3 ranuras con tela; 1 ranura si no se adjuntó tela)
        fa = fabric_analysis or {}
        has_fab_vt = bool(ref_bytes or ref_label or ref_filename or fa)
        pack = self.build_v8_reference_pack(
            mode="vistas_tela",
            fabric_label=ref_label if has_fab_vt else "",
            fabric_filename=(ref_filename or ref_label) if has_fab_vt else "",
            fabric_bytes=ref_bytes if (has_fab_vt and ref_bytes) else None,
            target_view=(view_name, view_bytes),
            tipo_mueble=furn_item,
            medidas_texto=medidas_texto,
        )
        slots = self._slots_from_v8_pack(pack)
        view_file = slots["primary_furn_file"]

        view_cam = "the exact same camera angle and perspective as Image 1"
        view_geom = "the exact 3D silhouette, contours, seams, piping, and folds"
        key = self.get_api_key(api_key)
        if key and view_bytes and len(view_bytes) >= 64:
            try:
                v_ana = self.analyze_furniture_for_enhancement(view_bytes, api_key=key)
                if v_ana.get("camera_angle") and "reference angle" not in str(v_ana.get("camera_angle", "")).lower():
                    view_cam = str(v_ana["camera_angle"]).strip()
                if v_ana.get("geometric_structure") and "attached photo" not in str(v_ana.get("geometric_structure", "")).lower():
                    view_geom = str(v_ana["geometric_structure"]).strip()
            except Exception:
                pass

        if slots.get("canvas_idx") and slots.get("fabric_idx"):
            c_idx = slots["canvas_idx"]
            f_idx = slots["fabric_idx"]
            fab_ais, fab_dal = self._build_v8_fabric_mandate_blocks(
                fa=fa,
                fabric_label=ref_label,
                canvas_idx=c_idx,
                canvas_file=slots.get("canvas_file", ""),
                swatch_idx=f_idx,
                swatch_file=slots.get("fabric_file", ""),
                total_tiles=slots.get("total_tiles", 196),
                protect_non_upholstered_from=f'Image 1 ("{view_file}")',
                reframe_white_bg=white_bg_enabled,
                is_room_scene=False,
            )
            fab_neg = self._fabric_negative_terms(fa, ref_label)
            bg_clause = (
                "pure seamless solid white background (#FFFFFF, RGB 255,255,255) at exact 2054 x 2054 px with 0% ground shadow, 0% contact shadow, 0% drop shadow, and 0% floor reflections (NEVER keep tiled fabric background in output)"
                if white_bg_enabled
                else f'preserve original scene background of Image 1 ("{view_file}") (NEVER keep tiled fabric conditioning background in output)'
            )
            local_ais = (
                f"INSTRUCTION (V8 BATCH MULTI-VIEW UPHOLSTERY ENGINE): Analyze target furniture view Image 1 (\"{view_file}\" — '{furn_item}'), "
                f'V8 scale conditioning canvas Image {c_idx} ("{slots["canvas_file"]}"), and V8 +30% calibrated swatch Image {f_idx} ("{slots["fabric_file"]}").\n\n'
                f"{slots['header_block']}\n\n"
                f'GENERATE: Completely erase 100% of the old upholstery color/fabric on Image 1 ("{view_file}") and wrap 100% of EL CASCO COMPLETO and all cushions '
                "in the V8 +30% calibrated multi-tone fabric at exact 1:1 miniature scale.\n\n"
                f'GEOMETRY & SCENE CONSTRAINT: Lock exact camera angle ({view_cam}), 3D shape ({view_geom}), seams, piping, folds, and exposed wood/metal legs from Image 1 ("{view_file}"). '
                f"ENVIRONMENT: {bg_clause}.{dims_part}{notes_part}\n\n"
                f"V8 SCALE, +30% CALIBRATION & MULTI-TONE CASCO LOCK:\n{fab_ais}\n\n"
                f"Negative Prompt:\n{fab_neg}, altered camera angle, altered wood legs, text, watermark, collage."
            )
            local_dal = (
                f'Precision V8 upholstery replacement on target view Image 1 ("{view_file}" — {furn_item}, camera lock: {view_cam}).\n'
                f"{slots['dal_photo_map']}\n"
                f"Materials: {fab_dal}.\n"
                f"Environment: {bg_clause}.{dims_part}{notes_part}\n"
                f"Avoid: {fab_neg}, altered camera angle, altered wood legs, text, watermark, collage."
            )
            local_mj = (
                f"Commercial product photography of {furn_item}, {view_cam}, {fab_dal}, "
                f"{'pure white background #FFFFFF RGB 255 255 255, 0% shadows, 2054x2054, ' if white_bg_enabled else ''}"
                f"80mm f/11 --ar 1:1 --v 6.1 --style raw --no {fab_neg}, altered angle, text, watermark"
            )
        else:
            bg_clause = (
                "pure seamless solid white background (#FFFFFF, RGB 255,255,255) at exact 2054 x 2054 px with 0% ground shadow, 0% contact shadow, 0% drop shadow, and 0% floor reflections"
                if white_bg_enabled
                else f'preserve original scene background of Image 1 ("{view_file}")'
            )
            local_ais = (
                f"INSTRUCTION (V8 BATCH MULTI-VIEW STUDIO ENGINE): Analyze target furniture view Image 1 (\"{view_file}\" — '{furn_item}').\n\n"
                f"{slots['header_block']}\n\n"
                f'GENERATE: Render target view Image 1 ("{view_file}") preserving its exact authentic upholstery, wood/metal legs, camera angle ({view_cam}), and 3D shape ({view_geom}).\n\n'
                f"ENVIRONMENT: {bg_clause}.{dims_part}{notes_part}\n\n"
                "Negative Prompt:\naltered camera angle, altered upholstery, altered wood legs, shadows, reflections, text, watermark, collage."
            )
            local_dal = (
                f'Commercial studio photograph of target view Image 1 ("{view_file}" — {furn_item}, camera lock: {view_cam}).\n'
                f"{slots['dal_photo_map']}\n"
                f'Preserve authentic materials and geometry from Image 1 ("{view_file}").\n'
                f"Environment: {bg_clause}.{dims_part}{notes_part}\n"
                "Avoid: altered camera angle, shadows, reflections, text, watermark, collage."
            )
            local_mj = (
                f"Commercial product photography of {furn_item}, {view_cam}, authentic upholstery and timber, "
                f"{'pure white background #FFFFFF RGB 255 255 255, 0% shadows, 2054x2054, ' if white_bg_enabled else ''}"
                "80mm f/11 --ar 1:1 --v 6.1 --style raw --no altered angle, shadows, text, watermark"
            )
        return (
            {"google_ai_studio": local_ais, "chatgpt_dalle3": local_dal, "midjourney_v6": local_mj},
            slots["guide"],
        )

    # ------------------------------------------------------------------
    # PUNTO DE ENTRADA ÚNICO V8 (9 MODOS + 3/4 DERECHA 2054x2054)
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
        material_mode: str = "fabric_only",
        wood_label: str = "",
        fabric_label: str = "",
        has_reference_imgs: bool = False,
        white_bg_enabled: bool = True,
        classic_numbering: bool = False,
        batch_ref_bytes: Optional[bytes] = None,
        batch_views: Optional[List[Tuple[str, bytes]]] = None,
        api_key: Optional[str] = None,
        furniture_filenames: Optional[List[str]] = None,
        wood_filename: str = "",
        fabric_filename: str = "",
        batch_ref_filename: str = "",
    ) -> Dict[str, Any]:
        _ = classic_numbering
        if mode not in MODES:
            raise ValueError(f"Modo V8 desconocido: {mode}")

        ma = furniture_analysis or {}
        wa = wood_analysis or {}
        fa = dict(fabric_analysis or {})

        if batch_ref_bytes and mode == "vistas_tela" and not fa:
            fa = self.analyze_fabric_v8_local(batch_ref_bytes, sample_name=fabric_filename or fabric_label)

        primary_fn_hint = (
            (furniture_filenames[0] if furniture_filenames else "")
            or (batch_views[0][0] if batch_views else "")
        )
        ai_item_raw = str(ma.get("furniture_item") or "").strip()
        ai_item_eff = ai_item_raw if bool(ma.get("is_material_swatch")) else clean_v8_ai_furniture_item(ai_item_raw)
        type_hint = resolve_v8_furniture_type_hint(
            tipo_mueble=tipo_mueble,
            ai_furniture_item=ai_item_eff,
            furniture_name=furniture_name,
            primary_filename=primary_fn_hint,
        )
        furn_item = (tipo_mueble or "").strip() or ai_item_eff or type_hint or furniture_name or "Furniture Piece"
        geom_struct = ma.get("geometric_structure") or "exact 3D silhouette, proportions, and joinery from the reference"
        existing_mats = ma.get("existing_materials") or "authentic materials, tones, and finishes from the reference"
        user_notes_clean = (notas_usuario or "").strip()

        profile_search = f"{furn_item} {type_hint} {furniture_name} {primary_fn_hint} {medidas_texto} {user_notes_clean}"
        profile = self.detect_furniture_profile(type_hint or furn_item, profile_search, geom_struct)

        has_wood = bool(wa) or bool(wood_label) or bool(wood_filename)
        has_fabric = bool(fa) or bool(fabric_label) or bool(fabric_filename)
        w_label = (wood_label or wood_filename or wa.get("name") or "Muestra de madera") if has_wood else ""
        f_label = (fabric_label or fabric_filename or fa.get("name") or "Muestra de tela") if has_fabric else ""
        w_file_arg = (wood_filename or wood_label or w_label) if has_wood else ""
        f_file_arg = (fabric_filename or fabric_label or f_label) if has_fabric else ""

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
                        self._build_environment_item_v8(
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
                            use_anchor=True,
                            medidas_texto=medidas_texto,
                            furniture_filenames=furniture_filenames,
                            wood_filename=w_file_arg,
                            fabric_filename=f_file_arg,
                        )
                    )
                else:
                    items.append(
                        self._build_single_studio_view_prompt_v8(
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
                            use_anchor=(vid != "vista_frontal"),
                            medidas_texto=medidas_texto,
                            furniture_filenames=furniture_filenames,
                            wood_filename=w_file_arg,
                            fabric_filename=f_file_arg,
                        )
                    )

            pack_master = self.build_v8_reference_pack(
                mode="catalogo",
                furniture_name=furniture_name,
                furniture_filenames=furniture_filenames,
                fabric_label=f_label if has_fabric else "",
                fabric_filename=f_file_arg if has_fabric else "",
                wood_label=w_label if has_wood else "",
                wood_filename=w_file_arg if has_wood else "",
                tipo_mueble=furn_item,
                medidas_texto=medidas_texto,
                has_ref=has_reference_imgs,
                include_anchor=False,
            )
            slots_master = self._slots_from_v8_pack(pack_master)
            primary_furn_file = slots_master["primary_furn_file"]
            mat_ais, mat_dal = self._build_v8_material_lock_text(
                profile=profile,
                furn_item=furn_item,
                existing_mats=existing_mats,
                wa=wa,
                fa=fa,
                slots_meta=slots_master,
                has_wood=has_wood,
                has_fabric=has_fabric,
                fabric_label=f_label,
                reframe_white_bg=True,
                is_room_scene=False,
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
                "[V8 COMMERCIAL 7-IMAGE CATALOG SERIES · TURN-BY-TURN SEQUENTIAL GENERATION]\n"
                f"TASK: Generate a complete 7-piece commercial catalog sequence for '{furn_item}' ('{furniture_name}') taken from Image 1 (\"{primary_furn_file}\"): "
                "5 studio cutouts on pure white (#FFFFFF, RGB 255,255,255, 0% shadows, 2054 x 2054 px), 1 isometric technical CAD blueprint, and 1 wide client home interior photo.\n\n"
                f"{slots_master['header_block']}\n\n"
                "FROZEN IDENTITY & V8 MATERIALS:\n"
                f"{mat_ais}\n"
                f"- GEOMETRY RULE: {profile['geometry_rule']}{dim_line}{mirror_line}{notes_block}\n\n"
                "STUDIO STANDARDS (VIEWS 1 TO 6):\n"
                "- Pure seamless solid white background (#FFFFFF, RGB 255,255,255), 0% ground shadows, 0% contact shadows, 0% drop shadows, 0% reflections (NEVER keep tiled fabric background in output).\n"
                "- Views 1–5: 100MP medium-format 80mm f/11 commercial photography, re-framed at ~74% of 2054 x 2054 px canvas.\n\n"
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
                f"  6. Vista 6 (Plano Técnico Isométrico): Minimalist black (#000000) CAD line art only on #FFFFFF, zero color/shading/fabric, showing ONLY: {dims_summary}.\n"
                f"  7. Vista 7 (Entorno Casa Cliente): Wide distant 35mm interior shot {room_intro}; {companions} Deliberate contrasting room palette (no tiled wall artifacts).\n\n"
                f"Exclude: collage, text/watermarks, ground shadows in views 1-6, CGI plastic sheen{fab_neg_master}{profile['neg_add']}."
            )

            master_dal = (
                f"Generate 7 separate standalone 2054 x 2054 px commercial images in sequence (no collage) for '{furn_item}' ('{furniture_name}') from Image 1 (\"{primary_furn_file}\"):\n"
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
                "Views 1–6 on pure solid white #FFFFFF (RGB 255,255,255) with 0% ground/contact/drop shadows (NEVER keep tiled fabric background in output)."
            )
            midjourney = items[0]["midjourney_v6"] if items else ""

        elif mode == "vista_suelta":
            if vista_id not in ALL_SINGLE_VIEWS:
                vista_id = "vista_frontal"
            if vista_id == "vista_plano_tecnico":
                it = self._build_blueprint_item(
                    furn_item, furniture_name, profile, medidas_texto, user_notes_clean,
                    furniture_filenames=furniture_filenames,
                )
            elif vista_id == "vista_entorno_cliente":
                it = self._build_environment_item_v8(
                    furn_item, furniture_name, profile, geom_struct, existing_mats,
                    wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                    lugar_casa, user_notes_clean, use_anchor=True, medidas_texto=medidas_texto,
                    furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                )
            else:
                it = self._build_single_studio_view_prompt_v8(
                    vista_id, furn_item, furniture_name, profile, geom_struct, existing_mats,
                    wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                    user_notes_clean, white_bg_enabled, use_anchor=(vista_id in ANCHOR_VIEWS),
                    medidas_texto=medidas_texto,
                    furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "material":
            it = self._build_material_swap_item_v8(
                material_mode, furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, w_label, f_label, user_notes_clean, white_bg_enabled,
                camera_angle=ma.get("camera_angle", ""), medidas_texto=medidas_texto,
                furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                has_wood=has_wood, has_fabric=has_fabric, has_ref=has_reference_imgs,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        elif mode == "entorno":
            it = self._build_environment_item_v8(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, has_reference_imgs, w_label, f_label,
                lugar_casa, user_notes_clean, use_anchor=False, medidas_texto=medidas_texto,
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
            it = self._build_extraction_item_v8(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, w_label, f_label, user_notes_clean,
                medidas_texto=medidas_texto,
                furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                has_ref=has_reference_imgs,
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
            it = self._build_hd_item_v8(
                furn_item, furniture_name, profile, geom_struct, existing_mats,
                wa, fa, has_wood, has_fabric, w_label, f_label,
                user_notes_clean, white_bg_enabled, medidas_texto=medidas_texto,
                furniture_filenames=furniture_filenames, wood_filename=w_file_arg, fabric_filename=f_file_arg,
                is_material_swatch=is_hd_swatch, has_ref=has_reference_imgs,
            )
            items = [it]
            midjourney = it.get("midjourney_v6", "")

        else:  # vistas_tela | clonar_color
            views = batch_views or []
            if not views:
                raise ValueError("Sube al menos una vista objetivo para procesar el lote.")
            ref_b = batch_ref_bytes or b""
            if mode == "vistas_tela":
                has_fab_vt = bool(has_fabric or batch_ref_bytes or batch_ref_filename)
                ref_lbl = f_label if has_fab_vt else ""
                ref_fname = (f_file_arg or batch_ref_filename) if has_fab_vt else ""
                ref_file_canon = (
                    self._canonical_photo_filename(ref_fname or ref_lbl, "tela.png")
                    if has_fab_vt
                    else ""
                )
            else:
                ref_lbl = (
                    batch_ref_filename
                    or (furniture_filenames[0] if furniture_filenames else "")
                    or "Foto referencia color"
                )
                ref_fname = (
                    batch_ref_filename
                    or (furniture_filenames[0] if furniture_filenames else "")
                    or furniture_name
                )
                ref_file_canon = self._canonical_photo_filename(
                    ref_fname or ref_lbl,
                    "referencia_color.png",
                )

            def _run_v8(pair: Tuple[str, bytes]) -> Tuple[str, bytes, Dict[str, str], List[str]]:
                vname, vbytes = pair
                pdict, guide_list = self._generate_batch_view_prompt_v8(
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
                return vname, vbytes, pdict, guide_list

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                batch_results = list(executor.map(_run_v8, views))

            for idx, (vname, vbytes, pdict, guide_list) in enumerate(batch_results, start=1):
                v_file_canon = self._canonical_photo_filename(vname, f"vista_{idx}.png")
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
                    "attachment_guide": guide_list,
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
        _ = classic_numbering
        ma = furniture_analysis or {}
        wa = wood_analysis or {}
        fa = fabric_analysis or {}

        clean_base_name = os.path.splitext(str(furniture_name or "Mueble").strip())[0].strip() or "Mueble"
        out_fname = f"{clean_base_name}.png"
        primary_fn_34 = furniture_filenames[0] if furniture_filenames else ""
        ai_item_34 = clean_v8_ai_furniture_item(str(ma.get("furniture_item") or ""))
        type_hint_34 = resolve_v8_furniture_type_hint(
            tipo_mueble=tipo_mueble,
            ai_furniture_item=ai_item_34,
            furniture_name=clean_base_name,
            primary_filename=primary_fn_34,
        )
        furn_item = (tipo_mueble or "").strip() or ai_item_34 or type_hint_34 or clean_base_name or "Furniture Piece"
        geom_struct = ma.get("geometric_structure") or "exact 3D silhouette, proportions, and joinery from the reference"
        existing_mats = ma.get("existing_materials") or "authentic materials, tones, and finishes from the reference"
        user_notes_clean = (notas_usuario or "").strip()

        profile_search = f"{furn_item} {type_hint_34} {clean_base_name} {primary_fn_34} {medidas_texto} {user_notes_clean}"
        profile = self.detect_furniture_profile(type_hint_34 or furn_item, profile_search, geom_struct)

        has_wood = bool(wa) or bool(wood_label) or bool(wood_filename)
        has_fabric = bool(fa) or bool(fabric_label) or bool(fabric_filename)
        w_label = wood_label or wood_filename or wa.get("name") or "Muestra de madera"
        f_label = fabric_label or fabric_filename or fa.get("name") or "Muestra de tela"
        w_file_arg = wood_filename or wood_label
        f_file_arg = fabric_filename or fabric_label

        pack = self.build_v8_reference_pack(
            mode="vista_34_der_2054",
            furniture_name=clean_base_name,
            furniture_filenames=furniture_filenames,
            fabric_label=f_label if has_fabric else "",
            fabric_filename=f_file_arg if has_fabric else "",
            wood_label=w_label if has_wood else "",
            wood_filename=w_file_arg if has_wood else "",
            tipo_mueble=type_hint_34,
            medidas_texto=medidas_texto,
            has_ref=has_reference_imgs,
            include_anchor=False,
        )
        slots = self._slots_from_v8_pack(pack)
        primary_furn_file = slots["primary_furn_file"]

        mat_ais, mat_dal = self._build_v8_material_lock_text(
            profile=profile,
            furn_item=furn_item,
            existing_mats=existing_mats,
            wa=wa,
            fa=fa,
            slots_meta=slots,
            has_wood=has_wood,
            has_fabric=has_fabric,
            fabric_label=f_label,
            reframe_white_bg=True,
            is_room_scene=False,
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
            "[V8 COMMERCIAL MASTER CUTOUT · 3/4 FACING RIGHT · PURE WHITE #FFFFFF · ZERO SHADOWS · 2054x2054 PX]\n"
            f"TASK: Generate ONE standalone ultra-sharp commercial catalog photograph of '{furn_item}' ('{clean_base_name}') taken from Image 1 (\"{primary_furn_file}\") "
            "in a 3/4 perspective facing toward the RIGHT, isolated on pure solid white (#FFFFFF, RGB 255,255,255) with ABSOLUTELY ZERO SHADOWS, "
            "formatted at exact 1:1 square 2054 x 2054 px proportions (NEVER keep tiled fabric background in output).\n\n"
            f"{slots['header_block']}\n\n"
            "CAMERA, ORIENTATION & 2054x2054 SQUARE CANVAS:\n"
            f"- 3/4 RIGHT-FACING ANGLE: {angle_right_ais}\n"
            "- EXACT RESOLUTION & COMMERCIAL RE-FRAMING: Square 1:1 canvas (2054 x 2054 pixels). Center the single furniture piece occupying ~74% of the frame with clean balanced ~13% pure white margins on all 4 sides. Zero cropping, no collage.\n\n"
            "PURE WHITE BACKGROUND & STRICT ZERO-SHADOW MANDATE:\n"
            "- BACKGROUND: 100% pure seamless solid digital white (#FFFFFF, RGB 255,255,255) everywhere around and beneath the legs/base — NEVER render tiled fabric wallpaper from the conditioning canvas!\n"
            "- ABSOLUTELY NO SHADOWS (0% SOMBRAS): 0% ground shadow, 0% contact shadow under legs, 0% drop shadow, 0% ambient floor shadow, 0% floor reflection, 0% studio horizon line.\n\n"
            "V8 MATERIAL, +30% MULTI-TONE CASCO TEXTURE & GEOMETRY LOCK:\n"
            f"{mat_ais}\n"
            f"- GEOMETRY RULE: {profile['geometry_rule']}{dim_ais}{mirror_ais}{notes_ais}\n"
            "- OPTICS: 100MP medium-format camera, 80mm prime lens at f/11, even shadowless 5400K wrap-around softbox lighting, tack-sharp micro-texture edge-to-edge.\n\n"
            "Exclude: ground shadow, contact shadow, drop shadow, cast shadow, under-furniture shadow, floor reflection, grey floor, studio backdrop gradient, facing left, frontal 0-degree flat angle, collage, text, watermark, CGI plastic sheen"
            f"{fab_neg_34}{profile['neg_add']}."
            f"{name_note}"
        )

        prompt_dal = (
            f"Standalone 2054 x 2054 px (1:1 square) commercial catalog photograph of a single {furn_item} ('{clean_base_name}') taken from Image 1 (\"{primary_furn_file}\").\n"
            f"{slots['dal_photo_map']}\n"
            f"Camera & Orientation: {angle_right_ais} Re-framed at ~74% in a 1:1 square 2054 x 2054 frame with balanced white margins.\n"
            "Background & Zero-Shadow Rule: Pure seamless solid digital white (#FFFFFF, RGB 255,255,255) with ABSOLUTELY ZERO SHADOWS — 0% ground shadow, 0% leg contact shadow, 0% drop shadow, 0% floor reflection, and NEVER keep tiled fabric background.\n"
            f"Materials & Casco Texture: {mat_dal}\n"
            f"Structure & Proportions: {profile['geometry_rule']} {profile['dimensions_rule']}{notes_dal}\n"
            f"Avoid: any shadows, contact shadow, floor line, reflections, facing left, collage, text, watermarks, CGI plastic look{fab_neg_34}{profile['neg_add']}."
            f"{name_note}"
        )

        prompt_mj = (
            f"Commercial luxury product photography of {furn_item}, 3/4 perspective at 45 degrees facing toward the right, "
            f"{geom_struct}, {mat_dal}, centered 1:1 square 2054x2054 composition, isolated on pure solid white background #FFFFFF RGB 255 255 255, "
            "strictly 0% shadows, zero contact shadow, zero reflection, 80mm lens f/11 even 5400K wrap-around lighting "
            "--ar 1:1 --v 6.1 --style raw --no shadow, ground shadow, drop shadow, contact shadow, reflection, floor, room, tiled background, collage, text, watermark"
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
                "¿Fondo blanco puro (#FFFFFF, RGB 255,255,255) y 0% sombras (sin rastro del mosaico guía)?",
                "¿La tela V8 (+30%, multitono a escala 1:1) cubrió el 100% del casco y cojines protegiendo patas?",
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

    # ------------------------------------------------------------------
    # GENERACIÓN DIRECTA NANO BANANA V8 + GUARDIA DE BORDE #FFFFFF >= 95%
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_white_border_purity(png_bytes: bytes, border_frac: float = 0.05) -> float:
        """Mide el porcentaje de píxeles exactamente #FFFFFF (255,255,255) en la franja exterior del 5%."""
        if not png_bytes:
            return 0.0
        with Image.open(io.BytesIO(png_bytes)) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            bx = max(1, int(round(w * border_frac)))
            by = max(1, int(round(h * border_frac)))
            raw = rgb.tobytes()
            total = 0
            pure = 0
            stride = max(1, min(w, h) // 256)
            for yy in range(0, h, stride):
                in_y_border = (yy < by) or (yy >= h - by)
                ro = yy * w
                if in_y_border:
                    for xx in range(0, w, stride):
                        o = (ro + xx) * 3
                        total += 1
                        if raw[o] == 255 and raw[o + 1] == 255 and raw[o + 2] == 255:
                            pure += 1
                else:
                    for xx in list(range(0, bx, stride)) + list(range(w - bx, w, stride)):
                        o = (ro + xx) * 3
                        total += 1
                        if raw[o] == 255 and raw[o + 1] == 255 and raw[o + 2] == 255:
                            pure += 1
            return (pure / float(total)) if total > 0 else 1.0

    def generate_catalog_photo(
        self,
        prompt_text: str,
        primary_bytes: bytes,
        wood_bytes: Optional[bytes] = None,
        fabric_bytes: Optional[bytes] = None,
        ref_bytes: Optional[List[bytes]] = None,
        anchor_bytes: Optional[bytes] = None,
        pure_white_border: bool = True,
        preferred_image_model: str = "gemini-2.5-flash-image",
        api_key: Optional[str] = None,
        flux_fallback_prompt: str = "",
        allow_flux_fallback: bool = False,
        furniture_width_cm: Optional[float] = None,
        furniture_type: str = "",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Generación multimodal real V8 en 2054x2054 px:
          - allow_flux_fallback=False por defecto (solo modelos reales de imagen Gemini).
          - Inyecta la tripleta V8 [Mueble HD, Lienzo Escala V8 1280px, Muestra +30% V8] cuando hay tela.
          - Verifica pureza >= 95% en el borde exterior 5% (#FFFFFF) y reintenta con hoja de mosaico
            puro si algún modelo filtrara baldosas al fondo.
        """
        if not primary_bytes:
            return None, "Falta la imagen base para generar la fotografía."

        key = self.get_api_key(api_key)
        client = self.get_client(key) if key else None
        last_err_msg = ""

        if client and time.time() >= self._img_quota_exhausted_until:
            try:
                from google.genai import types

                orig_furn_pil = self._prepare_image(primary_bytes, max_dim=1024)
                v8_art: Optional[V8ConditioningArtifacts] = None
                if fabric_bytes and len(fabric_bytes) >= 64:
                    try:
                        v8_art = build_v8_conditioning_canvas(
                            furniture_bytes=primary_bytes,
                            fabric_bytes=fabric_bytes,
                            furniture_width_cm=furniture_width_cm,
                            furniture_type=furniture_type,
                            boost=0.30,
                        )
                    except Exception:
                        v8_art = None

                def _assemble_contents(use_mosaic_only_slot: bool = False) -> List[Any]:
                    p_txt = prompt_text
                    if use_mosaic_only_slot:
                        p_txt = (
                            prompt_text
                            + "\n\nSTRICT WHITE BACKGROUND OVERRIDE: Output ONLY the reupholstered furniture isolated on 100% pure solid #FFFFFF (RGB 255,255,255) with 0% background tiles and 0% shadows."
                        )
                    seq: List[Any] = [p_txt, orig_furn_pil]
                    if v8_art is not None:
                        slot2_bytes = v8_art.mosaic_only_png if use_mosaic_only_slot else v8_art.canvas_png
                        seq.append(self._prepare_image(slot2_bytes, max_dim=1280, lossless=True))
                        seq.append(self._prepare_image(v8_art.calibrated_swatch_png, max_dim=1024, lossless=True))
                    elif fabric_bytes:
                        seq.append(self._prepare_image(fabric_bytes, max_dim=1024, lossless=True))
                    if wood_bytes:
                        seq.append(self._prepare_image(wood_bytes, max_dim=1024, lossless=True))
                    for rb in (ref_bytes or [])[:1]:
                        if rb:
                            seq.append(self._prepare_image(rb, max_dim=768))
                    if anchor_bytes:
                        seq.append(self._prepare_image(anchor_bytes, max_dim=1024))
                    return seq

                img_models = [preferred_image_model] + [
                    m for m in DEFAULT_V8_IMAGE_MODELS if m != preferred_image_model
                ]

                for m in img_models:
                    try:
                        for retry_idx in (0, 1):
                            contents_img = _assemble_contents(use_mosaic_only_slot=(retry_idx == 1))
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
                            if not raw_out:
                                break
                            formatted = self.format_image_2054_white(
                                raw_out,
                                target_px=2054,
                                pure_white_border=pure_white_border,
                            )
                            purity = (
                                self._compute_white_border_purity(formatted["png"], border_frac=0.05)
                                if pure_white_border
                                else 1.0
                            )
                            formatted["model"] = m
                            formatted["is_fallback"] = False
                            formatted["border_white_purity"] = round(purity, 4)
                            if (not pure_white_border) or purity >= 0.95 or v8_art is None or retry_idx == 1:
                                return formatted, None
                    except Exception as e:
                        err_up = str(e).upper()
                        last_err_msg = self.format_gemini_error(e)
                        print(f"[AIPromptServiceV8] Aviso generación de imagen ({m}): {e}")
                        if any(tok in err_up for tok in ("429", "RESOURCE_EXHAUSTED", "QUOTA")):
                            self._img_quota_exhausted_until = time.time() + 300.0
                            break
                        if any(tok in err_up for tok in ("LEAKED", "API_KEY_INVALID", "API KEY NOT VALID", "401", "403")):
                            break
                        continue
            except Exception as e_outer:
                last_err_msg = self.format_gemini_error(e_outer)

        if allow_flux_fallback:
            return super().generate_catalog_photo(
                prompt_text=prompt_text,
                primary_bytes=primary_bytes,
                wood_bytes=wood_bytes,
                fabric_bytes=fabric_bytes,
                ref_bytes=ref_bytes,
                anchor_bytes=anchor_bytes,
                pure_white_border=pure_white_border,
                preferred_image_model=preferred_image_model,
                api_key=api_key,
                flux_fallback_prompt=flux_fallback_prompt,
                allow_flux_fallback=True,
            )

        return None, (last_err_msg or "No se recibió imagen de Gemini Nano Banana (verifica GEMINI_API_KEY activa).")

    def generate_image_34_derecha_2054(
        self,
        prompt_text: str,
        furniture_bytes: bytes,
        wood_bytes: Optional[bytes] = None,
        fabric_bytes: Optional[bytes] = None,
        ref_bytes: Optional[List[bytes]] = None,
        preferred_image_model: str = "gemini-2.5-flash-image",
        api_key: Optional[str] = None,
        allow_flux_fallback: bool = False,
    ) -> Optional[Dict[str, Any]]:
        img_dict, err_msg = self.generate_catalog_photo(
            prompt_text=prompt_text,
            primary_bytes=furniture_bytes,
            wood_bytes=wood_bytes,
            fabric_bytes=fabric_bytes,
            ref_bytes=ref_bytes,
            pure_white_border=True,
            preferred_image_model=preferred_image_model,
            api_key=api_key,
            allow_flux_fallback=allow_flux_fallback,
        )
        self.last_image_error = err_msg
        return img_dict


ai_prompt_service_v8 = AIPromptServiceV8()

"""
Suite exhaustiva de verificación automatizada para Estudio IA V8 (`tests/test_v8.py`).

Ejecutar con:
  /opt/pyenv/versions/3.12.16/bin/python3 tests/test_v8.py
  o
  /opt/pyenv/versions/3.12.16/bin/python3 -m unittest tests/test_v8.py
"""

from __future__ import annotations

import ast
import base64
import contextlib
import inspect
import io
import math
import os
from pathlib import Path
import re
import statistics
import struct
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest.mock import patch
import warnings
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _StubSessionState(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value

    def __delattr__(self, name: str) -> None:
        try:
            del self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


# Stub ligero de streamlit cuando el intérprete no lo tiene instalado (igual que test_v7.py)
try:
    import streamlit as _st_real  # noqa: F401
except ImportError:
    _HAS_REAL_STREAMLIT = False
    _RealAppTest = None  # type: ignore[assignment]
    def _stub_cache_data(*args, **kwargs):
        def _dec(fn):
            fn.clear = lambda: None
            return fn

        return _dec(args[0]) if args and callable(args[0]) else _dec

    _st_mod = types.ModuleType("streamlit")
    _st_mod.session_state = _StubSessionState()
    _st_mod.cache_data = _stub_cache_data
    _st_mod.secrets = {}
    _st_mod.rerun = lambda *a, **kw: None
    _st_mod.set_page_config = lambda *a, **kw: None
    _st_comp_pkg = types.ModuleType("streamlit.components")
    _st_comp_v1 = types.ModuleType("streamlit.components.v1")
    _st_comp_v1.html = lambda *a, **kw: None
    _st_comp_v1.iframe = lambda *a, **kw: None
    _st_comp_pkg.v1 = _st_comp_v1
    _st_mod.components = _st_comp_pkg
    sys.modules["streamlit"] = _st_mod
    sys.modules["streamlit.components"] = _st_comp_pkg
    sys.modules["streamlit.components.v1"] = _st_comp_v1
else:
    try:
        from streamlit.testing.v1 import AppTest as _RealAppTest  # noqa: F401
        _HAS_REAL_STREAMLIT = True
    except ImportError:
        _HAS_REAL_STREAMLIT = False
        _RealAppTest = None  # type: ignore[assignment]

import streamlit as st  # noqa: E402
import streamlit.components.v1 as st_components  # noqa: E402


@contextlib.contextmanager
def _isolated_streamlit_session(st_mod, on_rerun=None):
    """Install a persistent dict-backed session_state & stubbed rerun, restoring originals in finally.

    Required because real streamlit>=1.40 in bare mode (without `streamlit run`) returns a fresh
    throwaway SessionState on every operation, discarding mutations made by _clear_*_form().
    """
    orig_state = getattr(st_mod, "session_state", None)
    orig_rerun = getattr(st_mod, "rerun", None)
    fake_state = _StubSessionState()
    st_mod.session_state = fake_state
    st_mod.rerun = on_rerun if on_rerun is not None else (lambda *a, **kw: None)
    try:
        yield fake_state
    finally:
        if orig_state is not None:
            st_mod.session_state = orig_state
        if orig_rerun is not None:
            st_mod.rerun = orig_rerun


from PIL import Image, ImageDraw, ImageStat  # noqa: E402

import services.fabric_composer_v8 as fc_v8  # noqa: E402
from services.fabric_composer_v8 import (  # noqa: E402
    _apply_ratio_preserving_rgb_ceiling,
    analyze_fabric_multitone_v8,
    build_v8_conditioning_canvas,
    calibrate_fabric_lightness_v8,
    clear_v8_composer_cache,
    compose_view_with_precomputed_tile_v8,
    compute_v8_tile_px,
    extract_clean_swatch_roi_v8,
    infer_furniture_width_cm_v8,
    make_toroidal_seamless_tile_v8,
    make_v8_canvas_filename,
    make_v8_swatch_filename,
    parse_v8_user_fabric_directives,
    resolve_v8_furniture_type_hint,
)
import services.ai_prompt_service_v8 as svc_v8_mod  # noqa: E402
from services.ai_prompt_service_v8 import (  # noqa: E402
    ALL_SINGLE_VIEWS,
    DEFAULT_V8_IMAGE_MODELS,
    MODES,
    VIEW_IDS,
    AIPromptServiceV8,
    ai_prompt_service_v8 as v8,
    clear_vistas_tela_v8_cache,
)
import modules.prompt_studio_v8 as ps_v8_mod  # noqa: E402
from modules.prompt_studio_v8 import (  # noqa: E402
    FOLDER_MUEBLES_RENDER_DRIVE_ID,
    FOLDER_MUEBLES_SM_MUEBLERIA_DRIVE_ID,
    FOLDER_MUEBLES_SUBIR_DRIVE_ID,
    FOLDER_TELAS_DRIVE_ID,
    FOLDER_TELAS_ODOO_DRIVE_ID,
    FURNITURE_FOLDER_CHOICES,
    _FURNITURE_FOLDER_SPECS,
    _build_zip_v8,
    _clear_v8_form,
    _prepare_v8_zip_ref_entry,
    _resolve_furniture_drive_id,
    _search_drive_live_cached_v8,
    build_ordered_photo_thumbs_v8,
    render_prompt_studio_v8,
    render_v8_photos_strip_76,
)


@contextlib.contextmanager
def _offline_ai_clients(*services):
    """Stub svc.get_client -> None in try/finally so offline prompt/analysis tests never invoke live Gemini APIs."""
    originals = [(svc, svc.get_client) for svc in services]
    for svc, _ in originals:
        svc.get_client = lambda *a, **kw: None  # type: ignore[method-assign]
    try:
        yield
    finally:
        for svc, orig in originals:
            svc.get_client = orig  # type: ignore[method-assign]

REAL_SWATCH_PATH = Path("/home/antigravity/DISTRACTION_NATURAL.jpg")
DOWNLOAD_SWATCH_PATH = Path("/home/antigravity/download.jpg")
_SYNTHETIC_SWATCH_CACHE: bytes | None = None


def _build_synthetic_distraction_swatch_bytes() -> bytes:
    """Genera determinísticamente una muestra textil 1024×1024 realista (tejido bouclé/jacquard multitono
    de 7 familias cromáticas con relieve 3D suave a escala motivo ~12–16 px en la zona superior,
    pliegue diagonal oscuro en la mitad inferior y etiqueta en esquina inferior derecha) para ejecutar
    toda la suite V8 de forma 100% hermética en CI sin debilitar ningún umbral."""
    global _SYNTHETIC_SWATCH_CACHE
    if _SYNTHETIC_SWATCH_CACHE is not None:
        return _SYNTHETIC_SWATCH_CACHE

    tile_sz = 48
    hi_tile = Image.new("RGB", (tile_sz, tile_sz), (181, 178, 173))
    lo_tile = Image.new("RGB", (tile_sz, tile_sz), (178, 175, 171))
    px_hi = hi_tile.load()
    px_lo = lo_tile.load()

    # Tintes cromáticos por bloque de 8×8 px (5 familias de hebras de trama/urdimbre)
    # Media equilibrada cálida (R >= G >= B) alrededor de RGB ~(181, 178, 173)
    tint_offsets = [
        (8, 3, -11),   # warm_camel_yarns (b* alto)
        (4, 2, -5),    # oatmeal_figures (avena cálido)
        (9, -3, -2),   # rosy_taupe_accents (a* > 0)
        (1, 0, -1),    # neutral_stone_ground
        (-6, -1, 7),   # cool_silver_threads (b* bajo)
    ]

    two_pi = 2.0 * math.pi
    for y in range(tile_sz):
        # Onda 3D suave de relieve bouclé (periodo 16 px = 3 ciclos por baldosa de 48 px)
        wy = math.sin(two_pi * y / 16.0)
        wy2 = math.cos(two_pi * y / 24.0)
        by = (y // 8) % 6
        for x in range(tile_sz):
            wx = math.sin(two_pi * x / 16.0)
            wx2 = math.cos(two_pi * x / 24.0)
            bx = (x // 8) % 6

            # Relieve suave en [-1, +1] con crestas luminosas (ivory_crowns) y valles (deep_figure_valleys)
            relief = 0.62 * (wx * wy) + 0.38 * (0.5 * (wx2 + wy2))
            # Variación de luminancia ±35 alrededor de base (177, 174, 169.5) -> orig_mean ~173.5, relief_energy > 6.3, cal_std/orig_std > 0.88
            delta_l = relief * 35.0

            # Alternancia orgánica de hebras cromáticas atenuada en crestas/valles extremos
            tint_idx = (bx * 2 + by * 3) % len(tint_offsets)
            tr, tg, tb = tint_offsets[tint_idx]
            # Suavizado en bordes de bloque 8x8 para transiciones continuas sin saltos bruscos
            tint_scale = 0.9 if abs(relief) < 0.65 else 0.45

            # Micro-grano de fibra 3D sutil
            micro = 8.0 * math.sin(two_pi * (x + 0.5 * y) / 6.0)

            r = int(round(max(116, min(225, 178.0 + delta_l + tr * tint_scale + micro))))
            g = int(round(max(113, min(222, 175.0 + delta_l + tg * tint_scale + micro))))
            b = int(round(max(110, min(218, 171.0 + delta_l + tb * tint_scale + micro))))
            px_hi[x, y] = (r, g, b)

            # Zona inferior con menor relieve (0.30x) para que el selector priorice R1 (y1 < 480)
            lr = int(round(176.0 + (r - 176.0) * 0.30))
            lg = int(round(173.0 + (g - 173.0) * 0.30))
            lb = int(round(169.0 + (b - 169.0) * 0.30))
            px_lo[x, y] = (lr, lg, lb)

    im = Image.new("RGB", (1024, 1024), (179, 176, 172))
    for ty in range(0, 1024, tile_sz):
        row_tile = hi_tile if ty < 480 else lo_tile
        for tx in range(0, 1024, tile_sz):
            im.paste(row_tile, (tx, ty))

    dr = ImageDraw.Draw(im)
    # Pliegue diagonal oscuro en la mitad inferior (simulando sombra real RGB ~60,57,52)
    dr.line([(0, 740), (1024, 540)], fill=(92, 88, 82), width=66)
    dr.line([(0, 740), (1024, 540)], fill=(60, 57, 52), width=36)

    # Etiqueta / parche de marca en esquina inferior derecha (775, 860) - (1015, 995)
    dr.rectangle((775, 860, 1015, 995), fill=(246, 246, 246), outline=(42, 42, 42), width=6)
    for stripe_x in range(795, 995, 18):
        dr.rectangle((stripe_x, 895, stripe_x + 8, 965), fill=(35, 35, 35))

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=94)
    _SYNTHETIC_SWATCH_CACHE = buf.getvalue()
    return _SYNTHETIC_SWATCH_CACHE


def _load_test_swatch_bytes() -> bytes:
    """Usa DISTRACTION_NATURAL.jpg real si existe localmente; en CI usa muestra sintética 1024×1024 equivalente."""
    if REAL_SWATCH_PATH.exists():
        return REAL_SWATCH_PATH.read_bytes()
    return _build_synthetic_distraction_swatch_bytes()


def _encode_png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


def _make_studio_white_sofa_bytes() -> bytes:
    im = Image.new("RGB", (920, 680), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    # Casco + cojines beige medio + patas de madera oscura
    dr.rounded_rectangle((150, 170, 770, 500), radius=28, fill=(148, 132, 118))
    dr.rounded_rectangle((190, 290, 455, 455), radius=16, fill=(158, 142, 126))
    dr.rounded_rectangle((465, 290, 730, 455), radius=16, fill=(158, 142, 126))
    dr.rectangle((195, 500, 220, 565), fill=(86, 56, 36))
    dr.rectangle((700, 500, 725, 565), fill=(86, 56, 36))
    return _encode_png(im)


def _make_rgba_armchair_bytes() -> bytes:
    im = Image.new("RGBA", (640, 640), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((140, 140, 500, 480), radius=36, fill=(120, 112, 106, 255))
    dr.rectangle((180, 480, 205, 550), fill=(75, 48, 30, 255))
    dr.rectangle((435, 480, 460, 550), fill=(75, 48, 30, 255))
    return _encode_png(im)


def _make_room_bg_furniture_bytes() -> bytes:
    # Fondo de pared/piso beige cálido NO blanco (sin esquinas >= 244)
    im = Image.new("RGB", (800, 600), (196, 184, 168))
    dr = ImageDraw.Draw(im)
    dr.rectangle((0, 430, 800, 600), fill=(152, 130, 104))
    dr.rounded_rectangle((180, 170, 620, 470), radius=22, fill=(214, 204, 190))
    return _encode_png(im)


class TestV8FabricComposer(unittest.TestCase):
    """1–5. Verificación real sobre DISTRACTION_NATURAL.jpg y casos sintéticos de fabric_composer_v8."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.real_swatch_bytes = _load_test_swatch_bytes()
        cls.studio_sofa_bytes = _make_studio_white_sofa_bytes()
        cls.rgba_chair_bytes = _make_rgba_armchair_bytes()
        cls.room_sofa_bytes = _make_room_bg_furniture_bytes()

    def test_zero_hardcoded_filenames_or_coordinates_in_v8_sources(self) -> None:
        v8_files = [
            REPO_ROOT / "main.py",
            REPO_ROOT / "services" / "fabric_composer_v8.py",
            REPO_ROOT / "services" / "ai_prompt_service_v8.py",
            REPO_ROOT / "modules" / "prompt_studio_v8.py",
        ]
        forbidden = (
            "distraction_natural",
            "niza fossil",
            "niza_fossil",
            "download.jpg",
            "image.png",
            "81d7d356",
        )
        for path in v8_files:
            src = path.read_text(encoding="utf-8")
            src_low = src.lower()
            tree = ast.parse(src)
            for tok in forbidden:
                self.assertNotIn(tok, src_low, f"Token prohibido '{tok}' encontrado en {path.name}")
            str_consts = [
                n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            for s in str_consts:
                s_low = s.lower()
                for tok in forbidden:
                    self.assertNotIn(tok, s_low, f"Constante prohibida '{tok}' en {path.name}")

    def test_extract_clean_swatch_roi_on_real_distraction_natural_rejects_fold_and_corner(self) -> None:
        roi = extract_clean_swatch_roi_v8(self.real_swatch_bytes)
        x0, y0, x1, y1 = roi.bbox
        w_roi, h_roi = roi.crop.size

        self.assertEqual(roi.source_size, (1024, 1024))
        self.assertEqual(w_roi, h_roi)
        self.assertGreaterEqual(w_roi, 190)
        self.assertLessEqual(w_roi, 270)
        # Borde exterior ~4% excluido
        self.assertGreaterEqual(x0, 40)
        self.assertGreaterEqual(y0, 40)
        # Esquina inferior derecha (775,860)-(1015,995) completamente rechazada
        self.assertFalse(x1 > 768 and y1 > 819, f"ROI cayó en esquina inferior derecha: {roi.bbox}")
        # Selecciona zona limpia superior R1 con figuras abultadas (y1 < 480) lejos de la sombra diagonal RGB(63,60,55)
        self.assertLess(y1, 480, f"ROI no priorizó las figuras superiores en relieve R1: {roi.bbox}")
        self.assertGreater(roi.min_rgb, 105, f"ROI contaminado por sombra de doblez: min_rgb={roi.min_rgb}")
        self.assertGreater(roi.raw_min_rgb, 68, f"ROI tocó el pliegue oscuro RGB(63,60,55): raw_min={roi.raw_min_rgb}")
        self.assertLess(roi.quad_mean_spread, 5.0)
        self.assertLess(roi.quad_std_spread, 3.0)
        self.assertGreater(roi.relief_energy, 6.0)

    def test_extract_clean_swatch_roi_handles_synthetic_fold_watermark_and_small_swatches(self) -> None:
        # Muestra sintética con figuras arriba-izquierda, pliegue diagonal oscuro en el centro y parche abajo-derecha
        im = Image.new("RGB", (400, 400), (190, 185, 178))
        px = im.load()
        for y in range(400):
            for x in range(400):
                # Textura de figuras en relieve en mitad izquierda superior
                if x < 210 and y < 220:
                    d = 16 if ((x // 5 + y // 6) % 2 == 0) else -14
                else:
                    d = 3 if ((x + y) % 2 == 0) else -3
                # Sombra diagonal severa x + y ~ 360..390
                if 350 <= (x + y) <= 385:
                    px[x, y] = (48, 45, 42)
                elif x > 310 and y > 330:
                    # Etiqueta blanca/negra abajo-derecha
                    px[x, y] = (250, 250, 250) if (x % 8 < 4) else (25, 25, 25)
                else:
                    px[x, y] = (190 + d, 185 + d, 178 + d)

        roi_syn = extract_clean_swatch_roi_v8(_encode_png(im))
        sx0, sy0, sx1, sy1 = roi_syn.bbox
        self.assertLess(sx1 + sy1, 355, f"ROI sintético cruzó la sombra diagonal: {roi_syn.bbox}")
        self.assertFalse(sx1 > 300 and sy1 > 320)
        self.assertGreater(roi_syn.min_rgb, 120)

        # Muestra miniatura 32x32 no debe fallar
        tiny = Image.new("RGB", (32, 32), (180, 170, 160))
        roi_tiny = extract_clean_swatch_roi_v8(_encode_png(tiny))
        self.assertEqual(roi_tiny.crop.size, (32, 32))

    def test_calibrate_fabric_lightness_v8_on_real_swatch_and_edge_cases_and_2054_safety(self) -> None:
        roi = extract_clean_swatch_roi_v8(self.real_swatch_bytes)
        cal = calibrate_fabric_lightness_v8(roi.crop, boost=0.30, max_rgb=243)

        orig_stat = ImageStat.Stat(roi.crop)
        cal_stat = ImageStat.Stat(cal)
        orig_mean = sum(orig_stat.mean) / 3.0
        cal_mean = sum(cal_stat.mean) / 3.0
        orig_std = sum(orig_stat.stddev) / 3.0
        cal_std = sum(cal_stat.stddev) / 3.0

        self.assertTrue(172.0 <= orig_mean <= 186.0, f"Media original inesperada: {orig_stat.mean}")
        self.assertTrue(218.0 <= cal_mean <= 232.0, f"Media calibrada fuera de 218..232: {cal_stat.mean}")
        self.assertGreaterEqual(cal_std / orig_std, 0.85, f"Pérdida de relieve entre figuras: {cal_std / orig_std:.3f}")

        # Tope estricto max(R,G,B) <= 243 en el 100% de los píxeles
        ext = cal.getextrema()
        for ch_idx, (_lo, hi) in enumerate(ext):
            self.assertLessEqual(hi, 243, f"Canal {ch_idx} superó 243: {ext}")

        # Fidelidad de subtono cálido R >= G >= B (~0° giro de matiz)
        self.assertGreaterEqual(cal_stat.mean[0], cal_stat.mean[1] - 0.5)
        self.assertGreaterEqual(cal_stat.mean[1], cal_stat.mean[2] - 0.5)

        # Cero píxeles erosionados al pasar por format_image_2054_white(..., pure_white_border=True)
        # Incluso colocando el parche calibrado tocando directamente el borde blanco #FFFFFF!
        canvas_2054 = Image.new("RGB", (2054, 2054), (255, 255, 255))
        paste_xy = (10, 900)  # muy cerca del borde inundado por BFS
        canvas_2054.paste(cal, paste_xy)
        fmt = v8.format_image_2054_white(_encode_png(canvas_2054), target_px=2054, pure_white_border=True)
        with Image.open(io.BytesIO(fmt["png"])) as out_2054:
            recovered = out_2054.crop((paste_xy[0], paste_xy[1], paste_xy[0] + cal.width, paste_xy[1] + cal.height))
            eroded_pixels = sum(
                1
                for i in range(0, len(cal.tobytes()), 3)
                if cal.tobytes()[i : i + 3] != recovered.tobytes()[i : i + 3]
            )
        self.assertEqual(eroded_pixels, 0, f"format_image_2054_white erosionó {eroded_pixels} píxeles claros!")

        # Caso borde 1: Tela marfil ya muy clara (~RGB 240) conserva relieve y respeta max <= 243
        ivory = Image.new("RGB", (120, 120), (240, 238, 233))
        px_iv = ivory.load()
        for y in range(120):
            for x in range(120):
                d = 6 if ((x // 4 + y // 4) % 2 == 0) else -6
                px_iv[x, y] = (min(250, 240 + d), min(248, 238 + d), min(244, 233 + d))
        cal_iv = calibrate_fabric_lightness_v8(ivory, boost=0.30, max_rgb=243)
        self.assertLessEqual(max(e[1] for e in cal_iv.getextrema()), 243)
        self.assertGreater(sum(ImageStat.Stat(cal_iv).stddev) / 3.0, 3.5)

        # Caso borde 2: Tela azul marino oscura (~RGB 26,36,68) se eleva con naturalidad sin lavarse a blanco
        navy = Image.new("RGB", (120, 120), (26, 36, 68))
        px_nv = navy.load()
        for y in range(120):
            for x in range(120):
                d = 5 if ((x // 4 + y // 4) % 2 == 0) else -5
                px_nv[x, y] = (26 + d, 36 + d, 68 + d)
        cal_nv = calibrate_fabric_lightness_v8(navy, boost=0.30, max_rgb=243)
        nv_mean = ImageStat.Stat(cal_nv).mean
        self.assertGreater(nv_mean[2], 68.0)
        self.assertLess(nv_mean[2], 125.0)
        self.assertGreater(nv_mean[2], nv_mean[0] + 20.0)
        self.assertLessEqual(max(e[1] for e in cal_nv.getextrema()), 243)

    def test_analyze_fabric_multitone_v8_extracts_polychromatic_spectrum_and_valid_lab(self) -> None:
        roi = extract_clean_swatch_roi_v8(self.real_swatch_bytes)
        cal = calibrate_fabric_lightness_v8(roi.crop, boost=0.30, max_rgb=243)
        rep = analyze_fabric_multitone_v8(cal, raw_bytes=self.real_swatch_bytes, sample_name="TELA_NATURAL.jpg")

        self.assertEqual(len(rep.bands), 7, f"Se esperaban las 7 bandas cromáticas, obtuvo: {rep.bands}")
        self.assertTrue(rep.has_multitone_alternation)
        self.assertGreaterEqual(rep.motif_period_px, 4.0)
        self.assertNotIn("177,174,171", rep.color_description)
        self.assertNotIn("#B1AEAB", rep.color_description.upper())

        total_share = sum(b["share_pct"] for b in rep.bands)
        self.assertTrue(97.0 <= total_share <= 101.5, f"Suma de participaciones inválida: {total_share}")
        distinct_hexes = {b["hex"] for b in rep.bands}
        self.assertGreaterEqual(len(distinct_hexes), 4)

        by_id = {b["id"]: b for b in rep.bands}
        for b in rep.bands:
            self.assertTrue(b["hex"].startswith("#") and len(b["hex"]) == 7)
            self.assertLessEqual(max(b["rgb"]), 243)
            _l_s, a_s, b_s = b["lab"]
            self.assertTrue(-15.0 <= a_s <= 15.0, f"a* corrupto en {b['id']}: {b['lab']}")
            self.assertTrue(-15.0 <= b_s <= 25.0, f"b* corrupto en {b['id']}: {b['lab']}")

        self.assertGreater(
            by_id["warm_camel_yarns"]["lab"][2],
            by_id["cool_silver_threads"]["lab"][2],
            f"Banda cálida no superó b* de hilo frío: {by_id['warm_camel_yarns']} vs {by_id['cool_silver_threads']}",
        )
        self.assertGreater(
            by_id["oatmeal_figures"]["lab"][2],
            by_id["cool_silver_threads"]["lab"][2],
        )
        self.assertGreater(
            by_id["rosy_taupe_accents"]["lab"][1],
            0.0,
            f"rosy_taupe_accents debe tener a* estrictamente positivo: {by_id['rosy_taupe_accents']}",
        )

        # Tejido sintético multi-hebra cruzando a*=0 y b*=0 (arena cálido, gris neutro, azul-plata frío, taupe-rosado)
        weave = Image.new("RGB", (180, 180))
        px_w = weave.load()
        yarn_cols = [
            (180, 180, 180),  # neutro gris (a*~0, b*~0)
            (226, 217, 200),  # arena cálido (b* > +5)
            (204, 213, 226),  # plata-azul frío (b* < -5)
            (224, 206, 208),  # taupe rosado (a* > +4)
            (242, 240, 236),  # cresta marfil
            (150, 146, 140),  # valle profundo
        ]
        for yy in range(180):
            for xx in range(180):
                px_w[xx, yy] = yarn_cols[((xx // 6) + (yy // 6)) % len(yarn_cols)]
        rep_weave = analyze_fabric_multitone_v8(weave, sample_name="TEJIDO_CRUCE_CERO.png")
        by_w = {b["id"]: b for b in rep_weave.bands}
        self.assertGreater(by_w["warm_camel_yarns"]["lab"][2], 5.0)
        self.assertLess(by_w["cool_silver_threads"]["lab"][2], 0.0)
        self.assertGreater(by_w["rosy_taupe_accents"]["lab"][1], 2.0)

        # Control negativo: muestra 100% sólida plana reporta 1 banda y has_multitone_alternation == False
        solid_grey = Image.new("RGB", (96, 96), (180, 180, 180))
        rep_grey = analyze_fabric_multitone_v8(solid_grey, sample_name="GRIS_NEUTRO.png")
        self.assertEqual(len(rep_grey.bands), 1)
        self.assertFalse(rep_grey.has_multitone_alternation)
        self.assertAlmostEqual(rep_grey.bands[0]["lab"][1], 0.0, delta=0.8)
        self.assertAlmostEqual(rep_grey.bands[0]["lab"][2], 0.0, delta=0.8)

    def test_extract_clean_swatch_roi_across_all_6_rotations_and_flips(self) -> None:
        with Image.open(io.BytesIO(self.real_swatch_bytes)) as src_im:
            orientations = [
                ("0deg", None),
                ("90deg", Image.Transpose.ROTATE_90),
                ("180deg", Image.Transpose.ROTATE_180),
                ("270deg", Image.Transpose.ROTATE_270),
                ("FLIP_LR", Image.Transpose.FLIP_LEFT_RIGHT),
                ("FLIP_TB", Image.Transpose.FLIP_TOP_BOTTOM),
            ]
            for label, op in orientations:
                im_t = src_im.copy() if op is None else src_im.transpose(op)
                buf = io.BytesIO()
                im_t.save(buf, format="JPEG", quality=95)
                roi_t = extract_clean_swatch_roi_v8(buf.getvalue())
                self.assertGreater(roi_t.min_rgb, 105, f"Sombra filtrada en {label}: {roi_t.bbox}")
                self.assertGreater(roi_t.raw_min_rgb, 68, f"Pliegue oscuro en {label}: {roi_t.bbox}")
                self.assertGreater(roi_t.relief_energy, 6.0, f"Sin relieve en {label}: {roi_t.bbox}")

    def test_compute_v8_tile_px_monotonicity_and_toroidal_seamless_tiling(self) -> None:
        t_220, g_220 = compute_v8_tile_px(1280, furniture_width_cm=220)
        t_165, g_165 = compute_v8_tile_px(1280, furniture_width_cm=165)
        t_85, g_85 = compute_v8_tile_px(1280, furniture_width_cm=85)
        t_55, g_55 = compute_v8_tile_px(1280, furniture_width_cm=55)

        for g in (g_220, g_165, g_85, g_55):
            self.assertTrue(9 <= g <= 34, f"grid_n fuera de 9..34: {g}")
            self.assertTrue(81 <= g * g <= 1156)

        self.assertTrue(
            t_220 < t_165 < t_85 < t_55,
            f"Escala no monótona: 220->{t_220}, 165->{t_165}, 85->{t_85}, 55->{t_55}",
        )

        roi = extract_clean_swatch_roi_v8(self.real_swatch_bytes)
        cal = calibrate_fabric_lightness_v8(roi.crop, boost=0.30, max_rgb=243)
        tile = make_toroidal_seamless_tile_v8(cal, tile_px=92, max_rgb=243)
        self.assertEqual(tile.size, (92, 92))
        self.assertLessEqual(max(e[1] for e in tile.getextrema()), 243)

        # Verificar ausencia de costuras en bordes toroidales X (x=91 vs x=0) e Y (y=91 vs y=0)
        raw_t = tile.tobytes()
        T = 92

        def _px_diff(x_a: int, y_a: int, x_b: int, y_b: int) -> float:
            oa = (y_a * T + x_a) * 3
            ob = (y_b * T + x_b) * 3
            return (
                abs(raw_t[oa] - raw_t[ob])
                + abs(raw_t[oa + 1] - raw_t[ob + 1])
                + abs(raw_t[oa + 2] - raw_t[ob + 2])
            ) / 3.0

        wrap_dx = sum(_px_diff(T - 1, y, 0, y) for y in range(T)) / T
        wrap_dy = sum(_px_diff(x, T - 1, x, 0) for x in range(T)) / T
        inner_dx = sum(_px_diff(x, y, x + 1, y) for y in range(0, T, 4) for x in range(10, T - 10)) / (23 * (T - 20))
        self.assertLessEqual(wrap_dx, max(14.5, inner_dx * 1.30), f"Costura X visible: wrap={wrap_dx:.2f} vs inner={inner_dx:.2f}")
        self.assertLessEqual(wrap_dy, max(14.5, inner_dx * 1.30), f"Costura Y visible: wrap={wrap_dy:.2f} vs inner={inner_dx:.2f}")

    def test_build_v8_conditioning_canvas_performance_halo_lazy_mosaic_and_room_frame(self) -> None:
        cold_wall_ms = []
        cold_cpu_ms = []
        art_white = None
        for _ in range(5):
            clear_v8_composer_cache()
            t0_wall = time.perf_counter()
            t0_cpu = time.process_time()
            art_white = build_v8_conditioning_canvas(
                furniture_bytes=self.studio_sofa_bytes,
                fabric_bytes=self.real_swatch_bytes,
                sample_name="MUESTRA_NATURAL.jpg",
                furniture_name="SOFA_CORVINO.jpg",
                furniture_width_cm=220.0,
                furniture_type="SOFA",
            )
            cold_cpu_ms.append((time.process_time() - t0_cpu) * 1000.0)
            cold_wall_ms.append((time.perf_counter() - t0_wall) * 1000.0)

        assert art_white is not None
        median_cpu_ms = statistics.median(cold_cpu_ms)
        median_wall_ms = statistics.median(cold_wall_ms)
        max_wall_ms = max(cold_wall_ms)

        t1 = time.perf_counter()
        art_hit = build_v8_conditioning_canvas(
            furniture_bytes=self.studio_sofa_bytes,
            fabric_bytes=self.real_swatch_bytes,
            sample_name="MUESTRA_NATURAL.jpg",
            furniture_name="SOFA_CORVINO.jpg",
            furniture_width_cm=220.0,
            furniture_type="SOFA",
        )
        hit_ms = (time.perf_counter() - t1) * 1000.0

        self.assertLess(median_cpu_ms, 280.0, f"Mediana CPU en frío excedió 280 ms: {median_cpu_ms:.1f} ms ({cold_cpu_ms})")
        self.assertLess(median_wall_ms, 420.0, f"Mediana wall-clock en frío excedió 420 ms: {median_wall_ms:.1f} ms ({cold_wall_ms})")
        self.assertLess(max_wall_ms, 550.0, f"Construcción wall-clock en frío excedió 550 ms: {max_wall_ms:.1f} ms ({cold_wall_ms})")
        self.assertLess(hit_ms, 5.0, f"Caché LRU no respondió al instante: {hit_ms:.3f} ms")
        self.assertIs(art_white, art_hit)
        self.assertEqual(art_white.canvas_size, (1280, 1280))
        self.assertTrue(81 <= art_white.total_tiles <= 1156)
        self.assertEqual(art_white.total_tiles, 484)
        self.assertEqual(art_white.isolation_mode, "alpha_halo")
        self.assertTrue(12 <= art_white.halo_or_frame_px <= 18)
        self.assertEqual(art_white.canvas_filename, "SOFA_CORVINO_V8_LIENZO_ESCALA.png")
        self.assertEqual(art_white.calibrated_swatch_filename, "MUESTRA_NATURAL_V8_LUZ30.png")

        # Verificar codificación perezosa (lazy) de mosaic_only_png bajo demanda y contabilidad exacta de _CANVAS_CACHE_BYTES
        self.assertIsNone(art_white._mosaic_only_png_cache)
        mos_bytes = art_white.mosaic_only_png
        self.assertIsNotNone(art_white._mosaic_only_png_cache)
        with Image.open(io.BytesIO(mos_bytes)) as mos_im:
            self.assertEqual(mos_im.size, (768, 768))
            self.assertEqual(mos_im.mode, "RGB")
            self.assertLessEqual(max(e[1] for e in mos_im.getextrema()), 243)

        for idx_ev in range(7):
            sw_ev = _encode_png(Image.new("RGB", (64, 64), (170 + idx_ev, 165, 158)))
            ev_art = build_v8_conditioning_canvas(
                furniture_bytes=self.studio_sofa_bytes,
                fabric_bytes=sw_ev,
                sample_name=f"FLAT_{idx_ev}.png",
                furniture_name=f"SOFA_{idx_ev}.png",
                furniture_width_cm=220.0,
                furniture_type="SOFA",
            )
            _ = ev_art.mosaic_only_png
        self.assertEqual(
            fc_v8._CANVAS_CACHE_BYTES,
            sum(v.approx_bytes() for v in fc_v8._CANVAS_CACHE.values()),
        )

        # Verificar acotado defensivo de knee_rgb en _apply_ratio_preserving_rgb_ceiling
        hi_im = Image.new("RGB", (16, 16), (252, 248, 240))
        for bad_knee in (-1, 0, 250):
            clamped_im = _apply_ratio_preserving_rgb_ceiling(hi_im, max_rgb=243, knee_rgb=bad_knee)
            self.assertLessEqual(max(e[1] for e in clamped_im.getextrema()), 243)

        with Image.open(io.BytesIO(art_white.canvas_png)) as cv_im:
            self.assertEqual(cv_im.size, (1280, 1280))
            self.assertEqual(cv_im.mode, "RGB")
            # Las esquinas exteriores son mosaico de tela (<= 243, no blanco puro 255)
            self.assertLessEqual(max(cv_im.getpixel((12, 12))), 243)

        # Mueble RGBA transparente -> alpha_halo
        art_rgba = build_v8_conditioning_canvas(
            furniture_bytes=self.rgba_chair_bytes,
            fabric_bytes=self.real_swatch_bytes,
            furniture_name="SILLON_RGBA.png",
            furniture_width_cm=85.0,
            furniture_type="SILLON",
        )
        self.assertEqual(art_rgba.isolation_mode, "alpha_halo")

        # Mueble con fondo de cuarto beige -> white_frame (sin comer tapicería clara!)
        art_room = build_v8_conditioning_canvas(
            furniture_bytes=self.room_sofa_bytes,
            fabric_bytes=self.real_swatch_bytes,
            furniture_name="SOFA_CUARTO.jpg",
            furniture_width_cm=165.0,
            furniture_type="LOVESEAT",
        )
        self.assertEqual(art_room.isolation_mode, "white_frame")
        self.assertTrue(10 <= art_room.halo_or_frame_px <= 14)

        # Guardia de seguridad: sofá blanco (248,248,246) sin contorno sobre #FFFFFF cae a white_frame sin perforarse
        wow_im = Image.new("RGB", (800, 600), (255, 255, 255))
        ImageDraw.Draw(wow_im).rounded_rectangle((120, 120, 680, 480), radius=30, fill=(248, 248, 246))
        art_wow = build_v8_conditioning_canvas(
            furniture_bytes=_encode_png(wow_im),
            fabric_bytes=self.real_swatch_bytes,
            furniture_name="SOFA_BLANCO.png",
            furniture_width_cm=200.0,
            furniture_type="SOFA",
        )
        self.assertEqual(art_wow.isolation_mode, "white_frame")
        with Image.open(io.BytesIO(art_wow.canvas_png)) as cv_wow:
            self.assertEqual(cv_wow.getpixel((640, 640)), (248, 248, 246))


class TestV8PromptServiceAndMultimodal(unittest.TestCase):
    """6. Verificación de AIPromptServiceV8 en los 9 modos + 3/4 Derecha, seguridad y API multimodal."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.real_swatch_bytes = _load_test_swatch_bytes()
        cls.studio_sofa_bytes = _make_studio_white_sofa_bytes()
        cls.fab_ana = v8.analyze_fabric_v8_local(cls.real_swatch_bytes, sample_name="TELA_NATURAL.jpg")
        cls.wood_ana = {
            "name": "PAROTA NATURAL",
            "color_description": "warm golden-brown parota heartwood",
            "texture_detail": "pronounced natural parota grain",
            "light_interaction": "soft satin-matte timber sheen",
        }

    def test_zero_hardcoded_api_keys_and_env_only_auth(self) -> None:
        svc_src = (REPO_ROOT / "services" / "ai_prompt_service_v8.py").read_text(encoding="utf-8")
        self.assertNotIn("QVEuQWI4", svc_src)
        self.assertNotIn("AIza", svc_src)
        self.assertEqual(v8._builtin_key, "")
        self.assertEqual(v8.default_api_key, "")

        prev_gem = os.environ.pop("GEMINI_API_KEY", None)
        prev_goo = os.environ.pop("GOOGLE_API_KEY", None)
        try:
            # Si no hay .env ni variables de entorno, get_api_key debe devolver cadena vacía ""
            env_file = REPO_ROOT / ".env"
            if not env_file.exists():
                self.assertEqual(v8.get_api_key(), "")
            os.environ["GEMINI_API_KEY"] = "AIzaTestKeyForV8EnvVerification123456789"
            self.assertEqual(v8.get_api_key(), "AIzaTestKeyForV8EnvVerification123456789")
        finally:
            if prev_gem is not None:
                os.environ["GEMINI_API_KEY"] = prev_gem
            else:
                os.environ.pop("GEMINI_API_KEY", None)
            if prev_goo is not None:
                os.environ["GOOGLE_API_KEY"] = prev_goo
            else:
                os.environ.pop("GOOGLE_API_KEY", None)

    def test_all_9_modes_and_34_derecha_dynamic_slot_alignment_and_mandates(self) -> None:
        # 1) Catálogo 7 vistas con tela + madera
        res_cat = v8.build_prompts(
            mode="catalogo",
            furniture_name="SOFA_CORVINO",
            tipo_mueble="SOFA",
            medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
            furniture_filenames=["SOFA_CORVINO.jpg"],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_analysis=self.fab_ana,
            wood_label="PAROTA NATURAL",
            wood_filename="PAROTA_NATURAL.jpg",
            wood_analysis=self.wood_ana,
        )
        self.assertEqual([it["id"] for it in res_cat["items"]], VIEW_IDS)

        # Vista 1 (sin ancla, con tela + madera): Image 1 Mueble, Image 2 Lienzo Escala V8, Image 3 Madera (sin 3.ª foto macro)
        v1 = res_cat["items"][0]
        self.assertEqual(len(v1["attachment_guide"]), 3)
        self.assertIn("SOFA_CORVINO.jpg", v1["attachment_guide"][0])
        self.assertIn("SOFA_CORVINO_V8_LIENZO_ESCALA.png", v1["attachment_guide"][1])
        self.assertIn("PAROTA_NATURAL.jpg", v1["attachment_guide"][2])
        self.assertNotIn("V8_LUZ30", v1["google_ai_studio"])
        self.assertIn('Image 2 ("SOFA_CORVINO_V8_LIENZO_ESCALA.png")', v1["google_ai_studio"])
        self.assertIn('Image 3 ("PAROTA_NATURAL.jpg")', v1["google_ai_studio"])
        self.assertIn("EL CASCO COMPLETO", v1["google_ai_studio"])
        self.assertIn("NEVER keep tiled fabric background", v1["google_ai_studio"])
        self.assertIn("#FFFFFF", v1["google_ai_studio"])
        self.assertIn("0% ground shadow", v1["google_ai_studio"])
        self.assertIn("2054 x 2054", v1["google_ai_studio"])

        # Vista 2 (con ancla Vista 1 en Image 4!)
        v2 = res_cat["items"][1]
        self.assertIn("Image 4 (APPROVED VISTA 1 ANCHOR", v2["google_ai_studio"])
        self.assertEqual(len(v2["attachment_guide"]), 4)

        # Vista 6 (Plano CAD): solo Image 1, sin mosaico de tela
        v6_bp = res_cat["items"][5]
        self.assertEqual(len(v6_bp["attachment_guide"]), 1)
        self.assertNotIn("V8_LIENZO_ESCALA", v6_bp["google_ai_studio"])
        self.assertIn("Ancho: 220 cm", v6_bp["google_ai_studio"])

        # Vista 7 (Entorno): habitación natural prohibiendo mosaico en paredes
        v7_env = res_cat["items"][6]
        self.assertIn("NEVER render tiled fabric wallpaper on room walls", v7_env["google_ai_studio"])
        self.assertIn("Image 4 (APPROVED VISTA 1 ANCHOR", v7_env["google_ai_studio"])

        # 2) vista_suelta (las 11 vistas)
        for vid in ALL_SINGLE_VIEWS:
            rv = v8.build_prompts(
                mode="vista_suelta",
                furniture_name="SILLON_NILO",
                tipo_mueble="SILLON",
                medidas_texto="85 cm frente x 85 cm fondo x 78 cm alto",
                vista_id=vid,
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
                fabric_analysis=self.fab_ana,
            )
            self.assertEqual(len(rv["items"]), 1)
            self.assertEqual(rv["items"][0]["id"], vid)

        # 3) material (fabric_only, wood_only, dual) sincronizado con build_ordered_photo_thumbs_v8
        for mm in ("fabric_only", "wood_only", "dual"):
            rm = v8.build_prompts(
                mode="material",
                material_mode=mm,
                furniture_name="SOFA_AMARETO",
                tipo_mueble="SOFA",
                medidas_texto="210 cm frente x 90 cm fondo x 80 cm alto",
                furniture_filenames=["SOFA_AMARETO.jpg"],
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
                fabric_analysis=self.fab_ana,
                wood_label="PAROTA NATURAL",
                wood_filename="PAROTA_NATURAL.jpg",
                wood_analysis=self.wood_ana,
            )
            thumbs_mm = build_ordered_photo_thumbs_v8(
                mode="material",
                material_mode=mm,
                m_names=["SOFA_AMARETO.jpg"],
                m_bytes=[self.studio_sofa_bytes],
                m_source="RENDER",
                fabric_name="TELA_NATURAL.jpg",
                fabric_bytes=self.real_swatch_bytes,
                wood_name="PAROTA_NATURAL.jpg",
                wood_bytes=self.studio_sofa_bytes,
                batch_views_files=[],
                tipo_mueble="SOFA",
                medidas_texto="210 cm frente x 90 cm fondo x 80 cm alto",
            )
            guide_mm = rm["items"][0]["attachment_guide"]
            self.assertEqual(len(thumbs_mm), len(guide_mm), f"Desajuste de slots en material/{mm}")
            for idx_s, (th_tuple, g_str) in enumerate(zip(thumbs_mm, guide_mm), start=1):
                self.assertIn(th_tuple[0], g_str, f"Slot {idx_s} no coincide en {mm}: {th_tuple[0]} vs {g_str}")

        # 4) entorno, plano, extraer, hd (mueble y muestra plana)
        r_ent = v8.build_prompts(
            mode="entorno",
            furniture_name="SOFA_SALA",
            tipo_mueble="SOFA",
            lugar_casa="Sala contemporánea luminosa",
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_analysis=self.fab_ana,
        )
        self.assertIn("Sala contemporánea luminosa", r_ent["items"][0]["google_ai_studio"])
        self.assertNotIn("Pure seamless solid digital white background", r_ent["items"][0]["google_ai_studio"])

        r_pl = v8.build_prompts(mode="plano", furniture_name="MESA", tipo_mueble="MESA", medidas_texto="120x60x45")
        self.assertEqual(len(r_pl["items"][0]["attachment_guide"]), 1)

        r_ext = v8.build_prompts(
            mode="extraer",
            furniture_name="SILLON_EXT",
            tipo_mueble="SILLON",
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_analysis=self.fab_ana,
        )
        self.assertIn("NEVER keep tiled fabric background", r_ext["items"][0]["google_ai_studio"])

        r_hd_furn = v8.build_prompts(
            mode="hd",
            furniture_name="SILLON_HD",
            tipo_mueble="SILLON",
            white_bg_enabled=False,
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_analysis=self.fab_ana,
        )
        self.assertIn("STRICT 1:1 SUBJECT LOCK", r_hd_furn["items"][0]["google_ai_studio"])

        r_hd_sw = v8.build_prompts(
            mode="hd",
            furniture_name="MUESTRA_PLANA",
            furniture_analysis={"is_material_swatch": True, "furniture_item": "flat textile swatch"},
            white_bg_enabled=False,
        )
        self.assertIn("FLAT 2D SWATCH ONLY", r_hd_sw["items"][0]["google_ai_studio"])

        # 5) vistas_tela (con lienzo V8 por vista) y clonar_color
        with _offline_ai_clients(v8):
            r_vt = v8.build_prompts(
                mode="vistas_tela",
                furniture_name="SOFA_LOTE",
                tipo_mueble="SOFA",
                medidas_texto="220 cm frente x 90 cm fondo x 80 cm alto",
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
                fabric_analysis=self.fab_ana,
                batch_ref_bytes=self.real_swatch_bytes,
                batch_views=[("frente.png", self.studio_sofa_bytes), ("perfil.png", self.studio_sofa_bytes)],
                api_key="",
            )
            self.assertEqual(len(r_vt["items"]), 2)
            self.assertEqual(len(r_vt["items"][0]["attachment_guide"]), 2)
            self.assertIn("frente_V8_LIENZO_ESCALA.png", r_vt["items"][0]["google_ai_studio"])
            self.assertIn("perfil_V8_LIENZO_ESCALA.png", r_vt["items"][1]["google_ai_studio"])
            self.assertNotIn("V8_LUZ30", r_vt["items"][0]["google_ai_studio"])
            self.assertNotIn("Image 3", r_vt["items"][0]["google_ai_studio"])

            r_cc = v8.build_prompts(
                mode="clonar_color",
                furniture_name="BASE_COLOR",
                tipo_mueble="SILLON",
                batch_ref_filename="BASE_COLOR.png",
                batch_ref_bytes=self.studio_sofa_bytes,
                batch_views=[("vista_lat.png", self.studio_sofa_bytes)],
                api_key="",
            )
            self.assertEqual(len(r_cc["items"]), 1)
            self.assertIn("BASE_COLOR.png", r_cc["items"][0]["google_ai_studio"])

        # 6) Botón maestro 3/4 Derecha 2054x2054 #FFFFFF 0% sombras
        r_34 = v8.build_34_derecha_2054_prompts(
            furniture_name="SOFA_CORVINO",
            tipo_mueble="SOFA",
            medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
            furniture_filenames=["SOFA_CORVINO.jpg"],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_analysis=self.fab_ana,
        )
        p34 = r_34["items"][0]["google_ai_studio"]
        self.assertIn("FACING TOWARD THE RIGHT", p34)
        self.assertIn("2054 x 2054", p34)
        self.assertIn("#FFFFFF", p34)
        self.assertIn("RGB 255,255,255", p34)
        self.assertIn("0% ground shadow", p34)
        self.assertIn("EL CASCO COMPLETO", p34)
        self.assertIn("NEVER keep tiled fabric background", p34)
        self.assertIn("OUTPUT FILE NAME: SOFA_CORVINO.png", p34)
        self.assertEqual(len(r_34["items"][0]["attachment_guide"]), 2)
        self.assertNotIn("V8_LUZ30", p34)

    def test_generate_catalog_photo_no_flux_fallback_and_border_guard_retry(self) -> None:
        sig_cat = inspect.signature(AIPromptServiceV8.generate_catalog_photo)
        sig_34 = inspect.signature(AIPromptServiceV8.generate_image_34_derecha_2054)
        self.assertIs(sig_cat.parameters["allow_flux_fallback"].default, False)
        self.assertIs(sig_34.parameters["allow_flux_fallback"].default, False)
        self.assertEqual(DEFAULT_V8_IMAGE_MODELS[0], "gemini-2.5-flash-image")

        # Simular respuesta 1 con fuga de mosaico en borde (<95% #FFFFFF) y respuesta 2 limpia #FFFFFF
        leaked_im = Image.new("RGB", (512, 512), (210, 200, 185))
        clean_im = Image.new("RGB", (512, 512), (255, 255, 255))
        ImageDraw.Draw(clean_im).rectangle((160, 160, 352, 352), fill=(222, 218, 212))
        leaked_b64 = base64.b64encode(_encode_png(leaked_im)).decode("ascii")
        clean_b64 = base64.b64encode(_encode_png(clean_im)).decode("ascii")

        calls = []

        class _FakeInline:
            def __init__(self, d):
                self.data = d

        class _FakePart:
            def __init__(self, d):
                self.inline_data = _FakeInline(d)

        class _FakeContent:
            def __init__(self, d):
                self.parts = [_FakePart(d)]

        class _FakeCand:
            def __init__(self, d):
                self.content = _FakeContent(d)

        class _FakeResp:
            def __init__(self, d):
                self.candidates = [_FakeCand(d)]

        class _FakeModels:
            def generate_content(self, model, contents, config=None):
                calls.append((model, contents))
                return _FakeResp(leaked_b64 if len(calls) == 1 else clean_b64)

        class _FakeClient:
            models = _FakeModels()

        # Inyectar stub temporal de google.genai.types si no está instalado en este intérprete
        had_google = "google" in sys.modules
        had_genai = "google.genai" in sys.modules
        g_pkg = None
        had_genai_attr = False
        prev_genai_attr = None
        if not had_genai:
            g_pkg = sys.modules.get("google") or types.ModuleType("google")
            had_genai_attr = hasattr(g_pkg, "genai")
            prev_genai_attr = getattr(g_pkg, "genai", None)
            genai_pkg = types.ModuleType("google.genai")
            types_mod = types.ModuleType("google.genai.types")

            class _GenCfg:
                def __init__(self, **kw):
                    self.kw = kw

            types_mod.GenerateContentConfig = _GenCfg
            genai_pkg.types = types_mod
            g_pkg.genai = genai_pkg
            sys.modules["google"] = g_pkg
            sys.modules["google.genai"] = genai_pkg
            sys.modules["google.genai.types"] = types_mod

        svc = AIPromptServiceV8()
        svc.get_client = lambda k=None: _FakeClient()  # type: ignore[method-assign]
        try:
            out, err = svc.generate_catalog_photo(
                prompt_text="Test V8 generation",
                primary_bytes=self.studio_sofa_bytes,
                fabric_bytes=self.real_swatch_bytes,
                pure_white_border=True,
                api_key="AIzaFakeUnitTestKey1234567890123456789",
            )
        finally:
            if not had_genai:
                sys.modules.pop("google.genai.types", None)
                sys.modules.pop("google.genai", None)
                if not had_google:
                    sys.modules.pop("google", None)
                elif g_pkg is not None:
                    if had_genai_attr:
                        g_pkg.genai = prev_genai_attr
                    elif hasattr(g_pkg, "genai"):
                        delattr(g_pkg, "genai")

        self.assertIsNone(err)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(len(calls), 2, "Debió reintentar al detectar borde contaminado <95% blanco")
        self.assertEqual(len(calls[0][1]), 3)  # [prompt, orig_furn, v8_canvas] (2 fotos limpias, sin 3.ª macro)
        self.assertGreaterEqual(out["border_white_purity"], 0.99)
        self.assertEqual((out["width"], out["height"]), (2054, 2054))

    def test_combinatorial_slot_parity_missing_materials_has_ref_clonar_color_and_swatch_ceiling(self) -> None:
        combos = [
            ("furn_only", ["SOFA_CORVINO.jpg"], [self.studio_sofa_bytes], "", "", None, None, "", "", None, None),
            ("furn_fab", ["SOFA_CORVINO.jpg"], [self.studio_sofa_bytes], "TELA", "TELA.jpg", self.real_swatch_bytes, self.fab_ana, "", "", None, None),
            ("furn_wood", ["SOFA_CORVINO.jpg"], [self.studio_sofa_bytes], "", "", None, None, "PAROTA", "PAROTA_NATURAL.jpg", self.studio_sofa_bytes, self.wood_ana),
            ("furn_fab_wood", ["SOFA_CORVINO.jpg"], [self.studio_sofa_bytes], "TELA", "TELA.jpg", self.real_swatch_bytes, self.fab_ana, "PAROTA", "PAROTA_NATURAL.jpg", self.studio_sofa_bytes, self.wood_ana),
            ("furn_3angles_fab_wood", ["SOFA_CORVINO.jpg", "LAT.jpg", "TRAS.jpg"], [self.studio_sofa_bytes] * 3, "TELA", "TELA.jpg", self.real_swatch_bytes, self.fab_ana, "PAROTA", "PAROTA_NATURAL.jpg", self.studio_sofa_bytes, self.wood_ana),
        ]

        for cname, f_files, f_blist, flbl, ffn, fb, fa_in, wlbl, wfn, wb, wa_in in combos:
            for has_ref in (False, True):
                for mm in ("fabric_only", "wood_only", "dual"):
                    res_m = v8.build_prompts(
                        mode="material",
                        material_mode=mm,
                        furniture_name="SOFA_CORVINO",
                        tipo_mueble="SOFA",
                        furniture_filenames=f_files,
                        fabric_label=flbl,
                        fabric_filename=ffn,
                        fabric_analysis=fa_in,
                        wood_label=wlbl,
                        wood_filename=wfn,
                        wood_analysis=wa_in,
                        has_reference_imgs=has_ref,
                    )
                    pack_m = v8.build_v8_reference_pack(
                        mode="material",
                        material_mode=mm,
                        furniture_name="SOFA_CORVINO",
                        furniture_filenames=f_files,
                        furniture_bytes_list=f_blist,
                        fabric_label=flbl,
                        fabric_filename=ffn,
                        fabric_bytes=fb,
                        wood_label=wlbl,
                        wood_filename=wfn,
                        wood_bytes=wb,
                        tipo_mueble="SOFA",
                        has_ref=has_ref,
                    )
                    self.assertFalse(any(p["role"] == "v8_calibrated_swatch" for p in pack_m))
                    self.assertEqual(
                        res_m["items"][0]["attachment_guide"],
                        [p["guide_line"] for p in pack_m],
                        f"Desajuste de guía en material/{mm}/{cname}/ref={has_ref}",
                    )
                    ais_m = res_m["items"][0]["google_ai_studio"]
                    cited_m = sorted({int(m) for m in re.findall(r"\bImage\s+(\d+)\b", ais_m)})
                    self.assertEqual(cited_m, [p["slot_index"] for p in pack_m])
                    self.assertNotIn("V8_LUZ30", ais_m)
                    if not (fb and mm in ("fabric_only", "dual")):
                        self.assertNotIn("V8_LIENZO_ESCALA", ais_m)
                    if cname == "furn_wood" and mm == "dual":
                        self.assertIn('Image 2 ("PAROTA_NATURAL.jpg")', ais_m)

                for md in ("extraer", "hd", "entorno", "plano"):
                    res_std = v8.build_prompts(
                        mode=md,
                        furniture_name="SOFA_CORVINO",
                        tipo_mueble="SOFA",
                        furniture_filenames=f_files,
                        fabric_label=flbl,
                        fabric_filename=ffn,
                        fabric_analysis=fa_in,
                        wood_label=wlbl,
                        wood_filename=wfn,
                        wood_analysis=wa_in,
                        has_reference_imgs=has_ref,
                        white_bg_enabled=True,
                    )
                    pack_std = v8.build_v8_reference_pack(
                        mode=md,
                        furniture_name="SOFA_CORVINO",
                        furniture_filenames=f_files,
                        furniture_bytes_list=f_blist,
                        fabric_label=flbl,
                        fabric_filename=ffn,
                        fabric_bytes=fb,
                        wood_label=wlbl,
                        wood_filename=wfn,
                        wood_bytes=wb,
                        tipo_mueble="SOFA",
                        has_ref=has_ref,
                    )
                    self.assertFalse(any(p["role"] == "v8_calibrated_swatch" for p in pack_std))
                    self.assertEqual(res_std["items"][0]["attachment_guide"], [p["guide_line"] for p in pack_std])
                    ais_std = res_std["items"][0]["google_ai_studio"]
                    cited_std = sorted({int(m) for m in re.findall(r"\bImage\s+(\d+)\b", ais_std)})
                    self.assertEqual(cited_std, [p["slot_index"] for p in pack_std])
                    self.assertNotIn("V8_LUZ30", ais_std)
                    if not fb or md == "plano":
                        self.assertNotIn("V8_LIENZO_ESCALA", ais_std)

            # vistas_tela (incluyendo fabric_bytes=None sin tela!)
            with _offline_ai_clients(v8):
                res_vt = v8.build_prompts(
                    mode="vistas_tela",
                    furniture_name="SOFA_CORVINO",
                    tipo_mueble="SOFA",
                    fabric_label=flbl,
                    fabric_filename=ffn,
                    fabric_analysis=fa_in,
                    batch_ref_bytes=fb,
                    batch_views=[("vista1.jpg", self.studio_sofa_bytes)],
                    api_key="",
                )
            pack_vt = v8.build_v8_reference_pack(
                mode="vistas_tela",
                fabric_label=flbl,
                fabric_filename=ffn,
                fabric_bytes=fb,
                target_view=("vista1.jpg", self.studio_sofa_bytes),
                tipo_mueble="SOFA",
            )
            self.assertFalse(any(p["role"] == "v8_calibrated_swatch" for p in pack_vt))
            self.assertEqual(res_vt["items"][0]["attachment_guide"], [p["guide_line"] for p in pack_vt])
            ais_vt = res_vt["items"][0]["google_ai_studio"]
            cited_vt = sorted({int(m) for m in re.findall(r"\bImage\s+(\d+)\b", ais_vt)})
            self.assertEqual(cited_vt, [p["slot_index"] for p in pack_vt])
            self.assertNotIn("V8_LUZ30", ais_vt)
            if not fb:
                self.assertNotIn("V8_LIENZO_ESCALA", ais_vt)

        # clonar_color (white_bg_enabled=True) exige #FFFFFF, RGB 255,255,255, 0% sombras y 2054 x 2054 px
        with _offline_ai_clients(v8):
            res_cc = v8.build_prompts(
                mode="clonar_color",
                furniture_name="BASE_COLOR",
                tipo_mueble="SILLON",
                batch_ref_filename="BASE_COLOR.png",
                batch_ref_bytes=self.studio_sofa_bytes,
                batch_views=[("vista_lat.png", self.studio_sofa_bytes)],
                white_bg_enabled=True,
                api_key="",
            )
        ais_cc = res_cc["items"][0]["google_ai_studio"]
        self.assertIn("#FFFFFF", ais_cc)
        self.assertIn("RGB 255,255,255", ais_cc)
        self.assertIn("0% ground shadow", ais_cc)
        self.assertIn("2054 x 2054", ais_cc)

        # Techo <= 243 post-Lanczos en vista previa UI previa a elegir mueble/vistas (build_calibrated_swatch_preview_bytes)
        prev_default = v8.build_calibrated_swatch_preview_bytes(self.real_swatch_bytes)
        with Image.open(io.BytesIO(prev_default)) as sw_im1:
            self.assertLessEqual(max(e[1] for e in sw_im1.getextrema()), 243)

        prev_boosted = v8.build_calibrated_swatch_preview_bytes(
            self.real_swatch_bytes,
            custom_notes="quiero que hagas un 40%mas claro el tono de la tela",
        )
        with Image.open(io.BytesIO(prev_boosted)) as sw_im2:
            self.assertLessEqual(max(e[1] for e in sw_im2.getextrema()), 243)


class TestV8StudioUIAndZeroRegression(unittest.TestCase):
    """7. Verificación de UI V8, reglas GEMINI.md 1–4, enrutamiento main.py y cero regresión git."""

    def test_main_py_v8_version_options_normalization_and_routing(self) -> None:
        main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('["🤖 V8", "V7", "V6", "V1"]', main_src)
        self.assertIn('"V8" if "V8" in ver_raw', main_src)
        self.assertIn("from modules.prompt_studio_v8 import render_prompt_studio_v8", main_src)
        self.assertIn("render_prompt_studio_v8()", main_src)
        self.assertIn('initial_sidebar_state="collapsed"', main_src)

    def test_prompt_studio_v8_header_76px_zoom_3_buttons_folders_and_no_credentials(self) -> None:
        v8_src = (REPO_ROOT / "modules" / "prompt_studio_v8.py").read_text(encoding="utf-8")
        tree = ast.parse(v8_src)

        # Regla 1: 1-line header con selectbox y render_sku_autofill_bar("v8", inline_header=True)
        self.assertIn('render_sku_autofill_bar("v8", inline_header=True)', v8_src)
        self.assertIn('key="v8_keep_mode"', v8_src)
        self.assertNotIn("st.radio(", v8_src)
        # Cero campos de credenciales
        for forbidden_cred in ("api_key_input", "GEMINI_API_KEY", "Service Account", "secrets.toml", "password"):
            self.assertNotIn(forbidden_cred, v8_src)

        # Exactamente 3 botones de acción en el formulario principal + 1 botón de salto "🚀 Subir" en salida
        btn_keys = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "button":
                for kw in node.keywords:
                    if kw.arg == "key":
                        btn_keys.append(ast.unparse(kw.value))
        self.assertEqual(len(btn_keys), 4, f"Botones detectados inesperados en prompt_studio_v8.py: {btn_keys}")
        self.assertTrue(any("v8_btn_go_" in k for k in btn_keys))
        self.assertTrue(any("v8_btn_34_" in k for k in btn_keys))
        self.assertTrue(any("v8_btn_clear" in k for k in btn_keys))
        self.assertTrue(any("v8_goto_alta_" in k for k in btn_keys))

        # Miniaturas 76x76 px con zoom al pasar el cursor y botón Copiar foto
        captured = []
        orig_html = st_components.html
        try:
            st_components.html = lambda doc, **kw: captured.append((doc, kw))
            thumbs = build_ordered_photo_thumbs_v8(
                mode="catalogo",
                material_mode="fabric_only",
                m_names=["SOFA_CORVINO.jpg"],
                m_bytes=[_make_studio_white_sofa_bytes()],
                m_source="RENDER",
                fabric_name="TELA_NATURAL.jpg",
                fabric_bytes=_load_test_swatch_bytes(),
                wood_name="",
                wood_bytes=None,
                batch_views_files=[],
                tipo_mueble="SOFA",
                medidas_texto="220x95x82",
            )
            render_v8_photos_strip_76(thumbs, key_prefix="test_v8")
        finally:
            st_components.html = orig_html

        self.assertEqual(
            [t[0] for t in thumbs],
            ["SOFA_CORVINO.jpg", make_v8_canvas_filename("SOFA_CORVINO.jpg")],
        )
        self.assertEqual(len(captured), 1)
        strip_html = captured[0][0]
        self.assertIn("width: 76px;", strip_html)
        self.assertIn("height: 76px;", strip_html)
        self.assertIn("transform: scale(", strip_html)
        self.assertEqual(strip_html.count("🖼️ Copiar foto"), 2)
        self.assertIn("CREATA_PROMPTS_COPY_IMAGE", strip_html)
        self.assertNotIn("writeText", strip_html)

        # Regla 4: Carpetas RENDER + SUBIR (11_rR-qhgM02Sfx9zw7uHU5AwXvTpKD4p) + Cotización + SM_MUEBLERIA, ThreadPoolExecutor y BFS
        self.assertEqual(FOLDER_MUEBLES_RENDER_DRIVE_ID, "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX")
        self.assertEqual(FOLDER_MUEBLES_SUBIR_DRIVE_ID, "11_rR-qhgM02Sfx9zw7uHU5AwXvTpKD4p")
        self.assertEqual(FOLDER_MUEBLES_SM_MUEBLERIA_DRIVE_ID, "1P06GIuVHFPhQtE2kvPX-_JPA9A6N-qoF")
        self.assertEqual(FOLDER_TELAS_DRIVE_ID, "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul")
        self.assertEqual(FOLDER_TELAS_ODOO_DRIVE_ID, "12gsKZVs6rFonOO8CIxokuE73bxhq8tS9")
        self.assertEqual(
            set(FURNITURE_FOLDER_CHOICES.values()),
            {"ALL", "RENDER", "SUBIR", "COTIZACION", "SM_MUEBLERIA"},
        )
        self.assertEqual(_resolve_furniture_drive_id("RENDER"), "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX")
        self.assertEqual(_resolve_furniture_drive_id("SUBIR"), "11_rR-qhgM02Sfx9zw7uHU5AwXvTpKD4p")
        self.assertTrue(_FURNITURE_FOLDER_SPECS["COTIZACION"]["drive_path"])
        self.assertIn("ThreadPoolExecutor", v8_src)
        self.assertIn("get_multiple_drive_folders_files", v8_src)
        self.assertIn('st.session_state["v7_last_photo_stem"] = name', v8_src)
        self.assertIn('st.session_state["_pending_active_app"] = "🚀 Alta de Fotos"', v8_src)

    def test_clear_v8_form_preserves_mode_and_suboptions_and_zip_packs_v8_artifacts(self) -> None:
        with _isolated_streamlit_session(st):
            st.session_state.update({
                "v8_keep_mode": "Tela / Madera",
                "v8_keep_matmode": "Tela + madera",
                "v8_keep_vista": "3/4 Derecha",
                "v8_keep_room": "Sala",
                "v8_keep_folder": "📤 SUBIR",
                "sku_input_v8": "SKU-V8-01",
                "field_tipo_v8": "SOFA",
                "field_medidas_v8": "220x95x82",
                "sku_loaded_data_v8": {"tipo_mueble": "SOFA"},
                "sku_last_searched_v8": "SKU-V8-01",
                "v8_notas_4": "Costura francesa",
                "v8_picked_mueble_4": {"name": "SOFA"},
                "v8_result": {"items": []},
                "v8_last_photo_stem": "SOFA_CORVINO",
                "v7_last_photo_stem": "SOFA_CORVINO",
                "sku_input_v7": "INTACTO_V7",
                "clear_key_v8": 4,
            })
            _clear_v8_form(4)

            # Modo y sub-opciones intactos (Regla 2)
            self.assertEqual(st.session_state.get("v8_keep_mode"), "Tela / Madera")
            self.assertEqual(st.session_state.get("v8_keep_matmode"), "Tela + madera")
            self.assertEqual(st.session_state.get("v8_keep_vista"), "3/4 Derecha")
            self.assertEqual(st.session_state.get("v8_keep_room"), "Sala")
            self.assertEqual(st.session_state.get("v8_keep_folder"), "📤 SUBIR")
            self.assertEqual(st.session_state.get("sku_input_v7"), "INTACTO_V7")
            self.assertEqual(st.session_state.get("clear_key_v8"), 5)

            # Campos temporales borrados
            for cleared_k in (
                "sku_input_v8",
                "field_tipo_v8",
                "field_medidas_v8",
                "sku_loaded_data_v8",
                "sku_last_searched_v8",
                "v8_notas_4",
                "v8_picked_mueble_4",
                "v8_result",
                "v8_last_photo_stem",
                "v7_last_photo_stem",
            ):
                self.assertNotIn(cleared_k, st.session_state)

        # Verificar ZIP limpio de 2 insumos V8 (mueble + <mueble>_V8_LIENZO_ESCALA.png, sin 3.ª foto macro)
        art = build_v8_conditioning_canvas(
            furniture_bytes=_make_studio_white_sofa_bytes(),
            fabric_bytes=_load_test_swatch_bytes(),
            sample_name="TELA_NATURAL.jpg",
            furniture_name="SOFA_ZIP.jpg",
            furniture_width_cm=220.0,
            furniture_type="SOFA",
        )
        r34 = v8.build_34_derecha_2054_prompts(
            furniture_name="SOFA_ZIP",
            tipo_mueble="SOFA",
            furniture_filenames=["SOFA_ZIP.jpg"],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
        )
        r34["mueble_name"] = "SOFA_ZIP"
        r34["ref_images"] = [
            ("SOFA_ZIP.jpg", _make_studio_white_sofa_bytes()),
            (art.canvas_filename, art.canvas_png),
        ]
        z_bytes = _build_zip_v8(r34, include_images=True)
        with zipfile.ZipFile(io.BytesIO(z_bytes), "r") as zf:
            names = set(zf.namelist())
        self.assertIn("prompts/SOFA_ZIP.txt", names)
        self.assertIn("insumos/SOFA_ZIP.jpg", names)
        self.assertIn("insumos/SOFA_ZIP_V8_LIENZO_ESCALA.png", names)
        self.assertFalse(any("_V8_LUZ30.png" in n for n in names))

    def test_vista_suelta_plano_tecnico_strip_and_zip_1_slot_and_blank_sku_tile_parity(self) -> None:
        sofa_bytes = _make_studio_white_sofa_bytes()
        swatch_bytes = _load_test_swatch_bytes()

        # 1) vista_suelta + vista_plano_tecnico ("6 · Plano Medidas"): prompt, tira 76x76 y ZIP con 1 sola ranura
        res_vp = v8.build_prompts(
            mode="vista_suelta",
            vista_id="vista_plano_tecnico",
            furniture_name="SOFA_CORVINO",
            furniture_filenames=["SOFA_CORVINO.jpg"],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            wood_label="PAROTA",
            wood_filename="PAROTA_NATURAL.jpg",
        )
        thumbs_vp = build_ordered_photo_thumbs_v8(
            mode="vista_suelta",
            vista_id="vista_plano_tecnico",
            material_mode="dual",
            m_names=["SOFA_CORVINO.jpg"],
            m_bytes=[sofa_bytes],
            m_source="RENDER",
            fabric_name="TELA_NATURAL.jpg",
            fabric_bytes=swatch_bytes,
            wood_name="PAROTA_NATURAL.jpg",
            wood_bytes=sofa_bytes,
            batch_views_files=[],
            tipo_mueble="SOFA",
            medidas_texto="220x95x82",
        )
        pack_vp = v8.build_v8_reference_pack(
            mode="vista_suelta",
            vista_id="vista_plano_tecnico",
            material_mode="dual",
            furniture_name="SOFA_CORVINO",
            furniture_filenames=["SOFA_CORVINO.jpg"],
            furniture_bytes_list=[sofa_bytes],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_bytes=swatch_bytes,
            wood_label="PAROTA",
            wood_filename="PAROTA_NATURAL.jpg",
            wood_bytes=sofa_bytes,
            tipo_mueble="SOFA",
            medidas_texto="220x95x82",
        )
        self.assertEqual(len(res_vp["items"][0]["attachment_guide"]), 1)
        self.assertEqual([t[0] for t in thumbs_vp], ["SOFA_CORVINO.jpg"])
        self.assertEqual([p["filename"] for p in pack_vp], ["SOFA_CORVINO.jpg"])

        res_vp["mueble_name"] = "SOFA_CORVINO"
        res_vp["ref_images"] = [(p["filename"], p["bytes"]) for p in pack_vp if p.get("bytes")]
        zip_vp = _build_zip_v8(res_vp, include_images=True)
        with zipfile.ZipFile(io.BytesIO(zip_vp), "r") as zf_vp:
            insumos_vp = [n for n in zf_vp.namelist() if n.startswith("insumos/")]
        self.assertEqual(insumos_vp, ["insumos/SOFA_CORVINO.jpg"])

        # 2) Paridad de punta a punta con SKU/tipo en blanco (analyze_all_parallel + tira 76x76 + prompts + 3/4 Der + ZIP)
        thumbs_blank = build_ordered_photo_thumbs_v8(
            mode="catalogo",
            material_mode="fabric_only",
            m_names=["SOFA_CORVINO.jpg"],
            m_bytes=[sofa_bytes],
            m_source="RENDER",
            fabric_name="TELA_NATURAL.jpg",
            fabric_bytes=swatch_bytes,
            wood_name="",
            wood_bytes=None,
            batch_views_files=[],
            tipo_mueble=resolve_v8_furniture_type_hint("", "", "SOFA_CORVINO", "SOFA_CORVINO.jpg"),
            medidas_texto="",
        )
        strip_canvas_bytes = thumbs_blank[1][1]

        for notas_case in ("", "tapizar todo el sofá"):
            with _offline_ai_clients(v8):
                f_ana, w_ana, t_ana = v8.analyze_all_parallel(
                    furniture_bytes=[sofa_bytes],
                    fabric_bytes=swatch_bytes,
                    fabric_name="TELA_NATURAL.jpg",
                    notas_ia=notas_case,
                )
            res_blank = v8.build_prompts(
                mode="catalogo",
                furniture_name="SOFA_CORVINO",
                furniture_analysis=f_ana,
                wood_analysis=w_ana,
                fabric_analysis=t_ana,
                tipo_mueble="",
                medidas_texto="",
                furniture_filenames=["SOFA_CORVINO.jpg"],
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
            )
            res_34_blank = v8.build_34_derecha_2054_prompts(
                furniture_name="SOFA_CORVINO",
                furniture_analysis=f_ana,
                wood_analysis=w_ana,
                fabric_analysis=t_ana,
                tipo_mueble="",
                medidas_texto="",
                furniture_filenames=["SOFA_CORVINO.jpg"],
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
            )
            resolved_blank_tipo = resolve_v8_furniture_type_hint(
                tipo_mueble="",
                ai_furniture_item=str(f_ana.get("furniture_item") or ""),
                furniture_name="SOFA_CORVINO",
                primary_filename="SOFA_CORVINO.jpg",
            )
            pack_blank = v8.build_v8_reference_pack(
                mode="catalogo",
                furniture_name="SOFA_CORVINO",
                furniture_filenames=["SOFA_CORVINO.jpg"],
                furniture_bytes_list=[sofa_bytes],
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
                fabric_bytes=swatch_bytes,
                tipo_mueble=resolved_blank_tipo,
                medidas_texto="",
            )
            pack_legacy_caller = v8.build_v8_reference_pack(
                mode="catalogo",
                furniture_name="SOFA_CORVINO",
                furniture_filenames=["SOFA_CORVINO.jpg"],
                furniture_bytes_list=[sofa_bytes],
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
                fabric_bytes=swatch_bytes,
                tipo_mueble=("" or f_ana.get("furniture_item") or "SOFA_CORVINO"),
                medidas_texto="",
            )

            canvas_entry = next(p for p in pack_blank if p["role"] == "v8_scale_canvas")
            canvas_legacy = next(p for p in pack_legacy_caller if p["role"] == "v8_scale_canvas")
            self.assertEqual(canvas_entry["total_tiles"], 484)
            self.assertEqual(canvas_legacy["total_tiles"], 484)
            self.assertEqual(res_blank["dims"]["category"], "seating")
            self.assertEqual(res_34_blank["dims"]["category"], "seating")
            self.assertIn("484 seamless reduced", res_blank["items"][0]["google_ai_studio"])
            self.assertIn("484 seamless reduced", res_34_blank["items"][0]["google_ai_studio"])
            self.assertEqual(strip_canvas_bytes, canvas_entry["bytes"])
            self.assertEqual(strip_canvas_bytes, canvas_legacy["bytes"])

            res_blank["mueble_name"] = "SOFA_CORVINO"
            res_blank["ref_images"] = [(p["filename"], p["bytes"]) for p in pack_blank if p.get("bytes")]
            zip_blank = _build_zip_v8(res_blank, include_images=True)
            with zipfile.ZipFile(io.BytesIO(zip_blank), "r") as zf_b:
                zip_canvas_bytes = zf_b.read("insumos/SOFA_CORVINO_V8_LIENZO_ESCALA.png")
            self.assertEqual(strip_canvas_bytes, zip_canvas_bytes)

    def test_git_zero_regression_on_tracked_v1_through_v7_files(self) -> None:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "diff", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
        modified_tracked = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        allowed = {
            "main.py",
            "RENDER_DEPLOY.md",
            "modules/prompt_studio_v8.py",
            "services/ai_prompt_service_v8.py",
            "services/fabric_composer_v8.py",
            "services/observability.py",
            "services/gemini_runtime.py",
            "services/sheets_service.py",
            "services/ai_prompt_service_v7.py",
            "services/ai_prompt_service_v5.py",
            "tests/test_v7.py",
            "tests/test_v8.py",
            "tests/test_gemini_contract.py",
            "tests/test_observability.py",
            ".github/workflows/ci.yml",
        }
        forbidden = [f for f in modified_tracked if f not in allowed]
        self.assertEqual(
            forbidden,
            [],
            f"Archivos versionados de V1–V7 modificados indebidamente: {forbidden}",
        )


class TestV8BackendEdgeCasesAndHardening(unittest.TestCase):
    """8. Pruebas de endurecimiento backend V8 (F-08, F-10, F-11, F-12, F-13, F-14)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.real_swatch_bytes = _load_test_swatch_bytes()
        cls.studio_sofa_bytes = _make_studio_white_sofa_bytes()

    def test_vistas_tela_total_tiles_parity_batch_ref_filename_and_lru_cache(self) -> None:
        clear_vistas_tela_v8_cache()
        with _offline_ai_clients(v8):
            res_vt = v8.build_prompts(
                mode="vistas_tela",
                furniture_name="SOFA_MILAN",
                tipo_mueble="SOFA",
                medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
                fabric_label="",
                fabric_filename="",
                batch_ref_bytes=self.real_swatch_bytes,
                batch_ref_filename="MI_TELA_PRO.jpg",
                batch_views=[("vista_1.png", self.studio_sofa_bytes)],
                api_key="",
            )
        item0 = res_vt["items"][0]
        ais0 = item0["google_ai_studio"]
        guide0 = " | ".join(item0["attachment_guide"])

        # Paridad de baldosas: 484 en todo el prompt (22x22 para sofá 220 cm), 2 fotos limpias sin V8_LUZ30
        self.assertEqual(len(item0["attachment_guide"]), 2)
        self.assertIn("484", ais0)
        self.assertNotIn("196", ais0)
        self.assertNotIn("V8_LUZ30", guide0)
        self.assertNotIn("V8_LUZ30", ais0)
        self.assertNotIn("Image 3", ais0)
        # batch_ref_filename NO queda eclipsado por el label por defecto
        self.assertIn("MI TELA PRO", ais0)

        # Multi-vista: total_tiles == 484 en todos los lienzos y caché LRU acotada en reruns
        clear_vistas_tela_v8_cache()
        views_2 = [("vista_a.png", self.studio_sofa_bytes), ("vista_b.png", _make_room_bg_furniture_bytes())]
        with patch.object(
            svc_v8_mod,
            "compose_view_with_precomputed_tile_v8",
            wraps=compose_view_with_precomputed_tile_v8,
        ) as spy_compose:
            pack_1 = v8.build_v8_reference_pack(
                mode="vistas_tela",
                furniture_name="SOFA_MILAN",
                tipo_mueble="SOFA",
                medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
                batch_ref_filename="MI_TELA_PRO.jpg",
                batch_ref_bytes=self.real_swatch_bytes,
                batch_views=views_2,
            )
            calls_after_first = spy_compose.call_count
            self.assertEqual(calls_after_first, 2)
            self.assertFalse(any(p["role"] == "v8_calibrated_swatch" for p in pack_1))
            canv_entries = [p for p in pack_1 if p["role"] == "v8_scale_canvas"]
            self.assertEqual(len(canv_entries), 2)
            for ce in canv_entries:
                self.assertEqual(ce["total_tiles"], 484)

            pack_2 = v8.build_v8_reference_pack(
                mode="vistas_tela",
                furniture_name="SOFA_MILAN",
                tipo_mueble="SOFA",
                medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
                batch_ref_filename="MI_TELA_PRO.jpg",
                batch_ref_bytes=self.real_swatch_bytes,
                batch_views=views_2,
            )
            self.assertEqual(spy_compose.call_count, calls_after_first, "vistas_tela no reutilizó la caché LRU")
            self.assertEqual(
                [p["bytes"] for p in pack_1 if p["role"] == "v8_scale_canvas"],
                [p["bytes"] for p in pack_2 if p["role"] == "v8_scale_canvas"],
            )

    def test_corrupt_image_resilience_in_analyze_fabric_v8_local_and_analyze_all_parallel(self) -> None:
        corrupt = b"not-an-image-corrupt-payload" * 10
        fab = v8.analyze_fabric_v8_local(corrupt, sample_name="TELA_ROTA.jpg", boost=0.30)
        self.assertIsInstance(fab, dict)
        self.assertEqual(fab["v8_calibrated_boost"], 0.30)
        self.assertIn("v8_multitone_bands", fab)
        self.assertIn("v8_has_multitone_alternation", fab)
        self.assertIn("v8_mean_rgb", fab)
        self.assertIn("v8_mean_hex", fab)
        self.assertIn("v8_motif_period_px", fab)
        self.assertIn("v8_roi_bbox", fab)

        svc = AIPromptServiceV8()
        with patch.object(svc, "get_api_key", return_value=""):
            f_ana, w_ana, t_ana = svc.analyze_all_parallel(
                furniture_bytes=[corrupt],
                wood_bytes=corrupt,
                wood_name="MADERA_ROTA.jpg",
                fabric_bytes=corrupt,
                fabric_name="TELA_ROTA.jpg",
            )
        self.assertIsInstance(f_ana, dict)
        self.assertIsNotNone(t_ana)
        assert t_ana is not None
        self.assertIn("v8_calibrated_boost", t_ana)

        # Un fallo aislado en el worker de mueble no tumba a los workers de madera/tela
        with patch.object(svc, "get_api_key", return_value=""), \
             patch.object(svc, "analyze_furniture_for_enhancement", side_effect=RuntimeError("boom")):
            f_err, _w_ok, t_ok = svc.analyze_all_parallel(
                furniture_bytes=[self.studio_sofa_bytes],
                fabric_bytes=self.real_swatch_bytes,
                fabric_name="TELA_OK.jpg",
            )
        self.assertEqual(f_err, {})
        self.assertIsNotNone(t_ok)
        assert t_ok is not None
        self.assertTrue(t_ok.get("v8_has_multitone_alternation"))

    def test_concurrent_mosaic_only_png_thread_safety(self) -> None:
        clear_v8_composer_cache()
        art = build_v8_conditioning_canvas(
            furniture_bytes=self.studio_sofa_bytes,
            fabric_bytes=self.real_swatch_bytes,
            sample_name="TELA_CONC.jpg",
            furniture_name="SOFA_CONC.png",
            furniture_width_cm=220.0,
            furniture_type="SOFA",
        )
        self.assertIsNone(art._mosaic_only_png_cache)

        n_threads = 8
        barrier = threading.Barrier(n_threads)
        results: list = [None] * n_threads
        errors: list = []

        def _worker(idx: int) -> None:
            try:
                barrier.wait(timeout=5.0)
                results[idx] = art.mosaic_only_png
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        self.assertEqual(errors, [])
        for r in results:
            self.assertIsInstance(r, bytes)
            self.assertTrue(r.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(r, results[0])
        with Image.open(io.BytesIO(results[0])) as im_m:
            self.assertEqual(im_m.size, (768, 768))
            self.assertEqual(im_m.mode, "RGB")
            self.assertLessEqual(max(e[1] for e in im_m.getextrema()), 243)

    def test_fabric_composer_rgba_opaque_corners_i16_scaling_and_large_photo_reduce(self) -> None:
        # 1) RGBA con esquinas opacas (cae en white_frame) y centro transparente -> compone sobre BLANCO (255,255,255), NO negro
        rgba_opaque = Image.new("RGBA", (400, 400), (160, 140, 120, 255))
        ImageDraw.Draw(rgba_opaque).rectangle((120, 120, 280, 280), fill=(0, 0, 0, 0))
        rgba_bytes = _encode_png(rgba_opaque)

        clear_v8_composer_cache()
        art_rgba = build_v8_conditioning_canvas(
            furniture_bytes=rgba_bytes,
            fabric_bytes=self.real_swatch_bytes,
            sample_name="TELA.jpg",
            furniture_name="RGBA_OPAQUE.png",
            furniture_width_cm=160.0,
        )
        self.assertEqual(art_rgba.isolation_mode, "white_frame")
        with Image.open(io.BytesIO(art_rgba.canvas_png)) as cv_rgba:
            self.assertEqual(cv_rgba.getpixel((640, 640)), (255, 255, 255))

        roi = extract_clean_swatch_roi_v8(self.real_swatch_bytes)
        cal = calibrate_fabric_lightness_v8(roi.crop, boost=0.30, max_rgb=243)
        tile = make_toroidal_seamless_tile_v8(cal, tile_px=86, max_rgb=243)
        _, vt_png, _ = compose_view_with_precomputed_tile_v8(rgba_bytes, tile, tile_px=86, grid_n=15, view_name="rgba_v.png")
        with Image.open(io.BytesIO(vt_png)) as cv_vt_rgba:
            self.assertEqual(cv_vt_rgba.getpixel((640, 640)), (255, 255, 255))

        # 2) Imagen de 16 bits (I;16 valor 30000) escala correctamente ~117 y NO blanquea a (255,255,255)
        i16_im = Image.new("I;16", (400, 400), 30000)
        buf_i16 = io.BytesIO()
        i16_im.save(buf_i16, format="PNG")
        i16_bytes = buf_i16.getvalue()

        rgb_i16 = fc_v8._open_rgb_safe(i16_bytes)
        px_i16 = rgb_i16.getpixel((200, 200))
        for ch in px_i16:
            self.assertTrue(95 <= ch <= 140, f"I;16 mal escalado en _open_rgb_safe: {px_i16}")

        art_i16 = build_v8_conditioning_canvas(
            furniture_bytes=i16_bytes,
            fabric_bytes=self.real_swatch_bytes,
            sample_name="TELA.jpg",
            furniture_name="MUEBLE_16BIT.png",
            furniture_width_cm=160.0,
        )
        with Image.open(io.BytesIO(art_i16.canvas_png)) as cv_i16:
            c_px = cv_i16.getpixel((640, 640))
            for ch in c_px:
                self.assertTrue(95 <= ch <= 140, f"I;16 blanqueado en lienzo V8: {c_px}")

        # 3) Foto grande >2560 px pasa por .reduce() sin OOM y lazy canvas_image mantiene RAM acotada
        big_im = Image.new("RGB", (3000, 2600), (255, 255, 255))
        ImageDraw.Draw(big_im).rectangle((600, 500, 2400, 2100), fill=(140, 125, 112))
        big_bytes = _encode_png(big_im)
        art_big = build_v8_conditioning_canvas(
            furniture_bytes=big_bytes,
            fabric_bytes=self.real_swatch_bytes,
            sample_name="TELA.jpg",
            furniture_name="SOFA_GRANDE.png",
            furniture_width_cm=220.0,
            furniture_type="SOFA",
        )
        self.assertEqual(art_big.canvas_size, (1280, 1280))
        self.assertIsNone(art_big._canvas_image_ref)
        lazy_im = art_big.canvas_image
        self.assertIsNotNone(lazy_im)
        assert lazy_im is not None
        self.assertEqual(lazy_im.size, (1280, 1280))
        self.assertGreater(art_big.approx_bytes(), len(art_big.canvas_png))

    def test_zip_lossless_png_preservation_deduplication_and_slash_sanitization(self) -> None:
        # Lienzo PNG > 1.5 MB (ruido de alta entropía) debe preservar PNG sin pérdida al pasar por _prepare_v8_zip_ref_entry
        noisy_im = Image.frombytes("RGB", (1280, 1280), os.urandom(1280 * 1280 * 3))
        noisy_png = _encode_png(noisy_im)
        self.assertGreater(len(noisy_png), 1_500_000)

        fn_c, raw_c = _prepare_v8_zip_ref_entry({
            "filename": "SOFA_V8_LIENZO_ESCALA.png",
            "bytes": noisy_png,
            "role": "v8_scale_canvas",
        })
        self.assertEqual(fn_c, "SOFA_V8_LIENZO_ESCALA.png")
        self.assertTrue(raw_c.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(raw_c, noisy_png)

        # Foto PNG 2054x2054 de mueble también conserva bytes PNG reales (jamás JPEG bajo extensión .png)
        big_furn = Image.new("RGB", (2054, 2054), (255, 255, 255))
        ImageDraw.Draw(big_furn).rectangle((400, 400, 1650, 1650), fill=(140, 130, 120))
        big_furn_png = _encode_png(big_furn)
        fn_f, raw_f = _prepare_v8_zip_ref_entry({
            "filename": "RENDER_SOFA.png",
            "bytes": big_furn_png,
            "role": "primary_furniture",
        })
        self.assertTrue(fn_f.endswith(".png"))
        self.assertTrue(raw_f.startswith(b"\x89PNG\r\n\x1a\n"))

        # JPEG etiquetado erróneamente como .png alinea su extensión a .jpg
        jpg_buf = io.BytesIO()
        Image.new("RGB", (400, 400), (150, 140, 130)).save(jpg_buf, format="JPEG", quality=90)
        fn_j, raw_j = _prepare_v8_zip_ref_entry({
            "filename": "FOTO_REAL.png",
            "bytes": jpg_buf.getvalue(),
            "role": "primary_furniture",
        })
        self.assertTrue(fn_j.endswith(".jpg"))
        self.assertTrue(raw_j.startswith(b"\xff\xd8\xff"))

        # Deduplicación + sanitización de diagonales y caracteres prohibidos sin UserWarning de zipfile
        dummy_png = _encode_png(Image.new("RGB", (64, 64), (255, 255, 255)))
        res_dup = {
            "mueble_name": "SOFA / MILAN: *PRO*",
            "master_ais": "MASTER AIS",
            "master_dal": "MASTER DAL",
            "items": [
                {
                    "output_filename": "sub/vista.png",
                    "attachment_guide": ["Image 1: vista"],
                    "google_ai_studio": "AIS 1",
                    "chatgpt_dalle3": "DAL 1",
                    "midjourney_v6": "MJ 1",
                    "generated_photo": {"png": dummy_png},
                },
                {
                    "output_filename": "sub/vista.png",
                    "attachment_guide": ["Image 1: vista"],
                    "google_ai_studio": "AIS 2",
                    "chatgpt_dalle3": "DAL 2",
                    "midjourney_v6": "MJ 2",
                    "generated_photo": {"png": dummy_png},
                },
            ],
            "ref_images": [
                ("SOFA/A.png", dummy_png),
                ("SOFA/A.png", dummy_png),
                (fn_c, raw_c),
            ],
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            z_bytes = _build_zip_v8(res_dup, include_images=True)
        dup_warns = [w for w in caught if "Duplicate name" in str(w.message)]
        self.assertEqual(dup_warns, [], f"zipfile emitió advertencia de duplicados: {dup_warns}")

        with zipfile.ZipFile(io.BytesIO(z_bytes), "r") as zf:
            names = zf.namelist()
            self.assertEqual(len(names), len(set(names)), f"Entradas duplicadas en ZIP: {names}")
            for nm in names:
                self.assertEqual(nm.count("/"), 1, f"Ruta anidada inesperada en ZIP: {nm}")
                for bad_ch in (":", "*", "?", '"', "<", ">", "|"):
                    self.assertNotIn(bad_ch, nm)
            self.assertTrue(zf.read("insumos/SOFA_V8_LIENZO_ESCALA.png").startswith(b"\x89PNG\r\n\x1a\n"))

    def test_drive_live_search_per_folder_resilience(self) -> None:
        from services.sheets_service import sheets_service

        def _fake_live(query_text: str, limit: int = 8, folder_id: str = ""):
            if folder_id == FOLDER_MUEBLES_RENDER_DRIVE_ID:
                raise RuntimeError("RENDER transient error")
            if folder_id == FOLDER_MUEBLES_SUBIR_DRIVE_ID:
                return [{"id": "subir_hit_1", "name": "SOFA_MILAN.jpg", "thumbnailLink": ""}]
            return []

        try:
            _search_drive_live_cached_v8.clear()
        except Exception:
            pass
        with patch.object(sheets_service, "ensure_connected", return_value=True), \
             patch.object(sheets_service, "search_drive_images_live", side_effect=_fake_live):
            hits = _search_drive_live_cached_v8("MILAN")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["id"], "subir_hit_1")
        self.assertEqual(hits[0]["source"], "SUBIR")

    def test_generate_catalog_photo_best_purity_retry_per_model_429_and_auth_rejection(self) -> None:
        from services import gemini_runtime

        # Helper local para crear stub google.genai.types si no está instalado
        had_google = "google" in sys.modules
        had_genai = "google.genai" in sys.modules
        if not had_genai:
            g_pkg = sys.modules.get("google") or types.ModuleType("google")
            genai_pkg = types.ModuleType("google.genai")
            types_mod = types.ModuleType("google.genai.types")

            class _GenCfg:
                def __init__(self, **kw):
                    self.kw = kw

            types_mod.GenerateContentConfig = _GenCfg
            genai_pkg.types = types_mod
            g_pkg.genai = genai_pkg
            sys.modules["google"] = g_pkg
            sys.modules["google.genai"] = genai_pkg
            sys.modules["google.genai.types"] = types_mod

        class _Resp:
            def __init__(self, raw_b: bytes):
                b64 = base64.b64encode(raw_b).decode("ascii")
                part = types.SimpleNamespace(inline_data=types.SimpleNamespace(data=b64))
                self.candidates = [types.SimpleNamespace(content=types.SimpleNamespace(parts=[part]))]

        def _img_with_border_purity(white_ratio: float) -> bytes:
            im = Image.new("RGB", (256, 256), (180, 170, 160))
            if white_ratio >= 0.99:
                im = Image.new("RGB", (256, 256), (255, 255, 255))
                ImageDraw.Draw(im).rectangle((70, 70, 186, 186), fill=(160, 150, 140))
            return _encode_png(im)

        dummy_ok = _img_with_border_purity(1.0)
        dummy_bad = _img_with_border_purity(0.0)

        try:
            # Subcaso A: intento 0 tiene pureza 0.90 (<0.95) e intento 1 tiene 0.50 (peor) -> conserva intento 0!
            svc_a = AIPromptServiceV8()
            purities_seq = iter([0.90, 0.50])
            call_models_a = []

            class _ModelsA:
                def generate_content(self, model, contents, config=None):
                    call_models_a.append(model)
                    return _Resp(dummy_bad)

            svc_a.get_client = lambda k=None: types.SimpleNamespace(models=_ModelsA())  # type: ignore[method-assign]
            with patch.object(svc_a, "_compute_white_border_purity", side_effect=lambda *a, **kw: next(purities_seq)):
                out_a, err_a = svc_a.generate_catalog_photo(
                    prompt_text="Test best retry",
                    primary_bytes=self.studio_sofa_bytes,
                    fabric_bytes=self.real_swatch_bytes,
                    pure_white_border=True,
                    api_key="AIzaFakeBestRetryKey12345678901234567",
                )
            self.assertIsNone(err_a)
            self.assertIsNotNone(out_a)
            assert out_a is not None
            self.assertEqual(len(call_models_a), 2)
            self.assertAlmostEqual(out_a["border_white_purity"], 0.90, places=3)

            # Subcaso B: 429 en modelo 0 intenta modelo 1 y NO activa cooldown global de 300s
            svc_b = AIPromptServiceV8()
            seen_b = []

            class _ModelsB:
                def generate_content(self, model, contents, config=None):
                    seen_b.append(model)
                    if len(seen_b) == 1:
                        raise RuntimeError("429 RESOURCE_EXHAUSTED for model 0")
                    return _Resp(dummy_ok)

            svc_b.get_client = lambda k=None: types.SimpleNamespace(models=_ModelsB())  # type: ignore[method-assign]
            out_b, err_b = svc_b.generate_catalog_photo(
                prompt_text="Test 429 fallback",
                primary_bytes=self.studio_sofa_bytes,
                pure_white_border=True,
                api_key="AIzaFakeFallback429Key12345678901234",
            )
            self.assertIsNone(err_b)
            self.assertIsNotNone(out_b)
            assert out_b is not None
            self.assertEqual(len(seen_b), 2)
            self.assertEqual(out_b["model"], DEFAULT_V8_IMAGE_MODELS[1])
            self.assertEqual(svc_b._img_quota_exhausted_until, 0.0)

            # Subcaso B2: todos los modelos fallan con 429 -> activa cooldown 300s
            svc_b2 = AIPromptServiceV8()
            seen_b2 = []

            class _ModelsB2:
                def generate_content(self, model, contents, config=None):
                    seen_b2.append(model)
                    raise RuntimeError("429 RESOURCE_EXHAUSTED")

            svc_b2.get_client = lambda k=None: types.SimpleNamespace(models=_ModelsB2())  # type: ignore[method-assign]
            out_b2, err_b2 = svc_b2.generate_catalog_photo(
                prompt_text="Test all 429",
                primary_bytes=self.studio_sofa_bytes,
                pure_white_border=True,
                api_key="AIzaFakeAll429Key1234567890123456789",
            )
            self.assertIsNone(out_b2)
            self.assertIsNotNone(err_b2)
            self.assertEqual(len(seen_b2), len(DEFAULT_V8_IMAGE_MODELS))
            self.assertGreater(svc_b2._img_quota_exhausted_until, time.time())

            # Subcaso C: 403/API_KEY_INVALID llama a gemini_runtime.mark_key_rejected(key)
            svc_c = AIPromptServiceV8()

            class _ModelsC:
                def generate_content(self, model, contents, config=None):
                    raise RuntimeError("403 API_KEY_INVALID leaked")

            svc_c.get_client = lambda k=None: types.SimpleNamespace(models=_ModelsC())  # type: ignore[method-assign]
            bad_k = "AIzaFakeRejectedKey12345678901234567"
            with patch.object(gemini_runtime, "mark_key_rejected") as mock_reject:
                out_c, _err_c = svc_c.generate_catalog_photo(
                    prompt_text="Test auth reject",
                    primary_bytes=self.studio_sofa_bytes,
                    pure_white_border=True,
                    api_key=bad_k,
                )
            self.assertIsNone(out_c)
            mock_reject.assert_called_once_with(bad_k)

            # Subcaso D: generate_image_34_derecha_2054 reenvía furniture_width_cm y furniture_type
            svc_d = AIPromptServiceV8()
            with patch.object(svc_d, "generate_catalog_photo", return_value=({"width": 2054}, None)) as mock_gen:
                res_d = svc_d.generate_image_34_derecha_2054(
                    prompt_text="3/4 test",
                    furniture_bytes=self.studio_sofa_bytes,
                    fabric_bytes=self.real_swatch_bytes,
                    furniture_width_cm=220.0,
                    furniture_type="SOFA",
                )
            self.assertEqual(res_d, {"width": 2054})
            self.assertEqual(mock_gen.call_args.kwargs["furniture_width_cm"], 220.0)
            self.assertEqual(mock_gen.call_args.kwargs["furniture_type"], "SOFA")
        finally:
            if not had_genai:
                sys.modules.pop("google.genai.types", None)
                sys.modules.pop("google.genai", None)
                if not had_google:
                    sys.modules.pop("google", None)


class _StrictWidgetAlreadyInstantiatedError(Exception):
    """Emula streamlit.errors.StreamlitWidgetAlreadyInstantiatedError en entornos sin Streamlit."""


class _StrictRerunSignal(Exception):
    """Señal interna de st.rerun() dentro del simulador estricto de ciclo de vida."""


class _StrictUploadedFile:
    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


class _StrictSessionState(dict):
    def __init__(self, runtime: "_StrictStreamlitRuntime") -> None:
        super().__init__()
        object.__setattr__(self, "_rt", runtime)

    def __setitem__(self, key: str, value) -> None:
        rt: _StrictStreamlitRuntime = object.__getattribute__(self, "_rt")
        if key in rt.read_only_keys:
            raise _StrictWidgetAlreadyInstantiatedError(
                f"st.session_state[{key!r}] is a read-only widget key and cannot be assigned."
            )
        if key in rt.instantiated_keys:
            raise _StrictWidgetAlreadyInstantiatedError(
                f"st.session_state[{key!r}] cannot be modified after the widget with that key is instantiated."
            )
        rt.new_state_values.add(key)
        super().__setitem__(key, value)

    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:
        self[name] = value


class _StrictNoopCtx:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _StrictEmptySlot:
    def __init__(self, rt: "_StrictStreamlitRuntime") -> None:
        self._rt = rt

    def error(self, msg: str) -> None:
        self._rt.errors.append(str(msg))

    def info(self, msg: str) -> None:
        self._rt.infos.append(str(msg))

    def warning(self, msg: str) -> None:
        self._rt.warnings.append(str(msg))

    def empty(self) -> None:
        pass


class _StrictStreamlitRuntime:
    """
    Simulador fiel del ciclo de vida de Streamlit SessionState (Layer B, cero dependencias):
      - Lanza _StrictWidgetAlreadyInstantiatedError en cualquier escritura post-instanciación o sobre widgets read-only.
      - Ejecuta callbacks on_change / on_click ANTES del rerun con instantiated_keys vacío.
      - Registra widget_value_changed (new_state_values) al instanciar cada widget (incl. sku_input_v8).
      - Soporta st.rerun() en bucle acotado.
    """

    def __init__(self) -> None:
        self.instantiated_keys: set = set()
        self.read_only_keys: set = set()
        self.new_state_values: set = set()
        self.widget_value_changed_log: dict = {}
        self.callbacks: dict = {}
        self.widget_options: dict = {}
        self.uploaded_files: dict = {}
        self.clicked_button_key: str | None = None
        self.errors: list = []
        self.warnings: list = []
        self.infos: list = []
        self.toasts: list = []
        self.downloads: dict = {}
        self.secrets: dict = {}
        self.session_state = _StrictSessionState(self)

    def _begin_run(self) -> None:
        self.instantiated_keys.clear()
        self.read_only_keys.clear()
        self.new_state_values.clear()
        self.widget_value_changed_log.clear()
        self.errors.clear()
        self.warnings.clear()
        self.infos.clear()
        self.toasts.clear()
        self.downloads.clear()

    def run_script(self, fn, max_reruns: int = 6) -> None:
        for _ in range(max_reruns):
            self._begin_run()
            try:
                fn()
                self.clicked_button_key = None
                return
            except _StrictRerunSignal:
                self.clicked_button_key = None
                continue
        raise AssertionError("Demasiados st.rerun() encadenados en _StrictStreamlitRuntime")

    def simulate_change(self, fn, key: str, value) -> None:
        self.instantiated_keys.clear()
        self.read_only_keys.clear()
        self.session_state[key] = value
        cb = self.callbacks.get(key)
        if cb:
            cb_fn, cb_args, cb_kwargs = cb
            cb_fn(*cb_args, **cb_kwargs)
        self.run_script(fn)

    def simulate_click(self, fn, key: str) -> None:
        self.instantiated_keys.clear()
        self.read_only_keys.clear()
        cb = self.callbacks.get(key)
        if cb:
            cb_fn, cb_args, cb_kwargs = cb
            cb_fn(*cb_args, **cb_kwargs)
            self.clicked_button_key = None
        else:
            self.clicked_button_key = key
        self.run_script(fn)

    def set_page_config(self, *a, **kw) -> None:
        pass

    def cache_data(self, *args, **kwargs):
        def _dec(fn):
            fn.clear = lambda: None
            return fn

        return _dec(args[0]) if args and callable(args[0]) else _dec

    def container(self, *a, **kw):
        return _StrictNoopCtx()

    def popover(self, *a, **kw):
        return _StrictNoopCtx()

    def columns(self, spec, *a, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_StrictNoopCtx() for _ in range(n)]

    def tabs(self, labels):
        return [_StrictNoopCtx() for _ in labels]

    def empty(self):
        return _StrictEmptySlot(self)

    def markdown(self, *a, **kw) -> None:
        pass

    def caption(self, *a, **kw) -> None:
        pass

    def error(self, msg, *a, **kw) -> None:
        self.errors.append(str(msg))

    def warning(self, msg, *a, **kw) -> None:
        self.warnings.append(str(msg))

    def info(self, msg, *a, **kw) -> None:
        self.infos.append(str(msg))

    def toast(self, msg, *a, **kw) -> None:
        self.toasts.append(str(msg))

    def rerun(self, *a, **kw) -> None:
        raise _StrictRerunSignal()

    def selectbox(self, label, options, index=0, key=None, on_change=None, args=None, kwargs=None, **kw):
        opts = list(options)
        if key:
            self.widget_options[key] = opts
            self.widget_value_changed_log[key] = key in self.new_state_values
            if on_change is not None:
                self.callbacks[key] = (on_change, tuple(args or ()), dict(kwargs or {}))
            else:
                self.callbacks.pop(key, None)
            val = self.session_state.get(key)
            if val not in opts:
                val = opts[index] if opts else None
                dict.__setitem__(self.session_state, key, val)
            self.instantiated_keys.add(key)
            return val
        return opts[index] if opts else None

    def text_input(self, label, value="", key=None, on_change=None, args=None, kwargs=None, **kw):
        if key:
            self.widget_value_changed_log[key] = key in self.new_state_values
            if on_change is not None:
                self.callbacks[key] = (on_change, tuple(args or ()), dict(kwargs or {}))
            if key not in self.session_state:
                dict.__setitem__(self.session_state, key, value)
            self.instantiated_keys.add(key)
            return self.session_state[key]
        return value

    def text_area(self, label, value="", key=None, **kw):
        if key:
            self.widget_value_changed_log[key] = key in self.new_state_values
            dict.__setitem__(self.session_state, key, value)
            self.instantiated_keys.add(key)
        return value

    def button(self, label, key=None, on_click=None, args=None, kwargs=None, **kw) -> bool:
        if key:
            self.read_only_keys.add(key)
            self.instantiated_keys.add(key)
            if on_click is not None:
                self.callbacks[key] = (on_click, tuple(args or ()), dict(kwargs or {}))
            else:
                self.callbacks.pop(key, None)
            if self.clicked_button_key == key:
                self.clicked_button_key = None
                return True
        return False

    def download_button(self, label, data=b"", file_name="", mime="", key=None, **kw) -> bool:
        if key:
            self.read_only_keys.add(key)
            self.instantiated_keys.add(key)
            self.downloads[key] = {"label": label, "data": data, "file_name": file_name, "mime": mime}
        return False

    def file_uploader(self, label, accept_multiple_files=False, key=None, **kw):
        if key:
            self.read_only_keys.add(key)
            self.instantiated_keys.add(key)
            val = self.uploaded_files.get(key)
            if accept_multiple_files:
                return list(val) if val else []
            return val
        return [] if accept_multiple_files else None


class TestV8StrictLifecycleSimulatorAndStaticAST(unittest.TestCase):
    """9. Capa B: Simulador estricto de ciclo de vida Streamlit + Guardia AST (corre siempre sin streamlit)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.real_swatch_bytes = _load_test_swatch_bytes()
        cls.studio_sofa_bytes = _make_studio_white_sofa_bytes()
        wood_files = sorted((REPO_ROOT / "muestras_madera").glob("*.jpg"))
        assert wood_files, "No se encontraron muestras locales en muestras_madera/"
        cls.local_wood_path = wood_files[0]

    def _build_fake_catalog(self):
        return (
            [
                {"id": "m_1", "name": "SOFA MILAN", "filename": "SOFA MILAN.png", "source": "RENDER"},
                {"id": "m_2", "name": "SILLON ROMA", "filename": "SILLON ROMA.png", "source": "SUBIR"},
            ],
            [
                {"id": "t_1", "name": "TELA NATURAL", "filename": "TELA_NATURAL.jpg", "source": "Telas"},
            ],
            [
                {
                    "id": "",
                    "name": self.local_wood_path.stem,
                    "filename": self.local_wood_path.name,
                    "local_path": str(self.local_wood_path),
                    "source": "Local",
                },
            ],
        )

    def _run_with_strict_runtime(self, test_body) -> None:
        prev_gem = os.environ.get("GEMINI_API_KEY")
        import modules.sku_banner as sku_banner_mod
        import modules.ui_helpers as ui_helpers_mod
        from services.sheets_service import sheets_service
        import main as main_mod

        rt = _StrictStreamlitRuntime()
        captured_html: list = []
        fake_cat = self._build_fake_catalog()

        def _fake_load_drive(fid: str):
            if fid == "t_1":
                return self.real_swatch_bytes
            return self.studio_sofa_bytes

        with patch.object(ps_v8_mod, "st", rt), \
             patch.object(sku_banner_mod, "st", rt), \
             patch.object(ui_helpers_mod, "st", rt), \
             patch.object(main_mod, "st", rt), \
             patch.object(ps_v8_mod.components, "html", side_effect=lambda doc, **kw: captured_html.append(doc)), \
             patch.object(ps_v8_mod, "cargar_todo_catalogo_v8", return_value=fake_cat), \
             patch.object(ps_v8_mod, "load_drive_file_cached", side_effect=_fake_load_drive), \
             patch.object(sheets_service, "ensure_connected", return_value=False), \
             patch.object(sheets_service, "get_drive_thumbnail_bytes", return_value=self.studio_sofa_bytes), \
             patch.object(svc_v8_mod.ai_prompt_service_v8, "get_api_key", return_value=""):
            try:
                test_body(rt, captured_html, main_mod, sheets_service)
            finally:
                if prev_gem is None:
                    os.environ.pop("GEMINI_API_KEY", None)
                else:
                    os.environ["GEMINI_API_KEY"] = prev_gem

    def test_strict_runtime_enforces_post_instantiation_and_readonly_guards(self) -> None:
        rt = _StrictStreamlitRuntime()
        rt._begin_run()
        rt.selectbox("Demo", ["A", "B"], key="demo_sb")
        with self.assertRaises(_StrictWidgetAlreadyInstantiatedError):
            rt.session_state["demo_sb"] = "A"
        rt.button("Go", key="demo_btn")
        with self.assertRaises(_StrictWidgetAlreadyInstantiatedError):
            rt.session_state["demo_btn"] = True

    def test_strict_runtime_pop_pick_pop_cat_refresh_and_filter_guard(self) -> None:
        def _body(rt: _StrictStreamlitRuntime, captured_html: list, _main_mod, sheets_service):
            # Arranque inicial limpio
            rt.run_script(render_prompt_studio_v8)
            pick_opts = rt.widget_options["v8_pop_pick_0"]
            sofa_opt = next(o for o in pick_opts if "SOFA MILAN" in o)
            tela_opt = next(o for o in pick_opts if "TELA NATURAL" in o)
            wood_opt = next(o for o in pick_opts if self.local_wood_path.stem in o)

            # 1) Elegir mueble, tela (DISTRACTION_NATURAL.jpg) y madera desde v8_pop_pick_0 sin error
            rt.simulate_change(render_prompt_studio_v8, "v8_pop_pick_0", sofa_opt)
            self.assertEqual(rt.session_state["v8_pop_pick_0"], ps_v8_mod._V8_POP_PICK_PLACEHOLDER)
            self.assertIn("SOFA MILAN", rt.session_state["v8_sb_mueble_0"])
            self.assertFalse(rt.session_state["v8_apply_pick_mueble_0"])

            rt.simulate_change(render_prompt_studio_v8, "v8_pop_pick_0", tela_opt)
            self.assertEqual(rt.session_state["v8_pop_pick_0"], ps_v8_mod._V8_POP_PICK_PLACEHOLDER)
            self.assertEqual(rt.session_state["v8_sb_fabric_0"], "TELA NATURAL")

            captured_html.clear()
            rt.simulate_change(render_prompt_studio_v8, "v8_pop_pick_0", wood_opt)
            self.assertEqual(rt.session_state["v8_sb_wood_0"], self.local_wood_path.stem)
            strip_docs = [d for d in captured_html if "v8-thumb-card" in d]
            self.assertTrue(strip_docs, "No se renderizó la tira 76x76 V8")
            # 3 tarjetas limpias en tira 76x76 con madera + tela: Mueble + Lienzo Escala V8 + Madera
            self.assertEqual(strip_docs[-1].count("🖼️ Copiar foto"), 3)
            self.assertNotIn("_V8_LUZ30.png", strip_docs[-1])

            # 2) Seleccionar "🔄 Actualizar Drive" en v8_pop_cat_0 sin StreamlitWidgetAlreadyInstantiatedError
            with patch.object(sheets_service, "_invalidate_drive_catalog_caches") as mock_inv_d, \
                 patch.object(ps_v8_mod, "invalidate_v8_catalog_caches") as mock_inv_v8:
                rt.simulate_change(render_prompt_studio_v8, "v8_pop_cat_0", "🔄 Actualizar Drive")
            self.assertEqual(rt.session_state["v8_pop_cat_0"], "📁 Todas")
            self.assertEqual(rt.session_state["v8_render_tick"], 1)
            mock_inv_d.assert_called_once()
            mock_inv_v8.assert_called_once()

            # 3) Filtro "🧵 Telas" con búsqueda sin resultados NO dispara búsqueda live de muebles
            with patch.object(ps_v8_mod, "_search_drive_live_cached_v8") as mock_live:
                rt.simulate_change(render_prompt_studio_v8, "v8_pop_cat_0", "🧵 Telas")
                rt.simulate_change(render_prompt_studio_v8, "v8_pop_q_0", "XYZINEXISTENTE")
            mock_live.assert_not_called()

            # 4) Guardia de v8_apply_pick_* pegajoso: un pick malformado se limpia incondicionalmente
            rt.instantiated_keys.clear()
            rt.session_state["v8_picked_mueble_0"] = {}
            rt.session_state["v8_apply_pick_mueble_0"] = True
            rt.run_script(render_prompt_studio_v8)
            self.assertFalse(rt.session_state["v8_apply_pick_mueble_0"])

        self._run_with_strict_runtime(_body)

    def test_strict_runtime_clear_button_preserves_modes_and_resets_sku_dom(self) -> None:
        def _body(rt: _StrictStreamlitRuntime, _captured_html: list, _main_mod, sheets_service):
            with patch.object(
                sheets_service,
                "get_furniture_by_sku",
                return_value={"tipo_mueble": "SOFA", "medidas": "220x95x82"},
            ):
                rt.run_script(render_prompt_studio_v8)
                rt.simulate_change(render_prompt_studio_v8, "v8_keep_mode", "Tela / Madera")
                rt.simulate_change(render_prompt_studio_v8, "v8_keep_matmode", "Tela + madera")
                rt.simulate_change(render_prompt_studio_v8, "v8_keep_folder", "📤 SUBIR")
                rt.simulate_change(render_prompt_studio_v8, "sku_input_v8", "SKU-123")
                self.assertEqual(rt.session_state["field_tipo_v8"], "SOFA")
                self.assertEqual(rt.session_state["field_medidas_v8"], "220x95x82")

                rt.simulate_change(render_prompt_studio_v8, "v8_notas_0", "Costura francesa")
                sofa_opt = next(o for o in rt.widget_options["v8_pop_pick_0"] if "SOFA MILAN" in o)
                tela_opt = next(o for o in rt.widget_options["v8_pop_pick_0"] if "TELA NATURAL" in o)
                wood_opt = next(o for o in rt.widget_options["v8_pop_pick_0"] if self.local_wood_path.stem in o)
                rt.simulate_change(render_prompt_studio_v8, "v8_pop_pick_0", sofa_opt)
                rt.simulate_change(render_prompt_studio_v8, "v8_pop_pick_0", tela_opt)
                rt.simulate_change(render_prompt_studio_v8, "v8_pop_pick_0", wood_opt)
                rt.simulate_click(render_prompt_studio_v8, "v8_btn_go_0")
                self.assertIn("v8_result", rt.session_state)
                self.assertIn("v8_gen_id_0", rt.session_state)

                # Pulsar 🗑️ Borrar (via on_click=_clear_v8_form_state)
                rt.simulate_click(render_prompt_studio_v8, "v8_btn_clear")

                # Regla 2: modo y sub-opciones JAMÁS se reinician
                self.assertEqual(rt.session_state["v8_keep_mode"], "Tela / Madera")
                self.assertEqual(rt.session_state["v8_keep_matmode"], "Tela + madera")
                self.assertEqual(rt.session_state["v8_keep_folder"], "📤 SUBIR")
                self.assertEqual(rt.session_state["clear_key_v8"], 1)

                # SKU DOM reset garantizado (widget_value_changed=True) y resultados/gen_id limpiados
                self.assertEqual(rt.session_state["sku_input_v8"], "")
                self.assertEqual(rt.session_state["field_tipo_v8"], "")
                self.assertEqual(rt.session_state["field_medidas_v8"], "")
                self.assertTrue(rt.widget_value_changed_log.get("sku_input_v8"), "sku_input_v8 no emitió widget_value_changed=True")
                self.assertNotIn("v8_result", rt.session_state)
                self.assertNotIn("v8_gen_id_0", rt.session_state)
                self.assertEqual(rt.session_state.get("v8_notas_1", ""), "")

        self._run_with_strict_runtime(_body)

    def test_strict_runtime_34_derecha_2054_popover_zip_and_main_subir_roundtrip(self) -> None:
        def _body(rt: _StrictStreamlitRuntime, _captured_html: list, main_mod, _sheets_service):
            import modules.alta_fotos_hub as alta_mod

            alta_called = []

            with patch.object(alta_mod, "render_alta_fotos_hub", side_effect=lambda: alta_called.append(True)):
                rt.run_script(main_mod.main)
                sofa_opt = next(o for o in rt.widget_options["v8_pop_pick_0"] if "SOFA MILAN" in o)
                tela_opt = next(o for o in rt.widget_options["v8_pop_pick_0"] if "TELA NATURAL" in o)
                rt.simulate_change(main_mod.main, "v8_pop_pick_0", sofa_opt)
                rt.simulate_change(main_mod.main, "v8_pop_pick_0", tela_opt)

                # ↘️ 3/4 Derecha
                rt.simulate_click(main_mod.main, "v8_btn_34_0")
                res = rt.session_state["v8_result"]
                self.assertIn("FACING TOWARD THE RIGHT", res["items"][0]["google_ai_studio"])
                self.assertIn("2054 x 2054", res["items"][0]["google_ai_studio"])
                self.assertIn("EL CASCO COMPLETO", res["items"][0]["google_ai_studio"])

                # ZIP contiene PNGs reales sin pérdida para Lienzo V8 y Tela +30% V8
                zip_dl = rt.downloads["v8_dl_0_1"]["data"]
                with zipfile.ZipFile(io.BytesIO(zip_dl), "r") as zf:
                    for nm in zf.namelist():
                        if nm.startswith("insumos/") and nm.endswith(".png"):
                            self.assertTrue(zf.read(nm).startswith(b"\x89PNG\r\n\x1a\n"), f"{nm} no es PNG válido")

                # 📐 2054px con archivo corrupto -> st.error amigable, cero excepción
                rt.uploaded_files["v8_ext2054_0_1"] = _StrictUploadedFile("roto.png", b"bad-image-bytes")
                rt.run_script(main_mod.main)
                self.assertTrue(any("2054" in e for e in rt.errors), f"Esperaba st.error en 2054px corrupto: {rt.errors}")

                # 📐 2054px con imagen válida -> 2054x2054 #FFFFFF y memoizado en rerun
                rt.uploaded_files["v8_ext2054_0_1"] = _StrictUploadedFile("ok.png", self.studio_sofa_bytes)
                with patch.object(
                    svc_v8_mod.ai_prompt_service_v8,
                    "format_image_2054_white",
                    wraps=svc_v8_mod.ai_prompt_service_v8.format_image_2054_white,
                ) as spy_2054:
                    rt.run_script(main_mod.main)
                    self.assertEqual(spy_2054.call_count, 1)
                    self.assertIn("v8_ext_png_0_1", rt.downloads)
                    self.assertIn("v8_ext_jpg_0_1", rt.downloads)
                    with Image.open(io.BytesIO(rt.downloads["v8_ext_png_0_1"]["data"])) as im2054:
                        self.assertEqual(im2054.size, (2054, 2054))
                        self.assertEqual(im2054.getpixel((0, 0)), (255, 255, 255))
                    # Segundo rerun reutiliza caché de sesión sin recalcular 2054x2054
                    rt.run_script(main_mod.main)
                    self.assertEqual(spy_2054.call_count, 1)

                # 🚀 Subir -> Alta de Fotos -> ← Prompts incrementa v8_render_tick sin error
                tick_before = int(rt.session_state.get("v8_render_tick", 0))
                rt.simulate_click(main_mod.main, "v8_goto_alta_0_1")
                self.assertEqual(rt.session_state["unified_active_app"], "🚀 Alta de Fotos")
                self.assertTrue(alta_called)
                self.assertEqual(rt.session_state["v7_last_photo_stem"], "SOFA MILAN")

                rt.simulate_click(main_mod.main, "btn_back_prompts")
                self.assertEqual(rt.session_state["unified_active_app"], "🤖 Prompts + IA")
                self.assertEqual(rt.session_state["v8_render_tick"], tick_before + 1)

        self._run_with_strict_runtime(_body)

    def test_static_ast_zero_post_instantiation_widget_writes_and_button_count(self) -> None:
        """T-STATIC-10: Bloquea estáticamente cualquier mutación post-instanciación o sobre widgets read-only."""
        widget_funcs = {
            "selectbox", "multiselect", "text_input", "text_area", "number_input",
            "slider", "checkbox", "toggle", "radio", "date_input", "time_input",
            "color_picker", "button", "download_button", "file_uploader",
            "camera_input", "audio_input", "data_editor", "pills", "segmented_control",
        }
        readonly_widgets = {"button", "download_button", "file_uploader", "camera_input", "audio_input"}
        violations = []

        for rel in ("modules/prompt_studio_v8.py", "main.py"):
            tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                widgets = []
                writes = []
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                        if isinstance(sub.func.value, ast.Name) and sub.func.value.id == "st" and sub.func.attr in widget_funcs:
                            for kw in sub.keywords:
                                if kw.arg == "key":
                                    widgets.append((sub.lineno, sub.func.attr, ast.unparse(kw.value)))
                    if isinstance(sub, ast.Assign):
                        for tgt in sub.targets:
                            if isinstance(tgt, ast.Subscript) and ast.unparse(tgt.value) == "st.session_state":
                                writes.append((sub.lineno, ast.unparse(tgt.slice)))
                            elif isinstance(tgt, ast.Attribute) and ast.unparse(tgt.value) == "st.session_state":
                                writes.append((sub.lineno, repr(tgt.attr)))
                for wline, wkey in writes:
                    for wid_line, wid_type, wid_key in widgets:
                        if wkey == wid_key and (wline > wid_line or wid_type in readonly_widgets):
                            violations.append(f"{rel}:{node.name}:L{wline} escribe {wkey} tras {wid_type}@L{wid_line}")

        self.assertEqual(violations, [], f"Violaciones de ciclo de vida de widgets: {violations}")

        # Invariante estricta GEMINI.md Regla 1: exactamente 4 st.button en prompt_studio_v8.py
        v8_tree = ast.parse((REPO_ROOT / "modules" / "prompt_studio_v8.py").read_text(encoding="utf-8"))
        btn_keys = [
            ast.unparse(kw.value)
            for node in ast.walk(v8_tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "button"
            for kw in node.keywords
            if kw.arg == "key"
        ]
        self.assertEqual(len(btn_keys), 4, f"len(btn_keys) cambió inesperadamente: {btn_keys}")


@unittest.skipUnless(_HAS_REAL_STREAMLIT, "Requiere streamlit>=1.40 real (streamlit.testing.v1.AppTest)")
class TestV8RealStreamlitAppTest(unittest.TestCase):
    """10. Capa A: Pruebas E2E con streamlit.testing.v1.AppTest real (idéntico al runtime Render)."""

    @staticmethod
    def _build_v8_apptest_script(
        *,
        use_main: bool = False,
        sku_mock: bool = False,
        drive_error_mode: bool = False,
    ) -> str:
        repo_str = repr(str(REPO_ROOT))
        swatch_str = repr(str(REAL_SWATCH_PATH))
        return f"""
import io, os, sys
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw

repo_root = {repo_str}
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from services.sheets_service import sheets_service
from services.ai_prompt_service_v8 import ai_prompt_service_v8 as svc_v8
from modules import prompt_studio_v8 as v8

def _mk_sofa():
    im = Image.new("RGB", (640, 480), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((110, 120, 530, 350), radius=24, fill=(148, 132, 118))
    dr.rectangle((140, 350, 165, 410), fill=(86, 56, 36))
    dr.rectangle((475, 350, 500, 410), fill=(86, 56, 36))
    b = io.BytesIO()
    im.save(b, format="PNG", compress_level=1)
    return b.getvalue()

sofa_png = _mk_sofa()
_sw_p = Path({swatch_str})
if _sw_p.exists():
    swatch_bytes = _sw_p.read_bytes()
else:
    from tests.test_v8 import _build_synthetic_distraction_swatch_bytes
    swatch_bytes = _build_synthetic_distraction_swatch_bytes()
wood_files = sorted((Path(repo_root) / "muestras_madera").glob("*.jpg"))
local_wood = wood_files[0]

fake_muebles = [
    {{"id": "d_render_1", "name": "SOFA MILAN", "filename": "SOFA MILAN.png", "source": "RENDER"}},
    {{"id": "d_subir_1", "name": "SILLON ROMA", "filename": "SILLON ROMA.png", "source": "SUBIR"}},
]
fake_telas = [
    {{"id": "d_tela_1", "name": "TELA NATURAL", "filename": "TELA_NATURAL.jpg", "source": "Telas"}},
]
fake_maderas = [
    {{"id": "", "name": local_wood.stem, "filename": local_wood.name, "local_path": str(local_wood), "source": "Local"}},
]

def _fake_load(fid):
    return swatch_bytes if fid == "d_tela_1" else sofa_png

def _fake_sku(code, **_kw):
    if str(code or "").strip().upper() == "SKU-TEST-1":
        return {{"tipo_mueble": "SOFA", "medidas": "220x95x82"}}
    return None

if {drive_error_mode!r}:
    with patch.object(sheets_service, "ensure_connected", side_effect=RuntimeError("Drive offline")), \\
         patch.object(svc_v8, "get_api_key", return_value=""):
        v8.render_prompt_studio_v8()
elif {use_main!r}:
    import main as app_main
    import modules.alta_fotos_hub as alta_hub
    with patch.object(v8, "cargar_todo_catalogo_v8", return_value=(fake_muebles, fake_telas, fake_maderas)), \\
         patch.object(sheets_service, "ensure_connected", return_value=False), \\
         patch.object(sheets_service, "get_drive_thumbnail_bytes", return_value=sofa_png), \\
         patch.object(v8, "load_drive_file_cached", side_effect=_fake_load), \\
         patch.object(svc_v8, "get_api_key", return_value=""), \\
         patch.object(alta_hub, "render_alta_fotos_hub", lambda: None):
        app_main.main()
else:
    sku_patch = patch.object(sheets_service, "get_furniture_by_sku", side_effect=_fake_sku) if {sku_mock!r} else patch.object(sheets_service, "get_furniture_by_sku", return_value=None)
    with patch.object(v8, "cargar_todo_catalogo_v8", return_value=(fake_muebles, fake_telas, fake_maderas)), \\
         patch.object(sheets_service, "ensure_connected", return_value=False), \\
         patch.object(sheets_service, "get_drive_thumbnail_bytes", return_value=sofa_png), \\
         patch.object(v8, "load_drive_file_cached", side_effect=_fake_load), \\
         patch.object(svc_v8, "get_api_key", return_value=""), \\
         sku_patch:
        v8.render_prompt_studio_v8()
"""

    def test_apptest_T_REPRO_01_and_T_FLOW_03_popover_pick_select_change_remove(self) -> None:
        at = _RealAppTest.from_string(self._build_v8_apptest_script()).run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción inicial: {at.exception}")

        # 1) Elegir mueble desde v8_pop_pick_0 (Crash #1 reportado en producción)
        sb_pick = at.selectbox(key="v8_pop_pick_0")
        sofa_opt = next(o for o in sb_pick.options if "SOFA MILAN" in o)
        sb_pick.select(sofa_opt).run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción en v8_pop_pick_0: {at.exception}")
        self.assertEqual(at.selectbox(key="v8_pop_pick_0").value, ps_v8_mod._V8_POP_PICK_PLACEHOLDER)
        self.assertIn("SOFA MILAN", at.selectbox(key="v8_sb_mueble_0").value)
        self.assertFalse(at.session_state["v8_apply_pick_mueble_0"])

        # 2) Filtrar a Telas y elegir DISTRACTION_NATURAL.jpg (TELA NATURAL)
        at.selectbox(key="v8_pop_cat_0").select("🧵 Telas").run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        tela_opt = next(o for o in at.selectbox(key="v8_pop_pick_0").options if "TELA NATURAL" in o)
        at.selectbox(key="v8_pop_pick_0").select(tela_opt).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.selectbox(key="v8_sb_fabric_0").value, "TELA NATURAL")

        # 3) Filtrar a Maderas y elegir madera local de muestras_madera/
        at.selectbox(key="v8_pop_cat_0").select("🪵 Maderas").run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        wood_opts = at.selectbox(key="v8_pop_pick_0").options
        self.assertGreater(len(wood_opts), 1)
        at.selectbox(key="v8_pop_pick_0").select(wood_opts[1]).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertNotEqual(at.selectbox(key="v8_sb_wood_0").value, at.selectbox(key="v8_sb_wood_0").options[0])

        # 4) Cambiar mueble a SILLON ROMA y luego remover (volver a placeholder)
        sb_m = at.selectbox(key="v8_sb_mueble_0")
        sillon_opt = next(o for o in sb_m.options if "SILLON ROMA" in o)
        sb_m.select(sillon_opt).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertIn("SILLON ROMA", at.selectbox(key="v8_sb_mueble_0").value)

        at.selectbox(key="v8_sb_mueble_0").select(at.selectbox(key="v8_sb_mueble_0").options[0]).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.selectbox(key="v8_sb_mueble_0").value, at.selectbox(key="v8_sb_mueble_0").options[0])

    def test_apptest_T_REPRO_02_popover_cat_actualizar_drive(self) -> None:
        at = _RealAppTest.from_string(self._build_v8_apptest_script()).run(timeout=30)
        self.assertEqual(len(at.exception), 0)

        # Crash #2 latente: seleccionar "🔄 Actualizar Drive" en v8_pop_cat_0
        at.selectbox(key="v8_pop_cat_0").select("🔄 Actualizar Drive").run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción en Actualizar Drive: {at.exception}")
        self.assertEqual(at.selectbox(key="v8_pop_cat_0").value, "📁 Todas")
        self.assertEqual(at.session_state["v8_render_tick"], 1)

    def test_apptest_T_FLOW_04_and_T_FLOW_07_sku_autofill_and_clear_across_modes(self) -> None:
        at = _RealAppTest.from_string(self._build_v8_apptest_script(sku_mock=True)).run(timeout=30)
        self.assertEqual(len(at.exception), 0)

        # Modo Tela / Madera + sub-opción Tela + madera + carpeta SUBIR + SKU autofill
        at.selectbox(key="v8_keep_mode").select(MODES["material"]).run(timeout=30)
        at.selectbox(key="v8_keep_matmode").select("Tela + madera").run(timeout=30)
        at.selectbox(key="v8_keep_folder").select("📤 SUBIR").run(timeout=30)

        # T-FLOW-07: SKU conocido rellena tipo/medidas; desconocido limpia; luego vuelve a conocido
        at.text_input(key="sku_input_v8").input("SKU-TEST-1").run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción SKU autofill: {at.exception}")
        self.assertEqual(at.text_input(key="field_tipo_v8").value, "SOFA")
        self.assertEqual(at.text_input(key="field_medidas_v8").value, "220x95x82")

        at.text_input(key="sku_input_v8").input("SKU-DESCONOCIDO").run(timeout=30)
        self.assertEqual(at.text_input(key="field_tipo_v8").value, "")
        self.assertEqual(at.text_input(key="field_medidas_v8").value, "")

        at.text_input(key="sku_input_v8").input("SKU-TEST-1").run(timeout=30)
        at.text_input(key="v8_notas_0").input("Costura francesa").run(timeout=30)

        # Cargar fotos y generar resultado
        sb_m = at.selectbox(key="v8_sb_mueble_0")
        sb_m.select(sb_m.options[1]).run(timeout=30)
        sb_f = at.selectbox(key="v8_sb_fabric_0")
        sb_f.select(sb_f.options[1]).run(timeout=30)
        sb_w = at.selectbox(key="v8_sb_wood_0")
        sb_w.select(sb_w.options[1]).run(timeout=30)
        at.button(key="v8_btn_go_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertIn("v8_result", at.session_state)

        # T-FLOW-04: Pulsar 🗑️ Borrar -> conserva v8_keep_*, limpia SKU/medidas/notas/v8_result
        at.button(key="v8_btn_clear").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción en Borrar: {at.exception}")
        self.assertEqual(at.session_state["clear_key_v8"], 1)
        self.assertEqual(at.selectbox(key="v8_keep_mode").value, MODES["material"])
        self.assertEqual(at.selectbox(key="v8_keep_matmode").value, "Tela + madera")
        self.assertEqual(at.selectbox(key="v8_keep_folder").value, "📤 SUBIR")
        self.assertEqual(at.text_input(key="sku_input_v8").value, "")
        self.assertEqual(at.text_input(key="field_tipo_v8").value, "")
        self.assertEqual(at.text_input(key="field_medidas_v8").value, "")
        self.assertEqual(at.text_input(key="v8_notas_1").value, "")
        self.assertNotIn("v8_result", at.session_state)

        # Repetir 🗑️ Borrar con "1 Vista" (v8_keep_vista) y "Entorno" (v8_keep_room)
        at.selectbox(key="v8_keep_mode").select(MODES["vista_suelta"]).run(timeout=30)
        vista_opts = at.selectbox(key="v8_keep_vista").options
        chosen_v = vista_opts[2]
        at.selectbox(key="v8_keep_vista").select(chosen_v).run(timeout=30)
        at.button(key="v8_btn_clear").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.selectbox(key="v8_keep_mode").value, MODES["vista_suelta"])
        self.assertEqual(at.selectbox(key="v8_keep_vista").value, chosen_v)

        at.selectbox(key="v8_keep_mode").select(MODES["entorno"]).run(timeout=30)
        room_opts = at.selectbox(key="v8_keep_room").options
        chosen_r = room_opts[1]
        at.selectbox(key="v8_keep_room").select(chosen_r).run(timeout=30)
        at.button(key="v8_btn_clear").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.selectbox(key="v8_keep_mode").value, MODES["entorno"])
        self.assertEqual(at.selectbox(key="v8_keep_room").value, chosen_r)

    def test_apptest_T_FLOW_05_mode_switching_and_launch_with_distraction_natural(self) -> None:
        at = _RealAppTest.from_string(self._build_v8_apptest_script()).run(timeout=30)
        self.assertEqual(len(at.exception), 0)

        # Seleccionar mueble + tela real DISTRACTION_NATURAL.jpg y ejecutar Catálogo (7 vistas)
        at.selectbox(key="v8_sb_mueble_0").select(at.selectbox(key="v8_sb_mueble_0").options[1]).run(timeout=30)
        at.selectbox(key="v8_sb_fabric_0").select(at.selectbox(key="v8_sb_fabric_0").options[1]).run(timeout=30)
        at.button(key="v8_btn_go_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción en 🚀 Catálogo: {at.exception}")

        res = at.session_state["v8_result"]
        self.assertEqual(len(res["items"]), 7)
        ais0 = res["items"][0]["google_ai_studio"]
        self.assertIn("EL CASCO COMPLETO", ais0)
        self.assertIn("#FFFFFF", ais0)
        self.assertIn("0% ground shadow", ais0)
        self.assertIn("2054 x 2054", ais0)
        ref_names = [fn for fn, _b in res["ref_images"]]
        self.assertEqual(len(ref_names), 2)
        self.assertTrue(any("_V8_LIENZO_ESCALA.png" in n for n in ref_names))
        self.assertFalse(any("_V8_LUZ30.png" in n for n in ref_names))
        for fn, raw_b in res["ref_images"]:
            if fn.endswith(".png"):
                self.assertTrue(raw_b.startswith(b"\x89PNG\r\n\x1a\n"))

        # Ciclar todos los demás modos en el selector sin errores de ciclo de vida
        for mode_lbl in MODES.values():
            at.selectbox(key="v8_keep_mode").select(mode_lbl).run(timeout=30)
            self.assertEqual(len(at.exception), 0, f"Excepción al cambiar al modo {mode_lbl}: {at.exception}")

    def test_apptest_T_FLOW_06_34_derecha_2054_popover_zip_and_main_subir_roundtrip(self) -> None:
        prev_gem = os.environ.get("GEMINI_API_KEY")
        try:
            at = _RealAppTest.from_string(self._build_v8_apptest_script(use_main=True)).run(timeout=30)
            self.assertEqual(len(at.exception), 0, f"Excepción inicial main(): {at.exception}")

            # Seleccionar mueble + tela y pulsar ↘️ 3/4 Derecha
            at.selectbox(key="v8_sb_mueble_0").select(at.selectbox(key="v8_sb_mueble_0").options[1]).run(timeout=30)
            at.selectbox(key="v8_sb_fabric_0").select(at.selectbox(key="v8_sb_fabric_0").options[1]).run(timeout=30)
            at.button(key="v8_btn_34_0").click().run(timeout=30)
            self.assertEqual(len(at.exception), 0, f"Excepción en 3/4 Derecha: {at.exception}")

            res = at.session_state["v8_result"]
            p34 = res["items"][0]["google_ai_studio"]
            self.assertIn("FACING TOWARD THE RIGHT", p34)
            self.assertIn("2054 x 2054", p34)
            self.assertIn("#FFFFFF", p34)
            self.assertIn("EL CASCO COMPLETO", p34)
            self.assertNotIn("V8_LUZ30", p34)

            # Verificar ZIP limpio de 2 insumos lossless PNG (mueble + lienzo, sin 3.ª foto macro)
            z_bytes = res["_zip_bytes_cache"]
            with zipfile.ZipFile(io.BytesIO(z_bytes), "r") as zf:
                znames = set(zf.namelist())
                insumos_z = [n for n in znames if n.startswith("insumos/")]
                self.assertEqual(len(insumos_z), 2)
                self.assertTrue(any(n.startswith("insumos/") and n.endswith("_V8_LIENZO_ESCALA.png") for n in znames))
                self.assertFalse(any("_V8_LUZ30.png" in n for n in znames))
                for n in znames:
                    if n.startswith("insumos/") and n.endswith(".png"):
                        self.assertTrue(zf.read(n).startswith(b"\x89PNG\r\n\x1a\n"))

            # 📐 2054px con archivo válido -> 2054x2054 #FFFFFF
            valid_sofa = _make_studio_white_sofa_bytes()
            at.file_uploader(key="v8_ext2054_0_1").upload("sofa.png", valid_sofa, "image/png").run(timeout=30)
            self.assertEqual(len(at.exception), 0, f"Excepción en 2054px válido: {at.exception}")
            self.assertIn("v8_ext2054_cache_0", at.session_state)
            self.assertNotIn("v8_ext2054_cache_0_1", at.session_state)
            cached_2054 = at.session_state["v8_ext2054_cache_0"]["data"]
            with Image.open(io.BytesIO(cached_2054["png"])) as im2054:
                self.assertEqual(im2054.size, (2054, 2054))
                self.assertEqual(im2054.getpixel((0, 0)), (255, 255, 255))

            # 📐 2054px con archivo corrupto -> st.error limpio, cero excepción
            at.file_uploader(key="v8_ext2054_0_1").upload("roto.png", b"corrupt-payload-xyz", "image/png").run(timeout=30)
            self.assertEqual(len(at.exception), 0, f"Excepción no controlada en 2054px corrupto: {at.exception}")
            self.assertTrue(any("2054" in e.value for e in at.error), f"Faltó st.error en 2054px corrupto: {at.error}")

            # 🚀 Subir -> Alta de Fotos -> ← Prompts (incrementa v8_render_tick sin error)
            at.button(key="v8_goto_alta_0_1").click().run(timeout=30)
            self.assertEqual(len(at.exception), 0, f"Excepción en 🚀 Subir: {at.exception}")
            self.assertEqual(at.selectbox(key="unified_active_app").value, "🚀 Alta de Fotos")
            self.assertEqual(at.session_state["v7_last_photo_stem"], "SOFA MILAN")

            at.button(key="btn_back_prompts").click().run(timeout=30)
            self.assertEqual(len(at.exception), 0, f"Excepción en ← Prompts: {at.exception}")
            self.assertEqual(at.selectbox(key="unified_active_app").value, "🤖 Prompts + IA")
            self.assertEqual(at.session_state["v8_render_tick"], 1)
        finally:
            if prev_gem is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = prev_gem

    def test_apptest_T_FLOW_08_two_photo_strip_and_dynamic_user_notes_override(self) -> None:
        at = _RealAppTest.from_string(self._build_v8_apptest_script()).run(timeout=30)
        self.assertEqual(len(at.exception), 0)

        at.selectbox(key="v8_sb_mueble_0").select(at.selectbox(key="v8_sb_mueble_0").options[1]).run(timeout=30)
        at.selectbox(key="v8_sb_fabric_0").select(at.selectbox(key="v8_sb_fabric_0").options[1]).run(timeout=30)
        at.text_input(key="v8_notas_0").input(
            "quiero que hagas un 40%mas claro el tono de la tela  y 20% mas pequeños la textura"
        ).run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción al escribir Notas V8: {at.exception}")

        at.button(key="v8_btn_34_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción en 3/4 Derecha con Notas V8: {at.exception}")

        res = at.session_state["v8_result"]
        p_ais = res["items"][0]["google_ai_studio"]
        p_dal = res["items"][0]["chatgpt_dalle3"]
        self.assertEqual(len(res["ref_images"]), 2)
        self.assertFalse(any("_V8_LUZ30.png" in fn for fn, _ in res["ref_images"]))
        self.assertNotIn("+30%", p_ais)
        self.assertNotIn("+30%", p_dal)
        self.assertNotIn("0% additional color, hue, or brightness drift", p_ais)
        self.assertIn("ALREADY BAKED INTO", p_ais)
        self.assertIn("DO NOT DOUBLE-APPLY", p_ais)
        self.assertIn("ALREADY pixel-calibrated in", p_dal)

    def test_apptest_T_ERR_09_empty_missing_and_drive_error_states(self) -> None:
        at = _RealAppTest.from_string(self._build_v8_apptest_script()).run(timeout=30)
        self.assertEqual(len(at.exception), 0)

        # 1) Sin foto en Catálogo y 3/4 Derecha -> st.error amigable
        at.button(key="v8_btn_go_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertGreater(len(at.error), 0)

        at.button(key="v8_btn_34_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertGreater(len(at.error), 0)

        # 2) Tela / Madera sin tela ni madera
        at.selectbox(key="v8_sb_mueble_0").select(at.selectbox(key="v8_sb_mueble_0").options[1]).run(timeout=30)
        at.selectbox(key="v8_keep_mode").select(MODES["material"]).run(timeout=30)
        at.selectbox(key="v8_keep_matmode").select("Solo tela").run(timeout=30)
        at.button(key="v8_btn_go_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("tela" in e.value.lower() for e in at.error))

        at.selectbox(key="v8_keep_matmode").select("Solo madera").run(timeout=30)
        at.button(key="v8_btn_go_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("madera" in e.value.lower() for e in at.error))

        # 3) Lote Tela sin vistas y Clonar Color sin base/objetivo
        at.selectbox(key="v8_keep_mode").select(MODES["vistas_tela"]).run(timeout=30)
        at.button(key="v8_btn_go_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertGreater(len(at.error), 0)

        at.selectbox(key="v8_keep_mode").select(MODES["clonar_color"]).run(timeout=30)
        at.button(key="v8_btn_go_0").click().run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertGreater(len(at.error), 0)

        # 4) Búsqueda en popover con 0 coincidencias mantiene únicamente el placeholder
        at.text_input(key="v8_pop_q_0").input("ZZZ_NO_EXISTE_999").run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.selectbox(key="v8_pop_pick_0").options, [ps_v8_mod._V8_POP_PICK_PLACEHOLDER])

        # 5) Fallo en Google Drive degrada limpiamente a muestras locales de muestras_madera/
        at_err = _RealAppTest.from_string(self._build_v8_apptest_script(drive_error_mode=True)).run(timeout=30)
        self.assertEqual(len(at_err.exception), 0, f"Excepción cuando Drive falla: {at_err.exception}")
        self.assertGreater(len(at_err.selectbox(key="v8_sb_wood_0").options), 1)

    def test_apptest_T_R3_none_name_guards_and_sanitized_downloads(self) -> None:
        # 1) {'name': None} en v8_picked_mueble_0, v8_picked_fabric_0 y catálogo de Drive -> 0 excepciones
        script_none_drive = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
import modules.prompt_studio_v8 as ps_v8
from services.sheets_service import sheets_service
sheets_service.ensure_connected = lambda: True
sheets_service.get_multiple_drive_folders_files = lambda *a, **k: {{
    "RENDER": [
        {{"id": "bad1", "name": None, "filename": "x.png", "source": "RENDER"}},
        {{"id": "d1", "name": "SOFA MILAN", "filename": "SOFA_MILAN.png", "source": "RENDER"}},
    ],
    "SUBIR": [], "COTIZACION": [], "SM_MUEBLERIA": [],
    "TELAS": [{{"id": "bt1", "name": None, "filename": "t.jpg"}}, {{"id": "t1", "name": "LINO", "filename": "LINO.jpg"}}],
    "TELAS_ODOO": [],
    "MADERAS": [{{"id": "bw1", "name": None, "filename": "m.jpg"}}],
}}
ps_v8.invalidate_v8_catalog_caches()
ps_v8.render_prompt_studio_v8()
"""
        at = _RealAppTest.from_string(script_none_drive)
        at.session_state["v8_apply_pick_mueble_0"] = True
        at.session_state["v8_picked_mueble_0"] = {"name": None, "id": "x"}
        at.session_state["v8_apply_pick_fabric_0"] = True
        at.session_state["v8_picked_fabric_0"] = {"name": None, "id": "x"}
        at.run(timeout=30)
        self.assertEqual(len(at.exception), 0, f"Excepción con {{'name': None}}: {at.exception}")
        self.assertFalse(at.session_state["v8_apply_pick_mueble_0"])
        self.assertFalse(at.session_state["v8_apply_pick_fabric_0"])

        # 2) Result con mueble_name hostil renderiza botones de descarga sin caracteres ilegales ni crash
        at2 = _RealAppTest.from_string(self._build_v8_apptest_script())
        at2.session_state["v8_result"] = {
            "mode": "vista_34_der_2054",
            "gen_id": 1,
            "mueble_name": 'SOFA / SECCIONAL: *?"<>| MILAN',
            "items": [{
                "id": "v1", "label": "3/4", "short_name": "3/4", "icon": "↘️",
                "google_ai_studio": "prompt ais", "chatgpt_dalle3": "prompt dal", "midjourney_v6": "prompt mj",
                "attachment_guide": ["Image 1: Foto"], "checklist": ["ok"], "output_filename": "SOFA.png",
            }],
            "ref_images": [],
        }
        at2.run(timeout=30)
        self.assertEqual(len(at2.exception), 0, f"Excepción con mueble_name hostil: {at2.exception}")


class TestV8Round2UpgradesAndUserDirectives(unittest.TestCase):
    """11. Verificación exhaustiva Ronda 2 (F-17 2-photo clean, F-18 ROI/CIELAB/scale, F-19 Notes parser & zero-contradiction)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.real_swatch_bytes = _load_test_swatch_bytes()
        cls.download_swatch_bytes = DOWNLOAD_SWATCH_PATH.read_bytes() if DOWNLOAD_SWATCH_PATH.exists() else None
        cls.studio_sofa_bytes = _make_studio_white_sofa_bytes()
        cls.fab_ana_default = v8.analyze_fabric_v8_local(cls.real_swatch_bytes, sample_name="TELA_NATURAL.jpg")

    @staticmethod
    def _mean_l_star(im: Image.Image) -> float:
        st_im = ImageStat.Stat(im)
        return fc_v8._srgb_to_lab_tuple(*st_im.mean)[0]

    @staticmethod
    def _hi242_pct(im: Image.Image) -> float:
        raw = im.tobytes()
        n = max(1, len(raw) // 3)
        hi = sum(1 for i in range(0, len(raw), 3) if max(raw[i], raw[i + 1], raw[i + 2]) >= 242)
        return (100.0 * hi) / float(n)

    def test_two_photo_clean_architecture_and_pre_furniture_preview_fallbacks(self) -> None:
        # Compatibilidad de nombre legacy conservada en fabric_composer_v8
        self.assertEqual(make_v8_swatch_filename("TELA_NATURAL.jpg"), "TELA_NATURAL_V8_LUZ30.png")

        # 1) Mueble + Tela -> estrictamente 2 fotos limpias (Image 1 Mueble + Image 2 Lienzo Escala V8)
        pack_2 = v8.build_v8_reference_pack(
            mode="vista_34_der_2054",
            furniture_name="SECCIONAL_ROMA",
            furniture_filenames=["SECCIONAL_ROMA.jpg"],
            furniture_bytes_list=[self.studio_sofa_bytes],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            tipo_mueble="SECCIONAL",
        )
        self.assertEqual([p["role"] for p in pack_2], ["primary_furniture", "v8_scale_canvas"])
        self.assertEqual([p["slot_index"] for p in pack_2], [1, 2])
        self.assertFalse(any("_V8_LUZ30" in p["filename"] for p in pack_2))

        # 2) Mueble + Tela + Madera -> estrictamente 3 fotos (Image 1 Mueble + Image 2 Lienzo + Image 3 Madera)
        pack_3 = v8.build_v8_reference_pack(
            mode="material",
            material_mode="dual",
            furniture_name="SECCIONAL_ROMA",
            furniture_filenames=["SECCIONAL_ROMA.jpg"],
            furniture_bytes_list=[self.studio_sofa_bytes],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            wood_label="PAROTA",
            wood_filename="PAROTA.jpg",
            wood_bytes=self.studio_sofa_bytes,
            tipo_mueble="SECCIONAL",
        )
        self.assertEqual([p["role"] for p in pack_3], ["primary_furniture", "v8_scale_canvas", "wood_sample"])
        self.assertEqual([p["slot_index"] for p in pack_3], [1, 2, 3])

        # 3) Fallback UI previa a elegir mueble (no entra al pack de prompts, solo vista previa segura <= 243)
        thumbs_pre_furn = build_ordered_photo_thumbs_v8(
            mode="catalogo",
            material_mode="fabric_only",
            m_names=[],
            m_bytes=[],
            m_source="",
            fabric_name="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            wood_name="",
            wood_bytes=None,
            batch_views_files=[],
        )
        self.assertEqual(len(thumbs_pre_furn), 1)
        self.assertEqual(thumbs_pre_furn[0][2], "Tela · Elige mueble")
        with Image.open(io.BytesIO(thumbs_pre_furn[0][1])) as im_pf:
            self.assertLessEqual(max(e[1] for e in im_pf.getextrema()), 243)

        # 4) Fallback UI previa a subir vistas en vistas_tela
        thumbs_pre_vt = build_ordered_photo_thumbs_v8(
            mode="vistas_tela",
            material_mode="fabric_only",
            m_names=[],
            m_bytes=[],
            m_source="",
            fabric_name="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            wood_name="",
            wood_bytes=None,
            batch_views_files=[],
        )
        self.assertEqual(len(thumbs_pre_vt), 1)
        self.assertEqual(thumbs_pre_vt[0][2], "Tela · Sube vistas")

    def test_compact_swatch_roi_and_download_jpg_cielab_calibration(self) -> None:
        if self.download_swatch_bytes is None:
            self.skipTest(f"No existe {DOWNLOAD_SWATCH_PATH}")

        # 1) Expansión uniforme 80% en muestra compacta limpia download.jpg (228x228 -> 182x182)
        roi_dl = extract_clean_swatch_roi_v8(self.download_swatch_bytes)
        self.assertEqual(roi_dl.crop.size, (182, 182))
        self.assertEqual(roi_dl.bbox, (23, 23, 205, 205))

        # 2) Muestra compacta con etiqueta sintética abajo-derecha -> cae a interior seguro top-left 160x160 sin tocar etiqueta
        with Image.open(io.BytesIO(self.download_swatch_bytes)) as im_dl:
            im_tag = im_dl.convert("RGB").copy()
            ImageDraw.Draw(im_tag).rectangle((172, 184, 224, 224), fill=(250, 250, 250))
            ImageDraw.Draw(im_tag).rectangle((180, 192, 216, 216), fill=(20, 20, 20))
            roi_tag = extract_clean_swatch_roi_v8(_encode_png(im_tag))
            self.assertEqual(roi_tag.crop.size, (160, 160))
            self.assertLessEqual(roi_tag.bbox[2], 171)
            self.assertLessEqual(roi_tag.bbox[3], 182)

            # 3) Muestra compacta con pliegue diagonal oscuro -> rechaza expansión uniforme y conserva ROI pequeño limpio
            im_fold = im_dl.convert("RGB").copy()
            px = im_fold.load()
            for yy in range(228):
                for xx in range(228):
                    if 200 <= (xx + yy) <= 230:
                        px[xx, yy] = (35, 33, 30)
            roi_fold = extract_clean_swatch_roi_v8(_encode_png(im_fold))
            self.assertLess(roi_fold.crop.size[0], 80)
            self.assertGreater(roi_fold.min_rgb, 60)

        # 4) CIELAB monótono en L*, techo <= 243, hi>=242 < 3%, calidez R>G>B y 0 píxeles erosionados en 2054x2054
        roi_dn = extract_clean_swatch_roi_v8(self.real_swatch_bytes)
        for sw_name, roi_obj in (("download.jpg", roi_dl), ("DISTRACTION_NATURAL.jpg", roi_dn)):
            l_seq = []
            for b_val in (-0.20, 0.0, 0.30, 0.40, 0.50):
                cal_im = calibrate_fabric_lightness_v8(roi_obj.crop, boost=b_val, max_rgb=243)
                st_cal = ImageStat.Stat(cal_im)
                l_seq.append(self._mean_l_star(cal_im))
                self.assertLessEqual(max(e[1] for e in cal_im.getextrema()), 243)
                self.assertLess(self._hi242_pct(cal_im), 3.0, f"Exceso de píxeles >=242 en {sw_name} boost={b_val}")
                self.assertGreaterEqual(st_cal.mean[0], st_cal.mean[1] - 0.5)
                self.assertGreaterEqual(st_cal.mean[1], st_cal.mean[2] - 0.5)
                if b_val in (0.30, 0.50):
                    c2054 = Image.new("RGB", (2054, 2054), (255, 255, 255))
                    c2054.paste(cal_im, (10, 900))
                    fmt = v8.format_image_2054_white(_encode_png(c2054), target_px=2054, pure_white_border=True)
                    with Image.open(io.BytesIO(fmt["png"])) as out_im:
                        rec = out_im.crop((10, 900, 10 + cal_im.width, 900 + cal_im.height))
                        self.assertEqual(cal_im.tobytes(), rec.tobytes(), f"Erosión 2054 en {sw_name} boost={b_val}")
            self.assertTrue(
                all(l_seq[i] < l_seq[i + 1] for i in range(len(l_seq) - 1)),
                f"L* no estrictamente monótono en {sw_name}: {l_seq}",
            )

    def test_sectional_width_inference_uuid_cutout_fallback_and_32x32_cold_cpu(self) -> None:
        cases_w = [
            ("sala en u", 300.0),
            ("SECCIONAL ROMA", 285.0),
            ("sectional beige", 285.0),
            ("esquinero derecho", 285.0),
            ("chaise longue", 285.0),
            ("sala en L", 285.0),
            ("sofá en lino", 220.0),
            ("sala en lino", 260.0),
            ("sala moderna", 260.0),
            ("loveseat 2 plazas", 165.0),
            ("sofá 3 plazas", 230.0),
            ("sofá 4 plazas", 265.0),
        ]
        for txt, expected_w in cases_w:
            self.assertEqual(infer_furniture_width_cm_v8(None, txt), expected_w, f"Ancho incorrecto para '{txt}'")

        self.assertEqual(compute_v8_tile_px(1280, 285.0, texture_scale_factor=1.0), (52, 25))
        self.assertEqual(compute_v8_tile_px(1280, 285.0, texture_scale_factor=0.80), (40, 32))

        # Respaldo de proporción de recorte para foto UUID anónima de seccional ancho (aspect >= 2.25:1)
        wide_sec = Image.new("RGB", (960, 600), (255, 255, 255))
        ImageDraw.Draw(wide_sec).rounded_rectangle((60, 220, 900, 500), radius=20, fill=(142, 130, 118))
        wide_bytes = _encode_png(wide_sec)

        clear_v8_composer_cache()
        art_uuid = build_v8_conditioning_canvas(
            furniture_bytes=wide_bytes,
            fabric_bytes=self.real_swatch_bytes,
            sample_name="TELA.jpg",
            furniture_name="81d7d356-0664-4b1e-8dac-a2667f073037.jpg",
            furniture_width_cm=None,
            furniture_type="",
            texture_scale_factor=0.80,
        )
        self.assertEqual((art_uuid.tile_px, art_uuid.grid_count, art_uuid.total_tiles), (40, 32, 1024))

        # Rendimiento frío CPU a 32x32 = 1024 baldosas debe mantenerse < 280 ms gracias a _tile_canvas_fast O(log N)
        cpu_runs = []
        sw_bench = self.download_swatch_bytes or self.real_swatch_bytes
        for _ in range(5):
            clear_v8_composer_cache()
            t0_cpu = time.process_time()
            build_v8_conditioning_canvas(
                furniture_bytes=wide_bytes,
                fabric_bytes=sw_bench,
                sample_name="TELA.jpg",
                furniture_name="SECCIONAL_BENCH.jpg",
                furniture_width_cm=285.0,
                texture_scale_factor=0.80,
            )
            cpu_runs.append((time.process_time() - t0_cpu) * 1000.0)
        self.assertLess(statistics.median(cpu_runs), 280.0, f"Mediana CPU 32x32 excedió 280 ms: {cpu_runs}")

    def test_parse_v8_user_fabric_directives_50_plus_vectors_and_zero_false_positives(self) -> None:
        vectors = [
            # Caso real exacto del usuario + variantes duales
            ("quiero que hagas un 40%mas claro el tono de la tela  y 20% mas pequeños la textura", ("lighter", 0.50, "smaller", 0.80, "")),
            ("40% mas claro el tono de la tela 20% mas pequena la textura", ("lighter", 0.50, "smaller", 0.80, "")),
            ("hacer la textura 20% más chica y 40% más clara la tela", ("lighter", 0.50, "smaller", 0.80, "")),
            ("quiero que hagas un 40%mas claro el tono de la tela y 20% mas pequeños la textura, Costura francesa", ("lighter", 0.50, "smaller", 0.80, "Costura francesa")),
            # Luminosidad (español + inglés + cualitativo + original + suave)
            ("40% más claro", ("lighter", 0.50, "default", 1.0, "")),
            ("aclarar 35%", ("lighter", 0.475, "default", 1.0, "")),
            ("20% más claro el tono", ("lighter", 0.40, "default", 1.0, "")),
            ("un 50 por ciento más clara la tela", ("lighter", 0.55, "default", 1.0, "")),
            ("tela un poco más clara", ("lighter", 0.40, "default", 1.0, "")),
            ("tono más claro", ("lighter", 0.45, "default", 1.0, "")),
            ("tela mucho más clara", ("lighter", 0.55, "default", 1.0, "")),
            ("lighten 40%", ("lighter", 0.50, "default", 1.0, "")),
            ("make fabric 30% lighter", ("lighter", 0.45, "default", 1.0, "")),
            ("25% más oscuro", ("darker", -0.25, "default", 1.0, "")),
            ("oscurecer 15%", ("darker", -0.15, "default", 1.0, "")),
            ("tono más oscuro", ("darker", -0.15, "default", 1.0, "")),
            ("darken fabric 20%", ("darker", -0.20, "default", 1.0, "")),
            ("sin aclarar", ("original", 0.0, "default", 1.0, "")),
            ("tono original de la tela", ("original", 0.0, "default", 1.0, "")),
            ("no aclarar la tela", ("original", 0.0, "default", 1.0, "")),
            ("0% más claro", ("original", 0.0, "default", 1.0, "")),
            ("do not lighten", ("original", 0.0, "default", 1.0, "")),
            ("keep original color", ("original", 0.0, "default", 1.0, "")),
            ("menos claro el tono", ("softer_light", 0.10, "default", 1.0, "")),
            ("no tan clara la tela", ("softer_light", 0.10, "default", 1.0, "")),
            # Escala de textura (más pequeña / más grande / acotado [0.50, 1.50])
            ("textura 30% más pequeña", ("default", 0.30, "smaller", 0.70, "")),
            ("tejido 25% más fino", ("default", 0.30, "smaller", 0.75, "")),
            ("trama más chica", ("default", 0.30, "smaller", 0.80, "")),
            ("smaller texture 20%", ("default", 0.30, "smaller", 0.80, "")),
            ("reduce fabric scale 30%", ("default", 0.30, "smaller", 0.70, "")),
            ("bajar el tamaño de la textura un 20%", ("default", 0.30, "smaller", 0.80, "")),
            ("microtextura", ("default", 0.30, "smaller", 0.70, "")),
            ("escala de textura 20% menor", ("default", 0.30, "smaller", 0.80, "")),
            ("20% más grande la textura", ("default", 0.30, "larger", 1.20, "")),
            ("20% larger weave", ("default", 0.30, "larger", 1.20, "")),
            ("reducir escala de textura 80%", ("default", 0.30, "smaller", 0.50, "")),
            ("agrandar textura 90%", ("default", 0.30, "larger", 1.50, "")),
            ("textura del sofá 25% más pequeña", ("default", 0.30, "smaller", 0.75, "")),
            ("tela del sillón 40% más clara", ("lighter", 0.50, "default", 1.0, "")),
            ("el sofá en tela 40% más clara", ("lighter", 0.50, "default", 1.0, "")),
            ("tela 30% más clara y 20% más fina", ("lighter", 0.45, "smaller", 0.80, "")),
            ("textura 20% más fina y 40% más clara", ("lighter", 0.50, "smaller", 0.80, "")),
            # Guardias estrictas contra falsos positivos (madera/patas, geometría, iluminación, negaciones, medidas)
            ("patas de madera 20% más oscuras", ("default", 0.30, "default", 1.0, "patas de madera 20% más oscuras")),
            ("patas más oscuras y delgadas", ("default", 0.30, "default", 1.0, "patas más oscuras y delgadas")),
            ("madera nogal 25% más clara", ("default", 0.30, "default", 1.0, "madera nogal 25% más clara")),
            ("base de metal más oscura", ("default", 0.30, "default", 1.0, "base de metal más oscura")),
            ("mesa más pequeña", ("default", 0.30, "default", 1.0, "mesa más pequeña")),
            ("sofá 30% más grande", ("default", 0.30, "default", 1.0, "sofá 30% más grande")),
            ("cojines 20% más pequeños", ("default", 0.30, "default", 1.0, "cojines 20% más pequeños")),
            ("sillón más chico y más oscuro", ("default", 0.30, "default", 1.0, "sillón más chico y más oscuro")),
            ("20% más pequeño", ("default", 0.30, "default", 1.0, "20% más pequeño")),
            ("luz de estudio más clara", ("default", 0.30, "default", 1.0, "luz de estudio más clara")),
            ("fondo más claro", ("default", 0.30, "default", 1.0, "fondo más claro")),
            ("pared más oscura y alfombra más pequeña", ("default", 0.30, "default", 1.0, "pared más oscura y alfombra más pequeña")),
            ("no oscurecer la tela", ("default", 0.30, "default", 1.0, "no oscurecer la tela")),
            ("que no quede oscura la tela", ("default", 0.30, "default", 1.0, "que no quede oscura la tela")),
            ("no agrandar la textura", ("default", 0.30, "default", 1.0, "no agrandar la textura")),
            ("no achicar la textura", ("default", 0.30, "default", 1.0, "no achicar la textura")),
            ("100% poliéster, 280 x 170 cm, vista 3/4 derecha", ("default", 0.30, "default", 1.0, "100% poliéster, 280 x 170 cm, vista 3/4 derecha")),
            ("100% lino natural", ("default", 0.30, "default", 1.0, "100% lino natural")),
            ("Costura francesa en cojines", ("default", 0.30, "default", 1.0, "Costura francesa en cojines")),
            # Cláusulas mixtas (tela + residual no textil)
            ("patas de madera 20% más oscuras y tela 40% más clara", ("lighter", 0.50, "default", 1.0, "patas de madera 20% más oscuras")),
            ("patas de madera nogal oscuro con tela 40% más clara", ("lighter", 0.50, "default", 1.0, "patas de madera nogal oscuro")),
            ("tela 35% más clara con patas de madera 20% más oscuras", ("lighter", 0.475, "default", 1.0, "con patas de madera 20% más oscuras")),
            ("make the fabric 40% lighter and 20% smaller texture, keep walnut legs darker", ("lighter", 0.50, "smaller", 0.80, "keep walnut legs darker")),
            ("hacer la tela más oscura pero las patas más claras", ("darker", -0.15, "default", 1.0, "las patas más claras")),
        ]
        for raw_txt, exp in vectors:
            d = parse_v8_user_fabric_directives(raw_txt)
            got = (d.lightness_mode, d.effective_boost, d.scale_mode, d.texture_scale_factor, d.residual_non_fabric_notes)
            self.assertEqual(got, exp, f"Fallo en parser para {raw_txt!r}: obtuvo {got} != {exp}")

    def test_zero_contradiction_prompts_and_dynamic_canvas_across_all_modes(self) -> None:
        user_note = "quiero que hagas un 40%mas claro el tono de la tela  y 20% mas pequeños la textura"
        mixed_note = "patas de madera 20% más oscuras y tela 40% más clara"

        # 1) Cero contradicciones y cero fugas "+30%" en TODOS los modos con tela (incluso con fabric_analysis precalculado)
        mode_outputs = []
        for md in ("catalogo", "vista_suelta", "material", "entorno", "extraer", "hd", "vistas_tela"):
            kw = {
                "mode": md,
                "furniture_name": "SECCIONAL_ROMA",
                "tipo_mueble": "SECCIONAL",
                "furniture_filenames": ["SECCIONAL_ROMA.jpg"],
                "fabric_label": "TELA NATURAL",
                "fabric_filename": "TELA_NATURAL.jpg",
                "fabric_analysis": self.fab_ana_default,
                "notas_usuario": user_note,
                "api_key": "",
            }
            if md == "vistas_tela":
                kw["batch_ref_bytes"] = self.real_swatch_bytes
                kw["batch_views"] = [("vista_1.png", self.studio_sofa_bytes)]
            with _offline_ai_clients(v8):
                res_m = v8.build_prompts(**kw)
            mode_outputs.append((md, res_m["items"][0]["google_ai_studio"], res_m["items"][0]["chatgpt_dalle3"]))
            if md == "catalogo":
                mode_outputs.append(("catalogo_master", res_m["master_ais"], res_m["master_dal"]))

        res_34 = v8.build_34_derecha_2054_prompts(
            furniture_name="SECCIONAL_ROMA",
            tipo_mueble="SECCIONAL",
            furniture_filenames=["SECCIONAL_ROMA.jpg"],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_analysis=self.fab_ana_default,
            notas_usuario=user_note,
        )
        mode_outputs.append(("34_derecha", res_34["items"][0]["google_ai_studio"], res_34["items"][0]["chatgpt_dalle3"]))

        for tag, p_ais, p_dal in mode_outputs:
            self.assertNotIn("+30%", p_ais, f"Fuga '+30%' en AIS ({tag})")
            self.assertNotIn("+30%", p_dal, f"Fuga '+30%' en DAL ({tag})")
            self.assertNotIn("0% additional color, hue, or brightness drift", p_ais, f"Contradicción en AIS ({tag})")
            self.assertIn("ALREADY BAKED INTO", p_ais, f"Falta reconciliación AIS ({tag})")
            self.assertIn("DO NOT DOUBLE-APPLY", p_ais, f"Falta anti-doble-aplicación AIS ({tag})")
            self.assertIn("ALREADY pixel-calibrated in", p_dal, f"Falta reconciliación DAL ({tag})")
            self.assertIn("coarse oversized weave", p_ais, f"Falta término negativo de escala fina en {tag}")

        # 2) Nota mixta conserva directiva residual de madera intacta junto a reconciliación de tela
        res_mix = v8.build_34_derecha_2054_prompts(
            furniture_name="SECCIONAL_ROMA",
            tipo_mueble="SECCIONAL",
            furniture_filenames=["SECCIONAL_ROMA.jpg"],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_analysis=self.fab_ana_default,
            notas_usuario=mixed_note,
        )
        self.assertIn("MANDATORY USER DIRECTIVES (APPLY TO SCENE/FURNITURE): patas de madera 20% más oscuras", res_mix["items"][0]["google_ai_studio"])
        self.assertIn("patas de madera 20% más oscuras", res_mix["items"][0]["chatgpt_dalle3"])
        self.assertNotIn("+30%", res_mix["items"][0]["google_ai_studio"])

        # 3) Modo oscuro / original omite "dark uncalibrated taupe shift" en Negative Prompt
        for dark_note in ("25% más oscuro", "sin aclarar"):
            r_dk = v8.build_34_derecha_2054_prompts(
                furniture_name="SECCIONAL_ROMA",
                tipo_mueble="SECCIONAL",
                furniture_filenames=["SECCIONAL_ROMA.jpg"],
                fabric_label="TELA NATURAL",
                fabric_filename="TELA_NATURAL.jpg",
                fabric_analysis=self.fab_ana_default,
                notas_usuario=dark_note,
            )
            self.assertNotIn("dark uncalibrated taupe shift", r_dk["items"][0]["google_ai_studio"])
            self.assertNotIn("+30%", r_dk["items"][0]["google_ai_studio"])

        # 4) El Lienzo V8 real es mediblemente más claro y de baldosas más finas con user_note que por defecto
        pack_def = v8.build_v8_reference_pack(
            mode="vista_34_der_2054",
            furniture_name="SECCIONAL_ROMA",
            furniture_filenames=["SECCIONAL_ROMA.jpg"],
            furniture_bytes_list=[self.studio_sofa_bytes],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            tipo_mueble="SECCIONAL",
            custom_notes="",
        )
        pack_usr = v8.build_v8_reference_pack(
            mode="vista_34_der_2054",
            furniture_name="SECCIONAL_ROMA",
            furniture_filenames=["SECCIONAL_ROMA.jpg"],
            furniture_bytes_list=[self.studio_sofa_bytes],
            fabric_label="TELA NATURAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            tipo_mueble="SECCIONAL",
            custom_notes=user_note,
        )
        c_def = next(p for p in pack_def if p["role"] == "v8_scale_canvas")
        c_usr = next(p for p in pack_usr if p["role"] == "v8_scale_canvas")
        self.assertEqual(c_def["total_tiles"], 625)   # 25x25
        self.assertEqual(c_usr["total_tiles"], 1024)  # 32x32 (-20% textura)
        with Image.open(io.BytesIO(c_def["bytes"])) as im_d, Image.open(io.BytesIO(c_usr["bytes"])) as im_u:
            l_def = self._mean_l_star(im_d.crop((0, 0, 200, 200)))
            l_usr = self._mean_l_star(im_u.crop((0, 0, 200, 200)))
        self.assertGreater(l_usr, l_def + 1.0, f"Lienzo +40% no superó L* del lienzo base: {l_usr:.2f} vs {l_def:.2f}")

        # 5) Caché de vistas_tela diferencia custom_notes (no devuelve bytes obsoletos de +30%)
        clear_vistas_tela_v8_cache()
        vt_def = v8.build_v8_reference_pack(
            mode="vistas_tela",
            furniture_name="SECCIONAL_ROMA",
            tipo_mueble="SECCIONAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            target_view=("vista_1.png", self.studio_sofa_bytes),
            custom_notes="",
        )
        vt_usr = v8.build_v8_reference_pack(
            mode="vistas_tela",
            furniture_name="SECCIONAL_ROMA",
            tipo_mueble="SECCIONAL",
            fabric_filename="TELA_NATURAL.jpg",
            fabric_bytes=self.real_swatch_bytes,
            target_view=("vista_1.png", self.studio_sofa_bytes),
            custom_notes=user_note,
        )
        self.assertNotEqual(vt_def[1]["bytes"], vt_usr[1]["bytes"])
        self.assertEqual(vt_usr[1]["total_tiles"], 1024)

    def test_r3_uuid_wide_cutout_total_tiles_parity_and_stale_fa_name_sanitization(self) -> None:
        real_img_path = Path("/home/antigravity/image.png")
        uuid_img_bytes: bytes | None = None
        if real_img_path.exists():
            _cand_img = real_img_path.read_bytes()
            if fc_v8._infer_cutout_width_cm_from_bytes_v8(_cand_img) is not None:
                uuid_img_bytes = _cand_img
        if uuid_img_bytes is None:
            wide_sec = Image.new("RGB", (1024, 1024), (255, 255, 255))
            ImageDraw.Draw(wide_sec).rounded_rectangle((16, 224, 726, 508), radius=20, fill=(130, 122, 114))
            uuid_img_bytes = _encode_png(wide_sec)
        sw_bytes = self.download_swatch_bytes or self.real_swatch_bytes
        user_note = "quiero que hagas un 40%mas claro el tono de la tela  y 20% mas pequeños la textura"

        # 1) Paridad 1:1 total_tiles (1024 con -20% y 625 por defecto) entre Image 2 y texto de prompts en UUID ancho
        for cur_note, exp_tiles in ((user_note, 1024), ("", 625)):
            pack_34 = v8.build_v8_reference_pack(
                mode="vista_34_der_2054",
                furniture_name="81d7d356-0664-4b1e-8dac-a2667f073037",
                furniture_filenames=["81d7d356-0664-4b1e-8dac-a2667f073037.jpg"],
                furniture_bytes_list=[uuid_img_bytes],
                fabric_label="TELA MUESTRA",
                fabric_filename="TELA_MUESTRA.jpg",
                fabric_bytes=sw_bytes,
                custom_notes=cur_note,
            )
            self.assertEqual(pack_34[1]["total_tiles"], exp_tiles)

            res_34 = v8.build_34_derecha_2054_prompts(
                furniture_name="81d7d356-0664-4b1e-8dac-a2667f073037",
                notas_usuario=cur_note,
                fabric_label="TELA MUESTRA",
                furniture_filenames=["81d7d356-0664-4b1e-8dac-a2667f073037.jpg"],
                fabric_filename="TELA_MUESTRA.jpg",
                furniture_bytes_list=[uuid_img_bytes],
                fabric_bytes=sw_bytes,
                precomputed_pack=pack_34,
            )
            self.assertIn(f"{exp_tiles} seamless", res_34["items"][0]["google_ai_studio"])

            for md in ("catalogo", "material"):
                res_m = v8.build_prompts(
                    mode=md,
                    furniture_name="81d7d356-0664-4b1e-8dac-a2667f073037",
                    notas_usuario=cur_note,
                    fabric_label="TELA MUESTRA",
                    furniture_filenames=["81d7d356-0664-4b1e-8dac-a2667f073037.jpg"],
                    fabric_filename="TELA_MUESTRA.jpg",
                    furniture_bytes_list=[uuid_img_bytes],
                    fabric_bytes=sw_bytes,
                )
                self.assertIn(f"{exp_tiles} seamless", res_m["items"][0]["google_ai_studio"])
                if md == "catalogo":
                    self.assertIn(f"{exp_tiles} seamless", res_m["master_ais"])

            with _offline_ai_clients(v8):
                res_vt = v8.build_prompts(
                    mode="vistas_tela",
                    furniture_name="81d7d356-0664-4b1e-8dac-a2667f073037",
                    notas_usuario=cur_note,
                    fabric_label="TELA MUESTRA",
                    fabric_filename="TELA_MUESTRA.jpg",
                    batch_ref_bytes=sw_bytes,
                    batch_views=[("81d7d356-0664-4b1e-8dac-a2667f073037.jpg", uuid_img_bytes)],
                    api_key="",
                )
            self.assertIn(f"{exp_tiles} seamless", res_vt["items"][0]["google_ai_studio"])

        # 2) fa['name'] anónimo precalculado con '(+30% V8)' nunca fuga '+30%' bajo override de luminosidad
        stale_fa = v8.analyze_fabric_v8_local(sw_bytes, sample_name="", custom_notes="")
        self.assertIn("+30%", stale_fa["name"])
        for ov_note in ("20% más oscuro", "sin aclarar", user_note):
            r_st = v8.build_34_derecha_2054_prompts(
                furniture_name="SOFA_MILAN",
                fabric_analysis=stale_fa,
                notas_usuario=ov_note,
                tipo_mueble="Seccional",
                furniture_filenames=["SOFA_MILAN.jpg"],
                fabric_filename="",
            )
            self.assertNotIn("+30%", r_st["items"][0]["google_ai_studio"])
            self.assertNotIn("+30%", r_st["items"][0]["chatgpt_dalle3"])

    def test_r3_format_image_2054_white_high_bit_depth_i16_i_and_f(self) -> None:
        # 1) I;16 16-bit PNG (16000 sobre fondo 65535 -> centro ~62, esquinas #FFFFFF)
        im16 = Image.new("I;16", (200, 200), 65535)
        ImageDraw.Draw(im16).rectangle((50, 50, 150, 150), fill=16000)
        b16 = io.BytesIO()
        im16.save(b16, format="PNG")
        out16 = v8.format_image_2054_white(b16.getvalue(), target_px=2054)
        with Image.open(io.BytesIO(out16["png"])) as p16:
            self.assertEqual(p16.size, (2054, 2054))
            self.assertEqual(p16.getpixel((0, 0)), (255, 255, 255))
            c16 = p16.getpixel((1027, 1027))
            self.assertGreaterEqual(c16[0], 55)
            self.assertLessEqual(c16[0], 70)

        # 2) I 32-bit TIFF
        im32 = Image.new("I", (200, 200), 65535)
        ImageDraw.Draw(im32).rectangle((50, 50, 150, 150), fill=16000)
        b32 = io.BytesIO()
        im32.save(b32, format="TIFF")
        out32 = v8.format_image_2054_white(b32.getvalue(), target_px=2054)
        with Image.open(io.BytesIO(out32["png"])) as p32:
            self.assertEqual(p32.size, (2054, 2054))
            self.assertEqual(p32.getpixel((0, 0)), (255, 255, 255))
            c32 = p32.getpixel((1027, 1027))
            self.assertGreaterEqual(c32[0], 55)
            self.assertLessEqual(c32[0], 70)

        # 3) F float32 [0.0..1.0] TIFF (0.25 sobre fondo 1.0 -> centro ~63, esquinas #FFFFFF)
        imf = Image.new("F", (200, 200), 1.0)
        ImageDraw.Draw(imf).rectangle((50, 50, 150, 150), fill=0.25)
        bf = io.BytesIO()
        imf.save(bf, format="TIFF")
        outf = v8.format_image_2054_white(bf.getvalue(), target_px=2054)
        with Image.open(io.BytesIO(outf["png"])) as pf:
            self.assertEqual(pf.size, (2054, 2054))
            self.assertEqual(pf.getpixel((0, 0)), (255, 255, 255))
            cf = pf.getpixel((1027, 1027))
            self.assertGreaterEqual(cf[0], 55)
            self.assertLessEqual(cf[0], 72)

    def test_r3_parser_negations_boundary_pcts_luz_and_spanish_polish(self) -> None:
        # 1) Negaciones con sustantivos/verbos intermedios nunca invierten la intención
        neg_cases = [
            "no hacer la textura más grande",
            "no hacer la textura más pequeña",
            "que no quede la tela más oscura",
            "no pongas la tela más clara",
            "no quiero la tela 40% mas clara",
            "no quiero que la tela sea 40% más clara",
            "no quiero 40% más clara la tela",
            "evitar que la textura sea más grande",
            "don't make the texture larger",
            "do not make fabric lighter",
        ]
        for s in neg_cases:
            d = parse_v8_user_fabric_directives(s)
            self.assertFalse(d.has_any_override, f"Negación violada para {s!r}: {d}")

        # 2) Porcentajes límite: 0%, >100%, negativos y decimales
        self.assertEqual(parse_v8_user_fabric_directives("0% más claro").lightness_mode, "original")
        d0_dk = parse_v8_user_fabric_directives("0% más oscuro")
        self.assertFalse(d0_dk.lightness_overridden)
        self.assertGreaterEqual(d0_dk.effective_boost, 0.0)
        self.assertFalse(parse_v8_user_fabric_directives("0% más pequeña la textura").scale_overridden)
        self.assertFalse(parse_v8_user_fabric_directives("0% más grande la textura").scale_overridden)

        self.assertEqual(parse_v8_user_fabric_directives("150% más claro").effective_boost, 0.80)
        self.assertEqual(parse_v8_user_fabric_directives("500% más claro").effective_boost, 0.80)
        self.assertEqual(parse_v8_user_fabric_directives("200% más oscuro").effective_boost, -0.45)
        self.assertEqual(parse_v8_user_fabric_directives("150% más pequeña la textura").texture_scale_factor, 0.50)
        self.assertEqual(parse_v8_user_fabric_directives("150% más grande la textura").texture_scale_factor, 1.50)

        self.assertNotEqual(parse_v8_user_fabric_directives("-30% más claro").lightness_mode, "lighter")
        self.assertNotEqual(parse_v8_user_fabric_directives("-20% más grande la textura").scale_mode, "larger")

        d_050 = parse_v8_user_fabric_directives("0.50% más claro")
        self.assertLessEqual(d_050.lightness_user_pct or 0, 1)
        d_505 = parse_v8_user_fabric_directives("50.5% más claro")
        self.assertIn(d_505.lightness_user_pct, (50, 51))

        # 3) subir/bajar la luz contextual + expresiones coloquiales + sin sombras + barra interna lino/algodón
        self.assertEqual(parse_v8_user_fabric_directives("subir la luz de la tela 40%").effective_boost, 0.50)
        self.assertEqual(parse_v8_user_fabric_directives("bajar la luz de la tela 20%").effective_boost, -0.20)
        self.assertFalse(parse_v8_user_fabric_directives("luz de estudio más clara").has_any_override)
        self.assertEqual(parse_v8_user_fabric_directives("bajar claridad del tapiz 15%").effective_boost, -0.15)
        self.assertEqual(parse_v8_user_fabric_directives("tighten the weave 25%").texture_scale_factor, 0.75)
        self.assertEqual(parse_v8_user_fabric_directives("hazla 30% mas clarita").effective_boost, 0.45)
        self.assertEqual(parse_v8_user_fabric_directives("tela mas oscurita").effective_boost, -0.15)
        self.assertEqual(parse_v8_user_fabric_directives("textura muy pequeña").texture_scale_factor, 0.70)

        d_sin = parse_v8_user_fabric_directives("tela 40% más clara sin sombras en el piso")
        self.assertEqual(d_sin.effective_boost, 0.50)
        self.assertEqual(d_sin.residual_non_fabric_notes, "sin sombras en el piso")

        d_slash = parse_v8_user_fabric_directives('Sofá "Milán" 3/4 derecha, tela 40% más clara, lino/algodón')
        self.assertEqual(d_slash.effective_boost, 0.50)
        self.assertIn("lino/algodón", d_slash.residual_non_fabric_notes)

        # 4) Guardia ReDoS (< 500 ms sobre cadenas de 10 KB)
        t0 = time.perf_counter()
        for payload in ("aclarar " + "el " * 3000 + "40%", "y " * 5000, "1" * 10000 + "%"):
            parse_v8_user_fabric_directives(payload)
        self.assertLess((time.perf_counter() - t0) * 1000.0, 500.0)

    def test_r3_width_boundaries_hd_swatch_guard_compact_roi_white_tags_webp_zip_and_multimodal(self) -> None:
        # 1) Límites de palabra, precedencia de pieza individual y rechazo de resoluciones en infer_furniture_width_cm_v8
        width_cases = [
            ("silla en la sala", 55.0),
            ("sillón para sala", 85.0),
            ("butaca de sala", 85.0),
            ("silla marsala", 55.0),
            ("silla masala", 55.0),
            ("silla camaleon", 55.0),
            ("silla de recamara", 55.0),
            ("buro de recamara", 55.0),
            ("SILLA_1920x1080.jpg", 55.0),
            ("silla 800x600", 55.0),
            ("sala", 260.0),
            ("sala en L", 285.0),
            ("sala en U", 300.0),
            ("seccional", 285.0),
            ("sofá en lino", 220.0),
        ]
        for txt, exp_w in width_cases:
            self.assertEqual(infer_furniture_width_cm_v8(None, txt), exp_w, f"Width incorrecto para {txt!r}")

        # 2) HD muestra plana preserva FLAT 2D SWATCH ONLY incluso con nombre MARSALA o SALA
        for fn in ("TELA_MARSALA", "TELA_SALA_BEIGE"):
            r_hd = v8.build_prompts(
                mode="hd",
                furniture_name=fn,
                furniture_analysis={"is_material_swatch": True, "furniture_item": "flat textile swatch"},
                tipo_mueble="muestra de tela / swatch textil plano",
                white_bg_enabled=False,
            )
            self.assertIn("FLAT 2D SWATCH ONLY", r_hd["items"][0]["google_ai_studio"])

        # 3) Etiquetas blancas en cualquier esquina de muestra compacta (0 píxeles de traslape) + terciopelo oscuro limpio
        if self.download_swatch_bytes is not None:
            im_dl = Image.open(io.BytesIO(self.download_swatch_bytes)).convert("RGB")
            for tag_box in (
                (0, 0, 50, 41),
                (178, 0, 228, 41),
                (0, 187, 50, 228),
                (178, 187, 228, 228),
                (184, 192, 228, 228),
                (184, 190, 204, 204),
            ):
                im_t = im_dl.copy()
                ImageDraw.Draw(im_t).rectangle(tag_box, fill=(255, 255, 255))
                roi_t = extract_clean_swatch_roi_v8(_encode_png(im_t))
                ix0, iy0 = max(roi_t.bbox[0], tag_box[0]), max(roi_t.bbox[1], tag_box[1])
                ix1, iy1 = min(roi_t.bbox[2], tag_box[2]), min(roi_t.bbox[3], tag_box[3])
                self.assertEqual(max(0, ix1 - ix0) * max(0, iy1 - iy0), 0, f"Traslape en {tag_box}: {roi_t.bbox}")

        im_dk = Image.new("RGB", (228, 228), (32, 30, 34))
        px_dk = im_dk.load()
        for yy in range(228):
            for xx in range(228):
                dlt = 4 if ((xx // 3 + yy // 3) % 2 == 0) else -3
                px_dk[xx, yy] = (32 + dlt, 30 + dlt, 34 + dlt)
        roi_dk = extract_clean_swatch_roi_v8(_encode_png(im_dk))
        self.assertEqual(roi_dk.crop.size, (182, 182))

        # 4) Normalización de extensión .webp -> .jpg en insumos ZIP y sanitización de nombre de descarga
        im_wp = Image.new("RGB", (300, 300), (140, 120, 100))
        b_wp = io.BytesIO()
        im_wp.save(b_wp, format="WEBP")
        fn_zip, raw_zip = ps_v8_mod._prepare_v8_zip_ref_entry(
            {"filename": "sofa_camara.webp", "bytes": b_wp.getvalue(), "role": "primary_furniture"}
        )
        self.assertEqual(fn_zip, "sofa_camara.jpg")
        self.assertTrue(raw_zip.startswith(b"\xff\xd8\xff"))
        safe_dl = ps_v8_mod._sanitize_zip_component_v8('SOFA / SECCIONAL: *?"<>| MILAN', "mueble")
        self.assertFalse(any(ch in safe_dl for ch in '/\\:*?"<>|'))

        # 5) Multimodal Furn+Fab+Wood envía len(contents)==4 y generate_image_34_derecha_2054 propaga custom_notes
        clean_im = Image.new("RGB", (512, 512), (255, 255, 255))
        ImageDraw.Draw(clean_im).rectangle((160, 160, 352, 352), fill=(215, 210, 200))
        clean_b64 = base64.b64encode(_encode_png(clean_im)).decode("ascii")
        recorded_calls: list = []

        class _FakeResp:
            def __init__(self) -> None:
                part = types.SimpleNamespace(inline_data=types.SimpleNamespace(data=clean_b64))
                self.candidates = [types.SimpleNamespace(content=types.SimpleNamespace(parts=[part]))]

        class _FakeModels:
            def generate_content(self, model, contents, config=None):
                recorded_calls.append((model, len(contents), contents))
                return _FakeResp()

        class _FakeClient:
            models = _FakeModels()

        had_google = "google" in sys.modules
        had_genai = "google.genai" in sys.modules
        if not had_genai:
            g_pkg = sys.modules.get("google") or types.ModuleType("google")
            genai_pkg = types.ModuleType("google.genai")
            types_mod = types.ModuleType("google.genai.types")
            types_mod.GenerateContentConfig = lambda **kw: kw
            genai_pkg.types = types_mod
            g_pkg.genai = genai_pkg
            sys.modules["google"] = g_pkg
            sys.modules["google.genai"] = genai_pkg
            sys.modules["google.genai.types"] = types_mod

        svc = AIPromptServiceV8()
        svc.get_client = lambda k=None: _FakeClient()  # type: ignore[method-assign]
        captured_canvas_kw: dict = {}
        orig_build_canvas = svc_v8_mod.build_v8_conditioning_canvas

        def _spy_build_canvas(*a, **kw):
            captured_canvas_kw.update(kw)
            return orig_build_canvas(*a, **kw)

        try:
            with patch.object(svc_v8_mod, "build_v8_conditioning_canvas", side_effect=_spy_build_canvas):
                out_dual, err_dual = svc.generate_catalog_photo(
                    prompt_text="Test dual",
                    primary_bytes=self.studio_sofa_bytes,
                    fabric_bytes=self.real_swatch_bytes,
                    wood_bytes=self.studio_sofa_bytes,
                    api_key="FAKE_TEST_KEY_V8_R3",
                )
                self.assertIsNone(err_dual)
                self.assertIsNotNone(out_dual)
                self.assertEqual(recorded_calls[-1][1], 4)

                out_34 = svc.generate_image_34_derecha_2054(
                    prompt_text="Test 34 custom notes",
                    furniture_bytes=self.studio_sofa_bytes,
                    fabric_bytes=self.real_swatch_bytes,
                    furniture_type="SECCIONAL",
                    custom_notes="quiero 40% más claro el tono de la tela y 20% más pequeña la textura",
                    api_key="FAKE_TEST_KEY_V8_R3",
                )
                self.assertIsNotNone(out_34)
                self.assertEqual(captured_canvas_kw.get("boost"), 0.50)
                self.assertEqual(captured_canvas_kw.get("texture_scale_factor"), 0.80)
        finally:
            if not had_genai:
                sys.modules.pop("google.genai.types", None)
                sys.modules.pop("google.genai", None)
                if not had_google:
                    sys.modules.pop("google", None)

    def test_r4_overflow_multiview_negation_i16b_and_merge_regressions(self) -> None:
        # 1) R2-BUG-1: Porcentajes >= 309 dígitos no lanzan OverflowError y acotan limpiamente
        self.assertEqual(parse_v8_user_fabric_directives("9" * 309 + "% más claro").effective_boost, 0.80)
        self.assertEqual(parse_v8_user_fabric_directives("9" * 309 + "% más oscuro").effective_boost, -0.45)
        self.assertEqual(parse_v8_user_fabric_directives("9" * 309 + "% más pequeña la textura").texture_scale_factor, 0.50)
        self.assertEqual(parse_v8_user_fabric_directives("9" * 309 + "% más grande la textura").texture_scale_factor, 1.50)
        self.assertEqual(parse_v8_user_fabric_directives("1" * 10000 + "% más claro").effective_boost, 0.80)
        self.assertFalse(parse_v8_user_fabric_directives("-" + "9" * 309 + "% más claro").has_any_override)

        # 2) R2-BUG-2: vistas_tela multi-vista con aspectos mixtos [wide, narrow] y [narrow, wide]
        im_wide = Image.new("RGB", (600, 600), (255, 255, 255))
        ImageDraw.Draw(im_wide).rectangle((30, 210, 570, 410), fill=(115, 100, 88))
        wide_b = _encode_png(im_wide)

        im_narrow = Image.new("RGB", (600, 600), (255, 255, 255))
        ImageDraw.Draw(im_narrow).rectangle((200, 120, 400, 480), fill=(115, 100, 88))
        narrow_b = _encode_png(im_narrow)

        sw_b = self.real_swatch_bytes
        note_ov = "quiero que hagas un 40%mas claro el tono de la tela y 20% mas pequeños la textura"
        for cur_note, exp_tiles in ((note_ov, 1024), ("", 625)):
            for views in (
                [("11111111-aaaa-4bbb-8ccc-000000000001.jpg", wide_b), ("22222222-aaaa-4bbb-8ccc-000000000002.jpg", narrow_b)],
                [("22222222-aaaa-4bbb-8ccc-000000000002.jpg", narrow_b), ("11111111-aaaa-4bbb-8ccc-000000000001.jpg", wide_b)],
            ):
                pack = v8.build_v8_reference_pack(
                    mode="vistas_tela",
                    furniture_name="11111111-aaaa-4bbb-8ccc-000000000001",
                    fabric_label="TELA MUESTRA",
                    fabric_filename="TELA_MUESTRA.jpg",
                    fabric_bytes=sw_b,
                    batch_views=views,
                    custom_notes=cur_note,
                )
                canv_tiles = [p["total_tiles"] for p in pack if p.get("role") == "v8_scale_canvas"]
                self.assertEqual(canv_tiles, [exp_tiles, exp_tiles])
                for pre_pack in (None, pack):
                    with _offline_ai_clients(v8):
                        res_vt = v8.build_prompts(
                            mode="vistas_tela",
                            furniture_name="11111111-aaaa-4bbb-8ccc-000000000001",
                            notas_usuario=cur_note,
                            fabric_label="TELA MUESTRA",
                            fabric_filename="TELA_MUESTRA.jpg",
                            batch_ref_bytes=sw_b,
                            batch_views=views,
                            precomputed_pack=pre_pack,
                            api_key="",
                        )
                    self.assertEqual(len(res_vt["items"]), 2)
                    for idx_v, it_v in enumerate(res_vt["items"]):
                        self.assertIn(f"{canv_tiles[idx_v]} seamless", it_v["google_ai_studio"])

        # 3) R2-BUG-3 + negación de gerundio / 'menos clara' preservando 'no tan clara'
        for neg_s in (
            "no quiero que el tono de la tela sea 40% más claro",
            "no quiero que el color de la tela quede más oscuro",
            "no hacerla menos clara",
            "no quiero que la tela quede menos clara",
            "evitar que la tela quede menos clara",
            "avoid making the weave 20% coarser",
        ):
            d_neg = parse_v8_user_fabric_directives(neg_s)
            self.assertFalse(d_neg.has_any_override, f"Negación no bloqueada para {neg_s!r}: {d_neg}")
        d_soft = parse_v8_user_fabric_directives("no tan clara la tela")
        self.assertTrue(d_soft.lightness_overridden)
        self.assertEqual(d_soft.lightness_mode, "softer_light")
        self.assertEqual(d_soft.effective_boost, 0.10)

        # 4) TIFF Motorola Big-Endian I;16B se formatea limpiamente en format_image_2054_white
        tw, th = 64, 64
        vals_be = [65535] * (tw * th)
        for yy in range(16, 48):
            for xx in range(16, 48):
                vals_be[yy * tw + xx] = 16000
        pix_be = struct.pack(f">{tw * th}H", *vals_be)
        ifd_off = 8
        entries = [
            (256, 4, 1, tw),
            (257, 4, 1, th),
            (258, 3, 1, 16 << 16),
            (259, 3, 1, 1 << 16),
            (262, 3, 1, 1 << 16),
            (273, 4, 1, 0),
            (277, 3, 1, 1 << 16),
            (278, 4, 1, th),
            (279, 4, 1, len(pix_be)),
        ]
        entries[5] = (273, 4, 1, ifd_off + 2 + 12 * len(entries) + 4)
        tiff_be = (
            b"MM"
            + struct.pack(">HI", 42, ifd_off)
            + struct.pack(">H", len(entries))
            + b"".join(struct.pack(">HHII", *e) for e in entries)
            + struct.pack(">I", 0)
            + pix_be
        )
        with Image.open(io.BytesIO(tiff_be)) as chk_be:
            self.assertEqual(chk_be.mode, "I;16B")
        out_be = v8.format_image_2054_white(tiff_be, target_px=2054)
        with Image.open(io.BytesIO(out_be["png"])) as p_be:
            self.assertEqual(p_be.size, (2054, 2054))
            self.assertEqual(p_be.getpixel((0, 0)), (255, 255, 255))
            c_be = p_be.getpixel((1027, 1027))
            self.assertGreaterEqual(c_be[0], 55)
            self.assertLessEqual(c_be[0], 70)

        # 5) _merge_telas_lists ignora defensivamente elementos que no sean dict
        merged_safe = ps_v8_mod._merge_telas_lists([None, "invalid", 123, {"id": "t1", "name": "Lino"}])  # type: ignore[list-item]
        self.assertEqual(merged_safe, [{"id": "t1", "name": "Lino"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)

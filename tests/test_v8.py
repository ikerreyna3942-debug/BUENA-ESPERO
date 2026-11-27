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
import inspect
import io
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import types
import unittest
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Stub ligero de streamlit cuando el intérprete no lo tiene instalado (igual que test_v7.py)
try:
    import streamlit as _st_real  # noqa: F401
except ImportError:
    class _StubSessionState(dict):
        def __getattr__(self, name: str):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name: str, value) -> None:
            self[name] = value

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

import streamlit as st  # noqa: E402
import streamlit.components.v1 as st_components  # noqa: E402
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
    make_toroidal_seamless_tile_v8,
    make_v8_canvas_filename,
    make_v8_swatch_filename,
    resolve_v8_furniture_type_hint,
)
from services.ai_prompt_service_v8 import (  # noqa: E402
    ALL_SINGLE_VIEWS,
    DEFAULT_V8_IMAGE_MODELS,
    MODES,
    VIEW_IDS,
    AIPromptServiceV8,
    ai_prompt_service_v8 as v8,
)
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
    _resolve_furniture_drive_id,
    build_ordered_photo_thumbs_v8,
    render_v8_photos_strip_76,
)

REAL_SWATCH_PATH = Path("/home/antigravity/DISTRACTION_NATURAL.jpg")


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
        assert REAL_SWATCH_PATH.exists(), f"No existe muestra real en {REAL_SWATCH_PATH}"
        cls.real_swatch_bytes = REAL_SWATCH_PATH.read_bytes()
        cls.studio_sofa_bytes = _make_studio_white_sofa_bytes()
        cls.rgba_chair_bytes = _make_rgba_armchair_bytes()
        cls.room_sofa_bytes = _make_room_bg_furniture_bytes()

    def test_zero_hardcoded_filenames_or_coordinates_in_v8_sources(self) -> None:
        v8_files = [
            REPO_ROOT / "services" / "fabric_composer_v8.py",
            REPO_ROOT / "services" / "ai_prompt_service_v8.py",
            REPO_ROOT / "modules" / "prompt_studio_v8.py",
        ]
        for path in v8_files:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            self.assertNotIn("DISTRACTION_NATURAL", src, f"Nombre hardcodeado en {path.name}")
            str_consts = [
                n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
            for s in str_consts:
                self.assertNotIn("distraction_natural", s.lower())

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
            self.assertTrue(9 <= g <= 17, f"grid_n fuera de 9..17: {g}")
            self.assertTrue(81 <= g * g <= 289)

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
        self.assertTrue(81 <= art_white.total_tiles <= 289)
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
        cls.real_swatch_bytes = REAL_SWATCH_PATH.read_bytes()
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

        # Vista 1 (sin ancla): Image 1 Mueble, Image 2 Lienzo Escala V8, Image 3 Tela +30% V8, Image 4 Madera
        v1 = res_cat["items"][0]
        self.assertEqual(len(v1["attachment_guide"]), 4)
        self.assertIn("SOFA_CORVINO.jpg", v1["attachment_guide"][0])
        self.assertIn("SOFA_CORVINO_V8_LIENZO_ESCALA.png", v1["attachment_guide"][1])
        self.assertIn("TELA_NATURAL_V8_LUZ30.png", v1["attachment_guide"][2])
        self.assertIn("PAROTA_NATURAL.jpg", v1["attachment_guide"][3])
        self.assertIn('Image 2 ("SOFA_CORVINO_V8_LIENZO_ESCALA.png")', v1["google_ai_studio"])
        self.assertIn('Image 3 ("TELA_NATURAL_V8_LUZ30.png")', v1["google_ai_studio"])
        self.assertIn("EL CASCO COMPLETO", v1["google_ai_studio"])
        self.assertIn("NEVER keep tiled fabric background", v1["google_ai_studio"])
        self.assertIn("#FFFFFF", v1["google_ai_studio"])
        self.assertIn("0% ground shadow", v1["google_ai_studio"])
        self.assertIn("2054 x 2054", v1["google_ai_studio"])

        # Vista 2 (con ancla Vista 1 en Image 5!)
        v2 = res_cat["items"][1]
        self.assertIn("Image 5 (APPROVED VISTA 1 ANCHOR", v2["google_ai_studio"])
        self.assertEqual(len(v2["attachment_guide"]), 5)

        # Vista 6 (Plano CAD): solo Image 1, sin mosaico de tela
        v6_bp = res_cat["items"][5]
        self.assertEqual(len(v6_bp["attachment_guide"]), 1)
        self.assertNotIn("V8_LIENZO_ESCALA", v6_bp["google_ai_studio"])
        self.assertIn("Ancho: 220 cm", v6_bp["google_ai_studio"])

        # Vista 7 (Entorno): habitación natural prohibiendo mosaico en paredes
        v7_env = res_cat["items"][6]
        self.assertIn("NEVER render tiled fabric wallpaper on room walls", v7_env["google_ai_studio"])
        self.assertIn("Image 5 (APPROVED VISTA 1 ANCHOR", v7_env["google_ai_studio"])

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
        self.assertIn("frente_V8_LIENZO_ESCALA.png", r_vt["items"][0]["google_ai_studio"])
        self.assertIn("perfil_V8_LIENZO_ESCALA.png", r_vt["items"][1]["google_ai_studio"])
        self.assertIn("TELA_NATURAL_V8_LUZ30.png", r_vt["items"][0]["google_ai_studio"])

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

        self.assertIsNone(err)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(len(calls), 2, "Debió reintentar al detectar borde contaminado <95% blanco")
        self.assertEqual(len(calls[0][1]), 4)  # [prompt, orig_furn, v8_canvas, cal_swatch]
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
                    self.assertEqual(
                        res_m["items"][0]["attachment_guide"],
                        [p["guide_line"] for p in pack_m],
                        f"Desajuste de guía en material/{mm}/{cname}/ref={has_ref}",
                    )
                    ais_m = res_m["items"][0]["google_ai_studio"]
                    cited_m = sorted({int(m) for m in re.findall(r"\bImage\s+(\d+)\b", ais_m)})
                    self.assertEqual(cited_m, [p["slot_index"] for p in pack_m])
                    if not (fb and mm in ("fabric_only", "dual")):
                        self.assertNotIn("V8_LIENZO_ESCALA", ais_m)
                        self.assertNotIn("V8_LUZ30", ais_m)
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
                    self.assertEqual(res_std["items"][0]["attachment_guide"], [p["guide_line"] for p in pack_std])
                    ais_std = res_std["items"][0]["google_ai_studio"]
                    cited_std = sorted({int(m) for m in re.findall(r"\bImage\s+(\d+)\b", ais_std)})
                    self.assertEqual(cited_std, [p["slot_index"] for p in pack_std])
                    if not fb or md == "plano":
                        self.assertNotIn("V8_LIENZO_ESCALA", ais_std)
                        self.assertNotIn("V8_LUZ30", ais_std)

            # vistas_tela (incluyendo fabric_bytes=None sin tela!)
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
            self.assertEqual(res_vt["items"][0]["attachment_guide"], [p["guide_line"] for p in pack_vt])
            ais_vt = res_vt["items"][0]["google_ai_studio"]
            cited_vt = sorted({int(m) for m in re.findall(r"\bImage\s+(\d+)\b", ais_vt)})
            self.assertEqual(cited_vt, [p["slot_index"] for p in pack_vt])
            if not fb:
                self.assertNotIn("V8_LIENZO_ESCALA", ais_vt)
                self.assertNotIn("V8_LUZ30", ais_vt)

        # clonar_color (white_bg_enabled=True) exige #FFFFFF, RGB 255,255,255, 0% sombras y 2054 x 2054 px
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

        # Techo <= 243 post-Lanczos en vistas previas independientes de muestra de tela
        pack_sw_only = v8.build_v8_reference_pack(
            mode="catalogo",
            fabric_label="TELA",
            fabric_filename="TELA.jpg",
            fabric_bytes=self.real_swatch_bytes,
        )
        sw_only_bytes = next(p["bytes"] for p in pack_sw_only if p["role"] == "v8_calibrated_swatch")
        with Image.open(io.BytesIO(sw_only_bytes)) as sw_im1:
            self.assertLessEqual(max(e[1] for e in sw_im1.getextrema()), 243)

        pack_vt_sw = v8.build_v8_reference_pack(
            mode="vistas_tela",
            fabric_label="TELA",
            fabric_filename="TELA.jpg",
            fabric_bytes=self.real_swatch_bytes,
            target_view=("v1.jpg", self.studio_sofa_bytes),
        )
        sw_vt_bytes = next(p["bytes"] for p in pack_vt_sw if p["role"] == "v8_calibrated_swatch")
        with Image.open(io.BytesIO(sw_vt_bytes)) as sw_im2:
            self.assertLessEqual(max(e[1] for e in sw_im2.getextrema()), 243)


class TestV8StudioUIAndZeroRegression(unittest.TestCase):
    """7. Verificación de UI V8, reglas GEMINI.md 1–4, enrutamiento main.py y cero regresión git."""

    def test_main_py_v8_version_options_normalization_and_routing(self) -> None:
        main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('["🤖 V8", "V7", "V6", "V5", "V4", "V3", "V2", "V1"]', main_src)
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
                fabric_bytes=REAL_SWATCH_PATH.read_bytes(),
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
            ["SOFA_CORVINO.jpg", make_v8_canvas_filename("SOFA_CORVINO.jpg"), make_v8_swatch_filename("TELA_NATURAL.jpg")],
        )
        self.assertEqual(len(captured), 1)
        strip_html = captured[0][0]
        self.assertIn("width: 76px;", strip_html)
        self.assertIn("height: 76px;", strip_html)
        self.assertIn("transform: scale(", strip_html)
        self.assertEqual(strip_html.count("🖼️ Copiar foto"), 3)
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
        orig_rerun = st.rerun
        try:
            st.rerun = lambda *a, **kw: None
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
        finally:
            st.rerun = orig_rerun

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

        # Verificar ZIP con insumos V8 (<mueble>_V8_LIENZO_ESCALA.png y <tela>_V8_LUZ30.png)
        art = build_v8_conditioning_canvas(
            furniture_bytes=_make_studio_white_sofa_bytes(),
            fabric_bytes=REAL_SWATCH_PATH.read_bytes(),
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
            (art.calibrated_swatch_filename, art.calibrated_swatch_png),
        ]
        z_bytes = _build_zip_v8(r34, include_images=True)
        with zipfile.ZipFile(io.BytesIO(z_bytes), "r") as zf:
            names = set(zf.namelist())
        self.assertIn("prompts/SOFA_ZIP.txt", names)
        self.assertIn("insumos/SOFA_ZIP.jpg", names)
        self.assertIn("insumos/SOFA_ZIP_V8_LIENZO_ESCALA.png", names)
        self.assertIn("insumos/TELA_NATURAL_V8_LUZ30.png", names)

    def test_vista_suelta_plano_tecnico_strip_and_zip_1_slot_and_blank_sku_tile_parity(self) -> None:
        sofa_bytes = _make_studio_white_sofa_bytes()
        swatch_bytes = REAL_SWATCH_PATH.read_bytes()

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
            self.assertEqual(canvas_entry["total_tiles"], 289)
            self.assertEqual(canvas_legacy["total_tiles"], 289)
            self.assertEqual(res_blank["dims"]["category"], "seating")
            self.assertEqual(res_34_blank["dims"]["category"], "seating")
            self.assertIn("289 seamless reduced", res_blank["items"][0]["google_ai_studio"])
            self.assertIn("289 seamless reduced", res_34_blank["items"][0]["google_ai_studio"])
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
            "modules/prompt_studio_v8.py",
            "services/ai_prompt_service_v8.py",
            "services/fabric_composer_v8.py",
            "tests/test_v8.py",
        }
        forbidden = [f for f in modified_tracked if f not in allowed]
        self.assertEqual(
            forbidden,
            [],
            f"Archivos versionados de V1–V7 modificados indebidamente: {forbidden}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

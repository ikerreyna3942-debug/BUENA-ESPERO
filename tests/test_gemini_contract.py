"""Contract test suite enforcing GEMINI.md Rules 1–4 and version retention (V1/V6/V7/V8 kept, V2–V5 removed).

Mapped 1-to-1 to GEMINI.md:
  - Rule 1: Clean 1-line UI, collapsed sidebar, selectbox (0 st.radio), 3 direct buttons,
            no synthetic FLUX UI button, photo previews (V8 76px hover zoom, V7 120px PNG copy),
            zero credential widgets in UI modules.
  - Rule 2: Parameterized Borrar/Limpiar matrix across all 9 modes and all sub-options
            for BOTH _clear_v7_form and _clear_v8_form.
  - Rule 3: Full casco upholstery (backrest/armrests/base/sides + cushions), micro-scale
            calibration, 0% hue drift, wood/metal leg protection across fabric-capable modes
            in BOTH V7 & V8; Master 3/4 Right clauses + exact 2054x2054 #FFFFFF output.
  - Rule 4 & Version Retention: Drive folder IDs (RENDER, SUBIR, Cotización), ThreadPoolExecutor,
            BFS batch Drive scan, active VISION_MODELS, <=640px responsive CSS, zero hardcoded
            secrets in V8 + observability + .github/, and V1/V6/V7/V8 retained vs V2–V5 removed.
"""

from __future__ import annotations

import ast
import base64
import contextlib
import importlib
import inspect
import io
import json
import re
import sys
import types
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

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


# Lightweight streamlit stub when running in minimal Python environments without streamlit
try:
    import streamlit as _st_real  # noqa: F401
except ImportError:
    def _stub_cache_decorator(*args, **kwargs):
        def _dec(fn):
            fn.clear = lambda: None
            return fn

        return _dec(args[0]) if args and callable(args[0]) else _dec

    _st_stub = types.ModuleType("streamlit")
    _st_stub.session_state = _StubSessionState()
    _st_stub.rerun = lambda *a, **kw: None
    _st_stub.markdown = lambda *a, **kw: None
    _st_stub.caption = lambda *a, **kw: None
    _st_stub.info = lambda *a, **kw: None
    _st_stub.warning = lambda *a, **kw: None
    _st_stub.error = lambda *a, **kw: None
    _st_stub.success = lambda *a, **kw: None
    _st_stub.toast = lambda *a, **kw: None
    _st_stub.cache_data = _stub_cache_decorator
    _st_stub.cache_resource = _stub_cache_decorator
    _st_stub.secrets = {}
    _st_stub.set_page_config = lambda *a, **kw: None
    _st_comp = types.ModuleType("streamlit.components")
    _st_comp_v1 = types.ModuleType("streamlit.components.v1")
    _st_comp_v1.html = lambda *a, **kw: None
    _st_comp_v1.iframe = lambda *a, **kw: None
    _st_comp.v1 = _st_comp_v1
    _st_stub.components = _st_comp
    sys.modules["streamlit"] = _st_stub
    sys.modules["streamlit.components"] = _st_comp
    sys.modules["streamlit.components.v1"] = _st_comp_v1

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


from modules.prompt_studio_v7 import (  # noqa: E402
    FOLDER_MUEBLES_RENDER_DRIVE_ID as V7_RENDER_ID,
    _FURNITURE_FOLDER_SPECS as V7_FOLDER_SPECS,
    _clear_v7_form,
)
from modules.prompt_studio_v8 import (  # noqa: E402
    FOLDER_MUEBLES_RENDER_DRIVE_ID as V8_RENDER_ID,
    FOLDER_MUEBLES_SUBIR_DRIVE_ID as V8_SUBIR_ID,
    _FURNITURE_FOLDER_SPECS as V8_FOLDER_SPECS,
    _clear_v8_form,
    render_v8_photos_strip_76,
)
from modules.ui_helpers import render_loaded_photos_strip  # noqa: E402
from services import gemini_runtime, sheets_service  # noqa: E402
from services.ai_prompt_service_v7 import MODES as V7_MODES, ai_prompt_service_v7 as v7  # noqa: E402
from services.ai_prompt_service_v8 import MODES as V8_MODES, ai_prompt_service_v8 as v8  # noqa: E402


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


def _make_sample_furniture_png() -> bytes:
    im = Image.new("RGB", (600, 480), (252, 252, 252))
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle((120, 120, 480, 360), radius=24, fill=(140, 124, 108))
    dr.rectangle((160, 360, 185, 420), fill=(80, 52, 32))
    dr.rectangle((415, 360, 440, 420), fill=(80, 52, 32))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _make_sample_fabric_png() -> bytes:
    im = Image.new("RGB", (256, 256), (186, 180, 172))
    dr = ImageDraw.Draw(im)
    for y in range(0, 256, 16):
        for x in range(0, 256, 16):
            c = (210, 204, 196) if ((x // 16 + y // 16) % 2 == 0) else (154, 148, 140)
            dr.rectangle((x, y, x + 10, y + 10), fill=c)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestRule1CleanSingleLineUI(unittest.TestCase):
    """GEMINI.md Rule 1: 1-line clean UI, collapsed sidebar, selectbox, 3 direct buttons, previews, no credentials."""

    def test_main_py_collapsed_sidebar_hidden_header_and_single_line_topbar(self) -> None:
        src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('initial_sidebar_state="collapsed"', src)
        self.assertIn('section[data-testid="stSidebar"]', src)
        self.assertIn('header[data-testid="stHeader"]', src)
        self.assertIn("display: none !important;", src)
        self.assertIn("st.columns([1.15, 0.72, 3.13]", src)
        self.assertIn("st.selectbox(", src)
        self.assertIn('["🤖 V8", "V7", "V6", "V1"]', src)
        # Defensive stale session fallback to V8
        self.assertIn('st.session_state["sidebar_version"] = "🤖 V8"', src)

    def test_v7_and_v8_use_selectbox_inline_header_no_radio_and_no_duplicate_dims(self) -> None:
        for rel in ("modules/prompt_studio_v7.py", "modules/prompt_studio_v8.py"):
            src = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("st.radio(", src, f"st.radio forbidden by GEMINI.md Rule 1 in {rel}")
            self.assertIn("inline_header=True", src, f"inline_header=True missing in {rel}")
            self.assertIn("st.selectbox(", src, f"st.selectbox missing in {rel}")
            # Dimensions come solely from sku_banner (no duplicate dimension input widget in studio file)
            self.assertNotIn('st.text_input("Medidas"', src, f"Duplicate dimension box in {rel}")
            self.assertNotIn('st.text_input("Dimensiones"', src, f"Duplicate dimension box in {rel}")

    def test_v7_and_v8_expose_3_direct_primary_buttons_and_no_synthetic_flux_ui_button(self) -> None:
        for rel, prefix in (("modules/prompt_studio_v7.py", "v7"), ("modules/prompt_studio_v8.py", "v8")):
            src = (REPO_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("f\"🚀 {mode_label}\"", src, f"Primary generate button missing in {rel}")
            self.assertIn('"↘️ 3/4 Derecha"', src, f"3/4 Derecha button missing in {rel}")
            self.assertIn('"🗑️ Borrar"', src, f"Borrar button missing in {rel}")
            self.assertIn(f'key=f"{prefix}_btn_go_{{ck}}"', src)
            self.assertIn(f'key=f"{prefix}_btn_34_{{ck}}"', src)
            self.assertIn(f'key="{prefix}_btn_clear"', src)
            self.assertNotIn("Generar foto sintética", src, f"Synthetic FLUX UI button forbidden in {rel}")
            self.assertNotIn("flux-studio-fallback", src, f"FLUX UI fallback button forbidden in {rel}")

        # V8 defaults allow_flux_fallback=False on both image entrypoints
        sig_cat = inspect.signature(v8.generate_catalog_photo)
        sig_34 = inspect.signature(v8.generate_image_34_derecha_2054)
        self.assertIs(sig_cat.parameters["allow_flux_fallback"].default, False)
        self.assertIs(sig_34.parameters["allow_flux_fallback"].default, False)

    def test_v8_76px_hover_zoom_preview_and_v7_preview_strip_contract(self) -> None:
        sample = _make_sample_furniture_png()
        captured: list[str] = []
        orig_html = st_components.html
        try:
            st_components.html = lambda doc, **kw: captured.append(doc)
            render_v8_photos_strip_76([("SOFA_TEST.png", sample, "Image 1")], key_prefix="contract_v8")
            render_loaded_photos_strip([("SOFA_TEST.png", sample, "Image 1")], key_prefix="contract_v7")
        finally:
            st_components.html = orig_html

        self.assertEqual(len(captured), 2)
        v8_html, v7_html = captured[0], captured[1]
        # V8: 76px x 76px with hover zoom + PNG copy
        self.assertIn("width: 76px;", v8_html)
        self.assertIn("height: 76px;", v8_html)
        self.assertIn("transform: scale(", v8_html)
        self.assertIn("🖼️ Copiar foto", v8_html)
        self.assertNotIn("writeText", v8_html)
        # V7: respects test_v7.py 120px strip + PNG copy (no writeText)
        self.assertIn("width: 120px;", v7_html)
        self.assertIn("height: 120px;", v7_html)
        self.assertIn("🖼️ Copiar foto", v7_html)
        self.assertNotIn("writeText", v7_html)

    def test_zero_credential_widgets_in_ui_modules(self) -> None:
        ui_files = (
            "main.py",
            "modules/prompt_studio_v7.py",
            "modules/prompt_studio_v8.py",
            "modules/alta_fotos_hub.py",
        )
        for rel in ui_files:
            src = (REPO_ROOT / rel).read_text(encoding="utf-8")
            tree = ast.parse(src, filename=rel)
            for forbidden in ("api_key_input", "Service Account", "secrets.toml"):
                self.assertNotIn(forbidden, src, f"Forbidden credential reference {forbidden!r} in {rel}")
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "text_input":
                        for kw in node.keywords:
                            if kw.arg == "type" and isinstance(kw.value, ast.Constant) and kw.value.value == "password":
                                self.fail(f"Password input widget forbidden in {rel}")
                    if node.func.attr in ("text_input", "text_area", "file_uploader"):
                        call_src = ast.unparse(node).lower()
                        for bad in ("api_key", "oauth", "credentials", "token", "secret"):
                            self.assertNotIn(bad, call_src, f"Credential widget ({bad}) forbidden in {rel}")


class TestRule2ClearButtonPreservesModeAndSubOptions(unittest.TestCase):
    """GEMINI.md Rule 2: Parameterized Borrar matrix across ALL 9 modes & sub-options for V7 & V8."""

    def test_clear_v7_and_v8_preserve_all_modes_and_suboptions(self) -> None:
        all_modes = [
            "catalogo",
            "vista_suelta",
            "material",
            "entorno",
            "plano",
            "extraer",
            "hd",
            "vistas_tela",
            "clonar_color",
        ]
        self.assertEqual(set(V7_MODES.keys()), set(all_modes))
        self.assertEqual(set(V8_MODES.keys()), set(all_modes))

        with _isolated_streamlit_session(st):
            for idx, mode_key in enumerate(all_modes):
                # --- V7 ---
                st.session_state.clear()
                v7_mode_label = V7_MODES[mode_key]
                st.session_state.update({
                    "v7_keep_mode": v7_mode_label,
                    "v7_keep_vista": "3/4 Derecha",
                    "v7_keep_matmode": "Tela + madera",
                    "v7_keep_room": "Sala",
                    "v7_keep_folder": "📁 RENDER",
                    "sku_input_v7": f"SKU-V7-{idx}",
                    "field_tipo_v7": "SOFA",
                    "field_medidas_v7": "220x95x82",
                    "v7_notas_1": "Nota temporal V7",
                    "v7_picked_mueble_1": {"name": "MUEBLE.jpg"},
                    "v7_result": {"items": [{"x": 1}]},
                    "v7_last_photo_stem": "MUEBLE",
                    "v7_last_sku": f"SKU-V7-{idx}",
                    "clear_key_v7": 1,
                })
                _clear_v7_form(1)
                self.assertEqual(st.session_state.get("v7_keep_mode"), v7_mode_label, f"V7 reset mode on {mode_key}")
                self.assertEqual(st.session_state.get("v7_keep_vista"), "3/4 Derecha")
                self.assertEqual(st.session_state.get("v7_keep_matmode"), "Tela + madera")
                self.assertEqual(st.session_state.get("v7_keep_room"), "Sala")
                self.assertEqual(st.session_state.get("v7_keep_folder"), "📁 RENDER")
                self.assertEqual(st.session_state.get("clear_key_v7"), 2)
                for cleared in ("sku_input_v7", "field_tipo_v7", "field_medidas_v7", "v7_notas_1", "v7_picked_mueble_1", "v7_result", "v7_last_photo_stem", "v7_last_sku"):
                    self.assertNotIn(cleared, st.session_state, f"V7 failed to clear {cleared} on {mode_key}")

                # --- V8 ---
                st.session_state.clear()
                v8_mode_label = V8_MODES[mode_key]
                st.session_state.update({
                    "v8_keep_mode": v8_mode_label,
                    "v8_keep_vista": "3/4 Derecha",
                    "v8_keep_matmode": "Tela + madera",
                    "v8_keep_room": "Sala",
                    "v8_keep_folder": "📤 SUBIR",
                    "sku_input_v8": f"SKU-V8-{idx}",
                    "field_tipo_v8": "SOFA",
                    "field_medidas_v8": "220x95x82",
                    "sku_loaded_data_v8": {"tipo_mueble": "SOFA"},
                    "sku_last_searched_v8": f"SKU-V8-{idx}",
                    "v8_notas_1": "Nota temporal V8",
                    "v8_picked_mueble_1": {"name": "MUEBLE.jpg"},
                    "v8_result": {"items": [{"x": 1}]},
                    "v8_last_photo_stem": "MUEBLE",
                    "clear_key_v8": 1,
                })
                _clear_v8_form(1)
                self.assertEqual(st.session_state.get("v8_keep_mode"), v8_mode_label, f"V8 reset mode on {mode_key}")
                self.assertEqual(st.session_state.get("v8_keep_vista"), "3/4 Derecha")
                self.assertEqual(st.session_state.get("v8_keep_matmode"), "Tela + madera")
                self.assertEqual(st.session_state.get("v8_keep_room"), "Sala")
                self.assertEqual(st.session_state.get("v8_keep_folder"), "📤 SUBIR")
                self.assertEqual(st.session_state.get("clear_key_v8"), 2)
                for cleared in ("sku_input_v8", "field_tipo_v8", "field_medidas_v8", "sku_loaded_data_v8", "sku_last_searched_v8", "v8_notas_1", "v8_picked_mueble_1", "v8_result", "v8_last_photo_stem"):
                    self.assertNotIn(cleared, st.session_state, f"V8 failed to clear {cleared} on {mode_key}")


class TestRule3UpholsteryAndMaster34RightStandard(unittest.TestCase):
    """GEMINI.md Rule 3: Full casco upholstery, micro-scale, 0% hue drift, leg protection, 3/4 Right 2054x2054 #FFFFFF."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.furn_bytes = _make_sample_furniture_png()
        cls.fab_bytes = _make_sample_fabric_png()
        cls.fab_ana_v7 = {
            "name": "BOUCLE ARENA",
            "color_description": "warm sand bouclé",
            "texture_detail": "dense looped weave",
            "light_interaction": "soft matte",
            "has_visible_pattern": True,
            "pattern_and_figures": "raised multitone bouclé loops",
        }
        cls.wood_ana = {
            "name": "PAROTA NATURAL",
            "color_description": "warm golden parota wood",
            "texture_detail": "natural timber grain",
            "light_interaction": "satin matte",
        }
        cls.fab_ana_v8 = v8.analyze_fabric_v8_local(cls.fab_bytes, sample_name="BOUCLE_ARENA.png")

    def _assert_upholstery_clauses(self, prompt_text: str, version: str, mode_desc: str) -> None:
        up = prompt_text.upper()
        self.assertIn("EL CASCO COMPLETO", up, f"{version} {mode_desc}: missing EL CASCO COMPLETO")
        self.assertTrue("BACKREST" in up or "RESPALDO" in up, f"{version} {mode_desc}: missing backrest/respaldo")
        self.assertTrue("ARMREST" in up or "DESCANSABRAZOS" in up, f"{version} {mode_desc}: missing armrest/descansabrazos")
        self.assertTrue("BASE" in up or "FALDÓN" in up or "SKIRT" in up, f"{version} {mode_desc}: missing base/faldón/skirt")
        self.assertTrue("CUSHION" in up or "COJINES" in up, f"{version} {mode_desc}: missing cushions/cojines")
        self.assertTrue(
            any(
                tok in up
                for tok in (
                    "0% HUE",
                    "0% UNWANTED HUE",
                    "0° HUE SHIFT",
                    "0% COLOR",
                    "ZERO HUE",
                    "0% ADDITIONAL COLOR",
                    "0% ADDITIONAL TONE",
                    "0% CAMBIO DE TONO",
                )
            ),
            f"{version} {mode_desc}: missing 0% hue/color drift lock",
        )
        self.assertTrue(
            ("WOOD" in up or "METAL" in up) and ("LEG" in up or "NON-UPHOLSTERED" in up or "FRAME" in up),
            f"{version} {mode_desc}: missing wood/metal leg protection clause",
        )
        if version == "V7":
            self.assertIn("97%", prompt_text, f"V7 {mode_desc}: missing 97% micro-scale calibration")
        else:
            v8_valid_squares = "|".join(str(n * n) for n in range(9, 35))
            self.assertTrue(
                bool(re.search(rf"\b({v8_valid_squares})\b", prompt_text))
                or "97%" in prompt_text,
                f"V8 {mode_desc}: missing micro-scale tile calibration",
            )

    def test_v7_upholstery_mandates_across_fabric_capable_modes(self) -> None:
        scenarios = [
            ("catalogo", dict(mode="catalogo", fabric_label="BOUCLE ARENA", fabric_analysis=self.fab_ana_v7)),
            ("vista_suelta", dict(mode="vista_suelta", vista_id="vista_3_4_derecha", fabric_label="BOUCLE ARENA", fabric_analysis=self.fab_ana_v7)),
            ("material/fabric_only", dict(mode="material", material_mode="fabric_only", fabric_label="BOUCLE ARENA", fabric_analysis=self.fab_ana_v7)),
            ("material/dual", dict(mode="material", material_mode="dual", fabric_label="BOUCLE ARENA", fabric_analysis=self.fab_ana_v7, wood_label="PAROTA", wood_analysis=self.wood_ana)),
            ("vistas_tela", dict(mode="vistas_tela", fabric_label="BOUCLE ARENA", fabric_analysis=self.fab_ana_v7, batch_views=[("SOFA_V1.png", self.furn_bytes)], batch_ref_bytes=self.fab_bytes)),
        ]
        with _offline_ai_clients(v7):
            for label, kwargs in scenarios:
                res = v7.build_prompts(
                    furniture_name="SOFA_CONTRACT",
                    tipo_mueble="SOFA",
                    medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
                    **kwargs,
                )
                self._assert_upholstery_clauses(res["items"][0]["google_ai_studio"], "V7", label)

            r34 = v7.build_34_derecha_2054_prompts(
                furniture_name="SOFA_CONTRACT",
                tipo_mueble="SOFA",
                medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
                fabric_label="BOUCLE ARENA",
                fabric_analysis=self.fab_ana_v7,
            )
            self._assert_upholstery_clauses(r34["items"][0]["google_ai_studio"], "V7", "3/4 Derecha")

    def test_v8_upholstery_mandates_across_fabric_capable_modes(self) -> None:
        scenarios = [
            ("catalogo", dict(mode="catalogo", fabric_label="BOUCLE ARENA", fabric_filename="BOUCLE_ARENA.png", fabric_analysis=self.fab_ana_v8)),
            ("vista_suelta", dict(mode="vista_suelta", vista_id="vista_3_4_derecha", fabric_label="BOUCLE ARENA", fabric_filename="BOUCLE_ARENA.png", fabric_analysis=self.fab_ana_v8)),
            ("material/fabric_only", dict(mode="material", material_mode="fabric_only", fabric_label="BOUCLE ARENA", fabric_filename="BOUCLE_ARENA.png", fabric_analysis=self.fab_ana_v8)),
            ("material/dual", dict(mode="material", material_mode="dual", fabric_label="BOUCLE ARENA", fabric_filename="BOUCLE_ARENA.png", fabric_analysis=self.fab_ana_v8, wood_label="PAROTA", wood_filename="PAROTA.jpg", wood_analysis=self.wood_ana)),
            ("vistas_tela", dict(mode="vistas_tela", fabric_label="BOUCLE ARENA", fabric_filename="BOUCLE_ARENA.png", fabric_analysis=self.fab_ana_v8, batch_views=[("SOFA_V1.png", self.furn_bytes)], batch_ref_bytes=self.fab_bytes)),
        ]
        with _offline_ai_clients(v8):
            for label, kwargs in scenarios:
                res = v8.build_prompts(
                    furniture_name="SOFA_CONTRACT",
                    tipo_mueble="SOFA",
                    medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
                    furniture_filenames=["SOFA_CONTRACT.png"],
                    **kwargs,
                )
                self._assert_upholstery_clauses(res["items"][0]["google_ai_studio"], "V8", label)

            r34 = v8.build_34_derecha_2054_prompts(
                furniture_name="SOFA_CONTRACT",
                tipo_mueble="SOFA",
                medidas_texto="220 cm frente x 95 cm fondo x 82 cm alto",
                furniture_filenames=["SOFA_CONTRACT.png"],
                fabric_label="BOUCLE ARENA",
                fabric_filename="BOUCLE_ARENA.png",
                fabric_analysis=self.fab_ana_v8,
            )
            self._assert_upholstery_clauses(r34["items"][0]["google_ai_studio"], "V8", "3/4 Derecha")

    def test_master_34_derecha_clauses_and_exact_2054_pure_white_output_in_v7_and_v8(self) -> None:
        for version, svc in (("V7", v7), ("V8", v8)):
            r34 = svc.build_34_derecha_2054_prompts(
                furniture_name="SILLON_MAESTRO",
                tipo_mueble="SILLON",
                medidas_texto="85 cm frente x 88 cm fondo x 78 cm alto",
                fabric_label="BOUCLE ARENA",
            )
            txt = r34["items"][0]["google_ai_studio"]
            up = txt.upper()
            self.assertIn("FACING TOWARD THE RIGHT", txt, f"{version}: missing facing right clause")
            self.assertIn("#FFFFFF", txt, f"{version}: missing #FFFFFF")
            self.assertIn("RGB 255,255,255", txt, f"{version}: missing RGB 255,255,255")
            self.assertIn("ZERO SHADOWS", up, f"{version}: missing ZERO SHADOWS clause")
            self.assertIn("0% GROUND SHADOW", up, f"{version}: missing 0% ground shadow clause")
            self.assertIn("0% CONTACT SHADOW", up, f"{version}: missing 0% contact shadow clause")
            self.assertIn("0% FLOOR REFLECTION", up, f"{version}: missing 0% floor reflection clause")
            self.assertIn("2054 x 2054", txt, f"{version}: missing 2054 x 2054 resolution")

            formatted = svc.format_image_2054_white(self.furn_bytes, target_px=2054, pure_white_border=True)
            with Image.open(io.BytesIO(formatted["png"])) as out_im:
                self.assertEqual(out_im.size, (2054, 2054), f"{version}: output not 2054x2054")
                for corner in ((0, 0), (2053, 0), (0, 2053), (2053, 2053)):
                    self.assertEqual(out_im.getpixel(corner), (255, 255, 255), f"{version}: corner {corner} not pure white")


class TestRule4FoldersModelsParallelismResponsiveAndSecrets(unittest.TestCase):
    """GEMINI.md Rule 4: Folders, active models, ThreadPoolExecutor, BFS, <=640px CSS, no secrets in V8/obs/CI."""

    def test_drive_folder_ids_parallelism_bfs_models_and_responsive_css(self) -> None:
        self.assertEqual(sheets_service.RENDER_DRIVE_ID, "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX")
        self.assertEqual(sheets_service.SUBIR_DRIVE_ID, "11_rR-qhgM02Sfx9zw7uHU5AwXvTpKD4p")
        self.assertEqual(V8_RENDER_ID, "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX")
        self.assertEqual(V8_SUBIR_ID, "11_rR-qhgM02Sfx9zw7uHU5AwXvTpKD4p")
        self.assertTrue(V8_FOLDER_SPECS["COTIZACION"]["drive_path"])
        self.assertEqual(V7_RENDER_ID, "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX")
        self.assertTrue(V7_FOLDER_SPECS["COTIZACION"]["drive_path"])
        gitignore_lines = {
            ln.strip()
            for ln in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        }
        self.assertIn(".env", gitignore_lines)
        self.assertIn(".streamlit/secrets.toml", gitignore_lines)

        self.assertTrue(len(gemini_runtime.VISION_MODELS) >= 3)
        self.assertTrue(all(isinstance(m[0], str) and m[0].startswith("gemini-") for m in gemini_runtime.VISION_MODELS))

        v7_src = (REPO_ROOT / "modules/prompt_studio_v7.py").read_text(encoding="utf-8")
        v8_src = (REPO_ROOT / "modules/prompt_studio_v8.py").read_text(encoding="utf-8")
        main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        for label, src in (("V7", v7_src), ("V8", v8_src)):
            self.assertIn("ThreadPoolExecutor", src, f"{label} missing ThreadPoolExecutor")
            self.assertIn("get_multiple_drive_folders_files", src, f"{label} missing BFS Drive scan")
        self.assertIn("@media (max-width: 640px)", main_src)

    def test_zero_hardcoded_secrets_in_v8_observability_and_ci(self) -> None:
        # Layer A: Strict static regex scan across ALL V8, observability, runtime, CI,
        # docs, and newly added test files (zero credential literals permitted).
        secret_patterns = [
            re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
            re.compile(r"ya29\.[0-9A-Za-z._-]+"),
            re.compile(r"AQ\.[0-9A-Za-z._-]{10,}"),
            re.compile(r"GOCSPX-[0-9A-Za-z_-]+"),
            re.compile(r"1//[0-9A-Za-z._-]{20,}"),
            re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
            re.compile("QVEu" + "QWI4"),
            re.compile("eyJ0b2tl" + "biI6"),
            re.compile("ewogIC" + "J0eX"),
        ]
        strict_paths = [
            REPO_ROOT / "modules" / "prompt_studio_v8.py",
            REPO_ROOT / "services" / "ai_prompt_service_v8.py",
            REPO_ROOT / "services" / "fabric_composer_v8.py",
            REPO_ROOT / "services" / "observability.py",
            REPO_ROOT / "services" / "gemini_runtime.py",
            REPO_ROOT / "services" / "ai_prompt_service_v5.py",
            REPO_ROOT / "tests" / "test_observability.py",
            REPO_ROOT / "tests" / "test_gemini_contract.py",
            REPO_ROOT / "RENDER_DEPLOY.md",
        ]
        gh_dir = REPO_ROOT / ".github"
        if gh_dir.exists():
            strict_paths.extend(sorted(p for p in gh_dir.rglob("*") if p.is_file()))

        for path in strict_paths:
            self.assertTrue(path.exists(), f"Expected audited path missing: {path}")
            content = path.read_text(encoding="utf-8")
            # Only ignore regex pattern definition lines in observability.py / test_gemini_contract.py
            lines_to_scan = [
                ln for ln in content.splitlines()
                if not (
                    path.name in ("observability.py", "test_gemini_contract.py")
                    and "re.compile(" in ln
                )
            ]
            joined = "\n".join(lines_to_scan)
            for pat in secret_patterns:
                self.assertIsNone(
                    pat.search(joined),
                    f"Potential hardcoded secret matched {pat.pattern} in {path.relative_to(REPO_ROOT)}",
                )

        # Layer B: Dynamic decoded-legacy-secret leak guard across ALL tracked text files
        # in the repo (preserves pre-existing legacy base64 blobs in main.py,
        # ai_prompt_service_v7.py, sheets_service.py for Render & test_v7.py:532,
        # while asserting ZERO decoded live secrets appear in plaintext anywhere).
        forbidden_needles: list[tuple[str, str]] = []
        main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        v7_src = (REPO_ROOT / "services" / "ai_prompt_service_v7.py").read_text(encoding="utf-8")
        sheets_src = (REPO_ROOT / "services" / "sheets_service.py").read_text(encoding="utf-8")

        m_main_aq = re.search(r'"(' + "QVEu" + r'[A-Za-z0-9+/=]+)"', main_src)
        if m_main_aq:
            aq_real = base64.b64decode(m_main_aq.group(1)).decode("utf-8", errors="ignore")
            if len(aq_real) >= 20:
                forbidden_needles.append(("legacy_main_aq", aq_real[:20]))

        m_v7_aq = re.search(r'"(' + "QVEu" + r'[A-Za-z0-9+/=]+)"', v7_src)
        if m_v7_aq:
            v7_aq_real = base64.b64decode(m_v7_aq.group(1)).decode("utf-8", errors="ignore")
            if len(v7_aq_real) >= 20:
                forbidden_needles.append(("legacy_v7_aq", v7_aq_real[:20]))

        m_oauth = re.search(r'b64decode\("(' + "eyJ0b2tl" + r'biI6[^"]+)"\)', sheets_src)
        if m_oauth:
            oauth_obj = json.loads(base64.b64decode(m_oauth.group(1)).decode("utf-8"))
            if oauth_obj.get("client_secret"):
                forbidden_needles.append(("legacy_oauth_client_secret", oauth_obj["client_secret"]))
                forbidden_needles.append(("legacy_oauth_client_secret_prefix", oauth_obj["client_secret"][:16]))
            if oauth_obj.get("token"):
                forbidden_needles.append(("legacy_oauth_token_prefix", oauth_obj["token"][:20]))
            if oauth_obj.get("refresh_token"):
                forbidden_needles.append(("legacy_oauth_refresh_prefix", oauth_obj["refresh_token"][:20]))

        m_sa = re.search(r'b64decode\("(' + "ewogIC" + r'J0eX[^"]+)"\)', sheets_src)
        if m_sa:
            sa_obj = json.loads(base64.b64decode(m_sa.group(1)).decode("utf-8"))
            if sa_obj.get("private_key_id"):
                forbidden_needles.append(("legacy_sa_private_key_id", sa_obj["private_key_id"]))
            pk_lines = [
                ln.strip()
                for ln in str(sa_obj.get("private_key") or "").splitlines()
                if ln.strip() and not ln.startswith("-----")
            ]
            for idx, pk_ln in enumerate(pk_lines[:2]):
                if len(pk_ln) >= 24:
                    forbidden_needles.append((f"legacy_sa_pk_line{idx}", pk_ln[:24]))

        scan_exts = {".py", ".yml", ".yaml", ".md", ".toml", ".txt", ".json"}
        for path in sorted(REPO_ROOT.rglob("*")):
            if ".git" in path.parts or "__pycache__" in path.parts or not path.is_file():
                continue
            if path.suffix.lower() not in scan_exts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, needle in forbidden_needles:
                # Never include `needle` in failure message so CI logs never print a live secret!
                self.assertNotIn(
                    needle,
                    text,
                    f"Decoded legacy credential ({label}, len={len(needle)}) leaked into {path.relative_to(REPO_ROOT)}",
                )


class TestVersionRetentionContract(unittest.TestCase):
    """Verify V1, V6 (+ internal V5 engine), V7, V8 remain importable & wired while obsolete V2–V5 files are absent."""

    def test_kept_versions_importable_and_wired_and_obsolete_v2_v5_removed(self) -> None:
        kept_modules = [
            "services.ai_prompt_service_v1",
            "modules.prompt_studio_v1",
            "services.unified_prompt_service",
            "services.ai_prompt_service_v5",
            "modules.prompt_studio_unified",
            "services.ai_prompt_service_v7",
            "modules.prompt_studio_v7",
            "services.ai_prompt_service_v8",
            "services.fabric_composer_v8",
            "modules.prompt_studio_v8",
            "services.observability",
        ]
        for mod_name in kept_modules:
            mod = importlib.import_module(mod_name)
            self.assertIsNotNone(mod, f"Failed importing retained module {mod_name}")

        main_src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        for expected_wire in (
            "modules.prompt_studio_v8",
            "modules.prompt_studio_v7",
            "modules.prompt_studio_unified",
            "modules.prompt_studio_v1",
            "modules.alta_fotos_hub",
        ):
            self.assertIn(expected_wire, main_src)

        removed_files = [
            "modules/prompt_studio_v2.py",
            "services/ai_prompt_service_v2.py",
            "modules/prompt_studio_v3.py",
            "services/ai_prompt_service_v3.py",
            "modules/prompt_studio_v4.py",
            "services/ai_prompt_service_v4.py",
            "modules/prompt_studio_v5.py",
        ]
        for rel in removed_files:
            self.assertFalse((REPO_ROOT / rel).exists(), f"Obsolete file should be removed: {rel}")
            stem = Path(rel).stem
            self.assertNotIn(stem, main_src, f"Stale reference {stem} in main.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)

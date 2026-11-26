"""Pruebas del Estudio V7. Ejecutar: python tests/test_v7.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ai_prompt_service_v7 import (  # noqa: E402
    ALL_SINGLE_VIEWS,
    MODES,
    VIEW_IDS,
    ai_prompt_service_v7 as v7,
)

FAILS = []


def check(name: str, cond: bool) -> None:
    print(("[PASS] " if cond else "[FAIL] ") + name)
    if not cond:
        FAILS.append(name)


def build(mode: str, tipo: str, medidas: str, **kw):
    return v7.build_prompts(
        mode=mode,
        furniture_name="PRUEBA",
        tipo_mueble=tipo,
        medidas_texto=medidas,
        **kw,
    )


# 1. Dimensiones y categorías
d = v7.parse_dimensions("MESA DE CENTRO", "138 cm frente x 70 cm fondo x 38 cm alto")
check("mesa: 138/70/38", (d["width_cm"], d["depth_cm"], d["height_cm"]) == (138, 70, 38))
d_round = v7.parse_dimensions("MESA AUXILIAR", "D. 46 cm x 44 cm alto")
check("mesa redonda D. 46: diam 46 alto 44", (d_round["diam_cm"], d_round["height_cm"]) == (46, 44))
d_mir = v7.parse_dimensions("ESPEJO", "80 cm frente x 120 cm fondo x 4 cm alto")
check("espejo: alto 120, grosor 4", (d_mir["height_cm"], d_mir["depth_cm"]) == (120, 4))
d_3d = v7.parse_dimensions("MESA", "authentic 3D geometry 138 cm frente")
check("'3D' no se lee como medida", d_3d["depth_cm"] is None)
check("compose", v7.compose_dimensions_text(80, 4, 120, 0) == "80 cm frente x 4 cm fondo x 120 cm alto")

# 2. Catálogo 7 vistas y anclaje dinámico (sin choque de Image 2 cuando hay madera!)
r = build("catalogo", "MESA DE CENTRO", "138 cm frente x 70 cm fondo x 38 cm alto")
check("catalogo: 7 items en orden", [i["id"] for i in r["items"]] == VIEW_IDS)
check("catalogo: maestro AIS rotacion", "CRITICAL ROTATION RULE" in r["master_ais"])
check("catalogo: vista 1 sin ancla", not r["items"][0]["needs_anchor"])
check("catalogo: vista 2 con ancla Image 2 (sin madera)", r["items"][1]["needs_anchor"] and "Image 2 (APPROVED VISTA 1 ANCHOR" in r["items"][1]["google_ai_studio"])

r_with_wood = build(
    "catalogo",
    "MESA DE CENTRO",
    "138 cm frente x 70 cm fondo x 38 cm alto",
    wood_label="PAROTA SKANOR",
    wood_analysis={"name": "PAROTA SKANOR", "color_description": "warm parota brown", "texture_detail": "natural grain", "light_interaction": "satin"},
)
v2_ais = r_with_wood["items"][1]["google_ai_studio"]
check("con madera: Image 2 es madera y Image 3 es ancla Vista 1", "Image 2 (WOOD SAMPLE" in v2_ais and "Image 3 (APPROVED VISTA 1 ANCHOR" in v2_ais)
check("con madera: attachment_guide exacto", any("Image 2: Muestra de madera" in g for g in r_with_wood["items"][1]["attachment_guide"]))

# 3. Plano técnico CAD y Espejo
check("catalogo: plano con cotas exactas", "Alto: 38 cm" in r["items"][5]["google_ai_studio"] and "Ancho: 138 cm" in r["items"][5]["google_ai_studio"])
r_mir = build("catalogo", "ESPEJO", "80 cm frente x 4 cm fondo x 120 cm alto")
check("espejo: grosor en plano", "Grosor: 4 cm" in r_mir["items"][5]["google_ai_studio"])
check("espejo vista 7: muro/recibidor sin sofa forzado", "wall-mounted mirror" in r_mir["items"][6]["google_ai_studio"] and "curved modern sofa" not in r_mir["items"][6]["google_ai_studio"])

# 4. Todas las 11 vistas sueltas
for vid in ALL_SINGLE_VIEWS:
    rv = build("vista_suelta", "BURO", "55 cm frente x 40 cm fondo x 55 cm alto", vista_id=vid)
    check(f"vista_suelta {vid}", len(rv["items"]) == 1 and rv["items"][0]["id"] == vid and len(rv["items"][0]["google_ai_studio"]) > 120)

# 5. Entorno con lugar_casa personalizado + categoría cama
r_bed = build("entorno", "CAMA KING", "200 cm frente x 210 cm fondo x 120 cm alto", lugar_casa="Recámara principal estilo Japandi")
check("entorno cama + lugar_casa", "Japandi" in r_bed["items"][0]["google_ai_studio"] and "linen bedding" in r_bed["items"][0]["google_ai_studio"])

# 6. Material (wood_only, fabric_only, dual) + toggle white_bg
for mm in ("wood_only", "fabric_only", "dual"):
    rm = build("material", "SILLA", "55 cm frente x 55 cm fondo x 85 cm alto", material_mode=mm, wood_label="NOGAL", fabric_label="BOUCLE")
    check(f"material {mm}", len(rm["items"]) == 1 and len(rm["items"][0]["google_ai_studio"]) > 150)

rm_orig_bg = build("hd", "SILLA", "55 cm frente x 55 cm fondo x 85 cm alto", white_bg_enabled=False)
check("hd sin fondo blanco conserva escena original", "original background" in rm_orig_bg["items"][0]["google_ai_studio"])

# 7. Modos lote (V4 integrados): vistas_tela y clonar_color en modo local
r_vt = build(
    "vistas_tela",
    "SOFA",
    "210 cm frente x 90 cm fondo x 80 cm alto",
    fabric_label="LINO ARENA",
    batch_ref_bytes=b"fake_fabric",
    batch_views=[("frente.jpg", b"v1"), ("lateral.jpg", b"v2")],
)
check("vistas_tela lote 2 vistas", len(r_vt["items"]) == 2 and "LINO ARENA" in r_vt["items"][0]["google_ai_studio"])

r_cc = build(
    "clonar_color",
    "MESA",
    "120 cm frente x 60 cm fondo x 45 cm alto",
    batch_ref_bytes=b"fake_ref",
    batch_views=[("v1.jpg", b"v1"), ("v2.jpg", b"v2"), ("v3.jpg", b"v3")],
)
check("clonar_color lote 3 vistas", len(r_cc["items"]) == 3 and "COLOR & MATERIAL MASTER" in r_cc["items"][0]["google_ai_studio"])

# 8. Consistencia de catálogo de modos y mejoras solicitadas
check("9 modos registrados", len(MODES) == 9)
check("menu compacto de pocas palabras", all(len(lbl.split()) <= 3 for lbl in MODES.values()))
check("warn sin medidas", len(v7.sanity_warnings("table", 0, 0, 0, 0)) == 1)

# 9. Textura exacta de tela en todo el casco + escala real (~97%)
rm_fab = build(
    "material",
    "SOFA",
    "220 cm frente x 95 cm fondo x 82 cm alto",
    material_mode="fabric_only",
    fabric_label="BOUCLE MARFIL",
    fabric_analysis={
        "name": "BOUCLE MARFIL",
        "color_description": "warm ivory bouclé",
        "texture_detail": "dense looped weave",
        "light_interaction": "soft matte",
    },
)
check(
    "material tela bloquea casco completo y escala 97%",
    "EL CASCO COMPLETO" in rm_fab["items"][0]["google_ai_studio"]
    and "97%" in rm_fab["items"][0]["google_ai_studio"],
)

# 10. Botón directo: 3/4 mirando a la derecha · fondo blanco · 0% sombras · 2054x2054
r_34_2054 = v7.build_34_derecha_2054_prompts(
    furniture_name="SILLON_PRUEBA",
    tipo_mueble="SILLON",
    medidas_texto="85 cm frente x 88 cm fondo x 78 cm alto",
    fabric_label="LINO ARENA",
    fabric_analysis={
        "name": "LINO ARENA",
        "color_description": "natural sand linen",
        "texture_detail": "fine linen weave",
        "light_interaction": "matte",
    },
)
p_34 = r_34_2054["items"][0]["google_ai_studio"]
check(
    "boton 3/4 derecha 2054x2054 sin sombras + tela en casco",
    "FACING TOWARD THE RIGHT" in p_34
    and "2054 x 2054" in p_34
    and "#FFFFFF" in p_34
    and "0% ground shadow" in p_34
    and "EL CASCO COMPLETO" in p_34,
)

# 11. Normalizador exacto a 2054x2054 px en blanco puro #FFFFFF
import io as _io
from PIL import Image as _Image

_sample = _Image.new("RGB", (600, 400), (250, 250, 250))
for _x in range(200, 400):
    for _y in range(120, 280):
        _sample.putpixel((_x, _y), (110, 80, 60))
_buf = _io.BytesIO()
_sample.save(_buf, format="JPEG", quality=95)
_fmt = v7.format_image_2054_white(_buf.getvalue())
with _Image.open(_io.BytesIO(_fmt["png"])) as _out:
    check(
        "imagen formateada exactamente a 2054x2054 y borde #FFFFFF",
        _out.size == (2054, 2054) and _out.getpixel((0, 0)) == (255, 255, 255),
    )

# 12. Modo escena (pure_white_border=False) conserva color de pared en 2054x2054
_fmt_room = v7.format_image_2054_white(_buf.getvalue(), target_px=2054, pure_white_border=False)
with _Image.open(_io.BytesIO(_fmt_room["png"])) as _out_room:
    check(
        "escena entorno 2054x2054 sin blanquear paredes",
        _out_room.size == (2054, 2054) and _out_room.getpixel((0, 0))[0] < 255,
    )

# 13. Helpers de URL Drive, carpetas de muebles (RENDER, Cotización, SM S Mueblería) y diagnóstico de API key
from pathlib import PureWindowsPath as _PWP  # noqa: E402
from services.sheets_service import sheets_service as _ss  # noqa: E402

try:
    import streamlit as _st_check  # noqa: F401
except ImportError:
    import types as _types

    class _StubSessionState(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name, value):
            self[name] = value

    def _stub_cache_data(*args, **kwargs):
        def _dec(fn):
            fn.clear = lambda: None
            return fn
        return _dec(args[0]) if args and callable(args[0]) else _dec

    _st_mod = _types.ModuleType("streamlit")
    _st_mod.session_state = _StubSessionState()
    _st_mod.cache_data = _stub_cache_data
    _st_mod.rerun = lambda *a, **kw: None
    _st_mod.set_page_config = lambda *a, **kw: None
    _st_comp_pkg = _types.ModuleType("streamlit.components")
    _st_comp_v1 = _types.ModuleType("streamlit.components.v1")
    _st_comp_v1.html = lambda *a, **kw: None
    _st_comp_v1.iframe = lambda *a, **kw: None
    _st_comp_pkg.v1 = _st_comp_v1
    _st_mod.components = _st_comp_pkg
    sys.modules["streamlit"] = _st_mod
    sys.modules["streamlit.components"] = _st_comp_pkg
    sys.modules["streamlit.components.v1"] = _st_comp_v1

from modules.prompt_studio_v7 import (  # noqa: E402
    FOLDER_MUEBLES_RENDER_DRIVE_ID,
    FOLDER_MUEBLES_SM_MUEBLERIA_DRIVE_ID,
    FOLDER_TELAS_DRIVE_ID,
    FOLDER_TELAS_ODOO_DRIVE_ID,
    FURNITURE_FOLDER_CHOICES,
    IMG_TYPES,
    LOCAL_COTIZACION_MUEBLES_DIR,
    LOCAL_RENDER_MUEBLES_DIR,
    LOCAL_SM_MUEBLERIA_MUEBLES_DIR,
    _build_zip as _build_zip_v7,
    _candidate_local_dirs,
    _extract_exact_photo_stem,
    _get_search_preview_src,
    _merge_telas_lists,
    _resolve_furniture_drive_id,
    filter_catalog_photos_by_name,
)

check(
    "extract_drive_id extrae ID limpio de link Drive",
    _ss.extract_drive_id("https://drive.google.com/file/d/1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B/view?usp=sharing")
    == "1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B"
    and _ss.extract_drive_id("https://drive.google.com/drive/folders/1P06GIuVHFPhQtE2kvPX-_JPA9A6N-qoF?usp=drive_link")
    == "1P06GIuVHFPhQtE2kvPX-_JPA9A6N-qoF",
)
check(
    "carpetas RENDER, Cotización y SM S Mueblería configuradas para muebles",
    FOLDER_MUEBLES_RENDER_DRIVE_ID == "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX"
    and FOLDER_MUEBLES_SM_MUEBLERIA_DRIVE_ID == "1P06GIuVHFPhQtE2kvPX-_JPA9A6N-qoF"
    and _PWP(str(LOCAL_RENDER_MUEBLES_DIR)).name == "RENDER"
    and "Cotiz" in _PWP(str(LOCAL_COTIZACION_MUEBLES_DIR)).name
    and _PWP(str(LOCAL_SM_MUEBLERIA_MUEBLES_DIR)).name == "FOTOS SM S MUEBLERIA"
    and set(FURNITURE_FOLDER_CHOICES.values()) == {"ALL", "RENDER", "COTIZACION", "SM_MUEBLERIA"}
    and len(_candidate_local_dirs("COTIZACION")) >= 1
    and len(_candidate_local_dirs("SM_MUEBLERIA")) >= 1
    and _ss._norm_drive_name("Cotización") == "cotizacion"
    and _resolve_furniture_drive_id("RENDER") == FOLDER_MUEBLES_RENDER_DRIVE_ID
    and _resolve_furniture_drive_id("SM_MUEBLERIA") == FOLDER_MUEBLES_SM_MUEBLERIA_DRIVE_ID,
)

_merged_telas = _merge_telas_lists(
    [{"id": "t1", "name": "Boucle Marfil"}, {"id": "t2", "name": "Lino Arena"}],
    [{"id": "t2", "name": "Lino Arena"}, {"id": "t3", "name": "Terciopelo Gris"}],
)
_cfg_toml = (Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml").read_text(encoding="utf-8")
check(
    "telas combina TELAS + FOTOS TELAS sin duplicados y config.toml habilita subidas en iframe",
    FOLDER_TELAS_DRIVE_ID == "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
    and FOLDER_TELAS_ODOO_DRIVE_ID == "12gsKZVs6rFonOO8CIxokuE73bxhq8tS9"
    and len(_merged_telas) == 3
    and "jfif" in IMG_TYPES
    and "avif" in IMG_TYPES
    and "enableXsrfProtection = false" in _cfg_toml
    and "enableCORS = false" in _cfg_toml,
)

_sample_cat = [
    {"name": "Sillón Ánkara", "filename": "sillon_ankara.jpg", "source": "SM S Mueblería"},
    {"name": "Mesa Parota Skanor", "filename": "mesa_parota.png", "source": "RENDER"},
    {"name": "Credenza Nórdica", "filename": "credenza_nordica.jpg", "source": "Cotización"},
]
_hits_ank = filter_catalog_photos_by_name(_sample_cat, "sillon ankara")
_hits_active = filter_catalog_photos_by_name(_sample_cat, "", active_names_upper={"CREDENZA NÓRDICA"})
_ss._drive_file_bytes_cache["thumb:test_prev_id"] = _fmt["jpg"]
_prev_uri = _get_search_preview_src({"id": "test_prev_id", "name": "Sillón Ánkara"}, max_dim=180, allow_network=False)
check(
    "buscador de menu flotante filtra por nombre sin acentos, prioriza cargadas y genera vista previa visual",
    len(_hits_ank) == 1
    and _hits_ank[0]["name"] == "Sillón Ánkara"
    and _hits_active[0]["name"] == "Credenza Nórdica"
    and _prev_uri.startswith("data:image/jpeg;base64,"),
)
check(
    "format_gemini_error detecta API key filtrada (403 leaked)",
    "bloqueada por Google" in v7.format_gemini_error(RuntimeError("403 Your API key was reported as leaked")),
)

r_34_2054["mueble_name"] = "SILLON_PRUEBA"
r_34_2054["ref_images"] = [("sillon.jpg", _fmt["jpg"])]
import zipfile as _zf

_zip_bytes = _build_zip_v7(r_34_2054, include_images=True)
with _zf.ZipFile(_io.BytesIO(_zip_bytes), "r") as _z:
    _names = _z.namelist()
    check(
        "zip empaqueta prompts e insumos limpiamente con nombre exacto",
        "prompts/SILLON_PRUEBA.txt" in _names
        and "insumos/sillon.jpg" in _names,
    )

# 14. Motor híbrido V1 + V7 para hacer tela (material fabric_only / dual / velvet guard / batch)
r_mat_v17 = build(
    "material",
    "SOFA",
    "220 cm frente x 95 cm fondo x 82 cm alto",
    material_mode="fabric_only",
    fabric_label="BOUCLE SAL Y PIMIENTA",
    fabric_analysis={
        "name": "Heathered Salt-and-Pepper Bouclé",
        "color_description": "marfil cálido con motas gris carbón",
        "texture_detail": "dense nubby loops over cool grey under-weave",
        "light_interaction": "soft matte textile",
    },
    furniture_analysis={"camera_angle": "eye-level 3/4 view facing right", "geometric_structure": "curved 3-seater sofa"},
)
p_mat = r_mat_v17["items"][0]["google_ai_studio"]
check(
    "V1+V7 material tela: estructura V1 + casco V7 + Image 1 tela",
    p_mat.startswith("INSTRUCTION:")
    and "GENERATE:" in p_mat
    and "CAMERA CONSTRAINT: You MUST lock the camera to eye-level 3/4 view facing right" in p_mat
    and "EL CASCO COMPLETO" in p_mat
    and "97%" in p_mat
    and "Negative Prompt:" in p_mat
    and "generic fabric, solid color, flat texture" in p_mat
    and r_mat_v17["items"][0]["attachment_guide"][0].startswith("Image 1: Muestra de tela"),
)

r_velvet = build(
    "material",
    "SILLON",
    "85 cm frente x 85 cm fondo x 78 cm alto",
    material_mode="fabric_only",
    fabric_label="TERCIOPELO ESMERALDA",
    fabric_analysis={
        "name": "Emerald Velvet",
        "color_description": "verde esmeralda profundo",
        "texture_detail": "plush directional velvet pile",
        "light_interaction": "directional velvet sheen",
    },
)
check(
    "V1+V7 velvet guard: no excluye velvet cuando la tela elegida es terciopelo",
    "velvet" not in r_velvet["items"][0]["google_ai_studio"].split("Negative Prompt:")[-1].lower(),
)

r_vt_ana = build(
    "vistas_tela",
    "SOFA",
    "210 cm frente x 90 cm fondo x 80 cm alto",
    fabric_label="BOUCLE SAL",
    fabric_analysis={
        "name": "Heathered Bouclé",
        "color_description": "arena con hilos taupe",
        "texture_detail": "tightly twisted bouclé loops",
        "light_interaction": "matte",
    },
    batch_ref_bytes=b"fake_fabric",
    batch_views=[("frente.jpg", b"v1")],
)
check(
    "V1+V7 vistas_tela inyecta análisis de tela en lote",
    "tightly twisted bouclé loops" in r_vt_ana["items"][0]["google_ai_studio"]
    and "INSTRUCTION:" in r_vt_ana["items"][0]["google_ai_studio"],
)

# 15. Botón copiar foto original debajo de cada foto (+50% más grande) + nombre exacto de foto original
from modules.ui_helpers import prepare_exact_copy_image_bytes, render_loaded_photos_strip  # noqa: E402
from modules.alta_fotos_hub import ODOO_DEST_FOLDERS, resolve_upload_filename  # noqa: E402
import streamlit.components.v1 as _st_comp  # noqa: E402

_exact_b, _exact_m = prepare_exact_copy_image_bytes(_buf.getvalue())
with _Image.open(_io.BytesIO(_exact_b)) as _exact_img:
    check(
        "copiar foto conserva dimensiones originales exactas sin recorte",
        _exact_img.size == (600, 400) and _exact_m in ("image/jpeg", "image/png"),
    )

_captured_html = []
_orig_comp_html = _st_comp.html
try:
    _st_comp.html = lambda html_str, **kw: _captured_html.append((html_str, kw))
    render_loaded_photos_strip(
        [("SILLON ANKARA.jpg", _buf.getvalue(), "Mueble · SM S Mueblería"), ("TELA LINO.jpg", _buf.getvalue(), "Tela")],
        key_prefix="test_strip",
    )
finally:
    _st_comp.html = _orig_comp_html

_strip_html = _captured_html[0][0] if _captured_html else ""
check(
    "tira de fotos cargadas muestra fotos 120x120 (+50%) con 1 botón Copiar foto (imagen PNG, no texto) debajo de cada foto",
    len(_captured_html) == 1
    and "width: 120px;" in _strip_html
    and "height: 120px;" in _strip_html
    and "flex-direction: column;" in _strip_html
    and _strip_html.count("🖼️ Copiar foto") == 2
    and _strip_html.find("<img class=\"thumb-img\"") < _strip_html.find("🖼️ Copiar foto")
    and "writePngToWindowClipboard(window.parent" in _strip_html
    and "CREATA_PROMPTS_COPY_IMAGE" in _strip_html
    and "writeText" not in _strip_html,
)

check(
    "prompts y alta de fotos conservan exactamente el mismo nombre de la foto cargada",
    _extract_exact_photo_stem("SILLON ANKARA BEIGE.jpg") == "SILLON ANKARA BEIGE"
    and r_34_2054["items"][0].get("output_filename") == "SILLON_PRUEBA.png"
    and "OUTPUT FILE NAME: SILLON_PRUEBA.png" in r_34_2054["items"][0]["google_ai_studio"]
    and "OUTPUT FILE NAME: SILLON_PRUEBA.png" in r_34_2054["items"][0]["chatgpt_dalle3"]
    and r_vt_ana["items"][0].get("output_filename") == "frente.png"
    and "OUTPUT FILE NAME: frente.png" in r_vt_ana["items"][0]["google_ai_studio"]
    and resolve_upload_filename("gen_ai_01.png", "SILLON ANKARA BEIGE", 1, 1, False) == ("SILLON ANKARA BEIGE.png", "SILLON ANKARA BEIGE")
    and resolve_upload_filename("gen_ai_02.jpg", "SILLON ANKARA BEIGE", 2, 2, True) == ("SILLON ANKARA BEIGE_2.png", "SILLON ANKARA BEIGE_2")
    and len(ODOO_DEST_FOLDERS) >= 5,
)

# 16. Permisos públicos "Cualquiera con el enlace" al subir y miniaturas privadas seguras
class _FakeExec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakePermsApi:
    def __init__(self, calls, list_perms=None):
        self._calls = calls
        self._list_perms = list_perms or []

    def create(self, **kw):
        self._calls.append(("perm_create", kw))
        return _FakeExec({"id": "perm_anyone"})

    def list(self, **kw):
        self._calls.append(("perm_list", kw))
        return _FakeExec({"permissions": self._list_perms})


class _FakeFilesApi:
    def __init__(self, calls, meta=None):
        self._calls = calls
        self._meta = meta or {}

    def create(self, **kw):
        self._calls.append(("file_create", kw))
        return _FakeExec({"id": "new_file_123", "name": kw["body"]["name"], "webViewLink": "https://drive.google.com/file/d/new_file_123/view"})

    def get(self, **kw):
        self._calls.append(("file_get", kw))
        return _FakeExec(self._meta)


class _FakeDriveService:
    def __init__(self, calls, meta=None, list_perms=None):
        self._calls = calls
        self._meta = meta or {}
        self._list_perms = list_perms or []

    def permissions(self):
        return _FakePermsApi(self._calls, self._list_perms)

    def files(self):
        return _FakeFilesApi(self._calls, self._meta)


_perm_calls = []
_orig_drive = _ss.drive_service
_orig_ensure = _ss.ensure_connected
try:
    _ss.ensure_connected = lambda: True
    _ss.drive_service = _FakeDriveService(_perm_calls, meta={"id": "f_priv", "name": "PRIV", "permissions": [{"type": "user", "role": "owner"}]})
    _priv_info = _ss.inspect_drive_item_permissions("f_priv")
    _ss.drive_service = _FakeDriveService(_perm_calls, meta={"id": "f_pub", "name": "PUB", "permissions": [{"type": "anyone", "role": "reader"}]})
    _pub_info = _ss.inspect_drive_item_permissions("f_pub")
    _up_link = _ss.upload_image_bytes_to_drive(_buf.getvalue(), "SILLON_TEST.jpg", "folder_dest_1")
finally:
    _ss.drive_service = _orig_drive
    _ss.ensure_connected = _orig_ensure

_perm_creates = [kw for tag, kw in _perm_calls if tag == "perm_create"]
check(
    "subida asigna permiso anyone/reader con supportsAllDrives=True y revisa carpetas privadas vs públicas",
    _priv_info["ok"] and not _priv_info["is_public"] and "Privado" in _priv_info["summary"]
    and _pub_info["ok"] and _pub_info["is_public"] and "Público" in _pub_info["summary"]
    and _up_link == "https://drive.google.com/file/d/new_file_123/view?usp=sharing"
    and len(_perm_creates) == 1
    and _perm_creates[0].get("fileId") == "new_file_123"
    and _perm_creates[0].get("body") == {"role": "reader", "type": "anyone"}
    and _perm_creates[0].get("supportsAllDrives") is True
    and _ss._last_permission_status.get("new_file_123", (False, ""))[0] is True,
)

check(
    "buscador nunca expone thumbnailLink privado/expirado directo al navegador",
    _get_search_preview_src(
        {"id": "uncached_priv_id", "name": "Privada", "thumbnailLink": "https://lh3.googleusercontent.com/private-expiring=s220"},
        max_dim=180,
        allow_network=False,
    ) == "",
)

# 17. Runtime rápido Gemini (respeto a llaves AIza, fallback auth, cooldown ante 503/404, y visibilidad de estado V7)
import os as _os  # noqa: E402
from services import gemini_runtime as _gr  # noqa: E402

_gr.reset_runtime_state()
_prev_env_key = _os.environ.get("GEMINI_API_KEY")
_sample_aiza = "AIza" + ("X" * 35)
try:
    _os.environ["GEMINI_API_KEY"] = _sample_aiza
    _resolved_aiza = v7.get_api_key()
    _gr.mark_key_rejected(_sample_aiza)
    _resolved_after_reject = v7.get_api_key()
finally:
    if _prev_env_key is None:
        _os.environ.pop("GEMINI_API_KEY", None)
    else:
        _os.environ["GEMINI_API_KEY"] = _prev_env_key
    _gr.reset_runtime_state()

check(
    "get_api_key respeta llave estándar AIza de 39 caracteres y cae a respaldo solo si fue rechazada",
    _resolved_aiza == _sample_aiza and _resolved_after_reject == v7._builtin_key,
)


class _FakeGeminiResp:
    def __init__(self, text: str):
        self.text = text


class _FakeModelsApi:
    def __init__(self, handler):
        self._handler = handler

    def generate_content(self, **kw):
        return self._handler(**kw)


class _FakeGenaiClient:
    def __init__(self, handler):
        self.models = _FakeModelsApi(handler)


_gr.reset_runtime_state()
_seen_models = []


def _handler_503_then_ok(model, contents, config=None):
    _seen_models.append(model)
    if model == _gr.VISION_MODELS[0][0]:
        raise RuntimeError("503 UNAVAILABLE: This model is currently experiencing high demand.")
    return _FakeGeminiResp('{"ok": true}')


_fake_cli = _FakeGenaiClient(_handler_503_then_ok)
_res1 = _gr.call_gemini_fast(_fake_cli, ["hi"], api_key="test-key-1")
_res2 = _gr.call_gemini_fast(_fake_cli, ["hi"], api_key="test-key-1")
check(
    "call_gemini_fast pone en cooldown el modelo 503 y reutiliza el modelo saludable al instante",
    _res1.text == '{"ok": true}'
    and _res2.text == '{"ok": true}'
    and _seen_models == [_gr.VISION_MODELS[0][0], _gr.VISION_MODELS[1][0], _gr.VISION_MODELS[1][0]],
)

_gr.reset_runtime_state()
_orig_build = _gr.build_genai_client
try:
    _fb_called = []

    def _bad_key_handler(model, contents, config=None):
        raise RuntimeError("403 PERMISSION_DENIED: Your API key was reported as leaked")

    def _good_fb_handler(model, contents, config=None):
        _fb_called.append(model)
        return _FakeGeminiResp('{"recovered": true}')

    _gr.build_genai_client = lambda k, timeout_ms=_gr.DEFAULT_TIMEOUT_MS: _FakeGenaiClient(_good_fb_handler)
    _res_fb = _gr.call_gemini_fast(
        _FakeGenaiClient(_bad_key_handler),
        ["hi"],
        api_key="AIzaLeakedKey1234567890123456789012345",
        fallback_key="AQ.GoodFallbackKey",
    )
finally:
    _gr.build_genai_client = _orig_build

check(
    "call_gemini_fast marca llave filtrada (403) y recupera automáticamente con fallback_key",
    _res_fb.text == '{"recovered": true}'
    and len(_fb_called) == 1
    and _gr.is_key_rejected("AIzaLeakedKey1234567890123456789012345"),
)
_gr.reset_runtime_state()

_v7_src = (Path(__file__).resolve().parent.parent / "modules" / "prompt_studio_v7.py").read_text(encoding="utf-8")
_main_src = (Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
check(
    "V7 muestra status_slot antes de la tira de fotos, spinner de catálogo en frío, toast y main.py no pisa llaves AIza",
    _v7_src.find("status_slot = st.empty()") != -1
    and _v7_src.find("status_slot = st.empty()") < _v7_src.find("_render_mini_thumbs(thumbs,")
    and 'show_spinner="📂 Cargando catálogo de fotos..."' in _v7_src
    and "st.toast(" in _v7_src
    and 'startswith("AIza")' not in _main_src,
)

# 18. Nombre exacto de foto copiada en prompts (todos los modos + AI Studio + ChatGPT + orden de tarjetas Image 1/2/3)
from modules.ui_helpers import resolve_copied_photo_filename  # noqa: E402
from modules.prompt_studio_v7 import build_ordered_photo_thumbs_v7  # noqa: E402

check(
    "resolve_copied_photo_filename normaliza igual que _canonical_photo_filename",
    resolve_copied_photo_filename("SILLON ANKARA BEIGE.jpg") == "SILLON ANKARA BEIGE.jpg"
    and resolve_copied_photo_filename("BOUCLE MARFIL") == "BOUCLE MARFIL.png"
    and resolve_copied_photo_filename("C:\\fotos\\PAROTA_NATURAL.jpg") == "PAROTA_NATURAL.jpg"
    and resolve_copied_photo_filename("SILLON ANKARA BEIGE.jpg") == v7._canonical_photo_filename("SILLON ANKARA BEIGE.jpg"),
)

_thumbs_cat = build_ordered_photo_thumbs_v7(
    mode="catalogo",
    material_mode="dual",
    m_names=["SILLON ANKARA BEIGE.jpg"],
    m_bytes=[b"m1"],
    m_source="RENDER",
    fabric_name="BOUCLE MARFIL.jpg",
    fabric_bytes=b"f1",
    wood_name="PAROTA NATURAL.jpg",
    wood_bytes=b"w1",
    batch_views_files=[],
)
check(
    "tarjetas copiar foto en catalogo coinciden 1-a-1 con orden del prompt (Image 1 Mueble, Image 2 Madera, Image 3 Tela)",
    [t[0] for t in _thumbs_cat] == ["SILLON ANKARA BEIGE.jpg", "PAROTA NATURAL.jpg", "BOUCLE MARFIL.jpg"]
    and _thumbs_cat[0][2].startswith("Image 1 · Mueble")
    and _thumbs_cat[1][2] == "Image 2 · Madera"
    and _thumbs_cat[2][2] == "Image 3 · Tela",
)

_thumbs_mat = build_ordered_photo_thumbs_v7(
    mode="material",
    material_mode="dual",
    m_names=["SILLON ANKARA BEIGE.jpg"],
    m_bytes=[b"m1"],
    m_source="RENDER",
    fabric_name="BOUCLE MARFIL.jpg",
    fabric_bytes=b"f1",
    wood_name="PAROTA NATURAL.jpg",
    wood_bytes=b"w1",
    batch_views_files=[],
)
check(
    "tarjetas copiar foto en material coinciden 1-a-1 con orden del prompt (Image 1 Tela, Image 2 Madera, Image 3 Mueble)",
    [t[0] for t in _thumbs_mat] == ["BOUCLE MARFIL.jpg", "PAROTA NATURAL.jpg", "SILLON ANKARA BEIGE.jpg"]
    and _thumbs_mat[0][2] == "Image 1 · Tela"
    and _thumbs_mat[1][2] == "Image 2 · Madera"
    and _thumbs_mat[2][2].startswith("Image 3 · Mueble"),
)

_r_cat_names = v7.build_prompts(
    mode="catalogo",
    furniture_name="SILLON ANKARA BEIGE",
    tipo_mueble="SILLON",
    medidas_texto="90 cm frente x 85 cm fondo x 80 cm alto",
    furniture_filenames=["SILLON ANKARA BEIGE.jpg", "SILLON ANKARA PERFIL.jpg"],
    wood_label="PAROTA NATURAL",
    wood_filename="PAROTA NATURAL.jpg",
    fabric_label="BOUCLE MARFIL",
    fabric_filename="BOUCLE MARFIL.jpg",
)
_v1_ais = _r_cat_names["items"][0]["google_ai_studio"]
_v1_dal = _r_cat_names["items"][0]["chatgpt_dalle3"]
_bp_ais = _r_cat_names["items"][5]["google_ai_studio"]
_env_ais = _r_cat_names["items"][6]["google_ai_studio"]
check(
    "catalogo y maestro incrustan nombres exactos de fotos copiadas (multi-ángulo + madera + tela + plano + entorno + ChatGPT)",
    'FILE: "SILLON ANKARA BEIGE.jpg"' in _v1_ais
    and 'Image 2 (ADDITIONAL FURNITURE ANGLE · FILE: "SILLON ANKARA PERFIL.jpg")' in _v1_ais
    and 'Image 3 (WOOD SAMPLE GROUND TRUTH · FILE: "PAROTA NATURAL.jpg")' in _v1_ais
    and 'Image 4 (FABRIC SWATCH GROUND TRUTH · FILE: "BOUCLE MARFIL.jpg")' in _v1_ais
    and "PHOTO IDENTIFICATION RULE:" in _v1_ais
    and 'Image 1 = "SILLON ANKARA BEIGE.jpg"' in _v1_dal
    and 'Image 4 = "BOUCLE MARFIL.jpg"' in _v1_dal
    and 'FILE: "SILLON ANKARA BEIGE.jpg"' in _bp_ais
    and 'FILE: "SILLON ANKARA BEIGE.jpg"' in _env_ais
    and 'FILE: "SILLON ANKARA BEIGE.jpg"' in _r_cat_names["master_ais"]
    and 'Image 1 = "SILLON ANKARA BEIGE.jpg"' in _r_cat_names["master_dal"]
    and 'SILLON ANKARA BEIGE.jpg' in _r_cat_names["items"][0]["attachment_guide"][0],
)

_r_mat_names = v7.build_prompts(
    mode="material",
    material_mode="dual",
    furniture_name="SOFA MILAN",
    tipo_mueble="SOFA",
    furniture_filenames=["SOFA_MILAN_FRENTE.jpg"],
    wood_label="NOGAL AMERICANO",
    wood_filename="NOGAL_AMERICANO.jpg",
    fabric_label="LINO ARENA 04",
    fabric_filename="LINO_ARENA_04.jpg",
)
_m_ais = _r_mat_names["items"][0]["google_ai_studio"]
_m_dal = _r_mat_names["items"][0]["chatgpt_dalle3"]
check(
    "material dual nombra exactamente foto de tela, madera y mueble en AIS, ChatGPT y guía",
    'Image 1 (FABRIC SWATCH GROUND TRUTH · FILE: "LINO_ARENA_04.jpg")' in _m_ais
    and 'Image 2 (WOOD SAMPLE GROUND TRUTH · FILE: "NOGAL_AMERICANO.jpg")' in _m_ais
    and 'Image 3 (TARGET FURNITURE PIECE · FILE: "SOFA_MILAN_FRENTE.jpg")' in _m_ais
    and 'Image 1 ("LINO_ARENA_04.jpg")' in _m_ais
    and 'Image 3 ("SOFA_MILAN_FRENTE.jpg")' in _m_ais
    and 'Image 3 = "SOFA_MILAN_FRENTE.jpg"' in _m_dal
    and '"SOFA_MILAN_FRENTE.jpg"' in _r_mat_names["items"][0]["attachment_guide"][2],
)

_r_34_names = v7.build_34_derecha_2054_prompts(
    furniture_name="SILLA VERONA",
    tipo_mueble="SILLA",
    furniture_filenames=["SILLA_VERONA_ORIG.jpg"],
    fabric_label="BOUCLE CREMA",
    fabric_filename="BOUCLE_CREMA.jpg",
)
check(
    "3/4 Derecha 2054 incluye nombres exactos de foto copiada en AIS, ChatGPT y guía",
    'FILE: "SILLA_VERONA_ORIG.jpg"' in _r_34_names["items"][0]["google_ai_studio"]
    and 'FILE: "BOUCLE_CREMA.jpg"' in _r_34_names["items"][0]["google_ai_studio"]
    and 'Image 1 = "SILLA_VERONA_ORIG.jpg"' in _r_34_names["items"][0]["chatgpt_dalle3"]
    and 'SILLA_VERONA_ORIG.jpg' in _r_34_names["items"][0]["attachment_guide"][0],
)

_r_clone_names = v7.build_prompts(
    mode="clonar_color",
    furniture_name="COMEDOR_BASE",
    tipo_mueble="COMEDOR",
    furniture_filenames=["COMEDOR_PAROTA_BASE.jpg"],
    batch_ref_filename="COMEDOR_PAROTA_BASE.jpg",
    batch_ref_bytes=b"fake_ref",
    batch_views=[("COMEDOR_VISTA_LATERAL.jpg", b"v1")],
)
check(
    "clonar_color incluye nombre exacto de foto base y foto vista en prompt y guía",
    'FILE: "COMEDOR_PAROTA_BASE.jpg"' in _r_clone_names["items"][0]["google_ai_studio"]
    and 'FILE: "COMEDOR_VISTA_LATERAL.jpg"' in _r_clone_names["items"][0]["google_ai_studio"]
    and '"COMEDOR_PAROTA_BASE.jpg"' in _r_clone_names["items"][0]["attachment_guide"][0]
    and '"COMEDOR_VISTA_LATERAL.jpg"' in _r_clone_names["items"][0]["attachment_guide"][1],
)

check(
    "tira copiar foto usa Blob directo compatible con Safari/iOS y envía dataUri + dataUrl sin writeText",
    "new targetWin.File(" not in _strip_html
    and "new File(" not in _strip_html
    and "dataUri: dataUri" in _strip_html
    and "dataUrl: dataUri" in _strip_html
    and "SILLON ANKARA.jpg" in _strip_html
    and "writeText" not in _strip_html,
)

# 19. Estabilidad Render 512 MB (evitar reinicio OOM al seleccionar 1 foto pesada)
from services.sheets_service import _BoundedBytesLRU  # noqa: E402
from modules.ui_helpers import make_thumbnail_bytes as _make_thumb  # noqa: E402

_big_img = _Image.new("RGB", (4000, 3000), (220, 210, 195))
for _bx in range(0, 4000, 40):
    _big_img.putpixel((_bx, 1500), (80, 60, 45))
_big_buf = _io.BytesIO()
_big_img.save(_big_buf, format="PNG")
_big_raw = _big_buf.getvalue()

_cp_big_b, _cp_big_m = prepare_exact_copy_image_bytes(_big_raw)
with _Image.open(_io.BytesIO(_cp_big_b)) as _cp_big_im:
    _w_big, _h_big = _cp_big_im.size
    check(
        "prepare_exact_copy_image_bytes acota fotos gigantes a <=1600px conservando proporción y <1MB",
        max(_w_big, _h_big) <= 1600
        and abs((_w_big / _h_big) - (4000 / 3000)) < 0.02
        and len(_cp_big_b) < 1_000_000
        and _cp_big_m == "image/jpeg",
    )

_big_thumb = _make_thumb(_big_raw, max_dim=260)
with _Image.open(_io.BytesIO(_big_thumb)) as _bt_im:
    check(
        "make_thumbnail_bytes reduce foto gigante a miniatura ligera <=260px",
        max(_bt_im.size) <= 260 and len(_big_thumb) < 60_000,
    )

_lru = _BoundedBytesLRU(max_full_entries=3, max_full_bytes=1024, max_thumb_entries=3, max_thumb_bytes=512)
_lru["f1"] = b"a" * 600
_lru["f2"] = b"b" * 600
_lru["thumb:t1"] = b"t" * 300
_lru["thumb:t2"] = b"u" * 300
check(
    "_BoundedBytesLRU aplica tope estricto en bytes por pool sin borrar miniaturas al eviccionar fotos",
    "f1" not in _lru
    and "f2" in _lru
    and "thumb:t1" not in _lru
    and "thumb:t2" in _lru
    and _lru.total_bytes() <= 1024 + 512,
)

_full_dl_called = []
_orig_get_full = _ss.get_drive_file_bytes
_orig_dl_thumb = _ss._download_thumbnail_url
_orig_drive_t = _ss.drive_service
_orig_ensure_t = _ss.ensure_connected
try:
    _ss.ensure_connected = lambda: True
    _ss.drive_service = None
    _ss._download_thumbnail_url = lambda url: None
    _ss.get_drive_file_bytes = lambda fid, raise_on_error=False: (_full_dl_called.append(fid) or b"raw")
    _th_none = _ss.get_drive_thumbnail_bytes("no_thumb_id_xyz", "https://expired.invalid/t=s220", allow_full_fallback=False)
finally:
    _ss.get_drive_file_bytes = _orig_get_full
    _ss._download_thumbnail_url = _orig_dl_thumb
    _ss.drive_service = _orig_drive_t
    _ss.ensure_connected = _orig_ensure_t

check(
    "get_drive_thumbnail_bytes nunca descarga archivo completo pesado cuando allow_full_fallback=False",
    _th_none is None and len(_full_dl_called) == 0,
)

_repo_root = Path(__file__).resolve().parent.parent
_render_yaml = (_repo_root / "render.yaml").read_text(encoding="utf-8")
check(
    "configuración Render/Streamlit evita reinicios (fileWatcherType=none, sin compresión WS, MALLOC_ARENA_MAX, caché fuera del repo, popover ocioso sin red)",
    'fileWatcherType = "none"' in _cfg_toml
    and "enableWebsocketCompression = false" in _cfg_toml
    and "MALLOC_ARENA_MAX" in _render_yaml
    and _ss._catalog_disk_cache_path.resolve().parent != _repo_root.resolve()
    and "if q_clean and matches:" in _v7_src
    and "var pngBlobPromise =" not in _strip_html,
)

# 20. Fix StreamlitAPIException, Zoom Lock, iOS/Android/PC polish, Cola Compartida, Drive fixes, Gemini runtime y Clear
import concurrent.futures as _cf  # noqa: E402
import streamlit as _st_live  # noqa: E402
import main as _main_mod  # noqa: E402
from services.sheets_service import (  # noqa: E402
    BUZON_DRIVE_ID as _BUZON_ID,
    RENDER_DRIVE_ID as _RENDER_ID,
    SUBIR_DRIVE_ID as _SUBIR_ID,
)
from modules.alta_fotos_hub import (  # noqa: E402
    IMG_AND_DOC_TYPES as _IMG_DOC_TYPES,
    _clear_alta_form,
    build_dest_folder_options,
    is_image_filename,
)
from modules.prompt_studio_v7 import _clear_v7_form  # noqa: E402

# 20.1 Staging key _pending_active_app (sin mutar unified_active_app tras crear el widget)
check(
    "cambio entre Prompts y Alta de Fotos usa _pending_active_app antes del selectbox (sin StreamlitAPIException)",
    'st.session_state.pop("_pending_active_app", None)' in _main_src
    and 'st.session_state["_pending_active_app"] = "🤖 Prompts + IA"' in _main_src
    and 'st.session_state["_pending_active_app"] = "🚀 Alta de Fotos"' in _v7_src
    and 'st.session_state["unified_active_app"] = "🚀 Alta de Fotos"' not in _v7_src
    and _main_src.count('st.session_state["unified_active_app"] =') <= 2,
)

# 20.2 Zoom Lock + Android / iOS / PC CSS
_zoom_html = _main_mod.get_zoom_lock_html()
check(
    "zoom lock bloquea pinch iOS, multi-touch, ctrl+wheel y ctrl+teclado con guarda __buenaZoomLockInstalled",
    "__buenaZoomLockInstalled" in _zoom_html
    and "user-scalable=no" in _zoom_html
    and "viewport-fit=cover" in _zoom_html
    and "gesturestart" in _zoom_html
    and "gesturechange" in _zoom_html
    and "gestureend" in _zoom_html
    and "touches.length > 1" in _zoom_html
    and '"wheel"' in _zoom_html
    and '"keydown"' in _zoom_html
    and "touch-action: pan-x pan-y" in _main_src
    and "-webkit-text-size-adjust: 100%" in _main_src
    and "@media (pointer: coarse)" in _main_src
    and "font-size: 16px !important;" in _main_src
    and "@media (pointer: coarse)" in _v7_src
    and "font-size: 16px !important;" in _v7_src,
)

# 20.3 MIME detection (sin extensión, .jfif, .heic, documentos)
check(
    "guess_mime_type detecta imágenes (.jfif, .heic, sin ext) y documentos (.pdf, .docx, .xlsx, .csv, .txt, .pptx, .zip)",
    _ss.guess_mime_type("foto_sin_ext", default="image/png") == "image/png"
    and _ss.guess_mime_type("foto_sin_ext") == "application/octet-stream"
    and _ss.guess_mime_type("foto.jfif") == "image/jpeg"
    and _ss.guess_mime_type("iphone.HEIC") == "image/heic"
    and _ss.guess_mime_type("cotizacion.pdf") == "application/pdf"
    and _ss.guess_mime_type("ficha.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    and _ss.guess_mime_type("precios.xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    and _ss.guess_mime_type("lista.csv") == "text/csv"
    and _ss.guess_mime_type("notas.txt") == "text/plain"
    and _ss.guess_mime_type("presentacion.pptx") == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    and _ss.guess_mime_type("paquete.zip") == "application/zip",
)

# 20.4 Carpeta activa de staging (Buzón activo vs papelera -> RENDER, nunca SUBIR PREN) + listado fotos y documentos + invalidación de caché
class _MockStageFilesApi:
    def __init__(self, calls, folder_metas, list_items):
        self._calls = calls
        self._folder_metas = folder_metas
        self._list_items = list_items

    def get(self, **kw):
        self._calls.append(("get", kw))
        fid = kw.get("fileId", "")
        if fid in self._folder_metas:
            return _FakeExec(self._folder_metas[fid])
        raise RuntimeError("404 not found")

    def list(self, **kw):
        self._calls.append(("list", kw))
        q = kw.get("q", "")
        if "mimeType = 'application/vnd.google-apps.folder'" in q or "mimeType='application/vnd.google-apps.folder'" in q:
            return _FakeExec({"files": self._list_items.get("folders", [])})
        return _FakeExec({"files": self._list_items.get("files", [])})

    def create(self, **kw):
        self._calls.append(("create", kw))
        return _FakeExec({"id": "created_doc_999", "name": kw["body"]["name"], "webViewLink": "https://drive.google.com/file/d/created_doc_999/view"})

    def update(self, **kw):
        self._calls.append(("update", kw))
        return _FakeExec({"id": kw.get("fileId"), "trashed": True})


class _MockStageDrive:
    def __init__(self, calls, folder_metas, list_items):
        self._calls = calls
        self._folder_metas = folder_metas
        self._list_items = list_items

    def files(self):
        return _MockStageFilesApi(self._calls, self._folder_metas, self._list_items)

    def permissions(self):
        return _FakePermsApi(self._calls)


_stg_calls = []
_orig_d2 = _ss.drive_service
_orig_e2 = _ss.ensure_connected
try:
    _ss.ensure_connected = lambda: True
    # Caso A: Buzón en papelera -> debe resolver a RENDER_DRIVE_ID (nunca SUBIR_DRIVE_ID)
    _ss.drive_service = _MockStageDrive(
        _stg_calls,
        folder_metas={_BUZON_ID: {"id": _BUZON_ID, "name": "Buzon", "trashed": True}},
        list_items={
            "folders": [{"id": "SUB_RENDER_1"}],
            "files": [
                {"id": "img_1", "name": "sillon.heic", "mimeType": "image/heic", "size": "2048", "modifiedTime": "2026-11-26T01:00:00Z", "webViewLink": "https://drive.google.com/file/d/img_1/view"},
                {"id": "doc_1", "name": "cotizacion.pdf", "mimeType": "application/pdf", "size": "4096", "modifiedTime": "2026-11-26T03:00:00Z", "webViewLink": "https://drive.google.com/file/d/doc_1/view"},
                {"id": "doc_2", "name": "precios.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "size": "1024", "modifiedTime": "2026-11-26T02:00:00Z"},
                {"id": "fld_x", "name": "Subcarpeta", "mimeType": "application/vnd.google-apps.folder", "modifiedTime": "2026-11-26T04:00:00Z"},
                {"id": "dot_x", "name": ".hidden.jpg", "mimeType": "image/jpeg", "modifiedTime": "2026-11-26T05:00:00Z"},
            ],
        },
    )
    _buzon_active_false = _ss.is_drive_folder_active(_BUZON_ID)
    _resolved_trashed = _ss.resolve_active_staging_folder_id()
    _staged_list = _ss.list_shared_staging_files(folder_id=_resolved_trashed)

    # Caso B: Buzón activo -> debe resolver a BUZON_DRIVE_ID
    _ss.drive_service = _MockStageDrive(
        _stg_calls,
        folder_metas={_BUZON_ID: {"id": _BUZON_ID, "name": "Buzon", "trashed": False}},
        list_items={"folders": [{"id": "SUB_F1"}], "files": [{"id": "hit_1", "name": "Sillon_Ankara.jpg", "mimeType": "image/jpeg"}]},
    )
    _buzon_active_true = _ss.is_drive_folder_active(_BUZON_ID)
    _resolved_active = _ss.resolve_active_staging_folder_id()

    # Caso C: search_drive_images_live acotado a folder_id + subcarpetas
    _ss._drive_subfolder_ids_cache.clear()
    _stg_calls.clear()
    _search_hits = _ss.search_drive_images_live("Sillon Ankara", limit=10, folder_id="ROOT_MUEBLES_99")
    _search_list_queries = [kw.get("q", "") for tag, kw in _stg_calls if tag == "list"]

    # Caso D: get_or_create_drive_folder escapa comillas simples
    _stg_calls.clear()
    _ss.get_or_create_drive_folder("PARENT_1", "O'Brien's Sofa")
    _folder_queries = [kw.get("q", "") for tag, kw in _stg_calls if tag == "list"]

    # Caso E: upload_file_bytes_to_drive + trash_drive_file invalidan _drive_folder_tree_cache y archivo en disco
    _ss._drive_folder_tree_cache["dummy:1:4"] = (12345.0, [{"id": "old"}])
    _ss._save_disk_catalog_cache()
    _disk_existed_before = _ss._catalog_disk_cache_path.exists()
    _up_doc_link = _ss.upload_file_bytes_to_drive(b"%PDF-1.4 test", "ficha.pdf", _RENDER_ID)
    _cache_cleared_on_up = (len(_ss._drive_folder_tree_cache) == 0) and (not _ss._catalog_disk_cache_path.exists())

    _ss._drive_folder_tree_cache["dummy2:1:4"] = (12345.0, [{"id": "old2"}])
    _ss._save_disk_catalog_cache()
    _trashed_ok = _ss.trash_drive_file("created_doc_999")
    _cache_cleared_on_trash = (len(_ss._drive_folder_tree_cache) == 0) and (not _ss._catalog_disk_cache_path.exists())

    # Caso F: publish_photo_and_get_urls devuelve =s2048 (no =s2054)
    _pub_res = _ss.publish_photo_and_get_urls(b"pngbytes", "SILLON_OUT.png", dest="render")
finally:
    _ss.drive_service = _orig_d2
    _ss.ensure_connected = _orig_e2

check(
    "is_drive_folder_active y resolve_active_staging_folder_id caen a RENDER (nunca SUBIR PREN) si Buzón está en papelera",
    (not _buzon_active_false)
    and _resolved_trashed == _RENDER_ID
    and _resolved_trashed != _SUBIR_ID
    and _buzon_active_true
    and _resolved_active == _BUZON_ID,
)
check(
    "list_shared_staging_files lista fotos y documentos ordenados por fecha desc excluyendo carpetas y ocultos",
    len(_staged_list) == 3
    and [x["id"] for x in _staged_list] == ["doc_1", "doc_2", "img_1"]
    and [x["kind"] for x in _staged_list] == ["document", "document", "image"]
    and all(k in _staged_list[0] for k in ("id", "name", "mimeType", "kind", "size", "modifiedTime", "webViewLink", "thumbnailLink")),
)
check(
    "search_drive_images_live acota consultas estrictamente a folder_id y subcarpetas",
    len(_search_hits) == 1
    and any("'ROOT_MUEBLES_99' in parents" in q and "'SUB_F1' in parents" in q and "name contains 'Sillon'" in q for q in _search_list_queries),
)
check(
    "get_or_create_drive_folder escapa comillas simples en folder_name",
    any("name='O\\'Brien\\'s Sofa'" in q for q in _folder_queries),
)
check(
    "upload_file_bytes_to_drive y trash_drive_file invalidan caché RAM y JSON temporal en disco + CDN =s2048",
    _disk_existed_before
    and bool(_up_doc_link)
    and _cache_cleared_on_up
    and _trashed_ok
    and _cache_cleared_on_trash
    and _pub_res.get("direct_cdn_url", "").endswith("=s2048")
    and "=s2054" not in _pub_res.get("direct_cdn_url", ""),
)

# 20.5 update_product_row_safe pasa tipo correcto y register_many_in_fotos_normalizadas actualiza enlaces obsoletos
class _MockSheetValues:
    def __init__(self, rows, batch_calls):
        self._rows = rows
        self._batch_calls = batch_calls

    def get(self, **kw):
        return _FakeExec({"values": self._rows})

    def batchUpdate(self, **kw):
        self._batch_calls.append(kw)
        return _FakeExec({})


class _MockSpreadsheets:
    def __init__(self, rows, batch_calls):
        self._rows = rows
        self._batch_calls = batch_calls

    def values(self):
        return _MockSheetValues(self._rows, self._batch_calls)


class _MockSheetsApi:
    def __init__(self, rows, batch_calls):
        self._rows = rows
        self._batch_calls = batch_calls

    def spreadsheets(self):
        return _MockSpreadsheets(self._rows, self._batch_calls)


_seen_tipos = []
_batch_upd_calls = []
_orig_svc_s = _ss.service
_orig_ens_s = _ss.ensure_connected
_orig_buscar = _ss.buscar_link_drive_inteligente
_orig_tab_dg = _ss._sheet_name_datos_general
_orig_tab_fn = _ss._sheet_name_fotos_norm
try:
    _ss.ensure_connected = lambda: True
    _ss._sheet_name_datos_general = "DATOS GENERAL"
    _ss._sheet_name_fotos_norm = "FOTOS NORMALIZADAS"
    _ss.buscar_link_drive_inteligente = lambda nom, tipo="MUEBLE": (_seen_tipos.append((nom, tipo)) or f"https://drive.google.com/file/d/{tipo.lower()}_id/view")
    _existing_fn_rows = [
        ["", "SILLON_OLD", "", "https://drive.google.com/file/d/stale_link/view"],
    ]
    _ss.service = _MockSheetsApi(_existing_fn_rows, _batch_upd_calls)
    _ss.update_product_row_safe(
        4,
        {
            "fotos": {
                "mueble_nombre": "M1",
                "tela_nombre": "T1",
                "madera_nombre": "MD1",
                "swatch_nombre": "SW1",
            }
        },
    )
    _batch_fn_calls = []
    _ss.service = _MockSheetsApi(_existing_fn_rows, _batch_fn_calls)
    _ss.register_many_in_fotos_normalizadas([
        {"tipo": "MUEBLE", "nombre": "SILLON_OLD", "link": "https://drive.google.com/file/d/new_fresh_link/view"},
    ])
finally:
    _ss.service = _orig_svc_s
    _ss.ensure_connected = _orig_ens_s
    _ss.buscar_link_drive_inteligente = _orig_buscar
    _ss._sheet_name_datos_general = _orig_tab_dg
    _ss._sheet_name_fotos_norm = _orig_tab_fn

check(
    "update_product_row_safe pasa tipo MUEBLE/TELA/MADERA/SWATCH y register_many actualiza enlaces obsoletos",
    _seen_tipos == [("M1", "MUEBLE"), ("T1", "TELA"), ("MD1", "MADERA"), ("SW1", "SWATCH")]
    and len(_batch_fn_calls) == 1
    and _batch_fn_calls[0]["body"]["data"][0]["range"] == "'FOTOS NORMALIZADAS'!D4"
    and _batch_fn_calls[0]["body"]["data"][0]["values"] == [["https://drive.google.com/file/d/new_fresh_link/view"]],
)

# 20.6 Alta de Fotos: documentos + Buzón papelera + Limpiar sin reiniciar checkboxes
_dest_trashed = build_dest_folder_options(buzon_active=False)
_orig_rerun = _st_live.rerun
_rerun_hits = []
try:
    _st_live.rerun = lambda *a, **kw: _rerun_hits.append(True)
    _st_live.session_state["v7_last_photo_stem"] = "SILLON_VIEJO"
    _st_live.session_state["alta_2054"] = True
    _st_live.session_state["alta_reg"] = False
    _st_live.session_state["alta_clear_tick"] = 0
    _clear_alta_form(0)
    _alta_clear_ok = (
        "v7_last_photo_stem" not in _st_live.session_state
        and _st_live.session_state.get("alta_2054") is True
        and _st_live.session_state.get("alta_reg") is False
        and _st_live.session_state.get("alta_clear_tick") == 1
    )

    # 20.7 _clear_v7_form limpia v7_last_photo_stem y v7_last_sku preservando modo y sub-opciones
    _st_live.session_state.update({
        "v7_keep_mode": "Tela / Madera",
        "v7_keep_matmode": "Solo tela",
        "v7_keep_vista": "3/4 Derecha",
        "v7_keep_room": "Sala",
        "v7_keep_folder": "🛋️ RENDER",
        "v7_last_photo_stem": "SILLON_VIEJO",
        "v7_last_sku": "SKU-999",
        "v7_result": {"items": []},
        "sku_input_v7": "SKU-999",
        "clear_key_v7": 2,
    })
    _clear_v7_form(2)
    _v7_clear_ok = (
        "v7_last_photo_stem" not in _st_live.session_state
        and "v7_last_sku" not in _st_live.session_state
        and "v7_result" not in _st_live.session_state
        and "sku_input_v7" not in _st_live.session_state
        and _st_live.session_state.get("v7_keep_mode") == "Tela / Madera"
        and _st_live.session_state.get("v7_keep_matmode") == "Solo tela"
        and _st_live.session_state.get("v7_keep_vista") == "3/4 Derecha"
        and _st_live.session_state.get("v7_keep_room") == "Sala"
        and _st_live.session_state.get("v7_keep_folder") == "🛋️ RENDER"
        and _st_live.session_state.get("clear_key_v7") == 3
    )
finally:
    _st_live.rerun = _orig_rerun

check(
    "Alta de Fotos soporta documentos, marca Buzón en papelera con fallback RENDER y Limpiar conserva checkboxes",
    "pdf" in _IMG_DOC_TYPES
    and "docx" in _IMG_DOC_TYPES
    and "xlsx" in _IMG_DOC_TYPES
    and not is_image_filename("cotizacion.pdf")
    and resolve_upload_filename("cotizacion.pdf", "COT_01", 1, 1, True) == ("COT_01.pdf", "COT_01")
    and any("papelera" in k and v[0] == _RENDER_ID for k, v in _dest_trashed.items())
    and _alta_clear_ok,
)
check(
    "_clear_v7_form limpia v7_last_photo_stem y v7_last_sku preservando modo/sub-opciones y TTL catálogo = 120s",
    _v7_clear_ok
    and "@st.cache_data(ttl=120" in _v7_src,
)

# 20.8 HEIC + Gemini runtime (8s/16s + aislamiento por hilo) + format_gemini_error + RENDER_DEPLOY.md
_req_txt = (_repo_root / "requirements.txt").read_text(encoding="utf-8")
_ui_src = (_repo_root / "modules" / "ui_helpers.py").read_text(encoding="utf-8")
_ai_src = (_repo_root / "services" / "ai_prompt_service_v7.py").read_text(encoding="utf-8")
_deploy_md = (_repo_root / "RENDER_DEPLOY.md").read_text(encoding="utf-8")

_gr.reset_runtime_state()


def _worker_meta(idx: int):
    def _h(model, contents, config=None):
        if idx == 0:
            raise RuntimeError("401 UNAUTHENTICATED")
        return _FakeGeminiResp('{"ok": true}')

    cli = _FakeGenaiClient(_h)
    try:
        _gr.call_gemini_fast(cli, ["test"], api_key=f"k_{idx}")
    except Exception:
        pass
    return _gr.get_last_vision_meta()


with _cf.ThreadPoolExecutor(max_workers=2) as _ex_meta:
    _m0_fut = _ex_meta.submit(_worker_meta, 0)
    _m1_fut = _ex_meta.submit(_worker_meta, 1)
    _m0, _m1 = _m0_fut.result(), _m1_fut.result()
_gr.reset_runtime_state()

check(
    "HEIC, gemini_runtime (8s/16s + meta por hilo), format_gemini_error sin botón inexistente y RENDER_DEPLOY V7",
    "pillow-heif>=0.18.0" in _req_txt
    and "register_heif_opener()" in _ui_src
    and "register_heif_opener()" in _ai_src
    and _gr.DEFAULT_TIMEOUT_MS == 8_000
    and _gr.MAX_WALL_SECONDS == 16.0
    and (_m0["used_ai"] is False and _m1["used_ai"] is True)
    and "🔑 API Key" not in v7.format_gemini_error(RuntimeError("403 LEAKED"))
    and "🔑 API Key" not in v7.format_gemini_error(RuntimeError("401 API_KEY_INVALID"))
    and "V7" in _deploy_md,
)

print(f"\n{'OK' if not FAILS else 'FALLARON: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)

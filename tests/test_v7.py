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

# 13. Helpers de URL Drive, carpeta única RENDER y diagnóstico claro de API key filtrada (403 leaked)
from services.sheets_service import sheets_service as _ss  # noqa: E402
from modules.prompt_studio_v7 import FOLDER_MUEBLES_RENDER_DRIVE_ID, LOCAL_RENDER_MUEBLES_DIR, _build_zip as _build_zip_v7  # noqa: E402

check(
    "extract_drive_id extrae ID limpio de link Drive",
    _ss.extract_drive_id("https://drive.google.com/file/d/1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B/view?usp=sharing")
    == "1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B"
    and _ss.extract_drive_id("https://drive.google.com/drive/folders/1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX")
    == "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX",
)
check(
    "carpeta unica RENDER configurada para muebles",
    FOLDER_MUEBLES_RENDER_DRIVE_ID == "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX"
    and LOCAL_RENDER_MUEBLES_DIR.name == "RENDER",
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
        "zip empaqueta prompts e insumos limpiamente",
        any(n.startswith("prompts/") and n.endswith(".txt") for n in _names)
        and any(n.startswith("insumos/") for n in _names),
    )

print(f"\n{'OK' if not FAILS else 'FALLARON: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)

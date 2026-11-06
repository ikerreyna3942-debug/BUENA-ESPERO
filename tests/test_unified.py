"""Pruebas del Estudio V6. Ejecutar:  python tests/test_unified.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import unified_prompt_service as ups  # noqa: E402

FAILS = []


def check(name, cond):
    print(("[PASS] " if cond else "[FAIL] ") + name)
    if not cond:
        FAILS.append(name)


def build(mode, tipo, medidas, **kw):
    return ups.build_prompts(
        mode=mode,
        furniture_name="PRUEBA",
        tipo_mueble=tipo,
        medidas_texto=medidas,
        furniture_filenames=["foto.jpg"],
        **kw,
    )


# --- parseo de medidas
d = ups.parse_dimensions("MESA DE CENTRO", "138 cm frente x 70 cm fondo x 38 cm alto")
check("mesa: 138/70/38", (d["width_cm"], d["depth_cm"], d["height_cm"]) == (138, 70, 38))
d = ups.parse_dimensions("MESA LATERAL", "46 cm diam x 44 cm alto")
check("mesa redonda: diam 46 alto 44", (d["diam_cm"], d["height_cm"]) == (46, 44))
d = ups.parse_dimensions("ESPEJO", "80 cm frente x 120 cm fondo x 4 cm alto")
check("espejo: alto 120, grosor 4", (d["height_cm"], d["depth_cm"]) == (120, 4))
d = ups.parse_dimensions("MESA", "authentic 3D geometry 138 cm frente")
check("'3D' no se lee como medida", d["depth_cm"] is None)
check("compose", ups.compose_dimensions_text(80, 4, 120, 0) == "80 cm frente x 4 cm fondo x 120 cm alto")

# --- catalogo
r = build("catalogo", "MESA DE CENTRO", "138 cm frente x 70 cm fondo x 38 cm alto")
ids = [i["id"] for i in r["items"]]
check("catalogo: 7 items en orden", ids == ups.VIEW_IDS)
check("catalogo: maestro AIS", "CRITICAL ROTATION RULE" in r["master_ais"])
check("catalogo: vista 2 con ancla", "ANCHOR IMAGE" in r["items"][1]["google_ai_studio"])
check("catalogo: vista 1 sin ancla", "ANCHOR IMAGE" not in r["items"][0]["google_ai_studio"])
check("catalogo: plano con medidas", "Alto: 38" in r["items"][5]["google_ai_studio"])
check("catalogo: checklist en todas", all(i["checklist"] for i in r["items"]))
check("catalogo (mesa): sigue hablando de tabletop", "tabletop" in r["master_ais"])

# --- espejo
r = build("catalogo", "ESPEJO", "80 cm frente x 4 cm fondo x 120 cm alto")
t = r["master_ais"]
check("espejo: escala 80x120x4", "Width/Frente: 80 cm" in t and "Height/Alto: 120 cm" in t and "Depth/Fondo: 4 cm" in t)
check("espejo: sin patas/credenza", "NOT a tall credenza" not in t and "tabletop color" not in t)
check("espejo: contorno organico", "organic asymmetric" in t)

# --- otros modos
r = build("vista_suelta", "MESA", "100 cm frente x 50 cm fondo x 45 cm alto", vista_id="vista_lateral")
check("vista suelta: 1 item lateral", len(r["items"]) == 1 and r["items"][0]["id"] == "vista_lateral")
r = build("entorno", "MESA", "100 cm frente x 50 cm fondo x 45 cm alto")
check("entorno: 1 item", len(r["items"]) == 1 and r["items"][0]["id"] == "vista_entorno_cliente")
check("entorno: escala y contraste", "CONTRAST" in r["items"][0]["google_ai_studio"] and "Alto: 45" in r["items"][0]["google_ai_studio"])
r = build("plano", "MESA", "100 cm frente x 50 cm fondo x 45 cm alto")
check("plano: 1 item", len(r["items"]) == 1 and r["items"][0]["id"] == "vista_plano_tecnico")
for m in ("extraer", "hd"):
    r = build(m, "MESA", "100 cm frente x 50 cm fondo x 45 cm alto")
    check(f"{m}: prompt no vacio", len(r["items"]) == 1 and len(r["items"][0]["google_ai_studio"]) > 100)
for mm in ("wood_only", "fabric_only", "dual"):
    r = build("material", "SILLA", "50 cm frente x 50 cm fondo x 90 cm alto", material_mode=mm)
    check(f"material {mm}: prompt no vacio", len(r["items"][0]["google_ai_studio"]) > 100)

# --- advertencias
check("warn: sin medidas", len(ups.sanity_warnings("table", 0, 0, 0, 0)) == 1)
check("warn: espejo alto raro", len(ups.sanity_warnings("mirror", 80, 120, 4, 0)) >= 1)

print(f"\n{'OK' if not FAILS else 'FALLARON: ' + ', '.join(FAILS)}")
sys.exit(1 if FAILS else 0)

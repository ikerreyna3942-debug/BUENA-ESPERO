"""
Servicio unificado del Estudio (V6).

Una sola entrada (`build_prompts`) para todos los modos:
catalogo, vista_suelta, material, entorno, plano, extraer, hd.

Reutiliza el motor probado `ai_prompt_service_v5` (análisis con Gemini Vision,
perfiles por categoría, bloques de identidad/medidas/fondo blanco) y le suma:
  * medidas confirmables (un único lugar donde se interpretan),
  * anclaje con la Vista 1 aprobada para las demás vistas,
  * checklist de revisión por imagen,
  * advertencias cuando los datos del SKU parecen contradictorios.
"""
from typing import Any, Dict, List, Optional

MODES = {
    "catalogo": "Catálogo completo (7 imágenes)",
    "vista_suelta": "Una sola vista (tú eliges cuál)",
    "material": "Cambio de material (madera / tela)",
    "entorno": "Entorno en casa de cliente",
    "plano": "Plano técnico con medidas",
    "extraer": "Extraer mueble en fondo blanco",
    "hd": "Mejora HD",
}

VIEW_IDS = [
    "vista_frontal",
    "vista_perspectiva_3_4",
    "vista_lateral",
    "vista_picada_alta",
    "vista_superior_cenital",
    "vista_plano_tecnico",
    "vista_entorno_cliente",
]

ANCHOR_VIEWS = {
    "vista_perspectiva_3_4",
    "vista_lateral",
    "vista_picada_alta",
    "vista_superior_cenital",
    "vista_entorno_cliente",
}

ANCHOR_BLOCK_AIS = (
    "\n\nANCHOR IMAGE (MANDATORY WHEN ATTACHED): Image 2 is the APPROVED Vista 1 render of this exact piece. "
    "Copy its exact outline, proportions, color, grain and finish. Change ONLY the camera angle. "
    "If Image 2 is not attached, use Image 1 as the only identity reference. "
    "Do NOT repeat the angle of Image 1 or Image 2."
)
ANCHOR_BLOCK_DAL = (
    "\n\nANCHOR IMAGE: Use the approved Vista 1 image (if attached) as the exact identity reference: "
    "same outline, proportions, color, grain and finish. Change only the camera angle."
)

_COMMON_CHECKS = [
    "¿Es el MISMO mueble (contorno, proporciones, color y textura) que la foto original?",
    "¿No inventó patas, puertas, cajones ni piezas que no están en la foto?",
]
_WHITE_CHECKS = [
    "¿Fondo blanco puro, sin piso, sin sombra y sin reflejo?",
]

CHECKLISTS: Dict[str, List[str]] = {
    "vista_frontal": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Está de frente, a 0°, centrado?"],
    "vista_perspectiva_3_4": _COMMON_CHECKS + _WHITE_CHECKS + ["¿El ángulo cambió a 3/4 (≈45°) respecto a la Vista 1?"],
    "vista_lateral": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Es un perfil lateral estricto a 90°?"],
    "vista_picada_alta": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Se ve desde arriba (60°–70°) y no de frente?"],
    "vista_superior_cenital": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Es vista cenital a 90° (plano desde arriba)?"],
    "vista_plano_tecnico": [
        "¿Solo líneas negras, sin color, sin sombras y sin texturas?",
        "¿Solo 3 cotas (alto a la izquierda, fondo abajo-izquierda, ancho abajo)?",
        "¿Los números coinciden con las medidas confirmadas?",
    ],
    "vista_entorno_cliente": [
        "¿Toma lejana, con el cuarto completo visible?",
        "¿El mueble tiene la escala correcta respecto al tapete y los otros muebles?",
        "¿Los colores del entorno contrastan con el mueble (no se camufla)?",
        "¿Se ve como la casa de un cliente, con otros muebles?",
    ],
    "extraer": _COMMON_CHECKS + _WHITE_CHECKS + ["¿Está centrado con márgenes parejos?"],
    "hd": _COMMON_CHECKS + ["¿Más nítido pero SIN cambiar color, forma ni textura?"],
    "material": [
        "¿La forma del mueble no cambió?",
        "¿El nuevo material coincide con la muestra (tono, veta o tejido)?",
        "¿Todas las piezas del mismo material quedaron del mismo tono?",
    ],
}


def parse_dimensions(tipo_mueble: str, medidas_texto: str) -> Dict[str, Any]:
    """Interpreta el texto de medidas con el mismo motor que usan los prompts."""
    from services.ai_prompt_service_v5 import ai_prompt_service_v5 as v5

    profile = v5._detect_furniture_profile(tipo_mueble or "", medidas_texto or "", "")
    return {
        "category": profile["category"],
        "width_cm": profile.get("width_cm"),
        "depth_cm": profile.get("depth_cm"),
        "height_cm": profile.get("height_cm"),
        "diam_cm": profile.get("diam_cm"),
    }


def compose_dimensions_text(
    width: float = 0, depth: float = 0, height: float = 0, diam: float = 0
) -> str:
    """Convierte los campos confirmados por el usuario en un texto canónico."""
    parts: List[str] = []
    if diam:
        parts.append(f"{int(diam)} cm diam")
    if width:
        parts.append(f"{int(width)} cm frente")
    if depth:
        parts.append(f"{int(depth)} cm fondo")
    if height:
        parts.append(f"{int(height)} cm alto")
    return " x ".join(parts)


def sanity_warnings(category: str, width: float, depth: float, height: float, diam: float) -> List[str]:
    """Advertencias para datos de SKU que probablemente estén mal."""
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
        w.append("No se reconoció el tipo de mueble: se usarán reglas genéricas. Escribe el tipo (mesa, espejo, silla...).")
    return w


def _wrap_single(prompts: Dict[str, Any], item_id: str, label: str, icon: str, short: str) -> Dict[str, Any]:
    item = {
        "id": item_id,
        "label": label,
        "short_name": short,
        "icon": icon,
        "google_ai_studio": prompts.get("google_ai_studio", ""),
        "chatgpt_dalle3": prompts.get("chatgpt_dalle3", ""),
        "checklist": CHECKLISTS.get(item_id, _COMMON_CHECKS),
        "needs_anchor": False,
    }
    return {
        "items": [item],
        "master_ais": "",
        "master_dal": "",
        "midjourney": prompts.get("midjourney_v6", ""),
    }


def _catalog_items(prompts: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for v in prompts.get("individual_vistas", []):
        vid = v.get("id", "")
        ais = v.get("google_ai_studio", "")
        dal = v.get("chatgpt_dalle3", "")
        needs_anchor = vid in ANCHOR_VIEWS
        if needs_anchor:
            ais = ais + ANCHOR_BLOCK_AIS
            dal = dal + ANCHOR_BLOCK_DAL
        items.append({
            "id": vid,
            "label": v.get("label", vid),
            "short_name": v.get("short_name", vid),
            "icon": v.get("icon", "🖼️"),
            "google_ai_studio": ais,
            "chatgpt_dalle3": dal,
            "checklist": CHECKLISTS.get(vid, _COMMON_CHECKS),
            "needs_anchor": needs_anchor,
        })
    return items


def build_prompts(
    mode: str,
    furniture_name: str,
    furniture_analysis: Optional[Dict[str, Any]] = None,
    wood_analysis: Optional[Dict[str, Any]] = None,
    fabric_analysis: Optional[Dict[str, Any]] = None,
    notas_usuario: str = "",
    tipo_mueble: str = "",
    medidas_texto: str = "",
    furniture_filenames: Optional[List[str]] = None,
    wood_filenames: Optional[List[str]] = None,
    fabric_filenames: Optional[List[str]] = None,
    reference_filenames: Optional[List[str]] = None,
    foto_refs: Optional[Dict[str, str]] = None,
    vista_id: str = "vista_frontal",
    material_mode: str = "wood_only",
) -> Dict[str, Any]:
    """Punto de entrada único. Devuelve siempre la misma estructura."""
    from services.ai_prompt_service_v5 import ai_prompt_service_v5 as v5

    if mode not in MODES:
        raise ValueError(f"Modo desconocido: {mode}")

    common = dict(
        furniture_name=furniture_name,
        furniture_analysis=furniture_analysis,
        notas_usuario=notas_usuario,
        tipo_mueble_usuario=tipo_mueble,
        medidas_usuario=medidas_texto,
        foto_refs=foto_refs,
    )
    dims = parse_dimensions(tipo_mueble, medidas_texto)
    result: Dict[str, Any]

    if mode in ("catalogo", "vista_suelta", "entorno", "plano"):
        prompts = v5.generate_vistas_prompts(
            fabric_analysis=fabric_analysis,
            wood_analysis=wood_analysis,
            furniture_filenames=furniture_filenames,
            wood_filenames=wood_filenames,
            reference_filenames=reference_filenames,
            **common,
        )
        items = _catalog_items(prompts)
        if mode == "vista_suelta":
            items = [i for i in items if i["id"] == vista_id] or items[:1]
        elif mode == "entorno":
            items = [i for i in items if i["id"] == "vista_entorno_cliente"]
        elif mode == "plano":
            items = [i for i in items if i["id"] == "vista_plano_tecnico"]
        result = {
            "items": items,
            "master_ais": prompts.get("google_ai_studio", "") if mode == "catalogo" else "",
            "master_dal": prompts.get("chatgpt_dalle3", "") if mode == "catalogo" else "",
            "midjourney": prompts.get("midjourney_v6", "") if mode == "catalogo" else "",
        }
    elif mode == "material":
        prompts = v5.generate_material_swap_prompts(
            mode=material_mode,
            fabric_analysis=fabric_analysis,
            wood_analysis=wood_analysis,
            furniture_filenames=furniture_filenames,
            wood_filenames=wood_filenames,
            fabric_filenames=fabric_filenames,
            reference_filenames=reference_filenames,
            **common,
        )
        result = _wrap_single(prompts, "material", "Cambio de material", "🎨", "Material")
    elif mode == "extraer":
        prompts = v5.generate_extraction_prompts(**common)
        result = _wrap_single(prompts, "extraer", "Extraer mueble (fondo blanco)", "⬜", "Extraer")
    else:  # hd
        prompts = v5.generate_hd_enhancement_prompts(**common)
        result = _wrap_single(prompts, "hd", "Mejora HD", "✨", "HD")

    result["mode"] = mode
    result["dims"] = dims
    result["warnings"] = sanity_warnings(
        dims["category"],
        dims["width_cm"] or 0,
        dims["depth_cm"] or 0,
        dims["height_cm"] or 0,
        dims["diam_cm"] or 0,
    )
    return result

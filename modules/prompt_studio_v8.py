"""
Interfaz de Estudio IA V8 (`render_prompt_studio_v8`).

Cumple estrictamente las 4 reglas de GEMINI.md sin modificar ningún archivo de V1–V7:
  1. Encabezado ultra limpio en 1 sola línea horizontal (modo + sub-opción + barra SKU/Mueble/Medidas),
     vistas previas propias de 76x76 px con zoom al pasar el cursor + botón 🖼️ Copiar foto (incluyendo
     automáticamente <mueble>_V8_LIENZO_ESCALA.png y <tela>_V8_LUZ30.png), cero credenciales en UI,
     y únicamente los 3 botones de acción (🚀 <Modo elegido>, ↘️ 3/4 Derecha, 🗑️ Borrar).
  2. Botón 🗑️ Borrar que limpia fotos, SKU, medidas, notas y resultados SIN reiniciar jamás
     v8_keep_mode ni las sub-opciones activas (v8_keep_vista, v8_keep_matmode, v8_keep_room, v8_keep_folder).
  3. Cobertura 100% en EL CASCO COMPLETO + cojines, escala física 1:1 (~97% reducción macro),
     calibración automática +30% CIELAB (0% deriva adicional), y toma 3/4 Derecha en #FFFFFF,
     0% sombras y 2054 x 2054 px exactos.
  4. Carga paralela (ThreadPoolExecutor + BFS multi-raíz en Drive) desde RENDER, SUBIR,
     Cotización y SM S Mueblería, más Telas y Maderas, responsiva <= 640px y puente directo a Alta de Fotos.
"""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import io
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import streamlit.components.v1 as components

from modules.sku_banner import render_sku_autofill_bar
from modules.ui_helpers import (
    load_drive_file_cached,
    make_thumbnail_bytes,
    prepare_exact_copy_image_bytes,
    render_copy_button,
    resolve_copied_photo_filename,
)
from services.ai_prompt_service_v8 import (
    ALL_SINGLE_VIEWS,
    MATERIAL_SUBMODES,
    MODES,
    ROOM_PRESETS,
    ai_prompt_service_v8,
    resolve_v8_furniture_type_hint,
)
from services.sheets_service import SUBIR_DRIVE_ID, sheets_service

# Carpetas de fotos de muebles en V8 (RENDER + SUBIR + Cotización + SM S Mueblería)
FOLDER_MUEBLES_RENDER_DRIVE_ID = "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX"
FOLDER_MUEBLES_SUBIR_DRIVE_ID = SUBIR_DRIVE_ID  # "11_rR-qhgM02Sfx9zw7uHU5AwXvTpKD4p"
FOLDER_MUEBLES_SM_MUEBLERIA_DRIVE_ID = "1P06GIuVHFPhQtE2kvPX-_JPA9A6N-qoF"

LOCAL_RENDER_MUEBLES_DIR = Path(r"I:\Mi unidad\DOC ANIPA\Fotos general\Informacion mia\RENDER")
LOCAL_SUBIR_MUEBLES_DIR = Path(r"G:\Mi unidad\DOC ANIPA\Fotos general\Fotos de del proyeto\SUBIR")
LOCAL_COTIZACION_MUEBLES_DIR = Path(r"G:\Mi unidad\DOC ANIPA\Fotos general\Informacion de fotos\Cotizacipón")
LOCAL_SM_MUEBLERIA_MUEBLES_DIR = Path(r"I:\Mi unidad\PROYECTOS FINALES\PLANTILLAS\PRESENTACION\FOTOS SM S MUEBLERIA")

# Carpetas de materiales (telas + maderas)
FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_TELAS_ODOO_DRIVE_ID = "12gsKZVs6rFonOO8CIxokuE73bxhq8tS9"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"

FURNITURE_FOLDER_CHOICES: Dict[str, str] = {
    "📁 Todas las carpetas": "ALL",
    "🛋️ RENDER": "RENDER",
    "📤 SUBIR": "SUBIR",
    "💰 Cotización": "COTIZACION",
    "🏪 SM S Mueblería": "SM_MUEBLERIA",
}

_FURNITURE_FOLDER_SPECS: Dict[str, Dict[str, Any]] = {
    "RENDER": {
        "source": "RENDER",
        "drive_id": FOLDER_MUEBLES_RENDER_DRIVE_ID,
        "drive_path": None,
        "local_rel_paths": [
            r"Mi unidad\DOC ANIPA\Fotos general\Informacion mia\RENDER",
        ],
    },
    "SUBIR": {
        "source": "SUBIR",
        "drive_id": FOLDER_MUEBLES_SUBIR_DRIVE_ID,
        "drive_path": [
            ("DOC ANIPA",),
            ("Fotos general", "Fotos generales"),
            ("Fotos de del proyeto", "Fotos del proyecto"),
            ("SUBIR", "SUBIR PROPT"),
        ],
        "local_rel_paths": [
            r"Mi unidad\DOC ANIPA\Fotos general\Fotos de del proyeto\SUBIR",
            r"Mi unidad\DOC ANIPA\Fotos general\Fotos de del proyeto\SUBIR PROPT",
        ],
    },
    "COTIZACION": {
        "source": "Cotización",
        "drive_id": "",
        "drive_path": [
            ("DOC ANIPA",),
            ("Fotos general", "Fotos generales"),
            ("Informacion de fotos", "Información de fotos"),
            ("Cotizacipón", "Cotización", "Cotizacion", "Cotizaciones"),
        ],
        "local_rel_paths": [
            r"Mi unidad\DOC ANIPA\Fotos general\Informacion de fotos\Cotizacipón",
            r"Mi unidad\DOC ANIPA\Fotos general\Informacion de fotos\Cotización",
            r"Mi unidad\DOC ANIPA\Fotos general\Información de fotos\Cotizacipón",
            r"Mi unidad\DOC ANIPA\Fotos general\Información de fotos\Cotización",
        ],
    },
    "SM_MUEBLERIA": {
        "source": "SM S Mueblería",
        "drive_id": FOLDER_MUEBLES_SM_MUEBLERIA_DRIVE_ID,
        "drive_path": [
            ("PROYECTOS FINALES",),
            ("PLANTILLAS",),
            ("PRESENTACION", "PRESENTACIÓN"),
            ("FOTOS SM S MUEBLERIA", "FOTOS SM´S MUEBLERIA", "FOTOS SMS MUEBLERIA"),
        ],
        "local_rel_paths": [
            r"Mi unidad\PROYECTOS FINALES\PLANTILLAS\PRESENTACION\FOTOS SM S MUEBLERIA",
            r"Mi unidad\PROYECTOS FINALES\PLANTILLAS\PRESENTACIÓN\FOTOS SM S MUEBLERIA",
        ],
    },
}

IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff", "jfif", "avif"]
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff", ".jfif", ".avif"}
MATERIAL_MODES = dict(MATERIAL_SUBMODES)


def _scan_local_dir(target_dir: Path, recursive: bool = False, source_label: str = "") -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    if not target_dir.exists():
        return items
    seen = set()
    iterator = sorted(target_dir.rglob("*")) if recursive else sorted(target_dir.iterdir())
    for f in iterator:
        if f.is_file() and f.suffix.lower() in _IMAGE_EXTS and not f.name.startswith("."):
            clean_name = f.stem.replace("_", " ").strip() if not recursive else f.stem.strip()
            key = clean_name.upper()
            if key in seen:
                continue
            seen.add(key)
            item: Dict[str, str] = {
                "id": "",
                "name": clean_name,
                "filename": f.name,
                "local_path": str(f),
            }
            if source_label:
                item["source"] = source_label
            items.append(item)
    return items


def _candidate_local_dirs(folder_key: str) -> List[Path]:
    dirs: List[Path] = []
    if folder_key == "RENDER":
        dirs.append(LOCAL_RENDER_MUEBLES_DIR)
    elif folder_key == "SUBIR":
        dirs.append(LOCAL_SUBIR_MUEBLES_DIR)
    elif folder_key == "COTIZACION":
        dirs.append(LOCAL_COTIZACION_MUEBLES_DIR)
    elif folder_key == "SM_MUEBLERIA":
        dirs.append(LOCAL_SM_MUEBLERIA_MUEBLES_DIR)

    if os.name == "nt":
        spec = _FURNITURE_FOLDER_SPECS.get(folder_key, {})
        for drv in ("I:", "G:", "H:", "D:", "E:", "F:"):
            for rel in spec.get("local_rel_paths", []):
                cand = Path(f"{drv}\\{rel}")
                if cand not in dirs:
                    dirs.append(cand)
    return dirs


def _scan_local_furniture_folder(folder_key: str) -> List[Dict[str, str]]:
    spec = _FURNITURE_FOLDER_SPECS[folder_key]
    source_label = spec["source"]
    local_items: List[Dict[str, str]] = []
    seen_local = set()
    for cand_dir in _candidate_local_dirs(folder_key):
        for it in _scan_local_dir(cand_dir, recursive=True, source_label=source_label):
            k = it["name"].strip().upper()
            if k not in seen_local:
                seen_local.add(k)
                local_items.append(it)
    return local_items


def _resolve_furniture_drive_id(folder_key: str) -> str:
    spec = _FURNITURE_FOLDER_SPECS[folder_key]
    drive_id = spec.get("drive_id", "")
    if drive_id:
        return drive_id
    if spec.get("drive_path"):
        return sheets_service.find_drive_folder_by_path(
            spec["drive_path"],
            fallback_id=drive_id,
        )
    return ""


def _merge_telas_lists(*lists: List[Dict[str, str]]) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    seen_ids = set()
    seen_names = set()
    for lst in lists:
        for item in lst or []:
            fid = str(item.get("id") or "").strip()
            nm_key = str(item.get("name") or "").strip().upper()
            if fid and fid in seen_ids:
                continue
            if not fid and nm_key in seen_names:
                continue
            if fid:
                seen_ids.add(fid)
            if nm_key:
                seen_names.add(nm_key)
            merged.append(item)
    return merged


@st.cache_data(ttl=120, max_entries=2, show_spinner="📂 Cargando catálogo de fotos...")
def cargar_todo_catalogo_v8(
    refresh_tick: int = 0,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Carga muebles (RENDER, SUBIR, Cotización, SM S Mueblería), telas (TELAS + FOTOS TELAS)
    y maderas en paralelo con ThreadPoolExecutor y un único pase BFS multi-raíz en Google Drive.
    """
    _ = refresh_tick
    f_keys = ["RENDER", "SUBIR", "COTIZACION", "SM_MUEBLERIA"]
    app_dir = Path(__file__).resolve().parent.parent

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        fut_loc = {k: ex.submit(_scan_local_furniture_folder, k) for k in f_keys}
        fut_wood = ex.submit(_scan_local_dir, app_dir / "muestras_madera", False)
        local_by_key = {k: fut.result() for k, fut in fut_loc.items()}
        local_maderas = fut_wood.result()

    drive_batches: Dict[str, List[Dict[str, str]]] = {}
    try:
        if sheets_service.ensure_connected():
            folder_map = {
                "RENDER": _resolve_furniture_drive_id("RENDER"),
                "SUBIR": _resolve_furniture_drive_id("SUBIR"),
                "COTIZACION": _resolve_furniture_drive_id("COTIZACION"),
                "SM_MUEBLERIA": _resolve_furniture_drive_id("SM_MUEBLERIA"),
                "TELAS": FOLDER_TELAS_DRIVE_ID,
                "TELAS_ODOO": FOLDER_TELAS_ODOO_DRIVE_ID,
                "MADERAS": FOLDER_MADERAS_DRIVE_ID,
            }
            drive_batches = sheets_service.get_multiple_drive_folders_files(
                folder_map,
                recursive=True,
                max_depth=4,
                ttl=120,
            )
    except Exception:
        drive_batches = {}

    all_muebles: List[Dict[str, str]] = []
    for k in f_keys:
        source_label = _FURNITURE_FOLDER_SPECS[k]["source"]
        loc_items = local_by_key.get(k, [])
        seen_local = {it["name"].strip().upper() for it in loc_items}
        all_muebles.extend(loc_items)
        for d in drive_batches.get(k, []):
            if d["name"].strip().upper() not in seen_local:
                item_copy = dict(d)
                item_copy["source"] = source_label
                all_muebles.append(item_copy)

    all_telas = _merge_telas_lists(
        drive_batches.get("TELAS", []),
        drive_batches.get("TELAS_ODOO", []),
    )
    seen_wood = {m["name"].upper() for m in local_maderas}
    all_maderas = local_maderas + [
        m for m in drive_batches.get("MADERAS", []) if m["name"].strip().upper() not in seen_wood
    ]
    return all_muebles, all_telas, all_maderas


def invalidate_v8_catalog_caches() -> None:
    for fn in (cargar_todo_catalogo_v8, _search_drive_live_cached_v8):
        try:
            fn.clear()
        except Exception:
            pass


def _read_files(files: Any) -> Tuple[List[bytes], List[str]]:
    if not files:
        return [], []
    lst = files if isinstance(files, list) else [files]
    data: List[bytes] = []
    names: List[str] = []
    for f in lst:
        data.append(f.getvalue() if hasattr(f, "getvalue") else f.read())
        names.append(getattr(f, "name", "foto.jpg"))
    return data, names


def _load_catalog_item_bytes(item: Dict[str, str]) -> Optional[bytes]:
    if not item:
        return None
    if item.get("local_path") and os.path.exists(item["local_path"]):
        try:
            return Path(item["local_path"]).read_bytes()
        except Exception:
            return None
    if item.get("id"):
        return load_drive_file_cached(item["id"])
    return None


def filter_catalog_photos_by_name_v8(
    items: List[Dict[str, str]],
    query: str = "",
    active_names_upper: Optional[set] = None,
) -> List[Dict[str, str]]:
    active_set = active_names_upper or set()
    q_norm = sheets_service._norm_drive_name(query.replace("_", " ").replace("-", " "))
    tokens = [t for t in q_norm.split(" ") if t]

    if not tokens:
        return sorted(
            items,
            key=lambda x: (
                0 if x.get("name", "").strip().upper() in active_set else 1,
                x.get("name", "").upper(),
            ),
        )

    scored: List[Tuple[int, str, Dict[str, str]]] = []
    for it in items:
        name_raw = it.get("name", "")
        fname_raw = it.get("filename", "")
        src_raw = it.get("source", "")
        sub_raw = it.get("subcarpeta", "")
        name_norm = sheets_service._norm_drive_name(name_raw.replace("_", " ").replace("-", " "))
        haystack = sheets_service._norm_drive_name(
            f"{name_raw} {fname_raw} {src_raw} {sub_raw}".replace("_", " ").replace("-", " ")
        )
        if all(tok in haystack for tok in tokens):
            is_active = 0 if name_raw.strip().upper() in active_set else 1
            if name_norm == q_norm:
                rank = 0
            elif name_norm.startswith(tokens[0]):
                rank = 1
            elif q_norm in name_norm:
                rank = 2
            else:
                rank = 3
            scored.append((is_active * 10 + rank, name_raw.upper(), it))

    scored.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in scored]


def _extract_exact_photo_stem(filename: str, fallback: str = "Mueble") -> str:
    raw = os.path.basename(str(filename or "").strip())
    if raw:
        stem = os.path.splitext(raw)[0].strip()
        if stem:
            return stem
    return (fallback or "Mueble").strip()


# ==============================================================================
# VISTAS PREVIAS PROPIAS DE V8 (76x76 PX CON ZOOM AL PASAR EL CURSOR + COPIAR FOTO)
# ==============================================================================
def build_ordered_photo_thumbs_v8(
    mode: str,
    material_mode: str,
    m_names: List[str],
    m_bytes: List[bytes],
    m_source: str,
    fabric_name: str,
    fabric_bytes: Optional[bytes],
    wood_name: str,
    wood_bytes: Optional[bytes],
    batch_views_files: List[Tuple[str, bytes]],
    tipo_mueble: str = "",
    medidas_texto: str = "",
    vista_id: str = "",
) -> List[Tuple[str, bytes, str]]:
    """
    Construye las tarjetas copiables 76x76 px en el MISMO orden exacto Image 1..N que
    build_v8_reference_pack (incluyendo <mueble>_V8_LIENZO_ESCALA.png y <tela>_V8_LUZ30.png).
    """
    has_any_furn = bool(m_bytes)
    has_any_batch = bool(batch_views_files)
    is_blueprint = mode == "plano" or (mode == "vista_suelta" and vista_id == "vista_plano_tecnico")
    inferred_primary_fn = (
        m_names[0]
        if m_names
        else (batch_views_files[0][0] if batch_views_files else "")
    )
    inferred_primary_name = _extract_exact_photo_stem(inferred_primary_fn, fallback="") if inferred_primary_fn else ""
    eff_tipo = resolve_v8_furniture_type_hint(
        tipo_mueble=tipo_mueble,
        furniture_name=inferred_primary_name,
        primary_filename=inferred_primary_fn,
    )

    if mode == "hd" and not has_any_furn and (fabric_bytes or wood_bytes):
        pack = ai_prompt_service_v8.build_v8_reference_pack(
            mode="hd",
            furniture_name=fabric_name or wood_name or "muestra.png",
            furniture_filenames=[fabric_name or wood_name or "muestra.png"],
            furniture_bytes_list=[fabric_bytes or wood_bytes or b""],
            fabric_bytes=fabric_bytes,
            wood_bytes=wood_bytes,
            is_hd_swatch=True,
        )
        return [(p["filename"], p["bytes"], p["label"]) for p in pack if p.get("bytes")]

    if mode in ("vistas_tela", "clonar_color"):
        if not has_any_batch and not fabric_bytes and not has_any_furn:
            return []
        pack = ai_prompt_service_v8.build_v8_reference_pack(
            mode=mode,
            furniture_name=m_names[0] if m_names else "mueble.png",
            furniture_filenames=m_names,
            furniture_bytes_list=m_bytes,
            fabric_label=fabric_name,
            fabric_filename=fabric_name,
            fabric_bytes=fabric_bytes,
            batch_views=batch_views_files,
            batch_ref_filename=(fabric_name if mode == "vistas_tela" else (m_names[0] if m_names else "")),
            batch_ref_bytes=(fabric_bytes if mode == "vistas_tela" else (m_bytes[0] if m_bytes else None)),
            tipo_mueble=eff_tipo,
            medidas_texto=medidas_texto,
        )
        return [(p["filename"], p["bytes"], p["label"]) for p in pack if p.get("bytes")]

    if not has_any_furn and not fabric_bytes and not wood_bytes:
        return []

    # Si el usuario aún no elige mueble pero ya seleccionó tela/madera, mostrar vista previa calibrada +30%
    if not has_any_furn:
        preview_only: List[Tuple[str, bytes, str]] = []
        slot = 1
        if fabric_bytes and (mode != "material" or material_mode in ("fabric_only", "dual")) and not is_blueprint:
            pack_sw = ai_prompt_service_v8.build_v8_reference_pack(
                mode="catalogo",
                furniture_name="mueble",
                fabric_label=fabric_name,
                fabric_filename=fabric_name,
                fabric_bytes=fabric_bytes,
                tipo_mueble=eff_tipo,
                medidas_texto=medidas_texto,
            )
            sw_entry = next((p for p in pack_sw if p["role"] == "v8_calibrated_swatch"), None)
            if sw_entry and sw_entry.get("bytes"):
                preview_only.append((sw_entry["filename"], sw_entry["bytes"], f"Image {slot} · Tela +30% V8"))
                slot += 1
        if wood_bytes and (mode != "material" or material_mode in ("wood_only", "dual")) and not is_blueprint:
            preview_only.append((resolve_copied_photo_filename(wood_name, "madera.png"), wood_bytes, f"Image {slot} · Madera"))
        return preview_only

    pack_std = ai_prompt_service_v8.build_v8_reference_pack(
        mode=mode,
        vista_id=vista_id,
        material_mode=material_mode,
        furniture_name=m_names[0] if m_names else "mueble.png",
        furniture_filenames=m_names,
        furniture_bytes_list=m_bytes,
        furniture_source=m_source,
        fabric_label=fabric_name,
        fabric_filename=fabric_name,
        fabric_bytes=fabric_bytes,
        wood_label=wood_name,
        wood_filename=wood_name,
        wood_bytes=wood_bytes,
        tipo_mueble=eff_tipo,
        medidas_texto=medidas_texto,
    )
    return [(p["filename"], p["bytes"], p["label"]) for p in pack_std if p.get("bytes")]


def render_v8_photos_strip_76(
    thumbs: List[Tuple[str, bytes, str]],
    key_prefix: str = "v8",
) -> None:
    """
    Renderiza vistas previas claras de exactamente 76x76 px con zoom suave al pasar el cursor
    (GEMINI.md Regla 1) y botón 🖼️ Copiar foto debajo de cada miniatura sin tocar ui_helpers.py.
    """
    if not thumbs:
        return

    img_px = 76
    card_w = 104
    card_blocks: List[str] = []
    js_entries: List[str] = []

    for idx, (lbl, raw_b, badge) in enumerate(thumbs):
        if not raw_b:
            continue
        exact_bytes, exact_mime = prepare_exact_copy_image_bytes(raw_b)
        if not exact_bytes:
            continue
        t_bytes = make_thumbnail_bytes(exact_bytes, max_dim=228)
        if not t_bytes:
            continue
        b64_thumb = base64.b64encode(t_bytes).decode("ascii")
        b64_exact = base64.b64encode(exact_bytes).decode("ascii")
        uid = hashlib.md5(f"{key_prefix}_{idx}_{lbl}_{len(raw_b)}".encode("utf-8")).hexdigest()[:8]
        btn_id = f"v8cpimg_{uid}"
        msg_id = f"v8cpmsg_{uid}"

        safe_dl = resolve_copied_photo_filename(lbl, fallback=f"foto_{idx + 1}.png")
        safe_lbl = safe_dl.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_title = safe_lbl.replace('"', "&quot;")
        safe_badge = (badge or "Cargada")[:34].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        js_dl = safe_dl.replace("\\", "\\\\").replace('"', '\\"')

        card_blocks.append(
            f'<div class="v8-thumb-card" title="{safe_badge}: {safe_title}">'
            f'<div class="v8-thumb-img-wrap">'
            f'<img class="v8-thumb-img" src="data:image/jpeg;base64,{b64_thumb}" alt="{safe_title}" />'
            f'</div>'
            f'<span class="v8-thumb-badge">✅ {safe_badge}</span>'
            f'<span class="v8-thumb-name" title="{safe_title}">{safe_lbl}</span>'
            f'<button type="button" id="{btn_id}" class="v8-cp-btn" title="Copiar imagen exacta ({safe_title})">🖼️ Copiar foto</button>'
            f'<span id="{msg_id}" class="v8-cp-msg"></span>'
            f'</div>'
        )
        js_entries.append(
            f'bindCopy("{btn_id}", "{msg_id}", "data:{exact_mime};base64,{b64_exact}", "{js_dl}");'
        )

    if not card_blocks:
        return

    rows_est = max(1, (len(card_blocks) + 2) // 3)
    row_h = img_px + 86
    comp_height = min(420, row_h * rows_est + 28)
    needs_scroll = (row_h * rows_est + 28) > 420

    html_doc = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8" />
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: transparent; padding: 10px 4px 6px 4px; overflow-x: hidden; }}
        .v8-strip {{
            display: flex;
            flex-wrap: wrap;
            gap: 7px;
            align-items: stretch;
        }}
        .v8-thumb-card {{
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 3px;
            width: {card_w}px;
            max-width: calc(50% - 4px);
            background: #0F172A;
            border: 1px solid #0284C7;
            border-radius: 8px;
            padding: 5px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.36);
            transition: z-index 0.1s ease, border-color 0.15s ease;
        }}
        .v8-thumb-card:hover {{
            z-index: 60;
            border-color: #38BDF8;
        }}
        .v8-thumb-img-wrap {{
            width: 76px;
            height: 76px;
            border-radius: 6px;
            overflow: visible;
            background: #020617;
            border: 1px solid #1E293B;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .v8-thumb-img {{
            width: 76px;
            height: 76px;
            border-radius: 6px;
            object-fit: cover;
            display: block;
            transition: transform 0.18s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.18s ease;
            transform-origin: center center;
        }}
        .v8-thumb-img:hover {{
            transform: scale(1.72);
            z-index: 80;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.78);
            border: 1px solid #38BDF8;
        }}
        .v8-thumb-badge {{
            width: 100%;
            font-size: 9px;
            color: #4ADE80;
            font-weight: 700;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .v8-thumb-name {{
            width: 100%;
            font-size: 9.5px;
            color: #F8FAFC;
            font-weight: 600;
            text-align: center;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .v8-cp-btn {{
            width: 100%;
            background: linear-gradient(135deg, #0284C7, #0EA5E9);
            color: #FFFFFF;
            border: none;
            border-radius: 5px;
            padding: 4px 5px;
            font-size: 10px;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
            margin-top: 1px;
            box-shadow: 0 1px 4px rgba(2,132,199,0.35);
        }}
        .v8-cp-btn:hover {{ filter: brightness(1.1); }}
        .v8-cp-btn:active {{ transform: scale(0.97); }}
        .v8-cp-btn:disabled {{ opacity: 0.65; cursor: wait; }}
        .v8-cp-msg {{
            width: 100%;
            font-size: 8.8px;
            font-weight: 700;
            color: #4ADE80;
            min-height: 12px;
            line-height: 12px;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
    </style>
    </head>
    <body>
        <div class="v8-strip">{"".join(card_blocks)}</div>
        <script>
        (function() {{
            function decodePngDataUriSync(dataUri) {{
                try {{
                    if (typeof dataUri !== "string" || dataUri.indexOf("data:image/png;base64,") !== 0) return null;
                    var b64 = dataUri.slice("data:image/png;base64,".length);
                    var bin = atob(b64);
                    var bytes = new Uint8Array(bin.length);
                    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                    return new Blob([bytes], {{ type: "image/png" }});
                }} catch (e) {{
                    return null;
                }}
            }}

            function dataUriToPngBlob(dataUri) {{
                var directPng = decodePngDataUriSync(dataUri);
                if (directPng) return Promise.resolve(directPng);
                return new Promise(function(resolve, reject) {{
                    var img = new Image();
                    img.onload = function() {{
                        try {{
                            var c = document.createElement("canvas");
                            c.width = img.naturalWidth || img.width;
                            c.height = img.naturalHeight || img.height;
                            var ctx = c.getContext("2d");
                            ctx.drawImage(img, 0, 0);
                            c.toBlob(function(blob) {{
                                if (blob) resolve(blob);
                                else reject(new Error("toBlob failed"));
                            }}, "image/png");
                        }} catch (e) {{ reject(e); }}
                    }};
                    img.onerror = function() {{ reject(new Error("img load failed")); }};
                    img.src = dataUri;
                }});
            }}

            function writePngToWindowClipboard(targetWin, syncBlob, blobPromise) {{
                return new Promise(function(resolve, reject) {{
                    try {{
                        if (!targetWin || !targetWin.navigator || !targetWin.navigator.clipboard || typeof targetWin.navigator.clipboard.write !== "function" || typeof targetWin.ClipboardItem !== "function") {{
                            reject(new Error("clipboard_image_unavailable"));
                            return;
                        }}
                        if (syncBlob) {{
                            var syncItem = new targetWin.ClipboardItem({{ "image/png": syncBlob }});
                            targetWin.navigator.clipboard.write([syncItem]).then(function() {{ resolve(true); }}, reject);
                            return;
                        }}
                        var promiseItem = new targetWin.ClipboardItem({{ "image/png": blobPromise }});
                        targetWin.navigator.clipboard.write([promiseItem]).then(function() {{ resolve(true); }}, function() {{
                            blobPromise.then(function(resolvedBlob) {{
                                var fbItem = new targetWin.ClipboardItem({{ "image/png": resolvedBlob }});
                                return targetWin.navigator.clipboard.write([fbItem]);
                            }}).then(function() {{ resolve(true); }}, reject);
                        }});
                    }} catch (err) {{
                        reject(err);
                    }}
                }});
            }}

            function requestHostBridgeCopyImage(dataUri, fileName) {{
                return new Promise(function(resolve) {{
                    var targets = [];
                    try {{
                        if (window.top && window.top !== window && typeof window.top.postMessage === "function") {{
                            targets.push(window.top);
                        }}
                    }} catch (e1) {{}}
                    if (!targets.length) {{
                        resolve(false);
                        return;
                    }}
                    var reqId = "v8cp_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
                    var done = false;
                    var timer = setTimeout(function() {{
                        if (done) return;
                        done = true;
                        window.removeEventListener("message", onMsg);
                        resolve(false);
                    }}, 1400);
                    function onMsg(ev) {{
                        var d = ev && ev.data;
                        if (!d || d.type !== "CREATA_PROMPTS_COPY_IMAGE_RESULT" || d.requestId !== reqId) return;
                        if (done) return;
                        done = true;
                        clearTimeout(timer);
                        window.removeEventListener("message", onMsg);
                        resolve(Boolean(d.ok));
                    }}
                    window.addEventListener("message", onMsg);
                    var payload = {{
                        type: "CREATA_PROMPTS_COPY_IMAGE",
                        requestId: reqId,
                        dataUri: dataUri,
                        dataUrl: dataUri,
                        fileName: fileName || "foto.png"
                    }};
                    for (var i = 0; i < targets.length; i++) {{
                        try {{ targets[i].postMessage(payload, "*"); }} catch (ePost) {{}}
                    }}
                }});
            }}

            function triggerFallbackDownload(dataUri, fileName) {{
                var a = document.createElement("a");
                a.href = dataUri;
                a.download = fileName || "foto.png";
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }}

            function bindCopy(btnId, msgId, dataUri, fileName) {{
                var btn = document.getElementById(btnId);
                var msg = document.getElementById(msgId);
                if (!btn) return;
                var readyPngBlob = null;

                btn.addEventListener("click", async function() {{
                    btn.disabled = true;
                    if (msg) msg.textContent = "Copiando...";
                    if (!readyPngBlob) readyPngBlob = decodePngDataUriSync(dataUri);
                    var activePromise = readyPngBlob
                        ? Promise.resolve(readyPngBlob)
                        : dataUriToPngBlob(dataUri).then(function(b) {{ readyPngBlob = b; return b; }});
                    var copiedImage = false;
                    try {{
                        try {{
                            await writePngToWindowClipboard(window, readyPngBlob, activePromise);
                            copiedImage = true;
                        }} catch (eSelf) {{}}
                        if (!copiedImage && window.parent && window.parent !== window) {{
                            try {{
                                await writePngToWindowClipboard(window.parent, readyPngBlob, activePromise);
                                copiedImage = true;
                            }} catch (eParent) {{}}
                        }}
                        if (!copiedImage) {{
                            copiedImage = await requestHostBridgeCopyImage(dataUri, fileName);
                        }}
                        if (copiedImage) {{
                            if (msg) msg.textContent = "✅ " + (fileName || "Copiada");
                        }} else {{
                            triggerFallbackDownload(dataUri, fileName);
                            if (msg) msg.textContent = "💾 " + (fileName || "Descargada");
                        }}
                    }} catch (err) {{
                        triggerFallbackDownload(dataUri, fileName);
                        if (msg) msg.textContent = "💾 " + (fileName || "Descargada");
                    }} finally {{
                        btn.disabled = false;
                        setTimeout(function() {{ if (msg) msg.textContent = ""; }}, 2800);
                    }}
                }});
            }}

            {" ".join(js_entries)}
        }})();
        </script>
    </body>
    </html>
    """
    components.html(html_doc, height=comp_height, scrolling=needs_scroll)


def _get_search_preview_src_v8(
    item: Dict[str, str],
    max_dim: int = 320,
    allow_network: bool = True,
) -> str:
    if not item:
        return ""
    loc_path = item.get("local_path", "")
    if loc_path and os.path.exists(loc_path):
        try:
            raw_b = Path(loc_path).read_bytes()
            t_bytes = make_thumbnail_bytes(raw_b, max_dim=max_dim)
            if t_bytes:
                return f"data:image/jpeg;base64,{base64.b64encode(t_bytes).decode('ascii')}"
        except Exception:
            pass

    f_id = item.get("id", "")
    t_link = (item.get("thumbnailLink") or "").strip()
    if f_id:
        mem_bytes = (
            sheets_service._drive_file_bytes_cache.get(f"thumb:{f_id}")
            or sheets_service._drive_file_bytes_cache.get(f_id)
        )
        if mem_bytes:
            t_bytes = make_thumbnail_bytes(mem_bytes, max_dim=max_dim)
            if t_bytes:
                return f"data:image/jpeg;base64,{base64.b64encode(t_bytes).decode('ascii')}"
        if allow_network:
            net_bytes = sheets_service.get_drive_thumbnail_bytes(f_id, t_link, allow_full_fallback=False)
            if net_bytes:
                t_bytes = make_thumbnail_bytes(net_bytes, max_dim=max_dim)
                if t_bytes:
                    return f"data:image/jpeg;base64,{base64.b64encode(t_bytes).decode('ascii')}"
    return ""


@st.cache_data(ttl=600, max_entries=32, show_spinner=False)
def _search_drive_live_cached_v8(query_str: str) -> List[Dict[str, str]]:
    hits: List[Dict[str, str]] = []
    seen = set()
    try:
        if sheets_service.ensure_connected():
            for fk in ("RENDER", "SUBIR", "SM_MUEBLERIA", "COTIZACION"):
                fid = _resolve_furniture_drive_id(fk)
                if not fid:
                    continue
                src_lbl = _FURNITURE_FOLDER_SPECS[fk]["source"]
                for lh in sheets_service.search_drive_images_live(
                    query_text=query_str,
                    limit=8,
                    folder_id=fid,
                ):
                    if lh.get("id") and lh["id"] not in seen:
                        seen.add(lh["id"])
                        row = dict(lh)
                        row["source"] = src_lbl
                        hits.append(row)
    except Exception:
        pass
    return hits


def _pick_catalog_photo_v8(ck: int, kind: str, item: Dict[str, str]) -> None:
    st.session_state[f"v8_picked_{kind}_{ck}"] = dict(item)
    st.session_state[f"v8_apply_pick_{kind}_{ck}"] = True
    cur_sig = st.session_state.get(f"v8_cur_up_sig_{kind}_{ck}")
    if cur_sig:
        st.session_state[f"v8_ign_up_{kind}_{ck}"] = cur_sig


def _resolve_mueble_selector_v8(
    ck: int,
    folder_key: str = "ALL",
    all_muebles_cat: Optional[List[Dict[str, str]]] = None,
) -> Tuple[List[bytes], List[str], str]:
    if all_muebles_cat is not None:
        if folder_key == "ALL":
            catalog_items = list(all_muebles_cat)
        else:
            target_src = _FURNITURE_FOLDER_SPECS.get(folder_key, {}).get("source", "")
            catalog_items = [x for x in all_muebles_cat if x.get("source") == target_src]
    else:
        tick = int(st.session_state.get("v8_render_tick", 0))
        catalog_items, _, _ = cargar_todo_catalogo_v8(tick)
        if folder_key != "ALL":
            target_src = _FURNITURE_FOLDER_SPECS.get(folder_key, {}).get("source", "")
            catalog_items = [x for x in catalog_items if x.get("source") == target_src]

    picked_item = st.session_state.get(f"v8_picked_mueble_{ck}")
    if isinstance(picked_item, dict) and picked_item.get("name"):
        p_name_up = picked_item["name"].strip().upper()
        p_src = picked_item.get("source", "")
        exists = any(
            x.get("name", "").strip().upper() == p_name_up and x.get("source", "") == p_src
            for x in catalog_items
        )
        if not exists:
            catalog_items = [picked_item] + catalog_items

    show_source = folder_key == "ALL"
    folder_short = _FURNITURE_FOLDER_SPECS.get(folder_key, {}).get("source", "Mueble")
    first_opt = f"🛋️ {folder_short if not show_source else 'Mueble'} ({len(catalog_items)})"

    display_map: Dict[str, Dict[str, str]] = {}
    options: List[str] = [first_opt]
    picked_target_lbl: Optional[str] = None
    for item in catalog_items:
        src = item.get("source", "")
        base_lbl = f"{item['name']} · [{src}]" if (show_source and src) else item["name"]
        lbl = base_lbl
        suffix = 2
        while lbl in display_map:
            lbl = f"{base_lbl} ({suffix})"
            suffix += 1
        display_map[lbl] = item
        options.append(lbl)
        if (
            isinstance(picked_item, dict)
            and picked_target_lbl is None
            and item.get("name", "").strip().upper() == picked_item.get("name", "").strip().upper()
            and (not picked_item.get("source") or item.get("source", "") == picked_item.get("source", ""))
        ):
            picked_target_lbl = lbl

    sb_key = f"v8_sb_mueble_{ck}"
    if st.session_state.get(f"v8_apply_pick_mueble_{ck}") and picked_target_lbl:
        st.session_state[sb_key] = picked_target_lbl
        st.session_state[f"v8_apply_pick_mueble_{ck}"] = False
    elif st.session_state.get(sb_key) not in options:
        st.session_state[sb_key] = first_opt

    c_sel, c_up = st.columns([2.15, 0.95], gap="small", vertical_alignment="center")
    with c_sel:
        sel_name = st.selectbox(
            "Mueble",
            options,
            key=sb_key,
            label_visibility="collapsed",
        )
    with c_up:
        up_mueble = st.file_uploader(
            "Subir mueble",
            type=IMG_TYPES,
            accept_multiple_files=True,
            key=f"v8_mueble_{ck}",
            label_visibility="collapsed",
        )

    if up_mueble:
        ub, un = _read_files(up_mueble)
        up_sig = "|".join(f"{n}:{len(b)}" for n, b in zip(un, ub))
        st.session_state[f"v8_cur_up_sig_mueble_{ck}"] = up_sig
        if up_sig != st.session_state.get(f"v8_ign_up_mueble_{ck}"):
            return ub, un, "Upload"
    else:
        st.session_state[f"v8_cur_up_sig_mueble_{ck}"] = ""

    if sel_name and sel_name in display_map:
        match = display_map[sel_name]
        raw_b = _load_catalog_item_bytes(match)
        if raw_b:
            fname = match.get("filename") or f"{match.get('name') or sel_name}.jpg"
            src = match.get("source") or ("Local" if match.get("local_path") else "Drive")
            return [raw_b], [fname], src
        st.warning(f"⚠️ No se pudo descargar «{match.get('name') or sel_name}» desde Drive.")
    return [], [], ""


def _resolve_material_selector_v8(
    kind: str,
    ck: int,
    catalog_items: List[Dict[str, str]],
) -> Tuple[Optional[bytes], str, str]:
    is_wood = kind == "wood"
    lbl = "🪵 Madera" if is_wood else "🧵 Tela"
    items_list = list(catalog_items)
    picked_item = st.session_state.get(f"v8_picked_{kind}_{ck}")
    if isinstance(picked_item, dict) and picked_item.get("name"):
        p_up = picked_item["name"].strip().upper()
        p_id = str(picked_item.get("id") or "").strip()
        exists = any(
            (p_id and str(x.get("id") or "").strip() == p_id)
            or (not p_id and x.get("name", "").strip().upper() == p_up)
            for x in items_list
        )
        if not exists:
            items_list = [picked_item] + items_list

    first_opt = f"{lbl} ({len(items_list)})"
    display_map: Dict[str, Dict[str, str]] = {}
    options: List[str] = [first_opt]
    picked_target_lbl: Optional[str] = None
    for item in items_list:
        base_lbl = item["name"].strip() or item.get("filename") or lbl
        sub = str(item.get("subcarpeta") or "").strip()
        opt_lbl = base_lbl
        if opt_lbl in display_map and sub:
            opt_lbl = f"{base_lbl} · {sub}"
        suffix = 2
        while opt_lbl in display_map:
            opt_lbl = f"{base_lbl} ({suffix})"
            suffix += 1
        display_map[opt_lbl] = item
        options.append(opt_lbl)
        if isinstance(picked_item, dict) and picked_target_lbl is None:
            p_id = str(picked_item.get("id") or "").strip()
            if (p_id and str(item.get("id") or "").strip() == p_id) or (
                item.get("name", "").strip().upper() == picked_item.get("name", "").strip().upper()
            ):
                picked_target_lbl = opt_lbl

    sb_key = f"v8_sb_{kind}_{ck}"
    if st.session_state.get(f"v8_apply_pick_{kind}_{ck}") and picked_target_lbl:
        st.session_state[sb_key] = picked_target_lbl
        st.session_state[f"v8_apply_pick_{kind}_{ck}"] = False
    elif st.session_state.get(sb_key) not in options:
        st.session_state[sb_key] = first_opt

    c_sel, c_up = st.columns([2.15, 0.95], gap="small", vertical_alignment="center")
    with c_sel:
        sel_name = st.selectbox(
            lbl,
            options,
            key=sb_key,
            label_visibility="collapsed",
        )
    with c_up:
        up_file = st.file_uploader(
            lbl,
            type=IMG_TYPES,
            key=f"v8_up_{kind}_{ck}",
            label_visibility="collapsed",
        )

    if up_file:
        ub = up_file.getvalue()
        uname = getattr(up_file, "name", lbl)
        up_sig = f"{uname}:{len(ub)}"
        st.session_state[f"v8_cur_up_sig_{kind}_{ck}"] = up_sig
        if up_sig != st.session_state.get(f"v8_ign_up_{kind}_{ck}"):
            return ub, uname, "Upload"
    else:
        st.session_state[f"v8_cur_up_sig_{kind}_{ck}"] = ""

    if sel_name and sel_name in display_map:
        match = display_map[sel_name]
        loaded = _load_catalog_item_bytes(match)
        if loaded:
            src = "Local" if match.get("local_path") else "Drive"
            return loaded, match.get("filename") or match.get("name") or sel_name, src
        st.warning(f"⚠️ No se pudo descargar «{match.get('name') or sel_name}» desde Drive.")
    return None, "", ""


def _render_floating_photo_menu_v8(
    ck: int,
    loaded_entries: List[Dict[str, Any]],
    all_muebles: List[Dict[str, str]],
    all_telas: List[Dict[str, str]],
    all_maderas: List[Dict[str, str]],
    tick: int,
) -> None:
    """Buscador flotante rápido (popover) con recarga de catálogo por selector sin botones extra en el formulario."""
    n_loaded = len(loaded_entries)
    total_cat = len(all_muebles) + len(all_telas) + len(all_maderas)
    pop_label = f"🔍 Fotos · ✅ {n_loaded}" if n_loaded > 0 else f"🔍 Buscar ({total_cat})"

    with st.popover(pop_label, use_container_width=True):
        active_names_upper = set()
        for entry in loaded_entries:
            e_name = str(entry.get("name") or "Foto").strip()
            active_names_upper.add(os.path.splitext(e_name)[0].strip().upper())
            active_names_upper.add(e_name.upper())

        c_q, c_cat = st.columns([1.65, 1.35], gap="small", vertical_alignment="center")
        with c_q:
            q_text = st.text_input(
                "Buscar foto",
                placeholder="🔎 Nombre de mueble, tela o madera...",
                key=f"v8_pop_q_{ck}",
                label_visibility="collapsed",
            )
        with c_cat:
            cat_filter = st.selectbox(
                "Categoría",
                [
                    "📁 Todas",
                    "🛋️ RENDER",
                    "📤 SUBIR",
                    "💰 Cotización",
                    "🏪 SM S Mueblería",
                    "🧵 Telas",
                    "🪵 Maderas",
                    "🔄 Actualizar Drive",
                ],
                key=f"v8_pop_cat_{ck}",
                label_visibility="collapsed",
            )

        if cat_filter == "🔄 Actualizar Drive":
            st.session_state[f"v8_pop_cat_{ck}"] = "📁 Todas"
            sheets_service._invalidate_drive_catalog_caches()
            sheets_service._resolved_folder_ids.clear()
            invalidate_v8_catalog_caches()
            st.session_state["v8_render_tick"] = tick + 1
            st.rerun()

        q_clean = q_text.strip()
        pool: List[Dict[str, str]] = []
        idle_cap = 20 if not q_clean else 0

        if cat_filter in ("📁 Todas", "🛋️ RENDER", "📤 SUBIR", "💰 Cotización", "🏪 SM S Mueblería"):
            for m in all_muebles:
                src = m.get("source") or "RENDER"
                if cat_filter == "🛋️ RENDER" and src != "RENDER":
                    continue
                if cat_filter == "📤 SUBIR" and src != "SUBIR":
                    continue
                if cat_filter == "💰 Cotización" and src != "Cotización":
                    continue
                if cat_filter == "🏪 SM S Mueblería" and src != "SM S Mueblería":
                    continue
                is_act = bool(active_names_upper and (m.get("name", "").strip().upper() in active_names_upper))
                if idle_cap and len(pool) >= idle_cap and not is_act:
                    continue
                row_m = dict(m)
                row_m["kind"] = "mueble"
                row_m["source"] = src
                row_m["badge"] = f"🛋️ {src}"
                pool.append(row_m)

        if cat_filter in ("📁 Todas", "🧵 Telas"):
            for t in all_telas:
                is_act = bool(active_names_upper and (t.get("name", "").strip().upper() in active_names_upper))
                if idle_cap and len(pool) >= idle_cap and not is_act:
                    continue
                row_t = dict(t)
                row_t["kind"] = "fabric"
                row_t["source"] = "Telas"
                row_t["badge"] = "🧵 Tela"
                pool.append(row_t)

        if cat_filter in ("📁 Todas", "🪵 Maderas"):
            for w in all_maderas:
                is_act = bool(active_names_upper and (w.get("name", "").strip().upper() in active_names_upper))
                if idle_cap and len(pool) >= idle_cap and not is_act:
                    continue
                row_w = dict(w)
                row_w["kind"] = "wood"
                row_w["source"] = "Maderas"
                row_w["badge"] = "🪵 Madera"
                pool.append(row_w)

        matches = filter_catalog_photos_by_name_v8(pool, q_clean, active_names_upper)
        if q_clean and len(q_clean) >= 3 and not matches:
            for lh in _search_drive_live_cached_v8(q_clean):
                clean_nm = os.path.splitext(lh.get("name", ""))[0].strip() or lh.get("name", "Foto")
                src_lh = lh.get("source") or "Drive"
                matches.append({
                    "id": lh["id"],
                    "name": clean_nm,
                    "filename": lh.get("name", f"{clean_nm}.jpg"),
                    "source": src_lh,
                    "kind": "mueble",
                    "badge": f"☁️ {src_lh}",
                    "thumbnailLink": lh.get("thumbnailLink", ""),
                })

        if q_clean and matches:
            top_to_warm = [
                m for m in matches[:6]
                if m.get("id")
                and f"thumb:{m['id']}" not in sheets_service._drive_file_bytes_cache
                and m["id"] not in sheets_service._drive_file_bytes_cache
            ]
            if top_to_warm:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(top_to_warm))) as ex:
                    for _ in ex.map(
                        lambda m: sheets_service.get_drive_thumbnail_bytes(
                            m["id"], m.get("thumbnailLink", ""), allow_full_fallback=False
                        ),
                        top_to_warm,
                    ):
                        pass

        pick_opts = ["➕ Seleccionar resultado para cargar..."]
        pick_map: Dict[str, Dict[str, str]] = {}
        for it in matches[:25]:
            lbl_p = f"{it.get('badge', '📁')} · {it.get('name', 'Foto')}"
            sfx = 2
            cur_lbl = lbl_p
            while cur_lbl in pick_map:
                cur_lbl = f"{lbl_p} ({sfx})"
                sfx += 1
            pick_map[cur_lbl] = it
            pick_opts.append(cur_lbl)

        pick_key = f"v8_pop_pick_{ck}"
        if st.session_state.get(pick_key) not in pick_opts:
            st.session_state[pick_key] = pick_opts[0]
        chosen = st.selectbox("Resultado", pick_opts, key=pick_key, label_visibility="collapsed")
        if chosen != pick_opts[0] and chosen in pick_map:
            chosen_it = pick_map[chosen]
            st.session_state[pick_key] = pick_opts[0]
            _pick_catalog_photo_v8(ck, chosen_it.get("kind", "mueble"), chosen_it)
            st.rerun()

        if matches:
            top_it = matches[0]
            prev_src = _get_search_preview_src_v8(top_it, max_dim=240, allow_network=bool(q_clean))
            if prev_src:
                safe_nm = top_it.get("name", "Foto").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;padding:4px;background:#0F172A;'
                    f'border:1px solid #1E293B;border-radius:8px;">'
                    f'<img class="v8-search-thumb" src="{prev_src}" style="width:76px;height:76px;object-fit:cover;'
                    f'border-radius:6px;border:1px solid #38BDF8;" />'
                    f'<div style="font-size:11px;color:#F8FAFC;font-weight:600;overflow:hidden;text-overflow:ellipsis;">'
                    f'{safe_nm}</div></div>',
                    unsafe_allow_html=True,
                )


def _clear_v8_form(ck: int) -> None:
    """
    Regla 2 de GEMINI.md:
      - Borra ÚNICAMENTE fotos cargadas, SKU de V8, medidas, notas y resultados generados.
      - JAMÁS reinicia ni modifica v8_keep_mode ni las sub-opciones activas
        (v8_keep_vista, v8_keep_matmode, v8_keep_room, v8_keep_folder).
    """
    clear_prefixes = (
        "v8_result",
        "v8_last_photo_stem",
        "v8_last_sku",
        "v8_notas_",
        "v8_sb_",
        "v8_up_",
        "v8_mueble_",
        "v8_batch_",
        "v8_clone_",
        "v8_ext2054_",
        "v8_picked_",
        "v8_preview_item_",
        "v8_apply_pick_",
        "v8_ign_up_",
        "v8_cur_up_sig_",
        "v8_pop_",
    )
    exact_keys = {
        "sku_input_v8",
        "field_tipo_v8",
        "field_medidas_v8",
        "sku_loaded_data_v8",
        "sku_last_searched_v8",
        "v7_last_photo_stem",
    }
    for k in list(st.session_state.keys()):
        if k in exact_keys or k.startswith(clear_prefixes):
            st.session_state.pop(k, None)
    st.session_state.clear_key_v8 = ck + 1
    st.rerun()


def _build_zip_v8(res: Dict[str, Any], include_images: bool = True) -> bytes:
    """Empaqueta prompts e insumos/ (incluyendo <mueble>_V8_LIENZO_ESCALA.png y <tela>_V8_LUZ30.png)."""
    buf = io.BytesIO()
    mueble_slug = res.get("mueble_name", "mueble")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, it in enumerate(res.get("items", []), start=1):
            guide = it.get("attachment_guide") or []
            guide_txt = "\n".join(f"  - {g}" for g in guide) if guide else "  - Image 1: Foto del mueble"
            out_fname = it.get("output_filename") or (f"{mueble_slug}.png" if i == 1 else f"{mueble_slug}_{i}.png")
            out_stem = os.path.splitext(out_fname)[0]
            body = (
                f"=== NOMBRE EXACTO DE SALIDA ===\n  {out_fname}\n\n"
                f"=== ORDEN EXACTO DE IMÁGENES V8 ===\n{guide_txt}\n\n"
                f"--- GOOGLE AI STUDIO / GEMINI ---\n{it.get('google_ai_studio', '')}\n\n"
                f"--- CHATGPT ---\n{it.get('chatgpt_dalle3', '')}\n\n"
                f"--- MIDJOURNEY ---\n{it.get('midjourney_v6', '')}\n"
            )
            z.writestr(f"prompts/{out_stem}.txt", body)

            gen_photo = it.get("generated_photo")
            if isinstance(gen_photo, dict) and gen_photo.get("png"):
                z.writestr(f"fotos_generadas_2054/{out_fname}", gen_photo["png"])

        if res.get("master_ais"):
            z.writestr(
                f"prompts/00_{mueble_slug}_maestro.txt",
                res["master_ais"] + "\n\n====================\n\n" + res.get("master_dal", ""),
            )

        if include_images:
            seen_in = set()
            for idx, (fname, raw) in enumerate(res.get("ref_images", []), start=1):
                if not raw:
                    continue
                safe_name = os.path.basename(fname or f"ref_{idx}.png")
                if safe_name in seen_in:
                    base_s, ext_s = os.path.splitext(safe_name)
                    safe_name = f"{base_s}_{idx}{ext_s}"
                seen_in.add(safe_name)
                z.writestr(f"insumos/{safe_name}", raw)
    return buf.getvalue()


def _render_item_v8(item: Dict[str, Any], idx: int, ck: int, gen_id: int) -> None:
    guide = item.get("attachment_guide") or []
    if guide:
        st.caption("📎 " + " · ".join(guide))
    out_fname = str(item.get("output_filename") or "").strip()
    if out_fname:
        fn_col, cp_col = st.columns([2.2, 1.0], gap="small", vertical_alignment="center")
        with fn_col:
            st.caption(f"🏷️ **`{out_fname}`**")
        with cp_col:
            render_copy_button(
                os.path.splitext(out_fname)[0],
                label="📋 Copiar nombre",
                key=f"v8_cp_name_{idx}_{ck}_{gen_id}",
            )

    t_ais, t_dal, t_mj = st.tabs(["AI Studio", "ChatGPT", "Midjourney"])
    with t_ais:
        txt = item.get("google_ai_studio", "")
        render_copy_button(
            txt,
            label="📋 Copiar",
            key=f"v8_cp_ais_{idx}_{ck}_{gen_id}",
            extra_link_url="https://accounts.google.com/AccountChooser?continue=https://aistudio.google.com/",
            extra_link_label="⚡ AI Studio",
        )
        st.text_area("Prompt", txt, height=165, key=f"v8_ais_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_dal:
        txt = item.get("chatgpt_dalle3", "")
        render_copy_button(
            txt,
            label="📋 Copiar",
            key=f"v8_cp_dal_{idx}_{ck}_{gen_id}",
            extra_link_url="https://chatgpt.com/",
            extra_link_label="🤖 ChatGPT",
        )
        st.text_area("Prompt", txt, height=165, key=f"v8_dal_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_mj:
        txt = item.get("midjourney_v6", "")
        render_copy_button(txt, label="📋 Copiar", key=f"v8_cp_mj_{idx}_{ck}_{gen_id}")
        st.text_area("Prompt", txt, height=115, key=f"v8_mj_{idx}_{ck}_{gen_id}", label_visibility="collapsed")


def render_prompt_studio_v8() -> None:
    if "clear_key_v8" not in st.session_state:
        st.session_state.clear_key_v8 = 0
    ck = int(st.session_state.clear_key_v8)

    st.markdown(
        """
<style>
.stButton > button,
.stDownloadButton > button,
div[data-testid="stPopover"] button {
    font-size: 11px !important;
    font-weight: 600 !important;
    min-height: 30px !important;
    height: auto !important;
    padding: 4px 6px !important;
    border-radius: 6px !important;
    white-space: normal !important;
    word-break: normal !important;
    line-height: 1.2 !important;
}
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    min-height: 28px !important;
    height: 28px !important;
    font-size: 11px !important;
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
section[data-testid="stFileUploaderDropzone"] {
    padding: 2px 3px !important;
    min-height: 30px !important;
    overflow: hidden !important;
}
section[data-testid="stFileUploaderDropzone"] svg,
section[data-testid="stFileUploaderDropzone"] small,
section[data-testid="stFileUploaderDropzone"] span[data-testid="stMarkdownContainer"],
div[data-testid="stFileUploaderDropzoneInstructions"] {
    display: none !important;
}
.v8-search-thumb {
    width: 76px;
    height: 76px;
    transition: transform 0.18s ease;
}
.v8-search-thumb:hover {
    transform: scale(1.55);
    z-index: 40;
}
@media (pointer: coarse), (hover: none) and (max-width: 1024px) {
    input,
    textarea,
    select,
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    div[data-baseweb="select"] input {
        font-size: 16px !important;
    }
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {
        min-height: 36px !important;
        height: auto !important;
    }
}
@media (max-width: 640px) {
    .stButton > button,
    .stDownloadButton > button,
    div[data-testid="stPopover"] button {
        font-size: 10.5px !important;
        min-height: 32px !important;
        padding: 4px 5px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: 5px 6px !important;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )

    # =====================================================================
    # ENCABEZADO DE 1 SOLA LÍNEA (REGLA 1): MODO + SUB-OPCIÓN + SKU / MUEBLE / MEDIDAS
    # =====================================================================
    with st.container(border=True):
        mode_labels = list(MODES.values())
        if st.session_state.get("v8_keep_mode") not in mode_labels:
            st.session_state["v8_keep_mode"] = mode_labels[0]

        cur_mode_preview = next(
            (k for k, v in MODES.items() if v == st.session_state["v8_keep_mode"]),
            "catalogo",
        )
        needs_sub = cur_mode_preview in ("vista_suelta", "material", "entorno")

        if needs_sub:
            h_mode, h_sub, h_sku = st.columns([0.95, 0.95, 3.1], vertical_alignment="center")
        else:
            h_mode, h_sku = st.columns([1.1, 3.9], vertical_alignment="center")
            h_sub = None

        with h_mode:
            mode_label = st.selectbox(
                "Modo",
                mode_labels,
                key="v8_keep_mode",
                label_visibility="collapsed",
            )
            mode = next(k for k, v in MODES.items() if v == mode_label)

        vista_id = "vista_3_4_derecha"
        material_mode = "fabric_only"
        lugar_casa = "Automático"

        if h_sub is not None:
            with h_sub:
                if mode == "vista_suelta":
                    view_opts = {k: v["label"] for k, v in ALL_SINGLE_VIEWS.items()}
                    view_labels = list(view_opts.values())
                    if st.session_state.get("v8_keep_vista") not in view_labels:
                        st.session_state["v8_keep_vista"] = view_opts["vista_3_4_derecha"]
                    vsel = st.selectbox("Vista", view_labels, key="v8_keep_vista", label_visibility="collapsed")
                    vista_id = next(k for k, v in view_opts.items() if v == vsel)
                elif mode == "material":
                    mat_labels = list(MATERIAL_MODES.keys())
                    if st.session_state.get("v8_keep_matmode") not in mat_labels:
                        st.session_state["v8_keep_matmode"] = mat_labels[0]
                    msel = st.selectbox("Material", mat_labels, key="v8_keep_matmode", label_visibility="collapsed")
                    material_mode = MATERIAL_MODES[msel]
                elif mode == "entorno":
                    if st.session_state.get("v8_keep_room") not in ROOM_PRESETS:
                        st.session_state["v8_keep_room"] = ROOM_PRESETS[0]
                    lugar_casa = st.selectbox("Espacio", ROOM_PRESETS, key="v8_keep_room", label_visibility="collapsed")

        with h_sku:
            sku = render_sku_autofill_bar("v8", inline_header=True)
            sku_code = (sku.get("sku") or "").strip().upper()
            tipo = sku["tipo_mueble"]
            medidas_final = sku["medidas"]

    # =====================================================================
    # ÁREA PRINCIPAL: INSUMOS (RENDER · SUBIR · COTIZACIÓN · SM) | PROMPTS V8
    # =====================================================================
    m_bytes: List[bytes] = []
    m_names: List[str] = []
    m_source: str = ""
    batch_views_files: List[Tuple[str, bytes]] = []
    wood_bytes: Optional[bytes] = None
    wood_name: str = ""
    wood_source: str = ""
    fabric_bytes: Optional[bytes] = None
    fabric_name: str = ""
    fabric_source: str = ""

    tick = int(st.session_state.get("v8_render_tick", 0))
    all_muebles_cat, all_telas_cat, all_maderas_cat = cargar_todo_catalogo_v8(tick)

    col_work, col_out = st.columns([1.2, 1.3], gap="small")

    with col_work:
        with st.container(border=True):
            folder_labels = list(FURNITURE_FOLDER_CHOICES.keys())
            if st.session_state.get("v8_keep_folder") not in folder_labels:
                st.session_state["v8_keep_folder"] = folder_labels[0]

            c_dir, c_pop = st.columns([1.85, 1.95], gap="small", vertical_alignment="center")
            with c_dir:
                folder_label = st.selectbox(
                    "Carpeta de fotos",
                    folder_labels,
                    key="v8_keep_folder",
                    label_visibility="collapsed",
                )
                folder_key = FURNITURE_FOLDER_CHOICES[folder_label]

            if mode == "vistas_tela":
                up_views = st.file_uploader(
                    "Vistas",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v8_batch_views_{ck}",
                    label_visibility="collapsed",
                )
                vb, vn = _read_files(up_views)
                batch_views_files = list(zip(vn, vb))
                fabric_bytes, fabric_name, fabric_source = _resolve_material_selector_v8("fabric", ck, all_telas_cat)
            elif mode == "clonar_color":
                u1, u2 = st.columns(2, gap="small")
                with u1:
                    up_ref_color = st.file_uploader(
                        "Base",
                        type=IMG_TYPES,
                        accept_multiple_files=False,
                        key=f"v8_clone_ref_{ck}",
                        label_visibility="collapsed",
                    )
                    m_bytes, m_names = _read_files(up_ref_color)
                    m_source = "Upload" if m_bytes else ""
                with u2:
                    up_views = st.file_uploader(
                        "Objetivo",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v8_clone_targets_{ck}",
                        label_visibility="collapsed",
                    )
                    vb, vn = _read_files(up_views)
                    batch_views_files = list(zip(vn, vb))
            else:
                m_bytes, m_names, m_source = _resolve_mueble_selector_v8(ck, folder_key, all_muebles_cat)
                if mode != "material" or material_mode in ("fabric_only", "dual"):
                    fabric_bytes, fabric_name, fabric_source = _resolve_material_selector_v8("fabric", ck, all_telas_cat)
                if mode != "material" or material_mode in ("wood_only", "dual"):
                    wood_bytes, wood_name, wood_source = _resolve_material_selector_v8("wood", ck, all_maderas_cat)

            loaded_entries: List[Dict[str, Any]] = []
            for nm, _raw in zip(m_names, m_bytes):
                loaded_entries.append({"kind": "mueble", "name": nm, "badge": f"🛋️ {m_source or 'Mueble'}"})
            if fabric_bytes:
                loaded_entries.append({"kind": "fabric", "name": fabric_name or "Tela", "badge": f"🧵 {fabric_source or 'Tela'}"})
            if wood_bytes:
                loaded_entries.append({"kind": "wood", "name": wood_name or "Madera", "badge": f"🪵 {wood_source or 'Madera'}"})
            for vn, _vb in batch_views_files:
                loaded_entries.append({"kind": "mueble", "name": vn, "badge": "🖼️ Vista"})

            with c_pop:
                _render_floating_photo_menu_v8(ck, loaded_entries, all_muebles_cat, all_telas_cat, all_maderas_cat, tick)

            notas = st.text_input(
                "Notas",
                key=f"v8_notas_{ck}",
                placeholder="📝 Notas opcionales",
                label_visibility="collapsed",
            )

            # ESTRICTAMENTE LOS 3 ÚNICOS BOTONES DIRECTOS (GEMINI.md Regla 1):
            # 1) 🚀 <Modo elegido> | 2) ↘️ 3/4 Derecha | 3) 🗑️ Borrar
            b_go, b_34, b_clr = st.columns([1.15, 1.25, 0.95], gap="small")
            with b_go:
                go = st.button(
                    f"🚀 {mode_label}",
                    type="primary",
                    use_container_width=True,
                    key=f"v8_btn_go_{ck}",
                )
            with b_34:
                btn_34_der = st.button(
                    "↘️ 3/4 Derecha",
                    use_container_width=True,
                    key=f"v8_btn_34_{ck}",
                )
            with b_clr:
                if st.button(
                    "🗑️ Borrar",
                    use_container_width=True,
                    key="v8_btn_clear",
                ):
                    _clear_v8_form(ck)

            status_slot = st.empty()

            # Tira propia V8 de 76x76 px con zoom hover y orden Image 1..N idéntico al prompt
            primary_fn_strip = (
                m_names[0]
                if m_names
                else (batch_views_files[0][0] if batch_views_files else "")
            )
            primary_name = (
                _extract_exact_photo_stem(primary_fn_strip, fallback=sku_code or "")
                if primary_fn_strip
                else (sku_code or "")
            )
            thumbs = build_ordered_photo_thumbs_v8(
                mode=mode,
                material_mode=material_mode,
                m_names=m_names,
                m_bytes=m_bytes,
                m_source=m_source,
                fabric_name=fabric_name,
                fabric_bytes=fabric_bytes,
                wood_name=wood_name,
                wood_bytes=wood_bytes,
                batch_views_files=batch_views_files,
                tipo_mueble=resolve_v8_furniture_type_hint(
                    tipo_mueble=tipo,
                    furniture_name=primary_name,
                    primary_filename=primary_fn_strip,
                ),
                medidas_texto=medidas_final,
                vista_id=vista_id,
            )
            render_v8_photos_strip_76(thumbs, key_prefix=f"v8_{ck}")

        # ------------------------------------------------------------------ BOTÓN 2: 3/4 DERECHA · BLANCO SIN SOMBRA · 2054x2054
        if btn_34_der:
            target_furn_bytes = m_bytes or ([batch_views_files[0][1]] if batch_views_files else [])
            target_furn_names = m_names or ([batch_views_files[0][0]] if batch_views_files else [])
            if not target_furn_bytes:
                status_slot.error("⚠️ Elige o sube la foto del mueble.")
            else:
                status_slot.info("⏳ Analizando tela +30% V8 y generando 3/4 Derecha...")
                try:
                    copied_furn_files = [
                        resolve_copied_photo_filename(fn, f"mueble_{i + 1}.png")
                        for i, fn in enumerate(target_furn_names)
                    ]
                    copied_wood_file = resolve_copied_photo_filename(wood_name, "madera.png") if wood_bytes else ""
                    copied_fabric_file = resolve_copied_photo_filename(fabric_name, "tela.png") if fabric_bytes else ""
                    first_photo_name = copied_furn_files[0] if copied_furn_files else ""
                    name = _extract_exact_photo_stem(first_photo_name, fallback=sku_code or "Mueble")
                    notas_ia = "\n".join(
                        p for p in [
                            f"Tipo de mueble: {tipo}" if tipo else "",
                            f"Medidas exactas: {medidas_final}" if medidas_final else "",
                            notas.strip(),
                        ] if p
                    )
                    f_ana, w_ana, t_ana = ai_prompt_service_v8.analyze_all_parallel(
                        furniture_bytes=target_furn_bytes,
                        wood_bytes=wood_bytes,
                        wood_name=copied_wood_file or wood_name,
                        fabric_bytes=fabric_bytes,
                        fabric_name=copied_fabric_file or fabric_name,
                        notas_ia=notas_ia,
                    )
                    resolved_tipo_34 = resolve_v8_furniture_type_hint(
                        tipo_mueble=tipo,
                        ai_furniture_item=str(f_ana.get("furniture_item") or ""),
                        furniture_name=name,
                        primary_filename=first_photo_name,
                    )
                    res = ai_prompt_service_v8.build_34_derecha_2054_prompts(
                        furniture_name=name,
                        furniture_analysis=f_ana,
                        wood_analysis=w_ana,
                        fabric_analysis=t_ana,
                        notas_usuario=notas.strip(),
                        tipo_mueble=tipo or resolved_tipo_34,
                        medidas_texto=medidas_final,
                        wood_label=wood_name,
                        fabric_label=fabric_name,
                        furniture_filenames=copied_furn_files,
                        wood_filename=copied_wood_file,
                        fabric_filename=copied_fabric_file,
                    )
                    pack_34 = ai_prompt_service_v8.build_v8_reference_pack(
                        mode="vista_34_der_2054",
                        furniture_name=name,
                        furniture_filenames=copied_furn_files,
                        furniture_bytes_list=target_furn_bytes,
                        furniture_source=m_source,
                        fabric_label=fabric_name,
                        fabric_filename=copied_fabric_file,
                        fabric_bytes=fabric_bytes,
                        wood_label=wood_name,
                        wood_filename=copied_wood_file,
                        wood_bytes=wood_bytes,
                        tipo_mueble=resolved_tipo_34,
                        medidas_texto=medidas_final,
                    )
                    ref_imgs = [
                        (p["filename"], prepare_exact_copy_image_bytes(p["bytes"])[0])
                        for p in pack_34
                        if p.get("bytes")
                    ]

                    gen_key = f"v8_gen_id_{ck}"
                    gen_id = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state[gen_key] = gen_id
                    res["gen_id"] = gen_id
                    res["mueble_name"] = name
                    res["ref_images"] = ref_imgs
                    st.session_state["v8_last_photo_stem"] = name
                    st.session_state["v7_last_photo_stem"] = name
                    if sku_code:
                        st.session_state["v8_last_sku"] = sku_code
                    st.session_state["v8_result"] = res
                    status_slot.empty()
                    st.toast(f"✅ Prompt V8 3/4 Derecha listo: {name}")
                except Exception as e:  # noqa: BLE001
                    status_slot.error(f"❌ {e}")

        # ------------------------------------------------------------------ BOTÓN 1: GENERAR MODO ELEGIDO
        if go:
            err = None
            eff_m_bytes = m_bytes
            eff_m_names = m_names
            eff_wood_bytes = wood_bytes
            eff_wood_name = wood_name
            eff_fabric_bytes = fabric_bytes
            eff_fabric_name = fabric_name
            hd_swatch_hint = ""

            if mode == "hd" and not eff_m_bytes and (fabric_bytes or wood_bytes):
                if fabric_bytes:
                    eff_m_bytes = [fabric_bytes]
                    eff_m_names = [fabric_name or "tela.png"]
                    eff_fabric_bytes = None
                    eff_fabric_name = ""
                    eff_wood_bytes = None
                    eff_wood_name = ""
                    hd_swatch_hint = "muestra de tela / swatch textil plano"
                elif wood_bytes:
                    eff_m_bytes = [wood_bytes]
                    eff_m_names = [wood_name or "madera.png"]
                    eff_wood_bytes = None
                    eff_wood_name = ""
                    eff_fabric_bytes = None
                    eff_fabric_name = ""
                    hd_swatch_hint = "muestra de madera / wood sample plano"

            if mode == "vistas_tela":
                if not batch_views_files:
                    err = "⚠️ Sube las vistas."
                elif not fabric_bytes:
                    err = "⚠️ Selecciona la tela."
            elif mode == "clonar_color":
                if not m_bytes or not batch_views_files:
                    err = "⚠️ Sube color base y vistas."
            else:
                if not eff_m_bytes:
                    err = "⚠️ Elige o sube la foto a mejorar." if mode == "hd" else "⚠️ Elige o sube la foto del mueble."
                elif mode == "material" and material_mode in ("wood_only", "dual") and not wood_bytes:
                    err = "⚠️ Selecciona madera."
                elif mode == "material" and material_mode in ("fabric_only", "dual") and not fabric_bytes:
                    err = "⚠️ Selecciona tela."

            if err:
                status_slot.error(err)
            else:
                status_slot.info(f"⏳ Calibrando escala +30% V8 y generando {mode_label}...")
                try:
                    copied_furn_files = [
                        resolve_copied_photo_filename(fn, f"mueble_{i + 1}.png")
                        for i, fn in enumerate(eff_m_names)
                    ]
                    copied_wood_file = resolve_copied_photo_filename(eff_wood_name, "madera.png") if eff_wood_bytes else ""
                    copied_fabric_file = resolve_copied_photo_filename(eff_fabric_name, "tela.png") if eff_fabric_bytes else ""
                    copied_batch_views = [
                        (resolve_copied_photo_filename(vn, f"vista_{i + 1}.png"), vb)
                        for i, (vn, vb) in enumerate(batch_views_files)
                    ]
                    first_photo_name = (
                        copied_furn_files[0]
                        if copied_furn_files
                        else (copied_batch_views[0][0] if copied_batch_views else "")
                    )
                    name = _extract_exact_photo_stem(first_photo_name, fallback=sku_code or "Mueble")
                    eff_tipo = tipo or hd_swatch_hint
                    notas_ia = "\n".join(
                        p for p in [
                            f"Tipo de mueble: {eff_tipo}" if eff_tipo else "",
                            f"Medidas exactas: {medidas_final}" if medidas_final else "",
                            notas.strip(),
                        ] if p
                    )
                    skip_f = mode in ("vistas_tela", "clonar_color")
                    f_ana, w_ana, t_ana = ai_prompt_service_v8.analyze_all_parallel(
                        furniture_bytes=eff_m_bytes,
                        wood_bytes=eff_wood_bytes,
                        wood_name=copied_wood_file or eff_wood_name,
                        fabric_bytes=(fabric_bytes if mode == "vistas_tela" else eff_fabric_bytes),
                        fabric_name=(copied_fabric_file or fabric_name) if mode == "vistas_tela" else (copied_fabric_file or eff_fabric_name),
                        notas_ia=notas_ia,
                        skip_furniture=skip_f,
                    )
                    if hd_swatch_hint:
                        f_ana["is_material_swatch"] = True

                    batch_ref = fabric_bytes if mode == "vistas_tela" else (eff_m_bytes[0] if mode == "clonar_color" else None)
                    batch_ref_fname = (
                        resolve_copied_photo_filename(fabric_name, "tela.png")
                        if mode == "vistas_tela"
                        else (copied_furn_files[0] if (mode == "clonar_color" and copied_furn_files) else "")
                    )
                    resolved_tipo_mode = resolve_v8_furniture_type_hint(
                        tipo_mueble=eff_tipo,
                        ai_furniture_item="" if hd_swatch_hint else str(f_ana.get("furniture_item") or ""),
                        furniture_name=name,
                        primary_filename=first_photo_name,
                    )

                    res = ai_prompt_service_v8.build_prompts(
                        mode=mode,
                        furniture_name=name,
                        furniture_analysis=f_ana,
                        wood_analysis=w_ana,
                        fabric_analysis=t_ana,
                        notas_usuario=notas.strip(),
                        tipo_mueble=(eff_tipo if mode == "hd" else (eff_tipo or resolved_tipo_mode)),
                        medidas_texto=medidas_final,
                        lugar_casa=lugar_casa,
                        vista_id=vista_id,
                        material_mode=material_mode,
                        wood_label=eff_wood_name,
                        fabric_label=(fabric_name if mode == "vistas_tela" else eff_fabric_name),
                        white_bg_enabled=(mode != "hd"),
                        classic_numbering=False,
                        batch_ref_bytes=batch_ref,
                        batch_views=copied_batch_views,
                        furniture_filenames=copied_furn_files,
                        wood_filename=copied_wood_file,
                        fabric_filename=(batch_ref_fname if mode == "vistas_tela" else copied_fabric_file),
                        batch_ref_filename=batch_ref_fname,
                    )

                    pack_mode = ai_prompt_service_v8.build_v8_reference_pack(
                        mode=mode,
                        vista_id=vista_id,
                        material_mode=material_mode,
                        furniture_name=name,
                        furniture_filenames=copied_furn_files,
                        furniture_bytes_list=eff_m_bytes,
                        furniture_source=m_source,
                        fabric_label=(fabric_name if mode == "vistas_tela" else eff_fabric_name),
                        fabric_filename=(batch_ref_fname if mode == "vistas_tela" else copied_fabric_file),
                        fabric_bytes=(fabric_bytes if mode == "vistas_tela" else eff_fabric_bytes),
                        wood_label=eff_wood_name,
                        wood_filename=copied_wood_file,
                        wood_bytes=eff_wood_bytes,
                        batch_views=copied_batch_views,
                        batch_ref_filename=batch_ref_fname,
                        batch_ref_bytes=batch_ref,
                        tipo_mueble=resolved_tipo_mode,
                        medidas_texto=medidas_final,
                        is_hd_swatch=bool(hd_swatch_hint),
                    )
                    ref_imgs = [
                        (p["filename"], prepare_exact_copy_image_bytes(p["bytes"])[0])
                        for p in pack_mode
                        if p.get("bytes")
                    ]

                    gen_key = f"v8_gen_id_{ck}"
                    gen_id = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state[gen_key] = gen_id
                    res["gen_id"] = gen_id
                    res["mueble_name"] = name
                    res["ref_images"] = ref_imgs
                    st.session_state["v8_last_photo_stem"] = name
                    st.session_state["v7_last_photo_stem"] = name
                    if sku_code:
                        st.session_state["v8_last_sku"] = sku_code
                    st.session_state["v8_result"] = res
                    status_slot.empty()
                    st.toast(f"✅ Prompts V8 listos ({mode_label}): {name}")
                except Exception as e:  # noqa: BLE001
                    status_slot.error(f"❌ {e}")

    # =====================================================================
    # COLUMNA DERECHA: SALIDA DE PROMPTS + 📐 2054px + 📦 ZIP + 🚀 SUBIR
    # =====================================================================
    with col_out:
        with st.container(border=True):
            res = st.session_state.get("v8_result")
            if not res:
                return

            gen_id = int(res.get("gen_id", 0))
            mueble_slug = res.get("mueble_name", "mueble")

            h_name, h_2054, h_zip, h_alta = st.columns([1.35, 0.85, 0.72, 0.78], gap="small", vertical_alignment="center")
            with h_name:
                st.markdown(f"**{mueble_slug}**")
            with h_2054:
                with st.popover("📐 2054px", use_container_width=True):
                    ext_up = st.file_uploader(
                        "2054",
                        type=IMG_TYPES,
                        key=f"v8_ext2054_{ck}_{gen_id}",
                        label_visibility="collapsed",
                    )
                    if ext_up:
                        fmt_img = ai_prompt_service_v8.format_image_2054_white(ext_up.getvalue(), target_px=2054)
                        st.download_button(
                            f"💾 {mueble_slug}.png",
                            data=fmt_img["png"],
                            file_name=f"{mueble_slug}.png",
                            mime="image/png",
                            use_container_width=True,
                            key=f"v8_ext_png_{ck}_{gen_id}",
                        )
                        st.download_button(
                            f"💾 {mueble_slug}.jpg",
                            data=fmt_img["jpg"],
                            file_name=f"{mueble_slug}.jpg",
                            mime="image/jpeg",
                            use_container_width=True,
                            key=f"v8_ext_jpg_{ck}_{gen_id}",
                        )
            with h_zip:
                if "_zip_bytes_cache" not in res:
                    res["_zip_bytes_cache"] = _build_zip_v8(res, include_images=True)
                st.download_button(
                    "📦 ZIP",
                    data=res["_zip_bytes_cache"],
                    file_name=f"{mueble_slug}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key=f"v8_dl_{ck}_{gen_id}",
                )
            with h_alta:
                if st.button(
                    "🚀 Subir",
                    use_container_width=True,
                    key=f"v8_goto_alta_{ck}_{gen_id}",
                    help="Ir directo a Alta de Fotos con este mismo nombre",
                ):
                    st.session_state["v8_last_photo_stem"] = mueble_slug
                    st.session_state["v7_last_photo_stem"] = mueble_slug
                    st.session_state["_pending_active_app"] = "🚀 Alta de Fotos"
                    st.rerun()

            items = res.get("items", [])
            if len(items) > 1:
                tabs = st.tabs([f"{i['icon']} {i['short_name']}" for i in items])
                for idx, (tab, item) in enumerate(zip(tabs, items)):
                    with tab:
                        _render_item_v8(item, idx, ck, gen_id)
            elif items:
                _render_item_v8(items[0], 0, ck, gen_id)

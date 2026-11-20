import base64
import concurrent.futures
import io
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from modules.sku_banner import render_sku_autofill_bar
from modules.ui_helpers import load_drive_file_cached, make_thumbnail_bytes, render_copy_button
from services.ai_prompt_service_v7 import (
    ALL_SINGLE_VIEWS,
    MODES,
    ROOM_PRESETS,
    ai_prompt_service_v7,
)
from services.sheets_service import SUBIR_DRIVE_ID, sheets_service

FOLDER_MUEBLES_RENDER_DRIVE_ID = "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX"
FOLDER_MUEBLES_SUBIR_DRIVE_ID = SUBIR_DRIVE_ID
LOCAL_RENDER_MUEBLES_DIR = Path(r"I:\Mi unidad\DOC ANIPA\Fotos general\Informacion mia\RENDER")
LOCAL_SUBIR_MUEBLES_DIR = Path(r"G:\Mi unidad\DOC ANIPA\Fotos general\Fotos de del proyeto\SUBIR")
LOCAL_COTIZACION_MUEBLES_DIR = Path(r"G:\Mi unidad\DOC ANIPA\Fotos general\Informacion de fotos\Cotizacipón")
FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_TELAS_ODOO_DRIVE_ID = "12gsKZVs6rFonOO8CIxokuE73bxhq8tS9"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"

FURNITURE_FOLDER_CHOICES: Dict[str, str] = {
    "📁 Todas las carpetas": "ALL",
    "🛋️ RENDER": "RENDER",
    "📥 SUBIR": "SUBIR",
    "💰 Cotización": "COTIZACION",
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
            ("Fotos general",),
            ("Fotos de del proyeto", "Fotos de del proyecto", "Fotos del proyecto"),
            ("SUBIR",),
        ],
        "local_rel_paths": [
            r"Mi unidad\DOC ANIPA\Fotos general\Fotos de del proyeto\SUBIR",
            r"Mi unidad\DOC ANIPA\Fotos general\Fotos de del proyecto\SUBIR",
            r"Mi unidad\DOC ANIPA\Fotos general\Fotos del proyecto\SUBIR",
        ],
    },
    "COTIZACION": {
        "source": "Cotización",
        "drive_id": "",
        "drive_path": [
            ("DOC ANIPA",),
            ("Fotos general",),
            ("Informacion de fotos", "Información de fotos"),
            ("Cotizacipón", "Cotización", "Cotizacion"),
        ],
        "local_rel_paths": [
            r"Mi unidad\DOC ANIPA\Fotos general\Informacion de fotos\Cotizacipón",
            r"Mi unidad\DOC ANIPA\Fotos general\Informacion de fotos\Cotización",
            r"Mi unidad\DOC ANIPA\Fotos general\Información de fotos\Cotizacipón",
            r"Mi unidad\DOC ANIPA\Fotos general\Información de fotos\Cotización",
        ],
    },
}

IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff", "jfif", "avif"]
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff", ".jfif", ".avif"}

MATERIAL_MODES = {
    "Solo tela": "fabric_only",
    "Solo madera": "wood_only",
    "Tela + madera": "dual",
}


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

    if os.name == "nt":
        spec = _FURNITURE_FOLDER_SPECS.get(folder_key, {})
        for drv in ("G:", "I:", "H:", "D:", "E:", "F:"):
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
    """Combina fotos de TELAS y FOTOS TELAS (Odoo) sin duplicados por ID ni nombre."""
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
            merged.append(dict(item))
    merged.sort(key=lambda x: str(x.get("name", "")).upper())
    return merged


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_muebles_v7(folder_key: str = "ALL", refresh_tick: int = 0) -> List[Dict[str, str]]:
    """Lee muebles de RENDER, SUBIR y Cotización en un solo lote BFS (local G:/I: + Google Drive)."""
    _ = refresh_tick
    keys = ["RENDER", "SUBIR", "COTIZACION"] if folder_key == "ALL" else [folder_key]

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(keys)) as ex:
        local_by_key = dict(zip(keys, ex.map(_scan_local_furniture_folder, keys)))

    drive_by_key: Dict[str, List[Dict[str, str]]] = {}
    try:
        if sheets_service.ensure_connected():
            folder_map = {k: _resolve_furniture_drive_id(k) for k in keys}
            drive_by_key = sheets_service.get_multiple_drive_folders_files(
                folder_map,
                recursive=True,
                max_depth=4,
                ttl=1800,
            )
    except Exception:
        drive_by_key = {}

    merged: List[Dict[str, str]] = []
    for k in keys:
        source_label = _FURNITURE_FOLDER_SPECS[k]["source"]
        loc_items = local_by_key.get(k, [])
        seen_local = {it["name"].strip().upper() for it in loc_items}
        merged.extend(loc_items)
        for d in drive_by_key.get(k, []):
            if d["name"].strip().upper() not in seen_local:
                item_copy = dict(d)
                item_copy["source"] = source_label
                merged.append(item_copy)
    return merged


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_muebles_render_v7(refresh_tick: int = 0) -> List[Dict[str, str]]:
    """Compatibilidad: lee la carpeta RENDER (local + Google Drive 1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX)."""
    return cargar_muebles_v7("RENDER", refresh_tick)


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_maderas_v7(include_drive: bool = True, refresh_tick: int = 0) -> List[Dict[str, str]]:
    _ = refresh_tick
    app_dir = Path(__file__).resolve().parent.parent
    local_maderas = _scan_local_dir(app_dir / "muestras_madera", recursive=False)
    seen = {m["name"].upper() for m in local_maderas}
    drive_maderas: List[Dict[str, str]] = []
    if include_drive:
        try:
            if sheets_service.ensure_connected():
                drive_maderas = sheets_service.get_drive_folder_files(
                    FOLDER_MADERAS_DRIVE_ID,
                    recursive=True,
                    max_depth=4,
                    ttl=1800,
                )
        except Exception:
            drive_maderas = []
    return local_maderas + [m for m in drive_maderas if m["name"].strip().upper() not in seen]


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_telas_v7(refresh_tick: int = 0) -> List[Dict[str, str]]:
    _ = refresh_tick
    try:
        if sheets_service.ensure_connected():
            batches = sheets_service.get_multiple_drive_folders_files(
                {
                    "TELAS": FOLDER_TELAS_DRIVE_ID,
                    "TELAS_ODOO": FOLDER_TELAS_ODOO_DRIVE_ID,
                },
                recursive=True,
                max_depth=4,
                ttl=1800,
            )
            return _merge_telas_lists(batches.get("TELAS", []), batches.get("TELAS_ODOO", []))
    except Exception:
        pass
    return []


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_todo_catalogo_v7(
    refresh_tick: int = 0,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[Dict[str, str]]]:
    """Carga muebles (RENDER, SUBIR, Cotización), telas (TELAS + FOTOS TELAS) y maderas en un solo BFS multi-raíz."""
    _ = refresh_tick
    f_keys = ["RENDER", "SUBIR", "COTIZACION"]
    app_dir = Path(__file__).resolve().parent.parent

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
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
                "TELAS": FOLDER_TELAS_DRIVE_ID,
                "TELAS_ODOO": FOLDER_TELAS_ODOO_DRIVE_ID,
                "MADERAS": FOLDER_MADERAS_DRIVE_ID,
            }
            drive_batches = sheets_service.get_multiple_drive_folders_files(
                folder_map,
                recursive=True,
                max_depth=4,
                ttl=1800,
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


def filter_catalog_photos_by_name(
    items: List[Dict[str, str]],
    query: str = "",
    active_names_upper: Optional[set] = None,
) -> List[Dict[str, str]]:
    """Filtra fotos cargadas en catálogo por nombre/archivo/carpeta (sin acentos ni mayúsculas)."""
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


def _pick_catalog_photo_cb(ck: int, kind: str, item: Dict[str, str]) -> None:
    """Callback del menú flotante para cargar una foto buscada por nombre."""
    st.session_state[f"v7_picked_{kind}_{ck}"] = dict(item)
    st.session_state[f"v7_apply_pick_{kind}_{ck}"] = True
    cur_sig = st.session_state.get(f"v7_cur_up_sig_{kind}_{ck}")
    if cur_sig:
        st.session_state[f"v7_ign_up_{kind}_{ck}"] = cur_sig


def _resolve_mueble_selector(
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
        tick = int(st.session_state.get("v7_render_tick", 0))
        catalog_items = list(cargar_muebles_v7(folder_key, tick))
    picked_item = st.session_state.get(f"v7_picked_mueble_{ck}")
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
    first_opt = f"🛋️ Mueble ({len(catalog_items)})..."

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

    sb_key = f"v7_sb_mueble_{ck}"
    if st.session_state.get(f"v7_apply_pick_mueble_{ck}") and picked_target_lbl:
        st.session_state[sb_key] = picked_target_lbl
        st.session_state[f"v7_apply_pick_mueble_{ck}"] = False
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
            key=f"v7_mueble_{ck}",
            label_visibility="collapsed",
        )

    if up_mueble:
        ub, un = _read_files(up_mueble)
        up_sig = "|".join(f"{n}:{len(b)}" for n, b in zip(un, ub))
        st.session_state[f"v7_cur_up_sig_mueble_{ck}"] = up_sig
        if up_sig != st.session_state.get(f"v7_ign_up_mueble_{ck}"):
            return ub, un, "Upload"
    else:
        st.session_state[f"v7_cur_up_sig_mueble_{ck}"] = ""

    if sel_name and sel_name in display_map:
        match = display_map[sel_name]
        raw_b = _load_catalog_item_bytes(match)
        if raw_b:
            return [raw_b], [match.get("filename") or f"{match['name']}.jpg"], match.get("source") or "RENDER"
    return [], [], ""


def _resolve_material_selector(
    kind: str,
    ck: int,
    catalog_items: List[Dict[str, str]],
) -> Tuple[Optional[bytes], str, str]:
    is_wood = kind == "wood"
    lbl = "🪵 Madera" if is_wood else "🧵 Tela"
    items_list = list(catalog_items)
    picked_item = st.session_state.get(f"v7_picked_{kind}_{ck}")
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

    first_opt = f"{lbl} ({len(items_list)})..."
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

    sb_key = f"v7_sb_{kind}_{ck}"
    if st.session_state.get(f"v7_apply_pick_{kind}_{ck}") and picked_target_lbl:
        st.session_state[sb_key] = picked_target_lbl
        st.session_state[f"v7_apply_pick_{kind}_{ck}"] = False
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
            key=f"v7_up_{kind}_{ck}",
            label_visibility="collapsed",
        )

    if up_file:
        ub = up_file.getvalue()
        uname = getattr(up_file, "name", lbl)
        up_sig = f"{uname}:{len(ub)}"
        st.session_state[f"v7_cur_up_sig_{kind}_{ck}"] = up_sig
        if up_sig != st.session_state.get(f"v7_ign_up_{kind}_{ck}"):
            return ub, uname, "Upload"
    else:
        st.session_state[f"v7_cur_up_sig_{kind}_{ck}"] = ""

    if sel_name and sel_name in display_map:
        match = display_map[sel_name]
        loaded = _load_catalog_item_bytes(match)
        if loaded:
            src = "Local" if match.get("local_path") else "Drive"
            return loaded, match.get("name") or sel_name, src
    return None, "", ""


def _render_mini_thumbs(thumbs: List[Tuple[str, bytes, str]]) -> None:
    """Muestra vistas previas más grandes y nítidas (76×76 px) de las fotos seleccionadas/cargadas."""
    if not thumbs:
        return
    cards: List[str] = []
    for lbl, raw_b, badge in thumbs:
        t_bytes = make_thumbnail_bytes(raw_b, max_dim=240)
        if not t_bytes:
            continue
        b64 = base64.b64encode(t_bytes).decode("ascii")
        safe_lbl = (lbl or "")[:24].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_badge = (badge or "Cargada")[:16].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cards.append(
            f'<div class="selected-thumb-card" style="display:flex;align-items:center;gap:8px;background:#0F172A;border:1px solid #0284C7;'
            f'border-radius:8px;padding:4px 8px 4px 4px;box-shadow:0 2px 8px rgba(0,0,0,0.35);" title="{safe_badge}: {safe_lbl}">'
            f'<img class="selected-photo-thumb" src="data:image/jpeg;base64,{b64}" style="width:76px;height:76px;object-fit:cover;border-radius:6px;display:block;flex-shrink:0;transition:transform 0.18s ease;" />'
            f'<div style="display:flex;flex-direction:column;gap:2px;line-height:1.25;">'
            f'<span style="font-size:10px;color:#4ADE80;font-weight:700;white-space:nowrap;">✅ {safe_badge}</span>'
            f'<span style="font-size:11px;color:#F8FAFC;font-weight:600;max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{safe_lbl}</span>'
            f'</div>'
            f'</div>'
        )
    if cards:
        st.markdown(
            f'<div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:4px;">{"".join(cards)}</div>',
            unsafe_allow_html=True,
        )


@st.cache_data(ttl=3600, max_entries=256, show_spinner=False)
def _load_drive_thumb_cached(file_id: str, thumbnail_link: str = "") -> Optional[bytes]:
    if not file_id:
        return None
    return sheets_service.get_drive_thumbnail_bytes(file_id, thumbnail_link)


def _get_search_preview_src(
    item: Dict[str, str],
    max_dim: int = 320,
    allow_network: bool = True,
) -> str:
    """Devuelve un data-URI base64 (o thumbnailLink directo) para visualizar una foto del catálogo al buscarla."""
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
            net_bytes = _load_drive_thumb_cached(f_id, t_link)
            if net_bytes:
                t_bytes = make_thumbnail_bytes(net_bytes, max_dim=max_dim)
                if t_bytes:
                    return f"data:image/jpeg;base64,{base64.b64encode(t_bytes).decode('ascii')}"
        elif t_link:
            return t_link
    return ""


def _preview_catalog_photo_cb(ck: int, item: Dict[str, str]) -> None:
    """Callback del botón 👁️ para visualizar en grande una foto en el buscador."""
    st.session_state[f"v7_preview_item_{ck}"] = dict(item)


@st.cache_data(ttl=600, max_entries=64, show_spinner=False)
def _search_drive_live_cached(query_str: str) -> List[Dict[str, str]]:
    try:
        if sheets_service.ensure_connected():
            return sheets_service.search_drive_images_live(
                query_text=query_str,
                limit=12,
                folder_id=FOLDER_MUEBLES_RENDER_DRIVE_ID,
            )
    except Exception:
        pass
    return []


def _render_floating_photo_menu(
    ck: int,
    loaded_entries: List[Dict[str, Any]],
    all_muebles: List[Dict[str, str]],
    all_telas: List[Dict[str, str]],
    all_maderas: List[Dict[str, str]],
) -> None:
    """Menú flotante (popover) con buscador de fotos por nombre, visualizador de foto y estado de fotos cargadas."""
    n_loaded = len(loaded_entries)
    total_cat = len(all_muebles) + len(all_telas) + len(all_maderas)
    if n_loaded > 0:
        pop_label = f"🔍 Fotos · ✅ {n_loaded} cargada{'s' if n_loaded != 1 else ''}"
    else:
        pop_label = f"🔍 Buscar foto ({total_cat})"

    with st.popover(pop_label, use_container_width=True):
        # 1. FOTOS CARGADAS ACTUALMENTE EN EL ESTUDIO
        loaded_html_parts: List[str] = []
        slots_status = {"mueble": False, "fabric": False, "wood": False}
        active_names_upper = set()

        for entry in loaded_entries:
            slots_status[entry.get("kind", "mueble")] = True
            e_name = str(entry.get("name") or "Foto").strip()
            active_names_upper.add(os.path.splitext(e_name)[0].strip().upper())
            active_names_upper.add(e_name.upper())
            e_role = str(entry.get("role") or "Foto")
            e_src = str(entry.get("source") or "Cargada")
            raw_b = entry.get("bytes") or b""
            t_bytes = make_thumbnail_bytes(raw_b, max_dim=240) if raw_b else b""
            img_tag = ""
            if t_bytes:
                b64 = base64.b64encode(t_bytes).decode("ascii")
                img_tag = (
                    f'<img class="selected-photo-thumb" src="data:image/jpeg;base64,{b64}" '
                    f'style="width:68px;height:68px;object-fit:cover;border-radius:6px;flex-shrink:0;transition:transform 0.18s ease;" />'
                )
            safe_name = e_name[:28].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe_role = e_role.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe_src = e_src.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            loaded_html_parts.append(
                f'<div style="display:flex;align-items:center;gap:8px;background:#0F172A;border:1px solid #0284C7;'
                f'border-radius:8px;padding:4px 8px 4px 4px;min-width:140px;">'
                f'{img_tag}'
                f'<div style="display:flex;flex-direction:column;gap:2px;line-height:1.25;overflow:hidden;">'
                f'<span style="font-size:10px;color:#4ADE80;font-weight:700;">✅ {safe_role} · [{safe_src}]</span>'
                f'<span style="font-size:11px;color:#F8FAFC;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{safe_name}</span>'
                f'</div></div>'
            )

        missing_chips: List[str] = []
        for k_slot, lbl_slot in (("mueble", "🛋️ Mueble"), ("fabric", "🧵 Tela"), ("wood", "🪵 Madera")):
            if not slots_status.get(k_slot):
                missing_chips.append(
                    f'<span style="font-size:9.5px;color:#94A3B8;background:#1E293B;border:1px dashed #334155;'
                    f'border-radius:999px;padding:1px 7px;">⚪ {lbl_slot}: sin cargar</span>'
                )

        n_ren = sum(1 for x in all_muebles if x.get("source") == "RENDER")
        n_sub = sum(1 for x in all_muebles if x.get("source") == "SUBIR")
        n_cot = sum(1 for x in all_muebles if x.get("source") == "Cotización")

        status_block = (
            f'<div style="margin-bottom:4px;">'
            f'<div style="font-size:10.5px;font-weight:700;color:#7DD3FC;margin-bottom:3px;">'
            f'📌 Fotos cargadas activas ({n_loaded})</div>'
            + (
                f'<div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:4px;">{"".join(loaded_html_parts)}</div>'
                if loaded_html_parts
                else ""
            )
            + (
                f'<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:4px;">{"".join(missing_chips)}</div>'
                if missing_chips
                else ""
            )
            + f'<div style="font-size:9.5px;color:#94A3B8;background:#0F172A;border:1px solid #1E293B;border-radius:5px;padding:2px 6px;">'
            f'📂 En carpetas: <b>RENDER</b> ({n_ren}) · <b>SUBIR</b> ({n_sub}) · <b>Cotización</b> ({n_cot}) · '
            f'<b>Telas</b> ({len(all_telas)}) · <b>Maderas</b> ({len(all_maderas)})</div>'
            f'</div>'
        )
        st.markdown(status_block, unsafe_allow_html=True)

        # 2. BUSCADOR DE FOTOS POR NOMBRE
        c_q, c_cat = st.columns([1.85, 1.15], gap="small", vertical_alignment="center")
        with c_q:
            q_text = st.text_input(
                "Buscar foto por nombre",
                placeholder="🔎 Buscar foto por nombre...",
                key=f"v7_pop_q_{ck}",
                label_visibility="collapsed",
            )
        with c_cat:
            cat_filter = st.selectbox(
                "Categoría",
                [
                    "📁 Todas",
                    "🛋️ Muebles",
                    "🛋️ RENDER",
                    "📥 SUBIR",
                    "💰 Cotización",
                    "🧵 Telas",
                    "🪵 Maderas",
                ],
                key=f"v7_pop_cat_{ck}",
                label_visibility="collapsed",
            )

        pool: List[Dict[str, str]] = []
        if cat_filter in ("📁 Todas", "🛋️ Muebles", "🛋️ RENDER", "📥 SUBIR", "💰 Cotización"):
            for m in all_muebles:
                src = m.get("source") or "RENDER"
                if cat_filter == "🛋️ RENDER" and src != "RENDER":
                    continue
                if cat_filter == "📥 SUBIR" and src != "SUBIR":
                    continue
                if cat_filter == "💰 Cotización" and src != "Cotización":
                    continue
                item_m = dict(m)
                item_m["kind"] = "mueble"
                item_m["source"] = src
                item_m["badge"] = f"🛋️ {src}"
                pool.append(item_m)
        if cat_filter in ("📁 Todas", "🧵 Telas"):
            for t in all_telas:
                item_t = dict(t)
                item_t["kind"] = "fabric"
                item_t["source"] = "Telas"
                item_t["badge"] = "🧵 Tela"
                pool.append(item_t)
        if cat_filter in ("📁 Todas", "🪵 Maderas"):
            for w in all_maderas:
                item_w = dict(w)
                item_w["kind"] = "wood"
                item_w["source"] = "Maderas"
                item_w["badge"] = "🪵 Madera"
                pool.append(item_w)

        matches = filter_catalog_photos_by_name(pool, q_text, active_names_upper)

        if q_text.strip() and len(q_text.strip()) >= 3 and not matches:
            for lh in _search_drive_live_cached(q_text.strip()):
                clean_nm = os.path.splitext(lh.get("name", ""))[0].strip() or lh.get("name", "Foto")
                matches.append({
                    "id": lh["id"],
                    "name": clean_nm,
                    "filename": lh.get("name", f"{clean_nm}.jpg"),
                    "source": "Drive",
                    "kind": "mueble",
                    "badge": "☁️ Drive",
                    "thumbnailLink": lh.get("thumbnailLink", ""),
                })

        # 3. VISUALIZADOR DE FOTO BUSCADA (automático al escribir nombre o al pulsar 👁️)
        explicit_prev = st.session_state.get(f"v7_preview_item_{ck}")
        preview_target: Optional[Dict[str, str]] = None
        if q_text.strip() and matches:
            if isinstance(explicit_prev, dict) and any(
                x.get("name") == explicit_prev.get("name") and x.get("source") == explicit_prev.get("source")
                for x in matches
            ):
                preview_target = explicit_prev
            else:
                preview_target = matches[0]
        elif isinstance(explicit_prev, dict) and explicit_prev.get("name"):
            preview_target = explicit_prev

        if preview_target:
            prev_src = _get_search_preview_src(preview_target, max_dim=360, allow_network=True)
            p_name = preview_target.get("name", "Foto")
            p_badge = preview_target.get("badge", "📁 Foto")
            p_kind = preview_target.get("kind", "mueble")
            p_fname = preview_target.get("filename") or f"{p_name}.jpg"
            p_is_loaded = (
                p_name.strip().upper() in active_names_upper
                or p_fname.strip().upper() in active_names_upper
            )
            safe_pname = p_name[:34].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe_pbadge = p_badge.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe_pfname = p_fname[:36].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            img_box = (
                f'<img class="selected-photo-thumb" src="{prev_src}" '
                f'style="width:132px;height:132px;object-fit:cover;border-radius:8px;border:1px solid #38BDF8;'
                f'background:#020617;flex-shrink:0;transition:transform 0.18s ease;" />'
                if prev_src
                else (
                    '<div style="width:132px;height:132px;border-radius:8px;border:1px dashed #334155;'
                    'background:#0F172A;display:flex;align-items:center;justify-content:center;'
                    'font-size:10px;color:#64748B;flex-shrink:0;">🖼️ Sin vista previa</div>'
                )
            )
            pv_col_img, pv_col_act = st.columns([2.25, 1.05], gap="small", vertical_alignment="center")
            with pv_col_img:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;background:#0F172A;border:1px solid #0284C7;'
                    f'border-radius:9px;padding:6px;margin:2px 0;">'
                    f'{img_box}'
                    f'<div style="display:flex;flex-direction:column;gap:3px;overflow:hidden;line-height:1.25;">'
                    f'<span style="font-size:10px;color:#38BDF8;font-weight:700;">👁️ Vista previa · {safe_pbadge}</span>'
                    f'<span style="font-size:12px;color:#F8FAFC;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{safe_pname}</span>'
                    f'<span style="font-size:9.5px;color:#94A3B8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{safe_pfname}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
            with pv_col_act:
                st.button(
                    "✅ Cargada" if p_is_loaded else "➕ Cargar foto",
                    key=f"v7_pick_prev_{p_kind}_{ck}",
                    type="primary",
                    use_container_width=True,
                    on_click=_pick_catalog_photo_cb,
                    args=(ck, p_kind, preview_target),
                )

        # Pre-cargar miniaturas en paralelo de los primeros 6 resultados cuando el usuario escribe una búsqueda
        if q_text.strip() and matches:
            top_to_warm = [
                m for m in matches[:6]
                if m.get("id")
                and f"thumb:{m['id']}" not in sheets_service._drive_file_bytes_cache
                and m["id"] not in sheets_service._drive_file_bytes_cache
            ]
            if top_to_warm:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(top_to_warm))) as ex:
                    for _ in ex.map(
                        lambda m: sheets_service.get_drive_thumbnail_bytes(
                            m["id"], m.get("thumbnailLink", "")
                        ),
                        top_to_warm,
                    ):
                        pass

        st.caption(
            f"🔎 {len(matches)} resultado{'s' if len(matches) != 1 else ''}"
            + (f" para «{q_text.strip()}»" if q_text.strip() else " disponibles en catálogo (pulsa 👁️ para visualizar)")
        )

        max_rows = 35 if q_text.strip() else 24
        with st.container(height=225, border=True):
            if not matches:
                st.caption("No se encontraron fotos con ese nombre.")
            else:
                for idx_m, it in enumerate(matches[:max_rows]):
                    it_name = it.get("name", "Foto")
                    it_badge = it.get("badge", "📁 Foto")
                    it_kind = it.get("kind", "mueble")
                    is_loaded = (
                        it_name.strip().upper() in active_names_upper
                        or (it.get("filename", "").strip().upper() in active_names_upper)
                    )
                    allow_net_row = bool(q_text.strip() and idx_m < 6)
                    row_thumb_src = _get_search_preview_src(it, max_dim=140, allow_network=allow_net_row)
                    thumb_html = (
                        f'<img class="selected-photo-thumb" src="{row_thumb_src}" '
                        f'style="width:44px;height:44px;object-fit:cover;border-radius:5px;border:1px solid #334155;'
                        f'flex-shrink:0;transition:transform 0.18s ease;" />'
                        if row_thumb_src
                        else ""
                    )
                    safe_it_name = it_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    safe_it_badge = it_badge.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    r_info, r_eye, r_btn = st.columns([2.35, 0.45, 0.95], gap="small", vertical_alignment="center")
                    with r_info:
                        status_icon = "✅ " if is_loaded else ""
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:7px;padding:1px 0;overflow:hidden;">'
                            f'{thumb_html}'
                            f'<div style="font-size:10.5px;line-height:1.25;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                            f'<span style="color:#38BDF8;font-weight:700;">{safe_it_badge}</span> · '
                            f'<span style="color:{"#4ADE80" if is_loaded else "#F8FAFC"};font-weight:{"700" if is_loaded else "500"};">'
                            f'{status_icon}{safe_it_name}</span></div></div>',
                            unsafe_allow_html=True,
                        )
                    with r_eye:
                        st.button(
                            "👁️",
                            key=f"v7_eye_{it_kind}_{idx_m}_{ck}",
                            help=f"Visualizar {it_name}",
                            use_container_width=True,
                            on_click=_preview_catalog_photo_cb,
                            args=(ck, it),
                        )
                    with r_btn:
                        st.button(
                            "✅ Cargada" if is_loaded else "➕ Cargar",
                            key=f"v7_pick_{it_kind}_{idx_m}_{ck}",
                            use_container_width=True,
                            on_click=_pick_catalog_photo_cb,
                            args=(ck, it_kind, it),
                        )


def _clear_v7_form(ck: int) -> None:
    """Limpia fotos, SKU, notas y salida SIN cambiar el modo ni sub-opción activa."""
    clear_prefixes = (
        "v7_result",
        "v7_notas_",
        "v7_sb_",
        "v7_up_",
        "v7_mueble_",
        "v7_batch_",
        "v7_clone_",
        "v7_ext2054_",
        "v7_picked_",
        "v7_preview_item_",
        "v7_apply_pick_",
        "v7_ign_up_",
        "v7_cur_up_sig_",
        "v7_pop_",
        "sku_",
        "field_",
    )
    for k in [k for k in list(st.session_state.keys()) if k.startswith(clear_prefixes)]:
        del st.session_state[k]
    st.session_state.clear_key_v7 = ck + 1
    st.rerun()


def _build_zip(res: Dict[str, Any], include_images: bool = False) -> bytes:
    buf = io.BytesIO()
    mueble_slug = res.get("mueble_name", "mueble")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, it in enumerate(res.get("items", []), start=1):
            guide = it.get("attachment_guide") or []
            guide_txt = "\n".join(f"  - {g}" for g in guide) if guide else "  - Image 1: Foto del mueble"
            body = (
                f"=== ORDEN DE IMÁGENES ===\n{guide_txt}\n\n"
                f"--- GOOGLE AI STUDIO / GEMINI ---\n{it.get('google_ai_studio', '')}\n\n"
                f"--- CHATGPT ---\n{it.get('chatgpt_dalle3', '')}\n\n"
                f"--- MIDJOURNEY ---\n{it.get('midjourney_v6', '')}\n"
            )
            z.writestr(f"prompts/{i:02d}_{it['id']}.txt", body)

            gen_photo = it.get("generated_photo")
            if isinstance(gen_photo, dict) and gen_photo.get("png"):
                fname_png = f"{i:02d}_{mueble_slug}_{it['id']}_2054x2054.png"
                z.writestr(f"fotos_generadas_2054/{fname_png}", gen_photo["png"])

        if res.get("master_ais"):
            z.writestr(
                "prompts/00_prompt_maestro_secuencial.txt",
                res["master_ais"] + "\n\n====================\n\n" + res.get("master_dal", ""),
            )

        if include_images:
            for idx, (fname, raw) in enumerate(res.get("ref_images", []), start=1):
                safe_name = os.path.basename(fname or f"ref_{idx}.jpg")
                z.writestr(f"insumos/{idx:02d}_{safe_name}", raw)
    return buf.getvalue()


def _render_item(item: Dict[str, Any], idx: int, ck: int, gen_id: int) -> None:
    t_ais, t_dal, t_mj = st.tabs(["AI Studio", "ChatGPT", "Midjourney"])
    with t_ais:
        txt = item.get("google_ai_studio", "")
        render_copy_button(txt, label="📋 Copiar", key=f"v7_cp_ais_{idx}_{ck}_{gen_id}")
        st.text_area("Prompt", txt, height=165, key=f"v7_ais_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_dal:
        txt = item.get("chatgpt_dalle3", "")
        render_copy_button(txt, label="📋 Copiar", key=f"v7_cp_dal_{idx}_{ck}_{gen_id}")
        st.text_area("Prompt", txt, height=165, key=f"v7_dal_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_mj:
        txt = item.get("midjourney_v6", "")
        render_copy_button(txt, label="📋 Copiar", key=f"v7_cp_mj_{idx}_{ck}_{gen_id}")
        st.text_area("Prompt", txt, height=115, key=f"v7_mj_{idx}_{ck}_{gen_id}", label_visibility="collapsed")


def render_prompt_studio_v7() -> None:
    if "clear_key_v7" not in st.session_state:
        st.session_state.clear_key_v7 = 0
    ck = st.session_state.clear_key_v7

    st.markdown(
        """
<style>
.stButton > button,
.stDownloadButton > button,
div[data-testid="stPopover"] > div > button {
    font-size: 11px !important;
    font-weight: 600 !important;
    min-height: 30px !important;
    height: 30px !important;
    padding: 2px 8px !important;
    border-radius: 6px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    box-sizing: border-box !important;
    max-width: 100% !important;
}
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    min-height: 30px !important;
    height: 30px !important;
    font-size: 11px !important;
    padding-top: 0px !important;
    padding-bottom: 0px !important;
}
div[data-baseweb="select"] span,
input,
textarea {
    font-size: 11px !important;
}
section[data-testid="stFileUploaderDropzone"] {
    padding: 0px !important;
    min-height: 30px !important;
    border: none !important;
    background: transparent !important;
}
section[data-testid="stFileUploaderDropzone"] svg,
section[data-testid="stFileUploaderDropzone"] small,
section[data-testid="stFileUploaderDropzone"] span[data-testid="stMarkdownContainer"],
div[data-testid="stFileUploaderDropzoneInstructions"] {
    display: none !important;
}
section[data-testid="stFileUploaderDropzone"] button {
    font-size: 11px !important;
    min-height: 30px !important;
    height: 30px !important;
    padding: 2px 8px !important;
    width: 100% !important;
    margin: 0px !important;
    border-radius: 6px !important;
    box-sizing: border-box !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}
div[data-testid="stHorizontalBlock"] {
    gap: 0.45rem !important;
}
div[data-testid="stVerticalBlock"] > div {
    gap: 0.30rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 8px 10px !important;
}
button[data-baseweb="tab"] {
    padding: 2px 8px !important;
    font-size: 11px !important;
    min-height: 26px !important;
}
div[data-testid="stPopover"] > div > button {
    border: 1px solid #0284C7 !important;
    background: linear-gradient(135deg, rgba(2,132,199,0.18), rgba(15,23,42,0.92)) !important;
    color: #7DD3FC !important;
}
div[data-testid="stPopover"] > div > button:hover {
    border-color: #38BDF8 !important;
    color: #FFFFFF !important;
}
div[data-baseweb="popover"] > div {
    min-width: min(410px, 94vw) !important;
    max-width: min(460px, 96vw) !important;
    background-color: #1E293B !important;
    border: 1px solid #0284C7 !important;
    border-radius: 10px !important;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.7) !important;
}
.selected-photo-thumb:hover {
    transform: scale(1.35);
    z-index: 20;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.65);
}
@media (max-width: 640px) {
    .stButton > button,
    .stDownloadButton > button {
        font-size: 10.5px !important;
        padding: 2px 6px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: 6px 6px !important;
    }
}
</style>
""",
        unsafe_allow_html=True,
    )

    # =====================================================================
    # ENCABEZADO DE 1 SOLA LÍNEA: MODO + SUB-OPCIÓN + SKU / MUEBLE / MEDIDAS
    # =====================================================================
    with st.container(border=True):
        mode_labels = list(MODES.values())
        if st.session_state.get("v7_keep_mode") not in mode_labels:
            st.session_state["v7_keep_mode"] = mode_labels[0]

        cur_mode_preview = next(
            (k for k, v in MODES.items() if v == st.session_state["v7_keep_mode"]),
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
                key="v7_keep_mode",
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
                    if st.session_state.get("v7_keep_vista") not in view_labels:
                        st.session_state["v7_keep_vista"] = view_opts["vista_3_4_derecha"]
                    vsel = st.selectbox("Vista", view_labels, key="v7_keep_vista", label_visibility="collapsed")
                    vista_id = next(k for k, v in view_opts.items() if v == vsel)
                elif mode == "material":
                    mat_labels = list(MATERIAL_MODES.keys())
                    if st.session_state.get("v7_keep_matmode") not in mat_labels:
                        st.session_state["v7_keep_matmode"] = mat_labels[0]
                    msel = st.selectbox("Material", mat_labels, key="v7_keep_matmode", label_visibility="collapsed")
                    material_mode = MATERIAL_MODES[msel]
                elif mode == "entorno":
                    if st.session_state.get("v7_keep_room") not in ROOM_PRESETS:
                        st.session_state["v7_keep_room"] = ROOM_PRESETS[0]
                    lugar_casa = st.selectbox("Espacio", ROOM_PRESETS, key="v7_keep_room", label_visibility="collapsed")

        with h_sku:
            sku = render_sku_autofill_bar("v7", inline_header=True)
            sku_code = (sku.get("sku") or "").strip().upper()
            tipo = sku["tipo_mueble"]
            medidas_final = sku["medidas"]

    # =====================================================================
    # ÁREA PRINCIPAL: INSUMOS (RENDER · SUBIR · COTIZACIÓN) | PROMPTS
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

    tick = int(st.session_state.get("v7_render_tick", 0))
    all_muebles_cat, all_telas_cat, all_maderas_cat = cargar_todo_catalogo_v7(tick)
    if not all_telas_cat and not st.session_state.get(f"v7_retried_telas_{tick}"):
        st.session_state[f"v7_retried_telas_{tick}"] = True
        cargar_todo_catalogo_v7.clear()
        all_muebles_cat, all_telas_cat, all_maderas_cat = cargar_todo_catalogo_v7(tick)

    col_work, col_out = st.columns([1.18, 1.32], gap="small")

    with col_work:
        with st.container(border=True):
            folder_labels = list(FURNITURE_FOLDER_CHOICES.keys())
            if st.session_state.get("v7_keep_folder") not in folder_labels:
                st.session_state["v7_keep_folder"] = folder_labels[0]

            c_dir, c_pop, c_ref = st.columns([1.85, 1.95, 0.52], gap="small", vertical_alignment="center")
            with c_dir:
                folder_label = st.selectbox(
                    "Carpeta de fotos",
                    folder_labels,
                    key="v7_keep_folder",
                    label_visibility="collapsed",
                )
                folder_key = FURNITURE_FOLDER_CHOICES[folder_label]
            with c_ref:
                if st.button(
                    "🔄",
                    use_container_width=True,
                    key=f"v7_btn_refresh_{ck}",
                    help="Actualizar fotos de RENDER, SUBIR y Cotización",
                ):
                    sheets_service._drive_folder_tree_cache.clear()
                    sheets_service._resolved_folder_ids.clear()
                    sheets_service._save_disk_catalog_cache()
                    cargar_todo_catalogo_v7.clear()
                    cargar_muebles_v7.clear()
                    cargar_telas_v7.clear()
                    cargar_maderas_v7.clear()
                    st.session_state["v7_render_tick"] = tick + 1
                    st.rerun()

            if mode == "vistas_tela":
                st.caption("🖼️ Vistas")
                up_views = st.file_uploader(
                    "Vistas",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_batch_views_{ck}",
                    label_visibility="collapsed",
                )
                vb, vn = _read_files(up_views)
                batch_views_files = list(zip(vn, vb))
                fabric_bytes, fabric_name, fabric_source = _resolve_material_selector("fabric", ck, all_telas_cat)
            elif mode == "clonar_color":
                u1, u2 = st.columns(2, gap="small")
                with u1:
                    st.caption("🎨 Color base")
                    up_ref_color = st.file_uploader(
                        "Base",
                        type=IMG_TYPES,
                        accept_multiple_files=False,
                        key=f"v7_clone_ref_{ck}",
                        label_visibility="collapsed",
                    )
                    m_bytes, m_names = _read_files(up_ref_color)
                    if m_bytes:
                        m_source = "Upload"
                with u2:
                    st.caption("🖼️ Vistas")
                    up_views = st.file_uploader(
                        "Objetivo",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_clone_targets_{ck}",
                        label_visibility="collapsed",
                    )
                    vb, vn = _read_files(up_views)
                    batch_views_files = list(zip(vn, vb))
            else:
                m_bytes, m_names, m_source = _resolve_mueble_selector(ck, folder_key, all_muebles_cat)
                if mode != "material" or material_mode in ("fabric_only", "dual"):
                    fabric_bytes, fabric_name, fabric_source = _resolve_material_selector("fabric", ck, all_telas_cat)
                if mode != "material" or material_mode in ("wood_only", "dual"):
                    wood_bytes, wood_name, wood_source = _resolve_material_selector("wood", ck, all_maderas_cat)

            loaded_entries: List[Dict[str, Any]] = []
            for nm, raw in zip(m_names, m_bytes):
                loaded_entries.append({
                    "kind": "mueble",
                    "role": "🛋️ Mueble",
                    "name": nm,
                    "source": m_source or "RENDER",
                    "bytes": raw,
                })
            if fabric_bytes:
                loaded_entries.append({
                    "kind": "fabric",
                    "role": "🧵 Tela",
                    "name": fabric_name or "Tela",
                    "source": fabric_source or "Telas",
                    "bytes": fabric_bytes,
                })
            if wood_bytes:
                loaded_entries.append({
                    "kind": "wood",
                    "role": "🪵 Madera",
                    "name": wood_name or "Madera",
                    "source": wood_source or "Maderas",
                    "bytes": wood_bytes,
                })
            for vn, vb in batch_views_files:
                loaded_entries.append({
                    "kind": "mueble",
                    "role": "🖼️ Vista",
                    "name": vn,
                    "source": "Lote",
                    "bytes": vb,
                })

            with c_pop:
                _render_floating_photo_menu(
                    ck=ck,
                    loaded_entries=loaded_entries,
                    all_muebles=all_muebles_cat,
                    all_telas=all_telas_cat,
                    all_maderas=all_maderas_cat,
                )

            notas = st.text_input(
                "Notas",
                key=f"v7_notas_{ck}",
                placeholder="📝 Notas opcionales",
                label_visibility="collapsed",
            )

            # 3 BOTONES CON SENTIDO CLARO:
            # 1) Generar el modo elegido arriba | 2) 3/4 Derecha sin sombra (2054) | 3) Borrar (sin mover el modo)
            b_go, b_34, b_clr = st.columns([1.15, 1.25, 0.85], gap="small")
            with b_go:
                go = st.button(
                    f"🚀 {mode_label}",
                    type="primary",
                    use_container_width=True,
                    key=f"v7_btn_go_{ck}",
                )
            with b_34:
                btn_34_der = st.button(
                    "↘️ 3/4 Derecha",
                    use_container_width=True,
                    key=f"v7_btn_34_{ck}",
                )
            with b_clr:
                if st.button(
                    "🗑️ Borrar",
                    use_container_width=True,
                    key="v7_btn_clear",
                ):
                    _clear_v7_form(ck)

            thumbs: List[Tuple[str, bytes, str]] = []
            for nm, raw in zip(m_names[:2], m_bytes[:2]):
                thumbs.append((nm, raw, f"🛋️ {m_source or 'Mueble'}"))
            if fabric_bytes:
                thumbs.append((fabric_name or "Tela", fabric_bytes, f"🧵 {fabric_source or 'Tela'}"))
            if wood_bytes:
                thumbs.append((wood_name or "Madera", wood_bytes, f"🪵 {wood_source or 'Madera'}"))
            for vn, vb in batch_views_files[:2]:
                thumbs.append((vn, vb, "🖼️ Vista"))

            _render_mini_thumbs(thumbs)

        # ------------------------------------------------------------------ BOTÓN 2: 3/4 DERECHA · BLANCO SIN SOMBRA · 2054×2054
        if btn_34_der:
            target_furn_bytes = m_bytes or ([batch_views_files[0][1]] if batch_views_files else [])
            target_furn_names = m_names or ([batch_views_files[0][0]] if batch_views_files else [])
            if not target_furn_bytes:
                st.error("⚠️ Elige o sube la foto del mueble.")
            else:
                with st.spinner("Generando 3/4 Derecha..."):
                    try:
                        name = sku_code or (target_furn_names[0].rsplit(".", 1)[0] if target_furn_names else "Mueble")
                        notas_ia = "\n".join(
                            p for p in [
                                f"Tipo de mueble: {tipo}" if tipo else "",
                                f"Medidas exactas: {medidas_final}" if medidas_final else "",
                                notas.strip(),
                            ] if p
                        )
                        f_ana, w_ana, t_ana = ai_prompt_service_v7.analyze_all_parallel(
                            furniture_bytes=target_furn_bytes,
                            wood_bytes=wood_bytes,
                            wood_name=wood_name,
                            fabric_bytes=fabric_bytes,
                            fabric_name=fabric_name,
                            notas_ia=notas_ia,
                        )
                        res = ai_prompt_service_v7.build_34_derecha_2054_prompts(
                            furniture_name=name,
                            furniture_analysis=f_ana,
                            wood_analysis=w_ana,
                            fabric_analysis=t_ana,
                            notas_usuario=notas.strip(),
                            tipo_mueble=tipo,
                            medidas_texto=medidas_final,
                            wood_label=wood_name,
                            fabric_label=fabric_name,
                        )

                        ref_imgs = list(zip(target_furn_names, target_furn_bytes))
                        if wood_bytes:
                            ref_imgs.append((f"madera_{wood_name or 'muestra'}.jpg", wood_bytes))
                        if fabric_bytes:
                            ref_imgs.append((f"tela_{fabric_name or 'muestra'}.jpg", fabric_bytes))

                        gen_key = f"v7_gen_id_{ck}"
                        gen_id = int(st.session_state.get(gen_key, 0)) + 1
                        st.session_state[gen_key] = gen_id
                        res["gen_id"] = gen_id
                        res["mueble_name"] = name
                        res["ref_images"] = ref_imgs
                        st.session_state["v7_result"] = res
                    except Exception as e:  # noqa: BLE001
                        st.error(f"❌ {e}")

        # ------------------------------------------------------------------ BOTÓN 1: GENERAR MODO SELECCIONADO
        if go:
            err = None
            if mode == "vistas_tela":
                if not batch_views_files:
                    err = "⚠️ Sube las vistas."
                elif not fabric_bytes:
                    err = "⚠️ Selecciona la tela."
            elif mode == "clonar_color":
                if not m_bytes or not batch_views_files:
                    err = "⚠️ Sube color base y vistas."
            else:
                if not m_bytes:
                    err = "⚠️ Elige o sube la foto del mueble."
                elif mode == "material" and material_mode in ("wood_only", "dual") and not wood_bytes:
                    err = "⚠️ Selecciona madera."
                elif mode == "material" and material_mode in ("fabric_only", "dual") and not fabric_bytes:
                    err = "⚠️ Selecciona tela."

            if err:
                st.error(err)
            else:
                with st.spinner(f"Generando {mode_label}..."):
                    try:
                        name = sku_code or (
                            m_names[0].rsplit(".", 1)[0]
                            if m_names
                            else (batch_views_files[0][0].rsplit(".", 1)[0] if batch_views_files else "Mueble")
                        )
                        notas_ia = "\n".join(
                            p for p in [
                                f"Tipo de mueble: {tipo}" if tipo else "",
                                f"Medidas exactas: {medidas_final}" if medidas_final else "",
                                notas.strip(),
                            ] if p
                        )
                        skip_f = mode in ("vistas_tela", "clonar_color")
                        f_ana, w_ana, t_ana = ai_prompt_service_v7.analyze_all_parallel(
                            furniture_bytes=m_bytes,
                            wood_bytes=wood_bytes,
                            wood_name=wood_name,
                            fabric_bytes=fabric_bytes,
                            fabric_name=fabric_name,
                            notas_ia=notas_ia,
                            skip_furniture=skip_f,
                        )
                        batch_ref = fabric_bytes if mode == "vistas_tela" else (m_bytes[0] if mode == "clonar_color" else None)

                        res = ai_prompt_service_v7.build_prompts(
                            mode=mode,
                            furniture_name=name,
                            furniture_analysis=f_ana,
                            wood_analysis=w_ana,
                            fabric_analysis=t_ana,
                            notas_usuario=notas.strip(),
                            tipo_mueble=tipo,
                            medidas_texto=medidas_final,
                            lugar_casa=lugar_casa,
                            vista_id=vista_id,
                            material_mode=material_mode,
                            wood_label=wood_name,
                            fabric_label=fabric_name,
                            white_bg_enabled=True,
                            classic_numbering=False,
                            batch_ref_bytes=batch_ref,
                            batch_views=batch_views_files,
                        )

                        ref_imgs = list(zip(m_names, m_bytes))
                        if wood_bytes:
                            ref_imgs.append((f"madera_{wood_name or 'muestra'}.jpg", wood_bytes))
                        if fabric_bytes:
                            ref_imgs.append((f"tela_{fabric_name or 'muestra'}.jpg", fabric_bytes))
                        for vn, vb in batch_views_files:
                            ref_imgs.append((vn, vb))

                        gen_key = f"v7_gen_id_{ck}"
                        gen_id = int(st.session_state.get(gen_key, 0)) + 1
                        st.session_state[gen_key] = gen_id
                        res["gen_id"] = gen_id
                        res["mueble_name"] = name
                        res["ref_images"] = ref_imgs
                        st.session_state["v7_result"] = res
                    except Exception as e:  # noqa: BLE001
                        st.error(f"❌ {e}")

    # =====================================================================
    # COLUMNA DERECHA: SALIDA DE PROMPTS + ESCALADOR 2054×2054 + ZIP
    # =====================================================================
    with col_out:
        with st.container(border=True):
            res = st.session_state.get("v7_result")
            if not res:
                st.caption(f"👈 Elige mueble (**RENDER / SUBIR / Cotización**) + **🧵 Tela** y pulsa **🚀 {mode_label}** o **↘️ 3/4 Derecha**.")
                return

            gen_id = int(res.get("gen_id", 0))
            mueble_slug = res.get("mueble_name", "mueble")

            h_name, h_2054, h_zip = st.columns([1.45, 0.95, 0.80], gap="small", vertical_alignment="center")
            with h_name:
                st.markdown(f"**{mueble_slug}**")
            with h_2054:
                with st.popover("📐 2054px", use_container_width=True):
                    ext_up = st.file_uploader(
                        "2054",
                        type=IMG_TYPES,
                        key=f"v7_ext2054_{ck}_{gen_id}",
                        label_visibility="collapsed",
                    )
                    if ext_up:
                        fmt_img = ai_prompt_service_v7.format_image_2054_white(ext_up.getvalue(), target_px=2054)
                        st.download_button(
                            "💾 PNG 2054×2054",
                            data=fmt_img["png"],
                            file_name=f"{mueble_slug}_2054x2054.png",
                            mime="image/png",
                            use_container_width=True,
                            key=f"v7_ext_png_{ck}_{gen_id}",
                        )
                        st.download_button(
                            "💾 JPG 2054×2054",
                            data=fmt_img["jpg"],
                            file_name=f"{mueble_slug}_2054x2054.jpg",
                            mime="image/jpeg",
                            use_container_width=True,
                            key=f"v7_ext_jpg_{ck}_{gen_id}",
                        )
            with h_zip:
                st.download_button(
                    "📦 ZIP",
                    data=_build_zip(res, include_images=True),
                    file_name=f"kit_{mueble_slug}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key=f"v7_dl_{ck}_{gen_id}",
                )

            items = res.get("items", [])
            if len(items) > 1:
                tabs = st.tabs([f"{i['icon']} {i['short_name']}" for i in items])
                for idx, (tab, item) in enumerate(zip(tabs, items)):
                    with tab:
                        _render_item(item, idx, ck, gen_id)
            elif items:
                _render_item(items[0], 0, ck, gen_id)

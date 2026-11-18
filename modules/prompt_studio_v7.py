import base64
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
from services.sheets_service import sheets_service

FOLDER_MUEBLES_RENDER_DRIVE_ID = "1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX"
LOCAL_RENDER_MUEBLES_DIR = Path(r"I:\Mi unidad\DOC ANIPA\Fotos general\Informacion mia\RENDER")
FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"

IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff"]
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".tiff"}

MATERIAL_MODES = {
    "Solo tela": "fabric_only",
    "Solo madera": "wood_only",
    "Tela + madera": "dual",
}


def _scan_local_dir(target_dir: Path, recursive: bool = False) -> List[Dict[str, str]]:
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
            items.append({
                "id": "",
                "name": clean_name,
                "filename": f.name,
                "local_path": str(f),
            })
    return items


@st.cache_data(ttl=15, show_spinner=False)
def cargar_muebles_render_v7(refresh_tick: int = 0) -> List[Dict[str, str]]:
    """Lee únicamente la carpeta RENDER (local + Google Drive 1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX)."""
    _ = refresh_tick
    local_items = _scan_local_dir(LOCAL_RENDER_MUEBLES_DIR, recursive=True)
    seen = {x["name"].strip().upper() for x in local_items}
    drive_items: List[Dict[str, str]] = []
    try:
        if sheets_service.ensure_connected():
            drive_items = sheets_service.get_drive_folder_files(
                FOLDER_MUEBLES_RENDER_DRIVE_ID,
                recursive=True,
                max_depth=3,
                ttl=10,
            )
    except Exception:
        drive_items = []
    return local_items + [d for d in drive_items if d["name"].strip().upper() not in seen]


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_maderas_v7(include_drive: bool = True) -> List[Dict[str, str]]:
    app_dir = Path(__file__).resolve().parent.parent
    local_maderas = _scan_local_dir(app_dir / "muestras_madera", recursive=False)
    seen = {m["name"].upper() for m in local_maderas}
    drive_maderas: List[Dict[str, str]] = []
    if include_drive:
        try:
            if sheets_service.ensure_connected():
                drive_maderas = sheets_service.get_drive_folder_files(FOLDER_MADERAS_DRIVE_ID, recursive=True)
        except Exception:
            drive_maderas = []
    return local_maderas + [m for m in drive_maderas if m["name"].strip().upper() not in seen]


@st.cache_data(ttl=1800, show_spinner=False)
def cargar_telas_v7() -> List[Dict[str, str]]:
    try:
        if sheets_service.ensure_connected():
            return sheets_service.get_drive_folder_files(FOLDER_TELAS_DRIVE_ID, recursive=True)
    except Exception:
        pass
    return []


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


def _resolve_mueble_render_selector(ck: int) -> Tuple[List[bytes], List[str]]:
    tick = int(st.session_state.get("v7_render_tick", 0))
    catalog_items = cargar_muebles_render_v7(tick)
    first_opt = f"🛋️ RENDER ({len(catalog_items)})..."
    refresh_opt = "🔄 Actualizar carpeta RENDER"
    options = [first_opt] + [item["name"] for item in catalog_items] + [refresh_opt]

    sel_name = st.selectbox(
        "Mueble RENDER",
        options,
        index=0,
        key=f"v7_sb_mueble_{ck}",
        label_visibility="collapsed",
    )
    if sel_name == refresh_opt:
        sheets_service._drive_folder_tree_cache.clear()
        st.session_state["v7_render_tick"] = tick + 1
        st.session_state[f"v7_sb_mueble_{ck}"] = first_opt
        st.rerun()

    up_mueble = st.file_uploader(
        "Subir mueble",
        type=IMG_TYPES,
        accept_multiple_files=True,
        key=f"v7_mueble_{ck}",
        label_visibility="collapsed",
    )
    if up_mueble:
        return _read_files(up_mueble)

    if sel_name and sel_name not in (first_opt, refresh_opt):
        match = next((x for x in catalog_items if x["name"].strip().upper() == sel_name.strip().upper()), None)
        if match:
            if match.get("local_path") and os.path.exists(match["local_path"]):
                return [Path(match["local_path"]).read_bytes()], [match.get("filename") or f"{sel_name}.jpg"]
            if match.get("id"):
                raw_b = load_drive_file_cached(match["id"])
                if raw_b:
                    return [raw_b], [match.get("filename") or f"{sel_name}.jpg"]
    return [], []


def _resolve_material_selector(
    kind: str,
    ck: int,
    catalog_items: List[Dict[str, str]],
) -> Tuple[Optional[bytes], str]:
    is_wood = kind == "wood"
    lbl = "🪵 Madera" if is_wood else "🧵 Tela"
    options = [f"{lbl} ({len(catalog_items)})..."] + [item["name"] for item in catalog_items]
    sel_name = st.selectbox(
        lbl,
        options,
        index=0,
        key=f"v7_sb_{kind}_{ck}",
        label_visibility="collapsed",
    )
    up_file = st.file_uploader(
        lbl,
        type=IMG_TYPES,
        key=f"v7_up_{kind}_{ck}",
        label_visibility="collapsed",
    )

    if up_file:
        return up_file.getvalue(), getattr(up_file, "name", lbl)

    if sel_name and sel_name != options[0]:
        match = next((x for x in catalog_items if x["name"].upper() == sel_name.upper()), None)
        if match:
            if match.get("local_path") and os.path.exists(match["local_path"]):
                return Path(match["local_path"]).read_bytes(), sel_name
            if match.get("id"):
                loaded = load_drive_file_cached(match["id"])
                if loaded:
                    return loaded, sel_name
    return None, ""


def _render_mini_thumbs(thumbs: List[Tuple[str, bytes]]) -> None:
    """Muestra miniaturas muy pequeñas (44×44 px) en una tira horizontal limpia."""
    if not thumbs:
        return
    cards: List[str] = []
    for lbl, raw_b in thumbs:
        t_bytes = make_thumbnail_bytes(raw_b, max_dim=96)
        if not t_bytes:
            continue
        b64 = base64.b64encode(t_bytes).decode("ascii")
        safe_lbl = (lbl or "")[:14].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cards.append(
            f'<div style="display:flex;align-items:center;gap:5px;background:#1E293B;border:1px solid #334155;'
            f'border-radius:6px;padding:2px 6px 2px 3px;">'
            f'<img src="data:image/jpeg;base64,{b64}" style="width:38px;height:38px;object-fit:cover;border-radius:4px;display:block;" />'
            f'<span style="font-size:10px;color:#CBD5E1;max-width:78px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{safe_lbl}</span>'
            f'</div>'
        )
    if cards:
        st.markdown(
            f'<div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:2px;">{"".join(cards)}</div>',
            unsafe_allow_html=True,
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
    min-height: 28px !important;
    height: 28px !important;
    padding: 1px 6px !important;
    border-radius: 5px !important;
    white-space: nowrap !important;
}
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    min-height: 28px !important;
    height: 28px !important;
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
    padding: 2px 6px !important;
    min-height: 28px !important;
}
section[data-testid="stFileUploaderDropzone"] svg,
section[data-testid="stFileUploaderDropzone"] small,
section[data-testid="stFileUploaderDropzone"] span[data-testid="stMarkdownContainer"],
div[data-testid="stFileUploaderDropzoneInstructions"] {
    display: none !important;
}
section[data-testid="stFileUploaderDropzone"] button {
    font-size: 10.5px !important;
    min-height: 24px !important;
    height: 24px !important;
    padding: 0px 8px !important;
    width: 100% !important;
}
div[data-testid="stVerticalBlock"] > div {
    gap: 0.25rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 6px 8px !important;
}
button[data-baseweb="tab"] {
    padding: 2px 8px !important;
    font-size: 11px !important;
    min-height: 26px !important;
}
@media (max-width: 640px) {
    .stButton > button,
    .stDownloadButton > button {
        font-size: 10.5px !important;
        padding: 1px 4px !important;
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
    # ÁREA PRINCIPAL: INSUMOS (CARPETA RENDER) | PROMPTS
    # =====================================================================
    m_bytes: List[bytes] = []
    m_names: List[str] = []
    batch_views_files: List[Tuple[str, bytes]] = []
    wood_bytes: Optional[bytes] = None
    wood_name: str = ""
    fabric_bytes: Optional[bytes] = None
    fabric_name: str = ""

    col_work, col_out = st.columns([1.02, 1.48], gap="small")

    with col_work:
        with st.container(border=True):
            if mode == "vistas_tela":
                u1, u2 = st.columns(2)
                with u1:
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
                with u2:
                    fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
            elif mode == "clonar_color":
                u1, u2 = st.columns(2)
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
                u_m, u_f, u_w = st.columns(3)
                with u_m:
                    m_bytes, m_names = _resolve_mueble_render_selector(ck)
                with u_f:
                    if mode != "material" or material_mode in ("fabric_only", "dual"):
                        fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
                with u_w:
                    if mode != "material" or material_mode in ("wood_only", "dual"):
                        wood_bytes, wood_name = _resolve_material_selector("wood", ck, cargar_maderas_v7())

            notas = st.text_input(
                "Notas",
                key=f"v7_notas_{ck}",
                placeholder="📝 Notas opcionales",
                label_visibility="collapsed",
            )

            # 3 BOTONES CON SENTIDO CLARO:
            # 1) Generar el modo elegido arriba | 2) 3/4 Derecha sin sombra (2054) | 3) Borrar (sin mover el modo)
            b_go, b_34, b_clr = st.columns(3)
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

            thumbs: List[Tuple[str, bytes]] = []
            for nm, raw in zip(m_names[:2], m_bytes[:2]):
                thumbs.append((nm, raw))
            if fabric_bytes:
                thumbs.append((fabric_name or "Tela", fabric_bytes))
            if wood_bytes:
                thumbs.append((wood_name or "Madera", wood_bytes))
            for vn, vb in batch_views_files[:2]:
                thumbs.append((vn, vb))

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
                st.caption(f"👈 Elige mueble en **🛋️ RENDER** + **🧵 Tela** y pulsa **🚀 {mode_label}** o **↘️ 3/4 Derecha**.")
                return

            gen_id = int(res.get("gen_id", 0))
            mueble_slug = res.get("mueble_name", "mueble")

            h_name, h_2054, h_zip = st.columns([1.6, 0.9, 0.8], vertical_alignment="center")
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

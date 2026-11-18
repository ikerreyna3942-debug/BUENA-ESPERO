import csv
import io
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from modules.sku_banner import render_sku_autofill_bar
from modules.ui_helpers import load_drive_file_cached, render_copy_button, render_preview_image
from services.ai_prompt_service_v7 import (
    ALL_SINGLE_VIEWS,
    MODES,
    ROOM_PRESETS,
    ai_prompt_service_v7,
)
from services.sheets_service import sheets_service

FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"
IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff"]
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

MATERIAL_MODES = {
    "Solo tela": "fabric_only",
    "Solo madera": "wood_only",
    "Tela + madera": "dual",
}


def _scan_local_maderas() -> List[Dict[str, str]]:
    app_dir = Path(__file__).resolve().parent.parent
    maderas_dir = app_dir / "muestras_madera"
    items: List[Dict[str, str]] = []
    seen = set()
    if maderas_dir.exists():
        for f in sorted(maderas_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTS:
                clean_name = f.stem.replace("_", " ").strip()
                key = clean_name.upper()
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "id": f.name,
                    "name": clean_name,
                    "filename": f.name,
                    "local_path": str(f),
                })
    return items


@st.cache_data(ttl=300, show_spinner=False)
def cargar_maderas_v7(include_drive: bool = True) -> List[Dict[str, str]]:
    local_maderas = _scan_local_maderas()
    seen = {m["name"].upper() for m in local_maderas}
    drive_maderas: List[Dict[str, str]] = []
    if include_drive:
        try:
            if sheets_service.ensure_connected():
                drive_maderas = sheets_service.get_drive_folder_files(FOLDER_MADERAS_DRIVE_ID, recursive=True)
        except Exception:
            drive_maderas = []
    return local_maderas + [m for m in drive_maderas if m["name"].strip().upper() not in seen]


@st.cache_data(ttl=300, show_spinner=False)
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


def _build_zip(res: Dict[str, Any], include_images: bool = False) -> bytes:
    buf = io.BytesIO()
    url_rows: List[List[str]] = []
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
                u_info = gen_photo.get("urls") or {}
                if u_info.get("drive_view_url"):
                    url_rows.append([
                        it.get("label", it["id"]),
                        fname_png,
                        u_info.get("drive_view_url", ""),
                        u_info.get("direct_cdn_url", ""),
                        u_info.get("download_url", ""),
                    ])

        if res.get("master_ais"):
            z.writestr(
                "prompts/00_prompt_maestro_secuencial.txt",
                res["master_ais"] + "\n\n====================\n\n" + res.get("master_dal", ""),
            )

        if url_rows:
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(["vista", "archivo", "drive_view_url", "direct_cdn_url_2054", "download_url"])
            writer.writerows(url_rows)
            z.writestr("urls_catalogo.csv", csv_buf.getvalue().encode("utf-8-sig"))

        if include_images:
            for idx, (fname, raw) in enumerate(res.get("ref_images", []), start=1):
                safe_name = os.path.basename(fname or f"ref_{idx}.jpg")
                z.writestr(f"insumos/{idx:02d}_{safe_name}", raw)
    return buf.getvalue()


def _render_item(item: Dict[str, Any], idx: int, ck: int, gen_id: int, mueble_slug: str) -> None:
    gen_photo = item.get("generated_photo")
    if isinstance(gen_photo, dict) and gen_photo.get("png"):
        c_img, c_act = st.columns([1.0, 1.0], vertical_alignment="center")
        with c_img:
            st.image(gen_photo["jpg"], use_container_width=True)
        with c_act:
            fname_base = f"{mueble_slug}_{item['id']}_2054x2054"
            d_p, d_j = st.columns(2)
            with d_p:
                st.download_button(
                    "💾 PNG",
                    data=gen_photo["png"],
                    file_name=f"{fname_base}.png",
                    mime="image/png",
                    use_container_width=True,
                    key=f"v7_it_png_{idx}_{ck}_{gen_id}",
                )
            with d_j:
                st.download_button(
                    "💾 JPG",
                    data=gen_photo["jpg"],
                    file_name=f"{fname_base}.jpg",
                    mime="image/jpeg",
                    use_container_width=True,
                    key=f"v7_it_jpg_{idx}_{ck}_{gen_id}",
                )
            u_info = gen_photo.get("urls") or {}
            if u_info.get("direct_cdn_url"):
                render_copy_button(
                    u_info["direct_cdn_url"],
                    label="🔗 Copiar URL",
                    key=f"v7_url_cp_{idx}_{ck}_{gen_id}",
                )

    t_ais, t_dal, t_mj = st.tabs(["AI Studio", "ChatGPT", "Midjourney"])
    with t_ais:
        txt = item.get("google_ai_studio", "")
        render_copy_button(txt, label="📋 Copiar", key=f"v7_cp_ais_{idx}_{ck}_{gen_id}")
        st.text_area("Prompt", txt, height=185, key=f"v7_ais_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_dal:
        txt = item.get("chatgpt_dalle3", "")
        render_copy_button(txt, label="📋 Copiar", key=f"v7_cp_dal_{idx}_{ck}_{gen_id}")
        st.text_area("Prompt", txt, height=185, key=f"v7_dal_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_mj:
        txt = item.get("midjourney_v6", "")
        render_copy_button(txt, label="📋 Copiar", key=f"v7_cp_mj_{idx}_{ck}_{gen_id}")
        st.text_area("Prompt", txt, height=120, key=f"v7_mj_{idx}_{ck}_{gen_id}", label_visibility="collapsed")


def render_prompt_studio_v7() -> None:
    if "clear_key_v7" not in st.session_state:
        st.session_state.clear_key_v7 = 0
    ck = st.session_state.clear_key_v7

    st.markdown(
        """
<style>
/* Interfaz ultra limpia, pequeña y compacta */
.stButton > button {
    font-size: 12px !important;
    font-weight: 600 !important;
    min-height: 32px !important;
    height: 32px !important;
    padding: 2px 8px !important;
    border-radius: 6px !important;
}
div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div {
    min-height: 32px !important;
    font-size: 12px !important;
}
div[data-baseweb="select"] span,
input {
    font-size: 12px !important;
}
section[data-testid="stFileUploaderDropzone"] {
    padding: 4px 8px !important;
    min-height: 42px !important;
}
section[data-testid="stFileUploaderDropzone"] small,
section[data-testid="stFileUploaderDropzone"] span[data-testid="stMarkdownContainer"] {
    display: none !important;
}
div[data-testid="stVerticalBlock"] > div {
    gap: 0.35rem !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div {
    padding: 8px 10px !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # =====================================================================
    # ENCABEZADO DE 1 SOLA LÍNEA PEQUEÑA Y LIMPIA
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
            h_mode, h_sub, h_sku, h_clr = st.columns([0.95, 0.95, 2.7, 0.55], vertical_alignment="center")
        else:
            h_mode, h_sku, h_clr = st.columns([1.15, 3.45, 0.55], vertical_alignment="center")
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

        with h_clr:
            if st.button("🗑️ Borrar", use_container_width=True, key="v7_btn_clear"):
                # Limpia fotos, SKU, notas y salida SIN mover el modo ni sub-opción activa
                clear_prefixes = (
                    "v7_result",
                    "v7_render_2054",
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

    # =====================================================================
    # ÁREA PRINCIPAL LIMPIA (IZQUIERDA: INSUMOS | DERECHA: SALIDA)
    # =====================================================================
    m_bytes: List[bytes] = []
    m_names: List[str] = []
    batch_views_files: List[Tuple[str, bytes]] = []
    wood_bytes: Optional[bytes] = None
    wood_name: str = ""
    fabric_bytes: Optional[bytes] = None
    fabric_name: str = ""

    col_work, col_out = st.columns([1.05, 1.45], gap="small")

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
                    st.markdown("<div style='font-size:11.5px;font-weight:600;height:32px;display:flex;align-items:center;'>🛋️ Mueble</div>", unsafe_allow_html=True)
                    up_mueble = st.file_uploader(
                        "Mueble",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_mueble_{ck}",
                        label_visibility="collapsed",
                    )
                    m_bytes, m_names = _read_files(up_mueble)
                with u_f:
                    if mode != "material" or material_mode in ("fabric_only", "dual"):
                        fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
                with u_w:
                    if mode != "material" or material_mode in ("wood_only", "dual"):
                        wood_bytes, wood_name = _resolve_material_selector("wood", ck, cargar_maderas_v7())

            notas = st.text_input(
                "Notas",
                key=f"v7_notas_{ck}",
                placeholder="📝 Notas (opcional)",
                label_visibility="collapsed",
            )

            # Solo 2 botones limpios y muy cortos
            b_34, b_go = st.columns(2)
            with b_34:
                btn_34_2054 = st.button(
                    "↘️ 3/4 Der · 2054",
                    type="primary",
                    use_container_width=True,
                    key=f"v7_btn_34_2054_{ck}",
                )
            with b_go:
                go = st.button(
                    "🚀 Generar",
                    use_container_width=True,
                    key=f"v7_btn_go_{ck}",
                )

            thumbs: List[Tuple[str, bytes]] = []
            for nm, raw in zip(m_names[:2], m_bytes[:2]):
                thumbs.append((nm[:14], raw))
            if fabric_bytes:
                thumbs.append(((fabric_name or "Tela")[:14], fabric_bytes))
            if wood_bytes:
                thumbs.append(((wood_name or "Madera")[:14], wood_bytes))
            for vn, vb in batch_views_files[:2]:
                thumbs.append((vn[:14], vb))

            if thumbs:
                t_cols = st.columns(len(thumbs))
                for tc, (lbl, raw_b) in zip(t_cols, thumbs):
                    with tc:
                        render_preview_image(raw_b, caption=lbl, max_dim=140)

        # ------------------------------------------------------------------ EJECUCIÓN 1: 3/4 DERECHA · 2054×2054
        if btn_34_2054:
            target_furn_bytes = m_bytes or ([batch_views_files[0][1]] if batch_views_files else [])
            target_furn_names = m_names or ([batch_views_files[0][0]] if batch_views_files else [])
            if not target_furn_bytes:
                st.error("⚠️ Sube la foto del mueble.")
            else:
                with st.spinner("Generando 3/4 Derecha · 2054×2054..."):
                    try:
                        name = sku_code or (target_furn_names[0].rsplit(".", 1)[0] if target_furn_names else "Mueble")
                        notas_ia = "\n".join(
                            p for p in [
                                f"Tipo de mueble: {tipo}" if tipo else "",
                                f"Medidas exactas: {medidas_final}" if medidas_final else "",
                                notas.strip(),
                            ] if p
                        )
                        f_ana = ai_prompt_service_v7.analyze_furniture_for_enhancement(
                            furniture_bytes=target_furn_bytes,
                            wood_bytes=[wood_bytes] if wood_bytes else None,
                            fabric_bytes=[fabric_bytes] if fabric_bytes else None,
                            notas_usuario=notas_ia,
                        )
                        w_ana = (
                            ai_prompt_service_v7.analyze_material(wood_bytes, material_type="wood", sample_name=wood_name)
                            if wood_bytes else None
                        )
                        t_ana = (
                            ai_prompt_service_v7.analyze_material(fabric_bytes, material_type="fabric", sample_name=fabric_name)
                            if fabric_bytes else None
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

                        render_2054, _ = ai_prompt_service_v7.generate_catalog_photo(
                            prompt_text=res["items"][0]["google_ai_studio"],
                            primary_bytes=target_furn_bytes[0],
                            wood_bytes=wood_bytes,
                            fabric_bytes=fabric_bytes,
                            pure_white_border=True,
                        )
                        if render_2054:
                            try:
                                render_2054["urls"] = sheets_service.publish_photo_and_get_urls(
                                    file_bytes=render_2054["png"],
                                    filename=f"{name}_3_4_derecha_2054x2054.png",
                                    dest="buzon",
                                    subfolder=sku_code or name,
                                )
                            except Exception:
                                pass
                            res["items"][0]["generated_photo"] = render_2054

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
                        res["render_2054"] = render_2054
                        st.session_state["v7_result"] = res
                    except Exception as e:  # noqa: BLE001
                        st.error(f"❌ {e}")

        # ------------------------------------------------------------------ EJECUCIÓN 2: MODO SELECCIONADO
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
                    err = "⚠️ Sube la foto del mueble."
                elif mode == "material" and material_mode in ("wood_only", "dual") and not wood_bytes:
                    err = "⚠️ Selecciona madera."
                elif mode == "material" and material_mode in ("fabric_only", "dual") and not fabric_bytes:
                    err = "⚠️ Selecciona tela."

            if err:
                st.error(err)
            else:
                with st.spinner("Generando..."):
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
                        f_ana: Dict[str, Any] = {}
                        if mode not in ("vistas_tela", "clonar_color"):
                            f_ana = ai_prompt_service_v7.analyze_furniture_for_enhancement(
                                furniture_bytes=m_bytes,
                                wood_bytes=[wood_bytes] if wood_bytes else None,
                                fabric_bytes=[fabric_bytes] if fabric_bytes else None,
                                notas_usuario=notas_ia,
                            )
                        w_ana = (
                            ai_prompt_service_v7.analyze_material(wood_bytes, material_type="wood", sample_name=wood_name)
                            if wood_bytes else None
                        )
                        t_ana = (
                            ai_prompt_service_v7.analyze_material(fabric_bytes, material_type="fabric", sample_name=fabric_name)
                            if fabric_bytes else None
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
    # COLUMNA DERECHA: SALIDA LIMPIA SIN TEXTO EXTRA
    # =====================================================================
    with col_out:
        with st.container(border=True):
            res = st.session_state.get("v7_result")
            if not res:
                st.caption("👈 Sube foto y pulsa **↘️ 3/4 Der · 2054** o **🚀 Generar**.")
                return

            gen_id = int(res.get("gen_id", 0))
            mueble_slug = res.get("mueble_name", "mueble")

            h_name, h_2054, h_zip = st.columns([1.6, 0.9, 0.9], vertical_alignment="center")
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
                        if st.button("🔗 URL Drive", use_container_width=True, key=f"v7_ext_url_{ck}_{gen_id}"):
                            try:
                                u_res = sheets_service.publish_photo_and_get_urls(
                                    file_bytes=fmt_img["png"],
                                    filename=f"{sku_code or mueble_slug}_2054x2054.png",
                                    dest="buzon",
                                    subfolder=sku_code or mueble_slug,
                                )
                                st.session_state[f"v7_ext_u_{ck}_{gen_id}"] = u_res["direct_cdn_url"]
                            except Exception as e_u:  # noqa: BLE001
                                st.error(f"{e_u}")
                        saved_u = st.session_state.get(f"v7_ext_u_{ck}_{gen_id}")
                        if saved_u:
                            render_copy_button(saved_u, label="📋 Copiar URL", key=f"v7_cp_extu_{ck}_{gen_id}")
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
                        _render_item(item, idx, ck, gen_id, mueble_slug)
            elif items:
                _render_item(items[0], 0, ck, gen_id, mueble_slug)

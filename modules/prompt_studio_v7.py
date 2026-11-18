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

FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"
IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff"]
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

MATERIAL_MODES = {
    "Solo tela": "fabric_only",
    "Solo madera": "wood_only",
    "Tela + madera": "dual",
}

SYS_PROMPT_COMPORTAMIENTO = (
    "Eres un Director de Arte experto en Fotografía Comercial de Muebles de Lujo. "
    "Priorizas fidelidad 100% en silueta 3D, aplicación exacta de la textura de tela en todo el casco y cojines "
    "a escala real de tejido, vetas naturales de madera y aislamiento impecable en blanco puro #FFFFFF con 0% sombras."
)


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
            from services.sheets_service import sheets_service
            if sheets_service.ensure_connected():
                drive_maderas = sheets_service.get_drive_folder_files(FOLDER_MADERAS_DRIVE_ID, recursive=True)
        except Exception:
            drive_maderas = []
    return local_maderas + [m for m in drive_maderas if m["name"].strip().upper() not in seen]


@st.cache_data(ttl=300, show_spinner=False)
def cargar_telas_v7() -> List[Dict[str, str]]:
    try:
        from services.sheets_service import sheets_service
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


def _num(label: str, key: str) -> float:
    return float(st.number_input(label, min_value=0.0, step=1.0, format="%.0f", key=key))


def _resolve_material_selector(
    kind: str,
    ck: int,
    catalog_items: List[Dict[str, str]],
) -> Tuple[Optional[bytes], str]:
    """Selector compacto para barra/columna adaptable: catálogo oficial o subida directa."""
    is_wood = kind == "wood"
    icon = "🪵" if is_wood else "🧵"
    short_lbl = "Madera" if is_wood else "Tela (casco)"
    options = [""] + [item["name"] for item in catalog_items]
    sel_name = st.selectbox(
        f"{icon} {short_lbl} ({len(catalog_items)}):",
        options,
        key=f"v7_sb_{kind}_{ck}",
    )
    up_file = st.file_uploader(
        f"Foto {('madera' if is_wood else 'tela')}:",
        type=IMG_TYPES,
        key=f"v7_up_{kind}_{ck}",
        label_visibility="collapsed",
    )

    if up_file:
        return up_file.getvalue(), getattr(up_file, "name", short_lbl)

    if sel_name:
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
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, it in enumerate(res.get("items", []), start=1):
            guide = it.get("attachment_guide") or []
            guide_txt = "\n".join(f"  - {g}" for g in guide) if guide else "  - Image 1: Foto del mueble"
            body = (
                f"=== ORDEN DE IMÁGENES ===\n{guide_txt}\n\n"
                f"--- GOOGLE AI STUDIO / GEMINI ---\n{it.get('google_ai_studio', '')}\n\n"
                f"--- CHATGPT (DALL-E 3 / GPT IMAGE) ---\n{it.get('chatgpt_dalle3', '')}\n\n"
                f"--- MIDJOURNEY v6.1 ---\n{it.get('midjourney_v6', '')}\n\n"
                "--- CHECKLIST ---\n"
                + "\n".join(f"- {c}" for c in it.get("checklist", []))
            )
            z.writestr(f"{i:02d}_{it['id']}.txt", body)

        if res.get("master_ais"):
            z.writestr(
                "00_prompt_maestro_secuencial.txt",
                res["master_ais"]
                + "\n\n====================\n\n"
                + res.get("master_dal", "")
                + "\n\n====================\n\nMIDJOURNEY:\n"
                + res.get("midjourney", ""),
            )

        render_2054 = res.get("render_2054")
        if isinstance(render_2054, dict) and render_2054.get("png"):
            z.writestr(f"foto_3_4_derecha_2054x2054_{res.get('mueble_name', 'mueble')}.png", render_2054["png"])

        if include_images:
            for idx, (fname, raw) in enumerate(res.get("ref_images", []), start=1):
                safe_name = os.path.basename(fname or f"referencia_{idx}.jpg")
                z.writestr(f"fotos/{idx:02d}_{safe_name}", raw)
    return buf.getvalue()


def _render_item(item: Dict[str, Any], idx: int, ck: int, gen_id: int) -> None:
    st.markdown(f"**{item['icon']} {item['label']}**")
    if item.get("preview_bytes"):
        render_preview_image(item["preview_bytes"], caption=item["label"], max_dim=280)

    guide = item.get("attachment_guide") or []
    if guide:
        bullets = " &nbsp;|&nbsp; ".join(f"<b>{g}</b>" for g in guide)
        st.markdown(
            f"<div style='background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.35);"
            f"border-radius:6px;padding:5px 9px;margin-bottom:6px;font-size:11.5px;color:#E2E8F0;'>"
            f"📎 {bullets}</div>",
            unsafe_allow_html=True,
        )

    if item.get("needs_anchor"):
        st.caption("📌 Adjunta también tu **Vista 1 aprobada** al final como **ANCHOR**.")

    t_ais, t_dal, t_mj = st.tabs(["🌐 AI Studio / Gemini", "🤖 ChatGPT", "🎨 Midjourney"])
    with t_ais:
        txt = item.get("google_ai_studio", "")
        render_copy_button(
            txt,
            label=f"📋 Copiar ({item.get('short_name', 'AI Studio')})",
            key=f"v7_cp_ais_{idx}_{ck}_{gen_id}",
        )
        st.text_area("AI Studio:", txt, height=195, key=f"v7_ais_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_dal:
        txt = item.get("chatgpt_dalle3", "")
        render_copy_button(
            txt,
            label=f"📋 Copiar ({item.get('short_name', 'ChatGPT')})",
            key=f"v7_cp_dal_{idx}_{ck}_{gen_id}",
        )
        st.text_area("ChatGPT:", txt, height=185, key=f"v7_dal_{idx}_{ck}_{gen_id}", label_visibility="collapsed")
    with t_mj:
        txt = item.get("midjourney_v6", "")
        render_copy_button(
            txt,
            label=f"📋 Copiar ({item.get('short_name', 'Midjourney')})",
            key=f"v7_cp_mj_{idx}_{ck}_{gen_id}",
        )
        st.text_area("Midjourney:", txt, height=115, key=f"v7_mj_{idx}_{ck}_{gen_id}", label_visibility="collapsed")

    with st.expander("✅ Revisión", expanded=False):
        for c in item.get("checklist", []):
            st.markdown(f"- {c}")


def render_prompt_studio_v7() -> None:
    if "clear_key_v7" not in st.session_state:
        st.session_state.clear_key_v7 = 0
    ck = st.session_state.clear_key_v7

    st.markdown(
        """
<style>
/* Diseño horizontal compacto y 100% adaptable a cualquier tamaño de pantalla */
.stButton > button {
    white-space: normal !important;
    font-size: clamp(11.5px, 0.9vw, 13px) !important;
    font-weight: 600 !important;
    height: auto !important;
    min-height: 36px !important;
    padding: 5px 10px !important;
}
div[role="radiogroup"][aria-orientation="horizontal"] {
    gap: 5px !important;
    flex-wrap: wrap !important;
}
div[role="radiogroup"][aria-orientation="horizontal"] > label {
    background: #1E293B !important;
    border: 1px solid #475569 !important;
    border-radius: 999px !important;
    padding: 2px 10px !important;
    margin: 0 !important;
    font-size: clamp(11px, 0.85vw, 12.5px) !important;
}
/* Dropzones compactas para que quepan en horizontal sin estirar hacia abajo */
section[data-testid="stFileUploaderDropzone"] {
    padding: 6px 10px !important;
    min-height: 54px !important;
}
section[data-testid="stFileUploaderDropzone"] small {
    display: none !important;
}
div[data-testid="stVerticalBlock"] > div {
    gap: 0.45rem !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # =====================================================================
    # ENCABEZADO SUPERIOR DE MODO Y CONTROLES (HORIZONTAL · SIN SCROLL ABAJO)
    # =====================================================================
    with st.container(border=True):
        # Fila 1 del encabezado: Menú de modos compacto + Rol IA + Botón Borrar (no mueve la opción activa)
        top_modes, top_role, top_clear = st.columns([4.2, 0.85, 0.65], vertical_alignment="center")
        with top_modes:
            mode_labels = list(MODES.values())
            if st.session_state.get("v7_keep_mode") not in mode_labels:
                st.session_state["v7_keep_mode"] = mode_labels[0]
            mode_label = st.radio(
                "Modo:",
                mode_labels,
                horizontal=True,
                key="v7_keep_mode",
                label_visibility="collapsed",
            )
            mode = next(k for k, v in MODES.items() if v == mode_label)
        with top_role:
            render_copy_button(SYS_PROMPT_COMPORTAMIENTO, label="🧠 Rol IA", key=f"v7_comp_{ck}")
        with top_clear:
            if st.button("🗑️ Borrar", use_container_width=True, key="v7_btn_clear"):
                # Borra fotos, SKU, medidas, notas y resultados SIN cambiar el modo ni sub-opciones activas
                clear_prefixes = (
                    "v7_result",
                    "v7_render_2054",
                    "v7_w_",
                    "v7_h_",
                    "v7_d_",
                    "v7_diam_",
                    "v7_med_src_",
                    "v7_notas_",
                    "v7_sb_",
                    "v7_up_",
                    "v7_mueble_",
                    "v7_batch_",
                    "v7_clone_",
                    "v7_ref_",
                    "v7_ext2054_",
                    "sku_",
                    "field_",
                )
                for k in [k for k in list(st.session_state.keys()) if k.startswith(clear_prefixes)]:
                    del st.session_state[k]
                st.session_state.clear_key_v7 = ck + 1
                st.rerun()

        # Sub-selector en línea solo cuando el modo lo requiere
        vista_id = "vista_3_4_derecha"
        material_mode = "fabric_only"
        lugar_casa = ""

        if mode == "vista_suelta":
            view_opts = {k: v["label"] for k, v in ALL_SINGLE_VIEWS.items()}
            view_labels = list(view_opts.values())
            if st.session_state.get("v7_keep_vista") not in view_labels:
                st.session_state["v7_keep_vista"] = view_opts["vista_3_4_derecha"]
            vsel = st.radio("Ángulo:", view_labels, horizontal=True, key="v7_keep_vista", label_visibility="collapsed")
            vista_id = next(k for k, v in view_opts.items() if v == vsel)
        elif mode == "material":
            mat_labels = list(MATERIAL_MODES.keys())
            if st.session_state.get("v7_keep_matmode") not in mat_labels:
                st.session_state["v7_keep_matmode"] = mat_labels[0]
            msel = st.radio("Material:", mat_labels, horizontal=True, key="v7_keep_matmode", label_visibility="collapsed")
            material_mode = MATERIAL_MODES[msel]

        if mode in ("catalogo", "entorno") or (mode == "vista_suelta" and vista_id == "vista_entorno_cliente"):
            room_opts = ROOM_PRESETS + ["Otra"]
            if st.session_state.get("v7_keep_room") not in room_opts:
                st.session_state["v7_keep_room"] = room_opts[0]
            r_col1, r_col2 = st.columns([2.2, 1.8], vertical_alignment="center")
            with r_col1:
                room_preset = st.radio("🏡 Espacio:", room_opts, horizontal=True, key="v7_keep_room", label_visibility="collapsed")
            with r_col2:
                if room_preset == "Otra":
                    lugar_casa = st.text_input(
                        "Espacio:",
                        placeholder="Ej: Sala minimalista",
                        key="v7_keep_room_custom",
                        label_visibility="collapsed",
                    )
                else:
                    lugar_casa = room_preset

        # Fila 2 del encabezado: SKU + Mueble + Medidas + Dimensiones cm + Toggles en horizontal
        sku = render_sku_autofill_bar("v7", inline_header=True)
        tipo = sku["tipo_mueble"]
        medidas = sku["medidas"]

        src_key = f"v7_med_src_{ck}"
        if src_key not in st.session_state or st.session_state[src_key] != medidas:
            d_init = ai_prompt_service_v7.parse_dimensions(tipo, medidas)
            st.session_state[f"v7_w_{ck}"] = float(d_init["width_cm"] or 0)
            st.session_state[f"v7_h_{ck}"] = float(d_init["height_cm"] or 0)
            st.session_state[f"v7_d_{ck}"] = float(d_init["depth_cm"] or 0)
            st.session_state[f"v7_diam_{ck}"] = float(d_init["diam_cm"] or 0)
            st.session_state[src_key] = medidas

        d1, d2, d3, d4, d5, d6 = st.columns([0.85, 0.85, 0.85, 0.85, 1.0, 1.0], vertical_alignment="bottom")
        with d1:
            w = _num("Ancho cm", f"v7_w_{ck}")
        with d2:
            h = _num("Alto cm", f"v7_h_{ck}")
        with d3:
            d_ = _num("Fondo cm", f"v7_d_{ck}")
        with d4:
            diam = _num("Diám. cm", f"v7_diam_{ck}")
        with d5:
            white_bg_enabled = st.toggle("⬜ Fondo blanco", value=True, key="v7_keep_whitebg")
        with d6:
            classic_num = st.toggle("🔙 Num. clásica", value=False, key="v7_keep_classic")

        medidas_final = ai_prompt_service_v7.compose_dimensions_text(w, d_, h, diam)

    # =====================================================================
    # PANEL PRINCIPAL ADAPTATIVO (IZQUIERDA: FOTOS + BOTONES | DERECHA: SALIDA)
    # =====================================================================
    m_bytes: List[bytes] = []
    m_names: List[str] = []
    r_bytes: List[bytes] = []
    r_names: List[str] = []
    batch_views_files: List[Tuple[str, bytes]] = []
    wood_bytes: Optional[bytes] = None
    wood_name: str = ""
    fabric_bytes: Optional[bytes] = None
    fabric_name: str = ""

    col_work, col_out = st.columns([1.15, 1.35], gap="medium")

    with col_work:
        with st.container(border=True):
            # Carga de fotos y materiales en columnas horizontales (sin apilar hacia abajo)
            if mode == "vistas_tela":
                u1, u2 = st.columns(2)
                with u1:
                    up_views = st.file_uploader(
                        "🖼️ Vistas del mueble:",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_batch_views_{ck}",
                    )
                    vb, vn = _read_files(up_views)
                    batch_views_files = list(zip(vn, vb))
                with u2:
                    fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
            elif mode == "clonar_color":
                u1, u2 = st.columns(2)
                with u1:
                    up_ref_color = st.file_uploader(
                        "🎨 Foto maestra (color):",
                        type=IMG_TYPES,
                        accept_multiple_files=False,
                        key=f"v7_clone_ref_{ck}",
                    )
                    m_bytes, m_names = _read_files(up_ref_color)
                with u2:
                    up_views = st.file_uploader(
                        "🖼️ Vistas objetivo:",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_clone_targets_{ck}",
                    )
                    vb, vn = _read_files(up_views)
                    batch_views_files = list(zip(vn, vb))
            else:
                u_m, u_f, u_w = st.columns(3)
                with u_m:
                    up_mueble = st.file_uploader(
                        "🛋️ Foto mueble:",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_mueble_{ck}",
                    )
                    m_bytes, m_names = _read_files(up_mueble)
                with u_f:
                    if mode != "material" or material_mode in ("fabric_only", "dual"):
                        fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
                with u_w:
                    if mode != "material" or material_mode in ("wood_only", "dual"):
                        wood_bytes, wood_name = _resolve_material_selector("wood", ck, cargar_maderas_v7())

            n_col, ref_col = st.columns([2.2, 1.0], vertical_alignment="bottom")
            with n_col:
                notas = st.text_input(
                    "📝 Notas:",
                    key=f"v7_notas_{ck}",
                    placeholder="Opcional: detalles de casco, costuras o madera...",
                )
            with ref_col:
                if mode not in ("vistas_tela", "clonar_color", "plano"):
                    with st.popover("📐 Ángulos extra", use_container_width=True):
                        up_ref = st.file_uploader(
                            "Referencias extra:",
                            type=IMG_TYPES,
                            accept_multiple_files=True,
                            key=f"v7_ref_{ck}",
                        )
                        r_bytes, r_names = _read_files(up_ref)

            # Botones principales en fila horizontal adaptable
            b_34, b_go = st.columns([1.35, 1.0])
            with b_34:
                btn_34_2054 = st.button(
                    "↘️ 3/4 Derecha · Sin Sombra · 2054×2054",
                    type="primary",
                    use_container_width=True,
                    key=f"v7_btn_34_2054_{ck}",
                )
            with b_go:
                go = st.button(
                    f"🚀 Generar ({mode_label})",
                    use_container_width=True,
                    key=f"v7_btn_go_{ck}",
                )

            # Tira horizontal de miniaturas cargadas
            thumbs: List[Tuple[str, bytes]] = []
            for nm, raw in zip(m_names[:2], m_bytes[:2]):
                thumbs.append((f"🛋️ {nm}", raw))
            if fabric_bytes:
                thumbs.append((f"🧵 {fabric_name or 'Tela'}", fabric_bytes))
            if wood_bytes:
                thumbs.append((f"🪵 {wood_name or 'Madera'}", wood_bytes))
            for vn, vb in batch_views_files[:2]:
                thumbs.append((f"🖼️ {vn}", vb))

            if thumbs:
                t_cols = st.columns(len(thumbs))
                for tc, (lbl, raw_b) in zip(t_cols, thumbs):
                    with tc:
                        render_preview_image(raw_b, caption=lbl, max_dim=180)

        # ------------------------------------------------------------------ ACCIÓN 1: BOTÓN 3/4 DERECHA · 2054×2054
        if btn_34_2054:
            target_furn_bytes = m_bytes or ([batch_views_files[0][1]] if batch_views_files else [])
            target_furn_names = m_names or ([batch_views_files[0][0]] if batch_views_files else [])
            if not target_furn_bytes:
                st.error("⚠️ Sube primero la foto del mueble.")
            else:
                status = st.empty()
                try:
                    name = target_furn_names[0].rsplit(".", 1)[0] if target_furn_names else "Mueble"
                    notas_ia = "\n".join(
                        p
                        for p in [
                            f"Tipo de mueble: {tipo}" if tipo else "",
                            f"Medidas exactas: {medidas_final}" if medidas_final else "",
                            notas.strip(),
                        ]
                        if p
                    )
                    has_key = bool(ai_prompt_service_v7.get_api_key())
                    status.info(
                        "⏳ Analizando casco, tela y geometría con Gemini..."
                        if has_key
                        else "🧩 Preparando prompt 3/4 Derecha · 2054×2054..."
                    )

                    f_ana = ai_prompt_service_v7.analyze_furniture_for_enhancement(
                        furniture_bytes=target_furn_bytes,
                        reference_bytes=r_bytes,
                        wood_bytes=[wood_bytes] if wood_bytes else None,
                        fabric_bytes=[fabric_bytes] if fabric_bytes else None,
                        notas_usuario=notas_ia,
                    )
                    w_ana = (
                        ai_prompt_service_v7.analyze_material(wood_bytes, material_type="wood", sample_name=wood_name)
                        if wood_bytes
                        else None
                    )
                    t_ana = (
                        ai_prompt_service_v7.analyze_material(
                            fabric_bytes, material_type="fabric", sample_name=fabric_name
                        )
                        if fabric_bytes
                        else None
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
                        has_reference_imgs=bool(r_bytes),
                        classic_numbering=classic_num,
                    )

                    render_2054 = None
                    if has_key:
                        status.info("🎨 Renderizando foto 3/4 Derecha en 2054×2054 px (#FFFFFF, 0% sombras)...")
                        render_2054 = ai_prompt_service_v7.generate_image_34_derecha_2054(
                            prompt_text=res["items"][0]["google_ai_studio"],
                            furniture_bytes=target_furn_bytes[0],
                            wood_bytes=wood_bytes,
                            fabric_bytes=fabric_bytes,
                            ref_bytes=r_bytes,
                        )

                    ref_imgs: List[Tuple[str, bytes]] = list(zip(target_furn_names, target_furn_bytes))
                    if wood_bytes:
                        ref_imgs.append((f"madera_{wood_name or 'muestra'}.jpg", wood_bytes))
                    if fabric_bytes:
                        ref_imgs.append((f"tela_{fabric_name or 'muestra'}.jpg", fabric_bytes))

                    gen_key = f"v7_gen_id_{ck}"
                    gen_id = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state[gen_key] = gen_id
                    res["gen_id"] = gen_id
                    res["mueble_name"] = name
                    res["analysis"] = f_ana
                    res["wood_analysis"] = w_ana
                    res["fabric_analysis"] = t_ana
                    res["ref_images"] = ref_imgs
                    res["render_2054"] = render_2054
                    st.session_state["v7_result"] = res
                    if render_2054:
                        st.session_state["v7_render_2054"] = render_2054
                        status.success("✅ ¡Foto 2054×2054 y Prompt listos!")
                    else:
                        status.success("✅ ¡Prompt 3/4 Derecha · 2054×2054 listo!")
                except Exception as e:  # noqa: BLE001
                    status.error(f"❌ Error: {e}")

        # ------------------------------------------------------------------ ACCIÓN 2: MODO SELECCIONADO
        if go:
            err = None
            if mode == "vistas_tela":
                if not batch_views_files:
                    err = "⚠️ Sube al menos una vista del mueble."
                elif not fabric_bytes:
                    err = "⚠️ Selecciona o sube la muestra de tela."
            elif mode == "clonar_color":
                if not m_bytes:
                    err = "⚠️ Sube la foto maestra con el color correcto."
                elif not batch_views_files:
                    err = "⚠️ Sube al menos una vista a recolorear."
            else:
                if not m_bytes:
                    err = "⚠️ Sube la foto del mueble."
                elif mode == "material" and material_mode in ("wood_only", "dual") and not wood_bytes:
                    err = "⚠️ Selecciona o sube muestra de madera."
                elif mode == "material" and material_mode in ("fabric_only", "dual") and not fabric_bytes:
                    err = "⚠️ Selecciona o sube muestra de tela."

            if err:
                st.error(err)
            else:
                status = st.empty()
                try:
                    name = (
                        m_names[0].rsplit(".", 1)[0]
                        if m_names
                        else (batch_views_files[0][0].rsplit(".", 1)[0] if batch_views_files else "Mueble")
                    )
                    notas_ia = "\n".join(
                        p
                        for p in [
                            f"Tipo de mueble: {tipo}" if tipo else "",
                            f"Medidas exactas: {medidas_final}" if medidas_final else "",
                            notas.strip(),
                        ]
                        if p
                    )

                    has_key = bool(ai_prompt_service_v7.get_api_key())
                    status.info("⏳ Analizando con Gemini..." if has_key else "🧩 Construyendo prompts...")

                    f_ana: Dict[str, Any] = {}
                    w_ana: Optional[Dict[str, Any]] = None
                    t_ana: Optional[Dict[str, Any]] = None

                    if mode not in ("vistas_tela", "clonar_color"):
                        f_ana = ai_prompt_service_v7.analyze_furniture_for_enhancement(
                            furniture_bytes=m_bytes,
                            reference_bytes=r_bytes,
                            wood_bytes=[wood_bytes] if wood_bytes else None,
                            fabric_bytes=[fabric_bytes] if fabric_bytes else None,
                            notas_usuario=notas_ia,
                        )
                    if wood_bytes:
                        w_ana = ai_prompt_service_v7.analyze_material(
                            wood_bytes, material_type="wood", sample_name=wood_name
                        )
                    if fabric_bytes:
                        t_ana = ai_prompt_service_v7.analyze_material(
                            fabric_bytes, material_type="fabric", sample_name=fabric_name
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
                        has_reference_imgs=bool(r_bytes),
                        white_bg_enabled=white_bg_enabled,
                        classic_numbering=classic_num,
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
                    for rn, rb in zip(r_names, r_bytes):
                        ref_imgs.append((rn, rb))

                    gen_key = f"v7_gen_id_{ck}"
                    gen_id = int(st.session_state.get(gen_key, 0)) + 1
                    st.session_state[gen_key] = gen_id
                    res["gen_id"] = gen_id
                    res["mueble_name"] = name
                    res["analysis"] = f_ana
                    res["wood_analysis"] = w_ana
                    res["fabric_analysis"] = t_ana
                    res["ref_images"] = ref_imgs
                    st.session_state.pop("v7_render_2054", None)
                    st.session_state["v7_result"] = res
                    status.success("✅ ¡Prompts listos!")
                except Exception as e:  # noqa: BLE001
                    status.error(f"❌ Error: {e}")

    # ------------------------------------------------------------------ COLUMNA DERECHA: RESULTADOS
    with col_out:
        with st.container(border=True):
            res = st.session_state.get("v7_result")
            if not res:
                st.caption("👈 Sube la foto a la izquierda y pulsa **↘️ 3/4 Derecha · 2054×2054** o **🚀 Generar**.")
                return

            gen_id = int(res.get("gen_id", 0))
            mueble_slug = res.get("mueble_name", "mueble")

            head_res, head_chk, head_zip = st.columns([1.4, 0.9, 1.1], vertical_alignment="center")
            with head_res:
                st.markdown(f"**✨ {mueble_slug}**")
            with head_chk:
                inc_imgs = st.checkbox("Fotos en .zip", value=True, key=f"v7_zip_imgs_{ck}")
            with head_zip:
                st.download_button(
                    "📦 Kit (.zip)",
                    data=_build_zip(res, include_images=inc_imgs),
                    file_name=f"kit_v7_{res.get('mode')}_{mueble_slug}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key=f"v7_dl_{ck}_{gen_id}",
                )

            render_2054 = st.session_state.get("v7_render_2054") or res.get("render_2054")
            if render_2054 and render_2054.get("png"):
                r_img_col, r_btn_col = st.columns([1.1, 1.0], vertical_alignment="center")
                with r_img_col:
                    st.image(render_2054["jpg"], caption="2054×2054 · #FFFFFF · Sin sombras", use_container_width=True)
                with r_btn_col:
                    st.success(f"✅ **{render_2054['width']} × {render_2054['height']} px**")
                    st.download_button(
                        "💾 PNG 2054×2054",
                        data=render_2054["png"],
                        file_name=f"{mueble_slug}_3_4_derecha_2054x2054.png",
                        mime="image/png",
                        use_container_width=True,
                        key=f"v7_dl_png2054_{ck}_{gen_id}",
                    )
                    st.download_button(
                        "💾 JPG 2054×2054",
                        data=render_2054["jpg"],
                        file_name=f"{mueble_slug}_3_4_derecha_2054x2054.jpg",
                        mime="image/jpeg",
                        use_container_width=True,
                        key=f"v7_dl_jpg2054_{ck}_{gen_id}",
                    )

            if res.get("mode") == "vista_34_der_2054":
                with st.expander("📐 Ajustar imagen externa a 2054×2054 exactos (#FFFFFF)", expanded=not bool(render_2054)):
                    ext_up = st.file_uploader(
                        "Sube foto para dejarla en 2054×2054 px exactos:",
                        type=IMG_TYPES,
                        key=f"v7_ext2054_{ck}_{gen_id}",
                        label_visibility="collapsed",
                    )
                    if ext_up:
                        fmt_img = ai_prompt_service_v7.format_image_2054_white(ext_up.getvalue(), target_px=2054)
                        c_p, c_j = st.columns(2)
                        with c_p:
                            st.download_button(
                                "💾 PNG 2054×2054",
                                data=fmt_img["png"],
                                file_name=f"{mueble_slug}_2054x2054.png",
                                mime="image/png",
                                use_container_width=True,
                                key=f"v7_ext_png_{ck}_{gen_id}",
                            )
                        with c_j:
                            st.download_button(
                                "💾 JPG 2054×2054",
                                data=fmt_img["jpg"],
                                file_name=f"{mueble_slug}_2054x2054.jpg",
                                mime="image/jpeg",
                                use_container_width=True,
                                key=f"v7_ext_jpg_{ck}_{gen_id}",
                            )

            items = res.get("items", [])
            if len(items) > 1:
                fmt = st.radio(
                    "Formato:",
                    ["📸 1x1", "⚡ Secuencial ('foto')"],
                    horizontal=True,
                    key=f"v7_fmt_{ck}",
                    label_visibility="collapsed",
                )
                if fmt.startswith("⚡") and res.get("master_ais"):
                    t1, t2, t3 = st.tabs(["🌐 AI Studio", "🤖 ChatGPT", "🎨 Midjourney"])
                    with t1:
                        render_copy_button(
                            res["master_ais"],
                            label="📋 Copiar Maestro (AI Studio)",
                            key=f"v7_cpm_ais_{ck}_{gen_id}",
                        )
                        st.text_area("Maestro:", res["master_ais"], height=210, key=f"v7_m_ais_{ck}_{gen_id}", label_visibility="collapsed")
                    with t2:
                        render_copy_button(
                            res["master_dal"],
                            label="📋 Copiar Maestro (ChatGPT)",
                            key=f"v7_cpm_dal_{ck}_{gen_id}",
                        )
                        st.text_area("Maestro:", res["master_dal"], height=210, key=f"v7_m_dal_{ck}_{gen_id}", label_visibility="collapsed")
                    with t3:
                        st.text_area("Midjourney:", res.get("midjourney", ""), height=120, key=f"v7_m_mj_{ck}_{gen_id}", label_visibility="collapsed")
                else:
                    tabs = st.tabs([f"{i['icon']} {i['short_name']}" for i in items])
                    for idx, (tab, item) in enumerate(zip(tabs, items)):
                        with tab:
                            _render_item(item, idx, ck, gen_id)
            elif items:
                _render_item(items[0], 0, ck, gen_id)

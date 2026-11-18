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


def _num(label: str, key: str, help_txt: Optional[str] = None) -> float:
    return float(st.number_input(label, min_value=0.0, step=1.0, format="%.0f", key=key, help=help_txt))


def _resolve_material_selector(
    kind: str,
    ck: int,
    catalog_items: List[Dict[str, str]],
) -> Tuple[Optional[bytes], str]:
    """Selector compacto: catálogo oficial (Drive/local) o foto subida."""
    is_wood = kind == "wood"
    icon = "🪵" if is_wood else "🧵"
    short_lbl = "Madera" if is_wood else "Tela (casco y cojines)"
    options = [""] + [item["name"] for item in catalog_items]
    sel_name = st.selectbox(
        f"{icon} {short_lbl} ({len(catalog_items)}):",
        options,
        key=f"v7_sb_{kind}_{ck}",
    )
    up_file = st.file_uploader(
        f"Subir {('madera' if is_wood else 'tela')}:",
        type=IMG_TYPES,
        key=f"v7_up_{kind}_{ck}",
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
    st.markdown(f"##### {item['icon']} {item['label']}")
    if item.get("preview_bytes"):
        render_preview_image(item["preview_bytes"], caption=item["label"], max_dim=320)

    guide = item.get("attachment_guide") or []
    if guide:
        bullets = " &nbsp;|&nbsp; ".join(f"<b>{g}</b>" for g in guide)
        st.markdown(
            f"<div style='background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.35);"
            f"border-radius:6px;padding:6px 10px;margin-bottom:8px;font-size:11.5px;color:#E2E8F0;'>"
            f"📎 <b>Adjuntar en orden:</b> {bullets}</div>",
            unsafe_allow_html=True,
        )

    if item.get("needs_anchor"):
        st.info("📌 Adjunta también tu **Vista 1 aprobada** al final como **ANCHOR**.")

    t_ais, t_dal, t_mj = st.tabs(["🌐 AI Studio / Gemini", "🤖 ChatGPT", "🎨 Midjourney"])
    with t_ais:
        txt = item.get("google_ai_studio", "")
        st.text_area("AI Studio:", txt, height=230, key=f"v7_ais_{idx}_{ck}_{gen_id}")
        render_copy_button(
            txt,
            label=f"📋 Copiar ({item.get('short_name', 'AI Studio')})",
            key=f"v7_cp_ais_{idx}_{ck}_{gen_id}",
        )
    with t_dal:
        txt = item.get("chatgpt_dalle3", "")
        st.text_area("ChatGPT:", txt, height=210, key=f"v7_dal_{idx}_{ck}_{gen_id}")
        render_copy_button(
            txt,
            label=f"📋 Copiar ({item.get('short_name', 'ChatGPT')})",
            key=f"v7_cp_dal_{idx}_{ck}_{gen_id}",
        )
    with t_mj:
        txt = item.get("midjourney_v6", "")
        st.text_area("Midjourney:", txt, height=120, key=f"v7_mj_{idx}_{ck}_{gen_id}")
        render_copy_button(
            txt,
            label=f"📋 Copiar ({item.get('short_name', 'Midjourney')})",
            key=f"v7_cp_mj_{idx}_{ck}_{gen_id}",
        )

    with st.expander("✅ Revisión rápida", expanded=False):
        for c in item.get("checklist", []):
            st.markdown(f"- {c}")


def render_prompt_studio_v7() -> None:
    if "clear_key_v7" not in st.session_state:
        st.session_state.clear_key_v7 = 0
    ck = st.session_state.clear_key_v7

    st.markdown(
        """
<style>
.v7-title { font-size:13.5px; font-weight:700; margin-top:4px; margin-bottom:6px; border-bottom:1px solid #334155; padding-bottom:4px; color:#F8FAFC; }
.v7-badge { background:rgba(56,189,248,0.18); color:#38BDF8; border:1px solid rgba(56,189,248,0.45); font-size:10.5px; padding:2px 8px; border-radius:999px; font-weight:700; }
.stButton > button { white-space:normal !important; font-size:12.5px !important; font-weight:600 !important; height:auto !important; min-height:38px !important; padding:6px 10px !important; }
div[role="radiogroup"][aria-orientation="horizontal"] { gap: 6px !important; flex-wrap: wrap !important; }
div[role="radiogroup"][aria-orientation="horizontal"] > label {
    background: #1E293B !important;
    border: 1px solid #475569 !important;
    border-radius: 7px !important;
    padding: 3px 9px !important;
    margin: 0 !important;
    font-size: 12px !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------ CABECERA COMPACTA
    h_left, h_mid, h_right = st.columns([2.2, 1.0, 0.9])
    with h_left:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
            '<span style="font-size:19px;font-weight:800;color:#38BDF8;">✨ Estudio V7</span>'
            '<span class="v7-badge">Casco + Tela · 2054×2054</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    with h_mid:
        render_copy_button(SYS_PROMPT_COMPORTAMIENTO, label="🧠 Rol IA", key=f"v7_comp_{ck}")
    with h_right:
        if st.button("🗑️ Borrar", use_container_width=True, key="v7_btn_clear"):
            # Limpia fotos, muestras, SKU, medidas, notas y resultados SIN cambiar el modo ni sub-opciones activas
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

    col_in, col_prev, col_out = st.columns([1.28, 0.62, 1.55])

    m_bytes: List[bytes] = []
    m_names: List[str] = []
    r_bytes: List[bytes] = []
    r_names: List[str] = []
    batch_views_files: List[Tuple[str, bytes]] = []
    wood_bytes: Optional[bytes] = None
    wood_name: str = ""
    fabric_bytes: Optional[bytes] = None
    fabric_name: str = ""

    # ------------------------------------------------------------------ COL 1: ENTRADAS COMPACTAS
    with col_in:
        with st.container(border=True):
            sku = render_sku_autofill_bar("v7")
            tipo = sku["tipo_mueble"]
            medidas = sku["medidas"]

            st.markdown('<div class="v7-title">🎯 1. Modo</div>', unsafe_allow_html=True)
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

            vista_id = "vista_3_4_derecha"
            material_mode = "fabric_only"
            lugar_casa = ""

            if mode == "vista_suelta":
                view_opts = {k: v["label"] for k, v in ALL_SINGLE_VIEWS.items()}
                view_labels = list(view_opts.values())
                if st.session_state.get("v7_keep_vista") not in view_labels:
                    st.session_state["v7_keep_vista"] = view_opts["vista_3_4_derecha"]
                vsel = st.selectbox("Vista:", view_labels, key="v7_keep_vista")
                vista_id = next(k for k, v in view_opts.items() if v == vsel)

            if mode == "material":
                mat_labels = list(MATERIAL_MODES.keys())
                if st.session_state.get("v7_keep_matmode") not in mat_labels:
                    st.session_state["v7_keep_matmode"] = mat_labels[0]
                msel = st.radio(
                    "Material:",
                    mat_labels,
                    horizontal=True,
                    key="v7_keep_matmode",
                    label_visibility="collapsed",
                )
                material_mode = MATERIAL_MODES[msel]

            if mode in ("catalogo", "entorno") or (mode == "vista_suelta" and vista_id == "vista_entorno_cliente"):
                room_opts = ROOM_PRESETS + ["Otra"]
                if st.session_state.get("v7_keep_room") not in room_opts:
                    st.session_state["v7_keep_room"] = room_opts[0]
                room_preset = st.selectbox("🏡 Espacio:", room_opts, key="v7_keep_room")
                if room_preset == "Otra":
                    lugar_casa = st.text_input(
                        "Espacio:",
                        placeholder="Ej: Sala minimalista",
                        key="v7_keep_room_custom",
                        label_visibility="collapsed",
                    )
                else:
                    lugar_casa = room_preset

            st.markdown('<div class="v7-title">📸 2. Fotos y Tela / Madera</div>', unsafe_allow_html=True)
            if mode == "vistas_tela":
                up_views = st.file_uploader(
                    "Vistas del mueble:",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_batch_views_{ck}",
                )
                vb, vn = _read_files(up_views)
                batch_views_files = list(zip(vn, vb))
            elif mode == "clonar_color":
                up_ref_color = st.file_uploader(
                    "Foto maestra (color correcto):",
                    type=IMG_TYPES,
                    accept_multiple_files=False,
                    key=f"v7_clone_ref_{ck}",
                )
                m_bytes, m_names = _read_files(up_ref_color)
                up_views = st.file_uploader(
                    "Vistas a recolorear:",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_clone_targets_{ck}",
                )
                vb, vn = _read_files(up_views)
                batch_views_files = list(zip(vn, vb))
            else:
                up_mueble = st.file_uploader(
                    "🛋️ Foto del mueble:",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_mueble_{ck}",
                )
                m_bytes, m_names = _read_files(up_mueble)

            # Selectores directos de Tela (para aplicar misma textura en el casco) y Madera
            if mode == "material":
                if material_mode in ("fabric_only", "dual"):
                    fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
                if material_mode in ("wood_only", "dual"):
                    wood_bytes, wood_name = _resolve_material_selector("wood", ck, cargar_maderas_v7())
            elif mode == "vistas_tela":
                fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
            elif mode != "clonar_color":
                with st.expander("🧵 Tela (casco) / 🪵 Madera (opcional)", expanded=True):
                    c_fab, c_wod = st.columns(2)
                    with c_fab:
                        fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
                    with c_wod:
                        wood_bytes, wood_name = _resolve_material_selector("wood", ck, cargar_maderas_v7())

            if mode not in ("vistas_tela", "clonar_color", "plano"):
                with st.expander("📐 Ángulos extra de referencia (opcional)", expanded=False):
                    up_ref = st.file_uploader(
                        "Referencias extra:",
                        type=IMG_TYPES,
                        accept_multiple_files=True,
                        key=f"v7_ref_{ck}",
                    )
                    r_bytes, r_names = _read_files(up_ref)

            st.markdown('<div class="v7-title">📐 3. Medidas (cm)</div>', unsafe_allow_html=True)
            src_key = f"v7_med_src_{ck}"
            if src_key not in st.session_state or st.session_state[src_key] != medidas:
                d_init = ai_prompt_service_v7.parse_dimensions(tipo, medidas)
                st.session_state[f"v7_w_{ck}"] = float(d_init["width_cm"] or 0)
                st.session_state[f"v7_h_{ck}"] = float(d_init["height_cm"] or 0)
                st.session_state[f"v7_d_{ck}"] = float(d_init["depth_cm"] or 0)
                st.session_state[f"v7_diam_{ck}"] = float(d_init["diam_cm"] or 0)
                st.session_state[src_key] = medidas

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                w = _num("Ancho", f"v7_w_{ck}")
            with c2:
                h = _num("Alto", f"v7_h_{ck}")
            with c3:
                d_ = _num("Fondo", f"v7_d_{ck}")
            with c4:
                diam = _num("Diám.", f"v7_diam_{ck}")

            medidas_final = ai_prompt_service_v7.compose_dimensions_text(w, d_, h, diam)
            dims_now = ai_prompt_service_v7.parse_dimensions(tipo, medidas_final)
            for msg in ai_prompt_service_v7.sanity_warnings(dims_now["category"], w, d_, h, diam):
                st.warning(msg)

            st.markdown('<div class="v7-title">⚙️ 4. Opciones</div>', unsafe_allow_html=True)
            t1, t2 = st.columns(2)
            with t1:
                white_bg_enabled = st.toggle(
                    "⬜ Fondo blanco",
                    value=True,
                    key="v7_keep_whitebg",
                )
            with t2:
                classic_num = st.toggle(
                    "🔙 Num. clásica",
                    value=False,
                    key="v7_keep_classic",
                )

            notas = st.text_area(
                "📝 Notas:",
                key=f"v7_notas_{ck}",
                height=65,
                placeholder="Notas opcionales (ej. respetar costuras del casco, patas tono nogal)...",
            )

            # BOTÓN DIRECTO SOLICITADO: 3/4 MIRANDO A LA DERECHA · FONDO BLANCO · SIN SOMBRA · 2054×2054
            btn_34_2054 = st.button(
                "↘️ 3/4 Derecha · Blanco Sin Sombra · 2054×2054",
                type="primary",
                use_container_width=True,
                key=f"v7_btn_34_2054_{ck}",
                help="Genera el mueble en posición 3/4 mirando a la derecha, sobre blanco puro #FFFFFF, 0% sombras, con la textura exacta de la tela en el casco y salida 2054×2054 px.",
            )
            go = st.button(
                f"🚀 Generar ({mode_label})",
                use_container_width=True,
                key=f"v7_btn_go_{ck}",
            )

        # ------------------------------------------------------------------ EJECUCIÓN BOTÓN 3/4 DERECHA · 2054×2054
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
                    if has_key:
                        status.info("⏳ Analizando casco, tela y geometría con Gemini...")
                    else:
                        status.info("🧩 Preparando prompt 3/4 Derecha · 2054×2054...")

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
                        status.info("🎨 Generando foto 3/4 Derecha en 2054×2054 px (#FFFFFF, 0% sombras)...")
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
                        status.success("✅ ¡Foto 2054×2054 y Prompt 3/4 Derecha listos!")
                    else:
                        status.success("✅ ¡Prompt 3/4 Derecha · 2054×2054 listo!")
                except Exception as e:  # noqa: BLE001
                    status.error(f"❌ Error: {e}")

        # ------------------------------------------------------------------ EJECUCIÓN MODO SELECCIONADO
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
                    if has_key:
                        status.info("⏳ Analizando fotos y materiales con Gemini...")
                    else:
                        status.info("🧩 Construyendo prompts V7...")

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

                    batch_ref = None
                    if mode == "vistas_tela":
                        batch_ref = fabric_bytes
                    elif mode == "clonar_color":
                        batch_ref = m_bytes[0]

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

    # ------------------------------------------------------------------ COL 2: VISTA PREVIA
    with col_prev:
        with st.container(border=True):
            st.markdown('<div class="v7-title">📦 Cargados</div>', unsafe_allow_html=True)
            any_prev = False
            if m_bytes:
                any_prev = True
                st.caption("🛋️ Mueble")
                for nm, raw in zip(m_names, m_bytes):
                    render_preview_image(raw, caption=nm, max_dim=300)
            if fabric_bytes:
                any_prev = True
                st.caption("🧵 Tela (casco)")
                render_preview_image(fabric_bytes, caption=fabric_name or "Tela", max_dim=300)
            if wood_bytes:
                any_prev = True
                st.caption("🪵 Madera")
                render_preview_image(wood_bytes, caption=wood_name or "Madera", max_dim=300)
            if batch_views_files:
                any_prev = True
                st.caption(f"🖼️ Lote ({len(batch_views_files)})")
                for vn, vb in batch_views_files[:6]:
                    render_preview_image(vb, caption=vn, max_dim=260)
            if r_bytes:
                any_prev = True
                st.caption("📐 Extra")
                for nm, raw in zip(r_names, r_bytes):
                    render_preview_image(raw, caption=nm, max_dim=260)
            if notas and notas.strip():
                any_prev = True
                st.caption("📝 Notas")
                st.info(notas.strip())

            if not any_prev:
                st.caption("Sin archivos.")

    # ------------------------------------------------------------------ COL 3: RESULTADOS
    with col_out:
        with st.container(border=True):
            st.markdown('<div class="v7-title">✨ Resultado</div>', unsafe_allow_html=True)
            res = st.session_state.get("v7_result")
            if not res:
                st.caption("Sube la foto y pulsa **↘️ 3/4 Derecha · 2054×2054** o **🚀 Generar**.")
                return

            gen_id = int(res.get("gen_id", 0))
            mueble_slug = res.get("mueble_name", "mueble")
            for msg in res.get("warnings", []):
                st.warning(msg)

            # Bloque de foto 2054×2054 (generada por IA o ajustador instantáneo a 2054×2054 #FFFFFF)
            render_2054 = st.session_state.get("v7_render_2054") or res.get("render_2054")
            if render_2054 and render_2054.get("png"):
                st.success(
                    f"✅ Foto generada: **{render_2054['width']} × {render_2054['height']} px** · Blanco #FFFFFF · Sin sombras"
                )
                st.image(render_2054["jpg"], caption=f"{mueble_slug} · 3/4 Derecha · 2054×2054", use_container_width=True)
                dl1, dl2 = st.columns(2)
                with dl1:
                    st.download_button(
                        "💾 Descargar PNG (2054×2054)",
                        data=render_2054["png"],
                        file_name=f"{mueble_slug}_3_4_derecha_2054x2054.png",
                        mime="image/png",
                        use_container_width=True,
                        key=f"v7_dl_png2054_{ck}_{gen_id}",
                    )
                with dl2:
                    st.download_button(
                        "💾 Descargar JPG (2054×2054)",
                        data=render_2054["jpg"],
                        file_name=f"{mueble_slug}_3_4_derecha_2054x2054.jpg",
                        mime="image/jpeg",
                        use_container_width=True,
                        key=f"v7_dl_jpg2054_{ck}_{gen_id}",
                    )

            if res.get("mode") == "vista_34_der_2054":
                with st.expander("📐 Convertir imagen descargada de AI Studio/ChatGPT a 2054×2054 exactos (#FFFFFF)", expanded=not bool(render_2054)):
                    ext_up = st.file_uploader(
                        "Sube el render para dejarlo en 2054×2054 px exactos y blanco puro #FFFFFF:",
                        type=IMG_TYPES,
                        key=f"v7_ext2054_{ck}_{gen_id}",
                    )
                    if ext_up:
                        fmt_img = ai_prompt_service_v7.format_image_2054_white(ext_up.getvalue(), target_px=2054)
                        st.caption(f"✅ Lista: **{fmt_img['width']} × {fmt_img['height']} px** · Fondo #FFFFFF")
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

            c_zip_chk, c_zip_btn = st.columns([1.1, 1.4])
            with c_zip_chk:
                inc_imgs = st.checkbox(
                    "Incluir fotos en .zip",
                    value=True,
                    key=f"v7_zip_imgs_{ck}",
                )
            with c_zip_btn:
                st.download_button(
                    "📦 Descargar Kit (.zip)",
                    data=_build_zip(res, include_images=inc_imgs),
                    file_name=f"kit_v7_{res.get('mode')}_{mueble_slug}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key=f"v7_dl_{ck}_{gen_id}",
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
                        st.text_area("Maestro:", res["master_ais"], height=280, key=f"v7_m_ais_{ck}_{gen_id}")
                        render_copy_button(
                            res["master_ais"],
                            label="📋 Copiar Maestro (AI Studio)",
                            key=f"v7_cpm_ais_{ck}_{gen_id}",
                        )
                    with t2:
                        st.text_area("Maestro:", res["master_dal"], height=280, key=f"v7_m_dal_{ck}_{gen_id}")
                        render_copy_button(
                            res["master_dal"],
                            label="📋 Copiar Maestro (ChatGPT)",
                            key=f"v7_cpm_dal_{ck}_{gen_id}",
                        )
                    with t3:
                        st.text_area("Midjourney:", res.get("midjourney", ""), height=130, key=f"v7_m_mj_{ck}_{gen_id}")
                else:
                    tabs = st.tabs([f"{i['icon']} {i['short_name']}" for i in items])
                    for idx, (tab, item) in enumerate(zip(tabs, items)):
                        with tab:
                            _render_item(item, idx, ck, gen_id)
            elif items:
                _render_item(items[0], 0, ck, gen_id)

            ana = res.get("analysis") or {}
            wa = res.get("wood_analysis") or {}
            fa = res.get("fabric_analysis") or {}
            if ana or wa or fa:
                with st.expander("🔍 Análisis IA", expanded=False):
                    if ana:
                        st.markdown(f"**Mueble:** `{ana.get('furniture_item', 'N/A')}`")
                        st.markdown(f"**Geometría:** `{ana.get('geometric_structure', 'N/A')}`")
                    if fa:
                        st.markdown(f"**Tela (casco):** `{fa.get('name', 'N/A')}` — `{fa.get('color_description', 'N/A')}`")
                    if wa:
                        st.markdown(f"**Madera:** `{wa.get('name', 'N/A')}` — `{wa.get('color_description', 'N/A')}`")

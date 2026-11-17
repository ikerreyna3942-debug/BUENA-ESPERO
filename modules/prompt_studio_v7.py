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
    "Solo madera": "wood_only",
    "Solo tela": "fabric_only",
    "Madera + tela": "dual",
}

SYS_PROMPT_COMPORTAMIENTO = (
    "Eres un Director de Arte de talla mundial, experto en Fotografía de Producto Comercial, "
    "Diseño de Interiores y Renderizado Arquitectónico Hiperrealista (CGI). "
    "Tu objetivo es conceptualizar escenas visuales impecables para catálogos de muebles de lujo. "
    "Dominas a la perfección la composición fotográfica, iluminación de estudio (softboxes, luz natural, HDR), "
    "materialidad (vetas de madera, tramado de telas premium) y atmósferas minimalistas o cálidas. "
    "Tu estilo es hiperrealista, fotográfico, elegante, de resolución 8k y renderizado fotorrealista."
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
    """Selector dual: catálogo oficial (Drive/local) o foto personalizada subida."""
    is_wood = kind == "wood"
    icon = "🪵" if is_wood else "🧵"
    title = "Muestra de Madera / Color" if is_wood else "Muestra de Tela"
    accent = "#F59E0B" if is_wood else "#38BDF8"

    st.markdown(
        f"""
        <div style="background:#1E293B; border:1px solid #475569; border-radius:8px; padding:8px 12px; margin-top:8px; margin-bottom:6px;">
            <div style="font-weight:700; color:{accent}; font-size:13px; display:flex; justify-content:space-between; align-items:center;">
                <span>{icon} {title}</span>
                <span style="font-size:11px; color:#94A3B8;">Catálogo ({len(catalog_items)}) o foto propia</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    options = [""] + [item["name"] for item in catalog_items]
    sel_name = st.selectbox(
        f"Catálogo oficial ({len(catalog_items)}):",
        options,
        key=f"v7_sb_{kind}_{ck}",
    )
    up_file = st.file_uploader(
        f"O sube foto personalizada ({'madera' if is_wood else 'tela'}):",
        type=IMG_TYPES,
        key=f"v7_up_{kind}_{ck}",
    )

    if up_file:
        return up_file.getvalue(), getattr(up_file, "name", title)

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
                "--- CHECKLIST DE REVISIÓN ---\n"
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

        if include_images:
            for idx, (fname, raw) in enumerate(res.get("ref_images", []), start=1):
                safe_name = os.path.basename(fname or f"referencia_{idx}.jpg")
                z.writestr(f"fotos/{idx:02d}_{safe_name}", raw)
    return buf.getvalue()


def _render_item(item: Dict[str, Any], idx: int, ck: int, gen_id: int) -> None:
    st.markdown(f"##### {item['icon']} {item['label']}")
    if item.get("preview_bytes"):
        render_preview_image(item["preview_bytes"], caption=item["label"], max_dim=360)

    guide = item.get("attachment_guide") or []
    if guide:
        bullets = " &nbsp;|&nbsp; ".join(f"<b>{g}</b>" for g in guide)
        st.markdown(
            f"<div style='background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.35);"
            f"border-radius:8px;padding:8px 12px;margin-bottom:10px;font-size:12px;color:#E2E8F0;'>"
            f"📎 <b>Adjunta en este orden exacto:</b><br/>{bullets}</div>",
            unsafe_allow_html=True,
        )

    if item.get("needs_anchor"):
        st.info(
            "📌 Tip de consistencia: genera y aprueba primero la **Vista 1 (Frontal 0°)**, "
            "y adjúntala al final como imagen **ANCHOR** junto con tu foto original."
        )

    t_ais, t_dal, t_mj = st.tabs(
        ["🌐 Google AI Studio / Gemini", "🤖 ChatGPT (GPT Image / DALL-E)", "🎨 Midjourney"]
    )
    with t_ais:
        txt = item.get("google_ai_studio", "")
        st.text_area("Prompt AI Studio:", txt, height=250, key=f"v7_ais_{idx}_{ck}_{gen_id}")
        render_copy_button(
            txt,
            label=f"📋 Copiar {item.get('short_name', 'prompt')} (AI Studio)",
            key=f"v7_cp_ais_{idx}_{ck}_{gen_id}",
        )
    with t_dal:
        txt = item.get("chatgpt_dalle3", "")
        st.text_area("Prompt ChatGPT:", txt, height=230, key=f"v7_dal_{idx}_{ck}_{gen_id}")
        render_copy_button(
            txt,
            label=f"📋 Copiar {item.get('short_name', 'prompt')} (ChatGPT)",
            key=f"v7_cp_dal_{idx}_{ck}_{gen_id}",
        )
    with t_mj:
        st.caption("⚠️ Solo para Midjourney (Discord). No pegar en Google AI Studio ni ChatGPT.")
        txt = item.get("midjourney_v6", "")
        st.text_area("Prompt Midjourney:", txt, height=130, key=f"v7_mj_{idx}_{ck}_{gen_id}")
        render_copy_button(
            txt,
            label=f"📋 Copiar {item.get('short_name', 'prompt')} (Midjourney)",
            key=f"v7_cp_mj_{idx}_{ck}_{gen_id}",
        )

    with st.expander("✅ Checklist de calidad: revisa la imagen generada", expanded=False):
        for c in item.get("checklist", []):
            st.markdown(f"- {c}")
        st.caption("Si algo no salió perfecto, anota la corrección en Notas y vuelve a pulsar GENERAR.")


def render_prompt_studio_v7() -> None:
    if "clear_key_v7" not in st.session_state:
        st.session_state.clear_key_v7 = 0
    ck = st.session_state.clear_key_v7

    st.markdown(
        """
<style>
.v7-title { font-size:15px; font-weight:700; margin-bottom:10px; border-bottom:1px solid #334155; padding-bottom:6px; color:#F8FAFC; }
.v7-badge { background:rgba(56,189,248,0.18); color:#38BDF8; border:1px solid rgba(56,189,248,0.45); font-size:11px; padding:3px 10px; border-radius:999px; font-weight:700; }
.stButton > button { white-space:normal !important; font-size:13px !important; font-weight:600 !important; height:auto !important; min-height:42px !important; }
</style>
""",
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------ CABECERA
    h_left, h_right = st.columns([2.6, 1.4])
    with h_left:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
            '<span style="font-size:22px;font-weight:800;color:#38BDF8;">✨ Estudio V7 · Studio Maestro</span>'
            '<span class="v7-badge">Todo en Uno · Más Actual</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        b_comp, b_info = st.columns([1.2, 2.8])
        with b_comp:
            render_copy_button(SYS_PROMPT_COMPORTAMIENTO, label="🧠 Copiar Comportamiento", key=f"v7_comp_{ck}")
        with b_info:
            st.info(
                "⚙️ Config recomendada (AI Studio): Gemini / Nano Banana Pro · Output: Image/Text · Thinking: High · Temp: 0.0"
            )
    with h_right:
        if st.button("🗑️ Limpiar todo", use_container_width=True, key="v7_btn_clear"):
            prefixes = ("v7_", "sku_", "field_")
            for k in [k for k in list(st.session_state.keys()) if k.startswith(prefixes)]:
                del st.session_state[k]
            st.session_state.clear_key_v7 = ck + 1
            st.rerun()

    col_in, col_prev, col_out = st.columns([1.25, 0.65, 1.55])

    # Variables de insumos recolectados
    m_bytes: List[bytes] = []
    m_names: List[str] = []
    r_bytes: List[bytes] = []
    r_names: List[str] = []
    batch_views_files: List[Tuple[str, bytes]] = []
    wood_bytes: Optional[bytes] = None
    wood_name: str = ""
    fabric_bytes: Optional[bytes] = None
    fabric_name: str = ""

    # ------------------------------------------------------------------ COL 1: ENTRADAS
    with col_in:
        with st.container(border=True):
            sku = render_sku_autofill_bar("v7")
            tipo = sku["tipo_mueble"]
            medidas = sku["medidas"]

            st.markdown('<div class="v7-title">🎯 1. Modo de trabajo</div>', unsafe_allow_html=True)
            mode_label = st.radio(
                "Modo V7:",
                list(MODES.values()),
                key=f"v7_mode_{ck}",
                label_visibility="collapsed",
            )
            mode = next(k for k, v in MODES.items() if v == mode_label)

            vista_id = "vista_frontal"
            material_mode = "wood_only"
            lugar_casa = ""

            if mode == "vista_suelta":
                view_opts = {k: v["label"] for k, v in ALL_SINGLE_VIEWS.items()}
                vsel = st.selectbox("Ángulo / Vista:", list(view_opts.values()), key=f"v7_vista_{ck}")
                vista_id = next(k for k, v in view_opts.items() if v == vsel)

            if mode == "material":
                msel = st.radio(
                    "Material a cambiar:",
                    list(MATERIAL_MODES.keys()),
                    horizontal=True,
                    key=f"v7_matmode_{ck}",
                )
                material_mode = MATERIAL_MODES[msel]

            if mode in ("catalogo", "entorno") or (mode == "vista_suelta" and vista_id == "vista_entorno_cliente"):
                room_preset = st.selectbox(
                    "🏡 Habitación para Entorno (Casa de Cliente):",
                    ROOM_PRESETS + ["Otra (escribir abajo)"],
                    key=f"v7_room_sel_{ck}",
                )
                if room_preset == "Otra (escribir abajo)":
                    lugar_casa = st.text_input(
                        "Especifica la habitación:",
                        placeholder="Ej: Sala minimalista doble altura con ventanal",
                        key=f"v7_room_txt_{ck}",
                    )
                else:
                    lugar_casa = room_preset

            st.markdown('<div class="v7-title">📸 2. Fotos e Insumos</div>', unsafe_allow_html=True)
            if mode == "vistas_tela":
                up_views = st.file_uploader(
                    "Vistas del mueble a las que aplicar tela (1 o varias):",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_batch_views_{ck}",
                )
                vb, vn = _read_files(up_views)
                batch_views_files = list(zip(vn, vb))
            elif mode == "clonar_color":
                up_ref_color = st.file_uploader(
                    "Foto MAESTRA con el color / acabado correcto (Image 1):",
                    type=IMG_TYPES,
                    accept_multiple_files=False,
                    key=f"v7_clone_ref_{ck}",
                )
                m_bytes, m_names = _read_files(up_ref_color)
                up_views = st.file_uploader(
                    "Vistas OBJETIVO a recolorear (Image 2, varias posibles):",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_clone_targets_{ck}",
                )
                vb, vn = _read_files(up_views)
                batch_views_files = list(zip(vn, vb))
            else:
                up_mueble = st.file_uploader(
                    "Foto(s) del mueble original (Image 1):",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_mueble_{ck}",
                )
                m_bytes, m_names = _read_files(up_mueble)

            # Selectores de Madera / Tela (directos en modos de material, opcionales en otros)
            if mode == "material":
                if material_mode in ("wood_only", "dual"):
                    wood_bytes, wood_name = _resolve_material_selector("wood", ck, cargar_maderas_v7())
                if material_mode in ("fabric_only", "dual"):
                    fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
            elif mode == "vistas_tela":
                fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
            elif mode in ("catalogo", "vista_suelta", "entorno", "extraer", "hd"):
                with st.expander("🪵/🧵 Aplicar o fijar muestra de Madera / Tela (opcional)", expanded=False):
                    use_cat_drive = st.checkbox(
                        "Incluir catálogo de Drive (además de muestras locales)",
                        value=False,
                        key=f"v7_drive_cat_{ck}",
                    )
                    wood_bytes, wood_name = _resolve_material_selector(
                        "wood", ck, cargar_maderas_v7(include_drive=use_cat_drive)
                    )
                    if use_cat_drive:
                        fabric_bytes, fabric_name = _resolve_material_selector("fabric", ck, cargar_telas_v7())
                    else:
                        up_fab_opt = st.file_uploader(
                            "Subir muestra de tela (opcional):",
                            type=IMG_TYPES,
                            key=f"v7_up_fabric_opt_{ck}",
                        )
                        if up_fab_opt:
                            fabric_bytes = up_fab_opt.getvalue()
                            fabric_name = getattr(up_fab_opt, "name", "Tela")

            if mode not in ("vistas_tela", "clonar_color", "plano"):
                up_ref = st.file_uploader(
                    "Referencias extra de ángulos (opcional):",
                    type=IMG_TYPES,
                    accept_multiple_files=True,
                    key=f"v7_ref_{ck}",
                )
                r_bytes, r_names = _read_files(up_ref)

            st.markdown('<div class="v7-title">📐 3. Confirma las medidas (cm)</div>', unsafe_allow_html=True)
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
                d_ = _num("Fondo/Grosor", f"v7_d_{ck}", "En espejos y piezas de pared, es el grosor.")
            with c4:
                diam = _num("Diámetro", f"v7_diam_{ck}", "Solo para piezas redondas.")

            medidas_final = ai_prompt_service_v7.compose_dimensions_text(w, d_, h, diam)
            dims_now = ai_prompt_service_v7.parse_dimensions(tipo, medidas_final)
            for msg in ai_prompt_service_v7.sanity_warnings(dims_now["category"], w, d_, h, diam):
                st.warning(msg)

            st.markdown('<div class="v7-title">⚙️ 4. Opciones y Notas</div>', unsafe_allow_html=True)
            t1, t2 = st.columns(2)
            with t1:
                white_bg_enabled = st.toggle(
                    "⬜ Fondo blanco puro (#FFFFFF)",
                    value=True,
                    key=f"v7_whitebg_{ck}",
                    help="Aplica fondo #FFFFFF con 0% sombras (desactívalo en Material / HD / Lote si deseas mantener el fondo original).",
                )
            with t2:
                classic_num = st.toggle(
                    "🔙 Numeración clásica V1",
                    value=False,
                    key=f"v7_classic_{ck}",
                    help="Por defecto V7 calcula el índice exacto (Image 1, Image 2...) según lo que adjuntas.",
                )

            notas = st.text_area(
                "📝 Notas obligatorias para la IA (opcional):",
                key=f"v7_notas_{ck}",
                height=80,
                placeholder="Ej: acabado roble mate sedoso, respetar proporciones. Si una vista falló, escribe aquí qué corregir.",
            )

            go = st.button("🚀 GENERAR PROMPTS V7", type="primary", use_container_width=True, key=f"v7_btn_go_{ck}")

        if go:
            err = None
            if mode == "vistas_tela":
                if not batch_views_files:
                    err = "⚠️ Sube al menos una vista del mueble para aplicar la tela."
                elif not fabric_bytes:
                    err = "⚠️ Selecciona o sube la muestra de tela."
            elif mode == "clonar_color":
                if not m_bytes:
                    err = "⚠️ Sube la foto maestra con el color/acabado correcto."
                elif not batch_views_files:
                    err = "⚠️ Sube al menos una vista objetivo a recolorear."
            else:
                if not m_bytes:
                    err = "⚠️ Sube al menos la foto original del mueble."
                elif mode == "material" and material_mode in ("wood_only", "dual") and not wood_bytes:
                    err = "⚠️ Selecciona o sube una muestra de madera."
                elif mode == "material" and material_mode in ("fabric_only", "dual") and not fabric_bytes:
                    err = "⚠️ Selecciona o sube una muestra de tela."

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
                        status.info("⏳ Analizando fotos y materiales con Gemini Vision...")
                    else:
                        status.info("🧩 Construyendo prompts V7 en modo local (sin GEMINI_API_KEY)...")

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

                    status.info("🧩 Ensamblando prompts optimizados V7...")
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

                    ref_imgs: List[Tuple[str, bytes]] = list(zip(m_names, m_bytes))
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
                    st.session_state["v7_result"] = res
                    status.success("✅ ¡Prompts V7 listos!")
                except Exception as e:  # noqa: BLE001
                    status.error(f"❌ Error al generar prompts: {e}")

    # ------------------------------------------------------------------ COL 2: VISTA PREVIA EN VIVO
    with col_prev:
        with st.container(border=True):
            st.markdown('<div class="v7-title">📦 Elementos Cargados</div>', unsafe_allow_html=True)
            any_prev = False
            if m_bytes:
                any_prev = True
                st.caption("📸 Foto del Mueble / Referencia")
                for nm, raw in zip(m_names, m_bytes):
                    render_preview_image(raw, caption=nm, max_dim=320)
            if wood_bytes:
                any_prev = True
                st.caption("🪵 Muestra de Madera")
                render_preview_image(wood_bytes, caption=wood_name or "Madera", max_dim=320)
            if fabric_bytes:
                any_prev = True
                st.caption("🧵 Muestra de Tela")
                render_preview_image(fabric_bytes, caption=fabric_name or "Tela", max_dim=320)
            if batch_views_files:
                any_prev = True
                st.caption(f"🖼️ Vistas del Lote ({len(batch_views_files)})")
                for vn, vb in batch_views_files[:6]:
                    render_preview_image(vb, caption=vn, max_dim=280)
            if r_bytes:
                any_prev = True
                st.caption("📐 Referencias Extra")
                for nm, raw in zip(r_names, r_bytes):
                    render_preview_image(raw, caption=nm, max_dim=280)
            if notas and notas.strip():
                any_prev = True
                st.caption("📝 Notas activas")
                st.info(notas.strip())

            if not any_prev:
                st.caption("Sube o selecciona tus fotos y muestras en la columna izquierda para verlas aquí.")

    # ------------------------------------------------------------------ COL 3: RESULTADOS
    with col_out:
        with st.container(border=True):
            st.markdown('<div class="v7-title">✨ Prompts Generados (V7)</div>', unsafe_allow_html=True)
            res = st.session_state.get("v7_result")
            if not res:
                st.info("👈 Configura el modo, fotos y medidas a la izquierda y pulsa **🚀 GENERAR PROMPTS V7**.")
                return

            gen_id = int(res.get("gen_id", 0))
            for msg in res.get("warnings", []):
                st.warning(msg)

            d = res.get("dims", {})
            if d.get("diam_cm"):
                dims_summary = f"Diámetro {d.get('diam_cm')} · Alto {d.get('height_cm') or '-'} cm"
            else:
                dims_summary = (
                    f"Ancho {d.get('width_cm') or '-'} · "
                    f"Alto {d.get('height_cm') or '-'} · Fondo/grosor {d.get('depth_cm') or '-'} cm"
                )
            st.caption(f"Categoría: **{d.get('category')} ({d.get('sub_category')})** · {dims_summary}")

            inc_imgs = st.checkbox(
                "Incluir fotos de referencia en el .zip",
                value=True,
                key=f"v7_zip_imgs_{ck}",
            )
            st.download_button(
                "📦 Descargar Kit Completo (.zip)",
                data=_build_zip(res, include_images=inc_imgs),
                file_name=f"kit_v7_{res.get('mode')}_{res.get('mueble_name', 'mueble')}.zip",
                mime="application/zip",
                use_container_width=True,
                key=f"v7_dl_{ck}_{gen_id}",
            )

            items = res.get("items", [])
            if len(items) > 1:
                fmt = st.radio(
                    "Formato:",
                    ["📸 Una imagen por prompt (recomendado)", "⚡ Un solo prompt maestro secuencial ('foto')"],
                    horizontal=True,
                    key=f"v7_fmt_{ck}",
                )
                if fmt.startswith("⚡") and res.get("master_ais"):
                    st.warning("El modo secuencial depende de la memoria del chat. Úsalo en un chat nuevo.")
                    t1, t2, t3 = st.tabs(["🌐 Google AI Studio", "🤖 ChatGPT", "🎨 Midjourney"])
                    with t1:
                        st.text_area("Prompt maestro:", res["master_ais"], height=310, key=f"v7_m_ais_{ck}_{gen_id}")
                        render_copy_button(
                            res["master_ais"],
                            label="📋 Copiar Prompt Maestro (AI Studio)",
                            key=f"v7_cpm_ais_{ck}_{gen_id}",
                        )
                    with t2:
                        st.text_area("Prompt maestro:", res["master_dal"], height=310, key=f"v7_m_dal_{ck}_{gen_id}")
                        render_copy_button(
                            res["master_dal"],
                            label="📋 Copiar Prompt Maestro (ChatGPT)",
                            key=f"v7_cpm_dal_{ck}_{gen_id}",
                        )
                    with t3:
                        st.caption("⚠️ Solo para Midjourney (Discord). No pegar en AI Studio ni ChatGPT.")
                        st.text_area("Midjourney:", res.get("midjourney", ""), height=140, key=f"v7_m_mj_{ck}_{gen_id}")
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
                with st.expander("🔍 Análisis de Visión y Materiales", expanded=False):
                    if ana:
                        st.markdown(f"**Mueble:** `{ana.get('furniture_item', 'N/A')}`")
                        st.markdown(f"**Materiales:** `{ana.get('existing_materials', 'N/A')}`")
                        st.markdown(f"**Geometría:** `{ana.get('geometric_structure', 'N/A')}`")
                    if wa:
                        st.markdown(f"**Madera:** `{wa.get('name', 'N/A')}` — `{wa.get('color_description', 'N/A')}`")
                    if fa:
                        st.markdown(f"**Tela:** `{fa.get('name', 'N/A')}` — `{fa.get('color_description', 'N/A')}`")

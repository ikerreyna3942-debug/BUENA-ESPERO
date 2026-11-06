import io
import zipfile

import streamlit as st

from modules.sku_banner import render_sku_autofill_bar
from modules.prompt_studio_v5 import render_copy_button, render_preview_image
from services import unified_prompt_service as ups

IMG_TYPES = ["png", "jpg", "jpeg", "webp", "bmp", "heic", "tiff"]
MATERIAL_MODES = {
    "Solo madera": "wood_only",
    "Solo tela": "fabric_only",
    "Madera + tela": "dual",
}
VIEW_LABELS = {
    "vista_frontal": "Vista 1 · Frontal 0°",
    "vista_perspectiva_3_4": "Vista 2 · 3/4 Perspectiva 45°",
    "vista_lateral": "Vista 3 · Lateral 90°",
    "vista_picada_alta": "Vista 4 · Picada alta 65°",
    "vista_superior_cenital": "Vista 5 · Superior cenital 90°",
    "vista_plano_tecnico": "Vista 6 · Plano técnico con medidas",
    "vista_entorno_cliente": "Vista 7 · Entorno casa de cliente",
}


def _read_files(files):
    """Devuelve (lista_de_bytes, lista_de_nombres) para uno o varios uploads."""
    if not files:
        return [], []
    lst = files if isinstance(files, list) else [files]
    data, names = [], []
    for f in lst:
        data.append(f.getvalue() if hasattr(f, "getvalue") else f.read())
        names.append(getattr(f, "name", "foto"))
    return data, names


def _num(label, key, help_txt=None):
    return st.number_input(label, min_value=0.0, step=1.0, format="%.0f", key=key, help=help_txt)


def _render_item(item, idx, ck, show_anchor_tip=True):
    st.markdown(f"##### {item['icon']} {item['label']}")
    if item.get("needs_anchor") and show_anchor_tip:
        st.info(
            "📌 Para que salga idéntico: primero genera y aprueba la **Vista 1**, "
            "y adjúntala como **Imagen 2** junto con la foto original."
        )
    t_ais, t_dal = st.tabs(["🌐 Google AI Studio / Gemini", "🤖 ChatGPT (DALL-E 3)"])
    with t_ais:
        txt = item.get("google_ai_studio", "")
        st.text_area("Prompt:", txt, height=230, key=f"uni_txt_ais_{idx}_{ck}")
        render_copy_button(txt, label=f"📋 Copiar {item.get('short_name', 'prompt')} (AI Studio)", key=f"uni_cp_ais_{idx}_{ck}")
    with t_dal:
        txt = item.get("chatgpt_dalle3", "")
        st.text_area("Prompt:", txt, height=230, key=f"uni_txt_dal_{idx}_{ck}")
        render_copy_button(txt, label=f"📋 Copiar {item.get('short_name', 'prompt')} (ChatGPT)", key=f"uni_cp_dal_{idx}_{ck}")
    with st.expander("✅ Checklist: revisa la imagen que te dé la IA", expanded=False):
        for c in item.get("checklist", []):
            st.markdown(f"- {c}")
        st.caption("Si algo falla, escribe en Notas qué salió mal y pulsa Generar de nuevo (se agrega al prompt).")


def _build_zip(res, mueble_name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, it in enumerate(res["items"], start=1):
            body = (
                f"--- GOOGLE AI STUDIO / GEMINI ---\n{it['google_ai_studio']}\n\n"
                f"--- CHATGPT / DALL-E 3 ---\n{it['chatgpt_dalle3']}\n\n"
                "--- CHECKLIST ---\n" + "\n".join(f"- {c}" for c in it.get("checklist", []))
            )
            z.writestr(f"{i:02d}_{it['id']}.txt", body)
        if res.get("master_ais"):
            z.writestr("00_prompt_maestro_secuencial.txt", res["master_ais"] + "\n\n=====\n\n" + res.get("master_dal", ""))
    return buf.getvalue()


def render_prompt_studio_unified():
    if "clear_key_uni" not in st.session_state:
        st.session_state.clear_key_uni = 0
    ck = st.session_state.clear_key_uni

    st.markdown(
        """
<style>
.uni-card { background-color:#283548; border:1px solid #475569; border-radius:12px; padding:18px; box-shadow:0 4px 15px rgba(0,0,0,.2); }
.uni-title { font-size:15px; font-weight:700; margin-bottom:12px; border-bottom:1px solid #334155; padding-bottom:8px; }
.stButton > button { white-space:normal !important; font-size:13px !important; font-weight:600 !important; height:auto !important; min-height:42px !important; }
</style>
""",
        unsafe_allow_html=True,
    )

    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(
            '<span style="font-size:22px; font-weight:800; color:#38BDF8;">🚀 Estudio V6 · Unificado</span>'
            ' <span style="font-size:12px; color:#94A3B8;">todas las funciones en un solo lugar</span>',
            unsafe_allow_html=True,
        )
    with h2:
        if st.button("🗑️ Limpiar todo", use_container_width=True, key="uni_btn_clear"):
            prefixes = ("uni_", "sku_", "field_", "last_studio_result")
            for k in [k for k in list(st.session_state.keys()) if k.startswith(prefixes)]:
                del st.session_state[k]
            st.session_state.clear_key_uni = ck + 1
            st.rerun()

    left, right = st.columns([1.2, 1.6])

    # ------------------------------------------------------------------ ENTRADAS
    with left:
        st.markdown('<div class="uni-card">', unsafe_allow_html=True)
        sku = render_sku_autofill_bar("uni")
        tipo = sku["tipo_mueble"]
        medidas = sku["medidas"]

        st.markdown('<div class="uni-title">📸 1. Fotos</div>', unsafe_allow_html=True)
        up_mueble = st.file_uploader("Mueble (foto original):", type=IMG_TYPES, accept_multiple_files=True, key=f"uni_mueble_{ck}")
        up_madera = st.file_uploader("Muestra de madera / color (opcional):", type=IMG_TYPES, accept_multiple_files=True, key=f"uni_madera_{ck}")
        up_tela = st.file_uploader("Muestra de tela (opcional):", type=IMG_TYPES, accept_multiple_files=True, key=f"uni_tela_{ck}")
        up_ref = st.file_uploader("Referencias extra (opcional):", type=IMG_TYPES, accept_multiple_files=True, key=f"uni_ref_{ck}")

        st.markdown('<div class="uni-title">📐 2. Confirma las medidas (cm)</div>', unsafe_allow_html=True)
        src_key = f"uni_med_src_{ck}"
        if st.session_state.get(src_key) != (tipo, medidas):
            d = ups.parse_dimensions(tipo, medidas)
            st.session_state[f"uni_w_{ck}"] = float(d["width_cm"] or 0)
            st.session_state[f"uni_h_{ck}"] = float(d["height_cm"] or 0)
            st.session_state[f"uni_d_{ck}"] = float(d["depth_cm"] or 0)
            st.session_state[f"uni_diam_{ck}"] = float(d["diam_cm"] or 0)
            st.session_state[src_key] = (tipo, medidas)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            w = _num("Ancho", f"uni_w_{ck}")
        with c2:
            h = _num("Alto", f"uni_h_{ck}")
        with c3:
            d_ = _num("Fondo / grosor", f"uni_d_{ck}", "En espejos y piezas de pared, es el grosor.")
        with c4:
            diam = _num("Diámetro", f"uni_diam_{ck}", "Solo para piezas redondas.")
        medidas_final = ups.compose_dimensions_text(w, d_, h, diam)
        dims_now = ups.parse_dimensions(tipo, medidas_final)
        for msg in ups.sanity_warnings(dims_now["category"], w, d_, h, diam):
            st.warning(msg)

        st.markdown('<div class="uni-title">🎯 3. ¿Qué quieres generar?</div>', unsafe_allow_html=True)
        mode_label = st.radio("Modo:", list(ups.MODES.values()), key=f"uni_mode_{ck}", label_visibility="collapsed")
        mode = next(k for k, v in ups.MODES.items() if v == mode_label)

        vista_id = "vista_frontal"
        material_mode = "wood_only"
        if mode == "vista_suelta":
            vsel = st.selectbox("Vista:", list(VIEW_LABELS.values()), key=f"uni_vista_{ck}")
            vista_id = next(k for k, v in VIEW_LABELS.items() if v == vsel)
        if mode == "material":
            msel = st.radio("Material a cambiar:", list(MATERIAL_MODES.keys()), horizontal=True, key=f"uni_matmode_{ck}")
            material_mode = MATERIAL_MODES[msel]

        notas = st.text_area(
            "📝 Notas obligatorias para la IA (opcional):",
            key=f"uni_notas_{ck}",
            height=80,
            placeholder="Ej: roble claro mate, respetar proporciones. Si una imagen salió mal, describe aquí qué falló.",
        )

        go = st.button("🚀 GENERAR", type="primary", use_container_width=True, key=f"uni_btn_go_{ck}")
        st.markdown("</div>", unsafe_allow_html=True)

        if go:
            err = None
            if not up_mueble:
                err = "⚠️ Sube al menos la foto del mueble."
            elif mode == "material" and material_mode in ("wood_only", "dual") and not up_madera:
                err = "⚠️ Para cambiar madera sube la muestra de madera."
            elif mode == "material" and material_mode in ("fabric_only", "dual") and not up_tela:
                err = "⚠️ Para cambiar tela sube la muestra de tela."
            if err:
                st.error(err)
            else:
                status = st.empty()
                try:
                    from services.ai_prompt_service_v5 import ai_prompt_service_v5 as v5

                    m_bytes, m_names = _read_files(up_mueble)
                    w_bytes, w_names = _read_files(up_madera)
                    t_bytes, t_names = _read_files(up_tela)
                    r_bytes, r_names = _read_files(up_ref)
                    name = m_names[0].rsplit(".", 1)[0] if m_names else "Mueble"

                    notas_ia = "\n".join(
                        p for p in [
                            f"Tipo de mueble: {tipo}" if tipo else "",
                            f"Medidas exactas y proporciones 3D reales: {medidas_final} (respetar al 100%)" if medidas_final else "",
                            notas.strip(),
                        ] if p
                    )

                    status.info("⏳ Analizando fotos con Gemini Vision...")
                    f_ana = v5.analyze_furniture_for_enhancement(
                        furniture_bytes=m_bytes or r_bytes or w_bytes,
                        reference_bytes=r_bytes,
                        wood_bytes=w_bytes,
                        notas_usuario=notas_ia,
                    )
                    w_ana = v5.analyze_material(w_bytes[0], material_type="wood") if w_bytes else None
                    t_ana = v5.analyze_material(t_bytes[0], material_type="fabric") if t_bytes else None

                    status.info("🧩 Construyendo prompts...")
                    res = ups.build_prompts(
                        mode=mode,
                        furniture_name=name,
                        furniture_analysis=f_ana,
                        wood_analysis=w_ana,
                        fabric_analysis=t_ana,
                        notas_usuario=notas_ia,
                        tipo_mueble=tipo,
                        medidas_texto=medidas_final,
                        furniture_filenames=m_names,
                        wood_filenames=w_names,
                        fabric_filenames=t_names,
                        reference_filenames=r_names,
                        foto_refs={
                            "mueble": ", ".join(m_names),
                            "madera": ", ".join(w_names),
                            "tela": ", ".join(t_names),
                            "referencia": ", ".join(r_names),
                        },
                        vista_id=vista_id,
                        material_mode=material_mode,
                    )
                    res["mueble_name"] = name
                    res["analysis"] = f_ana
                    st.session_state["uni_result"] = res
                    status.success("✅ Prompts listos.")
                except Exception as e:  # noqa: BLE001
                    status.error(f"❌ Error al procesar: {e}")

    # ----------------------------------------------------------------- RESULTADOS
    with right:
        st.markdown('<div class="uni-card">', unsafe_allow_html=True)
        st.markdown('<div class="uni-title">✨ Prompts generados</div>', unsafe_allow_html=True)
        res = st.session_state.get("uni_result")
        if not res:
            st.caption("Sube la foto, confirma las medidas, elige un modo y pulsa GENERAR.")
        else:
            for msg in res.get("warnings", []):
                st.warning(msg)

            d = res.get("dims", {})
            st.caption(
                f"Categoría: **{d.get('category')}** · Ancho {d.get('width_cm') or '-'} · "
                f"Alto {d.get('height_cm') or '-'} · Fondo/grosor {d.get('depth_cm') or '-'} cm"
            )

            st.download_button(
                "📦 Descargar kit (.zip)",
                data=_build_zip(res, res.get("mueble_name", "mueble")),
                file_name=f"kit_{res.get('mode')}_{res.get('mueble_name', 'mueble')}.zip",
                mime="application/zip",
                use_container_width=True,
                key=f"uni_dl_{ck}",
            )

            items = res["items"]
            if len(items) > 1:
                fmt = st.radio(
                    "Formato:",
                    ["📸 Una imagen por prompt (recomendado)", "⚡ Un solo prompt secuencial con 'foto'"],
                    horizontal=True,
                    key=f"uni_fmt_{ck}",
                )
                if fmt.startswith("⚡") and res.get("master_ais"):
                    st.warning("El modo secuencial depende de la memoria del chat y puede repetir ángulos. Abre un chat nuevo.")
                    t1, t2, t3 = st.tabs(["🌐 Google AI Studio", "🤖 ChatGPT", "🎨 Midjourney"])
                    with t1:
                        st.text_area("Prompt maestro:", res["master_ais"], height=300, key=f"uni_m_ais_{ck}")
                        render_copy_button(res["master_ais"], label="📋 Copiar prompt maestro (AI Studio)", key=f"uni_cpm_ais_{ck}")
                    with t2:
                        st.text_area("Prompt maestro:", res["master_dal"], height=300, key=f"uni_m_dal_{ck}")
                        render_copy_button(res["master_dal"], label="📋 Copiar prompt maestro (ChatGPT)", key=f"uni_cpm_dal_{ck}")
                    with t3:
                        st.caption("⚠️ Solo para Midjourney (Discord). No pegar en AI Studio ni ChatGPT.")
                        st.text_area("Midjourney:", res.get("midjourney", ""), height=140, key=f"uni_m_mj_{ck}")
                else:
                    tabs = st.tabs([f"{i['icon']} {i['short_name']}" for i in items])
                    for idx, (tab, item) in enumerate(zip(tabs, items)):
                        with tab:
                            _render_item(item, idx, ck)
            else:
                _render_item(items[0], 0, ck)

            ana = res.get("analysis") or {}
            if ana:
                with st.expander("🔍 Análisis de Gemini Vision", expanded=False):
                    st.markdown(f"**Mueble:** `{ana.get('furniture_item', 'N/A')}`")
                    st.markdown(f"**Materiales:** `{ana.get('existing_materials', 'N/A')}`")
                    st.markdown(f"**Geometría:** `{ana.get('geometric_structure', 'N/A')}`")
        st.markdown("</div>", unsafe_allow_html=True)

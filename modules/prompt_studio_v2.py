import os
import io
from pathlib import Path
import streamlit as st
from PIL import Image

FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"

@st.cache_data(ttl=300)
def cargar_telas_menu_v2():
    from services.sheets_service import sheets_service
    return sheets_service.get_drive_folder_files(FOLDER_TELAS_DRIVE_ID, recursive=True)

@st.cache_data(ttl=300)
def cargar_maderas_menu_v2():
    from services.sheets_service import sheets_service
    drive_maderas = sheets_service.get_drive_folder_files(FOLDER_MADERAS_DRIVE_ID, recursive=True)
    
    app_dir = Path(__file__).resolve().parent.parent
    maderas_dir = app_dir / "muestras_madera"
    local_maderas = []
    if maderas_dir.exists():
        for f in sorted(maderas_dir.glob("*.jpg")):
            clean_name = f.stem.replace("_", " ")
            local_maderas.append({
                "id": f.name,
                "name": clean_name,
                "filename": f.name,
                "link": "",
                "local_path": str(f)
            })
    
    combined = local_maderas + [m for m in drive_maderas if not any(l["name"].upper() == m["name"].upper() for l in local_maderas)]
    return combined

def render_copy_button(text: str, label: str = "📋 Copiar Prompt", key: str = "cp_v2"):
    """Renderiza un botón que copia el texto al portapapeles nativamente en 1 clic."""
    import json
    import streamlit.components.v1 as components
    escaped_text = json.dumps(text)
    html_code = f"""
    <div style="margin: 4px 0 8px 0;">
        <button id="btn_{key}" onclick='
            navigator.clipboard.writeText({escaped_text}).then(() => {{
                const b = document.getElementById("btn_{key}");
                const orig = b.innerHTML;
                b.innerHTML = "✅ ¡Copiado!";
                b.style.backgroundColor = "#059669";
                setTimeout(() => {{
                    b.innerHTML = orig;
                    b.style.backgroundColor = "#2563EB";
                }}, 2000);
            }});
        ' style="
            width: 100%;
            background-color: #2563EB;
            color: #FFFFFF;
            border: none;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 600;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
        ">
            {label}
        </button>
    </div>
    """
    components.html(html_code, height=44)

def render_prompt_studio_v2():
    from services.ai_prompt_service_v2 import ai_prompt_service_v2
    from services.sheets_service import sheets_service

    st.markdown("""
<style>
/* Usar los mismos estilos base */
.studio-top-bar { background-color: #283548; border: 1px solid #475569; border-radius: 10px; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.studio-badge { background: rgba(16, 185, 129, 0.2); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.4); font-size: 11px; padding: 3px 8px; border-radius: 9999px; font-weight: 700; }
.studio-card { background-color: #283548; border: 1px solid #475569; border-radius: 12px; padding: 18px; height: 100%; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
.studio-card-title { font-size: 15px; font-weight: 700; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; }
.protection-badge { background: rgba(56, 189, 248, 0.2); border: 1px solid rgba(56, 189, 248, 0.4); color: #38BDF8; border-radius: 8px; padding: 10px 14px; font-size: 12px; font-weight: 600; text-align: center; margin-top: 14px; }
.meta-pill { display: inline-block; background: #1E293B; border: 1px solid #475569; color: #38BDF8; font-size: 11px; padding: 4px 10px; border-radius: 6px; margin: 2px; }
</style>
""", unsafe_allow_html=True)

    c_head_left, c_head_right = st.columns([2, 2])

    with c_head_left:
        st.markdown("""
<div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
    <span style="font-size:22px; font-weight:800; color:#10B981;">⚡ Estudio V2 (Estructurado)</span>
    <span class="studio-badge">Producción Limpia</span>
</div>
        """, unsafe_allow_html=True)

    with c_head_right:
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if "last_studio_result_v2" in st.session_state:
                import io
                import zipfile
                res = st.session_state["last_studio_result_v2"]
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    prompt_txt = res["prompts"].get("google_ai_studio", "") or res["prompts"].get("chatgpt_dalle3", "") or res["prompts"].get("flux_midjourney", "")
                    if prompt_txt:
                        zip_file.writestr(f"prompt_{res.get('mueble_name', 'generado')}.txt", prompt_txt)
                    
                    m = st.session_state.get("st_mueble")
                    if m: zip_file.writestr("1_foto_mueble.jpg", m.getvalue())
                    t = st.session_state.get("st_tela")
                    if t: zip_file.writestr("2_foto_tela.jpg", t.getvalue())
                    w = st.session_state.get("st_madera")
                    if w: zip_file.writestr("3_foto_madera.jpg", w.getvalue())
                
                st.download_button(
                    label="📦 Descargar Kit (Fotos+Prompt)",
                    data=zip_buffer.getvalue(),
                    file_name=f"kit_{res.get('mueble_name', 'generado')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    type="primary"
                )
        with btn_col2:
            if st.button("🗑️ Limpiar Todo", key="btn_clear_studio", use_container_width=True):
                for k in ["last_studio_result_v2", "st_mueble_v2", "st_tela_v2", "st_madera_v2", "sb_tela_oficial_v2", "sb_madera_oficial_v2"]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

    lista_telas = cargar_telas_menu_v2()
    map_telas = {t["name"].upper(): t for t in lista_telas}
    opciones_telas = [""] + [t["name"] for t in lista_telas]

    lista_maderas = cargar_maderas_menu_v2()
    map_maderas = {m["name"].upper(): m for m in lista_maderas}
    opciones_maderas = [""] + [m["name"] for m in lista_maderas]

    col1, col2, col3 = st.columns([1.25, 0.7, 1.45])

    tela_bytes = None
    tela_name = ""
    madera_bytes = None
    madera_name = ""

    with col1:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">🎯 1. Configuración V2</div>', unsafe_allow_html=True)

        modo_sel = st.radio(
            "Selecciona el tipo de trabajo:",
            ["Solo Tela", "Solo Madera", "Tela + Madera", "Extraer Mueble (Fondo Blanco)", "Aumento HD", "Vistas (360)"],
            horizontal=True,
            label_visibility="collapsed",
            key="studio_mode_radio_v2"
        )

        fondo_blanco = st.toggle("⬜ Extraer Mueble (Fondo Blanco)", value=True, help="Le ordena a la IA extraer el mueble, preservando color, textura y geometría, colocándolo sobre blanco puro sin sombras ni reflejos.")

        st.markdown("---")
        st.markdown("##### 🛋️ Foto del Mueble Original")
        mueble_up = st.file_uploader(
            "Sube foto(s) del mueble",
            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
            key="st_mueble_v2",
            accept_multiple_files=True
        )

        if modo_sel in ["Solo Tela", "Tela + Madera"]:
            st.markdown("##### 🧵 2. Muestra de Tela")
            tipo_origen_tela = st.radio("Fuente:", ["📂 Menú Oficial", "📤 Subir Foto"], horizontal=True, key="rad_tipo_tela_v2")
            if tipo_origen_tela == "📂 Menú Oficial":
                sel_t_nombre = st.selectbox("Elige tela:", opciones_telas, key="sb_tela_oficial_v2")
                if sel_t_nombre:
                    obj_t = map_telas.get(sel_t_nombre.upper())
                    if obj_t and obj_t.get("id"):
                        tela_name = sel_t_nombre
                        tela_bytes = sheets_service.get_drive_file_bytes(obj_t["id"])
            else:
                tela_up = st.file_uploader("Sube muestra de tela", type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'], key="st_tela_v2")
                if tela_up:
                    tela_name = tela_up.name
                    tela_bytes = tela_up.getvalue()
        elif modo_sel == "Vistas (360)":
            st.markdown("##### 🧵 2. Muestra de Tela (Opcional)")
            st.caption("💡 Opcional: Si no seleccionas tela, se generarán las 5 vistas conservando el material original del mueble.")
            tipo_origen_tela = st.radio("Fuente:", ["Ninguna (Mantener original)", "📂 Menú Oficial", "📤 Subir Foto"], horizontal=True, key="rad_tipo_tela_v2_opt")
            if tipo_origen_tela == "📂 Menú Oficial":
                sel_t_nombre = st.selectbox("Elige tela:", opciones_telas, key="sb_tela_oficial_v2")
                if sel_t_nombre:
                    obj_t = map_telas.get(sel_t_nombre.upper())
                    if obj_t and obj_t.get("id"):
                        tela_name = sel_t_nombre
                        tela_bytes = sheets_service.get_drive_file_bytes(obj_t["id"])
            elif tipo_origen_tela == "📤 Subir Foto":
                tela_up = st.file_uploader("Sube muestra de tela (opcional)", type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'], key="st_tela_v2")
                if tela_up:
                    tela_name = tela_up.name
                    tela_bytes = tela_up.getvalue()

        if modo_sel in ["Solo Madera", "Tela + Madera"]:
            st.markdown("##### 🪵 Muestra de Madera")
            tipo_origen_mad = st.radio("Fuente:", ["📂 Menú Oficial", "📤 Subir Foto"], horizontal=True, key="rad_tipo_mad_v2")
            if tipo_origen_mad == "📂 Menú Oficial":
                sel_m_nombre = st.selectbox("Elige madera:", opciones_maderas, key="sb_madera_oficial_v2")
                if sel_m_nombre:
                    obj_m = map_maderas.get(sel_m_nombre.upper())
                    if obj_m:
                        madera_name = sel_m_nombre
                        if obj_m.get("local_path") and os.path.exists(obj_m["local_path"]):
                            madera_bytes = Path(obj_m["local_path"]).read_bytes()
                        elif obj_m.get("id"):
                            madera_bytes = sheets_service.get_drive_file_bytes(obj_m["id"])
            else:
                madera_up = st.file_uploader("Sube muestra de madera", type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'], key="st_madera_v2")
                if madera_up:
                    madera_name = madera_up.name
                    madera_bytes = madera_up.getvalue()

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("⚡ GENERAR PROMPT V2 (STRUCTURED)", type="primary", use_container_width=True, key="btn_gen_prompts_v2"):
            if not mueble_up:
                st.error("⚠️ Sube la foto del mueble primero.")
            elif modo_sel == "Solo Tela" and not tela_bytes:
                st.error("⚠️ Selecciona una tela.")
            elif modo_sel == "Solo Madera" and not madera_bytes:
                st.error("⚠️ Selecciona una madera.")
            elif modo_sel == "Tela + Madera" and (not tela_bytes or not madera_bytes):
                st.error("⚠️ Requiere muestra de tela y madera.")
            else:
                with st.spinner("Ejecutando Structured Outputs con Gemini..."):
                    m_bytes = [f.getvalue() for f in mueble_up]
                    m_name = ", ".join([f.name for f in mueble_up])
                    num_imgs = len(mueble_up)
                    vistas_data = []

                    f_ana = ai_prompt_service_v2.analyze_material(tela_bytes, material_type="fabric") if tela_bytes else None
                    w_ana = ai_prompt_service_v2.analyze_material(madera_bytes, material_type="wood") if madera_bytes else None
                    m_ana = ai_prompt_service_v2.analyze_furniture_for_enhancement(m_bytes)

                    if modo_sel == "Aumento HD":
                        prompts = ai_prompt_service_v2.generate_enhance_prompt(furniture_name=m_name, analysis=m_ana)
                    elif modo_sel == "Vistas (360)":
                        prompts_vistas = ai_prompt_service_v2.generate_multi_perspective_prompts(
                            mode="fabric_only", furniture_name=m_name, fabric_analysis=f_ana, wood_analysis=w_ana, furniture_analysis=m_ana, num_furniture_images=num_imgs, fondo_blanco=fondo_blanco
                        )
                        vistas_nombres = [
                            ("vista_de_frente", "vista de frente"),
                            ("vista_lateral_derecha", "vista lateral (derecha)"),
                            ("vista_lateral_izquierda", "vista lateral (izquierda)"),
                            ("vista_3_4_izquierda", "vista 3/4 mirando a la izquierda"),
                            ("vista_3_4_derecha", "vista 3/4 mirando a la derecha"),
                            ("vista_desde_arriba", "vista desde arriba"),
                            ("vista_3_4_posterior", "vista 3/4 posterior"),
                            ("vista_detalle_macro", "vista detalle macro"),
                            ("vista_lifestyle_ambientado", "vista lifestyle (ambientado)")
                        ]
                        for key_v, label_v in vistas_nombres:
                            vistas_data.append({
                                "name": label_v,
                                "bytes": None,
                                "prompt": prompts_vistas[key_v]
                            })

                        def build_all(ai_key):
                            return (
                                "=== 1. VISTA DE FRENTE ===\n" + prompts_vistas["vista_de_frente"][ai_key] + "\n\n" +
                                "=== 2. VISTA LATERAL ===\n" + prompts_vistas["vista_lateral_derecha"][ai_key] + "\n\n" +
                                "=== 3. VISTA 3/4 MIRANDO ALA IZQUIERDA ===\n" + prompts_vistas["vista_3_4_izquierda"][ai_key] + "\n\n" +
                                "=== 4. VISTA DESDE ARRIBA ===\n" + prompts_vistas["vista_desde_arriba"][ai_key] + "\n\n" +
                                "=== 5. VISTA 3/4 POSTERIOR ===\n" + prompts_vistas["vista_3_4_posterior"][ai_key]
                            )
                        prompts = {
                            "google_ai_studio": build_all("google_ai_studio"),
                            "midjourney_v6": build_all("flux_midjourney"),
                            "chatgpt_dalle3": build_all("chatgpt_dalle3")
                        }
                    else:
                        mode_key = "fabric_only" if modo_sel == "Solo Tela" else ("wood_only" if modo_sel == "Solo Madera" else "dual")
                        prompts = ai_prompt_service_v2.generate_material_swap_prompt_v2(
                            mode=mode_key,
                            furniture_name=m_name,
                            fabric_analysis=f_ana,
                            wood_analysis=w_ana,
                            furniture_analysis=m_ana,
                            num_furniture_images=num_imgs,
                            fondo_blanco=fondo_blanco
                        )
                    
                    st.session_state["last_studio_result_v2"] = {
                        "vistas_data": vistas_data,
                        "modo": modo_sel,
                        "mueble_name": m_name,
                        "fabric_analysis": f_ana,
                        "wood_analysis": w_ana,
                        "furniture_analysis": m_ana,
                        "prompts": prompts
                    }

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">📦 Elementos Cargados</div>', unsafe_allow_html=True)
        if mueble_up:
            for f in mueble_up:
                try:
                    f_name = getattr(f, "name", None) or (f.get("name") if isinstance(f, dict) else "Mueble")
                    if isinstance(f, dict) and "bytes" in f:
                        f_bytes = f["bytes"]
                    elif hasattr(f, "getvalue"):
                        f_bytes = f.getvalue()
                    elif hasattr(f, "read"):
                        f_bytes = f.read()
                    else:
                        f_bytes = f
                    st.image(f_bytes, caption=f"Mueble: {f_name}", use_container_width=True)
                except Exception:
                    st.caption(f"🖼️ Mueble cargado")

        if tela_bytes:
            try:
                st.image(tela_bytes, caption=f"Muestra Tela: {tela_name}", use_container_width=True)
            except Exception:
                st.caption(f"🧵 Tela: {tela_name}")

        if madera_bytes:
            try:
                st.image(madera_bytes, caption=f"Muestra Madera: {madera_name}", use_container_width=True)
            except Exception:
                st.caption(f"🪵 Madera: {madera_name}")
        
        if "last_studio_result_v2" in st.session_state:
            res = st.session_state["last_studio_result_v2"]
            st.markdown("---")
            st.markdown("##### 🔬 Análisis Estructurado (Pydantic)")
            if res.get("fabric_analysis"):
                fa = res["fabric_analysis"]
                st.markdown(f"<span class='meta-pill'>🏷️ {fa.get('name', '')}</span>", unsafe_allow_html=True)
                st.markdown(f"<span class='meta-pill'>🎨 {fa.get('color_description', '')}</span>", unsafe_allow_html=True)
            if res.get("wood_analysis"):
                wa = res["wood_analysis"]
                st.markdown(f"<span class='meta-pill'>🪵 {wa.get('name', '')}</span>", unsafe_allow_html=True)
                st.markdown(f"<span class='meta-pill'>✨ {wa.get('finish_type', '')}</span>", unsafe_allow_html=True)
            if res.get("furniture_analysis"):
                ma = res["furniture_analysis"]
                st.markdown(f"<span class='meta-pill'>📐 {ma.get('geometric_structure', '')}</span>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">⚡ Prompts V2 <span class="studio-badge">Específicos</span></div>', unsafe_allow_html=True)
        if "last_studio_result_v2" in st.session_state:
            res = st.session_state["last_studio_result_v2"]
            p_tabs = st.tabs(["🌟 Google AI Studio / Gemini Pro", "🤖 ChatGPT (DALL-E 3)", "⚡ Flux / Midjourney", "🎨 Render Gratis (FLUX.1)", "🕵️ Inspector de Calidad"])

            with p_tabs[0]:
                if res.get("vistas_data"):
                    st.caption(f"💡 Se generaron {len(res['vistas_data'])} vistas individuales. Copia la que necesites:")
                    for i, vd in enumerate(res["vistas_data"]):
                        st.markdown(f"##### {vd['name']}")
                        st.text_area(f"Prompt Google AI Studio ({vd['name']}):", value=vd["prompt"]["google_ai_studio"], height=130, key=f"g_v2_{i}")
                        st.code(vd["prompt"]["google_ai_studio"], language="markdown")
                        st.markdown("---")
                else:
                    p_google = res["prompts"]["google_ai_studio"]
                    st.text_area("Copia en Google AI Studio (Imagen 3) o Gemini Advanced:", value=p_google, height=300, key="txt_res_g_v2")
                    st.code(p_google, language="markdown")
                    st.download_button("💾 Descargar .txt", data=p_google, file_name=f"prompt_ai_studio_{res['mueble_name']}.txt", use_container_width=True)

            with p_tabs[1]:
                if res.get("vistas_data"):
                    st.caption(f"💡 Se generaron {len(res['vistas_data'])} vistas individuales para DALL-E 3:")
                    for i, vd in enumerate(res["vistas_data"]):
                        st.markdown(f"##### {vd['name']}")
                        st.text_area(f"Prompt DALL-E 3 ({vd['name']}):", value=vd["prompt"]["chatgpt_dalle3"], height=130, key=f"d_v2_{i}")
                        st.code(vd["prompt"]["chatgpt_dalle3"], language="markdown")
                        st.markdown("---")
                else:
                    p_dalle = res["prompts"]["chatgpt_dalle3"]
                    st.text_area("Copia en ChatGPT (DALL-E 3):", value=p_dalle, height=300, key="txt_res_d_v2")
                    st.code(p_dalle, language="markdown")
                    st.download_button("💾 Descargar .txt", data=p_dalle, file_name=f"prompt_dalle3_{res['mueble_name']}.txt", use_container_width=True)

            with p_tabs[2]:
                if res.get("vistas_data"):
                    st.caption(f"💡 Se generaron {len(res['vistas_data'])} vistas individuales para Midjourney:")
                    for i, vd in enumerate(res["vistas_data"]):
                        st.markdown(f"##### {vd['name']}")
                        p_flux_val = vd["prompt"].get("flux_midjourney") or vd["prompt"].get("midjourney_v6", "")
                        st.text_area(f"Prompt Midjourney ({vd['name']}):", value=p_flux_val, height=130, key=f"m_v2_{i}")
                        st.code(p_flux_val, language="markdown")
                        st.markdown("---")
                else:
                    p_flux = res["prompts"]["midjourney_v6"]
                    st.text_area("Copia en Midjourney (Discord):", value=p_flux, height=300, key="txt_res_f_v2")
                    st.code(p_flux, language="markdown")
                    st.download_button("💾 Descargar .txt", data=p_flux, file_name=f"prompt_mj_{res['mueble_name']}.txt", use_container_width=True)

            with p_tabs[3]:
                from services.free_image_service import free_image_service
                st.markdown("##### ⚡ Generador In-App V2 (FLUX.1)")
                
                if res.get("vistas_data"):
                    nombres_v2 = [vd["name"] for vd in res["vistas_data"]]
                    sel_v2_idx = st.selectbox("🎯 Elige la Vista a Renderizar:", range(len(nombres_v2)), format_func=lambda i: nombres_v2[i], key="sb_vista_render_v2")
                    vd_sel2 = res["vistas_data"][sel_v2_idx]
                    prompt_para_render = vd_sel2["prompt"].get("google_ai_studio") or vd_sel2["prompt"].get("chatgpt_dalle3", "")
                else:
                    prompt_para_render = res["prompts"].get("midjourney_v6") or res["prompts"].get("google_ai_studio") or res["prompts"].get("chatgpt_dalle3", "")
                
                col_gen_btn, col_gen_asp = st.columns([2, 1])
                with col_gen_asp:
                    formato_sel = st.selectbox("Resolución:", ["Rápido (512x512)", "Estándar (768x768)", "HD (1024x768)"], key="sel_asp_v2")
                    w_r, h_r = (512, 512) if "512" in formato_sel else ((768, 768) if "768" in formato_sel else (1024, 768))
                
                with col_gen_btn:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    btn_gen = st.button("🚀 Generar Render Ahora", type="primary", use_container_width=True, key="btn_flux_v2")
                
                if btn_gen:
                    with st.spinner("🎨 Renderizando mueble con difusión..."):
                        try:
                            img_render = free_image_service.generate_flux_image(
                                prompt=prompt_para_render,
                                width=w_r,
                                height=h_r
                            )
                            st.session_state["render_generado_v2"] = img_render
                            st.success("✅ ¡Render generado con éxito!")
                        except Exception as err:
                            st.error(f"⚠️ {err}")
                
                if "render_generado_v2" in st.session_state:
                    import re
                    raw_p2 = res.get('furniture_analysis', {}).get('furniture_item') if isinstance(res.get('furniture_analysis'), dict) else res.get('mueble_name', 'Mueble')
                    clean_prod2 = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(raw_p2).strip())[:35] or "Mueble"
                    vista_label2 = nombres_v2[sel_v2_idx] if (res.get("vistas_data") and 'sel_v2_idx' in locals()) else "render"
                    clean_v2 = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(vista_label2).strip())[:30]
                    download_name2 = f"{clean_prod2}_{clean_v2}.jpg"
                    
                    st.image(st.session_state["render_generado_v2"], caption=f"Render IA: {clean_prod2} ({vista_label2})", use_container_width=True)
                    st.download_button(
                        label=f"💾 Descargar {download_name2}",
                        data=st.session_state["render_generado_v2"],
                        file_name=download_name2,
                        mime="image/jpeg",
                        use_container_width=True
                    )

            with p_tabs[4]:
                from services.quality_inspector_service import quality_inspector_service
                st.markdown("##### 🕵️ Inspector de Calidad Automático (Quality Gate IA)")
                orig_mueble_ref2 = mueble_up[0].getvalue() if mueble_up and len(mueble_up) > 0 else None
                render_to_audit2 = st.session_state.get("render_generado_v2")
                
                audit_up2 = st.file_uploader("O sube un render/imagen externa:", type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'], key="up_audit_v2")
                if audit_up2:
                    render_to_audit2 = audit_up2.getvalue()
                    
                if not orig_mueble_ref2:
                    st.warning("⚠️ Sube la foto original del mueble.")
                elif not render_to_audit2:
                    st.info("💡 Genera un render en la pestaña '🎨 Render Gratis' o sube una imagen.")
                else:
                    if st.button("🔍 Auditar Calidad con IA", type="primary", use_container_width=True, key="btn_run_inspector_v2"):
                        with st.spinner("🕵️ Auditando calidad industrial..."):
                            q_res = quality_inspector_service.inspect_quality(
                                original_mueble_bytes=orig_mueble_ref2,
                                generated_render_bytes=render_to_audit2,
                                material_sample_bytes=tela_bytes
                            )
                            st.session_state["last_quality_check_v2"] = q_res
                    if "last_quality_check_v2" in st.session_state:
                        qc = st.session_state["last_quality_check_v2"]
                        st.markdown(f"### Score: {qc.get('score_total', 0)}/100 — {qc.get('verdict', '')}")
                        st.progress(qc.get("score_total", 0) / 100.0)
                        if qc.get("prompt_correction_patch"):
                            st.text_area("Corrección sugerida:", qc["prompt_correction_patch"], height=80, key="txt_qc_v2")
                            st.code(qc["prompt_correction_patch"], language="markdown")
        else:
            st.info("Configura y genera para ver los prompts optimizados.")
        st.markdown('</div>', unsafe_allow_html=True)

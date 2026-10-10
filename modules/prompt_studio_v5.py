import os
import io
import zipfile
from pathlib import Path
import streamlit as st

FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"

@st.cache_data(ttl=300)
def cargar_telas_menu_v5():
    from services.sheets_service import sheets_service
    return sheets_service.get_drive_folder_files(FOLDER_TELAS_DRIVE_ID, recursive=True)

@st.cache_data(ttl=300)
def cargar_maderas_menu_v5():
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

def render_copy_button(text: str, label: str = "📋 Copiar Prompt", key: str = "cp_v5"):
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

def render_prompt_studio_v5():
    if "clear_key_v5" not in st.session_state:
        st.session_state.clear_key_v5 = 0
    from services.ai_prompt_service_v5 import ai_prompt_service_v5
    from services.sheets_service import sheets_service

    st.markdown("""
<style>
.studio-top-bar { background-color: #283548; border: 1px solid #475569; border-radius: 10px; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.studio-badge-v5 { background: rgba(168, 85, 247, 0.2); color: #C084FC; border: 1px solid rgba(168, 85, 247, 0.4); font-size: 11px; padding: 3px 8px; border-radius: 9999px; font-weight: 700; }
.studio-card { background-color: #283548; border: 1px solid #475569; border-radius: 12px; padding: 18px; height: 100%; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
.studio-card-title { font-size: 15px; font-weight: 700; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; }
/* Forzar subida exclusivamente arrastrando archivos */
[data-testid="stFileUploader"] button { display: none !important; }
[data-testid="stFileUploaderDropzoneInstructions"] > div:last-child { display: none !important; }
</style>
""", unsafe_allow_html=True)

    c_head_left, c_head_right = st.columns([2, 2])

    with c_head_left:
        st.markdown("""
<div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
    <span style="font-size:22px; font-weight:800; color:#A855F7;">⚡ Estudio V5 (1 Solo Prompt - 5 Vistas)</span>
    <span class="studio-badge-v5">Nano Banana 2.1 & Pro</span>
</div>
        """, unsafe_allow_html=True)
        col_comp_btn, col_comp_info = st.columns([1, 2])
        with col_comp_btn:
            sys_prompt = (
                "Eres un Director de Arte de talla mundial, experto en Fotografía de Producto Comercial, "
                "Diseño de Interiores y Renderizado Arquitectónico Hiperrealista (CGI). "
                "Tu objetivo es conceptualizar escenas visuales impecables para catálogos de muebles de lujo. "
                "Dominas a la perfección la composición fotográfica, iluminación de estudio (softboxes, luz natural, HDR), "
                "materialidad (vetas de madera, tramado de telas premium) y atmósferas minimalistas o cálidas. "
                "Tu estilo es hiperrealista, fotográfico, elegante, de resolución 8k y renderizado fotorrealista."
            )
            render_copy_button(sys_prompt, label="Comportamiento", key="cp_comp_v5")
        with col_comp_info:
            st.info("⚙️ Configuración (AI Studio): Modelo: Nano Banana 2.1 / Nano Banana Pro | Output: Text/Image | Thinking: High | Temp: 0.0")

    with c_head_right:
        col_dl, col_clr = st.columns([1, 1])
        with col_dl:
            if "last_studio_result_v5" in st.session_state:
                res = st.session_state["last_studio_result_v5"]
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    prompts_dict = res.get("prompts", {})
                    # Master prompt
                    prompt_txt = prompts_dict.get("google_ai_studio", "") or prompts_dict.get("chatgpt_dalle3", "")
                    if prompt_txt:
                        zip_file.writestr(f"00_prompt_maestro_5_vistas.txt", prompt_txt)
                    
                    # Individual views
                    ind_vistas = prompts_dict.get("individual_vistas", [])
                    for idx, iv in enumerate(ind_vistas, start=1):
                        v_content = f"--- PROMPT GOOGLE AI STUDIO (FOTO INDIVIDUAL) ---\n{iv.get('google_ai_studio', '')}\n\n--- PROMPT CHATGPT / DALL-E 3 (FOTO INDIVIDUAL) ---\n{iv.get('chatgpt_dalle3', '')}"
                        zip_file.writestr(f"0{idx}_{iv.get('id', f'vista_{idx}')}.txt", v_content)

                st.download_button(
                    label="📦 Descargar Kit (5 Vistas)",
                    data=zip_buffer.getvalue(),
                    file_name=f"kit_5_vistas_{res.get('mueble_name', 'mueble')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="btn_dl_kit_v5"
                )
        with col_clr:
            if st.button("🗑️ Limpiar Todo", key="btn_clear_studio_v5", use_container_width=True):
                keys_to_del = [k for k in list(st.session_state.keys()) if k.startswith("last_studio_result") or k.startswith("st_") or k.startswith("sb_") or k.startswith("txt_")]
                for k in keys_to_del:
                    del st.session_state[k]
                st.session_state.clear_key_v5 = st.session_state.get("clear_key_v5", 0) + 1
                st.rerun()

    # Carga de catálogos conectados
    lista_telas = cargar_telas_menu_v5()
    map_telas = {t["name"].upper(): t for t in lista_telas}
    opciones_telas = [""] + [t["name"] for t in lista_telas]

    lista_maderas = cargar_maderas_menu_v5()
    map_maderas = {m["name"].upper(): m for m in lista_maderas}
    opciones_maderas = [""] + [m["name"] for m in lista_maderas]

    col1, col2, col3 = st.columns([1.25, 0.7, 1.45])

    tela_bytes = None
    tela_name = ""
    madera_bytes = None
    madera_name = ""

    with col1:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">🎯 1. Configuración de Vistas de Catálogo</div>', unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background:rgba(168,85,247,0.12); border:1px solid rgba(168,85,247,0.3); border-radius:8px; padding:10px 12px; margin-bottom:14px; font-size:12px; color:#E9D5FF; line-height:1.5;">
            <b>🎯 Vistas (1.1):</b> 5 vistas (3/4 Derecha, Lateral 90°, Frente 0°, 3/4 Picada Alta, Cenital 90°).<br>
            <b>⚡ Vistas (2.1):</b> 4 vistas de catálogo (Frontal 0°, 3/4 Perspectiva, Lateral 90°, Superior Cenital).
        </div>
        """, unsafe_allow_html=True)

        st.markdown("##### 🛋️ Foto(s) del Mueble Original (Arrastrar)")
        st.caption("📷 Puedes arrastrar **más de 1 foto** (frente, costado, detalles); Gemini las analiza todas juntas.")
        mueble_up = st.file_uploader(
            "Arrastra una o varias fotos del mueble original aquí:",
            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
            key=f"st_mueble_v5_{st.session_state.clear_key_v5}",
            accept_multiple_files=True
        )

        st.markdown("---")
        st.markdown("##### 💬 Notas / Directivas Especiales para la IA")
        st.caption("✨ Las notas que escribas aquí se integran **directamente dentro del prompt** como especificaciones obligatorias de materiales, iluminación y acabados.")
        notas_usuario = st.text_area(
            "Indica especificaciones clave (ej. Mantener las costuras beige, patas de roble claro, luz LED cálida integrada):",
            placeholder="Escribe aquí tus observaciones y ajustes para que la IA los integre en el prompt...",
            key=f"txt_notas_usuario_v5_{st.session_state.clear_key_v5}",
            height=90
        )

        st.markdown("<br>", unsafe_allow_html=True)

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            btn_1_1 = st.button("🎯 Vistas (1.1)", type="primary", use_container_width=True, key=f"btn_gen_11_{st.session_state.clear_key_v5}")
        with col_b2:
            btn_2_1 = st.button("⚡ Vistas (2.1)", type="primary", use_container_width=True, key=f"btn_gen_21_{st.session_state.clear_key_v5}")

        if btn_1_1 or btn_2_1:
            if not mueble_up:
                st.error("⚠️ Por favor arrastra al menos una fotografía del mueble original.")
            else:
                progress_holder = st.empty()
                modo_nombre = "Vistas (2.1)" if btn_2_1 else "Vistas (1.1)"
                progress_holder.info(f"⏳ Analizando foto(s) con Gemini Vision y generando {modo_nombre}...")
                try:
                    m_bytes_list = []
                    if isinstance(mueble_up, list):
                        for f in mueble_up:
                            m_bytes_list.append(f.getvalue() if hasattr(f, "getvalue") else f.read())
                        m_name = getattr(mueble_up[0], "name", "Mueble").split(".")[0]
                    else:
                        m_bytes_list.append(mueble_up.getvalue() if hasattr(mueble_up, "getvalue") else mueble_up.read())
                        m_name = getattr(mueble_up, "name", "Mueble").split(".")[0]

                    m_ana = ai_prompt_service_v5.analyze_furniture_for_enhancement(m_bytes_list)

                    if btn_2_1:
                        prompts = ai_prompt_service_v5.generate_vistas_2_1_prompts(
                            furniture_name=m_name,
                            furniture_analysis=m_ana,
                            notas_usuario=notas_usuario
                        )
                    else:
                        prompts = ai_prompt_service_v5.generate_vistas_1_1_prompts(
                            furniture_name=m_name,
                            furniture_analysis=m_ana,
                            notas_usuario=notas_usuario
                        )

                    st.session_state["last_studio_result_v5"] = {
                        "modo": modo_nombre,
                        "mueble_name": m_name,
                        "furniture_analysis": m_ana,
                        "prompts": prompts,
                        "notas_usuario": notas_usuario
                    }
                    progress_holder.success(f"✅ ¡Prompts para {modo_nombre} generados exitosamente!")
                except Exception as e:
                    progress_holder.error(f"❌ Error al procesar: {str(e)}")

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">📦 Elementos Cargados</div>', unsafe_allow_html=True)
        if mueble_up:
            for f in mueble_up:
                try:
                    f_name = getattr(f, "name", None) or (f.get("name") if isinstance(f, dict) else "Mueble")
                    if hasattr(f, "getvalue"):
                        f_bytes = f.getvalue()
                    elif hasattr(f, "read"):
                        f_bytes = f.read()
                    else:
                        f_bytes = f
                    st.image(f_bytes, caption=f"Mueble: {f_name}", use_container_width=True)
                except Exception:
                    st.caption("🖼️ Mueble cargado")

        if tela_bytes:
            st.image(tela_bytes, caption=f"Tela: {tela_name or 'Seleccionada'}", use_container_width=True)

        if madera_bytes:
            st.image(madera_bytes, caption=f"Madera: {madera_name or 'Seleccionada'}", use_container_width=True)

        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        modo_actual = st.session_state.get("last_studio_result_v5", {}).get("modo", "Vistas")
        st.markdown(f'<div class="studio-card-title">✨ 3. Prompts de {modo_actual}</div>', unsafe_allow_html=True)

        if "last_studio_result_v5" in st.session_state:
            res = st.session_state["last_studio_result_v5"]
            prompts = res.get("prompts", {})
            ind_vistas = prompts.get("individual_vistas", [])
            num_vistas = len(ind_vistas)

            # Modo de visualización: 1 Solo Prompt Maestro vs Vistas Individuales
            tipo_salida = st.radio(
                "Elige el formato de prompt que prefieres:",
                [f"⚡ 1 Solo Prompt Maestro (Ordena a la IA generar las {num_vistas} fotos por separado)", f"📸 Prompts Individuales ({num_vistas} pestañas separadas)"],
                horizontal=True,
                key=f"rb_tipo_salida_v5_{st.session_state.clear_key_v5}"
            )

            if "1 Solo Prompt Maestro" in tipo_salida:
                st.markdown(f"""
                <div style="background:rgba(168,85,247,0.15); border:1px solid #A855F7; border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:12px; color:#E9D5FF;">
                    🔥 <b>1 Solo Prompt Maestro para {modo_actual}:</b><br>
                    Instruye a Google AI Studio o ChatGPT a generar <b>todas las {num_vistas} fotos por separado</b> de forma secuencial en una sola orden.
                </div>
                """, unsafe_allow_html=True)

                p_tab1, p_tab2, p_tab3 = st.tabs(["🌐 Google AI Studio / Gemini", "🤖 ChatGPT (DALL-E 3)", "🎨 Midjourney v6.1"])
                with p_tab1:
                    p_txt = prompts.get("google_ai_studio", "")
                    st.text_area("Prompt Google AI Studio (Nano Banana 2.1 & Pro):", p_txt, height=260, key=f"txt_res_ais_v5_{st.session_state.clear_key_v5}")
                    render_copy_button(p_txt, label="📋 Copiar Prompt Maestro para Google AI Studio", key=f"cp_res_ais_v5_{st.session_state.clear_key_v5}")
                with p_tab2:
                    p_dalle = prompts.get("chatgpt_dalle3", "")
                    st.text_area("Prompt ChatGPT / DALL-E 3 (Fotos Separadas):", p_dalle, height=240, key=f"txt_res_dal_v5_{st.session_state.clear_key_v5}")
                    render_copy_button(p_dalle, label="📋 Copiar Prompt Maestro para ChatGPT", key=f"cp_res_dal_v5_{st.session_state.clear_key_v5}")
                with p_tab3:
                    p_mj = prompts.get("midjourney_v6", "")
                    st.text_area("Prompt Midjourney v6.1:", p_mj, height=220, key=f"txt_res_mj_v5_{st.session_state.clear_key_v5}")
                    render_copy_button(p_mj, label="📋 Copiar Prompt para Midjourney", key=f"cp_res_mj_v5_{st.session_state.clear_key_v5}")

            else:
                st.markdown("""
                <div style="background:rgba(16,185,129,0.15); border:1px solid #10B981; border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:12px; color:#A7F3D0;">
                    ✅ <b>Prompts 100% Individuales:</b> Genera 1 sola foto individual por cada vista a máxima resolución.
                </div>
                """, unsafe_allow_html=True)

                if ind_vistas:
                    vista_tabs = st.tabs([f"{v['icon']} {v['label'].split(':')[0]}" for v in ind_vistas])
                    for i, (tab, v_data) in enumerate(zip(vista_tabs, ind_vistas)):
                        with tab:
                            st.markdown(f"##### {v_data['icon']} {v_data['label']}")
                            engine_tabs = st.tabs(["🌐 Google AI Studio / Gemini", "🤖 ChatGPT (DALL-E 3)"])
                            with engine_tabs[0]:
                                p_ais = v_data.get("google_ai_studio", "")
                                st.text_area(f"Prompt AI Studio ({v_data['label']}):", p_ais, height=220, key=f"txt_ind_ais_{i}_{st.session_state.clear_key_v5}")
                                render_copy_button(p_ais, label=f"📋 Copiar Prompt para Google AI Studio", key=f"cp_ind_ais_{i}_{st.session_state.clear_key_v5}")
                            with engine_tabs[1]:
                                p_dal = v_data.get("chatgpt_dalle3", "")
                                st.text_area(f"Prompt ChatGPT / DALL-E 3 ({v_data['label']}):", p_dal, height=200, key=f"txt_ind_dal_{i}_{st.session_state.clear_key_v5}")
                                render_copy_button(p_dal, label=f"📋 Copiar Prompt para ChatGPT", key=f"cp_ind_dal_{i}_{st.session_state.clear_key_v5}")

            # Metadatos del análisis de visión
            fa = res.get("fabric_analysis")
            wa = res.get("wood_analysis")
            ma = res.get("furniture_analysis")
            if fa or wa or ma:
                with st.expander("🔍 Ver Análisis Detallado de Visión", expanded=False):
                    if ma:
                        st.markdown(f"**🛋️ Mueble:** `{ma.get('furniture_item', 'N/A')}`")
                        st.markdown(f"**📐 Ángulo Detectado:** `{ma.get('camera_angle', 'N/A')}`")
                        st.markdown(f"**🧱 Materiales Originales:** `{ma.get('existing_materials', 'N/A')}`")
                    if fa:
                        st.markdown(f"**🧵 Tela:** `{fa.get('name', 'N/A')}` | `{fa.get('color_description', 'N/A')}`")
                    if wa:
                        st.markdown(f"**🪵 Madera:** `{wa.get('name', 'N/A')}` | `{wa.get('color_description', 'N/A')}`")
        else:
            st.info("👈 Arrastra la(s) foto(s) de tu mueble a la izquierda y presiona **🎯 Vistas (1.1)** o **⚡ Vistas (2.1)**.")

        st.markdown('</div>', unsafe_allow_html=True)

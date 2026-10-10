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
                    prompt_txt = res["prompts"].get("google_ai_studio", "") or res["prompts"].get("chatgpt_dalle3", "")
                    if prompt_txt:
                        zip_file.writestr(f"prompt_v5_5vistas_{res.get('mueble_name', 'generado')}.txt", prompt_txt)
                st.download_button(
                    label="📦 Descargar Kit",
                    data=zip_buffer.getvalue(),
                    file_name=f"kit_v5_{res.get('mueble_name', 'prompt')}.zip",
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
        st.markdown('<div class="studio-card-title">🎯 1. Configuración de Materiales y Vistas</div>', unsafe_allow_html=True)

        modo_sel = st.radio(
            "Selecciona el tipo de trabajo:",
            ["Tela + Madera (5 Vistas)", "Solo Tela (5 Vistas)", "Solo Madera (5 Vistas)", "Solo Mueble Original (5 Vistas)"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"studio_mode_radio_v5_{st.session_state.clear_key_v5}"
        )

        st.markdown("---")
        st.markdown("##### 🛋️ Foto del Mueble Original (Arrastrar)")
        mueble_up = st.file_uploader(
            "Arrastra la foto del mueble original aquí:",
            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
            key=f"st_mueble_v5_{st.session_state.clear_key_v5}",
            accept_multiple_files=True
        )

        if modo_sel in ["Tela + Madera (5 Vistas)", "Solo Tela (5 Vistas)"]:
            st.markdown(f"""
            <div style="background:#1E293B; border:1px solid #475569; border-radius:8px; padding:10px 12px; margin-top:10px; margin-bottom:6px;">
                <div style="font-weight:700; color:#38BDF8; font-size:13px; display:flex; justify-content:space-between; align-items:center;">
                    <span>🧵 Muestra de Tela</span>
                    <span style="font-size:11px; color:#94A3B8;">Catálogo ({len(lista_telas)} telas) o Arrastrar foto</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            sel_t_nombre = st.selectbox(
                f"Elegir del catálogo oficial ({len(lista_telas)} telas):",
                opciones_telas,
                key=f"sb_tela_oficial_v5_{st.session_state.clear_key_v5}"
            )
            tela_up = st.file_uploader(
                "O arrastra tu foto de tela personalizada aquí:",
                type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
                key=f"st_tela_v5_{st.session_state.clear_key_v5}"
            )
            if tela_up:
                tela_name = tela_up.name
                tela_bytes = tela_up.getvalue()
                st.markdown(f"<div style='background:rgba(16,185,129,0.15); border:1px solid #10B981; border-radius:6px; padding:5px 10px; font-size:12px; color:#34D399; margin-top:-4px; margin-bottom:8px;'>✅ <b>Foto personalizada activa:</b> {tela_up.name}</div>", unsafe_allow_html=True)
            elif sel_t_nombre:
                obj_t = map_telas.get(sel_t_nombre.upper())
                if obj_t and obj_t.get("id"):
                    tela_name = sel_t_nombre
                    tela_bytes = sheets_service.get_drive_file_bytes(obj_t["id"])
                    st.markdown(f"<div style='background:rgba(56,189,248,0.15); border:1px solid #38BDF8; border-radius:6px; padding:5px 10px; font-size:12px; color:#38BDF8; margin-top:-4px; margin-bottom:8px;'>✅ <b>Tela de catálogo activa:</b> {sel_t_nombre}</div>", unsafe_allow_html=True)

        if modo_sel in ["Tela + Madera (5 Vistas)", "Solo Madera (5 Vistas)"]:
            st.markdown(f"""
            <div style="background:#1E293B; border:1px solid #475569; border-radius:8px; padding:10px 12px; margin-top:10px; margin-bottom:6px;">
                <div style="font-weight:700; color:#F59E0B; font-size:13px; display:flex; justify-content:space-between; align-items:center;">
                    <span>🪵 Muestra de Madera</span>
                    <span style="font-size:11px; color:#94A3B8;">Catálogo ({len(lista_maderas)} maderas) o Arrastrar foto</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            sel_m_nombre = st.selectbox(
                f"Elegir del catálogo oficial ({len(lista_maderas)} maderas):",
                opciones_maderas,
                key=f"sb_madera_oficial_v5_{st.session_state.clear_key_v5}"
            )
            madera_up = st.file_uploader(
                "O arrastra tu foto de madera personalizada aquí:",
                type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
                key=f"st_madera_v5_{st.session_state.clear_key_v5}"
            )
            if madera_up:
                madera_name = madera_up.name
                madera_bytes = madera_up.getvalue()
                st.markdown(f"<div style='background:rgba(16,185,129,0.15); border:1px solid #10B981; border-radius:6px; padding:5px 10px; font-size:12px; color:#34D399; margin-top:-4px; margin-bottom:8px;'>✅ <b>Foto personalizada activa:</b> {madera_up.name}</div>", unsafe_allow_html=True)
            elif sel_m_nombre:
                obj_m = map_maderas.get(sel_m_nombre.upper())
                if obj_m:
                    madera_name = sel_m_nombre
                    if obj_m.get("local_path") and os.path.exists(obj_m["local_path"]):
                        madera_bytes = Path(obj_m["local_path"]).read_bytes()
                    elif obj_m.get("id"):
                        madera_bytes = sheets_service.get_drive_file_bytes(obj_m["id"])
                    st.markdown(f"<div style='background:rgba(245,158,11,0.15); border:1px solid #F59E0B; border-radius:6px; padding:5px 10px; font-size:12px; color:#FCD34D; margin-top:-4px; margin-bottom:8px;'>✅ <b>Madera de catálogo activa:</b> {sel_m_nombre}</div>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("##### 💬 Comentarios y Directivas Especiales para la IA")
        st.caption("✨ Las notas que escribas aquí se integrarán como instrucciones de alta prioridad en el prompt.")
        notas_usuario = st.text_area(
            "Indica especificaciones clave (ej. Mantener las costuras en tono beige, patas cónicas de roble claro, cojines esponjosos):",
            placeholder="Escribe aquí tus observaciones para que la IA las tome en cuenta con máxima prioridad...",
            key=f"txt_notas_usuario_v5_{st.session_state.clear_key_v5}",
            height=90
        )

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("⚡ GENERAR PROMPT UNIFICADO (5 VISTAS)", type="primary", use_container_width=True, key="btn_gen_prompts_v5"):
            if not mueble_up:
                st.error("⚠️ Por favor arrastra al menos una fotografía del mueble original.")
            else:
                progress_holder = st.empty()
                progress_holder.info("⏳ Analizando imágenes con Gemini Vision y generando Prompt Maestro...")
                try:
                    m_file = mueble_up[0] if isinstance(mueble_up, list) else mueble_up
                    m_name = getattr(m_file, "name", "Mueble").split(".")[0]
                    m_bytes = m_file.getvalue() if hasattr(m_file, "getvalue") else m_file.read()

                    f_ana = None
                    if tela_bytes:
                        f_ana = ai_prompt_service_v5.analyze_material(tela_bytes, material_type="fabric")
                    
                    w_ana = None
                    if madera_bytes:
                        w_ana = ai_prompt_service_v5.analyze_material(madera_bytes, material_type="wood")

                    m_ana = ai_prompt_service_v5.analyze_furniture_for_enhancement(m_bytes)

                    # Determinar modo interno para el generador
                    if modo_sel == "Tela + Madera (5 Vistas)":
                        internal_mode = "dual"
                    elif modo_sel == "Solo Tela (5 Vistas)":
                        internal_mode = "fabric_only"
                    elif modo_sel == "Solo Madera (5 Vistas)":
                        internal_mode = "wood_only"
                    else:
                        internal_mode = "solo_mueble"

                    prompts = ai_prompt_service_v5.generate_all_in_one_multi_view_prompt(
                        mode=internal_mode,
                        furniture_name=m_name,
                        fabric_analysis=f_ana,
                        wood_analysis=w_ana,
                        furniture_analysis=m_ana,
                        notas_usuario=notas_usuario
                    )

                    st.session_state["last_studio_result_v5"] = {
                        "modo": modo_sel,
                        "mueble_name": m_name,
                        "fabric_analysis": f_ana,
                        "wood_analysis": w_ana,
                        "furniture_analysis": m_ana,
                        "prompts": prompts,
                        "notas_usuario": notas_usuario
                    }
                    progress_holder.success("✅ ¡Prompt Maestro de 5 Vistas generado exitosamente!")
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
        st.markdown('<div class="studio-card-title">✨ 3. Prompt Maestro de 5 Vistas</div>', unsafe_allow_html=True)

        if "last_studio_result_v5" in st.session_state:
            res = st.session_state["last_studio_result_v5"]
            prompts = res.get("prompts", {})

            st.markdown("""
            <div style="background:rgba(168,85,247,0.15); border:1px solid #A855F7; border-radius:8px; padding:10px 14px; margin-bottom:12px; font-size:12px; color:#E9D5FF;">
                🔥 <b>1 Solo Prompt para las 5 Vistas:</b><br>
                1. 3/4 mirando a la derecha | 2. Lateral 90° | 3. De frente 0° | 4. 3/4 Picada alta desde arriba | 5. Cenital desde arriba 90°
            </div>
            """, unsafe_allow_html=True)

            p_tab1, p_tab2, p_tab3 = st.tabs(["🌐 Google AI Studio / Gemini", "🤖 ChatGPT (DALL-E 3)", "🎨 Midjourney v6.1"])
            with p_tab1:
                p_txt = prompts.get("google_ai_studio", "")
                st.text_area("Prompt Google AI Studio (Nano Banana 2.1 & Pro):", p_txt, height=260, key="txt_res_ais_v5")
                render_copy_button(p_txt, label="📋 Copiar Prompt para Google AI Studio", key="cp_res_ais_v5")
            with p_tab2:
                p_dalle = prompts.get("chatgpt_dalle3", "")
                st.text_area("Prompt ChatGPT / DALL-E 3 (Multi-View Contact Sheet):", p_dalle, height=240, key="txt_res_dal_v5")
                render_copy_button(p_dalle, label="📋 Copiar Prompt para ChatGPT", key="cp_res_dal_v5")
            with p_tab3:
                p_mj = prompts.get("midjourney_v6", "")
                st.text_area("Prompt Midjourney v6.1:", p_mj, height=220, key="txt_res_mj_v5")
                render_copy_button(p_mj, label="📋 Copiar Prompt para Midjourney", key="cp_res_mj_v5")

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
            st.info("👈 Arrastra la foto de tu mueble a la izquierda y presiona **⚡ GENERAR PROMPT UNIFICADO** para obtener el prompt de las 5 vistas de un solo golpe.")

        st.markdown('</div>', unsafe_allow_html=True)

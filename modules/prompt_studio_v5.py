import os
import io
import zipfile
from pathlib import Path
import streamlit as st

def render_copy_button(text: str, label: str = "📋 Copiar Prompt", key: str = "cp_v5"):
    """Renderiza un botón que copia el texto al portapapeles nativamente en 1 clic de forma 100% blindada."""
    import base64
    import streamlit.components.v1 as components
    b64_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    html_code = f"""
    <div style="margin: 4px 0 8px 0;">
        <button id="btn_{key}" onclick="copy_{key}()" style="
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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        ">
            {label}
        </button>
    </div>
    <script>
    function copy_{key}() {{
        try {{
            const b64 = "{b64_text}";
            const raw = decodeURIComponent(escape(window.atob(b64)));
            if (navigator.clipboard && navigator.clipboard.writeText) {{
                navigator.clipboard.writeText(raw).then(function() {{
                    showCopied_{key}();
                }}).catch(function() {{
                    fallbackCopy_{key}(raw);
                }});
            }} else {{
                fallbackCopy_{key}(raw);
            }}
        }} catch (err) {{
            console.error("Error al copiar:", err);
        }}
    }}
    function fallbackCopy_{key}(textToCopy) {{
        const ta = document.createElement("textarea");
        ta.value = textToCopy;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        showCopied_{key}();
    }}
    function showCopied_{key}() {{
        const b = document.getElementById("btn_{key}");
        if (b) {{
            const orig = b.innerHTML;
            b.innerHTML = "✅ ¡Copiado!";
            b.style.backgroundColor = "#059669";
            setTimeout(function() {{
                b.innerHTML = orig;
                b.style.backgroundColor = "#2563EB";
            }}, 2000);
        }}
    }}
    </script>
    """
    components.html(html_code, height=44)

def render_preview_image(img_data, caption: str = ""):
    """Renderiza una imagen en Streamlit blindada con data URI en base64 para evitar errores 404 o caídas de caché."""
    import base64
    if not img_data:
        return
    try:
        raw_bytes = None
        if isinstance(img_data, dict) and "bytes" in img_data:
            raw_bytes = img_data["bytes"]
        elif hasattr(img_data, "getvalue"):
            raw_bytes = img_data.getvalue()
        elif hasattr(img_data, "read"):
            if hasattr(img_data, "seek"):
                img_data.seek(0)
            raw_bytes = img_data.read()
            if hasattr(img_data, "seek"):
                img_data.seek(0)
        elif isinstance(img_data, (bytes, bytearray)):
            raw_bytes = bytes(img_data)

        if raw_bytes and len(raw_bytes) > 0:
            b64 = base64.b64encode(raw_bytes).decode("utf-8")
            mime = "image/jpeg"
            if raw_bytes.startswith(b"\x89PNG"):
                mime = "image/png"
            elif raw_bytes.startswith(b"RIFF") and b"WEBP" in raw_bytes[:16]:
                mime = "image/webp"
            elif raw_bytes.startswith(b"GIF8"):
                mime = "image/gif"
            st.markdown(f'''
            <div style="text-align:center; margin-bottom:12px;">
                <img src="data:{mime};base64,{b64}" style="max-width:100%; border-radius:8px; border:1px solid #475569; box-shadow:0 4px 10px rgba(0,0,0,0.25);" />
                <div style="font-size:12px; color:#94A3B8; margin-top:4px;">{caption}</div>
            </div>
            ''', unsafe_allow_html=True)
            return
        
        st.image(img_data, caption=caption, use_container_width=True)
    except Exception:
        try:
            st.image(img_data, caption=caption, use_container_width=True)
        except Exception:
            st.caption(f"🖼️ {caption}")

def render_prompt_studio_v5():
    if "clear_key_v5" not in st.session_state:
        st.session_state.clear_key_v5 = 0
    from services.ai_prompt_service_v5 import ai_prompt_service_v5

    st.markdown("""
<style>
.studio-top-bar { background-color: #283548; border: 1px solid #475569; border-radius: 10px; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.studio-badge-v5 { background: rgba(168, 85, 247, 0.2); color: #C084FC; border: 1px solid rgba(168, 85, 247, 0.4); font-size: 11px; padding: 3px 8px; border-radius: 9999px; font-weight: 700; }
.studio-card { background-color: #283548; border: 1px solid #475569; border-radius: 12px; padding: 18px; height: 100%; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
.studio-card-title { font-size: 15px; font-weight: 700; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; }
.casilla-badge { display: inline-block; background: #3B82F6; color: white; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 700; margin-right: 6px; }
</style>
""", unsafe_allow_html=True)

    c_head_left, c_head_right = st.columns([2, 2])

    with c_head_left:
        st.markdown("""
<div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
    <span style="font-size:22px; font-weight:800; color:#A855F7;">⚡ Estudio V5 (Vistas 1.1 y 2.1 con Muestras de Madera)</span>
    <span class="studio-badge-v5">Nano Banana & ChatGPT Pro</span>
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
                    modo_res = res.get("modo", "Vistas")
                    safe_modo = modo_res.lower().replace(" ", "_").replace("(", "").replace(")", "")

                    # Master / Single prompt
                    ais_txt = prompts_dict.get("google_ai_studio", "")
                    dalle_txt = prompts_dict.get("chatgpt_dalle3", "")
                    mj_txt = prompts_dict.get("midjourney_v6", "")

                    if ais_txt or dalle_txt:
                        full_content = f"=== PROMPT GOOGLE AI STUDIO / GEMINI ===\n{ais_txt}\n\n=== PROMPT CHATGPT / DALL-E 3 ===\n{dalle_txt}\n\n=== PROMPT MIDJOURNEY ===\n{mj_txt}"
                        zip_file.writestr(f"00_prompt_{safe_modo}.txt", full_content)

                    # Individual views
                    ind_vistas = prompts_dict.get("individual_vistas", [])
                    for idx, iv in enumerate(ind_vistas, start=1):
                        v_content = f"--- PROMPT GOOGLE AI STUDIO (FOTO INDIVIDUAL) ---\n{iv.get('google_ai_studio', '')}\n\n--- PROMPT CHATGPT / DALL-E 3 (FOTO INDIVIDUAL) ---\n{iv.get('chatgpt_dalle3', '')}"
                        zip_file.writestr(f"0{idx}_{iv.get('id', f'vista_{idx}')}.txt", v_content)

                label_dl = "📦 Descargar Kit de Vistas" if ind_vistas else f"📦 Descargar Prompts"
                st.download_button(
                    label=label_dl,
                    data=zip_buffer.getvalue(),
                    file_name=f"prompts_{safe_modo}_{res.get('mueble_name', 'mueble')}.zip",
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

    col1, col2, col3 = st.columns([1.25, 0.7, 1.45])

    with col1:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">🎯 1. Configuración de Vistas y Materiales</div>', unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background:rgba(168,85,247,0.12); border:1px solid rgba(168,85,247,0.3); border-radius:8px; padding:10px 12px; margin-bottom:14px; font-size:12px; color:#E9D5FF; line-height:1.5;">
            <b>🎯 Vistas (1.1):</b> 5 vistas canónicas (3/4 Derecha, Lateral 90°, Frente 0°, 3/4 Picada Alta, Cenital 90°).<br>
            <b>⚡ Vistas (2.1):</b> 4 vistas de catálogo (Frontal 0°, 3/4 Perspectiva, Lateral 90°, Superior Cenital).
        </div>
        """, unsafe_allow_html=True)

        # CASILLA 1: Foto(s) Actual(es) del Mueble
        st.markdown("##### 📸 Casilla 1: Foto(s) del Mueble (Modelo y Proporciones)")
        mueble_actual_up = st.file_uploader(
            "Arrastra aquí la foto o fotos del mueble:",
            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
            key=f"st_mueble_actual_v5_{st.session_state.clear_key_v5}",
            accept_multiple_files=True,
            help="Foto tomada del mueble real (puedes subir 1 o más fotos)."
        )

        st.markdown("---")

        # CASILLA 2: Foto(s) de Muestra de Madera / Color / Acabado
        st.markdown("##### 🪵 Casilla 2: Foto(s) de Madera, Color o Acabado (Muestra Real)")
        mueble_madera_up = st.file_uploader(
            "Arrastra aquí la foto de la madera o muestras de color:",
            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
            key=f"st_mueble_madera_v5_{st.session_state.clear_key_v5}",
            accept_multiple_files=True,
            help="Foto de la madera real o muestras de textura y color (puedes subir 1 o más fotos)."
        )

        st.markdown("---")

        # CASILLA 3: Fotos de Referencia del Mueble (Otros ángulos y Vistas 360°)
        st.markdown("##### 📐 Casilla 3: Fotos de Referencia (Otros Ángulos y Vistas 360°)")
        mueble_ref_up = st.file_uploader(
            "Arrastra aquí las fotos de referencia de ángulos y vistas:",
            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
            key=f"st_mueble_ref_v5_{st.session_state.clear_key_v5}",
            accept_multiple_files=True,
            help="Fotos de referencia del diseño, otros ángulos o planos del mueble."
        )

        st.markdown("---")

        # CASILLA 4: Notas e instrucciones obligatorias
        st.markdown("##### 📝 Casilla 4: Notas / Directivas Obligatorias para la IA")
        notas_usuario = st.text_area(
            "Escribe tus notas obligatorias para la IA:",
            placeholder="Ej: Madera de roble claro acabado mate sedoso, respetar proporciones exactas, sin gavetas oscuras de dos tonos...",
            key=f"txt_notas_usuario_v5_{st.session_state.clear_key_v5}",
            height=85
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # BOTONERA: Vistas (1.1), Vistas (2.1), Extraer Mueble, Mejora HD
        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            btn_1_1 = st.button("🎯 Vistas (1.1)", type="primary", use_container_width=True, key=f"btn_gen_11_{st.session_state.clear_key_v5}")
        with col_b2:
            btn_2_1 = st.button("⚡ Vistas (2.1)", type="primary", use_container_width=True, key=f"btn_gen_21_{st.session_state.clear_key_v5}")

        col_b3, col_b4 = st.columns([1, 1])
        with col_b3:
            btn_extraer = st.button("⬜ Extraer Mueble", use_container_width=True, key=f"btn_gen_ext_{st.session_state.clear_key_v5}")
        with col_b4:
            btn_hd = st.button("✨ Mejora HD", use_container_width=True, key=f"btn_gen_hd_{st.session_state.clear_key_v5}")

        if btn_1_1 or btn_2_1 or btn_extraer or btn_hd:
            if not mueble_actual_up and not mueble_madera_up and not mueble_ref_up:
                st.error("⚠️ Por favor sube al menos una fotografía (mueble, muestra de madera o referencias).")
            else:
                progress_holder = st.empty()
                if btn_extraer:
                    modo_nombre = "Extraer Mueble (Fondo Blanco)"
                elif btn_hd:
                    modo_nombre = "Mejora HD"
                elif btn_2_1:
                    modo_nombre = "Vistas (2.1)"
                else:
                    modo_nombre = "Vistas (1.1)"
                progress_holder.info(f"⏳ Analizando fotos del mueble, muestras de madera y referencias con Gemini Vision para generar {modo_nombre}...")
                try:
                    # Bytes y nombres de archivos de fotos del mueble (Casilla 1)
                    m_actual_bytes = []
                    m_actual_filenames = []
                    m_name = "Mueble"
                    if mueble_actual_up:
                        actual_list = mueble_actual_up if isinstance(mueble_actual_up, list) else [mueble_actual_up]
                        for f in actual_list:
                            m_actual_bytes.append(f.getvalue() if hasattr(f, "getvalue") else f.read())
                            m_actual_filenames.append(getattr(f, "name", "Mueble"))
                        m_name = getattr(actual_list[0], "name", "Mueble").split(".")[0]

                    # Bytes y nombres de fotos de muestra de madera / color (Casilla 2)
                    m_madera_bytes = []
                    m_madera_filenames = []
                    if mueble_madera_up:
                        madera_list = mueble_madera_up if isinstance(mueble_madera_up, list) else [mueble_madera_up]
                        for f in madera_list:
                            m_madera_bytes.append(f.getvalue() if hasattr(f, "getvalue") else f.read())
                            m_madera_filenames.append(getattr(f, "name", "Madera"))

                    # Bytes y nombres de fotos de referencia (Casilla 3)
                    m_ref_bytes = []
                    m_ref_filenames = []
                    if mueble_ref_up:
                        ref_list = mueble_ref_up if isinstance(mueble_ref_up, list) else [mueble_ref_up]
                        for f in ref_list:
                            m_ref_bytes.append(f.getvalue() if hasattr(f, "getvalue") else f.read())
                            m_ref_filenames.append(getattr(f, "name", "Referencia"))
                        if not m_actual_bytes:
                            m_name = getattr(ref_list[0], "name", "Mueble").split(".")[0]

                    # Análisis integral con Gemini
                    m_ana = ai_prompt_service_v5.analyze_furniture_for_enhancement(
                        furniture_bytes=m_actual_bytes or m_ref_bytes or m_madera_bytes,
                        reference_bytes=m_ref_bytes,
                        wood_bytes=m_madera_bytes,
                        notas_usuario=notas_usuario
                    )

                    w_ana = None
                    if m_madera_bytes:
                        progress_holder.info("🪵 Analizando muestra de madera con Gemini Vision...")
                        w_ana = ai_prompt_service_v5.analyze_material(m_madera_bytes[0], material_type="wood")

                    if btn_extraer:
                        prompts = ai_prompt_service_v5.generate_extraction_prompts(
                            furniture_name=m_name,
                            furniture_analysis=m_ana,
                            notas_usuario=notas_usuario
                        )
                    elif btn_hd:
                        prompts = ai_prompt_service_v5.generate_hd_enhancement_prompts(
                            furniture_name=m_name,
                            furniture_analysis=m_ana,
                            notas_usuario=notas_usuario
                        )
                    elif btn_2_1:
                        prompts = ai_prompt_service_v5.generate_vistas_2_1_prompts(
                            furniture_name=m_name,
                            furniture_analysis=m_ana,
                            fabric_analysis=None,
                            wood_analysis=w_ana,
                            notas_usuario=notas_usuario,
                            furniture_filenames=m_actual_filenames,
                            wood_filenames=m_madera_filenames,
                            reference_filenames=m_ref_filenames
                        )
                    else:
                        prompts = ai_prompt_service_v5.generate_vistas_1_1_prompts(
                            furniture_name=m_name,
                            furniture_analysis=m_ana,
                            fabric_analysis=None,
                            wood_analysis=w_ana,
                            notas_usuario=notas_usuario,
                            furniture_filenames=m_actual_filenames,
                            wood_filenames=m_madera_filenames,
                            reference_filenames=m_ref_filenames
                        )

                    st.session_state["last_studio_result_v5"] = {
                        "modo": modo_nombre,
                        "mueble_name": m_name,
                        "furniture_analysis": m_ana,
                        "fabric_analysis": None,
                        "wood_analysis": w_ana,
                        "prompts": prompts,
                        "notas_usuario": notas_usuario,
                        "has_actual": bool(mueble_actual_up),
                        "has_madera": bool(mueble_madera_up),
                        "has_ref": bool(mueble_ref_up)
                    }
                    progress_holder.success(f"✅ ¡Prompts para {modo_nombre} generados exitosamente!")
                except Exception as e:
                    progress_holder.error(f"❌ Error al procesar: {str(e)}")

        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">📦 Elementos Cargados</div>', unsafe_allow_html=True)
        
        # Miniaturas de Casilla 1: Fotos del Mueble
        if mueble_actual_up:
            st.markdown("<b>📸 Foto(s) del Mueble (Casilla 1):</b>", unsafe_allow_html=True)
            for f in (mueble_actual_up if isinstance(mueble_actual_up, list) else [mueble_actual_up]):
                f_name = getattr(f, "name", "Foto Mueble")
                render_preview_image(f, caption=f"Mueble: {f_name}")

        # Miniaturas de Casilla 2: Muestra de Madera / Color
        if mueble_madera_up:
            st.markdown("<b>🪵 Muestra de Madera / Color (Casilla 2):</b>", unsafe_allow_html=True)
            for f in (mueble_madera_up if isinstance(mueble_madera_up, list) else [mueble_madera_up]):
                f_name = getattr(f, "name", "Muestra Madera")
                render_preview_image(f, caption=f"Madera/Color: {f_name}")

        # Miniaturas de Casilla 3: Fotos de Referencia
        if mueble_ref_up:
            st.markdown("<b>📐 Fotos de Referencia (Casilla 3):</b>", unsafe_allow_html=True)
            for f in (mueble_ref_up if isinstance(mueble_ref_up, list) else [mueble_ref_up]):
                f_name = getattr(f, "name", "Referencia")
                render_preview_image(f, caption=f"Ref: {f_name}")

        # Notas registradas (Casilla 4)
        if notas_usuario and notas_usuario.strip():
            st.markdown("<b>📝 Notas Registradas (Casilla 4):</b>", unsafe_allow_html=True)
            st.info(notas_usuario.strip())

        if not mueble_actual_up and not mueble_madera_up and not mueble_ref_up and not (notas_usuario and notas_usuario.strip()):
            st.caption("Esperando carga de fotos o notas en la columna izquierda...")

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

            if ind_vistas:
                # Selector de formato
                tipo_salida = st.radio(
                    "Formato de salida:",
                    [f"⚡ 1 Solo Prompt Maestro (Secuencial con 'foto')", f"📸 Vistas Individuales ({num_vistas} tarjetas con copia 1x1)"],
                    horizontal=True,
                    key=f"rb_tipo_salida_v5_{st.session_state.clear_key_v5}"
                )

                if "1 Solo Prompt Maestro" in tipo_salida:
                    p_tab1, p_tab2, p_tab3 = st.tabs(["🌐 Google AI Studio (Nano Banana)", "🤖 ChatGPT (DALL-E 3)", "🎨 Midjourney v6.1 (Discord)"])
                    with p_tab1:
                        st.markdown("""
                        <div style="background: rgba(16, 185, 129, 0.15); border-left: 4px solid #10B981; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                            <strong style="color: #10B981; font-size: 14px;">🌐 PROMPT PARA GOOGLE AI STUDIO (Nano Banana / Gemini 2.0 / Imagen 3)</strong><br>
                            <span style="color: #E2E8F0; font-size: 12px;">✅ Pega este prompt en Google AI Studio junto a tus fotos. Te dará la Foto 1; luego escribe la palabra <b>foto</b> en el chat para la siguiente vista.</span>
                        </div>
                        """, unsafe_allow_html=True)
                        p_txt = prompts.get("google_ai_studio", "")
                        st.text_area("Prompt Maestro Interactivo (Google AI Studio):", p_txt, height=270, key=f"txt_res_ais_v5_{st.session_state.clear_key_v5}")
                        render_copy_button(p_txt, label="📋 Copiar Prompt Maestro para Google AI Studio (Secuencial)", key=f"cp_res_ais_v5_{st.session_state.clear_key_v5}")
                    with p_tab2:
                        st.markdown("""
                        <div style="background: rgba(59, 130, 246, 0.15); border-left: 4px solid #3B82F6; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                            <strong style="color: #3B82F6; font-size: 14px;">🤖 PROMPT PARA CHATGPT (DALL-E 3)</strong><br>
                            <span style="color: #E2E8F0; font-size: 12px;">✅ Pega este prompt en ChatGPT. Generará todas las vistas secuenciales manteniendo la madera idéntica y congelada.</span>
                        </div>
                        """, unsafe_allow_html=True)
                        p_dalle = prompts.get("chatgpt_dalle3", "")
                        st.text_area("Prompt Maestro ChatGPT (Genera todas las fotos):", p_dalle, height=250, key=f"txt_res_dal_v5_{st.session_state.clear_key_v5}")
                        render_copy_button(p_dalle, label="📋 Copiar Prompt Maestro para ChatGPT (Todas las fotos)", key=f"cp_res_dal_v5_{st.session_state.clear_key_v5}")
                    with p_tab3:
                        st.markdown("""
                        <div style="background: rgba(245, 158, 11, 0.15); border-left: 4px solid #F59E0B; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                            <strong style="color: #F59E0B; font-size: 14px;">🎨 PROMPT EXCLUSIVO PARA MIDJOURNEY v6.1</strong><br>
                            <span style="color: #F87171; font-weight: bold; font-size: 12px;">⚠️ NO PEGAR EN GOOGLE AI STUDIO NI EN CHATGPT:</span> <span style="color: #E2E8F0; font-size: 12px;">Este prompt contiene parámetros como <code>--ar 16:9 --v 6.1</code> que solo funcionan dentro de Discord / Midjourney.</span>
                        </div>
                        """, unsafe_allow_html=True)
                        p_mj = prompts.get("midjourney_v6", "")
                        st.text_area("Prompt Midjourney v6.1:", p_mj, height=220, key=f"txt_res_mj_v5_{st.session_state.clear_key_v5}")
                        render_copy_button(p_mj, label="📋 Copiar Prompt para Midjourney", key=f"cp_res_mj_v5_{st.session_state.clear_key_v5}")

                else:
                    if ind_vistas:
                        vista_tabs = st.tabs([f"{v['icon']} {v.get('short_name', v['label'].split(':')[0])}" for v in ind_vistas])
                        for i, (tab, v_data) in enumerate(zip(vista_tabs, ind_vistas)):
                            with tab:
                                st.markdown(f"##### {v_data['icon']} {v_data['label']}")
                                engine_tabs = st.tabs(["🌐 Google AI Studio / Gemini", "🤖 ChatGPT (DALL-E 3)"])
                                with engine_tabs[0]:
                                    st.markdown("""
                                    <div style="background: rgba(16, 185, 129, 0.15); border-left: 4px solid #10B981; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;">
                                        <strong style="color: #10B981; font-size: 13px;">🌐 Google AI Studio:</strong> <span style="color: #E2E8F0; font-size: 12px;">Copia y pega individualmente para esta vista exacta.</span>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    p_ais = v_data.get("google_ai_studio", "")
                                    st.text_area(f"Prompt AI Studio ({v_data['label']}):", p_ais, height=220, key=f"txt_ind_ais_{i}_{st.session_state.clear_key_v5}")
                                    render_copy_button(p_ais, label=f"📋 Copiar {v_data.get('short_name', 'Vista')} para Google AI Studio", key=f"cp_ind_ais_{i}_{st.session_state.clear_key_v5}")
                                with engine_tabs[1]:
                                    st.markdown("""
                                    <div style="background: rgba(59, 130, 246, 0.15); border-left: 4px solid #3B82F6; padding: 8px 12px; border-radius: 6px; margin-bottom: 8px;">
                                        <strong style="color: #3B82F6; font-size: 13px;">🤖 ChatGPT (DALL-E 3):</strong> <span style="color: #E2E8F0; font-size: 12px;">Copia y pega individualmente para esta vista exacta.</span>
                                    </div>
                                    """, unsafe_allow_html=True)
                                    p_dal = v_data.get("chatgpt_dalle3", "")
                                    st.text_area(f"Prompt ChatGPT / DALL-E 3 ({v_data['label']}):", p_dal, height=200, key=f"txt_ind_dal_{i}_{st.session_state.clear_key_v5}")
                                    render_copy_button(p_dal, label=f"📋 Copiar {v_data.get('short_name', 'Vista')} para ChatGPT", key=f"cp_ind_dal_{i}_{st.session_state.clear_key_v5}")
            else:
                p_tab1, p_tab2, p_tab3 = st.tabs(["🌐 Google AI Studio / Gemini", "🤖 ChatGPT (DALL-E 3)", "🎨 Midjourney v6.1 (Discord)"])
                with p_tab1:
                    st.markdown("""
                    <div style="background: rgba(16, 185, 129, 0.15); border-left: 4px solid #10B981; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                        <strong style="color: #10B981; font-size: 14px;">🌐 PROMPT PARA GOOGLE AI STUDIO (Gemini / Imagen 3)</strong>
                    </div>
                    """, unsafe_allow_html=True)
                    p_txt = prompts.get("google_ai_studio", "")
                    st.text_area("Prompt Google AI Studio:", p_txt, height=270, key=f"txt_res_ais_single_{st.session_state.clear_key_v5}")
                    render_copy_button(p_txt, label="📋 Copiar Prompt para Google AI Studio", key=f"cp_res_ais_single_{st.session_state.clear_key_v5}")
                with p_tab2:
                    st.markdown("""
                    <div style="background: rgba(59, 130, 246, 0.15); border-left: 4px solid #3B82F6; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                        <strong style="color: #3B82F6; font-size: 14px;">🤖 PROMPT PARA CHATGPT (DALL-E 3)</strong>
                    </div>
                    """, unsafe_allow_html=True)
                    p_dalle = prompts.get("chatgpt_dalle3", "")
                    st.text_area("Prompt ChatGPT / DALL-E 3:", p_dalle, height=250, key=f"txt_res_dal_single_{st.session_state.clear_key_v5}")
                    render_copy_button(p_dalle, label="📋 Copiar Prompt para ChatGPT", key=f"cp_res_dal_single_{st.session_state.clear_key_v5}")
                with p_tab3:
                    st.markdown("""
                    <div style="background: rgba(245, 158, 11, 0.15); border-left: 4px solid #F59E0B; padding: 10px 14px; border-radius: 6px; margin-bottom: 10px;">
                        <strong style="color: #F59E0B; font-size: 14px;">🎨 PROMPT EXCLUSIVO PARA MIDJOURNEY v6.1</strong><br>
                        <span style="color: #F87171; font-weight: bold; font-size: 12px;">⚠️ NO PEGAR EN GOOGLE AI STUDIO NI EN CHATGPT:</span> <span style="color: #E2E8F0; font-size: 12px;">Solo funciona en Discord / Midjourney.</span>
                    </div>
                    """, unsafe_allow_html=True)
                    p_mj = prompts.get("midjourney_v6", "")
                    st.text_area("Prompt Midjourney v6.1:", p_mj, height=220, key=f"txt_res_mj_single_{st.session_state.clear_key_v5}")
                    render_copy_button(p_mj, label="📋 Copiar Prompt para Midjourney", key=f"cp_res_mj_single_{st.session_state.clear_key_v5}")

            # Metadatos del análisis de visión
            ma = res.get("furniture_analysis")
            if ma:
                with st.expander("🔍 Ver Análisis Detallado de Geometría y Materiales", expanded=False):
                    st.markdown(f"**🛋️ Mueble Identificado:** `{ma.get('furniture_item', 'N/A')}`")
                    st.markdown(f"**📐 Ángulo Detectado:** `{ma.get('camera_angle', 'N/A')}`")
                    st.markdown(f"**🧱 Materiales y Color:** `{ma.get('existing_materials', 'N/A')}`")
                    st.markdown(f"**🏗️ Topología 3D:** `{ma.get('geometric_structure', 'N/A')}`")
        else:
            st.info("👈 Sube la foto del mueble en la **Casilla 1**, la muestra de madera/color en la **Casilla 2**, referencias en la **Casilla 3**, notas en la **Casilla 4** y presiona **🎯 Vistas (1.1)** o **⚡ Vistas (2.1)**.")

        st.markdown('</div>', unsafe_allow_html=True)

    # SECCIÓN: SEPARADOR AUTOMÁTICO DE VISTAS (DIVIDE TIRAS DE CATÁLOGO EN FOTOS SEPARADAS)
    st.markdown("<br>", unsafe_allow_html=True)
    with st.container():
        st.markdown("""
        <div style="background-color: #283548; border: 1px solid #475569; border-radius: 12px; padding: 18px 20px; margin-bottom: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
            <div style="font-size: 16px; font-weight: 800; color: #38BDF8; margin-bottom: 6px; display: flex; align-items: center; gap: 8px;">
                <span>✂️ Separador Automático de Vistas (Corta tu tira de catálogo en fotos 100% separadas)</span>
            </div>
            <div style="font-size: 13px; color: #CBD5E1; line-height: 1.5;">
                💡 <b>La Solución Definitiva a la Inconsistencia de Betas, Color y Tamaño:</b><br>
                Cuando generas las vistas en <b>1 sola imagen panorámica de catálogo</b>, la IA congela el mueble y te da la <b>misma veta, el mismo color y las mismas medidas exactas</b>. Arrastra esa imagen aquí abajo para que la App la recorte automáticamente en fotos individuales en alta resolución con fondo blanco puro y las descargue en ZIP.
            </div>
        </div>
        """, unsafe_allow_html=True)

        c_spl1, c_spl2 = st.columns([1.2, 2.8])
        with c_spl1:
            strip_up = st.file_uploader(
                "Arrastra aquí tu tira o cuadrícula de vistas generada:",
                type=['png', 'jpg', 'jpeg', 'webp'],
                key=f"st_strip_splitter_{st.session_state.clear_key_v5}"
            )
        
        with c_spl2:
            if strip_up:
                from services.image_splitter_service import split_catalog_strip, create_zip_from_cropped
                crops = split_catalog_strip(strip_up.getvalue())
                if crops:
                    st.success(f"✅ ¡Detectadas y recortadas exitosamente **{len(crops)} vistas individuales**!")
                    
                    # Botón para descargar el ZIP completo
                    zip_data = create_zip_from_cropped(crops, base_name=strip_up.name.split('.')[0])
                    st.download_button(
                        label=f"📦 Descargar Todas las Vistas ({len(crops)} fotos) en ZIP",
                        data=zip_data,
                        file_name=f"vistas_separadas_{strip_up.name.split('.')[0]}.zip",
                        mime="application/zip",
                        key="btn_dl_all_crops_zip"
                    )
                    
                    # Mostrar cuadrícula de fotos separadas
                    cols_crops = st.columns(min(len(crops), 5))
                    for idx, c in enumerate(crops):
                        col_idx = idx % len(cols_crops)
                        with cols_crops[col_idx]:
                            st.image(c["bytes"], caption=f"Vista {c['index']}", use_container_width=True)
                            st.download_button(
                                label=f"⬇️ Vista {c['index']}",
                                data=c["bytes"],
                                file_name=f"vista_{c['index']}_{strip_up.name.split('.')[0]}.png",
                                mime="image/png",
                                key=f"btn_dl_crop_{idx}"
                            )
                else:
                    st.warning("⚠️ No se detectaron objetos aislados con suficiente separación sobre fondo blanco en esta imagen.")
            else:
                st.info("👈 Arrastra una imagen panorámica de catálogo para recortar cada ángulo automáticamente en alta resolución.")

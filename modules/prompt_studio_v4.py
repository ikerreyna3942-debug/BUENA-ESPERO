import os
import io
import zipfile
from pathlib import Path
import streamlit as st

FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"
FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"

@st.cache_data(ttl=300)
def cargar_telas_menu_v4():
    from services.sheets_service import sheets_service
    return sheets_service.get_drive_folder_files(FOLDER_TELAS_DRIVE_ID, recursive=True)

@st.cache_data(ttl=300)
def cargar_maderas_menu_v4():
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

def render_copy_button(text: str, label: str = "📋 Copiar Prompt", key: str = "cp"):
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

def render_prompt_studio_v4():
    if "clear_key_v4" not in st.session_state:
        st.session_state.clear_key_v4 = 0
    from services.ai_prompt_service_v4 import ai_prompt_service_v4
    from services.sheets_service import sheets_service

    st.markdown("""
<style>
.studio-top-bar { background-color: #283548; border: 1px solid #475569; border-radius: 10px; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.studio-badge { background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.4); font-size: 11px; padding: 3px 8px; border-radius: 9999px; font-weight: 700; }
.studio-card { background-color: #283548; border: 1px solid #475569; border-radius: 12px; padding: 18px; height: 100%; box-shadow: 0 4px 15px rgba(0,0,0,0.2); }
.studio-card-title { font-size: 15px; font-weight: 700; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 8px; }
.protection-badge { background: rgba(16, 185, 129, 0.2); border: 1px solid rgba(16, 185, 129, 0.4); color: #34D399; border-radius: 8px; padding: 10px 14px; font-size: 12px; font-weight: 600; text-align: center; margin-top: 14px; }
.meta-pill { display: inline-block; background: #1E293B; border: 1px solid #475569; color: #38BDF8; font-size: 11px; padding: 4px 10px; border-radius: 6px; margin: 2px; }
</style>
""", unsafe_allow_html=True)

    c_head_left, c_head_right = st.columns([2, 2])

    with c_head_left:
        st.markdown("""
<div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
    <span style="font-size:22px; font-weight:800; color:#F59E0B;">⚡ Estudio V4 (Ultra-Precisión)</span>
    <span class="studio-badge">Fidelidad Cromática 100%</span>
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
            render_copy_button(sys_prompt, label="Comportamiento", key="cp_comp_v4")
        with col_comp_info:
            st.info("⚙️ Configuración (AI Studio): Modelo: Nano Banana Pro | Output format: Text | Thinking level: High | Output length: 8192 | Temperatura: 0.0 | Top-P: 0.95")

    with c_head_right:
        col_dl, col_clr = st.columns(2)
        with col_dl:
            if "last_studio_result_v4" in st.session_state:
                res = st.session_state["last_studio_result_v4"]
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    prompt_txt = res["prompts"].get("google_ai_studio", "") or res["prompts"].get("chatgpt_dalle3", "")
                    if prompt_txt:
                        zip_file.writestr(f"prompt_{res.get('mueble_name', 'generado')}.txt", prompt_txt)
                st.download_button(
                    label="📦 Descargar Kit",
                    data=zip_buffer.getvalue(),
                    file_name=f"kit_v4_{res.get('mueble_name', 'prompt')}.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key="btn_dl_kit_v4"
                )
        with col_clr:
            if st.button("🗑️ Limpiar Todo", key="btn_clear_studio_v4", use_container_width=True):
                c = st.session_state.get("clear_key_v4", 0)
                st.session_state.clear()
                st.session_state["clear_key_v4"] = c + 1
                st.rerun()

    # Carga de catálogos conectados
    lista_telas = cargar_telas_menu_v4()
    map_telas = {t["name"].upper(): t for t in lista_telas}
    opciones_telas = [""] + [t["name"] for t in lista_telas]

    lista_maderas = cargar_maderas_menu_v4()
    map_maderas = {m["name"].upper(): m for m in lista_maderas}
    opciones_maderas = [""] + [m["name"] for m in lista_maderas]

    col1, col2, col3 = st.columns([1.25, 0.7, 1.45])

    tela_bytes = None
    tela_name = ""
    madera_bytes = None
    madera_name = ""

    with col1:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">🎯 1. ¿Qué deseas hacer?</div>', unsafe_allow_html=True)

        modo_sel = st.radio(
            "Selecciona el tipo de trabajo:",
            ["Solo Tela", "Solo Madera", "Tela + Madera", "Solo mueble", "Vistas", "Vistas + Tela y Madera", "Vistas + Tela", "Entorno"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"studio_mode_radio_v4_{st.session_state.clear_key_v4}"
        )

        st.markdown("---")
        st.markdown("##### 🛋️ Foto del Mueble Original")
        mueble_up = st.file_uploader(
            "Arrastra la(s) foto(s) del mueble aquí",
            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
            key=f"st_mueble_v4_{st.session_state.clear_key_v4}",
            accept_multiple_files=True
        )

        tipo_mueble_usuario = ""
        medidas_usuario = ""
        lugar_casa_usuario = ""
        
        if modo_sel == "Entorno":
            st.markdown("##### 📍 Contexto del Entorno")
            tipo_mueble_usuario = st.text_input("Tipo de mueble (ej. Silla de comedor, Sofá modular, Cama king):", key=f"txt_tipo_mueble_v4_{st.session_state.clear_key_v4}")
            medidas_usuario = st.text_input("Medidas estimadas (ej. 220cm largo x 95cm fondo):", key=f"txt_medidas_v4_{st.session_state.clear_key_v4}")
            lugar_casa_usuario = st.text_input("Lugar / Habitación (ej. Sala de estar contemporánea, Comedor principal):", key=f"txt_lugar_casa_v4_{st.session_state.clear_key_v4}")

        if modo_sel == "Vistas + Tela y Madera":
            st.markdown("##### 📸 Vistas Adicionales del Mueble")
            vistas_up = st.file_uploader(
                "Arrastra las fotos de las vistas a estandarizar",
                type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
                key=f"st_vistas_v4_{st.session_state.clear_key_v4}",
                accept_multiple_files=True
            )
            tela_bytes = None
            madera_bytes = None

        elif modo_sel in ["Solo Tela", "Tela + Madera", "Vistas + Tela", "Entorno"]:
            st.markdown("##### 🧵 Muestra de Tela (Opcional para Entorno)")
            tab_t1, tab_t2 = st.tabs([f"📂 Menú Catálogo ({len(lista_telas)} telas)", "📤 Arrastrar / Subir Foto"])
            with tab_t1:
                sel_t_nombre = st.selectbox("Elige tela del catálogo:", opciones_telas, key=f"sb_tela_oficial_v4_{st.session_state.clear_key_v4}")
                if sel_t_nombre:
                    obj_t = map_telas.get(sel_t_nombre.upper())
                    if obj_t and obj_t.get("id"):
                        tela_name = sel_t_nombre
                        tela_bytes = sheets_service.get_drive_file_bytes(obj_t["id"])
            with tab_t2:
                tela_up = st.file_uploader(
                    "Arrastra aquí la foto de la muestra de tela",
                    type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
                    key=f"st_tela_v4_{st.session_state.clear_key_v4}"
                )
                if tela_up:
                    tela_name = tela_up.name
                    tela_bytes = tela_up.getvalue()

        if modo_sel in ["Solo Madera", "Tela + Madera"]:
            st.markdown("##### 🪵 Muestra de Madera")
            tab_m1, tab_m2 = st.tabs([f"📂 Menú Catálogo ({len(lista_maderas)} maderas)", "📤 Arrastrar / Subir Foto"])
            with tab_m1:
                sel_m_nombre = st.selectbox("Elige madera del catálogo:", opciones_maderas, key=f"sb_madera_oficial_v4_{st.session_state.clear_key_v4}")
                if sel_m_nombre:
                    obj_m = map_maderas.get(sel_m_nombre.upper())
                    if obj_m:
                        madera_name = sel_m_nombre
                        if obj_m.get("local_path") and os.path.exists(obj_m["local_path"]):
                            madera_bytes = Path(obj_m["local_path"]).read_bytes()
                        elif obj_m.get("id"):
                            madera_bytes = sheets_service.get_drive_file_bytes(obj_m["id"])
            with tab_m2:
                madera_up = st.file_uploader(
                    "Arrastra aquí la foto de la muestra de madera",
                    type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],
                    key=f"st_madera_v4_{st.session_state.clear_key_v4}"
                )
                if madera_up:
                    madera_name = madera_up.name
                    madera_bytes = madera_up.getvalue()

        st.markdown("---")
        st.markdown("##### 💬 Comentarios / Notas adicionales (Opcional)")
        notas_usuario = st.text_area(
            "Indica detalles específicos para la IA (si está vacío, no afectará):",
            placeholder="Ej: Mantener cojines en tono marfil, respetar las patas cónicas de madera clara...",
            key=f"txt_notas_usuario_v4_{st.session_state.clear_key_v4}"
        )

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("⚡ GENERAR PROMPTS", type="primary", use_container_width=True, key="btn_gen_prompts_v4"):
            if not mueble_up:
                st.error("⚠️ Sube la foto del mueble primero.")
            elif modo_sel == "Vistas + Tela y Madera" and not ('vistas_up' in locals() and vistas_up):
                st.error("⚠️ Sube al menos una vista adicional.")
            elif modo_sel in ["Solo Tela", "Vistas + Tela"] and not tela_bytes:
                st.error("⚠️ Selecciona o sube una muestra de tela.")
            elif modo_sel == "Solo Madera" and not madera_bytes:
                st.error("⚠️ Selecciona o sube una muestra de madera.")
            elif modo_sel == "Tela + Madera" and (not tela_bytes or not madera_bytes):
                st.error("⚠️ Requiere muestra de tela y madera.")
            else:
                progress_holder = st.empty()
                with progress_holder.container():
                    st.info("🚀 Iniciando procesamiento con Gemini Vision...")
                    
                m_bytes = [f.getvalue() for f in mueble_up]
                m_name = ", ".join([f.name for f in mueble_up])
                num_imgs = len(mueble_up)
                vistas_data = []
                prompts = {}
                f_ana = None
                w_ana = None
                m_ana = None

                try:
                    if tela_bytes:
                        progress_holder.info("🧵 Analizando micro-textura y color de la tela...")
                        f_ana = ai_prompt_service_v4.analyze_material(tela_bytes, material_type="fabric")
                    if madera_bytes:
                        progress_holder.info("🪵 Analizando veta y textura de la madera...")
                        w_ana = ai_prompt_service_v4.analyze_material(madera_bytes, material_type="wood")
                    
                    if modo_sel == "Solo mueble":
                        progress_holder.info("🔄 Analizando mueble para extracción en fondo blanco...")
                        m_ana = ai_prompt_service_v4.analyze_furniture_for_enhancement(m_bytes)
                        prompts = ai_prompt_service_v4.generate_extraction_prompt(m_name, m_ana, notas_usuario=notas_usuario)

                    elif modo_sel in ["Solo Tela", "Solo Madera", "Tela + Madera"]:
                        progress_holder.info("🛋️ Analizando geometría del mueble...")
                        m_ana = ai_prompt_service_v4.analyze_furniture_for_enhancement(m_bytes)
                        mode_map = {"Solo Tela": "fabric_only", "Solo Madera": "wood_only", "Tela + Madera": "dual"}
                        prompts = ai_prompt_service_v4.generate_material_swap_prompt_v4(
                            mode=mode_map[modo_sel],
                            furniture_name=m_name,
                            fabric_analysis=f_ana,
                            wood_analysis=w_ana,
                            furniture_analysis=m_ana,
                            num_furniture_images=num_imgs,
                            notas_usuario=notas_usuario
                        )
                    
                    elif modo_sel == "Vistas":
                        progress_holder.info("🛋️ Calculando perspectivas ortogonales 360°...")
                        m_ana = ai_prompt_service_v4.analyze_furniture_for_enhancement(m_bytes)
                        prompts_vistas = ai_prompt_service_v4.generate_multi_perspective_prompts_v4(
                            furniture_name=m_name,
                            fabric_analysis=f_ana,
                            furniture_analysis=m_ana,
                            notas_usuario=notas_usuario
                        )
                        vistas_nombres = [
                            ("vista_de_frente", "vista de frente"),
                            ("vista_lateral", "vista lateral"),
                            ("vista_lateral_derecha", "vista lateral (derecha)"),
                            ("vista_lateral_izquierda", "vista lateral (izquierda)"),
                            ("vista_3_4_izquierda", "vista 3/4 mirando a la izquierda"),
                            ("vista_3_4_derecha", "vista 3/4 mirando a la derecha"),
                            ("vista_desde_arriba", "vista desde arriba"),
                            ("vista_3_4_posterior", "vista 3/4 posterior"),
                            ("vista_lifestyle", "vista lifestyle con fondo ambiental")
                        ]
                        for key_v, label_v in vistas_nombres:
                            vista_prompt = prompts_vistas.get(key_v)
                            if not isinstance(vista_prompt, dict):
                                continue
                            vistas_data.append({
                                "name": label_v,
                                "bytes": None,
                                "prompt": vista_prompt
                            })
                        
                        def build_all_v4(ai_key):
                            return "\n\n".join(
                                f"=== {i}. {vista['name'].upper()} ===\n{vista['prompt'][ai_key]}"
                                for i, vista in enumerate(vistas_data, start=1)
                                if vista["prompt"].get(ai_key)
                            )

                        prompts = {
                            "google_ai_studio": build_all_v4("google_ai_studio"),
                            "chatgpt_dalle3": build_all_v4("chatgpt_dalle3"),
                            "midjourney_v6": build_all_v4("midjourney_v6")
                        }

                    elif modo_sel == "Vistas + Tela":
                        import concurrent.futures
                        prompts_vistas = []
                        fab_bytes = tela_bytes
                        total_v = len(mueble_up)
                        progress_holder.info(f"🎨 Aplicando tela a {total_v} vistas simultáneamente...")
                        
                        def process_vista_tela(v_file):
                            return v_file, ai_prompt_service_v4.generate_dynamic_fabric_view_prompt(
                                fabric_bytes=fab_bytes,
                                view_bytes=v_file.getvalue(),
                                notas_usuario=notas_usuario
                            )
                            
                        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                            results = list(executor.map(process_vista_tela, mueble_up))
                            
                        for i, (v_file, p) in enumerate(results):
                            prompts_vistas.append(p)
                            vistas_data.append({
                                "name": f"Vista {i+1}: {v_file.name}",
                                "bytes": v_file.getvalue(),
                                "prompt": p
                            })
                        
                        def build_tela_vistas(ai_key):
                            result = ""
                            for i, p in enumerate(prompts_vistas):
                                result += f"=== PROMPT PARA VISTA {i+1} ===\n{p[ai_key]}\n\n"
                            return result.strip()

                        prompts = {
                            "google_ai_studio": build_tela_vistas("google_ai_studio"),
                            "chatgpt_dalle3": build_tela_vistas("chatgpt_dalle3"),
                            "midjourney_v6": build_tela_vistas("midjourney_v6")
                        }

                    elif modo_sel == "Vistas + Tela y Madera":
                        import concurrent.futures
                        prompts_vistas = []
                        total_v = len(vistas_up)
                        progress_holder.info(f"🧬 Clonando color y textura a {total_v} vistas simultáneamente...")
                        
                        def process_vista_clon(v_file):
                            return v_file, ai_prompt_service_v4.generate_dynamic_gemini_clone_prompt(
                                ref_bytes=m_bytes[0],
                                view_bytes=v_file.getvalue(),
                                notas_usuario=notas_usuario
                            )
                            
                        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                            results = list(executor.map(process_vista_clon, vistas_up))
                            
                        for i, (v_file, p) in enumerate(results):
                            prompts_vistas.append(p)
                            vistas_data.append({
                                "name": f"Vista {i+1}: {v_file.name}",
                                "bytes": v_file.getvalue(),
                                "prompt": p
                            })
                        
                        def build_clones(ai_key):
                            result = ""
                            for i, p in enumerate(prompts_vistas):
                                result += f"=== PROMPT PARA VISTA {i+1} ===\n{p[ai_key]}\n\n"
                            return result.strip()

                        prompts = {
                            "google_ai_studio": build_clones("google_ai_studio"),
                            "chatgpt_dalle3": build_clones("chatgpt_dalle3"),
                            "midjourney_v6": build_clones("midjourney_v6")
                        }

                    elif modo_sel == "Entorno":
                        progress_holder.info("✨ Diseñando entorno arquitectónico con IA...")
                        m_ana = ai_prompt_service_v4.analyze_furniture_for_enhancement(m_bytes)
                        prompts = ai_prompt_service_v4.generate_minimalist_environment_prompt_v4(
                            furniture_name=m_name,
                            fabric_analysis=f_ana,
                            furniture_analysis=m_ana,
                            num_furniture_images=num_imgs,
                            tipo_mueble_usuario=tipo_mueble_usuario,
                            medidas_usuario=medidas_usuario,
                            lugar_casa_usuario=lugar_casa_usuario,
                            notas_usuario=notas_usuario
                        )

                    st.session_state["last_studio_result_v4"] = {
                        "vistas_data": vistas_data,
                        "modo": modo_sel,
                        "mueble_name": m_name,
                        "fabric_analysis": f_ana,
                        "wood_analysis": w_ana,
                        "furniture_analysis": m_ana,
                        "prompts": prompts
                    }
                    progress_holder.success("✅ ¡Prompts generados exitosamente!")
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

        if 'vistas_up' in locals() and vistas_up:
            for f in vistas_up:
                try:
                    st.image(f.getvalue(), caption=f"Vista: {f.name}", use_container_width=True)
                except Exception:
                    pass

        if tela_bytes:
            st.image(tela_bytes, caption=f"Tela: {tela_name or 'Seleccionada'}", use_container_width=True)

        if madera_bytes:
            st.image(madera_bytes, caption=f"Madera: {madera_name or 'Seleccionada'}", use_container_width=True)

        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="studio-card">', unsafe_allow_html=True)
        st.markdown('<div class="studio-card-title">✨ 3. Prompts Generados</div>', unsafe_allow_html=True)

        if "last_studio_result_v4" in st.session_state:
            res = st.session_state["last_studio_result_v4"]
            v_data = res.get("vistas_data", [])
            prompts = res.get("prompts", {})

            if v_data:
                st.markdown(f"#### 👁️ Vistas Disponibles ({len(v_data)})")
                vista_tabs = st.tabs([f"{v['name'].title()}" for v in v_data])
                for idx, v_item in enumerate(v_data):
                    with vista_tabs[idx]:
                        if v_item.get("bytes"):
                            st.image(v_item["bytes"], caption=v_item["name"], use_container_width=True)
                        p_obj = v_item["prompt"]
                        st.markdown("###### 🌐 Google AI Studio / Gemini")
                        st.text_area(f"AI Studio ({v_item['name']})", p_obj.get("google_ai_studio", ""), height=130, key=f"txt_ais_{idx}_v4")
                        render_copy_button(p_obj.get("google_ai_studio", ""), label="📋 Copiar Prompt AI Studio", key=f"cp_ais_{idx}_v4")
                        
                        st.markdown("###### 🤖 ChatGPT (DALL-E 3)")
                        st.text_area(f"DALL-E 3 ({v_item['name']})", p_obj.get("chatgpt_dalle3", ""), height=100, key=f"txt_dal_{idx}_v4")
                        render_copy_button(p_obj.get("chatgpt_dalle3", ""), label="📋 Copiar Prompt DALL-E", key=f"cp_dal_{idx}_v4")

                st.markdown("---")
                st.markdown("#### 📋 Todos los Prompts Juntos")
                p_all_ai = prompts.get("google_ai_studio", "")
                st.text_area("Todos los prompts (AI Studio):", p_all_ai, height=180, key="txt_all_ais_v4")
                render_copy_button(p_all_ai, label="📋 Copiar Todos los Prompts", key="cp_all_v4")
            else:
                p_tab1, p_tab2, p_tab3 = st.tabs(["🌐 Google AI Studio", "🤖 ChatGPT (DALL-E 3)", "🎨 Midjourney v6.1"])
                with p_tab1:
                    p_txt = prompts.get("google_ai_studio", "")
                    st.text_area("Prompt Google AI Studio / Gemini:", p_txt, height=220, key="txt_res_ais_v4")
                    render_copy_button(p_txt, label="📋 Copiar Prompt para Google AI Studio", key="cp_res_ais_v4")
                with p_tab2:
                    p_dalle = prompts.get("chatgpt_dalle3", "")
                    st.text_area("Prompt ChatGPT / DALL-E 3:", p_dalle, height=200, key="txt_res_dal_v4")
                    render_copy_button(p_dalle, label="📋 Copiar Prompt para ChatGPT", key="cp_res_dal_v4")
                with p_tab3:
                    p_mj = prompts.get("midjourney_v6", "")
                    st.text_area("Prompt Midjourney v6.1:", p_mj, height=200, key="txt_res_mj_v4")
                    render_copy_button(p_mj, label="📋 Copiar Prompt para Midjourney", key="cp_res_mj_v4")

            # Metadatos del análisis
            fa = res.get("fabric_analysis")
            wa = res.get("wood_analysis")
            ma = res.get("furniture_analysis")
            if fa or wa or ma:
                with st.expander("🔍 Ver Análisis de Gemini Vision", expanded=False):
                    if ma:
                        st.markdown(f"**🛋️ Mueble:** `{ma.get('furniture_item', 'N/A')}`")
                        st.markdown(f"**📐 Cámara:** `{ma.get('camera_angle', 'N/A')}`")
                        st.markdown(f"**🧱 Materiales Detectados:** `{ma.get('existing_materials', 'N/A')}`")
                    if fa:
                        st.markdown(f"**🧵 Tela:** `{fa.get('name', 'N/A')}` | `{fa.get('color_description', 'N/A')}`")
                    if wa:
                        st.markdown(f"**🪵 Madera:** `{wa.get('name', 'N/A')}` | `{wa.get('color_description', 'N/A')}`")
        else:
            st.info("👈 Configura tus opciones a la izquierda y presiona **⚡ GENERAR PROMPTS**.")

        st.markdown('</div>', unsafe_allow_html=True)

import os

import io

import json

from pathlib import Path

import streamlit as st

from PIL import Image



FOLDER_TELAS_DRIVE_ID = "1JKJPXcnPFPeoUOo_mBIUyl_KXM0Fn3Ul"

FOLDER_MADERAS_DRIVE_ID = "1Jq2u1A6-xKi1YigUYSIzLauUww_RJ5Lx"



@st.cache_data(ttl=300)

def cargar_telas_menu():

    from services.sheets_service import sheets_service

    return sheets_service.get_drive_folder_files(FOLDER_TELAS_DRIVE_ID, recursive=True)



@st.cache_data(ttl=300)

def cargar_maderas_menu():

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

    

    # Combinar ambas listas

    combined = local_maderas + [m for m in drive_maderas if not any(l["name"].upper() == m["name"].upper() for l in local_maderas)]

    return combined



def render_copy_button(text: str, label: str = "📋 Copiar Prompt", key: str = "cp_v1"):
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

def render_prompt_studio():

    from services.ai_prompt_service_v1 import ai_prompt_service

    from services.sheets_service import sheets_service

    from services.photo_service import photo_service



    # Estilos CSS (Gris Pizarra / Slate Grey de Alto Contraste)

    st.markdown("""

    <style>

    [data-testid="stSidebar"] {

        background-color: #283548 !important;

    }



    header[data-testid="stHeader"] {

        background-color: #1E293B !important;

    }

    .stApp {

        background-color: #1E293B !important;

        color: #FFFFFF !important;

    }

    label, .stRadio label, .stSelectbox label, .stTextInput label, p, span, div {

        color: #FFFFFF !important;

        font-weight: 600 !important;

    }

    h1, h2, h3, h4, h5, h6 {

        color: #FFFFFF !important;

    }

    .studio-top-bar {

        background-color: #283548;

        border: 1px solid #475569;

        border-radius: 10px;

        padding: 12px 20px;

        display: flex;

        justify-content: space-between;

        align-items: center;

        margin-bottom: 18px;

    }

    .studio-badge {

        background: rgba(245, 158, 11, 0.2);

        color: #FBBF24;

        border: 1px solid rgba(245, 158, 11, 0.4);

        font-size: 11px;

        padding: 3px 8px;

        border-radius: 9999px;

        font-weight: 700;

    }

    .studio-card {

        background-color: #283548;

        border: 1px solid #475569;

        border-radius: 12px;

        padding: 18px;

        height: 100%;

        box-shadow: 0 4px 15px rgba(0,0,0,0.2);

    }

    .studio-card-title {

        font-size: 15px;

        font-weight: 700;

        color: #FFFFFF !important;

        margin-bottom: 14px;

        display: flex;

        justify-content: space-between;

        align-items: center;

        border-bottom: 1px solid #334155;

        padding-bottom: 8px;

    }

    .protection-badge {

        background: rgba(16, 185, 129, 0.2);

        border: 1px solid rgba(16, 185, 129, 0.4);

        color: #34D399;

        border-radius: 8px;

        padding: 10px 14px;

        font-size: 12px;

        font-weight: 600;

        text-align: center;

        margin-top: 14px;

    }

    .meta-pill {

        display: inline-block;

        background: #1E293B;

        border: 1px solid #475569;

        color: #38BDF8;

        font-size: 11px;

        padding: 4px 10px;

        border-radius: 6px;

        margin: 2px;

    }

</style>

""", unsafe_allow_html=True)



    # -------------------------------------------------------------------------

    # TOP BAR (CABECERA EXACTA)

    # -------------------------------------------------------------------------

    c_head_left, c_head_right = st.columns([2, 2])

    with c_head_left:
        st.markdown("""
<div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
    <span style="font-size:22px; font-weight:800; color:#F59E0B;">⚡ Estudio Prompts Exitosos</span>
    <span class="studio-badge">IA Multi-Modo</span>
</div>
        """, unsafe_allow_html=True)

    with c_head_right:
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if "last_studio_result" in st.session_state:
                import io
                import zipfile
                res = st.session_state["last_studio_result"]
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    prompt_txt = res["prompts"].get("google_ai_studio", "") or res["prompts"].get("chatgpt_dalle3", "") or res["prompts"].get("flux_midjourney", "")
                    if prompt_txt:
                        zip_file.writestr(f"prompt_{res.get('mueble_name', 'generado')}.txt", prompt_txt)
                    
                    m_files = st.session_state.get("st_mueble")
                    if m_files: 
                        for i, m in enumerate(m_files):
                            zip_file.writestr(f"1_foto_mueble_{i+1}.jpg", m.getvalue())
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

                for k in ["last_studio_result", "st_mueble", "st_tela", "st_madera", "sb_tela_oficial", "sb_madera_oficial"]:

                    if k in st.session_state:

                        del st.session_state[k]

                st.rerun()



    # Cargar catálogos interactivos para los menús

    lista_telas = cargar_telas_menu()

    map_telas = {t["name"].upper(): t for t in lista_telas}

    opciones_telas = [""] + [t["name"] for t in lista_telas]



    lista_maderas = cargar_maderas_menu()

    map_maderas = {m["name"].upper(): m for m in lista_maderas}

    opciones_maderas = [""] + [m["name"] for m in lista_maderas]



    # -------------------------------------------------------------------------

    # LAYOUT DE 3 COLUMNAS EXACTO A LA FOTO 1

    # -------------------------------------------------------------------------

    col1, col2, col3 = st.columns([1.25, 0.7, 1.45])



    # Variables para fotos seleccionadas

    tela_bytes = None

    tela_name = ""

    madera_bytes = None

    madera_name = ""



    # =========================================================================

    # COLUMNA 1: CONTROLES Y MENÚS DE SELECCIÓN

    # =========================================================================

    with col1:

        st.markdown('<div class="studio-card">', unsafe_allow_html=True)

        st.markdown('<div class="studio-card-title">🎯 1. ¿Qué deseas hacer?</div>', unsafe_allow_html=True)



        modo_sel = st.radio(
            "Selecciona el tipo de trabajo:",
            ["Solo Tela", "Solo Madera", "Tela + Madera", "Extraer Mueble (Fondo Blanco)", "Aumento HD", "Vistas (360)"],
            horizontal=True,
            label_visibility="collapsed",
            key="studio_mode_radio"
        )



        usar_prompts_clasicos = st.toggle("🔙 Usar Textos Clásicos Originales", value=True, help="Fuerza los textos a decir 'Image 2' o 'Image 3' como tus prompts originales, ignorando cuántas fotos del mueble subas.")

        fondo_blanco = st.toggle("⬜ Extraer Mueble (Fondo Blanco)", value=True, help="Le ordena a la IA extraer el mueble, preservando color, textura y geometría, colocándolo sobre blanco puro sin sombras ni reflejos.")



        st.markdown("---")

        st.markdown("##### 🛋️ Foto del Mueble Original")

        mueble_up = st.file_uploader(

            "Haz clic o arrastra foto(s) del mueble",

            type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'],

            key="st_mueble",

            accept_multiple_files=True,

            help="Sube una o más fotografías del mueble base a remasterizar."

        )



        # ---------------------------------------------------------------------

        # SELECCIÓN DE TELA (MENÚ O SUBIDA)

        # ---------------------------------------------------------------------

        if modo_sel in ["Solo Tela", "Tela + Madera"]:

            st.markdown("##### 🧵 2. Muestra de Tela")

            tipo_origen_tela = st.radio(

                "Fuente de tela:",

                ["📂 Menú Catálogo Oficial", "📤 Subir Foto Propia"],

                horizontal=True,

                key="rad_tipo_tela"

            )



            if tipo_origen_tela == "📂 Menú Catálogo Oficial":

                sel_t_nombre = st.selectbox(

                    "Escribe o elige tela (132 telas oficiales):",

                    opciones_telas,

                    key="sb_tela_oficial"

                )

                if sel_t_nombre:

                    obj_t = map_telas.get(sel_t_nombre.upper())

                    if obj_t and obj_t.get("id"):

                        tela_name = sel_t_nombre

                        tela_bytes = sheets_service.get_drive_file_bytes(obj_t["id"])

            else:

                tela_up = st.file_uploader("Haz clic o arrastra muestra de tela", type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'], key="st_tela")

                if tela_up:

                    tela_name = tela_up.name

                    tela_bytes = tela_up.getvalue()



        # ---------------------------------------------------------------------

        # SELECCIÓN DE MADERA (MENÚ O SUBIDA)

        # ---------------------------------------------------------------------

        if modo_sel in ["Solo Madera", "Tela + Madera"]:

            st.markdown("##### 🪵 Muestra de Madera / Acabado")

            tipo_origen_mad = st.radio(

                "Fuente de madera:",

                ["📂 Menú Catálogo Oficial", "📤 Subir Foto Propia"],

                horizontal=True,

                key="rad_tipo_mad"

            )



            if tipo_origen_mad == "📂 Menú Catálogo Oficial":

                sel_m_nombre = st.selectbox(

                    "Escribe o elige madera (Muestras y Tonos):",

                    opciones_maderas,

                    key="sb_madera_oficial"

                )

                if sel_m_nombre:

                    obj_m = map_maderas.get(sel_m_nombre.upper())

                    if obj_m:

                        madera_name = sel_m_nombre

                        if obj_m.get("local_path") and os.path.exists(obj_m["local_path"]):

                            madera_bytes = Path(obj_m["local_path"]).read_bytes()

                        elif obj_m.get("id"):

                            madera_bytes = sheets_service.get_drive_file_bytes(obj_m["id"])

            else:

                madera_up = st.file_uploader("Haz clic o arrastra muestra de madera", type=['png', 'jpg', 'jpeg', 'webp', 'bmp', 'heic', 'tiff'], key="st_madera")

                if madera_up:

                    madera_name = madera_up.name

                    madera_bytes = madera_up.getvalue()



        st.markdown("<br>", unsafe_allow_html=True)



        # Botón de Acción Principal

        btn_label = "⚡ GENERAR PROMPT MEJORA HD" if modo_sel == "Aumento HD" else "⚡ GENERAR PROMPT CAMBIO DE COLOR"

        btn_action = st.button(btn_label, type="primary", use_container_width=True, key="btn_gen_prompts")



        if btn_action:

            if not mueble_up:

                st.error("⚠️ Por favor sube la foto del mueble primero.")

            elif modo_sel == "Solo Tela" and not tela_bytes:

                st.error("⚠️ Por favor selecciona una tela del menú o sube una muestra.")

            elif modo_sel == "Solo Madera" and not madera_bytes:

                st.error("⚠️ Por favor selecciona una madera del menú o sube una muestra.")

            elif modo_sel == "Tela + Madera" and (not tela_bytes or not madera_bytes):

                st.error("⚠️ Para cambio dual requieres muestra de tela y madera.")

            else:

                with st.spinner("Analizando micro-texturas y generando prompts con Gemini..."):

                    m_bytes = [f.getvalue() for f in mueble_up]

                    m_name = ", ".join([f.name for f in mueble_up])

                    num_imgs = 1 if usar_prompts_clasicos else len(mueble_up)



                    if modo_sel == "Aumento HD":

                        ana = ai_prompt_service.analyze_furniture_for_enhancement(m_bytes)

                        prompts = ai_prompt_service.generate_enhance_prompt(m_name, ana)

                        st.session_state["last_studio_result"] = {

                            "modo": modo_sel,

                            "mueble_name": m_name,

                            "mueble_bytes": m_bytes,

                            "analysis": ana,

                            "prompts": prompts

                        }

                    elif modo_sel == "Vistas (360)":

                        ana = ai_prompt_service.analyze_furniture_for_enhancement(m_bytes)

                        prompts_vistas = ai_prompt_service.generate_multi_perspective_prompts(

                            "fabric_only", m_name, analysis=ana,

                            num_furniture_images=num_imgs

                        )

                        # Adapt to standard structure so it renders below

                        

                        def build_all(ai_key):

                            return (

                                "=== 1. VISTA DE FRENTE ===\n" + prompts_vistas["frontal_ortogonal"][ai_key] + "\n\n" +

                                "=== 2. VISTA LATERAL (DERECHA) ===\n" + prompts_vistas["lateral_derecha"][ai_key] + "\n\n" +

                                "=== 3. VISTA LATERAL (IZQUIERDA) ===\n" + prompts_vistas["lateral_izquierda"][ai_key] + "\n\n" +

                                "=== 4. VISTA 3/4 (DIAGONAL) ===\n" + prompts_vistas["tres_cuartos"][ai_key] + "\n\n" +

                                "=== 5. VISTA SUPERIOR (DESDE ARRIBA) ===\n" + prompts_vistas["cenital"][ai_key] + "\n\n" +

                                "=== 6. VISTA LIFESTYLE (CON FONDO AMBIENTAL) ===\n" + prompts_vistas["lifestyle"][ai_key]

                            )

                        

                        prompts = {

                            "google_ai_studio": build_all("google_ai_studio"),

                            "flux_midjourney": build_all("flux_midjourney"),

                            "dalle_chatgpt": build_all("dalle_chatgpt")

                        }

                        st.session_state["last_studio_result"] = {

                            "modo": modo_sel,

                            "mueble_name": m_name,

                            "mueble_bytes": m_bytes,

                            "analysis": ana,

                            "prompts": prompts,
                            "prompts_vistas": prompts_vistas

                        }

                    elif modo_sel == "Extraer Mueble (Fondo Blanco)":

                        m_ana = ai_prompt_service.analyze_furniture_for_enhancement(m_bytes)
                        prompts = ai_prompt_service.generate_extraction_prompt(m_name, m_ana)

                        st.session_state["last_studio_result"] = {
                            "modo": modo_sel,
                            "mueble_name": m_name,
                            "mueble_bytes": m_bytes,
                            "analysis": m_ana,
                            "prompts": prompts
                        }

                    elif modo_sel == "Solo Tela":

                        f_ana = ai_prompt_service.analyze_material(tela_bytes, material_type="fabric swatch")

                        m_ana = ai_prompt_service.analyze_furniture_for_enhancement(m_bytes)

                        prompts = ai_prompt_service.generate_material_swap_prompt(

                            mode="fabric_only",

                            furniture_name=m_name,

                            fabric_name=tela_name,

                            fabric_analysis=f_ana,

                            num_furniture_images=num_imgs,

                            fondo_blanco_sin_sombras=fondo_blanco,

                            furniture_analysis=m_ana

                        )

                        st.session_state["last_studio_result"] = {

                            "modo": modo_sel,

                            "mueble_name": m_name,

                            "mueble_bytes": m_bytes,

                            "tela_name": tela_name,

                            "tela_bytes": tela_bytes,

                            "fabric_analysis": f_ana,

                            "furniture_analysis": m_ana,

                            "prompts": prompts

                        }

                    elif modo_sel == "Solo Madera":

                        w_ana = ai_prompt_service.analyze_material(madera_bytes, material_type="wood swatch")

                        m_ana = ai_prompt_service.analyze_furniture_for_enhancement(m_bytes)

                        prompts = ai_prompt_service.generate_material_swap_prompt(

                            mode="wood_only",

                            furniture_name=m_name,

                            wood_name=madera_name,

                            wood_analysis=w_ana,

                            num_furniture_images=num_imgs,

                            fondo_blanco_sin_sombras=fondo_blanco,

                            furniture_analysis=m_ana

                        )

                        st.session_state["last_studio_result"] = {

                            "modo": modo_sel,

                            "mueble_name": m_name,

                            "mueble_bytes": m_bytes,

                            "madera_name": madera_name,

                            "madera_bytes": madera_bytes,

                            "wood_analysis": w_ana,

                            "furniture_analysis": m_ana,

                            "prompts": prompts

                        }

                    else: # Tela + Madera

                        f_ana = ai_prompt_service.analyze_material(tela_bytes, material_type="fabric swatch")

                        w_ana = ai_prompt_service.analyze_material(madera_bytes, material_type="wood swatch")

                        m_ana = ai_prompt_service.analyze_furniture_for_enhancement(m_bytes)

                        prompts = ai_prompt_service.generate_material_swap_prompt(

                            mode="dual",

                            furniture_name=m_name,

                            fabric_name=tela_name,

                            fabric_analysis=f_ana,

                            wood_name=madera_name,

                            wood_analysis=w_ana,

                            num_furniture_images=num_imgs,

                            fondo_blanco_sin_sombras=fondo_blanco,

                            furniture_analysis=m_ana

                        )

                        st.session_state["last_studio_result"] = {

                            "modo": modo_sel,

                            "mueble_name": m_name,

                            "mueble_bytes": m_bytes,

                            "tela_name": tela_name,

                            "tela_bytes": tela_bytes,

                            "madera_name": madera_name,

                            "madera_bytes": madera_bytes,

                            "prompts": prompts

                        }



        # Badge de protección

        if modo_sel == "Solo Tela":

            st.markdown('<div class="protection-badge">🛡️ Protección Activa: Madera original preservada al 100%</div>', unsafe_allow_html=True)

        elif modo_sel == "Solo Madera":

            st.markdown('<div class="protection-badge">🛡️ Protección Activa: Tapicería original preservada al 100%</div>', unsafe_allow_html=True)

        elif modo_sel == "Aumento HD":

            st.markdown('<div class="protection-badge">🛡️ Cero Drift: Geometría y colores originales bloqueados al 100%</div>', unsafe_allow_html=True)



        st.markdown('</div>', unsafe_allow_html=True)



    # =========================================================================

    # COLUMNA 2: ELEMENTOS CARGADOS (PREVISUALIZACIÓN)

    # =========================================================================

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



        if not mueble_up and not tela_bytes and not madera_bytes:

            st.info("Carga o selecciona tus fotos en el menú izquierdo para previsualizarlas aquí.")



        # Ficha técnica si hay análisis

        if "last_studio_result" in st.session_state:

            res = st.session_state["last_studio_result"]

            st.markdown("---")

            st.markdown("##### 🔬 Análisis Cromático")

            if "fabric_analysis" in res:

                fa = res["fabric_analysis"]

                st.markdown(f"""

                <span class="meta-pill">🏷️ {fa.get('name', 'N/D')}</span>

                <span class="meta-pill">🎨 {fa.get('color_description', 'N/D')}</span>

                """, unsafe_allow_html=True)

            if "wood_analysis" in res:

                wa = res["wood_analysis"]

                st.markdown(f"""

                <span class="meta-pill">🪵 {wa.get('name', 'N/D')}</span>

                <span class="meta-pill">✨ {wa.get('finish_type', 'N/D')}</span>

                """, unsafe_allow_html=True)



        st.markdown('</div>', unsafe_allow_html=True)



    # =========================================================================

    # COLUMNA 3: PROMPTS LISTOS

    # =========================================================================

    with col3:

        st.markdown('<div class="studio-card">', unsafe_allow_html=True)

        st.markdown('<div class="studio-card-title">⚡ Prompts Listos <span class="studio-badge">Micro-Escala -95%</span></div>', unsafe_allow_html=True)



        if "last_studio_result" in st.session_state:

            res = st.session_state["last_studio_result"]

            p_tabs = st.tabs(["🌟 Google AI Studio", "⚡ Flux / Midjourney", "🤖 DALL-E 3", "🎨 Render Gratis (FLUX.1)", "📚 Biblioteca"])



            with p_tabs[0]:
                if res.get("modo") == "Vistas (360)" and "prompts_vistas" in res:
                    for v_key, v_dict in res["prompts_vistas"].items():
                        st.markdown(f"**{v_key.replace('_', ' ').upper()}**")
                        st.code(v_dict["google_ai_studio"], language="markdown")
                else:
                    p_google = res["prompts"]["google_ai_studio"]
                    st.text_area("Prompt Google AI Studio / Imagen 3:", value=p_google, height=300, key="txt_res_g")
                    st.code(p_google, language="markdown")
                    st.download_button("💾 Descargar .txt", data=p_google, file_name=f"prompt_google_{res['mueble_name']}.txt", use_container_width=True)

            with p_tabs[1]:
                if res.get("modo") == "Vistas (360)" and "prompts_vistas" in res:
                    for v_key, v_dict in res["prompts_vistas"].items():
                        st.markdown(f"**{v_key.replace('_', ' ').upper()}**")
                        st.code(v_dict["flux_midjourney"], language="markdown")
                else:
                    p_flux = res["prompts"]["flux_midjourney"]
                    st.text_area("Prompt Flux / Midjourney v6.1:", value=p_flux, height=180, key="txt_res_f")
                    st.code(p_flux, language="markdown")
                    st.download_button("💾 Descargar .txt", data=p_flux, file_name=f"prompt_flux_{res['mueble_name']}.txt", use_container_width=True)

            with p_tabs[2]:
                if res.get("modo") == "Vistas (360)" and "prompts_vistas" in res:
                    for v_key, v_dict in res["prompts_vistas"].items():
                        st.markdown(f"**{v_key.replace('_', ' ').upper()}**")
                        st.code(v_dict["dalle_chatgpt"], language="markdown")
                else:
                    p_dalle = res["prompts"]["dalle_chatgpt"]
                    st.text_area("Prompt DALL-E 3 / ChatGPT:", value=p_dalle, height=180, key="txt_res_d")
                    st.code(p_dalle, language="markdown")
                    st.download_button("💾 Descargar .txt", data=p_dalle, file_name=f"prompt_dalle_{res['mueble_name']}.txt", use_container_width=True)



            with p_tabs[3]:
                from services.free_image_service import free_image_service
                st.markdown("##### ⚡ Generador In-App V1 (FLUX.1)")
                prompt_para_render = res["prompts"].get("flux_midjourney") or res["prompts"].get("google_ai_studio") or res["prompts"].get("dalle_chatgpt", "")
                
                col_gen_btn, col_gen_asp = st.columns([2, 1])
                with col_gen_asp:
                    formato_sel = st.selectbox("Formato:", ["Apaisado (4:3)", "Cuadrado (1:1)", "Panorámico (16:9)"], key="sel_asp_v1")
                    w_r, h_r = (1024, 768) if "4:3" in formato_sel else ((1024, 1024) if "1:1" in formato_sel else (1280, 720))
                
                with col_gen_btn:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    btn_gen = st.button("🚀 Generar Render Ahora", type="primary", use_container_width=True, key="btn_flux_v1")
                
                if btn_gen:
                    with st.spinner("🎨 Renderizando mueble con IA gratuita..."):
                        try:
                            img_render = free_image_service.generate_flux_image(
                                prompt=prompt_para_render,
                                width=w_r,
                                height=h_r
                            )
                            st.session_state["render_generado_v1"] = img_render
                            st.success("✅ ¡Render generado con éxito!")
                        except Exception as err:
                            st.error(f"❌ Error al generar imagen: {err}")
                
                if "render_generado_v1" in st.session_state:
                    st.image(st.session_state["render_generado_v1"], caption=f"Render IA: {res.get('mueble_name', 'Mueble')}", use_container_width=True)
                    st.download_button(
                        label="💾 Descargar Render (JPG)",
                        data=st.session_state["render_generado_v1"],
                        file_name=f"render_{res.get('mueble_name', 'mueble')}.jpg",
                        mime="image/jpeg",
                        use_container_width=True
                    )

            with p_tabs[4]:

                app_dir = Path(__file__).resolve().parent.parent

                prompts_dir = app_dir / "PROMPTS EXITOSOS"

                if prompts_dir.exists():

                    txt_files = list(prompts_dir.glob("*.txt"))

                    sel_p = st.selectbox("Ejemplos Certificados:", [f.name for f in txt_files], key="sb_lib_ex")

                    if sel_p:

                        p_content = (prompts_dir / sel_p).read_text(encoding="utf-8", errors="ignore")

                        st.text_area("Contenido:", value=p_content, height=220)

        else:
            st.markdown('<div style="text-align:center; padding: 60px 20px; color:#64748B;"><div style="font-size:32px; margin-bottom:10px;">✨</div><div>Los prompts aparecerán aquí con botones de descarga rápida.</div></div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)



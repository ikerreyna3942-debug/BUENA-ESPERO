import streamlit as st
from services.sheets_service import sheets_service

def render_sku_autofill_bar(version_key: str):
    """
    Renderiza la barra de búsqueda universal por SKU con auto-llenado automático de:
    - Medidas Exactas
    - Tipo de Mueble
    - Cuadro para comentarios e instrucciones del usuario
    - Referencias a fotos
    100% SOLO LECTURA respecto a Google Sheets.
    """
    k_sku = f"sku_input_{version_key}"
    k_tipo = f"tipo_mueble_{version_key}"
    k_medidas = f"medidas_{version_key}"
    k_loaded = f"sku_loaded_data_{version_key}"

    if k_tipo not in st.session_state:
        st.session_state[k_tipo] = ""
    if k_medidas not in st.session_state:
        st.session_state[k_medidas] = ""

    st.markdown("""
    <div style="background: linear-gradient(135deg, #1E293B, #283548); border: 1px solid #3B82F6; border-radius: 10px; padding: 12px 16px; margin-bottom: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.25);">
        <div style="font-weight: 800; font-size: 13px; color: #60A5FA; display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span>🔍 AUTO-LLENADO INTELIGENTE POR SKU (BASE DE DATOS GENERALES)</span>
        </div>
        <div style="font-size: 11px; color: #CBD5E1;">
            Coloca el SKU del mueble para cargar automáticamente sus <b>Medidas Exactas</b> y <b>Tipo de Mueble</b> desde el catálogo oficial.
        </div>
    </div>
    """, unsafe_allow_html=True)

    c_sku_in, c_sku_btn = st.columns([3.5, 1.2])
    with c_sku_in:
        sku_val = st.text_input(
            "SKU del Producto:",
            placeholder="Escribe el SKU (ej. ADSDT2038220, ADSMESREDCIRC, 1313DTOARCGRS...)",
            key=k_sku,
            label_visibility="collapsed"
        )
    with c_sku_btn:
        btn_buscar = st.button("⚡ Cargar SKU", key=f"btn_search_sku_{version_key}", use_container_width=True)

    if (btn_buscar or sku_val) and sku_val.strip():
        sku_clean = sku_val.strip().upper()
        current_loaded = st.session_state.get(k_loaded, {})
        if current_loaded.get("sku", "").upper() != sku_clean or btn_buscar:
            info = sheets_service.get_furniture_by_sku(sku_clean)
            if info:
                st.session_state[k_loaded] = info
                # Tomar ÚNICAMENTE Tipo de Mueble y Medidas Exactas
                if info.get("tipo_mueble"):
                    st.session_state[k_tipo] = info["tipo_mueble"]
                if info.get("medidas"):
                    st.session_state[k_medidas] = info["medidas"]
            else:
                st.warning(f"⚠️ El SKU '{sku_clean}' no fue encontrado en DATOS GENERAL. Puedes ingresar las medidas y tipo manualmente.")

    data_loaded = st.session_state.get(k_loaded)
    if data_loaded:
        st.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #10B981; border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; font-size: 12px; color: #FFFFFF;">
            <b>✅ SKU Reconocido:</b> {data_loaded.get('sku')} — <i>{data_loaded.get('nombre', '')}</i><br/>
            <b>🛋️ Tipo de Mueble:</b> <span style="color:#34D399; font-weight:700;">{st.session_state.get(k_tipo, 'Detectado')}</span> &nbsp;|&nbsp; 
            <b>📐 Medidas Exactas:</b> <span style="color:#38BDF8; font-weight:700;">{st.session_state.get(k_medidas, 'Detectadas')}</span>
        </div>
        """, unsafe_allow_html=True)

    c_tipo, c_med = st.columns([1, 1])
    with c_tipo:
        st.session_state[k_tipo] = st.text_input(
            "🛋️ Tipo de Mueble (detectado automáticamente o editable):",
            value=st.session_state[k_tipo],
            key=f"field_tipo_{version_key}"
        )
    with c_med:
        st.session_state[k_medidas] = st.text_input(
            "📐 Medidas Exactas (detectadas automáticamente o editables):",
            value=st.session_state[k_medidas],
            key=f"field_medidas_{version_key}"
        )

    return {
        "sku": sku_val.strip() if sku_val else "",
        "tipo_mueble": st.session_state[k_tipo].strip(),
        "medidas": st.session_state[k_medidas].strip(),
        "data_loaded": data_loaded
    }

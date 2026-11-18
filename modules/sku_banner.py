import streamlit as st
from services.sheets_service import sheets_service


def render_sku_autofill_bar(version_key: str):
    """Barra compacta de búsqueda por SKU (100% solo lectura de Google Sheets)."""
    k_sku = f"sku_input_{version_key}"
    k_tipo = f"field_tipo_{version_key}"
    k_medidas = f"field_medidas_{version_key}"
    k_loaded = f"sku_loaded_data_{version_key}"
    k_last_searched = f"sku_last_searched_{version_key}"

    if k_tipo not in st.session_state:
        st.session_state[k_tipo] = ""
    if k_medidas not in st.session_state:
        st.session_state[k_medidas] = ""

    st.markdown(
        """
        <div style="background:#1E293B;border:1px solid #3B82F6;border-radius:8px;padding:6px 10px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;">
            <span style="font-weight:700;font-size:12px;color:#60A5FA;">🔍 SKU</span>
            <span style="font-size:10px;color:#34D399;font-weight:600;">🟢 Sheets</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_sku_in, c_sku_btn = st.columns([3.4, 1.2])
    with c_sku_in:
        sku_val = st.text_input(
            "SKU:",
            placeholder="SKU (ej. ADSDT2038220)",
            key=k_sku,
            label_visibility="collapsed",
        )
    with c_sku_btn:
        btn_buscar = st.button("⚡ Cargar", key=f"btn_search_sku_{version_key}", use_container_width=True)

    sku_clean = (sku_val or "").strip().upper()
    last_searched = st.session_state.get(k_last_searched, "")
    had_loaded = st.session_state.get(k_loaded) is not None

    if not sku_clean:
        if had_loaded:
            st.session_state[k_tipo] = ""
            st.session_state[k_medidas] = ""
        st.session_state[k_loaded] = None
        st.session_state[k_last_searched] = ""
    elif btn_buscar or (len(sku_clean) >= 3 and sku_clean != last_searched):
        st.session_state[k_last_searched] = sku_clean
        info = sheets_service.get_furniture_by_sku(sku_clean, force_refresh=bool(btn_buscar))
        if info:
            st.session_state[k_loaded] = info
            st.session_state[k_tipo] = info.get("tipo_mueble", "")
            st.session_state[k_medidas] = info.get("medidas", "")
        else:
            if had_loaded:
                st.session_state[k_tipo] = ""
                st.session_state[k_medidas] = ""
            st.session_state[k_loaded] = None

    data_loaded = st.session_state.get(k_loaded)
    if sku_clean and not data_loaded and st.session_state.get(k_last_searched) == sku_clean:
        st.warning(f"⚠️ SKU '{sku_clean}' no encontrado.")

    if data_loaded:
        st.markdown(
            f"""
            <div style="background:rgba(16,185,129,0.12);border:1px solid #10B981;border-radius:6px;padding:5px 10px;margin-bottom:8px;font-size:11.5px;color:#FFFFFF;">
                <b>✅ {data_loaded.get('sku')}</b> · {data_loaded.get('nombre', '')}
            </div>
            """,
            unsafe_allow_html=True,
        )

    c_tipo, c_med = st.columns([1, 1])
    with c_tipo:
        tipo_in = st.text_input("🛋️ Mueble:", key=k_tipo)
    with c_med:
        med_in = st.text_input("📐 Medidas:", key=k_medidas)

    return {
        "sku": sku_val.strip() if sku_val else "",
        "tipo_mueble": tipo_in.strip() if tipo_in else "",
        "medidas": med_in.strip() if med_in else "",
        "data_loaded": data_loaded,
    }

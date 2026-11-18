import streamlit as st
from services.sheets_service import sheets_service


def render_sku_autofill_bar(version_key: str, inline_header: bool = False):
    """Barra compacta de 1 línea para SKU, Tipo y Medidas (solo lectura de Google Sheets)."""
    k_sku = f"sku_input_{version_key}"
    k_tipo = f"field_tipo_{version_key}"
    k_medidas = f"field_medidas_{version_key}"
    k_loaded = f"sku_loaded_data_{version_key}"
    k_last_searched = f"sku_last_searched_{version_key}"

    if k_tipo not in st.session_state:
        st.session_state[k_tipo] = ""
    if k_medidas not in st.session_state:
        st.session_state[k_medidas] = ""

    c_sku, c_tipo, c_med = st.columns([1.0, 1.15, 1.55], vertical_alignment="center")
    with c_sku:
        sku_val = st.text_input(
            "SKU",
            placeholder="🔍 SKU",
            key=k_sku,
            label_visibility="collapsed",
        )

    sku_clean = (sku_val or "").strip().upper()
    last_searched = st.session_state.get(k_last_searched, "")
    had_loaded = st.session_state.get(k_loaded) is not None

    if not sku_clean:
        if had_loaded:
            st.session_state[k_tipo] = ""
            st.session_state[k_medidas] = ""
        st.session_state[k_loaded] = None
        st.session_state[k_last_searched] = ""
    elif len(sku_clean) >= 3 and sku_clean != last_searched:
        st.session_state[k_last_searched] = sku_clean
        info = sheets_service.get_furniture_by_sku(sku_clean, force_refresh=False)
        if info:
            st.session_state[k_loaded] = info
            st.session_state[k_tipo] = info.get("tipo_mueble", "")
            st.session_state[k_medidas] = info.get("medidas", "")
        else:
            if had_loaded:
                st.session_state[k_tipo] = ""
                st.session_state[k_medidas] = ""
            st.session_state[k_loaded] = None

    with c_tipo:
        tipo_in = st.text_input(
            "Mueble",
            placeholder="🛋️ Mueble",
            key=k_tipo,
            label_visibility="collapsed",
        )
    with c_med:
        med_in = st.text_input(
            "Medidas",
            placeholder="📐 Medidas (ej. 180x90x78)",
            key=k_medidas,
            label_visibility="collapsed",
        )

    return {
        "sku": sku_val.strip() if sku_val else "",
        "tipo_mueble": tipo_in.strip() if tipo_in else "",
        "medidas": med_in.strip() if med_in else "",
        "data_loaded": st.session_state.get(k_loaded),
    }

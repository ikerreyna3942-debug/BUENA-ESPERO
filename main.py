import streamlit as st
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    st.set_page_config(
        page_title="Estudio de Prompts e IA",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

from modules.prompt_studio_v1 import render_prompt_studio as render_v1
from modules.prompt_studio_v2 import render_prompt_studio_v2 as render_v2
from modules.prompt_studio_v3 import render_prompt_studio_v3 as render_v3
from modules.prompt_studio_v4 import render_prompt_studio_v4 as render_v4

def main():
    st.sidebar.markdown("### 🤖 ESTUDIO DE IA")
    st.sidebar.caption("Generador de Prompts y Perspectivas")
    
    st.sidebar.markdown("---")
    version = st.sidebar.radio(
        "📌 Versión del estudio:",
        ["V4 Ultimate (Nuevas Casillas)", "V3 Nivel Dios (Recomendado)", "V2 Optimizado", "V1 Clásica original"]
    )
    st.sidebar.markdown("---")
    
    # Navegación rápida entre aplicaciones de la suite
    st.sidebar.markdown("### 🌐 Suite de aplicaciones")
    st.sidebar.markdown("""
    * [PROMPT](https://buena-espero.onrender.com)
    * [BASE DE DATOS](https://docs.google.com/spreadsheets/d/1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg/edit?gid=876651849#gid=876651849)
    * [ALTA DE ODO](https://app-vkz2.onrender.com/)
    * [FOTOS BASE](https://docs.google.com/spreadsheets/d/1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg/edit?gid=876651849#gid=876651849)
    """)
    st.sidebar.markdown("---")
    
    if version == "V4 Ultimate (Nuevas Casillas)":
        render_v4()
    elif version == "V3 Nivel Dios (Recomendado)":
        render_v3()
    elif version == "V2 Optimizado":
        render_v2()
    else:
        render_v1()

if __name__ == "__main__":
    main()

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
from modules.prompt_studio_v5 import render_prompt_studio_v5 as render_v5

def main():
    st.sidebar.markdown("### 🤖 ESTUDIO DE IA")
    st.sidebar.caption("Generador de Prompts y Perspectivas")
    
    st.sidebar.markdown("---")
    version = st.sidebar.radio(
        "📌 Versión del estudio:",
        [
            "V5 Multi-Vistas Pro (1 Solo Prompt)",
            "V4 Ultimate (Nuevas Casillas)",
            "V3 Nivel Dios (Recomendado)",
            "V2 Optimizado",
            "V1 Clásica original"
        ]
    )
    st.sidebar.markdown("---")
    
    # Navegación rápida y accesos directos
    st.sidebar.markdown("### 🌐 Enlaces & Herramientas IA")
    st.sidebar.markdown("""
    * 📊 [Documento Alta Odoo (Sheets)](https://docs.google.com/spreadsheets/d/1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg/edit?gid=876651849#gid=876651849)
    * 🚀 [App Alta Odoo (Render)](https://app-1-3y7y.onrender.com/)
    * ⚡ [Google AI Studio (Elegir Cuenta)](https://accounts.google.com/AccountChooser?continue=https://aistudio.google.com/)
    * ♊ [Google Gemini (Elegir Cuenta)](https://accounts.google.com/AccountChooser?continue=https://gemini.google.com/app)
    * 🤖 [ChatGPT (DALL-E 3)](https://chatgpt.com/)
    * 📁 [Carpeta Fotos Final (Drive)](https://drive.google.com/drive/folders/1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B)
    """)
    st.sidebar.markdown("---")
    
    if version == "V5 Multi-Vistas Pro (1 Solo Prompt)":
        render_v5()
    elif version == "V4 Ultimate (Nuevas Casillas)":
        render_v4()
    elif version == "V3 Nivel Dios (Recomendado)":
        render_v3()
    elif version == "V2 Optimizado":
        render_v2()
    else:
        render_v1()

if __name__ == "__main__":
    main()

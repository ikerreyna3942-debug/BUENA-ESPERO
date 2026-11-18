import streamlit as st
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    st.set_page_config(
        page_title="Estudio IA",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass


def main():
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] {
            width: 185px !important;
            min-width: 185px !important;
        }
        section[data-testid="stSidebar"] .block-container {
            padding-top: 1rem !important;
            padding-left: 0.75rem !important;
            padding-right: 0.75rem !important;
        }
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] li {
            font-size: 12.5px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("#### 🤖 Estudio IA")
    version = st.sidebar.radio(
        "Versión:",
        ["V7 Actual", "V6", "V5", "V4", "V3", "V2", "V1"],
        index=0,
        key="sidebar_version",
        label_visibility="collapsed",
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
* 📊 [Sheets](https://docs.google.com/spreadsheets/d/1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg/edit?gid=876651849#gid=876651849)
* 🚀 [Alta Odoo](https://app-1-3y7y.onrender.com/)
* ⚡ [AI Studio](https://accounts.google.com/AccountChooser?continue=https://aistudio.google.com/)
* ♊ [Gemini](https://accounts.google.com/AccountChooser?continue=https://gemini.google.com/app)
* 🤖 [ChatGPT](https://chatgpt.com/)
* 📁 [Drive](https://drive.google.com/drive/folders/1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B)
"""
    )

    if version == "V7 Actual":
        from modules.prompt_studio_v7 import render_prompt_studio_v7
        render_prompt_studio_v7()
    elif version == "V6":
        from modules.prompt_studio_unified import render_prompt_studio_unified
        render_prompt_studio_unified()
    elif version == "V5":
        from modules.prompt_studio_v5 import render_prompt_studio_v5
        render_prompt_studio_v5()
    elif version == "V4":
        from modules.prompt_studio_v4 import render_prompt_studio_v4
        render_prompt_studio_v4()
    elif version == "V3":
        from modules.prompt_studio_v3 import render_prompt_studio_v3
        render_prompt_studio_v3()
    elif version == "V2":
        from modules.prompt_studio_v2 import render_prompt_studio_v2
        render_prompt_studio_v2()
    else:
        from modules.prompt_studio_v1 import render_prompt_studio
        render_prompt_studio()


if __name__ == "__main__":
    main()

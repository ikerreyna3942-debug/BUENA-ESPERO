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
        initial_sidebar_state="collapsed",
    )
except Exception:
    pass


def main():
    st.markdown(
        """
        <style>
        /* Ocultar barra lateral vertical y aprovechar 100% del ancho de pantalla */
        section[data-testid="stSidebar"],
        div[data-testid="collapsedControl"],
        button[kind="header"] {
            display: none !important;
        }
        header[data-testid="stHeader"] {
            height: 0px !important;
            min-height: 0px !important;
            background: transparent !important;
        }
        .block-container {
            max-width: 100% !important;
            padding-top: 0.5rem !important;
            padding-bottom: 0.8rem !important;
            padding-left: clamp(0.5rem, 1.5vw, 1.25rem) !important;
            padding-right: clamp(0.5rem, 1.5vw, 1.25rem) !important;
        }

        /* Encabezado superior adaptable */
        .top-nav-links {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: flex-end;
            gap: 6px;
        }
        .top-nav-links a {
            background: #1E293B;
            border: 1px solid #475569;
            color: #E2E8F0 !important;
            text-decoration: none !important;
            font-size: clamp(11px, 0.85vw, 12.5px);
            font-weight: 600;
            padding: 4px 9px;
            border-radius: 999px;
            white-space: nowrap;
            transition: border-color 0.15s ease, background 0.15s ease;
        }
        .top-nav-links a:hover {
            border-color: #38BDF8;
            background: #283548;
            color: #38BDF8 !important;
        }

        /* Adaptación fluida en pantallas medianas / ventana dividida / móvil */
        @media (max-width: 1050px) {
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: 240px !important;
                flex: 1 1 240px !important;
            }
            .top-nav-links {
                justify-content: flex-start;
            }
        }
        @media (max-width: 640px) {
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ENCABEZADO SUPERIOR HORIZONTAL (Sustituye al menú vertical lateral)
    nav_brand, nav_ver, nav_links = st.columns([1.0, 0.9, 3.1], vertical_alignment="center")
    with nav_brand:
        st.markdown(
            '<div style="font-size:clamp(16px,1.3vw,20px);font-weight:800;color:#38BDF8;white-space:nowrap;">'
            "🤖 Estudio IA"
            "</div>",
            unsafe_allow_html=True,
        )
    with nav_ver:
        version = st.selectbox(
            "Versión:",
            ["V7 Actual", "V6", "V5", "V4", "V3", "V2", "V1"],
            index=0,
            key="sidebar_version",
            label_visibility="collapsed",
        )
    with nav_links:
        st.markdown(
            """
            <div class="top-nav-links">
                <a href="https://docs.google.com/spreadsheets/d/1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg/edit?gid=876651849#gid=876651849" target="_blank">📊 Sheets</a>
                <a href="https://app-1-3y7y.onrender.com/" target="_blank">🚀 Alta Odoo</a>
                <a href="https://accounts.google.com/AccountChooser?continue=https://aistudio.google.com/" target="_blank">⚡ AI Studio</a>
                <a href="https://accounts.google.com/AccountChooser?continue=https://gemini.google.com/app" target="_blank">♊ Gemini</a>
                <a href="https://chatgpt.com/" target="_blank">🤖 ChatGPT</a>
                <a href="https://drive.google.com/drive/folders/1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B" target="_blank">📁 Drive</a>
            </div>
            """,
            unsafe_allow_html=True,
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

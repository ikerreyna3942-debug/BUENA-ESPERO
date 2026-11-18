import base64
import os
import sys
from pathlib import Path
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Credencial integrada automáticamente (sin pedir nada al usuario)
_DEFAULT_KEY = base64.b64decode(
    "QVEuQWI4Uk42TDJjOXI4b01jb1RvQTlJR1pTcGxFaDU2R3M5UzFBQ3JZQWRqN2thRkZWSFE="
).decode("utf-8")
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    try:
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            _s = _line.strip()
            if _s and not _s.startswith("#") and "=" in _s:
                _k, _v = _s.split("=", 1)
                _val = _v.strip().strip('"').strip("'")
                if _k.strip() and _val:
                    os.environ[_k.strip()] = _val
    except Exception:
        pass
_cur_env = os.environ.get("GEMINI_API_KEY", "").strip()
if not _cur_env or (_cur_env.startswith("AIza") and len(_cur_env) == 39):
    os.environ["GEMINI_API_KEY"] = _DEFAULT_KEY

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
            padding: 0.35rem 0.75rem 0.6rem 0.75rem !important;
        }
        .top-nav-links {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: flex-end;
            gap: 4px;
        }
        .top-nav-links a {
            background: #1E293B;
            border: 1px solid #334155;
            color: #CBD5E1 !important;
            text-decoration: none !important;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 7px;
            border-radius: 999px;
            white-space: nowrap;
        }
        .top-nav-links a:hover {
            border-color: #38BDF8;
            color: #38BDF8 !important;
        }
        @media (max-width: 640px) {
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    c_brand, c_ver, c_links = st.columns([0.75, 0.65, 3.6], vertical_alignment="center")
    with c_brand:
        st.markdown(
            '<div style="font-size:15px;font-weight:800;color:#38BDF8;white-space:nowrap;">🤖 Estudio</div>',
            unsafe_allow_html=True,
        )
    with c_ver:
        version = st.selectbox(
            "Versión:",
            ["V7", "V6", "V5", "V4", "V3", "V2", "V1"],
            index=0,
            key="sidebar_version",
            label_visibility="collapsed",
        )
    with c_links:
        st.markdown(
            """
            <div class="top-nav-links">
                <a href="https://docs.google.com/spreadsheets/d/1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg/edit?gid=876651849#gid=876651849" target="_blank">📊 Sheets</a>
                <a href="https://app-1-3y7y.onrender.com/" target="_blank">🚀 Odoo</a>
                <a href="https://accounts.google.com/AccountChooser?continue=https://aistudio.google.com/" target="_blank">⚡ AI Studio</a>
                <a href="https://accounts.google.com/AccountChooser?continue=https://gemini.google.com/app" target="_blank">♊ Gemini</a>
                <a href="https://chatgpt.com/" target="_blank">🤖 ChatGPT</a>
                <a href="https://drive.google.com/drive/folders/1lfq8VBF1q-Kg9m6_qd2GU5zxwEywYw_B" target="_blank">📁 Drive</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if version == "V7":
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

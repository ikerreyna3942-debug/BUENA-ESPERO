import base64
import os
import sys
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

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
if not _cur_env:
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


def get_zoom_lock_html() -> str:
    """Devuelve script compacto para bloquear pinch/wheel/keyboard zoom en Android, iOS y PC sin duplicar listeners."""
    return """
    <script>
    (function() {
        var win = window;
        try {
            if (window.parent && window.parent.document) {
                win = window.parent;
            }
        } catch (e) {
            win = window;
        }
        try {
            if (win.__buenaZoomLockInstalled) return;
            win.__buenaZoomLockInstalled = true;
            var doc = win.document;
            if (doc && doc.head) {
                var vpContent = "width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no, viewport-fit=cover";
                var meta = doc.querySelector('meta[name="viewport"]');
                if (!meta) {
                    meta = doc.createElement("meta");
                    meta.setAttribute("name", "viewport");
                    doc.head.appendChild(meta);
                }
                meta.setAttribute("content", vpContent);
            }
            var prevent = function(ev) {
                if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
            };
            win.addEventListener("gesturestart", prevent, { passive: false });
            win.addEventListener("gesturechange", prevent, { passive: false });
            win.addEventListener("gestureend", prevent, { passive: false });
            doc.addEventListener("touchstart", function(ev) {
                if (ev.touches && ev.touches.length > 1) prevent(ev);
            }, { passive: false });
            doc.addEventListener("touchmove", function(ev) {
                if (ev.touches && ev.touches.length > 1) prevent(ev);
            }, { passive: false });
            win.addEventListener("wheel", function(ev) {
                if (ev.ctrlKey || ev.metaKey) prevent(ev);
            }, { passive: false });
            win.addEventListener("keydown", function(ev) {
                if (ev.ctrlKey || ev.metaKey) {
                    var k = ev.key || "";
                    var c = ev.code || "";
                    if (
                        k === "+" || k === "=" || k === "-" || k === "_" || k === "0" ||
                        c === "NumpadAdd" || c === "NumpadSubtract" || c === "Numpad0"
                    ) {
                        prevent(ev);
                    }
                }
            }, { passive: false });
        } catch (err) {}
    })();
    </script>
    """


def main():
    st.markdown(
        """
        <style>
        html, body, .stApp {
            touch-action: pan-x pan-y !important;
            -webkit-text-size-adjust: 100% !important;
            text-size-adjust: 100% !important;
        }
        section[data-testid="stSidebar"],
        div[data-testid="collapsedControl"],
        button[kind="header"],
        header[data-testid="stHeader"] {
            display: none !important;
        }
        iframe[height="0"] {
            display: block !important;
            height: 0 !important;
            min-height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            border: 0 !important;
        }
        .block-container {
            max-width: 100% !important;
            padding: 0.35rem 0.55rem 0.5rem 0.55rem !important;
        }
        .top-nav-links {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: flex-end;
            gap: 3px;
        }
        .top-nav-links a {
            background: #1E293B;
            border: 1px solid #334155;
            color: #CBD5E1 !important;
            text-decoration: none !important;
            font-size: 10px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 999px;
            white-space: nowrap;
            line-height: 1.25;
        }
        .top-nav-links a.folder-pill {
            border-color: #0284C7;
            color: #7DD3FC !important;
        }
        .top-nav-links a:hover {
            border-color: #38BDF8;
            color: #FFFFFF !important;
        }
        /* Botones consistentes y sin recortes en todas las versiones (V1–V7) */
        .stButton > button,
        .stDownloadButton > button,
        div[data-testid="stPopover"] button {
            white-space: normal !important;
            word-break: normal !important;
            overflow-wrap: break-word !important;
            height: auto !important;
            min-height: 36px !important;
            line-height: 1.25 !important;
            padding: 6px 10px !important;
            border-radius: 7px !important;
            font-size: 12.5px !important;
            font-weight: 600 !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
        .stButton > button p,
        .stDownloadButton > button p,
        div[data-testid="stPopover"] button p {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: unset !important;
            line-height: 1.25 !important;
            margin: 0 !important;
        }
        section[data-testid="stFileUploaderDropzone"] {
            box-sizing: border-box !important;
            max-width: 100% !important;
        }
        section[data-testid="stFileUploaderDropzone"] > span {
            max-width: 100% !important;
            min-width: 0 !important;
        }
        section[data-testid="stFileUploaderDropzone"] button {
            max-width: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
        }
        /* Evitar auto-zoom de iOS Safari / iPadOS al enfocar campos en dispositivos táctiles */
        @media (pointer: coarse), (hover: none) and (max-width: 1024px) {
            input,
            textarea,
            select,
            div[data-baseweb="input"] input,
            div[data-baseweb="textarea"] textarea,
            div[data-baseweb="select"] input {
                font-size: 16px !important;
            }
        }
        @media (max-width: 640px) {
            .block-container {
                padding: 0.3rem 0.32rem 0.45rem 0.32rem !important;
            }
            .top-nav-links {
                justify-content: flex-start !important;
                flex-wrap: nowrap !important;
                overflow-x: auto !important;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: none;
                padding-bottom: 1px;
            }
            .top-nav-links::-webkit-scrollbar {
                display: none;
            }
            .top-nav-links a {
                font-size: 9.5px;
                padding: 2px 6px;
                flex-shrink: 0;
            }
            .stButton > button,
            .stDownloadButton > button,
            div[data-testid="stPopover"] button {
                font-size: 11.5px !important;
                min-height: 36px !important;
                padding: 5px 6px !important;
            }
            /* Paneles principales a 100% en celular sin romper filas internas compactas */
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 4px !important;
                max-width: 100% !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: 100% !important;
                max-width: 100% !important;
                flex: 1 1 100% !important;
                box-sizing: border-box !important;
            }
            /* Encabezado superior: App + Versión lado a lado en 1 fila, links debajo en 1 tira deslizable */
            div[data-testid="stHorizontalBlock"]:has(.top-nav-links) > div[data-testid="stColumn"]:nth-child(1) {
                min-width: 0 !important;
                flex: 1.35 1 52% !important;
            }
            div[data-testid="stHorizontalBlock"]:has(.top-nav-links) > div[data-testid="stColumn"]:nth-child(2) {
                min-width: 0 !important;
                flex: 0.85 1 36% !important;
            }
            div[data-testid="stHorizontalBlock"]:has(.top-nav-links) > div[data-testid="stColumn"]:nth-child(3) {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }
            /* Controles internos dentro de tarjetas/columnas: 2 columnas fluidas sin desbordar */
            div[data-testid="stColumn"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
            div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
                min-width: 0 !important;
                flex: 1 1 calc(50% - 4px) !important;
            }
            /* Fila de 3 botones / 3 controles compactos (ej. 🚀 Modo · ↘️ 3/4 Derecha · 🗑️ Borrar): 1 sola línea */
            div[data-testid="stColumn"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"]:nth-child(3):last-child),
            div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"]:nth-child(3):last-child) {
                flex-wrap: nowrap !important;
            }
            div[data-testid="stColumn"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"]:nth-child(3):last-child) > div[data-testid="stColumn"],
            div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"]:nth-child(3):last-child) > div[data-testid="stColumn"] {
                min-width: 0 !important;
                flex: 1 1 0% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    components.html(get_zoom_lock_html(), height=0)

    pending_app = st.session_state.pop("_pending_active_app", None)
    if pending_app in ("🤖 Prompts + IA", "🚀 Alta de Fotos"):
        st.session_state["unified_active_app"] = pending_app
    if st.session_state.get("unified_active_app") not in ("🤖 Prompts + IA", "🚀 Alta de Fotos"):
        st.session_state["unified_active_app"] = "🤖 Prompts + IA"

    c_app, c_ver, c_links = st.columns([1.15, 0.72, 3.13], vertical_alignment="center")
    with c_app:
        active_app = st.selectbox(
            "App:",
            ["🤖 Prompts + IA", "🚀 Alta de Fotos"],
            key="unified_active_app",
            label_visibility="collapsed",
        )
    with c_ver:
        if active_app == "🤖 Prompts + IA":
            ver_raw = st.selectbox(
                "Versión:",
                ["🤖 V7", "V6", "V5", "V4", "V3", "V2", "V1"],
                index=0,
                key="sidebar_version",
                label_visibility="collapsed",
            )
            version = "V7" if "V7" in ver_raw else ver_raw
        else:
            version = "V7"
            if st.button("← Prompts", use_container_width=True, key="btn_back_prompts"):
                st.session_state["_pending_active_app"] = "🤖 Prompts + IA"
                st.rerun()
    with c_links:
        st.markdown(
            """
            <div class="top-nav-links">
                <a class="folder-pill" href="https://drive.google.com/drive/folders/1Xc-gaDUJHNSd_XSTob3b39CNYoC9UreX" target="_blank">📁 RENDER</a>
                <a href="https://docs.google.com/spreadsheets/d/1ZCLZppO5AH06Wp2gVuxMoaeX3oJwVHgTjRZ7hlqb6eg/edit?gid=876651849#gid=876651849" target="_blank">📊 Sheets</a>
                <a class="folder-pill" href="https://accounts.google.com/AccountChooser?continue=https://aistudio.google.com/" target="_blank">⚡ AI Studio</a>
                <a href="https://accounts.google.com/AccountChooser?continue=https://gemini.google.com/app" target="_blank">♊ Gemini</a>
                <a href="https://chatgpt.com/" target="_blank">🤖 ChatGPT</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if active_app == "🚀 Alta de Fotos":
        from modules.alta_fotos_hub import render_alta_fotos_hub
        render_alta_fotos_hub()
        return

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

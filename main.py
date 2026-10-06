import streamlit as st
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

st.set_page_config(
    page_title="Estudio de Prompts e IA",
    page_icon="??",
    layout="wide",
    initial_sidebar_state="expanded"
)

from modules.prompt_studio_v3 import render_prompt_studio_v3

def main():
    render_prompt_studio_v3()

if __name__ == '__main__':
    main()

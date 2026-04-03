from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st  # type: ignore


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

st.set_page_config(
    page_title="Balcony Green",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

from balconygreen.auth_ui import render_app


render_app()

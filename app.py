from __future__ import annotations

import logging
import streamlit as st
# from dotenv import load_dotenv
# load_dotenv()

# Silence noisy library loggers that dump debug/info messages to the terminal
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("watchdog").setLevel(logging.WARNING)

from src.pages import create_assessment, dashboard, architecture

st.set_page_config(page_title="Meridant Matrix", layout="wide")

with st.sidebar:
    st.title("Meridant Matrix")
    st.caption("Capability Maturity Assessment Platform")
    page = st.radio(
    "Navigate",
    ["Dashboard", "Create Assessment", "Architecture"],
)

if page == "Dashboard":
    dashboard.render()
elif page == "Create Assessment":
    create_assessment.render()
elif page == "Architecture":
    architecture.render()

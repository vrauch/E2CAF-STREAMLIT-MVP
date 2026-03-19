from __future__ import annotations

import logging
import os

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# Silence noisy library loggers that dump debug/info messages to the terminal
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("watchdog").setLevel(logging.WARNING)

from src.pages import create_assessment, dashboard, architecture, admin_users, assessments

st.set_page_config(page_title="Meridant Matrix", layout="wide")

# ── Bootstrap 5.3 + brand styling ────────────────────────────────────────────
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  /* ── Buttons: Bootstrap btn-sm on all Streamlit button variants ── */
  .stButton > button,
  button[data-testid="baseButton-primary"],
  button[data-testid="baseButton-secondary"],
  button[data-testid="baseButton-tertiary"],
  button[data-testid^="baseButton-"] {
    font-family: 'Inter', -apple-system, sans-serif !important;
    font-size: .775rem !important;
    font-weight: 400 !important;
    line-height: 1.5 !important;
    padding: .25rem .6rem !important;
    border-radius: .2rem !important;
    min-height: unset !important;
    height: auto !important;
  }
  /* ── Sidebar dark theme ── */
  [data-testid="stSidebar"] { background-color: #0F2744; }
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] label,
  [data-testid="stSidebar"] span { color: #F9FAFB !important; }
  [data-testid="stSidebar"] .stRadio > div { gap: 0.25rem; }
  [data-testid="stSidebar"] .stButton > button,
  [data-testid="stSidebar"] button[data-testid^="baseButton-"] {
    background-color: #2563EB !important;
    color: #F9FAFB !important;
    border: none !important;
    border-radius: 6px !important;
    padding: .35rem .9rem !important;
    width: 100%;
  }
  [data-testid="stSidebar"] .stButton > button:hover,
  [data-testid="stSidebar"] button[data-testid^="baseButton-"]:hover {
    background-color: #1D4ED8 !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Authentication ────────────────────────────────────────────────────────────
# AUTH_CONFIG_PATH env var allows Fly.io deployment to read from /data/auth_config.yaml
# (the persistent volume).  Falls back to project root for local Docker dev.
_AUTH_CONFIG_PATH = os.getenv(
    "AUTH_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "auth_config.yaml"),
)

if not os.path.exists(_AUTH_CONFIG_PATH):
    st.error(
        f"**Auth config not found:** `{_AUTH_CONFIG_PATH}`\n\n"
        "Upload `auth_config.yaml` to the Fly.io volume:\n\n"
        "```\nfly machine start --app streamlit-mvp\n"
        "fly ssh sftp shell --app streamlit-mvp\n"
        "put auth_config.yaml /data/auth_config.yaml\n"
        "exit\nfly deploy\n```"
    )
    st.stop()

with open(_AUTH_CONFIG_PATH) as f:
    _auth_config = yaml.load(f, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    _auth_config["credentials"],
    _auth_config["cookie"]["name"],
    _auth_config["cookie"]["key"],
    _auth_config["cookie"]["expiry_days"],
)

authenticator.login()

if st.session_state.get("authentication_status") is False:
    st.error("Incorrect username or password.")
    st.stop()

if st.session_state.get("authentication_status") is None:
    st.stop()

# ── Authenticated — render app ────────────────────────────────────────────────
# Handle cross-page navigation BEFORE the radio renders so we can preset its value.
_nav_target = st.session_state.pop("_navigate_to", None)

with st.sidebar:
    st.markdown("""
<div style="display:flex;align-items:center;gap:10px;padding:0.25rem 0 1.25rem;
            border-bottom:1px solid rgba(249,250,251,0.12);margin-bottom:0.5rem;">
  <svg width="40" height="34" viewBox="0 0 40 34" xmlns="http://www.w3.org/2000/svg">
    <polyline points="0,32 11,6 20,20" fill="none" stroke="#F9FAFB" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"/>
    <polyline points="20,20 29,2 40,32" fill="none" stroke="#2563EB" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="4" y1="8" x2="36" y2="0" stroke="#2563EB" stroke-width="1"
          stroke-dasharray="2.5,2" stroke-linecap="round"/>
    <circle cx="11" cy="6" r="2" fill="none" stroke="#F9FAFB" stroke-width="1.5"/>
    <circle cx="29" cy="2" r="2" fill="#2563EB"/>
  </svg>
  <div>
    <div style="font-family:'Inter',-apple-system,sans-serif;font-size:1.05rem;
                font-weight:300;color:#F9FAFB;letter-spacing:0.08em;line-height:1.2;">meridant</div>
    <div style="font-family:'Inter',-apple-system,sans-serif;font-size:0.58rem;
                color:#93C5FD;letter-spacing:0.20em;text-transform:uppercase;line-height:1.4;">matrix</div>
  </div>
</div>
""", unsafe_allow_html=True)
    _admins = _auth_config.get("admins", [])
    _is_admin = st.session_state.get("username", "") in _admins
    _nav_pages = ["Dashboard", "Assessments", "Create Assessment", "Architecture"]
    if _is_admin:
        _nav_pages.append("Admin")
    # Preset the radio to the programmatic target (must happen before widget renders)
    if _nav_target and _nav_target in _nav_pages:
        st.session_state["_sidebar_nav"] = _nav_target
    page = st.radio(
        "Navigate",
        _nav_pages,
        label_visibility="collapsed",
        key="_sidebar_nav",
    )
    st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)
    # ── User info + logout ────────────────────────────────────────────────────
    display_name = st.session_state.get("name", st.session_state.get("username", ""))
    st.markdown(
        f'<div style="font-size:.72rem;color:#93C5FD;margin-top:1rem;'
        f'padding-top:.75rem;border-top:1px solid rgba(249,250,251,0.12);">'
        f'Signed in as<br>'
        f'<span style="color:#F9FAFB;font-weight:600">{display_name}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    authenticator.logout("Sign out", "sidebar")

# ── Store authenticated username in session for attribution ──────────────────
st.session_state.setdefault(
    "authenticated_username", st.session_state.get("username", "")
)

if page == "Dashboard":
    dashboard.render()
elif page == "Assessments":
    assessments.render()
elif page == "Create Assessment":
    create_assessment.render()
elif page == "Architecture":
    architecture.render()
elif page == "Admin":
    admin_users.render()

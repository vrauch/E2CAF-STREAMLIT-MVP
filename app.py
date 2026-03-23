from __future__ import annotations

import logging
import os

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# Silence noisy library loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("watchdog").setLevel(logging.WARNING)

from src.pages import create_assessment, dashboard, admin_users, assessments

st.set_page_config(page_title="Meridant Matrix", layout="wide", initial_sidebar_state="collapsed")

# - Brand CSS ---------------------------------
_brand_css_path = os.path.join(os.path.dirname(__file__), "assets", "meridant_brand.css")
_brand_css = open(_brand_css_path).read() if os.path.exists(_brand_css_path) else ""
st.markdown(f"<style>{_brand_css}</style>", unsafe_allow_html=True)

# - App CSS ----------------------------------
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
""", unsafe_allow_html=True)

_app_css_path = os.path.join(os.path.dirname(__file__), "assets", "app.css")
_app_css = open(_app_css_path).read() if os.path.exists(_app_css_path) else ""
st.markdown(f"<style>{_app_css}</style>", unsafe_allow_html=True)


# - Authentication -------------------------------
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

# - Brand header (login page - no nav yet) ------------------
_LOGO = """<svg width="48" height="36" viewBox="0 0 40 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <polyline points="0,32 11,6 20,20" fill="none" stroke="#F9FAFB" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
  <polyline points="20,20 29,2 40,32" fill="none" stroke="#2563EB" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="4" y1="8" x2="36" y2="0" stroke="#2563EB" stroke-width="1" stroke-dasharray="2.5,2" stroke-linecap="round"/>
  <circle cx="11" cy="6" r="2" fill="none" stroke="#F9FAFB" stroke-width="1.6"/>
  <circle cx="29" cy="2" r="2" fill="#2563EB"/>
</svg>"""

st.markdown(f"""
<div id="meridant-brand">
  {_LOGO}
  <div>
    <div class="m-wordmark">meridant</div>
    <div class="m-tagline">Map the gap.&nbsp;&nbsp;Chart the path.</div>
  </div>
</div>
""", unsafe_allow_html=True)

authenticator.login()

if st.session_state.get("authentication_status") is False:
    st.error("Incorrect username or password.")
    st.stop()

if st.session_state.get("authentication_status") is None:
    st.stop()

# - Authenticated -------------------------------

# Handle logout action from header link
if st.query_params.get("_action") == "logout":
    authenticator.logout("_", "unrendered")
    st.query_params.clear()
    st.rerun()

# Build nav pages
_admins = _auth_config.get("admins", [])
_is_admin = st.session_state.get("username", "") in _admins
_nav_pages = ["Dashboard", "Assessments", "Create Assessment"]
if _is_admin:
    _nav_pages.append("Admin")

# Handle cross-page navigation from session state (e.g. Resume Assessment)
_nav_target = st.session_state.pop("_navigate_to", None)
if _nav_target and _nav_target in _nav_pages:
    st.query_params["page"] = _nav_target
    st.rerun()

# Current page from URL
_page = st.query_params.get("page", "Dashboard")
if _page not in _nav_pages:
    _page = "Dashboard"

# Build nav HTML
_nav_items = ""
for _p in _nav_pages:
    _active = " active" if _page == _p else ""
    _url = "?page=" + _p.replace(" ", "+")
    _nav_items += f'<a href="{_url}" target="_self" class="m-nav-link{_active}">{_p}</a>'

_display_name = st.session_state.get("name", st.session_state.get("username", ""))

# Full brand header with nav + responsive hamburger
st.markdown(f"""
<div id="meridant-brand">
  {_LOGO}
  <div>
    <div class="m-wordmark">meridant</div>
    <div class="m-tagline">Map the gap.&nbsp;&nbsp;Chart the path.</div>
  </div>
  <nav class="m-nav">{_nav_items}</nav>
  <div class="m-user-area">
    <div class="m-user-info">
      <div class="m-user-label">Signed in as</div>
      <div class="m-user-name">{_display_name}</div>
    </div>
    <a href="?_action=logout" target="_self" class="m-signout">Sign out</a>
  </div>
  <div class="m-hamburger-wrap">
    <input type="checkbox" id="m-menu-toggle">
    <label for="m-menu-toggle" class="m-hamburger-label">
      <span></span><span></span><span></span>
    </label>
    <div class="m-nav-mobile">{_nav_items}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# - Store authenticated username for attribution ----------------
st.session_state.setdefault(
    "authenticated_username", st.session_state.get("username", "")
)

# - Brand footer (injected before page render so st.stop() in pages doesn't block it) --
st.markdown("""
<div id="meridant-footer">
  <span class="mf-wordmark">meridant</span>
  <div class="mf-sep"></div>
  <span class="mf-product">Meridant Matrix</span>
  <div class="mf-right">
    <span class="mf-copy">&copy; 2026 Meridant. All rights reserved.</span>
  </div>
</div>
""", unsafe_allow_html=True)

# - Route to page -------------------------------
if _page == "Dashboard":
    dashboard.render()
elif _page == "Assessments":
    assessments.render()
elif _page == "Create Assessment":
    create_assessment.render()
elif _page == "Admin":
    admin_users.render()

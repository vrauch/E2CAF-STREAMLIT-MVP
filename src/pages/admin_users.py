"""Admin page — user management + client management (visible to admins only)."""

from __future__ import annotations

import os
import re

import bcrypt
import streamlit as st
import yaml
from yaml.loader import SafeLoader

from src.meridant_client import get_client
from src.sql_templates import get_clients_with_count, update_client, merge_clients

# AUTH_CONFIG_PATH env var allows Fly.io deployment to read from /data/auth_config.yaml
# (the persistent volume).  Falls back to project root for local Docker dev.
_AUTH_CONFIG_PATH = os.getenv(
    "AUTH_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "auth_config.yaml"),
)


def _load_config() -> dict:
    with open(_AUTH_CONFIG_PATH) as f:
        return yaml.load(f, Loader=SafeLoader)


def _save_config(cfg: dict) -> None:
    with open(_AUTH_CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _render_clients_tab() -> None:
    db = get_client()
    clients = get_clients_with_count(db)

    # ── Merge panel (shown when a source client is selected) ───────────────────
    merge_source = st.session_state.get("admin_merge_source")
    if merge_source is not None:
        src = next((c for c in clients if c["id"] == merge_source), None)
        if src:
            st.warning(
                f"Merging **{src['client_name']}** (id={merge_source}, "
                f"{src['assessment_count']} assessments) into another client."
            )
            other_clients = [c for c in clients if c["id"] != merge_source]
            if other_clients:
                target_options = {c["client_name"]: c["id"] for c in other_clients}
                target_name = st.selectbox(
                    "Merge into", list(target_options.keys()), key="admin_merge_target"
                )
                target_id = target_options[target_name]
                mc1, mc2 = st.columns(2)
                with mc1:
                    if st.button("Confirm Merge", type="primary", use_container_width=True):
                        result = merge_clients(db, merge_source, target_id)
                        if result.get("error"):
                            st.error(f"Merge failed: {result['error']}")
                        else:
                            st.success(
                                f"Merged {src['client_name']} → {target_name}. "
                                f"{src['assessment_count']} assessment(s) reassigned."
                            )
                            st.session_state.pop("admin_merge_source", None)
                            st.rerun()
                with mc2:
                    if st.button("Cancel", use_container_width=True):
                        st.session_state.pop("admin_merge_source", None)
                        st.rerun()
            else:
                st.info("No other clients to merge into.")
                if st.button("Cancel"):
                    st.session_state.pop("admin_merge_source", None)
                    st.rerun()
            st.divider()

    # ── Client list ────────────────────────────────────────────────────────────
    if not clients:
        st.info("No clients found.")
    else:
        _hdr = st.columns([2.2, 1.3, 1.3, 1.2, 0.7, 0.7, 0.7])
        for lbl, col in zip(["Client Name", "Industry", "Sector", "Country", "Assessments", "", ""], _hdr):
            col.markdown(
                f'<span style="font-size:.7rem;color:#6B7280;text-transform:uppercase;letter-spacing:.1em">{lbl}</span>',
                unsafe_allow_html=True,
            )
        st.markdown('<hr style="margin:2px 0 6px;border-color:#E5E7EB;border-width:2px 0 0">', unsafe_allow_html=True)

        for c in clients:
            cid = c["id"]
            edit_key = f"edit_client_{cid}"
            row_cols = st.columns([2.2, 1.3, 1.3, 1.2, 0.7, 0.7, 0.7])
            row_cols[0].markdown(f'<span style="font-size:.85rem;font-weight:600">{c["client_name"]}</span>', unsafe_allow_html=True)
            row_cols[1].markdown(f'<span style="font-size:.8rem;color:#6B7280">{c["industry"] or "—"}</span>', unsafe_allow_html=True)
            row_cols[2].markdown(f'<span style="font-size:.8rem;color:#6B7280">{c["sector"] or "—"}</span>', unsafe_allow_html=True)
            row_cols[3].markdown(f'<span style="font-size:.8rem;color:#6B7280">{c["country"] or "—"}</span>', unsafe_allow_html=True)
            row_cols[4].markdown(f'<span style="font-size:.8rem">{c["assessment_count"]}</span>', unsafe_allow_html=True)
            with row_cols[5]:
                if st.button("Edit", key=f"edit_btn_{cid}"):
                    st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                    st.rerun()
            with row_cols[6]:
                if st.button("Merge", key=f"merge_btn_{cid}"):
                    st.session_state["admin_merge_source"] = cid
                    st.rerun()

            # Inline edit form
            if st.session_state.get(edit_key):
                with st.form(f"edit_form_{cid}", clear_on_submit=False):
                    ef1, ef2 = st.columns(2)
                    ef_name    = ef1.text_input("Client name", value=c["client_name"])
                    ef_industry = ef2.text_input("Industry", value=c["industry"] or "")
                    ef3, ef4 = st.columns(2)
                    ef_sector  = ef3.text_input("Sector", value=c["sector"] or "")
                    ef_country = ef4.text_input("Country", value=c["country"] or "")
                    save_col, cancel_col, _ = st.columns([1, 1, 4])
                    saved   = save_col.form_submit_button("Save", type="primary")
                    cancelled = cancel_col.form_submit_button("Cancel")
                if saved:
                    result = update_client(db, cid, ef_name, ef_industry, ef_sector, ef_country)
                    if result.get("error"):
                        st.error(f"Update failed: {result['error']}")
                    else:
                        st.success(f"Client **{ef_name}** updated.")
                        st.session_state.pop(edit_key, None)
                        st.rerun()
                if cancelled:
                    st.session_state.pop(edit_key, None)
                    st.rerun()

            st.markdown('<hr style="margin:3px 0;border-color:#F3F4F6;border-width:1px 0 0">', unsafe_allow_html=True)

    # ── Add client ─────────────────────────────────────────────────────────────
    st.divider()
    with st.expander("+ Add New Client"):
        with st.form("add_client_form", clear_on_submit=True):
            ac1, ac2 = st.columns(2)
            ac_name    = ac1.text_input("Client name *", placeholder="Acme Corporation")
            ac_industry = ac2.text_input("Industry", placeholder="Financial Services")
            ac3, ac4 = st.columns(2)
            ac_sector  = ac3.text_input("Sector", placeholder="Banking")
            ac_country = ac4.text_input("Country", placeholder="Australia")
            ac_submit  = st.form_submit_button("Add Client", type="primary")
        if ac_submit:
            if not ac_name.strip():
                st.error("Client name is required.")
            else:
                result = db.write(
                    "INSERT INTO Client (client_name, industry, sector, country) VALUES (?, ?, ?, ?)",
                    [ac_name.strip(), ac_industry.strip() or None, ac_sector.strip() or None, ac_country.strip() or None],
                )
                if result.get("error"):
                    st.error(f"Failed to add client: {result['error']}")
                else:
                    st.success(f"Client **{ac_name}** added.")
                    st.rerun()


def _render_framework_tab() -> None:
    db = get_client()

    # ── Framework selector ────────────────────────────────────────────────────
    fw_res = db.query(
        "SELECT id, framework_key, framework_name FROM Next_Framework ORDER BY id", []
    )
    frameworks = fw_res.get("rows", [])
    if not frameworks:
        st.info("No frameworks registered.")
        return

    fw_options = {f["framework_name"]: f["id"] for f in frameworks}
    selected_fw_name = st.selectbox("Framework", list(fw_options.keys()), key="admin_fw_sel")
    selected_fw_id = fw_options[selected_fw_name]

    # ── Version list for this framework (MMTF only has Next_FrameworkVersion data) ──
    ver_res = db.query(
        """
        SELECT id, version_tag, version_label, status, released_by,
               SUBSTR(released_on, 1, 10) AS released_on, notes
        FROM Next_FrameworkVersion
        ORDER BY id DESC
        """,
        []
    )
    versions = ver_res.get("rows", [])

    if not versions:
        st.info("No version history available for this framework.")
        return

    # ── Version selector dropdown ─────────────────────────────────────────────
    ver_options = {
        f"{v['version_tag']} — {v['version_label'] or ''} ({v['released_on'] or 'n/a'})": v["id"]
        for v in versions
    }
    selected_ver_label = st.selectbox(
        "Version", list(ver_options.keys()), key="admin_ver_sel"
    )
    selected_ver_id = ver_options[selected_ver_label]
    selected_ver = next(v for v in versions if v["id"] == selected_ver_id)

    # ── Version detail ────────────────────────────────────────────────────────
    status_color = "green" if selected_ver["status"] == "published" else "orange"
    c1, c2, c3 = st.columns(3)
    c1.metric("Version", selected_ver["version_tag"])
    c2.metric("Status", (selected_ver["status"] or "").capitalize())
    c3.metric("Released", selected_ver["released_on"] or "—")

    if selected_ver.get("notes"):
        st.caption(selected_ver["notes"])

    st.divider()

    # ── Change records for the selected version ───────────────────────────────
    cr_res = db.query(
        """
        SELECT cr.id, cr.change_category, cr.change_type, cr.record_label,
               cr.rationale, SUBSTR(cr.changed_on, 1, 10) AS changed_on, cr.changed_by
        FROM Next_ChangeRecord cr
        WHERE cr.version_id = ?
        ORDER BY cr.id
        """,
        [selected_ver_id]
    )
    changes = cr_res.get("rows", [])

    if not changes:
        st.info("No change records for this version.")
        return

    st.markdown(f"**{len(changes)} change record(s)**")

    TYPE_COLORS = {"ADD": "🟢", "UPDATE": "🔵", "REMOVE": "🔴"}

    for cr in changes:
        ctype = (cr.get("change_type") or "").upper()
        icon = TYPE_COLORS.get(ctype, "⚪")
        with st.expander(f"{icon} {ctype} — {cr.get('record_label', '')}"):
            cols = st.columns([1, 1, 1])
            cols[0].caption(f"**Category:** {cr.get('change_category', '—')}")
            cols[1].caption(f"**Date:** {cr.get('changed_on', '—')}")
            cols[2].caption(f"**By:** {cr.get('changed_by', '—')}")
            if cr.get("rationale"):
                st.write(cr["rationale"])


def render() -> None:
    st.title("Administration")

    tab_users, tab_clients, tab_framework = st.tabs(["Users", "Clients", "Framework"])

    with tab_framework:
        _render_framework_tab()

    with tab_clients:
        _render_clients_tab()

    with tab_users:
        cfg = _load_config()
        users: dict = cfg.get("credentials", {}).get("usernames", {})
        admins: list = cfg.get("admins", [])

        # ── Current users ──────────────────────────────────────────────────────────
        st.subheader("Current users")
        if users:
            for username, info in list(users.items()):
                col_name, col_email, col_role, col_del = st.columns([2, 3, 1.5, 1])
                col_name.markdown(
                    f"**{info.get('name', username)}**  \n"
                    f"<span style='font-size:.8rem;color:#6B7280'>{username}</span>",
                    unsafe_allow_html=True,
                )
                col_email.markdown(
                    f"<span style='font-size:.85rem'>{info.get('email', '—')}</span>",
                    unsafe_allow_html=True,
                )
                col_role.markdown(
                    "🔑 Admin" if username in admins else "User",
                    unsafe_allow_html=True,
                )
                # Prevent the only admin from deleting themselves
                is_last_admin = username in admins and sum(1 for u in admins if u in users) <= 1
                if is_last_admin:
                    col_del.markdown("<span style='font-size:.75rem;color:#6B7280'>protected</span>", unsafe_allow_html=True)
                elif col_del.button("Remove", key=f"del_{username}", type="secondary"):
                    st.session_state[f"confirm_del_{username}"] = True

                if st.session_state.get(f"confirm_del_{username}"):
                    st.warning(
                        f"Remove **{info.get('name', username)}** (`{username}`)? This cannot be undone."
                    )
                    c1, c2 = st.columns(2)
                    if c1.button("Yes, remove", key=f"confirm_yes_{username}", type="primary"):
                        del users[username]
                        if username in admins:
                            admins.remove(username)
                        cfg["credentials"]["usernames"] = users
                        cfg["admins"] = admins
                        _save_config(cfg)
                        st.success(f"User `{username}` removed.")
                        st.session_state.pop(f"confirm_del_{username}", None)
                        st.rerun()
                    if c2.button("Cancel", key=f"confirm_no_{username}"):
                        st.session_state.pop(f"confirm_del_{username}", None)
                        st.rerun()
        else:
            st.info("No users configured.")

        st.divider()

        # ── Add new user ────────────────────────────────────────────────────────────
        st.subheader("Add user")
        with st.form("add_user_form", clear_on_submit=True):
            col_u, col_n = st.columns(2)
            new_username = col_u.text_input(
                "Username", placeholder="jsmith",
                help="Lowercase, letters/numbers/underscores only"
            )
            new_name = col_n.text_input("Display name", placeholder="Jane Smith")

            col_e, col_p = st.columns(2)
            new_email = col_e.text_input("Email", placeholder="jsmith@example.com")
            new_password = col_p.text_input("Temporary password", type="password")

            new_is_admin = st.checkbox("Grant admin access")
            submitted = st.form_submit_button("Add user", type="primary")

        if submitted:
            errors = []
            if not new_username:
                errors.append("Username is required.")
            elif not re.match(r"^[a-z0-9_]+$", new_username):
                errors.append("Username must be lowercase letters, numbers, or underscores.")
            elif new_username in users:
                errors.append(f"Username `{new_username}` already exists.")
            if not new_name:
                errors.append("Display name is required.")
            if not new_password or len(new_password) < 8:
                errors.append("Password must be at least 8 characters.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt(12)).decode()
                users[new_username] = {
                    "name": new_name,
                    "email": new_email or "",
                    "password": hashed,
                }
                if new_is_admin and new_username not in admins:
                    admins.append(new_username)
                cfg["credentials"]["usernames"] = users
                cfg["admins"] = admins
                _save_config(cfg)
                st.success(
                    f"User **{new_name}** (`{new_username}`) added. "
                    "They can log in immediately — no restart required."
                )
                st.rerun()

        st.divider()

        # ── Change password ─────────────────────────────────────────────────────────
        st.subheader("Change password")
        with st.form("change_pw_form", clear_on_submit=True):
            target_user = st.selectbox("User", list(users.keys()))
            new_pw = st.text_input("New password", type="password")
            confirm_pw = st.text_input("Confirm password", type="password")
            pw_submitted = st.form_submit_button("Update password", type="primary")

        if pw_submitted:
            if not new_pw or len(new_pw) < 8:
                st.error("Password must be at least 8 characters.")
            elif new_pw != confirm_pw:
                st.error("Passwords do not match.")
            else:
                hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt(12)).decode()
                users[target_user]["password"] = hashed
                cfg["credentials"]["usernames"] = users
                _save_config(cfg)
                st.success(f"Password updated for `{target_user}`. Takes effect on next login.")

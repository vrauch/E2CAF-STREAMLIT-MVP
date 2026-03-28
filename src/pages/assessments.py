"""Assessments list page — view all assessments, resume in-progress ones."""

from __future__ import annotations

import math

import streamlit as st

from src.meridant_client import get_client
from src.assessment_store import list_assessments, load_assessment, update_assessment_status
from src.sql_templates import get_frameworks

PAGE_SIZE = 15


def _get_fw_labels(db) -> dict[int, str]:
    """Return {framework_id: framework_key} (short name) from Next_Framework table."""
    rows = get_frameworks(db)
    return {r["id"]: r["framework_key"] for r in rows} if rows else {1: "MMTF"}

# Column proportions — must match between header and data rows
_COL_W = [0.4, 1.7, 1.7, 2.3, 1.1, 1.1, 0.65, 0.9, 0.75, 0.75]
_COL_HEADERS = ["ID", "Client", "Engagement", "Use Case", "Framework", "Status", "Score", "Created", "", ""]

_HDR_STYLE = (
    "margin:0;padding:2px 0 6px;font-family:'JetBrains Mono',monospace;font-size:.7rem;font-weight:400;"
    "color:#6B7280;text-transform:uppercase;letter-spacing:.16em"
)


def _hydrate_and_redirect(assessment_id: int) -> None:
    """Load assessment from DB, populate session state, navigate to wizard."""
    from src.pages.create_assessment import _hydrate_session_from_db
    from src.assessment_store import load_recommendations

    db = get_client()
    data = load_assessment(db, assessment_id)
    if not data:
        st.error(f"Assessment {assessment_id} not found.")
        return

    # Clear stale wizard state before hydrating
    for key in [
        "wizard_step", "core_caps", "upstream_caps", "downstream_caps",
        "questions", "responses", "findings_saved", "findings_narrative",
        "roadmap_data", "recommendations", "domain_targets", "domains_covered",
        "responses_ai_scored", "confirm_regen_narrative", "confirm_regen_recs",
        "show_new_form",
    ]:
        st.session_state.pop(key, None)

    _hydrate_session_from_db(data)

    recs = load_recommendations(db, assessment_id)
    st.session_state.recommendations = recs if recs else None

    st.session_state["_navigate_to"] = "Create Assessment"
    st.rerun()


def _navigate_to_detail(assessment_id: int) -> None:
    """Navigate to the read-only assessment detail page."""
    st.session_state["_detail_assessment_id"] = assessment_id
    st.session_state["_navigate_to"] = "Assessment Detail"
    st.rerun()


def _header() -> None:
    cols = st.columns(_COL_W)
    for col, label in zip(cols, _COL_HEADERS):
        col.markdown(f'<p style="{_HDR_STYLE}">{label}</p>', unsafe_allow_html=True)
    st.markdown('<hr style="margin:0 0 4px;border-color:#E5E7EB;border-width:2px 0 0">', unsafe_allow_html=True)


def _row(r: dict, fw_labels: dict) -> None:
    aid       = r["id"]
    status    = r.get("status") or "in_progress"
    score     = r.get("overall_score")
    created   = (r.get("created_at") or "")[:10]
    client    = r.get("client_name") or "—"
    engage    = r.get("engagement_name") or "—"
    usecase   = r.get("use_case_name") or "—"
    fw_id     = r.get("framework_id") or 1
    fw        = fw_labels.get(fw_id, "Unknown")
    score_txt = f"{score:.1f}" if score is not None else "—"

    if status == "complete":
        badge = (
            '<span style="background:#0D9488;color:#fff;padding:2px 9px;'
            'border-radius:999px;font-size:.7rem;font-weight:600;white-space:nowrap">'
            'Complete</span>'
        )
    elif status == "archived":
        badge = (
            '<span style="background:#6B7280;color:#fff;padding:2px 9px;'
            'border-radius:999px;font-size:.7rem;font-weight:600;white-space:nowrap">'
            'Archived</span>'
        )
    else:
        badge = (
            '<span style="background:#2563EB;color:#fff;padding:2px 9px;'
            'border-radius:999px;font-size:.7rem;font-weight:600;white-space:nowrap">'
            'In Progress</span>'
        )

    cols = st.columns(_COL_W)
    cols[0].markdown(f'<span style="font-size:.8rem;color:#9CA3AF">{aid}</span>', unsafe_allow_html=True)
    cols[1].markdown(f'<span style="font-size:.85rem;font-weight:600">{client}</span>', unsafe_allow_html=True)
    cols[2].markdown(f'<span style="font-size:.8rem;color:#6B7280">{engage}</span>', unsafe_allow_html=True)
    cols[3].markdown(f'<span style="font-size:.8rem">{usecase}</span>', unsafe_allow_html=True)
    cols[4].markdown(f'<span style="font-size:.78rem;color:#6B7280">{fw}</span>', unsafe_allow_html=True)
    cols[5].markdown(badge, unsafe_allow_html=True)
    cols[6].markdown(f'<span style="font-size:.8rem">{score_txt}</span>', unsafe_allow_html=True)
    cols[7].markdown(f'<span style="font-size:.78rem;color:#9CA3AF">{created}</span>', unsafe_allow_html=True)

    # col[8] — View (all statuses)
    with cols[8]:
        if st.button("View", key=f"view_{aid}", type="secondary"):
            _navigate_to_detail(aid)

    # col[9] — Resume (in_progress) | Archive (complete) | — (archived)
    with cols[9]:
        if status == "in_progress":
            if st.button("Resume", key=f"resume_{aid}", type="primary"):
                _hydrate_and_redirect(aid)
        elif status == "complete":
            confirm_key = f"confirm_archive_{aid}"
            if st.session_state.get(confirm_key):
                # Confirm state — show Yes/No inline
                ca, cb = st.columns(2)
                with ca:
                    if st.button("Yes", key=f"arch_yes_{aid}", type="primary"):
                        update_assessment_status(get_client(), aid, "archived")
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                with cb:
                    if st.button("No", key=f"arch_no_{aid}"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
            else:
                if st.button("Archive", key=f"arch_{aid}"):
                    st.session_state[confirm_key] = True
                    st.rerun()


def render() -> None:
    st.title("Assessments")
    db   = get_client()
    fw_labels = _get_fw_labels(db)
    current_user = st.session_state.get("authenticated_username") or None

    # Determine include_archived from session state (set by selectbox on prior render)
    _status_val = st.session_state.get("af_st", "All")
    _include_archived = (_status_val == "Archived")
    rows = list_assessments(db, consultant_name=current_user, include_archived=_include_archived)

    if not rows:
        st.info("No assessments yet. Go to **Create Assessment** to start one.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([1.4, 1.4, 3])

    # Show all registered frameworks, not just those present in this assessment list
    all_fw = sorted(fw_labels.values())
    with fc1:
        fw_filter = st.selectbox("Framework", ["All"] + all_fw, key="af_fw")
    with fc2:
        status_filter = st.selectbox("Status", ["All", "In Progress", "Complete", "Archived"], key="af_st")
    with fc3:
        search = st.text_input(
            "Search", placeholder="Filter by client or engagement…", key="af_sq"
        )

    # Apply filters
    filtered = rows
    if fw_filter != "All":
        filtered = [r for r in filtered
                    if fw_labels.get(r.get("framework_id") or 1, "Unknown") == fw_filter]
    if status_filter == "In Progress":
        filtered = [r for r in filtered if (r.get("status") or "in_progress") == "in_progress"]
    elif status_filter == "Complete":
        filtered = [r for r in filtered if r.get("status") == "complete"]
    elif status_filter == "Archived":
        filtered = [r for r in filtered if r.get("status") == "archived"]
    if search.strip():
        term = search.strip().lower()
        filtered = [r for r in filtered if
                    term in (r.get("client_name") or "").lower() or
                    term in (r.get("engagement_name") or "").lower()]

    total = len(filtered)
    if total == 0:
        st.info("No assessments match the current filters.")
        return

    # ── Pagination ─────────────────────────────────────────────────────────────
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    st.session_state.setdefault("assessments_page", 1)
    page = max(1, min(st.session_state["assessments_page"], total_pages))

    page_rows = filtered[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    # Summary + nav row
    ic, nc = st.columns([3, 2])
    with ic:
        start = (page - 1) * PAGE_SIZE + 1
        end   = min(page * PAGE_SIZE, total)
        st.caption(f"Showing {start}–{end} of {total} assessments")
    with nc:
        if total_pages > 1:
            p1, p2, p3 = st.columns([1, 2, 1])
            with p1:
                if st.button("‹ Prev", disabled=(page == 1), key="pg_prev"):
                    st.session_state.assessments_page = page - 1
                    st.rerun()
            with p2:
                st.markdown(
                    f"<div style='text-align:center;padding-top:6px;font-size:.8rem;"
                    f"color:#9CA3AF'>Page {page} of {total_pages}</div>",
                    unsafe_allow_html=True,
                )
            with p3:
                if st.button("Next ›", disabled=(page == total_pages), key="pg_next"):
                    st.session_state.assessments_page = page + 1
                    st.rerun()

    # ── Table ──────────────────────────────────────────────────────────────────
    _header()
    for idx, r in enumerate(page_rows):
        _row(r, fw_labels)
        if idx < len(page_rows) - 1:
            st.markdown(
                '<hr style="margin:3px 0;border-color:#F3F4F6;border-width:1px 0 0">',
                unsafe_allow_html=True,
            )


"""Assessments list page — view all assessments, resume in-progress ones."""

from __future__ import annotations

import json

import streamlit as st

from src.meridant_client import get_client
from src.assessment_store import list_assessments, load_assessment


def _hydrate_and_redirect(assessment_id: int) -> None:
    """Load an assessment from DB, hydrate session state, and redirect to the wizard."""
    # Import here to avoid circular import
    from src.pages.create_assessment import _hydrate_session_from_db

    db = get_client()
    data = load_assessment(db, assessment_id)
    if not data:
        st.error(f"Assessment {assessment_id} not found.")
        return

    # Reset wizard state before hydrating
    for key in [
        "wizard_step", "core_caps", "upstream_caps", "downstream_caps",
        "questions", "responses", "findings_saved", "findings_narrative",
        "roadmap_data", "recommendations", "domain_targets", "domains_covered",
        "responses_ai_scored", "confirm_regen_narrative", "confirm_regen_recs",
    ]:
        st.session_state.pop(key, None)

    _hydrate_session_from_db(data)

    # Load recommendations if they exist (Step 5b)
    from src.assessment_store import load_recommendations
    recs = load_recommendations(db, assessment_id)
    st.session_state.recommendations = recs if recs else None

    st.session_state._navigate_to = "Create Assessment"
    st.rerun()


def render() -> None:
    st.title("Assessments")

    db = get_client()
    rows = list_assessments(db)

    if not rows:
        st.info("No assessments yet. Go to **Create Assessment** to start one.")
        return

    # ── Filters ──────────────────────────────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        status_filter = st.selectbox(
            "Status",
            ["All", "In Progress", "Complete"],
            label_visibility="collapsed",
        )
    with col_f2:
        search = st.text_input(
            "Search client",
            placeholder="Filter by client name…",
            label_visibility="collapsed",
        )

    # Apply filters
    filtered = rows
    if status_filter == "In Progress":
        filtered = [r for r in filtered if r.get("status") == "in_progress"]
    elif status_filter == "Complete":
        filtered = [r for r in filtered if r.get("status") == "complete"]
    if search.strip():
        term = search.strip().lower()
        filtered = [r for r in filtered if term in (r.get("client_name") or "").lower()]

    if not filtered:
        st.info("No assessments match the current filter.")
        return

    st.caption(f"Showing {len(filtered)} of {len(rows)} assessments")

    # ── Table header ─────────────────────────────────────────────────────────
    hdr = st.columns([0.6, 2, 2, 2, 1.4, 1.4, 1, 1.2, 1.4])
    for col, label in zip(hdr, ["ID", "Client", "Engagement", "Use Case",
                                  "Status", "Consultant", "Score",
                                  "Created", "Action"]):
        col.markdown(f"**{label}**")

    st.divider()

    # ── Rows ─────────────────────────────────────────────────────────────────
    for r in filtered:
        aid      = r["id"]
        status   = r.get("status", "in_progress")
        score    = r.get("overall_score")
        created  = (r.get("created_at") or "")[:10]

        # Status badge
        if status == "complete":
            badge = "🟢 Complete"
        else:
            badge = "🔵 In Progress"

        score_str = f"{score:.1f}" if score is not None else "—"

        cols = st.columns([0.6, 2, 2, 2, 1.4, 1.4, 1, 1.2, 1.4])
        cols[0].markdown(f"`{aid}`")
        cols[1].markdown(r.get("client_name") or "—")
        cols[2].markdown(r.get("engagement_name") or "—")
        cols[3].markdown(r.get("use_case_name") or "—")
        cols[4].markdown(badge)
        cols[5].markdown(r.get("consultant_name") or "—")
        cols[6].markdown(score_str)
        cols[7].markdown(created)

        with cols[8]:
            if status == "in_progress":
                if st.button("Resume →", key=f"resume_{aid}", type="primary"):
                    _hydrate_and_redirect(aid)
            else:
                if st.button("View →", key=f"view_{aid}"):
                    _hydrate_and_redirect(aid)

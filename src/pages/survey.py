"""Public survey page — async multi-respondent capability assessment.

Rendered from app.py BEFORE the authenticator check.  No sidebar, no auth.
URL: /?survey=<token>
"""

from __future__ import annotations

import streamlit as st

from src.meridant_client import get_client
from src.assessment_store import (
    _ensure_respondent_columns,
    load_assessment_by_token,
    get_survey_respondents,
    _RESP_INSERT_SQL,
)

ROLES = [
    "CTO / CIO",
    "CISO / Security Lead",
    "Engineering Lead",
    "Finance / FinOps Lead",
    "Operations Lead",
    "Product / Business Lead",
    "Consultant / Advisor",
    "Other",
]

_LIKERT = {
    1: ("1", "Not Defined",   "No formal process — ad hoc or absent"),
    2: ("2", "Informal",      "Exists but undocumented and inconsistent"),
    3: ("3", "Defined",       "Documented, consistent, widely followed"),
    4: ("4", "Governed",      "Measured, reviewed, and actively managed"),
    5: ("5", "Optimised",     "Continuously improved, best-in-class"),
}

_LOGO_SVG = """<svg width="36" height="28" viewBox="0 0 40 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <polyline points="0,32 11,6 20,20" fill="none" stroke="#F9FAFB" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
  <polyline points="20,20 29,2 40,32" fill="none" stroke="#2563EB" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="4" y1="8" x2="36" y2="0" stroke="#2563EB" stroke-width="1" stroke-dasharray="2.5,2" stroke-linecap="round"/>
  <circle cx="11" cy="6" r="2" fill="none" stroke="#F9FAFB" stroke-width="1.6"/>
  <circle cx="29" cy="2" r="2" fill="#2563EB"/>
</svg>"""

_HIDE_CHROME = """
<style>
[data-testid="stSidebar"]          {display:none}
#MainMenu                          {visibility:hidden}
footer                             {visibility:hidden}
header                             {visibility:hidden}
.stDeployButton                    {display:none}
[data-testid="stToolbar"]          {display:none}

/* ── Survey page layout ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

.block-container {
    max-width: 740px !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    padding-top: 0 !important;
    margin: 0 auto !important;
}

/* ── Survey header ── */
.survey-header {
    background: #0F2744;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    margin: -1rem -2rem 1.5rem -2rem;
    font-family: 'Inter', sans-serif;
}
.survey-header-left {
    display: flex;
    align-items: center;
    gap: 12px;
}
.survey-wordmark {
    font-size: 1.1rem;
    font-weight: 700;
    color: #F9FAFB;
    letter-spacing: 0.08em;
    text-transform: lowercase;
}
.survey-tagline {
    font-size: 0.65rem;
    color: #94A3B8;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-top: 1px;
}
.survey-header-right {
    font-size: 0.78rem;
    color: #94A3B8;
    text-align: right;
    line-height: 1.4;
}
.survey-header-right strong {
    color: #F9FAFB;
    font-weight: 600;
}

/* ── Survey footer ── */
.survey-footer {
    background: #0F2744;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 20px;
    margin: 2.5rem -2rem -1rem -2rem;
    font-family: 'Inter', sans-serif;
    font-size: 0.72rem;
}
.survey-footer-left {
    display: flex;
    align-items: center;
    gap: 10px;
    color: #94A3B8;
}
.survey-footer-wordmark {
    color: #F9FAFB;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: lowercase;
}
.survey-footer-sep {
    width: 1px;
    height: 12px;
    background: #374151;
}
.survey-footer-right {
    color: #6B7280;
    font-size: 0.68rem;
}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_questions(db, assessment_id: int) -> list[dict]:
    """Load canonical question rows (respondent_name IS NULL) ordered by capability."""
    _ensure_respondent_columns(db)
    res = db.query(
        """
        SELECT * FROM AssessmentResponse
        WHERE assessment_id = ?
          AND (respondent_name IS NULL OR respondent_name = '')
        ORDER BY capability_id, id
        """,
        [int(assessment_id)],
    )
    return res.get("rows", [])


def _answered_questions(db, assessment_id: int, respondent_name: str) -> set[int]:
    """Return set of canonical AssessmentResponse row IDs already answered by this respondent."""
    res = db.query(
        """
        SELECT ar_canon.id
        FROM AssessmentResponse ar_canon
        JOIN AssessmentResponse ar_resp
          ON ar_resp.assessment_id = ar_canon.assessment_id
         AND ar_resp.capability_id = ar_canon.capability_id
         AND ar_resp.question      = ar_canon.question
         AND ar_resp.respondent_name = ?
        WHERE ar_canon.assessment_id = ?
          AND (ar_canon.respondent_name IS NULL OR ar_canon.respondent_name = '')
        """,
        [respondent_name, int(assessment_id)],
    )
    return {r["id"] for r in res.get("rows", [])}


def _save_answer(
    db,
    assessment_id: int,
    question_row: dict,
    score: int,
    rationale: str,
    respondent_name: str,
    respondent_role: str,
) -> None:
    """Insert a single respondent answer row with a numeric Likert score."""
    db.write(
        _RESP_INSERT_SQL,
        [
            assessment_id,
            int(question_row["capability_id"]),
            question_row["capability_name"],
            question_row.get("domain") or "",
            question_row.get("subdomain") or "",
            question_row.get("capability_role") or "",
            question_row["question"],
            "maturity_1_5",     # always numeric from survey — no AI scoring needed
            score,
            None,               # answer field unused for Likert
            rationale.strip(),  # notes = optional rationale text
            respondent_name,
            respondent_role,
        ],
    )


def _group_by_capability(questions: list[dict]) -> list[dict]:
    """Group question rows by capability_id."""
    groups: list[dict] = []
    seen: dict[int, int] = {}
    for q in questions:
        cid = q["capability_id"]
        if cid not in seen:
            seen[cid] = len(groups)
            groups.append({
                "cap_id":    cid,
                "cap_name":  q["capability_name"],
                "domain":    q.get("domain") or "",
                "subdomain": q.get("subdomain") or "",
                "questions": [],
            })
        groups[seen[cid]]["questions"].append(q)
    return groups


# ─────────────────────────────────────────────────────────────────────────────
# Static screens
# ─────────────────────────────────────────────────────────────────────────────

def _hide_chrome() -> None:
    st.markdown(_HIDE_CHROME, unsafe_allow_html=True)


def _render_header(assessment: dict | None = None) -> None:
    client_name = (assessment or {}).get("client_name") or ""
    engagement  = (assessment or {}).get("engagement_name") or ""
    right_html  = ""
    if client_name:
        right_html = f"<strong>{client_name}</strong>"
        if engagement:
            right_html += f"<br>{engagement}"
    st.markdown(
        f"""
        <div class="survey-header">
          <div class="survey-header-left">
            {_LOGO_SVG}
            <div>
              <div class="survey-wordmark">meridant</div>
              <div class="survey-tagline">Map the gap.&nbsp;&nbsp;Chart the path.</div>
            </div>
          </div>
          {"<div class='survey-header-right'>" + right_html + "</div>" if right_html else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_footer() -> None:
    st.markdown(
        """
        <div class="survey-footer">
          <div class="survey-footer-left">
            <span class="survey-footer-wordmark">meridant</span>
            <div class="survey-footer-sep"></div>
            <span>Meridant Matrix</span>
          </div>
          <div class="survey-footer-right">&copy; 2026 Meridant. All rights reserved.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_entry_screen(assessment: dict) -> None:
    _hide_chrome()
    _render_header(assessment)
    client_name = assessment.get("client_name") or "your organisation"
    engagement  = assessment.get("engagement_name") or "this engagement"

    st.markdown("## Capability Assessment Survey")
    st.markdown(
        f"You have been invited to complete a capability maturity assessment for "
        f"**{client_name}** ({engagement}).\n\n"
        "For each question you will be asked to rate your organisation's maturity on a "
        "**1–5 scale** and optionally explain your rating. "
        "Your responses are saved as you go — you can close this window and return at any time."
    )
    st.divider()

    name = st.text_input("Your name", placeholder="e.g. Sarah Chen")
    role = st.selectbox("Your role", ROLES)

    col_btn, _ = st.columns([2, 5])
    with col_btn:
        if st.button("Start survey →", type="primary", disabled=not name.strip(), use_container_width=True):
            st.session_state["survey_respondent_name"] = name.strip()
            st.session_state["survey_respondent_role"] = role
            st.session_state["survey_cap_idx"]         = 0
            st.session_state["survey_q_idx"]           = 0
            st.session_state["survey_history"]         = []
            st.rerun()
    _render_footer()


def _render_already_completed(assessment: dict) -> None:
    _hide_chrome()
    _render_header(assessment)
    st.success("✅  You have already completed this survey. Thank you for your input!")
    st.markdown(
        f"**{assessment.get('client_name', '')}** — {assessment.get('engagement_name', '')}"
    )
    _render_footer()


def _render_completion_screen(respondent_name: str, total_qs: int, assessment: dict | None = None) -> None:
    _hide_chrome()
    _render_header(assessment)
    st.balloons()
    st.success(f"🎉  All done, {respondent_name}! Your {total_qs} responses have been submitted.")
    st.markdown(
        "The assessment team will review all respondent inputs and generate findings. "
        "You can close this window."
    )
    _render_footer()


def _render_closed_screen() -> None:
    _hide_chrome()
    _render_header()
    st.warning("This survey has been closed. No further responses are being accepted.")
    _render_footer()


def _render_invalid_screen() -> None:
    _hide_chrome()
    _render_header()
    st.error("This survey link is invalid or has expired.")
    _render_footer()


# ─────────────────────────────────────────────────────────────────────────────
# Main survey UI
# ─────────────────────────────────────────────────────────────────────────────

def _render_survey(db, assessment: dict, questions: list[dict]) -> None:
    _hide_chrome()
    _render_header(assessment)

    assessment_id   = assessment["id"]
    respondent_name = st.session_state["survey_respondent_name"]
    respondent_role = st.session_state["survey_respondent_role"]

    groups     = _group_by_capability(questions)
    total_caps = len(groups)
    total_qs   = len(questions)

    cap_idx = st.session_state.get("survey_cap_idx", 0)
    q_idx   = st.session_state.get("survey_q_idx", 0)

    # ── Completion check ──────────────────────────────────────────────────────
    if cap_idx >= total_caps:
        _render_completion_screen(respondent_name, total_qs, assessment)
        return

    current_group = groups[cap_idx]
    current_qs    = current_group["questions"]
    cap_name      = current_group["cap_name"]
    domain        = current_group["domain"]
    subdomain     = current_group["subdomain"]
    current_q     = current_qs[q_idx]

    # Count answered from DB (source of truth; avoids double-counting on resume)
    answered_ids   = _answered_questions(db, assessment_id, respondent_name)
    answered_count = len(answered_ids)

    # ── Respondent name (below header, subtle) ────────────────────────────────
    st.markdown(
        f"<div style='text-align:right;color:#6B7280;font-size:.8rem;margin-top:-8px;margin-bottom:12px'>"
        f"👤 {respondent_name}</div>",
        unsafe_allow_html=True,
    )

    # ── Progress bar ─────────────────────────────────────────────────────────
    progress_pct = answered_count / total_qs if total_qs else 0
    st.progress(progress_pct)

    cap_num = cap_idx + 1
    q_num   = q_idx + 1
    q_in_cap = len(current_qs)

    st.markdown(
        f"<div style='display:flex;justify-content:space-between;"
        f"font-size:.78rem;color:#6B7280;margin-top:-6px;margin-bottom:12px'>"
        f"<span>Capability <b>{cap_num}</b> of <b>{total_caps}</b>"
        f" &nbsp;·&nbsp; Question <b>{q_num}</b> of <b>{q_in_cap}</b></span>"
        f"<span><b>{answered_count}</b> / <b>{total_qs}</b> answered "
        f"({int(progress_pct * 100)}%)</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Capability context card ───────────────────────────────────────────────
    breadcrumb = " › ".join(filter(None, [domain, subdomain]))
    st.markdown(
        f"""
        <div style="background:#F3F4F6;border-left:4px solid #2563EB;
                    border-radius:6px;padding:10px 14px;margin-bottom:16px">
          <div style="font-size:.72rem;color:#6B7280;text-transform:uppercase;
                      letter-spacing:.08em;margin-bottom:2px">{breadcrumb}</div>
          <div style="font-size:1rem;font-weight:600;color:#0F2744">{cap_name}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Question ─────────────────────────────────────────────────────────────
    st.markdown(f"**{current_q['question']}**")

    # ── Likert scale ─────────────────────────────────────────────────────────
    # Key is unique per question so the widget resets when we advance
    q_key = f"survey_likert_{current_q['id']}"

    score_choice = st.radio(
        "Select your rating:",
        options=[1, 2, 3, 4, 5],
        format_func=lambda v: f"{_LIKERT[v][0]} — {_LIKERT[v][1]}  ·  *{_LIKERT[v][2]}*",
        index=None,
        key=q_key,
        horizontal=False,
    )

    # ── Rationale ────────────────────────────────────────────────────────────
    r_key      = f"survey_rationale_{current_q['id']}"
    rationale  = st.text_area(
        "Why did you choose this rating? *(optional — add context or evidence)*",
        key=r_key,
        height=80,
        placeholder="e.g. We have a documented process but it's only followed by some teams…",
    )

    # ── Submit ───────────────────────────────────────────────────────────────
    col_btn, col_skip = st.columns([3, 2])
    with col_btn:
        submitted = st.button(
            "Save & continue →",
            type="primary",
            disabled=score_choice is None,
            use_container_width=True,
            key=f"survey_submit_{current_q['id']}",
        )
    with col_skip:
        st.caption("Select a rating to continue.")

    if submitted and score_choice is not None:
        _save_answer(
            db,
            assessment_id,
            current_q,
            score_choice,
            rationale or "",
            respondent_name,
            respondent_role,
        )

        # Record in local history for display
        history = st.session_state.get("survey_history", [])
        label   = f"{_LIKERT[score_choice][0]} — {_LIKERT[score_choice][1]}"
        history.append({
            "cap_name":  cap_name,
            "question":  current_q["question"],
            "score":     score_choice,
            "label":     label,
            "rationale": rationale or "",
        })
        st.session_state["survey_history"] = history

        # Advance indices
        new_q_idx   = q_idx + 1
        new_cap_idx = cap_idx
        if new_q_idx >= len(current_qs):
            new_cap_idx = cap_idx + 1
            new_q_idx   = 0

        st.session_state["survey_cap_idx"] = new_cap_idx
        st.session_state["survey_q_idx"]   = new_q_idx
        st.rerun()

    # ── Answered history (collapsed, scrollable) ──────────────────────────────
    history = st.session_state.get("survey_history", [])
    if history:
        st.divider()
        with st.expander(f"Your answers so far ({len(history)})", expanded=False):
            for item in reversed(history):
                score_val = item["score"]
                colour    = {1: "#DC2626", 2: "#D97706", 3: "#2563EB",
                             4: "#0D9488", 5: "#16A34A"}.get(score_val, "#374151")
                rationale_text = (
                    f"<br><span style='color:#6B7280;font-size:.78rem'>"
                    f"💬 {item['rationale']}</span>"
                    if item["rationale"] else ""
                )
                st.markdown(
                    f"<div style='border-left:3px solid {colour};padding:6px 10px;"
                    f"margin-bottom:8px;background:#F9FAFB;border-radius:4px'>"
                    f"<div style='font-size:.72rem;color:#6B7280'>{item['cap_name']}</div>"
                    f"<div style='font-size:.85rem;color:#111827'>{item['question']}</div>"
                    f"<div style='font-weight:600;color:{colour}'>{item['label']}</div>"
                    f"{rationale_text}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    _render_footer()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def render(token: str) -> None:
    """Called from app.py before the auth check."""
    db         = get_client()
    assessment = load_assessment_by_token(db, token)

    if not assessment:
        _render_invalid_screen()
        return

    if (assessment.get("survey_status") or "") == "closed":
        _render_closed_screen()
        return

    respondent_name = st.session_state.get("survey_respondent_name", "").strip()
    if not respondent_name:
        _render_entry_screen(assessment)
        return

    questions = _load_questions(db, assessment["id"])
    if not questions:
        st.error("This survey has no questions loaded yet. Please check back later.")
        return

    answered_ids = _answered_questions(db, assessment["id"], respondent_name)
    if len(answered_ids) >= len(questions):
        _render_already_completed(assessment)
        return

    # Resume positioning (first load after re-entry)
    if "survey_cap_idx" not in st.session_state:
        _restore_position(questions, answered_ids)

    _render_survey(db, assessment, questions)


def _restore_position(questions: list[dict], answered_ids: set[int]) -> None:
    """Set cap_idx / q_idx to the first unanswered question on re-entry."""
    groups = _group_by_capability(questions)

    for cap_idx, group in enumerate(groups):
        for q_idx, q in enumerate(group["questions"]):
            if q["id"] not in answered_ids:
                st.session_state["survey_cap_idx"] = cap_idx
                st.session_state["survey_q_idx"]   = q_idx
                st.session_state["survey_history"]  = []   # can't reconstruct on re-entry
                return

    # All answered
    st.session_state["survey_cap_idx"] = len(groups)
    st.session_state["survey_q_idx"]   = 0
    st.session_state["survey_history"]  = []

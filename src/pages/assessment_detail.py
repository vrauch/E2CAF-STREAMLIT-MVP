"""Assessment detail — read-only view of a completed assessment."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from src.meridant_client import get_client
from src.assessment_store import (
    load_assessment,
    load_findings,
    load_recommendations,
    load_roadmap,
    aggregate_survey_rationale,
    get_respondent_voices,
    _ensure_survey_columns,
    _ensure_synthesis_column,
)
from src.heatmap import render_heatmap_html, generate_heatmap_excel
from src.roadmap import render_roadmap_gantt_html, generate_roadmap_excel, TIMELINE_UNITS

try:
    from src.report_writer import generate_word_report
    _WORD_AVAILABLE = True
except ImportError:
    _WORD_AVAILABLE = False

try:
    from src.report_presenter import generate_pptx_report
    _PPTX_AVAILABLE = True
except ImportError:
    _PPTX_AVAILABLE = False


def _status_badge(status: str) -> str:
    if status == "complete":
        return (
            '<span style="background:#0D9488;color:#fff;padding:3px 12px;'
            'border-radius:999px;font-size:.75rem;font-weight:600">Complete</span>'
        )
    if status == "archived":
        return (
            '<span style="background:#6B7280;color:#fff;padding:3px 12px;'
            'border-radius:999px;font-size:.75rem;font-weight:600">Archived</span>'
        )
    return (
        '<span style="background:#2563EB;color:#fff;padding:3px 12px;'
        'border-radius:999px;font-size:.75rem;font-weight:600">In Progress</span>'
    )


def render(assessment_id: int | None) -> None:
    if not assessment_id:
        st.error("No assessment selected.")
        if st.button("← Back to Assessments"):
            st.session_state["_navigate_to"] = "Assessments"
            st.rerun()
        return

    db = get_client()
    data = load_assessment(db, assessment_id)
    if not data:
        st.error(f"Assessment {assessment_id} not found.")
        if st.button("← Back to Assessments"):
            st.session_state["_navigate_to"] = "Assessments"
            st.rerun()
        return

    a = data["assessment"]
    client_name  = a.get("client_name") or "—"
    engagement   = a.get("engagement_name") or "—"
    use_case     = a.get("use_case_name") or "—"
    status       = a.get("status") or "in_progress"
    score        = a.get("overall_score")
    created      = (a.get("created_at") or "")[:10]
    narrative    = a.get("findings_narrative") or ""
    consultant   = a.get("consultant_name") or ""

    findings      = load_findings(db, assessment_id)
    dom_findings  = findings["domain"]
    cap_findings  = findings["capability"]
    recommendations = load_recommendations(db, assessment_id)
    roadmap_record  = load_roadmap(db, assessment_id)

    # Load survey rationale if this assessment used the async survey path
    _ensure_survey_columns(db)
    _ensure_synthesis_column(db)
    _survey_rationale: dict[int, str] = {}
    try:
        _survey_rationale = aggregate_survey_rationale(db, assessment_id)
    except Exception:
        pass

    # Load AI-synthesised stakeholder perspectives (if generated)
    _respondent_synthesis: str = a.get("respondent_synthesis") or ""

    # Build dom_scores for heatmap (same shape as Step 5)
    dom_scores = [
        {
            "domain":    f["domain"],
            "avg_score": f["avg_score"],
            "target":    f.get("target_maturity") or 3,
        }
        for f in dom_findings
    ]

    score_txt = f"{score:.1f}" if score is not None else "—"

    # ── Back link ──────────────────────────────────────────────────────────────
    if st.button("← Back to Assessments"):
        st.session_state["_navigate_to"] = "Assessments"
        st.rerun()

    # ── Header bar ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;
                    padding:16px 20px;margin:8px 0 16px;display:flex;flex-wrap:wrap;gap:20px;
                    align-items:center">
          <div>
            <div style="font-size:.7rem;color:#9CA3AF;text-transform:uppercase;letter-spacing:.1em">Client</div>
            <div style="font-weight:700;font-size:1.05rem;color:#111827">{client_name}</div>
          </div>
          <div>
            <div style="font-size:.7rem;color:#9CA3AF;text-transform:uppercase;letter-spacing:.1em">Engagement</div>
            <div style="font-size:.9rem;color:#374151">{engagement}</div>
          </div>
          <div>
            <div style="font-size:.7rem;color:#9CA3AF;text-transform:uppercase;letter-spacing:.1em">Use Case</div>
            <div style="font-size:.9rem;color:#374151">{use_case}</div>
          </div>
          <div style="margin-left:auto;display:flex;gap:16px;align-items:center">
            {_status_badge(status)}
            <div style="background:#0F2744;color:#fff;padding:4px 14px;border-radius:8px;
                        font-size:1rem;font-weight:700">{score_txt}</div>
          </div>
          <div style="font-size:.75rem;color:#9CA3AF">{created}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_summary, tab_domains, tab_recs, tab_export = st.tabs(
        ["Executive Summary", "Domain Findings", "Recommendations", "Export"]
    )

    # ── Tab 1 — Executive Summary ─────────────────────────────────────────────
    with tab_summary:
        # Stakeholder perspectives synthesis (survey assessments only)
        if _respondent_synthesis:
            st.markdown(
                f"<div style='background:#EFF6FF;border-left:4px solid #2563EB;"
                f"border-radius:6px;padding:14px 18px;margin-bottom:16px'>"
                f"<div style='font-size:.72rem;color:#2563EB;font-weight:600;"
                f"text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px'>"
                f"🗣️ Stakeholder perspectives</div>"
                f"<div style='color:#0F2744;font-size:.92rem;line-height:1.6'>{_respondent_synthesis}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        if narrative:
            st.markdown(narrative)
        else:
            st.info("No executive summary available. Generate one via the Assessment wizard (Step 5).")

        if consultant:
            st.caption(f"Assessed by: {consultant} · {created}")

    # ── Tab 2 — Domain Findings ───────────────────────────────────────────────
    with tab_domains:
        if dom_scores:
            heatmap_html = render_heatmap_html(dom_scores)
            components.html(heatmap_html, height=380, scrolling=True)
        else:
            st.info("No domain findings. Save findings in Step 5 of the wizard.")

        if dom_findings:
            st.divider()
            st.subheader("Domain Gap Summary")
            _hdr = st.columns([2.5, 1, 1, 1, 1])
            for _lbl, _col in zip(["Domain", "Avg Score", "Target", "Gap", "Risk"], _hdr):
                _col.markdown(
                    f'<span style="font-size:.7rem;color:#6B7280;text-transform:uppercase;letter-spacing:.1em">{_lbl}</span>',
                    unsafe_allow_html=True,
                )
            st.markdown('<hr style="margin:2px 0 6px;border-color:#E5E7EB">', unsafe_allow_html=True)
            _RISK_ORDER = {"🔴 High": 0, "🟡 Medium": 1, "🟢 Low": 2}
            _RISK_COLOR = {"🔴 High": "#DC2626", "🟡 Medium": "#D97706", "🟢 Low": "#16A34A"}
            for f in sorted(dom_findings, key=lambda x: (
                _RISK_ORDER.get(x.get("risk_level") or "", 9),
                -(x.get("gap") or 0),
            )):
                _rc = st.columns([2.5, 1, 1, 1, 1])
                gap     = f.get("gap") or 0
                risk    = f.get("risk_level") or "—"
                avg     = f.get("avg_score")
                target  = f.get("target_maturity")
                risk_color = _RISK_COLOR.get(f.get("risk_level") or "", "#6B7280")
                _rc[0].markdown(f'<span style="font-size:.85rem;font-weight:600">{f.get("domain","")}</span>', unsafe_allow_html=True)
                _rc[1].markdown(f'<span style="font-size:.85rem">{f"{avg:.1f}" if avg is not None else "—"}</span>', unsafe_allow_html=True)
                _rc[2].markdown(f'<span style="font-size:.85rem">{target if target else "—"}</span>', unsafe_allow_html=True)
                _rc[3].markdown(f'<span style="font-size:.85rem;color:#DC2626;font-weight:600">{gap:.1f}</span>', unsafe_allow_html=True)
                _rc[4].markdown(f'<span style="font-size:.8rem;color:{risk_color};font-weight:600">{risk}</span>', unsafe_allow_html=True)

        if cap_findings:
            st.divider()
            with st.expander(f"Capability Detail ({len(cap_findings)} capabilities)", expanded=False):
                _ch = st.columns([2.5, 1.5, 1, 1, 1, 1])
                for _lbl, _col in zip(["Capability", "Domain", "Score", "Target", "Gap", "Role"], _ch):
                    _col.markdown(
                        f'<span style="font-size:.7rem;color:#6B7280;text-transform:uppercase;letter-spacing:.1em">{_lbl}</span>',
                        unsafe_allow_html=True,
                    )
                st.markdown('<hr style="margin:2px 0 4px;border-color:#E5E7EB">', unsafe_allow_html=True)
                _ROLE_ORDER = {"Core": 0, "Upstream": 1, "Downstream": 2}
                _DISAGREEMENT_THRESHOLD = 1.0
                for cf in sorted(cap_findings, key=lambda x: (
                    _ROLE_ORDER.get(x.get("capability_role") or "", 9),
                    -(x.get("gap") or 0),
                )):
                    _std_dev = cf.get("score_std_dev")
                    _n_resp  = cf.get("respondent_count")
                    _disagree = _std_dev is not None and _std_dev >= _DISAGREEMENT_THRESHOLD
                    _flag = (
                        f' <span style="color:#D97706;font-size:.75rem" title="{_n_resp} respondents · σ={_std_dev:.1f} (High disagreement)">⚠️</span>'
                        if _disagree else ""
                    )
                    _cr = st.columns([2.5, 1.5, 1, 1, 1, 1])
                    _cr[0].markdown(
                        f'<span style="font-size:.8rem">{cf.get("capability_name","")}{_flag}</span>',
                        unsafe_allow_html=True,
                    )
                    _cr[1].markdown(f'<span style="font-size:.78rem;color:#6B7280">{cf.get("domain","")}</span>', unsafe_allow_html=True)
                    _avg = cf.get("avg_score")
                    _cr[2].markdown(f'<span style="font-size:.8rem">{f"{_avg:.1f}" if _avg is not None else "—"}</span>', unsafe_allow_html=True)
                    _cr[3].markdown(f'<span style="font-size:.8rem">{cf.get("target_maturity","—")}</span>', unsafe_allow_html=True)
                    _gap = cf.get("gap") or 0
                    _cr[4].markdown(f'<span style="font-size:.8rem;color:#DC2626;font-weight:600">{_gap:.1f}</span>', unsafe_allow_html=True)
                    _cr[5].markdown(f'<span style="font-size:.78rem;color:#6B7280">{cf.get("capability_role","")}</span>', unsafe_allow_html=True)
                    if _disagree:
                        st.caption(f"⚠️ {_n_resp} respondents · σ={_std_dev:.1f} — High disagreement across respondents")

        # ── Respondent voices (survey assessments only) ──────────────────────
        if _survey_rationale:
            st.divider()
            with st.expander(
                f"💬 Respondent voices ({len(_survey_rationale)} capabilities with rationale)",
                expanded=False,
            ):
                st.caption(
                    "Direct quotes from survey respondents, grouped by capability. "
                    "These informed the AI-generated narrative and recommendations."
                )
                _cap_score_lookup = {
                    int(cf.get("capability_id") or 0): cf for cf in cap_findings
                }
                for cid, text in sorted(
                    _survey_rationale.items(),
                    key=lambda x: _cap_score_lookup.get(x[0], {}).get("avg_score") or 99,
                ):
                    _cf     = _cap_score_lookup.get(cid, {})
                    _cname  = _cf.get("capability_name") or f"Capability {cid}"
                    _domain = _cf.get("domain") or ""
                    _score  = _cf.get("avg_score")
                    _s_str  = f"avg {_score:.1f}" if _score is not None else ""
                    st.markdown(
                        f"<div style='border-left:3px solid #2563EB;padding:6px 12px;"
                        f"margin-bottom:10px;background:#F9FAFB;border-radius:4px'>"
                        f"<div style='font-size:.72rem;color:#6B7280'>"
                        f"{_domain} &nbsp;·&nbsp; {_s_str}</div>"
                        f"<div style='font-weight:600;color:#0F2744;margin-bottom:4px'>{_cname}</div>"
                        f"<div style='font-size:.85rem;color:#374151'>{text}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    # ── Tab 3 — Recommendations ───────────────────────────────────────────────
    with tab_recs:
        if not recommendations:
            st.info("No recommendations saved. Generate them in Step 5b of the wizard.")
        else:
            p1 = [r for r in recommendations if r.get("priority_tier") == "P1"]
            p2 = [r for r in recommendations if r.get("priority_tier") == "P2"]
            p3 = [r for r in recommendations if r.get("priority_tier") == "P3"]

            _rc1, _rc2, _rc3 = st.columns(3)
            _rc1.metric("P1 — Foundation", len(p1))
            _rc2.metric("P2 — Acceleration", len(p2))
            _rc3.metric("P3 — Optimisation", len(p3))

            tier_filter = st.selectbox(
                "Show", ["All", "P1 only", "P2 only", "P3 only"], key="detail_tier_filter"
            )
            filter_map = {"P1 only": "P1", "P2 only": "P2", "P3 only": "P3"}
            filtered_recs = (
                [r for r in recommendations if r.get("priority_tier") == filter_map[tier_filter]]
                if tier_filter != "All" else recommendations
            )

            _TIER_ORDER = {"P1": 0, "P2": 1, "P3": 2}
            _ROLE_ORDER_R = {"Core": 0, "Upstream": 1, "Downstream": 2}
            filtered_recs = sorted(
                filtered_recs,
                key=lambda r: (
                    _TIER_ORDER.get(r.get("priority_tier") or "", 9),
                    _ROLE_ORDER_R.get(r.get("capability_role") or "", 9),
                    -(r.get("gap") or 0),
                ),
            )
            tier_colours = {"P1": "🔴", "P2": "🟡", "P3": "🟢"}
            for rec in filtered_recs:
                tier = rec.get("priority_tier", "P2")
                label = (
                    f"{tier_colours.get(tier, '')} **[{tier}]** "
                    f"{rec['capability_name']} | {rec.get('domain','')} | "
                    f"gap: {rec.get('gap',0):.1f} | {rec.get('capability_role','')} | "
                    f"{rec.get('effort_estimate','')}"
                )
                with st.expander(label, expanded=(tier == "P1")):
                    if rec.get("narrative"):
                        st.markdown(rec["narrative"])
                    if rec.get("recommended_actions"):
                        st.markdown("**Recommended actions:**")
                        for action in rec["recommended_actions"]:
                            st.markdown(f"- {action}")
                    if rec.get("enabling_dependencies"):
                        st.markdown("**Must be in place first:**")
                        for dep in rec["enabling_dependencies"]:
                            st.markdown(f"- {dep}")
                    if rec.get("success_indicators"):
                        st.markdown("**Success indicators:**")
                        for ind in rec["success_indicators"]:
                            st.markdown(f"- {ind}")

    # ── Tab 4 — Export ────────────────────────────────────────────────────────
    with tab_export:
        st.subheader("Download Reports")

        _e1, _e2 = st.columns(2)

        # Excel heatmap
        with _e1:
            st.markdown("**Maturity Heatmap (Excel)**")
            if dom_scores:
                _heatmap_bytes = generate_heatmap_excel(dom_scores, client_name, engagement, use_case)
                st.download_button(
                    "⬇ Download Heatmap",
                    data=_heatmap_bytes,
                    file_name=f"Meridant_Insight_{client_name.replace(' ','_')}_{created}_heatmap.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            else:
                st.button("⬇ Download Heatmap", disabled=True, use_container_width=True)
                st.caption("No domain findings saved.")

        # Excel roadmap
        with _e2:
            st.markdown("**Transformation Roadmap (Excel)**")
            if roadmap_record:
                _roadmap = roadmap_record["roadmap"]
                _tunit   = roadmap_record.get("timeline_unit") or "Sprints (2 wks)"
                _roadmap_bytes = generate_roadmap_excel(_roadmap, client_name, engagement, use_case)
                st.download_button(
                    "⬇ Download Roadmap",
                    data=_roadmap_bytes,
                    file_name=f"Meridant_Insight_{client_name.replace(' ','_')}_{created}_roadmap.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            else:
                st.button("⬇ Download Roadmap", disabled=True, use_container_width=True)
                st.caption("No roadmap saved. Generate one in Step 6 of the wizard.")

        st.divider()
        _e3, _e4 = st.columns(2)

        # Word report
        with _e3:
            st.markdown("**Full Report (Word)**")
            if _WORD_AVAILABLE and dom_scores:
                try:
                    _word_bytes = generate_word_report(
                        client_name=client_name,
                        engagement_name=engagement,
                        use_case_name=use_case,
                        consultant_name=consultant,
                        findings_narrative=narrative,
                        dom_scores=dom_scores,
                        cap_findings=cap_findings,
                        recommendations=recommendations,
                    )
                    st.download_button(
                        "⬇ Download Word Report",
                        data=_word_bytes,
                        file_name=f"Meridant_Insight_{client_name.replace(' ','_')}_{created}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as _err:
                    st.error(f"Word generation failed: {_err}")
            else:
                st.button("⬇ Download Word Report", disabled=True, use_container_width=True)
                if not _WORD_AVAILABLE:
                    st.caption("`python-docx` not installed. Rebuild the container.")
                else:
                    st.caption("No domain findings saved.")

        # PowerPoint report
        with _e4:
            st.markdown("**Executive Readout (PowerPoint)**")
            if _PPTX_AVAILABLE and dom_scores:
                try:
                    _pptx_bytes = generate_pptx_report(
                        client_name=client_name,
                        engagement_name=engagement,
                        use_case_name=use_case,
                        consultant_name=consultant,
                        findings_narrative=narrative,
                        dom_scores=dom_scores,
                        cap_findings=cap_findings,
                        recommendations=recommendations,
                        roadmap=roadmap_record["roadmap"] if roadmap_record else None,
                    )
                    st.download_button(
                        "⬇ Download PowerPoint",
                        data=_pptx_bytes,
                        file_name=f"Meridant_Insight_{client_name.replace(' ','_')}_{created}.pptx",
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        use_container_width=True,
                    )
                except Exception as _err:
                    st.error(f"PowerPoint generation failed: {_err}")
            else:
                st.button("⬇ Download PowerPoint", disabled=True, use_container_width=True)
                if not _PPTX_AVAILABLE:
                    st.caption("`python-pptx` not installed. Rebuild the container.")
                else:
                    st.caption("No domain findings saved.")

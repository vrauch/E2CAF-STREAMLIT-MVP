import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from src.meridant_client import get_client
from src.assessment_builder import analyze_use_case_readonly, CapabilityResult
from src.assessment_store import save_assessment, save_findings, save_narrative, list_assessments, load_assessment
from src.question_generator import generate_questions_for_capability
from src.sql_templates import q_list_next_usecases
from collections import defaultdict


def _strengthen_intent_with_ai(rough_intent: str, use_case_name: str = "") -> str:
    """Call Claude to rewrite a vague intent into a clear, structured statement."""
    from src.ai_client import get_ai_client, _call_with_retry, DEFAULT_MODEL
    import json

    client = get_ai_client()
    prompt = f"""You are an enterprise transformation consultant.

A user has written a rough or vague intent for a capability assessment.
Rewrite it into a clear, specific, well-structured intent statement of 2-3 sentences.

Keep the rewritten intent concise and actionable. It should capture:
- What the client is trying to achieve
- The scope or focus areas
- The desired outcome or priority

Do NOT add information the user didn't imply. Strengthen the language, add structure,
and make it precise — but stay faithful to the original meaning.

Use case name: {use_case_name or '(not specified)'}
Original intent: {rough_intent}

Return ONLY the rewritten intent text — no preamble, no quotes, no explanation."""

    response = _call_with_retry(
        client,
        model=DEFAULT_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers for predefined use case loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_predefined_usecases(client) -> list[dict]:
    """Return [{id, usecase_title, usecase_description, business_value}] from Next_UseCase."""
    res = client.query("""
        SELECT id, usecase_title,
               COALESCE(usecase_description, '') AS usecase_description,
               COALESCE(business_value, '')       AS business_value,
               COALESCE(owner_role, '')            AS owner_role
        FROM Next_UseCase
        ORDER BY usecase_title
    """)
    return res.get("rows", [])


def _load_predefined_capabilities(client, usecase_id: int):
    """
    Load capabilities directly from Next_UseCaseCapabilityImpact for a given use case.
    Maps impact_weight to role:  5 → Core,  3–4 → Upstream,  1–2 → Downstream.
    Also loads capability-level target maturity from Next_TargetMaturity (avg across dims).
    Returns (core, upstream, downstream, domains_covered, cap_count).
    """
    res = client.query(f"""
        SELECT
            c.id            AS capability_id,
            c.capability_name,
            d.domain_name,
            sd.subdomain_name,
            uci.impact_weight,
            uci.maturity_target,
            uci.feasibility_score,
            COALESCE((
                SELECT ROUND(AVG(tm.target_score), 1)
                FROM Next_TargetMaturity tm
                WHERE tm.usecase_id = {int(usecase_id)}
                  AND tm.capability_id = c.id
            ), uci.maturity_target, 3) AS avg_target_maturity
        FROM Next_UseCaseCapabilityImpact uci
        JOIN Next_Capability c  ON c.id  = uci.capability_id
        JOIN Next_Domain     d  ON d.id  = c.domain_id
        JOIN Next_SubDomain  sd ON sd.id = c.subdomain_id
        WHERE uci.usecase_id = {int(usecase_id)}
        ORDER BY uci.impact_weight DESC NULLS LAST, c.capability_name
    """)
    rows = res.get("rows", [])

    core, upstream, downstream = [], [], []

    for r in rows:
        w = r.get("impact_weight") or 0
        cap = CapabilityResult(
            capability_id=int(r["capability_id"]),
            capability_name=r["capability_name"],
            domain_name=r["domain_name"],
            subdomain_name=r["subdomain_name"],
            score=float(w) / 5.0,           # normalise impact as a proxy relevance score
            rationale=f"Impact weight: {w}/5 | Target maturity: {r.get('avg_target_maturity', 3)}",
        )
        # Attach target maturity as extra attribute for Step 2b
        cap.__dict__["avg_target_maturity"] = float(r.get("avg_target_maturity") or 3)
        cap.__dict__["impact_weight"] = w

        if w == 5:
            core.append(cap)
        elif w in (3, 4):
            upstream.append(cap)
        else:
            downstream.append(cap)

    # Expand upstream via interdependencies (same logic as analyze_use_case_readonly)
    all_ids = {c.capability_id for c in core + upstream + downstream}
    if all_ids:
        id_list = ",".join(str(i) for i in all_ids)
        res_up = client.query(f"""
            SELECT DISTINCT nc.id AS capability_id, nc.capability_name,
                            nd.domain_name, ns.subdomain_name
            FROM Next_CapabilityInterdependency dep
            JOIN Next_Capability nc ON nc.id = dep.source_capability_id
            JOIN Next_Domain     nd ON nc.domain_id  = nd.id
            JOIN Next_SubDomain  ns ON nc.subdomain_id = ns.id
            WHERE dep.target_capability_id IN ({id_list})
              AND dep.source_capability_id  NOT IN ({id_list})
        """)
        for r in res_up.get("rows", []):
            cap = CapabilityResult(
                capability_id=int(r["capability_id"]),
                capability_name=r["capability_name"],
                domain_name=r["domain_name"],
                subdomain_name=r["subdomain_name"],
                score=0.0,
                rationale="Foundational upstream dependency",
            )
            cap.__dict__["avg_target_maturity"] = 3.0
            cap.__dict__["impact_weight"] = 0
            upstream.append(cap)

    # Derive domains covered
    all_caps = core + upstream + downstream
    domains_covered: dict[str, int] = {}
    for c in all_caps:
        domains_covered[c.domain_name] = domains_covered.get(c.domain_name, 0) + 1

    cap_count = len(all_caps)
    return core, upstream, downstream, domains_covered, cap_count


def _hydrate_session_from_db(data: dict) -> None:
    """Populate session state from a load_assessment() result dict."""
    a = data["assessment"]
    caps = data["capabilities"]
    responses = data["responses"]

    # Client & assessment header
    st.session_state.assessment_id       = a["id"]
    st.session_state.client_name         = a.get("client_name", "")
    st.session_state.engagement_name     = a.get("engagement_name", "") or ""
    st.session_state.client_industry     = a.get("industry", "") or ""
    st.session_state.client_sector       = a.get("sector", "") or ""
    st.session_state.client_country      = a.get("country", "") or ""
    st.session_state.use_case_name       = a.get("use_case_name", "")
    st.session_state.intent_text         = a.get("intent_text", "")
    st.session_state.assessment_mode     = a.get("assessment_mode", "custom") or "custom"
    st.session_state.selected_usecase_id = a.get("usecase_id")

    # Capabilities split by role (mapped to CapabilityResult dict shape)
    def _cap_to_dict(c):
        return {
            "capability_id":   c["capability_id"],
            "capability_name": c["capability_name"],
            "domain_name":     c["domain_name"],
            "subdomain_name":  c["subdomain_name"],
            "score":           c.get("ai_score") or 0.0,
            "rationale":       c.get("rationale") or "",
        }

    core       = [_cap_to_dict(c) for c in caps if c["capability_role"] == "Core"]
    upstream   = [_cap_to_dict(c) for c in caps if c["capability_role"] == "Upstream"]
    downstream = [_cap_to_dict(c) for c in caps if c["capability_role"] == "Downstream"]
    st.session_state.core_caps       = core
    st.session_state.upstream_caps   = upstream
    st.session_state.downstream_caps = downstream

    # Derive domain_targets and domains_covered from AssessmentCapability rows
    domain_targets: dict[str, int] = {}
    domains_covered: dict[str, int] = {}
    for c in caps:
        d = c["domain_name"]
        if d not in domain_targets:
            domain_targets[d] = c.get("target_maturity") or 3
        domains_covered[d] = domains_covered.get(d, 0) + 1
    st.session_state.domain_targets  = domain_targets
    st.session_state.domains_covered = domains_covered

    # Reconstruct questions list and responses dict from AssessmentResponse rows
    questions: list[dict] = []
    response_dict: dict = {}
    cap_counter: dict[int, int] = {}
    for r in responses:
        cap_id  = r["capability_id"]
        counter = cap_counter.get(cap_id, 0)
        cap_counter[cap_id] = counter + 1
        key = f"{cap_id}|{r['question']}|{counter}"
        response_dict[key] = {
            "capability_id":   cap_id,
            "capability_name": r["capability_name"],
            "domain":          r["domain"],
            "subdomain":       r["subdomain"],
            "capability_role": r["capability_role"],
            "question":        r["question"],
            "response_type":   r["response_type"],
            "score":           r.get("score"),
            "answer":          r.get("answer"),
            "notes":           r.get("notes") or "",
        }
        questions.append({
            "use_case":        a.get("use_case_name", ""),
            "capability_id":   cap_id,
            "capability_name": r["capability_name"],
            "domain":          r["domain"],
            "subdomain":       r["subdomain"],
            "capability_role": r["capability_role"],
            "question":        r["question"],
            "response_type":   r["response_type"],
            "guidance":        "",
        })

    st.session_state.questions             = questions
    st.session_state.responses             = response_dict
    st.session_state.findings_saved        = (a.get("status") == "complete")
    st.session_state.findings_narrative    = a.get("findings_narrative") or None
    st.session_state.responses_ai_scored   = False   # re-score on each load
    st.session_state.confirm_regen_narrative = False
    st.session_state.confirm_regen_recs      = False
    st.session_state.roadmap_data          = None
    st.session_state.wizard_step           = 5


def _build_client_stated_context(responses: dict) -> str:
    """
    Concatenate all free-text answer and notes values from the responses dict
    into a single string for use as the CLIENT-STATED CONTEXT in AI prompts.

    This is the ONLY source the AI is permitted to draw specific vendor/tool/
    product names from — preventing hallucination of technology specifics.
    Returns a formatted multi-line string, or an empty string if no text exists.
    """
    texts = [
        t.strip()
        for v in responses.values()
        for t in (v.get("answer", "") or "", v.get("notes", "") or "")
        if t and t.strip()
    ]
    if not texts:
        return ""
    # Deduplicate while preserving order
    seen: set = set()
    unique = [t for t in texts if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]
    return "\n".join(f"  - {t}" for t in unique)


def render():
    st.title("Create Assessment")
    st.caption("Guided wizard. No database writes for this test.")

    # Init session state
    st.session_state.setdefault("use_case_name", "")
    st.session_state.setdefault("intent_text", "")
    st.session_state.setdefault("wizard_step", 1)
    st.session_state.setdefault("client_name", "")
    st.session_state.setdefault("engagement_name", "")
    st.session_state.setdefault("client_industry", "")
    st.session_state.setdefault("client_sector", "")
    st.session_state.setdefault("client_country", "")
    st.session_state.setdefault("assessment_mode", "custom")   # "predefined" | "custom"
    st.session_state.setdefault("selected_usecase_id", None)

    # Storage for step 2 outputs
    st.session_state.setdefault("core_caps", [])
    st.session_state.setdefault("upstream_caps", [])
    st.session_state.setdefault("downstream_caps", [])
    st.session_state.setdefault("domains_covered", {})
    st.session_state.setdefault("questions", [])
    st.session_state.setdefault("responses", {})
    st.session_state.setdefault("findings_narrative", None)
    st.session_state.setdefault("domain_targets", {})
    st.session_state.setdefault("assessment_id", None)
    st.session_state.setdefault("findings_saved", False)
    st.session_state.setdefault("show_new_form", False)
    st.session_state.setdefault("roadmap_data", None)
    st.session_state.setdefault("roadmap_timeline_unit", "Sprints (2 wks)")
    st.session_state.setdefault("roadmap_horizon_months", 6)
    st.session_state.setdefault("roadmap_scope", "Core")
    st.session_state.setdefault("responses_ai_scored", False)
    st.session_state.setdefault("recommendations", None)
    st.session_state.setdefault("confirm_regen_narrative", False)
    st.session_state.setdefault("confirm_regen_recs", False)

    # -------------------------
    # STEP 1
    # -------------------------
    if st.session_state.wizard_step == 1:
        st.subheader("Step 1 — Client & Use Case")

        if not st.session_state.get("show_new_form", False):
            # ── LOAD EXISTING ASSESSMENT ──────────────────────────────────────
            st.markdown(
                "Select a previously saved assessment to resume or review it, "
                "or start a new one below."
            )
            _db = get_client()
            assessment_rows = list_assessments(_db)
            if assessment_rows:
                def _fmt_assessment(r):
                    status_label = "Complete" if r["status"] == "complete" else "In Progress"
                    date = (r.get("created_at") or "")[:10]
                    label = f"{r['client_name']} — {r['use_case_name']}"
                    if r.get("engagement_name"):
                        label = f"{r['client_name']} · {r['engagement_name']} — {r['use_case_name']}"
                    return f"{label}  ({status_label}, {date})"

                options_map = {_fmt_assessment(r): r["id"] for r in assessment_rows}
                selected_label = st.selectbox("Saved assessments", list(options_map.keys()))
                if st.button("Load Assessment", type="primary"):
                    with st.spinner("Loading assessment..."):
                        data = load_assessment(_db, options_map[selected_label])
                    if data:
                        _hydrate_session_from_db(data)
                        st.rerun()
                    else:
                        st.error("Could not load the selected assessment.")
            else:
                st.info("No saved assessments found.")

            st.divider()
            if st.button("＋ Start New Assessment"):
                st.session_state.show_new_form = True
                st.rerun()
            st.stop()

        # ── NEW ASSESSMENT FORM ───────────────────────────────────────────────
        if st.button("← Back"):
            st.session_state.show_new_form = False
            st.rerun()

        st.markdown(
            "Enter the client details, name your use case, and describe the client intent. "
            "The intent should capture what the client is trying to achieve — their goals, "
            "scope, and priorities for this engagement."
        )

        # Force custom mode (predefined mode is disabled for now)
        mode = "custom"
        st.session_state.assessment_mode = "custom"

        st.divider()

        # ── PREDEFINED: use case selector lives OUTSIDE the form so changes
        #    trigger immediate reruns and intent text refreshes live ──────────
        if mode == "predefined":
            db = get_client()
            uc_rows = _load_predefined_usecases(db)

            if not uc_rows:
                st.warning("No predefined use cases found in the framework.")
                st.stop()

            uc_options = [{"id": None, "label": "— Select a use case —"}] + [
                {"id": r["id"], "label": r["usecase_title"]} for r in uc_rows
            ]
            uc_labels = [o["label"] for o in uc_options]
            uc_ids    = [o["id"]    for o in uc_options]

            prior_id  = st.session_state.get("selected_usecase_id")
            prior_idx = uc_ids.index(prior_id) if prior_id in uc_ids else 0

            selected_idx = st.selectbox(
                "Use case *",
                options=range(len(uc_labels)),
                format_func=lambda i: uc_labels[i],
                index=prior_idx,
                key="uc_selectbox",
            )
            selected_id    = uc_ids[selected_idx]
            selected_label = uc_labels[selected_idx]

            # Persist immediately so the form below picks it up
            if selected_id != st.session_state.get("selected_usecase_id"):
                st.session_state.selected_usecase_id = selected_id
                st.session_state.use_case_name = selected_label if selected_id else ""
                # Clear intent so it gets re-derived below
                st.session_state.intent_text = ""

            # ── Use case info card ────────────────────────────────────────
            if selected_id is not None:
                uc_detail = next((r for r in uc_rows if r["id"] == selected_id), None)
                if uc_detail:
                    with st.container(border=True):
                        cols = st.columns([3, 1])
                        with cols[0]:
                            st.markdown(f"**{uc_detail['usecase_title']}**")
                            if uc_detail.get("usecase_description"):
                                st.caption(uc_detail["usecase_description"])
                        with cols[1]:
                            if uc_detail.get("owner_role"):
                                st.caption(f"👤 {uc_detail['owner_role']}")

                    if uc_detail.get("business_value"):
                        st.info(f"💡 **Business value:** {uc_detail['business_value']}")

                    cap_count_res = db.query(
                        f"SELECT COUNT(*) AS cnt FROM Next_UseCaseCapabilityImpact WHERE usecase_id = {int(selected_id)}"
                    )
                    cnt = (cap_count_res.get("rows") or [{}])[0].get("cnt", 0)
                    st.caption(f"📦 {cnt} capabilities mapped in the framework · interdependency expansion applied in Step 2")

                    # Derive intent prefill from framework text (only if not already customised)
                    if not st.session_state.intent_text and uc_detail:
                        parts = []
                        if uc_detail.get("usecase_description"):
                            parts.append(uc_detail["usecase_description"])
                        if uc_detail.get("business_value"):
                            parts.append(uc_detail["business_value"])
                        st.session_state.intent_text = " ".join(parts)

        else:
            selected_id    = None
            selected_label = ""

        st.divider()

        # ── The submission form — contains client fields + editable intent ─
        with st.form("step1_form", clear_on_submit=False):
            st.markdown("#### Client details")
            col_a, col_b = st.columns(2)
            with col_a:
                client_name = st.text_input(
                    "Client name *",
                    value=st.session_state.get("client_name", ""),
                    placeholder="e.g., Massey University",
                )
            with col_b:
                engagement_name = st.text_input(
                    "Engagement name",
                    value=st.session_state.get("engagement_name", ""),
                    placeholder="e.g., Data Transformation Programme",
                )

            col_c, col_d, col_e = st.columns(3)
            with col_c:
                industry = st.selectbox(
                    "Industry",
                    ["", "Education", "Financial Services", "Government",
                     "Healthcare", "Manufacturing", "Retail", "Telecommunications",
                     "Energy & Utilities", "Professional Services", "Other"],
                    index=0,
                )
            with col_d:
                sector = st.selectbox(
                    "Sector",
                    ["", "Public", "Private", "Non-Profit"],
                    index=0,
                )
            with col_e:
                country = st.text_input(
                    "Country",
                    value=st.session_state.get("client_country", ""),
                    placeholder="e.g., Australia",
                )

            st.divider()
            st.markdown("#### Use case & client intent")

            if mode == "custom":
                use_case_name = st.text_input(
                    "Use case name *",
                    value=st.session_state.use_case_name,
                    placeholder="e.g., AI Enablement",
                )
            else:
                # Display as read-only label — selection is handled above the form
                st.markdown(
                    f"**Use case:** {st.session_state.use_case_name or '*— not selected —*'}"
                )
                use_case_name = st.session_state.use_case_name

            # Intent text — pre-filled from framework, editable for client context
            if mode == "predefined":
                st.caption(
                    "✏️ The intent below is pre-filled from the framework definition. "
                    "Edit it to reflect the client's specific objectives, scope, and priorities."
                )
            intent_text = st.text_area(
                "Client intent *" if mode == "custom" else "Client intent (edit to reflect client context) *",
                value=st.session_state.intent_text,
                height=150,
                placeholder=(
                    "Describe what the client is trying to achieve — their specific goals, "
                    "constraints, and priorities for this engagement."
                    if mode == "custom" else
                    "Refine the pre-filled intent to reflect the client's specific objectives, "
                    "scope, and any known constraints or priorities..."
                ),
            )

            # ── Inline AI intent strengthener ─────────────────────────────
            st.caption(
                "✨ Optionally enter a rough idea below and click **Strengthen** "
                "to let AI rewrite your intent — or leave blank to strengthen what you've typed above."
            )
            col_ai, col_btn = st.columns([5, 1])
            with col_ai:
                rough_intent = st.text_input(
                    "Rough idea",
                    placeholder="e.g., we want to do AI but governance is a mess",
                    key="rough_intent_input",
                    label_visibility="collapsed",
                )
            with col_btn:
                strengthen_btn = st.form_submit_button("✨ Strengthen", type="secondary")

            st.divider()
            submitted = st.form_submit_button(
                "Load Capabilities →" if mode == "predefined" else "Analyse Use Case →",
                type="primary",
            )

        if strengthen_btn:
            # Save current form field values to session state so they survive the rerun
            st.session_state.client_name     = client_name.strip()
            st.session_state.engagement_name = engagement_name.strip()
            st.session_state.client_industry = industry
            st.session_state.client_sector   = sector
            st.session_state.client_country  = country.strip()
            if mode == "custom":
                st.session_state.use_case_name = use_case_name.strip()
            intent_to_strengthen = rough_intent.strip() or intent_text.strip()
            if intent_to_strengthen:
                with st.spinner("Rewriting intent…"):
                    rewritten = _strengthen_intent_with_ai(
                        intent_to_strengthen,
                        use_case_name=st.session_state.use_case_name,
                    )
                st.session_state.intent_text = rewritten
                st.rerun()
            else:
                st.warning("Please enter an intent or rough idea to strengthen.")

        elif submitted:
            if not client_name.strip():
                st.error("Please enter a client name.")
                return
            if mode == "predefined" and not st.session_state.get("selected_usecase_id"):
                st.error("Please select a use case from the list above.")
                return
            if mode == "custom":
                if not use_case_name.strip():
                    st.error("Please enter a use case name.")
                    return
            if not intent_text.strip():
                st.error("Please describe the client's intent.")
                return

            st.session_state.client_name        = client_name.strip()
            st.session_state.engagement_name    = engagement_name.strip()
            st.session_state.client_industry    = industry
            st.session_state.client_sector      = sector
            st.session_state.client_country     = country.strip()
            st.session_state.use_case_name      = use_case_name.strip()
            st.session_state.intent_text        = intent_text.strip()

            # ── Predefined: load capabilities immediately, skip to 2b ──────
            if mode == "predefined":
                with st.spinner("Loading capabilities from framework..."):
                    db = get_client()
                    core, upstream, downstream, domains_covered, cap_count = \
                        _load_predefined_capabilities(db, st.session_state.selected_usecase_id)

                st.session_state.core_caps       = [c.__dict__ for c in core]
                st.session_state.upstream_caps   = [c.__dict__ for c in upstream]
                st.session_state.downstream_caps = [c.__dict__ for c in downstream]
                st.session_state.domains_covered = domains_covered

                st.success(
                    f"Loaded **{cap_count}** capabilities for *{use_case_name}* "
                    f"({len(core)} core · {len(upstream)} upstream · {len(downstream)} downstream). "
                    f"Skipping capability discovery — proceeding to target maturity."
                )
                st.session_state.wizard_step = "2b"
                st.rerun()

            # ── Custom: proceed to Step 2 for AI discovery ──────────────────
            else:
                st.session_state.wizard_step = 2
                st.rerun()

    # -------------------------
    # STEP 2
    # -------------------------
    if st.session_state.wizard_step == 2:
        st.subheader("Step 2 — Capability discovery (Core / Upstream / Downstream)")
        st.markdown(
            "Set the number of core capabilities and click **Run Capability Discovery**. "
            "The AI will analyse your intent against the TMM library and classify capabilities "
            "as Core, Upstream, or Downstream. Review the results, then continue to set domain targets."
        )
        st.write(f"**Use case:** {st.session_state.use_case_name}")
        st.write(f"**Intent:** {st.session_state.intent_text}")

        st.info("This step reads from TMM only (no writes).")

        colA, colB = st.columns(2)
        with colA:
            core_k = st.slider("How many Core capabilities?", 5, 20, 10)
        
        run = st.button("Run Capability Discovery", type="primary")

        if run:
            client = get_client()
            candidates, core, upstream, downstream, covered, cap_count = analyze_use_case_readonly(
                client=client,
                intent_text=st.session_state.intent_text,
                core_k=core_k,
            )
            st.caption(f"Capability library size (from TMM): {cap_count}")

            # Store results for later steps
            st.session_state.core_caps = [c.__dict__ for c in core]
            st.session_state.upstream_caps = [c.__dict__ for c in upstream]
            st.session_state.downstream_caps = [c.__dict__ for c in downstream]
            st.session_state.domains_covered = covered

            st.success("Capability discovery complete.")

        # Show results if available
        if st.session_state.core_caps:
            st.markdown("### Core capabilities")
            df_core = pd.DataFrame(st.session_state.core_caps)
            cols_to_show = [c for c in ["capability_name", "domain_name", "subdomain_name", "score", "rationale"] if c in df_core.columns]
            st.dataframe(df_core[cols_to_show], width='stretch')

            st.markdown("### Upstream capabilities")
            df_up = pd.DataFrame(st.session_state.upstream_caps)
            st.dataframe(df_up, width='stretch')

            st.markdown("### Downstream capabilities")
            df_dn = pd.DataFrame(st.session_state.downstream_caps)
            st.dataframe(df_dn, width='stretch')

            st.markdown("### Domains covered (derived from selected capabilities)")
            df_dom = pd.DataFrame(
                [{"domain": k, "capability_count": v} for k, v in st.session_state.domains_covered.items()]
            ).sort_values("capability_count", ascending=False)
            st.dataframe(df_dom, width='stretch')

        # Navigation controls
        col1, col2 = st.columns(2)

        with col1:
            if st.button("Back to Step 1"):
                st.session_state.wizard_step = 1

        with col2:
            if st.button("Continue: Set Domain Targets"):
                if not st.session_state.core_caps:
                    st.error("Run capability discovery first.")
                else:
                    st.session_state.wizard_step = "2b"
                    st.rerun()
    
    # -------------------------
    # STEP 2b — Domain Targets
    # -------------------------
    if st.session_state.wizard_step == "2b":
        st.subheader("Step 2b — Set Target Maturity per Domain")
        st.markdown(
            "Set the target maturity level for each domain involved in this assessment. "
            "Use the sliders to adjust — the default is **3 (Defined)**. "
            "Higher targets flag larger gaps in the findings."
        )
        st.caption(
            "These targets define what 'good' looks like for each domain in this assessment. "
            "Default is 3 (Defined). Adjust domains where a higher or lower target is appropriate."
        )

        if not st.session_state.domains_covered:
            st.warning("No domains found. Go back to Step 2.")
            if st.button("Back to Step 2"):
                st.session_state.wizard_step = 2
                st.rerun()
            st.stop()

        domains = sorted(st.session_state.domains_covered.keys())

        # Load existing targets or default to 3
        current_targets = st.session_state.domain_targets or {d: 3 for d in domains}

        st.markdown("### Domain target maturity")
        st.markdown(
            "| Level | Label | Meaning |\n"
            "|---|---|---|\n"
            "| 1 | Not Defined | No formal process or ownership |\n"
            "| 2 | Informal | Ad-hoc, person-dependent |\n"
            "| 3 | Defined | Documented, consistently applied |\n"
            "| 4 | Governed | Measured, enforced, reported |\n"
            "| 5 | Optimized | Continuously improved, industry-leading |"
        )

        st.divider()

        new_targets = {}
        cols_per_row = 2
        domain_chunks = [domains[i:i+cols_per_row] for i in range(0, len(domains), cols_per_row)]

        for chunk in domain_chunks:
            cols = st.columns(cols_per_row)
            for col, domain in zip(cols, chunk):
                with col:
                    cap_count = st.session_state.domains_covered.get(domain, 0)
                    new_targets[domain] = st.select_slider(
                        f"{domain} ({cap_count} caps)",
                        options=[1, 2, 3, 4, 5],
                        value=current_targets.get(domain, 3),
                        key=f"target_{domain}",
                    )

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Back to Step 2"):
                st.session_state.wizard_step = 2
                st.rerun()
        with col2:
            if st.button("Continue to Step 3", type="primary"):
                st.session_state.domain_targets = new_targets
                st.session_state.wizard_step = 3
                st.rerun()
                
    # -------------------------
    # STEP 3
    # -------------------------
    if st.session_state.wizard_step == 3:
        st.subheader("Step 3 — Generate assessment questions")
        st.markdown(
            "Choose which capability tiers to include, set the number of questions per capability, "
            "and select a question style. Click **Generate Questions** to create the assessment instrument. "
            "You can download the questions as a CSV for offline completion."
        )

        if not st.session_state.core_caps:
            st.warning("No discovered capabilities found. Go back to Step 2 and run capability discovery.")
            if st.button("Back to Step 2"):
                st.session_state.wizard_step = 2
                st.rerun()
            st.stop()

        include_upstream = st.checkbox("Include upstream capabilities", value=True)
        include_downstream = st.checkbox("Include downstream capabilities", value=True)

        q_per_cap = st.slider("Questions per capability", 2, 7, 4)
        style = st.selectbox(
            "Question style",
            ["Maturity (1–5)", "Evidence (Yes/No + notes)", "Workshop (discussion)"],
        )

        if st.button("Generate Questions", type="primary"):
            from src.question_generator import generate_questions_for_capability

            use_case = st.session_state.use_case_name

            caps = []
            caps += [(c, "Core") for c in st.session_state.core_caps]
            if include_upstream:
                caps += [(c, "Upstream") for c in st.session_state.upstream_caps]
            if include_downstream:
                caps += [(c, "Downstream") for c in st.session_state.downstream_caps]

            questions = []
            progress_bar = st.progress(0)
            status = st.empty()
            total_caps = len(caps)

            for i, (cap, role) in enumerate(caps):
                status.caption(f"Generating questions for {cap['capability_name']} ({role})...")
                questions.extend(
                    generate_questions_for_capability(
                        use_case=use_case,
                        cap=cap,
                        role=role,
                        questions_per_capability=q_per_cap,
                        style=style,
                    )
                )
                progress_bar.progress((i + 1) / total_caps)

            status.caption(f"Done — {len(questions)} questions generated.")
            st.session_state.questions = [q.__dict__ for q in questions]
            st.success(f"Generated {len(questions)} questions across {total_caps} capabilities.")

        if st.session_state.questions:
            df_q = pd.DataFrame(st.session_state.questions)
            df_q["score"] = ""
            df_q["answer"] = ""
            df_q["notes"] = ""
            st.dataframe(df_q, width='stretch')

            st.download_button(
                "Download Questions (CSV)",
                data=df_q.to_csv(index=False).encode("utf-8"),
                file_name=f"{st.session_state.use_case_name}_questions.csv".replace(" ", "_"),
                mime="text/csv",
            )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Back to Step 2"):
                st.session_state.wizard_step = 2
                st.rerun()
        with col2:
            if st.button("Continue to Step 4"):
                if not st.session_state.questions:
                    st.error("Generate questions first.")
                else:
                    st.session_state.wizard_step = 4
                    st.session_state.responses = {}
                    st.rerun()

    # -------------------------
    # STEP 4
    # -------------------------
    if st.session_state.wizard_step == 4:
        st.subheader("Step 4 — Run Assessment")
        st.markdown(
            "Answer each question by selecting a score or response. Expand a capability to see its questions. "
            "Alternatively, upload a completed CSV from Step 3 using the **Offline option** below. "
            "Once you have answered enough questions, click **Submit Assessment** to save."
        )

        if not st.session_state.questions:
            st.warning("No questions found. Go back to Step 3.")
            if st.button("Back to Step 3"):
                st.session_state.wizard_step = 3
                st.rerun()
            st.stop()

        questions = st.session_state.questions
        responses = st.session_state.responses

        # Progress
        total = len(questions)
        answered = len(responses)
        st.progress(answered / total if total > 0 else 0)
        st.caption(f"Progress: {answered} / {total} answered")

        # Group questions by role → domain → capability
        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for q in questions:
            grouped[q["capability_role"]][q["domain"]][q["capability_name"]].append(q)

        role_order = ["Core", "Upstream", "Downstream"]

        widget_counter = 0
        for role in role_order:
            if role not in grouped:
                continue
            st.markdown(f"## {role} Capabilities")

            for domain, caps in sorted(grouped[role].items()):
                st.markdown(f"### {domain}")

                for cap_name, qs in sorted(caps.items()):
                    with st.expander(f"**{cap_name}** ({qs[0]['subdomain']})", expanded=False):
                        for q in qs:
                            widget_counter += 1
                            key = str(q["capability_id"]) + "|" + q["question"] + "|" + str(widget_counter)
                            rtype = q["response_type"]
                            st.markdown(f"**{q['question']}**")
                            st.caption(q["guidance"])

                            if rtype == "maturity_1_5":
                                score = st.radio(
                                    "Score",
                                    options=[1, 2, 3, 4, 5],
                                    format_func=lambda x: {
                                        1: "1 — Not Defined",
                                        2: "2 — Informal",
                                        3: "3 — Defined",
                                        4: "4 — Governed",
                                        5: "5 — Optimized",
                                    }[x],
                                    index=None,
                                    key=f"score_{key}",
                                    horizontal=True,
                                )
                                notes = st.text_area("Notes (optional)", key=f"notes_{key}", height=60)
                                if score is not None:
                                    responses[key] = {
                                        "capability_id": q["capability_id"],
                                        "capability_name": cap_name,
                                        "domain": domain,
                                        "subdomain": q["subdomain"],
                                        "capability_role": role,
                                        "question": q["question"],
                                        "response_type": rtype,
                                        "score": score,
                                        "answer": None,
                                        "notes": notes,
                                    }

                            elif rtype == "yes_no_evidence":
                                answer = st.radio(
                                    "Answer",
                                    options=["Yes", "No", "Partial"],
                                    index=None,
                                    key=f"yn_{key}",
                                    horizontal=True,
                                )
                                evidence = st.text_area("Evidence / Notes", key=f"ev_{key}", height=60)
                                if answer is not None:
                                    responses[key] = {
                                        "capability_id": q["capability_id"],
                                        "capability_name": cap_name,
                                        "domain": domain,
                                        "subdomain": q["subdomain"],
                                        "capability_role": role,
                                        "question": q["question"],
                                        "response_type": rtype,
                                        "score": None,
                                        "answer": answer,
                                        "notes": evidence,
                                    }

                            else:  # free_text / workshop
                                notes = st.text_area(
                                    "Discussion notes",
                                    key=f"ft_{key}",
                                    height=100,
                                    placeholder="Capture what was discussed...",
                                )
                                score = st.select_slider(
                                    "Agreed maturity score",
                                    options=[1, 2, 3, 4, 5],
                                    key=f"ws_{key}",
                                )
                                if notes.strip():
                                    responses[key] = {
                                        "capability_id": q["capability_id"],
                                        "capability_name": cap_name,
                                        "domain": domain,
                                        "subdomain": q["subdomain"],
                                        "capability_role": role,
                                        "question": q["question"],
                                        "response_type": rtype,
                                        "score": score,
                                        "answer": None,
                                        "notes": notes,
                                    }

                            st.divider()

        st.session_state.responses = responses
        # ── Offline workflow ──
        st.markdown("### Offline option")
        st.caption("Complete the question CSV downloaded in Step 3 (add score, answer, and notes columns), then upload it here.")

        uploaded = st.file_uploader(
        "📂 Upload Completed Answers (CSV or Excel)",
        type=["csv", "xlsx"],
        help="Upload the completed question sheet from Step 3.",
        )
        
        if uploaded is not None:
            try:
                filename = uploaded.name.lower()
                if filename.endswith(".xlsx"):
                    df_up = pd.read_excel(uploaded)
                else:
                    df_up = pd.read_csv(uploaded)
                required_cols = {"capability_id", "capability_name", "domain",
                                "subdomain", "capability_role", "question",
                                "response_type", "guidance"}
                if not required_cols.issubset(set(df_up.columns)):
                    st.error("Uploaded file is missing required columns. Please use the Step 3 CSV.")
                else:
                    loaded = 0
                    skipped = 0
                    for _, row in df_up.iterrows():
                        rtype = str(row.get("response_type", "")).strip()
                        score_raw = row.get("score", "")
                        answer_raw = str(row.get("answer", "")).strip()
                        notes_raw = str(row.get("notes", "")).strip()

                        score = None
                        if str(score_raw).strip() not in ("", "nan"):
                            try:
                                score = int(float(str(score_raw).strip()))
                                if score not in (1, 2, 3, 4, 5):
                                    score = None
                            except ValueError:
                                score = None

                        answer = answer_raw if answer_raw.lower() in ("yes", "no", "partial") else None

                        if rtype == "maturity_1_5" and score is None:
                            skipped += 1
                            continue
                        if rtype == "yes_no_evidence" and answer is None and score is None:
                            skipped += 1
                            continue
                        if rtype not in ("maturity_1_5", "yes_no_evidence") and not notes_raw and score is None:
                            skipped += 1
                            continue

                        key = str(row["capability_id"]) + "|" + str(row["capability_role"]) + "|" + str(row["question"])
                        responses[key] = {
                            "capability_id": row["capability_id"],
                            "capability_name": str(row["capability_name"]),
                            "domain": str(row["domain"]),
                            "subdomain": str(row["subdomain"]),
                            "capability_role": str(row["capability_role"]),
                            "question": str(row["question"]),
                            "response_type": rtype,
                            "score": score,
                            "answer": answer,
                            "notes": notes_raw,
                        }
                        loaded += 1

                    st.session_state.responses = responses
                    st.success(f"Loaded {loaded} responses. {skipped} skipped (no valid score/answer).")

            except Exception as e:
                st.error(f"Could not read file: {e}")
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Back to Step 3"):
                st.session_state.wizard_step = 3
                st.rerun()
        with col2:
            if st.button("Submit Assessment", type="primary"):
                if answered == 0:
                    st.error("Please answer at least one question before submitting.")
                else:
                    with st.spinner("Saving assessment..."):
                        try:
                            db = get_client()
                            assessment_id = save_assessment(db, st.session_state)
                            st.session_state.assessment_id = assessment_id
                            st.success(f"Saved — assessment ID: {assessment_id}")
                        except Exception as e:
                            st.error(f"Save failed: {e}")
                            import traceback
                            st.code(traceback.format_exc())
                            st.session_state.assessment_id = None
                    st.session_state.wizard_step = 5
                    st.rerun()
                    
    # -------------------------
    # STEP 5
    # -------------------------
    if st.session_state.wizard_step == 5:
        st.subheader("Step 5 — Assessment Findings")
        st.markdown(
            "Review the assessment results below. Domain and capability scores are shown with gap analysis "
            "against your targets. An AI-generated executive summary highlights key risks and recommendations. "
            "Use the export buttons to download scores and responses."
        )

        responses = st.session_state.responses
        if not responses:
            st.warning("No responses found. Go back to Step 4.")
            if st.button("Back to Step 4"):
                st.session_state.wizard_step = 4
                st.rerun()
            st.stop()

        # ── Ensure all responses have numeric scores ─────────────────────────
        if not st.session_state.get("responses_ai_scored"):
            # 1. Map yes/no/evidence answers to numeric scores
            for k, v in st.session_state.responses.items():
                if v.get("score") is not None:
                    continue
                if v.get("response_type") == "yes_no_evidence" and v.get("answer"):
                    mapped = {"Yes": 3, "Partial": 2, "No": 1}.get(v["answer"])
                    if mapped is not None:
                        st.session_state.responses[k]["score"] = mapped

            # 2. AI-score any remaining free-text answers that still have no score
            needs_ai = [
                (k, v) for k, v in st.session_state.responses.items()
                if v.get("score") is None and v.get("answer")
            ]
            if needs_ai:
                with st.spinner(f"AI scoring {len(needs_ai)} free-text responses…"):
                    from src.ai_client import score_free_text_responses
                    try:
                        results = score_free_text_responses([v for _, v in needs_ai])
                        for (k, _), result in zip(needs_ai, results):
                            st.session_state.responses[k]["score"] = result.get("score")
                            if result.get("rationale"):
                                existing_notes = st.session_state.responses[k].get("notes", "")
                                st.session_state.responses[k]["notes"] = (
                                    f"{existing_notes} [AI: {result['rationale']}]".strip()
                                )
                    except Exception as e:
                        st.warning(f"Could not AI-score free-text responses: {e}")

            st.session_state.responses_ai_scored = True
            st.rerun()

        # Build scored list
        scored = []
        for r in responses.values():
            if r["response_type"] == "maturity_1_5":
                s = r["score"] if r["score"] is not None else None
            elif r["response_type"] == "yes_no_evidence":
                s = {"Yes": 3, "Partial": 2, "No": 1}.get(r.get("answer")) if r.get("score") is None else r["score"]
            else:
                s = r["score"] if r["score"] is not None else None

            if s is not None:
                scored.append({
                    "capability_id": r["capability_id"],
                    "capability_name": r["capability_name"],
                    "domain": r["domain"],
                    "subdomain": r["subdomain"],
                    "capability_role": r["capability_role"],
                    "question": r["question"],
                    "score": s,
                    "answer": r.get("answer"),
                    "notes": r.get("notes", ""),
                })

        if not scored:
            st.warning("No scored responses found. Ensure questions were answered.")
            st.stop()

        df = pd.DataFrame(scored)

        # Capability scores
        cap_scores = (
            df.groupby(["capability_role", "domain", "subdomain", "capability_name"])["score"]
            .mean()
            .reset_index()
            .rename(columns={"score": "avg_score"})
            .copy()
        )
        cap_scores["avg_score"] = cap_scores["avg_score"].round(1)
        domain_targets = st.session_state.get("domain_targets", {})
        cap_scores["target"] = cap_scores["domain"].map(lambda d: domain_targets.get(d, 3))
        cap_scores["gap"] = cap_scores["target"] - cap_scores["avg_score"]
        cap_scores["risk"] = cap_scores["avg_score"].apply(
            lambda x: "🔴 High" if x < 2 else ("🟡 Medium" if x < 3 else "🟢 Low")
        )

        # Domain scores
        dom_scores = (
            df.groupby("domain")["score"]
            .mean()
            .reset_index()
            .rename(columns={"score": "avg_score"})
            .copy()
        )
        dom_scores["avg_score"] = dom_scores["avg_score"].round(1)
        dom_scores["target"] = dom_scores["domain"].map(lambda d: domain_targets.get(d, 3))
        dom_scores["gap"] = dom_scores["target"] - dom_scores["avg_score"]

        overall = round(df["score"].mean(), 1)

        if st.session_state.get("assessment_id") and not st.session_state.get("findings_saved"):
            try:
                client = get_client()
                save_findings(
                    client=client,
                    assessment_id=st.session_state.assessment_id,
                    cap_scores=cap_scores.to_dict(orient="records"),
                    dom_scores=dom_scores.to_dict(orient="records"),
                    overall_score=overall,
                )
                st.session_state.findings_saved = True
            except Exception as e:
                st.warning(f"Could not save findings: {e}")

        # ── Summary cards ──
        st.markdown(f"### Overall maturity: **{overall} / 5**")
        st.markdown(f"**Client:** {st.session_state.get('client_name', 'Unknown')}")
        if st.session_state.get("engagement_name"):
            st.markdown(f"**Engagement:** {st.session_state.engagement_name}")
        st.markdown(f"**Industry:** {st.session_state.get('client_industry', '')}  |  **Use case:** {st.session_state.use_case_name}")
        st.markdown(f"**Questions answered:** {len(scored)}")
        st.markdown(f"**Capabilities assessed:** {cap_scores['capability_name'].nunique()}")
        st.markdown(f"**Domains covered:** {dom_scores['domain'].nunique()}")

        st.divider()

        # ── Maturity Heatmap ──
        st.markdown("### Maturity Heatmap")
        from src.heatmap import render_heatmap_html, generate_heatmap_excel
        heatmap_html = render_heatmap_html(dom_scores.to_dict(orient="records"))
        n_domains    = len(dom_scores)
        heatmap_h    = max(320, 140 + n_domains * 6)   # rough height estimate
        components.html(heatmap_html, height=heatmap_h, scrolling=True)

        st.divider()

        # ── Domain scores ──
        st.markdown("### Domain scores")
        st.dataframe(dom_scores, width='stretch')

        st.divider()

        # ── Capability scores by role ──
        st.markdown("### Capability scores")
        roles_present = [r for r in ["Core", "Upstream", "Downstream"] if r in cap_scores["capability_role"].values]
        tabs = st.tabs(roles_present)

        for tab, role in zip(tabs, roles_present):
            with tab:
                df_role = cap_scores[cap_scores["capability_role"] == role].sort_values("avg_score")
                st.dataframe(df_role, width='stretch')

        st.divider()

        # ── High risk capabilities ──
        high_risk = cap_scores[cap_scores["avg_score"] < 2].sort_values("avg_score")
        if not high_risk.empty:
            st.markdown("### 🔴 High-risk capabilities")
            st.dataframe(
                high_risk[["capability_name", "domain", "capability_role", "avg_score", "gap"]],
                width='stretch',
            )
        else:
            st.success("No capabilities scored below 2.")

        # ── Executive summary ──
        st.divider()
        st.markdown("### Executive summary")

        top_gaps = cap_scores[cap_scores["gap"] > 0].sort_values("gap", ascending=False).head(5)

        # Auto-generate if no narrative exists and user is not in mid-confirm state
        if not st.session_state.get("findings_narrative") and not st.session_state.get("confirm_regen_narrative"):
            with st.spinner("Generating executive summary..."):
                from src.ai_client import generate_findings_narrative
                try:
                    narrative = generate_findings_narrative(
                        use_case_name=st.session_state.use_case_name,
                        intent_text=st.session_state.get("intent_text", ""),
                        overall_score=overall,
                        domain_scores=dom_scores.to_dict(orient="records"),
                        capability_scores=cap_scores.to_dict(orient="records"),
                        high_risk_caps=high_risk[["capability_name", "domain", "capability_role", "avg_score"]].to_dict(orient="records"),
                        top_gaps=top_gaps[["capability_name", "domain", "gap"]].to_dict(orient="records"),
                        client_name=st.session_state.get("client_name", ""),
                        client_industry=st.session_state.get("client_industry", ""),
                        client_country=st.session_state.get("client_country", ""),
                        client_stated_context=_build_client_stated_context(
                            st.session_state.get("responses", {})
                        ),
                    )
                    st.session_state.findings_narrative = narrative
                    # Persist to DB — overwritten each time a fresh version is generated
                    if st.session_state.get("assessment_id"):
                        try:
                            save_narrative(get_client(), st.session_state.assessment_id, narrative)
                        except Exception:
                            pass  # non-critical — summary still visible in session
                except Exception as e:
                    st.session_state.findings_narrative = None
                    st.error(f"Could not generate AI narrative: {e}")

        if st.session_state.get("findings_narrative"):
            st.markdown(st.session_state.findings_narrative)
            if not st.session_state.get("confirm_regen_narrative"):
                if st.button("Regenerate Summary"):
                    st.session_state.confirm_regen_narrative = True
                    st.rerun()
            else:
                st.warning("⚠️ This will replace the saved executive summary. Are you sure?")
                col_yn1, col_yn2, _ = st.columns([1, 1, 5])
                with col_yn1:
                    if st.button("Yes, regenerate", type="primary", key="confirm_regen_narr_yes"):
                        # Clear session only — DB will be overwritten once new narrative is saved
                        st.session_state.findings_narrative = None
                        st.session_state.confirm_regen_narrative = False
                        st.rerun()
                with col_yn2:
                    if st.button("Cancel", key="confirm_regen_narr_cancel"):
                        st.session_state.confirm_regen_narrative = False
                        st.rerun()

        st.divider()

        # ── Exports ──
        st.markdown("### Export")
        col_a, col_b, col_c, col_d = st.columns(4)

        with col_a:
            st.download_button(
                "Download Capability Scores (CSV)",
                data=cap_scores.to_csv(index=False).encode("utf-8"),
                file_name=f"{st.session_state.use_case_name}_capability_scores.csv".replace(" ", "_"),
                mime="text/csv",
            )
        with col_b:
            st.download_button(
                "Download Domain Scores (CSV)",
                data=dom_scores.to_csv(index=False).encode("utf-8"),
                file_name=f"{st.session_state.use_case_name}_domain_scores.csv".replace(" ", "_"),
                mime="text/csv",
            )
        with col_c:
            st.download_button(
                "Download All Responses (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"{st.session_state.use_case_name}_responses.csv".replace(" ", "_"),
                mime="text/csv",
            )
        with col_d:
            excel_bytes = generate_heatmap_excel(
                dom_scores.to_dict(orient="records"),
                client_name=st.session_state.get("client_name", ""),
                engagement_name=st.session_state.get("engagement_name", ""),
                use_case_name=st.session_state.use_case_name,
            )
            _client_slug = st.session_state.get("client_name", "Client").replace(" ", "_")
            st.download_button(
                "Download Heatmap (Excel)",
                data=excel_bytes,
                file_name=f"Meridant_Insight_{_client_slug}_Heatmap.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        st.divider()

        # ── Navigation ──
        col_nav_a, col_nav_b, col_nav_c = st.columns([1, 1, 1])
        with col_nav_a:
            if st.button("Start New Assessment"):
                for k in ["use_case_name", "intent_text", "client_name", "engagement_name",
                          "client_industry", "client_sector", "client_country",
                          "core_caps", "upstream_caps", "downstream_caps", "domains_covered",
                          "questions", "responses", "findings_narrative", "domain_targets",
                          "assessment_id", "findings_saved",
                          "assessment_mode", "selected_usecase_id", "show_new_form",
                          "roadmap_data", "responses_ai_scored", "recommendations",
                          "confirm_regen_narrative", "confirm_regen_recs"]:
                    if k in ["use_case_name", "intent_text", "client_name", "engagement_name",
                             "client_industry", "client_sector", "client_country"]:
                        st.session_state[k] = ""
                    elif k == "responses":
                        st.session_state[k] = {}
                    elif k in ("findings_narrative", "assessment_id", "roadmap_data",
                               "recommendations"):
                        st.session_state[k] = None
                    elif k in ("findings_saved", "responses_ai_scored",
                               "confirm_regen_narrative", "confirm_regen_recs"):
                        st.session_state[k] = False
                    elif k == "assessment_mode":
                        st.session_state[k] = "predefined"
                    elif k in ("selected_usecase_id",):
                        st.session_state[k] = None
                    elif k == "show_new_form":
                        st.session_state[k] = False
                    else:
                        st.session_state[k] = []
                st.session_state.wizard_step = 1
                st.rerun()
        with col_nav_b:
            if st.button("Generate Recommendations →", type="primary"):
                st.session_state.wizard_step = "5b"
                st.rerun()
        with col_nav_c:
            if st.button("Skip to Roadmap →"):
                st.session_state.wizard_step = 6
                st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 5b — Gap Recommendations
    # ─────────────────────────────────────────────────────────────────────────
    if st.session_state.wizard_step == "5b":
        st.subheader("Step 5b — Gap Recommendations")
        st.caption(
            "AI-generated per-capability recommendations grounded in E2CAF maturity "
            "descriptors, actual assessment responses, and dependency context."
        )

        from src.recommendation_engine import build_recommendations
        from src.assessment_store import save_recommendations, load_recommendations
        import json as _json

        db = get_client()
        assessment_id = st.session_state.get("assessment_id")

        # ── Recompute cap_scores (same logic as Step 5) ───────────────────────
        responses = st.session_state.get("responses", {})
        if not responses:
            st.warning("No responses found. Please complete Step 4 first.")
            if st.button("← Back to Findings"):
                st.session_state.wizard_step = 5
                st.rerun()
            st.stop()

        scored_vals = [v for v in responses.values() if v.get("score") is not None]
        if not scored_vals:
            st.warning("No scored responses found — return to Step 5 and complete scoring.")
            if st.button("← Back to Findings", key="5b_back_no_scores"):
                st.session_state.wizard_step = 5
                st.rerun()
            st.stop()

        import pandas as _pd
        _df = _pd.DataFrame(scored_vals)
        _cap_agg = (
            _df.groupby(["capability_id", "capability_name", "domain", "subdomain", "capability_role"])
            ["score"].mean().reset_index().rename(columns={"score": "avg_score"})
        )
        _cap_agg["avg_score"] = _cap_agg["avg_score"].round(1)
        _domain_targets = st.session_state.get("domain_targets", {})
        _cap_agg["target"] = _cap_agg["domain"].map(lambda d: _domain_targets.get(d, 3))
        _cap_agg["gap"] = _cap_agg["target"] - _cap_agg["avg_score"]
        cap_scores_5b = _cap_agg.to_dict(orient="records")

        # ── Try to load from DB if session is empty (e.g. after page reload) ──
        recs = st.session_state.get("recommendations")
        if recs is None and assessment_id:
            recs = load_recommendations(db, assessment_id)
            if recs:
                st.session_state.recommendations = recs

        # ── Generation controls ───────────────────────────────────────────────
        gap_caps_5b = [c for c in cap_scores_5b if (c.get("gap") or 0) > 0]
        gap_count = len(gap_caps_5b)

        with st.container(border=True):
            st.markdown("#### Recommendation settings")

            col_s1, col_s2 = st.columns(2)
            with col_s1:
                scope_opts = ["All priorities", "P1 only", "P1 + P2"]
                scope_sel = st.radio(
                    "Priority scope",
                    scope_opts,
                    horizontal=True,
                    key="rec_scope_sel",
                    help="Pre-filter which priority tiers to generate recommendations for.",
                )

            # Pre-filter by selected priority scope.
            # Priority is determined by the same logic as the engine, so compute tiers here.
            def _preview_tier(c):
                g = float(c.get("gap") or 0)
                role = c.get("capability_role", "")
                if g >= 2.0 or (role == "Core" and g >= 1.5):
                    return "P1"
                if g >= 1.0:
                    return "P2"
                return "P3"

            if scope_sel == "P1 only":
                eligible_caps = [c for c in gap_caps_5b if _preview_tier(c) == "P1"]
            elif scope_sel == "P1 + P2":
                eligible_caps = [c for c in gap_caps_5b if _preview_tier(c) in ("P1", "P2")]
            else:
                eligible_caps = gap_caps_5b

            eligible_count = len(eligible_caps)

            with col_s2:
                if eligible_count == 0:
                    st.caption("No capabilities match the selected scope.")
                    max_caps = 0
                elif eligible_count == 1:
                    max_caps = 1
                    st.caption("1 capability in scope — all will be analysed.")
                else:
                    max_caps = st.slider(
                        "Number of capabilities to analyse",
                        min_value=1,
                        max_value=eligible_count,
                        value=min(eligible_count, 20),
                        key="rec_max_caps_slider",
                        help="Capabilities are ranked by gap size (largest first), Core role prioritised.",
                    )

            st.caption(
                f"{gap_count} total gap capabilities · "
                f"{eligible_count} in scope · "
                f"{max_caps} will be analysed."
            )

            col_r1, col_r2 = st.columns([3, 1])
            with col_r2:
                if not recs:
                    # First run — no confirmation needed
                    run_btn = st.button("Generate Recommendations", type="primary", disabled=(max_caps == 0))
                elif not st.session_state.get("confirm_regen_recs"):
                    # Existing recs — ask for confirmation first
                    run_btn = False
                    if st.button("Regenerate", type="primary", disabled=(max_caps == 0)):
                        st.session_state.confirm_regen_recs = True
                        st.rerun()
                else:
                    # Waiting for user to confirm in the dialog below
                    run_btn = False

        # Confirm-before-overwrite dialog (rendered outside the settings container)
        if recs and st.session_state.get("confirm_regen_recs"):
            st.warning("⚠️ This will overwrite the saved recommendations for this assessment. Are you sure?")
            col_yn1, col_yn2, _ = st.columns([1, 1, 5])
            with col_yn1:
                if st.button("Yes, overwrite", type="primary", key="confirm_overwrite_recs"):
                    st.session_state.confirm_regen_recs = False
                    run_btn = True
            with col_yn2:
                if st.button("Cancel", key="cancel_overwrite_recs"):
                    st.session_state.confirm_regen_recs = False
                    st.rerun()

        if run_btn:
            st.session_state.recommendations = None
            progress_text = st.empty()
            progress_bar = st.progress(0)

            def _on_progress(idx, total, name):
                if total > 0:
                    progress_bar.progress(idx / total)
                if name != "Complete":
                    progress_text.caption(f"Analysing: **{name}** ({idx + 1}/{total})")
                else:
                    progress_text.caption("Recommendations complete.")
                    progress_bar.progress(1.0)

            try:
                recs = build_recommendations(
                    db=db,
                    assessment_id=assessment_id or 0,
                    cap_scores=eligible_caps,  # already filtered by scope
                    client_industry=st.session_state.get("client_industry", ""),
                    intent_text=st.session_state.get("intent_text", ""),
                    usecase_id=st.session_state.get("selected_usecase_id"),
                    max_caps=max_caps,
                    on_progress=_on_progress,
                    client_country=st.session_state.get("client_country", ""),
                )
                st.session_state.recommendations = recs
                if assessment_id:
                    save_recommendations(db, assessment_id, recs)
            except Exception as _e:
                st.error(f"Recommendation generation failed: {_e}")
                recs = st.session_state.get("recommendations")

        # ── Display recommendations ───────────────────────────────────────────
        recs = st.session_state.get("recommendations")
        if recs:
            st.divider()

            # Summary strip
            p1 = sum(1 for r in recs if r.get("priority_tier") == "P1")
            p2 = sum(1 for r in recs if r.get("priority_tier") == "P2")
            p3 = sum(1 for r in recs if r.get("priority_tier") == "P3")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Capabilities analysed", len(recs))
            c2.metric("P1 — Foundation", p1)
            c3.metric("P2 — Acceleration", p2)
            c4.metric("P3 — Optimisation", p3)

            # Priority filter
            tier_filter = st.radio(
                "Show", ["All", "P1 only", "P2 only", "P3 only"],
                horizontal=True, key="rec_tier_filter"
            )
            filter_map = {"P1 only": "P1", "P2 only": "P2", "P3 only": "P3"}
            filtered_recs = (
                [r for r in recs if r.get("priority_tier") == filter_map[tier_filter]]
                if tier_filter != "All" else recs
            )

            tier_colours = {"P1": "🔴", "P2": "🟡", "P3": "🟢"}
            for rec in filtered_recs:
                tier = rec.get("priority_tier", "P2")
                expanded = tier == "P1"
                label = (
                    f"{tier_colours.get(tier, '')} **[{tier}]** "
                    f"{rec['capability_name']} | {rec['domain']} | "
                    f"gap: {rec['gap']:.1f} | {rec.get('capability_role', '')} | "
                    f"{rec.get('effort_estimate', '')}"
                )
                with st.expander(label, expanded=expanded):
                    if rec.get("narrative"):
                        st.markdown(rec["narrative"])
                    st.markdown("**Recommended actions:**")
                    for action in rec.get("recommended_actions", []):
                        st.markdown(f"- {action}")
                    if rec.get("enabling_dependencies"):
                        st.markdown("**Must be in place first:**")
                        for dep in rec["enabling_dependencies"]:
                            st.markdown(f"- {dep}")
                    if rec.get("success_indicators"):
                        st.markdown("**Success indicators:**")
                        for ind in rec["success_indicators"]:
                            st.markdown(f"- {ind}")

            # Export
            st.divider()
            st.markdown("### Export")
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                import csv, io as _io
                _csv_buf = _io.StringIO()
                _fields = [
                    "capability_name", "domain", "capability_role", "current_score",
                    "target_maturity", "gap", "priority_tier", "effort_estimate",
                    "narrative",
                ]
                _writer = csv.DictWriter(_csv_buf, fieldnames=_fields, extrasaction="ignore")
                _writer.writeheader()
                _writer.writerows(recs)
                st.download_button(
                    "Download CSV",
                    data=_csv_buf.getvalue(),
                    file_name=f"{st.session_state.use_case_name}_recommendations.csv".replace(" ", "_"),
                    mime="text/csv",
                )
            with col_e2:
                st.download_button(
                    "Download JSON",
                    data=_json.dumps(recs, indent=2),
                    file_name=f"{st.session_state.use_case_name}_recommendations.json".replace(" ", "_"),
                    mime="application/json",
                )

        # ── Navigation ────────────────────────────────────────────────────────
        st.divider()
        col_5b_a, col_5b_b = st.columns([1, 1])
        with col_5b_a:
            if st.button("← Back to Findings"):
                st.session_state.wizard_step = 5
                st.rerun()
        with col_5b_b:
            if st.button("Continue to Roadmap →", type="primary"):
                st.session_state.wizard_step = 6
                st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6 — Transformation Roadmap
    # ─────────────────────────────────────────────────────────────────────────
    if st.session_state.wizard_step == 6:
        st.subheader("Step 6 — Transformation Roadmap")
        st.caption("AI-generated gap-closure roadmap prioritised by maturity gaps and business intent.")

        from src.roadmap import render_roadmap_gantt_html, generate_roadmap_excel, TIMELINE_UNITS
        from src.ai_client import generate_roadmap_plan

        # ── Need findings data (recompute from responses) ──────────────────
        responses = st.session_state.get("responses", {})
        if not responses:
            st.warning("No assessment responses found. Please complete the assessment in Step 4 first.")
            if st.button("← Back to Findings"):
                st.session_state.wizard_step = 5
                st.rerun()
        else:
            # Recompute cap/domain scores (same logic as Step 5)
            scored = {k: v for k, v in responses.items() if v.get("score") is not None}
            if not scored:
                st.warning("This assessment has no numeric scores — the roadmap requires at least some scored responses.")
                if st.button("← Back to Findings", key="back_findings_no_scores"):
                    st.session_state.wizard_step = 5
                    st.rerun()
                st.stop()

            df = pd.DataFrame(scored.values())

            cap_agg = (
                df.groupby(["capability_id", "capability_name", "domain", "subdomain", "capability_role"])
                ["score"].mean()
                .reset_index()
                .rename(columns={"score": "avg_score"})
            )
            cap_agg["avg_score"] = cap_agg["avg_score"].round(1)
            domain_targets = st.session_state.get("domain_targets", {})
            cap_agg["target"] = cap_agg["domain"].map(lambda d: domain_targets.get(d, 3))
            cap_agg["gap"]    = cap_agg["target"] - cap_agg["avg_score"]
            cap_scores_list   = cap_agg.to_dict(orient="records")

            dom_agg = (
                df.groupby("domain")["score"].mean()
                .reset_index()
                .rename(columns={"score": "avg_score"})
            )
            dom_agg["avg_score"] = dom_agg["avg_score"].round(1)
            dom_agg["target"] = dom_agg["domain"].map(lambda d: domain_targets.get(d, 3))
            dom_agg["gap"]    = dom_agg["target"] - dom_agg["avg_score"]
            dom_scores_list   = dom_agg.to_dict(orient="records")

            overall = round(df["score"].mean(), 1)

            # ── Settings ──────────────────────────────────────────────────────
            with st.container(border=True):
                st.markdown("#### Roadmap settings")
                col_s1, col_s2, col_s3 = st.columns(3)

                with col_s1:
                    timeline_unit = st.selectbox(
                        "Timeline unit",
                        TIMELINE_UNITS,
                        index=TIMELINE_UNITS.index(st.session_state.roadmap_timeline_unit)
                        if st.session_state.roadmap_timeline_unit in TIMELINE_UNITS else 0,
                        key="roadmap_timeline_unit_select",
                    )
                    st.session_state.roadmap_timeline_unit = timeline_unit

                with col_s2:
                    horizon_options = [3, 6, 9, 12, 18, 24]
                    current_horizon = st.session_state.roadmap_horizon_months
                    horizon_idx = horizon_options.index(current_horizon) if current_horizon in horizon_options else 1
                    horizon_months = st.selectbox(
                        "Horizon (months)",
                        horizon_options,
                        index=horizon_idx,
                        key="roadmap_horizon_select",
                    )
                    st.session_state.roadmap_horizon_months = horizon_months

                with col_s3:
                    scope_options = ["Core", "Core + Upstream", "All"]
                    current_scope = st.session_state.roadmap_scope
                    scope_idx = scope_options.index(current_scope) if current_scope in scope_options else 0
                    roadmap_scope = st.selectbox(
                        "Capability scope",
                        scope_options,
                        index=scope_idx,
                        key="roadmap_scope_select",
                    )
                    st.session_state.roadmap_scope = roadmap_scope

                recs_for_roadmap = st.session_state.get("recommendations")
                if recs_for_roadmap:
                    st.info(
                        f"Roadmap will be structured using {len(recs_for_roadmap)} "
                        "gap recommendations from Step 5b."
                    )
                else:
                    st.caption(
                        "No recommendations loaded. Run Step 5b first for a "
                        "recommendation-aligned roadmap, or generate below using scores only."
                    )

                if st.button("Generate Roadmap", type="primary"):
                    st.session_state.roadmap_data = None  # clear stale data
                    with st.spinner("Generating transformation roadmap with AI…"):
                        try:
                            roadmap = generate_roadmap_plan(
                                use_case_name=st.session_state.use_case_name,
                                intent_text=st.session_state.get("intent_text", ""),
                                cap_scores=cap_scores_list,
                                dom_scores=dom_scores_list,
                                overall_score=overall,
                                horizon_months=horizon_months,
                                scope=roadmap_scope,
                                recommendations=recs_for_roadmap,
                                client_name=st.session_state.get("client_name", ""),
                                client_industry=st.session_state.get("client_industry", ""),
                                client_country=st.session_state.get("client_country", ""),
                                client_stated_context=_build_client_stated_context(
                                    st.session_state.get("responses", {})
                                ),
                            )
                            st.session_state.roadmap_data = roadmap
                        except Exception as e:
                            st.error(f"Could not generate roadmap: {e}")

            # ── Roadmap display ───────────────────────────────────────────────
            roadmap = st.session_state.get("roadmap_data")
            if roadmap:
                st.divider()
                st.markdown("### Gap-Closure Roadmap")

                # Gantt chart
                gantt_html = render_roadmap_gantt_html(roadmap, timeline_unit)
                n_initiatives = sum(
                    len(ph.get("initiatives", []))
                    for ph in roadmap.get("phases", [])
                )
                gantt_h = max(400, 200 + n_initiatives * 36 + len(roadmap.get("phases", [])) * 60)
                components.html(gantt_html, height=gantt_h, scrolling=True)

                st.divider()

                # Phase narratives
                st.markdown("### Phase Narratives")
                for phase in roadmap.get("phases", []):
                    with st.expander(f"**{phase.get('name', '')}**", expanded=True):
                        if phase.get("story"):
                            st.markdown(f"*{phase['story']}*")
                        if phase.get("description"):
                            st.markdown(phase["description"])
                        if phase.get("activities"):
                            st.markdown("**Key activities:**")
                            for act in phase["activities"]:
                                st.markdown(f"- {act}")

                st.divider()

                # Export
                st.markdown("### Export")
                excel_bytes = generate_roadmap_excel(
                    roadmap=roadmap,
                    client_name=st.session_state.get("client_name", ""),
                    engagement_name=st.session_state.get("engagement_name", ""),
                    use_case_name=st.session_state.use_case_name,
                )
                _client_slug = st.session_state.get("client_name", "Client").replace(" ", "_")
                st.download_button(
                    "Download Roadmap (Excel)",
                    data=excel_bytes,
                    file_name=f"Meridant_Insight_{_client_slug}_Roadmap.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

            st.divider()

            # ── Navigation ────────────────────────────────────────────────────
            col_back, _ = st.columns([1, 3])
            with col_back:
                if st.button("← Back to Findings"):
                    st.session_state.wizard_step = 5
                    st.rerun()

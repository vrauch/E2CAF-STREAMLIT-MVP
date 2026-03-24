import base64
import os
import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from src.meridant_client import get_client
from src.assessment_builder import analyze_use_case_readonly, CapabilityResult
from src.assessment_store import (
    save_assessment, save_assessment_shell, upsert_capabilities, save_questions,
    save_findings, save_narrative, load_assessment,
    save_roadmap, load_roadmap,
    save_roadmap_progress, load_roadmap_progress,
    save_respondent_responses, load_respondent_sets,
    reset_assessment_data,
)
from src.question_generator import generate_questions_for_capability
from src.sql_templates import (
    q_list_next_usecases,
    get_frameworks,
    get_framework_labels,
    get_use_cases_for_framework,
)
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

# ─────────────────────────────────────────────────────────────────────────────
# Helpers for predefined use case loading
# ─────────────────────────────────────────────────────────────────────────────

def _load_predefined_usecases(client, framework_id: int = 1) -> list[dict]:
    """Return [{id, usecase_title, usecase_description, business_value}] from Next_UseCase,
    filtered to the given framework."""
    res = client.query(
        "SELECT id, usecase_title, "
        "COALESCE(usecase_description, '') AS usecase_description, "
        "COALESCE(business_value, '') AS business_value, "
        "COALESCE(owner_role, '') AS owner_role "
        "FROM Next_UseCase WHERE framework_id = ? ORDER BY usecase_title",
        [int(framework_id)]
    )
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
    fw_id = usecase_id  # framework_id sourced from caller via session; passed through below
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
              AND nc.framework_id = (
                  SELECT framework_id FROM Next_UseCase WHERE id = {int(usecase_id)} LIMIT 1
              )
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

    # Framework context — restore labels so all wizard steps use the correct terminology
    _fw_id = a.get("framework_id", 1) or 1
    st.session_state.framework_id = _fw_id
    _fw_client = get_client()
    st.session_state.framework_labels = get_framework_labels(_fw_client, _fw_id)

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
    # Only skip AI scoring if every response that has an answer already has a score.
    # This avoids re-running expensive AI scoring on completed assessments.
    _all_scored = all(
        v.get("score") is not None
        for v in response_dict.values()
        if v.get("answer") or (v.get("response_type") == "maturity_1_5")
    )
    st.session_state.responses_ai_scored   = _all_scored
    st.session_state.confirm_regen_narrative  = False
    st.session_state.confirm_regen_recs       = False
    st.session_state.confirm_regen_questions  = False
    st.session_state.confirm_rediscover       = False
    st.session_state.show_questions_table     = False
    st.session_state.respondent_sets          = load_respondent_sets(_fw_client, a["id"])

    # Restore recommendations for this specific assessment (always reload from DB to avoid
    # stale data from a previously-viewed assessment bleeding into this one)
    from src.assessment_store import load_recommendations as _load_recs
    _recs = _load_recs(_fw_client, a["id"])
    st.session_state.recommendations = _recs if _recs else None

    # Restore roadmap if previously generated
    _rmap = load_roadmap(_fw_client, a["id"])
    if _rmap:
        st.session_state.roadmap_data          = _rmap["roadmap"]
        st.session_state.roadmap_timeline_unit = _rmap["timeline_unit"]
        st.session_state.roadmap_horizon_months = _rmap["horizon_months"]
        st.session_state.roadmap_scope         = _rmap["scope"]
    else:
        st.session_state.roadmap_data = None

    # Restore roadmap progress
    if a.get("id"):
        st.session_state.roadmap_progress = load_roadmap_progress(_fw_client, a["id"])
    else:
        st.session_state.roadmap_progress = {}

    # ── Smart step detection — resume at the correct wizard step ──────────────
    # Determine where the assessment was interrupted based on what is saved in DB:
    #   No capabilities        → Step 1 (just started)
    #   Caps but no responses  → Step 3 (need to generate/re-load questions)
    #   Blank responses (all score=None AND answer=None) → Step 4 (questions saved, workshop pending)
    #   Roadmap persisted      → Step 6 (roadmap already generated)
    #   Any scored response    → Step 5 (responses captured, show findings)
    #   status = 'complete'    → Step 5 (findings already computed)
    if not caps:
        resume_step = 1
    elif not responses:
        resume_step = 3
    elif all(r.get("score") is None and r.get("answer") is None for r in responses):
        resume_step = 4
    elif _rmap:
        resume_step = 6
    else:
        resume_step = 5
    st.session_state.wizard_step = resume_step

    # ── Restore completed_steps for breadcrumb navigation ─────────────────────
    _mode       = a.get("assessment_mode", "custom") or "custom"
    _step_order = _get_wizard_steps(_mode)
    _completed: set = set()
    for _sk, _, _ in _step_order:
        if _sk == resume_step:
            break
        _completed.add(_sk)
    # If recommendations were loaded, step 5b was also previously completed
    if _recs and resume_step in (5, 6):
        _completed.add(5)
        _completed.add("5b")
    st.session_state.completed_steps = _completed


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


# ─────────────────────────────────────────────────────────────────────────────
# Wizard breadcrumb navigation
# ─────────────────────────────────────────────────────────────────────────────

def _get_wizard_steps(mode: str = "custom") -> list[tuple]:
    """Return ordered list of (step_key, display_num, label) for the wizard.

    Step 2 (Capability Discovery) is included for custom mode only; it is
    skipped (never shown) for predefined mode.
    """
    steps = [(1, "1", "Client & Use Case")]
    if mode == "custom":
        steps.append((2, "2", "Capability Discovery"))
    steps += [
        ("2b", "3" if mode == "custom" else "2", "Domain Targets"),
        (3,    "4" if mode == "custom" else "3", "Questions"),
        (4,    "5" if mode == "custom" else "4", "Responses"),
        (5,    "6" if mode == "custom" else "5", "Findings"),
        ("5b", "7" if mode == "custom" else "6", "Recommendations"),
        (6,    "8" if mode == "custom" else "7", "Roadmap"),
    ]
    return steps


_BS_CDN = (
    '<link rel="stylesheet" '
    'href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" '
    'crossorigin="anonymous">'
)
_NAV_JS = """
<script>
function triggerNav(key){
  var sel='[class*="st-key-_nav_btn_'+key+'"]';
  var wrap=window.parent.document.querySelector(sel);
  if(wrap){var btn=wrap.querySelector('button');if(btn)btn.click();}
}
// MutationObserver — applies inline styles to hidden triggers so they win
// the specificity battle against Streamlit's emotion CSS (same (0,1,0) weight).
(function(){
  var HIDE='height:0!important;min-height:0!important;overflow:hidden!important;'+
      'padding:0!important;margin:0!important;opacity:0!important;pointer-events:none!important;';
  function hideEl(el){
    if(el&&el.className&&typeof el.className==='string'&&
       el.className.indexOf('st-key-_nav_btn_')!==-1){
      el.setAttribute('style',HIDE);
    }
  }
  function scanNode(node){
    if(node.nodeType===1){hideEl(node);node.childNodes.forEach(scanNode);}
  }
  try{
    scanNode(window.parent.document.body);
    var obs=new window.parent.MutationObserver(function(muts){
      muts.forEach(function(m){m.addedNodes.forEach(scanNode);});
    });
    obs.observe(window.parent.document.body,{childList:true,subtree:true});
    setTimeout(function(){obs.disconnect();},5000);
  }catch(e){}
})();
</script>"""


def _render_nav_row(*buttons) -> dict:
    """Render a Bootstrap btn-sm button row and return {key: bool} for clicked buttons.

    Each button dict: label, key, style (Bootstrap suffix e.g. 'primary',
    'outline-secondary'), disabled (optional bool).
    """
    triggers = {btn["key"]: st.button("_", key=f"_nav_btn_{btn['key']}") for btn in buttons}

    btn_html = "".join(
        f'<button class="btn btn-{b["style"]} btn-sm" '
        f'onclick="triggerNav(\'{b["key"]}\')"'
        f'{" disabled" if b.get("disabled") else ""}>{b["label"]}</button>'
        for b in buttons
    )
    st.components.v1.html(
        f'<!DOCTYPE html><html><head>{_BS_CDN}</head>'
        f'<body style="background:transparent;margin:0;padding:6px 0;">'
        f'<div class="d-flex gap-2 flex-wrap">{btn_html}</div>'
        f'{_NAV_JS}</body></html>',
        height=48,
    )
    return triggers


def _export_btn_row(*items) -> None:
    """Render a row of Bootstrap btn-sm download anchor tags.

    Each item dict: label, data (bytes|str), filename, mime, style (optional, default 'outline-secondary').
    """
    links = []
    for item in items:
        data = item["data"]
        if isinstance(data, str):
            data = data.encode("utf-8")
        b64 = base64.b64encode(data).decode()
        mime = item.get("mime", "application/octet-stream")
        style = item.get("style", "outline-secondary")
        links.append(
            f'<a href="data:{mime};base64,{b64}" download="{item["filename"]}" '
            f'class="btn btn-{style} btn-sm">{item["label"]}</a>'
        )
    st.components.v1.html(
        f'<!DOCTYPE html><html><head>{_BS_CDN}</head>'
        f'<body style="background:transparent;margin:0;padding:6px 0;">'
        f'<div class="d-flex gap-2 flex-wrap">{"".join(links)}</div>'
        f'</body></html>',
        height=48,
    )


def _render_breadcrumbs() -> None:
    """Render wizard step breadcrumb navigation above the current step.

    Completed steps render as dark clickable text links (navigate back to that step).
    The current step renders as bold navy text.
    Future steps render as greyed-out text.

    Navigation uses hidden st.button bridges.  CSS collapses them to zero height
    (opacity:0, height:0) so they are invisible but still in the DOM, allowing the
    HTML component JS to call .click() on them programmatically.
    display:none is intentionally avoided — it prevents .click() in some browsers.
    """
    current   = st.session_state.wizard_step
    completed = st.session_state.get("completed_steps", set())
    mode      = st.session_state.get("assessment_mode", "custom")
    steps     = _get_wizard_steps(mode)

    # ── CSS: hide nav-trigger button containers via the key class Streamlit injects ──
    # Streamlit renders key="_bc_btn_1" as class "st-key-_bc_btn_1" on the wrapper div.
    # aria-label is empty in Streamlit 1.45+ so we cannot use attribute selectors on it.
    st.markdown(
        """<style>
        [class*="st-key-_bc_btn_"]{
            height:0!important;min-height:0!important;
            overflow:hidden!important;padding:0!important;margin:0!important;
            opacity:0!important;pointer-events:none!important;
        }
        </style>""",
        unsafe_allow_html=True,
    )

    # ── Hidden navigation trigger buttons (one per completed step) ────────────
    nav_clicked = None
    for key, _, _ in steps:
        if key in completed:
            if st.button(f"_bc_{key}_", key=f"_bc_btn_{key}"):
                nav_clicked = key

    if nav_clicked is not None:
        st.session_state.wizard_step = nav_clicked
        st.rerun()

    # ── Build Bootstrap breadcrumb HTML ───────────────────────────────────────
    crumb_parts = []
    for key, num, name in steps:
        is_current = key == current
        is_done    = key in completed

        if is_done:
            crumb_parts.append(
                f'<span class="bc bc-done" onclick="navTo(\'{key}\')" '
                f'title="Return to {name}">{name}</span>'
            )
        elif is_current:
            crumb_parts.append(f'<span class="bc bc-current">{name}</span>')
        else:
            crumb_parts.append(f'<span class="bc bc-future">{name}</span>')

    sep   = '<span class="bc-sep">&gt;</span>'
    trail = sep.join(crumb_parts)

    html = f"""<!DOCTYPE html><html><head><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:transparent;font-family:Inter,-apple-system,sans-serif;
     font-size:13px;padding:4px 2px 6px;}}
.breadcrumb-trail{{display:flex;align-items:center;flex-wrap:wrap;gap:1px;
    border-bottom:1px solid #E5E7EB;padding-bottom:7px;}}
.bc{{padding:2px 4px;white-space:nowrap;line-height:1.6;}}
.bc-done{{color:#111827;cursor:pointer;text-decoration:underline;font-weight:500;}}
.bc-done:hover{{color:#0F2744;text-decoration:underline;opacity:0.75;}}
.bc-current{{color:#0F2744;font-weight:700;}}
.bc-future{{color:#9CA3AF;}}
.bc-sep{{color:#6B7280;font-size:13px;padding:0 4px;line-height:1.6;font-weight:500;}}
</style></head><body>
<div class="breadcrumb-trail">{trail}</div>
<script>
function navTo(stepKey){{
    // Find trigger button by the st-key-_bc_btn_<key> class Streamlit adds to the wrapper.
    try{{
        var sel='[class*="st-key-_bc_btn_'+String(stepKey)+'"]';
        var wrap=window.parent.document.querySelector(sel);
        if(wrap){{
            var btn=wrap.querySelector('button');
            if(btn){{btn.click();return;}}
        }}
    }}catch(e){{console.warn('Breadcrumb nav error:',e);}}
}}
// Hide nav-trigger containers via the st-key class.
// MutationObserver fires before paint so there is no visible flash.
(function(){{
    var HIDE='height:0!important;min-height:0!important;overflow:hidden!important;'+
        'padding:0!important;margin:0!important;opacity:0!important;pointer-events:none!important;';
    function hideEl(el){{
        if(el&&el.className&&typeof el.className==='string'&&
           el.className.indexOf('st-key-_bc_btn_')!==-1){{
            el.style.cssText=HIDE;
        }}
    }}
    function scanNode(n){{
        if(!n)return;
        hideEl(n);
        if(n.querySelectorAll){{
            n.querySelectorAll('[class*="st-key-_bc_btn_"]').forEach(function(el){{
                el.style.cssText=HIDE;
            }});
        }}
    }}
    try{{
        scanNode(window.parent.document.body);
        var obs=new window.parent.MutationObserver(function(muts){{
            muts.forEach(function(m){{m.addedNodes.forEach(scanNode);}});
        }});
        obs.observe(window.parent.document.body,{{childList:true,subtree:true}});
        setTimeout(function(){{obs.disconnect();}},5000);
    }}catch(e){{}}
}})();
</script></body></html>"""

    components.html(html, height=48, scrolling=False)


def render():
    st.title("Create Assessment")

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
    st.session_state.setdefault("respondent_sets", [])   # raw per-respondent uploads
    st.session_state.setdefault("findings_narrative", None)
    st.session_state.setdefault("domain_targets", {})
    st.session_state.setdefault("assessment_id", None)
    st.session_state.setdefault("findings_saved", False)
    st.session_state.setdefault("roadmap_data", None)
    st.session_state.setdefault("roadmap_timeline_unit", "Sprints (2 wks)")
    st.session_state.setdefault("roadmap_horizon_months", 6)
    st.session_state.setdefault("roadmap_scope", "Core")
    st.session_state.setdefault("roadmap_progress", {})
    st.session_state.setdefault("responses_ai_scored", False)
    st.session_state.setdefault("recommendations", None)
    st.session_state.setdefault("confirm_regen_narrative", False)
    st.session_state.setdefault("confirm_regen_recs", False)
    st.session_state.setdefault("confirm_regen_questions", False)
    st.session_state.setdefault("confirm_rediscover", False)
    st.session_state.setdefault("framework_id", 1)
    st.session_state.setdefault("framework_labels", {"level1": "Pillar", "level2": "Domain", "level3": "Capability"})
    st.session_state.setdefault("completed_steps", set())

    # -------------------------
    # STEP 1
    # -------------------------
    if st.session_state.wizard_step == 1:
        _render_breadcrumbs()
        st.title("Step 1 — Client & Use Case")

        # ── NEW ASSESSMENT FORM ───────────────────────────────────────────────

        st.markdown(
            "Enter the client details, name your use case, and describe the client intent. "
            "The intent should capture what the client is trying to achieve — their goals, "
            "scope, and priorities for this engagement."
        )

        # Force custom mode (predefined mode is disabled for now)
        mode = "custom"
        st.session_state.assessment_mode = "custom"

        _fw_db = get_client()
        _frameworks = get_frameworks(_fw_db)

        # ── The submission form — contains client fields + editable intent ─
        with st.form("step1_form", clear_on_submit=False):
            st.subheader("Client details")
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
            _industry_opts = ["", "Education", "Financial Services", "Government",
                              "Healthcare", "Manufacturing", "Retail", "Telecommunications",
                              "Energy & Utilities", "Professional Services", "Other"]
            _sector_opts = ["", "Public", "Private", "Non-Profit"]
            _saved_industry = st.session_state.get("client_industry", "")
            _saved_sector = st.session_state.get("client_sector", "")
            with col_c:
                industry = st.selectbox(
                    "Industry",
                    _industry_opts,
                    index=_industry_opts.index(_saved_industry) if _saved_industry in _industry_opts else 0,
                )
            with col_d:
                sector = st.selectbox(
                    "Sector",
                    _sector_opts,
                    index=_sector_opts.index(_saved_sector) if _saved_sector in _sector_opts else 0,
                )
            with col_e:
                country = st.text_input(
                    "Country",
                    value=st.session_state.get("client_country", ""),
                    placeholder="e.g., Australia",
                )

            st.divider()
            st.subheader("Choose Assessment Framework")
            if _frameworks:
                _fw_options = {f["id"]: f["framework_name"] for f in _frameworks}
                _fw_keys = list(_fw_options.keys())
                _fw_current = st.session_state.get("framework_id", 1)
                _fw_idx = _fw_keys.index(_fw_current) if _fw_current in _fw_keys else 0
                selected_framework_id = st.selectbox(
                    "Choose Assessment Framework",
                    options=_fw_keys,
                    format_func=lambda x: _fw_options[x],
                    index=_fw_idx,
                    key="framework_selector",
                    label_visibility="collapsed",
                )
                _fw_labels = get_framework_labels(_fw_db, selected_framework_id)
                st.caption(
                    f"Assessing against: **{_fw_labels['level1']}s** → "
                    f"**{_fw_labels['level2']}s** → **{_fw_labels['level3']}s**"
                )
            else:
                selected_framework_id = st.session_state.get("framework_id", 1)

            st.divider()
            st.subheader("Use case & client intent")

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
            st.session_state.client_name        = client_name.strip()
            st.session_state.engagement_name    = engagement_name.strip()
            st.session_state.client_industry    = industry
            st.session_state.client_sector      = sector
            st.session_state.client_country     = country.strip()
            st.session_state["framework_id"]     = selected_framework_id
            st.session_state["framework_labels"] = get_framework_labels(_fw_db, selected_framework_id)
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
            st.session_state["framework_id"]     = selected_framework_id
            st.session_state["framework_labels"] = get_framework_labels(_fw_db, selected_framework_id)

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

                # ── Save assessment shell to DB immediately ────────────────
                db = get_client()
                # Clear stale data from any previously-loaded assessment before saving new one
                st.session_state.findings_narrative = None
                st.session_state.recommendations    = None
                st.session_state.roadmap_data        = None
                st.session_state.roadmap_progress    = {}
                st.session_state.assessment_id = save_assessment_shell(db, st.session_state)

                st.success(
                    f"Loaded **{cap_count}** capabilities for *{use_case_name}* "
                    f"({len(core)} core · {len(upstream)} upstream · {len(downstream)} downstream). "
                    f"Skipping capability discovery — proceeding to target maturity."
                )
                st.session_state.completed_steps.add(1)
                st.session_state.wizard_step = "2b"
                st.rerun()

            # ── Custom: proceed to Step 2 for AI discovery ──────────────────
            else:
                # ── Save assessment shell to DB immediately ────────────────
                db = get_client()
                # Clear stale data from any previously-loaded assessment before saving new one
                st.session_state.findings_narrative = None
                st.session_state.recommendations    = None
                st.session_state.roadmap_data        = None
                st.session_state.roadmap_progress    = {}
                st.session_state.assessment_id = save_assessment_shell(db, st.session_state)
                st.session_state.completed_steps.add(1)
                st.session_state.wizard_step = 2
                st.rerun()

    # -------------------------
    # STEP 2
    # -------------------------
    if st.session_state.wizard_step == 2:
        _render_breadcrumbs()
        st.title("Step 2 — Capability discovery (Core / Upstream / Downstream)")
        st.markdown(
            "Set the number of core capabilities and click **Run Capability Discovery**. "
            "The AI will analyse your intent against the capability library and classify capabilities "
            "as Core, Upstream, or Downstream. Review the results, then continue to set domain targets."
        )
        st.write(f"**Use case:** {st.session_state.use_case_name}")
        st.write(f"**Intent:** {st.session_state.intent_text}")


        colA, colB = st.columns(2)
        with colA:
            core_k = st.slider("How many Core capabilities?", 5, 20, 10)

        _already_discovered = bool(st.session_state.core_caps)

        # ── Confirm-before-overwrite guard ──────────────────────────────────────
        if st.session_state.get("confirm_rediscover"):
            st.error(
                "⛔ **This will permanently delete all assessment data for this engagement.**\n\n"
                "Re-running capability discovery will erase:\n"
                "- All questions and responses (including uploaded respondent sets)\n"
                "- All findings, scores, and the executive summary\n"
                "- All gap recommendations\n\n"
                "**This cannot be undone.** The assessment will restart from Step 2 with a new "
                "capability set. Any work already completed will be lost."
            )
            _rediscover_confirm = _render_nav_row(
                {"label": "Yes, delete everything and re-run",  "key": "s2_rediscover_yes",    "style": "danger"},
                {"label": "Cancel — keep existing data",        "key": "s2_rediscover_cancel",  "style": "outline-secondary"},
            )
            if _rediscover_confirm["s2_rediscover_cancel"]:
                st.session_state.confirm_rediscover = False
                st.rerun()
            run = _rediscover_confirm["s2_rediscover_yes"]
            if run:
                st.session_state.confirm_rediscover = False
                # Wipe all downstream DB data for this assessment
                if st.session_state.get("assessment_id"):
                    reset_assessment_data(get_client(), st.session_state.assessment_id)
                # Clear all downstream session state
                for _k in ("questions", "responses", "findings_narrative", "domain_targets",
                           "findings_saved", "responses_ai_scored", "recommendations",
                           "roadmap_data", "respondent_sets"):
                    if _k in ("questions",):
                        st.session_state[_k] = []
                    elif _k in ("responses", "domain_targets"):
                        st.session_state[_k] = {}
                    elif _k in ("findings_narrative", "roadmap_data", "recommendations"):
                        st.session_state[_k] = None
                    elif _k in ("findings_saved", "responses_ai_scored"):
                        st.session_state[_k] = False
                    elif _k == "respondent_sets":
                        st.session_state[_k] = []
                # Trim completed_steps back to step 1 only
                st.session_state.completed_steps = {
                    s for s in st.session_state.get("completed_steps", set()) if s == 1
                }
        else:
            _btn_label = "Re-run Capability Discovery" if _already_discovered else "Run Capability Discovery"
            run = bool(_render_nav_row(
                {"label": _btn_label, "key": "s2_run", "style": "primary"},
            )["s2_run"])
            if run and _already_discovered:
                # First click — show the confirm dialog instead of running
                st.session_state.confirm_rediscover = True
                st.rerun()
        # ────────────────────────────────────────────────────────────────────────

        if run and not st.session_state.get("confirm_rediscover"):
            client = get_client()
            candidates, core, upstream, downstream, covered, cap_count = analyze_use_case_readonly(
                client=client,
                intent_text=st.session_state.intent_text,
                core_k=core_k,
                framework_id=st.session_state.get("framework_id", 1),
            )
            st.caption(f"Capability library size: {cap_count}")

            # Store results in session state
            st.session_state.core_caps = [c.__dict__ for c in core]
            st.session_state.upstream_caps = [c.__dict__ for c in upstream]
            st.session_state.downstream_caps = [c.__dict__ for c in downstream]
            st.session_state.domains_covered = covered

            # Persist to DB immediately so a session reset doesn't lose the discovery.
            # domain_targets default to 3 here; Step 2b upsert_capabilities() will
            # overwrite with the consultant's chosen targets.
            if st.session_state.get("assessment_id"):
                upsert_capabilities(client, st.session_state.assessment_id, st.session_state)

            st.success("Capability discovery complete.")

        # Show results if available
        if st.session_state.core_caps:
            st.subheader("Core capabilities")
            df_core = pd.DataFrame(st.session_state.core_caps)
            cols_to_show = [c for c in ["capability_name", "domain_name", "subdomain_name", "score", "rationale"] if c in df_core.columns]
            st.dataframe(df_core[cols_to_show], use_container_width=True)

            st.subheader("Upstream capabilities")
            df_up = pd.DataFrame(st.session_state.upstream_caps)
            st.dataframe(df_up, use_container_width=True)

            st.subheader("Downstream capabilities")
            df_dn = pd.DataFrame(st.session_state.downstream_caps)
            st.dataframe(df_dn, use_container_width=True)

            st.subheader("Domains covered (derived from selected capabilities)")
            df_dom = pd.DataFrame(
                [{"domain": k, "capability_count": v} for k, v in st.session_state.domains_covered.items()]
            ).sort_values("capability_count", ascending=False)
            st.dataframe(df_dom, use_container_width=True)

        # Navigation controls
        _nav2 = _render_nav_row(
            {"label": "Back to Step 1",           "key": "s2_back",  "style": "outline-secondary"},
            {"label": "Continue: Set Domain Targets", "key": "s2_cont", "style": "primary"},
        )
        if _nav2["s2_back"]:
            st.session_state.wizard_step = 1
            st.rerun()
        if _nav2["s2_cont"]:
            if not st.session_state.core_caps:
                st.error("Run capability discovery first.")
            else:
                st.session_state.completed_steps.add(2)
                st.session_state.wizard_step = "2b"
                st.rerun()
    
    # -------------------------
    # STEP 2b — Domain Targets
    # -------------------------
    if st.session_state.wizard_step == "2b":
        _render_breadcrumbs()
        st.header("Step 2b — Set Target Maturity per Domain")
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

        st.subheader("Domain target maturity")
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
        _nav2b = _render_nav_row(
            {"label": "Back to Step 2",    "key": "s2b_back", "style": "outline-secondary"},
            {"label": "Continue to Step 3", "key": "s2b_cont", "style": "primary"},
        )
        if _nav2b["s2b_back"]:
            st.session_state.wizard_step = 2
            st.rerun()
        if _nav2b["s2b_cont"]:
            st.session_state.domain_targets = new_targets
            if st.session_state.get("assessment_id"):
                db = get_client()
                upsert_capabilities(db, st.session_state.assessment_id, st.session_state)
            st.session_state.completed_steps.add("2b")
            st.session_state.wizard_step = 3
            st.rerun()
                
    # -------------------------
    # STEP 3
    # -------------------------
    if st.session_state.wizard_step == 3:
        _render_breadcrumbs()
        st.title("Step 3 — Generate assessment questions")

        if not st.session_state.core_caps:
            st.warning("No discovered capabilities found. Go back to Step 2 and run capability discovery.")
            if st.button("Back to Step 2"):
                st.session_state.wizard_step = 2
                st.rerun()
            st.stop()

        st.session_state.setdefault("confirm_regen_questions", False)
        st.session_state.setdefault("show_questions_table", False)

        _has_questions = bool(st.session_state.questions)
        _has_responses = any(
            r.get("score") is not None or r.get("answer") is not None
            for r in st.session_state.responses.values()
        ) if isinstance(st.session_state.responses, dict) else bool(st.session_state.responses)

        # ── Contextual intro paragraph ──
        if not _has_questions:
            st.markdown(
                "Choose which capability tiers to include, set the number of questions per capability, "
                "and select a question style. Click **Generate Questions** to create the assessment instrument. "
                "You can download the questions as a CSV for offline completion."
            )
        elif _has_responses:
            st.markdown(
                f"**{len(st.session_state.questions)} questions** have been generated across "
                f"**{len(st.session_state.domains_covered)} domains** and responses have been recorded. "
                "The question set is locked — responses cannot be changed without starting a new assessment."
            )
        else:
            st.markdown(
                f"**{len(st.session_state.questions)} questions** have been generated across "
                f"**{len(st.session_state.domains_covered)} domains.** "
                "No responses have been recorded yet, so you can still regenerate the questions with different "
                "settings if needed. You can also download the response template as a CSV for offline completion."
            )

        # ── Generation controls — hidden once questions exist (re-shown for regen confirm) ──
        _show_controls = not _has_questions or st.session_state.confirm_regen_questions
        if _show_controls:
            include_upstream   = st.checkbox("Include upstream capabilities",   value=True)
            include_downstream = st.checkbox("Include downstream capabilities", value=True)
            st.subheader("Questions per capability")
            q_per_cap = st.slider("Questions per capability", 2, 7, 4, label_visibility="collapsed")
            st.subheader("Question style")
            style = st.selectbox(
                "Choose a question style",
                ["Maturity (1–5)", "Evidence (Yes/No + notes)", "Workshop (discussion)"],
            )
        else:
            include_upstream   = True
            include_downstream = True
            q_per_cap          = 4
            style              = "Maturity (1–5)"

        # ── Hidden Streamlit trigger buttons (zero-height, JS-clickable) ──
        _trigger_gen  = st.button("_gen",  key="_step3_btn_gen")
        _trigger_show = st.button("_show", key="_step3_btn_show")

        # ── Bootstrap btn-sm button row ──
        _gen_label = "Regenerate Questions" if _has_questions else "Generate Questions"
        _gen_dis   = "disabled" if (_has_responses or st.session_state.confirm_regen_questions) else ""
        _show_label = ("Hide Questions" if st.session_state.show_questions_table
                       else f"Show Questions ({len(st.session_state.questions)})")

        # Build show + download anchors (only when questions exist)
        _extra_html = ""
        if _has_questions:
            _df_tmp = pd.DataFrame(st.session_state.questions)
            _df_tmp["score"] = ""; _df_tmp["answer"] = ""; _df_tmp["notes"] = ""
            _csv_b64  = base64.b64encode(_df_tmp.to_csv(index=False).encode("utf-8")).decode()
            _csv_name = f"{st.session_state.use_case_name}_response_template.csv".replace(" ", "_")
            _extra_html = (
                f'<button class="btn btn-outline-secondary btn-sm" onclick="triggerStep3(\'show\')">{_show_label}</button>'
                f'<a href="data:text/csv;base64,{_csv_b64}" download="{_csv_name}" class="btn btn-outline-secondary btn-sm">&#128196; Download Response Template (CSV)</a>'
            )

        _step3_hide_js = (
            '(function(){'
            'var H="height:0!important;min-height:0!important;overflow:hidden!important;'
            'padding:0!important;margin:0!important;opacity:0!important;pointer-events:none!important;";'
            'function hide(el){if(el&&el.className&&typeof el.className==="string"&&'
            'el.className.indexOf("st-key-_step3_btn_")!==-1){el.setAttribute("style",H);}}'
            'function scan(n){if(n.nodeType===1){hide(n);n.childNodes.forEach(scan);}}'
            'try{scan(window.parent.document.body);'
            'var o=new window.parent.MutationObserver(function(ms){'
            'ms.forEach(function(m){m.addedNodes.forEach(scan);});});'
            'o.observe(window.parent.document.body,{childList:true,subtree:true});'
            'setTimeout(function(){o.disconnect();},5000);}catch(e){}'
            '})()'
        )
        st.components.v1.html(
            f'<!DOCTYPE html><html><head>{_BS_CDN}</head>'
            f'<body style="background:transparent;margin:0;padding:6px 0;">'
            f'<div class="d-flex gap-2 flex-wrap">'
            f'<button class="btn btn-primary btn-sm" onclick="triggerStep3(\'gen\')" {_gen_dis}>{_gen_label}</button>'
            f'{_extra_html}</div>'
            f'<script>'
            f'function triggerStep3(name){{'
            f'var sel=\'[class*="st-key-_step3_btn_\'+name+\'"]\';\n'
            f'var wrap=window.parent.document.querySelector(sel);'
            f'if(wrap){{var btn=wrap.querySelector("button");if(btn)btn.click();}}}}'
            f'{_step3_hide_js}'
            f'</script>'
            f'</body></html>',
            height=48,
        )

        # ── Handle show/hide toggle ──
        if _trigger_show and _has_questions:
            st.session_state.show_questions_table = not st.session_state.show_questions_table
            st.rerun()

        # ── Handle generation state machine ──
        _run_generation = False

        if st.session_state.confirm_regen_questions:
            st.warning(
                "Are you sure? All current questions will be overwritten and cannot be recovered."
            )
            _confirm_col, _cancel_col = st.columns([1, 4])
            with _confirm_col:
                _do_regen = st.button("Yes, regenerate", type="primary")
            with _cancel_col:
                if st.button("Cancel"):
                    st.session_state.confirm_regen_questions = False
                    st.rerun()
            if _do_regen:
                st.session_state.confirm_regen_questions = False
                _run_generation = True
        elif _trigger_gen:
            if _has_questions:
                st.session_state.confirm_regen_questions = True
                st.rerun()
            else:
                _run_generation = True  # first generation

        if _run_generation:
            from src.question_generator import generate_questions_for_capability

            use_case = st.session_state.use_case_name
            question_call_delay = max(
                0.0,
                float(os.getenv("QUESTION_GEN_CALL_DELAY_SECONDS", "1.5")),
            )
            per_cap_attempts = max(
                1,
                int(os.getenv("QUESTION_GEN_CAPABILITY_ATTEMPTS", "2")),
            )

            caps = []
            caps += [(c, "Core") for c in st.session_state.core_caps]
            if include_upstream:
                caps += [(c, "Upstream") for c in st.session_state.upstream_caps]
            if include_downstream:
                caps += [(c, "Downstream") for c in st.session_state.downstream_caps]

            questions = []
            failed_caps = []
            progress_bar = st.progress(0)
            status = st.empty()
            total_caps = len(caps)

            for i, (cap, role) in enumerate(caps):
                if i > 0 and question_call_delay > 0:
                    time.sleep(question_call_delay)
                cap_name = cap["capability_name"]
                generated = False
                last_err = None
                for attempt in range(1, per_cap_attempts + 1):
                    try:
                        suffix = (
                            f" (attempt {attempt}/{per_cap_attempts})"
                            if per_cap_attempts > 1 else ""
                        )
                        status.caption(f"Generating questions for {cap_name} ({role}){suffix}...")
                        questions.extend(
                            generate_questions_for_capability(
                                use_case=use_case,
                                cap=cap,
                                role=role,
                                questions_per_capability=q_per_cap,
                                style=style,
                            )
                        )
                        generated = True
                        break
                    except Exception as e:
                        last_err = str(e)
                        if attempt < per_cap_attempts:
                            time.sleep(max(1.0, question_call_delay))

                if not generated:
                    failed_caps.append({"capability_name": cap_name, "role": role, "error": last_err or "unknown error"})
                progress_bar.progress((i + 1) / total_caps)

            status.caption(f"Done — {len(questions)} questions generated.")
            st.session_state.questions = [q.__dict__ for q in questions]
            if st.session_state.get("assessment_id"):
                db = get_client()
                save_questions(db, st.session_state.assessment_id, st.session_state.questions)

            success_caps = total_caps - len(failed_caps)
            if failed_caps:
                sample = ", ".join(f"{c['capability_name']} ({c['role']})" for c in failed_caps[:3])
                more = "" if len(failed_caps) <= 3 else f" and {len(failed_caps) - 3} more"
                st.warning(
                    "Some capabilities could not be generated after retries. "
                    f"Succeeded: {success_caps}/{total_caps}. Failed: {len(failed_caps)}. "
                    f"Examples: {sample}{more}."
                )

            if questions:
                st.success(f"Generated {len(questions)} questions across {success_caps}/{total_caps} capabilities.")
            else:
                st.error("Question generation failed for all capabilities. Please try again in a minute.")

        if st.session_state.questions:
            df_q = pd.DataFrame(st.session_state.questions)
            df_q["score"] = ""
            df_q["answer"] = ""
            df_q["notes"] = ""

            if st.session_state.show_questions_table:
                st.dataframe(df_q, use_container_width=True)

            # ── Show assessment ID for workshop reference ──────────────────
            _aid = st.session_state.get("assessment_id")
            if _aid:
                st.info(
                    f"📋 **Assessment ID: {_aid}** — record this reference. "
                    "Open the **Assessments** page and click **Resume** to return "
                    "to Step 4 after your workshop."
                )

        st.divider()

        _nav3 = _render_nav_row(
            {"label": "Back to Step 2",    "key": "s3_back", "style": "outline-secondary"},
            {"label": "Continue to Step 4", "key": "s3_cont", "style": "primary",
             "disabled": not bool(st.session_state.questions)},
        )
        if _nav3["s3_back"]:
            st.session_state.wizard_step = 2
            st.rerun()
        if _nav3["s3_cont"]:
            if not st.session_state.questions:
                st.error("Generate questions first.")
            else:
                if st.session_state.get("assessment_id"):
                    db = get_client()
                    save_questions(db, st.session_state.assessment_id, st.session_state.questions)
                st.session_state.completed_steps.add(3)
                st.session_state.wizard_step = 4
                st.session_state.responses = {}
                st.rerun()

    # -------------------------
    # STEP 4
    # -------------------------
    if st.session_state.wizard_step == 4:
        _render_breadcrumbs()
        st.title("Step 4 — Run & Score Assessment")
        
        if not st.session_state.questions:
            st.warning("No questions found. Go back to Step 3.")
            if st.button("Back to Step 3"):
                st.session_state.wizard_step = 3
                st.rerun()
            st.stop()

        questions = st.session_state.questions
        responses = st.session_state.responses

        st.session_state.responses = responses
        # ── Offline / multi-respondent upload ──
        st.subheader("Upload - Offline / Multi-respondent response sheets")
        st.caption(
            "Upload one or more completed response templates from Step 3. "
            "Each file represents one respondent. When multiple files are uploaded, "
            "responses are synthesised by AI before scoring."
        )

        uploaded_files = st.file_uploader(
            "📂 Upload Completed Response Sheets (CSV or Excel)",
            type=["csv", "xlsx"],
            accept_multiple_files=True,
            help="Upload the Excel template from Step 3, completed by each respondent.",
        )
        # -- Manually input responses--
        st.subheader("Manually Input Responses based on user feedback")
        st.markdown(
            "Expand a capability to see its questions. Answer each question by selecting a score or response."
            "Alternatively, upload a completed CSV from Step 3 using the **Offline option** above. "
            "Once you have answered enough questions, click **Submit Assessment** to save."
        )

        # Progress — manual input only (hidden when respondent sets are uploaded)
        total = len(questions)
        answered = sum(
            1 for r in responses.values()
            if r.get("score") is not None or r.get("answer") is not None
        )
        _has_uploads = bool(st.session_state.get("respondent_sets", []))

        if not _has_uploads:
            col_prog, col_save = st.columns([4, 1])
            with col_prog:
                st.progress(answered / total if total > 0 else 0)
            with col_save:
                _save_label = "No responses yet" if answered == 0 else "💾 Save Progress"
                if st.button(
                    _save_label,
                    disabled=(answered == 0),
                    help="Save responses captured so far — you can resume later from the Assessments page.",
                ):
                    if st.session_state.get("assessment_id"):
                        with st.spinner("Saving…"):
                            save_assessment(get_client(), st.session_state)
                        st.success(f"Saved {answered} response(s).")
            if answered == 0:
                st.caption("No responses yet — expand a capability below to begin.")
            else:
                st.warning(f"{answered} response(s) saved out of {total} expected")

        # Group questions by role → domain → capability
        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for q in questions:
            grouped[q["capability_role"]][q["domain"]][q["capability_name"]].append(q)

        role_order = ["Core", "Upstream", "Downstream"]

        widget_counter = 0
        for role in role_order:
            if role not in grouped:
                continue
            st.subheader(f"{role} Capabilities")

            for domain, caps in sorted(grouped[role].items()):
                st.markdown(f"#### {domain}")

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

        

        def _parse_response_file(file) -> tuple[str, str, dict]:
            """Parse one response file. Returns (respondent_name, respondent_role, responses_dict)."""
            fname = file.name.lower()
            if fname.endswith(".xlsx"):
                df = pd.read_excel(file, header=1)
            else:
                df = pd.read_csv(file)

            required_cols = {"capability_id", "capability_name", "domain",
                             "subdomain", "capability_role", "question",
                             "response_type"}
            if not required_cols.issubset(set(df.columns)):
                raise ValueError(f"Missing required columns. Use the Step 3 response template.")

            # Respondent identity — take first non-empty value in the column (or filename)
            r_name = ""
            r_role = ""
            if "respondent_name" in df.columns:
                vals = df["respondent_name"].dropna().astype(str)
                vals = vals[vals.str.strip() != ""]
                if not vals.empty:
                    r_name = vals.iloc[0].strip()
            if not r_name:
                r_name = file.name.rsplit(".", 1)[0]  # fallback to filename

            if "respondent_role" in df.columns:
                vals = df["respondent_role"].dropna().astype(str)
                vals = vals[vals.str.strip() != ""]
                if not vals.empty:
                    r_role = vals.iloc[0].strip()

            resp_dict = {}
            loaded = skipped = 0
            for _, row in df.iterrows():
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
                    skipped += 1; continue
                if rtype == "yes_no_evidence" and answer is None and score is None:
                    skipped += 1; continue
                if rtype not in ("maturity_1_5", "yes_no_evidence") and not notes_raw and score is None:
                    skipped += 1; continue

                key = f"{row['capability_id']}|{row['capability_role']}|{row['question']}"
                resp_dict[key] = {
                    "capability_id":   row["capability_id"],
                    "capability_name": str(row["capability_name"]),
                    "domain":          str(row["domain"]),
                    "subdomain":       str(row["subdomain"]),
                    "capability_role": str(row["capability_role"]),
                    "question":        str(row["question"]),
                    "response_type":   rtype,
                    "score":           score,
                    "answer":          answer,
                    "notes":           notes_raw,
                }
                loaded += 1
            return r_name, r_role, resp_dict, loaded, skipped

        if uploaded_files:
            new_sets = []
            parse_errors = []
            for f in uploaded_files:
                try:
                    r_name, r_role, resp_dict, loaded, skipped = _parse_response_file(f)
                    new_sets.append({"name": r_name, "role": r_role, "responses": resp_dict})
                    st.success(f"✅ **{r_name}** ({r_role or 'no role'}): {loaded} responses loaded, {skipped} skipped.")
                except Exception as e:
                    parse_errors.append(f"❌ {f.name}: {e}")
            for err in parse_errors:
                st.error(err)

            if new_sets:
                # Merge into existing respondent sets — same name overwrites, new names append
                existing = {rs["name"]: rs for rs in st.session_state.respondent_sets}
                for ns in new_sets:
                    existing[ns["name"]] = ns
                st.session_state.respondent_sets = list(existing.values())
                total_sets = len(st.session_state.respondent_sets)
                st.info(
                    f"**{total_sets} respondent(s) loaded total.** "
                    "Responses will be synthesised by AI when you click Submit Assessment."
                )

        # Show current respondent set summary
        if st.session_state.respondent_sets:
            st.markdown("**Loaded respondent sets:**")
            for rs in st.session_state.respondent_sets:
                n_resp = len(rs.get("responses", {}))
                st.markdown(f"- **{rs['name']}** ({rs.get('role', '—')}) — {n_resp} responses")
            if st.button("🗑️ Clear uploaded respondents", type="secondary"):
                st.session_state.respondent_sets = []
                st.rerun()
        
        st.divider()
        _has_responses = answered > 0 or bool(st.session_state.get("respondent_sets", []))
        _nav4 = _render_nav_row(
            {"label": "Back to Step 3",    "key": "s4_back",   "style": "outline-secondary"},
            {"label": "Submit Assessment", "key": "s4_submit", "style": "primary", "disabled": not _has_responses},
        )
        if _nav4["s4_back"]:
            st.session_state.wizard_step = 3
            st.rerun()
        if _nav4["s4_submit"]:
                _rsets = st.session_state.get("respondent_sets", [])
                _has_online = answered > 0
                _has_uploads = len(_rsets) > 0
                if not _has_online and not _has_uploads:
                    st.error("Please answer at least one question or upload completed response sheets.")
                else:
                    db = get_client()
                    # ── Multi-respondent synthesis ──
                    if len(_rsets) > 1:
                        with st.spinner(f"Synthesising responses from {len(_rsets)} respondents…"):
                            try:
                                from src.ai_client import synthesize_respondent_responses
                                synthesized = synthesize_respondent_responses(
                                    respondent_sets=_rsets,
                                    use_case_name=st.session_state.use_case_name,
                                )
                                st.session_state.responses = synthesized
                                # Persist raw respondent data for audit
                                if st.session_state.get("assessment_id"):
                                    save_respondent_responses(db, st.session_state.assessment_id, _rsets)
                                st.success(f"Synthesised {len(synthesized)} responses from {len(_rsets)} respondents.")
                            except Exception as e:
                                st.error(f"Synthesis failed: {e}. Falling back to first respondent's answers.")
                                st.session_state.responses = _rsets[0]["responses"]
                    with st.spinner("Saving assessment..."):
                        try:
                            assessment_id = save_assessment(db, st.session_state)
                            st.session_state.assessment_id = assessment_id
                        except Exception as e:
                            st.error(f"Save failed: {e}")
                            import traceback
                            st.code(traceback.format_exc())
                            st.session_state.assessment_id = None
                    st.session_state.completed_steps.add(4)
                    st.session_state.wizard_step = 5
                    st.rerun()
                    
    # -------------------------
    # STEP 5
    # -------------------------
    if st.session_state.wizard_step == 5:
        _render_breadcrumbs()
        st.title("Step 5 — Assessment Findings")
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
        st.subheader(f"Overall maturity: **{overall} / 5**")
        st.markdown(f"**Client:** {st.session_state.get('client_name', 'Unknown')}")
        if st.session_state.get("engagement_name"):
            st.markdown(f"**Engagement:** {st.session_state.engagement_name}")
        st.markdown(f"**Industry:** {st.session_state.get('client_industry', '')}  |  **Use case:** {st.session_state.use_case_name}")
        st.markdown(f"**Questions answered:** {len(scored)}")
        st.markdown(f"**Capabilities assessed:** {cap_scores['capability_name'].nunique()}")
        st.markdown(f"**Domains covered:** {dom_scores['domain'].nunique()}")

        st.divider()

        # ── Maturity Heatmap ──
        st.subheader("Maturity Heatmap")
        from src.heatmap import render_heatmap_html, generate_heatmap_excel
        heatmap_html = render_heatmap_html(dom_scores.to_dict(orient="records"))
        n_domains    = len(dom_scores)
        heatmap_h    = max(320, 140 + n_domains * 6)   # rough height estimate
        components.html(heatmap_html, height=heatmap_h, scrolling=True)

        st.divider()

        # ── Domain scores ──
        st.subheader("Domain scores")
        st.dataframe(dom_scores, use_container_width=True)

        st.divider()

        # ── Capability scores by role ──
        st.subheader("Capability scores")
        roles_present = [r for r in ["Core", "Upstream", "Downstream"] if r in cap_scores["capability_role"].values]
        tabs = st.tabs(roles_present)

        for tab, role in zip(tabs, roles_present):
            with tab:
                df_role = cap_scores[cap_scores["capability_role"] == role].sort_values("avg_score")
                st.dataframe(df_role, use_container_width=True)

        st.divider()

        # ── High risk capabilities ──
        high_risk = cap_scores[cap_scores["avg_score"] < 2].sort_values("avg_score")
        if not high_risk.empty:
            st.subheader("🔴 High-risk capabilities")
            st.dataframe(
                high_risk[["capability_name", "domain", "capability_role", "avg_score", "gap"]],
                use_container_width=True,
            )
        else:
            st.success("No capabilities scored below 2.")

        # ── Executive summary ──
        st.divider()
        st.subheader("Executive summary")

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
                _regen_narr = _render_nav_row(
                    {"label": "Regenerate Summary", "key": "s5_regen_narr", "style": "outline-secondary"},
                )
                if _regen_narr["s5_regen_narr"]:
                    st.session_state.confirm_regen_narrative = True
                    st.rerun()
            else:
                st.warning("⚠️ This will replace the saved executive summary. Are you sure?")
                _confirm_narr = _render_nav_row(
                    {"label": "Yes, regenerate", "key": "s5_narr_yes",    "style": "primary"},
                    {"label": "Cancel",          "key": "s5_narr_cancel", "style": "outline-secondary"},
                )
                if _confirm_narr["s5_narr_yes"]:
                    st.session_state.findings_narrative = None
                    st.session_state.confirm_regen_narrative = False
                    st.rerun()
                if _confirm_narr["s5_narr_cancel"]:
                    st.session_state.confirm_regen_narrative = False
                    st.rerun()

        st.divider()

        # ── Exports ──
        st.subheader("Export")
        _uc_slug     = st.session_state.use_case_name.replace(" ", "_")
        _client_slug = st.session_state.get("client_name", "Client").replace(" ", "_")
        _heatmap_bytes = generate_heatmap_excel(
            dom_scores.to_dict(orient="records"),
            client_name=st.session_state.get("client_name", ""),
            engagement_name=st.session_state.get("engagement_name", ""),
            use_case_name=st.session_state.use_case_name,
        )
        _export_btn_row(
            {"label": "Capability Scores (CSV)", "data": cap_scores.to_csv(index=False).encode("utf-8"), "filename": f"{_uc_slug}_capability_scores.csv", "mime": "text/csv"},
            {"label": "Domain Scores (CSV)",     "data": dom_scores.to_csv(index=False).encode("utf-8"), "filename": f"{_uc_slug}_domain_scores.csv",     "mime": "text/csv"},
            {"label": "All Responses (CSV)",     "data": df.to_csv(index=False).encode("utf-8"),         "filename": f"{_uc_slug}_responses.csv",           "mime": "text/csv"},
            {"label": "Heatmap (Excel)",          "data": _heatmap_bytes,                                 "filename": f"Meridant_Insight_{_client_slug}_Heatmap.xlsx", "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        )

        st.divider()

        # ── Navigation ──
        _has_recs = bool(st.session_state.get("recommendations"))
        _nav5 = _render_nav_row(
            {"label": "Start New Assessment",                                    "key": "s5_new",  "style": "outline-secondary"},
            {"label": "View Recommendations →" if _has_recs else "Generate Recommendations →", "key": "s5_recs", "style": "primary"},
            {"label": "Skip to Roadmap →",                                       "key": "s5_skip", "style": "outline-secondary"},
        )
        if _nav5["s5_new"]:
            for k in ["use_case_name", "intent_text", "client_name", "engagement_name",
                      "client_industry", "client_sector", "client_country",
                      "core_caps", "upstream_caps", "downstream_caps", "domains_covered",
                      "questions", "responses", "findings_narrative", "domain_targets",
                      "assessment_id", "findings_saved",
                      "assessment_mode", "selected_usecase_id",
                      "roadmap_data", "responses_ai_scored", "recommendations",
                      "confirm_regen_narrative", "confirm_regen_recs", "confirm_regen_questions",
                      "confirm_rediscover", "show_questions_table"]:
                if k in ["use_case_name", "intent_text", "client_name", "engagement_name",
                         "client_industry", "client_sector", "client_country"]:
                    st.session_state[k] = ""
                elif k == "responses":
                    st.session_state[k] = {}
                elif k in ("findings_narrative", "assessment_id", "roadmap_data", "recommendations"):
                    st.session_state[k] = None
                elif k in ("findings_saved", "responses_ai_scored",
                           "confirm_regen_narrative", "confirm_regen_recs", "confirm_regen_questions",
                           "confirm_rediscover", "show_questions_table"):
                    st.session_state[k] = False
                elif k == "assessment_mode":
                    st.session_state[k] = "predefined"
                elif k in ("selected_usecase_id",):
                    st.session_state[k] = None
                else:
                    st.session_state[k] = []
            st.session_state.completed_steps = set()
            st.session_state.respondent_sets = []
            st.session_state.wizard_step = 1
            st.rerun()
        if _nav5["s5_recs"]:
            st.session_state.completed_steps.add(5)
            st.session_state.wizard_step = "5b"
            st.rerun()
        if _nav5["s5_skip"]:
            st.session_state.completed_steps.add(5)
            st.session_state.wizard_step = 6
            st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6 — Gap Recommendations
    # ─────────────────────────────────────────────────────────────────────────
    if st.session_state.wizard_step == "5b":
        _render_breadcrumbs()
        st.title("Step 6 — Gap Recommendations")
        st.caption(
            "AI-generated per-capability recommendations grounded in MMTF maturity "
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
            st.subheader("Recommendation settings")

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

            run_btn = False
            if not recs:
                _gen_row = _render_nav_row(
                    {"label": "Generate Recommendations", "key": "s5b_gen", "style": "primary", "disabled": (max_caps == 0)},
                )
                if _gen_row["s5b_gen"]:
                    run_btn = True
            elif not st.session_state.get("confirm_regen_recs"):
                _regen_row = _render_nav_row(
                    {"label": "Regenerate", "key": "s5b_regen", "style": "outline-secondary", "disabled": (max_caps == 0)},
                )
                if _regen_row["s5b_regen"]:
                    st.session_state.confirm_regen_recs = True
                    st.rerun()

        # Confirm-before-overwrite dialog (rendered outside the settings container)
        if recs and st.session_state.get("confirm_regen_recs"):
            st.warning("⚠️ This will overwrite the saved recommendations for this assessment. Are you sure?")
            _confirm_recs = _render_nav_row(
                {"label": "Yes, overwrite", "key": "s5b_overwrite_yes",    "style": "primary"},
                {"label": "Cancel",         "key": "s5b_overwrite_cancel", "style": "outline-secondary"},
            )
            if _confirm_recs["s5b_overwrite_yes"]:
                st.session_state.confirm_regen_recs = False
                run_btn = True
            if _confirm_recs["s5b_overwrite_cancel"]:
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
                st.session_state.completed_steps.add("5b")
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
            st.subheader("Export")
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
            _uc_slug = st.session_state.use_case_name.replace(" ", "_")
            _export_btn_row(
                {"label": "Recommendations (CSV)",  "data": _csv_buf.getvalue(),        "filename": f"{_uc_slug}_recommendations.csv",  "mime": "text/csv"},
                {"label": "Recommendations (JSON)", "data": _json.dumps(recs, indent=2), "filename": f"{_uc_slug}_recommendations.json", "mime": "application/json"},
            )

        # ── Navigation ────────────────────────────────────────────────────────
        st.divider()
        _nav5b = _render_nav_row(
            {"label": "← Back to Findings",   "key": "s5b_back", "style": "outline-secondary"},
            {"label": "Continue to Roadmap →", "key": "s5b_cont", "style": "primary"},
        )
        if _nav5b["s5b_back"]:
            st.session_state.wizard_step = 5
            st.rerun()
        if _nav5b["s5b_cont"]:
            st.session_state.completed_steps.add("5b")
            st.session_state.wizard_step = 6
            st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6 — Transformation Roadmap
    # ─────────────────────────────────────────────────────────────────────────
    if st.session_state.wizard_step == 6:
        _render_breadcrumbs()
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
                            if st.session_state.get("assessment_id"):
                                save_roadmap(
                                    get_client(),
                                    st.session_state.assessment_id,
                                    roadmap,
                                    timeline_unit=timeline_unit,
                                    horizon_months=horizon_months,
                                    scope=roadmap_scope,
                                )
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
                _export_btn_row(
                    {"label": "Roadmap (Excel)", "data": excel_bytes, "filename": f"Meridant_Insight_{_client_slug}_Roadmap.xlsx", "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                )

                # ── Progress Tracker ─────────────────────────────────────
                st.divider()
                st.markdown("### Roadmap Progress")

                all_initiatives = []
                for phase in roadmap.get("phases", []):
                    for init in phase.get("initiatives", []):
                        all_initiatives.append({
                            "phase": phase.get("name", ""),
                            "id": init.get("id") or init.get("name", ""),
                            "name": init.get("name", ""),
                            "domain": init.get("domain", ""),
                            "priority": init.get("priority", ""),
                            "capability_names": init.get("capability_names", []),
                        })

                if all_initiatives:
                    progress = dict(st.session_state.get("roadmap_progress", {}))
                    status_options = ["not_started", "in_progress", "complete"]
                    status_labels  = {"not_started": "Not Started", "in_progress": "In Progress", "complete": "Complete"}

                    # Summary counts
                    n_complete    = sum(1 for i in all_initiatives if progress.get(i["id"]) == "complete")
                    n_in_progress = sum(1 for i in all_initiatives if progress.get(i["id"]) == "in_progress")
                    n_total       = len(all_initiatives)
                    pc1, pc2, pc3 = st.columns(3)
                    pc1.metric("Total Initiatives", n_total)
                    pc2.metric("In Progress", n_in_progress)
                    pc3.metric("Complete", n_complete)

                    # Group by phase
                    phases_seen = []
                    for i in all_initiatives:
                        if i["phase"] not in phases_seen:
                            phases_seen.append(i["phase"])

                    updated_progress = dict(progress)
                    for phase_name in phases_seen:
                        phase_inits = [i for i in all_initiatives if i["phase"] == phase_name]
                        with st.expander(f"**{phase_name}** — {len(phase_inits)} initiative(s)", expanded=True):
                            for init in phase_inits:
                                init_id = init["id"]
                                current_status = progress.get(init_id, "not_started")
                                col_name, col_status = st.columns([3, 1])
                                with col_name:
                                    priority_colour = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(init["priority"], "⚪")
                                    st.markdown(f"{priority_colour} **{init['name']}** · *{init['domain']}*")
                                with col_status:
                                    new_status = st.selectbox(
                                        "Status",
                                        options=status_options,
                                        format_func=lambda x: status_labels[x],
                                        index=status_options.index(current_status),
                                        key=f"prog_{init_id}",
                                        label_visibility="collapsed",
                                    )
                                    updated_progress[init_id] = new_status

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("💾 Save Progress", key="save_roadmap_progress_btn"):
                            st.session_state.roadmap_progress = updated_progress
                            if st.session_state.get("assessment_id"):
                                save_roadmap_progress(
                                    get_client(),
                                    st.session_state.assessment_id,
                                    updated_progress,
                                )
                            st.success("Progress saved.")

                    with btn_col2:
                        completed_count = sum(1 for v in updated_progress.values() if v == "complete")
                        in_progress_count = sum(1 for v in updated_progress.values() if v == "in_progress")
                        can_regen = (completed_count + in_progress_count) > 0

                        if st.button(
                            "🔄 Regenerate from Progress",
                            key="regen_roadmap_progress_btn",
                            type="primary",
                            disabled=not can_regen,
                            help="Adjusts capability scores based on completed/in-progress initiatives, then regenerates the roadmap for remaining gaps." if can_regen else "Mark at least one initiative as In Progress or Complete first.",
                        ):
                            # Save progress first
                            st.session_state.roadmap_progress = updated_progress
                            if st.session_state.get("assessment_id"):
                                save_roadmap_progress(get_client(), st.session_state.assessment_id, updated_progress)

                            # Adjust cap scores based on initiative progress
                            import copy
                            adjusted_caps = copy.deepcopy(cap_scores_list)
                            for init in all_initiatives:
                                init_id = init["id"]
                                status  = updated_progress.get(init_id, "not_started")
                                if status == "not_started":
                                    continue
                                factor = 1.0 if status == "complete" else 0.5
                                for cap in adjusted_caps:
                                    if cap["capability_name"] in init["capability_names"]:
                                        gap       = cap["target"] - cap["avg_score"]
                                        cap["avg_score"] = round(
                                            min(cap["target"], cap["avg_score"] + gap * factor), 1
                                        )
                                        cap["gap"] = round(cap["target"] - cap["avg_score"], 1)

                            # Recompute domain scores from adjusted caps
                            dom_adjusted: dict[str, list] = {}
                            for cap in adjusted_caps:
                                dom_adjusted.setdefault(cap["domain"], []).append(cap["avg_score"])
                            adjusted_dom_scores = [
                                {
                                    "domain": d,
                                    "avg_score": round(sum(scores) / len(scores), 1),
                                    "target": domain_targets.get(d, 3),
                                    "gap": round(domain_targets.get(d, 3) - sum(scores) / len(scores), 1),
                                }
                                for d, scores in dom_adjusted.items()
                            ]
                            adjusted_overall = round(
                                sum(c["avg_score"] for c in adjusted_caps) / len(adjusted_caps), 1
                            ) if adjusted_caps else overall

                            with st.spinner("Regenerating roadmap from progress…"):
                                try:
                                    new_roadmap = generate_roadmap_plan(
                                        use_case_name=st.session_state.use_case_name,
                                        intent_text=st.session_state.get("intent_text", ""),
                                        cap_scores=adjusted_caps,
                                        dom_scores=adjusted_dom_scores,
                                        overall_score=adjusted_overall,
                                        horizon_months=horizon_months,
                                        scope=roadmap_scope,
                                        recommendations=st.session_state.get("recommendations"),
                                        client_name=st.session_state.get("client_name", ""),
                                        client_industry=st.session_state.get("client_industry", ""),
                                        client_country=st.session_state.get("client_country", ""),
                                        client_stated_context=_build_client_stated_context(
                                            st.session_state.get("responses", {})
                                        ),
                                    )
                                    st.session_state.roadmap_data = new_roadmap
                                    if st.session_state.get("assessment_id"):
                                        save_roadmap(
                                            get_client(),
                                            st.session_state.assessment_id,
                                            new_roadmap,
                                            timeline_unit=timeline_unit,
                                            horizon_months=horizon_months,
                                            scope=roadmap_scope,
                                        )
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Could not regenerate roadmap: {e}")

            st.divider()

            # ── Navigation ────────────────────────────────────────────────────
            col_back, _ = st.columns([1, 3])
            with col_back:
                if st.button("← Back to Findings"):
                    st.session_state.wizard_step = 5
                    st.rerun()

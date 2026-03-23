import os
import json
import time
import logging
from anthropic import Anthropic, APIStatusError

logger = logging.getLogger(__name__)

_client = None

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
MAX_RETRIES = int(os.getenv("ANTHROPIC_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("ANTHROPIC_RETRY_DELAY", "2.0"))


def get_ai_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment.")
        _client = Anthropic(api_key=api_key)
    return _client


def _call_with_retry(client: Anthropic, **kwargs):
    """Call client.messages.create with exponential backoff on 529 overload."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.messages.create(**kwargs)
        except APIStatusError as e:
            if e.status_code == 529 and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Anthropic overloaded (529). Retry %d/%d in %.1fs",
                    attempt, MAX_RETRIES, delay,
                )
                time.sleep(delay)
            else:
                raise


def rank_capabilities_by_intent(
    intent_text: str,
    use_case_name: str,
    candidates: list[dict],
    top_k: int = 10,
) -> list[dict]:
    """
    Send intent + candidate capabilities to Claude.
    Returns top_k capabilities ranked by relevance, each with an ai_score (0.0–1.0).

    Each candidate dict must have at minimum:
        capability_id, capability_name, domain_name, subdomain_name
    """
    client = get_ai_client()

    # Build a compact capability list for the prompt (avoid huge token counts)
    cap_list = "\n".join(
        f"{c['capability_id']}|{c['capability_name']}|{c['domain_name']}|{c['subdomain_name']}"
        for c in candidates
    )

    prompt = f"""You are an enterprise transformation consultant specialising in capability assessment.

A client has described the following use case and intent:

USE CASE: {use_case_name}
INTENT: {intent_text}

Below is a list of enterprise capabilities in the format:
capability_id|capability_name|domain|subdomain

{cap_list}

Your task:
1. Identify the {top_k} capabilities most directly relevant to achieving this intent.
2. Score each selected capability from 0.0 (not relevant) to 1.0 (highly relevant).
3. Return ONLY a JSON array with no preamble, no markdown, no explanation.

Each item in the array must have exactly these fields:
- capability_id (integer)
- capability_name (string)
- domain_name (string)
- subdomain_name (string)
- ai_score (float, 0.0 to 1.0)
- rationale (string, one sentence explaining why this capability is relevant)

Return exactly {top_k} items, sorted by ai_score descending.
"""

    response = _call_with_retry(
        client,
        model=DEFAULT_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    ranked = json.loads(raw)

    # Enrich with original candidate data (to preserve all fields downstream)
    cap_lookup = {c["capability_id"]: c for c in candidates}
    results = []
    for item in ranked:
        cid = int(item["capability_id"])
        base = cap_lookup.get(cid, {})
        merged = {**base, **item}
        merged["ai_score"] = float(item.get("ai_score", 0.0))
        merged["rationale"] = item.get("rationale", "")
        results.append(merged)

    return results
def generate_findings_narrative(
    use_case_name: str,
    intent_text: str,
    overall_score: float,
    domain_scores: list[dict],
    capability_scores: list[dict],
    high_risk_caps: list[dict],
    top_gaps: list[dict],
    client_name: str = "",
    client_industry: str = "",
    client_country: str = "",
    client_stated_context: str = "",
) -> str:
    """
    Uses Claude to generate a contextual executive findings narrative
    based on actual assessment scores and gaps.
    """
    client = get_ai_client()

    domain_summary = "\n".join(
        f"- {d['domain']}: {d['avg_score']}/5 (target: {d.get('target', 3)}, gap: {d['gap']})"
        for d in sorted(domain_scores, key=lambda x: x["avg_score"])
    )

    high_risk_summary = "\n".join(
        f"- {c['capability_name']} ({c['domain']}, {c['capability_role']}): {c['avg_score']}/5"
        for c in high_risk_caps
    ) if high_risk_caps else "None"

    gap_summary = "\n".join(
        f"- {c['capability_name']} ({c['domain']}): gap of {c['gap']:.1f}"
        for c in top_gaps
    ) if top_gaps else "None"

    cap_count = len(capability_scores)
    domain_count = len(domain_scores)

    client_context = ""
    if client_name or client_industry or client_country:
        parts = []
        if client_name:
            parts.append(f"CLIENT: {client_name}")
        if client_industry:
            parts.append(f"INDUSTRY: {client_industry}")
        if client_country:
            parts.append(f"COUNTRY / MARKET: {client_country}")
        client_context = "\n".join(parts) + "\n"

    prompt = f"""You are a senior enterprise transformation consultant writing an executive assessment findings report.

The following capability assessment has been completed:

{client_context}USE CASE: {use_case_name}
INTENT: {intent_text}
OVERALL MATURITY SCORE: {overall_score}/5
CAPABILITIES ASSESSED: {cap_count}
DOMAINS COVERED: {domain_count}

DOMAIN SCORES (lowest to highest):
{domain_summary}

HIGH RISK CAPABILITIES (score below 2):
{high_risk_summary}

TOP CAPABILITY GAPS (largest gap to target of 3):
{gap_summary}

CLIENT-STATED CONTEXT (verbatim from assessment answers and notes — the ONLY permitted source of specific vendor, tool, or product names):
{client_stated_context or "  None — no free-text answers were provided in this assessment."}

Write a professional executive summary of 3–4 paragraphs that:
1. Opens with an overall assessment of maturity relative to the use case intent, grounded in the client's industry and country context where relevant
2. Highlights the strongest and weakest domains with specific observations relevant to a {client_industry or "enterprise"} organisation operating in {client_country or "their market"}
3. Calls out high-risk capabilities and what this means for the transformation given the client's industry dynamics
4. Closes with 3 prioritised recommendations for immediate action, informed by typical pressures and constraints faced by {client_industry or "enterprise"} organisations in {client_country or "this market"}

Write in a direct, professional consulting tone suitable for a CIO or executive sponsor.
Do not use bullet points — write in flowing paragraphs.
Do not repeat the raw numbers mechanically — interpret what they mean.
Ground observations in the client's specific industry and market context — avoid generic advice.
CRITICAL — technology grounding: Do NOT name specific vendors, cloud providers, platforms, or products (e.g. Azure, AWS, Splunk, ServiceNow, VMware) unless that specific name appears verbatim in the CLIENT-STATED CONTEXT above. When specific tools are not confirmed, use the capability or category description instead. Violating this rule introduces misinformation into a client-facing report.
"""

    response = _call_with_retry(
        client,
        model=DEFAULT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()


def score_free_text_responses(responses: list[dict]) -> list[dict]:
    """
    Uses Claude to assign maturity scores (1–5) to free-text assessment responses.

    Each dict in responses must have at minimum:
        capability_name, domain, question, answer

    Returns the same list with 'score' (int 1–5) and 'rationale' (str) added.
    """
    client = get_ai_client()

    items = "\n\n".join(
        f"[{i}] Capability: {r.get('capability_name', '')} ({r.get('domain', '')})\n"
        f"    Question: {r.get('question', '')}\n"
        f"    Answer: {r.get('answer', '').strip()}"
        for i, r in enumerate(responses)
    )

    prompt = f"""You are an enterprise capability maturity assessor.

Score each response below on a 1–5 maturity scale based solely on what the answer implies about the organisation's current capability:

1 = Ad Hoc       — No formal process; reactive, undocumented, inconsistent
2 = Defined      — Basic process exists but inconsistently applied; limited measurement
3 = Integrated   — Consistent processes, measured, cross-functional alignment
4 = Intelligent  — Data-driven, optimised, proactive, continuous measurement
5 = Adaptive     — Continuously improving; leading practice; industry-leading

Responses to score:
{items}

Return ONLY a JSON array (no markdown, no preamble) with one object per response, in the same order:
[
  {{"index": 0, "score": <integer 1-5>, "rationale": "<one sentence explaining the score>"}},
  ...
]
"""

    response = _call_with_retry(
        client,
        model=DEFAULT_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    results = json.loads(raw)

    # Merge scores back into original response dicts
    score_map = {item["index"]: item for item in results}
    enriched = []
    for i, r in enumerate(responses):
        r = dict(r)
        if i in score_map:
            r["score"] = int(score_map[i].get("score", 1))
            r["rationale"] = score_map[i].get("rationale", "")
        enriched.append(r)
    return enriched


def generate_gap_recommendations(
    capability_name: str,
    domain: str,
    capability_role: str,
    current_score: float,
    target_maturity: int,
    gap: float,
    priority_tier: str,
    current_level_descriptor: str,
    target_level_descriptor: str,
    scored_responses: list[dict],
    foundational_deps: list[str],
    framework_phase: int | None,
    client_industry: str,
    intent_text: str,
    client_country: str = "",
) -> dict:
    """
    Generates a structured gap-closure recommendation for a single capability.

    Returns a dict with keys:
        recommended_actions, enabling_dependencies, success_indicators, narrative
    """
    client = get_ai_client()

    response_block = "\n".join(
        f"  Q: {r.get('question', '')}\n"
        f"  Score: {r.get('score', 'N/A')}/5"
        + (f"\n  Answer: {r.get('answer', '')}" if r.get("answer") else "")
        + (f"\n  Notes: {r.get('notes', '')}" if r.get("notes") else "")
        for r in scored_responses
    ) or "  No responses recorded."

    # Extract verbatim client-stated context from all answer and notes fields.
    # This is the ONLY permitted source of specific vendor/tool/product names.
    stated_texts = [
        t for r in scored_responses
        for t in (r.get("answer", "") or "", r.get("notes", "") or "")
        if t.strip()
    ]
    client_stated_context = (
        "\n".join(f"  - {t.strip()}" for t in stated_texts)
        if stated_texts
        else "  None — the client did not provide free-text answers for this capability."
    )

    dep_block = (
        "  " + "\n  ".join(foundational_deps)
        if foundational_deps
        else "  None identified."
    )

    phase_hint = (
        f"The MMTF framework places this capability in Phase {framework_phase} "
        f"of the transformation journey."
        if framework_phase
        else "No framework phase constraint applies."
    )

    prompt = f"""You are a senior enterprise transformation consultant writing a structured capability gap recommendation.

CAPABILITY: {capability_name}
DOMAIN: {domain}
ROLE IN ASSESSMENT: {capability_role}
CURRENT MATURITY SCORE: {current_score:.1f}/5
TARGET MATURITY LEVEL: L{target_maturity}
GAP: {gap:.1f}
PRIORITY TIER: {priority_tier}  (P1=Phase 1 Foundation, P2=Phase 2 Acceleration, P3=Phase 3 Optimisation)
CLIENT INDUSTRY: {client_industry or "Enterprise"}
CLIENT COUNTRY / MARKET: {client_country or "Not specified"}
TRANSFORMATION INTENT: {intent_text}
{phase_hint}

WHAT THE CLIENT LOOKS LIKE AT THEIR CURRENT LEVEL:
{current_level_descriptor or "No descriptor available."}

WHAT THEY NEED TO ACHIEVE AT L{target_maturity}:
{target_level_descriptor or "No descriptor available."}

ASSESSMENT RESPONSES FOR THIS CAPABILITY:
{response_block}

CLIENT-STATED CONTEXT (verbatim from assessment answers and notes — the ONLY permitted source of specific vendor, tool, or product names):
{client_stated_context}

FOUNDATIONAL CAPABILITIES THAT MUST BE IN PLACE FIRST:
{dep_block}

Based on the above, generate a precise, actionable recommendation grounded entirely in what is known about this client. Do NOT use generic maturity advice, and do NOT infer or invent information that was not stated by the client.

Return ONLY a valid JSON object with no preamble, no markdown, no explanation:
{{
  "recommended_actions": [
    "<specific action 1 — what to do, not what to assess>",
    "<specific action 2>",
    "<specific action 3>"
  ],
  "enabling_dependencies": [
    "<capability or foundation that must exist before this work begins>"
  ],
  "success_indicators": [
    "<measurable outcome 1 — specific, not generic>",
    "<measurable outcome 2>"
  ],
  "narrative": "<2-3 sentence recommendation paragraph written for a CIO or executive sponsor, explaining why this gap matters in the context of the client's industry and market, and what the recommended path forward is>"
}}

Rules:
- recommended_actions: 3–5 concrete actions, ordered from foundational to advanced, informed by the client's industry and country context
- If foundational dependencies exist, the first action must address them
- enabling_dependencies: only list capabilities (from the foundational deps provided) that truly block progress; leave empty array if none
- success_indicators: measurable, time-bound where possible, relevant to the client's industry
- narrative: explicitly reference the client's industry and/or market dynamics where they affect urgency or approach
- Do not repeat the raw scores — interpret what they mean
- CRITICAL — technology grounding: Do NOT name specific vendors, cloud providers, platforms, or products (e.g. Azure, AWS, Splunk, ServiceNow, Kubernetes) unless that specific name appears verbatim in the CLIENT-STATED CONTEXT above. When specific tools are not confirmed, use the capability or category description instead (e.g. "a container registry solution" not "Azure Container Registry", "a SIEM platform" not "Splunk", "a cloud-native CI/CD pipeline" not "GitHub Actions"). Violating this rule introduces misinformation into a client-facing report.
"""

    response = _call_with_retry(
        client,
        model=DEFAULT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def generate_roadmap_plan(
    use_case_name: str,
    intent_text: str,
    cap_scores: list[dict],
    dom_scores: list[dict],
    overall_score: float,
    horizon_months: int = 6,
    scope: str = "Core",
    recommendations: list[dict] | None = None,
    client_name: str = "",
    client_industry: str = "",
    client_country: str = "",
    client_stated_context: str = "",
) -> dict:
    """
    Calls Claude to generate a structured gap-closure roadmap.

    Args:
        use_case_name: Name of the use case being assessed.
        intent_text: The client intent statement.
        cap_scores: List of capability score dicts (capability_name, domain,
                    capability_role, avg_score, target, gap).
        dom_scores: List of domain score dicts (domain, avg_score, target, gap).
        overall_score: Overall maturity score (1–5).
        horizon_months: Transformation horizon in months.
        scope: Which capability roles to include ("Core", "Core + Upstream", "All").
        client_name: Client organisation name for contextualisation.
        client_industry: Client industry for contextualisation.
        client_country: Client country / market for contextualisation.

    Returns:
        Roadmap dict matching the schema expected by src/roadmap.py.
    """
    client = get_ai_client()
    total_weeks = horizon_months * 4

    # Filter cap_scores by scope
    scope_roles: dict[str, list[str]] = {
        "Core":             ["Core"],
        "Core + Upstream":  ["Core", "Upstream"],
        "All":              ["Core", "Upstream", "Downstream"],
    }
    allowed_roles = scope_roles.get(scope, ["Core"])
    filtered_caps = sorted(
        [c for c in cap_scores if c.get("capability_role") in allowed_roles],
        key=lambda x: x.get("gap", 0),
        reverse=True,
    )

    domain_summary = "\n".join(
        f"- {d['domain']}: current={d['avg_score']}/5, target={d.get('target', 3)}, gap={d['gap']:.1f}"
        for d in sorted(dom_scores, key=lambda x: x.get("gap", 0), reverse=True)
    )

    cap_summary = "\n".join(
        f"- [{c.get('capability_role', '')}] {c['capability_name']} ({c['domain']}): "
        f"score={c['avg_score']:.1f}, target={c.get('target', 3)}, gap={c.get('gap', 0):.1f}"
        for c in filtered_caps[:20]
    )

    # Build recommendations block if provided
    if recommendations:
        rec_cap_names = {r["capability_name"] for r in recommendations}
        recs_by_tier: dict[str, list[str]] = {"P1": [], "P2": [], "P3": []}
        for r in recommendations:
            tier = r.get("priority_tier", "P2")
            actions = r.get("recommended_actions", [])
            deps = r.get("enabling_dependencies", [])
            line = (
                f"  [{r['capability_name']} | {r['domain']}] "
                f"Actions: {'; '.join(actions[:3])}"
            )
            if deps:
                line += f" | Requires: {', '.join(deps[:2])}"
            recs_by_tier.get(tier, recs_by_tier["P2"]).append(line)

        rec_block = (
            "\n\nCAPABILITY RECOMMENDATIONS (AUTHORITATIVE — use these to structure phases and initiatives):\n"
            "Phase assignment rules: P1 → Phase 1, P2 → Phase 2, P3 → Phase 3. "
            "Do not move a capability to a later phase than its tier. "
            "You MAY promote a capability to an earlier phase only if a P1 dependency requires it.\n\n"
            "P1 — Phase 1 (Foundation):\n"
            + ("\n".join(recs_by_tier["P1"]) or "  None.") + "\n\n"
            "P2 — Phase 2 (Acceleration):\n"
            + ("\n".join(recs_by_tier["P2"]) or "  None.") + "\n\n"
            "P3 — Phase 3 (Optimisation):\n"
            + ("\n".join(recs_by_tier["P3"]) or "  None.")
        )
        phase_rule = (
            "- Phase 1 contains ALL P1 capabilities; Phase 2 ALL P2; Phase 3 ALL P3\n"
            "- Within each phase, sequence initiatives so dependencies are satisfied first\n"
            "- Use the recommended actions to name and describe each initiative"
        )
    else:
        rec_block = ""
        phase_rule = "- Assign capabilities to phases based on gap size and dependency order"

    roadmap_client_ctx = ""
    if client_name or client_industry or client_country:
        parts = []
        if client_name:
            parts.append(f"CLIENT: {client_name}")
        if client_industry:
            parts.append(f"INDUSTRY: {client_industry}")
        if client_country:
            parts.append(f"COUNTRY / MARKET: {client_country}")
        roadmap_client_ctx = "\n".join(parts) + "\n"

    prompt = f"""You are a senior enterprise transformation consultant.

A capability maturity assessment has been completed:

{roadmap_client_ctx}USE CASE: {use_case_name}
INTENT: {intent_text}
OVERALL MATURITY: {overall_score}/5
HORIZON: {horizon_months} months ({total_weeks} weeks)
SCOPE: {scope} capabilities

DOMAIN SCORES (current/target/gap, sorted by gap descending):
{domain_summary}

TOP CAPABILITY GAPS ({scope} scope, sorted by gap descending):
{cap_summary}{rec_block}

CLIENT-STATED CONTEXT (verbatim from assessment answers and notes — the ONLY permitted source of specific vendor, tool, or product names):
{client_stated_context or "  None — no free-text answers were provided in this assessment."}

Design a prioritised gap-closure roadmap with:
- 3–4 sequential phases that naturally overlap (waterfall planning, agile delivery within each phase)
- Each phase: 3–6 domain-level initiatives (grouped themes, NOT individual tasks)
- Total timeline = {total_weeks} weeks
- Phases should overlap by 2–4 weeks to enable smooth transitions
- Initiative names, narratives, and sequencing should reflect the realities of a {client_industry or "enterprise"} organisation operating in {client_country or "their market"} — reference relevant industry drivers, regulatory context, or market pressures where they affect priority or timing
{phase_rule}

Return ONLY a valid JSON object with this exact structure (no markdown, no preamble, no explanation):
{{
  "total_weeks": {total_weeks},
  "phases": [
    {{
      "id": "P1",
      "name": "<descriptive phase name>",
      "start_week": 1,
      "end_week": <integer>,
      "rationale": "<1-2 sentence rationale for this phase>",
      "story": "As a <team/role>, we need to <achieve X> so that <outcome>.",
      "description": "<2-3 sentence context paragraph describing the phase focus and approach>",
      "activities": ["<key activity 1>", "<key activity 2>", "<key activity 3>"],
      "initiatives": [
        {{
          "id": "I1",
          "name": "<initiative name>",
          "domain": "<domain name exactly as given in the input>",
          "capability_names": ["<capability name>"],
          "priority": "<Critical|High|Medium|Low>",
          "current_score": <float>,
          "target_score": <float>,
          "gap": <float>,
          "start_week": <integer>,
          "end_week": <integer>,
          "prerequisites": [],
          "outcome": "<one-line measurable outcome>"
        }}
      ]
    }}
  ],
  "critical_path": ["<initiative name>", "<initiative name>"],
  "quick_wins": ["<quick win description (< 2-week task)>"]
}}

Priority rules:
- Critical: gap > 2.0
- High: gap 1.5–2.0
- Medium: gap 1.0–1.5
- Low: gap < 1.0

Constraints:
- All week numbers must be between 1 and {total_weeks}
- Use domain names EXACTLY as given in the input data
- Quick wins: 2–5 concrete actions completable in under 2 weeks with immediate visible impact
- Critical path: 3–5 initiative names that represent the key sequential dependencies
- CRITICAL — technology grounding: Do NOT name specific vendors, cloud providers, platforms, or products (e.g. Azure, AWS, Splunk, ServiceNow, VMware) in initiative names, descriptions, activities, outcomes, or quick wins unless that specific name appears verbatim in the CLIENT-STATED CONTEXT above. Use capability or category descriptions instead (e.g. "cloud management platform" not "Azure Arc", "ITSM tooling" not "ServiceNow"). Violating this rule introduces misinformation into a client-facing deliverable.
"""

    response = _call_with_retry(
        client,
        model=DEFAULT_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def synthesize_respondent_responses(
    respondent_sets: list[dict],
    use_case_name: str,
) -> dict:
    """
    Synthesize multiple respondent response sets into a single normalized response dict.

    Each respondent_set: {"name": str, "role": str, "responses": {key: response_dict}}

    Returns a responses dict in the same format as st.session_state.responses,
    with synthesized score/answer/notes per question.
    If only one set is provided, returns it directly without an AI call.
    """
    from collections import defaultdict

    if not respondent_sets:
        return {}
    if len(respondent_sets) == 1:
        return respondent_sets[0]["responses"]

    client = get_ai_client()

    # ── Build question map and multi-respondent answer map ──
    question_map: dict = {}
    multi_answers: dict = defaultdict(list)

    for rs in respondent_sets:
        r_label = rs.get("name", "Unknown")
        r_role  = rs.get("role", "")
        label   = f"{r_label} ({r_role})" if r_role else r_label
        for r in rs.get("responses", {}).values():
            q_key = f"{r['capability_id']}|{r['question']}"
            if q_key not in question_map:
                question_map[q_key] = r.copy()
            multi_answers[q_key].append({
                "respondent": label,
                "score":      r.get("score"),
                "answer":     r.get("answer"),
                "notes":      r.get("notes", ""),
            })

    # ── Group questions by capability for batched API calls ──
    cap_questions: dict = defaultdict(list)
    for q_key in question_map:
        cap_id_str = q_key.split("|", 1)[0]
        cap_questions[cap_id_str].append(q_key)

    synthesized: dict = {}
    batch_size  = 10
    cap_ids     = list(cap_questions.keys())

    for batch_start in range(0, len(cap_ids), batch_size):
        batch_caps = cap_ids[batch_start:batch_start + batch_size]

        lines = []
        for cap_id_str in batch_caps:
            q_keys = cap_questions[cap_id_str]
            base   = question_map[q_keys[0]]
            lines.append(f"\nCAPABILITY: {base['capability_name']} | {base['domain']}")
            for q_key in q_keys:
                r = question_map[q_key]
                lines.append(f"  Q (cap_id={r['capability_id']}, type={r['response_type']}): {r['question']}")
                for ans in multi_answers[q_key]:
                    score_part  = f"score={ans['score']}" if ans["score"] is not None else ""
                    answer_part = f"answer={ans['answer']}" if ans["answer"] else ""
                    notes_part  = f"notes: {ans['notes']}" if ans["notes"] else ""
                    detail = " | ".join(p for p in [score_part, answer_part, notes_part] if p)
                    lines.append(f"    • {ans['respondent']}: {detail if detail else '(no response)'}")

        prompt = f"""You are synthesising multi-stakeholder capability maturity assessment responses.

Use case: {use_case_name}

For each question you will see responses from {len(respondent_sets)} stakeholders.
Synthesise each into a single score (1–5) that best represents the collective evidence.
Apply a conservative bias: if scores diverge significantly, lean toward the lower score
unless strong evidence in the notes justifies a higher one.

{chr(10).join(lines)}

Return ONLY a JSON array with no preamble, no markdown, no explanation:
[
  {{
    "capability_id": <int>,
    "question": "<exact question text>",
    "synthesized_score": <int 1-5>,
    "synthesized_answer": "<Yes|No|Partial|null>",
    "synthesis_rationale": "<1-2 sentences explaining basis and any divergence>"
  }},
  ...
]"""

        resp = _call_with_retry(
            client,
            model=DEFAULT_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            batch_results = json.loads(raw)
        except json.JSONDecodeError:
            batch_results = []

        result_lookup: dict = {}
        for item in batch_results:
            lk = f"{item['capability_id']}|{item['question']}"
            result_lookup[lk] = item

        cap_counter: dict = {}
        for cap_id_str in batch_caps:
            for q_key in cap_questions[cap_id_str]:
                base = question_map[q_key].copy()
                if q_key in result_lookup:
                    item = result_lookup[q_key]
                    base["score"] = item.get("synthesized_score")
                    ans = item.get("synthesized_answer", "") or ""
                    base["answer"] = ans if ans.lower() not in ("", "null") else None
                    base["notes"]  = item.get("synthesis_rationale", "")
                else:
                    scores = [a["score"] for a in multi_answers[q_key] if a["score"] is not None]
                    base["score"]  = round(sum(scores) / len(scores)) if scores else None
                    base["answer"] = None
                    base["notes"]  = "(synthesis fallback — averaged scores)"

                base.pop("respondent_name", None)
                base.pop("respondent_role", None)

                cap_id_int = base["capability_id"]
                c = cap_counter.get(cap_id_int, 0)
                cap_counter[cap_id_int] = c + 1
                synthesized[f"{cap_id_int}|{base['question']}|{c}"] = base

    return synthesized
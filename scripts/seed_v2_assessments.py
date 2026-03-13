# -*- coding: utf-8 -*-
"""Seed 6 comprehensive test assessments into the E2CAF database.

Assessments:
  1. Viennalife Insurance AG     / Enterprise Baseline Assessment  (maturity_1_5)
  2. Dubai Police HQ             / Zero Trust                       (yes_no_evidence)
  3. TechNova Systems Inc        / AI Readiness & Maturity          (free_text)
  4. Santos Energy Group         / Innovation at Scale              (MIXED)
  5. Quantex Capital Partners    / Edge & Cloud Modernization       (yes_no_evidence)
  6. Axiom Logistics APAC        / Digital Supply Chain             (free_text)

Run inside Docker:
    docker compose exec web python scripts/seed_v2_assessments.py

Or directly (local DB):
    python scripts/seed_v2_assessments.py
"""
from __future__ import annotations

import io
import os
import sys
import sqlite3
import json
import random
from datetime import datetime, timedelta
from collections import defaultdict

# Force UTF-8 stdout on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Path + env setup ──────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import dotenv_values as _dv
for _k, _v in _dv(os.path.join(ROOT, ".env")).items():
    if _v is not None:
        os.environ[_k] = _v

# ── DB path ───────────────────────────────────────────────────────────────────
FRAMEWORKS_PATH = (
    os.environ.get("MERIDANT_FRAMEWORKS_DB_PATH")
    or os.environ.get("TMM_DB_PATH", "/data/meridant_frameworks.db")
)
ASSESSMENTS_PATH = (
    os.environ.get("MERIDANT_ASSESSMENTS_DB_PATH")
    or os.environ.get("TMM_DB_PATH", "/data/meridant.db")
)
local_fw = os.path.join(ROOT, "data", "meridant_frameworks.db")
local_as = os.path.join(ROOT, "data", "meridant.db")
if not os.path.exists(FRAMEWORKS_PATH) and os.path.exists(local_fw):
    FRAMEWORKS_PATH = local_fw
if not os.path.exists(ASSESSMENTS_PATH) and os.path.exists(local_as):
    ASSESSMENTS_PATH = local_as

print(f"Using frameworks DB : {FRAMEWORKS_PATH}")
print(f"Using assessments DB: {ASSESSMENTS_PATH}")

con = sqlite3.connect(FRAMEWORKS_PATH)
con.execute(f'ATTACH DATABASE "{ASSESSMENTS_PATH}" AS assessments')
con.row_factory = sqlite3.Row

# ── DB helpers ────────────────────────────────────────────────────────────────

def run(sql, params=None):
    cur = con.cursor()
    cur.execute(sql, params or [])
    con.commit()
    return cur.lastrowid


def run_many(sql, rows):
    cur = con.cursor()
    cur.executemany(sql, rows)
    con.commit()


# ── Score helpers ─────────────────────────────────────────────────────────────

def score_for(mean: float, spread: float, rng: random.Random) -> int:
    return max(1, min(5, round(mean + rng.gauss(0, spread))))


def yn_for(yes_p: float, partial_p: float, rng: random.Random) -> str:
    r = rng.random()
    if r < yes_p:
        return "Yes"
    if r < yes_p + partial_p:
        return "Partial"
    return "No"


YN_MAP = {"Yes": 3, "Partial": 2, "No": 1}


def risk_label(score) -> str:
    if score is None:
        return ""
    if score < 2:
        return "High"
    if score < 3:
        return "Medium"
    return "Low"


# ── Findings computation ──────────────────────────────────────────────────────

def compute_findings(responses, domain_targets):
    cap_acc: dict = defaultdict(list)
    for r in responses:
        if r["response_type"] == "maturity_1_5":
            s = r.get("score")
        elif r["response_type"] == "yes_no_evidence":
            s = YN_MAP.get(r.get("answer"))
        else:
            s = r.get("score")
        if s is not None:
            key = (
                r["capability_role"], r["domain"], r["subdomain"],
                r["capability_name"], r["capability_id"],
            )
            cap_acc[key].append(s)

    cap_scores, dom_acc = [], defaultdict(list)
    for (role, dom, sub, name, cap_id), scores in cap_acc.items():
        avg = round(sum(scores) / len(scores), 1)
        tgt = domain_targets.get(dom, 3)
        cap_scores.append({
            "capability_id": cap_id, "capability_name": name,
            "domain": dom, "subdomain": sub, "capability_role": role,
            "avg_score": avg, "target": tgt, "gap": round(tgt - avg, 1),
        })
        dom_acc[dom].extend(scores)

    dom_scores = []
    for dom, scores in dom_acc.items():
        avg = round(sum(scores) / len(scores), 1)
        tgt = domain_targets.get(dom, 3)
        dom_scores.append({
            "domain": dom, "avg_score": avg,
            "target": tgt, "gap": round(tgt - avg, 1),
        })

    all_avgs = [c["avg_score"] for c in cap_scores]
    overall = round(sum(all_avgs) / len(all_avgs), 1) if all_avgs else 0.0
    return cap_scores, dom_scores, overall


# ── Priority / effort helpers ─────────────────────────────────────────────────

def priority_tier(gap: float, role: str) -> str:
    if gap >= 2.0 or (role == "Core" and gap >= 1.5):
        return "P1"
    if gap >= 1.0:
        return "P2"
    return "P3"


def effort_estimate(gap: float) -> str:
    if gap >= 2.0:
        return "High Effort"
    if gap >= 1.0:
        return "Medium"
    return "Quick Win"


# ── Free-text answer builder ──────────────────────────────────────────────────

def free_text_answer(cap_name: str, score: int, industry: str) -> str:
    """Return a realistic free-text answer tailored to score and industry."""
    cap = cap_name

    # Industry-specific context tags
    ctx = {
        "Insurance":              "insurance regulatory obligations and Solvency II compliance requirements",
        "Government":             "public sector mandate and national security obligations",
        "Technology":             "enterprise software delivery and product engineering practices",
        "Energy & Resources":     "operational continuity and critical infrastructure resilience requirements",
        "Financial Services":     "financial regulation requirements and risk management frameworks",
        "Logistics & Transportation": "supply chain resilience and cross-border logistics operations",
    }.get(industry, "organisational strategic priorities")

    if score <= 2:
        return (
            f"We currently have no formalised approach to {cap}. "
            f"Individual teams handle this in an ad hoc manner with no centralised oversight or governance. "
            f"Given our {ctx}, this has been flagged as a priority gap in recent internal audits. "
            f"We have not yet allocated dedicated budget or resource for a structured improvement programme."
        )
    elif score == 3:
        return (
            f"We have a defined process for {cap} that is followed by most teams. "
            f"Governance is in place but we see inconsistency in application at team level, "
            f"particularly across business units with different {ctx}. "
            f"We track some metrics but reporting is manual and not fully automated. "
            f"We are actively working to improve tooling coverage and formalise standards across the organisation."
        )
    else:
        return (
            f"Our {cap} practice is well-established with automated pipelines, continuous monitoring, "
            f"and regular improvement reviews embedded in our operating model. "
            f"We have a dedicated team, clear ownership, and measurable outcomes tracked against targets aligned to {ctx}. "
            f"We benchmark against industry peers and are considered a leading practice, "
            f"with quarterly capability reviews and board-level visibility of performance."
        )


# ── Insert a complete assessment ──────────────────────────────────────────────

def insert_assessment(
    client_name, industry, sector, country,
    engagement_name, use_case_name, usecase_id, intent_text, assessment_mode,
    caps_by_role, responses, domain_targets, findings_narrative,
    recommendations_data, created_days_ago=0,
):
    now = datetime.now()
    created_at   = (now - timedelta(days=created_days_ago)).isoformat()
    completed_at = (now - timedelta(days=max(0, created_days_ago - 1))).isoformat()

    # ── Idempotency check ─────────────────────────────────────────────────────
    cur = con.cursor()
    cur.execute(
        "SELECT a.id FROM Assessment a"
        " JOIN Client c ON c.id = a.client_id"
        " WHERE c.client_name = ? AND a.use_case_name = ? LIMIT 1",
        [client_name, use_case_name],
    )
    existing = cur.fetchone()
    if existing:
        print(f"  Skipping (already exists): {client_name} / {use_case_name}")
        return None

    # ── Client ────────────────────────────────────────────────────────────────
    cur.execute("SELECT id FROM Client WHERE client_name=? LIMIT 1", [client_name])
    row = cur.fetchone()
    if row:
        client_id = row["id"]
    else:
        client_id = run(
            "INSERT INTO Client (client_name, industry, sector, country, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            [client_name, industry, sector, country, created_at],
        )

    # ── Assessment header ─────────────────────────────────────────────────────
    assessment_id = run(
        "INSERT INTO Assessment"
        " (client_id, engagement_name, use_case_name, intent_text,"
        "  usecase_id, assessment_mode, findings_narrative, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)",
        [client_id, engagement_name, use_case_name, intent_text,
         usecase_id, assessment_mode, findings_narrative, created_at],
    )

    # ── AssessmentCapability rows ─────────────────────────────────────────────
    cap_rows = []
    for role, caps in caps_by_role.items():
        for c in caps:
            cap_rows.append((
                assessment_id, c["capability_id"],
                c["capability_name"], c["domain"], c["subdomain"],
                role, None, "",
                domain_targets.get(c["domain"], 3),
            ))
    run_many(
        "INSERT INTO AssessmentCapability"
        " (assessment_id, capability_id, capability_name, domain_name,"
        "  subdomain_name, capability_role, ai_score, rationale, target_maturity)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        cap_rows,
    )

    # ── AssessmentResponse rows ───────────────────────────────────────────────
    run_many(
        "INSERT INTO AssessmentResponse"
        " (assessment_id, capability_id, capability_name, domain, subdomain,"
        "  capability_role, question, response_type, score, answer, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(
            assessment_id,
            int(r["capability_id"]), r["capability_name"],
            r["domain"], r["subdomain"], r["capability_role"],
            r["question"], r["response_type"],
            r.get("score"), r.get("answer"), r.get("notes", ""),
        ) for r in responses],
    )

    # ── Findings ──────────────────────────────────────────────────────────────
    cap_scores, dom_scores, overall = compute_findings(responses, domain_targets)

    run(
        "UPDATE Assessment SET overall_score=?, status='complete', completed_at=?,"
        " findings_narrative=? WHERE id=?",
        [overall, completed_at, findings_narrative, assessment_id],
    )

    finding_rows = []
    for d in dom_scores:
        finding_rows.append((
            assessment_id, "domain", d["domain"], None, None, None, None,
            d["avg_score"], int(d["target"]), d["gap"], risk_label(d["avg_score"]),
        ))
    for c in cap_scores:
        finding_rows.append((
            assessment_id, "capability", c["domain"],
            c["capability_id"], c["capability_name"], c["capability_role"], c["subdomain"],
            c["avg_score"], int(c["target"]), c["gap"], risk_label(c["avg_score"]),
        ))
    run_many(
        "INSERT INTO AssessmentFinding"
        " (assessment_id, finding_type, domain, capability_id, capability_name,"
        "  capability_role, subdomain, avg_score, target_maturity, gap, risk_level)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        finding_rows,
    )

    # ── AssessmentRecommendation rows ─────────────────────────────────────────
    # Build a map from capability_id -> cap_score for lookup
    cap_score_map = {c["capability_id"]: c for c in cap_scores}

    now_iso = datetime.now().isoformat()
    rec_rows = []
    for rec in recommendations_data:
        cap_id = rec["capability_id"]
        cs = cap_score_map.get(cap_id, {})
        current = cs.get("avg_score", rec.get("current_score", 1.0))
        target  = cs.get("target", rec.get("target_score", 3))
        gap_val = round(target - current, 1)
        tier    = priority_tier(gap_val, cs.get("capability_role", "Core"))
        effort  = effort_estimate(gap_val)
        rec_rows.append((
            assessment_id,
            cap_id,
            rec["capability_name"],
            rec["domain"],
            rec["capability_role"],
            current,
            int(target),
            gap_val,
            tier,
            effort,
            json.dumps(rec["recommended_actions"]),
            json.dumps(rec["enabling_dependencies"]),
            json.dumps(rec["success_indicators"]),
            None,   # hpe_relevance
            rec.get("narrative", ""),
            now_iso,
        ))

    run_many(
        "INSERT INTO AssessmentRecommendation"
        " (assessment_id, capability_id, capability_name, domain,"
        "  capability_role, current_score, target_maturity, gap,"
        "  priority_tier, effort_estimate,"
        "  recommended_actions, enabling_dependencies, success_indicators,"
        "  hpe_relevance, narrative, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rec_rows,
    )

    print(
        f"  -> Assessment #{assessment_id}: {client_name} / {use_case_name}"
        f"  overall={overall}  domains={len(dom_scores)}  caps={len(cap_scores)}"
        f"  recs={len(rec_rows)}"
    )
    return assessment_id


# =============================================================================
# Capability definitions
# =============================================================================

# Each tuple: (id, name, domain, subdomain)
CAP_315 = (315, "AI Regulatory Compliance & Risk Management",   "AI & Cognitive Systems", "Responsible & Ethical AI")
CAP_305 = (305, "Supply Chain Security",                        "Security",               "Governance, Risk, and Compliance")
CAP_308 = (308, "Technical Debt Management",                    "Applications",           "Strategy")
CAP_317 = (317, "AI Agent & Orchestration Framework",           "AI & Cognitive Systems", "AI Integration & Orchestration")
CAP_313 = (313, "AI Bias Detection & Fairness Testing",         "AI & Cognitive Systems", "Responsible & Ethical AI")
CAP_319 = (319, "AI Compute & Accelerator Management",          "AI & Cognitive Systems", "AI Infrastructure & Compute")
CAP_314 = (314, "AI Explainability & Interpretability",         "AI & Cognitive Systems", "Responsible & Ethical AI")
CAP_307 = (307, "AI Security & Model Integrity",                "Security",               "Governance, Risk, and Compliance")
CAP_318 = (318, "Cognitive Search & Knowledge Retrieval",       "AI & Cognitive Systems", "AI Integration & Orchestration")
CAP_310 = (310, "Digital Twin & Simulation",                    "Innovation",             "Innovation Enablement Value Chain")
CAP_311 = (311, "Feature Store & Data Preparation",             "AI & Cognitive Systems", "AI Lifecycle Management")
CAP_309 = (309, "Generative AI & LLM Operations",               "AI & Cognitive Systems", "AI Lifecycle Management")
CAP_312 = (312, "Model Evaluation & Benchmarking",              "AI & Cognitive Systems", "AI Lifecycle Management")
CAP_316 = (316, "Predictive Analytics & Forecasting",           "AI & Cognitive Systems", "Decision Intelligence")
CAP_306 = (306, "Zero Trust Network Access (ZTNA) Architecture","Security",               "Infrastructure & Platform Security")


def _cap_dict(t, role):
    return {
        "capability_id":   t[0],
        "capability_name": t[1],
        "domain":          t[2],
        "subdomain":       t[3],
        "capability_role": role,
    }


# ── Question template builders ────────────────────────────────────────────────

def ai_questions(cap_name):
    return [
        f"Describe your current approach to {cap_name} — what processes, tools, and governance are in place?",
        f"What are the primary barriers preventing improvement in {cap_name}?",
        f"How do you measure success and monitor performance for {cap_name}?",
    ]


def security_questions(cap_name):
    return [
        f"How is {cap_name} currently implemented and enforced across the organisation?",
        f"What controls and monitoring processes are in place for {cap_name}?",
        f"How mature is your incident response and continuous improvement process for {cap_name}?",
    ]


def app_innovation_questions(cap_name):
    return [
        f"How is {cap_name} governed and managed within your application portfolio?",
        f"What tooling and automation supports your {cap_name} practice?",
        f"How does {cap_name} integrate with your broader delivery and operations model?",
    ]


def yn_questions(cap_name):
    return [
        f"Is a formal {cap_name} policy in place and enforced?",
        f"Are controls for {cap_name} regularly reviewed and tested?",
        f"Is performance against {cap_name} objectives measured and reported?",
    ]


def get_questions(cap_name, domain, q_style):
    """Return 3 question strings appropriate for the domain and question style."""
    if q_style == "yes_no_evidence":
        return yn_questions(cap_name)
    if domain == "Security":
        return security_questions(cap_name)
    if domain in ("Applications", "Innovation"):
        return app_innovation_questions(cap_name)
    # AI & Cognitive, Data, DevOps, etc.
    return ai_questions(cap_name)


# ── YN notes helpers ──────────────────────────────────────────────────────────

def yn_notes(answer, context=""):
    base = {
        "Yes":     "Policy documented and in active use. Evidence reviewed and confirmed compliant.",
        "Partial": "Framework exists but implementation is inconsistent. Not all teams comply.",
        "No":      "Not currently in place. Gap identified and on the improvement backlog.",
    }[answer]
    if context:
        base = base + f" {context}"
    return base


# ── Response builders ─────────────────────────────────────────────────────────

def build_maturity_responses(caps, domain_targets, mean, spread, rng, industry=""):
    responses = []
    for cap in caps:
        cid, cname, dom, sub, role = (
            cap["capability_id"], cap["capability_name"],
            cap["domain"], cap["subdomain"], cap["capability_role"],
        )
        questions = get_questions(cname, dom, "maturity_1_5")
        tgt = domain_targets.get(dom, 3)
        # Bias toward gap: score ~ mean
        for q in questions:
            s = score_for(mean, spread, rng)
            responses.append({
                "capability_id":   cid, "capability_name": cname,
                "domain": dom, "subdomain": sub, "capability_role": role,
                "question": q, "response_type": "maturity_1_5",
                "score": s, "answer": None, "notes": "",
            })
    return responses


def build_yn_responses(caps, yes_p, partial_p, rng, context_fn=None):
    responses = []
    for cap in caps:
        cid, cname, dom, sub, role = (
            cap["capability_id"], cap["capability_name"],
            cap["domain"], cap["subdomain"], cap["capability_role"],
        )
        questions = get_questions(cname, dom, "yes_no_evidence")
        for q in questions:
            answ = yn_for(yes_p, partial_p, rng)
            ctx = context_fn(answ, cname) if context_fn else ""
            responses.append({
                "capability_id":   cid, "capability_name": cname,
                "domain": dom, "subdomain": sub, "capability_role": role,
                "question": q, "response_type": "yes_no_evidence",
                "score": None, "answer": answ, "notes": yn_notes(answ, ctx),
            })
    return responses


def build_free_text_responses(caps, domain_targets, mean, spread, rng, industry=""):
    responses = []
    for cap in caps:
        cid, cname, dom, sub, role = (
            cap["capability_id"], cap["capability_name"],
            cap["domain"], cap["subdomain"], cap["capability_role"],
        )
        questions = get_questions(cname, dom, "free_text")
        for q in questions:
            s = score_for(mean, spread, rng)
            answer = free_text_answer(cname, s, industry)
            responses.append({
                "capability_id":   cid, "capability_name": cname,
                "domain": dom, "subdomain": sub, "capability_role": role,
                "question": q, "response_type": "free_text",
                "score": s, "answer": answer, "notes": "",
            })
    return responses


# =============================================================================
# Assessment 1 — Viennalife Insurance AG
# =============================================================================

def assessment_viennalife(rng):
    client_name     = "Viennalife Insurance AG"
    industry        = "Insurance"
    sector          = "Life Insurance"
    country         = "Austria"
    engagement_name = "AI & Digital Transformation Readiness -- FY26"
    use_case_name   = "Enterprise Baseline Assessment"
    usecase_id      = 35
    assessment_mode = "predefined"
    created_days_ago = 25

    intent_text = (
        "Viennalife Insurance AG is undertaking an enterprise baseline assessment to establish "
        "a current-state maturity profile across all E2CAF domains. The primary focus is on "
        "AI governance, regulatory compliance, and security posture given the evolving EU AI Act "
        "obligations and Solvency II capital risk requirements. This assessment will inform the "
        "FY26 transformation roadmap, prioritising investments in responsible AI, supply chain "
        "security, and technical debt remediation across legacy actuarial platforms."
    )

    domain_targets = {
        "AI & Cognitive Systems": 3,
        "Security":               3,
        "Applications":           3,
        "Innovation":             3,
    }

    mean   = 1.9
    spread = 0.6

    core_caps = [
        _cap_dict(CAP_315, "Core"),
        _cap_dict(CAP_305, "Core"),
        _cap_dict(CAP_308, "Core"),
    ]
    upstream_caps = [
        _cap_dict(CAP_317, "Upstream"),
        _cap_dict(CAP_313, "Upstream"),
        _cap_dict(CAP_319, "Upstream"),
        _cap_dict(CAP_314, "Upstream"),
        _cap_dict(CAP_307, "Upstream"),
        _cap_dict(CAP_318, "Upstream"),
        _cap_dict(CAP_310, "Upstream"),
        _cap_dict(CAP_311, "Upstream"),
        _cap_dict(CAP_309, "Upstream"),
        _cap_dict(CAP_312, "Upstream"),
        _cap_dict(CAP_316, "Upstream"),
        _cap_dict(CAP_306, "Upstream"),
    ]

    all_caps = core_caps + upstream_caps
    responses = build_maturity_responses(all_caps, domain_targets, mean, spread, rng, industry)

    findings_narrative = (
        "Viennalife Insurance AG presents a maturity profile that is largely Ad Hoc to Defined "
        "across the assessed capability domains, with an average score of approximately 1.9 out of 5. "
        "The organisation faces material gaps in AI governance and regulatory compliance, areas of "
        "increasing strategic urgency as the EU AI Act obligations come into force for insurance "
        "underwriting and claims automation systems. Security capabilities, particularly supply chain "
        "security and AI model integrity, reflect early-stage practices that require structured "
        "investment to meet the organisation's risk appetite.\n\n"
        "The Applications domain reveals significant technical debt accumulated across legacy actuarial "
        "platforms, with no formalised technical debt management programme in place. This constrains "
        "the organisation's ability to adopt modern AI and cloud capabilities, as modernisation efforts "
        "are repeatedly blocked by integration dependencies on aging core systems. Innovation capabilities "
        "are nascent, with digital twin and simulation capabilities unexplored despite clear applicability "
        "to risk modelling and scenario planning for life insurance products.\n\n"
        "The recommended transformation trajectory prioritises a Responsible AI framework as the "
        "foundational P1 initiative, establishing governance structures that will underpin all subsequent "
        "AI investments. Supply chain security hardening and a structured technical debt programme "
        "should proceed in parallel as P1 activities. The maturity targets of L3 across AI, Security, "
        "and Applications domains are achievable within an 18-month horizon given appropriate resourcing "
        "and executive sponsorship, and will position Viennalife to meet regulatory obligations while "
        "building competitive AI-driven underwriting capabilities."
    )

    caps_by_role = {"Core": core_caps, "Upstream": upstream_caps}

    # Top 4 gap capabilities by estimated score
    recommendations_data = [
        {
            "capability_id":   315,
            "capability_name": "AI Regulatory Compliance & Risk Management",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   1.0,
            "target_score":    3,
            "narrative": (
                "Viennalife has no formalised AI regulatory compliance programme. "
                "With EU AI Act obligations imminent for insurance use cases, establishing "
                "a structured risk management framework for AI systems is the highest-priority "
                "capability gap in this assessment."
            ),
            "recommended_actions": [
                "Establish an AI Risk & Compliance function with clear ownership and board reporting line",
                "Inventory all AI systems in production and classify against EU AI Act risk tiers",
                "Develop and publish an AI Use Policy covering underwriting, claims, and pricing models",
                "Implement a conformity assessment process for high-risk AI systems prior to deployment",
                "Integrate AI compliance checkpoints into the existing model governance lifecycle",
            ],
            "enabling_dependencies": [
                "AI Security & Model Integrity capability must be at L2 to support audit trail requirements",
                "AI Bias Detection & Fairness Testing required for EU AI Act conformity assessment",
                "Legal and Compliance function engagement to interpret regulatory obligations",
            ],
            "success_indicators": [
                "100% of production AI systems inventoried and risk-classified within 90 days",
                "AI Use Policy published and communicated to all business units",
                "Conformity assessment completed for all high-risk AI systems before go-live",
                "Zero regulatory enforcement actions related to AI compliance in the next 24 months",
            ],
        },
        {
            "capability_id":   305,
            "capability_name": "Supply Chain Security",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   1.0,
            "target_score":    3,
            "narrative": (
                "Supply chain security is in an ad hoc state with no structured third-party "
                "risk assessment programme. Given Viennalife's reliance on external actuarial "
                "data providers and reinsurance data feeds, this represents a significant "
                "operational risk under the DORA regulation applicable to insurance entities."
            ),
            "recommended_actions": [
                "Implement a Third-Party Risk Management (TPRM) framework covering all critical data suppliers",
                "Establish vendor security assessment questionnaires and annual review cycles",
                "Map all data ingestion pipelines to their upstream supplier dependencies",
                "Introduce contractual security requirements into new supplier agreements",
                "Deploy software composition analysis (SCA) tooling for all internally developed systems",
            ],
            "enabling_dependencies": [
                "Zero Trust Network Access (ZTNA) capability to enforce least-privilege supplier access",
                "Procurement function engagement for contractual security clause integration",
            ],
            "success_indicators": [
                "Critical supplier inventory completed and risk-rated within 60 days",
                "TPRM framework adopted and first assessment cycle completed within 6 months",
                "100% of new supplier contracts include mandatory security clauses",
                "Annual supplier security review schedule established and maintained",
            ],
        },
        {
            "capability_id":   309,
            "capability_name": "Generative AI & LLM Operations",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Upstream",
            "current_score":   1.0,
            "target_score":    3,
            "narrative": (
                "Viennalife has no operational capability for generative AI or LLM deployment. "
                "Business units are beginning to explore use cases in policy documentation, "
                "customer communications, and claims summarisation, but without governance or "
                "infrastructure in place. Establishing a controlled GenAI platform is critical "
                "to prevent ungoverned shadow AI adoption."
            ),
            "recommended_actions": [
                "Define and publish a Generative AI Acceptable Use Policy for internal and customer-facing applications",
                "Establish a controlled GenAI sandbox environment with appropriate data isolation",
                "Implement prompt management, logging, and audit trail capabilities for all LLM interactions",
                "Deploy a content moderation and output validation layer before any customer-facing GenAI",
                "Train development and business teams on responsible GenAI development practices",
            ],
            "enabling_dependencies": [
                "AI Regulatory Compliance & Risk Management framework must classify GenAI use cases",
                "AI Security & Model Integrity controls required for LLM prompt injection defence",
                "Feature Store & Data Preparation capability to manage training and inference data quality",
            ],
            "success_indicators": [
                "GenAI Use Policy published and adopted across all business units",
                "Controlled sandbox environment operational within 90 days",
                "All LLM interactions logged and auditable from day one of production deployment",
                "First governed GenAI use case delivered within 6 months of platform establishment",
            ],
        },
        {
            "capability_id":   308,
            "capability_name": "Technical Debt Management",
            "domain":          "Applications",
            "capability_role": "Core",
            "current_score":   1.5,
            "target_score":    3,
            "narrative": (
                "Legacy actuarial platforms carry significant technical debt that is blocking "
                "modernisation initiatives. There is no structured programme to quantify, "
                "prioritise, or remediate technical debt, resulting in compounding maintenance "
                "costs and increasing risk of system failure during peak processing periods."
            ),
            "recommended_actions": [
                "Conduct a technical debt inventory across all core actuarial and policy administration systems",
                "Implement a technical debt register with risk scoring and remediation priority matrix",
                "Allocate a minimum 20% of each sprint to technical debt remediation",
                "Define technical debt thresholds beyond which systems trigger a modernisation review",
                "Establish architectural review boards to prevent net-new technical debt accumulation",
            ],
            "enabling_dependencies": [
                "DevOps capability to automate static analysis and code quality metrics",
                "Applications portfolio governance to own the debt register and remediation targets",
            ],
            "success_indicators": [
                "Technical debt inventory completed for all tier-1 systems within 120 days",
                "Technical debt register operational with at least quarterly review cadence",
                "Measurable reduction in critical technical debt items year-on-year",
                "Zero new high-severity technical debt items introduced without documented approval",
            ],
        },
    ]

    return dict(
        client_name=client_name, industry=industry, sector=sector, country=country,
        engagement_name=engagement_name, use_case_name=use_case_name,
        usecase_id=usecase_id, intent_text=intent_text, assessment_mode=assessment_mode,
        caps_by_role=caps_by_role, responses=responses,
        domain_targets=domain_targets, findings_narrative=findings_narrative,
        recommendations_data=recommendations_data, created_days_ago=created_days_ago,
    )


# =============================================================================
# Assessment 2 — Dubai Police HQ
# =============================================================================

def assessment_dubai_police(rng):
    client_name     = "Dubai Police HQ"
    industry        = "Government"
    sector          = "Law Enforcement"
    country         = "UAE"
    engagement_name = "Zero Trust Security Posture Assessment 2026"
    use_case_name   = "Zero Trust"
    usecase_id      = 18
    assessment_mode = "predefined"
    created_days_ago = 18

    intent_text = (
        "Dubai Police HQ is assessing its security posture against a Zero Trust architecture "
        "reference model to comply with UAE National Cybersecurity Authority (NCA) ECC-1:2018 "
        "controls and align with the Smart Dubai digital government security framework. "
        "The assessment will identify capability gaps across supply chain security, ZTNA "
        "architecture, and AI model integrity — three areas directly relevant to the "
        "organisation's expanding use of AI-driven public safety and surveillance platforms."
    )

    domain_targets = {
        "Security":             4,
        "Strategy & Governance": 3,
        "Operations":           3,
    }

    yes_p    = 0.20
    partial_p = 0.35

    core_caps = [
        _cap_dict(CAP_305, "Core"),
        _cap_dict(CAP_306, "Core"),
        _cap_dict(CAP_307, "Core"),
    ]

    def uae_govt_context(answer, cap_name):
        if answer == "Yes":
            return (
                "Control is fully documented and aligned to UAE NCA ECC-1:2018 requirements. "
                "Evidence verified during assessment workshop."
            )
        if answer == "Partial":
            return (
                "Control is partially implemented. Gaps identified in cross-agency data sharing "
                "environments. Remediation plan required to achieve full NCA compliance."
            )
        return (
            "Control is absent. This represents a non-compliance item under UAE NCA ECC-1:2018. "
            "Immediate remediation action required and must be reported to the CISO."
        )

    responses = build_yn_responses(core_caps, yes_p, partial_p, rng, context_fn=uae_govt_context)

    findings_narrative = (
        "Dubai Police HQ demonstrates early-stage Zero Trust maturity, with most controls in "
        "a Partial or absent state against the UAE National Cybersecurity Authority ECC-1:2018 "
        "reference framework. The assessment identified critical gaps in all three assessed "
        "capability domains: Supply Chain Security, Zero Trust Network Access architecture, "
        "and AI Security & Model Integrity. The organisation's expanding deployment of AI-driven "
        "operational and citizen-facing platforms significantly elevates the risk profile "
        "associated with these capability gaps.\n\n"
        "Supply chain security controls are inconsistently applied, with no formal third-party "
        "risk programme covering the organisation's technology and data supply chain. "
        "Zero Trust Network Access architecture exists in concept but has not been implemented "
        "in a manner consistent with the micro-segmentation and continuous verification principles "
        "required under a mature Zero Trust model. AI Security & Model Integrity controls are "
        "largely absent, representing a significant risk given the operational dependence on "
        "AI-driven classification and decision support systems in law enforcement contexts.\n\n"
        "The recommended remediation programme should be sequenced to deliver NCA compliance "
        "as the primary near-term objective within 12 months, followed by a second phase "
        "achieving full Zero Trust architecture implementation across all operational networks "
        "by month 24. Executive sponsorship at CISO level and a dedicated Zero Trust programme "
        "team are prerequisites for successful delivery within this timeline."
    )

    caps_by_role = {"Core": core_caps}

    recommendations_data = [
        {
            "capability_id":   306,
            "capability_name": "Zero Trust Network Access (ZTNA) Architecture",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   1.0,
            "target_score":    4,
            "narrative": (
                "ZTNA architecture is absent across the organisation's operational networks. "
                "The current perimeter-based model does not meet UAE NCA ECC-1:2018 access "
                "control requirements and represents the most critical gap identified in this assessment."
            ),
            "recommended_actions": [
                "Conduct a network segmentation assessment to identify all trust boundaries and lateral movement risks",
                "Define a Zero Trust architecture target state aligned to NCA ECC-1:2018 access control controls",
                "Deploy identity-based access controls for all administrative and privileged access paths",
                "Implement continuous device health verification for all endpoints accessing sensitive systems",
                "Establish micro-segmentation for all critical operational networks and data centres",
                "Deploy encrypted traffic inspection for all east-west and north-south traffic flows",
            ],
            "enabling_dependencies": [
                "Identity & Access Management capability must be at L3 to support per-session authorisation",
                "Network Operations capability required for traffic inspection infrastructure management",
                "Supply Chain Security controls to govern third-party access under the Zero Trust model",
            ],
            "success_indicators": [
                "Zero Trust target architecture approved and published within 60 days",
                "Privileged access management controls deployed to 100% of administrative systems",
                "Micro-segmentation implemented across all tier-1 operational networks within 12 months",
                "NCA ECC-1:2018 access control compliance achieved and independently verified",
            ],
        },
        {
            "capability_id":   305,
            "capability_name": "Supply Chain Security",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   1.0,
            "target_score":    4,
            "narrative": (
                "No structured third-party risk programme exists. Technology and data suppliers "
                "are not assessed against NCA security requirements, creating an uncontrolled "
                "attack surface in the organisation's extended digital ecosystem."
            ),
            "recommended_actions": [
                "Develop a Third-Party Risk Management policy aligned to NCA ECC-1:2018 requirements",
                "Classify all technology suppliers by criticality and conduct baseline security assessments",
                "Establish mandatory security requirements and contractual obligations for all critical suppliers",
                "Implement continuous monitoring of supplier access activity and anomaly detection",
                "Conduct an annual supplier security review with escalation to CISO for critical findings",
            ],
            "enabling_dependencies": [
                "ZTNA architecture to enforce least-privilege access for all third-party connections",
                "Procurement and Legal functions to embed security requirements in all new contracts",
            ],
            "success_indicators": [
                "Complete supplier inventory and risk classification within 90 days",
                "100% of critical suppliers assessed against NCA security requirements within 6 months",
                "Supplier access monitoring operational and reporting to CISO monthly",
                "Zero critical security incidents attributable to unmanaged third-party risk",
            ],
        },
        {
            "capability_id":   307,
            "capability_name": "AI Security & Model Integrity",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   1.0,
            "target_score":    4,
            "narrative": (
                "AI systems used in operational contexts have no formal security controls "
                "or model integrity verification. In a law enforcement context, model tampering "
                "or adversarial attacks represent both an operational and a public accountability risk."
            ),
            "recommended_actions": [
                "Inventory all AI systems in operational use and classify by sensitivity and public impact",
                "Implement model versioning, access controls, and tamper-evident audit trails for all AI models",
                "Deploy adversarial input detection and anomaly monitoring for all AI inference endpoints",
                "Establish a model integrity verification process before each production deployment",
                "Define and test incident response procedures for AI model compromise scenarios",
            ],
            "enabling_dependencies": [
                "AI Regulatory Compliance framework to govern AI model approval and lifecycle",
                "Security Operations Centre capability to monitor AI-specific threat indicators",
            ],
            "success_indicators": [
                "All AI systems inventoried and classified within 60 days",
                "Model integrity controls deployed to all tier-1 AI systems within 6 months",
                "AI-specific incident response procedure tested annually",
                "Zero unauthorised model modifications detected in production",
            ],
        },
    ]

    return dict(
        client_name=client_name, industry=industry, sector=sector, country=country,
        engagement_name=engagement_name, use_case_name=use_case_name,
        usecase_id=usecase_id, intent_text=intent_text, assessment_mode=assessment_mode,
        caps_by_role=caps_by_role, responses=responses,
        domain_targets=domain_targets, findings_narrative=findings_narrative,
        recommendations_data=recommendations_data, created_days_ago=created_days_ago,
    )


# =============================================================================
# Assessment 3 — TechNova Systems Inc
# =============================================================================

def assessment_technova(rng):
    client_name     = "TechNova Systems Inc"
    industry        = "Technology"
    sector          = "Enterprise Software"
    country         = "USA"
    engagement_name = "AI Platform Readiness Assessment -- Q1 FY26"
    use_case_name   = "AI Readiness & Maturity Assessment"
    usecase_id      = 30
    assessment_mode = "predefined"
    created_days_ago = 12

    intent_text = (
        "TechNova Systems Inc is conducting an AI readiness assessment to establish a "
        "comprehensive baseline of its AI engineering, governance, and operationalisation "
        "capabilities before embarking on a company-wide AI platform investment programme. "
        "As an enterprise software vendor, TechNova must demonstrate AI governance maturity "
        "to enterprise customers in regulated industries. The assessment spans the full "
        "AI capability spectrum from data preparation and model lifecycle management through "
        "to responsible AI governance, security, and orchestration frameworks."
    )

    domain_targets = {
        "AI & Cognitive Systems": 4,
        "Security":               4,
        "Data":                   4,
        "Applications":           3,
        "People":                 3,
    }

    mean   = 3.5
    spread = 0.7

    core_caps = [
        _cap_dict(CAP_315, "Core"),
        _cap_dict(CAP_307, "Core"),
        _cap_dict(CAP_318, "Core"),
        _cap_dict(CAP_311, "Core"),
        _cap_dict(CAP_309, "Core"),
        _cap_dict(CAP_312, "Core"),
        _cap_dict(CAP_317, "Core"),
        _cap_dict(CAP_313, "Core"),
        _cap_dict(CAP_319, "Core"),
        _cap_dict(CAP_314, "Core"),
        _cap_dict(CAP_316, "Core"),
    ]

    all_caps = core_caps
    responses = build_free_text_responses(all_caps, domain_targets, mean, spread, rng, industry)

    findings_narrative = (
        "TechNova Systems Inc demonstrates solid mid-maturity AI capabilities, with an average "
        "score of approximately 3.5 across the assessed capability set. As an enterprise software "
        "organisation, TechNova has invested meaningfully in AI engineering practices — model "
        "evaluation, feature store infrastructure, and generative AI operations reflect Defined "
        "to Integrated maturity. However, the assessment reveals a pronounced gap between "
        "engineering capability and governance maturity, particularly in the areas of AI regulatory "
        "compliance, explainability, and bias detection — capabilities increasingly required by "
        "TechNova's enterprise customer base operating in regulated industries.\n\n"
        "AI Security & Model Integrity and Cognitive Search & Knowledge Retrieval show the "
        "largest capability gaps relative to the target of L4, representing material risks "
        "to both product security and the organisation's market positioning. AI Compute & "
        "Accelerator Management is at an early stage, creating infrastructure constraints "
        "as the organisation scales training workloads for its flagship AI products. "
        "The organisation's AI Agent & Orchestration Framework capability is nascent, "
        "limiting the ability to deliver agentic AI features that enterprise customers "
        "are increasingly demanding.\n\n"
        "The transformation roadmap should sequence Responsible AI governance as the "
        "highest-priority investment, as it creates a trust foundation required for "
        "enterprise sales in regulated sectors. AI Security hardening and Cognitive Search "
        "platform development are strong P2 candidates that deliver direct product value. "
        "AI Compute & Accelerator Management and Agent Orchestration capability should "
        "be addressed in a second wave once governance and security foundations are in place."
    )

    caps_by_role = {"Core": core_caps}

    recommendations_data = [
        {
            "capability_id":   315,
            "capability_name": "AI Regulatory Compliance & Risk Management",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   2.0,
            "target_score":    4,
            "narrative": (
                "TechNova's AI regulatory compliance capability is at Defined level, adequate "
                "for internal operations but insufficient for the enterprise customer trust "
                "requirements that are driving purchase decisions in regulated sectors. "
                "Achieving L4 requires an automated compliance monitoring platform with "
                "customer-facing attestation capabilities."
            ),
            "recommended_actions": [
                "Deploy an automated AI compliance monitoring platform covering model lifecycle events",
                "Develop customer-facing AI compliance attestation reports for regulated industry customers",
                "Establish a cross-functional AI Ethics & Compliance Board with monthly review cadence",
                "Integrate AI regulatory requirements tracking into the product development lifecycle",
                "Publish an annual AI Transparency Report covering model governance and fairness metrics",
            ],
            "enabling_dependencies": [
                "AI Bias Detection & Fairness Testing at L3 to provide compliance evidence",
                "AI Explainability & Interpretability at L3 to support customer audit requirements",
                "Legal function engagement to map product AI use cases against applicable regulations",
            ],
            "success_indicators": [
                "Automated compliance monitoring operational across all production AI models",
                "Customer-facing attestation report available for 100% of regulated-sector products",
                "AI Ethics Board operational with published quarterly compliance reports",
                "Zero compliance findings raised by enterprise customers in regulated sectors",
            ],
        },
        {
            "capability_id":   307,
            "capability_name": "AI Security & Model Integrity",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   2.5,
            "target_score":    4,
            "narrative": (
                "Model security controls are inconsistently applied across TechNova's product "
                "portfolio. As an enterprise software vendor shipping AI capabilities to "
                "customers, inadequate model integrity controls represent both a reputational "
                "and a contractual risk, particularly for customers in financial services and healthcare."
            ),
            "recommended_actions": [
                "Implement automated model signing and integrity verification for all released AI artefacts",
                "Deploy adversarial robustness testing as a mandatory gate in the model release pipeline",
                "Establish a responsible disclosure programme for AI-specific security vulnerabilities",
                "Integrate AI threat modelling into the secure software development lifecycle",
                "Implement runtime monitoring for model drift and anomalous inference patterns in production",
            ],
            "enabling_dependencies": [
                "Model Evaluation & Benchmarking capability to support adversarial robustness testing",
                "DevOps pipeline integration for automated security scanning of AI artefacts",
            ],
            "success_indicators": [
                "100% of released AI models have verifiable integrity signatures",
                "Adversarial robustness testing pass rate greater than 95% across all production models",
                "AI vulnerability disclosure programme operational within 90 days",
                "Zero model integrity incidents reported by enterprise customers",
            ],
        },
        {
            "capability_id":   318,
            "capability_name": "Cognitive Search & Knowledge Retrieval",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   2.5,
            "target_score":    4,
            "narrative": (
                "TechNova's cognitive search capability is a significant competitive differentiator "
                "opportunity. Current implementation covers basic vector search but lacks "
                "enterprise-grade knowledge graph integration, multi-modal retrieval, and "
                "the reranking capabilities required for enterprise knowledge management use cases."
            ),
            "recommended_actions": [
                "Extend the search platform with knowledge graph integration for entity-aware retrieval",
                "Implement hybrid retrieval combining dense vector search with sparse keyword indexing",
                "Deploy a multi-stage reranking pipeline with relevance feedback and query understanding",
                "Add multi-modal search support (text, image, structured data) for enterprise content repositories",
                "Establish retrieval quality benchmarking with standardised enterprise test sets",
            ],
            "enabling_dependencies": [
                "Feature Store & Data Preparation to manage embedding generation and index updates",
                "AI Agent & Orchestration Framework to enable RAG-based agentic workflows",
            ],
            "success_indicators": [
                "Retrieval relevance scores exceeding 0.85 on standard enterprise benchmark datasets",
                "Multi-modal search capability available in at least two product lines within 6 months",
                "Knowledge graph integration live in production for at least one enterprise customer pilot",
                "Search latency under 200ms at p99 for all standard retrieval workloads",
            ],
        },
        {
            "capability_id":   317,
            "capability_name": "AI Agent & Orchestration Framework",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   2.0,
            "target_score":    4,
            "narrative": (
                "Agentic AI capabilities are a rapidly growing enterprise customer requirement. "
                "TechNova's current orchestration framework is at prototype stage, insufficient "
                "for the production-grade, auditable multi-agent workflows that enterprise "
                "customers in regulated sectors require."
            ),
            "recommended_actions": [
                "Define an enterprise-grade agent orchestration reference architecture with observability built in",
                "Implement a multi-agent workflow engine with full execution tracing and rollback capability",
                "Establish agent safety controls including output validation, rate limiting, and human-in-the-loop gates",
                "Develop a library of pre-certified agent templates for common enterprise workflow patterns",
                "Create a developer SDK and documentation for building governed agentic applications",
            ],
            "enabling_dependencies": [
                "AI Regulatory Compliance framework to govern autonomous agent decision boundaries",
                "AI Security & Model Integrity controls for agent prompt injection defence",
                "Cognitive Search & Knowledge Retrieval as the primary retrieval layer for RAG-based agents",
            ],
            "success_indicators": [
                "Production-grade agent orchestration platform available to product teams within 9 months",
                "All agent executions fully traced and auditable end-to-end",
                "Human-in-the-loop controls available for all configurable decision thresholds",
                "First enterprise customer production deployment of multi-agent workflow within 12 months",
            ],
        },
    ]

    return dict(
        client_name=client_name, industry=industry, sector=sector, country=country,
        engagement_name=engagement_name, use_case_name=use_case_name,
        usecase_id=usecase_id, intent_text=intent_text, assessment_mode=assessment_mode,
        caps_by_role=caps_by_role, responses=responses,
        domain_targets=domain_targets, findings_narrative=findings_narrative,
        recommendations_data=recommendations_data, created_days_ago=created_days_ago,
    )


# =============================================================================
# Assessment 4 — Santos Energy Group (MIXED question styles)
# =============================================================================

def assessment_santos(rng):
    client_name     = "Santos Energy Group"
    industry        = "Energy & Resources"
    sector          = "Petroleum & Gas"
    country         = "Australia"
    engagement_name = "Innovation & AI Capability Assessment -- FY26"
    use_case_name   = "Innovation at Scale"
    usecase_id      = 9
    assessment_mode = "predefined"
    created_days_ago = 8

    intent_text = (
        "Santos Energy Group is assessing its innovation and AI capabilities to identify "
        "the foundation investments required to support a strategic shift toward AI-driven "
        "operational optimisation and digital twin-enabled asset management. The organisation "
        "operates in a complex regulatory environment and must balance innovation investment "
        "with operational continuity requirements for critical energy infrastructure. "
        "This assessment will inform the innovation investment portfolio for FY26-FY27, "
        "with a specific focus on generative AI for field operations, predictive analytics "
        "for asset performance, and digital twin capabilities for simulation and planning."
    )

    domain_targets = {
        "Innovation":             3,
        "AI & Cognitive Systems": 3,
        "Security":               3,
        "Data":                   3,
    }

    core_mean   = 2.2
    core_spread = 0.5
    yn_yes_p    = 0.22
    yn_partial_p = 0.40

    core_caps = [
        _cap_dict(CAP_317, "Core"),
        _cap_dict(CAP_310, "Core"),
        _cap_dict(CAP_309, "Core"),
        _cap_dict(CAP_316, "Core"),
    ]
    upstream_caps = [
        _cap_dict(CAP_311, "Upstream"),
        _cap_dict(CAP_312, "Upstream"),
    ]

    # Core caps: maturity_1_5; Upstream caps: yes_no_evidence
    core_responses = build_maturity_responses(
        core_caps, domain_targets, core_mean, core_spread, rng, industry
    )

    def energy_context(answer, cap_name):
        if answer == "Yes":
            return (
                "Practice is in place and applied to operational technology environments. "
                "Evidence reviewed against Australian Energy Sector Cyber Security Framework requirements."
            )
        if answer == "Partial":
            return (
                "Applied inconsistently across IT environments. Operational technology environments "
                "not yet covered. Gap identified for OT/IT convergence programme."
            )
        return (
            "Not in place. Identified as a critical gap for operational continuity and "
            "compliance with AESCSF requirements. Remediation priority raised to programme board."
        )

    upstream_responses = build_yn_responses(
        upstream_caps, yn_yes_p, yn_partial_p, rng, context_fn=energy_context
    )

    all_responses = core_responses + upstream_responses

    findings_narrative = (
        "Santos Energy Group's innovation and AI capability profile reveals a predominantly "
        "Ad Hoc to Defined maturity level across the assessed domains, with an average score "
        "of approximately 2.2 for core capabilities. The organisation faces a strategic tension "
        "between the urgency to adopt AI-driven operational optimisation — particularly for "
        "remote asset management and predictive maintenance — and the foundational data and "
        "governance infrastructure gaps that constrain safe and effective AI deployment in "
        "critical energy infrastructure contexts.\n\n"
        "The Digital Twin & Simulation capability represents the highest-value near-term "
        "investment, with direct application to reservoir simulation, plant optimisation, "
        "and emergency scenario planning. However, the Feature Store & Data Preparation "
        "and Model Evaluation & Benchmarking capabilities — assessed as mostly absent via "
        "the evidence review — represent foundational prerequisites that must be addressed "
        "before production AI systems can be deployed safely. Generative AI & LLM Operations "
        "is receiving informal exploration within engineering teams but lacks the governance "
        "and infrastructure required for operational deployment.\n\n"
        "The recommended sequencing prioritises data infrastructure and AI lifecycle management "
        "foundations in the first phase, enabling the deployment of predictive analytics and "
        "digital twin capabilities in the second phase. Generative AI for field operations "
        "should be treated as a third-phase initiative once governance and data quality "
        "foundations are established. This phased approach manages operational risk while "
        "delivering measurable capability uplift within a 24-month programme horizon."
    )

    caps_by_role = {"Core": core_caps, "Upstream": upstream_caps}

    recommendations_data = [
        {
            "capability_id":   310,
            "capability_name": "Digital Twin & Simulation",
            "domain":          "Innovation",
            "capability_role": "Core",
            "current_score":   1.5,
            "target_score":    3,
            "narrative": (
                "Digital twin capability is at a very early stage. Santos has conducted isolated "
                "pilot projects but has no enterprise-grade digital twin platform or methodology. "
                "Given the direct applicability to reservoir modelling, plant performance, and "
                "safety scenario simulation, this represents a high-value investment."
            ),
            "recommended_actions": [
                "Define a digital twin reference architecture for Santos' key asset classes (wells, processing, pipelines)",
                "Establish a digital twin Centre of Excellence with cross-disciplinary engineering, data, and IT membership",
                "Deploy a pilot digital twin for a single high-value asset class within 6 months",
                "Develop real-time data ingestion pipelines from SCADA and IoT sensors to the digital twin platform",
                "Define simulation scenarios covering production optimisation, maintenance planning, and safety modelling",
            ],
            "enabling_dependencies": [
                "Feature Store & Data Preparation to provide clean sensor and operational data for twin models",
                "Predictive Analytics & Forecasting capability to drive simulation outputs",
                "OT/IT convergence programme to enable real-time data flows from field equipment",
            ],
            "success_indicators": [
                "Digital twin reference architecture published and approved by engineering leadership within 90 days",
                "First pilot digital twin live and demonstrating measurable production optimisation within 6 months",
                "Real-time data ingestion from at least 500 sensors per major asset site",
                "Digital twin-enabled decisions documented and value measured quarterly",
            ],
        },
        {
            "capability_id":   309,
            "capability_name": "Generative AI & LLM Operations",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   2.0,
            "target_score":    3,
            "narrative": (
                "Generative AI exploration is underway informally within engineering teams, "
                "but no governed platform or policy exists. Use cases are emerging for technical "
                "documentation, field inspection reporting, and knowledge retrieval from "
                "well logs and engineering records. A governed platform is required to "
                "capture this value safely."
            ),
            "recommended_actions": [
                "Establish an enterprise GenAI platform with data isolation controls for operational data",
                "Define and publish a GenAI Use Policy covering sensitive operational and safety-critical content",
                "Deploy a document intelligence use case for well logs and inspection records as the first production deployment",
                "Implement output validation and human review requirements for any safety-relevant AI outputs",
                "Train engineering and operations staff on responsible GenAI use in field contexts",
            ],
            "enabling_dependencies": [
                "AI Security & Model Integrity controls for operational data protection in GenAI workloads",
                "Feature Store & Data Preparation for document ingestion and embedding management",
            ],
            "success_indicators": [
                "GenAI platform operational with data isolation controls for operational data within 90 days",
                "GenAI Use Policy published and mandatory training completed by all technical staff",
                "First document intelligence use case live in production with measurable efficiency gain",
                "No safety-relevant decisions made without documented human review of AI-generated outputs",
            ],
        },
        {
            "capability_id":   316,
            "capability_name": "Predictive Analytics & Forecasting",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   2.0,
            "target_score":    3,
            "narrative": (
                "Predictive analytics for asset performance and production forecasting is a "
                "critical operational capability for Santos. Current state relies on manual "
                "analysis and historical trend extrapolation rather than ML-driven forecasting. "
                "Establishing this capability has direct production revenue implications."
            ),
            "recommended_actions": [
                "Deploy predictive maintenance models for rotating equipment failure prediction on critical assets",
                "Establish a production forecasting platform integrating geological, operational, and market data",
                "Implement anomaly detection for early identification of production decline or equipment degradation",
                "Create a model performance monitoring framework with automated retraining triggers",
                "Develop a self-service analytics layer enabling engineering and operations teams to run forecasts",
            ],
            "enabling_dependencies": [
                "Feature Store & Data Preparation at L2 to provide consistent feature engineering for models",
                "Model Evaluation & Benchmarking to validate forecast accuracy before production deployment",
                "OT/IT data integration to provide real-time operational data for prediction inputs",
            ],
            "success_indicators": [
                "First predictive maintenance model deployed to at least 2 critical asset classes within 6 months",
                "Production forecast accuracy improvement of at least 10% versus current manual methods",
                "Anomaly detection alerts reviewed and actioned within defined SLA timeframes",
                "Model performance dashboards visible to operations leadership monthly",
            ],
        },
    ]

    return dict(
        client_name=client_name, industry=industry, sector=sector, country=country,
        engagement_name=engagement_name, use_case_name=use_case_name,
        usecase_id=usecase_id, intent_text=intent_text, assessment_mode=assessment_mode,
        caps_by_role=caps_by_role, responses=all_responses,
        domain_targets=domain_targets, findings_narrative=findings_narrative,
        recommendations_data=recommendations_data, created_days_ago=created_days_ago,
    )


# =============================================================================
# Assessment 5 — Quantex Capital Partners
# =============================================================================

def assessment_quantex(rng):
    client_name     = "Quantex Capital Partners"
    industry        = "Financial Services"
    sector          = "Asset Management"
    country         = "Singapore"
    engagement_name = "Edge & Cloud Modernization Capability Review -- Q1 2026"
    use_case_name   = "Edge & Cloud Modernization"
    usecase_id      = 16
    assessment_mode = "predefined"
    created_days_ago = 5

    intent_text = (
        "Quantex Capital Partners is assessing its edge and cloud modernisation capabilities "
        "to support the strategic objective of reducing on-premises infrastructure dependency "
        "by 60% over the next three years while maintaining full compliance with MAS TRM "
        "and MAS Notice 655 on technology risk management. The assessment will establish a "
        "baseline across security, applications modernisation, and innovation capabilities, "
        "with particular focus on supply chain security risks associated with the cloud "
        "transition, technical debt in legacy portfolio management systems, and ZTNA "
        "controls required for hybrid multi-cloud operations."
    )

    domain_targets = {
        "Applications": 4,
        "Security":     4,
        "Innovation":   3,
        "Operations":   3,
    }

    yes_p    = 0.28
    partial_p = 0.38

    core_caps = [
        _cap_dict(CAP_305, "Core"),
        _cap_dict(CAP_308, "Core"),
        _cap_dict(CAP_306, "Core"),
    ]
    upstream_caps = [
        _cap_dict(CAP_310, "Upstream"),
    ]

    def mas_context(answer, cap_name):
        if answer == "Yes":
            return (
                "Control is implemented and documented. Evidence reviewed and assessed as "
                "compliant with MAS TRM Guidelines requirements. Control owner confirmed."
            )
        if answer == "Partial":
            return (
                "Control exists but is not consistently applied across all business lines. "
                "Partial compliance with MAS TRM Guidelines identified. Gap remediation "
                "required before next MAS supervisory review."
            )
        return (
            "Control is not in place. This represents a gap against MAS TRM Guidelines "
            "requirements. Immediate remediation planning required and must be logged in "
            "the organisation's Technology Risk Register."
        )

    all_caps = core_caps + upstream_caps
    responses = build_yn_responses(all_caps, yes_p, partial_p, rng, context_fn=mas_context)

    findings_narrative = (
        "Quantex Capital Partners presents a mixed security and modernisation capability profile. "
        "Security capabilities related to supply chain risk and Zero Trust architecture are "
        "only partially implemented, representing gaps against MAS TRM Guidelines that require "
        "structured remediation before the organisation can safely proceed with its planned "
        "cloud migration programme. The Technical Debt Management capability is notably absent, "
        "with legacy portfolio management systems carrying significant unquantified technical "
        "debt that is already constraining cloud migration velocity.\n\n"
        "The Applications domain reflects the broader challenge: while the organisation has "
        "identified cloud modernisation as a strategic priority, the foundations for safe "
        "migration — including supply chain security controls for cloud service providers, "
        "ZTNA architecture for hybrid access, and systematic technical debt management — "
        "are not yet at the maturity level required for a compliant and resilient cloud estate. "
        "The Digital Twin & Simulation capability, while aspirational, is appropriately "
        "deprioritised until the security and modernisation foundations are in place.\n\n"
        "The recommended programme should sequence Security capability uplift as the critical "
        "path, as MAS compliance is a non-negotiable prerequisite for cloud service consumption "
        "at the scale Quantex is planning. A parallel technical debt programme will accelerate "
        "migration by reducing the integration complexity of legacy systems. ZTNA architecture "
        "should be designed upfront as the target access model for the hybrid estate, "
        "enabling secure cloud access from day one of the migration programme."
    )

    caps_by_role = {"Core": core_caps, "Upstream": upstream_caps}

    recommendations_data = [
        {
            "capability_id":   308,
            "capability_name": "Technical Debt Management",
            "domain":          "Applications",
            "capability_role": "Core",
            "current_score":   1.0,
            "target_score":    4,
            "narrative": (
                "Technical debt in legacy portfolio management systems is the primary blocker "
                "to cloud migration. Without a structured technical debt programme, migration "
                "costs and timelines are unpredictable, and the risk of production incidents "
                "during migration is unacceptably high for MAS-regulated operations."
            ),
            "recommended_actions": [
                "Conduct a technical debt assessment across all tier-1 portfolio and trading systems",
                "Establish a technical debt register with quantified remediation cost and risk scoring",
                "Create a cloud migration readiness score for each application based on technical debt profile",
                "Allocate dedicated sprint capacity for debt remediation ahead of each migration wave",
                "Define and enforce coding standards and architecture guardrails to prevent new debt accumulation",
            ],
            "enabling_dependencies": [
                "Applications portfolio governance function to own the debt register",
                "DevOps automation to enable static analysis and quality gate enforcement",
            ],
            "success_indicators": [
                "Technical debt assessment completed for all tier-1 systems within 90 days",
                "Cloud migration readiness score above 70% for all systems in migration wave 1",
                "Reduction in critical technical debt items by 30% within 12 months",
                "Zero production incidents attributable to unresolved technical debt during migration",
            ],
        },
        {
            "capability_id":   306,
            "capability_name": "Zero Trust Network Access (ZTNA) Architecture",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   1.0,
            "target_score":    4,
            "narrative": (
                "ZTNA architecture is absent. The current perimeter model is incompatible "
                "with the target hybrid multi-cloud estate and does not meet MAS TRM "
                "requirements for access control in cloud environments. Designing "
                "ZTNA as the target state upfront is critical to the cloud programme."
            ),
            "recommended_actions": [
                "Define a ZTNA target architecture for the hybrid multi-cloud estate aligned to MAS TRM requirements",
                "Deploy identity-verified, device-health-checked access controls for all cloud service access",
                "Implement continuous authentication for all privileged access to financial systems in cloud",
                "Establish encrypted traffic inspection for all east-west traffic in cloud environments",
                "Migrate all VPN-based remote access to the ZTNA platform within 12 months",
            ],
            "enabling_dependencies": [
                "Identity & Access Management at L3 to support per-session authorisation",
                "Supply Chain Security controls for cloud service provider access governance",
            ],
            "success_indicators": [
                "ZTNA target architecture approved by CISO and MAS-aligned within 60 days",
                "All cloud access routes transitioned from VPN to ZTNA within 12 months",
                "100% of privileged access to cloud financial systems through identity-verified controls",
                "MAS TRM compliance assessment for cloud access controls passes without findings",
            ],
        },
        {
            "capability_id":   305,
            "capability_name": "Supply Chain Security",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   1.5,
            "target_score":    4,
            "narrative": (
                "Cloud migration introduces significant supply chain risk via new technology "
                "providers. Current third-party risk controls do not cover cloud service "
                "providers at the depth required by MAS Notice 655 on outsourcing requirements "
                "for financial institutions."
            ),
            "recommended_actions": [
                "Extend the Third-Party Risk Management framework to explicitly cover cloud service providers",
                "Conduct MAS Notice 655-aligned due diligence assessments on all cloud service providers",
                "Establish data residency and sovereignty controls for all cloud-hosted workloads",
                "Implement continuous monitoring of cloud service provider security posture",
                "Define exit strategies and contractual protections for all critical cloud dependencies",
            ],
            "enabling_dependencies": [
                "Legal and Compliance to review all cloud contracts against MAS outsourcing requirements",
                "Technology Risk function to maintain cloud supplier risk register",
            ],
            "success_indicators": [
                "All cloud service providers assessed against MAS Notice 655 within 90 days",
                "100% of critical cloud contracts include MAS-required security and exit clauses",
                "Cloud supplier risk register reviewed and updated quarterly",
                "No MAS findings related to cloud outsourcing governance in next supervisory review",
            ],
        },
    ]

    return dict(
        client_name=client_name, industry=industry, sector=sector, country=country,
        engagement_name=engagement_name, use_case_name=use_case_name,
        usecase_id=usecase_id, intent_text=intent_text, assessment_mode=assessment_mode,
        caps_by_role=caps_by_role, responses=responses,
        domain_targets=domain_targets, findings_narrative=findings_narrative,
        recommendations_data=recommendations_data, created_days_ago=created_days_ago,
    )


# =============================================================================
# Assessment 6 — Axiom Logistics APAC
# =============================================================================

def assessment_axiom(rng):
    client_name     = "Axiom Logistics APAC"
    industry        = "Logistics & Transportation"
    sector          = "Third-Party Logistics"
    country         = "Singapore"
    engagement_name = "Digital Supply Chain Capability Assessment -- FY26"
    use_case_name   = "Digital Supply Chain"
    usecase_id      = 26
    assessment_mode = "predefined"
    created_days_ago = 2

    intent_text = (
        "Axiom Logistics APAC is undertaking a digital supply chain capability assessment "
        "to establish a maturity baseline for its AI-driven logistics optimisation programme. "
        "Operating across 14 APAC markets with complex multi-tier supplier networks, Axiom "
        "must build AI and security capabilities that support real-time visibility, predictive "
        "disruption management, and dynamic routing optimisation. The assessment will identify "
        "gaps in supply chain security, generative AI for operations, predictive analytics, "
        "and data preparation capabilities that are prerequisite investments for the FY26 "
        "AI logistics platform."
    )

    domain_targets = {
        "AI & Cognitive Systems": 3,
        "Security":               3,
        "Data":                   3,
    }

    mean   = 2.7
    spread = 0.6

    core_caps = [
        _cap_dict(CAP_305, "Core"),
        _cap_dict(CAP_309, "Core"),
        _cap_dict(CAP_316, "Core"),
    ]
    upstream_caps = [
        _cap_dict(CAP_307, "Upstream"),
        _cap_dict(CAP_311, "Upstream"),
    ]

    all_caps = core_caps + upstream_caps
    responses = build_free_text_responses(all_caps, domain_targets, mean, spread, rng, industry)

    findings_narrative = (
        "Axiom Logistics APAC's digital supply chain capability profile reflects the "
        "organisation's current transition from traditional logistics operations to a "
        "data-driven, AI-enabled model. Average capability maturity of approximately 2.7 "
        "indicates that foundational processes are in place but significant uplift is "
        "required to achieve the integrated, intelligent logistics platform the organisation "
        "is targeting. Supply Chain Security is a particular concern given Axiom's exposure "
        "across 14 APAC markets with diverse regulatory requirements and technology suppliers.\n\n"
        "Generative AI & LLM Operations and Predictive Analytics & Forecasting are the "
        "highest-priority gaps, as these capabilities directly underpin the core AI logistics "
        "platform use cases of demand forecasting, dynamic routing, and disruption prediction. "
        "Feature Store & Data Preparation shows early-stage maturity, creating a foundational "
        "constraint on model quality for all downstream AI initiatives. AI Security & Model "
        "Integrity controls are developing but require acceleration to meet the security "
        "standards expected by Axiom's enterprise shipper customers who are subject to "
        "Singapore's regulatory frameworks.\n\n"
        "The transformation programme should prioritise establishing a unified data platform "
        "with Feature Store capability as the foundational investment, enabling all subsequent "
        "AI development to build on consistent, governed data assets. Predictive analytics "
        "for demand forecasting and route optimisation should follow as the first production "
        "AI capability, delivering direct business value and demonstrating the platform's "
        "commercial viability. Supply chain security and GenAI capabilities should be "
        "developed in parallel, with a 12-month target for all three capabilities reaching L3."
    )

    caps_by_role = {"Core": core_caps, "Upstream": upstream_caps}

    recommendations_data = [
        {
            "capability_id":   305,
            "capability_name": "Supply Chain Security",
            "domain":          "Security",
            "capability_role": "Core",
            "current_score":   2.0,
            "target_score":    3,
            "narrative": (
                "Supply chain security controls cover Axiom's immediate IT environment but "
                "do not extend to the multi-tier supplier network spanning 14 APAC markets. "
                "This creates significant blind spots for cyber risk propagation through "
                "logistics technology partners and data exchange platforms."
            ),
            "recommended_actions": [
                "Map all technology and data exchange suppliers across the APAC supplier network",
                "Implement a tiered third-party risk assessment process based on data sensitivity and operational criticality",
                "Establish security requirements for all logistics platform integrations and API connections",
                "Deploy continuous monitoring of supplier-facing APIs for anomalous access patterns",
                "Develop a supply chain incident response playbook covering multi-market regulatory notification requirements",
            ],
            "enabling_dependencies": [
                "Data classification framework to identify sensitive logistics and customer data flows",
                "Legal function to map APAC data protection requirements by market",
            ],
            "success_indicators": [
                "Supplier security inventory completed across all 14 APAC markets within 90 days",
                "100% of critical logistics platform integrations assessed and secured within 6 months",
                "Supplier-facing API monitoring operational with real-time alerting",
                "Supply chain incident response playbook tested annually per market",
            ],
        },
        {
            "capability_id":   316,
            "capability_name": "Predictive Analytics & Forecasting",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   2.5,
            "target_score":    3,
            "narrative": (
                "Predictive analytics is in development with initial demand forecasting "
                "models in pilot. However, the models are not production-grade, lack "
                "multi-market calibration, and are disconnected from the operational "
                "systems that would consume their outputs in real time."
            ),
            "recommended_actions": [
                "Deploy production-grade demand forecasting models for at least 3 high-volume APAC trade lanes",
                "Integrate forecasting model outputs into the transport management system for automated routing suggestions",
                "Establish a multi-market model calibration process to account for regional demand patterns",
                "Implement disruption prediction models for major APAC port and customs delay risk factors",
                "Create forecasting accuracy dashboards visible to operations and commercial teams",
            ],
            "enabling_dependencies": [
                "Feature Store & Data Preparation at L2 to provide consistent feature pipelines for forecasting models",
                "Transport Management System integration for real-time operational data access",
            ],
            "success_indicators": [
                "Demand forecasting accuracy within 10% of actuals for major APAC trade lanes",
                "Forecasting model outputs consumed by TMS for routing decisions within 6 months",
                "Disruption prediction model live and informing customer communications for at least 2 markets",
                "Forecasting model retraining cycle operating on a minimum monthly cadence",
            ],
        },
        {
            "capability_id":   309,
            "capability_name": "Generative AI & LLM Operations",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Core",
            "current_score":   2.5,
            "target_score":    3,
            "narrative": (
                "GenAI is being explored for documentation generation, customs query handling, "
                "and customer exception management. Current approaches are informal and not "
                "governed. A production-grade GenAI platform with supply chain domain grounding "
                "is required to capture the operational efficiency gains at scale."
            ),
            "recommended_actions": [
                "Deploy a GenAI platform with RAG-based access to Axiom's operational knowledge base",
                "Implement governed GenAI use cases for customs documentation and exception management notifications",
                "Establish prompt management, logging, and audit trail for all GenAI operational use",
                "Define content moderation and accuracy thresholds for customer-facing GenAI outputs",
                "Create an internal GenAI capability building programme for operations and commercial teams",
            ],
            "enabling_dependencies": [
                "Feature Store & Data Preparation for document ingestion and logistics knowledge base management",
                "AI Security & Model Integrity for data protection in GenAI workloads handling shipper data",
            ],
            "success_indicators": [
                "GenAI platform with logistics domain knowledge base operational within 90 days",
                "First production GenAI use case live with measurable time saving versus manual process",
                "100% of GenAI outputs logged and auditable from day one of production",
                "Net Promoter Score improvement for customer exception communication within 6 months",
            ],
        },
        {
            "capability_id":   311,
            "capability_name": "Feature Store & Data Preparation",
            "domain":          "AI & Cognitive Systems",
            "capability_role": "Upstream",
            "current_score":   2.0,
            "target_score":    3,
            "narrative": (
                "Feature engineering is performed ad hoc by individual data science teams "
                "with no shared feature store. This creates duplicated effort, inconsistent "
                "feature definitions, and model quality issues as features drift between "
                "training and serving environments — a critical foundational gap for the "
                "AI logistics platform."
            ),
            "recommended_actions": [
                "Deploy an enterprise feature store platform covering all logistics domain features",
                "Standardise feature definitions across all AI use cases (demand, routing, disruption models)",
                "Implement training-serving consistency checks to detect feature drift before model degradation",
                "Establish a data quality framework with automated checks for all feature pipelines",
                "Create a feature discovery catalogue enabling reuse across data science teams",
            ],
            "enabling_dependencies": [
                "Data platform infrastructure to support both batch and real-time feature serving",
                "Data governance framework to define data ownership and quality standards",
            ],
            "success_indicators": [
                "Feature store operational with at least 50 standardised features from logistics domain within 90 days",
                "Training-serving feature consistency above 99% for all production models",
                "Feature reuse rate across AI projects exceeding 60% within 12 months",
                "Data quality checks passing at over 98% for all critical feature pipelines",
            ],
        },
    ]

    return dict(
        client_name=client_name, industry=industry, sector=sector, country=country,
        engagement_name=engagement_name, use_case_name=use_case_name,
        usecase_id=usecase_id, intent_text=intent_text, assessment_mode=assessment_mode,
        caps_by_role=caps_by_role, responses=responses,
        domain_targets=domain_targets, findings_narrative=findings_narrative,
        recommendations_data=recommendations_data, created_days_ago=created_days_ago,
    )


# =============================================================================
# Main
# =============================================================================

def main():
    rng = random.Random(99)

    # ── Ensure findings_narrative column exists ───────────────────────────────
    try:
        con.execute("ALTER TABLE Assessment ADD COLUMN findings_narrative TEXT")
        con.commit()
        print("Added findings_narrative column to Assessment table.")
    except Exception:
        pass  # already exists

    # ── Ensure AssessmentRecommendation table exists ──────────────────────────
    con.execute("""
        CREATE TABLE IF NOT EXISTS AssessmentRecommendation (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id        INTEGER NOT NULL,
            capability_id        INTEGER,
            capability_name      TEXT,
            domain               TEXT,
            capability_role      TEXT,
            current_score        REAL,
            target_maturity      INTEGER,
            gap                  REAL,
            priority_tier        TEXT,
            effort_estimate      TEXT,
            recommended_actions  TEXT,
            enabling_dependencies TEXT,
            success_indicators   TEXT,
            hpe_relevance        TEXT,
            narrative            TEXT,
            created_at           TEXT
        )
    """)
    con.commit()

    builders = [
        ("1", "Viennalife Insurance AG",    assessment_viennalife),
        ("2", "Dubai Police HQ",            assessment_dubai_police),
        ("3", "TechNova Systems Inc",       assessment_technova),
        ("4", "Santos Energy Group",        assessment_santos),
        ("5", "Quantex Capital Partners",   assessment_quantex),
        ("6", "Axiom Logistics APAC",       assessment_axiom),
    ]

    created = 0
    skipped = 0
    for idx, label, builder_fn in builders:
        print(f"\n{'='*60}")
        print(f"Assessment {idx}: {label}")
        data = builder_fn(rng)
        result = insert_assessment(**data)
        if result is None:
            skipped += 1
        else:
            created += 1

    print(f"\n{'='*60}")
    print(f"Done. {created} assessment(s) created, {skipped} skipped (already exist).")
    con.close()


if __name__ == "__main__":
    main()

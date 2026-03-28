# -*- coding: utf-8 -*-
"""
Seed 5 FinOps Foundation Framework assessments for fictitious clients.

Each assessment is at a different phase of the workflow, demonstrating the
full assessment lifecycle inside Meridant Matrix.

  Phase 1 — Wolters Kluwer NV        (Netherlands / Software)       UC-41  In Progress  (responses captured, no findings)
  Phase 2 — Marks & Spencer Group     (UK / Retail)                  UC-42  Findings only (no narrative)
  Phase 3 — Brambles Limited          (Australia / Logistics)        UC-43  Findings + executive narrative
  Phase 4 — Grab Holdings             (Singapore / Technology)       UC-41  Complete with recommendations
  Phase 5 — Fortescue Metals Group    (Australia / Mining)           UC-42  Archived (complete + recommendations)

Also seeds Next_UseCaseCapabilityImpact rows for the 3 FinOps use cases if they
are not already present (these live in the frameworks DB).

Run inside Docker:
    docker compose exec app python scripts/seed_finops_assessments.py

Pass --clean to remove and re-seed.
"""
from __future__ import annotations

import io
import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import dotenv_values as _dv
    for _k, _v in _dv(os.path.join(ROOT, ".env")).items():
        if _v is not None:
            os.environ[_k] = _v
except ImportError:
    pass

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

# ── Human-readable capability names (DB stores codes like FO-UUC-01) ──────────
FINOPS_CAP_NAMES = {
    426: "Data Ingestion & Billing Integration",
    427: "Cost Allocation & Chargeback",
    428: "Showback & Cost Reporting",
    429: "Usage & Cost Visibility",
    430: "Unit Economics & Cost Per Service",
    431: "Business Value Mapping",
    432: "FinOps KPIs & Benchmarking",
    433: "Budgeting & Forecasting",
    434: "Cloud Investment Justification",
    435: "Rightsizing & Waste Elimination",
    436: "Commitment-Based Discounts",
    437: "Workload Scheduling & Autoscaling",
    438: "Architecture Optimisation for Cost",
    439: "Licence & Software Cost Management",
    440: "FinOps Operating Model",
    441: "FinOps Governance & Policy",
    442: "Cloud Cost Culture",
    443: "Anomaly Detection & Alerting",
    444: "FinOps Tooling & Platform",
    445: "Vendor & Contract Management",
    446: "Multi-Cloud Cost Management",
}

# Subdomain each cap belongs to (for display)
FINOPS_CAP_SUBDOMAIN = {
    426: "Understand Usage & Cost", 427: "Understand Usage & Cost",
    428: "Understand Usage & Cost", 429: "Understand Usage & Cost",
    430: "Quantify Business Value",  431: "Quantify Business Value",
    432: "Quantify Business Value",  433: "Quantify Business Value",
    434: "Quantify Business Value",
    435: "Optimize Usage & Cost",    436: "Optimize Usage & Cost",
    437: "Optimize Usage & Cost",    438: "Optimize Usage & Cost",
    439: "Optimize Usage & Cost",
    440: "Manage the FinOps Practice", 441: "Manage the FinOps Practice",
    442: "Manage the FinOps Practice", 443: "Manage the FinOps Practice",
    444: "Manage the FinOps Practice", 445: "Manage the FinOps Practice",
    446: "Manage the FinOps Practice",
}

# ── Use-case capability impact definitions (to seed into Next_UseCaseCapabilityImpact) ─
# impact_weight: 5=Core, 3-4=Upstream, 1-2=Downstream  maturity_target: 1-5
FINOPS_USECASE_CAPS = {
    # UC 41 — Cloud Cost Baseline Assessment
    41: [
        # Core — must-have for establishing cost visibility
        {"cap_id": 426, "impact_weight": 5, "maturity_target": 3},  # Data Ingestion
        {"cap_id": 427, "impact_weight": 5, "maturity_target": 3},  # Cost Allocation
        {"cap_id": 428, "impact_weight": 4, "maturity_target": 3},  # Showback
        {"cap_id": 429, "impact_weight": 4, "maturity_target": 3},  # Visibility
        # Upstream — enablers for a baseline
        {"cap_id": 440, "impact_weight": 3, "maturity_target": 3},  # FinOps Op Model
        {"cap_id": 444, "impact_weight": 3, "maturity_target": 3},  # Tooling
        {"cap_id": 433, "impact_weight": 3, "maturity_target": 2},  # Budgeting
        {"cap_id": 443, "impact_weight": 2, "maturity_target": 2},  # Anomaly Detection
        # Downstream — value-adds once baseline is established
        {"cap_id": 435, "impact_weight": 2, "maturity_target": 2},  # Rightsizing
        {"cap_id": 432, "impact_weight": 1, "maturity_target": 2},  # KPIs
    ],
    # UC 42 — Cloud Optimisation Focus
    42: [
        # Core — direct levers for cost reduction
        {"cap_id": 435, "impact_weight": 5, "maturity_target": 3},  # Rightsizing
        {"cap_id": 436, "impact_weight": 5, "maturity_target": 3},  # Commitments
        {"cap_id": 437, "impact_weight": 4, "maturity_target": 3},  # Scheduling
        {"cap_id": 438, "impact_weight": 4, "maturity_target": 3},  # Architecture
        # Upstream — needed to measure and govern optimisation
        {"cap_id": 439, "impact_weight": 3, "maturity_target": 3},  # Licence
        {"cap_id": 426, "impact_weight": 3, "maturity_target": 3},  # Data Ingestion
        {"cap_id": 427, "impact_weight": 3, "maturity_target": 3},  # Cost Allocation
        {"cap_id": 429, "impact_weight": 2, "maturity_target": 3},  # Visibility
        # Downstream — value metrics
        {"cap_id": 443, "impact_weight": 2, "maturity_target": 2},  # Anomaly Detection
        {"cap_id": 430, "impact_weight": 1, "maturity_target": 2},  # Unit Economics
    ],
    # UC 43 — FinOps Practice Maturity
    43: [
        # Core — organisational and governance foundations
        {"cap_id": 440, "impact_weight": 5, "maturity_target": 3},  # FinOps Op Model
        {"cap_id": 441, "impact_weight": 5, "maturity_target": 3},  # Governance
        {"cap_id": 442, "impact_weight": 4, "maturity_target": 3},  # Culture
        {"cap_id": 444, "impact_weight": 4, "maturity_target": 3},  # Tooling
        # Upstream — operational capabilities
        {"cap_id": 426, "impact_weight": 3, "maturity_target": 3},  # Data Ingestion
        {"cap_id": 427, "impact_weight": 3, "maturity_target": 3},  # Cost Allocation
        {"cap_id": 435, "impact_weight": 3, "maturity_target": 3},  # Rightsizing
        {"cap_id": 430, "impact_weight": 2, "maturity_target": 3},  # Unit Economics
        {"cap_id": 433, "impact_weight": 2, "maturity_target": 3},  # Budgeting
        {"cap_id": 443, "impact_weight": 2, "maturity_target": 2},  # Anomaly Detection
        # Downstream — advanced / scale capabilities
        {"cap_id": 445, "impact_weight": 1, "maturity_target": 2},  # Vendor Mgmt
        {"cap_id": 446, "impact_weight": 1, "maturity_target": 2},  # Multi-Cloud
    ],
}

# ── Assessment specs (5 clients, 5 phases) ─────────────────────────────────────
CONSULTANT = "vrauch"

ASSESSMENTS = [
    {
        # Phase 1: In Progress — responses captured, step 5 not yet run
        "client_name":      "Wolters Kluwer NV",
        "client_industry":  "Financial Services",
        "client_sector":    "Enterprise Software",
        "client_country":   "Netherlands",
        "engagement_name":  "Cloud Financial Management Baseline 2026",
        "use_case_name":    "Cloud Cost Baseline Assessment",
        "usecase_id":       41,
        "assessment_mode":  "predefined",
        "q_type":           "maturity_1_5",
        "base_score":       1.5,
        "score_std":        0.4,
        "days_ago":         14,
        "phase":            "in_progress",
        "intent_text": (
            "Wolters Kluwer has migrated approximately 55% of workloads to cloud over the past 18 months "
            "but lacks a centralised view of cloud expenditure. Finance and engineering teams are operating "
            "with separate cost views. The objective is to establish a FinOps baseline — consistent cost "
            "allocation, tagging standards, and a shared dashboard — to create the foundation for "
            "optimisation and governance in FY2026."
        ),
    },
    {
        # Phase 2: Findings saved, no narrative (step 5 partially complete)
        "client_name":      "Marks & Spencer Group PLC",
        "client_industry":  "Retail",
        "client_sector":    "Omnichannel Retail",
        "client_country":   "United Kingdom",
        "engagement_name":  "Cloud Spend Optimisation Review",
        "use_case_name":    "Cloud Optimisation Focus",
        "usecase_id":       42,
        "assessment_mode":  "predefined",
        "q_type":           "yes_no_evidence",
        "base_score":       2.0,
        "score_std":        0.5,
        "days_ago":         10,
        "phase":            "findings_no_narrative",
        "intent_text": (
            "M&S has seen cloud costs grow 40% year-on-year, outpacing revenue growth. Commitments are "
            "ad hoc and largely unmanaged. Engineering teams have autonomy to provision resources without "
            "cost accountability. The focus is on identifying the highest-ROI optimisation levers — "
            "rightsizing, reserved instance coverage, and scheduling — and building a sustainable cost "
            "governance model."
        ),
    },
    {
        # Phase 3: Findings + executive narrative, no recommendations
        "client_name":      "Brambles Limited",
        "client_industry":  "Logistics",
        "client_sector":    "Supply Chain & Pooling",
        "client_country":   "Australia",
        "engagement_name":  "FinOps Practice Maturity Assessment",
        "use_case_name":    "FinOps Practice Maturity",
        "usecase_id":       43,
        "assessment_mode":  "predefined",
        "q_type":           "free_text",
        "base_score":       2.5,
        "score_std":        0.45,
        "days_ago":         7,
        "phase":            "findings_with_narrative",
        "intent_text": (
            "Brambles operates CHEP and IFCO across 60+ countries and has an established FinOps team "
            "of three practitioners. Cost visibility is reasonable but the practice is engineer-led "
            "and lacks executive sponsorship. The goal is to assess organisational maturity across all "
            "four FinOps domains and build a structured improvement roadmap that elevates the practice "
            "from reactive to proactive, with measurable business value outcomes."
        ),
    },
    {
        # Phase 4: Complete — findings + narrative + recommendations
        "client_name":      "Grab Holdings Inc",
        "client_industry":  "Technology",
        "client_sector":    "Super-App / Platform",
        "client_country":   "Singapore",
        "engagement_name":  "FinOps Baseline & Governance Programme",
        "use_case_name":    "Cloud Cost Baseline Assessment",
        "usecase_id":       41,
        "assessment_mode":  "predefined",
        "q_type":           "mixed",
        "base_score":       1.8,
        "score_std":        0.55,
        "days_ago":         5,
        "phase":            "complete_with_recs",
        "intent_text": (
            "Grab's engineering teams operate across AWS, GCP, and Azure with minimal centralised "
            "governance. Cloud spend has become a board-level concern following a 60% increase in "
            "annual cloud costs. Tagging compliance is below 30%. The objective is to assess the "
            "baseline FinOps posture, identify the critical gaps in cost visibility and allocation, "
            "and produce a prioritised recommendations set to establish a FinOps function with "
            "clear ownership and accountability."
        ),
    },
    {
        # Phase 5: Archived — complete with recommendations
        "client_name":      "Fortescue Metals Group",
        "client_industry":  "Mining",
        "client_sector":    "Iron Ore & Green Energy",
        "client_country":   "Australia",
        "engagement_name":  "Cloud Cost Optimisation Engagement",
        "use_case_name":    "Cloud Optimisation Focus",
        "usecase_id":       42,
        "assessment_mode":  "predefined",
        "q_type":           "maturity_1_5",
        "base_score":       2.2,
        "score_std":        0.5,
        "days_ago":         21,
        "phase":            "archived",
        "intent_text": (
            "Fortescue operates a hybrid cloud estate supporting mine operations, logistics, and its "
            "FFI green energy division. Cloud costs are growing but hard to attribute — multiple "
            "accounts lack tagging and commitment coverage is under 20%. The engagement scope is to "
            "assess the current optimisation posture, identify wasted spend (rightsizing, idle "
            "resources, over-committed licences) and establish governance foundations to sustain "
            "ongoing optimisation."
        ),
    },
]

# ── FinOps domain target (all capabilities target Walk = 3) ───────────────────
FINOPS_TARGET = 3

# ── Question banks (3 questions per capability, keyed by subdomain) ───────────
SUBDOMAIN_QUESTIONS = {
    "Understand Usage & Cost": [
        "How completely and accurately does {cap} capture all cloud cost and usage data across your estate?",
        "To what extent is {cap} automated, with data available in near real-time to all stakeholders?",
        "How well does {cap} support consistent attribution of costs to teams, products, and business units?",
        "How effectively does {cap} enable proactive identification of cost anomalies and unexpected spend?",
        "To what degree is {cap} integrated with your financial systems and budgeting processes?",
        "How consistently are the outputs of {cap} used to inform engineering and product decisions?",
    ],
    "Quantify Business Value": [
        "How clearly does {cap} connect cloud investment to measurable business and customer outcomes?",
        "To what extent does {cap} enable finance and engineering to speak a common language about cloud value?",
        "How effectively does {cap} support executive-level reporting on cloud ROI and efficiency trends?",
        "How well does {cap} integrate with strategic planning, OKR frameworks, and investment decisions?",
        "To what degree does {cap} enable showback or chargeback that drives accountability at team level?",
        "How consistently is {cap} applied across all cloud service types and business domains?",
    ],
    "Optimize Usage & Cost": [
        "How systematically does {cap} identify and act on cost reduction opportunities across your estate?",
        "To what extent is {cap} automated, with savings realised without requiring manual engineering effort?",
        "How well does {cap} balance cost reduction with performance, reliability, and security requirements?",
        "How consistently is {cap} applied across all cloud providers, regions, and account structures?",
        "How effectively does {cap} deliver measurable, sustained savings rather than one-off reductions?",
        "To what degree does {cap} leverage contractual, architectural, and operational levers together?",
    ],
    "Manage the FinOps Practice": [
        "How mature and sustainable is {cap} as an organisational capability with clear ownership?",
        "To what extent does {cap} drive cross-functional collaboration between finance, engineering, and product?",
        "How effectively does {cap} embed FinOps principles into day-to-day engineering and delivery practices?",
        "How well does {cap} scale with the growth of your cloud estate and organisational complexity?",
        "To what degree does {cap} enable continuous improvement rather than periodic, project-based activity?",
        "How consistently is {cap} measured and reported against agreed targets and industry benchmarks?",
    ],
}
DEFAULT_FINOPS_QUESTIONS = [
    "How well-defined and consistently applied is your {cap} capability?",
    "To what extent does {cap} deliver measurable business value for the organisation?",
    "How effectively does {cap} integrate with adjacent FinOps practices and financial processes?",
    "How consistently is {cap} adopted across teams, cloud providers, and business units?",
    "To what degree does {cap} leverage automation and data to drive continuous improvement?",
    "How well does {cap} support accountability and decision-making at the team and executive level?",
]

# ── Free-text answer bank (by integer score 1–5) ──────────────────────────────
FREE_TEXT_BY_SCORE = {
    1: [
        "No formal process in place. Cloud costs are reviewed manually and infrequently, with no "
        "consistent methodology or tooling. Visibility is limited to billing summaries.",
        "Ad hoc activity only. There is no defined ownership and no regular cadence for this capability. "
        "Output quality varies significantly between individuals.",
        "This capability is largely absent. Decisions are made without data and the organisation has "
        "limited awareness of what good looks like in this area.",
    ],
    2: [
        "A basic approach exists but adoption is inconsistent. Some teams follow a loose process but "
        "there is no central governance, tooling, or regular reporting cycle.",
        "Initial steps have been taken but the capability is immature. Coverage is partial and "
        "the output quality does not yet meet the needs of finance or senior stakeholders.",
        "There is awareness of the need for this capability but implementation is patchy. "
        "Manual effort is high and outcomes are not reliably tracked or reported.",
    ],
    3: [
        "A defined process is in place and broadly followed across key teams. Regular reporting "
        "exists and ownership is clear, though automation and coverage are not yet complete.",
        "The capability is operational and delivering value. Core processes are documented and "
        "outcomes are tracked, with improvement activity underway to address remaining gaps.",
        "Practices are standardised and largely consistent. Stakeholders have visibility of "
        "outputs and the capability supports monthly financial review cycles.",
    ],
    4: [
        "The capability is mature and data-driven. Automation is extensive, coverage is high, and "
        "insights are regularly used to inform engineering and business decisions.",
        "A well-embedded, proactively managed capability with clear KPIs, real-time data, and a "
        "continuous improvement cycle supported by dedicated tooling and cross-functional engagement.",
        "Strong practices with broad adoption. The organisation benchmarks this capability against "
        "peers and consistently performs in the upper quartile on key FinOps metrics.",
    ],
    5: [
        "Best-in-class practice. The capability is fully automated, continuously optimised, and "
        "deeply integrated into engineering, finance, and product workflows organisation-wide.",
        "Industry-leading maturity. This capability is a recognised strength and contributes directly "
        "to competitive cost efficiency and strategic agility.",
        "Comprehensive and continuously improving. Practices are shared externally and the "
        "organisation is recognised as a FinOps reference case in its industry.",
    ],
}

# ── Industry-specific notes ────────────────────────────────────────────────────
INDUSTRY_NOTES = {
    "Financial Services": [
        "Regulatory constraints (DORA, FCA guidelines) require cloud spend to be traceable to "
        "regulated activities, complicating simple chargeback models.",
        "Internal audit has flagged cloud cost governance as a control gap — remediation is "
        "actively tracked by the CFO office.",
        "Data residency requirements restrict the use of certain cloud-native cost management tools.",
        "Outsourced engineering teams create accountability gaps in the tagging and allocation model.",
    ],
    "Retail": [
        "Seasonal trading peaks create significant cost variability that makes static budgets unreliable.",
        "Multiple brands and trading formats create complexity in cost attribution that a simple "
        "account-level model cannot address.",
        "Engineering teams are measured on delivery velocity, not cost efficiency — incentive "
        "alignment is a significant cultural barrier.",
        "Recent ERP migration has created a period of financial system instability that affects "
        "budget integration.",
    ],
    "Logistics": [
        "Geographically distributed operations across 60+ countries create significant variation in "
        "cloud provider options and cost structures.",
        "Real-time supply chain systems require high availability guarantees that constrain "
        "aggressive rightsizing and scheduling optimisation.",
        "Sustainability commitments require carbon-aware cost management, adding complexity to "
        "standard FinOps tooling.",
    ],
    "Technology": [
        "Multi-cloud architecture (AWS, GCP, Azure) creates fragmented visibility and makes "
        "consolidated reporting technically challenging.",
        "Rapid engineering team growth means tagging compliance erodes faster than it can be "
        "enforced — tooling automation is essential.",
        "Microservices architecture with thousands of services makes workload-level cost attribution "
        "extremely granular and difficult to maintain.",
        "Platform engineering owns infrastructure provisioning but product teams hold cost budgets — "
        "the accountability model is misaligned.",
    ],
    "Mining": [
        "Hybrid cloud estate (on-premises + cloud) means total cost of ownership comparisons "
        "require visibility across both environments.",
        "Remote site connectivity constraints affect real-time monitoring and anomaly detection "
        "capabilities at the edge.",
        "FFI green energy division has distinct cloud cost drivers that require separate "
        "cost allocation treatment from core mining operations.",
        "Significant CapEx mindset in the organisation creates resistance to OpEx-oriented "
        "cloud financial management practices.",
    ],
    "default": [
        "Legacy financial systems do not easily consume cloud cost allocation data, requiring "
        "manual reconciliation steps.",
        "Engineering and finance teams have not historically collaborated on cloud spend, creating "
        "a cultural barrier to FinOps adoption.",
        "Tagging compliance is below target across several cloud accounts, limiting the accuracy "
        "of cost attribution models.",
        "Recent cloud provider contract renewal provides an opportunity to renegotiate commitment "
        "levels based on assessment findings.",
    ],
}

# ── Recommended actions per subdomain ─────────────────────────────────────────
RECOMMENDED_ACTIONS = {
    "Understand Usage & Cost": [
        "Implement an automated cost ingestion pipeline covering all cloud accounts, providers, "
        "and SaaS subscriptions with daily refresh and data validation",
        "Define and enforce an organisation-wide tagging taxonomy with automated compliance "
        "enforcement via policy-as-code and a tagging coverage dashboard",
        "Deploy a centralised cost visibility platform (e.g., native cloud tools or third-party) "
        "with team, product, and environment-level drilldown",
        "Establish a monthly cost review cadence with standardised reports distributed to "
        "engineering leads, finance, and product owners",
        "Build anomaly detection and budget alert automation to surface unexpected cost spikes "
        "within 24 hours of occurrence",
    ],
    "Quantify Business Value": [
        "Define unit cost metrics (cost per transaction, cost per active user, cost per API call) "
        "for all material services and track trends monthly",
        "Map cloud investment to strategic business outcomes by linking cost centre data to "
        "product P&L and OKR frameworks",
        "Implement a cloud ROI reporting framework with quarterly board-level summaries of "
        "cloud efficiency, waste reduction, and value-add metrics",
        "Build a FinOps forecasting model that integrates engineering roadmap inputs with "
        "committed spend and demand forecasts",
        "Establish benchmarks for key FinOps KPIs (unit cost, waste ratio, commitment coverage) "
        "and report performance against industry peers quarterly",
    ],
    "Optimize Usage & Cost": [
        "Conduct an organisation-wide rightsizing analysis and implement auto-remediation for "
        "idle and over-provisioned resources with a 30-day review cycle",
        "Implement a reserved instance and savings plan strategy with a target of ≥70% commitment "
        "coverage for baseline workloads, reviewed quarterly",
        "Define workload scheduling policies for non-production environments with automated "
        "start/stop schedules targeting ≥30% cost reduction in dev/test",
        "Establish an architecture optimisation review process to identify cloud-native "
        "re-architecture opportunities delivering sustained cost savings",
        "Conduct a software licence audit across all cloud-delivered services and renegotiate "
        "vendor contracts based on actual consumption data",
    ],
    "Manage the FinOps Practice": [
        "Establish a FinOps Centre of Excellence with dedicated practitioners, cross-functional "
        "representation, and a formal operating model",
        "Define and implement FinOps governance policies including tagging standards, cost "
        "allocation rules, budget accountability, and escalation thresholds",
        "Launch a Cloud Cost Culture programme to embed FinOps principles in engineering onboarding, "
        "team KPIs, and architecture design reviews",
        "Deploy an enterprise FinOps tooling platform (native or third-party) with self-service "
        "dashboards for all teams and automated anomaly alerting",
        "Establish a cloud vendor management practice with structured EDP/MOU negotiation cycles, "
        "consumption tracking, and commitment optimisation reviews",
    ],
}

# ── Success indicators per subdomain ──────────────────────────────────────────
SUCCESS_INDICATORS = {
    "Understand Usage & Cost": [
        "Tagging compliance reaches ≥90% of all cloud resources within 90 days",
        "100% of cloud accounts feeding into the cost visibility platform within 60 days",
        "Cost anomalies detected and alerted within 24 hours for ≥95% of material spend events",
    ],
    "Quantify Business Value": [
        "Unit cost metrics defined and tracked for ≥80% of production services within 6 months",
        "Cloud ROI reporting delivered to board within 90 days and maintained quarterly",
        "FinOps KPI dashboard operational with monthly reporting to leadership within 60 days",
    ],
    "Optimize Usage & Cost": [
        "Commitment coverage reaches ≥70% of baseline workloads within 6 months",
        "Non-production scheduling delivers ≥25% cost reduction within 90 days",
        "Rightsizing recommendations actioned within 30 days with ≥15% waste reduction in 6 months",
    ],
    "Manage the FinOps Practice": [
        "FinOps Centre of Excellence operational with defined charter and team within 90 days",
        "All engineering teams have access to self-service cost dashboards within 60 days",
        "Cloud cost culture programme launched with ≥80% of engineering teams onboarded in 6 months",
    ],
}

# ── Enabling dependencies per subdomain ───────────────────────────────────────
ENABLING_DEPS = {
    "Understand Usage & Cost": ["Cloud Account Governance", "Tagging Policy Enforcement"],
    "Quantify Business Value":  ["Cost Allocation & Chargeback", "Financial Reporting Integration"],
    "Optimize Usage & Cost":    ["Data Ingestion & Billing Integration", "FinOps Governance & Policy"],
    "Manage the FinOps Practice": ["Executive Sponsorship", "Cross-Functional FinOps Champion Network"],
}

# ── Executive narrative templates (per use case) ──────────────────────────────
NARRATIVE_TEMPLATES = {
    41: (
        "{client} engaged Meridant to conduct a Cloud Cost Baseline Assessment across {cap_count} "
        "FinOps capabilities spanning all four FinOps Foundation domains. The assessment reveals an "
        "overall maturity score of {score:.1f} out of 5.0, indicating a {maturity_label} level of "
        "FinOps capability — consistent with an organisation in the early stages of its cloud "
        "financial management journey. The most significant gaps were identified in {weak_cap}, "
        "where cost data quality and attribution are insufficient to support reliable financial "
        "reporting. Strengths were observed in {strong_cap}, where initial tooling investments "
        "are beginning to deliver value. As a {industry} organisation operating in {country}, "
        "regulatory obligations and organisational complexity add additional constraints to the "
        "speed of FinOps maturity improvement. {p1_count} P1-priority recommendations have been "
        "identified, representing the critical investments required to establish a reliable cost "
        "visibility and allocation baseline within the next 90 days."
    ),
    42: (
        "{client} engaged Meridant to assess its Cloud Optimisation posture across {cap_count} "
        "capabilities. The overall maturity score of {score:.1f} indicates a {maturity_label} "
        "optimisation capability, with significant untapped savings potential identified across "
        "rightsizing, commitment strategies, and workload scheduling. The assessment highlights "
        "{weak_cap} as the primary gap domain where optimisation activity is either absent or "
        "ad hoc. {strong_cap} demonstrates relative strength where some structured practices are "
        "in place. For a {industry} organisation in {country}, the combination of variable demand "
        "patterns and multi-provider complexity creates both challenges and opportunities for "
        "cost optimisation. {p1_count} P1-priority recommendations target the highest-ROI "
        "optimisation levers, with an estimated 20–35% reduction in avoidable cloud spend "
        "achievable within 12 months."
    ),
    43: (
        "{client} engaged Meridant to undertake a comprehensive FinOps Practice Maturity Assessment "
        "across {cap_count} capabilities covering all four FinOps Foundation domains. The overall "
        "maturity score of {score:.1f} out of 5.0 reflects a {maturity_label} FinOps practice — "
        "one that has established foundations but has not yet achieved the cross-functional "
        "integration and automation required for a sustainable, self-improving practice. "
        "{strong_cap} is a relative area of strength, while {weak_cap} represents the most "
        "material gap in the current operating model. The {industry} context in {country} creates "
        "specific organisational dynamics that influence the pace and design of FinOps adoption. "
        "{p1_count} P1-priority recommendations focus on building the governance, culture, and "
        "tooling foundations that will enable the practice to operate at Walk maturity "
        "consistently across all domains within 12 months."
    ),
    "default": (
        "{client} engaged Meridant to assess FinOps capability maturity across {cap_count} "
        "capabilities. The overall score of {score:.1f} out of 5.0 indicates a {maturity_label} "
        "FinOps baseline. {p1_count} P1-priority recommendations have been identified as the "
        "critical path to closing the most material gaps. The {industry} context in {country} "
        "shapes the specific approach required to achieve sustainable improvement."
    ),
}

MATURITY_LABELS = {1: "Crawl", 2: "Crawl", 3: "Walk", 4: "Run", 5: "Run"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _maturity_label(score: float) -> str:
    return MATURITY_LABELS.get(max(1, min(5, round(score))), "Walk")


def _risk(score: float) -> str:
    if score is None:
        return ""
    if score < 2:
        return "🔴 High"
    if score < 3:
        return "🟡 Medium"
    return "🟢 Low"


def _priority_tier(gap: float, role: str) -> str:
    if gap >= 2.0 or (role == "Core" and gap >= 1.5):
        return "P1"
    if gap >= 1.0:
        return "P2"
    return "P3"


def _effort_estimate(gap: float) -> str:
    if gap >= 2.0:
        return "High Effort"
    if gap >= 1.0:
        return "Medium"
    return "Quick Win"


def _clamp_score(s: float) -> float:
    return max(1.0, min(5.0, round(s * 2) / 2))


def _yn_answer(score: float) -> tuple[str, float]:
    if score >= 2.7:
        return "Yes", 3.0
    if score >= 1.5:
        return "Partial", 2.0
    return "No", 1.0


def _get_questions(subdomain: str, cap_name: str, cap_id: int) -> list[str]:
    bank = SUBDOMAIN_QUESTIONS.get(subdomain, DEFAULT_FINOPS_QUESTIONS)
    offset = cap_id % max(1, len(bank) - 2)
    qs = bank[offset:offset + 3]
    if len(qs) < 3:
        qs = qs + bank[:3 - len(qs)]
    return [q.format(cap=cap_name) for q in qs]


def _get_notes(industry: str, rng: random.Random, probability: float = 0.3) -> str:
    if rng.random() > probability:
        return ""
    pool = INDUSTRY_NOTES.get(industry, INDUSTRY_NOTES["default"])
    return rng.choice(pool)


def _get_cap_role(impact_weight: int) -> str:
    if impact_weight >= 4:
        return "Core"
    if impact_weight >= 2:
        return "Upstream"
    return "Downstream"


def _build_narrative(spec: dict, cap_count: int, avg_score: float,
                     p1_count: int, cap_scores: dict, all_caps: list) -> str:
    uc_id = spec["usecase_id"]
    template = NARRATIVE_TEMPLATES.get(uc_id, NARRATIVE_TEMPLATES["default"])

    # Find strongest and weakest by avg score
    cap_avgs = [(c["cap_name"], cap_scores[c["cap_id"]]) for c in all_caps]
    cap_avgs.sort(key=lambda x: x[1])
    weak_cap   = cap_avgs[0][0]   if cap_avgs else "core capabilities"
    strong_cap = cap_avgs[-1][0]  if cap_avgs else "operational practices"

    return template.format(
        client=spec["client_name"],
        cap_count=cap_count,
        score=avg_score,
        maturity_label=_maturity_label(avg_score),
        weak_cap=weak_cap,
        strong_cap=strong_cap,
        industry=spec["client_industry"],
        country=spec["client_country"],
        p1_count=p1_count,
    )


# ── Seed use case capability impacts (frameworks DB) ──────────────────────────

def _seed_usecase_impacts(cur: sqlite3.Cursor) -> None:
    """Insert impact rows for FinOps use cases if not already present."""
    for uc_id, caps in FINOPS_USECASE_CAPS.items():
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM Next_UseCaseCapabilityImpact WHERE usecase_id = ?",
            [uc_id]
        )
        row = cur.fetchone()
        if row and row["cnt"] > 0:
            print(f"  SKIP  Use case {uc_id} impacts already seeded ({row['cnt']} rows)")
            continue
        rows = [(uc_id, c["cap_id"], c["impact_weight"], c["maturity_target"]) for c in caps]
        cur.executemany(
            "INSERT INTO Next_UseCaseCapabilityImpact (usecase_id, capability_id, impact_weight, maturity_target) "
            "VALUES (?, ?, ?, ?)",
            rows
        )
        print(f"  Seeded {len(rows)} impact rows for use case {uc_id}")


# ── Core seed function ────────────────────────────────────────────────────────

def seed_assessment(conn: sqlite3.Connection, spec: dict, rng: random.Random) -> int | None:
    cur = conn.cursor()

    # Idempotency check
    cur.execute("""
        SELECT a.id FROM Assessment a
        JOIN Client c ON a.client_id = c.id
        WHERE c.client_name = ? AND a.use_case_name = ?
        LIMIT 1
    """, [spec["client_name"], spec["use_case_name"]])
    if cur.fetchone():
        print(f"  SKIP  {spec['client_name']} / {spec['use_case_name']} (already exists)")
        return None

    now         = datetime.now()
    created_at  = (now - timedelta(days=spec["days_ago"])).isoformat()
    phase       = spec["phase"]
    is_complete = phase in ("findings_no_narrative", "findings_with_narrative",
                            "complete_with_recs", "archived")
    completed_at = (now - timedelta(days=spec["days_ago"] - 1)).isoformat() if is_complete else None

    # ── 1. Client ─────────────────────────────────────────────────────────
    cur.execute("SELECT id FROM Client WHERE client_name = ? LIMIT 1", [spec["client_name"]])
    row = cur.fetchone()
    if row:
        client_id = row["id"]
    else:
        cur.execute("""
            INSERT INTO Client (client_name, industry, sector, country, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, [spec["client_name"], spec["client_industry"],
              spec["client_sector"], spec["client_country"], created_at])
        client_id = cur.lastrowid

    # ── 2. Load capabilities from impact table ────────────────────────────
    cur.execute("""
        SELECT nc.id   AS cap_id,
               nc.capability_name AS cap_code,
               nsd.subdomain_name,
               nd.domain_name,
               uci.impact_weight,
               COALESCE(uci.maturity_target, 3) AS tgt
        FROM   Next_UseCaseCapabilityImpact uci
        JOIN   Next_Capability   nc  ON nc.id  = uci.capability_id
        JOIN   Next_SubDomain    nsd ON nsd.id = nc.subdomain_id
        JOIN   Next_Domain       nd  ON nd.id  = nsd.domain_id
        WHERE  uci.usecase_id = ?
        ORDER  BY nd.id, nc.id
    """, [spec["usecase_id"]])
    raw_caps = cur.fetchall()

    all_caps = []
    for r in raw_caps:
        cap_id = r["cap_id"]
        all_caps.append({
            "cap_id":        cap_id,
            "cap_name":      FINOPS_CAP_NAMES.get(cap_id, r["cap_code"]),
            "cap_code":      r["cap_code"],
            "subdomain":     r["subdomain_name"],
            "domain_name":   r["domain_name"],
            "role":          _get_cap_role(r["impact_weight"]),
            "impact_weight": r["impact_weight"],
            "tgt":           r["tgt"],
        })

    if not all_caps:
        print(f"  ERROR  No capabilities found for use case {spec['usecase_id']} — "
              "did you seed the impact rows?")
        return None

    # Per-cap scores
    cap_scores: dict[int, float] = {}
    for cap in all_caps:
        cap_scores[cap["cap_id"]] = _clamp_score(
            rng.gauss(spec["base_score"], spec["score_std"])
        )

    # ── 3. Assessment header ──────────────────────────────────────────────
    overall = round(sum(cap_scores.values()) / len(cap_scores), 2) if cap_scores else 0.0
    status  = "in_progress" if phase == "in_progress" else \
              "archived"    if phase == "archived" else "complete"

    cur.execute("""
        INSERT INTO Assessment
            (client_id, engagement_name, use_case_name, intent_text,
             usecase_id, assessment_mode, overall_score, status,
             created_at, completed_at, framework_id, consultant_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 3, ?)
    """, [
        client_id, spec["engagement_name"], spec["use_case_name"], spec["intent_text"],
        spec["usecase_id"], spec["assessment_mode"],
        overall if is_complete else None,
        status, created_at, completed_at, CONSULTANT,
    ])
    assessment_id = cur.lastrowid

    # ── 4. AssessmentCapability ───────────────────────────────────────────
    cap_rows = [(
        assessment_id,
        cap["cap_id"],
        cap["cap_name"],
        cap["domain_name"],
        cap["subdomain"],
        cap["role"],
        cap_scores[cap["cap_id"]],
        f"Scored {cap_scores[cap['cap_id']]:.1f}/5.0 based on assessment responses.",
        FINOPS_TARGET,
    ) for cap in all_caps]

    cur.executemany("""
        INSERT INTO AssessmentCapability
            (assessment_id, capability_id, capability_name, domain_name, subdomain_name,
             capability_role, ai_score, rationale, target_maturity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, cap_rows)

    # ── 5. AssessmentResponse ─────────────────────────────────────────────
    q_type = spec["q_type"]
    response_rows = []

    for idx, cap in enumerate(all_caps):
        cid   = cap["cap_id"]
        score = cap_scores[cid]
        questions = _get_questions(cap["subdomain"], cap["cap_name"], cid)

        for i, question in enumerate(questions):
            q_score = _clamp_score(score + rng.gauss(0, 0.25))

            if q_type == "mixed":
                rt = ["maturity_1_5", "yes_no_evidence", "free_text"][idx % 3]
            else:
                rt = q_type

            if rt == "maturity_1_5":
                answer       = None
                stored_score = q_score
            elif rt == "yes_no_evidence":
                answer, stored_score = _yn_answer(q_score)
            else:
                int_s  = max(1, min(5, round(q_score)))
                pool   = FREE_TEXT_BY_SCORE[int_s]
                answer = pool[cid % len(pool)]
                stored_score = q_score

            notes = _get_notes(spec["client_industry"], rng, 0.25) if i == 0 else ""

            response_rows.append((
                assessment_id, cid, cap["cap_name"], cap["domain_name"], cap["subdomain"],
                cap["role"], question, rt,
                round(stored_score, 1), answer, notes,
            ))

    cur.executemany("""
        INSERT INTO AssessmentResponse
            (assessment_id, capability_id, capability_name, domain, subdomain,
             capability_role, question, response_type, score, answer, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, response_rows)

    # ── 6. Findings (phases 2–5) ──────────────────────────────────────────
    if phase != "in_progress":
        # Domain aggregate (only one domain for FinOps — "FinOps Framework")
        domain_agg: dict[str, list[float]] = {}
        for cap in all_caps:
            domain_agg.setdefault(cap["domain_name"], []).append(cap_scores[cap["cap_id"]])

        finding_rows = []
        for d, scores in domain_agg.items():
            avg_d = round(sum(scores) / len(scores), 2)
            gap_d = round(max(0.0, FINOPS_TARGET - avg_d), 2)
            finding_rows.append((
                assessment_id, "domain",
                d, None, None, None, None,
                avg_d, FINOPS_TARGET, gap_d, _risk(avg_d),
            ))

        for cap in all_caps:
            avg_c = cap_scores[cap["cap_id"]]
            gap_c = round(max(0.0, FINOPS_TARGET - avg_c), 2)
            finding_rows.append((
                assessment_id, "capability",
                cap["domain_name"], cap["cap_id"], cap["cap_name"], cap["role"], cap["subdomain"],
                avg_c, FINOPS_TARGET, gap_c, _risk(avg_c),
            ))

        cur.executemany("""
            INSERT INTO AssessmentFinding
                (assessment_id, finding_type, domain, capability_id, capability_name,
                 capability_role, subdomain, avg_score, target_maturity, gap, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, finding_rows)

        # Update overall score on assessment
        cur.execute(
            "UPDATE Assessment SET overall_score = ? WHERE id = ?",
            [overall, assessment_id]
        )

    # ── 7. Narrative (phases 3–5) ─────────────────────────────────────────
    if phase in ("findings_with_narrative", "complete_with_recs", "archived"):
        gap_caps_all = [
            c for c in all_caps
            if (FINOPS_TARGET - cap_scores[c["cap_id"]]) > 0
        ]
        p1_recs = [
            c for c in gap_caps_all
            if _priority_tier(
                round(max(0.0, FINOPS_TARGET - cap_scores[c["cap_id"]]), 2),
                c["role"]
            ) == "P1"
        ]
        narrative = _build_narrative(
            spec, len(all_caps), overall, len(p1_recs), cap_scores, all_caps
        )
        cur.execute(
            "UPDATE Assessment SET findings_narrative = ? WHERE id = ?",
            [narrative, assessment_id]
        )

    # ── 8. Recommendations (phases 4–5) ───────────────────────────────────
    if phase in ("complete_with_recs", "archived"):
        gap_caps = [
            c for c in all_caps
            if (FINOPS_TARGET - cap_scores[c["cap_id"]]) > 0
        ]
        gap_caps.sort(
            key=lambda c: -(FINOPS_TARGET - cap_scores[c["cap_id"]])
        )
        rec_caps = gap_caps[:8]

        rec_rows = []
        for cap in rec_caps:
            avg  = cap_scores[cap["cap_id"]]
            gap  = round(max(0.0, FINOPS_TARGET - avg), 2)
            tier = _priority_tier(gap, cap["role"])
            eff  = _effort_estimate(gap)
            sub  = cap["subdomain"]

            actions = RECOMMENDED_ACTIONS.get(sub, RECOMMENDED_ACTIONS["Manage the FinOps Practice"])[:4]
            deps    = ENABLING_DEPS.get(sub, ["Cost Allocation", "FinOps Governance"])
            indics  = SUCCESS_INDICATORS.get(sub, ["FinOps KPI dashboard operational within 60 days"])

            narrative = (
                f"{cap['cap_name']} is currently at maturity level {avg:.1f} against a target of "
                f"{FINOPS_TARGET}. This gap of {gap:.1f} is classified as {tier} priority requiring "
                f"{eff.lower()} to close. "
                + (
                    "Current practices are ad hoc with no consistent tooling or ownership."
                    if avg < 2 else
                    "Initial practices are in place but adoption is incomplete and outcomes are not "
                    "reliably measured or reported."
                    if avg < 3 else
                    "Defined practices exist but optimisation and automation opportunities remain "
                    "to reach Walk-level maturity consistently."
                )
            )

            rec_rows.append((
                assessment_id, cap["cap_id"], cap["cap_name"],
                cap["domain_name"], cap["role"],
                round(avg, 2), FINOPS_TARGET, round(gap, 2),
                tier, eff, narrative,
                json.dumps(actions), json.dumps(deps), json.dumps(indics),
                None, datetime.now().isoformat(),
            ))

        cur.executemany("""
            INSERT INTO AssessmentRecommendation
                (assessment_id, capability_id, capability_name, domain, capability_role,
                 current_score, target_maturity, gap, priority_tier, effort_estimate,
                 narrative, recommended_actions, enabling_dependencies, success_indicators,
                 hpe_relevance, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rec_rows)

    conn.commit()

    print(f"  -> Assessment #{assessment_id}: {spec['client_name']} / {spec['use_case_name']}")
    print(f"     Phase={phase}  Caps={len(all_caps)}  Responses={len(response_rows)}  "
          f"Overall={overall:.2f}  Status={status}")
    return assessment_id


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    clean = "--clean" in sys.argv

    conn = sqlite3.connect(FRAMEWORKS_PATH)
    conn.execute(f'ATTACH DATABASE "{ASSESSMENTS_PATH}" AS assessments')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure optional Assessment columns exist
    for col in ("findings_narrative TEXT", "usecase_id INTEGER",
                "assessment_mode TEXT", "framework_id INTEGER"):
        try:
            cur.execute(f"ALTER TABLE Assessment ADD COLUMN {col}")
        except Exception:
            pass

    # Ensure AssessmentRecommendation table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS AssessmentRecommendation (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id         INTEGER NOT NULL,
            capability_id         INTEGER,
            capability_name       TEXT NOT NULL,
            domain                TEXT,
            capability_role       TEXT,
            current_score         REAL,
            target_maturity       INTEGER,
            gap                   REAL,
            priority_tier         TEXT,
            effort_estimate       TEXT,
            recommended_actions   TEXT,
            enabling_dependencies TEXT,
            success_indicators    TEXT,
            hpe_relevance         TEXT,
            narrative             TEXT,
            created_at            TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (assessment_id) REFERENCES Assessment(id)
        )
    """)
    conn.commit()

    # --clean: remove existing FinOps seeded assessments
    if clean:
        client_names = [s["client_name"] for s in ASSESSMENTS]
        print(f"--clean: removing existing assessments for {len(client_names)} clients...")
        for client_name in client_names:
            cur.execute("""
                SELECT a.id FROM Assessment a
                JOIN Client c ON a.client_id = c.id
                WHERE c.client_name = ?
            """, [client_name])
            for row in cur.fetchall():
                aid = row["id"]
                for tbl in ("AssessmentRecommendation", "AssessmentFinding",
                            "AssessmentResponse", "AssessmentCapability"):
                    cur.execute(f"DELETE FROM {tbl} WHERE assessment_id = ?", [aid])
                cur.execute("DELETE FROM Assessment WHERE id = ?", [aid])
            cur.execute("DELETE FROM Client WHERE client_name = ?", [client_name])
        conn.commit()
        print("  Done.")

    # Seed use case capability impacts first
    print("\nSeeding FinOps use case capability impacts...")
    _seed_usecase_impacts(cur)
    conn.commit()

    # Seed assessments
    rng     = random.Random(99)
    created = 0
    skipped = 0

    for spec in ASSESSMENTS:
        print(f"\n{'='*65}")
        print(f"Assessment: {spec['client_name']} / {spec['use_case_name']}")
        print(f"Phase:      {spec['phase']}")
        aid = seed_assessment(conn, spec, rng)
        if aid is not None:
            created += 1
        else:
            skipped += 1

    print(f"\n{'='*65}")
    print(f"Done. Created={created}  Skipped={skipped}")


if __name__ == "__main__":
    main()

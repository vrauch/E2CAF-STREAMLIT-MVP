# -*- coding: utf-8 -*-
"""
Seed 6 comprehensive test assessments into the E2CAF database.

Each assessment covers 6-9 domains with 5-6 capabilities per domain,
across all question types (maturity_1_5 / yes_no_evidence / free_text / mixed).

Assessments:
  1. Deutsche Bank AG         / General IT Readiness   (maturity_1_5,    9 domains × 6 caps)
  2. Ramsay Health Care       / General IT Readiness   (yes_no_evidence, 9 domains × 6 caps)
  3. Siemens AG               / Operating Model Mod.   (maturity_1_5,    7 domains, all caps)
  4. Qatar National Bank      / AI Readiness           (mixed,           8 domains, all caps)
  5. Norsk Hydro ASA          / General IT Readiness   (free_text,       9 domains × 6 caps)
  6. Singapore Airlines       / Datacenter Transform.  (maturity_1_5,    6 domains, all caps)

Run inside Docker:
    docker compose exec app python scripts/seed_v3_assessments.py

Pass --clean to first delete the previous v2 seed data (IDs 9-14) before inserting.

Idempotent — skips any assessment whose client_name + use_case_name already exists.
"""
from __future__ import annotations

import io
import os
import sys
import sqlite3
import json
import random
from datetime import datetime, timedelta

# ── UTF-8 stdout on Windows ───────────────────────────────────────────────────
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
# Local fallbacks
local_fw = os.path.join(ROOT, "data", "meridant_frameworks.db")
local_as = os.path.join(ROOT, "data", "meridant.db")
if not os.path.exists(FRAMEWORKS_PATH) and os.path.exists(local_fw):
    FRAMEWORKS_PATH = local_fw
if not os.path.exists(ASSESSMENTS_PATH) and os.path.exists(local_as):
    ASSESSMENTS_PATH = local_as

print(f"Using frameworks DB : {FRAMEWORKS_PATH}")
print(f"Using assessments DB: {ASSESSMENTS_PATH}")

# ── Assessment specs ──────────────────────────────────────────────────────────
ASSESSMENTS = [
    {
        "client_name":       "Deutsche Bank AG",
        "client_industry":   "Financial Services",
        "client_sector":     "Banking",
        "client_country":    "Germany",
        "engagement_name":   "Enterprise IT Maturity Assessment 2026",
        "use_case_name":     "General IT Readiness & Maturity Assessment",
        "usecase_id":        31,
        "assessment_mode":   "predefined",
        "q_type":            "maturity_1_5",
        "base_score":        2.1,
        "score_std":         0.6,
        "days_ago":          22,
        "caps_per_domain":   6,
    },
    {
        "client_name":       "Ramsay Health Care",
        "client_industry":   "Healthcare",
        "client_sector":     "Healthcare Services",
        "client_country":    "Australia",
        "engagement_name":   "Digital Readiness Assessment 2026",
        "use_case_name":     "General IT Readiness & Maturity Assessment",
        "usecase_id":        31,
        "assessment_mode":   "predefined",
        "q_type":            "yes_no_evidence",
        "base_score":        2.4,
        "score_std":         0.5,
        "days_ago":          16,
        "caps_per_domain":   6,
    },
    {
        "client_name":       "Siemens AG",
        "client_industry":   "Industrial Manufacturing",
        "client_sector":     "Engineering & Technology",
        "client_country":    "Germany",
        "engagement_name":   "Operating Model Modernization Assessment",
        "use_case_name":     "Operating Model Modernization",
        "usecase_id":        27,
        "assessment_mode":   "predefined",
        "q_type":            "maturity_1_5",
        "base_score":        2.8,
        "score_std":         0.5,
        "days_ago":          12,
        "caps_per_domain":   None,   # all caps
    },
    {
        "client_name":       "Qatar National Bank",
        "client_industry":   "Financial Services",
        "client_sector":     "Banking",
        "client_country":    "Qatar",
        "engagement_name":   "AI Readiness & Governance Assessment",
        "use_case_name":     "AI Readiness & Maturity Assessment",
        "usecase_id":        30,
        "assessment_mode":   "predefined",
        "q_type":            "mixed",   # Core → maturity_1_5, others → yes_no_evidence
        "base_score":        2.2,
        "score_std":         0.7,
        "days_ago":          8,
        "caps_per_domain":   None,
    },
    {
        "client_name":       "Norsk Hydro ASA",
        "client_industry":   "Energy",
        "client_sector":     "Renewables & Industrial",
        "client_country":    "Norway",
        "engagement_name":   "IT Modernisation Maturity Review",
        "use_case_name":     "General IT Readiness & Maturity Assessment",
        "usecase_id":        31,
        "assessment_mode":   "predefined",
        "q_type":            "free_text",
        "base_score":        3.1,
        "score_std":         0.4,
        "days_ago":          5,
        "caps_per_domain":   6,
    },
    {
        "client_name":       "Singapore Airlines",
        "client_industry":   "Aviation",
        "client_sector":     "Air Transport",
        "client_country":    "Singapore",
        "engagement_name":   "Datacentre Transformation Assessment",
        "use_case_name":     "Datacenter Transformation",
        "usecase_id":        32,
        "assessment_mode":   "predefined",
        "q_type":            "maturity_1_5",
        "base_score":        2.6,
        "score_std":         0.5,
        "days_ago":          2,
        "caps_per_domain":   None,
    },
]

# ── Domain target overrides ───────────────────────────────────────────────────
DOMAIN_TARGETS = {
    "Strategy & Governance": 3,
    "Security":               4,
    "People":                 3,
    "Applications":           3,
    "Data":                   3,
    "DevOps":                 3,
    "Innovation":             3,
    "Operations":             3,
    "AI & Cognitive Systems": 3,
    "Intelligent Automation & Operations": 3,
    "Sustainability & Responsible Technology": 3,
    "Experience & Ecosystem Enablement": 3,
}

# ── Question banks (6 questions per domain) ───────────────────────────────────
DOMAIN_QUESTIONS = {
    "Strategy & Governance": [
        "How formally defined, documented, and regularly reviewed is your {cap} process?",
        "To what extent does {cap} directly influence executive decision-making and strategic investment?",
        "How well-integrated is {cap} with adjacent governance, risk, and compliance processes?",
        "What measurable outcomes or KPIs exist to demonstrate the effectiveness of {cap}?",
        "How consistently is {cap} applied and enforced across all business units and geographies?",
        "How effectively does {cap} support identification and mitigation of strategic or operational risk?",
    ],
    "Security": [
        "How comprehensive is your {cap} programme in terms of scope, tooling, and process maturity?",
        "How quickly and effectively can your organisation detect and respond to issues identified through {cap}?",
        "To what extent is {cap} automated and integrated into your broader security operations?",
        "How well does {cap} align with recognised frameworks such as NIST, ISO 27001, or CIS Controls?",
        "How regularly is {cap} reviewed and updated to address emerging threats and vulnerabilities?",
        "What level of cross-functional collaboration supports the improvement of {cap}?",
    ],
    "People": [
        "How mature is your approach to {cap} in terms of process definition and consistent execution?",
        "How effectively does {cap} support workforce planning and skills development at scale?",
        "To what extent is {cap} integrated with talent strategy and business transformation objectives?",
        "How well-measured and reported are outcomes from {cap} to leadership and HR business partners?",
        "How consistently is {cap} applied across different departments and management layers?",
        "To what degree does {cap} leverage data and analytics to drive continuous improvement?",
    ],
    "Applications": [
        "How mature is your {cap} capability in terms of defined process, tooling, and governance?",
        "How effectively does {cap} enable the organisation to modernise and rationalise its application portfolio?",
        "To what extent is {cap} automated and integrated into your development and delivery pipelines?",
        "How well-aligned is {cap} with enterprise architecture standards and API-first design principles?",
        "How consistently is {cap} adopted across application development teams and business units?",
        "How effectively does {cap} contribute to reducing technical debt and improving software quality?",
    ],
    "Data": [
        "How formally governed and documented is your {cap} framework across the organisation?",
        "To what extent does {cap} enable trusted, high-quality data for analytics and decision-making?",
        "How well-integrated is {cap} with data platform engineering and data product delivery?",
        "How effectively does {cap} support regulatory compliance and data privacy obligations?",
        "How consistently is {cap} applied across business units, domains, and data sources?",
        "To what degree does {cap} leverage automation, tooling, and metadata management?",
    ],
    "DevOps": [
        "How mature and automated is your {cap} capability within your software delivery lifecycle?",
        "To what extent does {cap} accelerate delivery velocity while maintaining quality and stability?",
        "How well-integrated is {cap} with security, compliance, and infrastructure provisioning?",
        "How consistently are {cap} practices applied across development teams and product lines?",
        "How effectively does {cap} leverage metrics and feedback loops to drive continuous improvement?",
        "To what degree is {cap} integrated with cloud-native tooling and modern engineering practices?",
    ],
    "Innovation": [
        "How mature is your {cap} capability in enabling rapid prototyping, experimentation, and scaling?",
        "To what extent does {cap} support cloud-native architecture adoption and technology leverage?",
        "How effectively does {cap} enable competitive differentiation and digital business models?",
        "How consistently are {cap} practices governed and adopted across product teams?",
        "How well does {cap} integrate with enterprise-wide innovation strategy and portfolio investment?",
        "To what degree does {cap} drive measurable business value and time-to-market improvements?",
    ],
    "Operations": [
        "How mature is your {cap} capability in terms of process definition, tooling, and SLA adherence?",
        "To what extent does {cap} provide real-time visibility and proactive response to operational issues?",
        "How well-integrated is {cap} with service management, change control, and incident response?",
        "How consistently are {cap} practices applied across infrastructure domains and service tiers?",
        "How effectively does {cap} leverage automation to reduce manual effort and operational risk?",
        "To what degree does {cap} contribute to improved availability, resilience, and customer experience?",
    ],
    "AI & Cognitive Systems": [
        "How mature is your {cap} capability in terms of strategy definition, governance, and execution?",
        "To what extent does {cap} enable responsible, explainable, and scalable AI/ML deployment?",
        "How well-integrated is {cap} with data platform, MLOps, and model lifecycle management?",
        "How effectively does {cap} address regulatory requirements, ethics, and bias mitigation?",
        "How consistently is {cap} applied across AI/ML initiatives and business domains?",
        "To what degree does {cap} enable measurable value from AI investments?",
    ],
    "Intelligent Automation & Operations": [
        "How mature and scalable is your {cap} capability across the organisation?",
        "To what extent does {cap} enable measurable reduction in manual effort and operational cost?",
        "How well-integrated is {cap} with enterprise architecture and technology strategy?",
        "How consistently are {cap} practices governed and adopted across business units?",
        "How effectively does {cap} leverage AI/ML to enhance automation intelligence?",
        "To what degree does {cap} contribute to improved operational outcomes and employee experience?",
    ],
    "Sustainability & Responsible Technology": [
        "How formally defined and governed is your {cap} programme at the organisational level?",
        "To what extent does {cap} enable measurable progress toward sustainability and ESG objectives?",
        "How well-integrated is {cap} with technology procurement, architecture, and operations?",
        "How consistently is {cap} reported against regulatory frameworks and board-level KPIs?",
        "How effectively does {cap} engage and align suppliers and partners on sustainability goals?",
        "To what degree does {cap} drive innovation in sustainable technology design and delivery?",
    ],
    "Experience & Ecosystem Enablement": [
        "How mature is your {cap} capability in enabling seamless digital experiences?",
        "To what extent does {cap} support ecosystem partner integration and value co-creation?",
        "How effectively does {cap} leverage data and analytics to personalise and optimise experiences?",
        "How consistently are {cap} practices governed across channels and partner touchpoints?",
        "How well-integrated is {cap} with product strategy, CX, and API management?",
        "To what degree does {cap} contribute to measurable improvements in customer and partner outcomes?",
    ],
}
DEFAULT_QUESTIONS = [
    "How formally defined and documented is your {cap} process?",
    "To what extent is {cap} integrated with adjacent capabilities and strategic objectives?",
    "How effectively does {cap} deliver measurable outcomes for the organisation?",
    "How consistently is {cap} applied across teams, business units, and geographies?",
    "To what degree is {cap} supported by appropriate tooling, data, and governance?",
    "How well does {cap} leverage automation and continuous improvement practices?",
]

# ── Free-text answer bank (by integer score 1-5) ──────────────────────────────
FREE_TEXT_BY_SCORE = {
    1: [
        "No formal process defined. Activities are reactive and undocumented, driven by individual effort with no organisational visibility.",
        "Minimal activity in this area. There is no consistent approach and the capability is not formally recognised or resourced.",
        "Largely absent as a managed capability. Any activity is ad hoc and varies significantly between individuals and teams.",
        "No standardised tooling or governance in place. Outcomes are unpredictable and dependent on key-person knowledge.",
    ],
    2: [
        "A basic process has been defined but is inconsistently applied. Documentation exists in parts but is not well maintained.",
        "Initial steps taken to formalise the capability, but adoption is patchy and metrics are not routinely tracked.",
        "A framework is in place but limited to certain teams. Tooling is basic and there is no central ownership or review process.",
        "Some policies exist but are not universally enforced. Awareness varies significantly across the organisation.",
    ],
    3: [
        "Standardised processes are broadly adopted across key teams. Regular reviews occur and outcomes are reported to management.",
        "The capability is well-defined with clear ownership and integration with adjacent processes improving steadily.",
        "Practices are consistent and documented. Some automation exists and KPIs are tracked on a quarterly basis.",
        "A formal programme is in place with defined roles, tooling, and a structured review cadence.",
    ],
    4: [
        "Processes are mature and data-driven. Automation is extensive and the capability continuously improves through feedback loops.",
        "Strong governance and tooling support this capability. Insights drive proactive improvements visible at executive level.",
        "The capability is well-embedded across the organisation with clear KPIs, continuous monitoring, and a centre of excellence.",
        "Practices are highly consistent and measurable. The organisation proactively benchmarks against peers and industry standards.",
    ],
    5: [
        "Best-in-class practices with full automation, continuous optimisation, and consistently industry-leading outcomes.",
        "The capability sets the organisational benchmark. Practices evolve proactively and contribute directly to competitive advantage.",
        "Comprehensive, fully integrated, and continuously improving. Regularly benchmarked against industry peers with top-quartile performance.",
        "The organisation is recognised externally as a leader in this capability area. Practices are shared across the industry.",
    ],
}

# ── Industry-specific notes ───────────────────────────────────────────────────
INDUSTRY_NOTES = {
    "Financial Services": [
        "Regulatory constraints (Basel III/IV, MiFID II, DORA) limit some automation initiatives.",
        "Recent internal audit findings highlighted gaps — remediation plan agreed with the regulator.",
        "Risk and compliance requirements necessitate a phased approach to any process changes.",
        "Outsourced functions create data sovereignty concerns that impact governance design.",
        "Third-party risk management obligations extend assessment scope to key vendors.",
        "Regulatory approval timelines add 3–6 months to any significant capability change.",
    ],
    "Healthcare": [
        "Privacy Act and health data obligations constrain cloud deployment options significantly.",
        "Clinical workflow integration requirements add complexity to any technology changes.",
        "Multiple legacy EHR systems create significant data interoperability challenges.",
        "Patient safety obligations mean change management is more rigorous than average.",
        "Funding model constraints limit investment in non-clinical technology capabilities.",
        "My Health Records Act and HIPAA obligations require careful data residency planning.",
    ],
    "Industrial Manufacturing": [
        "OT/IT convergence creates significant security and integration complexity.",
        "Existing ERP landscape shapes the scope and architecture of any transformation programme.",
        "Distributed manufacturing sites create governance and standardisation challenges.",
        "Supply chain partner integration requirements extend the capability boundary significantly.",
        "Safety-critical systems require additional change control and validation processes.",
        "Legacy SCADA and automation systems limit the pace of digital transformation.",
    ],
    "Energy": [
        "AESCSF and IEC 62443 compliance obligations shape the security approach taken here.",
        "SCADA and industrial control system integration creates significant technical constraints.",
        "Geographically distributed operations increase the complexity of consistent adoption.",
        "Regulatory frameworks for critical infrastructure impose additional governance requirements.",
        "Sustainability reporting obligations (TCFD, GRI) drive specific data management needs.",
        "Field operations create connectivity constraints that affect tooling and adoption choices.",
    ],
    "Aviation": [
        "IATA and ICAO compliance obligations constrain technology deployment options.",
        "Safety management system (SMS) integration requirements add complexity to any changes.",
        "Legacy reservation and operations systems create significant integration debt.",
        "Alliance and codeshare partner dependencies extend the scope of any data initiative.",
        "Operational resilience (24/7 uptime) requirements shape architecture and change management.",
        "CAAS/CASA regulatory oversight applies to any change touching operational systems.",
    ],
    "default": [
        "Legacy system constraints create integration dependencies that slow capability improvement.",
        "Organisational change fatigue from recent transformation programmes affects adoption.",
        "Vendor lock-in concerns are influencing architecture decisions in this area.",
        "Budget constraints require prioritisation — not all improvements can be funded in FY26.",
        "Skills gaps have been acknowledged and are being addressed through a targeted hiring plan.",
        "A recent reorganisation has temporarily disrupted governance structures and ownership.",
    ],
}

# ── Recommendation content banks ──────────────────────────────────────────────
RECOMMENDED_ACTIONS_BY_DOMAIN = {
    "Strategy & Governance": [
        "Establish a formal governance committee with clear ownership, terms of reference, and quarterly review cadence",
        "Define and instrument KPIs for this capability; integrate into executive dashboard and quarterly business review reporting",
        "Implement a policy and standards framework with version control, mandatory review cycles, and attestation tracking",
        "Conduct a maturity benchmark (COBIT/TOGAF) and build a time-bound, investment-linked improvement roadmap",
        "Establish a centre of excellence to codify best practices, provide enabling tools, and drive consistent adoption",
    ],
    "Security": [
        "Implement automated scanning integrated into CI/CD pipelines with mandatory break-on-critical policy enforcement",
        "Establish a 24/7 detection and response capability with documented playbooks for top-10 threat scenarios",
        "Deploy a centralised security operations platform with SIEM, SOAR, and threat intelligence integration",
        "Conduct a gap assessment against ISO 27001 / NIST CSF and implement a prioritised remediation roadmap",
        "Establish a regular security posture review board with cross-functional representation and executive sponsorship",
    ],
    "People": [
        "Implement a structured skills matrix and capability framework with defined proficiency levels and career pathways",
        "Launch a targeted learning and development programme addressing the highest-priority skills gaps in this assessment",
        "Establish a workforce planning model linked to technology strategy to ensure skills supply meets future demand",
        "Deploy a change management and communications programme to drive adoption and reduce change fatigue",
        "Implement regular engagement surveys with structured action-planning to address identified feedback",
    ],
    "Applications": [
        "Conduct an application portfolio rationalisation exercise to identify consolidation, modernisation, and retirement candidates",
        "Define and publish API design standards, a developer portal, and an integration governance model",
        "Implement automated code quality, dependency scanning, and software composition analysis in all pipelines",
        "Establish an architecture review board to govern design decisions and ensure alignment with enterprise standards",
        "Create a technical debt register with quantified business risk and an investment-linked remediation roadmap",
    ],
    "Data": [
        "Appoint domain data stewards and establish a data governance council with documented policies and decision rights",
        "Implement a metadata management and data catalogue platform to improve discoverability and lineage tracking",
        "Define and instrument data quality dimensions (completeness, accuracy, consistency, timeliness) with automated monitoring",
        "Establish a data product framework to enable self-service analytics while maintaining governance and access controls",
        "Conduct a data privacy impact assessment and implement controls to meet applicable regulatory obligations",
    ],
    "DevOps": [
        "Implement a standardised CI/CD pipeline template across all product teams with quality gates and automated testing",
        "Deploy infrastructure-as-code for all cloud environments with policy-as-code guardrails and drift detection",
        "Establish a developer experience platform to reduce cognitive load and accelerate developer onboarding",
        "Define and instrument DORA metrics (deployment frequency, lead time, MTTR, change failure rate) across all teams",
        "Implement GitOps-based deployment practices with mandatory peer review and automated rollback capabilities",
    ],
    "Innovation": [
        "Establish a cloud adoption framework with landing zone standards, guardrails, and a Cloud Centre of Excellence",
        "Implement FinOps practices with real-time cost visibility, tagging standards, and team-level accountability frameworks",
        "Create an innovation sandbox environment for rapid prototyping and proof-of-concept delivery",
        "Define and execute a container platform strategy with standardised tooling and developer self-service capabilities",
        "Establish a technology radar and architecture decision record process to guide technology selection",
    ],
    "Operations": [
        "Implement a full-stack observability platform (metrics, logs, traces) with automated alerting and anomaly detection",
        "Establish a site reliability engineering function with SLO/SLI definitions and error budget governance",
        "Define and automate incident management workflows with integrated ITSM, on-call scheduling, and post-incident reviews",
        "Implement event correlation to reduce alert noise and enable predictive capacity management",
        "Establish a problem management capability with root cause analysis processes and knowledge base integration",
    ],
    "AI & Cognitive Systems": [
        "Define an AI governance framework covering model risk, bias assessment, explainability, and regulatory compliance",
        "Implement an MLOps platform to standardise model development, testing, deployment, and monitoring",
        "Establish an AI ethics and responsible AI review board with documented principles and mandatory assessment processes",
        "Conduct an AI skills assessment and implement a targeted up-skilling programme for data science and engineering teams",
        "Define and instrument AI performance metrics (accuracy, drift, fairness) with automated retraining and alerting",
    ],
    "Intelligent Automation & Operations": [
        "Define an automation centre of excellence with a capability framework, tooling standards, and governance model",
        "Establish an automation opportunity register to systematically identify, prioritise, and track automation initiatives",
        "Implement a process mining capability to identify high-value automation targets using objective operational data",
        "Define and instrument automation ROI metrics to justify continued investment and demonstrate business value",
        "Build an automation academy to develop internal skills and reduce dependency on external vendors",
    ],
    "Sustainability & Responsible Technology": [
        "Establish an ICT sustainability governance framework with board-level reporting on energy and carbon metrics",
        "Implement automated energy and carbon monitoring for all datacentre and cloud workloads",
        "Define a green procurement policy and supplier sustainability scorecard aligned to TCFD/GRI frameworks",
        "Conduct a full lifecycle assessment of ICT estate to identify the highest-impact reduction opportunities",
        "Integrate sustainability criteria into all technology architecture and investment decisions",
    ],
    "Experience & Ecosystem Enablement": [
        "Define a digital experience strategy with measurable CX outcomes and cross-functional ownership",
        "Implement an API management platform to enable partner ecosystem integration and developer self-service",
        "Deploy experience analytics tooling to capture and act on real-time customer journey insights",
        "Establish a product-led growth framework to align technology delivery with customer value outcomes",
        "Create an ecosystem partner programme with standardised onboarding, integration standards, and SLA governance",
    ],
    "default": [
        "Define a formal capability framework with clear ownership, process documentation, and performance metrics",
        "Implement appropriate tooling to automate manual activities and improve consistency and auditability",
        "Establish a governance structure with defined roles, responsibilities, and regular review cadence",
        "Conduct a gap assessment and build a prioritised, investment-linked improvement roadmap",
        "Deploy training and enablement programmes to address skills gaps and drive consistent adoption",
    ],
}

SUCCESS_INDICATORS_BY_DOMAIN = {
    "Strategy & Governance":   ["Governance committee operational with quarterly reporting by Q2 2026",
                                 "Capability KPIs live in executive dashboard within 90 days",
                                 "Policy framework attested by all business units within 6 months"],
    "Security":                ["MTTD reduced by ≥50% within 12 months",
                                 "Critical vulnerability remediation SLA at ≥95% compliance within 6 months",
                                 "Security posture score improves ≥20 points on next external assessment"],
    "People":                  ["Skills matrix coverage reaches ≥90% of workforce within 6 months",
                                 "Target roles achieve ≥80% proficiency certification within 12 months",
                                 "Employee engagement score for this capability improves by ≥10 points"],
    "Applications":            ["Technical debt register established; ≥30% of critical items remediated in 12 months",
                                 "API adoption rate increases ≥40% across integration touchpoints within 9 months",
                                 "Application rationalisation delivers ≥15% portfolio footprint reduction in 18 months"],
    "Data":                    ["Data quality score for priority domains reaches ≥85% within 6 months",
                                 "Data catalogue covers ≥70% of critical data assets within 9 months",
                                 "Privacy compliance attestation completed for all in-scope systems within 12 months"],
    "DevOps":                  ["Deployment frequency increases to ≥weekly for all production services within 6 months",
                                 "Lead time for change reduced to <5 days for 80% of releases within 9 months",
                                 "DORA metrics published and tracked for all product teams within 90 days"],
    "Innovation":              ["Cloud adoption reaches ≥60% of new workloads within 12 months",
                                 "FinOps tooling deployed and cost dashboard available to teams within 90 days",
                                 "Container platform handling ≥40% of application workloads within 18 months"],
    "Operations":              ["Full-stack observability covers ≥80% of production services within 6 months",
                                 "MTTR for P1 incidents reduced by ≥40% within 12 months",
                                 "Alert noise ratio reduced by ≥60% within 9 months"],
    "AI & Cognitive Systems":  ["AI governance framework published with mandatory assessment process within 90 days",
                                 "MLOps platform deployed for ≥80% of new AI/ML initiatives within 12 months",
                                 "Bias and fairness assessments complete for all production models within 6 months"],
    "Intelligent Automation & Operations": [
                                 "Automation opportunity register established with top-20 candidates prioritised within 60 days",
                                 "Automation ROI metrics tracked and reported to leadership within 90 days",
                                 "Centre of excellence operational with internal delivery capability within 6 months"],
    "Sustainability & Responsible Technology": [
                                 "Carbon and energy dashboard operational for all material ICT workloads within 90 days",
                                 "Supplier sustainability scorecard deployed for top-20 vendors within 6 months",
                                 "ICT sustainability targets incorporated into enterprise ESG reporting within 12 months"],
    "Experience & Ecosystem Enablement": [
                                 "CX KPI framework agreed and instrumented within 90 days",
                                 "API management platform live with ≥5 partner integrations within 6 months",
                                 "Customer journey analytics deployed for top-3 digital journeys within 9 months"],
    "default":                 ["Formal capability framework documented and approved within 90 days",
                                 "Tooling deployed and adopted by ≥80% of target teams within 6 months",
                                 "Measurable KPI improvement of ≥20% against baseline within 12 months"],
}

ENABLING_DEPS_BY_DOMAIN = {
    "Strategy & Governance":   ["Executive Alignment", "Governance Risk Management"],
    "Security":                ["Identity & Access Management", "Vulnerability Management"],
    "People":                  ["Change Communications", "Talent Acquisition"],
    "Applications":            ["Architecture Design", "DevOps CI/CD"],
    "Data":                    ["Data Governance Organization", "Meta Data Management"],
    "DevOps":                  ["Core Infrastructure Automation", "Cloud Resource Management"],
    "Innovation":              ["Generic Cloud Technologies", "DevOps CI/CD"],
    "Operations":              ["Application Monitoring", "Incident Management"],
    "AI & Cognitive Systems":  ["Data Governance Organization", "Generative AI & LLM Operations"],
    "default":                 ["Governance Risk Management", "Service Design"],
}

# ── Narrative templates per use case ─────────────────────────────────────────
NARRATIVE_TEMPLATES = {
    31: (
        "{client} engaged HPE Consulting to undertake a General IT Readiness & Maturity Assessment spanning "
        "{domain_count} domains and {cap_count} capabilities. The assessment reveals an overall maturity score "
        "of {score:.1f} out of 5.0, indicating a {maturity_label} level of IT capability maturity. "
        "Key strengths were identified in {strong_domain}, where consistent processes and measurement frameworks "
        "are in place. The most significant gaps were observed in {weak_domain}, where foundational capabilities "
        "require immediate investment. Across the {industry} sector in {country}, this profile reflects "
        "common challenges in balancing operational demands with strategic transformation. "
        "A total of {p1_count} P1 priority recommendations have been identified, representing the critical "
        "capability investments required to close the most impactful gaps within the next 12 months."
    ),
    27: (
        "{client} commissioned HPE Consulting to conduct an Operating Model Modernization Assessment across "
        "{domain_count} domains and {cap_count} capabilities. The organisation achieved an overall maturity "
        "score of {score:.1f}, reflecting a {maturity_label} capability baseline. The assessment reveals "
        "strong People and Strategy capabilities offset by emerging gaps in DevOps and Operational maturity. "
        "The {industry} context in {country} creates specific considerations around change management, "
        "workforce capability uplift, and process standardisation. "
        "{p1_count} P1-priority recommendations focus on accelerating automation, formalising governance "
        "structures, and building the organisational capabilities required to sustain a modernised operating model."
    ),
    30: (
        "{client} engaged HPE Consulting to assess AI Readiness & Maturity across {domain_count} domains "
        "and {cap_count} capabilities. The overall maturity score of {score:.1f} indicates a {maturity_label} "
        "AI capability baseline. The organisation demonstrates nascent strengths in data management, offset "
        "by significant gaps in AI governance, MLOps, and responsible AI practices. "
        "As a {industry} organisation in {country}, regulatory compliance, model risk management, and "
        "explainability are non-negotiable requirements that must underpin any AI programme. "
        "{p1_count} P1-priority recommendations address foundational capability gaps that must be resolved "
        "before the organisation can scale AI-driven value creation responsibly."
    ),
    32: (
        "{client} engaged HPE Consulting to undertake a Datacentre Transformation Assessment across "
        "{domain_count} domains and {cap_count} capabilities. The overall maturity score of {score:.1f} "
        "reflects a {maturity_label} transformation baseline. The assessment identifies gaps in security "
        "automation, infrastructure modernisation, and operational tooling as the primary areas requiring "
        "investment. In the {industry} sector, {country} regulatory requirements and operational resilience "
        "obligations create additional complexity for any transformation programme. "
        "{p1_count} P1-priority recommendations define the critical path for a structured, risk-managed "
        "datacentre modernisation journey."
    ),
    "default": (
        "{client} engaged HPE Consulting to assess capability maturity across {domain_count} domains and "
        "{cap_count} capabilities. The overall maturity score of {score:.1f} out of 5.0 indicates a "
        "{maturity_label} level of capability. Key investment priorities have been identified across "
        "{p1_count} P1-priority recommendations that represent the most critical gaps to address. "
        "The {industry} context in {country} shapes the approach and timeline for capability uplift, "
        "particularly in areas subject to regulatory or operational constraints."
    ),
}

MATURITY_LABELS = {
    1: "Ad Hoc",
    2: "Defined",
    3: "Integrated",
    4: "Intelligent",
    5: "Adaptive",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _maturity_label(score: float) -> str:
    return MATURITY_LABELS.get(max(1, min(5, round(score))), "Defined")


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
    return max(1.0, min(5.0, round(s * 2) / 2))   # round to nearest 0.5


def _yn_answer(score: float) -> tuple[str, float]:
    """Map a 1-5 float score to (Yes/Partial/No, normalised_score)."""
    if score >= 2.7:
        return "Yes", 3.0
    if score >= 1.5:
        return "Partial", 2.0
    return "No", 1.0


def _get_questions(domain_name: str, cap_name: str, cap_id: int) -> list[str]:
    bank = DOMAIN_QUESTIONS.get(domain_name, DEFAULT_QUESTIONS)
    # Rotate by cap_id to get different question triples per capability
    offset = cap_id % (len(bank) - 2)
    qs = bank[offset:offset + 3]
    if len(qs) < 3:
        qs = qs + bank[:3 - len(qs)]
    return [q.format(cap=cap_name) for q in qs]


def _get_notes(industry: str, rng: random.Random, probability: float = 0.3) -> str:
    if rng.random() > probability:
        return ""
    pool = INDUSTRY_NOTES.get(industry, INDUSTRY_NOTES["default"])
    return rng.choice(pool)


def _build_narrative(spec: dict, domain_count: int, cap_count: int,
                      avg_score: float, p1_count: int,
                      sorted_domains: list[tuple]) -> str:
    """Build a realistic executive summary narrative."""
    uc_id = spec["usecase_id"]
    template = NARRATIVE_TEMPLATES.get(uc_id, NARRATIVE_TEMPLATES["default"])

    # Identify strongest and weakest domains
    if len(sorted_domains) >= 2:
        strong_domain = sorted_domains[-1][0]   # highest avg
        weak_domain   = sorted_domains[0][0]    # lowest avg
    elif sorted_domains:
        strong_domain = weak_domain = sorted_domains[0][0]
    else:
        strong_domain = weak_domain = "core capabilities"

    return template.format(
        client=spec["client_name"],
        domain_count=domain_count,
        cap_count=cap_count,
        score=avg_score,
        maturity_label=_maturity_label(avg_score),
        strong_domain=strong_domain,
        weak_domain=weak_domain,
        industry=spec["client_industry"],
        country=spec["client_country"],
        p1_count=p1_count,
    )


def _get_capability_role(impact_weight) -> str:
    if impact_weight is None:
        return "Core"
    w = int(impact_weight)
    if w >= 4:
        return "Core"
    if w >= 2:
        return "Upstream"
    return "Downstream"


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_columns(cur: sqlite3.Cursor) -> None:
    """Add optional columns that may not exist in older DB versions."""
    for col in ("findings_narrative TEXT", "usecase_id INTEGER", "assessment_mode TEXT"):
        try:
            cur.execute(f"ALTER TABLE Assessment ADD COLUMN {col}")
        except Exception:
            pass


def _load_use_case_caps(cur: sqlite3.Cursor, usecase_id: int) -> dict[int, list[dict]]:
    """Return {domain_id: [cap_dict, ...]} for all caps in a use case."""
    cur.execute("""
        SELECT nd.id  AS domain_id,
               nd.domain_name,
               nsd.subdomain_name,
               nc.id  AS cap_id,
               nc.capability_name,
               uci.impact_weight,
               COALESCE(uci.maturity_target, 3) AS tgt
        FROM   Next_UseCaseCapabilityImpact uci
        JOIN   Next_Capability   nc  ON nc.id  = uci.capability_id
        JOIN   Next_SubDomain    nsd ON nsd.id = nc.subdomain_id
        JOIN   Next_Domain       nd  ON nd.id  = nsd.domain_id
        WHERE  uci.usecase_id = ?
        ORDER  BY nd.id, nc.id
    """, [usecase_id])
    rows = cur.fetchall()
    by_domain: dict[int, list[dict]] = {}
    for r in rows:
        did = r["domain_id"]
        by_domain.setdefault(did, []).append({
            "domain_id":       r["domain_id"],
            "domain_name":     r["domain_name"],
            "subdomain_name":  r["subdomain_name"],
            "cap_id":          r["cap_id"],
            "cap_name":        r["capability_name"],
            "impact_weight":   r["impact_weight"],
            "tgt":             r["tgt"],
            "role":            _get_capability_role(r["impact_weight"]),
        })
    return by_domain


def _select_caps(by_domain: dict, caps_per_domain: int | None, rng: random.Random) -> list[dict]:
    """Flatten domain map, sampling up to caps_per_domain per domain."""
    result = []
    for caps in by_domain.values():
        pool = list(caps)
        if caps_per_domain and len(pool) > caps_per_domain:
            # Pick deterministically: first 3 highest-weight + random fill
            pool.sort(key=lambda c: -(c["impact_weight"] or 0))
            selected = pool[:3]
            remaining = [c for c in pool[3:] if c not in selected]
            rng.shuffle(remaining)
            selected += remaining[:caps_per_domain - 3]
            pool = selected
        result.extend(pool)
    return result


def _generate_cap_score(base: float, std: float, rng: random.Random) -> float:
    return _clamp_score(rng.gauss(base, std))


# ─────────────────────────────────────────────────────────────────────────────
# Core seed function
# ─────────────────────────────────────────────────────────────────────────────

def seed_assessment(conn: sqlite3.Connection, spec: dict, rng: random.Random) -> int | None:
    cur = conn.cursor()

    # ── Idempotency check ──────────────────────────────────────────────────
    cur.execute("""
        SELECT a.id FROM Assessment a
        JOIN Client c ON a.client_id = c.id
        WHERE c.client_name = ? AND a.use_case_name = ?
        LIMIT 1
    """, [spec["client_name"], spec["use_case_name"]])
    if cur.fetchone():
        print(f"  SKIP  {spec['client_name']} / {spec['use_case_name']} (already exists)")
        return None

    now = datetime.now()
    created_at   = (now - timedelta(days=spec["days_ago"])).isoformat()
    completed_at = (now - timedelta(days=spec["days_ago"] - 1)).isoformat()

    # ── 1. Client ──────────────────────────────────────────────────────────
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

    # ── 2. Load + select capabilities ─────────────────────────────────────
    by_domain  = _load_use_case_caps(cur, spec["usecase_id"])
    all_caps   = _select_caps(by_domain, spec.get("caps_per_domain"), rng)

    # Assign scores
    # Per-domain base: slight shift from overall base to create realistic variation
    domain_ids = list(dict.fromkeys(c["domain_id"] for c in all_caps))
    domain_base: dict[int, float] = {}
    for did in domain_ids:
        domain_base[did] = _clamp_score(rng.gauss(spec["base_score"], 0.3))

    cap_scores: dict[int, float] = {}
    for cap in all_caps:
        cap_scores[cap["cap_id"]] = _generate_cap_score(domain_base[cap["domain_id"]], spec["score_std"], rng)

    # ── 3. Assessment header ───────────────────────────────────────────────
    overall = round(sum(cap_scores.values()) / len(cap_scores), 2) if cap_scores else 0.0

    cur.execute("""
        INSERT INTO Assessment
            (client_id, engagement_name, use_case_name, intent_text,
             usecase_id, assessment_mode, overall_score, status, created_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?)
    """, [
        client_id,
        spec["engagement_name"],
        spec["use_case_name"],
        f"Assess current IT capability maturity for {spec['client_name']} to identify "
        f"transformation priorities and build a structured improvement roadmap.",
        spec["usecase_id"],
        spec["assessment_mode"],
        overall,
        created_at,
        completed_at,
    ])
    assessment_id = cur.lastrowid

    # ── 4. AssessmentCapability ────────────────────────────────────────────
    cap_rows = [(
        assessment_id,
        cap["cap_id"],
        cap["cap_name"],
        cap["domain_name"],
        cap["subdomain_name"],
        cap["role"],
        cap_scores[cap["cap_id"]],
        f"Scored {cap_scores[cap['cap_id']]:.1f}/5.0 based on assessment responses.",
        DOMAIN_TARGETS.get(cap["domain_name"], cap["tgt"]),
    ) for cap in all_caps]

    cur.executemany("""
        INSERT INTO AssessmentCapability
            (assessment_id, capability_id, capability_name, domain_name, subdomain_name,
             capability_role, ai_score, rationale, target_maturity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, cap_rows)

    # ── 5. AssessmentResponse ──────────────────────────────────────────────
    q_type = spec["q_type"]
    response_rows = []

    for cap in all_caps:
        cid    = cap["cap_id"]
        score  = cap_scores[cid]
        role   = cap["role"]
        domain = cap["domain_name"]
        sub    = cap["subdomain_name"]
        questions = _get_questions(domain, cap["cap_name"], cid)

        for i, question in enumerate(questions):
            # Slightly vary score per question
            q_score = _clamp_score(score + rng.gauss(0, 0.25))

            # Determine question type for this response
            if q_type == "mixed":
                # Rotate across all three types per capability position in the list
                # so every mixed assessment has all three question types represented.
                cap_idx = all_caps.index(cap)
                rt = ["maturity_1_5", "yes_no_evidence", "free_text"][cap_idx % 3]
            elif q_type == "maturity_1_5":
                rt = "maturity_1_5"
            elif q_type == "yes_no_evidence":
                rt = "yes_no_evidence"
            else:
                rt = "free_text"

            if rt == "maturity_1_5":
                answer = None
                stored_score = q_score
            elif rt == "yes_no_evidence":
                yn, stored_score = _yn_answer(q_score)
                answer = yn
            else:  # free_text
                int_score = max(1, min(5, round(q_score)))
                pool = FREE_TEXT_BY_SCORE[int_score]
                answer = pool[cid % len(pool)]
                stored_score = q_score

            notes = _get_notes(spec["client_industry"], rng, probability=0.25) if i == 0 else ""

            response_rows.append((
                assessment_id, cid, cap["cap_name"], domain, sub,
                role, question, rt,
                round(stored_score, 1), answer, notes,
            ))

    cur.executemany("""
        INSERT INTO AssessmentResponse
            (assessment_id, capability_id, capability_name, domain, subdomain,
             capability_role, question, response_type, score, answer, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, response_rows)

    # ── 6. Domain + Capability findings ───────────────────────────────────
    # Group avg by domain
    domain_agg: dict[str, list[float]] = {}
    for cap in all_caps:
        domain_agg.setdefault(cap["domain_name"], []).append(cap_scores[cap["cap_id"]])

    domain_scores = {
        d: round(sum(scores) / len(scores), 2)
        for d, scores in domain_agg.items()
    }

    finding_rows = []
    # Domain findings
    for d, avg in domain_scores.items():
        tgt = DOMAIN_TARGETS.get(d, 3)
        gap = round(max(0.0, tgt - avg), 2)
        finding_rows.append((
            assessment_id, "domain",
            d, None, None, None, None,
            avg, tgt, gap, _risk(avg),
        ))
    # Capability findings
    for cap in all_caps:
        avg  = cap_scores[cap["cap_id"]]
        tgt  = DOMAIN_TARGETS.get(cap["domain_name"], cap["tgt"])
        gap  = round(max(0.0, tgt - avg), 2)
        finding_rows.append((
            assessment_id, "capability",
            cap["domain_name"], cap["cap_id"], cap["cap_name"], cap["role"], cap["subdomain_name"],
            avg, tgt, gap, _risk(avg),
        ))

    cur.executemany("""
        INSERT INTO AssessmentFinding
            (assessment_id, finding_type, domain, capability_id, capability_name,
             capability_role, subdomain, avg_score, target_maturity, gap, risk_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, finding_rows)

    # ── 7. Recommendations (top-gap capabilities) ─────────────────────────
    gap_caps = [
        cap for cap in all_caps
        if (DOMAIN_TARGETS.get(cap["domain_name"], cap["tgt"]) - cap_scores[cap["cap_id"]]) > 0
    ]
    gap_caps.sort(key=lambda c: -(DOMAIN_TARGETS.get(c["domain_name"], c["tgt"]) - cap_scores[c["cap_id"]]))
    rec_caps = gap_caps[:8]   # top 8 by gap

    rec_rows = []
    for cap in rec_caps:
        avg  = cap_scores[cap["cap_id"]]
        tgt  = DOMAIN_TARGETS.get(cap["domain_name"], cap["tgt"])
        gap  = round(max(0.0, tgt - avg), 2)
        tier = _priority_tier(gap, cap["role"])
        eff  = _effort_estimate(gap)
        dom  = cap["domain_name"]

        actions_pool = RECOMMENDED_ACTIONS_BY_DOMAIN.get(dom, RECOMMENDED_ACTIONS_BY_DOMAIN["default"])
        actions = actions_pool[:4]

        deps   = ENABLING_DEPS_BY_DOMAIN.get(dom, ENABLING_DEPS_BY_DOMAIN["default"])
        indics = SUCCESS_INDICATORS_BY_DOMAIN.get(dom, SUCCESS_INDICATORS_BY_DOMAIN["default"])

        narrative = (
            f"{cap['cap_name']} is currently operating at maturity level {avg:.1f} against a target of "
            f"{tgt}. This represents a gap of {gap:.1f} maturity levels and is classified as a "
            f"{tier} priority requiring {eff.lower()} to close. Current practices are characterised by "
            f"{'reactive, undocumented activity with limited organisational visibility' if avg < 2 else 'partial standardisation with inconsistent adoption across the organisation' if avg < 3 else 'defined processes and measurement frameworks that are broadly in place'}."
        )

        rec_rows.append((
            assessment_id, cap["cap_id"], cap["cap_name"],
            dom, cap["role"],
            round(avg, 2), int(tgt), round(gap, 2),
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

    # ── 8. Executive summary narrative ────────────────────────────────────
    sorted_domains = sorted(domain_scores.items(), key=lambda x: x[1])
    p1_count = sum(1 for r in rec_rows if r[9] == "P1")
    narrative = _build_narrative(spec, len(domain_scores), len(all_caps), overall, p1_count, sorted_domains)

    cur.execute("UPDATE Assessment SET findings_narrative = ? WHERE id = ?", [narrative, assessment_id])

    conn.commit()

    domain_count = len(domain_scores)
    print(f"  -> Assessment #{assessment_id}: {spec['client_name']} / {spec['use_case_name']}")
    print(f"     Domains={domain_count}  Caps={len(all_caps)}  Responses={len(response_rows)}  "
          f"Recs={len(rec_rows)}  Overall={overall:.2f}")

    return assessment_id


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    clean = "--clean" in sys.argv

    conn = sqlite3.connect(FRAMEWORKS_PATH)
    conn.execute(f'ATTACH DATABASE "{ASSESSMENTS_PATH}" AS assessments')
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Ensure optional columns exist
    _ensure_columns(cur)

    # Ensure AssessmentRecommendation table exists (matches actual DB schema)
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

    # Optionally remove all seeded assessments by client name (idempotent re-seed)
    if clean:
        client_names = [s["client_name"] for s in ASSESSMENTS]
        print(f"--clean: removing existing seeded assessments for {len(client_names)} clients...")
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

    rng = random.Random(42)
    created = 0
    skipped = 0

    for spec in ASSESSMENTS:
        print(f"\n{'='*60}")
        print(f"Assessment: {spec['client_name']} / {spec['use_case_name']}")
        aid = seed_assessment(conn, spec, rng)
        if aid is not None:
            created += 1
        else:
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Done. {created} assessment(s) created, {skipped} skipped (already exist).")
    conn.close()


if __name__ == "__main__":
    main()

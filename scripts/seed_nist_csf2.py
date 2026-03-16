#!/usr/bin/env python3
"""
seed_nist_csf2.py
=================
Meridant Matrix — NIST CSF 2.0 Framework Seed
Run from project root inside Docker:

    docker compose exec app python scripts/seed_nist_csf2.py

What this script does
---------------------
1. Registers NIST CSF 2.0 in Next_Framework (framework_id auto-assigned)
2. Seeds 6 Functions     → Next_Domain      (Pillar level)
3. Seeds 22 Categories   → Next_SubDomain   (Domain level)
4. Seeds 106 Subcategories → Next_Capability (Capability level)
5. Generates L1-L5 maturity descriptors via Claude API → Next_CapabilityLevel
6. Seeds 5 starter use cases → Next_UseCase + Next_UseCaseCapabilityImpact

Checkpointing
-------------
Descriptor generation is checkpointed in a local file:
    /tmp/nist_csf2_descriptor_progress.json
If interrupted, re-running resumes from where it stopped.

Runtime estimate: 15-25 minutes (530 AI calls with retry backoff)

Options
-------
    --taxonomy-only     Seed taxonomy without generating descriptors
    --descriptors-only  Generate descriptors for already-seeded capabilities
    --use-cases-only    Seed use cases only
    --dry-run           Print what would be inserted, no DB writes
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FRAMEWORKS_DB = os.getenv("MERIDANT_FRAMEWORKS_DB_PATH", "/data/meridant_frameworks.db")
CHECKPOINT_FILE = "/tmp/nist_csf2_descriptor_progress.json"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0

# ---------------------------------------------------------------------------
# NIST CSF 2.0 Taxonomy
# Structure: (function_id, function_name, function_description, categories)
# Category: (category_id_str, category_name, subcategories)
# Subcategory: (subcategory_id_str, subcategory_name, subcategory_description)
# ---------------------------------------------------------------------------

NIST_CSF2_TAXONOMY = [
    {
        "key": "GV",
        "name": "Govern",
        "description": "Establishes and monitors the organisation's cybersecurity risk management strategy, expectations, and policy.",
        "categories": [
            {
                "key": "GV.OC",
                "name": "Organizational Context",
                "description": "The circumstances — mission, stakeholder expectations, dependencies — surrounding the organisation's cybersecurity risk decisions are understood.",
                "subcategories": [
                    ("GV.OC-01", "Organisational mission", "The organisational mission is understood and informs cybersecurity risk management."),
                    ("GV.OC-02", "Internal and external stakeholders", "Internal and external stakeholders are understood, and their needs and expectations regarding cybersecurity risk management are understood and considered."),
                    ("GV.OC-03", "Legal, regulatory, and contractual requirements", "Legal, regulatory, and contractual cybersecurity obligations of the organisation are understood and managed."),
                    ("GV.OC-04", "Organisational roles and responsibilities", "Organisational roles, responsibilities, and authorities related to cybersecurity risk management are established and communicated."),
                    ("GV.OC-05", "Outcomes, capabilities, and services dependencies", "Outcomes, capabilities, and services that the organisation depends on are understood and communicated."),
                ]
            },
            {
                "key": "GV.RM",
                "name": "Risk Management Strategy",
                "description": "The organisation's priorities, constraints, risk tolerance and appetite statements, and assumptions are established, communicated, and used to support operational risk decisions.",
                "subcategories": [
                    ("GV.RM-01", "Risk management objectives", "Risk management objectives are established and agreed to by organisational stakeholders."),
                    ("GV.RM-02", "Risk appetite and tolerance", "Risk appetite and risk tolerance statements are established, communicated, and maintained."),
                    ("GV.RM-03", "Cybersecurity risk management activities integration", "Cybersecurity risk management activities and outcomes are included in enterprise risk management processes."),
                    ("GV.RM-04", "Strategic direction for risk management", "Strategic direction that describes appropriate risk response options is established and communicated."),
                    ("GV.RM-05", "Lines of communication", "Lines of communication across the organisation are established for cybersecurity risks, including risks from suppliers and other third parties."),
                    ("GV.RM-06", "Standardised risk response process", "A standardised process for managing cybersecurity risks is established and communicated."),
                    ("GV.RM-07", "Strategic opportunities", "Strategic opportunities (i.e., positive risks) are characterised and are included in organisational cybersecurity risk discussions."),
                ]
            },
            {
                "key": "GV.RR",
                "name": "Roles, Responsibilities, and Authorities",
                "description": "Cybersecurity roles, responsibilities, and authorities to foster accountability, performance assessment, and continuous improvement are established and communicated.",
                "subcategories": [
                    ("GV.RR-01", "Leadership accountability", "Organisational leadership is responsible and accountable for cybersecurity risk and fosters a culture that is risk-aware, ethical, and continually improving."),
                    ("GV.RR-02", "Roles and responsibilities", "Roles, responsibilities, and authorities related to cybersecurity risk management are established, communicated, understood, and enforced."),
                    ("GV.RR-03", "Adequate resources", "Adequate resources are allocated commensurate with cybersecurity risk strategy, roles, responsibilities, and policies."),
                    ("GV.RR-04", "Cybersecurity is included in HR practices", "Cybersecurity is included in human resources practices."),
                ]
            },
            {
                "key": "GV.PO",
                "name": "Policy",
                "description": "Organisational cybersecurity policy is established, communicated, and enforced.",
                "subcategories": [
                    ("GV.PO-01", "Policy established", "Policy for managing cybersecurity risks is established based on organisational context, cybersecurity strategy, and priorities and is communicated and enforced."),
                    ("GV.PO-02", "Policy review and update", "Policy for managing cybersecurity risks is reviewed, updated, communicated, and enforced to reflect changes in requirements, threats, technology, and organisational mission."),
                ]
            },
            {
                "key": "GV.OV",
                "name": "Oversight",
                "description": "Results of organisation-wide cybersecurity risk management activities and performance are used to inform, improve, and adjust the risk management strategy.",
                "subcategories": [
                    ("GV.OV-01", "Cybersecurity review", "Cybersecurity risk management strategy outcomes are reviewed to inform and adjust strategy and direction."),
                    ("GV.OV-02", "Cybersecurity state of the organisation", "The cybersecurity risk management strategy is reviewed and adjusted to ensure coverage of organisational requirements and risks."),
                    ("GV.OV-03", "Organisational cybersecurity results", "Organisational cybersecurity risk management performance is evaluated and reviewed for adjustments needed."),
                ]
            },
            {
                "key": "GV.SC",
                "name": "Cybersecurity Supply Chain Risk Management",
                "description": "Cyber supply chain risk management processes are identified, established, managed, monitored, and improved by organisational stakeholders.",
                "subcategories": [
                    ("GV.SC-01", "Supply chain risk management programme", "A cybersecurity supply chain risk management programme, strategy, objectives, policies, and processes are established and agreed to by organisational stakeholders."),
                    ("GV.SC-02", "Cybersecurity requirements for suppliers", "Cybersecurity roles and responsibilities for suppliers, customers, and partners are established, communicated, and coordinated internally and externally."),
                    ("GV.SC-03", "Supply chain risk management integrated", "Cybersecurity supply chain risk management is integrated into cybersecurity and enterprise risk management, risk assessment, and improvement processes."),
                    ("GV.SC-04", "Supplier inventory", "Suppliers are known and prioritised by criticality."),
                    ("GV.SC-05", "Requirements included in agreements", "Requirements to address cybersecurity risks in supply chains are established, prioritised, and integrated into contracts and other types of agreements with suppliers and other relevant third parties."),
                    ("GV.SC-06", "Planning and due diligence", "Planning and due diligence are performed to reduce risks before entering into formal supplier or other third-party relationships."),
                    ("GV.SC-07", "Advanced controls for critical suppliers", "The risks posed by a supplier, their products and services, and other third parties are understood, recorded, prioritised, assessed, responded to, and monitored over the course of the relationship."),
                    ("GV.SC-08", "Incident reporting requirements", "Relevant suppliers and other third parties are included in incident planning, response, and recovery activities."),
                    ("GV.SC-09", "Integration of supplier security assessments", "Supply chain security practices are integrated into cybersecurity and enterprise risk management programmes, and their performance is monitored throughout the technology product and service life cycle."),
                    ("GV.SC-10", "Cybersecurity supply chain risk management plan", "Cybersecurity supply chain risk management plans include provisions for activities that occur after the conclusion of a partnership or service agreement."),
                ]
            },
        ]
    },
    {
        "key": "ID",
        "name": "Identify",
        "description": "Helps develop an organisational understanding to manage cybersecurity risk to systems, people, assets, data, and capabilities.",
        "categories": [
            {
                "key": "ID.AM",
                "name": "Asset Management",
                "description": "Assets (data, hardware, software, systems, facilities, services, people) that enable the organisation to achieve business purposes are identified and managed consistent with their relative importance to organisational objectives and the organisation's risk strategy.",
                "subcategories": [
                    ("ID.AM-01", "Inventories of hardware assets", "Inventories of hardware managed by the organisation are maintained."),
                    ("ID.AM-02", "Inventories of software assets", "Inventories of software, services, and systems managed by the organisation are maintained."),
                    ("ID.AM-03", "Representations of network and data flows", "Representations of the organisation's authorised network communication and internal and external network data flows are maintained."),
                    ("ID.AM-04", "Inventories of services", "Inventories of services provided by suppliers are maintained."),
                    ("ID.AM-05", "Assets prioritised by classification", "Assets are prioritised based on classification, criticality, resources, and impact on the achievement of organisational objectives."),
                    ("ID.AM-07", "Inventories of data and corresponding metadata", "Inventories of data and corresponding metadata for designated data types are maintained."),
                    ("ID.AM-08", "Systems, hardware, software, services, and data are managed", "Systems, hardware, software, services, and data are managed throughout their life cycles."),
                ]
            },
            {
                "key": "ID.RA",
                "name": "Risk Assessment",
                "description": "The organisation understands the cybersecurity risk to organisational operations (including mission, functions, image, or reputation), organisational assets, and individuals.",
                "subcategories": [
                    ("ID.RA-01", "Vulnerabilities identified", "Vulnerabilities in assets are identified, validated, and recorded."),
                    ("ID.RA-02", "Cyber threat intelligence", "Cyber threat intelligence is received from information sharing forums and sources."),
                    ("ID.RA-03", "Internal and external threats identified", "Internal and external threats to the organisation are identified and recorded."),
                    ("ID.RA-04", "Potential impacts and likelihoods", "Potential impacts and likelihoods of threats exploiting vulnerabilities are identified and recorded."),
                    ("ID.RA-05", "Threats, vulnerabilities, likelihoods, and impacts used to understand risk", "Threats, vulnerabilities, likelihoods, and impacts are used to understand inherent risk and inform risk response prioritisation."),
                    ("ID.RA-06", "Risk responses are chosen, prioritised, planned, tracked, and communicated", "Risk responses are chosen, prioritised, planned, tracked, and communicated."),
                    ("ID.RA-07", "Changes and exceptions are managed", "Changes and exceptions are managed, assessed for risk impact, recorded, and tracked."),
                    ("ID.RA-08", "Processes for receiving, analysing, and responding to vulnerability disclosures", "Processes for receiving, analysing, and responding to vulnerability disclosures are established."),
                    ("ID.RA-09", "The authenticity and integrity of hardware and software", "The authenticity and integrity of hardware and software are assessed prior to acquisition and use."),
                    ("ID.RA-10", "Critical suppliers are assessed", "Critical suppliers are assessed prior to acquisition."),
                ]
            },
            {
                "key": "ID.IM",
                "name": "Improvement",
                "description": "Improvements to organisational cybersecurity risk management processes, procedures and activities are identified across all CSF Functions.",
                "subcategories": [
                    ("ID.IM-01", "Improvements are identified from evaluations", "Improvements are identified from evaluations."),
                    ("ID.IM-02", "Improvements are identified from security tests and exercises", "Improvements are identified from security tests and exercises, including those done in coordination with suppliers and relevant third parties."),
                    ("ID.IM-03", "Improvements are identified from execution of operational processes", "Improvements are identified from execution of operational processes, procedures, and activities."),
                    ("ID.IM-04", "Incident response plans and other cybersecurity plans that affect operations", "Incident response plans and other cybersecurity plans that affect operations are established, communicated, maintained, and improved."),
                ]
            },
        ]
    },
    {
        "key": "PR",
        "name": "Protect",
        "description": "Develops and implements appropriate safeguards to ensure delivery of critical services.",
        "categories": [
            {
                "key": "PR.AA",
                "name": "Identity Management, Authentication, and Access Control",
                "description": "Access to physical and logical assets is limited to authorised users, services, and hardware and managed commensurate with the assessed risk of unauthorised access.",
                "subcategories": [
                    ("PR.AA-01", "Identities and credentials managed", "Identities and credentials for authorised users, services, and hardware are managed by the organisation."),
                    ("PR.AA-02", "Identities are proofed and bound to credentials", "Identities are proofed and bound to credentials based on the context of interactions."),
                    ("PR.AA-03", "Users, services, and hardware are authenticated", "Users, services, and hardware are authenticated."),
                    ("PR.AA-04", "Identity assertions are protected", "Identity assertions are protected, conveyed, and verified."),
                    ("PR.AA-05", "Access permissions and authorisations managed", "Access permissions, entitlements, and authorisations are defined in a policy, managed, enforced, and reviewed."),
                    ("PR.AA-06", "Physical access to assets is managed", "Physical access to assets is managed, monitored, and enforced commensurate with risk."),
                ]
            },
            {
                "key": "PR.AT",
                "name": "Awareness and Training",
                "description": "The organisation's personnel and partners are provided cybersecurity awareness education and are trained to perform their cybersecurity-related duties and responsibilities.",
                "subcategories": [
                    ("PR.AT-01", "Personnel are informed and trained", "Personnel are provided with awareness and training so that they possess the knowledge and skills to perform general tasks with cybersecurity risks in mind."),
                    ("PR.AT-02", "Individuals in specialised roles are trained", "Individuals in specialised roles are provided with awareness and training so that they possess the knowledge and skills to perform relevant tasks with cybersecurity risks in mind."),
                ]
            },
            {
                "key": "PR.DS",
                "name": "Data Security",
                "description": "Data are managed consistent with the organisation's risk strategy to protect the confidentiality, integrity, and availability of information.",
                "subcategories": [
                    ("PR.DS-01", "Data-at-rest are protected", "The confidentiality, integrity, and availability of data-at-rest are protected."),
                    ("PR.DS-02", "Data-in-transit are protected", "The confidentiality, integrity, and availability of data-in-transit are protected."),
                    ("PR.DS-10", "Data-in-use are protected", "The confidentiality, integrity, and availability of data-in-use are protected."),
                    ("PR.DS-11", "Backups are created, protected, maintained, and tested", "Backups of data are created, protected, maintained, and tested."),
                ]
            },
            {
                "key": "PR.PS",
                "name": "Platform Security",
                "description": "The hardware, software (e.g., firmware, operating systems, applications), and services of physical and virtual platforms are managed consistent with the organisation's risk strategy.",
                "subcategories": [
                    ("PR.PS-01", "Configuration management practices established", "Configuration management practices are established and applied."),
                    ("PR.PS-02", "Software is maintained, replaced, and removed", "Software is maintained, replaced, and removed commensurate with risk."),
                    ("PR.PS-03", "Hardware is maintained, replaced, and removed", "Hardware is maintained, replaced, and removed commensurate with risk."),
                    ("PR.PS-04", "Log records are generated and made available", "Log records are generated and made available for continuous monitoring."),
                    ("PR.PS-05", "Installation and execution of unauthorised software are prevented", "Installation and execution of unauthorised software are prevented."),
                    ("PR.PS-06", "Secure software development practices are integrated", "Secure software development practices are integrated, and their security is evaluated."),
                ]
            },
            {
                "key": "PR.IR",
                "name": "Technology Infrastructure Resilience",
                "description": "Security architectures are managed with the organisation's risk strategy to protect asset confidentiality, integrity, and availability, and organisational resilience.",
                "subcategories": [
                    ("PR.IR-01", "Networks and environments are protected", "Networks and environments are protected from unauthorised logical access and usage."),
                    ("PR.IR-02", "The organisation's technology assets are protected", "The organisation's technology assets are protected from environmental threats."),
                    ("PR.IR-03", "Mechanisms are implemented to achieve resilience", "Mechanisms are implemented to achieve resilience requirements in normal and adverse situations."),
                    ("PR.IR-04", "Adequate resource capacity to ensure availability", "Adequate resource capacity is ensured to maintain availability."),
                ]
            },
        ]
    },
    {
        "key": "DE",
        "name": "Detect",
        "description": "Develops and implements appropriate activities to identify the occurrence of a cybersecurity event.",
        "categories": [
            {
                "key": "DE.CM",
                "name": "Continuous Monitoring",
                "description": "Assets are monitored to find anomalies, indicators of compromise, and other potentially adverse events.",
                "subcategories": [
                    ("DE.CM-01", "Networks and network services are monitored", "Networks and network services are monitored to find potentially adverse events."),
                    ("DE.CM-02", "The physical environment is monitored", "The physical environment is monitored to find potentially adverse events."),
                    ("DE.CM-03", "Personnel activity and technology usage are monitored", "Personnel activity and technology usage are monitored to find potentially adverse events."),
                    ("DE.CM-06", "External service provider activities are monitored", "External service provider activities and services are monitored to find potentially adverse events."),
                    ("DE.CM-09", "Computing hardware and software are monitored", "Computing hardware and software, runtime environments, and their data are monitored to find potentially adverse events."),
                ]
            },
            {
                "key": "DE.AE",
                "name": "Adverse Event Analysis",
                "description": "Anomalies and indicators of compromise and other potentially adverse events are analysed to characterise the events and detect cybersecurity incidents.",
                "subcategories": [
                    ("DE.AE-02", "Potentially adverse events are analysed", "Potentially adverse events are analysed to better understand associated activities."),
                    ("DE.AE-03", "Information is correlated from multiple sources", "Information is correlated from multiple sources."),
                    ("DE.AE-04", "The estimated impact and scope of adverse events are understood", "The estimated impact and scope of adverse events are understood."),
                    ("DE.AE-06", "Information on adverse events is provided to authorised staff", "Information on adverse events is provided to authorised staff and tools."),
                    ("DE.AE-07", "Cyber threat intelligence and other contextual information are integrated", "Cyber threat intelligence and other contextual information are integrated into the analysis."),
                    ("DE.AE-08", "Incidents are declared when adverse events meet the defined criteria", "Incidents are declared when adverse events meet the defined criteria."),
                ]
            },
        ]
    },
    {
        "key": "RS",
        "name": "Respond",
        "description": "Develops and implements appropriate activities to take action regarding a detected cybersecurity incident.",
        "categories": [
            {
                "key": "RS.MA",
                "name": "Incident Management",
                "description": "Responses to detected cybersecurity incidents are managed.",
                "subcategories": [
                    ("RS.MA-01", "Incident response plan is executed", "The incident response plan is executed in coordination with relevant third parties once an incident is declared."),
                    ("RS.MA-02", "Incident reports are triaged", "Incident reports are triaged and validated."),
                    ("RS.MA-03", "Incidents are categorised and prioritised", "Incidents are categorised and prioritised."),
                    ("RS.MA-04", "Incidents are escalated or elevated", "Incidents are escalated or elevated as needed."),
                    ("RS.MA-05", "The criteria for initiating incident recovery are applied", "The criteria for initiating incident recovery are applied."),
                ]
            },
            {
                "key": "RS.AN",
                "name": "Incident Analysis",
                "description": "Investigations are conducted to ensure effective response and support forensics and recovery activities.",
                "subcategories": [
                    ("RS.AN-03", "Analysis is performed to establish what has occurred during an incident", "Analysis is performed to establish what has occurred during an incident and the root cause of the incident."),
                    ("RS.AN-06", "Actions performed during an investigation are recorded", "Actions performed during an investigation are recorded, and the records' integrity and provenance are preserved."),
                    ("RS.AN-07", "Incident data and metadata are collected", "Incident data and metadata are collected, and their integrity is preserved."),
                    ("RS.AN-08", "An incident's magnitude is estimated and validated", "An incident's magnitude is estimated and validated."),
                ]
            },
            {
                "key": "RS.CO",
                "name": "Incident Response Reporting and Communication",
                "description": "Response activities are coordinated with internal and external stakeholders (e.g. external support from law enforcement agencies).",
                "subcategories": [
                    ("RS.CO-02", "Internal and external stakeholders are notified", "Internal and external stakeholders are notified of incidents."),
                    ("RS.CO-03", "Information is shared with designated internal and external stakeholders", "Information is shared with designated internal and external stakeholders as authorised."),
                ]
            },
            {
                "key": "RS.MI",
                "name": "Incident Mitigation",
                "description": "Activities are performed to prevent expansion of an event, mitigate its effects, and resolve the incident.",
                "subcategories": [
                    ("RS.MI-01", "Incidents are contained", "Incidents are contained."),
                    ("RS.MI-02", "Incidents are eradicated", "Incidents are eradicated."),
                ]
            },
        ]
    },
    {
        "key": "RC",
        "name": "Recover",
        "description": "Develops and implements appropriate activities to maintain plans for resilience and to restore any capabilities or services that were impaired due to a cybersecurity incident.",
        "categories": [
            {
                "key": "RC.RP",
                "name": "Incident Recovery Plan Execution",
                "description": "Restoration activities are performed to ensure operational availability of systems and services affected by cybersecurity incidents.",
                "subcategories": [
                    ("RC.RP-01", "Recovery plan is executed", "The recovery portion of the incident response plan is executed once initiated from the incident response process."),
                    ("RC.RP-02", "Recovery actions are selected, scoped, prioritised, and performed", "Recovery actions are selected, scoped, prioritised, and performed."),
                    ("RC.RP-03", "The integrity of backups and other restoration assets is verified", "The integrity of backups and other restoration assets is verified before using them for restoration."),
                    ("RC.RP-04", "Critical mission functions and cybersecurity considerations are established", "Critical mission functions and cybersecurity considerations are established during recovery."),
                    ("RC.RP-05", "The integrity of restored assets is verified", "The integrity of restored assets is verified, systems and services are restored, and normal operating status is confirmed."),
                    ("RC.RP-06", "The end of incident recovery is declared", "The end of incident recovery is declared based on criteria, and incident-related documentation is completed."),
                ]
            },
            {
                "key": "RC.CO",
                "name": "Incident Recovery Communication",
                "description": "Restoration activities are coordinated with internal and external parties (e.g. coordinating centres, Internet Service Providers, owners of attacking systems, victims, other CSIRTs, and vendors).",
                "subcategories": [
                    ("RC.CO-03", "Recovery activities and progress are communicated", "Recovery activities and progress in restoring operational capabilities are communicated to designated internal and external stakeholders."),
                    ("RC.CO-04", "Public updates on incident recovery are shared", "Public updates on incident recovery are shared using approved methods and messaging."),
                ]
            },
        ]
    },
]

# ---------------------------------------------------------------------------
# Starter Use Cases for NIST CSF 2.0
# ---------------------------------------------------------------------------

NIST_USE_CASES = [
    {
        "title": "Cybersecurity Baseline Assessment",
        "description": "Establish an organisation-wide baseline maturity across all six NIST CSF 2.0 functions.",
        "business_value": "Provides a defensible, structured view of current cybersecurity posture for leadership and board reporting.",
        "owner_role": "CISO / Head of Cybersecurity",
        "core_functions": ["GV", "ID", "PR"],
        "upstream_functions": ["DE"],
        "downstream_functions": ["RS", "RC"],
    },
    {
        "title": "Incident Response Readiness",
        "description": "Assess the organisation's capability to detect, respond to, and recover from cybersecurity incidents.",
        "business_value": "Reduces mean time to detect and respond to incidents, limiting operational and reputational impact.",
        "owner_role": "Head of Security Operations",
        "core_functions": ["DE", "RS", "RC"],
        "upstream_functions": ["ID", "PR"],
        "downstream_functions": ["GV"],
    },
    {
        "title": "Cybersecurity Governance Review",
        "description": "Evaluate the maturity of cybersecurity governance, risk management strategy, and policy frameworks.",
        "business_value": "Strengthens accountability, risk-informed decision making, and regulatory alignment.",
        "owner_role": "CRO / CISO",
        "core_functions": ["GV"],
        "upstream_functions": ["ID"],
        "downstream_functions": ["PR", "DE", "RS", "RC"],
    },
    {
        "title": "Supply Chain Risk Assessment",
        "description": "Assess cybersecurity risk management practices across the supply chain and third-party ecosystem.",
        "business_value": "Reduces exposure to supplier-introduced vulnerabilities and strengthens third-party risk programmes.",
        "owner_role": "Head of Procurement / CISO",
        "core_functions": ["GV.SC", "ID.RA"],
        "upstream_functions": ["GV", "ID"],
        "downstream_functions": ["PR", "RS"],
    },
    {
        "title": "Protect and Detect Maturity",
        "description": "Deep-dive assessment of technical controls maturity across protection and detection capabilities.",
        "business_value": "Identifies gaps in technical security controls and monitoring capabilities to prioritise investment.",
        "owner_role": "Head of Security Architecture",
        "core_functions": ["PR", "DE"],
        "upstream_functions": ["ID", "GV"],
        "downstream_functions": ["RS", "RC"],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def table_exists(conn, table):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def load_checkpoint():
    if Path(CHECKPOINT_FILE).exists():
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {"completed": []}


def save_checkpoint(data):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f)


def ai_generate_descriptors(capability_key, capability_name, capability_description, category_name, function_name):
    """Call Claude API to generate L1-L5 maturity descriptors for a NIST CSF capability."""
    try:
        import anthropic
    except ImportError:
        print("  ! anthropic package not available — using stub descriptors")
        return _stub_descriptors(capability_name)

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""You are an expert in cybersecurity maturity assessment. Generate L1-L5 maturity level descriptors for the following NIST CSF 2.0 subcategory.

Framework: NIST CSF 2.0
Function: {function_name}
Category: {category_name}
Subcategory ID: {capability_key}
Subcategory Name: {capability_name}
Description: {capability_description}

Meridant's maturity level names are:
- L1: Ad Hoc
- L2: Defined
- L3: Integrated
- L4: Intelligent
- L5: Adaptive

For each level, provide:
- capability_state: A 2-3 sentence description of what the organisation looks like at this level for THIS specific subcategory
- key_indicators: 3-4 bullet-style indicators (pipe-separated string) that would evidence this level
- scoring_criteria: A single sentence describing what an assessor should look for to confirm this level

Return ONLY a JSON array with exactly 5 objects, one per level (L1 to L5):
[
  {{
    "level": 1,
    "level_name": "Ad Hoc",
    "capability_state": "...",
    "key_indicators": "indicator1 | indicator2 | indicator3",
    "scoring_criteria": "..."
  }},
  ...
]"""

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text.strip()
            # Strip markdown fences
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"    Retry {attempt + 1}/{MAX_RETRIES} after {delay:.1f}s ({e})")
                time.sleep(delay)
            else:
                print(f"    Failed after {MAX_RETRIES} attempts — using stub")
                return _stub_descriptors(capability_name)


def _stub_descriptors(capability_name):
    """Fallback stub descriptors if AI generation fails."""
    stubs = [
        {"level": 1, "level_name": "Ad Hoc", "capability_state": f"{capability_name} is performed reactively with no defined process.", "key_indicators": "No documented process | Reactive only | Inconsistent execution", "scoring_criteria": "No evidence of a defined or repeatable process exists."},
        {"level": 2, "level_name": "Defined", "capability_state": f"{capability_name} has a documented process that is followed consistently.", "key_indicators": "Process documented | Training exists | Roles defined", "scoring_criteria": "A documented process exists and is followed by relevant personnel."},
        {"level": 3, "level_name": "Integrated", "capability_state": f"{capability_name} is integrated with related processes and measured.", "key_indicators": "Integrated with adjacent processes | Metrics tracked | Regular review", "scoring_criteria": "Process is integrated with related organisational processes and performance is measured."},
        {"level": 4, "level_name": "Intelligent", "capability_state": f"{capability_name} is data-driven and continuously optimised.", "key_indicators": "Quantitative metrics | Automated monitoring | Trend analysis | Predictive capability", "scoring_criteria": "Performance is managed quantitatively and decisions are data-driven."},
        {"level": 5, "level_name": "Adaptive", "capability_state": f"{capability_name} is continuously improved based on threat intelligence and industry benchmarking.", "key_indicators": "Continuous improvement | Benchmarked externally | Proactive adaptation | Industry leadership", "scoring_criteria": "The organisation continuously adapts and improves based on emerging threats and industry benchmarks."},
    ]
    return stubs


# ---------------------------------------------------------------------------
# Seed functions
# ---------------------------------------------------------------------------

def seed_framework_registry(conn, dry_run=False):
    """Register NIST CSF 2.0 in Next_Framework."""
    print("\n[1] Registering NIST CSF 2.0 in Next_Framework")

    existing = conn.execute(
        "SELECT id FROM Next_Framework WHERE framework_key = 'NIST_CSF_2'",
    ).fetchone()

    if existing:
        fw_id = existing[0]
        print(f"  . Already registered as framework_id = {fw_id}")
        return fw_id

    if dry_run:
        print("  [dry-run] Would INSERT NIST_CSF_2 into Next_Framework")
        return -1

    conn.execute("""
        INSERT INTO Next_Framework (
            framework_key, framework_name, version, status,
            is_native, label_level1, label_level2, label_level3
        ) VALUES (
            'NIST_CSF_2',
            'NIST Cybersecurity Framework',
            '2.0',
            'active',
            0,
            'Function',
            'Category',
            'Subcategory'
        )
    """)
    fw_id = conn.execute(
        "SELECT id FROM Next_Framework WHERE framework_key = 'NIST_CSF_2'"
    ).fetchone()[0]
    print(f"  + Registered as framework_id = {fw_id}")
    return fw_id


def seed_taxonomy(conn, fw_id, dry_run=False):
    """Seed Functions, Categories, Subcategories."""
    print("\n[2] Seeding taxonomy (Functions → Categories → Subcategories)")

    pillar_map = {}   # function_key → domain_id
    domain_map = {}   # category_key → subdomain_id
    cap_map = {}      # subcategory_key → capability_id

    total_caps = 0

    for function in NIST_CSF2_TAXONOMY:
        # Pillar (Function)
        existing_pillar = conn.execute(
            "SELECT id FROM Next_Domain WHERE domain_name = ? AND framework_id = ?",
            (function["name"], fw_id)
        ).fetchone()

        if existing_pillar:
            pillar_id = existing_pillar[0]
        elif dry_run:
            pillar_id = -1
            print(f"  [dry-run] Pillar: {function['key']} — {function['name']}")
        else:
            conn.execute("""
                INSERT INTO Next_Domain (domain_name, domain_description, framework_id, version)
                VALUES (?, ?, ?, 'NIST_CSF_2.0')
            """, (function["name"], function["description"], fw_id))
            pillar_id = conn.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]
            print(f"  + Pillar: {function['key']} — {function['name']}")

        pillar_map[function["key"]] = pillar_id

        for category in function["categories"]:
            # Domain (Category)
            existing_domain = conn.execute(
                "SELECT id FROM Next_SubDomain WHERE subdomain_name = ? AND domain_id = ?",
                (category["name"], pillar_id)
            ).fetchone()

            if existing_domain:
                domain_id = existing_domain[0]
            elif dry_run:
                domain_id = -1
            else:
                conn.execute("""
                    INSERT INTO Next_SubDomain (domain_id, subdomain_name, subdomain_description, framework_id)
                    VALUES (?, ?, ?, ?)
                """, (pillar_id, category["name"], category["description"], fw_id))
                domain_id = conn.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]

            domain_map[category["key"]] = domain_id

            for (sub_key, sub_name, sub_desc) in category["subcategories"]:
                # Capability (Subcategory)
                existing_cap = conn.execute(
                    "SELECT id FROM Next_Capability WHERE capability_name = ? AND framework_id = ?",
                    (sub_key, fw_id)
                ).fetchone()

                if existing_cap:
                    cap_id = existing_cap[0]
                elif dry_run:
                    cap_id = -1
                    total_caps += 1
                else:
                    conn.execute("""
                        INSERT INTO Next_Capability (
                            domain_id, subdomain_id, capability_name,
                            capability_description, framework_id, category
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (pillar_id, domain_id, sub_key, sub_desc, fw_id, sub_name))
                    cap_id = conn.execute(
                        "SELECT last_insert_rowid()"
                    ).fetchone()[0]
                    total_caps += 1

                cap_map[sub_key] = cap_id

    if not dry_run:
        print(f"  ✓ {total_caps} capabilities seeded")
    else:
        print(f"  [dry-run] Would seed {total_caps} capabilities across 6 functions")

    return pillar_map, domain_map, cap_map


def seed_maturity_descriptors(conn, fw_id, cap_map, dry_run=False):
    """Generate and seed L1-L5 maturity descriptors via Claude API."""
    print("\n[3] Generating maturity descriptors (L1-L5 per capability)")
    print(f"    Model: {ANTHROPIC_MODEL}")
    print(f"    Total calls: {len(cap_map) * 5} | Est. time: 15-25 min")
    print(f"    Checkpoint: {CHECKPOINT_FILE}\n")

    checkpoint = load_checkpoint()
    completed = set(checkpoint.get("completed", []))
    skipped = 0
    generated = 0
    failed = 0

    # Build a lookup: sub_key → (function_name, category_name, cap_name, cap_desc)
    cap_context = {}
    for function in NIST_CSF2_TAXONOMY:
        for category in function["categories"]:
            for (sub_key, sub_name, sub_desc) in category["subcategories"]:
                cap_context[sub_key] = (
                    function["name"], category["name"], sub_name, sub_desc
                )

    total = len(cap_map)
    for i, (sub_key, cap_id) in enumerate(cap_map.items(), 1):
        if sub_key in completed:
            skipped += 1
            continue

        if cap_id == -1:
            continue

        ctx = cap_context.get(sub_key, ("Unknown", "Unknown", sub_key, ""))
        function_name, category_name, cap_name, cap_desc = ctx

        print(f"  [{i:3d}/{total}] {sub_key} — {cap_name[:50]}")

        if dry_run:
            print(f"    [dry-run] Would generate descriptors")
            continue

        # Check if descriptors already exist
        existing = conn.execute(
            "SELECT COUNT(*) FROM Next_CapabilityLevel WHERE capability_id = ? AND framework_id = ?",
            (cap_id, fw_id)
        ).fetchone()[0]

        if existing >= 5:
            completed.add(sub_key)
            skipped += 1
            continue

        descriptors = ai_generate_descriptors(
            sub_key, cap_name, cap_desc, category_name, function_name
        )

        if descriptors:
            # Delete any partial rows first
            conn.execute(
                "DELETE FROM Next_CapabilityLevel WHERE capability_id = ? AND framework_id = ?",
                (cap_id, fw_id)
            )
            for d in descriptors:
                conn.execute("""
                    INSERT INTO Next_CapabilityLevel (
                        capability_id, level, level_name,
                        capability_state, key_indicators, scoring_criteria, framework_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    cap_id, d["level"], d["level_name"],
                    d["capability_state"], d["key_indicators"],
                    d["scoring_criteria"], fw_id
                ))
            conn.commit()
            completed.add(sub_key)
            generated += 1
            save_checkpoint({"completed": list(completed)})

            # Polite delay to avoid rate limits
            time.sleep(0.5)
        else:
            failed += 1

    print(f"\n  ✓ Generated: {generated} | Skipped (existing): {skipped} | Failed: {failed}")

    # Clean up checkpoint on full completion
    if not dry_run and failed == 0:
        Path(CHECKPOINT_FILE).unlink(missing_ok=True)
        print("  ✓ Checkpoint cleared")


def seed_use_cases(conn, fw_id, pillar_map, cap_map, dry_run=False):
    """Seed starter NIST CSF 2.0 use cases."""
    print("\n[4] Seeding starter use cases")

    for uc in NIST_USE_CASES:
        existing = conn.execute(
            "SELECT id FROM Next_UseCase WHERE usecase_title = ? AND framework_id = ?",
            (uc["title"], fw_id)
        ).fetchone()

        if existing:
            print(f"  . Already exists: {uc['title']}")
            continue

        if dry_run:
            print(f"  [dry-run] Would INSERT use case: {uc['title']}")
            continue

        conn.execute("""
            INSERT INTO Next_UseCase (usecase_title, usecase_description, business_value, owner_role, framework_id, version)
            VALUES (?, ?, ?, ?, ?, 'NIST_CSF_2.0')
        """, (uc["title"], uc["description"], uc["business_value"], uc["owner_role"], fw_id))
        uc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Seed impact weights by function
        caps_inserted = 0
        for function in NIST_CSF2_TAXONOMY:
            fkey = function["key"]
            if fkey in uc.get("core_functions", []) or any(
                fkey.startswith(cf) for cf in uc.get("core_functions", [])
            ):
                weight = 5
            elif fkey in uc.get("upstream_functions", []):
                weight = 3
            else:
                weight = 1

            for category in function["categories"]:
                for (sub_key, _, _) in category["subcategories"]:
                    cap_id = cap_map.get(sub_key)
                    if cap_id and cap_id != -1:
                        conn.execute("""
                            INSERT OR IGNORE INTO Next_UseCaseCapabilityImpact
                            (usecase_id, capability_id, impact_weight, maturity_target, feasibility_score)
                            VALUES (?, ?, ?, 3, 3)
                        """, (uc_id, cap_id, weight))
                        caps_inserted += 1

        print(f"  + {uc['title']} ({caps_inserted} capability weights)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed NIST CSF 2.0 into meridant_frameworks.db")
    parser.add_argument("--taxonomy-only", action="store_true", help="Seed taxonomy only, skip descriptor generation")
    parser.add_argument("--descriptors-only", action="store_true", help="Generate descriptors only (taxonomy must exist)")
    parser.add_argument("--use-cases-only", action="store_true", help="Seed use cases only")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, no DB writes")
    args = parser.parse_args()

    print("Meridant Matrix — NIST CSF 2.0 Seed")
    print(f"DB: {FRAMEWORKS_DB}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}\n")

    if not Path(FRAMEWORKS_DB).exists():
        print(f"ERROR: {FRAMEWORKS_DB} not found")
        print("Check MERIDANT_FRAMEWORKS_DB_PATH env var")
        sys.exit(1)

    conn = sqlite3.connect(FRAMEWORKS_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL mode omitted — Windows Docker bind mounts don't support .shm file creation

    try:
        # Register framework
        fw_id = seed_framework_registry(conn, dry_run=args.dry_run)
        if not args.dry_run:
            conn.commit()

        if args.descriptors_only:
            # Get existing cap_map from DB
            rows = conn.execute(
                "SELECT capability_name, id FROM Next_Capability WHERE framework_id = ?", (fw_id,)
            ).fetchall()
            cap_map = {row[0]: row[1] for row in rows}
            pillar_map = {}
        else:
            pillar_map, domain_map, cap_map = seed_taxonomy(conn, fw_id, dry_run=args.dry_run)
            if not args.dry_run:
                conn.commit()

        if not args.use_cases_only and not (args.taxonomy_only):
            seed_maturity_descriptors(conn, fw_id, cap_map, dry_run=args.dry_run)

        if not args.descriptors_only:
            seed_use_cases(conn, fw_id, pillar_map, cap_map, dry_run=args.dry_run)
            if not args.dry_run:
                conn.commit()

        print(f"\n{'='*60}")
        print("NIST CSF 2.0 seed complete")
        print(f"{'='*60}")
        print(f"framework_id : {fw_id}")
        print(f"Labels       : Function / Category / Subcategory")

        if not args.dry_run:
            cap_count = conn.execute(
                "SELECT COUNT(*) FROM Next_Capability WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]
            desc_count = conn.execute(
                "SELECT COUNT(*) FROM Next_CapabilityLevel WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]
            uc_count = conn.execute(
                "SELECT COUNT(*) FROM Next_UseCase WHERE framework_id = ?", (fw_id,)
            ).fetchone()[0]
            print(f"Capabilities : {cap_count}")
            print(f"Descriptors  : {desc_count} (of {cap_count * 5} total)")
            print(f"Use cases    : {uc_count}")
        print(f"{'='*60}\n")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

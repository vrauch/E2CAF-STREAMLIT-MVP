"""
seed_upload_test.py — Create a test assessment with no responses + matching answer CSV.

Usage (inside Docker):
    docker compose exec app python scripts/seed_upload_test.py

What it does:
  1. Creates a Client + Assessment record (status = 'in_progress', no responses)
  2. Creates AssessmentCapability rows for all UC 32 capabilities
  3. Writes  outputs/upload_test_UC32_answers.csv  — ready to upload at Step 4

The CSV uses all three response types (maturity_1_5 / yes_no_evidence / free_text)
so you can verify the upload parser handles each correctly.

Pass --clean to remove a previous run before re-inserting.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import sqlite3

# ── DB paths ─────────────────────────────────────────────────────────────────
# Frameworks DB (read) — Next_* tables
FRAMEWORKS_DB = (
    os.getenv("MERIDANT_FRAMEWORKS_DB_PATH")
    or os.getenv("TMM_DB_PATH")
    or "/app/data/e2caf.db"
)
# Assessments DB (write) — Assessment*, Client tables
ASSESSMENTS_DB = (
    os.getenv("MERIDANT_ASSESSMENTS_DB_PATH")
    or os.getenv("TMM_DB_PATH")
    or "/app/data/meridant.db"
)

# ── constants ────────────────────────────────────────────────────────────────
CLIENT_NAME   = "Upload Test — Acme Datacenter"
ENGAGEMENT    = "Datacenter Transformation Readiness"
USE_CASE_NAME = "Datacenter Transformation"
USECASE_ID    = 32
CONSULTANT    = "vrauch"
OUTPUT_CSV    = Path(__file__).parent.parent / "outputs" / "upload_test_UC32_answers.csv"

# ── UC 32 capabilities (hardcoded from framework DB query) ───────────────────
# Format: (capability_id, capability_name, domain_name, subdomain_name, capability_role)
UC32_CAPS = [
    (310, "Digital Twin & Simulation",                      "Innovation",           "Innovation Enablement Value Chain",  "Core"),
    (114, "Low Code Application Platforms",                 "Applications",         "Architecture and Design",            "Downstream"),
    (128, "Data Retention",                                 "Applications",         "Governance Standards & Policies",    "Downstream"),
    (130, "Automation",                                     "Applications",         "Operations",                         "Downstream"),
    (145, "Cloud Adoption",                                 "Applications",         "Strategy",                           "Downstream"),
    (149, "Data Driven Culture",                            "Data",                 "Data Strategy & Culture",            "Downstream"),
    (147, "Data Governance Organization",                   "Data",                 "Governance",                         "Downstream"),
    (150, "Meta Data Management",                           "Data",                 "Governance",                         "Downstream"),
    (85,  "Change Communications",                          "People",               "Communications",                     "Downstream"),
    (120, "People Innovation",                              "People",               "Culture",                            "Downstream"),
    (101, "Organizational change strategy and planning",    "People",               "Organizational Change Management",   "Downstream"),
    (29,  "API Security",                                   "Security",             "Application Security",               "Downstream"),
    (38,  "Data Governance",                                "Security",             "Data Security",                      "Downstream"),
    (39,  "Data Mgmt.",                                     "Security",             "Data Security",                      "Downstream"),
    (40,  "Data Protection",                                "Security",             "Data Security",                      "Downstream"),
    (43,  "Cybersecurity Strategy",                         "Security",             "Governance, Risk, and Compliance",   "Downstream"),
    (45,  "Information Security Management",                "Security",             "Governance, Risk, and Compliance",   "Downstream"),
    (46,  "Integrated IT/OT Security",                      "Security",             "Governance, Risk, and Compliance",   "Downstream"),
    (48,  "OT Security Strategy",                           "Security",             "Governance, Risk, and Compliance",   "Downstream"),
    (58,  "Container Security",                             "Security",             "Infrastructure & Platform Security", "Downstream"),
    (59,  "Device Security",                                "Security",             "Infrastructure & Platform Security", "Downstream"),
    (60,  "Network Security",                               "Security",             "Infrastructure & Platform Security", "Downstream"),
    (61,  "Server/Endpoint Security",                       "Security",             "Infrastructure & Platform Security", "Downstream"),
    (62,  "Serverless Security",                            "Security",             "Infrastructure & Platform Security", "Downstream"),
    (63,  "Software-Defined Infrastructure",                "Security",             "Infrastructure & Platform Security", "Downstream"),
    (64,  "Storage Security",                               "Security",             "Infrastructure & Platform Security", "Downstream"),
    (69,  "Physical Security Officer Mgmt.",                "Security",             "Physical Security",                  "Downstream"),
    (70,  "Physical Security Policies & Standards",         "Security",             "Physical Security",                  "Downstream"),
    (73,  "Change, Configuration, and Release Mgmt.",       "Security",             "Security Operations",                "Downstream"),
    (25,  "Cloud Benchmarking",                             "Strategy & Governance","Vendor Management",                  "Downstream"),
]

# ── question templates (3 per capability, one of each type) ─────────────────
Q_TMPL = [
    (
        "maturity_1_5",
        "How would you rate the current maturity level of {name} within your organisation?",
        "Rate 1–5: 1=Not defined, 2=Informal/ad-hoc, 3=Defined process, 4=Measured & governed, 5=Optimised",
    ),
    (
        "yes_no_evidence",
        "Is there documented evidence that {name} practices are in place and producing outcomes?",
        "Yes = fully implemented with evidence; Partial = in progress or partial; No = not yet started",
    ),
    (
        "free_text",
        "Describe your organisation's current approach to {name}, including key challenges and recent initiatives.",
        "Describe openly — cover current state, gaps, and any active investment or plans",
    ),
]

# ── per-capability scores, answers, notes (keyed by capability_id) ──────────
# score = maturity_1_5 score; yes_no = answer for yes_no_evidence question;
# notes = free_text answer
ANSWERS: dict[int, tuple[int, str, str]] = {
    310: (2, "No",      "Digital twin capability is aspirational only. No production deployment exists. A small PoC was run in 2024 using vendor-provided tooling but was not continued."),
    114: (3, "Partial", "Low-code platforms are used by two business units for workflow automation. Governance and standards are informal — no enterprise-wide policy yet."),
    128: (3, "Partial", "Data retention policies exist for regulatory data but are not uniformly applied across all application tiers. Some legacy systems retain data indefinitely."),
    130: (3, "Partial", "Automation is applied to infrastructure provisioning (Terraform) but application release pipelines are largely manual. A tooling review is underway."),
    145: (4, "Yes",     "Cloud adoption strategy is formally documented and approved by the board. Two major workloads migrated to public cloud in FY25. FinOps practice established."),
    149: (2, "No",      "Data-driven culture is limited to the analytics team. Business units rely on gut feel and manual reporting. No formal data literacy programme exists."),
    147: (2, "Partial", "A data governance working group was formed in Q3 2025 but has not yet produced policy. Data ownership is unclear across most business domains."),
    150: (2, "No",      "Metadata management is ad-hoc. No enterprise metadata catalogue. Data dictionaries exist in spreadsheets maintained by individual teams."),
    85:  (3, "Partial", "Change communications are issued for major IT changes but the process is inconsistent. No dedicated change communications role or template library."),
    120: (3, "Partial", "People innovation initiatives include a quarterly hackathon and a small innovation fund. Participation is voluntary and adoption of outputs is low."),
    101: (3, "Yes",     "OCM strategy exists and is applied to major transformation programmes. Day-to-day change is handled informally. External consultants used for large programmes."),
    29:  (3, "Partial", "API security standards are defined for new development but legacy APIs are not covered. No automated API gateway scanning in production yet."),
    38:  (2, "No",      "Data governance from a security perspective is fragmented. DLP tools are licensed but not fully deployed. Classification scheme is not enforced at ingestion."),
    39:  (3, "Partial", "Data management practices cover structured data in core systems. Unstructured and shadow data stores are not inventoried or governed."),
    40:  (3, "Partial", "Data protection controls are applied to PII and financial data. Encryption at rest is standard; encryption in transit gaps exist on internal networks."),
    43:  (3, "Yes",     "Cybersecurity strategy is reviewed annually and aligned to ISO 27001. Risk register is maintained. Strategy lacks quantified risk appetite thresholds."),
    45:  (4, "Yes",     "ISMS is implemented and certified to ISO 27001. Internal audits conducted biannually. Scope covers corporate systems; OT environment is excluded."),
    46:  (2, "No",      "IT/OT security integration is minimal. OT systems are air-gapped but exceptions are not tracked. No unified SOC visibility across IT and OT environments."),
    48:  (2, "No",      "OT security strategy is informal and reactive. No dedicated OT security team. Vendor patching schedules are not enforced."),
    58:  (2, "Partial", "Container security scanning is configured in the CI pipeline for new services. Runtime security (Falco/Sysdig) is not deployed. Image signing not enforced."),
    59:  (3, "Yes",     "Device management is handled via Intune for corporate endpoints. BYOD policy is enforced. IoT device inventory is incomplete for manufacturing floor assets."),
    60:  (4, "Yes",     "Network security is mature — microsegmentation deployed in the datacentre, NGFWs at perimeter, quarterly penetration tests conducted. SD-WAN rollout in progress."),
    61:  (4, "Yes",     "Endpoint detection and response (EDR) deployed across 98% of corporate endpoints. Server hardening baselines documented and enforced via configuration management."),
    62:  (2, "No",      "Serverless functions are used in two microservices but security controls are developer-defined. No policy framework or automated scanning in place."),
    63:  (2, "Partial", "Software-defined infrastructure is being piloted for the new datacentre zone. Policy-as-code tooling (OPA) is in evaluation. Production rollout not started."),
    64:  (3, "Partial", "Storage security includes encryption at rest for SAN/NAS. Access controls are role-based but review cadence is annual. Immutable backup strategy under review."),
    69:  (3, "Yes",     "Physical security is managed by a dedicated security officer. Badge access logs are reviewed weekly. CCTV coverage is complete for datacentre floors."),
    70:  (4, "Yes",     "Physical security policies and standards are documented and reviewed annually. Aligned to ISO 27001 Annex A. Visitor management procedures enforced."),
    73:  (3, "Partial", "Change management process follows ITIL. CAB reviews changes weekly. Emergency change procedures exist but post-implementation reviews are inconsistently completed."),
    25:  (2, "No",      "Cloud benchmarking is informal — spot comparisons done during procurement cycles only. No continuous benchmarking tool or cost optimisation programme in place."),
}


def get_assessments_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(ASSESSMENTS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def clean(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("SELECT id FROM Client WHERE client_name = ?", (CLIENT_NAME,))
    row = cur.fetchone()
    if not row:
        print("Nothing to clean — client not found.")
        return
    client_id = row["id"]
    cur.execute("SELECT id FROM Assessment WHERE client_id = ?", (client_id,))
    for a in cur.fetchall():
        aid = a["id"]
        for tbl in ("AssessmentResponse", "AssessmentCapability", "AssessmentFinding",
                    "AssessmentRecommendation", "Assessment"):
            try:
                cur.execute(f"DELETE FROM {tbl} WHERE assessment_id = ?", (aid,))
            except Exception:
                pass
        print(f"  Deleted assessment {aid}")
    cur.execute("DELETE FROM Client WHERE id = ?", (client_id,))
    conn.commit()
    print(f"  Deleted client '{CLIENT_NAME}'")


def caps_as_dicts() -> list[dict]:
    """Return the hardcoded UC32 capability list as dicts."""
    return [
        {
            "capability_id":  cid,
            "capability_name": name,
            "domain_name":    domain,
            "subdomain_name": subdomain,
            "capability_role": role,
        }
        for cid, name, domain, subdomain, role in UC32_CAPS
    ]


def seed_db(conn: sqlite3.Connection, caps: list[dict]) -> int:
    cur = conn.cursor()
    now = datetime.now().isoformat()

    # ── Client ──
    cur.execute(
        "INSERT INTO Client (client_name, industry, sector, country, created_at) VALUES (?,?,?,?,?)",
        (CLIENT_NAME, "Technology", "Enterprise IT", "Australia", now),
    )
    client_id = cur.lastrowid

    # ── Assessment ──
    # Ensure consultant_name column exists (inline migration)
    try:
        cur.execute("ALTER TABLE Assessment ADD COLUMN consultant_name TEXT")
    except Exception:
        pass
    cur.execute(
        """INSERT INTO Assessment
               (client_id, engagement_name, use_case_name, intent_text,
                usecase_id, assessment_mode, consultant_name, status, created_at)
           VALUES (?,?,?,?,?,?,?,'in_progress',?)""",
        (
            client_id,
            ENGAGEMENT,
            USE_CASE_NAME,
            "Assess readiness for datacentre transformation including cloud migration, "
            "security posture, and operational modernisation.",
            USECASE_ID,
            "predefined",
            CONSULTANT,
            now,
        ),
    )
    assessment_id = cur.lastrowid
    print(f"  Created assessment id={assessment_id} for client '{CLIENT_NAME}'")

    # ── AssessmentCapability ──
    cap_rows = [
        (
            assessment_id,
            c["capability_id"],
            c["capability_name"],
            c["domain_name"],
            c["subdomain_name"],
            c["capability_role"],
            ANSWERS.get(c["capability_id"], (3, "Partial", ""))[0],  # ai_score from our answers
            "AI-scored during upload test seeding.",
            3,  # target_maturity
        )
        for c in caps
    ]
    cur.executemany(
        """INSERT INTO AssessmentCapability
               (assessment_id, capability_id, capability_name, domain_name,
                subdomain_name, capability_role, ai_score, rationale, target_maturity)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        cap_rows,
    )
    conn.commit()
    print(f"  Inserted {len(cap_rows)} AssessmentCapability rows (no responses)")
    return assessment_id


def write_csv(caps: list[dict]) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in caps:
        cid   = c["capability_id"]
        cname = c["capability_name"]
        dom   = c["domain_name"]
        sub   = c["subdomain_name"]
        role  = c["capability_role"]
        score, yes_no, notes = ANSWERS.get(cid, (3, "Partial", "No specific notes provided."))

        for q_type, q_tmpl, guidance in Q_TMPL:
            question = q_tmpl.format(name=cname)
            if q_type == "maturity_1_5":
                row_score, row_answer, row_notes = score, "", ""
            elif q_type == "yes_no_evidence":
                row_score, row_answer, row_notes = "", yes_no, ""
            else:  # free_text
                row_score, row_answer, row_notes = "", "", notes
            rows.append({
                "capability_id":   cid,
                "capability_name": cname,
                "domain":          dom,
                "subdomain":       sub,
                "capability_role": role,
                "question":        question,
                "response_type":   q_type,
                "guidance":        guidance,
                "score":           row_score,
                "answer":          row_answer,
                "notes":           row_notes,
            })

    fieldnames = ["capability_id", "capability_name", "domain", "subdomain",
                  "capability_role", "question", "response_type", "guidance",
                  "score", "answer", "notes"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} rows → {OUTPUT_CSV}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="Remove previous run first")
    args = parser.parse_args()

    print(f"Assessments DB : {ASSESSMENTS_DB}")
    conn = get_assessments_conn()

    if args.clean:
        print("Cleaning previous run...")
        clean(conn)

    # Guard against duplicate
    cur = conn.cursor()
    cur.execute("SELECT id FROM Client WHERE client_name = ?", (CLIENT_NAME,))
    if cur.fetchone():
        print(f"Client '{CLIENT_NAME}' already exists — pass --clean to reset.")
        sys.exit(0)

    caps = caps_as_dicts()
    print(f"Using {len(caps)} hardcoded UC 32 capabilities")

    assessment_id = seed_db(conn, caps)
    write_csv(caps)

    print(f"\n✓ Done.")
    print(f"  Assessment ID : {assessment_id}")
    print(f"  Answer CSV    : {OUTPUT_CSV}")
    print(f"\nNext steps:")
    print(f"  1. Open the app and go to Create Assessment")
    print(f"  2. Step 1 — use client '{CLIENT_NAME}', select predefined use case '{USE_CASE_NAME}'")
    print(f"  3. Complete Steps 2b and 3 to generate questions")
    print(f"  4. At Step 4 — choose 'Offline' mode and upload the CSV")
    print(f"     File: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()

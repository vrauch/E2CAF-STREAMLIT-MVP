# -*- coding: utf-8 -*-
"""
Seed 3 realistic test assessments into the TMM database.

Each uses a different question style:
  1. Maturity (1-5)        -- Meridian Retail Group    / Application Modernization
  2. Yes/No + Evidence     -- HealthBridge Systems      / Data Governance
  3. Workshop (free text)  -- Pinnacle Financial Svcs   / Cloud Engineering

Run from the project root:
    .venv/Scripts/python.exe scripts/seed_test_assessments.py
"""
from __future__ import annotations

import io
import os
import sys
import sqlite3
import random
from datetime import datetime, timedelta
from collections import defaultdict

# Force UTF-8 stdout so Unicode prints cleanly on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Path + env setup ──────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Load .env before any project imports so API key is in os.environ
from dotenv import dotenv_values as _dv
for _k, _v in _dv(os.path.join(ROOT, ".env")).items():
    if _v is not None:
        os.environ[_k] = _v

from src.meridant_client import MeridantClient
from src.assessment_builder import analyze_use_case_readonly
from src.question_generator import generate_questions_for_capability

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
print(f"API key:  {'SET' if os.environ.get('ANTHROPIC_API_KEY') else 'MISSING - check .env'}")

tmm = MeridantClient(
    frameworks_db_path=FRAMEWORKS_PATH,
    assessments_db_path=ASSESSMENTS_PATH,
)
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

def score_for(avg: float, spread: float, rng: random.Random) -> int:
    return max(1, min(5, round(avg + rng.gauss(0, spread))))

def yn_for(yes_prob: float, partial_prob: float, rng: random.Random) -> str:
    r = rng.random()
    if r < yes_prob:
        return "Yes"
    if r < yes_prob + partial_prob:
        return "Partial"
    return "No"

YN_MAP = {"Yes": 3, "Partial": 2, "No": 1}

WORKSHOP_NOTES = {
    1: "Team acknowledges this is ad hoc. No consistent process exists.",
    2: "Some informal practices in place but not standardised or documented.",
    3: "Process is defined and followed by most teams. Some gaps remain in tooling.",
    4: "Well-governed with metrics. Continuous improvement culture is evident.",
    5: "Fully optimised and largely automated. A clear leading practice.",
}

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
            key = (r["capability_role"], r["domain"], r["subdomain"],
                   r["capability_name"], r["capability_id"])
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
        dom_scores.append({"domain": dom, "avg_score": avg,
                           "target": tgt, "gap": round(tgt - avg, 1)})

    all_avgs = [c["avg_score"] for c in cap_scores]
    overall = round(sum(all_avgs) / len(all_avgs), 1) if all_avgs else 0.0
    return cap_scores, dom_scores, overall

def risk_label(score):
    if score is None: return ""
    if score < 2:     return "High"
    if score < 3:     return "Medium"
    return "Low"

# ── Insert a complete assessment ──────────────────────────────────────────────

def insert_assessment(
    client_name, industry, sector, country,
    engagement_name, use_case_name, usecase_id, intent_text, assessment_mode,
    caps_by_role, responses, domain_targets, created_days_ago=0,
):
    now = datetime.now()
    created_at   = (now - timedelta(days=created_days_ago)).isoformat()
    completed_at = (now - timedelta(days=max(0, created_days_ago - 1))).isoformat()

    # Client
    cur = con.cursor()
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

    # Assessment header
    assessment_id = run(
        "INSERT INTO Assessment"
        " (client_id, engagement_name, use_case_name, intent_text,"
        "  usecase_id, assessment_mode, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'in_progress', ?)",
        [client_id, engagement_name, use_case_name, intent_text,
         usecase_id, assessment_mode, created_at],
    )

    # AssessmentCapability rows
    cap_rows = []
    for role, caps in caps_by_role.items():
        for c in caps:
            cap_rows.append((
                assessment_id, int(c.capability_id),
                c.capability_name, c.domain_name, c.subdomain_name,
                role, None, getattr(c, "rationale", ""),
                domain_targets.get(c.domain_name, 3),
            ))
    run_many(
        "INSERT INTO AssessmentCapability"
        " (assessment_id, capability_id, capability_name, domain_name,"
        "  subdomain_name, capability_role, ai_score, rationale, target_maturity)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        cap_rows,
    )

    # AssessmentResponse rows
    run_many(
        "INSERT INTO AssessmentResponse"
        " (assessment_id, capability_id, capability_name, domain, subdomain,"
        "  capability_role, question, response_type, score, answer, notes)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(assessment_id,
          int(r["capability_id"]), r["capability_name"],
          r["domain"], r["subdomain"], r["capability_role"],
          r["question"], r["response_type"],
          r.get("score"), r.get("answer"), r.get("notes", ""))
         for r in responses],
    )

    # Findings
    cap_scores, dom_scores, overall = compute_findings(responses, domain_targets)
    run("UPDATE Assessment SET overall_score=?, status='complete', completed_at=? WHERE id=?",
        [overall, completed_at, assessment_id])

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

    print(f"  -> Assessment #{assessment_id}: {client_name} / {use_case_name}"
          f"  overall={overall}  domains={len(dom_scores)}  caps={len(cap_scores)}")
    return assessment_id


# ─────────────────────────────────────────────────────────────────────────────
# Assessment definitions
# ─────────────────────────────────────────────────────────────────────────────

ASSESSMENTS = [
    {
        "client_name":     "Meridian Retail Group",
        "industry":        "Retail",
        "sector":          "E-Commerce & Omnichannel",
        "country":         "Australia",
        "engagement_name": "Digital Platform Uplift -- FY25",
        "usecase_id":      19,
        "use_case_name":   "Application Modernization & Migration",
        "intent_text": (
            "Meridian Retail Group is modernising its legacy monolithic e-commerce platform "
            "to a cloud-native microservices architecture. The goal is to improve deployment "
            "velocity, scalability during peak trading events, and reduce the cost of "
            "maintaining a decade-old on-premises stack."
        ),
        "assessment_mode": "predefined",
        "q_style":         "Maturity (1\u20135)",
        "score_profile":   {"mean": 2.1, "spread": 0.7},
        "domain_targets":  {
            "Applications": 4, "DevOps": 3, "Security": 3,
            "Strategy & Governance": 3, "Data": 3, "Operations": 3, "People": 3,
        },
        "created_days_ago": 14,
    },
    {
        "client_name":     "HealthBridge Systems",
        "industry":        "Healthcare",
        "sector":          "Digital Health & Analytics",
        "country":         "United Kingdom",
        "engagement_name": "Data Governance Maturity Review 2025",
        "usecase_id":      13,
        "use_case_name":   "Data Governance",
        "intent_text": (
            "HealthBridge Systems must establish a robust enterprise data governance framework "
            "to meet NHS digital standards and GDPR obligations. The intent is enabling trusted "
            "traceable clinical data flows across 14 integrated care systems while providing "
            "auditable lineage for regulatory reporting and AI-driven diagnostics."
        ),
        "assessment_mode": "predefined",
        "q_style":         "Evidence (Yes/No + notes)",
        "yn_profile":      {"yes_prob": 0.28, "partial_prob": 0.42},
        "domain_targets":  {
            "Data": 4, "Security": 3, "Strategy & Governance": 3,
            "Applications": 3, "People": 3, "Operations": 3,
        },
        "created_days_ago": 7,
    },
    {
        "client_name":     "Pinnacle Financial Services",
        "industry":        "Financial Services",
        "sector":          "Banking & Capital Markets",
        "country":         "Singapore",
        "engagement_name": "Cloud Platform Engineering Assessment Q2 2025",
        "usecase_id":      24,
        "use_case_name":   "Cloud Engineering",
        "intent_text": (
            "Pinnacle Financial Services is investing in cloud-native platform engineering to "
            "accelerate product delivery and meet MAS TRM guidelines. This assessment examines "
            "DevOps, infrastructure-as-code, and SRE practices to identify capability gaps "
            "blocking a shift from quarterly releases to continuous delivery across 30+ squads."
        ),
        "assessment_mode": "predefined",
        "q_style":         "Workshop (discussion)",
        "score_profile":   {"mean": 3.2, "spread": 0.6},
        "domain_targets":  {
            "DevOps": 4, "Applications": 4, "Operations": 4,
            "Security": 3, "People": 3, "Strategy & Governance": 3,
        },
        "created_days_ago": 3,
    },
]

MAX_CORE       = 5
MAX_UPSTREAM   = 4
MAX_DOWNSTREAM = 3

# ─────────────────────────────────────────────────────────────────────────────

def main():
    rng = random.Random(42)

    for idx, defn in enumerate(ASSESSMENTS, start=1):
        print(f"\n{'='*60}")
        print(f"Assessment {idx}: {defn['client_name']} / {defn['use_case_name']}")
        print(f"  Style: {defn['q_style']}")

        print("  Loading capabilities (AI ranking)...", flush=True)
        _, core_caps, upstream_caps, downstream_caps, _, _ = analyze_use_case_readonly(
            tmm, defn["intent_text"], core_k=MAX_CORE,
        )
        upstream_caps   = upstream_caps[:MAX_UPSTREAM]
        downstream_caps = downstream_caps[:MAX_DOWNSTREAM]

        print(f"  Capabilities: {len(core_caps)} core | "
              f"{len(upstream_caps)} upstream | {len(downstream_caps)} downstream")

        caps_by_role = {
            "Core":       core_caps,
            "Upstream":   upstream_caps,
            "Downstream": downstream_caps,
        }

        all_responses = []
        role_bias = {"Core": 0.0, "Upstream": 0.2, "Downstream": 0.35}

        for role, caps in caps_by_role.items():
            for cap in caps:
                cap_dict = {
                    "capability_id":   cap.capability_id,
                    "capability_name": cap.capability_name,
                    "domain_name":     cap.domain_name,
                    "subdomain_name":  cap.subdomain_name,
                }
                label = cap.capability_name[:48]
                print(f"    [{role:10}] {label:50} ... ", end="", flush=True)

                try:
                    questions = generate_questions_for_capability(
                        use_case=defn["use_case_name"],
                        cap=cap_dict,
                        role=role,
                        questions_per_capability=3,
                        style=defn["q_style"],
                    )
                except Exception as e:
                    print(f"ERROR: {e}")
                    continue

                print(f"{len(questions)}q")

                for q_obj in questions:
                    resp = {
                        "capability_id":   q_obj.capability_id,
                        "capability_name": q_obj.capability_name,
                        "domain":          q_obj.domain,
                        "subdomain":       q_obj.subdomain,
                        "capability_role": q_obj.capability_role,
                        "question":        q_obj.question,
                        "response_type":   q_obj.response_type,
                        "notes":           "",
                        "score":           None,
                        "answer":          None,
                    }

                    q_style = defn["q_style"]
                    if q_style == "Maturity (1\u20135)":
                        prof = defn["score_profile"]
                        resp["score"] = score_for(
                            prof["mean"] + role_bias[role], prof["spread"], rng
                        )

                    elif q_style == "Evidence (Yes/No + notes)":
                        prof  = defn["yn_profile"]
                        answ  = yn_for(prof["yes_prob"], prof["partial_prob"], rng)
                        resp["answer"] = answ
                        resp["notes"]  = {
                            "Yes":     "Policy documented and consistently applied. Evidence reviewed.",
                            "Partial": "Framework exists but not uniformly adopted across all teams.",
                            "No":      "Not yet in place. Identified as a priority gap.",
                        }[answ]

                    else:   # Workshop
                        prof = defn["score_profile"]
                        s    = score_for(prof["mean"] + role_bias[role], prof["spread"], rng)
                        resp["score"] = s
                        resp["notes"] = WORKSHOP_NOTES[s]

                    all_responses.append(resp)

        print(f"  Total responses: {len(all_responses)}")

        insert_assessment(
            client_name=defn["client_name"],
            industry=defn["industry"],
            sector=defn["sector"],
            country=defn["country"],
            engagement_name=defn["engagement_name"],
            use_case_name=defn["use_case_name"],
            usecase_id=defn["usecase_id"],
            intent_text=defn["intent_text"],
            assessment_mode=defn["assessment_mode"],
            caps_by_role=caps_by_role,
            responses=all_responses,
            domain_targets=defn.get("domain_targets", {}),
            created_days_ago=defn.get("created_days_ago", 0),
        )

    print("\nDone. 3 test assessments created.")
    con.close()


if __name__ == "__main__":
    main()

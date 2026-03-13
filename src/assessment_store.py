"""Persistence layer for completed assessments."""

import json
from datetime import datetime
from src.meridant_client import MeridantClient


def _ensure_narrative_column(client: MeridantClient) -> None:
    """
    Add findings_narrative column to Assessment if it doesn't already exist.
    SQLite raises OperationalError on duplicate ADD COLUMN — we suppress it.
    This is a one-time inline migration, safe to call on every write path.
    """
    try:
        client.write("ALTER TABLE Assessment ADD COLUMN findings_narrative TEXT", [])
    except Exception:
        pass  # Column already exists


def save_narrative(client: MeridantClient, assessment_id: int, narrative: str) -> None:
    """
    Persist (or overwrite) the executive summary narrative for an assessment.
    Creates the column if this is the first time it's been used.
    """
    _ensure_narrative_column(client)
    client.write(
        "UPDATE Assessment SET findings_narrative = ? WHERE id = ?",
        [narrative, assessment_id],
    )


def save_assessment(client: MeridantClient, session: dict) -> int:
    """
    Persists a completed assessment to the database.
    Creates or reuses a Client record.
    Returns the new assessment_id.
    """

    # ── 1. Get or create Client ──
    client_name = session.get("client_name", "Unknown Client")
    existing = client.query(
        "SELECT id FROM Client WHERE client_name = ? ORDER BY id DESC LIMIT 1",
        [client_name]
    )
    if existing["rows"]:
        client_id = existing["rows"][0]["id"]
    else:
        result = client.write(
            """
            INSERT INTO Client (client_name, industry, sector, country, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                client_name,
                session.get("client_industry", ""),
                session.get("client_sector", ""),
                session.get("client_country", ""),
                datetime.now().isoformat(),
            ]
        )
        client_id = result["lastrowid"]

    # ── 2. Insert Assessment header ──
    result = client.write(
        """
        INSERT INTO Assessment
            (client_id, engagement_name, use_case_name, intent_text,
             usecase_id, assessment_mode, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'in_progress', ?)
        """,
        [
            client_id,
            session.get("engagement_name", ""),
            session.get("use_case_name", ""),
            session.get("intent_text", ""),
            session.get("selected_usecase_id"),          # FK to Next_UseCase — NULL for custom
            session.get("assessment_mode", "custom"),
            datetime.now().isoformat(),
        ]
    )
    assessment_id = result["lastrowid"]

    # ── 3. Insert capabilities ──
    domain_targets = session.get("domain_targets", {})
    all_caps = (
        [(c, "Core") for c in session.get("core_caps", [])] +
        [(c, "Upstream") for c in session.get("upstream_caps", [])] +
        [(c, "Downstream") for c in session.get("downstream_caps", [])]
    )
    if all_caps:
        cap_rows = [
            (
                assessment_id,
                int(c["capability_id"]),
                c["capability_name"],
                c["domain_name"],
                c["subdomain_name"],
                role,
                c.get("score") or c.get("ai_score"),
                c.get("rationale", ""),
                domain_targets.get(c["domain_name"], 3),
            )
            for c, role in all_caps
        ]
        client.write_many(
            """
            INSERT INTO AssessmentCapability
                (assessment_id, capability_id, capability_name, domain_name,
                 subdomain_name, capability_role, ai_score, rationale, target_maturity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            cap_rows
        )

    # ── 4. Insert responses ──
    responses = session.get("responses", {})
    if responses:
        response_rows = [
            (
                assessment_id,
                int(r["capability_id"]),
                r["capability_name"],
                r["domain"],
                r["subdomain"],
                r["capability_role"],
                r["question"],
                r["response_type"],
                r.get("score"),
                r.get("answer"),
                r.get("notes", ""),
            )
            for r in responses.values()
        ]
        client.write_many(
            """
            INSERT INTO AssessmentResponse
                (assessment_id, capability_id, capability_name, domain, subdomain,
                 capability_role, question, response_type, score, answer, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            response_rows
        )

    return assessment_id


def _risk(score) -> str:
    """Return a risk label based on avg_score."""
    if score is None:
        return ""
    if score < 2:
        return "🔴 High"
    if score < 3:
        return "🟡 Medium"
    return "🟢 Low"


def save_findings(
    client: MeridantClient,
    assessment_id: int,
    cap_scores: list[dict],
    dom_scores: list[dict],
    overall_score: float,
) -> None:
    """
    Persists computed capability scores, domain scores, and overall score
    back to the database for the given assessment.
    Uses a single AssessmentFinding table with finding_type = 'capability' | 'domain'.
    """

    # Ensure findings_narrative column exists (one-time inline migration)
    _ensure_narrative_column(client)

    # ── Update overall score, status, and completed_at on Assessment header ──
    client.write(
        """
        UPDATE Assessment
        SET overall_score = ?, status = 'complete', completed_at = ?
        WHERE id = ?
        """,
        [overall_score, datetime.now().isoformat(), assessment_id],
    )

    rows = []

    # ── Domain findings ──
    for d in (dom_scores or []):
        rows.append((
            assessment_id, "domain",
            d.get("domain", ""),          # domain
            None,                          # capability_id
            None,                          # capability_name
            None,                          # capability_role
            None,                          # subdomain
            d.get("avg_score"),
            int(d.get("target", 3)),
            d.get("gap"),
            _risk(d.get("avg_score")),
        ))

    # ── Capability findings ──
    for c in (cap_scores or []):
        rows.append((
            assessment_id, "capability",
            c.get("domain", ""),           # domain
            c.get("capability_id"),        # capability_id
            c.get("capability_name", ""),  # capability_name
            c.get("capability_role", ""),  # capability_role
            c.get("subdomain"),            # subdomain
            c.get("avg_score"),
            int(c.get("target", 3)),
            c.get("gap"),
            _risk(c.get("avg_score")),
        ))

    if rows:
        client.write_many(
            """
            INSERT INTO AssessmentFinding
                (assessment_id, finding_type, domain, capability_id,
                 capability_name, capability_role, subdomain,
                 avg_score, target_maturity, gap, risk_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def save_recommendations(
    client: MeridantClient,
    assessment_id: int,
    recommendations: list[dict],
) -> None:
    """
    Persists AI-generated recommendations for an assessment.
    Idempotent — clears existing rows then re-inserts.
    JSON-encodes list fields before storage.
    """
    client.write(
        "DELETE FROM AssessmentRecommendation WHERE assessment_id = ?",
        [assessment_id],
    )

    if not recommendations:
        return

    rows = [
        (
            assessment_id,
            r.get("capability_id"),
            r.get("capability_name", ""),
            r.get("domain"),
            r.get("capability_role"),
            r.get("current_score"),
            r.get("target_maturity"),
            r.get("gap"),
            r.get("priority_tier"),
            r.get("effort_estimate"),
            r.get("narrative"),
            json.dumps(r.get("recommended_actions") or []),
            json.dumps(r.get("enabling_dependencies") or []),
            json.dumps(r.get("success_indicators") or []),
            None,                               # hpe_relevance — removed from AI output
            datetime.now().isoformat(),
        )
        for r in recommendations
    ]

    client.write_many(
        """
        INSERT INTO AssessmentRecommendation
            (assessment_id, capability_id, capability_name, domain,
             capability_role, current_score, target_maturity, gap,
             priority_tier, effort_estimate, narrative,
             recommended_actions, enabling_dependencies,
             success_indicators, hpe_relevance, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def load_recommendations(client: MeridantClient, assessment_id: int) -> list[dict]:
    """
    Loads persisted recommendations for an assessment.
    JSON-decodes list fields.
    Returns empty list if none exist.
    """
    res = client.query(
        """
        SELECT * FROM AssessmentRecommendation
        WHERE assessment_id = ?
        ORDER BY
            CASE priority_tier WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END,
            gap DESC
        """,
        [assessment_id],
    )
    rows = res.get("rows", [])
    for r in rows:
        r["recommended_actions"]   = json.loads(r.get("recommended_actions")  or "[]")
        r["enabling_dependencies"] = json.loads(r.get("enabling_dependencies") or "[]")
        r["success_indicators"]    = json.loads(r.get("success_indicators")   or "[]")
        # Ensure in-memory key 'narrative' is always populated
        r["narrative"] = r.get("narrative") or ""
    return rows


def list_assessments(client: MeridantClient) -> list[dict]:
    """Return a summary list of all assessments, newest first."""
    res = client.query("""
        SELECT a.id, c.client_name, a.engagement_name, a.use_case_name,
               a.status, a.created_at, a.overall_score
        FROM Assessment a
        LEFT JOIN Client c ON a.client_id = c.id
        ORDER BY a.created_at DESC
    """)
    return res.get("rows", [])


def load_assessment(client: MeridantClient, assessment_id: int):
    """
    Load a complete assessment from the database.
    Returns a dict with keys: assessment, capabilities, responses.
    Returns None if the assessment is not found.
    """
    res = client.query(
        """
        SELECT a.*, c.client_name, c.industry, c.sector, c.country
        FROM Assessment a
        LEFT JOIN Client c ON a.client_id = c.id
        WHERE a.id = ?
        """,
        [int(assessment_id)]
    )
    rows = res.get("rows", [])
    if not rows:
        return None

    caps_res = client.query(
        "SELECT * FROM AssessmentCapability WHERE assessment_id = ? ORDER BY capability_role, capability_id",
        [int(assessment_id)]
    )
    resp_res = client.query(
        "SELECT * FROM AssessmentResponse WHERE assessment_id = ? ORDER BY capability_id",
        [int(assessment_id)]
    )
    return {
        "assessment":   rows[0],
        "capabilities": caps_res.get("rows", []),
        "responses":    resp_res.get("rows", []),
    }

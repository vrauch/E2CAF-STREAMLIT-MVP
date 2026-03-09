"""Persistence layer for completed assessments."""

from datetime import datetime
from src.tmm_client import TMMClient


def save_assessment(client: TMMClient, session: dict) -> int:
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
    client: TMMClient,
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


def list_assessments(client: TMMClient) -> list[dict]:
    """Return a summary list of all assessments, newest first."""
    res = client.query("""
        SELECT a.id, c.client_name, a.engagement_name, a.use_case_name,
               a.status, a.created_at, a.overall_score
        FROM Assessment a
        LEFT JOIN Client c ON a.client_id = c.id
        ORDER BY a.created_at DESC
    """)
    return res.get("rows", [])


def load_assessment(client: TMMClient, assessment_id: int):
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

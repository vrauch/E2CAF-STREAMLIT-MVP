"""Persistence layer for completed assessments."""

import json
from datetime import datetime
from src.meridant_client import MeridantClient

_narrative_column_ensured = False
_consultant_column_ensured = False
_framework_id_column_ensured = False
_roadmap_progress_table_ensured = False


def _ensure_narrative_column(client: MeridantClient) -> None:
    """
    Add findings_narrative column to Assessment if it doesn't already exist.
    Memoized — only runs the ALTER TABLE once per process.
    """
    global _narrative_column_ensured
    if _narrative_column_ensured:
        return
    try:
        client.write("ALTER TABLE Assessment ADD COLUMN findings_narrative TEXT", [])
    except Exception:
        pass  # Column already exists
    _narrative_column_ensured = True


def _ensure_consultant_column(client: MeridantClient) -> None:
    """
    Add consultant_name column to Assessment if it doesn't already exist.
    Memoized — only runs the ALTER TABLE once per process.
    """
    global _consultant_column_ensured
    if _consultant_column_ensured:
        return
    try:
        client.write("ALTER TABLE Assessment ADD COLUMN consultant_name TEXT", [])
    except Exception:
        pass  # Column already exists
    _consultant_column_ensured = True


def _ensure_framework_id_column(client: MeridantClient) -> None:
    """
    Add framework_id column to Assessment if it doesn't already exist.
    Memoized — only runs the ALTER TABLE once per process.
    """
    global _framework_id_column_ensured
    if _framework_id_column_ensured:
        return
    try:
        client.write("ALTER TABLE Assessment ADD COLUMN framework_id INTEGER DEFAULT 1", [])
    except Exception:
        pass  # Column already exists
    _framework_id_column_ensured = True


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


def _get_or_create_client(client: MeridantClient, session: dict) -> int:
    """Get existing client_id by name, or INSERT a new Client row. Returns client_id."""
    client_name = session.get("client_name", "Unknown Client")
    existing = client.query(
        "SELECT id FROM Client WHERE client_name = ? ORDER BY id DESC LIMIT 1",
        [client_name],
    )
    if existing["rows"]:
        return existing["rows"][0]["id"]
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
        ],
    )
    return result["lastrowid"]


def _build_cap_rows(assessment_id: int, session: dict) -> list:
    """Build the list of tuples for an AssessmentCapability bulk INSERT."""
    domain_targets = session.get("domain_targets", {})
    all_caps = (
        [(c, "Core")       for c in session.get("core_caps", [])] +
        [(c, "Upstream")   for c in session.get("upstream_caps", [])] +
        [(c, "Downstream") for c in session.get("downstream_caps", [])]
    )
    return [
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


_CAP_INSERT_SQL = """
INSERT INTO AssessmentCapability
    (assessment_id, capability_id, capability_name, domain_name,
     subdomain_name, capability_role, ai_score, rationale, target_maturity)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_RESP_INSERT_SQL = """
INSERT INTO AssessmentResponse
    (assessment_id, capability_id, capability_name, domain, subdomain,
     capability_role, question, response_type, score, answer, notes)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def save_assessment_shell(client: MeridantClient, session: dict) -> int:
    """
    Create (or update) just the Client + Assessment header row — no capabilities or responses.

    Call this at the end of Step 1 to get an assessment_id early so every subsequent step
    can save incrementally.  Idempotent: if session already contains 'assessment_id', the
    existing row is updated in place and the same ID is returned.
    """
    _ensure_consultant_column(client)
    _ensure_framework_id_column(client)
    client_id = _get_or_create_client(client, session)

    existing_id = session.get("assessment_id")
    if existing_id:
        client.write(
            """
            UPDATE Assessment
            SET client_id = ?, engagement_name = ?, use_case_name = ?,
                intent_text = ?, usecase_id = ?, assessment_mode = ?,
                consultant_name = ?, framework_id = ?
            WHERE id = ?
            """,
            [
                client_id,
                session.get("engagement_name", ""),
                session.get("use_case_name", ""),
                session.get("intent_text", ""),
                session.get("selected_usecase_id"),
                session.get("assessment_mode", "custom"),
                session.get("authenticated_username", ""),
                session.get("framework_id", 1),
                existing_id,
            ],
        )
        return existing_id

    result = client.write(
        """
        INSERT INTO Assessment
            (client_id, engagement_name, use_case_name, intent_text,
             usecase_id, assessment_mode, consultant_name, framework_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)
        """,
        [
            client_id,
            session.get("engagement_name", ""),
            session.get("use_case_name", ""),
            session.get("intent_text", ""),
            session.get("selected_usecase_id"),
            session.get("assessment_mode", "custom"),
            session.get("authenticated_username", ""),
            session.get("framework_id", 1),
            datetime.now().isoformat(),
        ],
    )
    return result["lastrowid"]


def upsert_capabilities(client: MeridantClient, assessment_id: int, session: dict) -> None:
    """
    Replace the AssessmentCapability rows for this assessment with the current session caps.
    Called at the end of Step 2b (after domain targets are confirmed).
    """
    client.write(
        "DELETE FROM AssessmentCapability WHERE assessment_id = ?",
        [assessment_id],
    )
    cap_rows = _build_cap_rows(assessment_id, session)
    if cap_rows:
        client.write_many(_CAP_INSERT_SQL, cap_rows)


def save_questions(
    client: MeridantClient, assessment_id: int, questions: list[dict]
) -> None:
    """
    Persist the generated question set as blank AssessmentResponse rows.
    score, answer, and notes are all NULL/empty — they are filled in at Step 4.
    Called after Step 3 question generation so the question set survives session expiry.
    Idempotent: clears existing response rows before inserting.
    """
    client.write(
        "DELETE FROM AssessmentResponse WHERE assessment_id = ?",
        [assessment_id],
    )
    if not questions:
        return
    rows = [
        (
            assessment_id,
            int(q["capability_id"]),
            q["capability_name"],
            q.get("domain", ""),
            q.get("subdomain", ""),
            q["capability_role"],
            q["question"],
            q["response_type"],
            None,   # score — filled at Step 4
            None,   # answer — filled at Step 4
            "",     # notes — filled at Step 4
        )
        for q in questions
    ]
    client.write_many(_RESP_INSERT_SQL, rows)


def save_assessment(client: MeridantClient, session: dict) -> int:
    """
    Persists a completed assessment to the database.
    Creates or reuses a Client record.
    Returns the assessment_id.

    If the session already contains an assessment_id (shell was created at Step 1 and
    questions were saved at Step 3), only the AssessmentResponse rows are replaced —
    the header and capabilities are left as-is.
    """
    existing_id = session.get("assessment_id")

    if existing_id:
        # ── Fast path: assessment already exists — update responses only ──
        client.write(
            "DELETE FROM AssessmentResponse WHERE assessment_id = ?",
            [existing_id],
        )
        responses = session.get("responses", {})
        if responses:
            response_rows = [
                (
                    existing_id,
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
            client.write_many(_RESP_INSERT_SQL, response_rows)
        return existing_id

    # ── Full path: no prior shell — insert everything (legacy / edge-case fallback) ──
    _ensure_consultant_column(client)
    _ensure_framework_id_column(client)
    client_id = _get_or_create_client(client, session)

    result = client.write(
        """
        INSERT INTO Assessment
            (client_id, engagement_name, use_case_name, intent_text,
             usecase_id, assessment_mode, consultant_name, framework_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)
        """,
        [
            client_id,
            session.get("engagement_name", ""),
            session.get("use_case_name", ""),
            session.get("intent_text", ""),
            session.get("selected_usecase_id"),
            session.get("assessment_mode", "custom"),
            session.get("authenticated_username", ""),
            session.get("framework_id", 1),
            datetime.now().isoformat(),
        ],
    )
    assessment_id = result["lastrowid"]

    cap_rows = _build_cap_rows(assessment_id, session)
    if cap_rows:
        client.write_many(_CAP_INSERT_SQL, cap_rows)

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
        client.write_many(_RESP_INSERT_SQL, response_rows)

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


_roadmap_table_ensured = False


def _ensure_roadmap_table(client: MeridantClient) -> None:
    global _roadmap_table_ensured
    if _roadmap_table_ensured:
        return
    client.write(
        """
        CREATE TABLE IF NOT EXISTS AssessmentRoadmap (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            roadmap_json TEXT NOT NULL,
            timeline_unit TEXT,
            horizon_months INTEGER,
            scope TEXT,
            generated_at TEXT DEFAULT (datetime('now'))
        )
        """,
        [],
    )
    _roadmap_table_ensured = True


def save_roadmap(
    client: MeridantClient,
    assessment_id: int,
    roadmap: dict,
    timeline_unit: str = "",
    horizon_months: int = 12,
    scope: str = "Core",
) -> None:
    """Persist the generated roadmap JSON for an assessment. Idempotent — replaces on re-generate."""
    _ensure_roadmap_table(client)
    client.write(
        "DELETE FROM AssessmentRoadmap WHERE assessment_id = ?",
        [assessment_id],
    )
    client.write(
        """
        INSERT INTO AssessmentRoadmap
            (assessment_id, roadmap_json, timeline_unit, horizon_months, scope, generated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            assessment_id,
            json.dumps(roadmap),
            timeline_unit,
            horizon_months,
            scope,
            datetime.now().isoformat(),
        ],
    )


def load_roadmap(client: MeridantClient, assessment_id: int) -> dict | None:
    """Load the persisted roadmap for an assessment. Returns None if not found."""
    _ensure_roadmap_table(client)
    res = client.query(
        "SELECT * FROM AssessmentRoadmap WHERE assessment_id = ? ORDER BY id DESC LIMIT 1",
        [assessment_id],
    )
    rows = res.get("rows", [])
    if not rows:
        return None
    row = rows[0]
    return {
        "roadmap": json.loads(row["roadmap_json"]),
        "timeline_unit": row.get("timeline_unit") or "Sprints (2 wks)",
        "horizon_months": row.get("horizon_months") or 12,
        "scope": row.get("scope") or "Core",
        "generated_at": row.get("generated_at"),
    }


def _ensure_roadmap_progress_table(client: MeridantClient) -> None:
    global _roadmap_progress_table_ensured
    if _roadmap_progress_table_ensured:
        return
    client.write(
        """
        CREATE TABLE IF NOT EXISTS AssessmentRoadmapProgress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            initiative_id TEXT NOT NULL,
            initiative_name TEXT,
            status TEXT DEFAULT 'not_started',
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(assessment_id, initiative_id)
        )
        """,
        [],
    )
    _roadmap_progress_table_ensured = True


def save_roadmap_progress(
    client: MeridantClient,
    assessment_id: int,
    progress: dict,
) -> None:
    """Persist initiative progress. progress is {initiative_id: status}."""
    _ensure_roadmap_progress_table(client)
    for init_id, status in progress.items():
        client.write(
            """
            INSERT INTO AssessmentRoadmapProgress
                (assessment_id, initiative_id, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(assessment_id, initiative_id)
            DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
            """,
            [assessment_id, init_id, status, datetime.now().isoformat()],
        )


def load_roadmap_progress(client: MeridantClient, assessment_id: int) -> dict:
    """Load initiative progress. Returns {initiative_id: status}."""
    _ensure_roadmap_progress_table(client)
    res = client.query(
        "SELECT initiative_id, status FROM AssessmentRoadmapProgress WHERE assessment_id = ?",
        [assessment_id],
    )
    return {r["initiative_id"]: r["status"] for r in res.get("rows", [])}


def list_assessments(client: MeridantClient, consultant_name: str | None = None) -> list[dict]:
    """Return a summary list of assessments, newest first.

    If consultant_name is provided, only assessments belonging to that consultant
    are returned. Pass None to return all (admin use).
    """
    _ensure_framework_id_column(client)
    if consultant_name:
        res = client.query(
            """
            SELECT a.id, c.client_name, a.engagement_name, a.use_case_name,
                   a.status, a.created_at, a.overall_score,
                   COALESCE(a.consultant_name, '') AS consultant_name,
                   COALESCE(a.framework_id, nu.framework_id, 1) AS framework_id
            FROM Assessment a
            LEFT JOIN Client c ON a.client_id = c.id
            LEFT JOIN Next_UseCase nu ON a.usecase_id = nu.id
            WHERE COALESCE(a.consultant_name, '') = ?
            ORDER BY a.created_at DESC
            """,
            [consultant_name],
        )
    else:
        res = client.query("""
            SELECT a.id, c.client_name, a.engagement_name, a.use_case_name,
                   a.status, a.created_at, a.overall_score,
                   COALESCE(a.consultant_name, '') AS consultant_name,
                   COALESCE(a.framework_id, nu.framework_id, 1) AS framework_id
            FROM Assessment a
            LEFT JOIN Client c ON a.client_id = c.id
            LEFT JOIN Next_UseCase nu ON a.usecase_id = nu.id
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

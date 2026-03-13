"""
Recommendation Engine — assembles per-capability DB context and orchestrates AI calls.

Exported function:
    build_recommendations(db, assessment_id, cap_scores, ...) -> list[dict]
"""

import logging
from src.meridant_client import MeridantClient
from src.ai_client import generate_gap_recommendations

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
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
);
"""


def _ensure_table(db: MeridantClient) -> None:
    db.write(_CREATE_TABLE_SQL, [])


# ── Priority / effort helpers ─────────────────────────────────────────────────

def _priority_tier(gap: float, capability_role: str, framework_phase: int | None) -> str:
    if framework_phase == 1:
        return "P1"
    if gap >= 2.0 or (capability_role == "Core" and gap >= 1.5):
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


# ── DB context loaders ────────────────────────────────────────────────────────

def _load_level_descriptor(db: MeridantClient, capability_id: int, level: int) -> str:
    """Return the capability_state + key_indicators text for a given capability/level."""
    res = db.query(
        """
        SELECT capability_state, key_indicators
        FROM Next_CapabilityLevel
        WHERE capability_id = ? AND level = ? AND level_name IS NOT NULL
        LIMIT 1
        """,
        [capability_id, level],
    )
    rows = res.get("rows", [])
    if not rows:
        return ""
    row = rows[0]
    parts = []
    if row.get("capability_state"):
        parts.append(row["capability_state"])
    if row.get("key_indicators"):
        parts.append(f"Key indicators: {row['key_indicators']}")
    return " ".join(parts)


def _load_responses(db: MeridantClient, assessment_id: int, capability_id: int) -> list[dict]:
    res = db.query(
        """
        SELECT question, response_type, score, answer, notes
        FROM AssessmentResponse
        WHERE assessment_id = ? AND capability_id = ?
        """,
        [assessment_id, capability_id],
    )
    return res.get("rows", [])


def _load_foundational_deps(db: MeridantClient, capability_id: int) -> list[str]:
    """Return names of capabilities that are Foundational prerequisites for this one."""
    res = db.query(
        """
        SELECT nc.capability_name
        FROM Next_CapabilityInterdependency dep
        JOIN Next_Capability nc ON nc.id = dep.source_capability_id
        WHERE dep.target_capability_id = ? AND dep.interaction_type_id = 1
        ORDER BY nc.capability_name
        """,
        [capability_id],
    )
    return [r["capability_name"] for r in res.get("rows", [])]


def _load_framework_phase(
    db: MeridantClient, capability_id: int, usecase_id: int | None
) -> int | None:
    if not usecase_id:
        return None
    res = db.query(
        """
        SELECT phase
        FROM Next_RoadmapStep
        WHERE usecase_id = ? AND capability_id = ?
        LIMIT 1
        """,
        [usecase_id, capability_id],
    )
    rows = res.get("rows", [])
    return rows[0]["phase"] if rows else None


# ── Main entry point ──────────────────────────────────────────────────────────

def build_recommendations(
    db: MeridantClient,
    assessment_id: int,
    cap_scores: list[dict],
    client_industry: str,
    intent_text: str,
    usecase_id: int | None = None,
    max_caps: int = 20,
    on_progress=None,
    client_country: str = "",
) -> list[dict]:
    """
    For each gap capability (up to max_caps), assembles DB context and calls AI
    to generate a structured recommendation.

    Args:
        db:               MeridantClient instance.
        assessment_id:    ID of the saved assessment.
        cap_scores:       List of capability score dicts from Step 5
                          (capability_id, capability_name, domain, capability_role,
                           avg_score, target, gap).
        client_industry:  Client industry string for AI context.
        intent_text:      The assessment intent statement.
        usecase_id:       FK to Next_UseCase (None for custom assessments).
        max_caps:         Maximum number of capabilities to process (bounds AI cost).
        on_progress:      Optional callback(current_idx, total, cap_name) for UI updates.
        client_country:   Client country / market for AI context.

    Returns:
        List of recommendation dicts, one per processed capability, sorted P1 → P3.
    """
    _ensure_table(db)

    # Filter to capabilities with a positive gap; sort by gap desc, Core first
    gap_caps = [c for c in cap_scores if (c.get("gap") or 0) > 0]
    gap_caps.sort(
        key=lambda c: (-(c.get("gap") or 0), 0 if c.get("capability_role") == "Core" else 1)
    )
    gap_caps = gap_caps[:max_caps]

    results = []

    for idx, cap in enumerate(gap_caps):
        cap_name = cap.get("capability_name", "Unknown")
        cap_id = cap.get("capability_id")
        current_score = float(cap.get("avg_score") or 0)
        target_maturity = int(cap.get("target") or 3)
        gap = float(cap.get("gap") or 0)
        capability_role = cap.get("capability_role", "")
        domain = cap.get("domain", "")

        if on_progress:
            on_progress(idx, len(gap_caps), cap_name)

        # Determine tier & effort before the AI call (passed as context constraints)
        framework_phase = (
            _load_framework_phase(db, cap_id, usecase_id) if cap_id else None
        )
        tier = _priority_tier(gap, capability_role, framework_phase)
        effort = _effort_estimate(gap)

        try:
            current_level = max(1, min(4, int(current_score)))  # cap at 4 so target is always higher
            current_desc = (
                _load_level_descriptor(db, cap_id, current_level) if cap_id else ""
            )
            target_desc = (
                _load_level_descriptor(db, cap_id, target_maturity) if cap_id else ""
            )
            responses = _load_responses(db, assessment_id, cap_id) if cap_id else []
            foundational_deps = (
                _load_foundational_deps(db, cap_id) if cap_id else []
            )

            ai_result = generate_gap_recommendations(
                capability_name=cap_name,
                domain=domain,
                capability_role=capability_role,
                current_score=current_score,
                target_maturity=target_maturity,
                gap=gap,
                priority_tier=tier,
                current_level_descriptor=current_desc,
                target_level_descriptor=target_desc,
                scored_responses=responses,
                foundational_deps=foundational_deps,
                framework_phase=framework_phase,
                client_industry=client_industry,
                intent_text=intent_text,
                client_country=client_country,
            )

            results.append(
                {
                    "capability_id": cap_id,
                    "capability_name": cap_name,
                    "domain": domain,
                    "capability_role": capability_role,
                    "current_score": current_score,
                    "target_maturity": target_maturity,
                    "gap": gap,
                    "priority_tier": tier,
                    "effort_estimate": effort,
                    **ai_result,
                }
            )

        except Exception as exc:
            logger.warning("Recommendation failed for '%s': %s", cap_name, exc)
            results.append(
                {
                    "capability_id": cap_id,
                    "capability_name": cap_name,
                    "domain": domain,
                    "capability_role": capability_role,
                    "current_score": current_score,
                    "target_maturity": target_maturity,
                    "gap": gap,
                    "priority_tier": tier,
                    "effort_estimate": effort,
                    "recommended_actions": [
                        "Recommendation generation failed — click Regenerate to retry."
                    ],
                    "enabling_dependencies": [],
                    "success_indicators": [],
                    "hpe_relevance": "",
                    "narrative": f"Could not generate recommendation: {exc}",
                }
            )

    if on_progress and gap_caps:
        on_progress(len(gap_caps), len(gap_caps), "Complete")

    # Return sorted P1 → P2 → P3, then by gap desc within tier
    tier_order = {"P1": 0, "P2": 1, "P3": 2}
    results.sort(key=lambda r: (tier_order.get(r["priority_tier"], 1), -r["gap"]))
    return results

"""
Remove legacy E2CAF and HPE branding from meridant_frameworks.db.

Changes:
  - Next_Domain.version:           E2CAF_Next_v1.0  -> MMTF_v1.0  (all 12 rows)
  - Next_UseCase.version:          E2CAF_Next_v1.0  -> MMTF_v1.0  (all rows)
  - Next_UseCase.usecase_description (id=35): remove E2CAF reference
  - Next_UseCase.business_value   (id=35): remove HPE Bold Goals reference
  - Next_FrameworkVersion.version_label (id=1): E2CAF Next Baseline -> MMTF Baseline
  - Next_FrameworkVersion.notes   (id=1): replace E2CAF references
  - Next_ModelMetadata.version    (id=1): E2CAF_Next_v1.0 -> MMTF_v1.0
  - Next_ModelMetadata.description (id=1): remove E2CAF reference

Safe to re-run -- uses targeted UPDATEs with WHERE clauses.
"""

from __future__ import annotations

import os
import sqlite3

DB_PATH = os.environ.get(
    "MERIDANT_FRAMEWORKS_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "meridant_frameworks.db"),
)


def run(db: sqlite3.Connection) -> None:
    changes: list[tuple[str, int]] = []

    # ── Next_Domain.version ───────────────────────────────────────────────────
    cur = db.execute(
        "UPDATE Next_Domain SET version = 'MMTF_v1.0' WHERE version = 'E2CAF_Next_v1.0'"
    )
    changes.append(("Next_Domain.version", cur.rowcount))

    # ── Next_UseCase.version ──────────────────────────────────────────────────
    cur = db.execute(
        "UPDATE Next_UseCase SET version = 'MMTF_v1.0' WHERE version = 'E2CAF_Next_v1.0'"
    )
    changes.append(("Next_UseCase.version", cur.rowcount))

    # ── Next_UseCase.usecase_description (id=35) ──────────────────────────────
    cur = db.execute(
        "UPDATE Next_UseCase SET usecase_description = ? WHERE id = 35",
        (
            "Full-spectrum MMTF maturity baseline assessment across all 12 domains and 292 "
            "capabilities. Establishes current state scores and target maturity levels to "
            "drive transformation roadmap prioritisation.",
        ),
    )
    changes.append(("Next_UseCase.usecase_description[35]", cur.rowcount))

    # ── Next_UseCase.business_value (id=35) ───────────────────────────────────
    cur = db.execute(
        "UPDATE Next_UseCase SET business_value = ? WHERE id = 35",
        (
            "Provides a structured, defensible foundation for enterprise transformation "
            "planning, investment prioritisation, and executive alignment.",
        ),
    )
    changes.append(("Next_UseCase.business_value[35]", cur.rowcount))

    # ── Next_FrameworkVersion.version_label (id=1) ────────────────────────────
    cur = db.execute(
        "UPDATE Next_FrameworkVersion SET version_label = 'MMTF Baseline' WHERE id = 1"
    )
    changes.append(("Next_FrameworkVersion.version_label[1]", cur.rowcount))

    # ── Next_FrameworkVersion.notes (id=1) ────────────────────────────────────
    cur = db.execute(
        "UPDATE Next_FrameworkVersion SET notes = ? WHERE id = 1",
        (
            "Initial MMTF framework population. 303 capabilities across 8 core domains "
            "(Strategy & Governance, Security, People, Applications, Data, DevOps, "
            "Innovation, Operations) plus 4 emerging domains (AI & Cognitive Systems, "
            "Intelligent Automation & Operations, Sustainability & Responsible Technology, "
            "Experience & Ecosystem Enablement). Full maturity level descriptors, "
            "interdependency graph, use case impact model, and roadmap scaffolding "
            "established.",
        ),
    )
    changes.append(("Next_FrameworkVersion.notes[1]", cur.rowcount))

    # ── Next_ModelMetadata.version (id=1) ─────────────────────────────────────
    cur = db.execute(
        "UPDATE Next_ModelMetadata SET version = 'MMTF_v1.0' WHERE id = 1"
    )
    changes.append(("Next_ModelMetadata.version[1]", cur.rowcount))

    # ── Next_ModelMetadata.description (id=1) ────────────────────────────────
    cur = db.execute(
        "UPDATE Next_ModelMetadata SET description = ? WHERE id = 1",
        (
            "Initialized as MMTF baseline with extended structures for maturity, "
            "interdependencies, and use-case impact mapping.",
        ),
    )
    changes.append(("Next_ModelMetadata.description[1]", cur.rowcount))

    db.commit()

    print("Migration complete:")
    for label, rowcount in changes:
        print(f"  {label}: {rowcount} row(s) updated")


if __name__ == "__main__":
    db = sqlite3.connect(DB_PATH)
    try:
        run(db)
    finally:
        db.close()

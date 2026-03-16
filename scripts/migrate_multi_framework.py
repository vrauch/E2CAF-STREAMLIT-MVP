#!/usr/bin/env python3
"""
migrate_multi_framework.py
==========================
Meridant Matrix — Multi-Framework Migration
Run from project root inside Docker:
    docker compose exec app python scripts/migrate_multi_framework.py
What this script does
---------------------
1. meridant_frameworks.db
   - Creates Next_Framework registry table
   - Adds label_level1 / label_level2 / label_level3 display columns
   - Seeds MMTF as framework_id = 1 (Pillar / Domain / Capability)
   - Adds framework_id FK column (DEFAULT 1) to all relevant content tables
2. meridant.db
   - Adds framework_id column (DEFAULT 1) to Assessment table
All operations are idempotent — safe to run multiple times.
All DDL runs inside a transaction; rolls back cleanly on any error.
"""
import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime
# ---------------------------------------------------------------------------
# Config — reads same env vars as MeridantClient
# ---------------------------------------------------------------------------
FRAMEWORKS_DB = os.getenv(
    "MERIDANT_FRAMEWORKS_DB_PATH",
    "/data/meridant_frameworks.db"
)
ASSESSMENTS_DB = os.getenv(
    "MERIDANT_ASSESSMENTS_DB_PATH",
    "/data/meridant.db"
)
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)
def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone()
    return row is not None
def add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str
) -> None:
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"  + {table}.{column}")
    else:
        print(f"  . {table}.{column} already exists — skipped")
# ---------------------------------------------------------------------------
# Migration 1: meridant_frameworks.db
# ---------------------------------------------------------------------------
FRAMEWORK_CONTENT_TABLES = [
    "Next_Domain",
    "Next_SubDomain",
    "Next_Capability",
    "Next_CapabilityLevel",
    "Next_UseCase",
    "Next_RoadmapStep",
    "Next_CapabilityInterdependency",
]
CREATE_NEXT_FRAMEWORK = """
CREATE TABLE IF NOT EXISTS Next_Framework (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    framework_key   TEXT    NOT NULL UNIQUE,
    framework_name  TEXT    NOT NULL,
    version         TEXT,
    status          TEXT    DEFAULT 'active'
                            CHECK(status IN ('active', 'draft', 'archived')),
    is_native       INTEGER DEFAULT 0,
    label_level1    TEXT    DEFAULT 'Pillar',
    label_level2    TEXT    DEFAULT 'Domain',
    label_level3    TEXT    DEFAULT 'Capability',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""
MMTF_SEED = """
INSERT OR IGNORE INTO Next_Framework (
    framework_key, framework_name, version, status,
    is_native, label_level1, label_level2, label_level3
) VALUES (
    'MMTF',
    'Meridant Matrix Transformation Framework',
    'v1.0',
    'active',
    1,
    'Pillar',
    'Domain',
    'Capability'
);
"""
def migrate_frameworks_db(db_path: str) -> None:
    print(f"\n{'='*60}")
    print(f"Migrating: {db_path}")
    print(f"{'='*60}")
    if not Path(db_path).exists():
        print(f"ERROR: {db_path} not found.")
        print("Check MERIDANT_FRAMEWORKS_DB_PATH env var.")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        with conn:
            # 1. Create Next_Framework table
            print("\n[1] Next_Framework registry")
            if not table_exists(conn, "Next_Framework"):
                conn.execute(CREATE_NEXT_FRAMEWORK)
                print("  + Created Next_Framework")
            else:
                print("  . Next_Framework already exists — checking columns")
                # Ensure label columns exist on pre-existing table
                add_column_if_missing(conn, "Next_Framework", "is_native",    "INTEGER DEFAULT 0")
                add_column_if_missing(conn, "Next_Framework", "label_level1", "TEXT DEFAULT 'Pillar'")
                add_column_if_missing(conn, "Next_Framework", "label_level2", "TEXT DEFAULT 'Domain'")
                add_column_if_missing(conn, "Next_Framework", "label_level3", "TEXT DEFAULT 'Capability'")
            # 2. Seed MMTF as framework_id = 1
            print("\n[2] Seeding MMTF (framework_id = 1)")
            conn.execute(MMTF_SEED)
            row = conn.execute(
                "SELECT id, framework_key, version FROM Next_Framework WHERE framework_key = 'MMTF'"
            ).fetchone()
            print(f"  . MMTF → id={row[0]}, key={row[1]}, version={row[2]}")
            # 3. Add framework_id to content tables
            print("\n[3] Adding framework_id FK to content tables")
            for table in FRAMEWORK_CONTENT_TABLES:
                if table_exists(conn, table):
                    add_column_if_missing(
                        conn, table, "framework_id",
                        "INTEGER DEFAULT 1"
                        # Note: REFERENCES omitted — SQLite forbids ALTER TABLE ADD COLUMN
                        # with both a DEFAULT and a FK constraint. The FK relationship is
                        # enforced at the application layer via MeridantClient's ATTACH pattern.
                    )
                else:
                    print(f"  ! {table} not found — skipped")
            # 4. Record migration in Next_ChangeRecord if it exists
            if table_exists(conn, "Next_ChangeRecord"):
                version_row = conn.execute(
                    "SELECT id FROM Next_FrameworkVersion WHERE status='published' ORDER BY id DESC LIMIT 1"
                ).fetchone() if table_exists(conn, "Next_FrameworkVersion") else None
                conn.execute("""
                    INSERT INTO Next_ChangeRecord (
                        version_id, change_category, change_type,
                        table_name, record_label, rationale, changed_by
                    ) VALUES (?, 'metadata', 'ADD', 'Next_Framework',
                        'Multi-framework migration',
                        'Added Next_Framework registry and framework_id columns for multi-framework support',
                        'Vernon Rauch')
                """, (version_row[0] if version_row else None,))
                print("\n[4] Logged to Next_ChangeRecord")
        print(f"\n✓ meridant_frameworks.db migration complete")
    except Exception as e:
        print(f"\nERROR during frameworks migration: {e}")
        raise
    finally:
        conn.close()
# ---------------------------------------------------------------------------
# Migration 2: meridant.db
# ---------------------------------------------------------------------------
def migrate_assessments_db(db_path: str) -> None:
    print(f"\n{'='*60}")
    print(f"Migrating: {db_path}")
    print(f"{'='*60}")
    if not Path(db_path).exists():
        print(f"ERROR: {db_path} not found.")
        print("Check MERIDANT_ASSESSMENTS_DB_PATH env var.")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        with conn:
            print("\n[1] Assessment table — adding framework_id")
            add_column_if_missing(
                conn, "Assessment", "framework_id",
                "INTEGER DEFAULT 1"
            )
            # Note: no FK constraint here — Assessment DB doesn't ATTACH
            # frameworks DB at migration time. The application layer enforces
            # the relationship via MeridantClient's ATTACH pattern.
        print(f"\n✓ meridant.db migration complete")
    except Exception as e:
        print(f"\nERROR during assessments migration: {e}")
        raise
    finally:
        conn.close()
# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify(frameworks_db: str, assessments_db: str) -> None:
    print(f"\n{'='*60}")
    print("Verification")
    print(f"{'='*60}")
    conn = sqlite3.connect(frameworks_db)
    try:
        frameworks = conn.execute(
            "SELECT id, framework_key, framework_name, version, is_native, "
            "label_level1, label_level2, label_level3 FROM Next_Framework"
        ).fetchall()
        print(f"\nNext_Framework rows: {len(frameworks)}")
        for fw in frameworks:
            native = "native" if fw[4] else "external"
            print(f"  [{fw[0]}] {fw[1]} — {fw[2]} {fw[3]} ({native})")
            print(f"       Labels: {fw[5]} / {fw[6]} / {fw[7]}")
        print("\nframework_id columns present:")
        for table in FRAMEWORK_CONTENT_TABLES:
            if table_exists(conn, table):
                has = column_exists(conn, table, "framework_id")
                status = "✓" if has else "✗"
                print(f"  {status} {table}")
    finally:
        conn.close()
    conn2 = sqlite3.connect(assessments_db)
    try:
        has = column_exists(conn2, "Assessment", "framework_id")
        status = "✓" if has else "✗"
        print(f"\n  {status} Assessment.framework_id (meridant.db)")
    finally:
        conn2.close()
    print(f"\n{'='*60}")
    print("Migration complete —", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(f"{'='*60}\n")
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Meridant Matrix — Multi-Framework Migration")
    print(f"Frameworks DB : {FRAMEWORKS_DB}")
    print(f"Assessments DB: {ASSESSMENTS_DB}")
    migrate_frameworks_db(FRAMEWORKS_DB)
    migrate_assessments_db(ASSESSMENTS_DB)
    verify(FRAMEWORKS_DB, ASSESSMENTS_DB)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migrate_split_db.py — Split e2caf.db into two purpose-specific databases.

  meridant_frameworks.db  — all Next_* tables (framework IP, local master)
  meridant.db             — all Assessment* + Client tables (client data)

Run inside Docker:
    docker compose exec app python scripts/migrate_split_db.py [source_db_path]

If source_db_path is omitted, reads TMM_DB_PATH from the environment (or .env).
Target paths read from MERIDANT_FRAMEWORKS_DB_PATH and MERIDANT_ASSESSMENTS_DB_PATH,
with sensible defaults alongside the source file.

Idempotent — if the target DB already exists and the table already has data,
the table is skipped (prints a notice).
"""
from __future__ import annotations

import io
import os
import sys
import sqlite3

# UTF-8 stdout on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ── Load .env if present ──────────────────────────────────────────────────────
try:
    from dotenv import dotenv_values as _dv
    for _k, _v in _dv(os.path.join(ROOT, ".env")).items():
        if _v is not None:
            os.environ[_k] = _v
except ImportError:
    pass

# ── Resolve paths ─────────────────────────────────────────────────────────────
if len(sys.argv) > 1:
    SOURCE_PATH = sys.argv[1]
else:
    SOURCE_PATH = os.environ.get("TMM_DB_PATH", "/data/e2caf.db")
    local_fallback = os.path.join(ROOT, "data", "e2caf.db")
    if not os.path.exists(SOURCE_PATH) and os.path.exists(local_fallback):
        SOURCE_PATH = local_fallback

data_dir = os.path.dirname(os.path.abspath(SOURCE_PATH))

FRAMEWORKS_PATH = os.environ.get(
    "MERIDANT_FRAMEWORKS_DB_PATH",
    os.path.join(data_dir, "meridant_frameworks.db"),
)
ASSESSMENTS_PATH = os.environ.get(
    "MERIDANT_ASSESSMENTS_DB_PATH",
    os.path.join(data_dir, "meridant.db"),
)

print(f"\n{'='*60}")
print("Meridant Matrix — DB Split Migration")
print(f"{'='*60}")
print(f"  Source  : {SOURCE_PATH}")
print(f"  Frameworks target : {FRAMEWORKS_PATH}")
print(f"  Assessments target: {ASSESSMENTS_PATH}")
print()


# ── Helpers ───────────────────────────────────────────────────────────────────

def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def copy_table(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    table: str,
) -> int:
    """
    Copy a single table (schema + data) from source_conn to target_conn.
    Returns number of rows copied, or -1 if skipped (already has data).
    """
    # Check if table already exists and has data in target
    existing = target_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table]
    ).fetchone()
    if existing:
        count = target_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if count > 0:
            print(f"    SKIP  {table} — already has {count} rows in target")
            return -1

    # Get CREATE TABLE statement from source
    schema_row = source_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", [table]
    ).fetchone()
    if not schema_row or not schema_row[0]:
        print(f"    WARN  {table} — no schema found, skipping")
        return 0

    create_sql = schema_row[0]
    # Ensure IF NOT EXISTS to avoid errors on re-run
    if "IF NOT EXISTS" not in create_sql.upper():
        create_sql = create_sql.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)

    target_conn.execute(create_sql)

    # Copy indexes
    idx_rows = source_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        [table],
    ).fetchall()
    for idx_row in idx_rows:
        try:
            target_conn.execute(idx_row[0])
        except sqlite3.OperationalError:
            pass  # index already exists

    # Copy data
    rows = source_conn.execute(f'SELECT * FROM "{table}"').fetchall()
    if rows:
        cols = len(rows[0])
        placeholders = ",".join(["?"] * cols)
        target_conn.executemany(
            f'INSERT OR IGNORE INTO "{table}" VALUES ({placeholders})', rows
        )

    target_conn.commit()
    return len(rows)


def run_migration(
    source_path: str,
    frameworks_path: str,
    assessments_path: str,
) -> None:
    if not os.path.exists(source_path):
        print(f"ERROR: Source DB not found at: {source_path}")
        sys.exit(1)

    source_conn = sqlite3.connect(source_path)
    all_tables = list_tables(source_conn)

    # Classify tables
    framework_tables = [t for t in all_tables if t.startswith("Next_")]
    assessment_tables = [
        t for t in all_tables
        if t.startswith("Assessment") or t == "Client"
    ]
    skipped_tables = [
        t for t in all_tables
        if t not in framework_tables and t not in assessment_tables
    ]

    print(f"Found {len(all_tables)} tables in source:")
    print(f"  Framework (Next_*) : {len(framework_tables)}")
    print(f"  Assessment/Client  : {len(assessment_tables)}")
    if skipped_tables:
        print(f"  Skipped (legacy)   : {len(skipped_tables)} — {', '.join(skipped_tables)}")
    print()

    # ── Copy framework tables ─────────────────────────────────────────────────
    print(f"[1/2] Copying framework tables → {frameworks_path}")
    fw_conn = sqlite3.connect(frameworks_path)
    fw_total = 0
    for table in framework_tables:
        n = copy_table(source_conn, fw_conn, table)
        if n >= 0:
            print(f"    OK    {table} ({n} rows)")
            fw_total += n
    fw_conn.close()
    print(f"  Done — {len(framework_tables)} tables, {fw_total} rows total\n")

    # ── Copy assessment tables ────────────────────────────────────────────────
    print(f"[2/2] Copying assessment tables → {assessments_path}")
    as_conn = sqlite3.connect(assessments_path)
    as_total = 0
    for table in assessment_tables:
        n = copy_table(source_conn, as_conn, table)
        if n >= 0:
            print(f"    OK    {table} ({n} rows)")
            as_total += n
    as_conn.close()
    print(f"  Done — {len(assessment_tables)} tables, {as_total} rows total\n")

    source_conn.close()

    # ── Verification ──────────────────────────────────────────────────────────
    print("Verification — row counts:")
    print(f"\n  meridant_frameworks.db:")
    fw_conn = sqlite3.connect(frameworks_path)
    for t in framework_tables:
        src_n = sqlite3.connect(source_path).execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        tgt_n = fw_conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        status = "✓" if src_n == tgt_n else "✗ MISMATCH"
        print(f"    {status}  {t}: source={src_n}, target={tgt_n}")
    fw_conn.close()

    print(f"\n  meridant.db:")
    as_conn = sqlite3.connect(assessments_path)
    for t in assessment_tables:
        src_n = sqlite3.connect(source_path).execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        tgt_n = as_conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        status = "✓" if src_n == tgt_n else "✗ MISMATCH"
        print(f"    {status}  {t}: source={src_n}, target={tgt_n}")
    as_conn.close()

    print(f"\n{'='*60}")
    print("Migration complete.")
    print(f"\nNext steps:")
    print(f"  1. Update your .env file:")
    print(f"       MERIDANT_FRAMEWORKS_DB_PATH={frameworks_path}")
    print(f"       MERIDANT_ASSESSMENTS_DB_PATH={assessments_path}")
    print(f"  2. Remove or comment out TMM_DB_PATH")
    print(f"  3. Run: docker compose up --build")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_migration(SOURCE_PATH, FRAMEWORKS_PATH, ASSESSMENTS_PATH)

#!/usr/bin/env python3
"""
repair_wal.py
=============
Switches meridant_frameworks.db and meridant.db from WAL journal mode
back to DELETE (rollback) journal mode.

WAL mode does not work on Windows Docker bind mounts because SQLite
cannot create the .shm shared-memory file on virtual filesystems.

Run from project root inside Docker (with app stopped):
    docker compose run --rm app python scripts/repair_wal.py
"""
import os
import sqlite3
import sys
from pathlib import Path

FRAMEWORKS_DB = os.getenv("MERIDANT_FRAMEWORKS_DB_PATH", "/app/data/meridant_frameworks.db")
ASSESSMENTS_DB = os.getenv("MERIDANT_ASSESSMENTS_DB_PATH", "/app/data/meridant.db")


def repair_db(path: str, label: str) -> None:
    print(f"\n--- {label} ---")
    print(f"    Path: {path}")

    if not Path(path).exists():
        print(f"    SKIP — file not found")
        return

    try:
        conn = sqlite3.connect(path)

        # EXCLUSIVE locking mode MUST be set before any read/write operation.
        # It tells SQLite it is the sole connection, so it skips the .shm
        # shared-memory file entirely — the only way to connect to a WAL-mode
        # database on a filesystem that cannot create .shm files.
        conn.execute("PRAGMA locking_mode = EXCLUSIVE")

        # A dummy read forces SQLite to acquire the exclusive lock and open
        # the WAL file without needing .shm.
        conn.execute("SELECT 1").fetchone()

        # Switch back to DELETE (rollback) journal mode.
        # This checkpoints any pending WAL data into the main DB file
        # and rewrites the DB header to indicate rollback mode.
        result = conn.execute("PRAGMA journal_mode = DELETE").fetchone()
        print(f"    journal_mode → {result[0]}")

        # Verify
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        locking = conn.execute("PRAGMA locking_mode").fetchone()[0]
        print(f"    Verified: journal_mode={mode}, locking_mode={locking}")

        conn.close()
        print(f"    ✓ Repaired")

    except Exception as e:
        print(f"    ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("Meridant Matrix — WAL Repair")
    repair_db(FRAMEWORKS_DB, "meridant_frameworks.db")
    repair_db(ASSESSMENTS_DB, "meridant.db")
    print("\nDone. Both databases are now in DELETE journal mode.")
    print("WAL and SHM files (if any) can be safely deleted from data/")

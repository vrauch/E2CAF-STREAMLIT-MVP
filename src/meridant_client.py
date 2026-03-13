from __future__ import annotations

import os
import sqlite3
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

load_dotenv()

DEFAULT_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))


@dataclass
class MeridantClient:
    """
    SQLite client for Meridant Matrix.

    Supports two modes:
      - Split mode (recommended): frameworks_db_path + assessments_db_path
        Opens meridant_frameworks.db as the main connection and ATTACHes
        meridant.db. All table names are unique across the two DBs, so
        existing SQL queries resolve correctly without modification.
      - Legacy single-path mode: db_path only (backward-compat with e2caf.db)
    """
    db_path: Optional[str] = None              # legacy single-path mode
    frameworks_db_path: Optional[str] = None   # split mode: framework tables (Next_*)
    assessments_db_path: Optional[str] = None  # split mode: assessment tables (Assessment*/Client)

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the primary DB and ATTACH the secondary if split mode."""
        if self.frameworks_db_path and self.assessments_db_path:
            conn = sqlite3.connect(self.frameworks_db_path)
            conn.execute(
                f'ATTACH DATABASE "{self.assessments_db_path}" AS assessments'
            )
        else:
            conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, sql: str, params: list = None) -> dict:
        """
        Execute a SELECT query and return rows as a list of dicts.
        """
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(sql, params or [])
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            return {"rows": rows, "count": len(rows)}
        except Exception as e:
            return {"rows": [], "count": 0, "error": str(e)}

    def write(self, sql: str, params: list = None) -> dict:
        """
        Execute an INSERT, UPDATE, or DELETE query.
        Returns lastrowid and rowcount.
        """
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(sql, params or [])
            conn.commit()
            result = {"lastrowid": cur.lastrowid, "rowcount": cur.rowcount}
            conn.close()
            return result
        except Exception as e:
            return {"lastrowid": None, "rowcount": 0, "error": str(e)}

    def write_many(self, sql: str, params_list: list) -> dict:
        """
        Execute a batch INSERT using executemany.
        """
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.executemany(sql, params_list)
            conn.commit()
            result = {"rowcount": cur.rowcount}
            conn.close()
            return result
        except Exception as e:
            return {"rowcount": 0, "error": str(e)}


def get_client() -> MeridantClient:
    """
    Return a configured MeridantClient.

    Split mode (preferred): reads MERIDANT_FRAMEWORKS_DB_PATH and
    MERIDANT_ASSESSMENTS_DB_PATH from the environment.

    Legacy mode (fallback): reads TMM_DB_PATH (single DB, backward-compat).
    """
    fw_path = os.getenv("MERIDANT_FRAMEWORKS_DB_PATH")
    as_path = os.getenv("MERIDANT_ASSESSMENTS_DB_PATH")

    if fw_path and as_path:
        # Split mode
        missing = []
        if not os.path.exists(fw_path):
            missing.append(f"Frameworks DB not found at: {fw_path}")
        if not os.path.exists(as_path):
            missing.append(f"Assessments DB not found at: {as_path}")
        if missing:
            raise FileNotFoundError(
                "\n".join(missing)
                + "\nRun scripts/migrate_split_db.py to create the split databases."
            )
        return MeridantClient(
            frameworks_db_path=fw_path,
            assessments_db_path=as_path,
        )

    # Legacy single-path fallback (TMM_DB_PATH)
    db_path = os.getenv("TMM_DB_PATH")
    if not db_path:
        raise ValueError(
            "No database path configured. Set MERIDANT_FRAMEWORKS_DB_PATH + "
            "MERIDANT_ASSESSMENTS_DB_PATH in your .env file.\n"
            "(Legacy: TMM_DB_PATH is also accepted as a single-DB fallback.)"
        )
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"SQLite database not found at: {db_path}\n"
            "Check MERIDANT_FRAMEWORKS_DB_PATH / MERIDANT_ASSESSMENTS_DB_PATH in .env"
        )
    return MeridantClient(db_path=db_path)

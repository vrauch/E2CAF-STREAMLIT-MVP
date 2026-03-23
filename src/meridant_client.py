from __future__ import annotations

import os
import sqlite3
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass
class MeridantClient:
    """
    SQLite client for Meridant Matrix.

    Supports two modes:
      - Split mode (recommended): frameworks_db_path + assessments_db_path
        Opens meridant_frameworks.db as the main connection and ATTACHes
        meridant.db. All table names are unique across the two DBs, so
        existing SQL queries resolve correctly without modification.
    """
    frameworks_db_path: str = None   # framework tables (Next_*)
    assessments_db_path: str = None  # assessment tables (Assessment*/Client)

    def _connect(self) -> sqlite3.Connection:
        """Open frameworks DB and ATTACH assessments DB."""
        conn = sqlite3.connect(self.frameworks_db_path)
        conn.execute(f'ATTACH DATABASE "{self.assessments_db_path}" AS assessments')
        conn.row_factory = sqlite3.Row
        return conn

    def query(self, sql: str, params: list = None) -> dict:
        """
        Execute a SELECT query and return rows as a list of dicts.
        """
        conn = None
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(sql, params or [])
            rows = [dict(r) for r in cur.fetchall()]
            return {"rows": rows, "count": len(rows)}
        except Exception as e:
            return {"rows": [], "count": 0, "error": str(e)}
        finally:
            if conn:
                conn.close()

    def write(self, sql: str, params: list = None) -> dict:
        """
        Execute an INSERT, UPDATE, or DELETE query.
        Returns lastrowid and rowcount.
        """
        conn = None
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(sql, params or [])
            conn.commit()
            return {"lastrowid": cur.lastrowid, "rowcount": cur.rowcount}
        except Exception as e:
            return {"lastrowid": None, "rowcount": 0, "error": str(e)}
        finally:
            if conn:
                conn.close()

    def write_many(self, sql: str, params_list: list) -> dict:
        """
        Execute a batch INSERT using executemany.
        """
        conn = None
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.executemany(sql, params_list)
            conn.commit()
            return {"rowcount": cur.rowcount}
        except Exception as e:
            return {"rowcount": 0, "error": str(e)}
        finally:
            if conn:
                conn.close()


def get_client() -> MeridantClient:
    """
    Return a configured MeridantClient.

    Reads MERIDANT_FRAMEWORKS_DB_PATH and MERIDANT_ASSESSMENTS_DB_PATH from
    the environment (.env).  Both must be set and the files must exist.
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

    raise ValueError(
        "Database paths not configured. Set MERIDANT_FRAMEWORKS_DB_PATH + "
        "MERIDANT_ASSESSMENTS_DB_PATH in your .env file."
    )

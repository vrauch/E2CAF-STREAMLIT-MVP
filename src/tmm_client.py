from __future__ import annotations

import os
import sqlite3
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Any, Dict

load_dotenv()

DEFAULT_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))

@dataclass
class TMMClient:
    db_path: str

    def query(self, sql: str, params: list = None) -> dict:
        """
        Execute a SELECT query and return rows as a list of dicts.
        Matches the interface previously used by the FastAPI client.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # rows accessible by column name
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
            conn = sqlite3.connect(self.db_path)
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
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.executemany(sql, params_list)
            conn.commit()
            result = {"rowcount": cur.rowcount}
            conn.close()
            return result
        except Exception as e:
            return {"rowcount": 0, "error": str(e)}


def get_client() -> TMMClient:
    db_path = os.getenv("TMM_DB_PATH")
    if not db_path:
        raise ValueError(
            "TMM_DB_PATH not set in environment. "
            "Add it to your .env file pointing to your SQLite database."
        )
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"SQLite database not found at: {db_path}\n"
            "Check your TMM_DB_PATH in .env"
        )
    return TMMClient(db_path=db_path)

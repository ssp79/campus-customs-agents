"""Working-copy management and read-only checks the backend runs itself.

All agent reads and writes go through the MCP server. The backend only reads the
database directly to validate agent output (do the ids an agent reports exist?)
and to reset the working copy before a full run.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

HW_DIR = Path(__file__).resolve().parent.parent
ORIGINAL_DB = HW_DIR / "data" / "campus_customs.db"
WORKING_DB = HW_DIR / "data" / "campus_customs_new.db"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reset_database() -> dict:
    """Copy the untouched original over the working copy. The original is only ever read."""
    original_hash = _sha256(ORIGINAL_DB)
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    if _sha256(WORKING_DB) != original_hash or _sha256(ORIGINAL_DB) != original_hash:
        raise RuntimeError("Reset failed: working copy does not match the original")
    # Mark the reset in the append-only audit trail so later readers know where a fresh run starts.
    import audit
    audit.append_record({"type": "reset", "time": audit.now(), "working_db": WORKING_DB.name, "sha256": original_hash})
    return {"reset": True, "working_db": WORKING_DB.name, "sha256": original_hash}


def read_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{WORKING_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def missing_ids(table: str, ids: list[int]) -> list[int]:
    """ids that do not exist in approvals or drafts (used to catch invented ids)."""
    if table not in ("approvals", "drafts") or not ids:
        return []
    conn = read_conn()
    try:
        if not _has_table(conn, table):
            return list(ids)
        found = {r[0] for r in conn.execute(
            f"SELECT id FROM {table} WHERE id IN ({','.join('?' * len(ids))})", ids)}
    finally:
        conn.close()
    return [i for i in ids if i not in found]


def ticket_status(ticket_id: int) -> str | None:
    conn = read_conn()
    try:
        row = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    finally:
        conn.close()
    return row["status"] if row else None


def open_ticket_ids() -> list[int]:
    conn = read_conn()
    try:
        return [r["id"] for r in conn.execute("SELECT id FROM tickets WHERE status = 'open' ORDER BY id")]
    finally:
        conn.close()

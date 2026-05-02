"""API token repository."""
from datetime import datetime, timezone

from db.connection import get_connection


def insert_token(token_hash: str, prefix: str, label: str,
                 expires_at: str | None = None) -> int:
    """Insert a new token row. Returns the row id."""
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO api_tokens "
            "(token_hash, prefix, label, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token_hash, prefix, label, now_iso, expires_at),
        )
        return cur.lastrowid


def find_active_by_hash(token_hash: str) -> dict | None:
    """Return token row if hash matches and token is not revoked or expired."""
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM api_tokens "
            "WHERE token_hash = ? "
            "AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > ?) "
            "LIMIT 1",
            (token_hash, now_iso),
        ).fetchone()
        return dict(row) if row else None


def touch_last_used(token_id: int) -> None:
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
            (now_iso, token_id),
        )


def list_tokens() -> list[dict]:
    """Return all token rows for CLI listing (most recent first)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, prefix, label, created_at, expires_at, "
            "       last_used_at, revoked_at "
            "FROM api_tokens "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def revoke_token(token_id: int) -> bool:
    """Mark token revoked. Returns True if a row was updated."""
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE api_tokens SET revoked_at = ? "
            "WHERE id = ? AND revoked_at IS NULL",
            (now_iso, token_id),
        )
        return cur.rowcount > 0

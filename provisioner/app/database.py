"""Small SQLite state store for workspace ownership and browser sessions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkspaceRecord:
    workspace_id: str
    workspace_key: str
    user_id: str
    identity: dict[str, Any]
    container_name: str
    backend_api_key: str
    status: str
    error: str | None


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    workspace_key TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL UNIQUE,
                    identity_json TEXT NOT NULL,
                    container_name TEXT NOT NULL UNIQUE,
                    backend_api_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS launch_tickets (
                    token_hash TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER
                );

                CREATE TABLE IF NOT EXISTS browser_sessions (
                    token_hash TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_launch_tickets_expiry
                    ON launch_tickets(expires_at);
                CREATE INDEX IF NOT EXISTS idx_browser_sessions_expiry
                    ON browser_sessions(expires_at);
                """
            )

    @staticmethod
    def _workspace(row: sqlite3.Row | None) -> WorkspaceRecord | None:
        if row is None:
            return None
        return WorkspaceRecord(
            workspace_id=row["workspace_id"],
            workspace_key=row["workspace_key"],
            user_id=row["user_id"],
            identity=json.loads(row["identity_json"]),
            container_name=row["container_name"],
            backend_api_key=row["backend_api_key"],
            status=row["status"],
            error=row["error"],
        )

    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workspaces WHERE workspace_id = ?", (workspace_id,)
            ).fetchone()
        return self._workspace(row)

    def get_workspace_by_key(self, workspace_key: str) -> WorkspaceRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workspaces WHERE workspace_key = ?", (workspace_key,)
            ).fetchone()
        return self._workspace(row)

    def get_workspace_by_user(self, user_id: str) -> WorkspaceRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM workspaces WHERE user_id = ?", (user_id,)
            ).fetchone()
        return self._workspace(row)

    def list_workspaces(self) -> list[WorkspaceRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workspaces ORDER BY created_at, workspace_id"
            ).fetchall()
        return [record for row in rows if (record := self._workspace(row)) is not None]

    def create_workspace(
        self,
        *,
        workspace_id: str,
        workspace_key: str,
        user_id: str,
        identity: dict[str, Any],
        container_name: str,
        backend_api_key: str,
    ) -> WorkspaceRecord:
        now = int(time.time())
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO workspaces (
                    workspace_id, workspace_key, user_id, identity_json,
                    container_name, backend_api_key, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'provisioning', ?, ?)
                """,
                (
                    workspace_id,
                    workspace_key,
                    user_id,
                    json.dumps(identity, sort_keys=True, separators=(",", ":")),
                    container_name,
                    backend_api_key,
                    now,
                    now,
                ),
            )
        record = self.get_workspace(workspace_id)
        if record is None:
            raise RuntimeError("Workspace creation did not persist")
        return record

    def update_identity(self, workspace_id: str, identity: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE workspaces
                SET identity_json = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (
                    json.dumps(identity, sort_keys=True, separators=(",", ":")),
                    int(time.time()),
                    workspace_id,
                ),
            )

    def update_status(self, workspace_id: str, status: str, error: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE workspaces
                SET status = ?, error = ?, updated_at = ?
                WHERE workspace_id = ?
                """,
                (status, error, int(time.time()), workspace_id),
            )

    def create_launch_ticket(
        self, *, token: str, workspace_id: str, user_id: str, expires_at: int
    ) -> None:
        self.cleanup_expired()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO launch_tickets (token_hash, workspace_id, user_id, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_digest(token), workspace_id, user_id, expires_at),
            )

    def consume_launch_ticket(
        self, *, ticket: str, session_token: str, session_expires_at: int
    ) -> WorkspaceRecord | None:
        now = int(time.time())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT workspace_id, user_id
                FROM launch_tickets
                WHERE token_hash = ? AND consumed_at IS NULL AND expires_at >= ?
                """,
                (token_digest(ticket), now),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            connection.execute(
                "UPDATE launch_tickets SET consumed_at = ? WHERE token_hash = ?",
                (now, token_digest(ticket)),
            )
            connection.execute(
                """
                INSERT INTO browser_sessions (
                    token_hash, workspace_id, user_id, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    token_digest(session_token),
                    row["workspace_id"],
                    row["user_id"],
                    session_expires_at,
                    now,
                ),
            )
            connection.commit()
        return self.get_workspace(row["workspace_id"])

    def resolve_session(self, token: str) -> WorkspaceRecord | None:
        now = int(time.time())
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT w.*
                FROM browser_sessions s
                JOIN workspaces w ON w.workspace_id = s.workspace_id
                WHERE s.token_hash = ? AND s.expires_at >= ? AND w.status = 'ready'
                """,
                (token_digest(token), now),
            ).fetchone()
        return self._workspace(row)

    def cleanup_expired(self) -> None:
        now = int(time.time())
        with self.connect() as connection:
            connection.execute("DELETE FROM launch_tickets WHERE expires_at < ?", (now,))
            connection.execute("DELETE FROM browser_sessions WHERE expires_at < ?", (now,))

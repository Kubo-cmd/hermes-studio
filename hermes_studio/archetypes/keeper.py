"""
Keeper — session-scoped memory and timeline.

Partially addresses Hermes issue #6320 (session/memory contamination
between profiles). The real fix for #6320 is upstream in Hermes's
session_search — this archetype sits *alongside* Hermes's memory and
provides an additional per-session timeline that is strictly scoped to
(profile_id, session_id). It's append-only and never returns entries
from a different profile.

Keeper is the source of truth for the Visualizer's timeline view and
for the studio_timeline_fork tool.

Storage: SQLite at ~/.hermes/studio/keeper.db. One table per profile
via schema-level isolation (not row-level) so a bug in query-building
can never leak across profiles.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


def _studio_dir() -> Path:
    override = os.environ.get("STUDIO_MEDIA_DIR")
    if override:
        return Path(override).parent
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return home / "studio"


# Profile IDs come from Hermes config; we sanitize aggressively before using
# them as a SQLite schema name to prevent injection.
_PROFILE_RE = re.compile(r"[^A-Za-z0-9_]")


def _profile_key(profile_id: str) -> str:
    safe = _PROFILE_RE.sub("_", profile_id or "default")
    return safe[:64] or "default"


class Keeper:
    """Per-profile, per-session append-only timeline."""

    def __init__(self) -> None:
        self._dir = _studio_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._dir / "keeper.db"
        self._conn: sqlite3.Connection | None = None
        self._active_sessions: dict[tuple[str, str], float] = {}

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _table(self, profile_id: str) -> str:
        return f"timeline_{_profile_key(profile_id)}"

    def _ensure_table(self, profile_id: str) -> None:
        table = self._table(profile_id)
        with self._connect() as cx:
            cx.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id          TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    fork_of     TEXT,
                    ts          REAL NOT NULL,
                    role        TEXT NOT NULL,
                    kind        TEXT NOT NULL,
                    content     TEXT,
                    media_ref   TEXT
                )
            """)
            cx.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_sess ON {table}(session_id, ts)")

    # ---- Lifecycle hooks ----

    def on_session_start(self, session_id: str, profile_id: str = "default", **kw: Any) -> None:
        self._ensure_table(profile_id)
        self._active_sessions[(profile_id, session_id)] = time.time()

    def on_session_end(self, session_id: str, profile_id: str = "default", **kw: Any) -> None:
        self._active_sessions.pop((profile_id, session_id), None)

    # ---- Timeline API (used by Visualizer and the timeline_fork tool) ----

    def append(
        self,
        session_id: str,
        role: str,
        kind: str,
        content: str | None = None,
        media_ref: str | None = None,
        profile_id: str = "default",
        fork_of: str | None = None,
    ) -> str:
        """Append an entry to the timeline for (profile_id, session_id)."""
        self._ensure_table(profile_id)
        entry_id = uuid.uuid4().hex
        with self._connect() as cx:
            cx.execute(
                f"INSERT INTO {self._table(profile_id)} "
                "(id, session_id, fork_of, ts, role, kind, content, media_ref) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (entry_id, session_id, fork_of, time.time(), role, kind, content, media_ref),
            )
        return entry_id

    def list_session(
        self,
        session_id: str,
        profile_id: str = "default",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """List entries for (profile_id, session_id). Strictly scoped."""
        self._ensure_table(profile_id)
        with self._connect() as cx:
            rows = cx.execute(
                f"SELECT id, session_id, fork_of, ts, role, kind, content, media_ref "
                f"FROM {self._table(profile_id)} "
                "WHERE session_id = ? ORDER BY ts ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        cols = ["id", "session_id", "fork_of", "ts", "role", "kind", "content", "media_ref"]
        return [dict(zip(cols, r)) for r in rows]

    # ---- Tool handler for studio_timeline_fork ----

    def fork(self, args: dict[str, Any], **kwargs: Any) -> str:
        """Create a forked session starting from `from_message_id`."""
        import json

        from_id: str = args["from_message_id"]
        label: str | None = args.get("label")
        profile_id: str = kwargs.get("profile_id", "default")
        original_session: str | None = kwargs.get("session_id")

        if not original_session:
            return json.dumps({"ok": False, "error": "no session_id in context"})

        # Find the anchor message in the original session
        entries = self.list_session(original_session, profile_id=profile_id)
        anchor = next((e for e in entries if e["id"] == from_id), None)
        if anchor is None:
            return json.dumps({"ok": False, "error": f"message {from_id} not found in session"})

        new_session = f"{original_session}_fork_{uuid.uuid4().hex[:8]}"
        # Copy entries up to and including the anchor into the new session.
        for e in entries:
            self.append(
                session_id=new_session,
                role=e["role"],
                kind=e["kind"],
                content=e["content"],
                media_ref=e["media_ref"],
                profile_id=profile_id,
                fork_of=original_session,
            )
            if e["id"] == from_id:
                break

        return json.dumps({
            "ok": True,
            "new_session_id": new_session,
            "label": label,
            "entries_copied": len([e for e in entries if e["ts"] <= anchor["ts"]]),
        })

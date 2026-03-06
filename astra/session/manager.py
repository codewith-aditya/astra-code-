"""Session management -- persist and restore conversation sessions."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionInfo:
    """Metadata for a single Astra session."""

    id: str
    name: str
    created_at: float
    last_active: float
    repo_path: str
    message_count: int


class SessionManager:
    """Create, save, load, list, fork, and delete conversation sessions.

    Sessions are stored as JSON files inside ``.astra/sessions/`` relative
    to the working directory (usually the repository root).
    """

    def __init__(self, repo_path: str = ".") -> None:
        self.sessions_dir: Path = Path(repo_path).resolve() / ".astra" / "sessions"
        self.current_session: SessionInfo | None = None

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_session(self, name: str) -> SessionInfo:
        """Create a new empty session and set it as current."""
        now = time.time()
        session = SessionInfo(
            id=uuid.uuid4().hex,
            name=name,
            created_at=now,
            last_active=now,
            repo_path=str(self.sessions_dir.parent.parent),
            message_count=0,
        )
        self.current_session = session
        return session

    def save_session(
        self,
        session: SessionInfo,
        messages: list[dict[str, Any]],
    ) -> None:
        """Persist a session and its messages to disk."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        session.last_active = time.time()
        session.message_count = len(messages)

        payload = {
            "session": asdict(session),
            "messages": messages,
        }

        target = self.sessions_dir / f"{session.id}.json"
        target.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )

    def load_session(
        self,
        id_or_name: str,
    ) -> tuple[SessionInfo, list[dict[str, Any]]]:
        """Load a session by id or name.

        Raises ``FileNotFoundError`` if no matching session is found.
        """
        path = self._resolve_session_path(id_or_name)
        if path is None:
            raise FileNotFoundError(f"No session found for '{id_or_name}'")

        data = json.loads(path.read_text(encoding="utf-8"))
        info = SessionInfo(**data["session"])
        messages: list[dict[str, Any]] = data.get("messages", [])
        self.current_session = info
        return info, messages

    def list_sessions(self) -> list[SessionInfo]:
        """Return metadata for every saved session, newest first."""
        if not self.sessions_dir.is_dir():
            return []

        sessions: list[SessionInfo] = []
        for fp in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                sessions.append(SessionInfo(**data["session"]))
            except Exception:
                # Skip corrupted session files silently.
                continue

        sessions.sort(key=lambda s: s.last_active, reverse=True)
        return sessions

    def rename_session(self, session_id: str, new_name: str) -> None:
        """Rename an existing session.

        Raises ``FileNotFoundError`` if the session does not exist.
        """
        path = self._resolve_session_path(session_id)
        if path is None:
            raise FileNotFoundError(f"No session found for '{session_id}'")

        data = json.loads(path.read_text(encoding="utf-8"))
        data["session"]["name"] = new_name
        path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

    def fork_session(self, session_id: str, new_name: str) -> SessionInfo:
        """Create a copy of a session with a new id and name.

        The forked session shares the same message history but is
        otherwise independent.

        Raises ``FileNotFoundError`` if the source session does not exist.
        """
        info, messages = self.load_session(session_id)

        now = time.time()
        forked = SessionInfo(
            id=uuid.uuid4().hex,
            name=new_name,
            created_at=now,
            last_active=now,
            repo_path=info.repo_path,
            message_count=info.message_count,
        )
        self.save_session(forked, list(messages))
        return forked

    def delete_session(self, session_id: str) -> None:
        """Delete a session file from disk.

        Raises ``FileNotFoundError`` if the session does not exist.
        """
        path = self._resolve_session_path(session_id)
        if path is None:
            raise FileNotFoundError(f"No session found for '{session_id}'")

        path.unlink()

        if self.current_session and self.current_session.id == session_id:
            self.current_session = None

    def cleanup_old_sessions(self, days: int = 30) -> int:
        """Remove sessions that have not been active for *days* days.

        Returns the number of sessions removed.
        """
        if not self.sessions_dir.is_dir():
            return 0

        cutoff = time.time() - (days * 86400)
        removed = 0

        for fp in list(self.sessions_dir.glob("*.json")):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                last_active = data["session"].get("last_active", 0)
                if last_active < cutoff:
                    fp.unlink()
                    removed += 1
            except Exception:
                continue

        return removed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_session_path(self, id_or_name: str) -> Path | None:
        """Find a session file by exact id or by name match.

        Returns the ``Path`` to the JSON file, or ``None``.
        """
        if not self.sessions_dir.is_dir():
            return None

        # Try exact id match first (fast path).
        direct = self.sessions_dir / f"{id_or_name}.json"
        if direct.is_file():
            return direct

        # Fall back to scanning names.
        for fp in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if data["session"].get("name") == id_or_name:
                    return fp
            except Exception:
                continue

        return None

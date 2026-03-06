"""Checkpointing and rewind system -- snapshot files and restore them later."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileSnapshot:
    """Snapshot of a single file's content at a point in time."""

    path: str
    content: str
    timestamp: float


@dataclass
class Checkpoint:
    """A named checkpoint containing one or more file snapshots."""

    id: str
    label: str
    snapshots: list[FileSnapshot]
    timestamp: float
    message_index: int


class CheckpointManager:
    """Create, list, and restore file-level checkpoints.

    Checkpoints capture the contents of one or more files so they can be
    restored later if an edit goes wrong.  Each checkpoint is identified
    by a short hex id derived from a UUID4.
    """

    def __init__(self) -> None:
        self.checkpoints: list[Checkpoint] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(
        self,
        label: str,
        file_paths: list[str],
        message_index: int,
    ) -> Checkpoint:
        """Read each file in *file_paths* and store a checkpoint.

        Files that do not exist or cannot be read are silently skipped so
        that a checkpoint never fails due to a single missing path.
        """
        snapshots: list[FileSnapshot] = []
        now = time.time()

        for fpath in file_paths:
            content = self._read_file(fpath)
            if content is not None:
                snapshots.append(
                    FileSnapshot(path=fpath, content=content, timestamp=now)
                )

        checkpoint = Checkpoint(
            id=uuid.uuid4().hex[:8],
            label=label,
            snapshots=snapshots,
            timestamp=now,
            message_index=message_index,
        )
        self.checkpoints.append(checkpoint)
        return checkpoint

    def restore(self, checkpoint_id: str) -> dict[str, Any]:
        """Restore every file recorded in the checkpoint.

        Returns a dict with ``restored`` (list of paths written) and
        ``errors`` (list of dicts with path and error message).
        """
        checkpoint = self.get(checkpoint_id)
        if checkpoint is None:
            return {"restored": [], "errors": [{"path": "", "error": f"Checkpoint '{checkpoint_id}' not found"}]}

        restored: list[str] = []
        errors: list[dict[str, str]] = []

        for snap in checkpoint.snapshots:
            try:
                p = Path(snap.path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(snap.content, encoding="utf-8")
                restored.append(snap.path)
            except Exception as exc:
                errors.append({"path": snap.path, "error": str(exc)})

        return {"restored": restored, "errors": errors}

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """Return a lightweight summary of every checkpoint."""
        return [
            {
                "id": cp.id,
                "label": cp.label,
                "timestamp": cp.timestamp,
                "file_count": len(cp.snapshots),
            }
            for cp in self.checkpoints
        ]

    def get(self, checkpoint_id: str) -> Checkpoint | None:
        """Look up a checkpoint by its short hex id."""
        for cp in self.checkpoints:
            if cp.id == checkpoint_id:
                return cp
        return None

    def auto_checkpoint(self, file_path: str, message_index: int) -> Checkpoint | None:
        """Convenience wrapper: snapshot a single file before editing it.

        If the file does not exist yet (new file), no snapshot is taken and
        ``None`` is returned.
        """
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return None

        return self.capture(
            label=f"auto: {p.name}",
            file_paths=[file_path],
            message_index=message_index,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_file(path: str) -> str | None:
        """Read a file's text content, returning None on failure."""
        try:
            p = Path(path)
            if not p.is_file():
                return None
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

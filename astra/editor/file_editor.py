"""Safe file editor with backup and diff support."""

from __future__ import annotations

import difflib
import shutil
from datetime import datetime
from pathlib import Path


class FileEditor:
    """Apply safe edits to files with automatic backups."""

    def __init__(self, backup_dir: str | Path | None = None) -> None:
        if backup_dir:
            self._backup_dir = Path(backup_dir)
        else:
            self._backup_dir = Path(".astra_backups")
        self._backup_dir.mkdir(parents=True, exist_ok=True)

    def backup(self, path: Path) -> Path | None:
        """Create a timestamped backup of a file."""
        if not path.exists():
            return None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self._backup_dir / f"{path.name}.{stamp}.bak"
        shutil.copy2(path, dest)
        return dest

    @staticmethod
    def diff(old: str, new: str, filename: str = "file") -> str:
        """Generate a unified diff between two strings."""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff_lines = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
        return "".join(diff_lines)

    def apply_edit(
        self,
        path: str | Path,
        old_string: str,
        new_string: str,
        create_backup: bool = True,
    ) -> dict:
        """Apply a search-and-replace edit with optional backup."""
        file = Path(path)
        if not file.exists():
            return {"error": f"File not found: {path}"}

        original = file.read_text(encoding="utf-8", errors="replace")

        if old_string not in original:
            return {"error": "old_string not found in file."}

        if create_backup:
            self.backup(file)

        updated = original.replace(old_string, new_string, 1)
        file.write_text(updated, encoding="utf-8")

        return {
            "status": "ok",
            "diff": self.diff(original, updated, file.name),
        }

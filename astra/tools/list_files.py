"""Tool: list_files — List files and directories in a path."""

from __future__ import annotations

from pathlib import Path

import pathspec

from astra.tools.registry import ToolDefinition

DEFAULT_IGNORE = [
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "*.pyc", ".DS_Store", "dist", "build",
]


def handle_list_files(
    path: str = ".",
    glob_pattern: str | None = None,
    max_depth: int | None = None,
) -> dict:
    """List files under the given path, respecting ignore rules."""
    root = Path(path).resolve()
    if not root.exists():
        return {"error": f"Path not found: {path}"}

    ignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", DEFAULT_IGNORE)

    entries: list[str] = []

    iterator = root.rglob(glob_pattern or "*")

    for entry in sorted(iterator):
        rel = entry.relative_to(root).as_posix()

        if ignore_spec.match_file(rel):
            continue

        if max_depth is not None and rel.count("/") >= max_depth:
            continue

        prefix = "[DIR] " if entry.is_dir() else "      "
        entries.append(f"{prefix}{rel}")

    return {
        "root": str(root),
        "count": len(entries),
        "entries": entries,
    }


LIST_FILES_TOOL = ToolDefinition(
    name="list_files",
    description=(
        "List files and directories under a given path. "
        "Supports glob filtering and depth limiting."
    ),
    parameters={
        "path": {
            "type": "string",
            "description": "Directory to list. Defaults to '.'.",
            "optional": True,
        },
        "glob_pattern": {
            "type": "string",
            "description": "Glob pattern to filter entries (e.g. '*.py'). Optional.",
            "optional": True,
        },
        "max_depth": {
            "type": "integer",
            "description": "Maximum directory depth to traverse. Optional.",
            "optional": True,
        },
    },
    handler=handle_list_files,
)

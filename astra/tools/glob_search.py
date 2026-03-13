"""Tool: glob_search -- Find files by glob pattern."""

from __future__ import annotations

from pathlib import Path

import pathspec

from astra.tools.registry import ToolDefinition

DEFAULT_IGNORE = [
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "*.pyc", ".DS_Store", "dist", "build",
]


def handle_glob(
    pattern: str,
    path: str = ".",
) -> dict:
    """Find files matching a glob pattern."""
    root = Path(path).resolve()
    if not root.exists():
        return {"error": f"Path not found: {path}"}

    ignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", DEFAULT_IGNORE)

    matches: list[str] = []
    for entry in sorted(root.glob(pattern)):
        rel = entry.relative_to(root).as_posix()
        if ignore_spec.match_file(rel):
            continue
        matches.append(rel)
        if len(matches) >= 200:
            return {"matches": matches, "truncated": True}

    return {"matches": matches, "truncated": False}


GLOB_TOOL = ToolDefinition(
    name="glob",
    description="Find files matching a glob pattern (e.g. '**/*.py', 'src/**/*.ts').",
    parameters={
        "pattern": {
            "type": "string",
            "description": "Glob pattern to match files (e.g. '**/*.py').",
        },
        "path": {
            "type": "string",
            "description": "Root directory to search in. Defaults to '.'.",
            "optional": True,
        },
    },
    handler=handle_glob,
)

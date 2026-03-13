"""Tool: search_code — Search for a regex pattern across repository files."""

from __future__ import annotations

import re
from pathlib import Path

import pathspec

from astra.tools.registry import ToolDefinition

DEFAULT_IGNORE = [
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "*.pyc", ".DS_Store", "dist", "build",
]


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gi = root / ".gitignore"
    if gi.exists():
        return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text().splitlines())
    return None


def handle_search_code(
    pattern: str,
    path: str = ".",
    glob: str | None = None,
    max_results: int = 50,
) -> dict:
    """Search files under *path* for lines matching *pattern*."""
    root = Path(path).resolve()
    if not root.exists():
        return {"error": f"Path not found: {path}"}

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return {"error": f"Invalid regex: {exc}"}

    ignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", DEFAULT_IGNORE)
    gitignore = _load_gitignore(root)

    matches: list[dict] = []

    for file in root.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(root).as_posix()
        if ignore_spec.match_file(rel):
            continue
        if gitignore and gitignore.match_file(rel):
            continue
        if glob:
            if not file.match(glob):
                continue

        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append({
                    "file": rel,
                    "line": lineno,
                    "content": line.rstrip(),
                })
                if len(matches) >= max_results:
                    return {"matches": matches, "truncated": True}

    return {"matches": matches, "truncated": False}


SEARCH_CODE_TOOL = ToolDefinition(
    name="search_code",
    description=(
        "Search for a regex pattern across files in the repository. "
        "Returns matching lines with file paths and line numbers."
    ),
    parameters={
        "pattern": {
            "type": "string",
            "description": "Regex pattern to search for.",
        },
        "path": {
            "type": "string",
            "description": "Root directory to search in. Defaults to '.'.",
            "optional": True,
        },
        "glob": {
            "type": "string",
            "description": "File glob to filter (e.g. '*.py'). Optional.",
            "optional": True,
        },
        "max_results": {
            "type": "integer",
            "description": "Maximum matches to return. Default 50.",
            "optional": True,
        },
    },
    handler=handle_search_code,
)

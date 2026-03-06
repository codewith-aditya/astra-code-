"""Tool: grep_search -- Search file contents with regex, richer than search_code."""

from __future__ import annotations

import re
from pathlib import Path

import pathspec

from astra.tools.registry import ToolDefinition

DEFAULT_IGNORE = [
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "*.pyc", ".DS_Store", "dist", "build",
]


def handle_grep(
    pattern: str,
    path: str = ".",
    file_type: str | None = None,
    context_lines: int = 0,
    max_results: int = 50,
    case_insensitive: bool = False,
) -> dict:
    """Search file contents with regex and optional context lines."""
    root = Path(path).resolve()
    if not root.exists():
        return {"error": f"Path not found: {path}"}

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as exc:
        return {"error": f"Invalid regex: {exc}"}

    ignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", DEFAULT_IGNORE)

    # File type to extension mapping
    type_map = {
        "py": "*.py", "js": "*.js", "ts": "*.ts", "tsx": "*.tsx",
        "jsx": "*.jsx", "java": "*.java", "go": "*.go", "rs": "*.rs",
        "c": "*.c", "cpp": "*.cpp", "rb": "*.rb", "php": "*.php",
        "html": "*.html", "css": "*.css", "json": "*.json", "yaml": "*.yaml",
        "yml": "*.yml", "md": "*.md", "toml": "*.toml", "sql": "*.sql",
    }

    matches: list[dict] = []

    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file():
            continue
        rel = fpath.relative_to(root).as_posix()
        if ignore_spec.match_file(rel):
            continue
        if file_type:
            ext_pattern = type_map.get(file_type, f"*.{file_type}")
            if not fpath.match(ext_pattern):
                continue

        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for i, line in enumerate(lines):
            if regex.search(line):
                # Gather context
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                context = []
                for j in range(start, end):
                    prefix = ">" if j == i else " "
                    context.append(f"{prefix} {j + 1}: {lines[j]}")

                matches.append({
                    "file": rel,
                    "line": i + 1,
                    "match": line.rstrip(),
                    "context": "\n".join(context) if context_lines > 0 else None,
                })

                if len(matches) >= max_results:
                    return {"matches": matches, "truncated": True}

    return {"matches": matches, "truncated": False}


GREP_TOOL = ToolDefinition(
    name="grep",
    description=(
        "Search file contents with regex. Supports file type filtering, "
        "context lines, and case-insensitive search."
    ),
    parameters={
        "pattern": {
            "type": "string",
            "description": "Regex pattern to search for.",
        },
        "path": {
            "type": "string",
            "description": "Root directory. Defaults to '.'.",
            "optional": True,
        },
        "file_type": {
            "type": "string",
            "description": "File type filter (e.g. 'py', 'js', 'ts'). Optional.",
            "optional": True,
        },
        "context_lines": {
            "type": "integer",
            "description": "Lines of context before/after match. Default 0.",
            "optional": True,
        },
        "max_results": {
            "type": "integer",
            "description": "Max matches. Default 50.",
            "optional": True,
        },
        "case_insensitive": {
            "type": "boolean",
            "description": "Case insensitive search. Default false.",
            "optional": True,
        },
    },
    handler=handle_grep,
)

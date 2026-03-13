"""Tool: read_file — Read the contents of a file with optional line range."""

from __future__ import annotations

from pathlib import Path

from astra.tools.registry import ToolDefinition


def handle_read_file(
    path: str,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    """Read a file and return its contents with line numbers."""
    file = Path(path)
    if not file.exists():
        return {"error": f"File not found: {path}"}
    if not file.is_file():
        return {"error": f"Not a file: {path}"}

    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"error": f"Failed to read file: {exc}"}

    lines = text.splitlines(keepends=True)
    total = len(lines)

    start = (offset or 1) - 1  # 1-indexed to 0-indexed
    end = start + limit if limit else total
    selected = lines[start:end]

    numbered = "".join(
        f"{i + start + 1:>6}\t{line}" for i, line in enumerate(selected)
    )

    return {
        "path": str(file.resolve()),
        "total_lines": total,
        "showing": f"{start + 1}-{min(end, total)}",
        "content": numbered,
    }


READ_FILE_TOOL = ToolDefinition(
    name="read_file",
    description=(
        "Read the contents of a file. Returns line-numbered content. "
        "Use offset and limit to read specific ranges of large files."
    ),
    parameters={
        "path": {
            "type": "string",
            "description": "Absolute or relative path to the file.",
        },
        "offset": {
            "type": "integer",
            "description": "Line number to start reading from (1-indexed). Optional.",
            "optional": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of lines to read. Optional.",
            "optional": True,
        },
    },
    handler=handle_read_file,
)

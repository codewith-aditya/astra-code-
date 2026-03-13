"""Tool: multi_edit -- Apply multiple edits to a single file at once."""

from __future__ import annotations

from pathlib import Path

from astra.tools.registry import ToolDefinition


def handle_multi_edit(
    path: str,
    edits: list[dict],
) -> dict:
    """Apply multiple search-and-replace edits to a file in order."""
    file = Path(path)
    if not file.exists():
        return {"error": f"File not found: {path}"}

    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"error": f"Failed to read: {exc}"}

    applied = 0
    errors = []

    for i, edit in enumerate(edits):
        old = edit.get("old_string", "")
        new = edit.get("new_string", "")
        if not old:
            errors.append(f"Edit {i + 1}: empty old_string")
            continue
        if old not in text:
            errors.append(f"Edit {i + 1}: old_string not found")
            continue
        text = text.replace(old, new, 1)
        applied += 1

    try:
        file.write_text(text, encoding="utf-8")
    except Exception as exc:
        return {"error": f"Failed to write: {exc}"}

    result = {"path": str(file.resolve()), "applied": applied, "status": "ok"}
    if errors:
        result["errors"] = errors
    return result


MULTI_EDIT_TOOL = ToolDefinition(
    name="multi_edit",
    description=(
        "Apply multiple search-and-replace edits to a single file in one operation. "
        "Each edit has old_string and new_string. Edits are applied in order."
    ),
    parameters={
        "path": {
            "type": "string",
            "description": "Path to the file.",
        },
        "edits": {
            "type": "array",
            "description": "List of edits. Each: {\"old_string\": \"...\", \"new_string\": \"...\"}.",
            "items": {"type": "object"},
        },
    },
    handler=handle_multi_edit,
)

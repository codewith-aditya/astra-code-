"""Tool: edit_file — Apply a targeted search-and-replace edit to a file."""

from __future__ import annotations

from pathlib import Path

from astra.tools.registry import ToolDefinition


def handle_edit_file(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> dict:
    """Replace an exact substring in a file.

    The edit fails if *old_string* is not found or if it matches
    multiple locations (unless replace_all is True).
    """
    file = Path(path)
    if not file.exists():
        return {"error": f"File not found: {path}"}

    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"error": f"Failed to read file: {exc}"}

    count = text.count(old_string)

    if count == 0:
        return {"error": "old_string not found in file."}

    if count > 1 and not replace_all:
        return {
            "error": (
                f"old_string found {count} times. "
                "Provide more context to make it unique, or set replace_all=true."
            )
        }

    new_text = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)

    try:
        file.write_text(new_text, encoding="utf-8")
    except Exception as exc:
        return {"error": f"Failed to write file: {exc}"}

    return {
        "path": str(file.resolve()),
        "replacements": count if replace_all else 1,
        "status": "ok",
    }


EDIT_FILE_TOOL = ToolDefinition(
    name="edit_file",
    description=(
        "Apply a search-and-replace edit to a file. "
        "Provide the exact old_string to match and the new_string to replace it with. "
        "Fails if old_string is ambiguous (matches multiple locations) unless replace_all is true."
    ),
    parameters={
        "path": {
            "type": "string",
            "description": "Path to the file to edit.",
        },
        "old_string": {
            "type": "string",
            "description": "The exact text to find in the file.",
        },
        "new_string": {
            "type": "string",
            "description": "The replacement text.",
        },
        "replace_all": {
            "type": "boolean",
            "description": "If true, replace all occurrences. Default false.",
            "optional": True,
        },
    },
    handler=handle_edit_file,
)

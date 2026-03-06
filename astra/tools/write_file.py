"""Tool: write_file — Create or overwrite a file with new content."""

from __future__ import annotations

from pathlib import Path

from astra.tools.registry import ToolDefinition


def handle_write_file(path: str, content: str) -> dict:
    """Write content to a file, creating parent directories as needed."""
    file = Path(path)

    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
    except Exception as exc:
        return {"error": f"Failed to write file: {exc}"}

    return {
        "path": str(file.resolve()),
        "bytes_written": len(content.encode("utf-8")),
        "status": "ok",
    }


WRITE_FILE_TOOL = ToolDefinition(
    name="write_file",
    description="Create a new file or completely overwrite an existing file with the given content.",
    parameters={
        "path": {
            "type": "string",
            "description": "Absolute or relative path to the file.",
        },
        "content": {
            "type": "string",
            "description": "The full content to write to the file.",
        },
    },
    handler=handle_write_file,
)

"""Tool: run_command — Execute a shell command and return output."""

from __future__ import annotations

import subprocess
from astra.tools.registry import ToolDefinition

BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){",
    "shutdown",
    "reboot",
    "format c:",
]


def handle_run_command(
    command: str,
    timeout: int = 60,
) -> dict:
    """Run a shell command and capture its output."""
    # Safety check
    lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in lower:
            return {"error": f"Blocked dangerous command pattern: {pattern}"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as exc:
        return {"error": f"Command execution failed: {exc}"}

    return {
        "exit_code": result.returncode,
        "stdout": result.stdout[-10000:] if result.stdout else "",
        "stderr": result.stderr[-5000:] if result.stderr else "",
    }


RUN_COMMAND_TOOL = ToolDefinition(
    name="run_command",
    description=(
        "Execute a shell command and return its stdout, stderr, and exit code. "
        "Use this for running tests, builds, git commands, etc."
    ),
    parameters={
        "command": {
            "type": "string",
            "description": "The shell command to execute.",
        },
        "timeout": {
            "type": "integer",
            "description": "Timeout in seconds. Default 60.",
            "optional": True,
        },
    },
    handler=handle_run_command,
)

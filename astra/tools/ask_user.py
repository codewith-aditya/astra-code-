"""Tool: ask_user -- Ask the user a clarifying question."""

from __future__ import annotations

from rich.console import Console

from astra.tools.registry import ToolDefinition

console = Console()


def handle_ask_user(question: str) -> dict:
    """Ask the user a question and return their answer."""
    console.print(f"\n[bold cyan]Question:[/bold cyan] {question}")
    try:
        answer = console.input("[bold cyan]Answer: [/bold cyan]").strip()
    except (EOFError, KeyboardInterrupt):
        return {"answer": "", "skipped": True}

    return {"answer": answer, "skipped": False}


ASK_USER_TOOL = ToolDefinition(
    name="ask_user",
    description="Ask the user a clarifying question when you need more information.",
    parameters={
        "question": {
            "type": "string",
            "description": "The question to ask the user.",
        },
    },
    handler=handle_ask_user,
)

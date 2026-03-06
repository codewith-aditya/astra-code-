"""UI utilities -- context visualization, doctor, export, prompt suggestions."""

from __future__ import annotations

import json
import subprocess
import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


def render_context_grid(messages: list, max_tokens: int = 200_000) -> None:
    """Visualize context window usage as a colored grid."""
    if not messages:
        console.print("[dim]No messages in context.[/dim]")
        return

    total_chars = sum(len(json.dumps(m, default=str)) for m in messages)
    total_tokens = total_chars // 4
    pct = min(100, int((total_tokens / max_tokens) * 100))

    # Build grid: 50 cells
    cells = 50
    filled = int(cells * pct / 100)

    grid = ""
    for i in range(cells):
        if i < filled:
            if pct > 80:
                grid += "[red]#[/red]"
            elif pct > 60:
                grid += "[yellow]#[/yellow]"
            else:
                grid += "[green]#[/green]"
        else:
            grid += "[dim].[/dim]"

    # Message breakdown
    user_count = sum(1 for m in messages if m.get("role") == "user")
    asst_count = sum(1 for m in messages if m.get("role") == "assistant")

    lines = [
        f"Context: {grid} {pct}%",
        f"~{total_tokens:,} / {max_tokens:,} tokens",
        f"Messages: {len(messages)} ({user_count} user, {asst_count} assistant)",
    ]

    console.print(Panel("\n".join(lines), title="Context Window", border_style="cyan"))


def run_doctor(repo_path: str = ".") -> None:
    """Diagnose installation and environment."""
    table = Table(title="Astra Doctor", border_style="cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status", style="white")
    table.add_column("Detail", style="dim")

    # Python version
    import sys
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 10)
    table.add_row("Python", "[green]OK[/green]" if ok else "[red]FAIL[/red]", py_ver)

    # Git
    git_ok = shutil.which("git") is not None
    table.add_row("Git", "[green]OK[/green]" if git_ok else "[red]MISSING[/red]", shutil.which("git") or "")

    # gh CLI
    gh_ok = shutil.which("gh") is not None
    table.add_row("GitHub CLI", "[green]OK[/green]" if gh_ok else "[yellow]MISSING[/yellow]", "Optional")

    # API key
    import os
    has_key = bool(os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY"))
    table.add_row("API Key", "[green]SET[/green]" if has_key else "[red]MISSING[/red]", "")

    # .env file
    env_exists = Path(repo_path).resolve().joinpath(".env").exists()
    table.add_row(".env file", "[green]Found[/green]" if env_exists else "[yellow]Missing[/yellow]", "")

    # ASTRA.md
    astra_md = Path(repo_path).resolve().joinpath("ASTRA.md").exists()
    table.add_row("ASTRA.md", "[green]Found[/green]" if astra_md else "[dim]Not found[/dim]", "")

    # Dependencies
    deps = ["anthropic", "openai", "rich", "click", "pathspec", "dotenv"]
    for dep in deps:
        mod_name = dep if dep != "dotenv" else "dotenv"
        try:
            __import__(mod_name)
            table.add_row(f"  {dep}", "[green]OK[/green]", "")
        except ImportError:
            table.add_row(f"  {dep}", "[red]MISSING[/red]", "pip install " + dep)

    console.print(table)


def export_conversation(messages: list, filepath: str | None = None) -> str:
    """Export conversation as plain text."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")

        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        parts.append(f"[Tool: {block.get('name', '')}]")
                    elif block.get("type") == "tool_result":
                        parts.append(f"[Result: {str(block.get('content', ''))[:200]}]")
                else:
                    parts.append(str(block))
            content = "\n".join(parts)

        lines.append(f"--- {role} ---")
        lines.append(str(content)[:5000])
        lines.append("")

    text = "\n".join(lines)

    if filepath:
        Path(filepath).write_text(text, encoding="utf-8")

    return text


def get_prompt_suggestions(messages: list, repo_path: str = ".") -> list[str]:
    """Generate simple prompt suggestions based on context."""
    suggestions = []

    if not messages:
        suggestions.extend([
            "Show me the project structure",
            "Explain the architecture of this codebase",
            "Find any bugs or issues in the code",
        ])
        return suggestions

    # Based on what was discussed
    last_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                last_content = content.lower()
            break

    if "error" in last_content or "bug" in last_content:
        suggestions.append("Fix the issue we found")
        suggestions.append("Run the tests to verify the fix")
    elif "test" in last_content:
        suggestions.append("Run the test suite")
        suggestions.append("Add more test coverage")
    elif "created" in last_content or "wrote" in last_content:
        suggestions.append("Review the changes we made")
        suggestions.append("Run tests to verify everything works")

    suggestions.append("What else should we improve?")
    return suggestions[:3]

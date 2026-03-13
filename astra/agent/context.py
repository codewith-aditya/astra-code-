"""Context manager -- conversation history, repo context, ASTRA.md, memory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astra.repo.scanner import RepoScanner


class ContextManager:
    """Manages conversation history, repo context, project config, and memory.

    Responsibilities:
    - Build initial context from repository scan + ASTRA.md
    - Load persistent memory from .astra/memory.json
    - Store and retrieve conversation messages
    - Inject tool results back into the conversation
    - Manage context budget
    """

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = repo_path
        self.messages: list[dict[str, Any]] = []
        self._repo_summary: str | None = None

    def build_repo_context(self) -> str:
        """Scan the repository and return a summary string."""
        if self._repo_summary is None:
            scanner = RepoScanner(self.repo_path)
            self._repo_summary = scanner.summary()
        return self._repo_summary

    def load_astra_md(self) -> str:
        """Load ASTRA.md project config if it exists."""
        astra_md = Path(self.repo_path).resolve() / "ASTRA.md"
        if astra_md.exists():
            try:
                return astra_md.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""
        return ""

    def load_memory(self) -> str:
        """Load persistent memory entries."""
        memory_file = Path(self.repo_path).resolve() / ".astra" / "memory.json"
        if not memory_file.exists():
            return ""
        try:
            data = json.loads(memory_file.read_text(encoding="utf-8"))
            if not data:
                return ""
            lines = ["Remembered instructions:"]
            for entry in data:
                lines.append(f"- {entry}")
            return "\n".join(lines)
        except Exception:
            return ""

    def save_memory_entry(self, entry: str) -> None:
        """Add a persistent memory entry."""
        memory_dir = Path(self.repo_path).resolve() / ".astra"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_file = memory_dir / "memory.json"

        data: list[str] = []
        if memory_file.exists():
            try:
                data = json.loads(memory_file.read_text(encoding="utf-8"))
            except Exception:
                data = []

        data.append(entry)
        memory_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def forget_memory(self, keyword: str) -> int:
        """Remove memory entries matching a keyword. Returns count removed."""
        memory_file = Path(self.repo_path).resolve() / ".astra" / "memory.json"
        if not memory_file.exists():
            return 0
        try:
            data = json.loads(memory_file.read_text(encoding="utf-8"))
            before = len(data)
            data = [e for e in data if keyword.lower() not in e.lower()]
            memory_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return before - len(data)
        except Exception:
            return 0

    def list_memory(self) -> list[str]:
        """Return all memory entries."""
        memory_file = Path(self.repo_path).resolve() / ".astra" / "memory.json"
        if not memory_file.exists():
            return []
        try:
            return json.loads(memory_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def build_full_context(self) -> str:
        """Build the complete initial context: repo + ASTRA.md + memory."""
        parts = []

        repo_ctx = self.build_repo_context()
        parts.append(f"<repository_context>\n{repo_ctx}\n</repository_context>")

        astra_md = self.load_astra_md()
        if astra_md:
            parts.append(f"<project_config>\n{astra_md}\n</project_config>")

        memory = self.load_memory()
        if memory:
            parts.append(f"<memory>\n{memory}\n</memory>")

        return "\n\n".join(parts)

    def add_user_message(self, content: str) -> None:
        """Append a user message, injecting full context on the first turn."""
        if not self.messages:
            full_context = self.build_full_context()
            full_content = f"{full_context}\n\n{content}"
            self.messages.append({"role": "user", "content": full_content})
        else:
            self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: Any) -> None:
        """Append an assistant message (text and/or tool-use blocks)."""
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results(self, results: list[dict]) -> None:
        """Append tool results for the Anthropic-style tool_result flow."""
        self.messages.append({"role": "user", "content": results})

    def get_messages(self) -> list[dict]:
        """Return the full message history."""
        return list(self.messages)

    def token_estimate(self) -> int:
        """Rough character-based token estimate (4 chars ~ 1 token)."""
        total_chars = sum(len(json.dumps(m)) for m in self.messages)
        return total_chars // 4

    def trim_if_needed(self, max_tokens: int = 150_000) -> None:
        """Drop the oldest non-system messages if the context is too large."""
        while self.token_estimate() > max_tokens and len(self.messages) > 2:
            self.messages.pop(1)

    def save_conversation(self, filepath: str) -> None:
        """Save conversation history to a JSON file."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        Path(filepath).write_text(
            json.dumps(self.messages, indent=2, default=str),
            encoding="utf-8",
        )

    def load_conversation(self, filepath: str) -> bool:
        """Load conversation history from a JSON file."""
        path = Path(filepath)
        if not path.exists():
            return False
        try:
            self.messages = json.loads(path.read_text(encoding="utf-8"))
            return True
        except Exception:
            return False

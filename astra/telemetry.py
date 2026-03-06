"""Telemetry -- session metrics and usage tracking."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class SessionMetrics:
    """Metrics for a single session."""

    session_id: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    api_requests: int = 0
    tools_used: dict[str, int] = field(default_factory=dict)
    files_read: int = 0
    files_written: int = 0
    files_edited: int = 0
    commands_run: int = 0
    errors: int = 0
    model: str = ""

    def record_tool(self, tool_name: str) -> None:
        self.tools_used[tool_name] = self.tools_used.get(tool_name, 0) + 1
        if tool_name == "read_file":
            self.files_read += 1
        elif tool_name == "write_file":
            self.files_written += 1
        elif tool_name == "edit_file":
            self.files_edited += 1
        elif tool_name == "run_command":
            self.commands_run += 1

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time if self.start_time else 0

    def summary(self) -> dict:
        return {
            "duration": f"{int(self.duration_seconds)}s",
            "tokens": self.total_input_tokens + self.total_output_tokens,
            "api_calls": self.api_requests,
            "files_touched": self.files_read + self.files_written + self.files_edited,
            "commands": self.commands_run,
        }


class TelemetryManager:
    """Track and persist session metrics."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._dir = Path(data_dir) if data_dir else Path(".astra/telemetry")
        self._dir.mkdir(parents=True, exist_ok=True)
        self.current = SessionMetrics(start_time=time.time())

    def save(self) -> None:
        """Save current session metrics."""
        self.current.end_time = time.time()
        filepath = self._dir / f"session_{int(self.current.start_time)}.json"
        filepath.write_text(
            json.dumps(asdict(self.current), indent=2),
            encoding="utf-8",
        )

    def load_history(self, limit: int = 30) -> list[dict]:
        """Load recent session metrics."""
        files = sorted(self._dir.glob("session_*.json"), reverse=True)[:limit]
        results = []
        for f in files:
            try:
                results.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    def stats_summary(self) -> dict:
        """Aggregate stats across recent sessions."""
        history = self.load_history()
        if not history:
            return {"sessions": 0}

        total_tokens = sum(h.get("total_input_tokens", 0) + h.get("total_output_tokens", 0) for h in history)
        total_time = sum(
            (h.get("end_time", 0) - h.get("start_time", 0))
            for h in history
            if h.get("start_time")
        )

        return {
            "sessions": len(history),
            "total_tokens": total_tokens,
            "total_time": f"{int(total_time / 60)}m",
            "avg_tokens_per_session": total_tokens // max(len(history), 1),
        }

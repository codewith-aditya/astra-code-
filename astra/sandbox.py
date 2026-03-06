"""Sandbox mode -- filesystem and command restrictions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SandboxConfig:
    """Sandbox restrictions."""

    enabled: bool = False
    allowed_write_paths: list[str] = field(default_factory=list)
    denied_write_paths: list[str] = field(default_factory=lambda: [
        "/etc", "/usr", "/bin", "/sbin", "C:\\Windows", "C:\\Program Files",
    ])
    denied_read_paths: list[str] = field(default_factory=lambda: [
        "**/.env", "**/credentials*", "**/*secret*",
    ])
    allowed_domains: list[str] = field(default_factory=list)


class SandboxManager:
    """Enforce filesystem and network sandbox restrictions."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def toggle(self) -> bool:
        """Toggle sandbox on/off. Returns new state."""
        self.config.enabled = not self.config.enabled
        return self.config.enabled

    def check_write(self, path: str) -> tuple[bool, str]:
        """Check if writing to path is allowed. Returns (allowed, reason)."""
        if not self.config.enabled:
            return True, ""

        abs_path = str(Path(path).resolve())

        for denied in self.config.denied_write_paths:
            if abs_path.startswith(denied) or denied in abs_path:
                return False, f"Write denied: {denied} is restricted"

        if self.config.allowed_write_paths:
            for allowed in self.config.allowed_write_paths:
                if abs_path.startswith(allowed):
                    return True, ""
            return False, "Write denied: path not in allowed list"

        return True, ""

    def check_read(self, path: str) -> tuple[bool, str]:
        """Check if reading path is allowed."""
        if not self.config.enabled:
            return True, ""

        name = Path(path).name.lower()
        for denied in self.config.denied_read_paths:
            pattern = denied.replace("**/", "").replace("*", "")
            if pattern in name:
                return False, f"Read denied: matches {denied}"

        return True, ""

    def check_command(self, command: str) -> tuple[bool, str]:
        """Check if a shell command is allowed."""
        if not self.config.enabled:
            return True, ""

        # Block network commands if domains are restricted
        network_cmds = ["curl", "wget", "nc", "ncat", "ssh"]
        cmd_lower = command.lower().strip()

        for nc in network_cmds:
            if cmd_lower.startswith(nc) and self.config.allowed_domains:
                return False, f"Network command '{nc}' restricted in sandbox mode"

        return True, ""

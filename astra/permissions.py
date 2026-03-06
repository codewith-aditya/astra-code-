"""Permission system for controlling tool access.

Provides mode-based and rule-based permission checks for the agent's
tool invocations, ensuring safe defaults and user-configurable overrides.
"""

from __future__ import annotations

import fnmatch
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PermissionMode(Enum):
    """Operating modes that control default permission behavior."""

    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    PLAN = "plan"
    BYPASS = "bypass"


# Tools that always require confirmation in DEFAULT mode
_WRITE_TOOLS = {"write_file", "edit_file", "run_command"}

# Tools allowed in PLAN mode (read-only operations)
PLAN_ALLOWED_TOOLS = frozenset({"read_file", "search_code", "list_files"})


@dataclass
class PermissionRule:
    """A single permission rule matching tool names via glob patterns.

    Attributes:
        tool: Glob pattern matching tool names (e.g. "write_*", "run_command").
        action: One of "allow", "deny", or "ask".
    """

    tool: str
    action: str  # "allow" | "deny" | "ask"

    def matches(self, tool_name: str) -> bool:
        """Check if this rule matches the given tool name."""
        return fnmatch.fnmatch(tool_name, self.tool)

    def to_dict(self) -> dict[str, str]:
        return {"tool": self.tool, "action": self.action}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionRule:
        return cls(tool=data["tool"], action=data.get("action", "ask"))


class PermissionManager:
    """Manages permission modes and rules for tool access control.

    Modes:
        DEFAULT      - Check rules, fallback to "ask" for write/edit/run tools.
        ACCEPT_EDITS - Auto-allow write_file and edit_file; rest use rules/defaults.
        PLAN         - Only read_file, search_code, list_files are allowed.
        BYPASS       - Allow everything without prompts.
    """

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self.current_mode: PermissionMode = PermissionMode.DEFAULT
        self.rules: list[PermissionRule] = []
        self._load_rules()

    # ------------------------------------------------------------------
    # Mode cycling
    # ------------------------------------------------------------------

    _MODE_CYCLE = [
        PermissionMode.DEFAULT,
        PermissionMode.ACCEPT_EDITS,
        PermissionMode.PLAN,
    ]

    def cycle_mode(self) -> PermissionMode:
        """Rotate mode: DEFAULT -> ACCEPT_EDITS -> PLAN -> DEFAULT.

        BYPASS is intentionally excluded from cycling; it must be set
        explicitly for safety.

        Returns:
            The new active mode.
        """
        try:
            idx = self._MODE_CYCLE.index(self.current_mode)
        except ValueError:
            # If currently in BYPASS (not in cycle list), reset to DEFAULT
            idx = -1
        next_idx = (idx + 1) % len(self._MODE_CYCLE)
        self.current_mode = self._MODE_CYCLE[next_idx]
        return self.current_mode

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    def check(self, tool_name: str, args: dict[str, Any] | None = None) -> str:
        """Determine whether a tool call should be allowed, denied, or asked.

        Args:
            tool_name: Name of the tool being invoked.
            args: Arguments to the tool (reserved for future rule extensions).

        Returns:
            "allow", "deny", or "ask".
        """
        mode = self.current_mode

        # BYPASS: everything goes through
        if mode == PermissionMode.BYPASS:
            return "allow"

        # PLAN: only read-only tools
        if mode == PermissionMode.PLAN:
            if tool_name in PLAN_ALLOWED_TOOLS:
                return "allow"
            return "deny"

        # ACCEPT_EDITS: auto-allow write_file and edit_file
        if mode == PermissionMode.ACCEPT_EDITS:
            if tool_name in ("write_file", "edit_file"):
                return "allow"
            # Fall through to rule evaluation for other tools

        # Evaluate user-defined rules (first match wins)
        for rule in self.rules:
            if rule.matches(tool_name):
                return rule.action

        # DEFAULT fallback: ask for dangerous tools, allow the rest
        if tool_name in _WRITE_TOOLS:
            return "ask"

        return "allow"

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, tool_pattern: str, action: str) -> PermissionRule:
        """Add a permission rule.

        Args:
            tool_pattern: Glob pattern for tool names.
            action: "allow", "deny", or "ask".

        Returns:
            The newly created rule.

        Raises:
            ValueError: If action is not valid.
        """
        if action not in ("allow", "deny", "ask"):
            raise ValueError(
                f"Invalid action {action!r}. Must be 'allow', 'deny', or 'ask'."
            )
        rule = PermissionRule(tool=tool_pattern, action=action)
        self.rules.append(rule)
        return rule

    def remove_rule(self, index: int) -> bool:
        """Remove a rule by index. Returns True if removed."""
        if 0 <= index < len(self.rules):
            self.rules.pop(index)
            return True
        return False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_rules(self) -> None:
        """Load rules from .astra/permissions.json if it exists."""
        path = self.project_root / ".astra" / "permissions.json"
        if not path.exists():
            return
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            print(
                f"Warning: failed to read {path}: {exc}",
                file=sys.stderr,
            )
            return

        for entry in data.get("rules", []):
            try:
                self.rules.append(PermissionRule.from_dict(entry))
            except (KeyError, TypeError) as exc:
                print(
                    f"Warning: skipping invalid permission rule: {exc}",
                    file=sys.stderr,
                )

        # Optionally restore saved mode
        saved_mode = data.get("mode")
        if saved_mode:
            try:
                self.current_mode = PermissionMode(saved_mode)
            except ValueError:
                pass  # Ignore unknown modes; keep DEFAULT

    def save_rules(self, path: str | None = None) -> None:
        """Save current rules and mode to .astra/permissions.json."""
        target = Path(path) if path else (self.project_root / ".astra" / "permissions.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "mode": self.current_mode.value,
            "rules": [r.to_dict() for r in self.rules],
        }
        target.write_text(
            json.dumps(data, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

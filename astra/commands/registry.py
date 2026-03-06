"""Command registry and dispatcher for slash commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from astra.agent.controller import AgentController


@dataclass
class CommandDefinition:
    """A single slash command."""

    name: str
    description: str
    usage: str
    handler: Callable[..., str | None]
    aliases: list[str] | None = None


class CommandRegistry:
    """Registry for all slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, cmd: CommandDefinition) -> None:
        """Register a command and its aliases."""
        self._commands[cmd.name] = cmd
        if cmd.aliases:
            for alias in cmd.aliases:
                self._aliases[alias] = cmd.name

    def get(self, name: str) -> CommandDefinition | None:
        """Get a command by name or alias."""
        resolved = self._aliases.get(name, name)
        return self._commands.get(resolved)

    def list_commands(self) -> list[CommandDefinition]:
        """Return all registered commands sorted by name."""
        return sorted(self._commands.values(), key=lambda c: c.name)

    def is_command(self, text: str) -> bool:
        """Check if the input text is a slash command."""
        return text.strip().startswith("/")

    def dispatch(self, text: str, agent: AgentController) -> str | None:
        """Parse and execute a slash command. Returns output text or None."""
        text = text.strip()
        if not text.startswith("/"):
            return None

        parts = text[1:].split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        cmd = self.get(cmd_name)
        if cmd is None:
            return f"Unknown command: /{cmd_name}. Type /help to see all commands."

        return cmd.handler(agent, args)


def build_command_registry() -> CommandRegistry:
    """Build the registry with all built-in slash commands."""
    from astra.commands.handlers import ALL_COMMANDS

    registry = CommandRegistry()
    for cmd in ALL_COMMANDS:
        registry.register(cmd)
    return registry

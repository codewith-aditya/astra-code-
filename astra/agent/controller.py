"""Agent controller -- full-featured agentic loop with all systems integrated."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.text import Text
from rich.theme import Theme

from astra.agent.context import ContextManager
from astra.agent.planner import Planner
from astra.agent.plan_mode import PlanModeController
from astra.commands.registry import CommandRegistry, build_command_registry
from astra.config import Config
from astra.hooks import HookManager
from astra.llm.client import LLMClient
from astra.permissions import PermissionManager
from astra.sandbox import SandboxManager
from astra.session.checkpoint import CheckpointManager
from astra.session.manager import SessionManager
from astra.telemetry import TelemetryManager
from astra.tools.registry import ToolDefinition, ToolRegistry, build_registry

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
})
console = Console(theme=custom_theme)

# Status messages for different iterations
_THINKING_PHASES = [
    "Thinking",
    "Analyzing",
    "Working",
    "Processing",
    "Reasoning",
]

_SPINNERS = ["dots2", "dots2", "dots2", "dots2", "dots2"]

# Circular orb spinner frames
_ORB_FRAMES = ["◐", "◓", "◑", "◒"]

# Register custom spinner in Rich
from rich.spinner import SPINNERS as _RICH_SPINNERS
_RICH_SPINNERS["orb"] = {"interval": 120, "frames": _ORB_FRAMES}


class _CircleStatus:
    """Animated circular orb spinner with label text."""

    def __init__(self, text: str, console: Console) -> None:
        self._text = text
        self._console = console
        self._spinner = Spinner("orb", text, style="bold cyan")
        self._live: Live | None = None

    def start(self) -> None:
        self._live = Live(self._spinner, console=self._console, refresh_per_second=12, transient=True)
        self._live.start()

    def stop(self) -> None:
        if self._live:
            self._live.stop()
            self._live = None


def _phase_label(iteration: int) -> str:
    """Get a phase label based on iteration number."""
    idx = min(iteration - 1, len(_THINKING_PHASES) - 1)
    return _THINKING_PHASES[idx]


def _format_tokens(n: int) -> str:
    """Format token count with K suffix for large numbers."""
    if n >= 10_000:
        return f"{n / 1000:.1f}K"
    if n >= 1_000:
        return f"{n:,}"
    return str(n)


def _format_time(seconds: float) -> str:
    """Format elapsed time."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}m {secs}s"


class AgentController:
    """Drives the full agent loop with all features integrated."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.registry: ToolRegistry = build_registry()
        self.context = ContextManager(repo_path=config.repo_path)
        self.planner = Planner()
        self.plan_mode = PlanModeController()
        self.command_registry: CommandRegistry = build_command_registry()
        self.permission_mgr = PermissionManager()
        self.sandbox = SandboxManager()
        self.checkpoint_mgr = CheckpointManager()
        self.session_mgr = SessionManager(config.repo_path)
        self.telemetry = TelemetryManager()
        self.hook_mgr = HookManager(config.repo_path)
        self.iteration = 0
        self.plugins: dict[str, list[str]] = {}
        self._subagent_mgr = None
        self._auto_approved_tools: set[str] = set()  # tools approved with "always"

        # Load plugins
        self._load_plugins()

        # Build LLM client with all tools registered
        self.llm = LLMClient(config, self.registry.to_schemas())

        # Fire session start hook
        self.hook_mgr.fire("SessionStart", {"repo_path": config.repo_path})

    # ------------------------------------------------------------------
    # Plugin system
    # ------------------------------------------------------------------
    def _load_plugins(self) -> None:
        plugin_dir = Path(self.config.repo_path).resolve() / ".astra" / "plugins"
        if not plugin_dir.exists():
            return

        for plugin_file in sorted(plugin_dir.glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(
                    f"astra_plugin_{plugin_file.stem}", plugin_file
                )
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                tools = getattr(module, "TOOLS", [])
                tool_names = []
                for tool in tools:
                    if isinstance(tool, ToolDefinition):
                        self.registry.register(tool)
                        tool_names.append(tool.name)

                if tool_names:
                    self.plugins[plugin_file.stem] = tool_names
                    console.print(f"[dim]Plugin: {plugin_file.stem} ({', '.join(tool_names)})[/dim]")
            except Exception as exc:
                console.print(f"[warning]Plugin {plugin_file.stem} failed: {exc}[/warning]")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self, user_input: str) -> None:
        console.print()
        console.print(Panel(
            user_input,
            title="[bold white]User[/bold white]",
            border_style="bright_blue",
            padding=(0, 1),
        ))

        # Fire user prompt hook
        hook_result = self.hook_mgr.fire("UserPromptSubmit", {"content": user_input})
        if hook_result and hook_result.action == "block":
            console.print(f"[warning]Blocked by hook: {hook_result.reason}[/warning]")
            return

        self.context.add_user_message(user_input)
        self.iteration = 0

        while self.iteration < self.config.max_iterations:
            self.iteration += 1
            phase = _phase_label(self.iteration)

            # Show thinking status
            status_handle = _CircleStatus(
                f"[bold cyan]  {phase}...[/bold cyan]",
                console=console,
            )
            status_handle.start()

            # Callback to stop spinner when first token arrives
            def on_first_chunk():
                status_handle.stop()
                console.print()  # clean line after spinner

            try:
                response = self.llm.chat(
                    self.context.get_messages(),
                    stream=True,
                    on_first_chunk=on_first_chunk,
                )
            except KeyboardInterrupt:
                status_handle.stop()
                console.print("\n[warning]Interrupted.[/warning]")
                break
            except Exception as exc:
                status_handle.stop()
                console.print(f"[error]LLM error: {exc}[/error]")
                self.telemetry.current.errors += 1
                break

            # Make sure spinner is stopped (if no streaming text was produced)
            status_handle.stop()

            self.telemetry.current.api_requests += 1

            # Show stats line
            self._print_stats(response)

            if not response["tool_calls"]:
                self._add_assistant_text(response["text"])
                # Fire stop hook
                self.hook_mgr.fire("Stop", {"text": response["text"]})
                break

            # Plan mode check
            if self.plan_mode.is_active:
                blocked = []
                for tc in response["tool_calls"]:
                    if not self.plan_mode.is_tool_allowed(tc["name"]):
                        blocked.append(tc["name"])
                if blocked:
                    console.print(
                        f"[warning]Plan mode: blocked tools: {', '.join(blocked)}[/warning]"
                    )

            assistant_content = self._build_assistant_content(response)
            self.context.add_assistant_message(assistant_content)

            tool_results = self._execute_tool_calls(response["tool_calls"])
            self.context.add_tool_results(tool_results)

            self.context.trim_if_needed()
        else:
            console.print("[error]Reached maximum iterations. Stopping.[/error]")

    # ------------------------------------------------------------------
    # Stats display
    # ------------------------------------------------------------------
    def _print_stats(self, response: dict) -> None:
        """Print token usage and timing after each LLM response."""
        tracker = self.llm.token_tracker
        timing = response.get("timing", 0.0)
        has_tools = bool(response.get("tool_calls"))

        parts = []
        if tracker.last_input or tracker.last_output:
            parts.append(f"{_format_tokens(tracker.last_input)} in")
            parts.append(f"{_format_tokens(tracker.last_output)} out")
        if timing > 0:
            parts.append(_format_time(timing))
        if has_tools:
            n = len(response["tool_calls"])
            parts.append(f"{n} tool{'s' if n > 1 else ''}")

        if parts:
            stats_text = " | ".join(parts)
            console.print(f"[dim]  [{stats_text}][/dim]")

    # ------------------------------------------------------------------
    # Interactive REPL
    # ------------------------------------------------------------------
    def repl(self) -> None:
        console.print()
        console.print(Panel(
            "[bold cyan]  ◆ ASTRA[/bold cyan] [dim]v0.1.0[/dim]  —  AI Coding Agent\n"
            "[dim]  Type your request · [bold]/help[/bold] for commands · Ctrl+C to stop · /exit to quit[/dim]",
            border_style="cyan",
            padding=(0, 2),
        ))

        # Show startup info
        info_parts = []
        astra_md = Path(self.config.repo_path).resolve() / "ASTRA.md"
        if astra_md.exists():
            info_parts.append("ASTRA.md loaded")
        memory = self.context.list_memory()
        if memory:
            info_parts.append(f"{len(memory)} memories")
        if self.plugins:
            info_parts.append(f"{len(self.plugins)} plugin(s)")

        # Load rules
        from astra.rules import RulesManager
        rules_mgr = RulesManager()
        rules = rules_mgr.load_rules(self.config.repo_path)
        if rules:
            info_parts.append(f"{len(rules)} rule(s)")

        info_parts.append(f"model: {self.config.model}")

        if info_parts:
            console.print(f"[dim]  {' | '.join(info_parts)}[/dim]")

        # Prompt suggestions
        from astra.ui import get_prompt_suggestions
        suggestions = get_prompt_suggestions(self.context.messages, self.config.repo_path)
        if suggestions:
            console.print()
            console.print("  [dim]Try:[/dim]")
            for s in suggestions:
                console.print(f"  [dim]  • {s}[/dim]")

        while True:
            try:
                # Show mode indicator
                mode = ""
                if self.plan_mode.is_active:
                    mode = "[yellow][PLAN] [/yellow]"
                user_input = console.input(f"\n{mode}[bold cyan]>>> [/bold cyan]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break

            # Bash shortcut: !command
            if user_input.startswith("!"):
                import subprocess
                cmd = user_input[1:].strip()
                if cmd:
                    try:
                        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                        if result.stdout:
                            console.print(result.stdout.rstrip())
                        if result.stderr:
                            console.print(f"[dim]{result.stderr.rstrip()}[/dim]")
                    except Exception as exc:
                        console.print(f"[error]{exc}[/error]")
                continue

            # Slash command handling
            if self.command_registry.is_command(user_input):
                result = self.command_registry.dispatch(user_input, self)
                if result == "__EXIT__":
                    console.print("[dim]Goodbye![/dim]")
                    break
                if isinstance(result, str):
                    console.print(result)
                continue

            self.run(user_input)

            # Post-run suggestions
            suggestions = get_prompt_suggestions(self.context.messages)
            if suggestions:
                console.print()
                console.print("  [dim]Try:[/dim]")
                for s in suggestions:
                    console.print(f"  [dim]  • {s}[/dim]")

        # Cleanup
        self._print_session_summary()
        self.telemetry.save()
        self.hook_mgr.fire("SessionEnd", {})

    # ------------------------------------------------------------------
    # Session summary on exit
    # ------------------------------------------------------------------
    def _print_session_summary(self) -> None:
        """Show a summary when the session ends."""
        tracker = self.llm.token_tracker
        if tracker.request_count == 0:
            return

        total = tracker.total_input + tracker.total_output
        cost = tracker.estimate_cost(self.config.model)

        console.print()
        console.print(
            f"[dim]  Session: {tracker.request_count} requests | "
            f"{_format_tokens(total)} tokens | "
            f"${cost:.4f} est. cost[/dim]"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _add_assistant_text(self, text: str) -> None:
        if text:
            self.context.add_assistant_message(text)

    @staticmethod
    def _build_assistant_content(response: dict) -> list[dict]:
        content: list[dict] = []
        if response["text"]:
            content.append({"type": "text", "text": response["text"]})
        for tc in response["tool_calls"]:
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["arguments"],
            })
        return content

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        results: list[dict] = []

        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]
            call_id = tc["id"]

            # Tool call display
            args_preview = self._compact_args(args)
            console.print(
                f"\n  [bold yellow]⚡ {name}[/bold yellow] [dim]{args_preview}[/dim]"
            )

            # Plan mode block
            if self.plan_mode.is_active and not self.plan_mode.is_tool_allowed(name):
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": json.dumps({"error": f"Tool '{name}' not available in plan mode. Only read-only tools allowed."}),
                })
                console.print(f"  [warning]Blocked (plan mode)[/warning]")
                continue

            # Pre-tool hook
            hook_result = self.hook_mgr.fire("PreToolUse", {"tool": name, "args": args})
            if hook_result and hook_result.action == "block":
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": json.dumps({"error": f"Blocked by hook: {hook_result.reason}"}),
                })
                continue

            # Permission check
            perm = self.permission_mgr.check(name, args)
            if perm == "deny":
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": json.dumps({"error": "Permission denied."}),
                })
                console.print(f"  [warning]Denied[/warning]")
                continue

            if perm == "ask" and not self.config.auto_approve_tools:
                if name not in self._auto_approved_tools:
                    decision = self._confirm_tool(name, args)
                    if decision == "deny":
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": json.dumps({"error": "User denied tool execution."}),
                        })
                        continue
                    elif decision == "always":
                        self._auto_approved_tools.add(name)

            # Sandbox check
            if name in ("write_file", "edit_file"):
                path = args.get("path", "")
                allowed, reason = self.sandbox.check_write(path)
                if not allowed:
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": json.dumps({"error": reason}),
                    })
                    continue

            # Auto-checkpoint before file modifications
            if name in ("write_file", "edit_file", "multi_edit"):
                path = args.get("path", "")
                if Path(path).exists():
                    self.checkpoint_mgr.auto_checkpoint(path, len(self.context.messages))

            # Execute with spinner
            tool_start = time.time()
            tool_spinner = _CircleStatus(f"[dim]  Running {name}...[/dim]", console=console)
            tool_spinner.start()
            try:
                result = asyncio.run(self.registry.execute(name, **args))
            finally:
                tool_spinner.stop()
            tool_time = time.time() - tool_start

            result_str = json.dumps(result, indent=2, default=str)

            # Track telemetry
            self.telemetry.current.record_tool(name)

            # Post-tool hook
            self.hook_mgr.fire("PostToolUse", {"tool": name, "args": args, "result": result_str[:500]})

            # Show result - smart display based on tool type
            display = self._format_tool_result(name, result)
            console.print(
                f"  [dim green]✓[/dim green] [dim]{name}[/dim] [dim]({_format_time(tool_time)})[/dim]"
            )
            if display:
                console.print(Panel(
                    display,
                    border_style="dim green",
                    padding=(0, 1),
                ))

            results.append({
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": result_str,
            })

        return results

    @staticmethod
    def _format_tool_result(name: str, result: dict) -> str:
        """Format tool result for display — clean, human-readable."""
        if "error" in result:
            return f"[red]Error:[/red] {result['error']}"

        # run_command: show stdout/stderr cleanly, not as JSON
        if name == "run_command":
            parts = []
            stdout = result.get("stdout", "").strip()
            stderr = result.get("stderr", "").strip()
            exit_code = result.get("exit_code", 0)

            if stdout:
                # Truncate long output
                lines = stdout.splitlines()
                if len(lines) > 30:
                    shown = "\n".join(lines[:15]) + f"\n[dim]... ({len(lines) - 15} more lines)[/dim]\n" + "\n".join(lines[-5:])
                else:
                    shown = stdout
                parts.append(shown)
            if stderr:
                stderr_lines = stderr.splitlines()
                shown_err = "\n".join(stderr_lines[:10])
                parts.append(f"[yellow]{shown_err}[/yellow]")
            if exit_code != 0:
                parts.append(f"[red]exit code: {exit_code}[/red]")

            return "\n".join(parts) if parts else "[dim]Done (no output)[/dim]"

        # read_file / write_file / edit_file: brief status
        if name in ("write_file", "edit_file", "multi_edit"):
            path = result.get("path", "")
            status = result.get("status", "ok")
            replacements = result.get("replacements", "")
            rep_str = f" ({replacements} replacement{'s' if replacements != 1 else ''})" if replacements else ""
            return f"[green]{status}[/green] {path}{rep_str}"

        if name == "read_file":
            content = result.get("content", "")
            lines = content.splitlines() if content else []
            return f"[dim]{len(lines)} lines read[/dim]"

        # glob/grep: show matches count
        if name in ("glob_search", "grep_search", "search_code"):
            matches = result.get("matches", result.get("files", []))
            if isinstance(matches, list):
                count = len(matches)
                preview = "\n".join(str(m) for m in matches[:8])
                suffix = f"\n[dim]... {count - 8} more[/dim]" if count > 8 else ""
                return f"[dim]{count} match{'es' if count != 1 else ''}[/dim]\n{preview}{suffix}" if preview else f"[dim]{count} matches[/dim]"

        # Default: compact JSON, max 800 chars
        raw = json.dumps(result, indent=2, default=str)
        if len(raw) > 800:
            return raw[:800] + f"\n[dim]... ({len(raw):,} chars total)[/dim]"
        return raw

    @staticmethod
    def _compact_args(args: dict) -> str:
        """Create a compact one-line preview of tool arguments."""
        if not args:
            return ""
        parts = []
        for k, v in args.items():
            val_str = str(v)
            if len(val_str) > 50:
                val_str = val_str[:47] + "..."
            parts.append(f"{k}={val_str}")
        preview = ", ".join(parts)
        if len(preview) > 120:
            preview = preview[:117] + "..."
        return preview

    @staticmethod
    def _confirm_tool(name: str, args: dict) -> str:
        """Ask user to approve a tool. Returns 'allow', 'deny', or 'always'."""
        console.print(
            f"\n  [bold yellow]⚠ Approve [cyan]{name}[/cyan]?[/bold yellow]  "
            f"[dim]y[/dim] yes  [dim]n[/dim] no  [dim]a[/dim] always"
        )
        try:
            answer = console.input("  [dim]>[/dim] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "deny"
        if answer in ("a", "always"):
            return "always"
        if answer in ("y", "yes"):
            return "allow"
        return "deny"

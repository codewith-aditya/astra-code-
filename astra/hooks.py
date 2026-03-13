"""Hooks system -- lifecycle event hooks with shell command execution.

Hooks let users attach shell commands to agent lifecycle events.
Configuration lives in .astra/hooks.json.  Each hook fires a shell
command via subprocess, passing event context as JSON on stdin.

Exit codes control behaviour:
    0  -> allow  (proceed normally)
    2  -> block  (cancel the action, with optional reason)
    *  -> pass   (treat as transparent / no opinion)

Matchers let hooks target specific tools for PreToolUse / PostToolUse.
"""

from __future__ import annotations

import enum
import fnmatch
import json
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Enums and data structures
# -----------------------------------------------------------------------

class HookEvent(enum.Enum):
    """Lifecycle events that hooks can subscribe to."""

    SESSION_START = "session_start"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    STOP = "stop"
    PRE_COMPACT = "pre_compact"
    SESSION_END = "session_end"


class HookAction(enum.Enum):
    """Possible outcomes of a hook invocation."""

    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"
    PASS = "pass"


@dataclass
class HookResult:
    """Result returned after firing a hook.

    Attributes:
        action:  What the hook decided (allow / block / modify / pass).
        reason:  Human-readable explanation, typically from the hook's
                 stderr or JSON output.
        output:  Raw stdout captured from the hook process.
        modified_context:  If action is MODIFY, this dict contains the
                           updated context values to apply.
    """

    action: HookAction = HookAction.ALLOW
    reason: str = ""
    output: str = ""
    modified_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookDefinition:
    """A single hook binding.

    Attributes:
        event:    The lifecycle event this hook listens to.
        command:  Shell command to execute (passed to the platform shell).
        matcher:  Optional glob pattern matched against the tool name.
                  Only relevant for PRE_TOOL_USE and POST_TOOL_USE events.
                  If None, the hook fires for every invocation of that event.
        timeout:  Maximum seconds to wait for the hook process.
    """

    event: HookEvent
    command: str
    matcher: Optional[str] = None
    timeout: float = 30.0


# -----------------------------------------------------------------------
# HookManager
# -----------------------------------------------------------------------

class HookManager:
    """Loads hook definitions from config and fires them on demand.

    Typical usage::

        manager = HookManager(repo_path=".")
        manager.load_hooks()

        result = manager.fire(
            HookEvent.PRE_TOOL_USE,
            {"tool_name": "run_command", "arguments": {"command": "rm -rf /"}},
        )
        if result.action == HookAction.BLOCK:
            print(f"Blocked: {result.reason}")
    """

    # Default timeout for hook processes (seconds).
    DEFAULT_TIMEOUT: float = 30.0

    # Default config file path relative to repo root.
    CONFIG_RELPATH: str = ".astra/hooks.json"

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()
        self._hooks: list[HookDefinition] = []
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_hooks(self) -> None:
        """Load hook definitions from .astra/hooks.json.

        The config file uses the following schema::

            {
              "hooks": [
                {
                  "event": "pre_tool_use",
                  "command": "python .astra/scripts/guard.py",
                  "matcher": "run_command",
                  "timeout": 10
                }
              ]
            }

        If the config file does not exist, no hooks are loaded (this is
        not an error).
        """
        self._hooks.clear()
        config_path = self.repo_path / self.CONFIG_RELPATH

        if not config_path.exists():
            self._loaded = True
            return

        try:
            raw = config_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse hooks config at %s: %s", config_path, exc)
            self._loaded = True
            return

        hook_list = data.get("hooks", [])
        if not isinstance(hook_list, list):
            logger.warning("hooks.json 'hooks' key must be a list; ignoring.")
            self._loaded = True
            return

        for idx, entry in enumerate(hook_list):
            hook = self._parse_hook_entry(entry, idx)
            if hook is not None:
                self._hooks.append(hook)

        self._loaded = True
        logger.info("Loaded %d hook(s) from %s", len(self._hooks), config_path)

    def _parse_hook_entry(
        self, entry: dict[str, Any], index: int
    ) -> HookDefinition | None:
        """Parse a single hook entry from the config."""
        if not isinstance(entry, dict):
            logger.warning("Hook entry #%d is not a dict; skipping.", index)
            return None

        event_str = entry.get("event")
        command = entry.get("command")

        if not event_str or not command:
            logger.warning(
                "Hook entry #%d missing required 'event' or 'command'; skipping.",
                index,
            )
            return None

        # Resolve event enum
        try:
            event = HookEvent(event_str)
        except ValueError:
            logger.warning(
                "Hook entry #%d has unknown event '%s'; skipping.", index, event_str
            )
            return None

        matcher = entry.get("matcher")
        if matcher is not None and not isinstance(matcher, str):
            logger.warning(
                "Hook entry #%d 'matcher' must be a string; ignoring matcher.", index
            )
            matcher = None

        timeout = entry.get("timeout", self.DEFAULT_TIMEOUT)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            timeout = self.DEFAULT_TIMEOUT

        return HookDefinition(
            event=event,
            command=str(command),
            matcher=matcher,
            timeout=float(timeout),
        )

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    @property
    def hooks(self) -> list[HookDefinition]:
        """Return all loaded hook definitions."""
        return list(self._hooks)

    @property
    def loaded(self) -> bool:
        """Whether load_hooks() has been called."""
        return self._loaded

    def hooks_for_event(
        self, event: HookEvent, tool_name: str | None = None
    ) -> list[HookDefinition]:
        """Return hooks matching *event* and optionally *tool_name*.

        For PRE_TOOL_USE and POST_TOOL_USE events, only hooks whose
        matcher is None (wildcard) or matches the tool name via
        ``fnmatch`` are returned.
        """
        matched: list[HookDefinition] = []
        for hook in self._hooks:
            if hook.event != event:
                continue

            # Apply matcher filtering for tool events
            if event in (HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE):
                if hook.matcher is not None and tool_name is not None:
                    if not fnmatch.fnmatch(tool_name, hook.matcher):
                        continue

            matched.append(hook)
        return matched

    # ------------------------------------------------------------------
    # Firing
    # ------------------------------------------------------------------

    def fire(
        self,
        event: HookEvent,
        context: dict[str, Any] | None = None,
    ) -> HookResult:
        """Fire all hooks for *event*, passing *context* as JSON on stdin.

        Hooks are executed sequentially in definition order.  The first
        hook that returns BLOCK stops execution and its result is
        returned immediately.  If a hook returns MODIFY, the modified
        context is merged into the running context for subsequent hooks.

        Parameters
        ----------
        event:
            The lifecycle event being triggered.
        context:
            Arbitrary dict serialised to JSON and piped into the hook
            process on stdin.  For tool events this typically includes
            ``tool_name`` and ``arguments``.

        Returns
        -------
        HookResult
            Aggregate result.  If no hooks matched, returns ALLOW with
            empty output.
        """
        if not self._loaded:
            self.load_hooks()

        ctx = dict(context) if context else {}
        tool_name = ctx.get("tool_name")

        matching = self.hooks_for_event(event, tool_name=tool_name)
        if not matching:
            return HookResult(action=HookAction.ALLOW)

        aggregate = HookResult(action=HookAction.ALLOW)

        for hook in matching:
            result = self._run_hook(hook, ctx)

            if result.action == HookAction.BLOCK:
                return result

            if result.action == HookAction.MODIFY and result.modified_context:
                ctx.update(result.modified_context)
                aggregate.action = HookAction.MODIFY
                aggregate.modified_context.update(result.modified_context)

            # Collect output
            if result.output:
                if aggregate.output:
                    aggregate.output += "\n"
                aggregate.output += result.output

            if result.reason:
                aggregate.reason = result.reason

        return aggregate

    def _run_hook(
        self, hook: HookDefinition, context: dict[str, Any]
    ) -> HookResult:
        """Execute a single hook command and interpret the result."""
        payload = json.dumps(
            {
                "event": hook.event.value,
                "context": context,
            },
            default=str,
        )

        # Determine shell usage per platform
        use_shell = True

        try:
            proc = subprocess.run(
                hook.command,
                input=payload,
                capture_output=True,
                text=True,
                timeout=hook.timeout,
                shell=use_shell,
                cwd=str(self.repo_path),
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Hook timed out after %.1fs: %s", hook.timeout, hook.command
            )
            return HookResult(
                action=HookAction.PASS,
                reason="Hook timed out (%.1fs limit)" % hook.timeout,
            )
        except FileNotFoundError:
            logger.warning("Hook command not found: %s", hook.command)
            return HookResult(
                action=HookAction.PASS,
                reason="Hook command not found: %s" % hook.command,
            )
        except OSError as exc:
            logger.warning("Hook execution failed: %s -- %s", hook.command, exc)
            return HookResult(
                action=HookAction.PASS,
                reason="Hook execution error: %s" % str(exc),
            )

        stdout = proc.stdout.strip() if proc.stdout else ""
        stderr = proc.stderr.strip() if proc.stderr else ""

        return self._interpret_exit_code(proc.returncode, stdout, stderr)

    @staticmethod
    def _interpret_exit_code(
        code: int, stdout: str, stderr: str
    ) -> HookResult:
        """Map a process exit code to a HookResult.

        Exit codes:
            0  -> ALLOW
            2  -> BLOCK  (reason taken from stderr or stdout JSON)
            *  -> PASS   (no opinion; transparent)
        """
        if code == 0:
            # Check if stdout contains a JSON modification payload
            modified = _try_parse_modify_payload(stdout)
            if modified is not None:
                return HookResult(
                    action=HookAction.MODIFY,
                    reason=stderr,
                    output=stdout,
                    modified_context=modified,
                )
            return HookResult(
                action=HookAction.ALLOW,
                reason=stderr,
                output=stdout,
            )

        if code == 2:
            # BLOCK -- use stderr as reason, fall back to stdout
            reason = stderr if stderr else stdout
            return HookResult(
                action=HookAction.BLOCK,
                reason=reason,
                output=stdout,
            )

        # Any other exit code is treated as pass-through
        return HookResult(
            action=HookAction.PASS,
            reason=stderr if stderr else ("Hook exited with code %d" % code),
            output=stdout,
        )

    # ------------------------------------------------------------------
    # Config template
    # ------------------------------------------------------------------

    @classmethod
    def generate_default_config(cls, repo_path: str = ".") -> str:
        """Generate a default hooks.json template and write it to disk.

        Returns the absolute path to the created config file.
        """
        config_dir = Path(repo_path).resolve() / ".astra"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "hooks.json"

        template = _default_hooks_template()
        config_path.write_text(
            json.dumps(template, indent=2), encoding="utf-8"
        )

        return str(config_path)

    @classmethod
    def default_config_template(cls) -> dict[str, Any]:
        """Return the default hooks config template as a dict."""
        return _default_hooks_template()


# -----------------------------------------------------------------------
# Helpers (module-private)
# -----------------------------------------------------------------------

def _try_parse_modify_payload(stdout: str) -> dict[str, Any] | None:
    """Attempt to parse stdout as a JSON modify payload.

    If stdout is valid JSON containing a top-level key ``"modify"``,
    return that dict.  Otherwise return None.
    """
    if not stdout:
        return None
    try:
        data = json.loads(stdout)
        if isinstance(data, dict) and "modify" in data:
            modify = data["modify"]
            if isinstance(modify, dict):
                return modify
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _default_hooks_template() -> dict[str, Any]:
    """Return the default hooks.json template structure."""
    return {
        "_comment": (
            "Astra hooks configuration. "
            "Each hook runs a shell command when its event fires. "
            "Context is passed as JSON on stdin. "
            "Exit 0 = allow, exit 2 = block (reason on stderr), other = pass."
        ),
        "hooks": [
            {
                "_comment": (
                    "Example: log every tool call to a file."
                ),
                "event": "pre_tool_use",
                "command": "echo hook fired >> .astra/hook_log.txt",
                "matcher": None,
                "timeout": 10,
            },
            {
                "_comment": (
                    "Example: block dangerous shell commands. "
                    "Write a script that reads JSON from stdin and "
                    "exits with code 2 to block."
                ),
                "event": "pre_tool_use",
                "command": "python .astra/scripts/guard.py",
                "matcher": "run_command",
                "timeout": 15,
            },
            {
                "_comment": "Example: notify on session start.",
                "event": "session_start",
                "command": "echo session started >> .astra/hook_log.txt",
                "timeout": 5,
            },
        ],
    }

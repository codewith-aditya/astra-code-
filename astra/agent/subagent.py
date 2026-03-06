"""Subagent system -- isolated agents that run in foreground or background threads.

Each SubAgent gets its own LLMClient and ContextManager, runs a simplified
agent loop (no interactive UI), and returns a result string to the caller.
SubAgentManager tracks all running and completed subagents.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from astra.agent.context import ContextManager
from astra.config import Config
from astra.llm.client import LLMClient
from astra.tools.registry import ToolRegistry, build_registry

logger = logging.getLogger(__name__)


# ======================================================================
# Status enum
# ======================================================================

class SubAgentStatus(Enum):
    """Lifecycle status of a subagent."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ======================================================================
# Built-in agent type definitions
# ======================================================================

EXPLORE_SYSTEM_PROMPT = """\
You are an Astra sub-agent specialising in codebase exploration and research.

Your job is to investigate the repository and answer questions about it.
You have access to tools for reading files, searching code, and listing
directory contents. Use them methodically.

RULES:
1. Be thorough -- check multiple files when needed.
2. DO NOT modify any files. Only read and search.
3. Summarise your findings clearly at the end.
4. If you cannot find the answer, say so explicitly.
5. Keep your final summary concise but complete.
"""

PLAN_SYSTEM_PROMPT = """\
You are an Astra sub-agent specialising in implementation planning.

Your job is to analyse the repository and produce a detailed, step-by-step
implementation plan for the requested change. You may read and search files
to understand the existing architecture.

RULES:
1. Read relevant files to understand the current structure.
2. DO NOT modify any files. Only read and search.
3. Produce a numbered plan with concrete actions (file paths, function names).
4. Note any risks, edge cases, or dependencies.
5. Keep the plan actionable -- another agent will execute it.
"""

# Read-only tools allowed for subagents that should not mutate the repo.
_READ_ONLY_TOOLS = {"read_file", "search_code", "list_files"}


@dataclass
class AgentTypeSpec:
    """Specification for a built-in subagent type."""

    name: str
    system_prompt: str
    allowed_tools: set[str]
    default_max_turns: int


BUILTIN_AGENT_TYPES: dict[str, AgentTypeSpec] = {
    "explore": AgentTypeSpec(
        name="Explore",
        system_prompt=EXPLORE_SYSTEM_PROMPT,
        allowed_tools=_READ_ONLY_TOOLS,
        default_max_turns=15,
    ),
    "plan": AgentTypeSpec(
        name="Plan",
        system_prompt=PLAN_SYSTEM_PROMPT,
        allowed_tools=_READ_ONLY_TOOLS,
        default_max_turns=20,
    ),
}


# ======================================================================
# SubAgent
# ======================================================================

class SubAgent:
    """An isolated agent that runs its own agentic loop.

    Parameters
    ----------
    agent_id : str
        Unique identifier for this subagent instance.
    task : str
        Natural-language description of what the subagent should do.
    config : Config
        Astra configuration (API keys, model, repo path, etc.).
    agent_type : str | None
        One of the built-in type keys ("explore", "plan") or None for a
        generic subagent that uses all tools and the default prompt.
    system_prompt : str | None
        Override the system prompt (takes precedence over agent_type).
    max_turns : int | None
        Maximum number of LLM turns before the agent stops.  Defaults to
        the agent type's default or 15 if no type is given.
    allowed_tools : set[str] | None
        Restrict available tools to this set.  ``None`` means all tools.
    """

    def __init__(
        self,
        agent_id: str,
        task: str,
        config: Config,
        agent_type: str | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        allowed_tools: set[str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.task = task
        self.config = config
        self.status = SubAgentStatus.PENDING
        self.result: str = ""
        self.error: str = ""
        self.turns_used: int = 0
        self._cancel_event = threading.Event()

        # Resolve agent type spec
        type_spec: AgentTypeSpec | None = None
        if agent_type is not None:
            type_spec = BUILTIN_AGENT_TYPES.get(agent_type.lower())
            if type_spec is None:
                valid = ", ".join(sorted(BUILTIN_AGENT_TYPES.keys()))
                raise ValueError(
                    f"Unknown agent type '{agent_type}'. "
                    f"Valid types: {valid}"
                )

        # System prompt precedence: explicit > type spec > default
        if system_prompt is not None:
            self._system_prompt = system_prompt
        elif type_spec is not None:
            self._system_prompt = type_spec.system_prompt
        else:
            self._system_prompt = (
                "You are an Astra sub-agent. Complete the assigned task "
                "using the available tools, then provide a clear summary "
                "of your findings or results."
            )

        # Max turns precedence: explicit > type spec > 15
        if max_turns is not None:
            self.max_turns = max_turns
        elif type_spec is not None:
            self.max_turns = type_spec.default_max_turns
        else:
            self.max_turns = 15

        # Allowed tools precedence: explicit > type spec > None (all)
        if allowed_tools is not None:
            self._allowed_tools = allowed_tools
        elif type_spec is not None:
            self._allowed_tools = type_spec.allowed_tools
        else:
            self._allowed_tools = None  # all tools

        # Build isolated tool registry (filtered if needed)
        full_registry = build_registry()
        if self._allowed_tools is not None:
            self.registry = ToolRegistry()
            for tool_def in full_registry.list_tools():
                if tool_def.name in self._allowed_tools:
                    self.registry.register(tool_def)
        else:
            self.registry = full_registry

        # Build isolated context manager (fresh message list)
        self.context = ContextManager(repo_path=config.repo_path)

        # Build LLM client with subagent-specific prompt and tool schemas
        self.llm = LLMClient(
            config,
            self.registry.to_schemas(),
            system_prompt=self._system_prompt,
        )

        # Timing
        self._start_time: float = 0.0
        self._end_time: float = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> str:
        """Execute the subagent loop synchronously. Returns the result text.

        This is the main entry point.  For background execution, use
        ``SubAgentManager.launch_background()``.
        """
        self.status = SubAgentStatus.RUNNING
        self._start_time = time.monotonic()
        try:
            self._agent_loop()
            if self.status == SubAgentStatus.RUNNING:
                # Normal completion (not cancelled)
                self.status = SubAgentStatus.COMPLETED
        except Exception as exc:
            self.status = SubAgentStatus.FAILED
            self.error = str(exc)
            logger.error("SubAgent %s failed: %s", self.agent_id, exc)
            self.result = f"[SubAgent FAILED] {exc}"
        finally:
            self._end_time = time.monotonic()
        return self.result

    def cancel(self) -> None:
        """Signal the subagent to stop at the next turn boundary."""
        self._cancel_event.set()

    @property
    def is_done(self) -> bool:
        return self.status in (
            SubAgentStatus.COMPLETED,
            SubAgentStatus.FAILED,
            SubAgentStatus.CANCELLED,
        )

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time == 0.0:
            return 0.0
        end = self._end_time if self._end_time > 0.0 else time.monotonic()
        return end - self._start_time

    def summary(self) -> str:
        """Return a short status line for display."""
        elapsed = f"{self.elapsed_seconds:.1f}s"
        parts = [
            f"SubAgent[{self.agent_id[:8]}]",
            f"status={self.status.value}",
            f"turns={self.turns_used}/{self.max_turns}",
            f"elapsed={elapsed}",
        ]
        return " | ".join(parts)

    # ------------------------------------------------------------------
    # Internal agent loop
    # ------------------------------------------------------------------

    def _agent_loop(self) -> None:
        """Simplified agentic loop -- no interactive UI, no approval gates."""
        # Seed the conversation with the task
        self.context.add_user_message(self.task)

        last_text = ""

        for turn in range(1, self.max_turns + 1):
            # Check for cancellation
            if self._cancel_event.is_set():
                self.status = SubAgentStatus.CANCELLED
                self.result = (
                    last_text
                    or "[SubAgent cancelled before producing a result]"
                )
                return

            self.turns_used = turn

            # Call LLM (non-streaming -- subagents run headlessly)
            try:
                response = self.llm.chat(
                    self.context.get_messages(), stream=False
                )
            except Exception as exc:
                raise RuntimeError(
                    f"LLM call failed on turn {turn}: {exc}"
                ) from exc

            text = response.get("text", "")
            tool_calls = response.get("tool_calls", [])

            # If the LLM produced text, keep it as the latest output
            if text:
                last_text = text

            # No tool calls means the agent is done thinking
            if not tool_calls:
                self.result = text or last_text or "[SubAgent produced no output]"
                return

            # Build assistant message (text + tool_use blocks)
            assistant_content = self._build_assistant_content(text, tool_calls)
            self.context.add_assistant_message(assistant_content)

            # Execute each tool call
            tool_results = self._execute_tool_calls(tool_calls)
            self.context.add_tool_results(tool_results)

            # Trim context if it grows too large
            self.context.trim_if_needed(max_tokens=80_000)

        # Hit max turns -- return whatever we have
        self.result = (
            last_text
            or "[SubAgent reached max turns without a final answer]"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_assistant_content(
        text: str, tool_calls: list[dict]
    ) -> list[dict]:
        content: list[dict] = []
        if text:
            content.append({"type": "text", "text": text})
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["arguments"],
            })
        return content

    def _execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """Execute tool calls and return Anthropic-style tool_result blocks."""
        results: list[dict] = []
        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]
            call_id = tc["id"]

            logger.debug(
                "SubAgent %s executing tool %s(%s)",
                self.agent_id[:8],
                name,
                json.dumps(args, default=str),
            )

            try:
                result = asyncio.run(self.registry.execute(name, **args))
                result_str = json.dumps(result, indent=2, default=str)
            except Exception as exc:
                result_str = json.dumps(
                    {"error": f"Tool '{name}' failed: {exc}"},
                    default=str,
                )

            # Truncate very large tool results to conserve context
            max_result_len = 30_000
            if len(result_str) > max_result_len:
                result_str = (
                    result_str[:max_result_len]
                    + "\n... [truncated, result too large]"
                )

            results.append({
                "type": "tool_result",
                "tool_use_id": call_id,
                "content": result_str,
            })

        return results


# ======================================================================
# SubAgentManager
# ======================================================================

class SubAgentManager:
    """Creates, tracks, and manages subagents (foreground and background).

    Thread-safe: all mutations go through a lock so callers on different
    threads can safely query status.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._agents: dict[str, SubAgent] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Creation helpers
    # ------------------------------------------------------------------

    def _make_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def create(
        self,
        task: str,
        agent_type: str | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        allowed_tools: set[str] | None = None,
    ) -> SubAgent:
        """Create a new SubAgent (does not start it yet).

        Parameters
        ----------
        task : str
            What the subagent should do.
        agent_type : str | None
            Built-in type key ("explore" or "plan").
        system_prompt : str | None
            Custom system prompt override.
        max_turns : int | None
            Turn limit override.
        allowed_tools : set[str] | None
            Restrict to these tool names.

        Returns
        -------
        SubAgent
            The newly created (but not yet started) subagent.
        """
        agent_id = self._make_id()
        agent = SubAgent(
            agent_id=agent_id,
            task=task,
            config=self.config,
            agent_type=agent_type,
            system_prompt=system_prompt,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
        )
        with self._lock:
            self._agents[agent_id] = agent
        return agent

    # ------------------------------------------------------------------
    # Foreground execution
    # ------------------------------------------------------------------

    def run_foreground(
        self,
        task: str,
        agent_type: str | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        allowed_tools: set[str] | None = None,
    ) -> str:
        """Create and immediately run a subagent in the calling thread.

        Returns the result text.
        """
        agent = self.create(
            task=task,
            agent_type=agent_type,
            system_prompt=system_prompt,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
        )
        return agent.run()

    # ------------------------------------------------------------------
    # Background execution
    # ------------------------------------------------------------------

    def launch_background(
        self,
        task: str,
        agent_type: str | None = None,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        allowed_tools: set[str] | None = None,
    ) -> str:
        """Create and start a subagent in a background daemon thread.

        Returns the agent_id so the caller can poll / retrieve results.
        """
        agent = self.create(
            task=task,
            agent_type=agent_type,
            system_prompt=system_prompt,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
        )

        thread = threading.Thread(
            target=agent.run,
            name=f"subagent-{agent.agent_id}",
            daemon=True,
        )
        with self._lock:
            self._threads[agent.agent_id] = thread
        thread.start()
        return agent.agent_id

    # ------------------------------------------------------------------
    # Query / control
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> SubAgent | None:
        """Look up a subagent by ID."""
        with self._lock:
            return self._agents.get(agent_id)

    def get_result(self, agent_id: str) -> str | None:
        """Return the result text if the subagent is done, else None."""
        agent = self.get_agent(agent_id)
        if agent is None:
            return None
        if agent.is_done:
            return agent.result
        return None

    def get_status(self, agent_id: str) -> SubAgentStatus | None:
        """Return the current status of a subagent."""
        agent = self.get_agent(agent_id)
        if agent is None:
            return None
        return agent.status

    def is_done(self, agent_id: str) -> bool:
        """Check whether a subagent has finished (completed/failed/cancelled)."""
        agent = self.get_agent(agent_id)
        if agent is None:
            return True  # unknown agent treated as done
        return agent.is_done

    def wait_for(self, agent_id: str, timeout: float | None = None) -> str:
        """Block until the background subagent finishes and return its result.

        Parameters
        ----------
        agent_id : str
            The ID returned by ``launch_background()``.
        timeout : float | None
            Maximum seconds to wait.  ``None`` means wait forever.

        Returns
        -------
        str
            The subagent's result text.

        Raises
        ------
        TimeoutError
            If the timeout expires before the agent finishes.
        KeyError
            If ``agent_id`` is unknown.
        """
        with self._lock:
            thread = self._threads.get(agent_id)
            agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown subagent ID: {agent_id}")
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                raise TimeoutError(
                    f"SubAgent {agent_id} did not finish within "
                    f"{timeout} seconds"
                )
        return agent.result

    def cancel(self, agent_id: str) -> bool:
        """Cancel a running subagent. Returns True if the signal was sent."""
        agent = self.get_agent(agent_id)
        if agent is None:
            return False
        if agent.is_done:
            return False
        agent.cancel()
        return True

    def cancel_all(self) -> int:
        """Cancel every running subagent. Returns count of agents cancelled."""
        count = 0
        with self._lock:
            agents = list(self._agents.values())
        for agent in agents:
            if not agent.is_done:
                agent.cancel()
                count += 1
        return count

    # ------------------------------------------------------------------
    # Listing / reporting
    # ------------------------------------------------------------------

    def list_agents(self) -> list[SubAgent]:
        """Return all tracked subagents (running and finished)."""
        with self._lock:
            return list(self._agents.values())

    def list_running(self) -> list[SubAgent]:
        """Return only the currently running subagents."""
        with self._lock:
            return [
                a for a in self._agents.values()
                if a.status == SubAgentStatus.RUNNING
            ]

    def list_completed(self) -> list[SubAgent]:
        """Return subagents that finished (completed, failed, or cancelled)."""
        with self._lock:
            return [a for a in self._agents.values() if a.is_done]

    def status_report(self) -> str:
        """Return a multi-line status report of all subagents."""
        agents = self.list_agents()
        if not agents:
            return "No subagents have been created."
        lines = [f"SubAgent Status Report ({len(agents)} total):"]
        lines.append("-" * 60)
        for agent in agents:
            lines.append(agent.summary())
            if agent.is_done and agent.result:
                # Show first 200 chars of result as preview
                preview = agent.result[:200].replace("\n", " ")
                if len(agent.result) > 200:
                    preview += "..."
                lines.append(f"  Result preview: {preview}")
        lines.append("-" * 60)
        running = [a for a in agents if a.status == SubAgentStatus.RUNNING]
        done = [a for a in agents if a.is_done]
        lines.append(f"Running: {len(running)}  |  Done: {len(done)}")
        return "\n".join(lines)

    def cleanup_done(self) -> int:
        """Remove all finished subagents from tracking. Returns count removed."""
        with self._lock:
            done_ids = [
                aid for aid, a in self._agents.items() if a.is_done
            ]
            for aid in done_ids:
                del self._agents[aid]
                self._threads.pop(aid, None)
            return len(done_ids)

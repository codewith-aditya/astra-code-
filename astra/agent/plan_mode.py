"""Plan mode controller -- restricts the agent to read-only tools.

When plan mode is active the agent can only use read_file, search_code,
and list_files.  All other tool calls are blocked with an informative
error message.  This lets the LLM explore the codebase and produce a
structured plan before any mutations happen.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from astra.agent.controller import AgentController

# The only tools permitted while plan mode is active.
PLAN_TOOLS = frozenset({"read_file", "search_code", "list_files"})

_PLAN_PROMPT_TEMPLATE = """
You are ASTRA, an elite AI planning agent with deep expertise in software architecture and codebase analysis.

You are currently operating in PLAN MODE.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  STRICT CONSTRAINT: You are FORBIDDEN from making any changes to the codebase.
     Any attempt to write, modify, or delete files will be treated as a critical violation.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## YOUR MISSION
Analyze the user's request with surgical precision and produce an airtight,
step-by-step implementation plan that a senior engineer (or an AI agent) can
execute with zero ambiguity.

Before producing the plan, you MUST explore the repository using the available
read-only tools to understand the relevant parts of the codebase.

## AVAILABLE TOOLS IN PLAN MODE (READ-ONLY)
You may ONLY use the following tools:

  ┌──────────────┬─────────────────────────────────────────────────────┐
  │ Tool         │ Purpose                                             │
  ├──────────────┼─────────────────────────────────────────────────────┤
  │ read_file    │ Read file with line numbers, offset + limit support │
  │ list_files   │ Directory listing with glob filter + depth limit    │
  │ search_code  │ Semantic search across the entire codebase          │
  │ grep_search  │ Regex/literal search — fast, precise, line-level    │
  │ glob_search  │ Find files by pattern (e.g. **/*.test.ts)           │
  │ web_search   │ Search web for docs, prior art, or solutions        │
  │ web_fetch    │ Fetch and read a specific URL                       │
  │ ask_user     │ Clarify ambiguous requirements before planning      │
  └──────────────┴─────────────────────────────────────────────────────┘

  ⛔ write_file, edit_file, multi_edit, run_command are FORBIDDEN in PLAN MODE.

## EXPLORATION ORDER
  1. glob_search  — find relevant files by pattern first
  2. grep_search  — locate exact symbols, strings, or patterns
  3. read_file    — read only what is directly relevant
  4. ask_user     — if intent is still unclear after exploration

## PLANNING STANDARDS
  ✦ Every step must be atomic, actionable, and unambiguous.
  ✦ Reference exact file paths, function names, and line numbers where possible.
  ✦ Identify all files to be CREATED, MODIFIED, or DELETED — nothing left vague.
  ✦ Specify which tool should be used in each execution step.
  ✦ Surface all dependencies, blockers, and integration points upfront.
  ✦ Flag every edge case, failure mode, and risk — no surprises during execution.
  ✦ Note if any step requires subagent, sandbox, or worktree isolation.
  ✦ Assume the executing agent has zero additional context beyond what you provide.

## OUTPUT FORMAT (STRICT — NO DEVIATIONS)

───────────────────────────────────────────────────
 📂 FILES IMPACTED
───────────────────────────────────────────────────
  CREATE  • <file path>
  MODIFY  • <file path>
  DELETE  • <file path>

───────────────────────────────────────────────────
 📋 IMPLEMENTATION PLAN
───────────────────────────────────────────────────
1. [Step Title]
   → Action:  <read | search | edit | multi_edit | create | run | web | ask>
   → Tool:    <exact tool name>
   → Where:   <file path / module / function / line>
   → What:    <what exactly needs to be done>
   → How:     <specific implementation detail>
   → Outcome: <what success looks like>

2. [Step Title]
   → Action:
   → Tool:
   → Where:
   → What:
   → How:
   → Outcome:

───────────────────────────────────────────────────
 ⚠️  RISKS & EDGE CASES
───────────────────────────────────────────────────
  • <Risk 1> — <mitigation strategy>
  • <Risk 2> — <mitigation strategy>

───────────────────────────────────────────────────
 🔗 DEPENDENCIES & BLOCKERS
───────────────────────────────────────────────────
  • <dependency or blocker>

───────────────────────────────────────────────────
 🤖 AGENT STRATEGY  (if applicable)
───────────────────────────────────────────────────
  • Subagents needed:   <yes / no — if yes, describe split>
  • Sandbox required:   <yes / no — if yes, explain why>
  • Worktree isolation: <yes / no — if yes, name the branch>

───────────────────────────────────────────────────
 📌 EXECUTIVE SUMMARY
───────────────────────────────────────────────────
  <A sharp 2–3 sentence summary of the full plan,
   what it achieves, and what to watch out for
   during execution.>

───────────────────────────────────────────────────
⛔ IMPORTANT: Do NOT implement the plan.
             Do NOT execute any write operations.
             Stop immediately after generating the plan.
───────────────────────────────────────────────────

## USER REQUEST
{user_request}

Produce the plan now.
"""
class PlanModeController:
    """Controls plan mode: restricts tools to read-only operations.

    Usage::

        plan_ctl = PlanModeController()
        plan_ctl.enter_plan_mode(agent)
        # ... agent runs in plan mode ...
        plan_ctl.exit_plan_mode(agent)
    """

    def __init__(self) -> None:
        self.is_active: bool = False
        self._stashed_tools: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Activation / deactivation
    # ------------------------------------------------------------------

    def enter_plan_mode(self, agent: AgentController) -> None:
        """Restrict the agent to read-only tools."""
        if self.is_active:
            return

        self._stashed_tools = {
            name: True for name in list(agent.registry._tools.keys())
        }

        to_remove = [
            name for name in agent.registry._tools
            if name not in PLAN_TOOLS
        ]
        for name in to_remove:
            del agent.registry._tools[name]

        self.is_active = True

    def exit_plan_mode(self, agent: AgentController) -> None:
        """Restore all tools that were available before plan mode."""
        if not self.is_active:
            return

        from astra.tools.registry import build_registry
        fresh_registry = build_registry()

        for name, tool in fresh_registry._tools.items():
            if name not in agent.registry._tools:
                agent.registry._tools[name] = tool

        self._stashed_tools = None
        self.is_active = False

    # ------------------------------------------------------------------
    # Guard
    # ------------------------------------------------------------------

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed in the current mode."""
        if not self.is_active:
            return True
        return tool_name in PLAN_TOOLS

    def guard_tool_call(self, tool_name: str) -> str | None:
        """Check whether a tool call is permitted in plan mode.

        Returns None if allowed, or an error message string if blocked.
        """
        if not self.is_active:
            return None

        if tool_name in PLAN_TOOLS:
            return None

        allowed = ", ".join(sorted(PLAN_TOOLS))
        return (
            f"Tool '{tool_name}' is not available in plan mode. "
            f"Only the following tools are allowed: {allowed}. "
            "Exit plan mode to use other tools."
        )

    # ------------------------------------------------------------------
    # Prompt generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_plan_prompt(user_request: str) -> str:
        """Generate a prompt that instructs the LLM to plan."""
        return _PLAN_PROMPT_TEMPLATE.format(user_request=user_request)

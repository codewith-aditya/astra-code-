"""Tool registry — discovers, stores, and dispatches agent tools."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolDefinition:
    """Schema for a single tool exposed to the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]


class ToolRegistry:
    """Central registry of all tools available to the agent."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Retrieve a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """Return all registered tools."""
        return list(self._tools.values())

    async def execute(self, name: str, **kwargs: Any) -> Any:
        """Execute a tool by name with the given arguments."""
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}

        try:
            # Filter kwargs to only include parameters the handler accepts
            sig = inspect.signature(tool.handler)
            valid_params = set(sig.parameters.keys())
            filtered = {k: v for k, v in kwargs.items() if k in valid_params}

            result = tool.handler(**filtered)
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as exc:
            return {"error": f"Tool '{name}' failed: {exc}"}

    def to_schemas(self) -> list[dict[str, Any]]:
        """Export all tools as JSON schemas for the LLM API."""
        schemas = []
        for tool in self._tools.values():
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": [
                        k for k, v in tool.parameters.items()
                        if not v.get("optional", False)
                    ],
                },
            })
        return schemas


def build_registry() -> ToolRegistry:
    """Build the default tool registry with all built-in tools."""
    from astra.tools.read_file import READ_FILE_TOOL
    from astra.tools.write_file import WRITE_FILE_TOOL
    from astra.tools.edit_file import EDIT_FILE_TOOL
    from astra.tools.multi_edit import MULTI_EDIT_TOOL
    from astra.tools.search_code import SEARCH_CODE_TOOL
    from astra.tools.glob_search import GLOB_TOOL
    from astra.tools.grep_search import GREP_TOOL
    from astra.tools.list_files import LIST_FILES_TOOL
    from astra.tools.run_command import RUN_COMMAND_TOOL
    from astra.tools.web_fetch import WEB_FETCH_TOOL
    from astra.tools.web_search import WEB_SEARCH_TOOL
    from astra.tools.ask_user import ASK_USER_TOOL

    registry = ToolRegistry()
    for tool in [
        READ_FILE_TOOL,
        WRITE_FILE_TOOL,
        EDIT_FILE_TOOL,
        MULTI_EDIT_TOOL,
        SEARCH_CODE_TOOL,
        GLOB_TOOL,
        GREP_TOOL,
        LIST_FILES_TOOL,
        RUN_COMMAND_TOOL,
        WEB_FETCH_TOOL,
        WEB_SEARCH_TOOL,
        ASK_USER_TOOL,
    ]:
        registry.register(tool)
    return registry

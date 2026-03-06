"""LLM client with streaming, retry, and cost tracking."""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from astra.config import Config
from astra.llm.prompts import SYSTEM_PROMPT

console = Console()

# Fix Windows stdout encoding for streaming Unicode
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    except Exception:
        pass

# Cost per 1M tokens (approximate)
COST_TABLE = {
    "claude": {"input": 3.0, "output": 15.0},
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4": {"input": 10.0, "output": 30.0},
    "default": {"input": 3.0, "output": 15.0},
}


class TokenTracker:
    """Track token usage and estimated cost across the session."""

    def __init__(self) -> None:
        self.total_input: int = 0
        self.total_output: int = 0
        self.request_count: int = 0
        self.last_input: int = 0
        self.last_output: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.last_input = input_tokens
        self.last_output = output_tokens
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.request_count += 1

    def estimate_cost(self, model: str = "") -> float:
        """Estimate cost in USD."""
        model_lower = model.lower()
        rates = COST_TABLE["default"]
        for key, r in COST_TABLE.items():
            if key in model_lower:
                rates = r
                break

        input_cost = (self.total_input / 1_000_000) * rates["input"]
        output_cost = (self.total_output / 1_000_000) * rates["output"]
        return input_cost + output_cost


class StreamBuffer:
    """Simple stream buffer — prints chunks immediately as they arrive."""

    def __init__(self) -> None:
        self._total: str = ""
        self._first_chunk: bool = True
        self.on_first_chunk: Any = None

    def add(self, chunk: str) -> None:
        if self._first_chunk and chunk.strip():
            self._first_chunk = False
            if self.on_first_chunk:
                self.on_first_chunk()

        self._total += chunk
        self._write(chunk)

    def flush(self) -> str:
        """Return full text (nothing buffered to flush)."""
        return self._total

    @staticmethod
    def _write(text: str) -> None:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (UnicodeEncodeError, OSError):
            safe = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            sys.stdout.write(safe)
            sys.stdout.flush()


class LLMClient:
    """Wrapper around Anthropic / OpenAI APIs with streaming, retry, cost tracking."""

    def __init__(self, config: Config, tool_schemas: list[dict], system_prompt: str = "") -> None:
        self.config = config
        self.tool_schemas = tool_schemas
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self._client: Any = None
        self.token_tracker = TokenTracker()

        if config.llm_provider == "anthropic":
            import anthropic
            client_kwargs: dict[str, Any] = {"api_key": config.anthropic_api_key}
            if config.anthropic_base_url:
                client_kwargs["base_url"] = config.anthropic_base_url
            self._client = anthropic.Anthropic(**client_kwargs)
        elif config.llm_provider == "openai":
            import openai
            self._client = openai.OpenAI(api_key=config.openai_api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {config.llm_provider}")

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------
    def _retry(self, fn, max_retries: int = 3, base_delay: float = 1.0) -> Any:
        """Call fn() with exponential backoff retry on failure."""
        last_error = None
        for attempt in range(max_retries):
            try:
                return fn()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    console.print(
                        f"[yellow]API error (attempt {attempt + 1}/{max_retries}):[/yellow] {exc}"
                    )
                    console.print(f"[dim]Retrying in {delay:.0f}s...[/dim]")
                    time.sleep(delay)
        raise last_error  # type: ignore

    # ------------------------------------------------------------------
    # Anthropic (streaming)
    # ------------------------------------------------------------------
    def _call_anthropic_stream(self, messages: list[dict], on_first_chunk=None) -> dict:
        """Stream response from Anthropic Messages API with word buffering."""
        result: dict = {"text": "", "tool_calls": [], "stop_reason": "", "timing": 0.0}
        start = time.time()

        def _do_stream():
            nonlocal result
            stream_buf = StreamBuffer()
            stream_buf.on_first_chunk = on_first_chunk

            with self._client.messages.stream(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=self.system_prompt,
                tools=self.tool_schemas,
                messages=messages,
            ) as stream:
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                stream_buf.add(event.delta.text)

                # Flush remaining buffered text
                stream_buf.flush()

                # Get the final message
                response = stream.get_final_message()
                result["stop_reason"] = response.stop_reason

                # Track tokens
                if hasattr(response, "usage"):
                    self.token_tracker.add(
                        response.usage.input_tokens,
                        response.usage.output_tokens,
                    )

                # Parse content blocks
                for block in response.content:
                    if block.type == "text":
                        result["text"] += block.text
                    elif block.type == "tool_use":
                        result["tool_calls"].append({
                            "id": block.id,
                            "name": block.name,
                            "arguments": block.input,
                        })

        self._retry(_do_stream)
        result["timing"] = time.time() - start

        if result["text"]:
            sys.stdout.write("\n")
            sys.stdout.flush()

        return result

    def _call_anthropic(self, messages: list[dict]) -> dict:
        """Non-streaming fallback for Anthropic."""
        start = time.time()

        def _do_call():
            return self._client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=self.system_prompt,
                tools=self.tool_schemas,
                messages=messages,
            )

        response = self._retry(_do_call)

        if hasattr(response, "usage"):
            self.token_tracker.add(
                response.usage.input_tokens,
                response.usage.output_tokens,
            )

        result = self._parse_anthropic_response(response)
        result["timing"] = time.time() - start
        return result

    @staticmethod
    def _parse_anthropic_response(response: Any) -> dict:
        result: dict = {
            "text": "",
            "tool_calls": [],
            "stop_reason": response.stop_reason,
            "timing": 0.0,
        }
        for block in response.content:
            if block.type == "text":
                result["text"] += block.text
            elif block.type == "tool_use":
                result["tool_calls"].append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })
        return result

    # ------------------------------------------------------------------
    # OpenAI (streaming)
    # ------------------------------------------------------------------
    def _call_openai_stream(self, messages: list[dict], on_first_chunk=None) -> dict:
        """Stream response from OpenAI Chat API with word buffering."""
        oai_tools = []
        for t in self.tool_schemas:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            })

        oai_messages = [{"role": "system", "content": self.system_prompt}]
        for m in messages:
            oai_messages.append(self._convert_message_to_openai(m))

        result: dict = {"text": "", "tool_calls": [], "stop_reason": "", "timing": 0.0}
        tool_call_chunks: dict[int, dict] = {}
        start = time.time()

        def _do_stream():
            nonlocal result
            stream_buf = StreamBuffer()
            stream_buf.on_first_chunk = on_first_chunk

            stream = self._client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                tools=oai_tools or None,
                messages=oai_messages,
                stream=True,
                stream_options={"include_usage": True},
            )

            for chunk in stream:
                if not chunk.choices:
                    # Usage chunk at end
                    if hasattr(chunk, "usage") and chunk.usage:
                        self.token_tracker.add(
                            chunk.usage.prompt_tokens,
                            chunk.usage.completion_tokens,
                        )
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    result["text"] += delta.content
                    stream_buf.add(delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc_delta.id:
                            tool_call_chunks[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_chunks[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_chunks[idx]["arguments"] += tc_delta.function.arguments

                if chunk.choices[0].finish_reason:
                    result["stop_reason"] = chunk.choices[0].finish_reason

            # Flush remaining
            stream_buf.flush()

        self._retry(_do_stream)
        result["timing"] = time.time() - start

        # Assemble tool calls
        for idx in sorted(tool_call_chunks.keys()):
            tc = tool_call_chunks[idx]
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            result["tool_calls"].append({
                "id": tc["id"],
                "name": tc["name"],
                "arguments": args,
            })

        if result["text"]:
            sys.stdout.write("\n")
            sys.stdout.flush()

        return result

    @staticmethod
    def _convert_message_to_openai(msg: dict) -> dict:
        role = msg["role"]
        content = msg.get("content", "")

        if isinstance(content, str):
            return {"role": role, "content": content}

        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": json.dumps(block["content"]) if not isinstance(block["content"], str) else block["content"],
                    }
            parts = [str(b) for b in content]
            return {"role": role, "content": "\n".join(parts)}

        return {"role": role, "content": str(content)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def chat(self, messages: list[dict], stream: bool = True, on_first_chunk=None) -> dict:
        """Send messages and return a standardized response dict.

        Returns:
            {"text": str, "tool_calls": [...], "stop_reason": str, "timing": float}
        """
        if self.config.llm_provider == "anthropic":
            if stream:
                return self._call_anthropic_stream(messages, on_first_chunk=on_first_chunk)
            return self._call_anthropic(messages)
        else:
            if stream:
                return self._call_openai_stream(messages, on_first_chunk=on_first_chunk)
            # Non-streaming OpenAI fallback
            return self._call_openai_no_stream(messages)

    def _call_openai_no_stream(self, messages: list[dict]) -> dict:
        """Non-streaming OpenAI fallback."""
        oai_tools = []
        for t in self.tool_schemas:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            })

        oai_messages = [{"role": "system", "content": self.system_prompt}]
        for m in messages:
            oai_messages.append(self._convert_message_to_openai(m))

        start = time.time()

        def _do_call():
            return self._client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                tools=oai_tools or None,
                messages=oai_messages,
            )

        response = self._retry(_do_call)

        if hasattr(response, "usage") and response.usage:
            self.token_tracker.add(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )

        choice = response.choices[0]
        msg = choice.message
        result: dict = {
            "text": msg.content or "",
            "tool_calls": [],
            "stop_reason": choice.finish_reason,
            "timing": time.time() - start,
        }
        if msg.tool_calls:
            for tc in msg.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })
        return result

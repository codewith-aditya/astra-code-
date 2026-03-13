"""MCP (Model Context Protocol) server manager.

Manages connections to MCP servers via stdio or HTTP transports,
discovers tools, and dispatches tool calls using JSON-RPC 2.0.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError


@dataclass
class MCPServer:
    """Configuration for a single MCP server."""

    name: str
    transport: str  # "stdio", "http", or "sse"
    command: str = ""  # For stdio: executable to run
    url: str = ""  # For http/sse: server URL
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        data: dict[str, Any] = {
            "name": self.name,
            "transport": self.transport,
        }
        if self.transport == "stdio":
            data["command"] = self.command
            if self.args:
                data["args"] = self.args
            if self.env:
                data["env"] = self.env
        else:
            data["url"] = self.url
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServer:
        """Deserialize from a JSON-compatible dict."""
        return cls(
            name=data["name"],
            transport=data.get("transport", "stdio"),
            command=data.get("command", ""),
            url=data.get("url", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
        )


def _make_jsonrpc_request(method: str, params: dict[str, Any] | None = None) -> dict:
    """Build a JSON-RPC 2.0 request envelope."""
    req: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
    }
    if params is not None:
        req["params"] = params
    return req


def _parse_jsonrpc_response(raw: str) -> dict[str, Any]:
    """Parse a JSON-RPC 2.0 response, raising on errors."""
    data = json.loads(raw)
    if "error" in data:
        err = data["error"]
        code = err.get("code", -1)
        message = err.get("message", "Unknown JSON-RPC error")
        raise RuntimeError(f"JSON-RPC error {code}: {message}")
    return data.get("result", {})


class MCPManager:
    """Manages MCP server configurations, tool discovery, and invocation."""

    def __init__(self, project_root: str = ".") -> None:
        self.project_root = Path(project_root).resolve()
        self._servers: dict[str, MCPServer] = {}

    # ------------------------------------------------------------------
    # Configuration loading / saving
    # ------------------------------------------------------------------

    def load_servers(self) -> None:
        """Load server configs from .mcp.json and .astra/mcp.json."""
        self._servers.clear()

        # Primary config: project_root/.mcp.json
        project_config = self.project_root / ".mcp.json"
        self._load_config_file(project_config)

        # Secondary config: project_root/.astra/mcp.json
        astra_config = self.project_root / ".astra" / "mcp.json"
        self._load_config_file(astra_config)

    def _load_config_file(self, path: Path) -> None:
        """Load servers from a single config file."""
        if not path.exists():
            return
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: failed to read {path}: {exc}", file=sys.stderr)
            return

        servers_list = data.get("servers", [])
        # Also support dict-style keyed by name
        if isinstance(servers_list, dict):
            for name, cfg in servers_list.items():
                cfg.setdefault("name", name)
                server = MCPServer.from_dict(cfg)
                self._servers[server.name] = server
        elif isinstance(servers_list, list):
            for cfg in servers_list:
                server = MCPServer.from_dict(cfg)
                self._servers[server.name] = server

    def save_config(self, path: str | None = None) -> None:
        """Save current server configs to .mcp.json in the project root."""
        target = Path(path) if path else (self.project_root / ".mcp.json")
        data = {
            "servers": [s.to_dict() for s in self._servers.values()],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(data, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Server management
    # ------------------------------------------------------------------

    def add_server(
        self,
        name: str,
        transport: str,
        command_or_url: str,
        args: list[str] | None = None,
    ) -> MCPServer:
        """Add a new MCP server configuration."""
        if transport not in ("stdio", "http", "sse"):
            raise ValueError(f"Unsupported transport: {transport!r}")

        server = MCPServer(
            name=name,
            transport=transport,
            command=command_or_url if transport == "stdio" else "",
            url=command_or_url if transport in ("http", "sse") else "",
            args=args or [],
        )
        self._servers[name] = server
        return server

    def remove_server(self, name: str) -> bool:
        """Remove a server by name. Returns True if it existed."""
        return self._servers.pop(name, None) is not None

    def list_servers(self) -> list[MCPServer]:
        """Return all configured servers."""
        return list(self._servers.values())

    def get_server(self, name: str) -> MCPServer | None:
        """Get a server by name."""
        return self._servers.get(name)

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def get_tools(self, server_name: str) -> list[dict[str, Any]]:
        """Fetch available tool schemas from a server.

        For stdio: launches the process, sends an initialize request,
        then a tools/list request via JSON-RPC 2.0.

        For http/sse: sends a POST to <url>/tools/list.
        """
        server = self._servers.get(server_name)
        if server is None:
            raise KeyError(f"Unknown MCP server: {server_name!r}")

        if server.transport == "stdio":
            return self._get_tools_stdio(server)
        else:
            return self._get_tools_http(server)

    def _get_tools_stdio(self, server: MCPServer) -> list[dict[str, Any]]:
        """Discover tools via stdio JSON-RPC."""
        cmd = [server.command] + server.args
        env = None
        if server.env:
            import os
            env = {**os.environ, **server.env}

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        try:
            # Step 1: Send initialize
            init_req = _make_jsonrpc_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "astra", "version": "0.1.0"},
            })
            self._stdio_send(proc, init_req)
            self._stdio_recv(proc)

            # Step 2: Send initialized notification (no id)
            notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            self._stdio_send(proc, notif)

            # Step 3: Request tools/list
            list_req = _make_jsonrpc_request("tools/list", {})
            self._stdio_send(proc, list_req)
            result = self._stdio_recv(proc)

            return result.get("tools", [])
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _get_tools_http(self, server: MCPServer) -> list[dict[str, Any]]:
        """Discover tools via HTTP POST."""
        url = server.url.rstrip("/") + "/tools/list"
        payload = _make_jsonrpc_request("tools/list", {})

        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                result = _parse_jsonrpc_response(body)
                return result.get("tools", [])
        except URLError as exc:
            raise ConnectionError(f"Failed to connect to {url}: {exc}") from exc

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Invoke a tool on the specified server and return the result."""
        server = self._servers.get(server_name)
        if server is None:
            raise KeyError(f"Unknown MCP server: {server_name!r}")

        if server.transport == "stdio":
            return self._call_tool_stdio(server, tool_name, arguments or {})
        else:
            return self._call_tool_http(server, tool_name, arguments or {})

    def _call_tool_stdio(
        self,
        server: MCPServer,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call a tool via stdio JSON-RPC."""
        cmd = [server.command] + server.args
        env = None
        if server.env:
            import os
            env = {**os.environ, **server.env}

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        try:
            # Initialize handshake
            init_req = _make_jsonrpc_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "astra", "version": "0.1.0"},
            })
            self._stdio_send(proc, init_req)
            self._stdio_recv(proc)

            notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            self._stdio_send(proc, notif)

            # Call the tool
            call_req = _make_jsonrpc_request("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })
            self._stdio_send(proc, call_req)
            result = self._stdio_recv(proc)

            return result
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _call_tool_http(
        self,
        server: MCPServer,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call a tool via HTTP POST."""
        url = server.url.rstrip("/") + "/tools/call"
        payload = _make_jsonrpc_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
                return _parse_jsonrpc_response(body)
        except URLError as exc:
            raise ConnectionError(
                f"Failed to call tool {tool_name!r} on {server.name}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # stdio I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _stdio_send(proc: subprocess.Popen, message: dict) -> None:
        """Send a JSON-RPC message over stdin."""
        assert proc.stdin is not None
        raw = json.dumps(message, ensure_ascii=True)
        line = raw + "\n"
        proc.stdin.write(line.encode("utf-8"))
        proc.stdin.flush()

    @staticmethod
    def _stdio_recv(proc: subprocess.Popen) -> dict[str, Any]:
        """Read a single JSON-RPC response from stdout."""
        assert proc.stdout is not None
        line = proc.stdout.readline()
        if not line:
            stderr_output = ""
            if proc.stderr:
                stderr_output = proc.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"MCP server closed stdout unexpectedly. stderr: {stderr_output}"
            )
        return _parse_jsonrpc_response(line.decode("utf-8"))

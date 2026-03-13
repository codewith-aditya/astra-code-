"""Configuration management for Astra agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Central configuration for the Astra agent."""

    # LLM settings
    llm_provider: str = "anthropic"  # "anthropic" or "openai"
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""  # Custom base URL for proxy providers
    openai_api_key: str = ""
    model: str = "gemini-claude-sonnet-4-6-thinking"
    max_tokens: int = 8192
    temperature: float = 0.0

    # Agent settings
    max_iterations: int = 30
    auto_approve_tools: bool = False

    # Repository settings
    repo_path: str = "."
    ignore_patterns: list[str] = field(default_factory=lambda: [
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".env", "*.pyc", ".DS_Store", "dist", "build", ".egg-info",
    ])

    # Safety settings
    allow_terminal_commands: bool = True
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "mkfs", "dd if=", ":(){", "shutdown", "reboot",
    ])

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        return cls(
            llm_provider=os.getenv("ASTRA_LLM_PROVIDER", "anthropic"),
            anthropic_api_key=os.getenv("ANTHROPIC_AUTH_TOKEN", os.getenv("ANTHROPIC_API_KEY", "")),
            anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("ANTHROPIC_MODEL", os.getenv("ASTRA_MODEL", "gemini-claude-sonnet-4-6-thinking")),
            max_tokens=int(os.getenv("ASTRA_MAX_TOKENS", "8192")),
            temperature=float(os.getenv("ASTRA_TEMPERATURE", "0.0")),
            max_iterations=int(os.getenv("ASTRA_MAX_ITERATIONS", "30")),
            auto_approve_tools=os.getenv("ASTRA_AUTO_APPROVE", "false").lower() == "true",
            repo_path=os.getenv("ASTRA_REPO_PATH", "."),
            allow_terminal_commands=os.getenv("ASTRA_ALLOW_TERMINAL", "true").lower() == "true",
        )

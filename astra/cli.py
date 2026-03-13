"""CLI entry point for the Astra coding agent."""

from __future__ import annotations

import sys

import click
from rich.console import Console

from astra import __version__
from astra.config import Config

console = Console()


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("request", nargs=-1)
@click.option(
    "--provider",
    type=click.Choice(["anthropic", "openai"]),
    default=None,
    help="LLM provider to use.",
)
@click.option("--model", "-m", default=None, help="Model name to use.")
@click.option(
    "--repo", "-r",
    default=".",
    help="Path to the repository root.",
)
@click.option(
    "--auto-approve", "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompts for tool calls.",
)
@click.option(
    "--interactive", "-i",
    is_flag=True,
    default=False,
    help="Start an interactive REPL session.",
)
@click.option(
    "--pipe", "-p",
    is_flag=True,
    default=False,
    help="Headless pipe mode: read prompt from stdin, output result, exit.",
)
@click.option(
    "--output-format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format for headless mode.",
)
@click.option(
    "--max-turns",
    type=int,
    default=None,
    help="Maximum agent iterations (overrides config).",
)
@click.version_option(version=__version__, prog_name="astra")
def main(
    request: tuple[str, ...],
    provider: str | None,
    model: str | None,
    repo: str,
    auto_approve: bool,
    interactive: bool,
    pipe: bool,
    output_format: str,
    max_turns: int | None,
) -> None:
    """Astra -- AI-powered coding agent.

    \b
    Examples:
      astra "fix the authentication bug"
      astra "add input validation to user signup"
      astra --interactive
      astra -p openai -m gpt-4o "refactor the database module"
      echo "explain this codebase" | astra --pipe
      astra --pipe --output-format json "list all TODO comments"
    """
    config = Config.from_env()

    # CLI overrides
    if provider:
        config.llm_provider = provider
    if model:
        config.model = model
    config.repo_path = repo
    config.auto_approve_tools = auto_approve
    if max_turns is not None:
        config.max_iterations = max_turns

    # Validate API key
    if config.llm_provider == "anthropic" and not config.anthropic_api_key:
        console.print(
            "[bold red]Error:[/bold red] ANTHROPIC_AUTH_TOKEN (or ANTHROPIC_API_KEY) is not set.\n"
            "Set it in your environment or in a .env file."
        )
        raise SystemExit(1)
    if config.llm_provider == "openai" and not config.openai_api_key:
        console.print(
            "[bold red]Error:[/bold red] OPENAI_API_KEY is not set.\n"
            "Set it in your environment or in a .env file."
        )
        raise SystemExit(1)

    from astra.agent.controller import AgentController

    agent = AgentController(config)

    # Headless pipe mode
    if pipe:
        _run_pipe_mode(agent, request, output_format)
        return

    if interactive or not request:
        agent.repl()
    else:
        user_request = " ".join(request)
        agent.run(user_request)


def _run_pipe_mode(
    agent: "AgentController",
    request: tuple[str, ...],
    output_format: str,
) -> None:
    """Run in headless pipe mode: process input, output result, exit."""
    # Get prompt: from args or stdin
    if request:
        prompt = " ".join(request)
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    else:
        console.print("[red]Error:[/red] No prompt provided. Use args or pipe stdin.")
        raise SystemExit(1)

    if not prompt:
        console.print("[red]Error:[/red] Empty prompt.")
        raise SystemExit(1)

    # Auto-approve in pipe mode
    agent.config.auto_approve_tools = True

    # Run the agent
    agent.run(prompt)

    # Extract last assistant message
    last_text = ""
    for msg in reversed(agent.context.messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                last_text = content
            elif isinstance(content, list):
                texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                last_text = "\n".join(texts)
            break

    if output_format == "json":
        import json
        output = {
            "result": last_text,
            "iterations": agent.iteration,
            "messages": len(agent.context.messages),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if last_text:
            print(last_text)


if __name__ == "__main__":
    main()

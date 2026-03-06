"""Built-in slash command handlers."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from astra.commands.registry import CommandDefinition

if TYPE_CHECKING:
    from astra.agent.controller import AgentController

console = Console()

# -- Tracking state -----------------------------------------------------------
_session_start: float = time.time()


# =============================================================================
#  /help
# =============================================================================
def _handle_help(agent: AgentController, args: str) -> str | None:
    table = Table(title="Astra Commands", border_style="cyan", show_lines=False)
    table.add_column("Command", style="bold cyan", min_width=18)
    table.add_column("Description", style="white")

    for cmd in agent.command_registry.list_commands():
        aliases = ""
        if cmd.aliases:
            aliases = f" ({', '.join('/' + a for a in cmd.aliases)})"
        table.add_row(f"/{cmd.name}{aliases}", cmd.description)

    console.print(table)
    return None


# =============================================================================
#  /init
# =============================================================================
INIT_TEMPLATE = """\
# {project_name} - ASTRA.md

## Project Overview
<!-- Describe your project here so Astra understands the codebase -->

## Tech Stack
<!-- e.g. Python 3.12, FastAPI, PostgreSQL -->

## Architecture
<!-- High-level architecture notes -->

## Conventions
- Follow existing code style
- Write tests for new features
- Keep functions small and focused

## Important Files
<!-- List key entry points and config files -->

## Custom Instructions
<!-- Any extra instructions for the AI agent -->
"""


def _handle_init(agent: AgentController, args: str) -> str | None:
    repo = Path(agent.config.repo_path).resolve()
    astra_md = repo / "ASTRA.md"

    if astra_md.exists():
        console.print("[yellow]ASTRA.md already exists.[/yellow] Use a text editor to modify it.")
        return None

    project_name = repo.name
    content = INIT_TEMPLATE.format(project_name=project_name)
    astra_md.write_text(content, encoding="utf-8")

    console.print(f"[green]Created ASTRA.md[/green] in {repo}")
    console.print("[dim]Edit this file to give Astra context about your project.[/dim]")
    return None


# =============================================================================
#  /model
# =============================================================================
AVAILABLE_MODELS = {
    "sonnet": "gemini-claude-sonnet-4-6-thinking",
    "opus": "gemini-claude-opus-4-6-thinking",
    "haiku": "gemini-claude-sonnet-4-6",
    "gpt4o": "gpt-4o",
    "gpt4": "gpt-4-turbo",
}


def _handle_model(agent: AgentController, args: str) -> str | None:
    args = args.strip()

    if not args:
        console.print(f"[bold]Current model:[/bold] {agent.config.model}")
        console.print()
        table = Table(title="Available Models", border_style="cyan")
        table.add_column("Shortcut", style="bold cyan")
        table.add_column("Model ID", style="white")
        for shortcut, model_id in AVAILABLE_MODELS.items():
            marker = " (active)" if model_id == agent.config.model else ""
            table.add_row(shortcut, f"{model_id}{marker}")
        console.print(table)
        console.print("[dim]Usage: /model <shortcut or full model id>[/dim]")
        return None

    new_model = AVAILABLE_MODELS.get(args.lower(), args)
    old_model = agent.config.model
    agent.config.model = new_model

    from astra.llm.client import LLMClient
    agent.llm = LLMClient(agent.config, agent.registry.to_schemas())

    console.print(f"[green]Model switched:[/green] {old_model} -> [bold]{new_model}[/bold]")
    return None


# =============================================================================
#  /clear
# =============================================================================
def _handle_clear(agent: AgentController, args: str) -> str | None:
    agent.context.messages.clear()
    agent.context._repo_summary = None
    agent.iteration = 0
    console.clear()
    console.print("[green]Conversation cleared.[/green] Starting fresh.")
    return None


# =============================================================================
#  /compact
# =============================================================================
def _handle_compact(agent: AgentController, args: str) -> str | None:
    before = len(agent.context.messages)
    before_tokens = agent.context.token_estimate()

    if before > 6:
        first = agent.context.messages[0]
        recent = agent.context.messages[-4:]
        agent.context.messages = [first] + recent

    after = len(agent.context.messages)
    after_tokens = agent.context.token_estimate()

    console.print(
        f"[green]Compacted:[/green] {before} messages -> {after} messages "
        f"(~{before_tokens:,} -> ~{after_tokens:,} tokens)"
    )
    return None


# =============================================================================
#  /cost
# =============================================================================
def _handle_cost(agent: AgentController, args: str) -> str | None:
    elapsed = time.time() - _session_start
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    tracker = agent.llm.token_tracker

    table = Table(title="Session Stats", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="white")
    table.add_row("Session duration", f"{mins}m {secs}s")
    table.add_row("Messages in context", str(len(agent.context.messages)))
    table.add_row("API requests", str(tracker.request_count))
    table.add_row("Input tokens", f"{tracker.total_input:,}")
    table.add_row("Output tokens", f"{tracker.total_output:,}")
    table.add_row("Total tokens", f"{tracker.total_input + tracker.total_output:,}")
    table.add_row("Est. cost", f"${tracker.estimate_cost(agent.config.model):.4f}")
    table.add_row("Model", agent.config.model)
    console.print(table)
    return None


# =============================================================================
#  /status
# =============================================================================
def _handle_status(agent: AgentController, args: str) -> str | None:
    repo = Path(agent.config.repo_path).resolve()

    table = Table(title="Astra Status", border_style="cyan")
    table.add_column("Setting", style="bold")
    table.add_column("Value", style="white")
    table.add_row("Repository", str(repo))
    table.add_row("Provider", agent.config.llm_provider)
    table.add_row("Model", agent.config.model)
    table.add_row("Max iterations", str(agent.config.max_iterations))
    table.add_row("Auto-approve tools", str(agent.config.auto_approve_tools))
    table.add_row("Context messages", str(len(agent.context.messages)))
    table.add_row("Est. tokens", f"~{agent.context.token_estimate():,}")
    table.add_row("Plugins loaded", str(len(agent.plugins)))

    astra_md = repo / "ASTRA.md"
    table.add_row("ASTRA.md", "Found" if astra_md.exists() else "Not found")

    memory = agent.context.list_memory()
    table.add_row("Memory entries", str(len(memory)))

    console.print(table)
    return None


# =============================================================================
#  /config
# =============================================================================
def _handle_config(agent: AgentController, args: str) -> str | None:
    args = args.strip()

    if not args:
        table = Table(title="Configuration", border_style="cyan")
        table.add_column("Key", style="bold cyan")
        table.add_column("Value", style="white")
        for key, val in vars(agent.config).items():
            if "api_key" in key or "auth_token" in key.lower():
                display = val[:8] + "..." if val else "(not set)"
            else:
                display = str(val)
            table.add_row(key, display)
        console.print(table)
        return None

    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        console.print(f"[bold]{parts[0]}:[/bold] {getattr(agent.config, parts[0], 'unknown')}")
        return None

    key, value = parts
    if not hasattr(agent.config, key):
        console.print(f"[red]Unknown config key:[/red] {key}")
        return None

    current = getattr(agent.config, key)
    if isinstance(current, bool):
        value = value.lower() in ("true", "1", "yes")
    elif isinstance(current, int):
        value = int(value)
    elif isinstance(current, float):
        value = float(value)

    setattr(agent.config, key, value)
    console.print(f"[green]Set[/green] {key} = {value}")
    return None


# =============================================================================
#  /diff
# =============================================================================
def _handle_diff(agent: AgentController, args: str) -> str | None:
    repo = Path(agent.config.repo_path).resolve()

    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True, cwd=repo, timeout=15,
        )
        diff_stat = result.stdout.strip()

        result2 = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True, cwd=repo, timeout=15,
        )
        diff_full = result2.stdout.strip()
    except Exception as exc:
        console.print(f"[red]git diff failed:[/red] {exc}")
        return None

    if not diff_stat:
        console.print("[dim]No uncommitted changes.[/dim]")
        return None

    console.print(Panel(diff_stat, title="Changed Files", border_style="yellow"))
    if diff_full:
        if len(diff_full) > 5000:
            diff_full = diff_full[:5000] + "\n... (truncated)"
        console.print(Panel(diff_full, title="Diff", border_style="green"))
    return None


# =============================================================================
#  /undo
# =============================================================================
def _handle_undo(agent: AgentController, args: str) -> str | None:
    backup_dir = Path(".astra_backups")

    if not backup_dir.exists():
        console.print("[dim]No backups found.[/dim]")
        return None

    backups = sorted(backup_dir.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    if not backups:
        console.print("[dim]No backups found.[/dim]")
        return None

    if not args.strip():
        console.print("[bold]Available backups:[/bold]")
        for i, bak in enumerate(backups[:20]):
            console.print(f"  {i + 1}. {bak.name}")
        console.print("[dim]Usage: /undo <number> or /undo <filename>[/dim]")
        return None

    arg = args.strip()

    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(backups):
            backup_file = backups[idx]
        else:
            console.print("[red]Invalid backup number.[/red]")
            return None
    else:
        matches = [b for b in backups if arg in b.name]
        if not matches:
            console.print(f"[red]No backup matching '{arg}'.[/red]")
            return None
        backup_file = matches[0]

    name_parts = backup_file.name.rsplit(".", 3)
    if len(name_parts) >= 3:
        original_name = name_parts[0] + "." + name_parts[1] if len(name_parts) == 4 else name_parts[0]
    else:
        original_name = name_parts[0]

    console.print(f"[yellow]Restore {backup_file.name}?[/yellow] (y/n) ", end="")
    try:
        answer = console.input("").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if answer in ("y", "yes"):
        import shutil
        target = Path(agent.config.repo_path) / original_name
        shutil.copy2(backup_file, target)
        console.print(f"[green]Restored[/green] {backup_file.name} -> {target}")
    else:
        console.print("[dim]Cancelled.[/dim]")

    return None


# =============================================================================
#  /commit
# =============================================================================
def _handle_commit(agent: AgentController, args: str) -> str | None:
    repo = Path(agent.config.repo_path).resolve()
    msg = args.strip() if args.strip() else "Auto-commit by Astra"

    try:
        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, timeout=15)

        # Check if there's anything to commit
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=repo, timeout=15,
        )
        if not status.stdout.strip():
            console.print("[dim]Nothing to commit.[/dim]")
            return None

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", msg],
            capture_output=True, text=True, cwd=repo, timeout=30,
        )

        if result.returncode == 0:
            console.print(f"[green]Committed:[/green] {msg}")
            # Show short log
            log = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                capture_output=True, text=True, cwd=repo, timeout=10,
            )
            if log.stdout.strip():
                console.print(f"[dim]{log.stdout.strip()}[/dim]")
        else:
            console.print(f"[red]Commit failed:[/red] {result.stderr.strip()}")

    except Exception as exc:
        console.print(f"[red]Git error:[/red] {exc}")

    return None


# =============================================================================
#  /pr
# =============================================================================
def _handle_pr(agent: AgentController, args: str) -> str | None:
    repo = Path(agent.config.repo_path).resolve()

    try:
        # Get current branch
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=repo, timeout=10,
        )
        branch_name = branch.stdout.strip()

        if not branch_name:
            console.print("[red]Not on a branch.[/red]")
            return None

        if branch_name in ("main", "master"):
            console.print("[yellow]You're on the main branch. Create a feature branch first.[/yellow]")
            return None

        # Push branch
        console.print(f"[dim]Pushing branch {branch_name}...[/dim]")
        push = subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            capture_output=True, text=True, cwd=repo, timeout=60,
        )

        if push.returncode != 0:
            console.print(f"[red]Push failed:[/red] {push.stderr.strip()}")
            return None

        # Create PR
        title = args.strip() if args.strip() else f"PR from {branch_name}"
        pr = subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", "Created by Astra agent", "--fill"],
            capture_output=True, text=True, cwd=repo, timeout=30,
        )

        if pr.returncode == 0:
            console.print(f"[green]PR created:[/green] {pr.stdout.strip()}")
        else:
            console.print(f"[red]PR creation failed:[/red] {pr.stderr.strip()}")
            console.print("[dim]Make sure 'gh' CLI is installed and authenticated.[/dim]")

    except FileNotFoundError:
        console.print("[red]'gh' CLI not found.[/red] Install it: https://cli.github.com")
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")

    return None


# =============================================================================
#  /save
# =============================================================================
def _handle_save(agent: AgentController, args: str) -> str | None:
    name = args.strip() or "default"
    save_dir = Path(agent.config.repo_path).resolve() / ".astra" / "sessions"
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / f"{name}.json"

    agent.context.save_conversation(str(filepath))
    console.print(f"[green]Conversation saved:[/green] {filepath.name}")
    return None


# =============================================================================
#  /load
# =============================================================================
def _handle_load(agent: AgentController, args: str) -> str | None:
    name = args.strip()
    save_dir = Path(agent.config.repo_path).resolve() / ".astra" / "sessions"

    if not name:
        # List available sessions
        if not save_dir.exists():
            console.print("[dim]No saved sessions.[/dim]")
            return None
        sessions = list(save_dir.glob("*.json"))
        if not sessions:
            console.print("[dim]No saved sessions.[/dim]")
            return None
        console.print("[bold]Saved sessions:[/bold]")
        for s in sorted(sessions):
            console.print(f"  - {s.stem}")
        console.print("[dim]Usage: /load <session_name>[/dim]")
        return None

    filepath = save_dir / f"{name}.json"
    if agent.context.load_conversation(str(filepath)):
        console.print(f"[green]Loaded session:[/green] {name} ({len(agent.context.messages)} messages)")
    else:
        console.print(f"[red]Session not found:[/red] {name}")

    return None


# =============================================================================
#  /remember
# =============================================================================
def _handle_remember(agent: AgentController, args: str) -> str | None:
    entry = args.strip()
    if not entry:
        # List memories
        memories = agent.context.list_memory()
        if not memories:
            console.print("[dim]No memories saved.[/dim]")
            console.print("[dim]Usage: /remember <instruction>[/dim]")
            return None
        console.print("[bold]Saved memories:[/bold]")
        for i, m in enumerate(memories, 1):
            console.print(f"  {i}. {m}")
        return None

    agent.context.save_memory_entry(entry)
    console.print(f"[green]Remembered:[/green] {entry}")
    return None


# =============================================================================
#  /forget
# =============================================================================
def _handle_forget(agent: AgentController, args: str) -> str | None:
    keyword = args.strip()
    if not keyword:
        console.print("[dim]Usage: /forget <keyword>[/dim]")
        return None

    removed = agent.context.forget_memory(keyword)
    if removed > 0:
        console.print(f"[green]Forgot {removed} memory entry(s) matching '{keyword}'.[/green]")
    else:
        console.print(f"[dim]No memories matching '{keyword}'.[/dim]")
    return None


# =============================================================================
#  /plugins
# =============================================================================
def _handle_plugins(agent: AgentController, args: str) -> str | None:
    if not agent.plugins:
        console.print("[dim]No plugins loaded.[/dim]")
        plugin_dir = Path(agent.config.repo_path).resolve() / ".astra" / "plugins"
        console.print(f"[dim]Put .py plugin files in: {plugin_dir}[/dim]")
        return None

    table = Table(title="Loaded Plugins", border_style="cyan")
    table.add_column("Name", style="bold cyan")
    table.add_column("Tools", style="white")
    for name, tools in agent.plugins.items():
        table.add_row(name, ", ".join(tools))
    console.print(table)
    return None


# =============================================================================
#  /exit
# =============================================================================
def _handle_exit(agent: AgentController, args: str) -> str | None:
    return "__EXIT__"


# =============================================================================
#  /context
# =============================================================================
def _handle_context(agent: AgentController, args: str) -> str | None:
    from astra.ui import render_context_grid
    render_context_grid(agent.context.messages)
    return None


# =============================================================================
#  /rewind
# =============================================================================
def _handle_rewind(agent: AgentController, args: str) -> str | None:
    checkpoints = agent.checkpoint_mgr.list_checkpoints()

    if not checkpoints:
        console.print("[dim]No checkpoints available.[/dim]")
        return None

    arg = args.strip()
    if not arg:
        console.print("[bold]Available checkpoints:[/bold]")
        for i, cp in enumerate(checkpoints, 1):
            import datetime
            ts = datetime.datetime.fromtimestamp(cp["timestamp"]).strftime("%H:%M:%S")
            console.print(f"  {i}. [{cp['id']}] {cp['label']} ({cp['file_count']} files, {ts})")
        console.print("[dim]Usage: /rewind <number or checkpoint_id>[/dim]")
        return None

    # Find checkpoint
    target_id = None
    if arg.isdigit():
        idx = int(arg) - 1
        if 0 <= idx < len(checkpoints):
            target_id = checkpoints[idx]["id"]
        else:
            console.print("[red]Invalid checkpoint number.[/red]")
            return None
    else:
        target_id = arg

    result = agent.checkpoint_mgr.restore(target_id)
    if result["restored"]:
        console.print(f"[green]Restored {len(result['restored'])} file(s):[/green]")
        for p in result["restored"]:
            console.print(f"  - {p}")
    if result["errors"]:
        for err in result["errors"]:
            console.print(f"[red]Error: {err.get('error', 'unknown')}[/red]")

    return None


# =============================================================================
#  /plan
# =============================================================================
def _handle_plan(agent: AgentController, args: str) -> str | None:
    if agent.plan_mode.is_active:
        agent.plan_mode.exit_plan_mode(agent)
        console.print("[green]Plan mode OFF.[/green] All tools are now available.")
    else:
        agent.plan_mode.enter_plan_mode(agent)
        console.print("[yellow]Plan mode ON.[/yellow] Only read-only tools are available.")
        console.print("[dim]The agent will explore and plan without making changes.[/dim]")
    return None


# =============================================================================
#  /sandbox
# =============================================================================
def _handle_sandbox(agent: AgentController, args: str) -> str | None:
    new_state = agent.sandbox.toggle()
    if new_state:
        console.print("[yellow]Sandbox mode ON.[/yellow] File writes are restricted.")
    else:
        console.print("[green]Sandbox mode OFF.[/green] All writes are allowed.")
    return None


# =============================================================================
#  /doctor
# =============================================================================
def _handle_doctor(agent: AgentController, args: str) -> str | None:
    from astra.ui import run_doctor
    run_doctor(agent.config.repo_path)
    return None


# =============================================================================
#  /export
# =============================================================================
def _handle_export(agent: AgentController, args: str) -> str | None:
    from astra.ui import export_conversation

    filepath = args.strip() or None
    text = export_conversation(agent.context.messages, filepath)

    if filepath:
        console.print(f"[green]Exported conversation to:[/green] {filepath}")
    else:
        # Print to console
        if len(text) > 3000:
            text = text[:3000] + "\n... (truncated, use /export <file> to save full)"
        console.print(text)
    return None


# =============================================================================
#  /worktree
# =============================================================================
def _handle_worktree(agent: AgentController, args: str) -> str | None:
    from astra.worktree import WorktreeManager
    wt_mgr = WorktreeManager(agent.config.repo_path)
    arg = args.strip()

    if not arg or arg == "list":
        worktrees = wt_mgr.list_worktrees()
        if not worktrees:
            console.print("[dim]No astra worktrees.[/dim]")
            console.print("[dim]Usage: /worktree create [name] | /worktree remove <name>[/dim]")
            return None
        table = Table(title="Astra Worktrees", border_style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Branch", style="cyan")
        table.add_column("Path", style="dim")
        for wt in worktrees:
            table.add_row(wt.name, wt.branch, wt.path)
        console.print(table)
        return None

    parts = arg.split(maxsplit=1)
    subcmd = parts[0].lower()

    if subcmd == "create":
        name = parts[1] if len(parts) > 1 else None
        wt = wt_mgr.create(name)
        console.print(f"[green]Created worktree:[/green] {wt.name}")
        console.print(f"  Branch: {wt.branch}")
        console.print(f"  Path: {wt.path}")
    elif subcmd == "remove":
        if len(parts) < 2:
            console.print("[red]Usage: /worktree remove <name>[/red]")
            return None
        ok = wt_mgr.remove(parts[1])
        if ok:
            console.print(f"[green]Removed worktree:[/green] {parts[1]}")
        else:
            console.print(f"[red]Failed to remove worktree:[/red] {parts[1]}")
    else:
        console.print("[dim]Usage: /worktree [list|create [name]|remove <name>][/dim]")

    return None


# =============================================================================
#  /permissions
# =============================================================================
def _handle_permissions(agent: AgentController, args: str) -> str | None:
    arg = args.strip()

    if not arg:
        mode = agent.permission_mgr.current_mode.value
        console.print(f"[bold]Permission mode:[/bold] {mode}")
        if agent.permission_mgr.rules:
            table = Table(title="Permission Rules", border_style="cyan")
            table.add_column("#", style="dim")
            table.add_column("Pattern", style="bold")
            table.add_column("Action", style="white")
            for i, rule in enumerate(agent.permission_mgr.rules):
                table.add_row(str(i), rule.tool, rule.action)
            console.print(table)
        else:
            console.print("[dim]No custom rules defined.[/dim]")
        console.print("[dim]Usage: /permissions mode | /permissions add <pattern> <action> | /permissions remove <index>[/dim]")
        return None

    parts = arg.split(maxsplit=2)
    subcmd = parts[0].lower()

    if subcmd == "mode":
        new_mode = agent.permission_mgr.cycle_mode()
        console.print(f"[green]Permission mode:[/green] {new_mode.value}")
    elif subcmd == "add" and len(parts) >= 3:
        pattern = parts[1]
        action = parts[2].lower()
        try:
            agent.permission_mgr.add_rule(pattern, action)
            console.print(f"[green]Added rule:[/green] {pattern} -> {action}")
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
    elif subcmd == "remove" and len(parts) >= 2:
        try:
            idx = int(parts[1])
            if agent.permission_mgr.remove_rule(idx):
                console.print(f"[green]Removed rule #{idx}[/green]")
            else:
                console.print("[red]Invalid rule index.[/red]")
        except ValueError:
            console.print("[red]Usage: /permissions remove <index>[/red]")
    elif subcmd == "save":
        agent.permission_mgr.save_rules()
        console.print("[green]Permissions saved.[/green]")
    else:
        console.print("[dim]Usage: /permissions [mode|add <pattern> <action>|remove <index>|save][/dim]")

    return None


# =============================================================================
#  /agents
# =============================================================================
def _handle_agents(agent: AgentController, args: str) -> str | None:
    if not hasattr(agent, '_subagent_mgr') or agent._subagent_mgr is None:
        console.print("[dim]No subagent manager initialized.[/dim]")
        return None

    report = agent._subagent_mgr.status_report()
    console.print(Panel(report, title="SubAgents", border_style="cyan"))
    return None


# =============================================================================
#  /resume
# =============================================================================
def _handle_resume(agent: AgentController, args: str) -> str | None:
    name = args.strip()
    if not name:
        # List sessions
        sessions = agent.session_mgr.list_sessions()
        if not sessions:
            console.print("[dim]No saved sessions to resume.[/dim]")
            return None
        table = Table(title="Sessions", border_style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Messages", style="white")
        table.add_column("Last Active", style="dim")
        for s in sessions[:15]:
            import datetime
            ts = datetime.datetime.fromtimestamp(s.last_active).strftime("%Y-%m-%d %H:%M")
            table.add_row(s.name, str(s.message_count), ts)
        console.print(table)
        console.print("[dim]Usage: /resume <session_name>[/dim]")
        return None

    try:
        info, messages = agent.session_mgr.load_session(name)
        agent.context.messages = messages
        console.print(f"[green]Resumed session:[/green] {info.name} ({info.message_count} messages)")
    except FileNotFoundError:
        console.print(f"[red]Session not found:[/red] {name}")

    return None


# =============================================================================
#  /fork
# =============================================================================
def _handle_fork(agent: AgentController, args: str) -> str | None:
    new_name = args.strip()
    if not new_name:
        console.print("[dim]Usage: /fork <new_session_name>[/dim]")
        return None

    # Save current conversation as a new session
    from astra.session.manager import SessionInfo
    new_session = agent.session_mgr.create_session(new_name)
    agent.session_mgr.save_session(new_session, agent.context.messages)
    console.print(f"[green]Forked session:[/green] {new_name} ({len(agent.context.messages)} messages)")
    return None


# =============================================================================
#  /rename
# =============================================================================
def _handle_rename(agent: AgentController, args: str) -> str | None:
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        console.print("[dim]Usage: /rename <old_name> <new_name>[/dim]")
        return None

    old_name, new_name = parts
    try:
        agent.session_mgr.rename_session(old_name, new_name)
        console.print(f"[green]Renamed:[/green] {old_name} -> {new_name}")
    except FileNotFoundError:
        console.print(f"[red]Session not found:[/red] {old_name}")

    return None


# =============================================================================
#  /mcp
# =============================================================================
def _handle_mcp(agent: AgentController, args: str) -> str | None:
    if not hasattr(agent, 'mcp_mgr'):
        from astra.mcp.manager import MCPManager
        agent.mcp_mgr = MCPManager(agent.config.repo_path)

    arg = args.strip()

    if not arg or arg == "list":
        agent.mcp_mgr.load_servers()
        servers = agent.mcp_mgr.list_servers()
        if not servers:
            console.print("[dim]No MCP servers configured.[/dim]")
            console.print("[dim]Usage: /mcp add <name> <transport> <command_or_url>[/dim]")
            return None
        table = Table(title="MCP Servers", border_style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Transport", style="cyan")
        table.add_column("Endpoint", style="white")
        for s in servers:
            endpoint = s.command if s.transport == "stdio" else s.url
            table.add_row(s.name, s.transport, endpoint)
        console.print(table)
        return None

    parts = arg.split(maxsplit=3)
    subcmd = parts[0].lower()

    if subcmd == "add" and len(parts) >= 4:
        _, name, transport, cmd_or_url = parts
        try:
            agent.mcp_mgr.add_server(name, transport, cmd_or_url)
            agent.mcp_mgr.save_config()
            console.print(f"[green]Added MCP server:[/green] {name} ({transport})")
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
    elif subcmd == "remove" and len(parts) >= 2:
        name = parts[1]
        if agent.mcp_mgr.remove_server(name):
            agent.mcp_mgr.save_config()
            console.print(f"[green]Removed MCP server:[/green] {name}")
        else:
            console.print(f"[red]Server not found:[/red] {name}")
    elif subcmd == "tools" and len(parts) >= 2:
        name = parts[1]
        try:
            tools = agent.mcp_mgr.get_tools(name)
            if tools:
                console.print(f"[bold]Tools from {name}:[/bold]")
                for t in tools:
                    desc = t.get("description", "")[:60]
                    console.print(f"  - {t.get('name', '?')}: {desc}")
            else:
                console.print("[dim]No tools found.[/dim]")
        except Exception as exc:
            console.print(f"[red]Error fetching tools:[/red] {exc}")
    else:
        console.print("[dim]Usage: /mcp [list|add <name> <transport> <endpoint>|remove <name>|tools <name>][/dim]")

    return None


# =============================================================================
#  /rules
# =============================================================================
def _handle_rules(agent: AgentController, args: str) -> str | None:
    from astra.rules import RulesManager
    rules_mgr = RulesManager()
    rules = rules_mgr.load_rules(agent.config.repo_path)

    if not rules:
        console.print("[dim]No rules found.[/dim]")
        rules_dir = Path(agent.config.repo_path).resolve() / ".astra" / "rules"
        console.print(f"[dim]Put .md rule files in: {rules_dir}[/dim]")
        return None

    table = Table(title="Loaded Rules", border_style="cyan")
    table.add_column("Source", style="bold")
    table.add_column("Paths", style="cyan")
    table.add_column("Content Preview", style="dim")
    for rule in rules:
        source = Path(rule.source_file).name
        paths = ", ".join(rule.paths) if rule.paths else "(global)"
        preview = rule.content[:80].replace("\n", " ")
        table.add_row(source, paths, preview)
    console.print(table)
    return None


# =============================================================================
#  /hooks
# =============================================================================
def _handle_hooks(agent: AgentController, args: str) -> str | None:
    arg = args.strip()

    if arg == "init":
        from astra.hooks import HookManager
        path = HookManager.generate_default_config(agent.config.repo_path)
        console.print(f"[green]Created hooks config:[/green] {path}")
        return None

    hooks = agent.hook_mgr.hooks
    if not hooks:
        console.print("[dim]No hooks configured.[/dim]")
        console.print("[dim]Usage: /hooks init -- create a default hooks.json template[/dim]")
        return None

    table = Table(title="Registered Hooks", border_style="cyan")
    table.add_column("Event", style="bold")
    table.add_column("Command", style="white")
    table.add_column("Matcher", style="cyan")
    table.add_column("Timeout", style="dim")
    for hook in hooks:
        table.add_row(
            hook.event.value,
            hook.command[:40],
            hook.matcher or "(all)",
            f"{hook.timeout}s",
        )
    console.print(table)
    return None


# =============================================================================
#  /stats (historical telemetry)
# =============================================================================
def _handle_stats(agent: AgentController, args: str) -> str | None:
    summary = agent.telemetry.stats_summary()

    if summary.get("sessions", 0) == 0:
        console.print("[dim]No telemetry data yet.[/dim]")
        return None

    table = Table(title="Historical Stats", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="white")
    for key, val in summary.items():
        table.add_row(key.replace("_", " ").title(), str(val))
    console.print(table)
    return None


# =============================================================================
#  Command list
# =============================================================================
ALL_COMMANDS: list[CommandDefinition] = [
    CommandDefinition(
        name="help",
        description="Show all available commands",
        usage="/help",
        handler=_handle_help,
        aliases=["h", "?"],
    ),
    CommandDefinition(
        name="init",
        description="Create ASTRA.md project config file",
        usage="/init",
        handler=_handle_init,
    ),
    CommandDefinition(
        name="model",
        description="View or switch the active LLM model",
        usage="/model [name]",
        handler=_handle_model,
        aliases=["m"],
    ),
    CommandDefinition(
        name="clear",
        description="Clear conversation history and screen",
        usage="/clear",
        handler=_handle_clear,
    ),
    CommandDefinition(
        name="compact",
        description="Compress conversation to save context window",
        usage="/compact",
        handler=_handle_compact,
    ),
    CommandDefinition(
        name="cost",
        description="Session stats, token usage, and estimated cost",
        usage="/cost",
        handler=_handle_cost,
    ),
    CommandDefinition(
        name="status",
        description="Show project and agent status",
        usage="/status",
        handler=_handle_status,
        aliases=["s"],
    ),
    CommandDefinition(
        name="config",
        description="View or update configuration",
        usage="/config [key] [value]",
        handler=_handle_config,
    ),
    CommandDefinition(
        name="diff",
        description="Show git diff of uncommitted changes",
        usage="/diff",
        handler=_handle_diff,
    ),
    CommandDefinition(
        name="undo",
        description="Restore a file from Astra backups",
        usage="/undo [number|filename]",
        handler=_handle_undo,
    ),
    CommandDefinition(
        name="commit",
        description="Stage all changes and git commit",
        usage="/commit [message]",
        handler=_handle_commit,
    ),
    CommandDefinition(
        name="pr",
        description="Push branch and create a GitHub PR",
        usage="/pr [title]",
        handler=_handle_pr,
    ),
    CommandDefinition(
        name="save",
        description="Save conversation to disk",
        usage="/save [name]",
        handler=_handle_save,
    ),
    CommandDefinition(
        name="load",
        description="Load a saved conversation",
        usage="/load [name]",
        handler=_handle_load,
    ),
    CommandDefinition(
        name="remember",
        description="Save a persistent instruction across sessions",
        usage="/remember <instruction>",
        handler=_handle_remember,
    ),
    CommandDefinition(
        name="forget",
        description="Remove memories matching a keyword",
        usage="/forget <keyword>",
        handler=_handle_forget,
    ),
    CommandDefinition(
        name="plugins",
        description="List loaded plugins",
        usage="/plugins",
        handler=_handle_plugins,
    ),
    CommandDefinition(
        name="exit",
        description="Exit the interactive session",
        usage="/exit",
        handler=_handle_exit,
        aliases=["quit", "q"],
    ),
    CommandDefinition(
        name="context",
        description="Visualize context window usage",
        usage="/context",
        handler=_handle_context,
        aliases=["ctx"],
    ),
    CommandDefinition(
        name="rewind",
        description="Rewind files to a checkpoint",
        usage="/rewind [id]",
        handler=_handle_rewind,
    ),
    CommandDefinition(
        name="plan",
        description="Toggle plan mode (read-only exploration)",
        usage="/plan",
        handler=_handle_plan,
    ),
    CommandDefinition(
        name="sandbox",
        description="Toggle sandbox mode (restrict writes)",
        usage="/sandbox",
        handler=_handle_sandbox,
    ),
    CommandDefinition(
        name="doctor",
        description="Diagnose environment and dependencies",
        usage="/doctor",
        handler=_handle_doctor,
    ),
    CommandDefinition(
        name="export",
        description="Export conversation as text",
        usage="/export [filepath]",
        handler=_handle_export,
    ),
    CommandDefinition(
        name="worktree",
        description="Manage git worktrees for parallel sessions",
        usage="/worktree [list|create|remove]",
        handler=_handle_worktree,
        aliases=["wt"],
    ),
    CommandDefinition(
        name="permissions",
        description="View or change permission mode and rules",
        usage="/permissions [mode|add|remove|save]",
        handler=_handle_permissions,
        aliases=["perm"],
    ),
    CommandDefinition(
        name="agents",
        description="List running and completed subagents",
        usage="/agents",
        handler=_handle_agents,
    ),
    CommandDefinition(
        name="resume",
        description="Resume a previously saved session",
        usage="/resume [name]",
        handler=_handle_resume,
    ),
    CommandDefinition(
        name="fork",
        description="Fork current conversation as a new session",
        usage="/fork <name>",
        handler=_handle_fork,
    ),
    CommandDefinition(
        name="rename",
        description="Rename a saved session",
        usage="/rename <old> <new>",
        handler=_handle_rename,
    ),
    CommandDefinition(
        name="mcp",
        description="Manage MCP (Model Context Protocol) servers",
        usage="/mcp [list|add|remove|tools]",
        handler=_handle_mcp,
    ),
    CommandDefinition(
        name="rules",
        description="Show loaded project rules",
        usage="/rules",
        handler=_handle_rules,
    ),
    CommandDefinition(
        name="hooks",
        description="Show or initialize lifecycle hooks",
        usage="/hooks [init]",
        handler=_handle_hooks,
    ),
    CommandDefinition(
        name="telemetry",
        description="Show historical session statistics",
        usage="/telemetry",
        handler=_handle_stats,
    ),
]

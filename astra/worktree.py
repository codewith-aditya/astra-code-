"""Git worktree support for parallel isolated sessions."""

from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Worktree:
    """A git worktree."""
    name: str
    path: str
    branch: str
    is_active: bool = True


class WorktreeManager:
    """Manage git worktrees for parallel sessions."""

    def __init__(self, repo_path: str = ".") -> None:
        self.repo_path = Path(repo_path).resolve()
        self.worktrees_dir = self.repo_path / ".astra" / "worktrees"

    def create(self, name: str | None = None) -> Worktree:
        """Create a new worktree with its own branch."""
        name = name or f"astra-{uuid.uuid4().hex[:6]}"
        branch = f"astra/{name}"
        wt_path = self.worktrees_dir / name

        wt_path.parent.mkdir(parents=True, exist_ok=True)

        # Create branch and worktree
        subprocess.run(
            ["git", "worktree", "add", "-b", branch, str(wt_path)],
            cwd=self.repo_path, capture_output=True, text=True, timeout=30,
        )

        return Worktree(name=name, path=str(wt_path), branch=branch)

    def remove(self, name: str) -> bool:
        """Remove a worktree."""
        wt_path = self.worktrees_dir / name

        result = subprocess.run(
            ["git", "worktree", "remove", str(wt_path), "--force"],
            cwd=self.repo_path, capture_output=True, text=True, timeout=15,
        )

        # Also delete the branch
        worktrees = self.list_worktrees()
        for wt in worktrees:
            if wt.name == name:
                subprocess.run(
                    ["git", "branch", "-D", wt.branch],
                    cwd=self.repo_path, capture_output=True, timeout=10,
                )
                break

        return result.returncode == 0

    def list_worktrees(self) -> list[Worktree]:
        """List all astra worktrees."""
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=self.repo_path, capture_output=True, text=True, timeout=10,
        )

        worktrees = []
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []

        i = 0
        while i < len(lines):
            if lines[i].startswith("worktree "):
                wt_path = lines[i][9:]
                branch = ""
                if i + 1 < len(lines) and lines[i + 1].startswith("branch "):
                    branch = lines[i + 1][7:]

                # Only show astra worktrees
                p = Path(wt_path)
                if str(self.worktrees_dir) in wt_path:
                    worktrees.append(Worktree(
                        name=p.name,
                        path=wt_path,
                        branch=branch,
                    ))
            i += 1

        return worktrees

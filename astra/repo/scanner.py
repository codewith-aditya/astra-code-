"""Repository scanner — build a map of the project for context."""

from __future__ import annotations

from pathlib import Path

import pathspec

DEFAULT_IGNORE = [
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "*.pyc", ".DS_Store", "dist", "build", ".egg-info",
]

# Extensions considered "code" for summarisation purposes
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".kt", ".scala", ".sh", ".bash", ".zsh", ".yaml", ".yml",
    ".toml", ".json", ".xml", ".html", ".css", ".scss", ".sql",
    ".md", ".txt", ".cfg", ".ini", ".env",
}


class RepoScanner:
    """Scan a repository and produce a structural summary."""

    def __init__(self, root: str | Path, extra_ignore: list[str] | None = None) -> None:
        self.root = Path(root).resolve()
        patterns = DEFAULT_IGNORE + (extra_ignore or [])
        self._ignore = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        self._gitignore = self._load_gitignore()

    def _load_gitignore(self) -> pathspec.PathSpec | None:
        gi = self.root / ".gitignore"
        if gi.exists():
            return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text().splitlines())
        return None

    def _is_ignored(self, rel: str) -> bool:
        if self._ignore.match_file(rel):
            return True
        if self._gitignore and self._gitignore.match_file(rel):
            return True
        return False

    def scan_tree(self, max_depth: int = 4) -> list[str]:
        """Return a tree-style listing of the repository."""
        entries: list[str] = []
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            if self._is_ignored(rel):
                continue
            depth = rel.count("/")
            if depth >= max_depth:
                continue
            indent = "  " * depth
            name = path.name + ("/" if path.is_dir() else "")
            entries.append(f"{indent}{name}")
        return entries

    def get_code_files(self) -> list[Path]:
        """Return all non-ignored code files."""
        files: list[Path] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            if self._is_ignored(rel):
                continue
            if path.suffix.lower() in CODE_EXTENSIONS:
                files.append(path)
        return files

    def summary(self, max_depth: int = 3) -> str:
        """Return a human-readable project summary."""
        tree = self.scan_tree(max_depth=max_depth)
        code_files = self.get_code_files()

        ext_count: dict[str, int] = {}
        for f in code_files:
            ext_count[f.suffix] = ext_count.get(f.suffix, 0) + 1

        lines = [
            f"Repository: {self.root.name}",
            f"Total code files: {len(code_files)}",
            "",
            "File types:",
        ]
        for ext, count in sorted(ext_count.items(), key=lambda x: -x[1]):
            lines.append(f"  {ext}: {count}")

        lines.append("")
        lines.append("Structure:")
        lines.extend(f"  {e}" for e in tree[:80])
        if len(tree) > 80:
            lines.append(f"  ... and {len(tree) - 80} more entries")

        return "\n".join(lines)

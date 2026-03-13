"""Rules system -- load project-level instruction rules from .astra/rules/*.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


@dataclass
class Rule:
    """A single instruction rule loaded from a Markdown file."""

    content: str
    source_file: str
    paths: list[str] = field(default_factory=list)


# Regex to extract YAML-style frontmatter between --- markers.
_FRONTMATTER_RE = re.compile(
    r"\A\s*---\s*\n(.*?)\n\s*---\s*\n",
    re.DOTALL,
)

# Regex to pull the ``paths:`` list items out of the frontmatter block.
_PATHS_ITEM_RE = re.compile(r"^\s*-\s*(.+?)\s*$", re.MULTILINE)


class RulesManager:
    """Load and query instruction rules stored in ``.astra/rules/``.

    Each ``.md`` file in the rules directory may contain optional YAML
    frontmatter with a ``paths:`` list.  If present, the rule only applies
    to files whose path matches one of those glob patterns.  If omitted,
    the rule applies globally.

    Rules are read-only -- the user edits the Markdown files directly.
    """

    def __init__(self) -> None:
        self._rules: list[Rule] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_rules(self, repo_path: str) -> list[Rule]:
        """Scan ``.astra/rules/*.md`` and parse each file into a Rule.

        Returns the full list of loaded rules.  Subsequent calls reload
        from disk so edits are picked up.
        """
        self._rules = []
        rules_dir = Path(repo_path).resolve() / ".astra" / "rules"

        if not rules_dir.is_dir():
            self._loaded = True
            return []

        for md_file in sorted(rules_dir.glob("*.md")):
            rule = self._parse_rule_file(md_file)
            if rule is not None:
                self._rules.append(rule)

        self._loaded = True
        return list(self._rules)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_rules_for_path(self, file_path: str) -> list[Rule]:
        """Return rules whose path patterns match *file_path*.

        Rules with no path patterns are considered global and always
        included.  Pattern matching uses ``fnmatch`` style globs.
        """
        matching: list[Rule] = []
        normalized = file_path.replace("\\", "/")

        for rule in self._rules:
            if not rule.paths:
                # Global rule -- always applies.
                matching.append(rule)
                continue

            for pattern in rule.paths:
                if fnmatch(normalized, pattern):
                    matching.append(rule)
                    break

        return matching

    def get_all_rules(self) -> str:
        """Return all rule contents concatenated for system prompt injection.

        Each rule is separated by a horizontal line for readability.
        """
        if not self._rules:
            return ""

        parts: list[str] = []
        for rule in self._rules:
            header = f"[rule: {Path(rule.source_file).name}]"
            parts.append(f"{header}\n{rule.content}")

        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_rule_file(md_path: Path) -> Rule | None:
        """Parse a single Markdown rule file.

        Returns ``None`` if the file is empty or unreadable.
        """
        try:
            raw = md_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        raw = raw.strip()
        if not raw:
            return None

        paths: list[str] = []
        content = raw

        fm_match = _FRONTMATTER_RE.match(raw)
        if fm_match:
            frontmatter = fm_match.group(1)
            content = raw[fm_match.end():].strip()

            # Extract the paths list from the frontmatter block.
            paths_section = _extract_paths_section(frontmatter)
            if paths_section is not None:
                paths = _PATHS_ITEM_RE.findall(paths_section)
                # Strip surrounding quotes from each pattern.
                paths = [_strip_quotes(p) for p in paths]

        return Rule(
            content=content,
            source_file=str(md_path),
            paths=paths,
        )


def _extract_paths_section(frontmatter: str) -> str | None:
    """Pull the ``paths:`` value block out of YAML-like frontmatter.

    Handles both inline (``paths: [a, b]``) and multi-line list syntax.
    Returns ``None`` if no ``paths:`` key is found.
    """
    # Look for ``paths:`` key at the start of a line.
    match = re.search(r"^paths:\s*(.*)$", frontmatter, re.MULTILINE)
    if match is None:
        return None

    inline = match.group(1).strip()

    # Inline list: ``paths: ["*.py", "src/**"]``
    if inline.startswith("["):
        bracket_content = inline.strip("[]")
        # Convert comma-separated inline list to YAML-style list lines.
        items = [item.strip() for item in bracket_content.split(",") if item.strip()]
        return "\n".join(f"  - {item}" for item in items)

    if inline and not inline.startswith("#"):
        # Single value on the same line: ``paths: *.py``
        return f"  - {inline}"

    # Multi-line list: collect subsequent ``  - value`` lines.
    lines_after = frontmatter[match.end():]
    collected: list[str] = []
    for line in lines_after.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            collected.append(line)
        elif not stripped:
            continue
        else:
            break

    if collected:
        return "\n".join(collected)

    return None


def _strip_quotes(value: str) -> str:
    """Remove surrounding single or double quotes from a string."""
    if len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'"):
            return value[1:-1]
    return value

"""Safe YAML frontmatter read/write for markdown files.

bb-wiki convention: every node file has YAML frontmatter delimited by `---`
on its own line, followed by markdown body. Missing frontmatter is allowed
(returns empty dict + full text as body).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def split(text: str) -> tuple[dict[str, Any], str]:
    """Split markdown text into (frontmatter_dict, body).

    Empty dict + original text if no frontmatter found.
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)
    return fm, body


def join(frontmatter: dict[str, Any], body: str) -> str:
    """Join frontmatter dict + body into a markdown document.

    Empty frontmatter → return body as-is (no `---` markers).
    """
    if not frontmatter:
        return body
    fm_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    body_norm = body if body.startswith("\n") or not body else "\n" + body
    return f"---\n{fm_text}\n---{body_norm}"


def read(path: Path) -> tuple[dict[str, Any], str]:
    """Read file at path, return (frontmatter, body)."""
    text = path.read_text(encoding="utf-8")
    return split(text)


def write(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    """Write frontmatter + body to path. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(join(frontmatter, body), encoding="utf-8")
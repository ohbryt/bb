"""bb-wiki adapter — markdown IO + index/log management."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Optional

from bb.frontmatter import read, write
from bb.memory import (
    Node,
    SECTION_DIRS,
    node_id_for,
    slugify,
    today_kst,
)
from rich.console import Console

INDEX_FILENAME = "index.md"
LOG_FILENAME = "log.md"
RECENT_SECTION = "## Recent (via bb CLI)"
_err_console = Console(stderr=True)


def find_wiki_root(
    start: Optional[Path] = None,
    env_var: str = "WIKI_ROOT",
) -> Path:
    """Resolve bb-wiki root.

    Priority:
    1. ``$WIKI_ROOT`` env var (must contain a SCHEMA.md).
    2. Walk up from ``start`` (default: cwd) up to 6 levels looking for SCHEMA.md.
    3. Default ``~/openclaw/workspace/bb-wiki``.

    Raises FileNotFoundError if no bb-wiki found.
    """
    env = os.environ.get(env_var)
    if env:
        p = Path(env).expanduser()
        if (p / "SCHEMA.md").exists():
            return p
        raise FileNotFoundError(
            f"{env_var}={p} has no SCHEMA.md — not a bb-wiki checkout"
        )
    cursor = (start or Path.cwd()).resolve()
    for _ in range(6):
        if (cursor / "SCHEMA.md").exists():
            return cursor
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    default = Path("~/openclaw/workspace/bb-wiki").expanduser()
    if (default / "SCHEMA.md").exists():
        return default
    raise FileNotFoundError(
        "bb-wiki not found. Set WIKI_ROOT or run from inside a bb-wiki checkout."
    )


def list_node_paths(root: Path) -> list[Path]:
    """Return all .md node files under recognized sections, sorted by mtime desc."""
    paths: list[Path] = []
    for section in SECTION_DIRS:
        d = root / section
        if not d.exists():
            continue
        paths.extend(
            p for p in d.glob("*.md") if p.name not in (INDEX_FILENAME,)
        )
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths


def load_all_nodes(root: Path) -> list[Node]:
    """Load every node under bb-wiki root.

    Skips malformed files with a stderr warning rather than crashing — a single
    bad frontmatter shouldn't break the entire ``bb status`` / ``bb recall``.
    """
    nodes: list[Node] = []
    for p in list_node_paths(root):
        try:
            nodes.append(Node.from_path(p, root))
        except Exception as e:  # noqa: BLE001 — we want to keep going
            _err_console.print(
                f"[yellow]warning:[/yellow] skipping {p.relative_to(root)}: {e}"
            )
    return nodes


def node_path(root: Path, node_id: str, section: str) -> Path:
    """Return the canonical filesystem path for a node."""
    return root / section / f"{node_id}.md"


def write_node(root: Path, node: Node) -> Path:
    """Write a node to disk. Sets ``updated`` to today."""
    frontmatter = {
        "title": node.title,
        "created": node.created.isoformat(),
        "updated": today_kst().isoformat(),
        "type": node.type,
        "tags": node.tags,
        "sources": node.sources,
    }
    body = node.body if node.body.endswith("\n") else node.body + "\n"
    write(node.path, frontmatter, body)
    return node.path


def remove_node(root: Path, node: Node) -> bool:
    """Remove a node file from disk. Returns True if a file was deleted."""
    if node.path.exists():
        node.path.unlink()
        return True
    return False


# --- index.md / log.md helpers ---------------------------------------------


def append_to_index(root: Path, node: Node) -> bool:
    """Append a bullet under ``## Recent (via bb CLI)`` in index.md.

    Idempotent: re-running with the same node is a no-op.
    Creates the section if missing. Returns True if index was modified.
    """
    index = root / INDEX_FILENAME
    if not index.exists():
        return False
    text = index.read_text(encoding="utf-8")
    bullet = f"- [{node.title}]({node.section}/{node.id}.md)"
    if bullet in text:
        return False
    if RECENT_SECTION in text:
        text = text.replace(
            RECENT_SECTION,
            f"{RECENT_SECTION}\n\n{bullet}",
            1,
        )
    else:
        text = text.rstrip() + f"\n\n{RECENT_SECTION}\n\n{bullet}\n"
    index.write_text(text, encoding="utf-8")
    return True


def remove_from_index(root: Path, node: Node) -> bool:
    """Remove the bullet for a node from index.md. Idempotent.

    Only touches the ``## Recent (via bb CLI)`` section so human edits
    elsewhere are preserved.
    """
    index = root / INDEX_FILENAME
    if not index.exists():
        return False
    text = index.read_text(encoding="utf-8")
    bullet = f"- [{node.title}]({node.section}/{node.id}.md)"
    new_lines = [line for line in text.splitlines() if line.rstrip() != bullet]
    new_text = "\n".join(new_lines)
    if new_text == text:
        return False
    index.write_text(new_text + "\n", encoding="utf-8")
    return True


def append_to_log(root: Path, action: str, node: Node) -> bool:
    """Append an audit entry to log.md (append-only, per SCHEMA.md)."""
    log = root / LOG_FILENAME
    if not log.exists():
        return False
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    entry = (
        f"- `{ts}` **{action}** — `{node.id}` "
        f"({node.section}/{node.id}.md)\n"
    )
    with log.open("a", encoding="utf-8") as f:
        f.write(entry)
    return True


# --- search -----------------------------------------------------------------


def search(
    root: Path,
    query: str,
    top: int = 5,
    section: str = "all",
) -> list[tuple[Node, float, str]]:
    """Keyword search across nodes.

    Returns ``(node, score, snippet)`` sorted by score desc.

    Scoring (per token): title hits ×3, tag hits ×2, body hits ×1.
    """
    q = query.lower().strip()
    if not q:
        return []
    tokens = [t for t in q.split() if t]
    if not tokens:
        return []
    results: list[tuple[Node, float, str]] = []
    for node in load_all_nodes(root):
        if section != "all" and node.section != section:
            continue
        title_l = node.title.lower()
        tags_l = " ".join(node.tags).lower()
        body_l = node.body.lower()
        score = 0.0
        snippet = ""
        for tok in tokens:
            t_hits = title_l.count(tok)
            g_hits = tags_l.count(tok)
            b_hits = body_l.count(tok)
            score += t_hits * 3 + g_hits * 2 + b_hits
            if not snippet and b_hits > 0:
                idx = body_l.find(tok)
                start = max(0, idx - 60)
                end = min(len(node.body), idx + 140)
                snippet = (
                    ("…" if start > 0 else "")
                    + node.body[start:end].replace("\n", " ").strip()
                    + ("…" if end < len(node.body) else "")
                )
        if score > 0:
            results.append((node, score, snippet))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top]
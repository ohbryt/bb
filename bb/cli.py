"""bb CLI — thin memory-ops wrapper over bb-wiki.

Commands mirror cognee's memory API: ``remember / recall / forget``, plus a
wiki-aware ``status`` for at-a-glance health.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from bb import __version__
from bb.memory import (
    SECTION_TO_TYPE,
    Node,
    node_id_for,
    today_kst,
)
from bb.wiki import (
    append_to_index,
    append_to_log,
    find_wiki_root,
    load_all_nodes,
    node_path,
    remove_from_index,
    remove_node,
    search,
    write_node,
)

app = typer.Typer(
    name="bb",
    help="Brown Biotech CLI — thin memory-ops wrapper over bb-wiki.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err = Console(stderr=True)


def _err(msg: str) -> None:
    err.print(f"[bold red]error:[/bold red] {msg}")
    raise typer.Exit(code=1)


def _resolve_root(wiki_root: Optional[Path]) -> Path:
    try:
        return wiki_root or find_wiki_root()
    except FileNotFoundError as e:
        _err(str(e))


@app.command()
def version() -> None:
    """Print bb version."""
    console.print(f"bb {__version__}")


@app.command()
def status(
    wiki_root: Optional[Path] = typer.Option(
        None,
        "--wiki-root",
        "-w",
        help="bb-wiki root path (default: auto-detect or $WIKI_ROOT).",
    ),
) -> None:
    """Show bb-wiki stats: node count by section + recent activity."""
    root = _resolve_root(wiki_root)
    nodes = load_all_nodes(root)
    by_section: dict[str, int] = {}
    for n in nodes:
        by_section[n.section] = by_section.get(n.section, 0) + 1

    table = Table(title=f"bb-wiki @ {root}", show_header=True)
    table.add_column("section", style="cyan")
    table.add_column("count", justify="right", style="magenta")
    for sec in ("raw", "concepts", "entities", "queries", "comparisons"):
        if sec in by_section:
            table.add_row(sec, str(by_section[sec]))
    if by_section:
        table.add_row("[bold]total[/bold]", f"[bold]{len(nodes)}[/bold]")
    console.print(table)

    cutoff = today_kst() - dt.timedelta(days=7)
    recent = [n for n in nodes if n.created >= cutoff]
    if recent:
        console.print(
            f"\n[green]{len(recent)} nodes added in the last 7 days[/green]"
        )
        for n in recent[:5]:
            console.print(
                f"  • [dim]{n.created.isoformat()}[/dim] "
                f"{n.section}/{n.id}.md"
            )
    else:
        console.print("\n[dim]no nodes added in the last 7 days[/dim]")


@app.command()
def remember(
    text: str = typer.Argument(..., help="Memory text to remember."),
    tags: str = typer.Option(
        "",
        "--tags",
        "-t",
        help="Comma-separated tags.",
    ),
    source: str = typer.Option(
        "",
        "--source",
        "-s",
        help="Source URL, DOI, or PMID.",
    ),
    section: str = typer.Option(
        "raw",
        "--section",
        help="Target section: raw|concepts|entities|queries|comparisons.",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        help="Override page title (default: first line of text, max 80 chars).",
    ),
    wiki_root: Optional[Path] = typer.Option(
        None,
        "--wiki-root",
        "-w",
    ),
) -> None:
    """Save a memory node to bb-wiki."""
    if not text.strip():
        _err("text cannot be empty")
    if section not in SECTION_TO_TYPE:
        _err(
            f"invalid section: {section!r}. "
            f"Choose from {sorted(SECTION_TO_TYPE)}."
        )
    root = _resolve_root(wiki_root)

    created = today_kst()
    node_id = node_id_for(text, created=created)
    path = node_path(root, node_id, section)
    if path.exists():
        _err(
            f"node already exists: {path.relative_to(root)}. "
            "Use different text or --section."
        )

    page_title = title or text.split("\n", 1)[0].strip()[:80]
    body = (
        f"{text}\n\n"
        "## 4-섹션 판단 레이어\n\n"
        "### 1. Source Quotes\n\n_FILL_\n\n"
        "### 2. My Interpretation\n\n_FILL_\n\n"
        "### 3. Open Questions\n\n_FILL_\n\n"
        "### 4. Contradictions\n\n_FILL_\n"
    )
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    source_list = [source] if source else []

    node = Node(
        id=node_id,
        title=page_title,
        created=created,
        updated=created,
        type=SECTION_TO_TYPE[section],
        tags=tag_list,
        sources=source_list,
        body=body.strip(),
        path=path,
        section=section,
    )
    write_node(root, node)
    append_to_index(root, node)
    append_to_log(root, "remember", node)
    console.print(f"[green]✓ remembered[/green] {path.relative_to(root)}")


@app.command()
def recall(
    query: str = typer.Argument(..., help="Search query."),
    top: int = typer.Option(5, "--top", "-n", help="Max results."),
    section: str = typer.Option(
        "all",
        "--section",
        help="Filter by section.",
    ),
    wiki_root: Optional[Path] = typer.Option(
        None,
        "--wiki-root",
        "-w",
    ),
) -> None:
    """Search bb-wiki for relevant memory nodes."""
    if not query.strip():
        _err("query cannot be empty")
    root = _resolve_root(wiki_root)
    results = search(root, query, top=top, section=section)
    if not results:
        console.print(f"[yellow]no matches for[/yellow] '{query}'")
        raise typer.Exit(code=0)

    table = Table(
        title=f"recall: '{query}'  (top {len(results)})",
        show_header=True,
    )
    table.add_column("score", justify="right", style="magenta")
    table.add_column("section", style="cyan")
    table.add_column("node", style="green", overflow="fold", min_width=40)
    table.add_column("snippet", style="dim", overflow="fold")
    for node, score, snippet in results:
        table.add_row(
            f"{score:.0f}",
            node.section,
            node.id,
            snippet or "—",
        )
    console.print(table)


@app.command()
def forget(
    node_id: str = typer.Argument(
        ...,
        help="Node id (YYYY-MM-DD-<slug>) to forget.",
    ),
    wiki_root: Optional[Path] = typer.Option(
        None,
        "--wiki-root",
        "-w",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
) -> None:
    """Remove a memory node from bb-wiki."""
    root = _resolve_root(wiki_root)

    target: Optional[Path] = None
    section_found: Optional[str] = None
    for sec in ("raw", "concepts", "entities", "queries", "comparisons"):
        candidate = root / sec / f"{node_id}.md"
        if candidate.exists():
            target = candidate
            section_found = sec
            break
    if target is None or section_found is None:
        _err(f"node not found: {node_id}.md in any section")

    if not yes:
        confirm = typer.confirm(
            f"remove {section_found}/{node_id}.md?", default=False
        )
        if not confirm:
            console.print("[dim]cancelled[/dim]")
            raise typer.Abort()

    node = Node.from_path(target, root)
    remove_node(root, node)
    remove_from_index(root, node)
    append_to_log(root, "forget", node)
    console.print(f"[green]✓ forgotten[/green] {section_found}/{node_id}.md")


if __name__ == "__main__":
    app()
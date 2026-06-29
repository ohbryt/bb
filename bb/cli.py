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
from bb.data.bb_qa_tickets import (
    ADVISORY_TICKETS,
    BLOCKING_TICKETS,
    PIPELINE_PHASES,
    TICKETS,
    Phase,
    Severity,
    Ticket,
)
from bb.ticket import Finding, blocking_failures, inspect_node
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


def _find_node(root: Path, node_id: str) -> tuple[Node, str]:
    """Find a node by id (YYYY-MM-DD-<slug>) across all sections.

    Returns ``(node, section)``. Raises typer.Exit(1) if not found.

    Used by ``forget``, ``ticket inspect``, ``review``, ``gate`` to avoid
    duplicating the section-loop logic.
    """
    for sec in ("raw", "concepts", "entities", "queries", "comparisons"):
        path = root / sec / f"{node_id}.md"
        if path.exists():
            return Node.from_path(path, root), sec
    _err(f"node not found: {node_id}.md in any section")


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


# --- ticket subcommands (added 2026-06-29, OpenDraft back-port) ----------


def _ticket_table(tickets: Iterable[Ticket]) -> None:
    """Pretty-print a ticket table grouped by pipeline phase."""
    for phase, descr in PIPELINE_PHASES:
        rows = [t for t in tickets if t.phase == phase]
        if not rows:
            continue
        console.rule(f"[cyan]{phase}[/cyan]  [dim]{descr}[/dim]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("code", style="green", min_width=32)
        table.add_column("name", style="magenta")
        table.add_column("severity", justify="center")
        table.add_column("bb_mapping", style="dim", overflow="fold", min_width=28)
        for t in rows:
            sev_color = "red" if t.severity == "blocking" else "yellow"
            table.add_row(
                t.code,
                t.name,
                f"[{sev_color}]{t.severity}[/{sev_color}]",
                t.bb_mapping,
            )
        console.print(table)


@app.command(name="ticket")
def ticket_cmd(
    node_id: Optional[str] = typer.Argument(
        None,
        help="Node id to inspect. Omit to list the full ticket taxonomy.",
    ),
    phase: Optional[str] = typer.Option(
        None,
        "--phase",
        help="Filter by pipeline phase: research|structure|compose|qa|export",
    ),
    severity: Optional[str] = typer.Option(
        None,
        "--severity",
        help="Filter by severity: blocking|advisory",
    ),
    wiki_root: Optional[Path] = typer.Option(
        None,
        "--wiki-root",
        "-w",
    ),
) -> None:
    """bb QA ticket taxonomy (16 tickets, OpenDraft back-port 2026-06-29).

    With no args:    list all 16 tickets grouped by 5-Phase pipeline.
    With <node-id>:  run heuristics against the node and surface findings.
    """
    if phase is not None and phase not in ("research", "structure", "compose", "qa", "export"):
        _err(f"invalid --phase: {phase!r}")
    if severity is not None and severity not in ("blocking", "advisory"):
        _err(f"invalid --severity: {severity!r}")

    if node_id is None:
        # List mode (no node = show taxonomy)
        tickets: Iterable[Ticket] = TICKETS
        if phase:
            tickets = [t for t in TICKETS if t.phase == phase]
        if severity:
            tickets = [t for t in tickets if t.severity == severity]
        if not tickets:
            console.print("[yellow]no tickets match filter[/yellow]")
            raise typer.Exit(code=0)
        console.print(
            f"[bold]bb QA tickets[/bold]  "
            f"[dim]{len(list(tickets))} shown "
            f"(of {len(TICKETS)} total — "
            f"{len(BLOCKING_TICKETS)} blocking, {len(ADVISORY_TICKETS)} advisory)[/dim]"
        )
        console.print()
        _ticket_table(tickets)
        return

    # Inspect mode
    root = _resolve_root(wiki_root)
    node, section = _find_node(root, node_id)
    console.print(
        f"[bold]bb ticket inspect[/bold]  "
        f"[cyan]{section}/{node.id}.md[/cyan]  [dim]{node.title!r}[/dim]"
    )
    findings = inspect_node(node, severity=severity, phase=phase)
    if not findings:
        console.print("[green]✓ no ticket signals detected[/green]")
        raise typer.Exit(code=0)

    table = Table(show_header=True, header_style="bold")
    table.add_column("phase", style="cyan", min_width=10)
    table.add_column("status", justify="center", min_width=6)
    table.add_column("ticket", style="magenta", overflow="fold", min_width=26)
    table.add_column("detail", overflow="fold")
    for f in findings:
        status_color = {"ok": "green", "warn": "yellow", "fail": "red"}[f.status]
        table.add_row(
            f.ticket.phase,
            f"[{status_color}]{f.status.upper()}[/{status_color}]",
            f"{f.ticket.code}  ({f.ticket.name})",
            f.detail,
        )
    console.print(table)
    blocking_open = blocking_failures(findings)
    if blocking_open:
        console.print(
            f"\n[red]✗ {len(blocking_open)} BLOCKING ticket(s) failed[/red]  "
            f"(would block pre-publish)"
        )
        raise typer.Exit(code=1)
    console.print(
        f"\n[green]✓ no blocking tickets failed[/green]  "
        f"({len(findings)} advisory / warning signal(s))"
    )


@app.command(name="review")
def review_cmd(
    node_id: str = typer.Argument(..., help="Node id to review (advisory QA)."),
    wiki_root: Optional[Path] = typer.Option(None, "--wiki-root", "-w"),
) -> None:
    """Advisory QA pass — OpenDraft Thread/Narrator style. Always exits 0.

    Surfaces every advisory ticket signal so Dr. OCM can decide whether to
    address them. Use this when iterating on a draft — never blocks.
    """
    root = _resolve_root(wiki_root)
    node, section = _find_node(root, node_id)
    console.print(
        f"[bold]bb review[/bold]  [dim](advisory — non-blocking)[/dim]\n"
        f"  [cyan]{section}/{node.id}.md[/cyan]  [dim]{node.title!r}[/dim]\n"
    )
    findings = inspect_node(node, severity="advisory")
    if not findings:
        console.print("[green]✓ no advisory signals[/green]")
        raise typer.Exit(code=0)
    table = Table(show_header=True, header_style="bold")
    table.add_column("phase", style="cyan", min_width=10)
    table.add_column("ticket", style="magenta", overflow="fold", min_width=26)
    table.add_column("detail", overflow="fold")
    for f in findings:
        status_color = "yellow" if f.status == "warn" else "green"
        table.add_row(
            f.ticket.phase,
            f"[{status_color}]{f.status} {f.ticket.code} ({f.ticket.name})[/{status_color}]",
            f.detail,
        )
    console.print(table)
    console.print(
        f"\n[dim]review complete — {len(findings)} advisory signal(s). "
        f"Run `bb gate {node_id}` for blocking pre-publish check.[/dim]"
    )


@app.command(name="gate")
def gate_cmd(
    node_id: str = typer.Argument(..., help="Node id to gate (blocking QA)."),
    wiki_root: Optional[Path] = typer.Option(None, "--wiki-root", "-w"),
) -> None:
    """Blocking QA pass — OpenDraft Citation-Compiler style.

    Surfaces every blocking ticket signal. Exits 1 if any blocking ticket
    failed — use this in pre-publish CI or before client delivery.
    """
    root = _resolve_root(wiki_root)
    node, section = _find_node(root, node_id)
    console.print(
        f"[bold]bb gate[/bold]  [dim](blocking — exit 1 if any BLOCKING ticket fails)[/dim]\n"
        f"  [cyan]{section}/{node.id}.md[/cyan]  [dim]{node.title!r}[/dim]\n"
    )
    findings = inspect_node(node, severity="blocking")
    if not findings:
        console.print("[green]✓ pass — no blocking ticket signals detected[/green]")
        raise typer.Exit(code=0)

    table = Table(show_header=True, header_style="bold")
    table.add_column("phase", style="cyan", min_width=10)
    table.add_column("status", justify="center", min_width=6)
    table.add_column("ticket", style="magenta", overflow="fold", min_width=26)
    table.add_column("detail", overflow="fold")
    for f in findings:
        status_color = {"ok": "green", "warn": "yellow", "fail": "red"}[f.status]
        table.add_row(
            f.ticket.phase,
            f"[{status_color}]{f.status.upper()}[/{status_color}]",
            f"{f.ticket.code} ({f.ticket.name})",
            f.detail,
        )
    console.print(table)

    fails = blocking_failures(findings)
    if fails:
        console.print(
            f"\n[red]✗ gate FAIL — {len(fails)} blocking ticket(s) violated[/red]"
        )
        for f in fails:
            console.print(f"  • {f.ticket.code} [{f.ticket.phase}]: {f.detail}")
        raise typer.Exit(code=1)
    console.print(
        f"\n[green]✓ gate PASS — no blocking ticket violated "
        f"({len(findings)} blocking ticket(s) OK)[/green]"
    )


if __name__ == "__main__":
    app()
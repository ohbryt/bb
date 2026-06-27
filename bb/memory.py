"""Node model + ops for bb-wiki memory entries."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from pydantic import BaseModel, Field

# KST timezone (UTC+9) — bb-wiki frontmatter uses local-date convention.
_KST = dt.timezone(dt.timedelta(hours=9))

# Sections recognized by bb. Mapped to bb-wiki directory names.
SECTION_DIRS: tuple[str, ...] = (
    "raw",
    "concepts",
    "entities",
    "queries",
    "comparisons",
)

# Map bb-wiki directory → frontmatter `type` value.
SECTION_TO_TYPE: dict[str, str] = {
    "raw": "raw-note",
    "concepts": "concept",
    "entities": "entity",
    "queries": "query",
    "comparisons": "comparison",
}

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, replace non-alphanumerics with hyphens, collapse, trim.

    >>> slugify("Hello World")
    'hello-world'
    >>> slugify("KEAP1 NRF2 axis!")
    'keap1-nrf2-axis'
    """
    s = SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "untitled"


def today_kst() -> dt.date:
    """Today's date in KST (UTC+9). Matches bb-wiki's local-date frontmatter."""
    return dt.datetime.now(_KST).date()


def node_id_for(text: str, created: dt.date | None = None) -> str:
    """Generate a YYYY-MM-DD-<slug> node id from text."""
    date = created or today_kst()
    return f"{date.isoformat()}-{slugify(text)[:48]}"


def _coerce_date(value: object, default: dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return default
    return default


class Node(BaseModel):
    """A bb-wiki memory node (one markdown file)."""

    id: str = Field(..., description="YYYY-MM-DD-<slug>")
    title: str
    created: dt.date
    updated: dt.date
    type: str
    tags: list[str] = Field(default_factory=list)
    sources: list[object] = Field(
        default_factory=list,
        description="Source URLs / DOIs / PMIDs / structured refs. Mixed types allowed.",
    )
    body: str
    path: Path
    section: str

    @classmethod
    def from_path(cls, path: Path, wiki_root: Path) -> "Node":
        """Load a Node from a markdown file on disk."""
        from bb.frontmatter import read

        rel = path.relative_to(wiki_root)
        section = rel.parts[0] if len(rel.parts) > 1 else "raw"
        fm, body = read(path)
        return cls(
            id=path.stem,
            title=fm.get("title", path.stem),
            created=_coerce_date(fm.get("created"), dt.date.today()),
            updated=_coerce_date(fm.get("updated"), dt.date.today()),
            type=fm.get("type", "raw-note"),
            tags=list(fm.get("tags") or []),
            sources=list(fm.get("sources") or []),
            body=body.strip(),
            path=path,
            section=section,
        )
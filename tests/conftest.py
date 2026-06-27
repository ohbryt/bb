"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_wiki(tmp_path: Path) -> Path:
    """Create a minimal bb-wiki fixture (mirrors real SCHEMA.md layout)."""
    root = tmp_path / "wiki"
    root.mkdir()
    (root / "SCHEMA.md").write_text("# bb-wiki schema (test fixture)\n")
    (root / "index.md").write_text("# bb-wiki index\n")
    (root / "log.md").write_text("# bb-wiki log\n")
    for sec in ("raw", "concepts", "entities", "queries", "comparisons"):
        (root / sec).mkdir()

    # Sample entity node
    sample = (
        "---\n"
        "title: NAAA lead compound\n"
        "created: 2026-06-14\n"
        "updated: 2026-06-14\n"
        "type: entity\n"
        "tags: [naaa, synthesis, drug-discovery]\n"
        "sources: []\n"
        "---\n\n"
        "# NAAA lead compound\n\n"
        "CHEMBL2419814 is the lead NAAA inhibitor with "
        "-13.0 kcal/mol binding affinity (PDB 6DXX).\n"
    )
    (root / "entities" / "naaa-lead.md").write_text(sample, encoding="utf-8")
    return root
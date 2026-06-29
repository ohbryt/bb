"""Tests for bb.data.bb_qa_tickets and bb.ticket (added 2026-06-29).

Covers the OpenDraft back-port: 16-ticket taxonomy + deterministic heuristics.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from bb.data.bb_qa_tickets import (
    ADVISORY_TICKETS,
    BLOCKING_TICKETS,
    PIPELINE_PHASES,
    TICKETS,
    TICKETS_BY_CODE,
    TICKETS_BY_PHASE,
    Ticket,
    get,
)
from bb.memory import Node
from bb.ticket import (
    HEURISTICS,
    Finding,
    blocking_failures,
    inspect_node,
)


# --- taxonomy invariants --------------------------------------------------


def test_tickets_count():
    """OpenDraft shipped 16 tickets — must stay exactly 16."""
    assert len(TICKETS) == 16, f"expected 16 tickets, got {len(TICKETS)}"


def test_tickets_unique_codes():
    codes = [t.code for t in TICKETS]
    assert len(codes) == len(set(codes)), "ticket codes must be unique"


def test_severity_split():
    """7 blocking + 9 advisory per current data (verify taxonomy balance)."""
    assert len(BLOCKING_TICKETS) == 7, f"expected 7 blocking, got {len(BLOCKING_TICKETS)}"
    assert len(ADVISORY_TICKETS) == 9, f"expected 9 advisory, got {len(ADVISORY_TICKETS)}"


def test_phase_coverage():
    """Every 5 pipeline phases has at least one ticket."""
    expected = {"research", "structure", "compose", "qa", "export"}
    assert set(TICKETS_BY_PHASE) == expected


def test_pipeline_phases_count():
    """OpenDraft 5-phase pipeline must stay exactly 5 phases."""
    assert len(PIPELINE_PHASES) == 5


def test_get_returns_ticket():
    t = get("bb-ticket-005-padding")
    assert t.name == "padding"
    assert t.severity == "blocking"


def test_get_unknown_raises():
    import pytest

    with pytest.raises(KeyError, match="unknown ticket code"):
        get("bb-ticket-999-fake")


def test_every_ticket_has_heuristic():
    """Theorist: TICKETS must match HEURISTICS keys 1:1."""
    codes_in_taxonomy = {t.code for t in TICKETS}
    codes_with_heuristic = set(HEURISTICS)
    assert codes_in_taxonomy == codes_with_heuristic, (
        f"ticket/heuristic mismatch — taxonomy only: {codes_in_taxonomy - codes_with_heuristic}, "
        f"heuristic only: {codes_with_heuristic - codes_in_taxonomy}"
    )


# --- inspector smoke tests ------------------------------------------------


def _make_node(title: str, body: str, section: str = "raw") -> Node:
    """Test helper — build a Node without going through the wiki."""
    nid = "2026-06-29-test"
    path = Path(f"/tmp/bb-test/{section}/{nid}.md")
    return Node(
        id=nid,
        title=title,
        created=dt.date(2026, 6, 29),
        updated=dt.date(2026, 6, 29),
        type="raw-note",
        tags=[],
        sources=[],
        body=body,
        path=path,
        section=section,
    )


# rich body — every section present, citations inline, no padding
RICH_BODY = """\
Title intro.

## 4-섹션 판단 레이어

### 1. Source Quotes
> "SLC7A2 intron 1 SNP P < 1e-15" [1] and the alpha-cell regulatory region.

### 2. My Interpretation
The 2024 EXTEND cohort study [Smith et al., 2024] demonstrated a strong
signal, but the mechanism may involve several pathways.

### 3. Open Questions
- Is the SLC7A2 finding specific to alpha cells, or shared with beta cells?
- What is the effect size in non-European cohorts?

### 4. Contradictions
None observed vs. previous literature (DiGruccio 2016).
"""


def test_rich_node_passes_methodology():
    node = _make_node("SLC7A2 alpha-cell proliferation", RICH_BODY)
    findings = inspect_node(node, severity="blocking")
    # TICKET-001 should be ok (rich content + 4-섹션)
    methodology = [f for f in findings if f.ticket.code == "bb-ticket-001-methodology"]
    assert all(f.status != "fail" for f in methodology), (
        f"methodology failed on rich node: {methodology}"
    )


def test_empty_body_triggers_failures():
    node = _make_node("stub", "")
    findings = inspect_node(node)
    fails = blocking_failures(findings)
    assert len(fails) >= 1, "empty body must trigger at least one blocking failure"


def test_blocking_failures_helper():
    ok = Finding(Ticket("bb-ticket-x", "x", "x", "compose", "advisory", "x"), "ok", "")
    fail = Finding(Ticket("bb-ticket-y", "y", "y", "compose", "blocking", "y"), "fail", "boom")
    fails = blocking_failures([ok, fail])
    assert len(fails) == 1 and fails[0].status == "fail"


def test_overconfident_heuristic_detects_absolute_words():
    body = """
This discovery will prove that the pathway always works.
The mechanism definitely drives tumor growth in every case we examined.
These findings certainly confirm the original hypothesis without doubt.
"""
    node = _make_node("overconfident draft", body)
    findings = inspect_node(node)
    overconf = [f for f in findings if f.ticket.code == "bb-ticket-007-overconfident"]
    assert overconf, "expected TICKET-007 to trigger"
    assert overconf[0].status == "warn"


def test_phase_filter():
    """--phase compose should only return compose-phase tickets."""
    node = _make_node("SLC7A2 alpha-cell", RICH_BODY)
    findings = inspect_node(node, phase="compose")
    assert all(f.ticket.phase == "compose" for f in findings)


def test_severity_filter():
    """--severity advisory should only return advisory tickets."""
    node = _make_node("SLC7A2 alpha-cell", RICH_BODY)
    findings = inspect_node(node, severity="advisory")
    assert all(f.ticket.severity == "advisory" for f in findings)

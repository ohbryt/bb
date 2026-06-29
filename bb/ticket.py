"""bb ticket inspector — heuristic ticket scoring over bb-wiki nodes.

Back-port from OpenDraft (MIT, 2026-06-29) — see ``brown-biotech-oss-skill-back-port``
and ``~/.hermes/reads/opendraft/SYNTHESIS.md``.

This module is pure (no LLM, no DB) so it can run in CI / pre-publish gates
without API cost. Each ticket ships with a deterministic ``heuristic()`` that
looks for surface-level signals (regex / count / density). The multi-LLM judge
ensemble in ``brown-biotech-bb-rubric-scorer`` is the deeper layer; this is
the cheap-and-fast gate that catches obvious failures first.

Two CLI surfaces consume this module:

- ``bb review <node-id>`` — advisory only (exit 0), surfaces advisory tickets.
- ``bb gate <node-id>``   — blocking (exit 1 if any BLOCKING ticket violated).

Tickets source-of-truth: ``bb.data.bb_qa_tickets``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from bb.data.bb_qa_tickets import (
    ADVISORY_TICKETS,
    BLOCKING_TICKETS,
    PIPELINE_PHASES,
    TICKETS,
    TICKETS_BY_PHASE,
    Phase,
    Severity,
    Ticket,
)
from bb.memory import Node


# --- result type ----------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    ticket: Ticket
    status: str          # "ok" | "warn" | "fail"
    detail: str          # human-readable explanation
    snippet: str = ""    # optional excerpt (≤120 chars)

    def is_blocking_failure(self) -> bool:
        return self.ticket.severity == "blocking" and self.status == "fail"


# --- heuristics (per-ticket) ----------------------------------------------


def _word_count(body: str) -> int:
    return len(re.findall(r"\S+", body))


def _citation_count(body: str) -> int:
    """Count visible citation markers: [1], (Author, 2024), DOI:..., PMID:..."""
    patterns = [
        r"\[\d+\]",                       # numbered references [1]
        r"\([A-Z][A-Za-z\- ]+ et al\.,? \d{4}\)",  # (Smith et al., 2024)
        r"\(\d{4}\)",                     # year-only inline (Smith, 2024)
        r"PMID:\s*\d+",                   # PubMed
        r"DOI:\s*10\.\d+",                # DOI
        r"arXiv:\d{4}\.\d{4,5}",          # arXiv ID
    ]
    n = 0
    for p in patterns:
        n += len(re.findall(p, body))
    return n


def _section_present(body: str, name: str) -> bool:
    """Check if a markdown section heading like ``## name`` is filled (not ``_FILL_``)."""
    pattern = rf"^##+\s*{re.escape(name)}\s*$(.+?)(?=^##+\s|\Z)"
    m = re.search(pattern, body, re.MULTILINE | re.DOTALL)
    if not m:
        return False
    content = m.group(1).strip()
    return bool(content) and "_FILL_" not in content[:80]


def _title_words(title: str) -> set[str]:
    return {w.lower() for w in re.findall(r"\w{4,}", title)}


def _has_4section_judgment(node: Node) -> bool:
    body = node.body or ""
    return (
        _section_present(body, "Source Quotes")
        and _section_present(body, "My Interpretation")
        and _section_present(body, "Open Questions")
        and _section_present(body, "Contradictions")
    )


# Per-ticket heuristics. Each returns (status, detail, snippet) or ("ok", "", "").


def _h_methodology(node: Node) -> tuple[str, str, str]:
    if _word_count(node.body) < 200:
        return "warn", "very short body — methodology hard to assess", node.body[:120]
    if not _has_4section_judgment(node):
        return "fail", "missing 4-섹션 judgment layer (Source Quotes / Interpretation / Open Questions / Contradictions)", ""
    return "ok", "", ""


def _h_analysis(node: Node) -> tuple[str, str, str]:
    if not _section_present(node.body, "Open Questions"):
        return "warn", "Open Questions section empty — analysis depth signal missing", ""
    return "ok", "", ""


def _h_citation_mismatch(node: Node) -> tuple[str, str, str]:
    n = _citation_count(node.body)
    if n == 0 and _word_count(node.body) > 200:
        return "fail", f"0 citation markers in {_word_count(node.body)} words — citation fidelity unverifiable", ""
    return "ok", "", ""


def _h_preprints(node: Node) -> tuple[str, str, str]:
    if re.search(r"arXiv:\d{4}\.\d+|biorxiv|medrxiv", node.body, re.IGNORECASE):
        return "warn", "preprint URL detected — verify journal version exists", ""
    return "ok", "", ""


def _h_padding(node: Node) -> tuple[str, str, str]:
    words = _word_count(node.body)
    cites = _citation_count(node.body)
    if words > 500 and cites > 0 and cites / max(words / 100, 1) < 1.0:
        # < 1 citation per 100 words = sparse padding signal
        return "warn", f"low citation density: {cites} citations / {words} words ({cites * 100 // max(words, 1)} per 100w) — check for padding", ""
    return "ok", "", ""


def _h_contradictions(node: Node) -> tuple[str, str, str]:
    # Heuristic: detect both "however" and "in contrast" in same body
    body = node.body.lower()
    if "however" in body and "in contrast" in body:
        return "warn", "both 'however' and 'in contrast' present — manual cross-check recommended", ""
    return "ok", "", ""


def _h_overconfident(node: Node) -> tuple[str, str, str]:
    absolute_patterns = [
        r"\b(always|never|definitely|certainly|will prove|proves that)\b",
    ]
    body = node.body
    hits = sum(len(re.findall(p, body, re.IGNORECASE)) for p in absolute_patterns)
    if hits >= 3:
        return "warn", f"{hits} absolute-claim patterns found (always/never/definitely/...) — consider hedging", ""
    return "ok", "", ""


def _h_semantic_scholar(node: Node) -> tuple[str, str, str]:
    return "ok", "", ""  # infra check — out of scope for static body inspection


def _h_precision(node: Node) -> tuple[str, str, str]:
    if re.search(r"(?:≈|~|\bapproximately\b|\babout\s+\d)", node.body):
        return "warn", "approximation symbols detected (≈/~, 'approximately', 'about N') — verify exactness", ""
    return "ok", "", ""


def _h_repetition(node: Node) -> tuple[str, str, str]:
    # Cheap heuristic: detect duplicate bigrams
    words = re.findall(r"\w+", node.body.lower())
    bigrams = [tuple(words[i:i+2]) for i in range(len(words) - 1)]
    dup = sum(1 for i in range(len(bigrams) - 1) if bigrams[i] == bigrams[i + 1] and len(bigrams[i][0]) > 3)
    if dup >= 5:
        return "warn", f"{dup} duplicate bigrams — possible repetition", ""
    return "ok", "", ""


def _h_grammar(node: Node) -> tuple[str, str, str]:
    # Cheap heuristic: double-space + repeated comma
    if re.search(r"  +", node.body) or re.search(r",,", node.body):
        return "warn", "double-space or double-comma detected", ""
    return "ok", "", ""


def _h_table_numbering(node: Node) -> tuple[str, str, str]:
    tables = re.findall(r"^(?:Table|Figure)\s+(\d+)", node.body, re.MULTILINE)
    if not tables:
        return "ok", "", ""
    nums = sorted(int(t) for t in tables)
    if nums != list(range(1, len(nums) + 1)):
        return "warn", f"non-contiguous table/figure numbering: {nums}", ""
    return "ok", "", ""


def _h_document_type(node: Node) -> tuple[str, str, str]:
    if node.section == "raw" and _word_count(node.body) > 1500:
        return "warn", "raw-note longer than typical brief — promote to concept/paper section?", ""
    return "ok", "", ""


def _h_domain_terminology(node: Node) -> tuple[str, str, str]:
    # Cheap heuristic: domain jargon with sloppy descriptors
    body = node.body.lower()
    if re.search(r"\b(methylation|metabol[ie]?[cz]ed?|epigeneti[cs]+)\b", body) and re.search(r"\b(generally|usually|always)\b", body):
        return "warn", "epigenetic/methylation claims often overgeneralized — check specificity", ""
    return "ok", "", ""


def _h_domain_coverage(node: Node) -> tuple[str, str, str]:
    # Cheap heuristic: domain coverage — clinical/ML/wet-lab topic missing key study-type citations
    body = node.body.lower()
    if "clinical" in body and not re.search(r"\b(rct|randomized|trial|meta-analysis|cohort)\b", body):
        return "warn", "clinical topic but no RCT/trial/cohort citation — domain gap likely", ""
    return "ok", "", ""


def _h_title_promise(node: Node) -> tuple[str, str, str]:
    body_words = {w.lower() for w in re.findall(r"\w{4,}", node.body)}
    title_words = _title_words(node.title)
    if not title_words:
        return "ok", "", ""
    overlap = title_words & body_words
    coverage = len(overlap) / len(title_words) if title_words else 1.0
    if coverage < 0.5:
        return "fail", f"only {int(coverage * 100)}% of title keywords appear in body — title promises content that is not delivered", ""
    return "ok", "", ""


HEURISTICS: dict[str, Callable[[Node], tuple[str, str, str]]] = {
    "bb-ticket-001-methodology":      _h_methodology,
    "bb-ticket-002-analysis":         _h_analysis,
    "bb-ticket-003-citation_mismatch": _h_citation_mismatch,
    "bb-ticket-004-preprints":        _h_preprints,
    "bb-ticket-005-padding":          _h_padding,
    "bb-ticket-006-contradictions":   _h_contradictions,
    "bb-ticket-007-overconfident":    _h_overconfident,
    "bb-ticket-008-semantic_scholar": _h_semantic_scholar,
    "bb-ticket-009-precision":        _h_precision,
    "bb-ticket-010-repetition":       _h_repetition,
    "bb-ticket-011-grammar":          _h_grammar,
    "bb-ticket-012-table_numbering":  _h_table_numbering,
    "bb-ticket-013-document_type":    _h_document_type,
    "bb-ticket-014-domain-terminology": _h_domain_terminology,
    "bb-ticket-015-domain-coverage":  _h_domain_coverage,
    "bb-ticket-016-title_promise":    _h_title_promise,
}


# --- public API -----------------------------------------------------------


def inspect_node(
    node: Node,
    severity: Optional[Severity] = None,
    phase: Optional[Phase] = None,
) -> list[Finding]:
    """Run all relevant ticket heuristics against a node.

    Optionally filter by ``severity`` (``"blocking"`` | ``"advisory"``)
    and ``phase`` (``"research"`` | ``"structure"`` | ``"compose"`` | ``"qa"`` | ``"export"``).
    """
    findings: list[Finding] = []
    for ticket in TICKETS:
        if severity is not None and ticket.severity != severity:
            continue
        if phase is not None and ticket.phase != phase:
            continue
        h = HEURISTICS.get(ticket.code)
        if h is None:
            continue
        status, detail, snippet = h(node)
        if status == "ok" and not detail:
            # Skip silent-OK to keep output dense on actionable items
            continue
        findings.append(
            Finding(
                ticket=ticket,
                status=status,
                detail=detail,
                snippet=snippet[:120],
            )
        )
    return findings


def blocking_failures(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.is_blocking_failure()]


__all__ = [
    "Finding",
    "HEURISTICS",
    "inspect_node",
    "blocking_failures",
]

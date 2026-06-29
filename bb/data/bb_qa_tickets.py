"""bb QA ticket taxonomy — 16 named quality concerns.

Source: OpenDraft (federicodeponte/opendraft) test_ticket001..016 — MIT licensed.
Back-port: 2026-06-29 by Demis for Brown Biotech.

A QA ticket is a named, diagnosable quality concern. Each ticket has:
- ``code``: stable ID (e.g. ``"bb-ticket-005-padding"``)
- ``name``: short name used in CLI output
- ``concern``: one-line description
- ``phase``: which pipeline phase this ticket surfaces in
    (research / structure / compose / qa / export — see bb-data-pipeline-phases)
- ``severity``: ``blocking`` (must fix before delivery) or ``advisory`` (note, don't block)
- ``bb_mapping``: the BB rubric criterion this ticket corresponds to
    (see ``brown-biotech-bb-rubric-scorer`` skill)

Used by:
- ``bb ticket <artifact>`` — score any markdown artifact against the taxonomy
- ``bb review`` — produce advisory ticket report (non-blocking)
- ``bb gate`` — produce blocking ticket report (must pass before delivery)
- ``brown-biotech-bb-rubric-scorer`` — multi-LLM judge ensemble wires ticket IDs into fail messages

Back-port source: ~/.hermes/reads/opendraft/SYNTHESIS.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["blocking", "advisory"]
Phase = Literal["research", "structure", "compose", "qa", "export"]


@dataclass(frozen=True)
class Ticket:
    code: str
    name: str
    concern: str
    phase: Phase
    severity: Severity
    bb_mapping: str
    detection_hint: str = ""


TICKETS: tuple[Ticket, ...] = (
    Ticket(
        code="bb-ticket-001-methodology",
        name="methodology",
        concern="Methodology rigor — appropriate study design, controls, sample size",
        phase="research",
        severity="blocking",
        bb_mapping="rubric:accuracy",
        detection_hint="study_design, cohort_size, control_group, randomization",
    ),
    Ticket(
        code="bb-ticket-002-analysis",
        name="analysis",
        concern="Analysis depth — statistical methods, sensitivity checks, effect sizes",
        phase="research",
        severity="blocking",
        bb_mapping="rubric:critical_analysis",
        detection_hint="p_value, effect_size, ci, sensitivity_analysis, multiple_testing",
    ),
    Ticket(
        code="bb-ticket-003-citation_mismatch",
        name="citation_mismatch",
        concern="Citation fidelity — DOI/PMID/author/year match the claim",
        phase="compose",
        severity="blocking",
        bb_mapping="rubric:citation_hygiene",
        detection_hint="doi:, pmid:, author names, year vs publication date",
    ),
    Ticket(
        code="bb-ticket-004-preprints",
        name="preprints",
        concern="Source provenance — prefer peer-reviewed over preprints",
        phase="research",
        severity="advisory",
        bb_mapping="rubric:citation_hygiene",
        detection_hint="bioRxiv, medRxiv, arXiv preprint without journal version",
    ),
    Ticket(
        code="bb-ticket-005-padding",
        name="padding",
        concern="No padding — every citation must earn its place (Quality > Quantity)",
        phase="compose",
        severity="blocking",
        bb_mapping="rubric:conciseness",
        detection_hint="unrelated fields, generic claims, weak relevance",
    ),
    Ticket(
        code="bb-ticket-006-contradictions",
        name="contradictions",
        concern="Internal consistency — no contradictions across sections",
        phase="qa",
        severity="blocking",
        bb_mapping="rubric:critical_analysis",
        detection_hint="cross-section narrative inconsistency, conflicting numbers",
    ),
    Ticket(
        code="bb-ticket-007-overconfident",
        name="overconfident",
        concern="Epistemic honesty — hedge where evidence is weak",
        phase="compose",
        severity="advisory",
        bb_mapping="rubric:critical_analysis",
        detection_hint="absolute claims without citation, no may/might/could",
    ),
    Ticket(
        code="bb-ticket-008-semantic_scholar",
        name="semantic_scholar",
        concern="Semantic Scholar integration check — required for cross-ref",
        phase="research",
        severity="advisory",
        bb_mapping="infra:citation_api",
        detection_hint="S2 API response missing, no DOI enrichment",
    ),
    Ticket(
        code="bb-ticket-009-precision",
        name="precision",
        concern="Numeric precision — values cited exactly, no rounding silently",
        phase="compose",
        severity="blocking",
        bb_mapping="rubric:accuracy",
        detection_hint="P=0.05 vs P=0.049, n=100 vs n≈100, percentage vs pp",
    ),
    Ticket(
        code="bb-ticket-010-repetition",
        name="repetition",
        concern="Conciseness — no redundant content across sections",
        phase="qa",
        severity="advisory",
        bb_mapping="rubric:conciseness",
        detection_hint="repeated paragraphs, redundant introductions per section",
    ),
    Ticket(
        code="bb-ticket-011-grammar",
        name="grammar",
        concern="Linguistic quality — grammar, spelling, punctuation",
        phase="export",
        severity="advisory",
        bb_mapping="rubric:clarity",
        detection_hint="spell-check fail, subject-verb mismatch, tense inconsistency",
    ),
    Ticket(
        code="bb-ticket-012-table_numbering",
        name="table_numbering",
        concern="Table/figure numbering consistent — no skipping or duplicates",
        phase="export",
        severity="advisory",
        bb_mapping="rubric:organization",
        detection_hint="Table 1, Table 2, ..., Table 2 (duplicate)",
    ),
    Ticket(
        code="bb-ticket-013-document_type",
        name="document_type",
        concern="Structural fit — format matches deliverable type (brief vs paper)",
        phase="structure",
        severity="advisory",
        bb_mapping="rubric:organization",
        detection_hint="paid-brief needs exec summary first, full paper needs abstract last",
    ),
    Ticket(
        code="bb-ticket-014-domain-terminology",
        name="domain-terminology",
        concern="Domain-specific terminology correctness — epistemics / genetics / ML terms accurate",
        phase="research",
        severity="advisory",
        bb_mapping="rubric:relevance",
        detection_hint="epigenetics, methylation calls, ATAC-seq, scRNA-seq, transformer/lora — domain-specific jargon used loosely",
    ),
    Ticket(
        code="bb-ticket-015-domain-coverage",
        name="domain-coverage",
        concern="Domain gap coverage — missing key paper types per domain (clinical/MR/ML)",
        phase="research",
        severity="advisory",
        bb_mapping="rubric:completeness",
        detection_hint="clinical domain needs RCT/MR; ML domain needs benchmarks; wet-lab needs replication studies",
    ),
    Ticket(
        code="bb-ticket-016-title_promise",
        name="title_promise",
        concern="Title-content fidelity — title promises what the body delivers",
        phase="structure",
        severity="blocking",
        bb_mapping="rubric:relevance",
        detection_hint="title says 'review of X' but body only covers Y",
    ),
)


# Convenience indices
TICKETS_BY_CODE: dict[str, Ticket] = {t.code: t for t in TICKETS}
TICKETS_BY_PHASE: dict[Phase, list[Ticket]] = {}
for t in TICKETS:
    TICKETS_BY_PHASE.setdefault(t.phase, []).append(t)

BLOCKING_TICKETS: tuple[Ticket, ...] = tuple(
    t for t in TICKETS if t.severity == "blocking"
)
ADVISORY_TICKETS: tuple[Ticket, ...] = tuple(
    t for t in TICKETS if t.severity == "advisory"
)


def get(code: str) -> Ticket:
    """Return ticket by code, raising KeyError with a clear message."""
    if code not in TICKETS_BY_CODE:
        raise KeyError(
            f"unknown ticket code: {code!r}. "
            f"Known: {sorted(TICKETS_BY_CODE)}"
        )
    return TICKETS_BY_CODE[code]


# Phases — also exported here for the 5-phase pipeline vocabulary reference.
# Source: OpenDraft docs/ARCHITECTURE.md — Research → Structure → Compose → QA → Export.
# Back-port 2026-06-29 for brown-biotech-paper-intake-workflow Step 1.5.
PIPELINE_PHASES: tuple[tuple[str, str], ...] = (
    ("research", "Discover sources, dedupe, build citation_database"),
    ("structure", "Design outline, apply academic style"),
    ("compose", "Write sections with verified citations (Crafter pattern)"),
    ("qa", "Cross-section coherence, voice, citation verification"),
    ("export", "Compile, format, deliver (PDF/DOCX/markdown)"),
)


__all__ = [
    "TICKETS",
    "TICKETS_BY_CODE",
    "TICKETS_BY_PHASE",
    "BLOCKING_TICKETS",
    "ADVISORY_TICKETS",
    "PIPELINE_PHASES",
    "Ticket",
    "Severity",
    "Phase",
    "get",
]

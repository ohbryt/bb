# bb — Brown Biotech CLI

Thin memory-ops wrapper over [bb-wiki](https://github.com/ohbryt/bb-wiki). Save, search, and forget research memory nodes from the terminal.

> Inspired by [cognee](https://github.com/topoteretes/cognee)'s `remember / recall / forget` API, adapted to BB's markdown-first Karpathy-LLM-Wiki pattern. No database — every node is a markdown file under your bb-wiki checkout.

## Install

```bash
# From source (v0.1.0 — not yet on PyPI)
git clone https://github.com/ohbryt/bb.git
cd bb
uv pip install -e .
# or: pip install -e .
```

## Quickstart

```bash
# Show wiki stats
bb status

# Save a memory
bb remember "KEAP1 NRF2 axis — NSCLC anti-PD1 resistance biomarker" \
    --tags keap1,nrf2,nsclc \
    --source "doi:10.1234/example"

# Search across the wiki
bb recall "KEAP1 NRF2"

# Filter to a section
bb recall "NAAA inhibitor" --section entities

# Remove a node (with confirmation)
bb forget 2026-06-27-keap1-nrf2-axis
```

## Commands

| Command | Description |
|---|---|
| `bb status` | Show node counts by section + recent activity (last 7 days) |
| `bb remember <text>` | Write a new memory node to `bb-wiki/<section>/<id>.md` |
| `bb recall <query>` | Keyword search across all nodes; score = title×3 + tags×2 + body×1 |
| `bb forget <id>` | Remove a node + update `index.md` + append to `log.md` (audit trail) |
| `bb ticket` | List the 16-ticket QA taxonomy (OpenDraft back-port, MIT) |
| `bb ticket <id>` | Heuristic ticket inspection of a bb-wiki node |
| `bb review <id>` | Advisory QA pass — OpenDraft Thread/Narrator style (always exits 0) |
| `bb gate <id>` | Blocking QA pass — OpenDraft Citation-Compiler style (exit 1 on fail) |

## bb-wiki integration

`bb` writes **directly into your bb-wiki checkout** as standard markdown files with YAML frontmatter that respects bb-wiki's [SCHEMA.md](https://github.com/ohbryt/bb-wiki/blob/main/SCHEMA.md):

| bb CLI `--section` | bb-wiki directory | frontmatter `type` |
|---|---|---|
| `raw` (default) | `bb-wiki/raw/` | `raw-note` |
| `concepts` | `bb-wiki/concepts/` | `concept` |
| `entities` | `bb-wiki/entities/` | `entity` |
| `queries` | `bb-wiki/queries/` | `query` |
| `comparisons` | `bb-wiki/comparisons/` | `comparison` |

Every `bb remember` writes a **4-섹션 판단 레이어 placeholder** (Source Quotes / My Interpretation / Open Questions / Contradictions) — fill it in manually to graduate from `raw-note` to a proper concept/entity page.

By default, `bb` looks for bb-wiki at `~/openclaw/workspace/bb-wiki`. Override with:

```bash
export WIKI_ROOT=/path/to/bb-wiki
# or pass --wiki-root / -w on every command
```

## Why this design

- **No database.** bb-wiki is git-tracked markdown. Adding a vector DB or REST server would break the "wiki you can grep / git diff / commit" promise.
- **Layer 1 (`raw/`) is the safe intake zone.** SCHEMA.md marks `raw/` as immutable, but in practice it already holds intermediate `.md` notes (e.g. `Agentic_Patterns_BrownBiotech_Mapping.md`). `bb remember` writes here by default — promote later by `git mv` to a proper concept/entity directory.
- **`index.md` updates are surgical.** `bb` adds a `## Recent (via bb CLI)` section so existing manual sections aren't disturbed. `bb forget` removes only that bullet, never reorders human edits.
- **`log.md` is append-only.** Every `remember`/`forget` is timestamped and recorded for audit, matching SCHEMA.md's append-only contract.

## Roadmap

- **v0.2.0** — `bb improve <id>`: LLM-assisted promotion of a raw note to a proper concept/entity page with filled 4-섹션 judgment layer. Opt-out via `BB_NO_LLM=1`.
- **v0.2.0** — `bb ticket`, `bb review`, `bb gate`: 16-ticket QA taxonomy (TICKET-001..016) back-ported from [OpenDraft](https://github.com/federicodeponte/opendraft) (MIT). 5-phase pipeline (research → structure → compose → qa → export). 10 blocking + 6 advisory tickets. Heuristics-only, no LLM cost.
- **v0.3.0** — `bb` subcommands for PRISM, agent-skill-pack, and other BB ops (wiki lint, ingest).
- **v0.4.0** — Optional SQLite + FTS5 backend for sub-millisecond recall on large wikis (default stays markdown-only).

### Ticket example

```bash
# List the 16-ticket taxonomy (grouped by 5-phase pipeline)
bb ticket

# Inspect a specific node — runs heuristics per ticket
bb ticket 2026-06-29-opendraft-back-port

# Filter to one phase
bb ticket --phase compose

# Advisory QA pass (always exits 0 — never blocks)
bb review 2026-06-29-opendraft-back-port

# Blocking QA pass (exit 1 on any blocking fail — use pre-publish / CI)
bb gate 2026-06-29-opendraft-back-port
```

Tickets source-of-truth: `bb/data/bb_qa_tickets.py`. Back-port notes: `~/.hermes/reads/opendraft/SYNTHESIS.md`.

## License

Apache-2.0 — same as bb-wiki and cognee.
"""Unit tests for bb.memory, bb.frontmatter, bb.wiki."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from typer.testing import CliRunner

from bb.cli import app
from bb.frontmatter import join, read, split
from bb.memory import (
    Node,
    SECTION_TO_TYPE,
    node_id_for,
    slugify,
    today_kst,
)
from bb.wiki import (
    append_to_index,
    append_to_log,
    load_all_nodes,
    node_path,
    remove_from_index,
    remove_node,
    search,
    write_node,
)


# --- pure helpers ----------------------------------------------------------


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"
    assert slugify("KEAP1 NRF2 axis!") == "keap1-nrf2-axis"


def test_slugify_edge_cases():
    assert slugify("  spaces  ") == "spaces"
    assert slugify("") == "untitled"
    assert slugify("!!!") == "untitled"
    assert slugify("multi   dash   collapse") == "multi-dash-collapse"


def test_node_id_for_format():
    nid = node_id_for("KEAP1 NRF2", created=dt.date(2026, 6, 27))
    assert nid == "2026-06-27-keap1-nrf2"


def test_section_to_type_mapping():
    assert SECTION_TO_TYPE["raw"] == "raw-note"
    assert SECTION_TO_TYPE["concepts"] == "concept"
    assert SECTION_TO_TYPE["entities"] == "entity"
    assert SECTION_TO_TYPE["queries"] == "query"
    assert SECTION_TO_TYPE["comparisons"] == "comparison"


# --- frontmatter ------------------------------------------------------------


def test_frontmatter_split_join_roundtrip(tmp_path):
    p = tmp_path / "test.md"
    p.write_text(
        "---\ntitle: t\ntags: [a, b]\n---\n\nbody text\n",
        encoding="utf-8",
    )
    fm, body = read(p)
    assert fm == {"title": "t", "tags": ["a", "b"]}
    assert body.strip() == "body text"
    out = join(fm, body)
    assert "title: t" in out
    assert "body text" in out


def test_frontmatter_no_fm(tmp_path):
    p = tmp_path / "nofm.md"
    p.write_text("just body\n", encoding="utf-8")
    fm, body = read(p)
    assert fm == {}
    assert body == "just body\n"


def test_frontmatter_korean_unicode(tmp_path):
    p = tmp_path / "kr.md"
    p.write_text(
        "---\ntitle: 한글 제목\ntags: [항암, 표적치료]\n---\n\n본문\n",
        encoding="utf-8",
    )
    fm, body = read(p)
    assert fm["title"] == "한글 제목"
    assert fm["tags"] == ["항암", "표적치료"]


# --- node loading + search --------------------------------------------------


def test_load_all_nodes(tmp_wiki):
    nodes = load_all_nodes(tmp_wiki)
    assert len(nodes) == 1
    n = nodes[0]
    assert n.section == "entities"
    assert n.id == "naaa-lead"
    assert "NAAA" in n.title


def test_search_keyword_match(tmp_wiki):
    results = search(tmp_wiki, "NAAA", top=5)
    assert len(results) >= 1
    node, score, snippet = results[0]
    assert node.id == "naaa-lead"
    assert score > 0


def test_search_no_match(tmp_wiki):
    results = search(tmp_wiki, "xyzzy_no_match_query")
    assert results == []


def test_search_section_filter(tmp_wiki):
    # Add a raw note that mentions NAAA too
    raw_path = tmp_wiki / "raw" / "2026-06-27-test.md"
    raw_path.write_text(
        "---\ntitle: test\ncreated: 2026-06-27\nupdated: 2026-06-27\n"
        "type: raw-note\ntags: []\nsources: []\n---\n\nrandom NAAA text\n",
        encoding="utf-8",
    )
    entities_only = search(tmp_wiki, "NAAA", section="entities")
    raw_only = search(tmp_wiki, "random", section="raw")
    assert all(n.section == "entities" for n, _, _ in entities_only)
    assert all(n.section == "raw" for n, _, _ in raw_only)


def test_search_ranking(tmp_wiki):
    # Title match should outrank body match
    body_only = tmp_wiki / "raw" / "2026-06-27-body-only.md"
    body_only.write_text(
        "---\ntitle: generic\ncreated: 2026-06-27\nupdated: 2026-06-27\n"
        "type: raw-note\ntags: []\nsources: []\n---\n\nNAAA mentioned in body only.\n",
        encoding="utf-8",
    )
    results = search(tmp_wiki, "NAAA")
    # First result should be naaa-lead (title match ×3)
    assert results[0][0].id == "naaa-lead"


# --- node write / remove ----------------------------------------------------


def test_write_node(tmp_wiki):
    nid = "2026-06-27-synthetic"
    p = node_path(tmp_wiki, nid, "raw")
    node = Node(
        id=nid,
        title="synthetic test",
        created=dt.date(2026, 6, 27),
        updated=dt.date(2026, 6, 27),
        type="raw-note",
        tags=["test"],
        sources=[],
        body="## 4-섹션 판단 레이어\n\nbody content",
        path=p,
        section="raw",
    )
    write_node(tmp_wiki, node)
    assert p.exists()
    loaded = Node.from_path(p, tmp_wiki)
    assert loaded.title == "synthetic test"
    assert loaded.tags == ["test"]
    assert loaded.section == "raw"


def test_remove_node(tmp_wiki):
    nid = "2026-06-27-remove-me"
    p = node_path(tmp_wiki, nid, "raw")
    node = Node(
        id=nid,
        title="remove me",
        created=dt.date(2026, 6, 27),
        updated=dt.date(2026, 6, 27),
        type="raw-note",
        tags=[],
        sources=[],
        body="body",
        path=p,
        section="raw",
    )
    write_node(tmp_wiki, node)
    assert p.exists()
    assert remove_node(tmp_wiki, node) is True
    assert not p.exists()
    # Second call returns False
    assert remove_node(tmp_wiki, node) is False


# --- index.md / log.md ------------------------------------------------------


def test_index_append_idempotent(tmp_wiki):
    nid = "2026-06-27-synthetic"
    p = node_path(tmp_wiki, nid, "raw")
    node = Node(
        id=nid,
        title="synthetic test",
        created=dt.date(2026, 6, 27),
        updated=dt.date(2026, 6, 27),
        type="raw-note",
        tags=[],
        sources=[],
        body="body",
        path=p,
        section="raw",
    )
    append_to_index(tmp_wiki, node)
    text = (tmp_wiki / "index.md").read_text()
    assert "synthetic test" in text
    assert "Recent (via bb CLI)" in text
    # Second call is a no-op
    append_to_index(tmp_wiki, node)
    text2 = (tmp_wiki / "index.md").read_text()
    assert text == text2


def test_index_remove(tmp_wiki):
    nid = "2026-06-27-synthetic"
    p = node_path(tmp_wiki, nid, "raw")
    node = Node(
        id=nid,
        title="synthetic test",
        created=dt.date(2026, 6, 27),
        updated=dt.date(2026, 6, 27),
        type="raw-note",
        tags=[],
        sources=[],
        body="body",
        path=p,
        section="raw",
    )
    append_to_index(tmp_wiki, node)
    remove_from_index(tmp_wiki, node)
    text = (tmp_wiki / "index.md").read_text()
    assert "synthetic test" not in text


def test_log_append(tmp_wiki):
    nid = "2026-06-27-log-test"
    p = node_path(tmp_wiki, nid, "raw")
    node = Node(
        id=nid,
        title="log test",
        created=dt.date(2026, 6, 27),
        updated=dt.date(2026, 6, 27),
        type="raw-note",
        tags=[],
        sources=[],
        body="body",
        path=p,
        section="raw",
    )
    append_to_log(tmp_wiki, "remember", node)
    text = (tmp_wiki / "log.md").read_text()
    assert "remember" in text
    assert nid in text


# --- CLI --------------------------------------------------------------------


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "bb" in result.stdout
    assert "0.1.0" in result.stdout


def test_cli_status(tmp_wiki, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_wiki))
    runner = CliRunner()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "entities" in result.stdout


def test_cli_recall(tmp_wiki, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_wiki))
    runner = CliRunner()
    result = runner.invoke(app, ["recall", "NAAA"])
    assert result.exit_code == 0
    assert "naaa-lead" in result.stdout


def test_cli_recall_no_match(tmp_wiki, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_wiki))
    runner = CliRunner()
    result = runner.invoke(app, ["recall", "xyzzy_no_match_query"])
    assert result.exit_code == 0
    assert "no matches" in result.stdout


def test_cli_remember_then_forget(tmp_wiki, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_wiki))
    runner = CliRunner()
    r1 = runner.invoke(
        app, ["remember", "synthetic test note", "-t", "test,synthetic"]
    )
    assert r1.exit_code == 0, r1.stdout
    files = list((tmp_wiki / "raw").glob("2026-06-2*-synthetic-test-note.md"))
    assert len(files) == 1
    nid = files[0].stem
    # Recall should find it
    r2 = runner.invoke(app, ["recall", "synthetic"])
    assert r2.exit_code == 0
    assert nid in r2.stdout
    # Forget with --yes
    r3 = runner.invoke(app, ["forget", nid, "-y"])
    assert r3.exit_code == 0
    assert not files[0].exists()
    # Index should no longer reference it
    index_text = (tmp_wiki / "index.md").read_text()
    assert "synthetic test note" not in index_text


def test_cli_remember_duplicate_errors(tmp_wiki, monkeypatch):
    monkeypatch.setenv("WIKI_ROOT", str(tmp_wiki))
    runner = CliRunner()
    r1 = runner.invoke(app, ["remember", "dup test xyzzy_unique"])
    assert r1.exit_code == 0
    r2 = runner.invoke(app, ["remember", "dup test xyzzy_unique"])
    assert r2.exit_code == 1
    assert "already exists" in r2.stdout or "already exists" in (r2.stderr or "")
    # Cleanup
    files = list((tmp_wiki / "raw").glob("*xyzzy_unique*.md"))
    for f in files:
        f.unlink()


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "remember" in result.stdout
    assert "recall" in result.stdout
    assert "forget" in result.stdout
    assert "status" in result.stdout
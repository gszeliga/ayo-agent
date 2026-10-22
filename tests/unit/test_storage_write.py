import os
from pathlib import Path

import pytest

from ayo_copilot.ingestion.storage import InvalidInputError, markdown_path, write_markdown_atomic

TEXT = "# Guía de inspección\n\nRevisar la señal de presión ¿antes o después?\n"


def test_markdown_path_layout(tmp_path: Path) -> None:
    assert markdown_path(tmp_path, "acme", "upload-abc123def456") == (
        tmp_path / "acme" / "upload" / "upload-abc123def456.md"
    )


def test_writes_utf8_file_in_tenant_directory(tmp_path: Path) -> None:
    path = write_markdown_atomic(tmp_path, "acme", "upload-abc123def456", TEXT)

    assert path == tmp_path / "acme" / "upload" / "upload-abc123def456.md"
    assert path.read_text(encoding="utf-8") == TEXT


def test_overwrites_existing_file_and_leaves_no_temp_files(tmp_path: Path) -> None:
    write_markdown_atomic(tmp_path, "acme", "upload-abc123def456", "old")
    path = write_markdown_atomic(tmp_path, "acme", "upload-abc123def456", TEXT)

    assert path.read_text(encoding="utf-8") == TEXT
    assert sorted(p.name for p in path.parent.iterdir()) == ["upload-abc123def456.md"]


def test_failed_write_keeps_previous_file_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_markdown_atomic(tmp_path, "acme", "upload-abc123def456", "previous")

    def failing_replace(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError, match="disk full"):
        write_markdown_atomic(tmp_path, "acme", "upload-abc123def456", TEXT)

    assert path.read_text(encoding="utf-8") == "previous"
    assert sorted(p.name for p in path.parent.iterdir()) == ["upload-abc123def456.md"]


@pytest.mark.parametrize(
    ("tenant", "doc_id"),
    [("../etc", "upload-abc123def456"), ("acme", "../../x"), ("acme", "a/b")],
)
def test_rejects_paths_outside_knowledge_dir(tmp_path: Path, tenant: str, doc_id: str) -> None:
    with pytest.raises(InvalidInputError):
        write_markdown_atomic(tmp_path, tenant, doc_id, TEXT)

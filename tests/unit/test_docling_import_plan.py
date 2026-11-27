"""Planning a docling import: what is scanned, where the Markdown goes, what is skipped."""

import os
from pathlib import Path

import pytest

from ayo_copilot.docling_import.plan import (
    OFFICE_HINT,
    Action,
    Item,
    Plan,
    PlanError,
    Skipped,
    SkipReason,
    plan_import,
)


def touch(path: Path, *, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_a_single_file_goes_next_to_its_source(tmp_path: Path) -> None:
    pdf = touch(tmp_path / "PRO-014 Control de sellado.pdf")

    assert plan_import(pdf).items == [
        Item(pdf, tmp_path / "PRO-014 Control de sellado.md", Action.CONVERT)
    ]


def test_a_single_file_goes_into_out_dir(tmp_path: Path) -> None:
    docx = touch(tmp_path / "docs" / "manual-extrusora.docx")
    out = tmp_path / "md"

    assert plan_import(docx, out_dir=out).items == [
        Item(docx, out / "manual-extrusora.md", Action.CONVERT)
    ]


def test_a_single_markdown_file_is_taken_as_is(tmp_path: Path) -> None:
    md = touch(tmp_path / "notas.md")

    assert plan_import(md).items == [Item(md, md, Action.AS_IS)]


def test_an_unsupported_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="unsupported file type"):
        plan_import(touch(tmp_path / "datos.zip"))


def test_a_missing_path_is_refused(tmp_path: Path) -> None:
    with pytest.raises(PlanError, match="no such file or folder"):
        plan_import(tmp_path / "nada")


def test_a_folder_is_scanned_flat_by_default(tmp_path: Path) -> None:
    pdf = touch(tmp_path / "a.pdf")
    md = touch(tmp_path / "b.md")
    zip_file = touch(tmp_path / "c.zip")
    touch(tmp_path / ".oculto.pdf")
    touch(tmp_path / "sub" / "d.pdf")

    plan = plan_import(tmp_path)

    assert plan.items == [
        Item(pdf, tmp_path / "a.md", Action.CONVERT),
        Item(md, md, Action.AS_IS),
    ]
    assert plan.skipped == [Skipped(zip_file, SkipReason.UNSUPPORTED)]


def test_recursive_scans_subfolders_but_not_hidden_ones(tmp_path: Path) -> None:
    top = touch(tmp_path / "a.pdf")
    deep = touch(tmp_path / "sub" / "deeper" / "d.PPTX")
    touch(tmp_path / ".git" / "e.pdf")

    assert plan_import(tmp_path, recursive=True).items == [
        Item(top, tmp_path / "a.md", Action.CONVERT),
        Item(deep, tmp_path / "sub" / "deeper" / "d.md", Action.CONVERT),
    ]


def test_out_dir_keeps_subfolders_and_is_not_scanned(tmp_path: Path) -> None:
    src = tmp_path / "src"
    deep = touch(src / "sub" / "d.pdf")
    out = src / "md"
    touch(out / "old.pdf")

    assert plan_import(src, out_dir=out, recursive=True).items == [
        Item(deep, out / "sub" / "d.md", Action.CONVERT)
    ]


def test_a_markdown_newer_than_its_source_is_up_to_date(tmp_path: Path) -> None:
    pdf = touch(tmp_path / "a.pdf", mtime=1_000)
    md = touch(tmp_path / "a.md", mtime=2_000)

    assert plan_import(tmp_path).items == [Item(pdf, md, Action.UP_TO_DATE)]
    assert plan_import(tmp_path, reconvert=True).items == [Item(pdf, md, Action.CONVERT)]


def test_a_markdown_older_than_its_source_is_converted_again(tmp_path: Path) -> None:
    pdf = touch(tmp_path / "a.pdf", mtime=2_000)
    md = touch(tmp_path / "a.md", mtime=1_000)

    assert plan_import(tmp_path).items == [Item(pdf, md, Action.CONVERT)]


def test_two_sources_writing_the_same_markdown_are_refused(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "a.docx")

    with pytest.raises(PlanError, match="same Markdown file") as raised:
        plan_import(tmp_path)

    assert "a.pdf" in str(raised.value) and "a.docx" in str(raised.value)


def test_out_dir_clash_across_folders_only_when_paths_match(tmp_path: Path) -> None:
    touch(tmp_path / "x" / "a.pdf")
    touch(tmp_path / "y" / "a.pdf")

    items = plan_import(tmp_path, out_dir=tmp_path / "md", recursive=True).items

    assert [item.markdown for item in items] == [
        tmp_path / "md" / "x" / "a.md",
        tmp_path / "md" / "y" / "a.md",
    ]


def test_unsupported_files_are_skipped_sorted_and_hidden_ones_never_listed(
    tmp_path: Path,
) -> None:
    pdf = touch(tmp_path / "a.pdf")
    ppt = touch(tmp_path / "sub" / "PDCA ESP 2012.PPT")
    bare = touch(tmp_path / "LEEME")
    touch(tmp_path / ".a.md.1234.tmp")
    touch(tmp_path / ".cache" / "x.bin")

    assert plan_import(tmp_path, recursive=True) == Plan(
        [Item(pdf, tmp_path / "a.md", Action.CONVERT)],
        [
            Skipped(bare, SkipReason.UNSUPPORTED),
            Skipped(ppt, SkipReason.NO_OFFICE_CONVERTER),
        ],
    )


def test_a_single_file_has_nothing_skipped(tmp_path: Path) -> None:
    assert plan_import(touch(tmp_path / "a.pdf")).skipped == []


def test_old_office_files_are_sources_with_an_office_converter(tmp_path: Path) -> None:
    ppt = touch(tmp_path / "PDCA ESP 2012.ppt")
    doc = touch(tmp_path / "sub" / "Ficha.DOC")
    xls = touch(tmp_path / "datos.xls")

    plan = plan_import(tmp_path, recursive=True, legacy=True)

    assert plan == Plan(
        [
            Item(ppt, tmp_path / "PDCA ESP 2012.md", Action.CONVERT),
            Item(xls, tmp_path / "datos.md", Action.CONVERT),
            Item(doc, tmp_path / "sub" / "Ficha.md", Action.CONVERT),
        ]
    )


def test_an_old_office_file_is_up_to_date_against_the_original(tmp_path: Path) -> None:
    ppt = touch(tmp_path / "a.ppt", mtime=1_000)
    md = touch(tmp_path / "a.md", mtime=2_000)

    assert plan_import(tmp_path, legacy=True).items == [Item(ppt, md, Action.UP_TO_DATE)]


@pytest.mark.parametrize("legacy", [True, False])
def test_an_old_file_next_to_its_newer_copy_is_skipped(tmp_path: Path, legacy: bool) -> None:
    ppt = touch(tmp_path / "PDCA.ppt")
    pptx = touch(tmp_path / "PDCA.PPTX")

    assert plan_import(tmp_path, legacy=legacy) == Plan(
        [Item(pptx, tmp_path / "PDCA.md", Action.CONVERT)],
        [Skipped(ppt, SkipReason.NEWER_FORMAT)],
    )


def test_an_old_file_next_to_a_pdf_of_the_same_name_is_a_clash(tmp_path: Path) -> None:
    touch(tmp_path / "Ficha.pdf")
    touch(tmp_path / "Ficha.doc")

    with pytest.raises(PlanError, match="same Markdown file"):
        plan_import(tmp_path, legacy=True)


def test_a_single_old_file_needs_an_office_converter(tmp_path: Path) -> None:
    ppt = touch(tmp_path / "a.ppt")

    with pytest.raises(PlanError, match="install OnlyOffice or LibreOffice") as raised:
        plan_import(ppt)

    assert str(raised.value) == f"{ppt}: {OFFICE_HINT}"
    assert plan_import(ppt, legacy=True).items == [Item(ppt, tmp_path / "a.md", Action.CONVERT)]

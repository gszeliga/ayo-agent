"""`docling-import-files --no-upload`: conversion with a fake converter, lines, exit codes."""

import io
import logging
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from ayo_copilot.docling_import import converter as converter_module
from ayo_copilot.docling_import.cli import main
from ayo_copilot.docling_import.converter import (
    INSTALL_HINT,
    ConverterUnavailableError,
    DoclingConverter,
    write_markdown,
)

SECRET_TEXT = "Contenido confidencial del procedimiento"


class FakeConverter:
    def __init__(self, failing: set[str] | None = None, empty: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.empty = empty or set()
        self.calls: list[Path] = []

    def to_markdown(self, source: Path) -> str:
        self.calls.append(source)
        if source.name in self.failing:
            raise ValueError(f"cannot parse page 3\n{SECRET_TEXT}")
        if source.name in self.empty:
            return "  \n"
        return f"# {source.stem}\n\n{SECRET_TEXT}"


def run(*argv: str, converter: FakeConverter | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    fake = converter or FakeConverter()
    code = main([*argv, "--no-upload"], make_converter=lambda: fake, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def touch(path: Path, *, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_converts_a_folder_and_writes_the_markdown(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "b.docx")
    out_dir = tmp_path / "md"

    code, out, err = run(str(tmp_path), "--out", str(out_dir))

    assert code == 0 and err == ""
    assert (out_dir / "a.md").read_text(encoding="utf-8") == f"# a\n\n{SECRET_TEXT}\n"
    assert (out_dir / "b.md").is_file()
    assert f"converted   {tmp_path / 'a.pdf'} -> {out_dir / 'a.md'}" in out
    assert out.splitlines()[-1] == "2 documents: 2 converted"
    assert SECRET_TEXT not in out


def test_up_to_date_and_markdown_files_are_not_converted(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf", mtime=1_000)
    touch(tmp_path / "a.md", mtime=2_000)
    touch(tmp_path / "notas.md")
    fake = FakeConverter()

    code, out, _ = run(str(tmp_path), converter=fake)

    assert code == 0 and fake.calls == []
    assert f"up to date  {tmp_path / 'a.md'}" in out
    assert f"as is       {tmp_path / 'notas.md'}" in out
    assert out.splitlines()[-1] == "2 documents: 1 up to date, 1 as is"


def test_no_converter_is_built_when_nothing_needs_converting(tmp_path: Path) -> None:
    touch(tmp_path / "notas.md")

    def unavailable() -> FakeConverter:
        raise ConverterUnavailableError(INSTALL_HINT)

    code = main([str(tmp_path), "--no-upload"], make_converter=unavailable, stdout=io.StringIO())

    assert code == 0


def test_a_failed_file_does_not_stop_the_run_and_leaks_no_content(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "b.pdf")
    touch(tmp_path / "c.pdf")

    code, out, _ = run(str(tmp_path), converter=FakeConverter(failing={"a.pdf"}, empty={"b.pdf"}))

    assert code == 1
    assert f"failed      {tmp_path / 'a.pdf'} (ValueError: cannot parse page 3)" in out
    assert f"failed      {tmp_path / 'b.pdf'} (EmptyMarkdownError: no text extracted)" in out
    assert not (tmp_path / "a.md").exists() and not (tmp_path / "b.md").exists()
    assert (tmp_path / "c.md").is_file()
    assert out.splitlines()[-1] == "3 documents: 1 converted, 2 failed"
    assert SECRET_TEXT not in out


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    fake = FakeConverter()

    code, out, _ = run(str(tmp_path), "--dry-run", converter=fake)

    assert code == 0 and fake.calls == []
    assert out == f"would convert {tmp_path / 'a.pdf'} -> {tmp_path / 'a.md'}\n"
    assert not (tmp_path / "a.md").exists()


def test_reconvert_converts_an_up_to_date_file(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf", mtime=1_000)
    touch(tmp_path / "a.md", mtime=2_000)
    fake = FakeConverter()

    code, _, _ = run(str(tmp_path), "--reconvert", converter=fake)

    assert code == 0 and fake.calls == [tmp_path / "a.pdf"]


def test_a_missing_path_exits_2(tmp_path: Path) -> None:
    code, out, err = run(str(tmp_path / "nada"))

    assert code == 2 and out == "" and "no such file or folder" in err


def test_a_clash_exits_2_before_converting(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "a.docx")
    fake = FakeConverter()

    code, out, err = run(str(tmp_path), converter=fake)

    assert code == 2 and out == "" and "same Markdown file" in err
    assert fake.calls == []


def test_a_folder_without_documents_exits_2_and_lists_what_it_skipped(tmp_path: Path) -> None:
    touch(tmp_path / "x.zip")

    code, out, err = run(str(tmp_path))

    assert code == 2 and "no documents found" in err
    assert out == f"skipped     {tmp_path / 'x.zip'} (unsupported: .zip)\n"


def test_each_conversion_announces_itself_before_it_starts(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "b.pdf", mtime=1_000)
    touch(tmp_path / "b.md", mtime=2_000)
    touch(tmp_path / "c.docx")
    touch(tmp_path / "notas.md")

    code, out, _ = run(str(tmp_path))

    assert code == 0
    assert out.splitlines() == [
        f"converting  (1/2) {tmp_path / 'a.pdf'} …",
        f"converted   {tmp_path / 'a.pdf'} -> {tmp_path / 'a.md'}",
        f"up to date  {tmp_path / 'b.md'}",
        f"converting  (2/2) {tmp_path / 'c.docx'} …",
        f"converted   {tmp_path / 'c.docx'} -> {tmp_path / 'c.md'}",
        f"as is       {tmp_path / 'notas.md'}",
        "4 documents: 2 converted, 1 up to date, 1 as is",
    ]


def test_a_failed_conversion_also_announced_itself(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")

    _, out, _ = run(str(tmp_path), converter=FakeConverter(failing={"a.pdf"}))

    assert out.splitlines()[:2] == [
        f"converting  (1/1) {tmp_path / 'a.pdf'} …",
        f"failed      {tmp_path / 'a.pdf'} (ValueError: cannot parse page 3)",
    ]


def test_skipped_files_come_first_and_are_counted(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "PDCA.ppt")
    touch(tmp_path / "LEEME")

    code, out, _ = run(str(tmp_path))

    lines = out.splitlines()
    assert code == 0
    assert lines[:2] == [
        f"skipped     {tmp_path / 'LEEME'} (unsupported: no extension)",
        f"skipped     {tmp_path / 'PDCA.ppt'} (unsupported: .ppt)",
    ]
    assert lines[-1] == "1 document: 1 converted; 2 skipped"


def test_dry_run_lists_skipped_files(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "PDCA.PPT")

    code, out, _ = run(str(tmp_path), "--dry-run")

    assert code == 0
    assert out.splitlines() == [
        f"skipped     {tmp_path / 'PDCA.PPT'} (unsupported: .ppt)",
        f"would convert {tmp_path / 'a.pdf'} -> {tmp_path / 'a.md'}",
    ]


@pytest.fixture
def root_logger_level() -> Iterator[None]:
    root = logging.getLogger()
    level = root.level
    yield
    root.setLevel(level)


@pytest.mark.usefixtures("root_logger_level")
@pytest.mark.parametrize(("flag", "expected"), [("-v", logging.INFO), ("--verbose", logging.INFO)])
def test_verbose_shows_info_logs(tmp_path: Path, flag: str, expected: int) -> None:
    touch(tmp_path / "notas.md")
    logging.getLogger().setLevel(logging.WARNING)

    run(str(tmp_path), flag)

    assert logging.getLogger().level == expected


@pytest.mark.usefixtures("root_logger_level")
def test_without_verbose_the_log_level_is_left_alone(tmp_path: Path) -> None:
    touch(tmp_path / "notas.md")
    logging.getLogger().setLevel(logging.WARNING)

    run(str(tmp_path))

    assert logging.getLogger().level == logging.WARNING


class FlushRecorder(io.StringIO):
    """Records what had been flushed when each line was written."""

    def __init__(self) -> None:
        super().__init__()
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1
        super().flush()


def test_every_line_is_flushed(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "x.zip")
    out = FlushRecorder()

    main([str(tmp_path), "--no-upload"], make_converter=FakeConverter, stdout=out)

    assert out.flushes == len(out.getvalue().splitlines()) == 4


def test_missing_docling_exits_2_with_the_install_hint(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")

    def unavailable() -> FakeConverter:
        raise ConverterUnavailableError(INSTALL_HINT)

    err = io.StringIO()
    code = main(
        [str(tmp_path), "--no-upload"],
        make_converter=unavailable,
        stdout=io.StringIO(),
        stderr=err,
    )

    assert code == 2
    assert "uv sync --group convert" in err.getvalue()


def test_docling_converter_reports_a_missing_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "docling", None)
    monkeypatch.setitem(sys.modules, "docling.document_converter", None)

    with pytest.raises(ConverterUnavailableError, match="uv sync --group convert"):
        DoclingConverter()


def test_write_markdown_is_utf8_with_a_final_newline(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "a.md"

    write_markdown(target, "# Título\n\nlínea")

    assert target.read_bytes() == "# Título\n\nlínea\n".encode()
    assert [p.name for p in target.parent.iterdir()] == ["a.md"]


def test_write_markdown_keeps_the_old_file_when_writing_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "a.md"
    target.write_text("old", encoding="utf-8")

    def boom(src: str, dst: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(converter_module.os, "replace", boom)

    with pytest.raises(OSError):
        write_markdown(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["a.md"]

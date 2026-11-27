"""Old Office formats: the x2t and soffice commands, their checks, finding a converter."""

import subprocess
from pathlib import Path

import pytest

from ayo_copilot.docling_import import office as office_module
from ayo_copilot.docling_import.office import (
    TIMEOUT_SECONDS,
    OfficeConversionError,
    OfficeConverterUnavailableError,
    SofficeConverter,
    UpgradingConverter,
    X2tConverter,
    find_office_converter,
    run_quietly,
)

X2T = Path("/opt/onlyoffice/desktopeditors/converter/x2t")


class FakeRunner:
    """Records each command; writes `output` (if any) and returns `status`."""

    def __init__(self, output: Path | None, *, status: int = 0, data: bytes = b"PK") -> None:
        self.output, self.status, self.data = output, status, data
        self.calls: list[tuple[list[str], dict[str, str] | None, float]] = []

    def __call__(self, args: list[str], *, env: dict[str, str] | None, timeout: float) -> int:
        self.calls.append((args, env, timeout))
        if self.output is not None:
            self.output.write_bytes(self.data)
        return self.status


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_x2t_converts_into_the_folder_with_its_libraries(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "PDCA ESP 2012.PPT"
    target = tmp_path / "PDCA ESP 2012.pptx"
    runner = FakeRunner(target)

    result = X2tConverter(X2T, runner=runner).upgrade(source, tmp_path)

    assert result == target
    ((args, env, timeout),) = runner.calls
    assert args == [str(X2T), str(source), str(target)]
    assert env is not None and env["LD_LIBRARY_PATH"] == str(X2T.parent)
    assert timeout == TIMEOUT_SECONDS


@pytest.mark.parametrize(("suffix", "new"), [(".doc", ".docx"), (".xls", ".xlsx")])
def test_x2t_picks_the_newer_format(tmp_path: Path, suffix: str, new: str) -> None:
    runner = FakeRunner(tmp_path / f"a{new}")

    assert X2tConverter(X2T, runner=runner).upgrade(tmp_path / f"a{suffix}", tmp_path).suffix == new


def test_soffice_uses_a_throwaway_profile_in_the_folder(tmp_path: Path) -> None:
    soffice = Path("/usr/bin/soffice")
    source = tmp_path / "docs" / "Ficha.doc"
    runner = FakeRunner(tmp_path / "Ficha.docx")

    result = SofficeConverter(soffice, runner=runner).upgrade(source, tmp_path)

    assert result == tmp_path / "Ficha.docx"
    ((args, env, timeout),) = runner.calls
    profile = (tmp_path / ".soffice-profile").resolve().as_uri()
    assert args == [
        str(soffice),
        f"-env:UserInstallation={profile}",
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(tmp_path),
        str(source),
    ]
    assert env is None and timeout == TIMEOUT_SECONDS


def test_a_non_zero_exit_fails_the_file(tmp_path: Path) -> None:
    runner = FakeRunner(tmp_path / "a.pptx", status=1)

    with pytest.raises(OfficeConversionError, match=r"^x2t exit 1$"):
        X2tConverter(X2T, runner=runner).upgrade(tmp_path / "a.ppt", tmp_path)


@pytest.mark.parametrize("written", [False, True])
def test_a_missing_or_empty_output_fails_the_file(tmp_path: Path, written: bool) -> None:
    runner = FakeRunner(tmp_path / "a.pptx" if written else None, data=b"")

    with pytest.raises(OfficeConversionError, match=r"^soffice wrote no output$"):
        SofficeConverter(Path("/usr/bin/soffice"), runner=runner).upgrade(
            tmp_path / "a.ppt", tmp_path
        )


def test_run_quietly_discards_output_and_returns_the_status(
    capfd: pytest.CaptureFixture[str],
) -> None:
    script = "import sys; print('Contenido confidencial'); sys.exit(3)"

    status = run_quietly(["python3", "-c", script], env=None, timeout=10)

    assert status == 3
    assert capfd.readouterr() == ("", "")


def test_run_quietly_turns_a_timeout_into_a_conversion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def slow(args: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(args, 300)

    monkeypatch.setattr(office_module.subprocess, "run", slow)

    with pytest.raises(OfficeConversionError, match=r"^x2t timed out after 300 s$"):
        run_quietly([str(X2T), "a.ppt", "a.pptx"], env=None, timeout=300)


def test_find_prefers_the_flag_and_tells_x2t_by_its_name(tmp_path: Path) -> None:
    x2t = executable(tmp_path / "x2t")
    soffice = executable(tmp_path / "soffice")
    nowhere = tmp_path / "none" / "x2t"

    assert find_office_converter(x2t, x2t_path=nowhere) == X2tConverter(x2t)
    assert find_office_converter(soffice, x2t_path=nowhere) == SofficeConverter(soffice)


@pytest.mark.parametrize("make", ["missing", "not executable"])
def test_find_refuses_an_unusable_flag(tmp_path: Path, make: str) -> None:
    path = tmp_path / "x2t"
    if make == "not executable":
        path.write_text("")

    with pytest.raises(OfficeConverterUnavailableError, match="not an executable file"):
        find_office_converter(path)


def test_find_uses_onlyoffice_then_libreoffice_then_nothing(tmp_path: Path) -> None:
    x2t = executable(tmp_path / "onlyoffice" / "x2t")
    found = {"libreoffice": "/usr/bin/libreoffice"}

    def which(name: str) -> str | None:
        return found.get(name)

    def no_which(name: str) -> None:
        return None

    assert find_office_converter(x2t_path=x2t, which=which) == X2tConverter(x2t)
    missing = tmp_path / "nada" / "x2t"
    assert find_office_converter(x2t_path=missing, which=which) == SofficeConverter(
        Path("/usr/bin/libreoffice")
    )
    assert find_office_converter(x2t_path=missing, which=no_which) is None


class RecordingConverter:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, bool]] = []

    def to_markdown(self, source: Path) -> str:
        self.calls.append((source, source.is_file()))
        return "# Ficha"


class FakeOffice:
    name = "x2t"
    path = X2T

    def upgrade(self, source: Path, out_dir: Path) -> Path:
        target = out_dir / (source.stem + ".docx")
        target.write_bytes(b"PK")
        return target


def test_upgrading_converter_upgrades_old_files_only(tmp_path: Path) -> None:
    inner = RecordingConverter()
    converter = UpgradingConverter(inner, FakeOffice())

    assert converter.to_markdown(tmp_path / "a.pdf") == "# Ficha"
    assert converter.to_markdown(tmp_path / "Ficha.DOC") == "# Ficha"

    (pdf, _), (upgraded, existed) = inner.calls
    assert pdf == tmp_path / "a.pdf"
    assert upgraded.name == "Ficha.docx" and existed
    assert not upgraded.parent.exists()

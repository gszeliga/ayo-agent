"""Old Office formats (`.ppt`, `.doc`, `.xls`): converted to the newer one before docling.

docling reads only the XML Office formats. An office converter turns an old file into its
newer format in a temporary folder: OnlyOffice's `x2t` (shipped with OnlyOffice Desktop
Editors; an internal tool, so its output is checked) or LibreOffice's `soffice`. Their own
messages are never printed (they could quote the document): only the exit status.
"""

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ayo_copilot.docling_import.converter import Converter
from ayo_copilot.docling_import.plan import LEGACY_SUFFIXES

X2T_PATH = Path("/opt/onlyoffice/desktopeditors/converter/x2t")
SOFFICE_NAMES = ("soffice", "libreoffice")
TIMEOUT_SECONDS = 300.0


class OfficeConversionError(Exception):
    """One file could not be converted; the message holds no document content."""


class OfficeConverterUnavailableError(Exception):
    """`--office-converter` names nothing that can run; the message says what."""


class Runner(Protocol):
    def __call__(self, args: list[str], *, env: dict[str, str] | None, timeout: float) -> int:
        """Run `args`, discard its output, return the exit status (raise on a timeout)."""
        ...


def run_quietly(args: list[str], *, env: dict[str, str] | None, timeout: float) -> int:
    try:
        completed = subprocess.run(
            args,
            env=env,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise OfficeConversionError(f"{Path(args[0]).name} timed out after {timeout:g} s") from None
    return completed.returncode


class OfficeConverter(Protocol):
    name: str
    path: Path

    def upgrade(self, source: Path, out_dir: Path) -> Path:
        """Write `source` in its newer format into `out_dir`; return the new file."""
        ...


def _target(source: Path, out_dir: Path) -> Path:
    return out_dir / (source.stem + LEGACY_SUFFIXES[source.suffix.lower()])


def _checked(name: str, status: int, target: Path) -> Path:
    if status != 0:
        raise OfficeConversionError(f"{name} exit {status}")
    if not target.is_file() or target.stat().st_size == 0:
        raise OfficeConversionError(f"{name} wrote no output")
    return target


@dataclass(frozen=True)
class X2tConverter:
    """OnlyOffice's converter: `x2t <in> <out>`, its libraries next to it."""

    path: Path
    runner: Runner = run_quietly
    timeout: float = TIMEOUT_SECONDS
    name: str = field(default="x2t", init=False)

    def upgrade(self, source: Path, out_dir: Path) -> Path:
        target = _target(source, out_dir)
        env = {**os.environ, "LD_LIBRARY_PATH": str(self.path.parent)}
        status = self.runner(
            [str(self.path), str(source), str(target)], env=env, timeout=self.timeout
        )
        return _checked(self.name, status, target)


@dataclass(frozen=True)
class SofficeConverter:
    """LibreOffice headless, with a throwaway profile (an open LibreOffice window is fine)."""

    path: Path
    runner: Runner = run_quietly
    timeout: float = TIMEOUT_SECONDS
    name: str = field(default="soffice", init=False)

    def upgrade(self, source: Path, out_dir: Path) -> Path:
        target = _target(source, out_dir)
        profile = (out_dir / ".soffice-profile").resolve().as_uri()
        args = [
            str(self.path),
            f"-env:UserInstallation={profile}",
            "--headless",
            "--convert-to",
            target.suffix.lstrip("."),
            "--outdir",
            str(out_dir),
            str(source),
        ]
        return _checked(self.name, self.runner(args, env=None, timeout=self.timeout), target)


def find_office_converter(
    explicit: Path | None = None,
    *,
    x2t_path: Path = X2T_PATH,
    which: Callable[[str], str | None] = shutil.which,
) -> OfficeConverter | None:
    """`explicit` if given (x2t by its name, else LibreOffice), else x2t, else soffice."""
    if explicit is not None:
        if not (explicit.is_file() and os.access(explicit, os.X_OK)):
            raise OfficeConverterUnavailableError(f"not an executable file: {explicit}")
        if explicit.name == "x2t":
            return X2tConverter(explicit)
        return SofficeConverter(explicit)
    if x2t_path.is_file() and os.access(x2t_path, os.X_OK):
        return X2tConverter(x2t_path)
    for name in SOFFICE_NAMES:
        found = which(name)
        if found is not None:
            return SofficeConverter(Path(found))
    return None


@dataclass(frozen=True)
class UpgradingConverter:
    """A `Converter` that sends old Office files through `office` first, the rest straight."""

    inner: Converter
    office: OfficeConverter

    def to_markdown(self, source: Path) -> str:
        if source.suffix.lower() not in LEGACY_SUFFIXES:
            return self.inner.to_markdown(source)
        with tempfile.TemporaryDirectory(prefix="docling-import-") as tmp:
            return self.inner.to_markdown(self.office.upgrade(source, Path(tmp)))

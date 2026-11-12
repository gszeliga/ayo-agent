"""The prompt files: loaded and rendered once, at startup.

The prompts live as Markdown files in `prompts/` so consultants can edit them: `base.md`
(every phase) and one file per phase but `closed`. Rendering uses `string.Template`, never
`str.format` (the text may hold braces), and only with values that come from code:

- `$phase`: the phase the file is for (phase files only);
- `$exit_conditions`: where the case can go from that phase and when, generated from the
  transitions table, so the prose cannot drift from the rules the code enforces.

User text, the case record, the knowledge block and the date are never substituted into a
template: the context assembly adds them as separate parts. HTML comments (`<!-- -->`)
are notes for the editors and are removed before rendering. A literal dollar is `$$`.

Any problem (missing, unreadable or empty file, a stray `$`, an unknown placeholder)
raises `PromptError` naming the file, never its content, and the app does not start.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from types import MappingProxyType

from ayo_copilot.conversation.case import PHASES, Phase
from ayo_copilot.conversation.phases import describe_targets

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
BASE_PROMPT = "base"
# The phases with a prompt file: every phase but `closed` (a closed case gets no turn).
PROMPT_PHASES: tuple[Phase, ...] = tuple(phase for phase in PHASES if phase != "closed")

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


class PromptError(Exception):
    """A prompt file cannot be used; the message names the file, never its content."""


@dataclass(frozen=True)
class PromptSet:
    """The rendered prompts. `sha256` identifies the files' exact bytes (for the startup
    log: it shows an edit made without bumping PROMPTS_VERSION)."""

    base: str = field(repr=False)
    phases: Mapping[Phase, str] = field(repr=False)
    sha256: str

    def for_phase(self, phase: Phase) -> str:
        try:
            return self.phases[phase]
        except KeyError:
            raise ValueError(f"no prompt for phase {phase}") from None

    @property
    def file_count(self) -> int:
        return 1 + len(self.phases)


def load_prompts(directory: Path | None = None) -> PromptSet:
    """Read and render every prompt file in `directory` (default: the package's own)."""
    directory = PROMPTS_DIR if directory is None else directory
    digest = hashlib.sha256()

    def load(name: str, variables: Mapping[str, str]) -> str:
        path = directory / f"{name}.md"
        raw = _read(path)
        digest.update(f"{path.name}\0".encode() + raw + b"\0")
        return _render(path.name, raw, variables)

    base = load(BASE_PROMPT, {})
    phases: dict[Phase, str] = {
        phase: load(phase, {"phase": phase, "exit_conditions": describe_targets(phase)})
        for phase in PROMPT_PHASES
    }
    return PromptSet(base=base, phases=MappingProxyType(phases), sha256=digest.hexdigest())


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise PromptError(f"prompt file {path.name} is missing from {path.parent}") from None
    except OSError as error:
        raise PromptError(f"prompt file {path.name} cannot be read: {error.strerror}") from None


def _render(name: str, raw: bytes, variables: Mapping[str, str]) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PromptError(f"prompt file {name} is not UTF-8") from None
    text = _COMMENT.sub("", text)
    if "<!--" in text:
        raise PromptError(f"prompt file {name} has a comment that is never closed (-->)")
    text = text.strip()
    if not text:
        raise PromptError(f"prompt file {name} is empty (comments do not count)")
    template = Template(text)
    if not template.is_valid():
        raise PromptError(
            f"prompt file {name} has a $ that is not a placeholder;"
            " write $$ for a literal dollar sign"
        )
    unknown = sorted(set(template.get_identifiers()) - set(variables))
    if unknown:
        allowed = ", ".join(f"${v}" for v in sorted(variables)) or "none"
        raise PromptError(
            f"prompt file {name} uses unknown placeholders"
            f" {', '.join('$' + u for u in unknown)} (allowed here: {allowed})"
        )
    return template.substitute(variables)

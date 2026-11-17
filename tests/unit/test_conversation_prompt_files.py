"""The prompt files: the real drafts load, and every broken file fails clearly."""

import shutil
from pathlib import Path

import pytest

from ayo_copilot.conversation.phases import describe_targets
from ayo_copilot.conversation.prompt_files import (
    PROMPT_PHASES,
    PROMPTS_DIR,
    PromptError,
    load_prompts,
)

SECRETISH = "Contenido del fichero que no debe aparecer en el error"


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """A copy of the real prompt files, to break one at a time."""
    target = tmp_path / "prompts"
    shutil.copytree(PROMPTS_DIR, target)
    return target


def write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.md").write_text(text, encoding="utf-8")


def test_the_real_files_load_with_every_placeholder_resolved() -> None:
    prompts = load_prompts()

    assert prompts.file_count == 8
    assert set(prompts.phases) == set(PROMPT_PHASES)
    assert "closed" not in prompts.phases
    for text in (prompts.base, prompts.glossary, prompts.summary, *prompts.phases.values()):
        assert text.strip() == text and text
        assert "$" not in text
        assert "DRAFT" not in text and "<!--" not in text and "-->" not in text
    for phase in PROMPT_PHASES:
        rendered = prompts.for_phase(phase)
        assert f"Fase actual: {phase} " in rendered
        assert rendered.endswith(describe_targets(phase))


def test_every_real_file_carries_the_draft_note() -> None:
    for name in ("base", "glossary", *PROMPT_PHASES):
        text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
        assert text.startswith("<!--\nDRAFT to make the engine work end to end.")


def test_the_summary_prompt_is_a_draft_with_its_own_version() -> None:
    raw = (PROMPTS_DIR / "summary.md").read_text(encoding="utf-8")
    assert raw.startswith("<!--\nDRAFT of the case summary prompt")
    assert "SUMMARY_PROMPTS_VERSION" in raw
    assert "### Problema" in load_prompts().summary


def test_hash_covers_the_summary_prompt(prompts_dir: Path) -> None:
    before = load_prompts(prompts_dir).sha256
    write(prompts_dir, "summary", (prompts_dir / "summary.md").read_text() + " ")
    assert load_prompts(prompts_dir).sha256 != before


def test_for_phase_refuses_closed() -> None:
    with pytest.raises(ValueError, match="closed"):
        load_prompts().for_phase("closed")


def test_hash_changes_with_any_byte(prompts_dir: Path) -> None:
    before = load_prompts(prompts_dir).sha256
    assert before == load_prompts(PROMPTS_DIR).sha256
    write(prompts_dir, "action", (prompts_dir / "action.md").read_text() + " ")
    assert load_prompts(prompts_dir).sha256 != before


def test_repr_hides_the_prompts() -> None:
    text = repr(load_prompts())
    assert "copiloto" not in text and "sha256=" in text


def test_comments_anywhere_are_removed_and_dollars_escape(prompts_dir: Path) -> None:
    write(
        prompts_dir,
        "base",
        "<!-- nota -->Coste: $$5 por unidad.<!--\notra nota\n--> Fin. {llaves} ${'{'}x",
    )
    with pytest.raises(PromptError):  # `${'{'}` is not a valid placeholder
        load_prompts(prompts_dir)
    write(prompts_dir, "base", "<!-- nota -->Coste: $$5 por unidad.<!--\nnota\n--> {llaves}")
    assert load_prompts(prompts_dir).base == "Coste: $5 por unidad. {llaves}"


def test_braced_placeholders_work(prompts_dir: Path) -> None:
    write(prompts_dir, "analyse", "Fase ${phase}.\n$exit_conditions")
    assert load_prompts(prompts_dir).for_phase("analyse") == (
        "Fase analyse.\n" + describe_targets("analyse")
    )


@pytest.mark.parametrize("name", ["challenge", "summary"])
def test_missing_file(prompts_dir: Path, name: str) -> None:
    (prompts_dir / f"{name}.md").unlink()
    with pytest.raises(PromptError, match=rf"prompt file {name}\.md is missing from"):
        load_prompts(prompts_dir)


@pytest.mark.parametrize("text", ["", "  \n", "<!-- solo una nota -->\n"])
def test_empty_file(prompts_dir: Path, text: str) -> None:
    write(prompts_dir, "followup", text)
    with pytest.raises(PromptError, match=r"followup\.md is empty"):
        load_prompts(prompts_dir)


def test_not_utf8(prompts_dir: Path) -> None:
    (prompts_dir / "base.md").write_bytes("Línea".encode("latin-1"))
    with pytest.raises(PromptError, match=r"base\.md is not UTF-8"):
        load_prompts(prompts_dir)


def test_unclosed_comment(prompts_dir: Path) -> None:
    write(prompts_dir, "base", f"Texto.\n<!-- {SECRETISH}")
    with pytest.raises(PromptError, match=r"base\.md has a comment that is never closed") as info:
        load_prompts(prompts_dir)
    assert SECRETISH not in str(info.value)


@pytest.mark.parametrize("text", [f"{SECRETISH}: cuesta 5 $", f"{SECRETISH} $ 5", "$5"])
@pytest.mark.parametrize("name", ["understand", "summary"])
def test_stray_dollar(prompts_dir: Path, text: str, name: str) -> None:
    write(prompts_dir, name, text)
    with pytest.raises(PromptError, match=rf"{name}\.md has a \$ that is not a placeholder"):
        load_prompts(prompts_dir)


def test_unknown_placeholder_names_the_allowed_ones(prompts_dir: Path) -> None:
    write(prompts_dir, "action", f"{SECRETISH} $phase $owner ${{today}}")
    with pytest.raises(PromptError) as info:
        load_prompts(prompts_dir)
    message = str(info.value)
    assert message == (
        "prompt file action.md uses unknown placeholders $owner, $today"
        " (allowed here: $exit_conditions, $phase)"
    )


@pytest.mark.parametrize("name", ["base", "glossary", "summary"])
def test_base_glossary_and_summary_allow_no_placeholder(prompts_dir: Path, name: str) -> None:
    write(prompts_dir, name, "Fase $phase")
    with pytest.raises(PromptError, match=rf"{name}\.md uses unknown placeholders \$phase"):
        load_prompts(prompts_dir)


def test_glossary_names_every_phase() -> None:
    glossary = load_prompts().glossary
    for phase in ("understand", "challenge", "analyse", "action", "followup", "closed"):
        assert f"- {phase} (" in glossary

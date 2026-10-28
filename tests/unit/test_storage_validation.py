import pytest

from ayo_copilot.ingestion.storage import (
    InvalidInputError,
    normalize_source_key,
    validate_tenant,
)


@pytest.mark.parametrize("tenant", ["acme", "planta-sevilla", "a1", "0x", "a" * 63])
def test_valid_tenants(tenant: str) -> None:
    assert validate_tenant(tenant) == tenant


@pytest.mark.parametrize(
    "tenant",
    [
        "",
        "a",
        "a" * 64,
        "Acme",
        "-acme",
        "acme_sur",
        "acme/sur",
        "../../etc/passwd",
        "/etc",
        "acme\n",
        "acme\x00",
        "españa",
        " acme",
    ],
)
def test_invalid_tenants(tenant: str) -> None:
    with pytest.raises(InvalidInputError, match="tenant") as exc:
        validate_tenant(tenant)
    assert (exc.value.field, exc.value.code) == ("tenant", "tenant_invalid")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("pro-014.md", "pro-014.md"),
        ("Procedimiento de sellado.md", "Procedimiento de sellado.md"),
        ("  guía.md  ", "guía.md"),
        ("../../etc/passwd", "passwd"),
        ("/etc/passwd", "passwd"),
        ("C:\\Users\\ana\\inspección.md", "inspección.md"),
        ("docs/sub/señal.md", "señal.md"),
    ],
)
def test_source_key_keeps_only_the_file_name(raw: str, expected: str) -> None:
    assert normalize_source_key(raw) == expected


def test_source_key_is_nfc_normalized() -> None:
    decomposed = "inspeccio\u0301n.md"

    assert normalize_source_key(decomposed) == "inspección.md"


@pytest.mark.parametrize(
    "raw",
    ["", "   ", ".", "..", "../", "a/..", "/", "\\", "bad\x00name.md", "bad\nname.md", "x\x1b.md"],
)
def test_invalid_source_keys(raw: str) -> None:
    with pytest.raises(InvalidInputError, match="source_key") as exc:
        normalize_source_key(raw)
    assert (exc.value.field, exc.value.code) == ("source_key", "source_key_invalid")


def test_source_key_length_is_limited() -> None:
    with pytest.raises(InvalidInputError, match="source_key") as exc:
        normalize_source_key("a" * 253 + ".md")
    assert (exc.value.field, exc.value.code) == ("source_key", "source_key_invalid")

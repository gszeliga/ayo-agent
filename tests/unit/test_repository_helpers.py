import pytest

from ayo_copilot.db.repository import DEFAULT_SORT, SORT_KEYS, escape_like, parse_sort


@pytest.mark.parametrize("key", SORT_KEYS)
def test_parse_sort_accepts_every_key_in_both_directions(key: str) -> None:
    assert parse_sort(key) == (key, False)
    assert parse_sort(f"-{key}") == (key, True)


def test_default_sort_is_newest_update_first() -> None:
    assert parse_sort(DEFAULT_SORT) == ("updated_at", True)


@pytest.mark.parametrize(
    "sort", ["", "-", "--title", "+title", "title_x", "Title", "markdown", "id; drop table x"]
)
def test_parse_sort_rejects_anything_else(sort: str) -> None:
    with pytest.raises(ValueError, match="unknown sort key"):
        parse_sort(sort)


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("sellado", "sellado"),
        ("50%", "50\\%"),
        ("pro_014", "pro\\_014"),
        ("a\\b", "a\\\\b"),
        ("\\%_", "\\\\\\%\\_"),
    ],
)
def test_escape_like(text: str, escaped: str) -> None:
    assert escape_like(text) == escaped

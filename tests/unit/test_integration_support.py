import pytest

from tests.integration.support import is_neon_url, with_database


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@ep-cool-name-123456.eu-central-1.aws.neon.tech/neondb?sslmode=require",
        "postgresql://u:p@ep-cool-name-123456-pooler.eu-central-1.aws.neon.tech/neondb",
        "postgres://u:p@EP-X.NEON.TECH:5432/db",
    ],
)
def test_neon_urls_are_detected(url: str) -> None:
    assert is_neon_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://ayo:ayo@localhost:5433/ayo",
        "postgresql://test:test@127.0.0.1:32768/test",
        "postgresql://u:p@neon.tech.example.com/db",
        "postgresql://u:p@notneon.tech/db",
    ],
)
def test_other_urls_are_not_neon(url: str) -> None:
    assert not is_neon_url(url)


def test_with_database_keeps_credentials_host_and_query() -> None:
    url = "postgresql://u:p@localhost:5433/ayo?sslmode=disable"

    assert (
        with_database(url, "scratch_1")
        == "postgresql://u:p@localhost:5433/scratch_1?sslmode=disable"
    )

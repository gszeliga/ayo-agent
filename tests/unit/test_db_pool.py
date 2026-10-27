import logging

import pytest

from ayo_copilot.db.pool import set_db_log_level


@pytest.fixture
def psycopg_logger():
    logger = logging.getLogger("psycopg")
    previous = logger.level
    yield logger
    logger.setLevel(previous)


def test_set_db_log_level_also_applies_to_the_pool_logger(psycopg_logger: logging.Logger) -> None:
    set_db_log_level("INFO")

    assert psycopg_logger.level == logging.INFO
    assert logging.getLogger("psycopg.pool").getEffectiveLevel() == logging.INFO

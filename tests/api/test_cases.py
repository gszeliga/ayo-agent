"""The cases endpoints through HTTP and the real database: the listing's filters, order,
pagination and row fields. Cases are written with SQL, so times and counts are exact."""

from collections.abc import Iterator
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.dependencies import get_llm_provider, get_today
from ayo_copilot.llm.fake import FakeLLMProvider, text_response

pytestmark = pytest.mark.integration

API_KEY = "test-admin-key"
HEADERS = {"X-API-Key": API_KEY}
TODAY = date(2026, 11, 16)


@pytest.fixture
def client(db_pool: ConnectionPool, migrated_database_url: str) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url=migrated_database_url,
        allow_remote_database=True,
        admin_api_key=API_KEY,
        embedding_provider="fake",
    )
    app = create_app(settings, docs_enabled=True)
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as client:
        yield client


def add_case(
    pool: ConnectionPool,
    *,
    tenant: str = "cliente-acme",
    state: str = "understand",
    what: str | None = None,
    updated: str = "2026-11-10 10:00+00",
    turns: int = 0,
    actions: tuple[tuple[str, str], ...] = (),
    link: tuple[str, str] | None = ("web", "web"),
) -> tuple[UUID, str]:
    """A case with `turns` traces, `actions` as (status, due date) and one link; returns
    the case id and the link's thread id."""
    thread = str(uuid4())
    with pool.connection() as conn:
        row = conn.execute(
            "insert into problems (tenant, state, what, created_at, updated_at, closed_at)"
            " values (%s, %s, %s, %s::timestamptz - interval '1 day', %s,"
            " case when %s = 'closed' then %s::timestamptz end) returning id",
            (tenant, state, what, updated, updated, state, updated),
        ).fetchone()
        assert row is not None
        problem_id = row[0]
        for turn_no in range(1, turns + 1):
            conn.execute(
                "insert into turn_traces (problem_id, turn_no, phase_before, phase_after,"
                " prompts_version, llm_calls, duration_ms)"
                " values (%s, %s, 'understand', 'understand', 'draft-1', 1, 10)",
                (problem_id, turn_no),
            )
        for status, due in actions:
            conn.execute(
                "insert into actions (problem_id, description, owner, due_date, status)"
                " values (%s, 'Recalibrar el sensor', 'Ana', %s, %s)",
                (problem_id, due, status),
            )
        if link is not None:
            conn.execute(
                "insert into conversation_links"
                " (problem_id, channel_type, external_channel_id, external_thread_id)"
                " values (%s, %s, %s, %s)",
                (problem_id, link[0], link[1], thread),
            )
    return problem_id, thread


def list_cases(client: TestClient, headers: dict[str, str] = HEADERS, **params: Any):
    return client.get("/admin/cases", params=params, headers=headers)


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [item["case_id"] for item in response.json()["items"]]


def test_empty_listing(client: TestClient) -> None:
    response = list_cases(client)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 0}


def test_row_fields(client: TestClient, db_pool: ConnectionPool) -> None:
    problem_id, thread = add_case(
        db_pool,
        state="action",
        what="Merma del 4 %\nen el envasado",
        updated="2026-11-13 16:02:11+00",
        turns=3,
        actions=(("pending", "2026-11-15"), ("pending", "2026-11-16"), ("done", "2026-11-01")),
    )

    [item] = list_cases(client).json()["items"]

    assert item == {
        "case_id": str(problem_id),
        "tenant": "cliente-acme",
        "title": "Merma del 4 % en el envasado",
        "phase": "action",
        "turns": 3,
        "pending_actions": 2,
        # Due today is not overdue yet; done never is.
        "overdue_actions": 1,
        "created_at": "2026-11-12T16:02:11Z",
        "updated_at": "2026-11-13T16:02:11Z",
        "closed_at": None,
        "web_session_id": thread,
    }


def test_title_is_cut_and_null_until_recorded(client: TestClient, db_pool: ConnectionPool) -> None:
    add_case(db_pool, what="a" * 81, updated="2026-11-10 10:00+00")
    add_case(db_pool, what="b" * 80, updated="2026-11-11 10:00+00")
    add_case(db_pool, what="   ", updated="2026-11-12 10:00+00")
    add_case(db_pool, what=None, updated="2026-11-13 10:00+00")

    titles = [item["title"] for item in list_cases(client).json()["items"]]

    assert titles == [None, None, "b" * 80, "a" * 79 + "…"]


def test_case_from_another_channel_has_no_web_session(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    add_case(db_pool, link=("slack", "T01-C02"))
    add_case(db_pool, link=None, updated="2026-11-11 10:00+00")

    items = list_cases(client).json()["items"]

    assert [item["web_session_id"] for item in items] == [None, None]


def test_closed_case_has_its_closing_time(client: TestClient, db_pool: ConnectionPool) -> None:
    add_case(db_pool, state="closed", updated="2026-11-14 08:00+00")

    [item] = list_cases(client).json()["items"]

    assert (item["phase"], item["closed_at"]) == ("closed", "2026-11-14T08:00:00Z")


def test_newest_update_first_and_stable_on_ties(
    client: TestClient, db_pool: ConnectionPool
) -> None:
    old, _ = add_case(db_pool, updated="2026-11-10 10:00+00")
    new, _ = add_case(db_pool, updated="2026-11-12 10:00+00")
    tie_a, _ = add_case(db_pool, updated="2026-11-11 10:00+00")
    tie_b, _ = add_case(db_pool, updated="2026-11-11 10:00+00")
    ties = sorted([str(tie_a), str(tie_b)])

    assert ids(list_cases(client)) == [str(new), *ties, str(old)]


def test_pagination(client: TestClient, db_pool: ConnectionPool) -> None:
    created = [add_case(db_pool, updated=f"2026-11-{day} 10:00+00")[0] for day in (10, 11, 12)]

    page = list_cases(client, limit=2, offset=1).json()

    assert [item["case_id"] for item in page["items"]] == [str(created[1]), str(created[0])]
    assert (page["total"], page["limit"], page["offset"]) == (3, 2, 1)
    assert list_cases(client, offset=5).json()["items"] == []


def test_filters(client: TestClient, db_pool: ConnectionPool) -> None:
    acme_open, _ = add_case(db_pool, state="analyse", what="Merma en la llenadora")
    acme_closed, _ = add_case(
        db_pool, state="closed", what="Atasco en la etiquetadora", updated="2026-11-11 10:00+00"
    )
    beta, _ = add_case(
        db_pool, tenant="beta", state="analyse", what="MERMA de film", updated="2026-11-12 10:00+00"
    )

    assert ids(list_cases(client, tenant="beta")) == [str(beta)]
    assert ids(list_cases(client, phase="analyse")) == [str(beta), str(acme_open)]
    assert ids(list_cases(client, closed=True)) == [str(acme_closed)]
    assert ids(list_cases(client, closed=False)) == [str(beta), str(acme_open)]
    assert ids(list_cases(client, q="merma")) == [str(beta), str(acme_open)]
    assert ids(list_cases(client, q="merma", tenant="cliente-acme")) == [str(acme_open)]
    assert ids(list_cases(client, phase="closed", closed=False)) == []
    assert list_cases(client, q="merma").json()["total"] == 2
    # An empty search is no filter.
    assert len(ids(list_cases(client, q=""))) == 3


def test_search_matches_wildcards_literally(client: TestClient, db_pool: ConnectionPool) -> None:
    percent, _ = add_case(db_pool, what="Merma del 4 % en el envasado")
    add_case(db_pool, what="Merma del 4 en el envasado", updated="2026-11-11 10:00+00")
    underscore, _ = add_case(db_pool, what="Paro_largo", updated="2026-11-12 10:00+00")
    add_case(db_pool, what="Paro largo", updated="2026-11-13 10:00+00")

    assert ids(list_cases(client, q="4 %")) == [str(percent)]
    assert ids(list_cases(client, q="o_l")) == [str(underscore)]


def test_case_opened_through_the_copilot_is_listed(client: TestClient) -> None:
    llm = FakeLLMProvider([text_response("¿En qué línea?")])
    client.app.dependency_overrides[get_llm_provider] = lambda: llm
    session_id = str(uuid4())
    sent = client.post(
        "/copilot/messages",
        json={"session_id": session_id, "tenant": "cliente-acme", "text": "Hay merma"},
        headers=HEADERS,
    ).json()

    [item] = list_cases(client).json()["items"]

    assert (item["case_id"], item["web_session_id"], item["turns"]) == (
        sent["case_id"],
        session_id,
        1,
    )
    assert item["title"] is None


@pytest.mark.parametrize(
    ("params", "loc", "type"),
    [
        ({"phase": "done"}, "phase", "literal_error"),
        ({"closed": "maybe"}, "closed", "bool_parsing"),
        ({"limit": 0}, "limit", "greater_than_equal"),
        ({"limit": 101}, "limit", "less_than_equal"),
        ({"offset": -1}, "offset", "greater_than_equal"),
        ({"q": "a" * 201}, "q", "string_too_long"),
        ({"tenant": "Acme Corp"}, "tenant", "string_pattern_mismatch"),
    ],
)
def test_invalid_parameters_are_422(
    client: TestClient, params: dict[str, Any], loc: str, type: str
) -> None:
    response = list_cases(client, **params)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert (error["loc"], error["type"]) == (["query", loc], type)


def test_search_text_is_not_logged(
    client: TestClient, db_pool: ConnectionPool, caplog: pytest.LogCaptureFixture
) -> None:
    add_case(db_pool, what="Merma confidencial")

    with caplog.at_level("DEBUG"):
        list_cases(client, q="confidencial")

    # The app's own loggers; the request line of an HTTP access log is the server's
    # (see the open item on access logs in plans/chat-progress.md).
    app_messages = [r.getMessage() for r in caplog.records if r.name.startswith("ayo_copilot")]
    assert not any("confidencial" in message for message in app_messages)

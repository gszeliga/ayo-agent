"""A real conversation: eight fixed user messages over HTTP, with the configured model
(OpenRouter, `LLM_MODEL`), real Voyage embeddings and a test container database.

BILLED: about 8 to 48 model calls (usually 16 to 20) and a few small embedding requests.
Runs only with `-m live` and both keys (environment or `.env`).

Asserts structure only (spec): every message answered, a legal phase at every step, one
trace per turn, only real tool names. How well the model follows the phases is for a
person to read in the transcript, written to `eval/conversations/` (git-ignored) even
when an assertion fails.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from ayo_copilot.app import create_app
from ayo_copilot.config import Settings
from ayo_copilot.conversation.case import PHASES
from ayo_copilot.conversation.channels import web_key
from ayo_copilot.conversation.phases import is_allowed
from ayo_copilot.conversation.store import SessionView, read_session, read_traces
from ayo_copilot.conversation.tools import TOOL_NAMES
from ayo_copilot.conversation.transcript import render_transcript, write_transcript
from ayo_copilot.db.conversations import StoredTrace

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
OUT_DIR = REPO_ROOT / "eval" / "conversations"
API_KEY = "live-test-key"
HEADERS = {"X-API-Key": API_KEY}
TENANT = "cliente-sevilla"

# From a vague first message towards an action plan, in the procedure's domain.
USER_MESSAGES = [
    "Hola, tenemos un problema con fugas en los envases.",
    "Son bolsas que fugan por el sellado: estamos rechazando un 3,8 % en la selladora 2 de la"
    " línea de envasado de Sevilla.",
    "Empezó el martes 10 de noviembre, en el turno de tarde. El estándar es menos de un 0,5 %"
    " de rechazo por sellado.",
    "El jefe de turno está convencido de que es el film nuevo del proveedor.",
    "Hemos medido: la presión de sellado está en 2,1 bar, por debajo del mínimo del PRO-014,"
    " y la temperatura en 185 °C. Con el film antiguo el rechazo sale igual.",
    "Mantenimiento ha revisado el cilindro neumático de la mordaza y tiene una fuga de aire."
    " Al cambiarlo de prueba, la presión volvió a 2,7 bar y el rechazo bajó al 0,4 % durante"
    " dos turnos.",
    "Acordamos que Luis, de mantenimiento, cambie el cilindro definitivamente antes del 20 de"
    " noviembre, y que Carmen, de calidad, añada la comprobación de presión a la hoja de turno"
    " antes del 25 de noviembre.",
    "Sí, eso es todo por ahora. Podemos pasar al seguimiento.",
]


@pytest.fixture
def settings(migrated_database_url: str) -> Settings:
    """The real configuration (model, keys) from the environment or `.env`, with the test
    container database."""
    common = {
        "database_url": migrated_database_url,
        "allow_remote_database": True,
        "admin_api_key": API_KEY,
    }
    # Read the keys first: Settings refuses `voyage` without its key.
    probe = Settings(**common, embedding_provider="fake")
    if probe.openrouter_api_key is None:
        pytest.skip("OPENROUTER_API_KEY is not set (environment or .env)")
    if probe.voyage_api_key is None:
        pytest.skip("VOYAGE_API_KEY is not set (environment or .env)")
    return Settings(**common, embedding_provider="voyage")


@pytest.fixture
def client(db_pool: ConnectionPool, settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings, docs_enabled=True)) as client:
        yield client


def upload(client: TestClient, name: str, tenant: str) -> None:
    with (FIXTURES / name).open("rb") as file:
        response = client.post(
            "/admin/documents",
            files={"file": (name, file, "text/markdown")},
            data={"tenant": tenant},
            headers=HEADERS,
        )
    assert response.status_code == 201, response.text


def test_a_real_conversation_keeps_the_structural_invariants(
    client: TestClient, db_pool: ConnectionPool, settings: Settings
) -> None:
    upload(client, "pro-014-control-sellado.md", TENANT)
    upload(client, "metodo-cinco-porques.md", "ayo")
    session_id = uuid4()
    phases = ["understand"]
    try:
        for text in USER_MESSAGES:
            response = client.post(
                "/copilot/messages",
                json={"session_id": str(session_id), "tenant": TENANT, "text": text},
                headers=HEADERS,
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["reply"].strip()
            assert body["phase"] in PHASES
            assert body["previous_phase"] == phases[-1]
            if body["phase_changed"]:
                assert is_allowed(phases[-1], body["phase"])
            phases.append(body["phase"])
            if body["phase"] == "closed":
                break
    finally:
        written = write_session(db_pool, session_id, settings)

    assert written is not None, "no case was opened"
    view, traces = written
    assert len(traces) == view.turns == len(phases) - 1
    assert {tool.name for t in traces for tool in t.trace.tool_calls} <= set(TOOL_NAMES)


def write_session(
    pool: ConnectionPool, session_id: UUID, settings: Settings
) -> tuple[SessionView, list[StoredTrace]] | None:
    """Write the transcript of whatever was committed; returns the view and traces, or
    None when no case was opened (so an earlier failure is not hidden)."""
    now = datetime.now(UTC)
    today = now.astimezone(settings.timezone()).date()
    view = read_session(pool, web_key(str(session_id)), today=today)
    if view is None:
        return None
    traces = read_traces(pool, view.problem_id)
    text = render_transcript(session_id, view, traces, written_at=now)
    path = write_transcript(text, session_id=session_id, out_dir=OUT_DIR, now=now)
    print(f"\ntranscript: {path}")
    return view, traces

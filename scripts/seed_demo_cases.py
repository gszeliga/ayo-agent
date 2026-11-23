"""Seed demo cases for trying the test chat and its inspector: no model call, no cost.

    uv run python scripts/seed_demo_cases.py                      # local database
    uv run python scripts/seed_demo_cases.py --host HOST          # a remote one (dev branch!)
    uv run python scripts/seed_demo_cases.py --reset [--yes]      # remove what it wrote

Writes through the engine's own path (`resolve_case`, `load_snapshot`, `commit_turn`), so
rows have the shape a real turn writes; traces carry made-up metrics. Everything lives in
the `demo-*` tenants: the cases (marked `created_by = demo-seed`) and two fixture documents
embedded with the fake embedder (their vectors are meaningless: search them for nothing).
Timestamps are moved back afterwards so the list reads like days of work.

Uses DATABASE_URL (`.env` or the shell). Local hosts are allowed; any other host only when
passed as `--host`, exactly. Only the host is ever printed. Logs no content.
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool

from ayo_copilot.config import Settings
from ayo_copilot.conversation.case import Action, Event, FieldName, Phase, TurnChanges
from ayo_copilot.conversation.channels import WEB_CHANNEL, WEB_CHANNEL_ID
from ayo_copilot.conversation.store import (
    ChannelKey,
    TurnCommit,
    commit_turn,
    load_snapshot,
    resolve_case,
)
from ayo_copilot.db import conversations as db
from ayo_copilot.db.pool import open_pool
from ayo_copilot.documents import delete_document
from ayo_copilot.ingestion.embedding import FakeEmbedder
from ayo_copilot.ingestion.service import ingest_document

MARKER = "demo-seed"
TENANTS = ("demo-acme", "demo-norte", "demo-sur")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
MODEL = "demo/fake-model"

# --- What a turn of the script holds -------------------------------------------------------


@dataclass
class Ref:
    """A retrieved chunk: a fixture document by key and a chunk index in it."""

    doc: str
    chunk: int
    similarity: float


@dataclass
class Turn:
    user: str
    reply: str
    phase: Phase | None = None  # the phase after the turn; None keeps it
    fields: dict[FieldName, str] = field(default_factory=dict)
    events: list[tuple[str, str]] = field(default_factory=list)  # (event_type, content)
    actions: list[tuple[str, str, int]] = field(default_factory=list)  # (text, owner, due in days)
    done: list[str] = field(default_factory=list)  # descriptions of actions now done
    tools: list[db.ToolCallTrace] = field(default_factory=list)
    refs: list[Ref] = field(default_factory=list)
    retrieval_error: str | None = None
    capped: bool = False


@dataclass
class DemoCase:
    tenant: str
    hours_ago: int  # when its last turn happened
    turns: list[Turn]
    web: bool = True
    summary: str | None = None


def ok(name: str, target: Phase | None = None) -> db.ToolCallTrace:
    return db.ToolCallTrace(name, True, target=target)


def refused(target: Phase, *missing: str) -> db.ToolCallTrace:
    return db.ToolCallTrace(
        "propose_transition", False, "criteria_not_met", target=target, missing=missing
    )


# --- The cases -------------------------------------------------------------------------------

WHAT = "Merma del 4 % en el envasado de la línea 2"

ACME = DemoCase(
    tenant="demo-acme",
    hours_ago=1,
    turns=[
        Turn(
            "Tenemos mucha merma en el envasado de la línea 2, sobre un 4 %.",
            "Entendido. Para centrar el problema: **¿desde cuándo** lo veis y cuál es el "
            "estándar de merma que debería cumplir la línea?",
            fields={"what": WHAT},
            tools=[ok("record_field")],
            refs=[Ref("metodo", 0, 0.61)],
        ),
        Turn(
            "Desde el lunes 9. El estándar es como mucho un 1 %.",
            "Gracias. ¿Dónde se concentra la merma: en la llenadora, en el sellado o al final?",
            fields={"since": "Desde el lunes 9", "standard": "Merma máxima del 1 %"},
            tools=[ok("record_field"), ok("record_field"), refused("challenge", "where")],
        ),
        Turn(
            "En la selladora, la mayoría de bolsas salen mal selladas.",
            "Con eso ya tenemos el problema descrito. Pasemos a **contrastar los datos**: "
            "¿tenéis registros de merma por turno?",
            phase="challenge",
            fields={"where": "Línea 2, selladora"},
            tools=[ok("record_field"), ok("propose_transition", "challenge")],
            refs=[Ref("sellado", 1, 0.74), Ref("sellado", 2, 0.69)],
        ),
        Turn(
            "Sí: de noche la merma sube al 6 %, de día se queda en el 2 %.",
            "Es una diferencia clara entre turnos. La anoto como evidencia.",
            events=[("evidence", "La merma sube al 6 % en el turno de noche (2 % de día)")],
            tools=[ok("log_event"), refused("analyse", "evidence_count")],
            retrieval_error="timeout",
        ),
        Turn(
            "Además, el turno de noche cambió de bobina de film la semana pasada.",
            "Otro dato útil. Con dos evidencias podemos pasar a **analizar causas**.",
            phase="analyse",
            events=[("evidence", "Cambio de proveedor de film en el turno de noche")],
            tools=[ok("log_event"), ok("propose_transition", "analyse")],
            refs=[Ref("sellado", 3, 0.71), Ref("deleted", 0, 0.58)],
        ),
        Turn(
            "Creo que la temperatura de las mordazas de noche es más baja.",
            "Lo anoto como hipótesis. ¿Se registra la temperatura de sellado por turno?",
            events=[("hypothesis", "Temperatura de mordazas más baja en el turno de noche")],
            tools=[ok("log_event")],
            refs=[Ref("sellado", 0, 0.77)],
        ),
        Turn(
            "Se registra, y es la misma en los dos turnos.",
            "Entonces descartamos la temperatura. ¿Qué cambió con el film nuevo?",
            events=[
                ("hypothesis_discarded", "La temperatura de mordazas es igual en ambos turnos")
            ],
            tools=[ok("log_event")],
        ),
        Turn(
            "El film nuevo es más grueso, 60 micras en vez de 50.",
            "Eso encaja: un film más grueso necesita más tiempo de sellado. Lo anoto.",
            events=[("hypothesis", "El film de 60 µm necesita más tiempo de sellado")],
            tools=[ok("log_event"), refused("action", "validated_cause")],
            refs=[Ref("sellado", 4, 0.82), Ref("metodo", 2, 0.55)],
        ),
        Turn(
            "¿Cómo podemos comprobarlo sin parar la línea?",
            "Podéis hacer una prueba corta con el film de 50 µm en el turno de noche y "
            "comparar la merma. **Por qué** importa: si baja, confirma la hipótesis.",
            refs=[Ref("metodo", 1, 0.66)],
        ),
    ],
)

NORTE = DemoCase(
    tenant="demo-norte",
    hours_ago=5,
    turns=[
        Turn(
            "La llenadora L3 se para varias veces cada noche.",
            "Vamos a describir el problema. ¿Desde cuándo pasa y qué sería lo normal?",
            fields={"what": "Paradas repetidas de la llenadora L3 en el turno de noche"},
            tools=[ok("record_field")],
        ),
        Turn(
            "Desde hace dos semanas, en la llenadora L3. Lo normal son cero paradas.",
            "Problema descrito. Pasamos a los datos.",
            phase="challenge",
            fields={
                "where": "Llenadora L3",
                "since": "Desde hace dos semanas",
                "standard": "Ninguna parada no planificada por turno",
            },
            tools=[ok("record_field")] * 3 + [ok("propose_transition", "challenge")],
        ),
        Turn(
            "El registro dice 5 paradas por noche, todas por el sensor de nivel.",
            "Anotado como evidencia. Con esto pasamos al análisis.",
            phase="analyse",
            events=[
                ("evidence", "5 paradas por noche, todas por alarma del sensor de nivel"),
                ("evidence", "El sensor se limpió por última vez hace un mes"),
            ],
            tools=[ok("log_event"), ok("log_event"), ok("propose_transition", "analyse")],
        ),
        Turn(
            "Al limpiar el sensor esta mañana las paradas han desaparecido.",
            "Entonces la causa validada es la suciedad del sensor. Definamos acciones.",
            phase="action",
            events=[
                ("hypothesis", "Suciedad en el sensor de nivel"),
                ("validated_cause", "El sensor de nivel sucio da falsas alarmas"),
            ],
            tools=[ok("log_event"), ok("log_event"), ok("propose_transition", "action")],
        ),
        Turn(
            "Acciones: Marta limpia el sensor cada semana, Luis revisa el plan de "
            "mantenimiento y Ana forma al turno de noche.",
            "Registradas las tres acciones con responsable y fecha.",
            actions=[
                ("Limpieza semanal del sensor de nivel", "Marta (mantenimiento)", -3),
                ("Revisar el plan de mantenimiento preventivo de L3", "Luis (ingeniería)", 7),
                ("Formar al turno de noche en la limpieza del sensor", "Ana (producción)", 2),
            ],
            tools=[ok("add_action")] * 3,
        ),
        Turn(
            "Ana ya ha dado la formación.",
            "La marco como hecha. Quedan dos acciones pendientes, una vencida.",
            done=["Formar al turno de noche en la limpieza del sensor"],
            tools=[ok("update_action")],
        ),
    ],
    summary=(
        "**Problema:** paradas repetidas de la llenadora L3 en el turno de noche.\n\n"
        "**Causa validada:** el sensor de nivel sucio da falsas alarmas.\n\n"
        "**Acciones:** limpieza semanal, revisión del plan preventivo y formación (hecha)."
    ),
)

SUR = DemoCase(
    tenant="demo-sur",
    hours_ago=30,
    turns=[
        Turn(
            "Hay fugas en la junta de la bomba P-201.",
            "¿Desde cuándo, y qué debería cumplir la bomba?",
            fields={"what": "Fugas en la junta de la bomba P-201", "where": "Bomba P-201"},
            tools=[ok("record_field"), ok("record_field")],
        ),
        Turn(
            "Desde el mes pasado; no debería perder nada.",
            "Problema descrito. ¿Qué datos tenemos?",
            phase="challenge",
            fields={"since": "Desde el mes pasado", "standard": "Sin fugas visibles"},
            tools=[ok("record_field"), ok("record_field"), ok("propose_transition", "challenge")],
        ),
        Turn(
            "La junta se cambió hace 6 semanas por una de otro proveedor.",
            "Evidencia anotada; pasemos al análisis.",
            phase="analyse",
            events=[("evidence", "Junta cambiada hace 6 semanas por otro proveedor")],
            tools=[ok("log_event"), ok("propose_transition", "analyse")],
        ),
        Turn(
            "Con la junta original no pierde: está comprobado.",
            "Causa validada: la junta del proveedor nuevo. Acciones:",
            phase="action",
            events=[
                ("hypothesis", "La junta del proveedor nuevo no ajusta"),
                ("validated_cause", "La junta del proveedor nuevo no ajusta en la P-201"),
            ],
            actions=[("Volver a la junta original en la P-201", "Pedro (mantenimiento)", -10)],
            tools=[ok("log_event"), ok("log_event"), ok("add_action")],
        ),
        Turn(
            "Hecho: la junta original ya está puesta y no pierde.",
            "Perfecto, cerramos el caso.",
            phase="closed",
            done=["Volver a la junta original en la P-201"],
            tools=[ok("update_action"), ok("propose_transition", "closed")],
        ),
    ],
    summary=(
        "**Problema:** fugas en la junta de la bomba P-201 desde el mes pasado.\n\n"
        "**Causa validada:** la junta del proveedor nuevo no ajusta.\n\n"
        "**Resultado:** se volvió a la junta original; caso cerrado sin fugas."
    ),
)

OTHER_CHANNEL = DemoCase(
    tenant="demo-acme",
    hours_ago=50,
    web=False,
    turns=[
        Turn(
            "Temperatura alta en el horno 2 desde ayer.",
            "¿Dónde exactamente, y qué temperatura sería la normal?",
            fields={"what": "Temperatura alta en el horno 2", "since": "Desde ayer"},
            tools=[ok("record_field"), ok("record_field")],
        ),
        Turn(
            "En la zona 3; lo normal son 180 °C y estamos en 195 °C.",
            "Descrito. Pasamos a los datos.",
            phase="challenge",
            fields={"where": "Horno 2, zona 3", "standard": "180 °C ± 5"},
            tools=[ok("record_field"), ok("record_field"), ok("propose_transition", "challenge")],
        ),
        Turn(
            "El termopar de la zona 3 se cambió ayer.",
            "Anotado. (Este turno llegó al límite de llamadas del modelo.)",
            events=[("evidence", "Termopar de la zona 3 cambiado ayer")],
            tools=[ok("log_event"), db.ToolCallTrace("log_event", False, "invalid_arguments")] * 3,
            capped=True,
        ),
    ],
)

UNTITLED = DemoCase(
    tenant="demo-norte",
    hours_ago=80,
    turns=[
        Turn(
            "Hola, tenemos un problema en la planta.",
            "Hola. Cuéntame **qué está pasando**: qué ves, dónde y desde cuándo.",
        ),
    ],
)

CASES = [ACME, NORTE, SUR, OTHER_CHANNEL, UNTITLED]

# --- Writing --------------------------------------------------------------------------------


def check_host(url: str, allowed: str | None) -> str:
    host = (urlsplit(url).hostname or "").lower()
    if host in LOCAL_HOSTS or (allowed is not None and host == allowed.lower()):
        return host
    sys.exit(
        f"Refusing host {host!r}: pass --host {host} to write there (the Neon dev branch only)."
    )


def ingest_fixtures(settings: Settings, pool: ConnectionPool) -> dict[str, str]:
    """The two fixture documents in demo-acme, plus one deleted afterwards: key -> doc_id."""
    embedder = FakeEmbedder(dimensions=settings.embedding_dimensions)
    docs = {
        "sellado": ("pro-014-control-sellado.md", "PRO-014 Control del sellado"),
        "metodo": ("metodo-cinco-porques.md", "Método de los cinco porqués"),
        "deleted": ("metodo-cinco-porques.md", "Borrador antiguo (borrado)"),
    }
    ids: dict[str, str] = {}
    for key, (filename, title) in docs.items():
        result = ingest_document(
            settings=settings,
            pool=pool,
            embedder=embedder,
            tenant="demo-acme",
            filename=filename,
            content=(FIXTURES / filename).read_bytes(),
            title=title,
            source_key=f"demo-{key}.md",
            force=True,
        )
        ids[key] = result.doc_id
    return ids


def chunk_ids(pool: ConnectionPool, doc_ids: dict[str, str]) -> dict[tuple[str, int], UUID]:
    found: dict[tuple[str, int], UUID] = {}
    with pool.connection() as conn:
        for key, doc_id in doc_ids.items():
            rows = conn.execute(
                "select c.chunk_index, c.id from chunks c join documents d on d.id = c.document_id"
                " where d.doc_id = %s",
                (doc_id,),
            ).fetchall()
            for index, chunk_id in rows:
                found[(key, index)] = chunk_id
    return found


def seed_case(
    pool: ConnectionPool,
    demo: DemoCase,
    number: int,
    doc_ids: dict[str, str],
    chunks: dict[tuple[str, int], UUID],
    prompts_version: str,
) -> UUID:
    channel = (WEB_CHANNEL, WEB_CHANNEL_ID) if demo.web else ("slack", "T-demo")
    # A web thread is the session id the browser makes: a UUID.
    thread = str(uuid4()) if demo.web else f"demo-{number}-{uuid4().hex[:8]}"
    key = ChannelKey(*channel, thread)
    case_id = resolve_case(pool, key, tenant=demo.tenant, created_by=MARKER).problem_id
    today = date.today()
    for turn in demo.turns:
        snapshot = load_snapshot(pool, case_id, message_limit=1)
        case = snapshot.case
        phase_before = case.state
        changes = TurnChanges()
        for name, value in turn.fields.items():
            case.set_field(name, value)
            changes.fields[name] = value
        for event_type, content in turn.events:
            changes.new_events.append(
                Event("assistant", event_type, content, state_at_time=phase_before)  # type: ignore[arg-type]
            )
        for text, owner, days in turn.actions:
            changes.new_actions.append(Action(text, owner, today + timedelta(days=days)))
        for text in turn.done:
            stored = next(a for a in snapshot.actions if a.description == text)
            assert stored.id is not None
            changes.action_updates[stored.id] = "done"
        if turn.phase is not None:
            case.state = turn.phase
        retrieved = tuple(
            db.RetrievedTrace(chunks[(ref.doc, ref.chunk)], ref.similarity, doc_ids[ref.doc])
            for ref in turn.refs
            if (ref.doc, ref.chunk) in chunks
        )
        calls = 1 + len(turn.tools)
        trace = db.TraceRecord(
            prompts_version=prompts_version,
            llm_calls=calls,
            duration_ms=1800 + 900 * calls,
            model=MODEL,
            prompt_tokens=2600 * calls,
            completion_tokens=180 * calls,
            total_tokens=2780 * calls,
            cost=0.0009 * calls,
            tool_calls=tuple(turn.tools),
            retrieved=retrieved,
            retrieval_error=turn.retrieval_error,
            capped=turn.capped,
        )
        commit_turn(
            pool,
            TurnCommit(
                snapshot=snapshot,
                phase_before=phase_before,
                user_message=turn.user,
                reply=turn.reply,
                changes=changes,
                trace=trace,
            ),
        )
    if demo.summary is not None:
        with pool.connection() as conn, conn.transaction():
            version = conn.execute(
                "select version from problems where id = %s", (case_id,)
            ).fetchone()[0]
            # North's summary is made one version back, so it reads as stale.
            source = version - 1 if demo is NORTE else version
            db.upsert_case_summary(
                conn,
                case_id,
                db.SummaryRecord(demo.summary, source, MODEL, "summary-draft-1", 1900, 0.0011),
            )
    age(pool, case_id, demo)
    return case_id


def age(pool: ConnectionPool, case_id: UUID, demo: DemoCase) -> None:
    """Move the case's times back: turns six minutes apart, the last `hours_ago` ago."""
    step = timedelta(minutes=6)
    end = datetime.now(UTC) - timedelta(hours=demo.hours_ago)
    start = end - step * len(demo.turns)
    with pool.connection() as conn, conn.transaction():
        conn.execute(
            "update turn_traces set created_at = %(start)s + turn_no * %(step)s"
            " where problem_id = %(id)s",
            {"start": start, "step": step, "id": case_id},
        )
        # Messages and annotations in id order, spread over the same span.
        conn.execute(
            """
            with ordered as (
              select id, row_number() over (order by id) as n,
                     count(*) over () as total from problem_events where problem_id = %(id)s
            )
            update problem_events e set created_at = %(start)s
                   + (%(end)s - %(start)s) * (ordered.n::float / ordered.total)
            from ordered where e.id = ordered.id
            """,
            {"start": start, "end": end, "id": case_id},
        )
        conn.execute(
            "update actions set created_at = %(end)s, updated_at = %(end)s"
            " where problem_id = %(id)s",
            {"end": end, "id": case_id},
        )
        conn.execute(
            "update conversation_links set created_at = %(start)s where problem_id = %(id)s",
            {"start": start, "id": case_id},
        )
        conn.execute(
            "update case_summaries set created_at = %(end)s where problem_id = %(id)s",
            {"end": end, "id": case_id},
        )
        conn.execute(
            "update problems set created_at = %(start)s, updated_at = %(end)s,"
            " closed_at = case when closed_at is null then null else %(end)s end"
            " where id = %(id)s",
            {"start": start, "end": end, "id": case_id},
        )


def demo_rows(pool: ConnectionPool) -> tuple[int, list[str]]:
    with pool.connection() as conn:
        cases = conn.execute(
            "select count(*) from problems where created_by = %s", (MARKER,)
        ).fetchone()[0]
        docs = [
            row[0]
            for row in conn.execute(
                "select doc_id from documents where tenant = any(%s)",
                (list(TENANTS),),
            ).fetchall()
        ]
    return cases, docs


def reset(pool: ConnectionPool, yes: bool) -> None:
    cases, docs = demo_rows(pool)
    print(f"Demo data here: {cases} cases (created_by={MARKER}), {len(docs)} documents.")
    if not yes:
        print("Nothing deleted: run again with --yes to delete exactly these.")
        return
    with pool.connection() as conn, conn.transaction():
        conn.execute("delete from problems where created_by = %s", (MARKER,))
    for doc_id in docs:
        delete_document(pool, doc_id)
    print("Deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", help="allow this remote database host (the Neon dev branch)")
    parser.add_argument("--reset", action="store_true", help="remove the demo data")
    parser.add_argument("--yes", action="store_true", help="with --reset: really delete")
    args = parser.parse_args()

    settings = Settings()
    url = settings.database_url.get_secret_value()
    host = check_host(url, args.host)
    print(f"Database host: {host}")
    pool = open_pool(url)
    try:
        if args.reset:
            reset(pool, args.yes)
            return
        cases, docs = demo_rows(pool)
        if cases or docs:
            sys.exit(
                f"Demo data already here ({cases} cases, {len(docs)} documents): --reset first."
            )
        doc_ids = ingest_fixtures(settings, pool)
        chunks = chunk_ids(pool, doc_ids)
        # The "deleted" document goes now: its chunks stay in the traces, as after a delete.
        delete_document(pool, doc_ids["deleted"])
        for number, demo in enumerate(CASES, start=1):
            seed_case(pool, demo, number, doc_ids, chunks, settings.prompts_version)
        print(f"Seeded {len(CASES)} cases in {', '.join(TENANTS)} and 2 documents in demo-acme.")
    finally:
        pool.close()


if __name__ == "__main__":
    main()

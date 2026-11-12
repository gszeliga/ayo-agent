"""The retrieval query built from the case state."""

from uuid import uuid4

from ayo_copilot.conversation.case import Case, CaseSnapshot, Event
from ayo_copilot.conversation.query import QUERY_MAX_CHARS, build_query
from ayo_copilot.schemas import MAX_QUERY_CHARS


def snapshot(**fields: str) -> CaseSnapshot:
    return CaseSnapshot(case=Case(id=uuid4(), tenant="cliente-acme", state="analyse", **fields))


def annotation(event_type: str, content: str) -> Event:
    return Event(
        role="assistant",
        event_type=event_type,  # type: ignore[arg-type]
        content=content,
        state_at_time="challenge",
    )


def test_limit_matches_the_search_service() -> None:
    assert QUERY_MAX_CHARS == MAX_QUERY_CHARS


def test_parts_in_priority_order_newest_first() -> None:
    case = snapshot(
        what="Merma del 4 %",
        where_="Línea 2, llenadora 3",
        since="Desde el lunes",
        standard="1,5 %",
    )
    case.events += [
        annotation("evidence", "Evidencia antigua"),
        annotation("hypothesis", "Hipótesis antigua"),
        annotation("hypothesis_discarded", "Descartada"),
        annotation("evidence", "Evidencia nueva\ncon dos líneas"),
        annotation("hypothesis", "Hipótesis nueva"),
        annotation("validated_cause", "Causa"),
        Event(role="user", event_type="message", content="Mensaje viejo", state_at_time="analyse"),
    ]
    assert build_query(case, "¿Qué método usamos?").split("\n") == [
        "Merma del 4 %",
        "Línea 2, llenadora 3",
        "¿Qué método usamos?",
        "Evidencia nueva con dos líneas",
        "Evidencia antigua",
        "Hipótesis nueva",
        "Hipótesis antigua",
    ]


def test_empty_parts_are_skipped_and_text_is_cleaned() -> None:
    case = snapshot(what="  Merma\x00  alta ", where_="   ")
    assert build_query(case, "\x07Hola ") == "Merma alta\nHola"
    assert build_query(snapshot(), "") == ""


def test_deterministic_and_cut_at_the_limit_losing_old_evidence_first() -> None:
    case = snapshot(what="Merma", where_="Línea 2")
    case.events += [annotation("evidence", f"evidencia {n} " + "x" * 300) for n in range(10)]
    query = build_query(case, "pregunta")
    assert query == build_query(case, "pregunta")
    assert len(query) <= QUERY_MAX_CHARS
    assert query.startswith("Merma\nLínea 2\npregunta\nevidencia 9 ")
    assert "evidencia 0 " not in query

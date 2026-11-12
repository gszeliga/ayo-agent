"""The tools offered to the model: their specs, which phase gets which, and their handlers.

This module is the single source of the tools (the `ayo-llm-check` scenarios will import
the specs from here). Tool descriptions are in Spanish, like the prompts; error codes are
English snake_case and `detail` is a short English reason.

`execute_tool` never trusts a call: an unknown or not-offered tool, unparsable arguments,
arguments that break the JSON Schema or fail a semantic check are not executed, and the
model gets an error result instead. Results are small JSON objects:
`{"ok": true, ...}` or `{"ok": false, "error": "<code>", "detail": "<reason>"}`.

Validation details may repeat argument values (customer content): they only ever go back
to the model. Logs and traces carry the tool name and `error_code`, never the result.
"""

import json
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from jsonschema import Draft202012Validator

from ayo_copilot.conversation.case import (
    ACTION_STATUSES,
    ANNOTATION_TYPES,
    FIELDS,
    Action,
    CaseSnapshot,
    Event,
    EventType,
    Phase,
    Transition,
    TurnChanges,
)
from ayo_copilot.conversation.phases import (
    TRANSITIONS,
    describe_missing,
    is_allowed,
    missing_for,
    targets,
)
from ayo_copilot.llm.types import ToolCall, ToolSpec

FIELD_VALUE_MAX = 500
EVENT_CONTENT_MAX = 1000
ACTION_DESCRIPTION_MAX = 500
ACTION_OWNER_MAX = 100
REASONING_MAX = 500
# Each schema error message sent back to the model is capped (it may echo the value).
_SCHEMA_DETAIL_MAX = 200

TOOL_NAMES: tuple[str, ...] = (
    "record_field",
    "log_event",
    "add_action",
    "update_action",
    "propose_transition",
)

# The annotation types `log_event` may record, per phase.
LOG_EVENT_TYPES: dict[Phase, tuple[EventType, ...]] = {
    "challenge": ("evidence", "hypothesis", "hypothesis_discarded"),
    "analyse": ANNOTATION_TYPES,
}

# The phases that get each tool (`propose_transition`: every phase with a target).
_PHASES_BY_TOOL: dict[str, frozenset[Phase]] = {
    "record_field": frozenset({"understand", "challenge"}),
    "log_event": frozenset(LOG_EVENT_TYPES),
    "add_action": frozenset({"action", "followup"}),
    "update_action": frozenset({"action", "followup"}),
    "propose_transition": frozenset(p for p, t in TRANSITIONS.items() if t),
}

# String arguments that are stored or shown, so they are cleaned before use.
_TEXT_ARGUMENTS: dict[str, tuple[str, ...]] = {
    "record_field": ("value",),
    "log_event": ("content",),
    "add_action": ("description", "owner"),
    "update_action": (),
    "propose_transition": ("reasoning",),
}


# --- Specs --------------------------------------------------------------------


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _text(max_length: int) -> dict[str, Any]:
    return {"type": "string", "minLength": 1, "maxLength": max_length}


def record_field_tool() -> ToolSpec:
    return ToolSpec(
        name="record_field",
        description=(
            "Registra uno de los cuatro datos que definen el problema, en cuanto el usuario"
            " lo dice de forma clara: qué se desvía (what), dónde (where), desde cuándo"
            " (since) y cuál es el estándar esperado (standard). Si el dato ya estaba"
            " registrado, lo sustituye (sirve para corregirlo)."
        ),
        parameters=_object(
            {
                "field": {"type": "string", "enum": list(FIELDS)},
                "value": _text(FIELD_VALUE_MAX),
            }
        ),
    )


def log_event_tool(phase: Phase) -> ToolSpec:
    """`event_type` offers only the annotation types allowed in `phase`."""
    types = LOG_EVENT_TYPES.get(phase)
    if not types:
        raise ValueError(f"log_event is not offered in phase {phase}")
    meanings = {
        "evidence": "evidence: un dato o una observación que el usuario aporta",
        "hypothesis": "hypothesis: una posible causa aún sin confirmar",
        "hypothesis_discarded": "hypothesis_discarded: una hipótesis que los datos descartan",
        "validated_cause": "validated_cause: una causa confirmada por la evidencia",
    }
    return ToolSpec(
        name="log_event",
        description=(
            "Registra un hecho del análisis con una formulación breve y propia (no una cita"
            " literal). Tipos: " + "; ".join(meanings[t] for t in types) + "."
        ),
        parameters=_object(
            {
                "event_type": {"type": "string", "enum": list(types)},
                "content": _text(EVENT_CONTENT_MAX),
            }
        ),
    )


def add_action_tool() -> ToolSpec:
    return ToolSpec(
        name="add_action",
        description=(
            "Registra una acción acordada con el usuario, con su responsable y su fecha"
            " límite (AAAA-MM-DD). Confirma la acción con el usuario antes de registrarla."
            " El identificador de la acción se asigna al terminar el turno."
        ),
        parameters=_object(
            {
                "description": _text(ACTION_DESCRIPTION_MAX),
                "owner": _text(ACTION_OWNER_MAX),
                "due_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            }
        ),
    )


def update_action_tool() -> ToolSpec:
    return ToolSpec(
        name="update_action",
        description=(
            "Cambia el estado de una acción registrada del caso (pending o done), usando el"
            " identificador que aparece en el registro del caso."
        ),
        parameters=_object(
            {
                "action_id": {"type": "integer", "minimum": 1},
                "status": {"type": "string", "enum": list(ACTION_STATUSES)},
            }
        ),
    )


def propose_transition_tool(phase: Phase) -> ToolSpec:
    """`target_state` offers only the phases reachable from `phase`; the description gives
    each target's condition."""
    reachable = TRANSITIONS[phase]
    if not reachable:
        raise ValueError(f"propose_transition is not offered in phase {phase}")
    lines = "\n".join(f"- {target.phase}: {target.condition}" for target in reachable)
    return ToolSpec(
        name="propose_transition",
        description=(
            "Propone pasar el caso a otra fase. El sistema comprueba las condiciones y, si"
            " falta algo, rechaza la propuesta indicando qué falta. Fases posibles desde"
            f" aquí:\n{lines}"
        ),
        parameters=_object(
            {
                "target_state": {"type": "string", "enum": list(targets(phase))},
                "reasoning": _text(REASONING_MAX),
            }
        ),
    )


def tools_for_phase(phase: Phase) -> tuple[ToolSpec, ...]:
    """The tools offered in `phase`, in the order of `TOOL_NAMES` (none when closed)."""
    builders: dict[str, Callable[[], ToolSpec]] = {
        "record_field": record_field_tool,
        "log_event": lambda: log_event_tool(phase),
        "add_action": add_action_tool,
        "update_action": update_action_tool,
        "propose_transition": lambda: propose_transition_tool(phase),
    }
    return tuple(builders[name]() for name in TOOL_NAMES if phase in _PHASES_BY_TOOL[name])


# --- Execution ----------------------------------------------------------------


@dataclass(frozen=True)
class ToolOutcome:
    """What a tool call did. `result` is the JSON object sent back to the model; it may
    hold customer content, so it is left out of the repr."""

    name: str
    ok: bool
    error_code: str | None
    result: Mapping[str, Any] = field(repr=False)

    def content(self) -> str:
        """The result as the tool message's content."""
        return json.dumps(self.result, ensure_ascii=False)


def _error(name: str, code: str, detail: str, **extra: Any) -> ToolOutcome:
    return ToolOutcome(name, False, code, {"ok": False, "error": code, "detail": detail, **extra})


def _success(name: str, **result: Any) -> ToolOutcome:
    return ToolOutcome(name, True, None, {"ok": True, **result})


def clean_text(value: str) -> str:
    """Remove control characters (keeping newlines and tabs) and surrounding whitespace."""
    kept = (ch for ch in value if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    return "".join(kept).strip()


def _schema_errors(spec: ToolSpec, arguments: Mapping[str, Any]) -> list[str]:
    validator = Draft202012Validator(dict(spec.parameters))
    errors = sorted(validator.iter_errors(dict(arguments)), key=lambda e: list(e.path))
    found = []
    for error in errors:
        where = "/".join(str(part) for part in error.path) or "(arguments)"
        message = error.message
        if len(message) > _SCHEMA_DETAIL_MAX:
            message = message[: _SCHEMA_DETAIL_MAX - 3] + "..."
        found.append(f"{where}: {message}")
    return found


def execute_tool(
    snapshot: CaseSnapshot,
    changes: TurnChanges,
    call: ToolCall,
    *,
    allow_transition: bool = True,
) -> ToolOutcome:
    """Validate and run one tool call on the snapshot, recording what it changed.

    `allow_transition=False` (the engine's phase-hop cap) makes `propose_transition` answer
    `phase_hop_limit` without checking anything.
    """
    phase = snapshot.case.state
    name = call.name
    if name not in TOOL_NAMES:
        return _error(name, "unknown_tool", f"there is no tool named {name!r}")
    offered = {spec.name: spec for spec in tools_for_phase(phase)}
    spec = offered.get(name)
    if spec is None:
        return _error(name, "tool_not_offered", f"{name} is not available in phase {phase}")
    if call.arguments is None:
        return _error(
            name, "invalid_json", f"the arguments are not valid JSON: {call.arguments_error}"
        )
    schema_errors = _schema_errors(spec, call.arguments)
    if schema_errors:
        return _error(name, "invalid_arguments", "; ".join(schema_errors))
    arguments = dict(call.arguments)
    for key in _TEXT_ARGUMENTS[name]:
        arguments[key] = clean_text(arguments[key])
        if not arguments[key]:
            return _error(name, "invalid_arguments", f"{key}: is empty")
    handler = _HANDLERS[name]
    return handler(snapshot, changes, arguments, allow_transition)


def _record_field(
    snapshot: CaseSnapshot, changes: TurnChanges, args: dict[str, Any], _: bool
) -> ToolOutcome:
    name = args["field"]
    previous = snapshot.case.get_field(name)
    snapshot.case.set_field(name, args["value"])
    changes.fields[name] = args["value"]
    return _success("record_field", field=name, overwrote=bool((previous or "").strip()))


def _log_event(
    snapshot: CaseSnapshot, changes: TurnChanges, args: dict[str, Any], _: bool
) -> ToolOutcome:
    event = Event(
        role="assistant",
        event_type=args["event_type"],
        content=args["content"],
        state_at_time=snapshot.case.state,
    )
    snapshot.events.append(event)
    changes.new_events.append(event)
    return _success("log_event", event_type=event.event_type)


def _add_action(
    snapshot: CaseSnapshot, changes: TurnChanges, args: dict[str, Any], _: bool
) -> ToolOutcome:
    try:
        due_date = date.fromisoformat(args["due_date"])
    except ValueError:
        return _error("add_action", "invalid_date", "due_date is not a real date (YYYY-MM-DD)")
    action = Action(description=args["description"], owner=args["owner"], due_date=due_date)
    snapshot.actions.append(action)
    changes.new_actions.append(action)
    return _success("add_action", due_date=due_date.isoformat(), status=action.status)


def _update_action(
    snapshot: CaseSnapshot, changes: TurnChanges, args: dict[str, Any], _: bool
) -> ToolOutcome:
    action_id = int(args["action_id"])
    action = snapshot.find_action(action_id)
    if action is None:
        return _error(
            "update_action", "action_not_found", f"no recorded action {action_id} in this case"
        )
    status = args["status"]
    changed = action.status != status
    if changed:
        action.status = status
        changes.action_updates[action_id] = status
    return _success("update_action", action_id=action_id, status=status, changed=changed)


def _propose_transition(
    snapshot: CaseSnapshot, changes: TurnChanges, args: dict[str, Any], allow_transition: bool
) -> ToolOutcome:
    name = "propose_transition"
    if not allow_transition:
        return _error(
            name,
            "phase_hop_limit",
            "the phase already changed in this turn; it can change again on the next message",
        )
    source: Phase = snapshot.case.state
    target: Phase = args["target_state"]
    if not is_allowed(source, target):  # the enum already prevents it; kept as a guard
        return _error(name, "transition_not_allowed", f"{source} cannot move to {target}")
    missing = missing_for(snapshot, target)
    if missing:
        return _error(name, "criteria_not_met", describe_missing(missing), missing=missing)
    snapshot.case.state = target
    changes.transitions.append(Transition(source, target))
    return _success(name, previous_phase=source, phase=target)


_HANDLERS: dict[str, Callable[[CaseSnapshot, TurnChanges, dict[str, Any], bool], ToolOutcome]] = {
    "record_field": _record_field,
    "log_event": _log_event,
    "add_action": _add_action,
    "update_action": _update_action,
    "propose_transition": _propose_transition,
}

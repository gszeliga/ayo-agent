"""Draft scenarios for the tool-calling check.

DRAFT: the system prompts, tool descriptions and tool schemas below only exercise the
machinery and compare models on tool-calling discipline. They are NOT the production
prompts or tools: those will be written with AYO consultants and finalized with the
conversation engine. Scenario texts are in Spanish, like the users.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from ayo_copilot.llm.fake import tool_call
from ayo_copilot.llm.types import Message, ToolSpec

PHASES = ("understand", "challenge", "analyse", "action", "follow_up")
FIELDS = ("what", "where", "since", "standard")
EVENT_TYPES = ("evidence", "hypothesis", "hypothesis_discarded", "validated_cause")


# --- Draft tools ------------------------------------------------------------


def record_field_tool() -> ToolSpec:
    return ToolSpec(
        name="record_field",
        description=(
            "Registra uno de los cuatro datos que definen el problema, solo cuando el usuario"
            " lo ha dicho de forma clara: qué ocurre (what), dónde (where), desde cuándo"
            " (since) y cuál es el estándar esperado (standard)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": list(FIELDS)},
                "value": {"type": "string", "minLength": 1},
            },
            "required": ["field", "value"],
            "additionalProperties": False,
        },
    )


def log_event_tool() -> ToolSpec:
    return ToolSpec(
        name="log_event",
        description=(
            "Registra un hecho del análisis: una evidencia con datos (evidence), una hipótesis"
            " (hypothesis), una hipótesis descartada por los datos (hypothesis_discarded) o una"
            " causa validada con evidencia (validated_cause)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "event_type": {"type": "string", "enum": list(EVENT_TYPES)},
                "content": {"type": "string", "minLength": 1},
            },
            "required": ["event_type", "content"],
            "additionalProperties": False,
        },
    )


def propose_transition_tool(targets: Sequence[str]) -> ToolSpec:
    """Its `target_state` enum changes per scenario, as it will in production: only the
    transitions allowed from the current phase are offered."""
    return ToolSpec(
        name="propose_transition",
        description=(
            "Propone pasar el caso a otra fase cuando se cumplen sus condiciones. El sistema"
            " valida la propuesta y puede rechazarla."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target_state": {"type": "string", "enum": list(targets)},
                "reasoning": {"type": "string", "minLength": 1},
            },
            "required": ["target_state", "reasoning"],
            "additionalProperties": False,
        },
    )


def add_action_tool() -> ToolSpec:
    return ToolSpec(
        name="add_action",
        description="Registra una acción acordada, con responsable y fecha límite.",
        parameters={
            "type": "object",
            "properties": {
                "description": {"type": "string", "minLength": 1},
                "owner": {"type": "string", "minLength": 1},
                "due_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            },
            "required": ["description", "owner", "due_date"],
            "additionalProperties": False,
        },
    )


# --- Expectations -----------------------------------------------------------


@dataclass(frozen=True)
class ValueRule:
    """Calls to `tool` whose `field` argument is (or must be) one of `values`."""

    tool: str
    field: str
    values: frozenset[str]


@dataclass(frozen=True)
class Expectations:
    """What a response must do, beyond the checks applied to every call (offered tool,
    valid JSON, valid against the schema)."""

    # At least one call to one of these tools.
    must_call_any: frozenset[str] = frozenset()
    # No tool call at all.
    must_call_none: bool = False
    # None of these tools may be called.
    forbidden_tools: frozenset[str] = frozenset()
    # No call may set the field to one of these values.
    forbidden_values: tuple[ValueRule, ...] = ()
    # At least one call to the tool with the field set to one of these values.
    required_values: tuple[ValueRule, ...] = ()
    # Together, the calls to the tool set the field to every one of these values.
    must_cover: ValueRule | None = None
    # The text asks something: contains "?". A crude heuristic for "asks for evidence or
    # clarification"; judging the question itself is out of scope.
    needs_question: bool = False

    def tools_named(self) -> set[str]:
        rules = [*self.forbidden_values, *self.required_values]
        if self.must_cover is not None:
            rules.append(self.must_cover)
        return {*self.must_call_any, *self.forbidden_tools, *(r.tool for r in rules)}


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    phase: str
    system: str = field(repr=False)
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...]
    expectations: Expectations

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self.tools]


# --- Draft system prompts ---------------------------------------------------

_BASE = (
    "Eres el copiloto AYO, que guía a un equipo de planta industrial en la resolución"
    " estructurada de un problema, fase a fase: Entender, Cuestionar, Analizar, Actuar y"
    " Seguimiento. Respondes en español, de forma breve. Usas las herramientas solo cuando"
    " corresponde; nunca cambias de fase escribiendo texto, solo con propose_transition."
)

_PHASE_PROMPTS = {
    "understand": (
        "Fase actual: Entender. Objetivo: definir el problema con cuatro datos: qué ocurre,"
        " dónde, desde cuándo y cuál es el estándar. Registra cada dato con record_field"
        " cuando el usuario lo dé con claridad. Si el mensaje es vago, pregunta lo que falta."
        " Cuando los cuatro datos estén registrados y el usuario los confirme, propone pasar"
        " a la fase Cuestionar (challenge)."
    ),
    "challenge": (
        "Fase actual: Cuestionar. Objetivo: separar hechos de opiniones. Toda causa que el"
        " usuario proponga es una hipótesis hasta que haya datos. Pide evidencia concreta."
        " Registra evidencias, hipótesis e hipótesis descartadas con log_event. No valides"
        " causas en esta fase."
    ),
    "analyse": (
        "Fase actual: Analizar. Objetivo: confirmar la causa raíz con evidencia. Cuando una"
        " causa esté respaldada por datos verificados, regístrala con log_event como"
        " validated_cause."
    ),
}


def _system(phase: str, context: str = "") -> str:
    parts = [_BASE, _PHASE_PROMPTS[phase]]
    if context:
        parts.append(context)
    return "\n\n".join(parts)


_RECORDED_FIELDS = (
    "Datos ya registrados en el caso:\n"
    "- what: bolsas mal selladas en la selladora 3\n"
    "- where: línea 3 de envasado, planta de Burgos\n"
    "- since: lunes 3 de noviembre, turno de noche\n"
    "- standard: menos del 0,5 % de rechazo por sellado"
)


def _user(text: str) -> Message:
    return Message(role="user", content=text)


def _assistant(text: str) -> Message:
    return Message(role="assistant", content=text)


# --- The scenarios ----------------------------------------------------------


def build_scenarios() -> tuple[Scenario, ...]:
    """The nine draft scenarios, in a stable order (their ids appear in reports)."""
    understand_tools = (record_field_tool(), propose_transition_tool(["challenge"]))
    challenge_tools = (log_event_tool(), propose_transition_tool(["analyse"]))
    analyse_tools = (log_event_tool(), propose_transition_tool(["action"]), add_action_tool())
    rejected_call = tool_call(
        "propose_transition",
        {
            "target_state": "analyse",
            "reasoning": "El usuario identifica al operador nuevo como causa del problema.",
        },
        call_id="call_transition_1",
    )

    return (
        Scenario(
            id="understand_all_facts",
            title="Entender: el usuario da los cuatro datos con claridad",
            phase="understand",
            system=_system("understand"),
            messages=(
                _user(
                    "La selladora 3 está dejando bolsas mal selladas. Pasa en la línea 3 de"
                    " envasado de la planta de Burgos, desde el lunes 3 de noviembre en el"
                    " turno de noche. El estándar es menos del 0,5 % de rechazo por sellado"
                    " y ahora estamos en el 4,2 %."
                ),
            ),
            tools=understand_tools,
            expectations=Expectations(
                must_call_any=frozenset({"record_field"}),
                must_cover=ValueRule("record_field", "field", frozenset(FIELDS)),
            ),
        ),
        Scenario(
            id="understand_vague",
            title="Entender: mensaje vago, hay que preguntar",
            phase="understand",
            system=_system("understand"),
            messages=(_user("Tenemos problemas de calidad."),),
            tools=understand_tools,
            expectations=Expectations(must_call_none=True, needs_question=True),
        ),
        Scenario(
            id="understand_confirmed",
            title="Entender: datos completos y confirmados, proponer Cuestionar",
            phase="understand",
            system=_system("understand", _RECORDED_FIELDS),
            messages=(
                _assistant(
                    "Tengo registrados los cuatro datos del problema. ¿Los confirmas antes de"
                    " seguir?"
                ),
                _user("Sí, son correctos. Podemos seguir."),
            ),
            tools=understand_tools,
            expectations=Expectations(
                must_call_any=frozenset({"propose_transition"}),
                required_values=(
                    ValueRule("propose_transition", "target_state", frozenset({"challenge"})),
                ),
            ),
        ),
        Scenario(
            id="challenge_cause_without_data",
            title="Cuestionar: causa afirmada sin datos, pedir evidencia",
            phase="challenge",
            system=_system("challenge", _RECORDED_FIELDS),
            messages=(
                _user(
                    "Está clarísimo: es el operador nuevo del turno de noche. Empezó justo esa"
                    " semana."
                ),
            ),
            tools=challenge_tools,
            expectations=Expectations(
                forbidden_tools=frozenset({"propose_transition"}),
                forbidden_values=(
                    ValueRule("log_event", "event_type", frozenset({"validated_cause"})),
                ),
                needs_question=True,
            ),
        ),
        Scenario(
            id="challenge_contradicting_data",
            title="Cuestionar: los datos contradicen la hipótesis anterior",
            phase="challenge",
            system=_system(
                "challenge",
                _RECORDED_FIELDS + "\n\nHipótesis registrada: el problema viene del cambio de"
                " proveedor de film de la semana pasada.",
            ),
            messages=(
                _user(
                    "Hemos revisado los lotes de las dos últimas semanas: con el film del"
                    " proveedor antiguo el rechazo fue del 4,1 % y con el nuevo del 4,3 %."
                    " Prácticamente igual."
                ),
            ),
            tools=challenge_tools,
            expectations=Expectations(
                required_values=(
                    ValueRule(
                        "log_event",
                        "event_type",
                        frozenset({"evidence", "hypothesis_discarded"}),
                    ),
                ),
            ),
        ),
        Scenario(
            id="analyse_validated_cause",
            title="Analizar: causa respaldada por evidencia",
            phase="analyse",
            system=_system(
                "analyse",
                _RECORDED_FIELDS + "\n\nHipótesis abierta: temperatura de sellado"
                " insuficiente en la mordaza.",
            ),
            messages=(
                _user(
                    "Hicimos el ensayo: subiendo la temperatura de la mordaza de 165 a 180 °C"
                    " el rechazo bajó del 4,2 % al 0,6 % durante tres turnos, y al volver a"
                    " 165 °C volvió a subir al 4 %. La causa es la temperatura de sellado"
                    " insuficiente."
                ),
            ),
            tools=analyse_tools,
            expectations=Expectations(
                required_values=(
                    ValueRule("log_event", "event_type", frozenset({"validated_cause"})),
                ),
            ),
        ),
        Scenario(
            id="enum_skip_ahead",
            title="Enum: el usuario insiste en saltar a Actuar; solo se permite Cuestionar",
            phase="understand",
            system=_system("understand", _RECORDED_FIELDS),
            messages=(
                _user(
                    "Ya sabemos que es la temperatura, no perdamos tiempo. Pasa directamente a"
                    " definir acciones."
                ),
            ),
            tools=understand_tools,
            # Only the every-call checks: any propose_transition must use the one allowed
            # target (the schema's enum), or there must be no call.
            expectations=Expectations(),
        ),
        Scenario(
            id="greeting",
            title="Saludo sin contenido del problema",
            phase="understand",
            system=_system("understand"),
            messages=(_user("¡Hola! Buenos días, ¿qué tal?"),),
            tools=understand_tools,
            expectations=Expectations(must_call_none=True),
        ),
        Scenario(
            id="rejected_transition",
            title="Resultado de herramienta: transición rechazada por falta de evidencia",
            phase="challenge",
            system=_system("challenge", _RECORDED_FIELDS),
            messages=(
                _user("Ya está claro, es el operador nuevo. Pasemos al análisis."),
                Message(role="assistant", tool_calls=(rejected_call,)),
                Message(
                    role="tool",
                    tool_call_id=rejected_call.id,
                    content=(
                        '{"status": "rejected", "reason": "missing_evidence", "detail":'
                        ' "Para pasar a Analizar hace falta al menos una evidencia registrada'
                        ' que apoye o descarte la hipótesis."}'
                    ),
                ),
            ),
            tools=challenge_tools,
            expectations=Expectations(
                forbidden_tools=frozenset({"propose_transition"}),
                needs_question=True,
            ),
        ),
    )

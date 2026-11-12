"""The in-memory case a turn works on, and the changes the turn accepted.

The engine loads a `CaseSnapshot` at the start of a turn; tool handlers change it, so that
exit criteria see what was accepted earlier in the same turn, and record each change in
`TurnChanges`, which the repository commits in one transaction at the end of the turn.
Nothing here touches the database.

Field values, event content and action text are customer content: they are left out of
every `repr`.
"""

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal
from uuid import UUID

Phase = Literal["understand", "challenge", "analyse", "action", "followup", "closed"]
PHASES: tuple[Phase, ...] = ("understand", "challenge", "analyse", "action", "followup", "closed")

# The four facts, as the model names them. `where` is stored as `where_` (a reserved word).
FieldName = Literal["what", "where", "since", "standard"]
FIELDS: tuple[FieldName, ...] = ("what", "where", "since", "standard")
FIELD_COLUMNS: dict[str, str] = {
    "what": "what",
    "where": "where_",
    "since": "since",
    "standard": "standard",
}

EventType = Literal["message", "evidence", "hypothesis", "hypothesis_discarded", "validated_cause"]
# The annotation types `log_event` can record (every event type but `message`).
ANNOTATION_TYPES: tuple[EventType, ...] = (
    "evidence",
    "hypothesis",
    "hypothesis_discarded",
    "validated_cause",
)

ActionStatus = Literal["pending", "done"]
ACTION_STATUSES: tuple[ActionStatus, ...] = ("pending", "done")


def clean_text(value: str) -> str:
    """Remove control characters (keeping newlines and tabs) and surrounding whitespace."""
    kept = (ch for ch in value if ch in "\n\t" or unicodedata.category(ch) != "Cc")
    return "".join(kept).strip()


@dataclass
class Case:
    """A problem being solved: its phase, the four facts and the version read at load."""

    id: UUID
    tenant: str
    state: Phase
    what: str | None = field(default=None, repr=False)
    where_: str | None = field(default=None, repr=False)
    since: str | None = field(default=None, repr=False)
    standard: str | None = field(default=None, repr=False)
    version: int = 0

    def get_field(self, name: FieldName) -> str | None:
        return getattr(self, FIELD_COLUMNS[name])

    def set_field(self, name: FieldName, value: str) -> None:
        setattr(self, FIELD_COLUMNS[name], value)

    def missing_fields(self) -> list[FieldName]:
        """The facts still empty, in the order of `FIELDS`."""
        return [name for name in FIELDS if not (self.get_field(name) or "").strip()]


@dataclass
class Event:
    """A message or an annotation. `id` and `created_at` are None until committed."""

    role: Literal["user", "assistant"]
    event_type: EventType
    content: str = field(repr=False)
    state_at_time: Phase
    id: int | None = None
    created_at: datetime | None = None


@dataclass
class Action:
    """An agreed action. `id` is None until committed (an action added in this turn)."""

    description: str = field(repr=False)
    owner: str = field(repr=False)
    due_date: date
    status: ActionStatus = "pending"
    id: int | None = None

    def is_overdue(self, today: date) -> bool:
        """Pending and past its due date (computed, never stored)."""
        return self.status == "pending" and self.due_date < today


@dataclass
class CaseSnapshot:
    """The case, its events (oldest first) and its actions, as the turn sees them."""

    case: Case
    events: list[Event] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)

    def has_event(self, event_type: EventType) -> bool:
        return any(event.event_type == event_type for event in self.events)

    def find_action(self, action_id: int) -> Action | None:
        """A stored action of this case by id (actions added in this turn have no id)."""
        return next((a for a in self.actions if a.id is not None and a.id == action_id), None)


@dataclass(frozen=True)
class Transition:
    source: Phase
    target: Phase


@dataclass
class TurnChanges:
    """What the turn accepted, in order, for the commit.

    `fields` holds the last value set per fact (model names). `new_events` are annotation
    events (the user message and the reply are added by the engine). `new_actions` are the
    `Action` objects also appended to the snapshot; `action_updates` maps a stored action id
    to its new status.
    """

    fields: dict[FieldName, str] = field(default_factory=dict, repr=False)
    new_events: list[Event] = field(default_factory=list)
    new_actions: list[Action] = field(default_factory=list)
    action_updates: dict[int, ActionStatus] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.fields
            or self.new_events
            or self.new_actions
            or self.action_updates
            or self.transitions
        )

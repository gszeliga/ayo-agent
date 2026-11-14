"""Channels: where messages come from (the web UI now; Slack or Google Chat later).

An adapter turns a channel's raw input into an `IncomingMessage` and the engine's result
into what the channel sends back. `handle_message` resolves the case from the message's
channel key and runs the turn; the engine never knows which channel a message came from.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from psycopg_pool import ConnectionPool

from ayo_copilot.conversation.engine import TurnEngine, TurnResult
from ayo_copilot.conversation.store import ChannelKey, resolve_case

WEB_CHANNEL = "web"
# Decision 4: one constant channel id, the session is the thread. Using the tenant here
# would open a new case on a tenant mismatch instead of rejecting it.
WEB_CHANNEL_ID = "web"


@dataclass(frozen=True)
class IncomingMessage:
    """One user message, whatever the channel. `text` is customer content."""

    channel_type: str
    external_channel_id: str
    # The conversation within the channel: for the web, the session id.
    external_thread_id: str
    user_id: str | None
    text: str = field(repr=False)
    tenant: str

    @property
    def key(self) -> ChannelKey:
        return ChannelKey(self.channel_type, self.external_channel_id, self.external_thread_id)


class ChannelAdapter(Protocol):
    def parse(self, raw: Mapping[str, Any]) -> IncomingMessage: ...

    def deliver(self, incoming: IncomingMessage, result: TurnResult) -> object:
        """What the channel sends back (the web: the response body)."""
        ...


def web_key(session_id: str) -> ChannelKey:
    return ChannelKey(WEB_CHANNEL, WEB_CHANNEL_ID, session_id)


class WebAdapter:
    """The web UI. Input is the validated request body, so parsing only maps it."""

    def parse(self, raw: Mapping[str, Any]) -> IncomingMessage:
        return IncomingMessage(
            channel_type=WEB_CHANNEL,
            external_channel_id=WEB_CHANNEL_ID,
            external_thread_id=str(raw["session_id"]),
            user_id=raw.get("user_id"),
            text=raw["text"],
            tenant=raw["tenant"],
        )

    def deliver(self, incoming: IncomingMessage, result: TurnResult) -> dict[str, Any]:
        return {
            "session_id": incoming.external_thread_id,
            "reply": result.reply,
            "phase": result.phase_after,
            "previous_phase": result.phase_before,
            "phase_changed": result.phase_after != result.phase_before,
            "turn": result.turn_no,
            "tools_used": [{"name": tool.name, "ok": tool.ok} for tool in result.tools_used],
        }


def handle_message(
    engine: TurnEngine, pool: ConnectionPool, incoming: IncomingMessage
) -> TurnResult:
    """Find or create the conversation's case, then run the turn. Raises
    `CaseTenantMismatch` (nothing created) and whatever `TurnEngine.handle_turn` raises."""
    case = resolve_case(pool, incoming.key, tenant=incoming.tenant, created_by=incoming.user_id)
    return engine.handle_turn(case.problem_id, incoming.text)

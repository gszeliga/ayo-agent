"""The reply sent to the user: the texts of the turn's model calls, in order."""

from collections.abc import Iterable

# Sent when a cap (tool rounds, time) stops the turn before a final text, or when the
# model gave no text at all. What was accepted before the cap is still committed.
FALLBACK_REPLY = (
    "No he podido terminar de procesar tu mensaje. Lo que ya estaba claro ha quedado"
    " guardado; ¿puedes continuar o reformularlo?"
)


# The reply of a turn that closed the case when the model said nothing.
CLOSED_REPLY = "Caso cerrado. Si el problema vuelve a aparecer, abre una conversación nueva."


def compose_reply(texts: Iterable[str | None], *, capped: bool, closed: bool = False) -> str:
    """The non-empty texts, trimmed and joined by a blank line; the fallback is appended
    when the turn was capped, and replaces a reply that would be empty. A turn that closed
    the case and has no text gets `CLOSED_REPLY` instead."""
    parts = [text.strip() for text in texts if text and text.strip()]
    if closed and not parts and not capped:
        return CLOSED_REPLY
    if capped or not parts:
        parts.append(FALLBACK_REPLY)
    return "\n\n".join(parts)

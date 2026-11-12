"""The reply sent to the user: the texts of the turn's model calls, in order."""

from collections.abc import Iterable

# Sent when a cap (tool rounds, time) stops the turn before a final text, or when the
# model gave no text at all. What was accepted before the cap is still committed.
FALLBACK_REPLY = (
    "No he podido terminar de procesar tu mensaje. Lo que ya estaba claro ha quedado"
    " guardado; ¿puedes continuar o reformularlo?"
)


def compose_reply(texts: Iterable[str | None], *, capped: bool) -> str:
    """The non-empty texts, trimmed and joined by a blank line; the fallback is appended
    when the turn was capped, and replaces a reply that would be empty."""
    parts = [text.strip() for text in texts if text and text.strip()]
    if capped or not parts:
        parts.append(FALLBACK_REPLY)
    return "\n\n".join(parts)

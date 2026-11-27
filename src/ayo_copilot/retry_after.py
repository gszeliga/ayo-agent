"""`Retry-After` parsing, shared by the HTTP clients that retry (OpenRouter, Voyage)."""

from email.utils import parsedate_to_datetime


def parse_retry_after(value: str | None, *, now: float) -> float | None:
    """Seconds to wait from a `Retry-After` header: a number of seconds or an HTTP date.
    None when absent or unreadable; a date in the past means no wait."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - now
        except (TypeError, ValueError, IndexError):
            return None
    if seconds != seconds:  # NaN
        return None
    return max(0.0, seconds)

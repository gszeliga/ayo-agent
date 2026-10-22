import re
import unicodedata

TENANT_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
SOURCE_KEY_MAX_LENGTH = 255


class InvalidInputError(ValueError):
    """Raised when an upload parameter is not acceptable (translated to HTTP 422)."""


def validate_tenant(tenant: str) -> str:
    # fullmatch, because `$` alone would accept a trailing newline.
    if not re.fullmatch(TENANT_PATTERN, tenant):
        raise InvalidInputError(f"tenant must match {TENANT_PATTERN}")
    return tenant


def normalize_source_key(raw: str) -> str:
    """Reduce a client-supplied name to a bare, NFC-normalized file name."""
    name = unicodedata.normalize("NFC", raw)
    if any(unicodedata.category(char) == "Cc" for char in name):
        raise InvalidInputError("source_key must not contain control characters")
    # Clients may send a full path from any OS; keep only the last component.
    name = re.split(r"[/\\]", name)[-1].strip()
    if name in ("", ".", ".."):
        raise InvalidInputError("source_key must contain a file name")
    if len(name) > SOURCE_KEY_MAX_LENGTH:
        raise InvalidInputError(f"source_key must be at most {SOURCE_KEY_MAX_LENGTH} characters")
    return name

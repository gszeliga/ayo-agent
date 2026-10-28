import re
import unicodedata

TENANT_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
SOURCE_KEY_MAX_LENGTH = 255


class InvalidInputError(ValueError):
    """Raised when an upload parameter is not acceptable (translated to HTTP 422).

    `field` names the upload field at fault and `code` is a stable, machine-readable
    error type; both end up in the API error body.
    """

    def __init__(self, message: str, *, field: str, code: str) -> None:
        super().__init__(message)
        self.field = field
        self.code = code


def validate_tenant(tenant: str) -> str:
    # fullmatch, because `$` alone would accept a trailing newline.
    if not re.fullmatch(TENANT_PATTERN, tenant):
        raise InvalidInputError(
            f"tenant must match {TENANT_PATTERN}", field="tenant", code="tenant_invalid"
        )
    return tenant


def normalize_source_key(raw: str) -> str:
    """Reduce a client-supplied name to a bare, NFC-normalized file name."""
    name = unicodedata.normalize("NFC", raw)
    if any(unicodedata.category(char) == "Cc" for char in name):
        raise InvalidInputError(
            "source_key must not contain control characters",
            field="source_key",
            code="source_key_invalid",
        )
    # Clients may send a full path from any OS; keep only the last component.
    name = re.split(r"[/\\]", name)[-1].strip()
    if name in ("", ".", ".."):
        raise InvalidInputError(
            "source_key must contain a file name", field="source_key", code="source_key_invalid"
        )
    if len(name) > SOURCE_KEY_MAX_LENGTH:
        raise InvalidInputError(
            f"source_key must be at most {SOURCE_KEY_MAX_LENGTH} characters",
            field="source_key",
            code="source_key_invalid",
        )
    return name

import os
import re
import tempfile
import unicodedata
from pathlib import Path

TENANT_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
SOURCE_KEY_MAX_LENGTH = 255
DOC_ID_PATTERN = r"^upload-[0-9a-f]{12}$"


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


def markdown_path(knowledge_dir: Path, tenant: str, doc_id: str) -> Path:
    validate_tenant(tenant)
    if not re.fullmatch(DOC_ID_PATTERN, doc_id):
        raise InvalidInputError("doc_id has an unexpected format")
    path = knowledge_dir / tenant / "upload" / f"{doc_id}.md"
    if not path.resolve().is_relative_to(knowledge_dir.resolve()):
        raise InvalidInputError("markdown path escapes the knowledge directory")
    return path


def write_markdown_atomic(knowledge_dir: Path, tenant: str, doc_id: str, text: str) -> Path:
    """Write the file via a temporary sibling and a rename, so readers never see a partial file."""
    path = markdown_path(knowledge_dir, tenant, doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{doc_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path

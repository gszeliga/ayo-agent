"""Uploading one Markdown file to `POST /admin/documents`, and what the API answered.

A per-file refusal (413, 422, 502, ...) is an `UploadRejectedError`: the run goes on. A
failure every later file would share (a wrong key, a wrong URL, the API unreachable) is an
`UploadAbortedError`: the run stops. Messages hold the API's error `type` and `msg`, which
carry no document content; the key is never part of one.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx2
from pydantic import SecretStr

UPLOAD_PATH = "/admin/documents"
# The server chunks and embeds during the request: a large document takes a while.
READ_TIMEOUT_SECONDS = 120.0
CONNECT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class Uploaded:
    status: Literal["indexed", "up_to_date"]
    doc_id: str
    chunk_count: int | None = None


class UploadRejectedError(Exception):
    """The API refused this file; later files may still go through."""


class UploadAbortedError(Exception):
    """No later upload can succeed either: stop the run."""


def api_origin(api_url: str) -> str:
    """`scheme://host[:port]` of the API, for display (never credentials or a path)."""
    parts = urlsplit(api_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"not an http(s) URL: {api_url!r}")
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


class Uploader:
    def __init__(
        self, api_url: str, api_key: SecretStr, *, client: httpx2.Client | None = None
    ) -> None:
        self._client = client or httpx2.Client(
            base_url=api_url,
            timeout=httpx2.Timeout(READ_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS),
        )
        self._key = api_key

    def upload(self, markdown: Path, *, tenant: str, source_key: str, force: bool) -> Uploaded:
        content = markdown.read_bytes()
        try:
            response = self._client.post(
                UPLOAD_PATH,
                headers={"X-API-Key": self._key.get_secret_value()},
                files={"file": (markdown.name, content, "text/markdown")},
                data={
                    "tenant": tenant,
                    "source_key": source_key,
                    "force": "true" if force else "false",
                },
            )
        except httpx2.TransportError as error:
            raise UploadAbortedError(f"cannot reach the API ({type(error).__name__})") from None

        if response.status_code in (200, 201):
            body = response.json()
            return Uploaded(body["status"], body["doc_id"], body.get("chunk_count"))
        reason = _api_error(response)
        if response.status_code == 401:
            raise UploadAbortedError(f"the API refused the key ({reason})")
        if response.status_code in (404, 405):
            raise UploadAbortedError(f"no upload endpoint at this URL ({reason})")
        raise UploadRejectedError(reason)

    def close(self) -> None:
        self._client.close()


def _api_error(response: httpx2.Response) -> str:
    """`<status> <type>: <msg>` from the API's error body, else the status alone."""
    try:
        first = response.json()["detail"][0]
        return f"{response.status_code} {first['type']}: {first['msg']}"
    except (ValueError, KeyError, IndexError, TypeError):
        return f"HTTP {response.status_code}"

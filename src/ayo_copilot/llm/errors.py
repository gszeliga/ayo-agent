"""Failures of a language model provider.

Messages are safe by construction: a fixed text plus a status or an exception type name.
They never hold the API key, message content, tool arguments or a response body (an error
body can echo the prompt).
"""


class LLMError(Exception):
    """A language model call failed.

    - `status`: the HTTP status, when there was one (200 for an error inside a 200 body).
    - `reason`: a short safe tag for logs, such as `http_429`, `body_502`, `timeout`.
    - `retry_after`: seconds the provider asked us to wait (`Retry-After`), if it did.
    - `generation_id`: the provider's id for the failed attempt, if it sent one.
    - `attempts` and `generation_ids`: set on the error a call finally raises, covering
      every attempt (ids only for the attempts that had one).
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        reason: str | None = None,
        retry_after: float | None = None,
        generation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.retry_after = retry_after
        self.generation_id = generation_id
        self.attempts = 1
        self.generation_ids: tuple[str, ...] = (generation_id,) if generation_id else ()


class LLMConfigError(LLMError):
    """The provider is not configured (for example, no API key). Raised on first use, not
    at startup: the rest of the app works without a language model."""


class LLMAuthError(LLMError):
    """The provider refused the API key (HTTP 401). Never retried."""


class LLMInsufficientCreditsError(LLMError):
    """The account has no credits left (HTTP 402). Never retried."""


class LLMRateLimitError(LLMError):
    """Still rate limited (HTTP 429) after the allowed retries."""


class LLMUnavailableError(LLMError):
    """The provider or model could not answer: timeouts, connection errors or HTTP 5xx,
    after the allowed retries."""


class LLMBadRequestError(LLMError):
    """The provider rejected the request as built (HTTP 400, or 403 for a moderation or
    guardrail block). Never retried: the same request fails the same way."""


class LLMResponseError(LLMError):
    """The provider answered 200 with a body we cannot use: malformed, empty, or an error
    object instead of a completion."""

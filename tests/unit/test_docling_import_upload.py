"""`docling-import-files` uploads: the request, the API's answers, clashes, stops, exit codes.

Every request goes to an `httpx2.MockTransport`: no network, no cost.
"""

import io
import os
from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from ayo_copilot.docling_import.cli import main
from ayo_copilot.docling_import.upload import (
    UploadAbortedError,
    Uploader,
    UploadRejectedError,
    api_origin,
)

KEY = "clave-de-prueba-123"
API = "http://api.test:8000"
CONTENT = "# Procedimiento\n\nContenido confidencial del procedimiento\n"

Handler = Callable[[httpx2.Request], httpx2.Response]


def indexed(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(
        201, json={"doc_id": "upload-1890b5dc5335", "status": "indexed", "chunk_count": 5}
    )


def error(status: int, error_type: str, msg: str) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status, json={"detail": [{"type": error_type, "loc": ["body"], "msg": msg}]}
        )

    return handler


class FakeConverter:
    def __init__(self, failing: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.calls: list[Path] = []

    def to_markdown(self, source: Path) -> str:
        self.calls.append(source)
        if source.name in self.failing:
            raise ValueError("cannot parse")
        return CONTENT


class Recorder:
    """A MockTransport handler that records each request and answers with `answer(n)`."""

    def __init__(self, *answers: Handler) -> None:
        self.answers = answers
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        request.read()
        self.requests.append(request)
        answer = self.answers[min(len(self.requests), len(self.answers)) - 1]
        return answer(request)


def run(
    *argv: str,
    handler: Handler = indexed,
    converter: FakeConverter | None = None,
    api_key: str | None = KEY,
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()

    def make_uploader(url: str, key: SecretStr) -> Uploader:
        client = httpx2.Client(transport=httpx2.MockTransport(handler), base_url=url)
        return Uploader(url, key, client=client)

    code = main(
        list(argv),
        make_converter=lambda: converter or FakeConverter(),
        make_uploader=make_uploader,
        load_api_key=lambda: SecretStr(api_key) if api_key else None,
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def touch(path: Path, text: str = "x", *, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def form_fields(request: httpx2.Request) -> dict[str, str]:
    """The multipart form's text fields and the file's name and bytes, crudely parsed."""
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields: dict[str, str] = {}
    for part in request.content.split(b"--" + boundary)[1:-1]:
        head, _, body = part.removeprefix(b"\r\n").removesuffix(b"\r\n").partition(b"\r\n\r\n")
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        if b"filename=" in head:
            fields["filename"] = head.split(b'filename="')[1].split(b'"')[0].decode()
        fields[name] = body.decode()
    return fields


def test_converts_then_uploads_each_document(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "notas.md", CONTENT)
    recorder = Recorder(indexed)

    code, out, err = run(str(tmp_path), "--tenant", "acme", "--api-url", API, handler=recorder)

    assert code == 0 and err == ""
    assert len(recorder.requests) == 2
    request = recorder.requests[0]
    assert request.method == "POST" and str(request.url) == f"{API}/admin/documents"
    assert request.headers["x-api-key"] == KEY
    assert form_fields(request) == {
        "filename": "a.md",
        "file": CONTENT,
        "tenant": "acme",
        "source_key": "a.md",
        "force": "false",
    }
    assert out.splitlines() == [
        f"uploading to {API}, tenant acme",
        f"converting  (1/1) {tmp_path / 'a.pdf'} …",
        f"converted   {tmp_path / 'a.pdf'} -> {tmp_path / 'a.md'}",
        f"indexed     {tmp_path / 'a.md'} (upload-1890b5dc5335, 5 chunks)",
        f"as is       {tmp_path / 'notas.md'}",
        f"indexed     {tmp_path / 'notas.md'} (upload-1890b5dc5335, 5 chunks)",
        "2 documents: 1 converted, 1 as is; uploaded: 2 indexed",
    ]
    assert KEY not in out and "confidencial" not in out


def test_an_up_to_date_markdown_is_still_uploaded(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf", mtime=1_000)
    touch(tmp_path / "a.md", CONTENT, mtime=2_000)
    converter = FakeConverter()

    def unchanged(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"doc_id": "upload-1890b5dc5335", "status": "up_to_date"})

    code, out, _ = run(
        str(tmp_path),
        "--tenant",
        "acme",
        "--force",
        handler=Recorder(unchanged),
        converter=converter,
    )

    assert code == 0 and converter.calls == []
    assert f"unchanged   {tmp_path / 'a.md'} (upload-1890b5dc5335, already indexed)" in out
    assert out.splitlines()[-1] == "1 document: 1 up to date; uploaded: 1 unchanged"


def test_force_is_sent(tmp_path: Path) -> None:
    touch(tmp_path / "notas.md", CONTENT)
    recorder = Recorder(indexed)

    run(str(tmp_path), "--tenant", "acme", "--force", handler=recorder)

    assert form_fields(recorder.requests[0])["force"] == "true"


@pytest.mark.parametrize(
    ("status", "error_type", "msg"),
    [
        (413, "file_too_large", "file exceeds 5242880 bytes"),
        (422, "file_empty", "file is empty"),
        (502, "embedding_failed", "embedding provider failed"),
    ],
)
def test_a_refused_file_does_not_stop_the_run(
    tmp_path: Path, status: int, error_type: str, msg: str
) -> None:
    touch(tmp_path / "a.md", CONTENT)
    touch(tmp_path / "b.md", CONTENT)
    recorder = Recorder(error(status, error_type, msg), indexed)

    code, out, _ = run(str(tmp_path), "--tenant", "acme", handler=recorder)

    assert code == 1 and len(recorder.requests) == 2
    assert f"upload failed {tmp_path / 'a.md'} ({status} {error_type}: {msg})" in out
    assert out.splitlines()[-1] == "2 documents: 2 as is; uploaded: 1 indexed, 1 failed"


def test_a_wrong_key_stops_the_run(tmp_path: Path) -> None:
    for name in ("a.md", "b.md", "c.md"):
        touch(tmp_path / name, CONTENT)
    recorder = Recorder(error(401, "unauthorized", "missing or invalid API key"))

    code, out, err = run(str(tmp_path), "--tenant", "acme", handler=recorder)

    assert code == 2 and len(recorder.requests) == 1
    assert "the API refused the key (401 unauthorized" in err
    assert out.splitlines()[-1] == "3 documents: 1 as is; uploaded: 1 failed, 2 not attempted"
    assert KEY not in out + err


def test_an_unreachable_api_stops_the_run(tmp_path: Path) -> None:
    touch(tmp_path / "a.md", CONTENT)
    touch(tmp_path / "b.md", CONTENT)

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    code, out, err = run(str(tmp_path), "--tenant", "acme", handler=refuse)

    assert code == 2
    assert "cannot reach the API (ConnectError)" in err
    assert out.splitlines()[-1] == "2 documents: 1 as is; uploaded: 1 failed, 1 not attempted"


def test_a_failed_conversion_is_not_uploaded(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    touch(tmp_path / "b.pdf")
    recorder = Recorder(indexed)

    code, out, _ = run(
        str(tmp_path),
        "--tenant",
        "acme",
        handler=recorder,
        converter=FakeConverter(failing={"a.pdf"}),
    )

    assert code == 1 and len(recorder.requests) == 1
    assert form_fields(recorder.requests[0])["source_key"] == "b.md"
    assert out.splitlines()[-1] == "2 documents: 1 converted, 1 failed; uploaded: 1 indexed"


def test_same_file_names_in_subfolders_refuse_to_start(tmp_path: Path) -> None:
    touch(tmp_path / "x" / "a.pdf")
    touch(tmp_path / "y" / "a.md", CONTENT)
    recorder = Recorder(indexed)
    converter = FakeConverter()

    code, out, err = run(
        str(tmp_path), "-r", "--tenant", "acme", handler=recorder, converter=converter
    )

    assert code == 2 and out == ""
    assert "would replace each other" in err and "a.md" in err
    assert recorder.requests == [] and converter.calls == []


def test_the_clash_check_does_not_apply_without_upload(tmp_path: Path) -> None:
    touch(tmp_path / "x" / "a.pdf")
    touch(tmp_path / "y" / "a.md", CONTENT)

    code, _, _ = run(str(tmp_path), "-r", "--no-upload")

    assert code == 0


def test_a_missing_key_exits_2_before_converting(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    converter = FakeConverter()

    code, out, err = run(str(tmp_path), "--tenant", "acme", api_key=None, converter=converter)

    assert code == 2 and out == "" and converter.calls == []
    assert "ADMIN_API_KEY is not set" in err


def test_dry_run_shows_the_uploads_and_sends_nothing(tmp_path: Path) -> None:
    touch(tmp_path / "a.pdf")
    recorder = Recorder(indexed)

    code, out, _ = run(str(tmp_path), "--tenant", "acme", "--dry-run", handler=recorder)

    assert code == 0 and recorder.requests == []
    assert out.splitlines() == [
        f"would convert {tmp_path / 'a.pdf'} -> {tmp_path / 'a.md'}",
        f"would upload {tmp_path / 'a.md'} as a.md",
    ]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        ([], "--tenant is required"),
        (["--tenant", "ACME!"], "tenant must match"),
        (["--tenant", "acme", "--api-url", "ftp://x"], "not an http(s) URL"),
    ],
)
def test_bad_arguments_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    touch(tmp_path / "a.md", CONTENT)

    with pytest.raises(SystemExit) as raised:
        run(str(tmp_path), *argv)

    assert raised.value.code == 2
    assert message in capsys.readouterr().err


def test_api_origin_shows_no_credentials_or_path() -> None:
    assert api_origin("https://user:secret@kb.example.com:8443/base?x=1") == (
        "https://kb.example.com:8443"
    )


@pytest.mark.parametrize("status", [404, 405])
def test_a_url_without_the_endpoint_aborts(tmp_path: Path, status: int) -> None:
    md = touch(tmp_path / "a.md", CONTENT)
    client = httpx2.Client(
        transport=httpx2.MockTransport(lambda r: httpx2.Response(status, text="<html>")),
        base_url=API,
    )

    with pytest.raises(
        UploadAbortedError, match=f"no upload endpoint at this URL \\(HTTP {status}"
    ):
        Uploader(API, SecretStr(KEY), client=client).upload(
            md, tenant="acme", source_key="a.md", force=False
        )


def test_an_error_body_without_detail_shows_the_status(tmp_path: Path) -> None:
    md = touch(tmp_path / "a.md", CONTENT)
    client = httpx2.Client(
        transport=httpx2.MockTransport(lambda r: httpx2.Response(500, text="boom")),
        base_url=API,
    )

    with pytest.raises(UploadRejectedError, match=r"^HTTP 500$"):
        Uploader(API, SecretStr(KEY), client=client).upload(
            md, tenant="acme", source_key="a.md", force=False
        )


def test_the_api_url_may_have_a_path_prefix(tmp_path: Path) -> None:
    touch(tmp_path / "a.md", CONTENT)
    recorder = Recorder(indexed)

    run(str(tmp_path), "--tenant", "acme", "--api-url", f"{API}/kb", handler=recorder)

    assert str(recorder.requests[0].url) == f"{API}/kb/admin/documents"

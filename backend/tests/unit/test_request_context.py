"""The request-ID middleware and the logging set-up, on a small app with no database."""

import json
import logging
import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from gtm_studio.audit.context import bind_actor, get_request_context
from gtm_studio.audit.logging import configure_logging
from gtm_studio.audit.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from gtm_studio.settings import Settings

StderrLogs = Callable[[], list[dict[str, Any]]]


@pytest.fixture
def probe() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ok")
    def ok() -> dict[str, str | None]:
        context = get_request_context()
        return {"request_id": context.request_id if context else None}

    @app.get("/who")
    def who() -> dict[str, str]:
        bind_actor("user-42")  # as the `current_actor` dependency does
        return {}

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("kaboom")

    return app


def _access(lines: list[dict[str, Any]]) -> dict[str, Any]:
    [line] = [entry for entry in lines if entry["event"] == "request"]
    return line


# ------------------------------------------------------------------ the request ID


def test_a_request_id_is_generated_when_the_caller_sends_none(probe: FastAPI) -> None:
    response = TestClient(probe).get("/ok")
    request_id = response.headers[REQUEST_ID_HEADER]
    assert uuid.UUID(request_id).version == 4
    assert response.json() == {"request_id": request_id}  # the handler sees the same ID


def test_an_acceptable_inbound_request_id_is_kept(probe: FastAPI) -> None:
    sent = "trace-0123456789-abcdef"
    response = TestClient(probe).get("/ok", headers={REQUEST_ID_HEADER: sent})
    assert response.headers[REQUEST_ID_HEADER] == sent
    assert response.json() == {"request_id": sent}


@pytest.mark.parametrize(
    "sent",
    ["short", "a" * 65, "has space in it!", "under_score_not_allowed", "semi;colon-12345", "é" * 10, ""],
)
def test_an_unacceptable_inbound_request_id_is_replaced(probe: FastAPI, sent: str) -> None:
    # (An unacceptable ID could carry text into the logs, so it is never echoed.)
    # Bytes, because an `é` can't be sent as a str header.
    headers = {REQUEST_ID_HEADER.encode(): sent.encode("utf-8")}
    response = TestClient(probe).get("/ok", headers=headers)
    received = response.headers[REQUEST_ID_HEADER]
    assert received != sent
    assert uuid.UUID(received).version == 4


def test_the_boundary_lengths_are_accepted(probe: FastAPI) -> None:
    for sent in ("a" * 8, "A-" * 32):
        assert (
            TestClient(probe).get("/ok", headers={REQUEST_ID_HEADER: sent}).headers[REQUEST_ID_HEADER] == sent
        )


def test_every_kind_of_response_carries_the_request_id(probe: FastAPI) -> None:
    client = TestClient(probe, raise_server_exceptions=False)
    assert REQUEST_ID_HEADER in client.get("/ok").headers
    assert REQUEST_ID_HEADER in client.get("/missing").headers  # 404
    assert REQUEST_ID_HEADER in client.post("/ok").headers  # 405
    crashed = client.get("/boom")
    assert crashed.status_code == 500
    assert crashed.text == "Internal Server Error"
    assert REQUEST_ID_HEADER in crashed.headers  # Starlette's own 500 handler would have left it out


def test_a_crash_still_reaches_the_caller_of_the_test_client(probe: FastAPI) -> None:
    with pytest.raises(RuntimeError, match="kaboom"):
        TestClient(probe).get("/boom")


def test_the_context_ends_with_the_request(probe: FastAPI) -> None:
    TestClient(probe).get("/ok")
    assert get_request_context() is None


def test_the_context_has_the_address_and_a_bounded_user_agent(probe: FastAPI) -> None:
    @probe.get("/context")
    def context_route() -> dict[str, str | None]:
        context = get_request_context()
        assert context is not None
        return {"ip": context.ip, "user_agent": context.user_agent}

    body = TestClient(probe).get("/context", headers={"User-Agent": "u" * 600}).json()
    assert body == {"ip": "testclient", "user_agent": "u" * 512}


# ------------------------------------------------------------------ the access log


def test_one_access_line_per_request_with_the_request_id(probe: FastAPI, stderr_logs: StderrLogs) -> None:
    response = TestClient(probe).get("/ok")
    line = _access(stderr_logs())
    assert line["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert (line["method"], line["path"], line["status"]) == ("GET", "/ok", 200)
    assert line["actor_id"] is None
    assert isinstance(line["duration_ms"], float)
    assert line["level"] == "info"
    assert line["timestamp"].endswith("Z")


def test_the_access_line_names_the_actor_that_a_dependency_bound(
    probe: FastAPI, stderr_logs: StderrLogs
) -> None:
    TestClient(probe).get("/who")
    assert _access(stderr_logs())["actor_id"] == "user-42"


def test_the_access_line_has_the_path_but_no_query_string_and_no_body(
    probe: FastAPI, stderr_logs: StderrLogs
) -> None:
    TestClient(probe).post("/echo?token=hunter2", content=b'{"password": "s3cret-body"}')
    lines = stderr_logs()
    assert _access(lines)["path"] == "/echo"
    everything = json.dumps(lines)
    assert "hunter2" not in everything
    assert "s3cret-body" not in everything
    assert "token" not in everything


def test_a_failed_request_is_logged_with_status_500(probe: FastAPI, stderr_logs: StderrLogs) -> None:
    TestClient(probe, raise_server_exceptions=False).get("/boom")
    assert _access(stderr_logs())["status"] == 500


def test_a_log_line_from_inside_a_handler_carries_the_request_context(
    probe: FastAPI, stderr_logs: StderrLogs
) -> None:
    @probe.get("/logs")
    def logs() -> dict[str, str]:
        structlog.get_logger().info("inside the handler")
        return {}

    response = TestClient(probe).get("/logs")
    [inside] = [e for e in stderr_logs() if e["event"] == "inside the handler"]
    assert inside["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert (inside["method"], inside["path"]) == ("GET", "/logs")


def test_each_request_gets_its_own_id_in_the_log(probe: FastAPI, stderr_logs: StderrLogs) -> None:
    client = TestClient(probe)
    first, second = client.get("/ok"), client.get("/ok")
    ids = [line["request_id"] for line in stderr_logs() if line["event"] == "request"]
    assert ids == [first.headers[REQUEST_ID_HEADER], second.headers[REQUEST_ID_HEADER]]
    assert ids[0] != ids[1]


# ------------------------------------------------------------------ configure_logging


def test_nothing_is_written_to_stdout(
    probe: FastAPI, stderr_logs: StderrLogs, capsys: pytest.CaptureFixture[str]
) -> None:
    TestClient(probe).get("/ok")
    structlog.get_logger().warning("hello")
    logging.getLogger("uvicorn.error").error("from uvicorn")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err != ""


def test_stdlib_logging_is_routed_through_the_same_json_renderer(stderr_logs: StderrLogs) -> None:
    logging.getLogger("uvicorn.error").warning("server says %s", "hi")
    logging.getLogger("some.library").error("library failed")
    uvicorn_line, library_line = stderr_logs()
    assert (uvicorn_line["event"], uvicorn_line["level"], uvicorn_line["logger"]) == (
        "server says hi",
        "warning",
        "uvicorn.error",
    )
    assert library_line["event"] == "library failed"
    assert library_line["timestamp"]


def test_uvicorns_own_access_log_is_silenced(stderr_logs: StderrLogs) -> None:
    """It prints the whole request target, query string included."""
    logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /api/x?token=abc HTTP/1.1" 200')
    assert stderr_logs() == []


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
def test_libraries_that_log_urls_and_sql_parameters_stay_quiet(
    settings: Settings, capsys: pytest.CaptureFixture[str], level: str
) -> None:
    """httpx logs the full request URL, query string included. SQLAlchemy logs statement parameters, which
    would hold audit details and, later, document text. Neither may reach the logs at INFO or DEBUG."""
    configure_logging(settings.model_copy(update={"log_level": level}))
    logging.getLogger("httpx").info('HTTP Request: GET https://x.test/?token=hunter2 "200 OK"')
    logging.getLogger("httpx2").debug("sending GET https://x.test/?token=hunter2")
    logging.getLogger("sqlalchemy.engine").info("INSERT ... [parameters: ('prompt text',)]")
    logging.getLogger("anthropic._base_client").debug("Request options: {'json_data': 'prompt text'}")
    logging.getLogger("some.library").info("our own code and others still log")
    logging.getLogger("httpx").warning("but a warning from them does")
    events = [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines()]
    assert events == ["our own code and others still log", "but a warning from them does"]


def test_a_traceback_is_one_json_field(stderr_logs: StderrLogs) -> None:
    try:
        raise ValueError("bad thing")
    except ValueError:
        structlog.get_logger().exception("it failed")
        logging.getLogger("some.library").exception("library failed")
    ours, theirs = stderr_logs()
    assert "ValueError: bad thing" in ours["exception"]
    assert "ValueError: bad thing" in theirs["exception"]


def test_the_log_level_filters(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(settings.model_copy(update={"log_level": "WARNING"}))
    structlog.get_logger().info("quiet")
    structlog.get_logger().warning("loud")
    logging.getLogger("some.library").info("quiet too")
    events = [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines()]
    assert events == ["loud"]


def test_dev_uses_the_console_renderer(settings: Settings, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(settings.model_copy(update={"env": "dev"}))
    structlog.get_logger().info("readable", answer=42)
    logging.getLogger("some.library").info("readable too")
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    assert not any(line.startswith("{") for line in lines)
    assert re.search(r"readable\s+answer=42", lines[0])
    assert "readable too" in lines[1]


def test_configuring_twice_keeps_the_first_configuration(settings: Settings) -> None:
    configure_logging(settings)
    handlers = logging.getLogger().handlers[:]
    configure_logging(settings.model_copy(update={"env": "dev"}))
    assert logging.getLogger().handlers == handlers


def test_an_existing_capture_is_not_overwritten(settings: Settings) -> None:
    """The app and the CLI configure logging when they start. Inside a test's capture that must be a no-op."""
    with capture_logs() as captured:
        configure_logging(settings)
        structlog.get_logger().info("captured")
    assert [entry["event"] for entry in captured] == ["captured"]

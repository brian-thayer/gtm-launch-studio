import json
import logging

import pytest
import structlog
from fastapi import FastAPI
from structlog.testing import capture_logs
from typer.testing import CliRunner

from gtm_studio import __version__, cli
from gtm_studio.cli import app
from gtm_studio.settings import Settings
from gtm_studio.worker import runner

runner_cli = CliRunner()


def test_version() -> None:
    result = runner_cli.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__ == "0.1.0"


def test_no_arguments_prints_help() -> None:
    result = runner_cli.invoke(app, [])
    assert "openapi" in result.output
    assert "worker" in result.output


def test_openapi_is_valid_json_with_health_route() -> None:
    result = runner_cli.invoke(app, ["openapi"])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert "/api/health" in schema["paths"]
    assert schema["info"]["version"] == __version__


def test_openapi_output_is_canonical() -> None:
    """Sorted keys, LF endings and one trailing newline, so the committed file never churns."""
    raw = runner_cli.invoke(app, ["openapi"]).stdout_bytes
    assert raw.endswith(b"}\n")
    assert not raw.endswith(b"\n\n")
    assert b"\r" not in raw
    parsed = json.loads(raw)
    assert raw.decode("ascii") == json.dumps(parsed, indent=2, sort_keys=True) + "\n"


def test_openapi_ignores_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = runner_cli.invoke(app, ["openapi"]).stdout
    monkeypatch.setenv("GTM_ENV", "production")
    monkeypatch.setenv("GTM_LOG_LEVEL", "nonsense")
    assert runner_cli.invoke(app, ["openapi"]).stdout == baseline


def test_openapi_stdout_stays_json_with_logging_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """structlog's default writes to stdout, where `gtm openapi > frontend/openapi.json` puts the schema.
    Even a log line emitted while the command runs must go to stderr."""
    real_create_app = cli.create_app

    def noisy_create_app(settings: Settings) -> FastAPI:
        structlog.get_logger().warning("stray log line")
        logging.getLogger("some.library").warning("stray stdlib line")
        return real_create_app(settings)

    monkeypatch.setattr(cli, "create_app", noisy_create_app)
    assert not structlog.is_configured()
    result = runner_cli.invoke(app, ["openapi"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["info"]["title"] == "GTM Launch Studio"  # not corrupted
    assert "stray log line" in result.stderr
    assert "stray stdlib line" in result.stderr
    assert structlog.is_configured()  # the Typer callback did it


def test_commands_configure_logging_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "production")
    monkeypatch.setenv("GTM_AUTH_PROVIDER", "oidc")
    monkeypatch.setenv("GTM_SESSION_SECRET", "s" * 48)
    result = runner_cli.invoke(app, ["worker", "--once"])
    assert result.exit_code == 0
    [line] = [json.loads(entry) for entry in result.stderr.splitlines()]  # JSON outside dev
    assert line["event"] == "worker idle (implemented in S33)"


def test_operation_ids_are_tag_and_function_name() -> None:
    schema = json.loads(runner_cli.invoke(app, ["openapi"]).stdout)
    assert schema["paths"]["/api/health"]["get"]["operationId"] == "health_health"


def test_worker_once_logs_once_and_exits_zero() -> None:
    with capture_logs() as logs:
        result = runner_cli.invoke(app, ["worker", "--once"])
    assert result.exit_code == 0
    assert [entry["event"] for entry in logs] == ["worker idle (implemented in S33)"]


def test_ctrl_c_stops_the_worker_cleanly_and_says_so_on_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(*, once: bool) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_idle", interrupted)
    result = runner_cli.invoke(app, ["worker"])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert "worker stopped" in result.stderr


def test_worker_idles_until_interrupted() -> None:
    sleeps: list[float] = []

    def stop_after_three(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise KeyboardInterrupt

    with capture_logs() as logs, pytest.raises(KeyboardInterrupt):
        runner.run_idle(sleep=stop_after_three)
    assert len(logs) == 3
    assert sleeps == [30.0, 30.0, 30.0]

import json

import pytest
from structlog.testing import capture_logs
from typer.testing import CliRunner

from gtm_studio import __version__
from gtm_studio.cli import app
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


def test_operation_ids_are_tag_and_function_name() -> None:
    schema = json.loads(runner_cli.invoke(app, ["openapi"]).stdout)
    assert schema["paths"]["/api/health"]["get"]["operationId"] == "health_health"


def test_worker_once_logs_once_and_exits_zero() -> None:
    with capture_logs() as logs:
        result = runner_cli.invoke(app, ["worker", "--once"])
    assert result.exit_code == 0
    assert [entry["event"] for entry in logs] == ["worker idle (implemented in S33)"]


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

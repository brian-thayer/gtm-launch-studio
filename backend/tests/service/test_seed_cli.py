from pathlib import Path

import pytest
import yaml
from sqlalchemy import Engine
from typer.testing import CliRunner

from gtm_studio.cli import app
from gtm_studio.settings import REPO_ROOT, Settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _point_the_cli_at_the_test_database(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "test")
    monkeypatch.setenv("GTM_DB_URL", settings.db_url)
    monkeypatch.setenv("GTM_CATALOG_DIR", str(settings.catalog_dir))  # never the real gtm_catalog/


def test_seed_dev_users_is_idempotent(migrated_engine: Engine) -> None:
    first = runner.invoke(app, ["seed", "dev-users"])
    assert first.exit_code == 0, first.output
    assert "7 created" in first.output

    second = runner.invoke(app, ["seed", "dev-users"])
    assert second.exit_code == 0, second.output
    assert "dev users: 0 created, 0 updated, 7 unchanged; roles: 0 created" in second.output


def test_seed_dev_users_takes_a_path(migrated_engine: Engine, tmp_path: Path) -> None:
    users = [
        {
            "id": "55555555-5555-4555-8555-555555555555",
            "email": "q@example.test",
            "display_name": "Q",
            "roles": ["q"],
        }
    ]
    path = tmp_path / "users.yaml"
    path.write_text(yaml.safe_dump({"users": users}), encoding="utf-8")
    result = runner.invoke(app, ["seed", "dev-users", "--path", str(path)])
    assert result.exit_code == 0, result.output
    assert "dev users: 1 created, 0 updated, 0 unchanged; roles: 1 created" in result.output


def test_seed_dev_users_needs_a_migrated_database() -> None:
    result = runner.invoke(app, ["seed", "dev-users"])
    assert result.exit_code == 1
    assert "gtm db upgrade" in result.output


@pytest.mark.usefixtures("hosted_env")
def test_seed_dev_users_refuses_production(migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "production")
    result = runner.invoke(app, ["seed", "dev-users"])
    assert result.exit_code == 1
    assert "production" in result.output


def test_seed_dev_users_reports_a_bad_file_without_a_traceback(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["seed", "dev-users", "--path", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 1
    assert "seeding failed" in result.output
    assert "Traceback" not in result.output


def test_seeding_warns_about_roles_the_catalog_does_not_declare(
    migrated_engine: Engine, catalog_min_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTM_CATALOG_DIR", str(catalog_min_dir))  # declares role_a and role_b only
    result = runner.invoke(app, ["seed", "dev-users"])
    assert result.exit_code == 0, result.output  # a warning, never a failure
    assert "warning: the catalog at" in result.output
    assert "cs, launch_owner, pmm, product, support" in result.output
    assert "admin" not in result.output.split("declare these seeded roles:")[1]  # system roles always fine


def test_seeding_is_quiet_when_the_demo_catalog_declares_every_role(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTM_CATALOG_DIR", str(REPO_ROOT / "fixtures" / "demo" / "catalog"))
    result = runner.invoke(app, ["seed", "dev-users"])
    assert result.exit_code == 0, result.output
    assert "warning" not in result.output


def test_seeding_is_quiet_without_a_catalog_or_with_one_that_does_not_load(
    migrated_engine: Engine, catalog_min_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GTM_CATALOG_DIR", str(tmp_path / "nowhere"))
    assert "warning" not in runner.invoke(app, ["seed", "dev-users"]).output
    (catalog_min_copy / "tiers.yaml").write_text("tiers: [unclosed\n", encoding="utf-8")
    monkeypatch.setenv("GTM_CATALOG_DIR", str(catalog_min_copy))
    result = runner.invoke(app, ["seed", "dev-users"])
    assert result.exit_code == 0, result.output
    assert "warning" not in result.output

from pathlib import Path

import pytest
from pydantic import ValidationError

from gtm_studio.settings import ENV_FILE, REPO_ROOT, Settings


def test_repo_root_is_the_repository() -> None:
    assert (REPO_ROOT / "backend" / "pyproject.toml").is_file()
    assert (REPO_ROOT / "CLAUDE.md").is_file()


def test_defaults() -> None:
    s = Settings()
    assert s.env == "dev"
    assert s.llm_provider == "mock"
    assert s.allow_bedrock is False
    assert s.aws_region is None
    assert s.log_level == "INFO"
    assert s.storage_dir == REPO_ROOT / "storage"
    assert s.catalog_dir == REPO_ROOT / "gtm_catalog"
    assert s.config_dir == REPO_ROOT / "config"
    assert s.db_url == f"sqlite:///{(REPO_ROOT / 'storage' / 'gtm_studio.db').as_posix()}"


def test_reads_gtm_prefixed_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "test")
    monkeypatch.setenv("GTM_LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("GTM_ALLOW_BEDROCK", "true")
    monkeypatch.setenv("GTM_AWS_REGION", "us-east-1")
    s = Settings()
    assert (s.env, s.llm_provider, s.allow_bedrock, s.aws_region) == ("test", "bedrock", True, "us-east-1")


def test_unprefixed_env_vars_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    assert Settings().env == "dev"


def test_log_level_is_case_insensitive_and_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_LOG_LEVEL", "debug")
    assert Settings().log_level == "DEBUG"
    monkeypatch.setenv("GTM_LOG_LEVEL", "loud")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("bad", ["staging", "prod", "", "DEV"])
def test_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv("GTM_ENV", bad)
    with pytest.raises(ValidationError):
        Settings()


def test_rejects_invalid_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_LLM_PROVIDER", "openai")
    with pytest.raises(ValidationError):
        Settings()


def test_relative_dirs_resolve_against_repo_root_not_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GTM_CATALOG_DIR", "fixtures/demo/catalog")
    monkeypatch.setenv("GTM_STORAGE_DIR", "var/data")
    s = Settings()
    assert s.catalog_dir == REPO_ROOT / "fixtures" / "demo" / "catalog"
    assert s.storage_dir == REPO_ROOT / "var" / "data"


def test_absolute_dirs_are_kept(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GTM_CONFIG_DIR", str(tmp_path))
    assert Settings().config_dir == tmp_path


def test_relative_sqlite_path_resolves_against_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GTM_DB_URL", "sqlite:///storage/other.db")
    assert Settings().db_url == f"sqlite:///{(REPO_ROOT / 'storage' / 'other.db').as_posix()}"


@pytest.mark.parametrize("driver", ["sqlite", "sqlite+pysqlite"])
def test_relative_sqlite_path_resolves_for_driver_qualified_urls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, driver: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GTM_DB_URL", f"{driver}:///storage/other.db")
    assert Settings().db_url == f"{driver}:///{(REPO_ROOT / 'storage' / 'other.db').as_posix()}"


@pytest.mark.parametrize(
    "url",
    [
        "sqlite://",
        "sqlite+pysqlite:///:memory:",
        "sqlite:///file:gtm.db?mode=ro&uri=true",
        "sqlite:///:memory:",
        "sqlite:////var/lib/gtm.db",
        "postgresql+psycopg://user@host/gtm",
    ],
)
def test_other_db_urls_pass_through_unchanged(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("GTM_DB_URL", url)
    assert Settings().db_url == url


def test_absolute_sqlite_path_is_kept(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'x.db').as_posix()}"
    monkeypatch.setenv("GTM_DB_URL", url)
    assert Settings().db_url == url


def test_env_file_is_read_and_unknown_keys_are_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GTM_ENV=test\nGTM_NOT_A_SETTING=1\nOTHER=2\n", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    assert Settings().env == "test"


def test_environment_beats_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GTM_ENV=test\n", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    monkeypatch.setenv("GTM_ENV", "production")
    assert Settings().env == "production"


def test_the_default_env_file_is_backend_dot_env() -> None:
    """Pinned: S09's hosting notes and the README tell people to put overrides in backend/.env."""
    assert ENV_FILE == REPO_ROOT / "backend" / ".env"


def test_defaults_ignores_environment_and_never_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "production")
    monkeypatch.setenv("GTM_LOG_LEVEL", "nonsense")
    s = Settings.defaults()
    assert (s.env, s.log_level, s.storage_dir) == ("dev", "INFO", REPO_ROOT / "storage")


def test_no_caching_between_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GTM_ENV", "test")
    first = Settings()
    monkeypatch.setenv("GTM_ENV", "production")
    second = Settings()
    assert (first.env, second.env) == ("test", "production")


def test_cors_origins_default_to_empty() -> None:
    assert Settings().cors_origins == []
    assert Settings.defaults().cors_origins == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://a.example", ["https://a.example"]),
        ("https://a.example,https://b.example", ["https://a.example", "https://b.example"]),
        (" https://a.example , ,https://b.example, ", ["https://a.example", "https://b.example"]),
        ("", []),
    ],
)
def test_cors_origins_is_a_comma_separated_env_var(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
) -> None:
    monkeypatch.setenv("GTM_CORS_ORIGINS", raw)
    assert Settings().cors_origins == expected


def test_cors_origins_rejects_a_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials are allowed cross-origin, so a wildcard would let any site ride the session cookie."""
    monkeypatch.setenv("GTM_CORS_ORIGINS", "https://a.example,*")
    with pytest.raises(ValidationError):
        Settings()

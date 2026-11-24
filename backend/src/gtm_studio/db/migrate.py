"""Run Alembic from code: no subprocess, and the database URL always comes from ``Settings``."""

from pathlib import Path
from typing import Any, Literal

from alembic import command
from alembic.autogenerate.api import AutogenContext
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import Script, ScriptDirectory
from sqlalchemy.engine import make_url

from gtm_studio.db.base import UTCDateTime
from gtm_studio.db.engine import make_engine, sqlite_file
from gtm_studio.settings import Settings

# backend/src/gtm_studio/db/migrate.py -> parents[3] is backend/.
ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _config(settings: Settings) -> Config:
    config = Config(str(ALEMBIC_INI))
    # Absolute, so the working directory never matters. env.py reads the Settings back from here.
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["settings"] = settings
    return config


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Autogenerate hook (used by env.py): keep migrations self-contained by writing the portable
    SQLAlchemy type rather than one from this application."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def upgrade(settings: Settings, revision: str = "head") -> None:
    command.upgrade(_config(settings), revision)


def downgrade(settings: Settings, revision: str) -> None:
    command.downgrade(_config(settings), revision)


def new_revision(settings: Settings, message: str, *, autogenerate: bool = False) -> list[Script]:
    """Write a new migration file. ``autogenerate`` diffs the models against the (upgraded) database."""
    result = command.revision(_config(settings), message=message, autogenerate=autogenerate)
    scripts = result if isinstance(result, list) else [result]
    return [script for script in scripts if script is not None]


def current(settings: Settings) -> str | None:
    """The revision the database is at, or None for a database that was never migrated.

    Asking never creates a missing SQLite file (connecting would)."""
    db_file = sqlite_file(make_url(settings.db_url))
    if db_file is not None and not db_file.exists():
        return None
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def head(settings: Settings) -> str:
    """The newest revision in the migration scripts."""
    revision = ScriptDirectory.from_config(_config(settings)).get_current_head()
    if revision is None:
        raise RuntimeError("no migrations found")
    return revision

"""Alembic environment. The database URL comes from ``Settings``, never from alembic.ini.

``db/migrate.py`` passes the Settings in through ``config.attributes["settings"]``. When the plain
``alembic`` command runs this file instead, it builds ``Settings()`` itself.
"""

from alembic import context

import gtm_studio.db.models  # noqa: F401  (registers every table on Base.metadata)
from gtm_studio.db.base import Base
from gtm_studio.db.engine import make_engine
from gtm_studio.db.migrate import render_item
from gtm_studio.settings import Settings

config = context.config


def run_migrations_online() -> None:
    settings: Settings = config.attributes.get("settings") or Settings()
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                render_as_batch=True,  # SQLite cannot ALTER most things: batch mode copies the table
                compare_type=True,
                render_item=render_item,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline (--sql) migrations are not supported: run against a database")
run_migrations_online()

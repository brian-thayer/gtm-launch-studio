"""The ``gtm`` command line."""

import sys
from typing import Annotated

import typer

from gtm_studio import __version__
from gtm_studio.api.app import create_app
from gtm_studio.api.openapi import render_openapi
from gtm_studio.db import migrate
from gtm_studio.settings import Settings
from gtm_studio.worker.runner import run_idle

app = typer.Typer(name="gtm", help="GTM Launch Studio.", no_args_is_help=True, add_completion=False)
db_app = typer.Typer(help="Database migrations.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def openapi() -> None:
    """Print the OpenAPI schema as JSON, without starting a server.

    Pipe it into frontend/openapi.json. The schema never depends on settings, so the app is built from
    the defaults: a stray GTM_* variable or backend/.env can neither change the output nor break it.
    """
    schema = render_openapi(create_app(Settings.defaults()))
    # Write bytes: text mode on Windows would turn every "\n" into "\r\n" and churn the committed file.
    sys.stdout.flush()
    sys.stdout.buffer.write(schema.encode("ascii"))
    sys.stdout.buffer.flush()


@db_app.command("upgrade")
def db_upgrade(
    revision: Annotated[str, typer.Argument(help="Target revision.")] = "head",
) -> None:
    """Create or migrate the database (GTM_DB_URL) up to a revision, by default the latest."""
    settings = Settings()
    migrate.upgrade(settings, revision)
    typer.echo(f"database is at {migrate.current(settings)}")


@db_app.command("current")
def db_current() -> None:
    """Print the database's migration revision, marked (head) when it is the latest."""
    settings = Settings()
    revision = migrate.current(settings)
    if revision is None:
        typer.echo("(not migrated: run `gtm db upgrade`)")
    else:
        typer.echo(f"{revision} (head)" if revision == migrate.head(settings) else revision)


@db_app.command("revision")
def db_revision(
    message: Annotated[str, typer.Option("-m", "--message", help="What the migration does.")],
    autogenerate: Annotated[
        bool, typer.Option("--autogenerate", help="Fill it in from the models' difference to the database.")
    ] = False,
) -> None:
    """Write a new migration file. With --autogenerate, upgrade the database first; review the result."""
    for script in migrate.new_revision(Settings(), message, autogenerate=autogenerate):
        typer.echo(f"created {script.path}")


@app.command()
def worker(
    once: Annotated[bool, typer.Option("--once", help="Log once and exit.")] = False,
) -> None:
    """Run the job worker (a placeholder until S33)."""
    try:
        run_idle(once=once)
    except KeyboardInterrupt:
        typer.echo("worker stopped")

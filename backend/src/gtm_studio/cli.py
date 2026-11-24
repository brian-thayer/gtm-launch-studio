"""The ``gtm`` command line."""

import sys
from typing import Annotated

import typer

from gtm_studio import __version__
from gtm_studio.api.app import create_app
from gtm_studio.api.openapi import render_openapi
from gtm_studio.settings import Settings
from gtm_studio.worker.runner import run_idle

app = typer.Typer(name="gtm", help="GTM Launch Studio.", no_args_is_help=True, add_completion=False)


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


@app.command()
def worker(
    once: Annotated[bool, typer.Option("--once", help="Log once and exit.")] = False,
) -> None:
    """Run the job worker (a placeholder until S33)."""
    try:
        run_idle(once=once)
    except KeyboardInterrupt:
        typer.echo("worker stopped")

"""The ``gtm`` command line."""

import sys
from functools import partial
from pathlib import Path
from typing import Annotated

import typer

from gtm_studio import __version__
from gtm_studio.api.app import create_app
from gtm_studio.api.openapi import render_openapi
from gtm_studio.audit.logging import configure_logging
from gtm_studio.auth.dev_users import load_dev_users
from gtm_studio.catalog.loader import CatalogLoadError, catalog_present, load_catalog
from gtm_studio.catalog.source import check_catalog
from gtm_studio.catalog.todos import MARKER, count_todos
from gtm_studio.db import migrate
from gtm_studio.db.engine import make_engine, make_session_factory
from gtm_studio.db.uow import SqlUnitOfWork
from gtm_studio.domain.catalog import Catalog, IssueSummary
from gtm_studio.services.identity import IdentityService, SeedError
from gtm_studio.services.ports import UnitOfWorkFactory
from gtm_studio.settings import Settings
from gtm_studio.worker.runner import run_idle

app = typer.Typer(name="gtm", help="GTM Launch Studio.", no_args_is_help=True, add_completion=False)
db_app = typer.Typer(help="Database migrations.", no_args_is_help=True)
app.add_typer(db_app, name="db")
seed_app = typer.Typer(help="Load seed data.", no_args_is_help=True)
app.add_typer(seed_app, name="seed")
catalog_app = typer.Typer(help="The GTM catalog (gtm_catalog/).", no_args_is_help=True)
app.add_typer(catalog_app, name="catalog")


@app.callback()
def main(ctx: typer.Context) -> None:
    """GTM Launch Studio."""
    # Logs go to stderr, so `gtm openapi > file` stays clean. openapi must not depend on the machine, so
    # it doesn't even read the environment.
    configure_logging(Settings.defaults() if ctx.invoked_subcommand == "openapi" else Settings())


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


@seed_app.command("dev-users")
def seed_dev_users(
    path: Annotated[
        Path | None, typer.Option("--path", help="YAML file. Default: config/dev_users.yaml.")
    ] = None,
) -> None:
    """Create the demo users and their roles (idempotent). The database must be migrated first."""
    settings = Settings()
    if settings.env == "production":
        typer.echo("refusing to seed dev users when GTM_ENV=production", err=True)
        raise typer.Exit(1)
    if migrate.current(settings) != migrate.head(settings):
        typer.echo("the database is not migrated: run `gtm db upgrade` first", err=True)
        raise typer.Exit(1)
    source = path or settings.config_dir / "dev_users.yaml"
    engine = make_engine(settings)
    try:
        uow_factory: UnitOfWorkFactory = partial(SqlUnitOfWork, make_session_factory(engine))
        summary = IdentityService(uow_factory).seed_dev_users(load_dev_users(source))
    except SeedError as exc:
        typer.echo(f"seeding failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        engine.dispose()
    typer.echo(
        f"dev users: {summary.users_created} created, {summary.users_updated} updated, "
        f"{summary.users_unchanged} unchanged; roles: {summary.roles_created} created"
    )


def _table(rows: list[list[str]]) -> list[str]:
    """Rows as indented, column-aligned lines (all rows have the same number of cells)."""
    if not rows:
        return ["  none"]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return [
        "  " + "  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip() for row in rows
    ]


def _timing_text(catalog: Catalog, tier_key: str) -> str:
    tier = catalog.tier(tier_key)
    parts: list[str] = []
    if tier.timing is not None:
        parts.append(f"anchor {tier.timing.anchor}")
        if tier.timing.plan_start_days is not None:
            parts.append(f"plan start {tier.timing.plan_start_days:+d}d")
        if tier.timing.core_due_days is not None:
            parts.append(f"core due {tier.timing.core_due_days:+d}d")
    text = f"timing: {', '.join(parts)}" if parts else ""
    return "; ".join(p for p in (text, f"optional: {', '.join(tier.optional)}" if tier.optional else "") if p)


def _render_catalog(catalog: Catalog) -> str:
    """The text `gtm catalog show` prints."""
    gates = catalog.gates_in_order()
    tiers = catalog.tiers_by_rank()
    inherits = "each also gets the core assets of the tiers below it" if catalog.tiers.inherits_lower else ""
    matrix = catalog.matrix()
    triggers = [
        [
            t.key,
            t.context_key or "(a person decides)",
            f"-> {', '.join(t.assets)}",
            f"tiers: {', '.join(t.tiers)}" if t.tiers is not None else "every tier",
        ]
        for t in catalog.tiers.triggers
    ]
    undefined = sorted(catalog.undefined_asset_keys())
    lines = [
        f"version {catalog.version_hash}",
        "",
        "gates, in order",
        *_table(
            [
                [
                    str(g.order),
                    g.key,
                    g.label,
                    f"approvers: {', '.join(g.approver_roles)}"
                    + ("  [release gate]" if g.release_gate else ""),
                ]
                for g in gates
            ]
        ),
        "",
        f"tiers, by rank{f' ({inherits})' if inherits else ''}",
        *_table([[str(t.rank), t.key, t.label, _timing_text(catalog, t.key)] for t in tiers]),
        "",
        "core assets by tier and gate",
        *_table(
            [
                ["", *(g.key for g in gates)],
                *([t.key, *(", ".join(matrix[t.key][g.key]) or "-" for g in gates)] for t in tiers),
            ]
        ),
        "",
        "triggers",
        *(_table(triggers) if triggers else ["  none"]),
        "",
        "asset keys with no asset type folder",
        *([f"  {', '.join(undefined)}"] if undefined else ["  none"]),
    ]
    return "\n".join(lines)


@catalog_app.command("show")
def catalog_show(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path", help="Catalog folder, relative to the working directory. Default: GTM_CATALOG_DIR."
        ),
    ] = None,
) -> None:
    """Print a catalog's version hash, gates, tiers, tier x gate matrix, triggers and missing asset types."""
    root = path if path is not None else Settings().catalog_dir
    if not catalog_present(root):
        typer.echo(f"no catalog at {root}", err=True)
        raise typer.Exit(1)
    try:
        catalog = load_catalog(root)
    except CatalogLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(_render_catalog(catalog))


@catalog_app.command("validate")
def catalog_validate(
    path: Annotated[
        Path | None,
        typer.Option(
            "--path", help="Catalog folder, relative to the working directory. Default: GTM_CATALOG_DIR."
        ),
    ] = None,
    strict: Annotated[
        bool, typer.Option("--strict", help="Count warnings as errors (TODO markers stay warnings).")
    ] = False,
) -> None:
    """List every problem in a catalog. Exits 1 when there is an error."""
    root = path if path is not None else Settings().catalog_dir
    if not catalog_present(root):
        typer.echo(f"no catalog at {root}", err=True)
        raise typer.Exit(1)
    todos = count_todos(root)
    catalog, issues = check_catalog(root, strict=strict, todos=todos)
    summary = IssueSummary(
        errors=sum(issue.level == "error" for issue in issues),
        warnings=sum(issue.level == "warning" for issue in issues),
        todo_count=sum(todos.values()) if catalog is not None else 0,
    )
    typer.echo("issues")
    for line in _table([[issue.level, issue.where, issue.message] for issue in issues]):
        typer.echo(line)
    typer.echo("")
    typer.echo(f"{summary.errors} errors, {summary.warnings} warnings, {summary.todo_count} {MARKER}")
    if catalog is not None:
        typer.echo(f"version {catalog.version_hash}")
    if summary.errors:
        raise typer.Exit(1)


@app.command()
def worker(
    once: Annotated[bool, typer.Option("--once", help="Log once and exit.")] = False,
) -> None:
    """Run the job worker (a placeholder until S33)."""
    try:
        run_idle(once=once)
    except KeyboardInterrupt:
        typer.echo("worker stopped", err=True)  # stdout is for command output

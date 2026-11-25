"""Structured logging: structlog for our code, and stdlib logging (uvicorn, alembic, libraries) routed
through the same renderer so every line has one shape.

**Everything goes to stderr.** stdout belongs to command output: ``gtm openapi > frontend/openapi.json``
would be corrupted by a single stray log line. ``sys.stderr`` is looked up on every write rather than
captured once, so a test (or a caller) that swaps it is respected.

JSON lines outside ``env=dev``, a readable console format in dev. Request bodies are never logged: the
middleware doesn't read them, and the rule for everyone else is in ``backend/CLAUDE.md``.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.typing import Processor

from gtm_studio.settings import Settings

# Libraries that log request URLs (query strings included), SQL parameters, message bodies or tokens once the
# level is INFO or DEBUG. They stay at WARNING whatever GTM_LOG_LEVEL says: prompts, document text and tokens
# must not reach the logs (backend/CLAUDE.md). authlib logs the PKCE code verifier at DEBUG.
QUIET_LIBRARIES = (
    "authlib",
    "httpx",
    "httpx2",
    "httpcore",
    "anthropic",
    "boto3",
    "botocore",
    "urllib3",
    "sqlalchemy.engine",
)

_LOGGING_FORMAT_PROCESSORS = (
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
)


def _stderr_logger(*_args: Any) -> structlog.PrintLogger:
    return structlog.PrintLogger(file=sys.stderr)


class StderrHandler(logging.Handler):
    """Writes to whatever ``sys.stderr`` is at the time (``logging.StreamHandler`` would keep the one
    it saw at construction)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stderr.write(self.format(record) + "\n")
            sys.stderr.flush()
        except Exception:
            self.handleError(record)


def configure_logging(settings: Settings) -> None:
    """Configure structlog and the root stdlib logger from ``settings`` (``env``, ``log_level``).

    Does nothing when structlog is already configured: a process configures itself once, at start-up,
    and a test's ``structlog.testing.capture_logs()`` must not be overwritten by a command or app that
    starts inside it. (``structlog.reset_defaults()`` makes it configurable again.)
    """
    if structlog.is_configured():
        return
    level = logging.getLevelNamesMapping()[settings.log_level]
    renderer: Processor = (
        structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        if settings.env == "dev"
        else structlog.processors.JSONRenderer()
    )
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        *_LOGGING_FORMAT_PROCESSORS,
    ]
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=_stderr_logger,
        cache_logger_on_first_use=False,  # capture_logs() relies on loggers being resolved on each call
    )

    handler = StderrHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[structlog.stdlib.add_logger_name, *shared],
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in QUIET_LIBRARIES:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))

    # uvicorn installs its own handlers and doesn't propagate. Hand its server messages to the root
    # handler. Its access log is silenced: it prints the full request target (the query string too),
    # and RequestContextMiddleware writes the access line without it.
    for name in ("uvicorn", "uvicorn.error"):
        server = logging.getLogger(name)
        server.handlers.clear()
        server.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False

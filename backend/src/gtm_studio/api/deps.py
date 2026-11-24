"""Shared FastAPI dependencies. Per-request wiring only: no business rules."""

from fastapi import Request

from gtm_studio.settings import Settings


def get_settings(request: Request) -> Settings:
    """The Settings instance ``create_app`` stored on the app. Override it in tests with
    ``app.dependency_overrides``."""
    settings: Settings = request.app.state.settings
    return settings

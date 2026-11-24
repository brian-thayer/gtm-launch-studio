"""Import every model module here so ``Base.metadata`` is complete wherever it is used (Alembic
autogenerate and its env.py import this package). A model that isn't imported here is invisible to
migrations."""

from gtm_studio.db.models.app_meta import AppMeta

__all__ = ["AppMeta"]

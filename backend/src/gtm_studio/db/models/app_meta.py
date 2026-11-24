"""``app_meta``: small key/value facts about this installation (the first migrated table)."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from gtm_studio.db.base import Base, TimestampMixin

INSTALL_ID_KEY = "install_id"


class AppMeta(TimestampMixin, Base):
    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

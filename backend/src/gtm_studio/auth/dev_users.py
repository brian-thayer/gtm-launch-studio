"""Read ``config/dev_users.yaml``, the demo users ``gtm seed dev-users`` creates. File IO lives here, in
infrastructure, so ``IdentityService.seed_dev_users`` takes parsed values (ADR-0006)."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from gtm_studio.domain.identity import DevUserSeed
from gtm_studio.services.identity import SeedError


class _DevUsersFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    users: list[DevUserSeed]


def load_dev_users(path: Path) -> list[DevUserSeed]:
    """The users in ``path``. Raises ``SeedError`` (naming the file) when it is unreadable or malformed."""
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        return _DevUsersFile.model_validate(data).users
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise SeedError(f"{path}: {exc}") from exc

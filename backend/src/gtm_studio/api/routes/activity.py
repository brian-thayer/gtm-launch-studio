"""The audit trail: everyone's (``audit:read``) and your own (any signed-in user). A bad cursor is a 422
from ``api/errors.py``."""

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from gtm_studio.api.deps import ActivityServiceDep
from gtm_studio.api.schemas.activity import ActivityPage
from gtm_studio.auth.deps import current_actor, require
from gtm_studio.domain.audit import AuditFilters
from gtm_studio.domain.identity import Actor, Permission
from gtm_studio.services.activity import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

router = APIRouter(prefix="/activity", tags=["activity"])

CursorParam = Annotated[
    str | None, Query(max_length=300, description="`next_cursor` of the previous page. Opaque.")
]
LimitParam = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
EntityTypeParam = Annotated[str | None, Query(max_length=50)]
EntityIdParam = Annotated[str | None, Query(max_length=100)]
ActionPrefixParam = Annotated[
    str | None, Query(max_length=100, description="Match actions that start with this, e.g. `asset.`.")
]


def _filters(
    entity_type: EntityTypeParam = None,
    entity_id: EntityIdParam = None,
    action_prefix: ActionPrefixParam = None,
) -> AuditFilters:
    return AuditFilters(entity_type=entity_type, entity_id=entity_id, action_prefix=action_prefix)


FiltersDep = Annotated[AuditFilters, Depends(_filters)]


@router.get("", response_model=ActivityPage)
def list_activity(
    _: Annotated[Actor, Depends(require(Permission.AUDIT_READ))],
    activity: ActivityServiceDep,
    filters: FiltersDep,
    actor_id: Annotated[str | None, Query(max_length=36, description="Only this user's events.")] = None,
    cursor: CursorParam = None,
    limit: LimitParam = DEFAULT_PAGE_SIZE,
) -> ActivityPage:
    """Every audit event, newest first. Needs the `audit:read` permission."""
    page = activity.list_events(replace(filters, actor_id=actor_id), cursor, limit)
    return ActivityPage.from_page(page)


@router.get("/me", response_model=ActivityPage)
def list_my_activity(
    actor: Annotated[Actor, Depends(current_actor)],
    activity: ActivityServiceDep,
    filters: FiltersDep,
    cursor: CursorParam = None,
    limit: LimitParam = DEFAULT_PAGE_SIZE,
) -> ActivityPage:
    """The signed-in user's own audit events, newest first."""
    page = activity.list_own_events(actor, filters, cursor, limit)
    return ActivityPage.from_page(page)

"""Response models for ``/api/catalog``. The domain's frozen catalog models are reused where the API shows
them as they are (gates, triggers, the brand, an asset type's spec and examples); the rest are the views
``CatalogService`` computes, so the UI renders them and works nothing out."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from gtm_studio.domain.catalog import (
    AssetTypeSpec,
    Gate,
    GoldExample,
    Issue,
    RoleDef,
    RubricCriterion,
    TierCriterion,
    Trigger,
)
from gtm_studio.services.catalog import AssetTypeView, LoadedCatalog, MatrixView


class _FromDomain(BaseModel):
    """Built from a service view (a dataclass or a domain model) by attribute."""

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- GET /api/catalog
class IssuesOut(BaseModel):
    errors: int
    warnings: int
    todo_count: int  # TODO(confirm) markers: questions for a person, never errors
    items: list[Issue]


class TimingOut(BaseModel):
    """Planning context, never an approval gate. Offsets are signed days from the anchor."""

    anchor: str
    anchor_label: str  # the anchor context key's label
    plan_start_days: int | None
    core_due_days: int | None


class TierOut(BaseModel):
    key: str
    label: str
    rank: int
    description: str
    examples: list[str]
    criteria: list[TierCriterion]
    channels: list[str]
    timing: TimingOut | None


class AssetTypeSummary(BaseModel):
    key: str
    name: str
    gate: str
    audience: Literal["internal", "external"]
    family: str
    foundation: bool
    decides: Literal["tier"] | None
    example_count: int


class CatalogResponse(BaseModel):
    version_hash: str
    loaded_at: datetime
    issues: IssuesOut
    roles: list[RoleDef]
    gates: list[Gate]
    tiers: list[TierOut]
    triggers: list[Trigger]
    asset_types: list[AssetTypeSummary]

    @classmethod
    def from_loaded(cls, loaded: LoadedCatalog) -> "CatalogResponse":
        catalog = loaded.catalog
        labels = {key: context_key.label for key, context_key in catalog.context_keys.items()}
        tiers = [
            TierOut(
                key=tier.key,
                label=tier.label,
                rank=tier.rank,
                description=tier.description,
                examples=tier.examples,
                criteria=tier.criteria,
                channels=tier.channels,
                timing=None
                if tier.timing is None
                else TimingOut(
                    anchor=tier.timing.anchor,
                    anchor_label=labels.get(tier.timing.anchor, tier.timing.anchor),
                    plan_start_days=tier.timing.plan_start_days,
                    core_due_days=tier.timing.core_due_days,
                ),
            )
            for tier in catalog.tiers_by_rank()
        ]
        asset_types = [
            AssetTypeSummary(
                key=key,
                name=asset_type.spec.name,
                gate=asset_type.spec.gate,
                audience=asset_type.spec.audience,
                family=asset_type.spec.family,
                foundation=asset_type.spec.foundation,
                decides=asset_type.spec.decides,
                example_count=len(asset_type.examples),
            )
            for key, asset_type in sorted(catalog.asset_types.items())
        ]
        return cls(
            version_hash=catalog.version_hash,
            loaded_at=loaded.loaded_at,
            issues=IssuesOut(**loaded.summary.model_dump(), items=loaded.issues),
            roles=catalog.lifecycle.roles,
            gates=catalog.gates_in_order(),
            tiers=tiers,
            triggers=catalog.tiers.triggers,
            asset_types=asset_types,
        )


# ------------------------------------------------------------ GET /api/catalog/matrix
class AssetRefOut(_FromDomain):
    key: str
    name: str


class MatrixGateOut(_FromDomain):
    key: str
    short: str


class MatrixTierOut(_FromDomain):
    key: str
    label: str


class MatrixTriggerOut(_FromDomain):
    key: str
    label: str
    assets: list[AssetRefOut]


class MatrixRowOut(_FromDomain):
    tier: MatrixTierOut
    cells: list[list[AssetRefOut]]  # one list per gate, in the order of ``gates``
    optional: list[AssetRefOut]
    triggers: list[MatrixTriggerOut]


class MatrixResponse(_FromDomain):
    gates: list[MatrixGateOut]
    rows: list[MatrixRowOut]
    undefined_assets: list[str]

    @classmethod
    def from_view(cls, view: MatrixView) -> "MatrixResponse":
        return cls.model_validate(view)


# ------------------------------------------------- GET /api/catalog/asset-types/{key}
class RubricOut(BaseModel):
    pass_threshold: int
    criteria: list[RubricCriterion]


class AssetTypeResponse(BaseModel):
    spec: AssetTypeSpec
    prompt_md: str
    rubric: RubricOut
    examples: list[GoldExample]
    approver_roles: list[str]

    @classmethod
    def from_view(cls, view: AssetTypeView) -> "AssetTypeResponse":
        asset_type = view.asset_type
        return cls(
            spec=asset_type.spec,
            prompt_md=asset_type.prompt_md,
            rubric=RubricOut(
                pass_threshold=asset_type.rubric.pass_threshold, criteria=asset_type.rubric.criteria
            ),
            examples=asset_type.examples,
            approver_roles=view.approver_roles,
        )


# ------------------------------------------------------------ POST /api/catalog/reload
class ReloadResponse(_FromDomain):
    ok: bool
    old_hash: str | None
    new_hash: str | None  # null when the files didn't load at all
    issues: list[Issue]

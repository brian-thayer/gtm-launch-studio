"""The GTM catalog as typed, frozen models. Pure: no IO, no YAML (``catalog/`` reads the files).

The catalog is the user's GTM framework as data (ADR-0005): lifecycle gates and their approver roles,
launch tiers with the assets each needs (core, optional and triggered), the context keys facts are filed
under, the brand, and every asset type with its prompt, rubric and gold examples. Nothing here knows a
particular gate, tier or asset: all of that comes from the files.

An asset type's gate lives only in its spec. A tier lists asset keys, and ``Catalog.matrix`` groups them
by the spec's gate.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from gtm_studio.domain.errors import NotFoundError

ContextKeyType = Literal["text", "date", "boolean", "number", "list"]
ContextSourceKind = Literal[
    "aha", "document", "note", "qa", "aha_api", "kb"
]  # input kinds (code), not taxonomy
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class _Model(BaseModel):
    """A catalog value: unknown fields are an error (a typo must not pass silently) and nothing mutates."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- lifecycle
class RoleDef(_Model):
    key: str
    label: str


class Gate(_Model):
    key: str
    label: str
    short: str
    order: int
    approver_roles: list[str]
    release_gate: bool = False
    color: str | None = None


class ReadinessCategory(_Model):
    key: str
    label: str
    gates: list[str]


class Lifecycle(_Model):
    roles: list[RoleDef]
    gates: list[Gate]
    approved_gate_values: list[str]
    release_cutoff_values: list[str] = []
    readiness_categories: list[ReadinessCategory] = []


# -------------------------------------------------------------------- tiers
class TierCriterion(_Model):
    key: str
    label: str
    description: str


class TierTiming(_Model):
    """Planning context, never an approval gate. Offsets are signed days relative to the anchor."""

    anchor: str  # a context key of type "date"
    plan_start_days: int | None = None  # e.g. -56
    core_due_days: int | None = None  # e.g. -14


class Tier(_Model):
    key: str
    label: str
    rank: int  # 1 = the biggest launch
    description: str
    examples: list[str] = []
    criteria: list[TierCriterion] = []
    channels: list[str] = []
    core: list[str] = []
    optional: list[str] = []
    timing: TierTiming | None = None


class Trigger(_Model):
    key: str
    label: str
    description: str
    context_key: str | None = None  # a boolean context key, or None = a person decides
    assets: list[str]
    tiers: list[str] | None = None  # None = every tier


class Tiers(_Model):
    inherits_lower: bool = False
    tiers: list[Tier]
    triggers: list[Trigger] = []


# ------------------------------------------------------------- context keys
class ContextKey(_Model):
    key: str
    label: str
    description: str
    type: ContextKeyType = "text"
    sources: list[ContextSourceKind]


# -------------------------------------------------------------------- brand
class ProductName(_Model):
    name: str
    rules: str = ""
    never: list[str] = []


class PreferredTerm(_Model):
    use: str
    avoid: list[str]


class Terminology(_Model):
    product_names: list[ProductName] = []
    preferred: list[PreferredTerm] = []
    banned_external: list[str] = []


class Visual(_Model):
    colors: dict[str, str]
    fonts: dict[str, str] = {}
    logo: str | None = None
    slide: dict[str, Any] = {}


class Brand(_Model):
    voice_md: str
    claims_md: str
    legal_md: str
    terminology: Terminology
    visual: Visual


# -------------------------------------------------------------- asset types
class AssetTypeSpec(_Model):
    key: str
    name: str
    gate: str
    audience: Literal["internal", "external"]
    family: str  # checked against the backend's families by the validator, not here
    foundation: bool = False
    decides: Literal["tier"] | None = None
    depends_on: list[str] = []
    formats: list[str]
    required_context: list[str] = []
    approver_roles: list[str] | None = None  # None = the gate's approver roles
    route: str = "writer"
    effort: Effort = "medium"
    length: dict[str, int] | None = None


class RubricCriterion(_Model):
    key: str
    title: str
    body_md: str


class Rubric(_Model):
    pass_threshold: int
    criteria: list[RubricCriterion]
    raw_md: str  # the rubric file without its frontmatter


class GoldExample(_Model):
    slug: str
    title: str
    source: str
    redacted: bool
    redactions: list[str] = []
    why_good: list[str]
    context_summary: str
    tier: str | None = None
    body_md: str


class AssetType(_Model):
    spec: AssetTypeSpec
    prompt_md: str
    rubric: Rubric
    examples: list[GoldExample] = []


# ------------------------------------------------------------------ catalog
class Catalog(_Model):
    lifecycle: Lifecycle
    tiers: Tiers
    context_keys: dict[str, ContextKey]
    brand: Brand
    asset_types: dict[str, AssetType]
    version_hash: str  # set by the loader from the files' content; the model never computes it

    def gate(self, key: str) -> Gate:
        for gate in self.lifecycle.gates:
            if gate.key == key:
                return gate
        raise NotFoundError(f"unknown gate {key!r}")

    def gates_in_order(self) -> list[Gate]:
        return sorted(self.lifecycle.gates, key=lambda gate: gate.order)

    def tier(self, key: str) -> Tier:
        for tier in self.tiers.tiers:
            if tier.key == key:
                return tier
        raise NotFoundError(f"unknown tier {key!r}")

    def tiers_by_rank(self) -> list[Tier]:
        return sorted(self.tiers.tiers, key=lambda tier: tier.rank)

    def asset_type(self, key: str) -> AssetType:
        try:
            return self.asset_types[key]
        except KeyError:
            raise NotFoundError(f"unknown asset type {key!r}") from None

    def approver_roles_for(self, asset_key: str) -> list[str]:
        """Who may approve this asset: its own override, else its gate's approvers."""
        spec = self.asset_type(asset_key).spec
        roles = self.gate(spec.gate).approver_roles if spec.approver_roles is None else spec.approver_roles
        return list(roles)

    def core_assets(self, tier_key: str) -> list[str]:
        """The tier's expected assets. With ``inherits_lower`` that is its own ``core`` followed by the
        ``core`` of each smaller tier (larger rank) in increasing rank order, without repeats. Keys with no
        asset type are included: ``undefined_asset_keys`` reports them."""
        tier = self.tier(tier_key)
        chain = [tier]
        if self.tiers.inherits_lower:
            chain += [other for other in self.tiers_by_rank() if other.rank > tier.rank]
        return list(dict.fromkeys(key for member in chain for key in member.core))

    def optional_assets(self, tier_key: str) -> list[str]:
        """Assets a person may opt into for the tier. Never inherited."""
        return list(self.tier(tier_key).optional)

    def triggers_for(self, tier_key: str) -> list[Trigger]:
        self.tier(tier_key)  # an unknown tier is an error even for triggers that apply to every tier
        return [t for t in self.tiers.triggers if t.tiers is None or tier_key in t.tiers]

    def tier_decider(self) -> AssetType | None:
        """The asset type that classifies a solution into a tier, or None when there is none. (The
        validator allows only one; if there are several, the first by key.)"""
        for key in sorted(self.asset_types):
            if self.asset_types[key].spec.decides == "tier":
                return self.asset_types[key]
        return None

    def matrix(self) -> dict[str, dict[str, list[str]]]:
        """``{tier: {gate: [core asset keys, sorted]}}``: tiers by rank, every gate in gate order even when
        empty. Keys with no asset type are left out, and so are optional and triggered assets."""
        gates = self.gates_in_order()
        grid: dict[str, dict[str, list[str]]] = {}
        for tier in self.tiers_by_rank():
            defined = [key for key in self.core_assets(tier.key) if key in self.asset_types]
            grid[tier.key] = {
                gate.key: sorted(key for key in defined if self.asset_types[key].spec.gate == gate.key)
                for gate in gates
            }
        return grid

    def undefined_asset_keys(self) -> set[str]:
        """Asset keys that a tier (core or optional) or a trigger names but that have no asset type."""
        named = {key for tier in self.tiers.tiers for key in (*tier.core, *tier.optional)}
        named |= {key for trigger in self.tiers.triggers for key in trigger.assets}
        return named - self.asset_types.keys()

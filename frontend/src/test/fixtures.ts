/**
 * Typed test data. Every shape comes from the generated API types, so a changed endpoint breaks these
 * at compile time. `handlers.ts` builds the mock server from them.
 */
import type {
  ActivityEvent,
  AssetTypeResponse,
  AuthOptions,
  Brand,
  CatalogResponse,
  MatrixResponse,
  Me,
  Permission,
  ReloadResponse,
} from "@/api/types";

const ALL_PERMISSIONS: Permission[] = [
  "solution:read",
  "context:write",
  "import:run",
  "asset:generate",
  "asset:review",
  "audit:read",
  "catalog:read",
  "catalog:admin",
  "user:admin",
];

export const adminMe: Me = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "avery.admin@example.test",
  display_name: "Avery Admin",
  roles: ["admin"],
  role_info: [{ key: "admin", label: "Administrator", kind: "system" }],
  permissions: ALL_PERMISSIONS,
};

export const viewerMe: Me = {
  id: "00000000-0000-4000-8000-000000000002",
  email: "val.viewer@example.test",
  display_name: "Val Viewer",
  roles: ["viewer"],
  role_info: [{ key: "viewer", label: "Viewer", kind: "system" }],
  permissions: ["solution:read", "catalog:read"],
};

export const devUsers: Me[] = [adminMe, viewerMe];

export const devOptions: AuthOptions = {
  provider: "dev",
  dev_users: devUsers.map(({ id, display_name, roles }) => ({ id, display_name, roles })),
};

export const oidcOptions: AuthOptions = { provider: "oidc", dev_users: [] };

/** The nth event, newest first: `activityEvent(0)` is the latest. */
export function activityEvent(n: number, overrides: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    id: `event-${n}`,
    occurred_at: new Date(Date.UTC(2026, 10, 25, 12, 0, 0) - n * 60_000).toISOString(),
    actor_user_id: adminMe.id,
    actor_display: adminMe.display_name,
    action: "auth.login",
    entity_type: "user",
    entity_id: adminMe.id,
    request_id: `req-${String(n).padStart(8, "0")}`,
    ip: "127.0.0.1",
    user_agent: "test",
    details: {},
    before_hash: null,
    after_hash: null,
    ...overrides,
  };
}

/**
 * A small catalog shaped like the backend's `catalog_min`: two gates (the second a release gate), two
 * tiers, one trigger and five asset types. `catalogMatrix` is what the backend would compute from it;
 * the UI only renders it, so the tests check the cells as given.
 */
export const catalogOverview: CatalogResponse = {
  version_hash: "abc123def456",
  loaded_at: "2026-11-25T12:00:00Z",
  issues: {
    errors: 0,
    warnings: 1,
    todo_count: 2,
    items: [{ level: "warning", where: "brand/voice.md", message: "2 TODO(confirm) markers" }],
  },
  roles: [
    { key: "role_a", label: "Role A" },
    { key: "role_b", label: "Role B" },
  ],
  gates: [
    {
      key: "gate_one",
      label: "Gate One",
      short: "One",
      order: 1,
      approver_roles: ["role_a"],
      color: "#112233",
      release_gate: false,
    },
    {
      key: "gate_two",
      label: "Gate Two",
      short: "Two",
      order: 2,
      approver_roles: ["role_a", "role_b"],
      color: null,
      release_gate: true,
    },
  ],
  tiers: [
    {
      key: "tier_big",
      label: "Big",
      rank: 1,
      description: "The largest launches.",
      examples: ["An example of a big launch"],
      criteria: [{ key: "reach", label: "Reach", description: "How many customers it touches." }],
      channels: ["email"],
      timing: {
        anchor: "facts.launch_date",
        anchor_label: "Launch date",
        plan_start_days: -56,
        core_due_days: -14,
      },
    },
    {
      key: "tier_small",
      label: "Small",
      rank: 2,
      description: "The smallest launches.",
      examples: [],
      criteria: [],
      channels: [],
      timing: null,
    },
  ],
  triggers: [
    {
      key: "needs_setup",
      label: "Needs setup",
      description: "The customer has to set something up.",
      context_key: "facts.needs_setup",
      assets: ["setup_guide"],
      tiers: null,
    },
  ],
  asset_types: [
    ["brief", "Brief", "gate_one", "internal", true],
    ["classify", "Classify", "gate_one", "internal", false],
    ["deep_dive", "Deep dive", "gate_two", "external", false],
    ["extra_note", "Extra note", "gate_two", "internal", false],
    ["setup_guide", "Setup guide", "gate_two", "external", false],
  ].map(([key, name, gate, audience, foundation]) => ({
    key: String(key),
    name: String(name),
    gate: String(gate),
    audience: audience as "internal" | "external",
    family: "document",
    decides: null,
    foundation: foundation === true,
    example_count: 1,
  })),
};

const ref = (key: string, name: string) => ({ key, name });

export const catalogMatrix: MatrixResponse = {
  gates: [
    { key: "gate_one", short: "One" },
    { key: "gate_two", short: "Two" },
  ],
  rows: [
    {
      tier: { key: "tier_big", label: "Big" },
      cells: [[ref("brief", "Brief")], [ref("deep_dive", "Deep dive")]],
      optional: [ref("extra_note", "Extra note")],
      triggers: [
        { key: "needs_setup", label: "Needs setup", assets: [ref("setup_guide", "Setup guide")] },
      ],
    },
    {
      tier: { key: "tier_small", label: "Small" },
      cells: [[ref("brief", "Brief"), ref("classify", "Classify")], []],
      optional: [],
      triggers: [],
    },
  ],
  undefined_assets: ["not_there"],
};

/** The prompt carries raw HTML and a remote image on purpose: the UI shows the HTML as text and drops the image. */
export const briefAssetType: AssetTypeResponse = {
  approver_roles: ["role_a"],
  prompt_md:
    "Write a **short** brief.\n\n<script>alert(1)</script>\n\n![pixel](https://example.test/pixel.png)",
  rubric: {
    pass_threshold: 0.7,
    criteria: [{ key: "clear", title: "Clear", body_md: "Says one thing plainly." }],
  },
  examples: [
    {
      slug: "sample",
      title: "A sample brief",
      why_good: ["Short", "Grounded"],
      body_md: "Body of the sample.",
      context_summary: "",
      redacted: false,
      redactions: [],
      source: "",
      tier: null,
    },
  ],
  spec: {
    key: "brief",
    name: "Brief",
    gate: "gate_one",
    audience: "internal",
    family: "document",
    formats: ["md", "html"],
    effort: "medium",
    route: "writer",
    foundation: true,
    depends_on: [],
    required_context: ["facts.summary"],
    length: { words: 300 },
    approver_roles: null,
    decides: null,
  },
};

export const catalogBrand: Brand = {
  voice_md: "Plain and direct.",
  claims_md: "Only claim what is true.",
  legal_md: "Ask legal first.",
  terminology: {
    product_names: [{ name: "Widget", rules: "Always capitalised", never: ["widgit"] }],
    preferred: [{ use: "customer", avoid: ["user"] }],
    banned_external: ["synergy"],
  },
  visual: { colors: { primary: "#112233" }, fonts: {}, slide: {}, logo: null },
};

export const reloadOk: ReloadResponse = {
  ok: true,
  old_hash: "abc123def456",
  new_hash: "fedcba654321",
  issues: [],
};

export const reloadRejected: ReloadResponse = {
  ok: false,
  old_hash: "abc123def456",
  new_hash: null,
  issues: [{ level: "error", where: "tiers.yaml: tiers[tier_big].core", message: "unknown asset" }],
};

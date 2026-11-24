# Architecture (living document: update it at each milestone review)

## Flow
```
Context in ──► Facts / Snapshots ──► Planner ──► Jobs ──► Writer ─► Judges ─► Review ─► Publish
(Aha! file,     (stable IDs,        (gate ×      (worker)  (Claude on  (rules +   (RBAC     (HTML/DOCX/
 PDF, docs,      value hashes,       tier ×                 Bedrock,    rubric     approver, PPTX/PDF/
 notes, Q&A,     precedence)         catalog)               cached      LLM)       audit)    MP4+SRT)
 Aha! API)            │                                     prefix)                   │
                      └──── snapshot diff ──► stale assets ──► regenerate-with-diff ◄──┘
```

## Layers (`backend/src/gtm_studio/`)
| Layer (high to low) | May import | Must not import |
|---|---|---|
| `cli` | everything | — |
| `api`, `worker` | everything below; they wire adapters into services | each other |
| infrastructure: `adapters`, `db`, `auth`, `audit`, `catalog` | each other, `services` (port definitions), `domain`, third-party libraries | `api`, `worker`, `cli` |
| `services` | `domain`, the port protocols | fastapi, starlette, anthropic, boto3, concrete adapters (they're injected) |
| `domain` | stdlib, pydantic | sqlalchemy, fastapi, starlette, anthropic, boto3, httpx, `gtm_studio.settings`, any adapter, file IO |

The layering rules are enforced by three `import-linter` contracts in `backend/pyproject.toml` (`uv run lint-imports`). The infrastructure packages form one layer on purpose: `audit` writes `db` models and `auth` binds the actor into `audit.context`, so they must be able to import one another. `gtm_studio.settings` sits outside the layers; only `domain` is forbidden from importing it.

## Ports (protocols defined by services)
`UnitOfWork` (implemented: `services/ports.py`, `db/uow.py`) · `Repositories` (per aggregate) · `LLMClient` · `JobQueue` · `BlobStore` · `AuditLog` · `AhaSource` · `KnowledgeSource` · `DocumentExtractor` · `Renderer` (per format and family) · `TTSProvider` · `Clock` · `AuthProvider`

## Key aggregates
- `User`, `Role`, `UserRole`.
- `AuditEvent`, `LlmCall`.
- `Catalog` (in memory, with a version hash; roles synced to the DB).
- `Solution`, `Release`, `ContextSource`, `Fact`, `FactVersion`, `ContextSnapshot`, `GateDecision`.
- `Asset` (solution or release × asset type), `AssetVersion` (content JSON, snapshot ID, manifest, catalog version, model usage), `JudgeResult`, `Review`.
- `Job`.

## Claude on Bedrock
See the root `CLAUDE.md` § "Claude on Bedrock". Model routes live in `config/models.yaml`, e.g. `foundation` / `writer` / `judge` / `extract` / `smoke` → model ID or ARN, effort and `max_tokens`. The default for every route is Opus 5.5. Prices are in `config/pricing.yaml`.

## Deployment shape (target, not POC)
- API container and worker containers on Linux, plus one Windows worker for SAPI video.
- Postgres; S3 for the `BlobStore`.
- An IAM role for Bedrock; Secrets Manager.
- OIDC through the corporate IdP.

See `docs/hosting.md` (from S09) and `docs/security.md` (from S47).

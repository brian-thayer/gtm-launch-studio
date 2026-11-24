# ADR-0001: FastAPI + React, SQLAlchemy/Alembic, uv

- Status: accepted (2026-11-24)
- Deciders: product owner, Opus planning session

## Context
The first POC (Streamlit, `../GTM Operating System/`) proved the workflow, but it mixes business rules into UI scripts, runs long LLM jobs in the UI thread, and has no path to multi-user auth. The rebuild must stay a local POC, but one that Engineering can harden for hosting.

## Decision
- **Backend:**
  - Python 3.12 and FastAPI, managed with `uv`, in a `src/` layout with package `gtm_studio`.
  - Pydantic v2 everywhere.
  - SQLAlchemy 2 (typed ORM) with Alembic migrations: SQLite (WAL) locally, Postgres-portable.
  - Typer CLI `gtm`.
- **Frontend:**
  - React and Vite with strict TypeScript.
  - TanStack Router (code-based routes) and TanStack Query; Tailwind and shadcn/ui.
  - A typed client generated from the backend's OpenAPI schema (`openapi-typescript` + `openapi-fetch`).
- **Contract:** OpenAPI is the only interface between the frontend and backend. `gtm openapi` dumps the schema without starting a server.
- **Quality gates:**
  - Backend: ruff (lint and format), pyright, pytest, import-linter (layering).
  - Frontend: ESLint, Prettier, Vitest, and Playwright using the installed Edge (`channel: "msedge"`).

## Consequences
- Python keeps the existing Bedrock, rendering (DOCX, PPTX, Edge PDF) and SAPI video work portable from the old POC.
- Two toolchains to maintain, and Sonnet writes more code per feature than with Streamlit. Small step cards offset this.
- The production path (containers, Postgres, an OIDC IdP) needs configuration changes, not rewrites.

# S##: <Title>

Status: todo
Milestone: M#
Depends on: S##
Human in the loop: no | yes (<what the user must provide or decide>)
Size budget: about 300–600 changed lines, one session

## Goal
<1–2 sentences: the outcome, not the activity.>

## Why it matters
<1–2 sentences linking this step to the demo goal or to production readiness.>

## Read first
- `<path>`: <why>
- Old POC reference: `../GTM Operating System/<path>`: <what to port>

## Create / modify
- `<path>`: <purpose>

## Interfaces and contracts
<Signatures, Pydantic models, endpoints (method, path, permission, request and response), table columns, config keys.>

## Acceptance criteria
- [ ] <Testable statement>
- [ ] <Testable statement>

## Verification
```bash
cd backend && uv run pytest -q tests/<...>   # expect: all pass
```
<Manual check if any: what to open, what to click, and the expected result.>

## Out of scope
- <Things that look adjacent but belong to later steps>

## Notes
<Filled in by the implementer: deviations, follow-ups.>

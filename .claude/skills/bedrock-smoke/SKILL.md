---
name: bedrock-smoke
description: Verify Claude-on-Bedrock access with two small structured-output calls (checks model/route config, structured outputs, effort, and prompt-cache reads). Costs a few cents; requires explicit user approval. Available from step S30.
disable-model-invocation: true
---

# Bedrock smoke test

If `scripts/smoke_bedrock.py` doesn't exist yet (before S30), say so and stop.

1. Show the user what will run: 2 calls on the `smoke` route from `config/models.yaml`, the model ID or ARN, the AWS region, and a cost estimate (under $0.10). Ask for explicit approval.
2. From the repo root: `cd backend && GTM_ALLOW_BEDROCK=1 uv run python ../scripts/smoke_bedrock.py`. The guard hook will also ask.
3. Report each item with its value:
   - client class;
   - model;
   - structured output parsed;
   - `stop_reason`;
   - effort accepted;
   - `cache_creation_input_tokens` on call 1;
   - `cache_read_input_tokens` on call 2, which should be above 0;
   - latency;
   - the cost logged to `llm_calls`.
4. On failure, map the typed SDK error to a likely cause:
   - `AuthenticationError` or `PermissionDeniedError`: credentials, or model access not enabled;
   - `NotFoundError`: wrong model ID, region or ARN form;
   - `BadRequestError`: a parameter isn't supported on this endpoint.

   Don't retry in a loop.

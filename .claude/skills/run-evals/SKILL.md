---
name: run-evals
description: Run the asset-quality eval suite. Offline (MockLLM, free) by default; --bedrock runs real Claude generations + judges on Bedrock only after a cost estimate and explicit user approval. Available from step S45.
argument-hint: "[--bedrock] [--asset-type <key>] [--scenario <name>]"
disable-model-invocation: true
---

# Run evals $ARGUMENTS

If `backend/src/gtm_studio/evals/` doesn't exist yet (before S45), say so and stop.

## Offline (default)
- From `backend/`: `uv run gtm evals run --provider mock [filters]`.
- This checks the pipeline (schemas, citations, deterministic judges, rubric wiring), not quality. Report the pass/fail per scenario.

## Bedrock (`--bedrock`)
1. Run `uv run gtm evals estimate [filters]` and show the scenario count, the call count, and the estimated input/output tokens and cost.
2. **Ask the user for explicit approval with the estimate.** If they don't approve, stop.
3. Run `GTM_ALLOW_BEDROCK=1 uv run gtm evals run --provider bedrock [filters]`. The guard hook will ask too, and that is expected.
4. Report:
   - per asset type: rubric scores against the gold-example baseline, grounding failures, and judge-vs-human agreement (where reviewer data exists);
   - the actual cost against the estimate;
   - the 3 biggest regressions compared with the last run in `storage/evals/`.
5. For low-scoring assets, offer to run `gtm-content-reviewer` and propose concrete `prompt.md` or `rubric.md` edits.

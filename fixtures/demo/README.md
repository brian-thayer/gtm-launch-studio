# Demo fixtures (synthetic, safe to commit)

These files were copied from the first POC (`../GTM Operating System/`). They are **illustrative only** and are not the company's real data or GTM framework.

| Path | What | Used from |
|---|---|---|
| `aha/aha_export_v1.xlsx`, `v2`, `v3` | Snapshot sequence: a baseline, then the AI Proactive Outreach solution reaching GA candidate (approved), then a capability change that makes assets stale | S17, S18, S46 |
| `aha/aha_launch_mix.xlsx` | One file holding 11 solutions across 4 releases, for the next-launch flow | S41 |
| `aha/aha_list_features.csv` | An Aha! list export with no ref, status, gate or tier columns, for the "fill in missing data" flow | S17, S19 |
| `aha/aha_records_v2.pdf` | A mock Aha! record PDF (partial snapshot), *not* a real Aha! export | S20 |
| `aha/make_samples.reference.py` | The old generator script, kept for reference when samples need regenerating | — |
| `prds/ai-proactive-outreach.md` | A sample PRD for document upload and fact extraction | S21, S22 |
| `knowledge/` | Fictional competitor profiles, personas and customer-voice notes for the knowledge base | S26 |
| `catalog/` | The demo GTM catalog, converted from the old POC config | S10 |

When the user supplies real Aha! exports, add them as private local files. Never put them here.

# Drop zone for your GTM source material

Put your raw documents here, in any format (PDF, DOCX, PPTX, XLSX, MD). Everything in this folder except this README is **git-ignored**.

Subfolders are optional: files at the top level are fine, because the skills inventory the whole folder.

| Subfolder | What to put here | Used by |
|---|---|---|
| `brand/` | Brand guidelines: voice and tone, visual identity, logo files, naming rules, legal and claims guidance | `/ingest-brand-guidelines` (S12) |
| `tiers/` | Your GTM tier framework: tier definitions and criteria, plus which assets and channels each tier gets at each gate | `/ingest-tier-framework` (S11) |
| `lifecycle/` | Your product lifecycle and gate definitions, with approver roles (if separate from the tier doc) | `/ingest-tier-framework` (S11) |
| `asset_types/` | Your list of GTM asset types, with descriptions, owners and templates | `/add-asset-type` (S13) |
| `examples/<asset_type>/` | Gold-standard past assets of each type (battlecards, one-pagers, briefings, emails…) | `/add-gold-example` (S14) |
| `templates/` | Corporate DOCX and PPTX templates, if you want branded output | Renderers (S40) |

Claude Code reads these files and writes structured, reviewed files into `gtm_catalog/`. It never invents brand rules: anything it can't find here, it asks you about.

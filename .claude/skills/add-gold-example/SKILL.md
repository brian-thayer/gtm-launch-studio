---
name: add-gold-example
description: Add a redacted, annotated gold-standard example to gtm_catalog/asset_types/<key>/examples/ from a past asset in gtm_catalog/sources/examples/. Examples become style references for the writer and references for evals. Use for step S14.
argument-hint: "<asset_type_key> <source file>"
disable-model-invocation: true
---

# Add gold example: $ARGUMENTS

Follow `catalog-author` rules, and especially the redaction rules.

## Steps
1. Read the source file and the asset type's `spec.yaml`, `prompt.md` and `rubric.md`. If the example doesn't fit the asset type's structure, say so. It may be a different asset type.
2. Convert it to Markdown. Keep its structure and wording.
3. **Redact:**
   - customer and partner names (unless the user confirms they're public references);
   - people's names, emails and phone numbers;
   - unreleased product names the user flags;
   - confidential numbers.

   Use consistent placeholders (`[Customer A]`, `[Name]`, `[X%]`, `[$Y]`) and list them all in the frontmatter `redactions`.
4. Write `gtm_catalog/asset_types/<key>/examples/<slug>.md` with this frontmatter:
   ```yaml
   title: ...
   source: sources/examples/<file>        # the path only; the source stays git-ignored
   redacted: true
   redactions: [...]
   why_good: [3-6 bullets tied to rubric criteria]
   context_summary: one paragraph on the product situation it was written for (no confidential detail)
   tier: <tier key it was produced for, if known>
   ```
5. **Score it against `rubric.md`.** A gold example should score 4 or higher on every criterion. If it doesn't, tell the user. Either the rubric is wrong or this isn't a gold example.
6. Run `uv run gtm catalog validate`. Then show the user a redaction diff (each original term → its placeholder) so they can confirm, and ask whether the example file is safe to commit.

# Progress log

Newest entries go at the bottom. Each step appends one entry: what was built, any deviations, follow-ups, and verification evidence.

## S00 + S01: Repo and Claude Code harness (2026-11-24, Opus)
- Built:
  - git repo, `.gitignore`, README;
  - root CLAUDE.md, plus nested ones for `backend/`, `frontend/` and `gtm_catalog/`;
  - `.claude/settings.json` (permissions, plus PreToolUse, PostToolUse and Stop hooks);
  - 4 subagents and 8 skills;
  - ADRs 0001–0004, `docs/architecture.md`, ROADMAP, and full step cards S02–S15.
- Hooks are Python scripts in `.claude/hooks/`. They skip quietly until `uv` and the scaffolds exist.
- `guard_bash.py` was checked against sample commands. It denies `rm -rf` and `cat .env`; it asks before Bedrock-enabling commands, destructive DB commands and writes to the old POC; it allows ordinary commands.
- Follow-ups:
  - The user drops their brand, tier, lifecycle, asset-list and example material into `gtm_catalog/sources/` before S11.
  - Run `/fewer-permission-prompts` after M1.

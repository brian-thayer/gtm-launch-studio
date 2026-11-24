---
name: implement-step
description: Implement one roadmap step card (S##) end to end — branch, build, verify, independent review, progress log, commit. Use when the user types /implement-step S## or asks to build the next step.
argument-hint: "S## (e.g. S02), or 'next'"
disable-model-invocation: true
---

# Implement step $ARGUMENTS

Run this in a **fresh Sonnet session** (`claude --model sonnet`, or `/clear` and then `/model sonnet`). The step card is the brief, and the root and nested CLAUDE.md files hold the rules.

## 1. Locate and check
- If the argument is `next`, choose the first step in `docs/plan/ROADMAP.md` whose status is `todo` and whose `Depends on` steps are all `done`.
- Read the card `docs/plan/steps/<ID>-*.md`. If its status is `done`, or a dependency isn't `done`, stop and tell the user.
- If the card says **Human in the loop**, tell the user what input you'll need from them before you start.
- Run `git status`.
  - If there are uncommitted changes that don't belong to this step, stop and ask.
  - If `main` has no commits yet, stop and ask the user to commit the harness first.
- Create the branch: `git switch main && git switch -c step/<ID>-<slug>`.

## 2. Build
- Follow the procedure in `.claude/agents/step-implementer.md`, inline in this session:
  1. Read the card's **Read first** list.
  2. Port the old POC's tests first where the card says to.
  3. Implement within the card's file list.
  4. Run the **Verification** commands until they pass.
- Keep to the card's **Out of scope** list. If you find necessary work outside the scope, add it to the card's `## Notes` as a follow-up instead of doing it.
- If the card's **Verification** includes a manual UI check, start the app and check it yourself (headless Edge `--dump-dom`, or a Playwright test), then tell the user what to click.

## 3. Independent review
- Spawn the `code-reviewer` subagent with the prompt `Review step <ID>.` It reads the card and the diff itself. Don't pass it your own conclusions.
- If the verdict is **BLOCKED**, fix the blocking items, re-run verification, and run the reviewer once more. If it's still blocked, stop and report to the user.
- Fix cheap non-blocking nits. Leave the rest as follow-ups in `## Notes`.

## 4. Record
- In the card, set `Status: done` and fill in `## Notes` (deviations, follow-ups).
- In `docs/plan/ROADMAP.md`, set the step's status to `done`.
- In `docs/plan/PROGRESS.md`, append an entry:
  - `## <ID> <title> (<YYYY-MM-DD>)`;
  - built (3–6 bullets);
  - deviations;
  - follow-ups;
  - verification evidence: each command and its pass count.
- If the step changed a command or convention, update the relevant CLAUDE.md now.

## 5. Commit (the user confirms)
- `git add` only the files belonging to this step, and show `git status --short`.
- Commit message:
  ```
  <ID>: <card title>

  <2-4 lines: what and why>

  Generated with Claude Code
  ```
- Ask the user whether to fast-forward `main` (`git switch main && git merge --ff-only step/<ID>-<slug>`). Never push.

## 6. Report
Report in under 15 lines:
- what was built;
- verification results;
- the reviewer's verdict;
- follow-ups;
- the next step ID, plus whether it needs Opus (milestone boundary) or human input.

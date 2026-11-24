"""PreToolUse hook for Bash: block destructive commands, ask before anything that costs money.

Reads the hook payload (JSON) from stdin. Emits a permission decision as JSON on stdout.
Fails open (exit 0, no output) on any unexpected error so it never wedges a session.
"""

from __future__ import annotations

import json
import re
import sys

DENY = [
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r"),
     "rm -rf is blocked in this repo. Write to a fresh temp directory instead, or ask the user to delete."),
    (re.compile(r"\bcat\b[^|;&]*\.env(\s|$)|\btype\b[^|;&]*\.env(\s|$)"),
     "Reading .env files is not allowed. Use .env.example for variable names."),
]

ASK = [
    (re.compile(r"GTM_ALLOW_BEDROCK|GTM_LLM_PROVIDER=bedrock|--provider\s+bedrock|smoke_bedrock|-m\s+[\"']?bedrock"),
     "This command can call Claude on AWS Bedrock and costs money. Confirm the user approved a Bedrock run."),
    (re.compile(r"alembic\s+downgrade|gtm\s+db\s+(reset|downgrade)|\b(rm|del)\b[^|;&]*\.db\b"),
     "This command can destroy local data. Confirm with the user."),
]

# The old POC is a read-only reference: reading it is fine, writing to it needs confirmation.
OLD_POC = re.compile(r"GTM Operating System")
WRITES = re.compile(r"\b(mv|cp|rm|del|tee|touch|mkdir)\b|>|sed\s+-i")


def decide(command: str) -> tuple[str, str] | None:
    for pattern, reason in DENY:
        if pattern.search(command):
            return "deny", reason
    for pattern, reason in ASK:
        if pattern.search(command):
            return "ask", reason
    if OLD_POC.search(command) and WRITES.search(command):
        return "ask", "This command may modify the old POC folder, which is a read-only reference. Confirm with the user."
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        command = payload.get("tool_input", {}).get("command", "") or ""
    except Exception:
        return
    result = decide(command)
    if result is None:
        return
    decision, reason = result
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))


if __name__ == "__main__":
    main()

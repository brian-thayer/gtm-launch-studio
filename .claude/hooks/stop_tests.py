"""Stop hook: if backend Python files changed, run the fast unit tests before Claude finishes.

Exit 2 with a short failure summary makes Claude address the failures. Guards against
loops with `stop_hook_active`, and skips entirely until the backend scaffold exists.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    backend = root / "backend"
    if not (shutil.which("uv") and (backend / "pyproject.toml").exists() and (backend / "tests" / "unit").exists()):
        return 0
    try:
        changed = subprocess.run(
            ["git", "status", "--porcelain", "--", "backend/"],
            cwd=root, capture_output=True, text=True, timeout=20,
        ).stdout
    except Exception:
        return 0
    if ".py" not in changed:
        return 0
    try:
        proc = subprocess.run(
            ["uv", "run", "--quiet", "pytest", "-q", "-x", "tests/unit", "-m", "not bedrock and not slow"],
            cwd=backend, capture_output=True, text=True, timeout=150,
        )
    except subprocess.TimeoutExpired:
        return 0
    if proc.returncode in (0, 5):  # 5 = no tests collected
        return 0
    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-25:])
    print(f"Backend unit tests are failing after your changes. Fix them or explain why:\n{tail}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

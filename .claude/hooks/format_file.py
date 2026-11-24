"""PostToolUse hook for Edit/Write: auto-format the touched file.

Formatting only (ruff format, prettier) — never lint --fix, which can delete an import
that a later edit in the same task is about to use. Linting happens in each step's
verification commands. Silently skips when the toolchain isn't installed yet.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PRETTIER_EXT = {".ts", ".tsx", ".js", ".jsx", ".css", ".json", ".md"}


def run(cmd: list[str], cwd: Path) -> None:
    try:
        subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=60, check=False)
    except Exception:
        pass


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        file_path = Path(payload.get("tool_input", {}).get("file_path", ""))
    except Exception:
        return
    if not file_path.is_file():
        return
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    backend, frontend = root / "backend", root / "frontend"
    resolved = file_path.resolve()

    if resolved.suffix == ".py" and backend in resolved.parents:
        if shutil.which("uv") and (backend / "pyproject.toml").exists():
            run(["uv", "run", "--quiet", "ruff", "format", str(resolved)], backend)
    elif resolved.suffix in PRETTIER_EXT and frontend in resolved.parents:
        prettier = frontend / "node_modules" / ".bin" / ("prettier.cmd" if os.name == "nt" else "prettier")
        if prettier.exists():
            run([str(prettier), "--write", str(resolved)], frontend)


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
import re
import sys
import tempfile
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict, Any

# Meetup-grade static checks (NOT a hardened sandbox)
BANNED_PATTERNS = [
    r"\bimport\s+os\b",
    r"\bimport\s+subprocess\b",
    r"\bimport\s+socket\b",
    r"\bimport\s+requests\b",
    r"\bimport\s+http\b",
    r"\bimport\s+urllib\b",
    r"\bimport\s+pathlib\b",
    r"\bopen\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\b__import__\s*\(",
]

SAFE_NOTE = (
    "Execution policy: temporary working directory, time-limited, and blocks some risky "
    "imports/calls. This is NOT a hardened sandbox."
)

@dataclass
class PythonRunResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    note: str = SAFE_NOTE


def _is_code_allowed(code: str) -> Optional[str]:
    for pat in BANNED_PATTERNS:
        if re.search(pat, code):
            return f"Blocked by policy (matched pattern: {pat})."
    return None


def run_python(code: str, timeout_s: int = 3) -> Dict[str, Any]:
    """
    Executes Python code with basic restrictions.
    Returns a JSON-serializable dict with stdout/stderr.
    """
    deny_reason = _is_code_allowed(code)
    if deny_reason:
        return {
            "ok": False,
            "stdout": "",
            "stderr": deny_reason,
            "exit_code": -1,
            "note": SAFE_NOTE,
        }

    with tempfile.TemporaryDirectory(prefix="agent_exec_") as td:
        script_path = os.path.join(td, "main.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        cmd = [sys.executable, "-I", script_path]

        try:
            proc = subprocess.run(
                cmd,
                cwd=td,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env={
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONIOENCODING": "utf-8",
                },
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "exit_code": proc.returncode,
                "note": SAFE_NOTE,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "ok": False,
                "stdout": e.stdout or "",
                "stderr": (e.stderr or "") + f"\nTimed out after {timeout_s}s.",
                "exit_code": -2,
                "note": SAFE_NOTE,
            }

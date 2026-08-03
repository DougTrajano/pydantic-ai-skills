#!/usr/bin/env python3
"""Stop hook: no session ends with a red test suite.

The full suite runs in well under a minute, so there is no reason for an agent
to hand back Python changes it never executed. The gate only fires when the
session actually touched Python, and only once per stop (`stop_hook_active`
guards against a block loop).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _hookutil import block, changed_files, read_event, run

WATCHED_DIRS = ('pydantic_ai_skills', 'tests')
MAX_OUTPUT_LINES = 40


def touched_python(paths: list[Path]) -> list[Path]:
    """Return the changed Python files under the package or the test suite."""
    return [p for p in paths if p.suffix == '.py' and p.parts and p.parts[0] in WATCHED_DIRS]


def tail(text: str, lines: int = MAX_OUTPUT_LINES) -> str:
    """Return the last `lines` lines of `text` — pytest puts the failure summary last."""
    return '\n'.join(text.strip().splitlines()[-lines:])


def main() -> None:
    """Run the test suite when the session changed Python, and block on failure."""
    event = read_event()
    # Set when this hook already blocked once; running again would loop forever.
    if event.get('stop_hook_active'):
        return
    if not touched_python(changed_files()):
        return

    # --no-cov: this gate is about correctness and speed. Coverage (and its
    # threshold) is enforced by CI, which runs the suite properly.
    result = run([sys.executable, '-m', 'pytest', '-q', '-x', '--no-cov', '-m', 'not slow'], timeout=900)
    if result.returncode != 0:
        block(
            'The test suite fails on the changes in this session. Fix it before finishing '
            f'(`python -m pytest -q -x`):\n\n{tail(result.stdout or result.stderr)}'
        )


if __name__ == '__main__':
    main()

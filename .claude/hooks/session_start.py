#!/usr/bin/env python3
"""SessionStart hook: make the quality gates runnable before the agent needs them.

A fresh container (Claude Code on the web, a CI sandbox) starts with none of this
project's dependencies installed, so `pytest` and `mypy` fail with import errors
and an agent that cannot run them tends to ship code it never checked. This
installs the dev extras once per session and tells the agent what the gates are.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _hookutil import have, project_dir, run

EXTRAS = '.[test,git,s3,dev]'

CONTEXT = """\
Quality gates for this repository (see docs/contributing.md):

- `python -m pytest` — full suite, runs in seconds; a Stop hook blocks on failures.
- `pre-commit run --all-files` — ruff, ruff-format, mypy, actionlint, zizmor. This is what CI's lint job runs.
- Edits to `*.py` and `.github/workflows/*.yml` are linted automatically after every Write/Edit.
- Before pushing, run the `pre-push-review` skill.
"""


def install() -> tuple[bool, str]:
    """Install the dev extras, preferring uv. Returns (ok, message)."""
    in_venv = sys.prefix != sys.base_prefix
    if have('uv'):
        cmd = ['uv', 'pip', 'install', '--quiet', '-e', EXTRAS]
        # Outside a virtualenv uv refuses to touch the interpreter without --system.
        if not in_venv:
            cmd.insert(3, '--system')
    else:
        cmd = [sys.executable, '-m', 'pip', 'install', '--quiet', '-e', EXTRAS]

    result = run(cmd, timeout=600)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()[-500:]
    return True, ''


def main() -> None:
    """Install dependencies when they are missing and print the session context."""
    if importlib.util.find_spec('pydantic_ai') is None:
        ok, error = install()
        if ok:
            print(f'Installed {EXTRAS} into the session interpreter.')
        else:
            # Never fail the hook: a session with no network is still a usable
            # session, it just cannot run the suite. Say so rather than dying.
            print(f'Could not install {EXTRAS} ({error}). `pytest` and `mypy` will not run in this session.')

    print(CONTEXT)


if __name__ == '__main__':
    # `project_dir()` is where every command must run; _hookutil.run defaults to it.
    assert project_dir().exists()
    main()

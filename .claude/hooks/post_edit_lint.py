#!/usr/bin/env python3
"""PostToolUse hook: lint whatever the agent just wrote, immediately.

Python files get `ruff format` + `ruff check --fix` (the same tools, config and
version CI's `pre-commit` job runs). Workflow files get `actionlint` + `zizmor`,
so a generated workflow is checked for expression injection and over-broad
permissions before it is ever pushed.

Anything the auto-fixers cannot resolve is reported back to the agent as a
blocking error, so the fix happens in the same turn as the mistake.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _hookutil import block, have, project_dir, read_event, relative_to_project, run

WORKFLOW_DIR = Path('.github/workflows')


def lint_python(path: Path) -> list[str]:
    """Format and lint a Python file, returning any unresolved problems."""
    if not have('ruff'):
        return []
    problems: list[str] = []
    # `ruff format` and `--fix` rewrite the file in place; only what survives them
    # is worth the agent's attention.
    run(['ruff', 'format', str(path)], timeout=60)
    run(['ruff', 'check', '--fix', str(path)], timeout=60)
    check = run(['ruff', 'check', str(path)], timeout=60)
    if check.returncode != 0:
        problems.append(check.stdout.strip() or check.stderr.strip())
    return problems


WORKFLOW_LINTERS: tuple[tuple[str, list[str]], ...] = (
    ('actionlint', []),
    # --offline: the online audits need a GitHub token, which a local session has
    # no reason to hold. Configuration comes from .github/zizmor.yml.
    ('zizmor', ['--offline', '--persona=regular']),
)


def lint_workflow(path: Path) -> list[str]:
    """Lint a GitHub Actions workflow, returning any problems found."""
    problems: list[str] = []
    for tool, args in WORKFLOW_LINTERS:
        if have(tool):
            result = run([tool, *args, str(path)], timeout=180)
        elif have('pre-commit'):
            # Neither linter is a Python dependency of this project, so normally
            # neither is on PATH — but pre-commit owns a pinned copy of both, with
            # the same arguments CI uses. Use that rather than skipping the check.
            result = run(['pre-commit', 'run', tool, '--files', str(path)], timeout=600)
        else:
            continue
        if result.returncode != 0:
            problems.append(result.stdout.strip() or result.stderr.strip())
    return problems


def main() -> None:
    """Lint the file named by the tool call that just ran."""
    event = read_event()
    file_path = (event.get('tool_input') or {}).get('file_path')
    if not file_path:
        return

    relative = relative_to_project(file_path)
    # Files outside the repo (scratch space, /tmp) are not ours to police.
    if relative is None or not (project_dir() / relative).is_file():
        return

    if relative.suffix == '.py':
        problems = lint_python(relative)
        tool = 'ruff'
    elif relative.parent == WORKFLOW_DIR and relative.suffix in {'.yml', '.yaml'}:
        problems = lint_workflow(relative)
        tool = 'actionlint/zizmor'
    else:
        return

    if problems:
        details = '\n\n'.join(p for p in problems if p)
        block(f'{tool} still reports problems in {relative} after auto-fixes. Fix them before moving on:\n\n{details}')


if __name__ == '__main__':
    main()

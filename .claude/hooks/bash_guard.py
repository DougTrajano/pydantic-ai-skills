#!/usr/bin/env python3
"""PreToolUse hook: refuse the git commands that route around the quality gates.

Every rule here exists because the command it blocks makes a check *look* green
without the check having run:

- `--no-verify` skips pre-commit, i.e. ruff, ruff-format and mypy;
- a bare `--force` push can silently discard commits (including someone else's);
- pushing straight to `main` skips CI, review and the branch protection that
  makes the other gates mean anything.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _hookutil import block, read_event

PROTECTED_BRANCH = 'main'

NO_VERIFY = re.compile(r'(?:^|\s)--no-verify(?=\s|$)')
# `-n` is the short form of --no-verify for `git commit`, but of --dry-run for
# `git push` — a dry run is harmless, so the short form only counts on commits.
COMMIT_SHORT_NO_VERIFY = re.compile(r'\bgit\s+commit\b[^|;&]*?(?:^|\s)-n(?=\s|$)')
GIT_COMMIT_OR_PUSH = re.compile(r'\bgit\s+(?:commit|push)\b')
GIT_PUSH = re.compile(r'\bgit\s+push\b')
FORCE_FLAG = re.compile(r'(?:^|\s)(?:--force|-f)(?=\s|$)')
FORCE_WITH_LEASE = re.compile(r'--force-with-lease')
PUSH_TO_MAIN = re.compile(rf'\bgit\s+push\b[^|;&]*?(?:^|\s){PROTECTED_BRANCH}(?::\S+)?(?=\s|$)')


def check(command: str) -> str | None:
    """Return the reason `command` must be refused, or None when it is allowed."""
    if (GIT_COMMIT_OR_PUSH.search(command) and NO_VERIFY.search(command)) or COMMIT_SHORT_NO_VERIFY.search(command):
        return (
            '`--no-verify` skips the pre-commit hooks (ruff, ruff-format, mypy), which is exactly '
            'what CI runs. Fix what the hooks report instead of bypassing them.'
        )
    if GIT_PUSH.search(command) and FORCE_FLAG.search(command) and not FORCE_WITH_LEASE.search(command):
        return (
            'A bare force push can discard commits that are not in your local history. '
            'Use `git push --force-with-lease` if you genuinely need to rewrite the branch.'
        )
    if PUSH_TO_MAIN.search(command):
        return (
            f'Pushing directly to `{PROTECTED_BRANCH}` skips CI, the AI review and branch protection. '
            'Push to a feature branch and open a pull request.'
        )
    return None


def main() -> None:
    """Inspect the Bash command about to run and block it when it bypasses a gate."""
    event = read_event()
    command = (event.get('tool_input') or {}).get('command') or ''
    reason = check(command)
    if reason:
        block(reason)


if __name__ == '__main__':
    main()

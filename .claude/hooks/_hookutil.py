"""Shared helpers for the repository's Claude Code hooks.

The hooks are the local half of the quality gates described in
`docs/contributing.md`: they run the same tools CI runs, but while the agent is
still editing, so a violation is fed back as tool output instead of surfacing as
a red check twenty minutes later.

Hook protocol (https://docs.claude.com/en/docs/claude-code/hooks):

- the event payload arrives as JSON on stdin;
- exit 0 means "allow, nothing to say";
- exit 2 means "block", and stderr is fed back to the agent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Exit code that makes Claude Code block the action and show stderr to the agent.
BLOCK = 2


def read_event() -> dict:
    """Read the hook event payload from stdin.

    Returns:
        The decoded event, or an empty dict when stdin holds no valid JSON.
    """
    try:
        return json.loads(sys.stdin.read() or '{}')
    except (json.JSONDecodeError, ValueError):
        return {}


def project_dir() -> Path:
    """Return the repository root Claude Code is running in."""
    return Path(os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())).resolve()


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """Run `cmd`, capturing output as text and never raising on a non-zero exit."""
    return subprocess.run(
        cmd,
        cwd=cwd or project_dir(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def have(tool: str) -> bool:
    """Return whether `tool` is on PATH."""
    return shutil.which(tool) is not None


def block(message: str) -> None:
    """Fail the hook so Claude Code blocks the action and shows `message` to the agent."""
    print(message.rstrip(), file=sys.stderr)
    sys.exit(BLOCK)


def relative_to_project(path: str | Path) -> Path | None:
    """Return `path` relative to the project root, or None when it lives outside it."""
    try:
        return Path(path).resolve().relative_to(project_dir())
    except ValueError:
        return None


def changed_files() -> list[Path]:
    """Return paths with uncommitted changes, relative to the project root.

    Includes staged, unstaged and untracked files. Returns an empty list when git
    is unavailable or the directory is not a work tree.
    """
    if not have('git'):
        return []
    result = run(['git', 'status', '--porcelain', '--untracked-files=all'], timeout=30)
    if result.returncode != 0:
        return []
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:]
        # Renames are reported as "old -> new"; only the new path still exists.
        if ' -> ' in entry:
            entry = entry.split(' -> ', 1)[1]
        paths.append(Path(entry.strip().strip('"')))
    return paths

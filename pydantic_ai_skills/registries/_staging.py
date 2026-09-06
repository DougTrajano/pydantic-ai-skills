"""Shared filesystem helpers for materializing skill libraries.

The composition wrappers (filtered, prefixed, renamed, combined) present a *different*
library than the one they wrap: a subset of it, or one whose skills are named
differently. Since a registry's contract is to hand back a directory harness can read,
those wrappers do their work by staging real directories rather than by mapping objects
in memory.

[`copy_skill_directory`][pydantic_ai_skills.registries._staging.copy_skill_directory]
carries the path-traversal and symlink-escape checks that every copy out of an untrusted
source must keep.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

__all__ = ['copy_skill_directory', 'staging_directory']

_STAGING_PREFIX = 'pydantic-ai-skills-staging-'

# Staging directories outlive the call that creates them -- they are handed to harness,
# which reads them for the lifetime of the agent -- so the TemporaryDirectory objects are
# parked here and cleaned up when the process exits.
_STAGING_HANDLES: list[tempfile.TemporaryDirectory[str]] = []


def staging_directory(target_dir: str | Path | None = None) -> Path:
    """Return an empty directory to stage a composed skill library into.

    Args:
        target_dir: Where to stage. When None, a process-lifetime temporary directory is
            used. An existing directory is emptied so a re-sync does not leave skills
            behind that the composition no longer selects.

    Returns:
        Path to an existing, empty directory.
    """
    if target_dir is None:
        handle = tempfile.TemporaryDirectory(prefix=_STAGING_PREFIX)
        _STAGING_HANDLES.append(handle)
        return Path(handle.name)

    staged = Path(target_dir).expanduser().resolve()
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    return staged


def copy_skill_directory(src_skill_dir: str | Path, target_dir: str | Path, skill_name: str) -> Path:
    """Copy a skill directory into ``target_dir/skill_name`` with safety checks.

    Args:
        src_skill_dir: Source skill directory to copy from.
        target_dir: Destination root directory; a ``skill_name`` subdirectory is
            created inside it.
        skill_name: Name of the skill (used as the destination subdirectory name).

    Returns:
        Path to the copied skill directory (``target_dir/skill_name``).

    Raises:
        ValueError: When the destination or any source path escapes its expected
            directory (path traversal / symlink-escape protection).
    """
    dest_root = Path(target_dir).expanduser().resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    dest_skill_dir = dest_root / skill_name

    # Path traversal check on destination.
    if not dest_skill_dir.resolve().is_relative_to(dest_root):
        raise ValueError(f"Destination path '{dest_skill_dir}' escapes target directory '{dest_root}'.")

    # Validate no source symlinks escape the skill directory.
    src_resolved = Path(src_skill_dir).resolve()
    for src_file in src_resolved.rglob('*'):
        if src_file.is_symlink() or src_file.is_file():
            try:
                src_file.resolve().relative_to(src_resolved)
            except ValueError as exc:
                raise ValueError(
                    f"Source path '{src_file}' escapes skill directory (path traversal detected)."
                ) from exc

    if dest_skill_dir.exists():
        shutil.rmtree(dest_skill_dir)
    shutil.copytree(src_resolved, dest_skill_dir)

    return dest_skill_dir

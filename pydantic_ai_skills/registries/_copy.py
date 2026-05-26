"""Shared filesystem helpers for copying skill directories into a target dir.

Used by the concrete registries (e.g. :class:`GitSkillsRegistry`,
:class:`S3SkillsRegistry`) to install a skill while enforcing path-traversal and
symlink-escape protection.
"""

from __future__ import annotations

import shutil
from pathlib import Path

__all__ = ['copy_skill_directory']


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

"""Shared staging helpers for sandbox script executors.

Sandboxes need the skill's files copied in before a script can run. Getting the
boundary right matters: stage too little and relative paths break, stage too
much and a script can read files it should not see.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai_skills.types import SkillScript

__all__ = ['iter_stageable_files', 'skill_root_for']


def skill_root_for(script: SkillScript) -> Path:
    """Resolve the skill folder root that a script belongs to.

    Anchored on the nearest ancestor holding a ``SKILL.md``, which is what
    actually defines a skill folder. Deriving it from ``script.name`` alone is
    not safe: discovery stores a *resolved* ``uri`` but an *unresolved* name, so
    an in-tree symlink that changes depth (``skill/scripts/run.py`` pointing at
    ``skill/run.py``) would walk up too far and stage the parent directory,
    exposing sibling skills. The name-depth walk is kept only as a fallback for
    scripts built outside discovery.

    Args:
        script: A file-based script with a ``uri``.

    Returns:
        Resolved path to the skill folder.
    """
    script_path = Path(str(script.uri)).resolve()
    for candidate in script_path.parents:
        if (candidate / 'SKILL.md').is_file():
            return candidate

    root = script_path.parent
    for _ in range(len(PurePosixPath(script.name).parts) - 1):
        root = root.parent
    return root


def iter_stageable_files(skill_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(relative_posix_path, resolved_file)`` for files safe to stage.

    Symlinks that resolve outside ``skill_root`` are skipped with a warning.
    Discovery already rejects those, but staging re-walks the folder, and
    following such a link would copy an arbitrary host file into the sandbox
    where the script could read it back out.

    Args:
        skill_root: Resolved path to the skill folder.

    Yields:
        Tuples of the path relative to ``skill_root`` and the resolved file.
    """
    for path in sorted(skill_root.rglob('*')):
        resolved = path.resolve()
        if not resolved.is_relative_to(skill_root):
            warnings.warn(
                f"Skipping '{path}': resolves outside the skill folder (symlink escape detected).",
                UserWarning,
                stacklevel=2,
            )
            continue
        if resolved.is_file():
            yield path.relative_to(skill_root).as_posix(), resolved


def _stage_snapshot(skill_root: Path) -> tuple[list[tuple[str, Path]], tuple[tuple[str, int, int], ...]]:
    """Walk the skill folder once, returning its files and a change fingerprint.

    The fingerprint covers every staged path with its size and modification
    time, so a reused sandbox can tell whether the source skill was edited since
    it was staged — ``auto_reload`` and ``reload()`` both surface edits under an
    unchanged skill root.

    Args:
        skill_root: Resolved path to the skill folder.

    Returns:
        The staged ``(relative, resolved)`` pairs and their fingerprint.
    """
    entries: list[tuple[str, Path]] = []
    fingerprint: list[tuple[str, int, int]] = []
    for relative, resolved in iter_stageable_files(skill_root):
        entries.append((relative, resolved))
        stat = resolved.stat()
        fingerprint.append((relative, stat.st_size, stat.st_mtime_ns))
    return entries, tuple(fingerprint)

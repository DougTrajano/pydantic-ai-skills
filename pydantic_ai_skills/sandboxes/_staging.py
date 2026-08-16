"""Shared staging helpers for sandbox script executors.

Sandboxes need the skill's files copied in before a script can run. Getting the
boundary right matters: stage too little and relative paths break, stage too
much and a script can read files it should not see.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic_ai_skills.types import SkillScript

__all__ = ['EXCLUDED_STAGING_DIRS', 'iter_stageable_files', 'skill_root_for']

# Directories never copied into a sandbox.
#
# Version-control metadata is the important entry: a registry skill whose
# SKILL.md sits at the repository root makes the clone root the skill root, and
# GitSkillsRegistry clones with a token-bearing URL, so .git/config holds the
# caller's PAT. Staging it would hand that token to any script the sandbox runs.
# Discovery already excludes .git from resources for the same reason (see
# DEFAULT_RESOURCE_EXCLUDES in pydantic_ai_skills.directory).
EXCLUDED_STAGING_DIRS = frozenset({'.git', '.hg', '.svn', '.bzr', '__pycache__'})


def skill_root_for(script: SkillScript) -> Path:
    """Resolve the skill folder root that a script belongs to.

    Discovery records the folder it loaded the skill from on the script, and that
    is authoritative. Both fallbacks are lossy, which is why the recorded value
    exists: the nearest ``SKILL.md`` ancestor picks the wrong folder when a skill
    nests another skill, while walking up by ``script.name`` depth walks too far
    when an in-tree symlink changes the script's depth (``skill/scripts/run.py``
    pointing at ``skill/run.py``), staging sibling skills. They are used only for
    scripts built outside discovery.

    Args:
        script: A file-based script with a ``uri``.

    Returns:
        Resolved path to the skill folder.
    """
    recorded = getattr(script, 'skill_root', None)
    if recorded:
        return Path(recorded).resolve()

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

    Two things are filtered out:

    - :data:`EXCLUDED_STAGING_DIRS`, most importantly version-control metadata,
      which can hold the credentials a registry cloned with. Both the directories
      themselves and symlinks resolving into them are skipped.
    - Symlinks resolving outside ``skill_root``. Discovery already rejects those,
      but staging re-walks the folder, and following such a link would copy an
      arbitrary host file into the sandbox where the script could read it back out.

    Args:
        skill_root: Resolved path to the skill folder.

    Yields:
        Tuples of the path relative to ``skill_root`` and the resolved file.
    """
    for dirpath, dirnames, filenames in os.walk(skill_root):
        # Pruned in place so os.walk never descends into them.
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_STAGING_DIRS)

        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            resolved = path.resolve()
            if not resolved.is_relative_to(skill_root):
                warnings.warn(
                    f"Skipping '{path}': resolves outside the skill folder (symlink escape detected).",
                    UserWarning,
                    stacklevel=2,
                )
                continue

            # Pruning directories is not enough: a symlink elsewhere in the skill
            # (resources/config -> ../.git/config) is an ordinary file entry whose
            # target still lives under skill_root, and would alias a credential in.
            if EXCLUDED_STAGING_DIRS.intersection(resolved.relative_to(skill_root).parts):
                warnings.warn(
                    f"Skipping '{path}': resolves into an excluded directory.",
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

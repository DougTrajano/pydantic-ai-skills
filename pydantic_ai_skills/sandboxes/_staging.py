"""Shared staging helpers for sandbox script executors.

Sandboxes need the skill's files copied in before a script can run. Getting the
boundary right matters: stage too little and relative paths break, stage too
much and a script can read files it should not see.
"""

from __future__ import annotations

import hashlib
import os
import warnings
from collections.abc import Iterator
from dataclasses import dataclass
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


@dataclass(frozen=True)
class StagedFile:
    """One file to copy into a sandbox, with the bytes already read.

    Attributes:
        relative: Path relative to the skill root, posix-style.
        source: Resolved path on the host.
        data: File contents, read once and reused for both the fingerprint and
            the upload.
        executable: Whether the source file carries an execute bit.
    """

    relative: str
    source: Path
    data: bytes
    executable: bool


def _stage_snapshot(skill_root: Path) -> tuple[list[StagedFile], str]:
    """Walk the skill folder once, returning its files and a content fingerprint.

    The fingerprint is a digest of every staged path and its contents, so a
    reused sandbox can tell whether the source skill changed since it was
    staged. Size and mtime are not enough: reproducible-build tooling pins
    mtimes, so an edit that preserves file size would go unnoticed and the
    sandbox would keep running the previously staged script.

    Contents are read once here and carried on the returned entries, so hashing
    costs no extra I/O over staging itself.

    Args:
        skill_root: Resolved path to the skill folder.

    Returns:
        The staged files and a hex digest covering their paths and contents.
    """
    entries: list[StagedFile] = []
    digest = hashlib.sha256()
    for relative, resolved in iter_stageable_files(skill_root):
        data = resolved.read_bytes()
        entries.append(
            StagedFile(
                relative=relative,
                source=resolved,
                data=data,
                executable=bool(resolved.stat().st_mode & 0o111),
            )
        )
        digest.update(relative.encode('utf-8'))
        digest.update(b'\0')
        digest.update(hashlib.sha256(data).digest())
    return entries, digest.hexdigest()

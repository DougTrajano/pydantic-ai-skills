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

__all__ = ['EXCLUDED_STAGING_DIRS', 'iter_stageable_dirs', 'iter_stageable_files', 'skill_root_for']

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


def _safe_staged_file(path: Path, skill_root: Path) -> Path | None:
    """Resolve a file for staging, rejecting escapes and excluded targets.

    Args:
        path: Candidate file, possibly a symlink.
        skill_root: Resolved path to the skill folder.

    Returns:
        The resolved file, or None when it must not be staged.
    """
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as exc:
        # A symlink loop raises here on Python <=3.12; 3.13+ returns the path
        # unresolved instead and it is dropped by the is_file() check below.
        # Discovery tolerates such entries either way, so staging must not be
        # the thing that fails.
        warnings.warn(f"Skipping '{path}': {exc}", UserWarning, stacklevel=3)
        return None

    if not resolved.is_relative_to(skill_root):
        warnings.warn(
            f"Skipping '{path}': resolves outside the skill folder (symlink escape detected).",
            UserWarning,
            stacklevel=3,
        )
        return None

    # Pruning directories is not enough: a symlink elsewhere in the skill
    # (resources/config -> ../.git/config) is an ordinary file entry whose target
    # still lives under skill_root, and would alias a credential in.
    if EXCLUDED_STAGING_DIRS.intersection(resolved.relative_to(skill_root).parts):
        warnings.warn(f"Skipping '{path}': resolves into an excluded directory.", UserWarning, stacklevel=3)
        return None

    return resolved if resolved.is_file() else None


def _safe_directory_alias(directory: Path, skill_root: Path) -> Path | None:
    """Return the target of an in-tree directory symlink, or None.

    Args:
        directory: A symlinked directory inside the skill.
        skill_root: Resolved path to the skill folder.

    Returns:
        The resolved target when it is safe to stage under the alias.
    """
    try:
        target = directory.resolve()
    except (OSError, RuntimeError):
        return None  # Symlink loop; skipped like any other unusable alias.

    if not target.is_dir() or not target.is_relative_to(skill_root):
        return None
    if EXCLUDED_STAGING_DIRS.intersection(target.relative_to(skill_root).parts):
        return None
    return target


def _walk_files(root: Path, skill_root: Path) -> Iterator[tuple[Path, Path]]:
    """Yield ``(path, resolved)`` for stageable files under ``root``.

    Directory symlinks are not followed here; callers expand those explicitly.

    Args:
        root: Directory to walk.
        skill_root: Resolved path to the skill folder.

    Yields:
        Tuples of the walked path and its resolved target.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_STAGING_DIRS)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            resolved = _safe_staged_file(path, skill_root)
            if resolved is not None:
                yield path, resolved


def _partition_directories(
    dirpath: str, dirnames: list[str], skill_root: Path
) -> tuple[list[str], list[tuple[str, Path]]]:
    """Split walked subdirectories into ones to descend into and aliases to expand.

    os.walk does not follow directory symlinks, so an in-tree alias such as
    ``resources/current -> data/v2`` would simply be missing from the sandbox even
    though it resolves locally. Aliases are returned for the caller to expand once
    — one level only, so they cannot cycle.

    Args:
        dirpath: Directory currently being walked.
        dirnames: Its subdirectory names.
        skill_root: Resolved path to the skill folder.

    Returns:
        The subdirectories to descend into, and ``(alias, target)`` pairs.
    """
    kept: list[str] = []
    aliases: list[tuple[str, Path]] = []
    for name in sorted(dirnames):
        if name in EXCLUDED_STAGING_DIRS:
            continue
        directory = Path(dirpath) / name
        if not directory.is_symlink():
            kept.append(name)
            continue
        target = _safe_directory_alias(directory, skill_root)
        if target is not None:
            aliases.append((directory.relative_to(skill_root).as_posix(), target))
    return kept, aliases


def iter_stageable_files(skill_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(relative_posix_path, resolved_file)`` for files safe to stage.

    Two things are filtered out:

    - :data:`EXCLUDED_STAGING_DIRS`, most importantly version-control metadata,
      which can hold the credentials a registry cloned with. Both the directories
      themselves and symlinks resolving into them are skipped.
    - Symlinks resolving outside ``skill_root``. Discovery already rejects those,
      but staging re-walks the folder, and following such a link would copy an
      arbitrary host file into the sandbox where the script could read it back out.

    Directory symlinks that resolve safely inside the skill are staged under both
    their alias and their real path, so a script reading ``resources/current/x``
    finds it. They are expanded one level only, so aliases cannot cycle.

    Args:
        skill_root: Resolved path to the skill folder.

    Yields:
        Tuples of the path relative to ``skill_root`` and the resolved file.
    """
    aliases: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(skill_root):
        kept, found = _partition_directories(dirpath, dirnames, skill_root)
        dirnames[:] = kept
        aliases.extend(found)

        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            resolved = _safe_staged_file(path, skill_root)
            if resolved is not None:
                yield path.relative_to(skill_root).as_posix(), resolved

    for alias, target in aliases:
        for path, resolved in _walk_files(target, skill_root):
            yield f'{alias}/{path.relative_to(target).as_posix()}', resolved


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


def _iter_alias_dirs(alias: str, target: Path) -> Iterator[str]:
    """Yield the directory paths a staged alias contributes, including itself.

    Args:
        alias: Skill-relative path of the directory symlink.
        target: Its resolved in-tree target.

    Yields:
        Directory paths relative to the skill root, posix-style.
    """
    yield alias
    for dirpath, dirnames, _filenames in os.walk(target):
        # Pruned in place, so excluded trees are never descended into.
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_STAGING_DIRS)
        for name in dirnames:
            yield f'{alias}/{(Path(dirpath) / name).relative_to(target).as_posix()}'


def iter_stageable_dirs(skill_root: Path) -> Iterator[str]:
    """Yield skill-relative directory paths that are safe to create in a sandbox.

    Files alone are not enough: a skill may ship an empty directory that its
    script writes into, and creating only the ancestors of staged files would
    leave it missing.

    Args:
        skill_root: Resolved path to the skill folder.

    Yields:
        Directory paths relative to ``skill_root``, posix-style.
    """
    for dirpath, dirnames, _filenames in os.walk(skill_root):
        kept, aliases = _partition_directories(dirpath, dirnames, skill_root)
        dirnames[:] = kept
        for name in kept:
            yield (Path(dirpath) / name).relative_to(skill_root).as_posix()
        for alias, target in aliases:
            yield from _iter_alias_dirs(alias, target)


def _stage_snapshot(skill_root: Path) -> tuple[list[StagedFile], list[str], str]:
    """Walk the skill folder once, returning its files and a content fingerprint.

    The fingerprint is a digest of every staged path, its executable bit and its
    contents, so a reused sandbox can tell whether the source skill changed since
    it was staged. Size and mtime are not enough: reproducible-build tooling pins
    mtimes, so an edit that preserves file size would go unnoticed and the sandbox
    would keep running the previously staged script.

    Contents are read once here and carried on the returned entries, so hashing
    costs no extra I/O over staging itself.

    Args:
        skill_root: Resolved path to the skill folder.

    Returns:
        The staged files, the directories to create, and a hex digest covering
        their paths and contents.
    """
    entries: list[StagedFile] = []
    directories = sorted(set(iter_stageable_dirs(skill_root)))
    digest = hashlib.sha256()
    for directory in directories:
        digest.update(b'd\0')
        digest.update(directory.encode('utf-8'))
    for relative, resolved in iter_stageable_files(skill_root):
        data = resolved.read_bytes()
        executable = bool(resolved.stat().st_mode & 0o111)
        entries.append(StagedFile(relative=relative, source=resolved, data=data, executable=executable))

        digest.update(relative.encode('utf-8'))
        digest.update(b'\0')
        # The mode matters too: chmod +x with no content change makes discovery
        # treat the file as a script, and a stale 0644 copy would fail to execute.
        digest.update(b'x' if executable else b'-')
        digest.update(hashlib.sha256(data).digest())
    return entries, directories, digest.hexdigest()

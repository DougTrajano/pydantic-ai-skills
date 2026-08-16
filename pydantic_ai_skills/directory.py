"""Filesystem-based skill discovery and management.

This module provides [`SkillsDirectory`][pydantic_ai_skills.SkillsDirectory]
for discovering and loading skills from a filesystem directory.

Supports nested skill directories with configurable depth limits and provides
internal helper functions for skill validation, metadata parsing, and resource/script discovery.
"""

from __future__ import annotations

import codecs
import os
import warnings
from collections.abc import Iterable
from fnmatch import fnmatch
from pathlib import Path

from ._parsing import parse_skill_md, validate_skill_metadata
from .executors import SkillScriptExecutor
from .local import (
    LocalSkillScriptExecutor,
    create_file_based_resource,
    create_file_based_script,
)
from .types import Skill, SkillResource, SkillScript

_SUPPORTED_SCRIPT_EXTENSIONS = {'.py', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd'}
_WINDOWS_EXECUTABLE_EXTENSIONS = {'.exe', '.bat', '.cmd', '.com', '.ps1'}
_IGNORED_SCRIPT_NAMES = {'__init__.py', 'SKILL.md'}

#: Glob patterns always excluded from resource discovery. User-provided
#: ``exclude_resources`` patterns extend (do not replace) this set.
DEFAULT_RESOURCE_EXCLUDES: tuple[str, ...] = ('__pycache__', '*.pyc', '*.pyo', '.DS_Store', '.git')

_TEXT_SNIFF_BYTES = 65536


def _resolve_resource_excludes(exclude_resources: Iterable[str] | None) -> list[str]:
    """Build the resource exclude patterns, extending the built-in defaults.

    User-provided glob patterns are appended to :data:`DEFAULT_RESOURCE_EXCLUDES`,
    so noise such as ``__pycache__`` and ``.DS_Store`` stays excluded even when a
    caller supplies extra patterns.

    Args:
        exclude_resources: Extra glob patterns to exclude, or None for defaults only.

    Returns:
        List of glob patterns with the defaults first.
    """
    patterns = list(DEFAULT_RESOURCE_EXCLUDES)
    if exclude_resources is not None:
        patterns.extend(exclude_resources)
    return patterns


def _is_excluded(rel_path: Path, patterns: list[str]) -> bool:
    """Return True if a skill-relative path matches any exclude glob.

    A pattern matches when it matches the full posix-style relative path
    (for path-scoped patterns like ``docs/*.tmp``) or any single path
    component (for name patterns like ``__pycache__`` or ``*.pyc``).
    """
    posix = rel_path.as_posix()
    for pattern in patterns:
        if fnmatch(posix, pattern) or any(fnmatch(part, pattern) for part in rel_path.parts):
            return True
    return False


def _is_text_file(path: Path) -> bool:
    """Return True if a file reads as UTF-8 text (matching the resource loader).

    The loader reads resources with ``read_text('utf-8')``, so a file only
    qualifies as a resource if it decodes as UTF-8. To keep discovery cheap this
    inspects at most the first ``_TEXT_SNIFF_BYTES`` bytes rather than the whole
    file: binaries fail on the first invalid byte, and real text is text
    throughout. Files that fit within the window are validated exactly (a
    trailing multibyte character split by the window is not treated as invalid
    for larger files). Unreadable files are treated as non-text and skipped.
    """
    try:
        with path.open('rb') as handle:
            prefix = handle.read(_TEXT_SNIFF_BYTES)
            at_eof = handle.read(1) == b''
        codecs.getincrementaldecoder('utf-8')().decode(prefix, final=at_eof)
    except (UnicodeDecodeError, OSError):
        return False
    return True


def _is_script_candidate(script_file: Path) -> bool:
    """Check if a file should be treated as a script."""
    if script_file.name in _IGNORED_SCRIPT_NAMES or not script_file.is_file():
        return False

    suffix = script_file.suffix.lower()
    if suffix in _SUPPORTED_SCRIPT_EXTENSIONS:
        return True

    if os.name == 'nt':
        return suffix in _WINDOWS_EXECUTABLE_EXTENSIONS

    try:
        return bool(script_file.stat().st_mode & 0o111)
    except OSError:
        return False


def _iter_script_directories(skill_folder: Path) -> list[Path]:
    """Return directories to scan for scripts."""
    scripts_dir = skill_folder / 'scripts'
    if scripts_dir.is_dir():
        return [skill_folder, scripts_dir]
    return [skill_folder]


def _resolve_script_path(script_file: Path, skill_folder_resolved: Path) -> Path | None:
    """Resolve script path and reject symlink escapes."""
    resolved_path = script_file.resolve()
    try:
        resolved_path.relative_to(skill_folder_resolved)
    except ValueError:
        warnings.warn(
            f"Script '{script_file}' resolves outside skill directory (symlink escape detected). Skipping.",
            UserWarning,
            stacklevel=4,
        )
        return None
    return resolved_path


__all__ = [
    'DEFAULT_RESOURCE_EXCLUDES',
    'SkillsDirectory',
    'discover_skills',
    'parse_skill_md',
    'validate_skill_metadata',
]


def _discover_resources(
    skill_folder: Path,
    exclude_resources: Iterable[str] | None = None,
    script_uris: set[str] | None = None,
) -> list[SkillResource]:
    """Discover resource files in a skill folder.

    Any UTF-8-readable text file other than SKILL.md, in any subdirectory, is a
    resource. Binary files (anything that does not decode as UTF-8), files
    discovered as scripts, and files matching an exclude glob are skipped.

    Security validates that resolved paths remain within skill_folder
    after symlink resolution to prevent traversal attacks.

    Args:
        skill_folder: Path to the skill directory.
        exclude_resources: Extra glob patterns to exclude, in addition to the
            built-in :data:`DEFAULT_RESOURCE_EXCLUDES`. None for defaults only.
        script_uris: Resolved URIs of files already discovered as scripts, which
            are excluded from resources so a file is never both.

    Returns:
        List of discovered SkillResource objects.
    """
    resources: list[SkillResource] = []
    exclude_patterns = _resolve_resource_excludes(exclude_resources)
    script_uris = script_uris or set()
    skill_folder_resolved = skill_folder.resolve()

    for resource_file in skill_folder.rglob('*'):
        if not resource_file.is_file() or resource_file.name.upper() == 'SKILL.MD':
            continue

        rel_path = resource_file.relative_to(skill_folder)
        if _is_excluded(rel_path, exclude_patterns):
            continue

        resolved_path = resource_file.resolve()
        try:
            resolved_path.relative_to(skill_folder_resolved)
        except ValueError:
            warnings.warn(
                f"Resource '{resource_file}' resolves outside skill directory (symlink escape detected). Skipping.",
                UserWarning,
                stacklevel=2,
            )
            continue

        if str(resolved_path) in script_uris or not _is_text_file(resource_file):
            continue

        resources.append(
            create_file_based_resource(
                name=rel_path.as_posix(),
                uri=str(resolved_path),
            )
        )

    return resources


def _find_skill_files(root_dir: Path, max_depth: int | None) -> list[Path]:
    """Find SKILL.md files with depth-limited search using glob patterns.

    Args:
        root_dir: Root directory to search from.
        max_depth: Maximum depth to search. None for unlimited.

    Returns:
        List of paths to SKILL.md files.
    """
    if max_depth is None:
        return list(root_dir.glob('**/SKILL.md'))

    skill_files: list[Path] = []

    for depth in range(max_depth + 1):
        if depth == 0:
            pattern = 'SKILL.md'
        else:
            pattern = '/'.join(['*'] * depth) + '/SKILL.md'

        skill_files.extend(root_dir.glob(pattern))

    return skill_files


def _discover_scripts(
    skill_folder: Path,
    skill_name: str,
    executor: SkillScriptExecutor,
) -> list[SkillScript]:
    """Discover executable scripts in a skill folder.

    Looks for script files and executables in the root and scripts/ subdirectory.
    Security validates that resolved paths remain within skill_folder
    after symlink resolution to prevent traversal attacks.

    Args:
        skill_folder: Path to the skill directory.
        skill_name: Name of the parent skill.
        executor: Executor for running file-based scripts.

    Returns:
        List of discovered SkillScript objects.
    """
    scripts: list[SkillScript] = []
    skill_folder_resolved = skill_folder.resolve()

    for directory in _iter_script_directories(skill_folder):
        for script_file in directory.iterdir():
            if not _is_script_candidate(script_file):
                continue

            resolved_path = _resolve_script_path(script_file, skill_folder_resolved)
            if resolved_path is None:
                continue

            scripts.append(
                create_file_based_script(
                    name=script_file.relative_to(skill_folder).as_posix(),
                    uri=str(resolved_path),
                    skill_name=skill_name,
                    executor=executor,
                    skill_root=str(skill_folder_resolved),
                )
            )

    return scripts


def discover_skills(
    path: str | Path,
    validate: bool = True,
    max_depth: int | None = 3,
    script_executor: SkillScriptExecutor | None = None,
    exclude_resources: Iterable[str] | None = None,
) -> list[Skill]:
    """Discover skills from a filesystem directory.

    Searches for SKILL.md files in the given directory and loads
    skill metadata and structure.

    Args:
        path: Directory path to search for skills.
        validate: Whether to validate skill structure (requires name and description).
        max_depth: Maximum depth to search for SKILL.md files. None for unlimited.
            Default is 3 levels deep to prevent performance issues with large trees.
        script_executor: Optional custom script executor for file-based scripts.
        exclude_resources: Extra glob patterns to exclude from resource discovery, in
            addition to the built-in :data:`DEFAULT_RESOURCE_EXCLUDES`. None for
            defaults only.

    Returns:
        List of discovered Skill objects.

    Raises:
        ValueError: If validation is enabled and a skill is invalid, or if a
            skill file fails to load due to malformed contents or I/O errors.
    """
    skills: list[Skill] = []
    dir_path = Path(path).expanduser().resolve()

    if not dir_path.exists():
        return skills

    if not dir_path.is_dir():
        return skills

    # `is None`, not `or`: a custom executor defining __bool__/__len__ can be
    # falsey, and silently swapping it for the local one would run scripts
    # directly on the host.
    executor = LocalSkillScriptExecutor() if script_executor is None else script_executor
    skill_files = _find_skill_files(dir_path, max_depth)
    for skill_file in skill_files:
        try:
            skill = Skill.from_file(
                skill_file,
                validate=validate,
                script_executor=executor,
                exclude_resources=exclude_resources,
            )
            skills.append(skill)
        except ValueError as ve:
            if validate:
                raise
            else:
                warnings.warn(f'Skipping invalid skill at {skill_file}: {ve}', UserWarning, stacklevel=2)
        except (OSError, KeyError) as e:
            raise ValueError(f'Failed to load skill from {skill_file}: {e}') from e

    return skills


class SkillsDirectory:
    """Skill source for a single filesystem directory.

    Discovers and loads skills from a local directory by finding SKILL.md files
    and automatically discovering associated resources and scripts.

    File-based scripts are executed using the configured script executor, any
    object implementing the
    [`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor] protocol.
    """

    def __init__(
        self,
        *,
        path: str | Path,
        validate: bool = True,
        max_depth: int | None = 3,
        script_executor: SkillScriptExecutor | None = None,
        exclude_resources: Iterable[str] | None = None,
    ) -> None:
        """Initialize the skills directory source.

        Args:
            path: Directory path to search for skills.
            validate: Validate skill structure on discovery.
            max_depth: Maximum depth for skill discovery (None for unlimited).
            script_executor: Optional custom script executor for file-based scripts.
                Any object implementing the
                [`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor] protocol.
                If None, uses LocalSkillScriptExecutor with default settings.
            exclude_resources: Extra glob patterns to exclude from resource discovery,
                in addition to the built-in :data:`DEFAULT_RESOURCE_EXCLUDES`. None for
                defaults only.

        Example:
            ```python
            # Discovery mode - single directory
            source = SkillsDirectory(path="./skills")

            # With custom executor
            from pydantic_ai_skills import LocalSkillScriptExecutor

            executor = LocalSkillScriptExecutor(timeout=60)
            source = SkillsDirectory(path="./skills", script_executor=executor)

            # With callable executor
            from pydantic_ai_skills import CallableSkillScriptExecutor

            async def my_executor(script, args=None):
                return f"Executed {script.name}"

            executor = CallableSkillScriptExecutor(func=my_executor)
            source = SkillsDirectory(path="./skills", script_executor=executor)
            ```
        """
        self._path = Path(path).expanduser().resolve()
        self._validate = validate
        self._max_depth = max_depth
        # `is None`, not `or`: see discover_skills.
        self._script_executor = LocalSkillScriptExecutor() if script_executor is None else script_executor
        self._exclude_resources = exclude_resources

        # Discover skills from directory
        self._skills: dict[str, Skill] = self.get_skills()

    def get_skills(self) -> dict[str, Skill]:
        """Get all skills from this source.

        Returns:
            Dictionary of skill URI to Skill object.
        """
        skills = discover_skills(
            path=self._path,
            validate=self._validate,
            max_depth=self._max_depth,
            script_executor=self._script_executor,
            exclude_resources=self._exclude_resources,
        )

        return {skill.uri: skill for skill in skills if skill.uri is not None}

    @property
    def skills(self) -> dict[str, Skill]:
        """Get the dictionary of loaded skills.

        Returns:
            Dictionary mapping skill URI to Skill objects.
        """
        return self._skills

    def load_skill(self, skill_uri: str) -> Skill:
        """Load full instructions for a skill.

        Args:
            skill_uri: URI of the skill to load (skill name for filesystem skills).

        Returns:
            Loaded Skill object.

        Raises:
            KeyError: If skill is not found.
        """
        skill = self._skills.get(skill_uri)

        if skill is None:
            raise KeyError(f"Skill '{skill_uri}' not found in {self._path.as_posix()}.")

        return skill

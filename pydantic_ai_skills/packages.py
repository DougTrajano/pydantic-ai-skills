"""Bundled-file index for Agent Skill packages.

`pydantic-ai-harness`'s `Skills` capability reads a skill's `SKILL.md` and stops
there — it does not enumerate, read, or execute the `references/`, `assets/`, and
`scripts/` directories an Agent Skill package may ship. This module indexes exactly
those files so [`SkillsCapability`][pydantic_ai_skills.SkillsCapability] can expose
them to the model.

Discovery deliberately mirrors harness's rule: a skill is an **immediate** child
directory of a library that contains a `SKILL.md`. Nothing here parses or validates
frontmatter — harness owns that — so a package indexed by this module but rejected by
harness simply never reaches the model.
"""

from __future__ import annotations

import codecs
import os
import unicodedata
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

from pydantic_ai_skills.executors import SkillScriptExecutor
from pydantic_ai_skills.local import (
    LocalSkillScriptExecutor,
    create_file_based_resource,
    create_file_based_script,
)
from pydantic_ai_skills.types import SkillResource, SkillScript

__all__ = [
    'DEFAULT_RESOURCE_EXCLUDES',
    'SkillPackage',
    'index_libraries',
]

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
        for script_file in sorted(directory.iterdir()):
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

    for resource_file in sorted(skill_folder.rglob('*')):
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


@dataclass(frozen=True)
class SkillPackage:
    """The on-disk files of one Agent Skill package.

    Built by [`index_libraries`][pydantic_ai_skills.packages.index_libraries] for every
    immediate child directory of a skill library that contains a `SKILL.md`. Holds only
    what harness's `Skills` does not: the package's directory and its bundled resources
    and scripts.

    Attributes:
        name: The skill's directory name, NFKC-normalized so it matches the `id` harness
            gives the skill's deferred capability.
        directory: The resolved skill directory, or None for a programmatic skill that has
            no on-disk package. When set, this is the value substituted for
            `${SKILL_DIR}` / `${CLAUDE_SKILL_DIR}` in the skill's instructions.
        resources: Bundled text files, keyed in `resources_by_name` by their
            skill-relative posix path (e.g. `references/FORMS.md`).
        scripts: Bundled executables, named by their skill-relative posix path
            (e.g. `scripts/fill_form.py`).
    """

    name: str
    directory: Path | None = None
    resources: tuple[SkillResource, ...] = ()
    scripts: tuple[SkillScript, ...] = ()

    resources_by_name: dict[str, SkillResource] = field(init=False, repr=False, compare=False)
    scripts_by_name: dict[str, SkillScript] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Build the name lookups the skill-file tools resolve against."""
        object.__setattr__(self, 'resources_by_name', {resource.name: resource for resource in self.resources})
        object.__setattr__(self, 'scripts_by_name', {script.name: script for script in self.scripts})


def index_libraries(
    libraries: Sequence[str | Path],
    *,
    script_executor: SkillScriptExecutor | None = None,
    exclude_resources: Iterable[str] | None = None,
) -> dict[str, SkillPackage]:
    """Index the bundled files of every skill package in `libraries`.

    Scans the immediate child directories of each library for a `SKILL.md`, exactly as
    harness's `Skills` does, so the keys of the returned mapping line up with the `id`
    of each deferred capability harness produces.

    Later libraries win on a duplicate name, matching the argument order the caller
    passed to `Skills`. (harness rejects duplicates among *selected* skills outright, so
    a surviving duplicate here belongs to a skill that was excluded from the catalog.)

    Args:
        libraries: Skill-library directories. Non-existent entries are skipped rather
            than raising — harness validates library paths itself and reports them with
            a better message.
        script_executor: Executor used for the discovered scripts. Defaults to
            [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor],
            which runs them as subprocesses on the host.
        exclude_resources: Extra glob patterns to exclude from resource discovery, in
            addition to the built-in :data:`DEFAULT_RESOURCE_EXCLUDES`.

    Returns:
        Mapping of NFKC-normalized skill name to its
        [`SkillPackage`][pydantic_ai_skills.packages.SkillPackage].
    """
    # `is None`, not `or`: a falsey custom executor (e.g. a pool-backed one that is
    # empty at index time) must not be silently replaced by the host executor, which
    # would run untrusted scripts on the host.
    executor = LocalSkillScriptExecutor() if script_executor is None else script_executor
    packages: dict[str, SkillPackage] = {}

    for configured in libraries:
        library = Path(configured)
        if not library.is_dir():
            continue

        for child in sorted(library.iterdir()):
            if not child.is_dir() or not (child / 'SKILL.md').is_file():
                continue

            name = unicodedata.normalize('NFKC', child.name)
            scripts = _discover_scripts(child, name, executor)
            resources = _discover_resources(
                child,
                exclude_resources=exclude_resources,
                script_uris={script.uri for script in scripts if script.uri},
            )
            packages[name] = SkillPackage(
                name=name,
                directory=child.resolve(),
                resources=tuple(resources),
                scripts=tuple(scripts),
            )

    return packages

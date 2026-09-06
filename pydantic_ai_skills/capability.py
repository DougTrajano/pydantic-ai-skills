"""The `SkillsCapability` entry point.

[`SkillsCapability`][pydantic_ai_skills.SkillsCapability] is a composite capability that
delegates Agent Skills discovery, `SKILL.md` validation and instruction injection to
`pydantic-ai-harness`'s `Skills`, and adds the three things `Skills` does not do:

1. **Remote sources.** Registries (Git, S3, and compositions of them) are synced to local
   directories before `Skills` ever sees them.
2. **Bundled files.** Each skill's `references/`, `assets/` and `scripts/` files are
   indexed and reachable through `read_skill_resource` / `run_skill_script`.
3. **Programmatic skills.** Skills defined in Python join the same deferred catalog.

Each skill remains one deferred capability, loaded by the model through pydantic-ai's own
`load_capability` tool — this package does not add a `load_skill` tool of its own.
"""

from __future__ import annotations

import unicodedata
import warnings
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai.capabilities import AbstractCapability, Capability
from pydantic_ai.tools import AgentDepsT
from pydantic_ai.toolsets import AgentToolset
from pydantic_ai_harness import Skills

from pydantic_ai_skills._toolset import SkillFilesToolset
from pydantic_ai_skills.executors import SkillScriptExecutor
from pydantic_ai_skills.packages import SkillPackage, index_libraries
from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.types import Skill, SkillWrapper

__all__ = ['SkillsCapability']

#: Placeholders substituted with a skill's directory when `resolve_skill_dir` is set.
#: `${CLAUDE_SKILL_DIR}` is the spelling used by published Anthropic skill packages;
#: `${SKILL_DIR}` is the portable one. harness leaves both untouched by design.
_SKILL_DIR_PLACEHOLDERS = ('${SKILL_DIR}', '${CLAUDE_SKILL_DIR}')

#: Most entries of one kind listed in a skill's bundled-file inventory. A package shipping
#: more than this gets a count instead of a wall of names; the file tools' not-found retry
#: still reports the full list.
_MAX_LISTED_FILES = 50


def _normalize(name: str) -> str:
    """NFKC-normalize a skill name, matching how harness compares them."""
    return unicodedata.normalize('NFKC', name)


def _normalize_selection(option: str, values: Collection[str]) -> frozenset[str]:
    """Normalize an `include`/`exclude` collection of skill names.

    Args:
        option: Name of the option being normalized, used in error messages.
        values: Collection of skill names.

    Returns:
        Frozenset of NFKC-normalized skill names.

    Raises:
        TypeError: If `values` is a bare string or contains non-string entries.
    """
    if isinstance(values, str):
        raise TypeError(f'{option} must be a collection of skill names, not a string.')
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f'{option} must contain only skill names as strings.')
        normalized.add(_normalize(value))
    return frozenset(normalized)


def _resolve_placeholders(text: str, directory: Path | None) -> str:
    """Substitute the skill-directory placeholders in `text`."""
    if directory is None:
        return text
    for placeholder in _SKILL_DIR_PLACEHOLDERS:
        text = text.replace(placeholder, str(directory))
    return text


def _format_file_list(names: Sequence[str]) -> str:
    """Render indexed file names as a bullet list, truncated past `_MAX_LISTED_FILES`."""
    listed = [f'- `{name}`' for name in names[:_MAX_LISTED_FILES]]
    remaining = len(names) - len(listed)
    if remaining > 0:
        listed.append(f'- ...and {remaining} more')
    return '\n'.join(listed)


def _bundled_files_section(package: SkillPackage, *, resources: bool, scripts: bool) -> str | None:
    """Render the inventory of a skill's bundled files, or None when there is nothing to list.

    The names the file tools resolve against are skill-relative paths, but a `SKILL.md`
    usually refers to its own files in prose ("run the aggregate script"). Without this the
    model has to guess a path on its first call. Appending the inventory to the skill's
    *instructions* keeps it behind `load_capability` — the model pays for it only once it
    has loaded the skill, not in the always-on catalog.

    Args:
        package: The indexed package whose files to list.
        resources: The `read_skill_resource` tool is registered, so list resources.
        scripts: The `run_skill_script` tool is registered, so list scripts.

    Returns:
        A Markdown section, or None when neither kind has anything to list.
    """
    blocks: list[str] = []

    if resources and package.resources:
        names = sorted(resource.name for resource in package.resources)
        blocks.append(
            f'Read with `read_skill_resource`, using these exact `resource_name` values:\n\n{_format_file_list(names)}'
        )

    if scripts and package.scripts:
        names = sorted(script.name for script in package.scripts)
        blocks.append(
            f'Run with `run_skill_script`, using these exact `script_name` values:\n\n{_format_file_list(names)}'
        )

    if not blocks:
        return None

    return '## Bundled files\n\n' + '\n\n'.join(blocks)


@dataclass(init=False, repr=False)
class SkillsCapability(AbstractCapability[AgentDepsT]):
    """Expose Agent Skills — local, remote, or Python-defined — to a Pydantic AI agent.

    Every skill becomes its own deferred capability: the model sees names and descriptions
    up front and pulls a skill's instructions in with `load_capability`. Skills discovered
    on disk are validated and rendered by `pydantic-ai-harness`; this capability adds
    remote sources, the bundled-file tools, and programmatic skills on top.

    Discovery is a snapshot taken during construction, matching harness's own semantics.
    Call `registry.sync()` and build a new `SkillsCapability` to pick up changes.

    Example:
        ```python
        from pydantic_ai import Agent
        from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

        agent = Agent(
            'anthropic:claude-sonnet-4-6',
            capabilities=[
                SkillsCapability(
                    '.agents/skills',
                    registries=[
                        GitSkillsRegistry(
                            'https://github.com/anthropics/skills',
                            path='skills',
                        ),
                    ],
                ),
            ],
        )
        ```
    """

    directories: tuple[str | Path, ...]
    """Skill-library paths scanned during construction."""

    registries: tuple[SkillRegistry, ...]
    """Registries synced to local libraries during construction."""

    include: frozenset[str] | None
    """Exact skill names to expose, or `None` to expose all discovered skills."""

    exclude: frozenset[str]
    """Exact skill names to omit from the catalog."""

    _skills: Skills[AgentDepsT] | None = field(init=False, repr=False, compare=False)
    _packages: dict[str, SkillPackage] = field(init=False, repr=False, compare=False)
    _leaves: tuple[AbstractCapability[AgentDepsT], ...] = field(init=False, repr=False, compare=False)
    _files_toolset: SkillFilesToolset | None = field(init=False, repr=False, compare=False)
    _list_resources: bool = field(init=False, repr=False, compare=False)
    _list_scripts: bool = field(init=False, repr=False, compare=False)

    def __init__(
        self,
        directories: str | Path | Sequence[str | Path] = (),
        *,
        registries: Sequence[SkillRegistry] = (),
        skills: Sequence[Skill | SkillWrapper[Any]] = (),
        include: Collection[str] | None = None,
        exclude: Collection[str] | None = None,
        script_executor: SkillScriptExecutor | None = None,
        exclude_resources: Sequence[str] | None = None,
        resources: bool = True,
        scripts: bool = True,
        require_loaded: bool = True,
        resolve_skill_dir: bool = True,
        list_bundled_files: bool = True,
        id: str | None = None,
    ) -> None:
        """Build the deferred catalog from libraries, registries and Python-defined skills.

        Args:
            directories: One skill-library path or a sequence of them. A library is the
                *parent* of the skill packages, not a skill package itself.
            registries: Registries to sync into local libraries before discovery. See
                [`SkillRegistry`][pydantic_ai_skills.SkillRegistry].
            skills: Python-defined skills, which join the same deferred catalog.
            include: Exact names to expose. Omit to expose all discovered skills.
            exclude: Exact names to omit. Cannot be combined with `include`.
            script_executor: Executor for bundled scripts. Defaults to
                [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor],
                which runs them as subprocesses on the host. Pass a sandbox executor for
                skills from sources you do not fully trust.
            exclude_resources: Extra glob patterns to exclude from resource discovery, on
                top of
                [`DEFAULT_RESOURCE_EXCLUDES`][pydantic_ai_skills.packages.DEFAULT_RESOURCE_EXCLUDES].
            resources: Register the `read_skill_resource` tool.
            scripts: Register the `run_skill_script` tool.
            require_loaded: Refuse bundled-file calls for a skill the model has not loaded,
                keeping files behind the same boundary as the skill's instructions.
            resolve_skill_dir: Substitute `${SKILL_DIR}` and `${CLAUDE_SKILL_DIR}` in a
                skill's instructions with its real directory, so instructions that name
                those placeholders resolve to paths the script tool can actually use.
            list_bundled_files: Append a "Bundled files" section naming a skill's
                resources and scripts to its instructions, so the model reads the names
                the file tools expect instead of inferring them from prose. Turn off for
                skills whose `SKILL.md` already lists its files.
            id: Stable identifier for the capability that carries the bundled-file tools.

        Raises:
            ValueError: If `include` and `exclude` are combined, if no source is
                configured, or if `include`/`exclude` name a skill that does not exist.
        """
        if include is not None and exclude is not None:
            raise ValueError('include and exclude cannot be used together.')

        self.id = id
        self.directories = self._normalize_directories(directories)
        self.registries = tuple(registries)
        self.include = _normalize_selection('include', include) if include is not None else None
        self.exclude = _normalize_selection('exclude', exclude) if exclude is not None else frozenset()
        # Only list what the model can actually reach: a kind whose tool is not registered
        # has no name worth advertising.
        self._list_resources = resources and list_bundled_files
        self._list_scripts = scripts and list_bundled_files

        programmatic = [entry.to_skill() if isinstance(entry, SkillWrapper) else entry for entry in skills]

        if not self.directories and not self.registries and not programmatic:
            raise ValueError(
                'SkillsCapability needs at least one source: a skill-library directory, a registry, or a skill.'
            )

        libraries: list[str | Path] = [*self.directories]
        libraries.extend(registry.sync() for registry in self.registries)

        # Index bundled files first: the directory-backed names it finds are what lets us
        # split `include`/`exclude` between harness (which rejects names it does not know)
        # and the programmatic skills harness never sees.
        self._packages = index_libraries(
            libraries,
            script_executor=script_executor,
            exclude_resources=exclude_resources,
        )
        directory_names = frozenset(self._packages)
        programmatic_names = frozenset(_normalize(skill.name) for skill in programmatic)
        self._validate_selection(directory_names | programmatic_names)

        self._skills = self._build_harness_skills(libraries, directory_names)

        selected_programmatic = self._resolve_duplicates(
            [skill for skill in programmatic if self._is_selected(_normalize(skill.name))]
        )
        shadowed = {_normalize(skill.name) for skill in selected_programmatic}

        leaves: list[AbstractCapability[AgentDepsT]] = []
        if self._skills is not None:
            harness_leaves: list[AbstractCapability[AgentDepsT]] = []
            self._skills.apply(harness_leaves.append)
            leaves.extend(
                self._rebuild_leaf(leaf, resolve_skill_dir) for leaf in harness_leaves if leaf.id not in shadowed
            )

        for skill in selected_programmatic:
            name = _normalize(skill.name)
            if name in self._packages:
                warnings.warn(
                    f"Programmatic skill '{name}' shadows a skill of the same name discovered on disk. "
                    'The programmatic definition wins; rename one of them to expose both.',
                    UserWarning,
                    stacklevel=2,
                )
            package = SkillPackage(
                name=name,
                resources=tuple(skill.resources),
                scripts=tuple(skill.scripts),
            )
            self._packages[name] = package

            instructions = f'# Skill: {name}\n\n{skill.content}' if skill.content else f'# Skill: {name}'
            inventory = _bundled_files_section(package, resources=self._list_resources, scripts=self._list_scripts)
            if inventory is not None:
                instructions = f'{instructions}\n\n{inventory}'

            leaves.append(
                Capability[AgentDepsT](
                    id=name,
                    description=skill.description,
                    instructions=instructions,
                    defer_loading=True,
                )
            )

        self._files_toolset = self._build_files_toolset(
            resources=resources,
            scripts=scripts,
            require_loaded=require_loaded,
        )
        self._leaves = tuple(leaves)

    def __repr__(self) -> str:
        """Show only the configuration the caller controls."""
        return (
            f'{type(self).__name__}('
            f'directories={self.directories!r}, registries={self.registries!r}, '
            f'include={self.include!r}, exclude={self.exclude!r})'
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_directories(directories: str | Path | Sequence[str | Path]) -> tuple[str | Path, ...]:
        if isinstance(directories, (str, Path)):
            return (directories,)
        return tuple(directories)

    @staticmethod
    def _resolve_duplicates(skills: Sequence[Skill]) -> list[Skill]:
        """Collapse programmatic skills sharing a name, keeping the last and warning.

        Two skills under one name would produce two deferred capabilities with the same
        id, which pydantic-ai rejects at run setup with an error that says nothing about
        where the collision came from.
        """
        by_name: dict[str, Skill] = {}
        for skill in skills:
            name = _normalize(skill.name)
            if name in by_name:
                warnings.warn(
                    f"Duplicate skill '{name}' found in `skills`; the last definition wins.",
                    UserWarning,
                    stacklevel=3,
                )
            by_name[name] = skill
        return list(by_name.values())

    def _is_selected(self, name: str) -> bool:
        """Apply `include`/`exclude` to a single skill name."""
        if self.include is not None:
            return name in self.include
        return name not in self.exclude

    def _validate_selection(self, available: frozenset[str]) -> None:
        """Reject `include`/`exclude` names that match no skill from any source.

        harness performs this check for its own libraries, but it never sees programmatic
        skills — so a selection naming one would look unknown to it. Validating across
        both sources here means the error message lists everything actually available.

        Raises:
            ValueError: When a selected name matches no known skill.
        """
        for option, selected in (('include', self.include), ('exclude', self.exclude)):
            if selected is None:
                continue
            unknown = sorted(selected - available)
            if not unknown:
                continue
            noun = 'skill' if len(unknown) == 1 else 'skills'
            available_text = ', '.join(sorted(available)) or '(none)'
            raise ValueError(f'Unknown {noun} in {option}: {", ".join(unknown)}. Available skills: {available_text}.')

    def _build_harness_skills(
        self,
        libraries: Sequence[str | Path],
        directory_names: frozenset[str],
    ) -> Skills[AgentDepsT] | None:
        """Construct the harness `Skills` that owns discovery and instruction rendering.

        The selection is narrowed to names harness can actually see: it raises on an
        `include` naming a skill it did not discover, and a selection may legitimately
        refer to a programmatic skill instead.
        """
        if not libraries:
            return None

        if self.include is not None:
            return Skills[AgentDepsT](libraries, include=sorted(self.include & directory_names))
        return Skills[AgentDepsT](libraries, exclude=sorted(self.exclude & directory_names))

    def _rebuild_leaf(
        self,
        leaf: AbstractCapability[AgentDepsT],
        resolve_skill_dir: bool,
    ) -> AbstractCapability[AgentDepsT]:
        """Return `leaf` with placeholders resolved and its bundled files listed.

        harness emits plain-string instructions, so when there is nothing to substitute and
        nothing to list the original leaf is handed back untouched rather than rebuilt.
        """
        package = self._packages.get(leaf.id) if leaf.id else None
        if package is None:
            return leaf

        instructions = leaf.get_instructions()
        if not isinstance(instructions, list) or not all(isinstance(part, str) for part in instructions):
            return leaf

        resolved = list(instructions)
        if resolve_skill_dir and package.directory is not None:
            resolved = [_resolve_placeholders(part, package.directory) for part in resolved]

        inventory = _bundled_files_section(package, resources=self._list_resources, scripts=self._list_scripts)
        if inventory is not None:
            resolved.append(inventory)

        if resolved == instructions:
            return leaf

        return Capability[AgentDepsT](
            id=leaf.id,
            description=leaf.get_description(),
            instructions=resolved,
            defer_loading=True,
        )

    def _build_files_toolset(
        self,
        *,
        resources: bool,
        scripts: bool,
        require_loaded: bool,
    ) -> SkillFilesToolset | None:
        """Build the bundled-file toolset, or None when it would expose no tools."""
        has_resources = resources and any(package.resources for package in self._packages.values())
        has_scripts = scripts and any(package.scripts for package in self._packages.values())
        if not has_resources and not has_scripts:
            return None

        return SkillFilesToolset(
            self._packages,
            resources=has_resources,
            scripts=has_scripts,
            require_loaded=require_loaded,
            id=self.id,
        )

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    @property
    def skill_names(self) -> list[str]:
        """Names of the skills exposed to the model, sorted."""
        return sorted(leaf.id for leaf in self._leaves if leaf.id)

    @property
    def packages(self) -> dict[str, SkillPackage]:
        """The indexed bundled files, keyed by skill name."""
        return self._packages

    def apply(self, visitor: Callable[[AbstractCapability[AgentDepsT]], None]) -> None:
        """Visit this capability and each skill it exposes as a deferred leaf.

        Unlike a pure container, this visits `self` as well. It has to: pydantic-ai builds
        the run's capability registry from `apply`, and the toolset returned by
        `get_toolset` is owned by whichever capability that registry maps it to. Skipping
        `self` leaves the bundled-file tools with no registered owner, which fails the run
        the first time the model calls one.

        Only visited when this capability actually contributes a toolset, so a
        `SkillsCapability` over skills that ship no files stays a pure container.
        """
        if self._files_toolset is not None:
            visitor(self)
        for leaf in self._leaves:
            leaf.apply(visitor)

    def visit_and_replace(
        self,
        visitor: Callable[[AbstractCapability[AgentDepsT]], AbstractCapability[AgentDepsT] | None],
    ) -> AbstractCapability[AgentDepsT] | None:
        """Rewrite the leaves in place, keeping this capability as their container."""
        replaced: list[AbstractCapability[AgentDepsT]] = []
        changed = False
        for leaf in self._leaves:
            result = leaf.visit_and_replace(visitor)
            if result is not leaf:
                changed = True
            if result is not None:
                replaced.append(result)

        if not changed:
            return self
        if not replaced:
            return None

        clone = object.__new__(type(self))
        clone.__dict__.update(self.__dict__)
        clone._leaves = tuple(replaced)
        return clone

    def get_toolset(self) -> AgentToolset[AgentDepsT] | None:
        """Return the bundled-file toolset, or None when no skill ships files.

        This has to come from the container itself rather than from a leaf: pydantic-ai
        collects toolsets by calling `get_toolset()` on a container's direct children
        (see `CombinedCapability.get_toolset`), and does not recurse through `apply` the
        way it does when building the capability-id registry. A toolset parked on a leaf
        would never be registered.

        The tools stay always-on while each skill is deferred, which is deliberate: the
        model needs them the moment it loads a skill, and `require_loaded` — not tool
        visibility — is what keeps a skill's files behind its instructions.
        """
        return self._files_toolset

    @classmethod
    def get_serialization_name(cls) -> str | None:
        """Return the name used to reference this capability in agent specs."""
        return 'SkillsCapability'

    @classmethod
    def from_spec(
        cls,
        *,
        directories: list[str] | str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        exclude_resources: list[str] | None = None,
        resources: bool = True,
        scripts: bool = True,
        require_loaded: bool = True,
        resolve_skill_dir: bool = True,
        list_bundled_files: bool = True,
        id: str | None = None,
    ) -> AbstractCapability[Any]:
        """Create from a YAML/JSON agent spec.

        Only serializable arguments are supported. Registries, programmatic skills, and
        custom script executors cannot be expressed in a spec; construct the capability in
        Python for those.

        Args:
            directories: Skill-library paths, as strings.
            include: Exact skill names to expose. Cannot be combined with `exclude`.
            exclude: Exact skill names to omit. Cannot be combined with `include`.
            exclude_resources: Extra glob patterns to exclude from resource discovery.
            resources: Register the `read_skill_resource` tool.
            scripts: Register the `run_skill_script` tool.
            require_loaded: Refuse bundled-file calls for a skill that is not loaded.
            resolve_skill_dir: Substitute `${SKILL_DIR}` / `${CLAUDE_SKILL_DIR}` in
                instructions with the skill's directory.
            list_bundled_files: Append a "Bundled files" section naming a skill's
                resources and scripts to its instructions.
            id: Stable identifier for the capability carrying the bundled-file tools.
        """
        return cls(
            directories=directories if directories is not None else (),
            include=include,
            exclude=exclude,
            exclude_resources=exclude_resources,
            resources=resources,
            scripts=scripts,
            require_loaded=require_loaded,
            resolve_skill_dir=resolve_skill_dir,
            list_bundled_files=list_bundled_files,
            id=id,
        )

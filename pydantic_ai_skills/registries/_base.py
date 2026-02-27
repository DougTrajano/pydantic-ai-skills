"""Abstract base class for skill registries.

Provides the [`SkillRegistry`][pydantic_ai_skills.registries.SkillRegistry] ABC
that all concrete registry implementations must implement.

Composition wrappers live in sibling modules:

- :class:`~pydantic_ai_skills.registries.wrapper.WrapperRegistry`
- :class:`~pydantic_ai_skills.registries.filtered.FilteredRegistry`
- :class:`~pydantic_ai_skills.registries.prefixed.PrefixedRegistry`
- :class:`~pydantic_ai_skills.registries.renamed.RenamedRegistry`
- :class:`~pydantic_ai_skills.registries.combined.CombinedRegistry`
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai_skills.types import Skill

if TYPE_CHECKING:
    from pydantic_ai_skills.registries.filtered import FilteredRegistry
    from pydantic_ai_skills.registries.prefixed import PrefixedRegistry
    from pydantic_ai_skills.registries.renamed import RenamedRegistry

__all__ = ['SkillRegistry']


class SkillRegistry(ABC):
    """Abstract base for skill registries.

    A skill registry is a source of skills that can be searched, retrieved,
    installed and updated. Concrete implementations may back registries with
    a Git repository, a REST API, a local directory, etc.

    Convenience methods :meth:`filtered`, :meth:`prefixed`, and
    :meth:`renamed` return lightweight wrapper views — the underlying
    registry is never modified.
    """

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Search for skills by keyword.

        Args:
            query: Keyword matched case-insensitively against ``name`` and
                ``description``.
            limit: Maximum number of results.

        Returns:
            List of matching :class:`~pydantic_ai_skills.Skill` objects.
        """

    @abstractmethod
    async def get(self, skill_name: str) -> Skill:
        """Return a single skill by name.

        Args:
            skill_name: Exact skill name from ``SKILL.md`` frontmatter.

        Returns:
            The matching :class:`~pydantic_ai_skills.Skill`.

        Raises:
            SkillNotFoundError: When no skill with ``skill_name`` exists.
        """

    @abstractmethod
    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Copy a skill into ``target_dir``.

        Args:
            skill_name: Name of the skill to install.
            target_dir: Destination directory; a ``skill_name`` subdirectory
                is created inside it.

        Returns:
            Path to the installed skill directory.
        """

    @abstractmethod
    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Update an already-installed skill to the latest version.

        Args:
            skill_name: Name of the skill to update.
            target_dir: Directory where the skill was previously installed.

        Returns:
            Path to the updated skill directory.
        """

    @abstractmethod
    def get_skills(self) -> list[Skill]:
        """Return all skills available in this registry.

        Concrete implementations must return pre-loaded skill objects.
        This is called synchronously by :class:`~pydantic_ai_skills.SkillsToolset`
        during initialization.

        Returns:
            List of :class:`~pydantic_ai_skills.Skill` objects.
        """

    def filtered(self, predicate: Callable[[Skill], bool]) -> FilteredRegistry:
        """Return a view of this registry limited to skills matching ``predicate``.

        Args:
            predicate: A callable that accepts a :class:`~pydantic_ai_skills.Skill`
                and returns ``True`` if the skill should be included.

        Returns:
            A :class:`~pydantic_ai_skills.registries.filtered.FilteredRegistry`
            view backed by the same underlying source.
        """
        from pydantic_ai_skills.registries.filtered import FilteredRegistry as _Filtered

        return _Filtered(wrapped=self, predicate=predicate)

    def prefixed(self, prefix: str) -> PrefixedRegistry:
        """Return a view of this registry with ``prefix`` prepended to every skill name.

        Args:
            prefix: String to prepend to every skill name.

        Returns:
            A :class:`~pydantic_ai_skills.registries.prefixed.PrefixedRegistry`
            view backed by the same underlying source.
        """
        from pydantic_ai_skills.registries.prefixed import PrefixedRegistry as _Prefixed

        return _Prefixed(wrapped=self, prefix=prefix)

    def renamed(self, name_map: dict[str, str]) -> RenamedRegistry:
        """Return a view of this registry with skills renamed per ``name_map``.

        Args:
            name_map: Mapping of ``{new_name: original_name}``.

        Returns:
            A :class:`~pydantic_ai_skills.registries.renamed.RenamedRegistry`
            view backed by the same underlying source.
        """
        from pydantic_ai_skills.registries.renamed import RenamedRegistry as _Renamed

        return _Renamed(wrapped=self, name_map=name_map)

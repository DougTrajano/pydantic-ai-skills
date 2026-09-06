"""Abstract base class for skill registries.

A registry is a **source of skill libraries**: it fetches skill packages from wherever
they live and materializes them into a local directory that
[`SkillsCapability`][pydantic_ai_skills.SkillsCapability] — and therefore
`pydantic-ai-harness`'s `Skills` — can read. Everything downstream of that directory is
harness's job.

That is the whole contract: one synchronous
[`sync()`][pydantic_ai_skills.SkillRegistry.sync] returning a path. Concrete
implementations back it with a Git clone, an S3 sync, or a plain local directory.

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

from pydantic_ai_skills._parsing import SkillInfo, read_skill_info

if TYPE_CHECKING:
    from pydantic_ai_skills.registries.combined import CombinedRegistry
    from pydantic_ai_skills.registries.filtered import FilteredRegistry
    from pydantic_ai_skills.registries.prefixed import PrefixedRegistry
    from pydantic_ai_skills.registries.renamed import RenamedRegistry

__all__ = ['SkillRegistry']


class SkillRegistry(ABC):
    """Abstract base for skill registries.

    Implement [`sync`][pydantic_ai_skills.SkillRegistry.sync] to fetch skill packages and
    lay them out as immediate child directories of a returned library path. Nothing else
    is required — parsing, validation and instruction rendering all belong to harness.

    Convenience methods :meth:`filtered`, :meth:`prefixed`, and :meth:`renamed` return
    lightweight wrapper views; the underlying registry is never modified.
    """

    @abstractmethod
    def sync(self) -> Path:
        """Materialize this registry's skills and return the local library directory.

        The returned path is a *library*: its immediate children are skill package
        directories, each holding a `SKILL.md`. It is passed straight to harness's
        `Skills`, so it must satisfy harness's rules — in particular the library itself
        must not contain a `SKILL.md`.

        Implementations should be idempotent and safe to call repeatedly: a second call
        refreshes the local copy (a `git pull`, a re-sync) rather than starting over.

        Returns:
            Path to the local skill-library directory.
        """

    def skill_infos(self) -> list[SkillInfo]:
        """Return the catalog fields of every skill package in this registry.

        Syncs first, then reads each immediate child's `SKILL.md`. Used by
        [`filtered`][pydantic_ai_skills.SkillRegistry.filtered] and by callers that want
        to know what a registry holds without constructing an agent.

        Returns:
            One [`SkillInfo`][pydantic_ai_skills._parsing.SkillInfo] per package, sorted
            by name.
        """
        library = self.sync()
        infos = [read_skill_info(child) for child in sorted(library.iterdir()) if child.is_dir()]
        return [info for info in infos if info is not None]

    def skill_names(self) -> list[str]:
        """Return the names of every skill package in this registry, sorted."""
        return [info.name for info in self.skill_infos()]

    def filtered(self, predicate: Callable[[SkillInfo], bool]) -> FilteredRegistry:
        """Return a view of this registry limited to skills matching ``predicate``.

        Args:
            predicate: A callable that accepts a
                [`SkillInfo`][pydantic_ai_skills._parsing.SkillInfo] and returns ``True``
                if the skill should be included.

        Returns:
            A :class:`~pydantic_ai_skills.registries.filtered.FilteredRegistry`
            view backed by the same underlying source.
        """
        from pydantic_ai_skills.registries.filtered import FilteredRegistry as _Filtered

        return _Filtered(wrapped=self, predicate=predicate)

    def prefixed(self, prefix: str) -> PrefixedRegistry:
        """Return a view of this registry with ``prefix`` prepended to every skill name.

        Args:
            prefix: String to prepend to every skill name. The result must still be a
                valid skill name, so a prefix normally ends with a hyphen.

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

    def __or__(self, other: SkillRegistry) -> CombinedRegistry:
        """Return a registry that merges this one with ``other``.

        Earlier registries win on a duplicate skill name, matching
        :class:`~pydantic_ai_skills.registries.combined.CombinedRegistry`.
        """
        from pydantic_ai_skills.registries.combined import CombinedRegistry as _Combined

        return _Combined(registries=[self, other])

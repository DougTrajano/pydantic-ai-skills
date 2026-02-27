"""Filtered registry composition.

Provides :class:`FilteredRegistry`, a wrapper that restricts which
skills are visible based on a predicate function. Follows the same
pattern as Pydantic AI's ``FilteredToolset``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai_skills.exceptions import SkillNotFoundError
from pydantic_ai_skills.registries.wrapper import WrapperRegistry
from pydantic_ai_skills.types import Skill

__all__ = ['FilteredRegistry']


@dataclass
class FilteredRegistry(WrapperRegistry):
    """A registry that filters skills using a predicate function.

    Only skills for which ``predicate(skill)`` returns ``True`` are
    visible through this view. The underlying registry is never modified.

    Example:
        ```python
        pdf_only = registry.filtered(lambda s: 'pdf' in s.name)
        results = await pdf_only.search('document')
        ```
    """

    predicate: Callable[[Skill], bool]

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Search the wrapped registry and filter results by predicate.

        Fetches extra results from the inner registry to compensate for
        filtering, then trims to ``limit``.
        """
        results = await self.wrapped.search(query, limit=limit * 5)
        return [s for s in results if self.predicate(s)][:limit]

    async def get(self, skill_name: str) -> Skill:
        """Get a skill by name, raising if it doesn't pass the predicate."""
        skill = await self.wrapped.get(skill_name)
        if not self.predicate(skill):
            raise SkillNotFoundError(f"Skill '{skill_name}' not found in filtered registry.")
        return skill

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Install a skill after validating it passes the predicate."""
        await self.get(skill_name)  # validates predicate
        return await self.wrapped.install(skill_name, target_dir)

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Update a skill after validating it passes the predicate."""
        await self.get(skill_name)  # validates predicate
        return await self.wrapped.update(skill_name, target_dir)

    def get_skills(self) -> list[Skill]:
        """Return only skills that pass the predicate."""
        return [s for s in self.wrapped.get_skills() if self.predicate(s)]

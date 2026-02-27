"""Combined registry composition.

Provides :class:`CombinedRegistry`, an aggregate that presents
multiple registries as a single unified source. Follows the same
pattern as Pydantic AI's ``CombinedToolset``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic_ai_skills.exceptions import SkillNotFoundError
from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.types import Skill

__all__ = ['CombinedRegistry']


@dataclass
class CombinedRegistry(SkillRegistry):
    """A registry that aggregates multiple registries into one.

    Searches are fanned out to every child registry in parallel.
    ``get``, ``install``, and ``update`` try each registry in order
    and return the first successful result.

    Example:
        ```python
        from pydantic_ai_skills.registries import CombinedRegistry

        combined = CombinedRegistry(registries=[github_registry, gitlab_registry])
        results = await combined.search('pdf')
        ```
    """

    registries: Sequence[SkillRegistry]

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Search all child registries in parallel and merge results.

        Results are deduplicated by skill name (first occurrence wins).
        """
        all_results = await asyncio.gather(*(reg.search(query, limit) for reg in self.registries))
        seen: set[str] = set()
        merged: list[Skill] = []
        for results in all_results:
            for skill in results:
                if skill.name not in seen:
                    seen.add(skill.name)
                    merged.append(skill)
                if len(merged) >= limit:
                    return merged
        return merged

    async def get(self, skill_name: str) -> Skill:
        """Try each registry in order and return the first match.

        Raises:
            SkillNotFoundError: When no registry contains the skill.
        """
        for reg in self.registries:
            try:
                return await reg.get(skill_name)
            except SkillNotFoundError:
                continue
        raise SkillNotFoundError(
            f"Skill '{skill_name}' not found in any of the {len(self.registries)} combined registries."
        )

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Install from the first registry that contains the skill.

        Raises:
            SkillNotFoundError: When no registry contains the skill.
        """
        for reg in self.registries:
            try:
                await reg.get(skill_name)
                return await reg.install(skill_name, target_dir)
            except SkillNotFoundError:
                continue
        raise SkillNotFoundError(f"Skill '{skill_name}' not found in any combined registry for install.")

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Update from the first registry that contains the skill.

        Raises:
            SkillNotFoundError: When no registry contains the skill.
        """
        for reg in self.registries:
            try:
                await reg.get(skill_name)
                return await reg.update(skill_name, target_dir)
            except SkillNotFoundError:
                continue
        raise SkillNotFoundError(f"Skill '{skill_name}' not found in any combined registry for update.")

    def get_skills(self) -> list[Skill]:
        """Return skills from all child registries, deduplicated by name.

        First occurrence wins when multiple registries provide skills with
        the same name.
        """
        seen: set[str] = set()
        merged: list[Skill] = []
        for reg in self.registries:
            for skill in reg.get_skills():
                if skill.name not in seen:
                    seen.add(skill.name)
                    merged.append(skill)
        return merged

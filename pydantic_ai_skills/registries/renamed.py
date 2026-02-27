"""Renamed registry composition.

Provides :class:`RenamedRegistry`, a wrapper that renames skills
using an explicit mapping. Follows the same pattern as Pydantic
AI's ``RenamedToolset``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from pydantic_ai_skills.registries.wrapper import WrapperRegistry
from pydantic_ai_skills.types import Skill

__all__ = ['RenamedRegistry']


@dataclass
class RenamedRegistry(WrapperRegistry):
    """A registry that renames skills using a name map.

    ``name_map`` maps **new names to original names**:
    ``{'new-name': 'original-name'}``.  Skills not present in the
    map keep their original names.

    Example:
        ```python
        renamed = registry.renamed({'doc-tool': 'pdf', 'sheet-tool': 'xlsx'})
        skill = await renamed.get('doc-tool')    # fetches 'pdf'
        skill = await renamed.get('xlsx')         # still works (unmapped)
        ```
    """

    name_map: dict[str, str]

    @property
    def _reverse_map(self) -> dict[str, str]:
        """Map from original name → new name."""
        return {v: k for k, v in self.name_map.items()}

    def _to_new_name(self, skill: Skill) -> Skill:
        """Apply the rename mapping to a skill, if applicable."""
        new_name = self._reverse_map.get(skill.name)
        if new_name:
            return replace(skill, name=new_name)
        return skill

    def _to_original_name(self, name: str) -> str:
        """Resolve a possibly-renamed name back to the original."""
        return self.name_map.get(name, name)

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Search the wrapped registry and apply renames to results."""
        results = await self.wrapped.search(query, limit)
        return [self._to_new_name(s) for s in results]

    async def get(self, skill_name: str) -> Skill:
        """Get a skill by its (possibly renamed) name."""
        original_name = self._to_original_name(skill_name)
        skill = await self.wrapped.get(original_name)
        return self._to_new_name(skill)

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Install a skill, resolving the renamed name first."""
        original_name = self._to_original_name(skill_name)
        return await self.wrapped.install(original_name, target_dir)

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Update a skill, resolving the renamed name first."""
        original_name = self._to_original_name(skill_name)
        return await self.wrapped.update(original_name, target_dir)

    def get_skills(self) -> list[Skill]:
        """Return all skills with renamed names applied."""
        return [self._to_new_name(s) for s in self.wrapped.get_skills()]

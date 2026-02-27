"""Prefixed registry composition.

Provides :class:`PrefixedRegistry`, a wrapper that prepends a
prefix to every skill name. Follows the same pattern as Pydantic
AI's ``PrefixedToolset``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from pydantic_ai_skills.exceptions import SkillNotFoundError
from pydantic_ai_skills.registries.wrapper import WrapperRegistry
from pydantic_ai_skills.types import Skill

__all__ = ['PrefixedRegistry']


@dataclass
class PrefixedRegistry(WrapperRegistry):
    """A registry that prepends a prefix to every skill name.

    The prefix is added to names returned by ``search`` and ``get``,
    and stripped before delegating ``install`` and ``update`` to the
    wrapped registry.

    Example:
        ```python
        prefixed = registry.prefixed('anthropic-')
        # Skill 'pdf' is now accessible as 'anthropic-pdf'
        skill = await prefixed.get('anthropic-pdf')
        ```
    """

    prefix: str

    def _add_prefix(self, skill: Skill) -> Skill:
        """Return a copy of the skill with the prefix prepended to its name."""
        return replace(skill, name=f'{self.prefix}{skill.name}')

    def _strip_prefix(self, name: str) -> str:
        """Remove the prefix from a skill name if present."""
        if name.startswith(self.prefix):
            return name[len(self.prefix) :]
        return name

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Search the wrapped registry and prefix all result names."""
        results = await self.wrapped.search(query, limit)
        return [self._add_prefix(s) for s in results]

    async def get(self, skill_name: str) -> Skill:
        """Get a skill by its prefixed name.

        Raises:
            SkillNotFoundError: When the name doesn't start with the
                expected prefix.
        """
        if not skill_name.startswith(self.prefix):
            raise SkillNotFoundError(f"Skill '{skill_name}' not found — expected prefix '{self.prefix}'.")
        inner_name = self._strip_prefix(skill_name)
        skill = await self.wrapped.get(inner_name)
        return self._add_prefix(skill)

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Install a skill, stripping the prefix before delegating."""
        inner_name = self._strip_prefix(skill_name)
        return await self.wrapped.install(inner_name, target_dir)

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Update a skill, stripping the prefix before delegating."""
        inner_name = self._strip_prefix(skill_name)
        return await self.wrapped.update(inner_name, target_dir)

    def get_skills(self) -> list[Skill]:
        """Return all skills with the prefix prepended to their names."""
        return [self._add_prefix(s) for s in self.wrapped.get_skills()]

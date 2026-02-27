"""Wrapper base class for registry composition.

Provides :class:`WrapperRegistry`, the base for all registry
decorators (filtered, prefixed, renamed). Follows the same
delegation pattern as Pydantic AI's ``WrapperToolset``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.types import Skill

__all__ = ['WrapperRegistry']


@dataclass
class WrapperRegistry(SkillRegistry):
    """A registry that wraps another registry and delegates to it.

    All abstract methods are forwarded to ``wrapped``. Subclasses
    override only the methods they need to modify.

    Example:
        ```python
        class MyCustomRegistry(WrapperRegistry):
            async def search(self, query: str, limit: int = 10) -> list[Skill]:
                results = await self.wrapped.search(query, limit)
                # custom post-processing
                return results
        ```
    """

    wrapped: SkillRegistry

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Delegate search to the wrapped registry."""
        return await self.wrapped.search(query, limit)

    async def get(self, skill_name: str) -> Skill:
        """Delegate get to the wrapped registry."""
        return await self.wrapped.get(skill_name)

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Delegate install to the wrapped registry."""
        return await self.wrapped.install(skill_name, target_dir)

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Delegate update to the wrapped registry."""
        return await self.wrapped.update(skill_name, target_dir)

    def get_skills(self) -> list[Skill]:
        """Delegate get_skills to the wrapped registry."""
        return self.wrapped.get_skills()

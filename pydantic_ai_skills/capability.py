"""Capability integration for pydantic-ai-skills.

This module provides [`SkillsCapability`][pydantic_ai_skills.SkillsCapability],
an alternative integration path for Pydantic AI users on versions that support
the capabilities API (pydantic-ai >= 1.71).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic_ai.tools import RunContext

from .directory import SkillsDirectory
from .registries._base import SkillRegistry
from .toolset import SkillsToolset
from .types import Skill

_AgentDepsT = TypeVar('_AgentDepsT')

if TYPE_CHECKING:
    from pydantic_ai.capabilities import AbstractCapability as _AbstractCapabilityBase

    _CAPABILITIES_AVAILABLE = True
else:
    try:
        from pydantic_ai.capabilities import AbstractCapability as _AbstractCapabilityBase

        _CAPABILITIES_AVAILABLE = True
    except ImportError:
        _CAPABILITIES_AVAILABLE = False

        class _AbstractCapabilityBase(Generic[_AgentDepsT]):
            """Fallback placeholder when pydantic-ai capabilities are unavailable."""


class SkillsCapability(_AbstractCapabilityBase[Any]):
    """Capability wrapper for `SkillsToolset`.

    Use this class with the agent `capabilities=[...]` API introduced in
    pydantic-ai 1.71+.

    Example:
        ```python
        from pydantic_ai import Agent
        from pydantic_ai_skills import SkillsCapability

        agent = Agent(
            model='openai:gpt-5.2',
            capabilities=[SkillsCapability(directories=['./skills'])],
        )
        ```
    """

    def __init__(
        self,
        *,
        skills: list[Skill] | None = None,
        directories: list[str | Path | SkillsDirectory] | None = None,
        registries: list[SkillRegistry] | None = None,
        validate: bool = True,
        max_depth: int | None = 3,
        id: str | None = None,
        instruction_template: str | None = None,
        exclude_tools: set[str] | list[str] | None = None,
        auto_reload: bool = False,
    ) -> None:
        """Initialize a skills capability.

        Args:
            skills: Pre-loaded skills.
            directories: Skill directories to discover.
            registries: Remote registries to discover.
            validate: Validate skill structure during discovery.
            max_depth: Maximum discovery depth.
            id: Optional toolset id.
            instruction_template: Optional custom instructions template.
            exclude_tools: Tool names to exclude.
            auto_reload: Re-scan directories before each run.

        Raises:
            RuntimeError: If capabilities API is unavailable in installed
                pydantic-ai version.
        """
        if not _CAPABILITIES_AVAILABLE:
            raise RuntimeError(
                'SkillsCapability requires pydantic-ai>=1.71 with capabilities support. '
                'Use SkillsToolset instead or upgrade pydantic-ai.'
            )

        self._toolset = SkillsToolset(
            skills=skills,
            directories=directories,
            registries=registries,
            validate=validate,
            max_depth=max_depth,
            id=id,
            instruction_template=instruction_template,
            exclude_tools=exclude_tools,
            auto_reload=auto_reload,
        )

    def get_toolset(self) -> SkillsToolset | None:
        """Return the underlying skills toolset."""
        return self._toolset

    def get_instructions(self) -> Any:
        """Return dynamic instructions via the underlying skills toolset."""

        async def _instructions(ctx: RunContext[Any]) -> str | None:
            return await self._toolset.get_instructions(ctx)

        return _instructions

    @property
    def toolset(self) -> SkillsToolset:
        """Expose the underlying `SkillsToolset` instance."""
        return self._toolset

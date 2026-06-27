"""Capability integration for pydantic-ai-skills.

This module provides [`SkillsCapability`][pydantic_ai_skills.SkillsCapability],
the preferred integration path for Pydantic AI users via the `capabilities=[...]` API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai.agent.abstract import AgentInstructions
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.tools import AgentDepsT

from .directory import SkillsDirectory
from .registries._base import SkillRegistry
from .toolset import SkillsToolset
from .types import Skill


class SkillsCapability(AbstractCapability[Any]):
    """Capability wrapper for `SkillsToolset`.

    Use this class with the agent `capabilities=[...]` API.

    Example:
        ```python
        from pydantic_ai import Agent
        from pydantic_ai_skills import SkillsCapability

        agent = Agent(
            model='openai:gpt-5.2',
            capabilities=[SkillsCapability(directories=['./skills'])],
        )
        ```

    Set `defer_loading=True` (with a stable `id`) to hide the skills tools and
    instructions behind the agent's `load_capability` tool until the model
    explicitly loads them:

        ```python
        agent = Agent(
            model='openai:gpt-5.2',
            capabilities=[
                SkillsCapability(id='skills', directories=['./skills'], defer_loading=True),
            ],
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
        description: str | None = None,
        defer_loading: bool = False,
    ) -> None:
        """Initialize a skills capability.

        Args:
            skills: Pre-loaded skills.
            directories: Skill directories to discover.
            registries: Remote registries to discover.
            validate: Validate skill structure during discovery.
            max_depth: Maximum discovery depth.
            id: Stable identifier shared by the capability and its toolset. Required when
                ``defer_loading`` is True so message history can identify the capability.
            instruction_template: Optional custom instructions template.
            exclude_tools: Tool names to exclude.
            auto_reload: Re-scan directories before each run.
            description: Optional catalog description surfaced to the model when
                ``defer_loading`` is True. Defaults to a summary of the available skills.
            defer_loading: If True, the skills tools and instructions stay hidden until the
                model loads this capability via the agent's ``load_capability`` tool.

        Raises:
            ValueError: If ``defer_loading`` is True but no ``id`` is provided.
        """
        if defer_loading and id is None:
            raise ValueError("SkillsCapability requires a stable 'id' when defer_loading=True.")

        self.id = id
        self.description = description
        self.defer_loading = defer_loading
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

    def get_instructions(self) -> AgentInstructions[AgentDepsT] | None:
        """Return None — instructions are pulled natively from the toolset by the agent."""
        return None

    def get_description(self) -> str | None:
        """Return the catalog description shown when this capability is deferred.

        Falls back to a summary of the available skill names when no explicit
        ``description`` was provided.
        """
        if self.description is not None:
            return self.description
        names = sorted(self._toolset.skills)
        if not names:
            return None
        return 'Provides specialized skills: ' + ', '.join(names) + '.'

    @property
    def toolset(self) -> SkillsToolset:
        """Expose the underlying `SkillsToolset` instance."""
        return self._toolset

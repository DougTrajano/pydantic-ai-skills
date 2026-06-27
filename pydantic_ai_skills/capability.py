"""Capability integration for pydantic-ai-skills.

This module provides [`SkillsCapability`][pydantic_ai_skills.SkillsCapability],
the preferred integration path for Pydantic AI users via the `capabilities=[...]` API.
"""

from __future__ import annotations

from dataclasses import KW_ONLY, dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai.agent.abstract import AgentInstructions
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.tools import AgentDepsT

from .directory import SkillsDirectory
from .registries._base import SkillRegistry
from .toolset import SkillsToolset
from .types import Skill


@dataclass
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

    The capability is usable in declarative agent specs (`Agent.from_spec` /
    `Agent.from_file`) by passing it via `custom_capability_types`:

        ```yaml
        capabilities:
          - SkillsCapability:
              directories: ['./skills']
              defer_loading: true
              id: skills
        ```

        ```python
        agent = Agent.from_file('agent.yaml', custom_capability_types=[SkillsCapability])
        ```

    Only serializable arguments are spec-expressible (see
    [`from_spec`][pydantic_ai_skills.SkillsCapability.from_spec]); programmatic
    `skills`, `registries`, and `SkillsDirectory` instances require Python construction.
    """

    _: KW_ONLY

    skills: list[Skill] | None = None
    """Pre-loaded skills."""

    directories: list[str | Path | SkillsDirectory] | None = None
    """Skill directories to discover."""

    registries: list[SkillRegistry] | None = None
    """Remote registries to discover."""

    validate: bool = True
    """Validate skill structure during discovery."""

    max_depth: int | None = 3
    """Maximum discovery depth."""

    instruction_template: str | None = None
    """Optional custom instructions template."""

    exclude_tools: set[str] | list[str] | None = None
    """Tool names to exclude."""

    auto_reload: bool = False
    """Re-scan directories before each run."""

    _toolset: SkillsToolset = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate deferred configuration and build the underlying toolset.

        Raises:
            ValueError: If ``defer_loading`` is True but no ``id`` is provided.
        """
        if self.defer_loading and self.id is None:
            raise ValueError("SkillsCapability requires a stable 'id' when defer_loading=True.")

        self._toolset = SkillsToolset(
            skills=self.skills,
            directories=self.directories,
            registries=self.registries,
            validate=self.validate,
            max_depth=self.max_depth,
            id=self.id,
            instruction_template=self.instruction_template,
            exclude_tools=self.exclude_tools,
            auto_reload=self.auto_reload,
        )

    @classmethod
    def get_serialization_name(cls) -> str | None:
        """Return the name used to reference this capability in agent specs."""
        return 'SkillsCapability'

    @classmethod
    def from_spec(
        cls,
        *,
        directories: list[str] | None = None,
        validate: bool = True,
        max_depth: int | None = 3,
        id: str | None = None,
        instruction_template: str | None = None,
        exclude_tools: list[str] | None = None,
        auto_reload: bool = False,
        description: str | None = None,
        defer_loading: bool = False,
    ) -> SkillsCapability:
        """Create from a YAML/JSON agent spec.

        Only serializable arguments are supported. Programmatic `skills`, `registries`,
        and `SkillsDirectory` instances cannot be expressed in a spec; construct the
        capability in Python for those.

        Args:
            directories: Skill directories to discover, as path strings.
            validate: Validate skill structure during discovery.
            max_depth: Maximum discovery depth.
            id: Stable identifier shared by the capability and its toolset. Required when
                ``defer_loading`` is True.
            instruction_template: Optional custom instructions template.
            exclude_tools: Tool names to exclude.
            auto_reload: Re-scan directories before each run.
            description: Optional catalog description surfaced when ``defer_loading`` is True.
            defer_loading: If True, the skills tools and instructions stay hidden until the
                model loads this capability via the agent's ``load_capability`` tool.
        """
        return cls(
            directories=list(directories) if directories is not None else None,
            validate=validate,
            max_depth=max_depth,
            id=id,
            instruction_template=instruction_template,
            exclude_tools=exclude_tools,
            auto_reload=auto_reload,
            description=description,
            defer_loading=defer_loading,
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

"""pydantic-ai-skills: A tool-calling-based agent skills implementation for Pydantic AI.

This package provides a standardized, composable framework for building and managing
Agent Skills within the Pydantic AI ecosystem. Agent Skills are modular collections
of instructions, scripts, tools, and resources that enable AI agents to progressively
discover, load, and execute specialized capabilities for domain-specific tasks.

Key components:
- [`SkillsToolset`][pydantic_ai_skills.SkillsToolset]: Main toolset for integrating skills with agents
- [`Skill`][pydantic_ai_skills.Skill]: Data class representing a skill with resources and scripts
- [`SkillsDirectory`][pydantic_ai_skills.SkillsDirectory]: Filesystem-based skill discovery and management
- [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor]: Execute scripts via subprocess
- [`CallableSkillScriptExecutor`][pydantic_ai_skills.CallableSkillScriptExecutor]: Wrap callables as script executors

Example:
    ```python
    from pydantic_ai import Agent
    from pydantic_ai_skills import SkillsToolset

    # Initialize Skills Toolset with skill directories
    skills_toolset = SkillsToolset(directories=["./skills"])

    # Create agent with skills as a toolset
    # Skills instructions are automatically injected via get_instructions()
    agent = Agent(
        model='openai:gpt-5.2',
        instructions="You are a helpful research assistant.",
        toolsets=[skills_toolset]
    )

    # Use agent - skills tools are available for the agent to call
    result = await agent.run(
        "What are the last 3 papers on arXiv about machine learning?"
    )
    print(result.output)
    ```
"""

from pydantic_ai_skills.directory import SkillsDirectory, discover_skills, parse_skill_md
from pydantic_ai_skills.exceptions import (
    SkillException,
    SkillNotFoundError,
    SkillRegistryError,
    SkillResourceLoadError,
    SkillResourceNotFoundError,
    SkillScriptExecutionError,
    SkillValidationError,
)
from pydantic_ai_skills.local import CallableSkillScriptExecutor, LocalSkillScriptExecutor
from pydantic_ai_skills.registries import GitCloneOptions, GitSkillsRegistry, SkillRegistry
from pydantic_ai_skills.toolset import SkillsToolset
from pydantic_ai_skills.types import Skill, SkillResource, SkillScript

__all__ = [
    # Main toolset
    'SkillsToolset',
    # Directory discovery
    'SkillsDirectory',
    # Executors
    'LocalSkillScriptExecutor',
    'CallableSkillScriptExecutor',
    # Types
    'Skill',
    'SkillResource',
    'SkillScript',
    # Exceptions
    'SkillException',
    'SkillNotFoundError',
    'SkillRegistryError',
    'SkillResourceLoadError',
    'SkillResourceNotFoundError',
    'SkillScriptExecutionError',
    'SkillValidationError',
    # Registries
    'SkillRegistry',
    'GitSkillsRegistry',
    'GitCloneOptions',
    # Utility functions
    'discover_skills',
    'parse_skill_md',
]

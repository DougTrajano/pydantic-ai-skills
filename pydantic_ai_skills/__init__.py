"""pydantic-ai-skills: remote sources and bundled files for Pydantic AI Agent Skills.

`pydantic-ai-harness` ships a `Skills` capability that reads Agent Skill packages from
local directories and turns each `SKILL.md` into a deferred Pydantic AI capability. It
deliberately stops there: it does not fetch skills from anywhere remote, and it does not
enumerate, read, or execute the `references/`, `assets/` and `scripts/` files a skill
package ships alongside its instructions.

This package is the companion that fills those gaps. It hands discovery, validation and
instruction rendering to harness — so a skill behaves identically either way — and adds:

- **Remote registries.** Git and S3 sources, plus composition (filter, prefix, rename,
  merge), materialized into local libraries before harness reads them.
- **Bundled files.** `read_skill_resource` and `run_skill_script`, scoped per skill.
- **Sandboxed execution.** Run a skill's scripts in a container or virtual filesystem
  instead of on the host.
- **Programmatic skills.** Skills defined in Python, joining the same deferred catalog.

Key components:
- [`SkillsCapability`][pydantic_ai_skills.SkillsCapability]: The entry point; pass it to
  an agent's `capabilities=`
- [`SkillRegistry`][pydantic_ai_skills.SkillRegistry]: Base class for skill sources
- [`GitSkillsRegistry`][pydantic_ai_skills.GitSkillsRegistry]: Skills from a Git repository
- [`S3SkillsRegistry`][pydantic_ai_skills.S3SkillsRegistry]: Skills from an S3 bucket
- [`Skill`][pydantic_ai_skills.Skill] / [`skill`][pydantic_ai_skills.skill]: Skills defined in Python
- [`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor]: Protocol for custom script executors
- [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor]: Execute scripts via subprocess
- [`CallableSkillScriptExecutor`][pydantic_ai_skills.CallableSkillScriptExecutor]: Wrap callables as script executors
- [`OpenSandboxScriptExecutor`][pydantic_ai_skills.OpenSandboxScriptExecutor]: Run scripts in an OpenSandbox container
- [`LocalSandboxScriptExecutor`][pydantic_ai_skills.LocalSandboxScriptExecutor]: Run scripts in a LocalSandbox virtual filesystem

Example:
    ```python
    from pydantic_ai import Agent
    from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

    agent = Agent(
        'anthropic:claude-sonnet-4-6',
        instructions='You are a helpful research assistant.',
        capabilities=[
            SkillsCapability(
                '.agents/skills',
                registries=[
                    GitSkillsRegistry(
                        'https://github.com/anthropics/skills',
                        path='skills',
                    ),
                ],
            ),
        ],
    )

    # Each skill is deferred: the model sees names and descriptions, loads the ones it
    # needs with `load_capability`, then reads their files with `read_skill_resource`
    # and runs their scripts with `run_skill_script`.
    result = await agent.run(
        'What are the last 3 papers on arXiv about machine learning?'
    )
    print(result.output)
    ```
"""

from pydantic_ai_skills._parsing import SkillInfo
from pydantic_ai_skills.capability import SkillsCapability
from pydantic_ai_skills.executors import SkillScriptExecutor
from pydantic_ai_skills.local import CallableSkillScriptExecutor, LocalSkillScriptExecutor
from pydantic_ai_skills.packages import SkillPackage
from pydantic_ai_skills.registries import (
    GitCloneOptions,
    GitSkillsRegistry,
    LocalSkillsRegistry,
    S3SkillsRegistry,
    SkillRegistry,
)
from pydantic_ai_skills.sandboxes import LocalSandboxScriptExecutor, OpenSandboxScriptExecutor
from pydantic_ai_skills.types import Skill, SkillResource, SkillScript, SkillWrapper, skill

__all__ = [
    # Entry point
    'SkillsCapability',
    # Registries
    'SkillRegistry',
    'GitSkillsRegistry',
    'GitCloneOptions',
    'S3SkillsRegistry',
    'LocalSkillsRegistry',
    # Executors
    'SkillScriptExecutor',
    'LocalSkillScriptExecutor',
    'CallableSkillScriptExecutor',
    # Sandbox executors
    'OpenSandboxScriptExecutor',
    'LocalSandboxScriptExecutor',
    # Types
    'Skill',
    'SkillWrapper',
    'SkillResource',
    'SkillScript',
    'SkillInfo',
    'SkillPackage',
    # Programmatic skill decorator
    'skill',
]

"""Skills toolset for pydantic-ai-skills.

Skills are modular packages that extend agent capabilities. Each skill is a folder
containing a SKILL.md file with YAML frontmatter and Markdown instructions, along
with optional resource files (documents, scripts, etc.).

Progressive disclosure: Only skill metadata is exposed initially. The full
instructions are loaded on-demand when the agent calls the load_skill tool.

This module provides:
- SkillsToolset: A Pydantic AI toolset with four tools for skill management
- Skill discovery from filesystem directories
- YAML frontmatter parsing for SKILL.md files
- Safe script execution with path validation
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import anyio
import yaml
from pydantic_ai import RunContext
from pydantic_ai.toolsets import FunctionToolset

from pydantic_ai_skills.exceptions import (
    SkillNotFoundError,
    SkillResourceLoadError,
    SkillScriptExecutionError,
    SkillValidationError,
)
from pydantic_ai_skills.types import (
    Skill,
    SkillMetadata,
    SkillResource,
    SkillScript,
)

logger = logging.getLogger('pydantic-ai-skills')

# Anthropic's naming convention: lowercase letters, numbers, and hyphens only
SKILL_NAME_PATTERN = re.compile(r'^[a-z0-9-]+$')
RESERVED_WORDS = {'anthropic', 'claude'}


def _validate_skill_metadata(
    frontmatter: dict[str, Any],
    instructions: str,
) -> list[str]:
    """Validate skill metadata against Anthropic's requirements.

    Args:
        frontmatter: Parsed YAML frontmatter.
        instructions: The skill instructions content.

    Returns:
        List of validation warnings (empty if no issues).
    """
    warnings_list = []

    name = frontmatter.get('name', '')
    description = frontmatter.get('description', '')

    # Validate name format
    if name:
        # Check length first to prevent regex on excessively long strings
        if len(name) > 64:
            warnings_list.append(f"Skill name '{name}' exceeds 64 characters ({len(name)} chars)")
        # Only run regex if name is reasonable length (defense in depth)
        elif not SKILL_NAME_PATTERN.match(name):
            warnings_list.append(f"Skill name '{name}' should contain only lowercase letters, numbers, and hyphens")
        # Check for reserved words
        for reserved in RESERVED_WORDS:
            if reserved in name:
                warnings_list.append(f"Skill name '{name}' contains reserved word '{reserved}'")

    # Validate description
    if description and len(description) > 1024:
        warnings_list.append(f'Skill description exceeds 1024 characters ({len(description)} chars)')

    # Validate instructions length (Anthropic recommends under 500 lines)
    lines = instructions.split('\n')
    if len(lines) > 500:
        warnings_list.append(
            f'SKILL.md body exceeds recommended 500 lines ({len(lines)} lines). '
            f'Consider splitting into separate resource files.'
        )

    return warnings_list


def parse_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file into frontmatter and instructions.

    Uses PyYAML for robust YAML parsing.

    Args:
        content: Full content of the SKILL.md file.

    Returns:
        Tuple of (frontmatter_dict, instructions_markdown).

    Raises:
        SkillValidationError: If YAML parsing fails.
    """
    # Match YAML frontmatter between --- delimiters
    frontmatter_pattern = r'^---\s*\n(.*?)^---\s*\n'
    match = re.search(frontmatter_pattern, content, re.DOTALL | re.MULTILINE)

    if not match:
        # No frontmatter, treat entire content as instructions
        return {}, content.strip()

    frontmatter_yaml = match.group(1).strip()
    instructions = content[match.end() :].strip()

    # Handle empty frontmatter
    if not frontmatter_yaml:
        return {}, instructions

    try:
        frontmatter = yaml.safe_load(frontmatter_yaml)
        if frontmatter is None:
            frontmatter = {}
    except yaml.YAMLError as e:
        raise SkillValidationError(f'Failed to parse YAML frontmatter: {e}') from e

    return frontmatter, instructions


def _discover_resources(skill_folder: Path) -> list[SkillResource]:
    """Discover resource files in a skill folder.

    Resources are markdown files other than SKILL.md, plus any files
    in a resources/ subdirectory.

    Args:
        skill_folder: Path to the skill directory.

    Returns:
        List of discovered SkillResource objects.
    """
    resources: list[SkillResource] = []

    # Find .md files other than SKILL.md (FORMS.md, REFERENCE.md, etc.)
    for md_file in skill_folder.glob('*.md'):
        if md_file.name.upper() != 'SKILL.MD':
            resources.append(
                SkillResource(
                    name=md_file.name,
                    path=md_file.resolve(),
                )
            )

    # Find files in resources/ subdirectory if it exists
    resources_dir = skill_folder / 'resources'
    if resources_dir.exists() and resources_dir.is_dir():
        for resource_file in resources_dir.rglob('*'):
            if resource_file.is_file():
                rel_path = resource_file.relative_to(skill_folder)
                resources.append(
                    SkillResource(
                        name=str(rel_path),
                        path=resource_file.resolve(),
                    )
                )

    return resources


def _discover_scripts(skill_folder: Path, skill_name: str) -> list[SkillScript]:
    """Discover executable scripts in a skill folder.

    Looks for Python scripts in:
    - Directly in the skill folder (*.py)
    - In a scripts/ subdirectory

    Args:
        skill_folder: Path to the skill directory.
        skill_name: Name of the parent skill.

    Returns:
        List of discovered SkillScript objects.
    """
    scripts: list[SkillScript] = []

    # Find .py files in skill folder root (excluding __init__.py)
    for py_file in skill_folder.glob('*.py'):
        if py_file.name != '__init__.py':
            scripts.append(
                SkillScript(
                    name=py_file.stem,  # filename without .py
                    path=py_file.resolve(),
                    skill_name=skill_name,
                )
            )

    # Find .py files in scripts/ subdirectory
    scripts_dir = skill_folder / 'scripts'
    if scripts_dir.exists() and scripts_dir.is_dir():
        for py_file in scripts_dir.glob('*.py'):
            if py_file.name != '__init__.py':
                scripts.append(
                    SkillScript(
                        name=py_file.stem,
                        path=py_file.resolve(),
                        skill_name=skill_name,
                    )
                )

    return scripts


def discover_skills(
    directories: Sequence[str | Path],
    validate: bool = True,
) -> list[Skill]:
    """Discover skills from filesystem directories.

    Searches for SKILL.md files in the given directories and loads
    skill metadata and structure.

    Args:
        directories: List of directory paths to search for skills.
        validate: Whether to validate skill structure (requires name and description).

    Returns:
        List of discovered Skill objects.

    Raises:
        SkillValidationError: If validation is enabled and a skill is invalid.
    """
    skills: list[Skill] = []

    for skill_dir in directories:
        dir_path = Path(skill_dir).expanduser().resolve()

        if not dir_path.exists():
            logger.warning('Skills directory does not exist: %s', dir_path)
            continue

        if not dir_path.is_dir():
            logger.warning('Skills path is not a directory: %s', dir_path)
            continue

        # Find all SKILL.md files (recursive search)
        for skill_file in dir_path.glob('**/SKILL.md'):
            try:
                skill_folder = skill_file.parent
                content = skill_file.read_text(encoding='utf-8')
                frontmatter, instructions = parse_skill_md(content)

                # Get required fields
                name = frontmatter.get('name')
                description = frontmatter.get('description', '')

                # Validation
                if validate:
                    if not name:
                        logger.warning(
                            'Skill at %s missing required "name" field, skipping',
                            skill_folder,
                        )
                        continue
                    if not description:
                        logger.warning(
                            'Skill "%s" at %s missing "description" field',
                            name,
                            skill_folder,
                        )

                # Use folder name if name not provided
                if not name:
                    name = skill_folder.name

                # Extract extra metadata fields
                extra = {k: v for k, v in frontmatter.items() if k not in ('name', 'description')}

                # Create metadata
                metadata = SkillMetadata(
                    name=name,
                    description=description,
                    extra=extra,
                )

                # Validate metadata (log warnings)
                if validate:
                    validation_warnings = _validate_skill_metadata(frontmatter, instructions)
                    for warning in validation_warnings:
                        logger.warning('Skill "%s" at %s: %s', name, skill_folder, warning)

                # Discover resources and scripts
                resources = _discover_resources(skill_folder)
                scripts = _discover_scripts(skill_folder, name)

                # Create skill
                skill = Skill(
                    name=name,
                    path=skill_folder.resolve(),
                    metadata=metadata,
                    content=instructions,
                    resources=resources,
                    scripts=scripts,
                )

                skills.append(skill)
                logger.debug('Discovered skill: %s at %s', name, skill_folder)

            except SkillValidationError as e:
                logger.exception('Skill validation error in %s: %s', skill_file, e)
                raise
            except OSError as e:
                logger.warning('Failed to load skill from %s: %s', skill_file, e)
                continue

    logger.info('Discovered %d skills from %d directories', len(skills), len(directories))
    return skills


def _is_safe_path(base_path: Path, target_path: Path) -> bool:
    """Check if target_path is safely within base_path (no path traversal).

    Args:
        base_path: The base directory path.
        target_path: The target path to validate.

    Returns:
        True if target_path is within base_path, False otherwise.
    """
    try:
        target_path.resolve().relative_to(base_path.resolve())
        return True
    except ValueError:
        return False


class SkillsToolset(FunctionToolset):
    """Pydantic AI toolset for automatic skill discovery and integration.

    This is the primary interface for integrating skills with Pydantic AI agents.
    It implements the toolset protocol and automatically discovers, loads, and
    registers skills from specified directories.

    Provides the following tools to agents:
    - list_skills(): List all available skills
    - load_skill(skill_name): Load a specific skill's instructions
    - read_skill_resource(skill_name, resource_name): Read a skill resource file
    - run_skill_script(skill_name, script_name, args): Execute a skill script

    Example:
        ```python
        from pydantic_ai import Agent
        from pydantic_ai_skills import SkillsToolset

        skills_toolset = SkillsToolset(directories=["./skills"])

        agent = Agent(
            model='openai:gpt-4o',
            instructions="You are a helpful assistant.",
            toolsets=[skills_toolset]
        )

        @agent.system_prompt
        def add_skills_prompt() -> str:
            return skills_toolset.get_skills_system_prompt()
        ```
    """

    def __init__(
        self,
        directories: list[str | Path],
        *,
        auto_discover: bool = True,
        validate: bool = True,
        toolset_id: str = 'skills',
        script_timeout: int = 30,
        python_executable: str | Path | None = None,
    ) -> None:
        """Initialize the skills toolset.

        Args:
            directories: List of directory paths to search for skills.
            auto_discover: Automatically discover and load skills on init.
            validate: Validate skill structure and metadata on load.
            toolset_id: Unique identifier for this toolset.
            script_timeout: Timeout in seconds for script execution (default: 30).
            python_executable: Path to Python executable for running scripts.
                If None, uses sys.executable (default).
        """
        super().__init__(id=toolset_id)

        self._directories = [Path(d) for d in directories]
        self._validate = validate
        self._script_timeout = script_timeout
        self._python_executable = str(python_executable) if python_executable else sys.executable
        self._skills: dict[str, Skill] = {}

        if auto_discover:
            self._discover_skills()

        # Register tools
        self._register_tools()

    def _discover_skills(self) -> None:
        """Discover and load skills from configured directories."""
        skills = discover_skills(
            directories=self._directories,
            validate=self._validate,
        )
        self._skills = {skill.name: skill for skill in skills}

    def _register_tools(self) -> None:  # noqa: C901
        """Register skill management tools with the toolset.

        This method registers all four skill management tools:
        - list_skills: List available skills
        - load_skill: Load skill instructions
        - read_skill_resource: Read skill resources
        - run_skill_script: Execute skill scripts
        """

        @self.tool
        async def list_skills(_ctx: RunContext[Any]) -> str:
            """List all available skills with their descriptions.

            Only use this tool if the available skills are not in your system prompt.

            Returns:
                Formatted list of available skills with names and descriptions.
            """
            if not self._skills:
                return 'No skills available.'

            lines = ['# Available Skills', '']

            for name, skill in sorted(self._skills.items()):
                lines.append(f'{name}: {skill.metadata.description}')

            return '\n'.join(lines)

        @self.tool
        async def load_skill(ctx: RunContext[Any], skill_name: str) -> str:  # noqa: D417
            """Load full instructions for a skill.

            Always load the skill before using read_skill_resource
            or run_skill_script to understand the skill's capabilities, available
            resources, scripts, and their usage patterns.

            Args:
                skill_name: Name of the skill to load.

            Returns:
                Full skill instructions including available resources and scripts.
            """
            _ = ctx  # Required by Pydantic AI toolset protocol
            if skill_name not in self._skills:
                available = ', '.join(sorted(self._skills.keys())) or 'none'
                return f"Error: Skill '{skill_name}' not found. Available skills: {available}"

            skill = self._skills[skill_name]
            logger.info('Loading skill: %s', skill_name)

            lines = [
                f'# Skill: {skill.name}',
                f'**Description:** {skill.metadata.description}',
                f'**Path:** {skill.path}',
                '',
            ]

            # Add resource list if available
            if skill.resources:
                lines.append('**Available Resources:**')
                for resource in skill.resources:
                    lines.append(f'- {resource.name}')
                lines.append('')

            # Add scripts list if available
            if skill.scripts:
                lines.append('**Available Scripts:**')
                for script in skill.scripts:
                    lines.append(f'- {script.name}')
                lines.append('')

            lines.append('---')
            lines.append('')
            lines.append(skill.content)

            return '\n'.join(lines)

        @self.tool
        async def read_skill_resource(  # noqa: D417
            ctx: RunContext[Any],
            skill_name: str,
            resource_name: str,
        ) -> str:
            """Read a resource file from a skill (e.g., FORMS.md, REFERENCE.md).

            Call load_skill first to see which resources are available.

            Args:
                skill_name: Name of the skill.
                resource_name: The resource filename (e.g., "FORMS.md").

            Returns:
                The resource file content.
            """
            _ = ctx  # Required by Pydantic AI toolset protocol
            if skill_name not in self._skills:
                return f"Error: Skill '{skill_name}' not found."

            skill = self._skills[skill_name]

            # Find the resource
            resource = None
            for r in skill.resources:
                if r.name == resource_name:
                    resource = r
                    break

            if resource is None:
                available = [r.name for r in skill.resources]
                return (
                    f"Error: Resource '{resource_name}' not found in skill '{skill_name}'. "
                    f'Available resources: {available}'
                )

            # Security check
            if not _is_safe_path(skill.path, resource.path):
                logger.warning('Path traversal attempt detected: %s in %s', resource_name, skill_name)
                return 'Error: Resource path escapes skill directory.'

            try:
                content = resource.path.read_text(encoding='utf-8')
                logger.info('Read resource: %s from skill %s', resource_name, skill_name)
                return content
            except OSError as e:
                logger.error('Failed to read resource %s: %s', resource_name, e)
                raise SkillResourceLoadError(f"Failed to read resource '{resource_name}': {e}") from e

        @self.tool
        async def run_skill_script(  # noqa: D417
            ctx: RunContext[Any],
            skill_name: str,
            script_name: str,
            args: list[str] | None = None,
        ) -> str:
            """Execute a skill script with command-line arguments.

            Call load_skill first to understand the script's expected arguments,
            usage patterns, and example invocations. Running scripts without
            loading instructions first will likely fail.

            Args:
                skill_name: Name of the skill.
                script_name: The script name (without .py extension).
                args: Optional list of command-line arguments (positional args, flags, values).

            Returns:
                The script's output (stdout and stderr combined).
            """
            _ = ctx  # Required by Pydantic AI toolset protocol
            if skill_name not in self._skills:
                return f"Error: Skill '{skill_name}' not found."

            skill = self._skills[skill_name]

            # Find the script
            script = None
            for s in skill.scripts:
                if s.name == script_name:
                    script = s
                    break

            if script is None:
                available = [s.name for s in skill.scripts]
                return (
                    f"Error: Script '{script_name}' not found in skill '{skill_name}'. Available scripts: {available}"
                )

            # Security check
            if not _is_safe_path(skill.path, script.path):
                logger.warning('Path traversal attempt detected: %s in %s', script_name, skill_name)
                return 'Error: Script path escapes skill directory.'

            # Build command
            cmd = [self._python_executable, str(script.path)]
            if args:
                cmd.extend(args)

            logger.info('Running script: %s with args: %s', script_name, args)

            try:
                # Use anyio.run_process for async-compatible execution
                result = None
                with anyio.move_on_after(self._script_timeout) as scope:
                    result = await anyio.run_process(
                        cmd,
                        check=False,  # We handle return codes manually
                        cwd=str(skill.path),
                    )

                # Check if timeout was reached
                if scope.cancelled_caught:
                    logger.error('Script %s timed out after %d seconds', script_name, self._script_timeout)
                    raise SkillScriptExecutionError(
                        f"Script '{script_name}' timed out after {self._script_timeout} seconds"
                    )

                # At this point, result should be set (timeout check passed)
                assert result is not None

                # Decode output from bytes to string
                output = result.stdout.decode('utf-8', errors='replace')
                if result.stderr:
                    stderr = result.stderr.decode('utf-8', errors='replace')
                    output += f'\n\nStderr:\n{stderr}'

                if result.returncode != 0:
                    output += f'\n\nScript exited with code {result.returncode}'

                return output.strip() or '(no output)'

            except OSError as e:
                logger.error('Failed to execute script %s: %s', script_name, e)
                raise SkillScriptExecutionError(f"Failed to execute script '{script_name}': {e}") from e

    def get_skills_system_prompt(self) -> str:
        """Get the combined system prompt from all loaded skills.

        This should be added to the agent's system prompt to provide
        skill discovery and usage instructions.

        Following Anthropic's approach, this includes all skill metadata upfront
        in the system prompt, enabling the agent to discover and select skills
        without needing to call list_skills() first.

        Returns:
            Formatted system prompt containing:
            - All skill metadata (name + description)
            - Instructions for using skill tools
            - Progressive disclosure guidance
        """
        if not self._skills:
            return ''

        lines = [
            '# Skills',
            '',
            'You have access to skills that extend your capabilities. Skills are modular packages',
            'containing instructions, resources, and scripts for specialized tasks.',
            '',
            '## Available Skills',
            '',
            'The following skills are available to you. Use them when relevant to the task:',
            '',
        ]

        # List all skills with descriptions
        for name, skill in sorted(self._skills.items()):
            lines.append(f'- **{name}**: {skill.metadata.description}')

        lines.extend(
            [
                '## How to Use Skills',
                '',
                '**Progressive disclosure**: Load skill information only when needed.',
                '',
                '1. **When a skill is relevant to the current task**: Use `load_skill(skill_name)` to read the full instructions.',
                '2. **For additional documentation**: Use `read_skill_resource(skill_name, resource_name)` to read FORMS.md, REFERENCE.md, or other resources.',
                '3. **To execute skill scripts**: Use `run_skill_script(skill_name, script_name, args)` with appropriate command-line arguments.',
                '',
                '**Best practices**:',
                '- Select skills based on task relevance and descriptions listed above',
                '- Use progressive disclosure: load only what you need, when you need it, starting with load_skill',
                "- Follow the skill's documented usage patterns and examples",
                '',
            ]
        )

        return '\n'.join(lines)

    @property
    def skills(self) -> dict[str, Skill]:
        """Get the dictionary of loaded skills.

        Returns:
            Dictionary mapping skill names to Skill objects.
        """
        return self._skills

    def get_skill(self, name: str) -> Skill:
        """Get a specific skill by name.

        Args:
            name: The skill name.

        Returns:
            The Skill object.

        Raises:
            SkillNotFoundError: If the skill is not found.
        """
        if name not in self._skills:
            raise SkillNotFoundError(f"Skill '{name}' not found")
        return self._skills[name]

    def refresh(self) -> None:
        """Re-discover skills from configured directories.

        Call this method to reload skills after changes to the filesystem.
        """
        logger.info('Refreshing skills from directories')
        self._discover_skills()

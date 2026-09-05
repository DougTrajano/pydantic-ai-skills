"""The skill-file toolset: the two tools harness's `Skills` deliberately does not provide.

harness turns each `SKILL.md` into a deferred capability, so the model reaches a skill's
*instructions* through pydantic-ai's own `load_capability` tool. What it cannot reach is
the rest of the package — the `references/`, `assets/` and `scripts/` files those
instructions tell it to use. This toolset closes that gap with
`read_skill_resource` and `run_skill_script`.

Both tools are keyed by `skill_name` and live on a single always-registered toolset
rather than one toolset per skill: per-skill toolsets would contribute colliding tool
names as soon as the model loaded two skills at once.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from pydantic import BeforeValidator
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.toolsets import FunctionToolset

from pydantic_ai_skills.packages import SkillPackage

__all__ = ['SkillFilesToolset']


def _coerce_to_dict(v: Any) -> Any:
    """Convert JSON string to dict if needed, pass through non-string values unchanged."""
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError as e:
            # Catch JSON parsing errors and throw a more intuitive error message
            raise ValueError(
                f'Invalid JSON string. Error: {e.msg} at line {e.lineno} col {e.colno}. Input snippet: {v[:100]}'
            ) from e
        if not isinstance(parsed, dict):
            raise ValueError(f'args must be a JSON object, got {type(parsed).__name__}')
        return parsed
    return v


class SkillFilesToolset(FunctionToolset[Any]):
    """Expose the bundled resources and scripts of indexed skill packages.

    Registers `read_skill_resource` and/or `run_skill_script`, both taking the skill's
    name as their first argument. The packages come from
    [`index_libraries`][pydantic_ai_skills.packages.index_libraries] and from
    programmatic skills; the keys line up with the capability ids harness assigns, which
    is what makes the `require_loaded` gate work.

    Args:
        packages: Mapping of skill name to its
            [`SkillPackage`][pydantic_ai_skills.packages.SkillPackage].
        resources: Register `read_skill_resource`.
        scripts: Register `run_skill_script`.
        require_loaded: Refuse calls for a skill the model has not loaded yet, so bundled
            files stay behind the same progressive-disclosure boundary as the skill's
            instructions. Set False when a skill's files should be reachable without
            loading it first.
        id: Toolset id, forwarded to `FunctionToolset`.
        max_retries: Retry budget for `ModelRetry`, forwarded to `FunctionToolset`.
    """

    def __init__(
        self,
        packages: dict[str, SkillPackage],
        *,
        resources: bool = True,
        scripts: bool = True,
        require_loaded: bool = True,
        id: str | None = None,
        max_retries: int = 1,
    ) -> None:
        super().__init__(id=id, max_retries=max_retries)
        self._packages = packages
        self._require_loaded = require_loaded

        if resources:
            self._register_read_skill_resource()
        if scripts:
            self._register_run_skill_script()

    @property
    def packages(self) -> dict[str, SkillPackage]:
        """The indexed skill packages this toolset serves files from."""
        return self._packages

    def _resolve_package(self, ctx: RunContext[Any], skill_name: str) -> SkillPackage:
        """Return the package for `skill_name`, or raise `ModelRetry` explaining why not.

        Raises:
            ModelRetry: When the skill is unknown, or when `require_loaded` is set and the
                model has not loaded it via `load_capability` yet.
        """
        package = self._packages.get(skill_name)
        if package is None:
            available = ', '.join(sorted(self._packages)) or 'none'
            raise ModelRetry(
                f"Skill '{skill_name}' has no bundled files available. Skills with bundled files: {available}. "
                'Use the exact skill name.'
            )

        # `active_capability_ids` covers always-on capabilities plus the deferred ones the
        # model has loaded. Every skill is deferred, so this reads "the model loaded it".
        # It is refreshed from message history before each request, so a skill loaded in an
        # earlier step is visible here; only a call issued in the *same* step as the
        # `load_capability` is refused, and the retry tells the model to try again.
        if self._require_loaded and skill_name not in ctx.active_capability_ids:
            raise ModelRetry(
                f"Skill '{skill_name}' is not loaded. Call load_capability with id='{skill_name}' "
                'first, then read its files.'
            )

        return package

    def _register_read_skill_resource(self) -> None:
        """Register the read_skill_resource tool."""

        @self.tool
        async def read_skill_resource(  # pyright: ignore[reportUnusedFunction]  # noqa: D417
            ctx: RunContext[Any],
            skill_name: str,
            resource_name: str,
            args: Annotated[dict[str, Any] | None, BeforeValidator(_coerce_to_dict)] = None,
        ) -> str:
            """Read a supplementary file bundled with a skill.

            Skill packages ship reference documentation, templates, schemas and data files
            alongside their instructions. A skill's instructions name the ones it needs;
            this tool reads them.

            When to use this:
            - When a loaded skill's instructions reference a specific file
            - To access form templates, reference documentation, or data schemas
            - When you need supplementary information beyond the skill instructions

            Args:
                skill_name: Name of the skill containing the resource, exactly as it
                    appears in the capability catalog.
                resource_name: Path of the resource relative to the skill directory.
                    Examples: "FORMS.md", "references/REFERENCE.md", "get_schema"
                    Must match exactly - do not infer or guess.
                args: Arguments for callable resources (optional for static files).
                    Keys must match the parameter names in the resource's schema.

            Returns:
                The resource content as a string.

            Important:
            - Load the skill with `load_capability` first; its instructions list the files
            - Use exact resource names - do not modify or guess
            - Static files don't need args; callable resources may require them
            """
            package = self._resolve_package(ctx, skill_name)

            resource = package.resources_by_name.get(resource_name)
            if resource is None:
                available = sorted(package.resources_by_name)
                raise ModelRetry(
                    f"Resource '{resource_name}' not found in skill '{skill_name}'. "
                    f'Available resources: {available}. Use the exact name from the skill instructions.'
                )

            return await resource.load(ctx=ctx, args=args)

    def _register_run_skill_script(self) -> None:
        """Register the run_skill_script tool."""

        @self.tool
        async def run_skill_script(  # pyright: ignore[reportUnusedFunction]  # noqa: D417
            ctx: RunContext[Any],
            skill_name: str,
            script_name: str,
            args: Annotated[dict[str, Any] | None, BeforeValidator(_coerce_to_dict)] = None,
        ) -> str:
            """Execute a script bundled with a skill.

            Scripts are executable programs a skill ships to perform actions (API calls,
            file operations), process data (transformations, analysis), or generate
            outputs (reports, visualizations).

            When to use this:
            - When a loaded skill's instructions tell you to run a specific script
            - To perform automated tasks that the skill provides
            - For data processing, API interactions, or file operations

            Args:
                skill_name: Name of the skill containing the script, exactly as it appears
                    in the capability catalog.
                script_name: Path of the script relative to the skill directory.
                    Examples: "analyze.py", "scripts/analyze.py", "scripts/deploy.sh"
                    Must match exactly - do not infer or guess.
                args: Arguments required by the script.
                    Keys must match the parameter names in the script's schema.

            Returns:
                Script execution output including stdout and stderr.

            Important:
            - Load the skill with `load_capability` first; its instructions list the scripts
            - Use exact script names - do not modify or guess
            - Review the skill's instructions before running its scripts
            - Scripts may modify external state (files, databases, APIs)
            - Execution errors are included in the output
            """
            package = self._resolve_package(ctx, skill_name)

            script = package.scripts_by_name.get(script_name)
            if script is None:
                available = sorted(package.scripts_by_name)
                raise ModelRetry(
                    f"Script '{script_name}' not found in skill '{skill_name}'. "
                    f'Available scripts: {available}. Use the exact name from the skill instructions.'
                )

            return await script.run(ctx=ctx, args=args)

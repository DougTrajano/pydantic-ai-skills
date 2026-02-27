# Copilot Instructions for pydantic-ai-skills

## Project Overview

Python library (Python ≥3.10) implementing the [Agent Skills specification](https://agentskills.io/specification) for Pydantic AI. Agent Skills is an open format maintained by Anthropic and open to contributions from the community. Skills are modular collections of instructions, scripts, and resources that extend AI agent capabilities through **progressive disclosure** (load-on-demand to reduce token usage).

## Core Architecture

**3-Layer Skill System:**

1. **Discovery Layer** ([directory.py](../pydantic_ai_skills/directory.py)): `SkillsDirectory` scans filesystem for skills, validates YAML frontmatter in SKILL.md files
2. **Type Layer** ([types.py](../pydantic_ai_skills/types.py)): Dataclasses (`Skill`, `SkillResource`, `SkillScript`) with dual modes — file-based (subclassed in `local.py`) and programmatic (callables with `function_schema`)
3. **Integration Layer** ([toolset.py](../pydantic_ai_skills/toolset.py)): `SkillsToolset` extends Pydantic AI's `FunctionToolset`, auto-registers 4 tools: `list_skills`, `load_skill`, `read_skill_resource`, `run_skill_script`

Registries (`pydantic_ai_skills/registries/`) extend discovery to remote sources (Git repos) with composition wrappers (`FilteredRegistry`, `PrefixedRegistry`, `RenamedRegistry`, `CombinedRegistry`).

**Dual Skill Modes:**

- **Filesystem skills**: Directory with SKILL.md + optional scripts/, resources (see [examples/skills/arxiv-search/](../examples/skills/arxiv-search/))
- **Programmatic skills**: Python-defined via decorators with callable resources/scripts (see [examples/programatic_skills.py](../examples/programatic_skills.py))

## Critical Patterns

### Tool Registration (toolset.py)

Tools are registered using Pydantic AI's `@self.tool` decorator. **Every tool function MUST accept `ctx: RunContext[Any]` as first parameter** (protocol requirement), even if unused:

```python
@self.tool
async def load_skill(ctx: RunContext[Any], skill_name: str) -> str:
    """Load full instructions for a skill."""
    _ = ctx  # Required by protocol, suppress unused warning
    skill = self.get_skill(skill_name)
    return LOAD_SKILL_TEMPLATE.format(...)
```

### Skill Naming Conventions (directory.py#L35-L36)

The Agent Skills spec enforces strict validation (warnings, not errors):

- Pattern: `^[a-z0-9]+(-[a-z0-9]+)*$` (lowercase, hyphens only)
- Max 64 chars, no reserved words (`anthropic`, `claude`)
- Use `normalize_skill_name()` to convert function names (underscores → hyphens). Violations emit warnings, not errors.
- Example: `arxiv-search`, `web-research` ✓ | `ArxivSearch`, `claude_helper` ✗

### YAML Frontmatter Parsing (toolset.py#L94-L121)

Uses regex `^---\s*\n(.*?)^---\s*\n` with `DOTALL|MULTILINE` flags to extract frontmatter, then `yaml.safe_load()`. Critical fields:

- `name` (required): Skill identifier
- `description` (required, ≤1024 chars): Used in tool selection

### Security Measures

- **Path traversal prevention**: `_is_safe_path()` checks before any file read
- **Script timeout**: Default 30s, configurable via `script_timeout` param
- **Async execution**: Scripts run via `anyio.run_process` (not `subprocess`)
- **Symlink escape detection**: in `_discover_resources()`

## Development Workflow

### Testing (pytest.ini)

```bash
pytest                     # Full suite with coverage
pytest tests/test_toolset.py -v  # Specific test file
```

- `pytest-asyncio` in auto mode - **no `@pytest.mark.asyncio` needed**
- Fixtures use `tmp_path` to create temporary skill directories (see `sample_skills_dir` in `tests/test_toolset.py`)
- Coverage reports to `htmlcov/` and terminal
- Markers: `slow`, `integration`

### Code Style (pyproject.toml)

```bash
ruff check pydantic_ai_skills/   # Lint
ruff format pydantic_ai_skills/  # Format
```

- **Single quotes** for strings (enforced by ruff)
- **Google docstring** convention (D-series rules)
- Line length: 120 chars
- Max complexity: 15 (mccabe)

### Running Examples

```bash
# Basic usage with filesystem skills
python examples/basic_usage.py

# Programmatic skills with HR analytics
python examples/programatic_skills.py
```

Examples expect skill-specific dependencies (e.g., `arxiv` package). Install on-demand as needed per skill.

## Exception Hierarchy

All inherit from `SkillException` in `pydantic_ai_skills/exceptions.py`:
`SkillNotFoundError`, `SkillValidationError`, `SkillResourceNotFoundError`, `SkillResourceLoadError`, `SkillScriptExecutionError`, `SkillRegistryError`.

## Key Files Reference

| File                                                 | Purpose                                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------------------------ |
| [toolset.py](../pydantic_ai_skills/toolset.py)       | Main integration — tool registration, `get_instructions()`, `@skill` decorator |
| [types.py](../pydantic_ai_skills/types.py)           | Data structures — `Skill.resource()`, `Skill.script()`, `SkillWrapper`         |
| [directory.py](../pydantic_ai_skills/directory.py)   | Filesystem scanning — `validate_skill_metadata()`, `parse_skill_md()`          |
| [local.py](../pydantic_ai_skills/local.py)           | File-based resource/script implementations, `LocalSkillScriptExecutor`         |
| [registries/](../pydantic_ai_skills/registries/)     | Remote skill sources — `GitSkillsRegistry`, composition wrappers               |
| [exceptions.py](../pydantic_ai_skills/exceptions.py) | Exception hierarchy — all inherit from `SkillException`                        |
| [test_toolset.py](../tests/test_toolset.py)          | Primary test patterns — `sample_skills_dir` fixture shows skill structure      |

## Creating New Skills

**Filesystem skill minimum (examples/skills/arxiv-search/):**

```markdown
---
name: my-skill
description: Brief description (max 1024 chars)
---

# Instructions

When to use, how to use, example invocations...
```

**With scripts (scripts/ subdirectory):**

- Python files executed via subprocess
- Document args in SKILL.md
- Use `run_skill_script(skill_name, script_name, args)` from agent

**Programmatic skill (see examples/programatic_skills.py):**

- Create `Skill` instance with metadata
- Use `@skill.resource` decorator for dynamic content
- Use `@skill.script` decorator for executable functions
- Both decorators support `takes_ctx=True` for RunContext access

## Progressive Disclosure Flow

1. Agent receives skill list via `get_instructions()` in system prompt
2. Agent calls `load_skill(name)` to get full SKILL.md content
3. Optionally calls `read_skill_resource(skill_name, resource)` for FORMS.md, REFERENCE.md
4. Executes `run_skill_script(skill_name, script, args)` when needed

This pattern keeps initial context small - agents discover capabilities incrementally.

## Priority Order for Skill Sources

1. Programmatic skills (passed via `skills=[]`) — highest priority
2. Directory-based skills (passed via `directories=[]`)
3. Registry skills (passed via `registries=[]`) — lowest, never override existing

If neither `skills`, `directories`, nor `registries` are provided, defaults to `./skills` directory.

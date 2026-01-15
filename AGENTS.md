# Copilot Instructions for pydantic-ai-skills

## Project Overview

Python library implementing [Anthropic's Agent Skills framework](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) for Pydantic AI. Skills are modular collections of instructions, scripts, and resources that extend AI agent capabilities through **progressive disclosure** (load-on-demand to reduce token usage).

## Core Architecture

**3-Layer Skill System:**

1. **Discovery Layer** ([directory.py](../pydantic_ai_skills/directory.py)): `SkillsDirectory` scans filesystem for skills, validates YAML frontmatter in SKILL.md files
2. **Type Layer** ([types.py](../pydantic_ai_skills/types.py)): Dataclasses (`Skill`, `SkillResource`, `SkillScript`) with inheritance for file vs. programmatic variants
3. **Integration Layer** ([toolset.py](../pydantic_ai_skills/toolset.py)): `SkillsToolset` extends Pydantic AI's `FunctionToolset`, auto-registers 4 tools: `list_skills`, `load_skill`, `read_skill_resource`, `run_skill_script`

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

Anthropic enforces strict validation (warnings, not errors):

- Pattern: `^[a-z0-9-]+$` (lowercase, hyphens only)
- Max 64 chars, no reserved words (`anthropic`, `claude`)
- Example: `arxiv-search`, `web-research` ✓ | `ArxivSearch`, `claude_helper` ✗

### YAML Frontmatter Parsing (toolset.py#L94-L121)

Uses regex `^---\s*\n(.*?)^---\s*\n` with `DOTALL|MULTILINE` flags to extract frontmatter, then `yaml.safe_load()`. Critical fields:

- `name` (required): Skill identifier
- `description` (required, ≤1024 chars): Used in tool selection

### Security Measures

- **Path traversal prevention**: `_is_safe_path()` checks before any file read
- **Script timeout**: Default 30s, configurable via `script_timeout` param
- **Async execution**: Scripts run via `anyio.run_process` (not `subprocess`)

## Development Workflow

### Testing (pytest.ini)

```bash
pytest                     # Full suite with coverage
pytest tests/test_toolset.py -v  # Specific test file
```

- `pytest-asyncio` in auto mode - **no `@pytest.mark.asyncio` needed**
- Fixtures use `tmp_path` to create temporary skill directories
- Coverage reports to `htmlcov/` and terminal

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

## Key Files Reference

- [toolset.py](../pydantic_ai_skills/toolset.py): Main integration point - start here for tool logic
- [types.py](../pydantic_ai_skills/types.py): Data structures - understand `SkillResource.load()` and `SkillScript.execute()` methods
- [directory.py](../pydantic_ai_skills/directory.py): Filesystem scanning - see `_validate_skill_metadata()` for Anthropic rules
- [exceptions.py](../pydantic_ai_skills/exceptions.py): Exception hierarchy - all inherit from `SkillException`
- [test_toolset.py](../tests/test_toolset.py): Test patterns - see `sample_skills_dir` fixture for skill structure

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

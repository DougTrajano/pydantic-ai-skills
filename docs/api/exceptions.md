# Exceptions API Reference

Exception classes for pydantic-ai-skills error handling.

## Exception Hierarchy

```
Exception
└── SkillException (base)
    ├── SkillNotFoundError
    ├── SkillValidationError
    ├── SkillResourceLoadError
    └── SkillScriptExecutionError
```

## Exception Classes

::: pydantic_ai_skills.exceptions.SkillException
    options:
      show_source: true
      heading_level: 3

::: pydantic_ai_skills.exceptions.SkillNotFoundError
    options:
      show_source: true
      heading_level: 3

::: pydantic_ai_skills.exceptions.SkillValidationError
    options:
      show_source: true
      heading_level: 3

::: pydantic_ai_skills.exceptions.SkillResourceLoadError
    options:
      show_source: true
      heading_level: 3

::: pydantic_ai_skills.exceptions.SkillScriptExecutionError
    options:
      show_source: true
      heading_level: 3

## Usage Examples

### Handling SkillNotFoundError

```python
from pydantic_ai_skills import SkillsToolset, SkillNotFoundError

toolset = SkillsToolset(directories=["./skills"])

try:
    skill = toolset.get_skill("non-existent-skill")
except SkillNotFoundError as e:
    print(f"Error: {e}")
    print("Available skills:", list(toolset.skills.keys()))
```

### Handling SkillValidationError

```python
from pydantic_ai_skills import discover_skills, SkillValidationError

try:
    skills = discover_skills(
        directories=["./skills"],
        validate=True  # Strict validation
    )
except SkillValidationError as e:
    print(f"Skill validation failed: {e}")
```

### Handling SkillResourceLoadError

```python
from pydantic_ai_skills import SkillsToolset, SkillResourceLoadError

toolset = SkillsToolset(directories=["./skills"])
skill = toolset.get_skill("my-skill")

try:
    # Attempt to read a resource
    for resource in skill.resources:
        content = resource.path.read_text()
except SkillResourceLoadError as e:
    print(f"Failed to load resource: {e}")
```

### Handling SkillScriptExecutionError

```python
from pydantic_ai import Agent
from pydantic_ai_skills import SkillsToolset, SkillScriptExecutionError

toolset = SkillsToolset(
    directories=["./skills"],
    script_timeout=10  # 10 second timeout
)

agent = Agent(model='openai:gpt-5.2', toolsets=[toolset])

# The agent will receive an error if script times out or fails
result = await agent.run("Run the long-running-script")
# If script times out, agent will see:
# "Script 'script_name' timed out after 10 seconds"
```

### General Exception Handling

```python
from pydantic_ai_skills import (
    SkillsToolset,
    SkillException,
    SkillNotFoundError,
    SkillValidationError
)

try:
    toolset = SkillsToolset(directories=["./skills"])
    skill = toolset.get_skill("my-skill")
    # ... work with skill ...

except SkillNotFoundError as e:
    print(f"Skill not found: {e}")
except SkillValidationError as e:
    print(f"Validation error: {e}")
except SkillException as e:
    print(f"General skill error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## When Exceptions Are Raised

### SkillNotFoundError

Raised by:
- `SkillsToolset.get_skill(name)` - When skill doesn't exist

### SkillValidationError

Raised by:
- `discover_skills()` - When YAML frontmatter is invalid
- `parse_skill_md()` - When YAML parsing fails

### SkillResourceLoadError

Raised by:
- `read_skill_resource` tool - When resource file can't be read
- File I/O operations on skill resources

### SkillScriptExecutionError

Raised by:
- `run_skill_script` tool - When script execution fails or times out
- Subprocess operations on skill scripts

## Best Practices

### 1. Catch Specific Exceptions

```python
# ✅ Good - specific handling
try:
    skill = toolset.get_skill("my-skill")
except SkillNotFoundError:
    print("Skill not found, using default behavior")
    skill = None

# ❌ Bad - too broad
try:
    skill = toolset.get_skill("my-skill")
except Exception:
    pass
```

### 2. Provide Helpful Error Messages

```python
# ✅ Good - informative
try:
    skill = toolset.get_skill(skill_name)
except SkillNotFoundError:
    available = ", ".join(toolset.skills.keys())
    print(f"Skill '{skill_name}' not found.")
    print(f"Available skills: {available}")

# ❌ Bad - not helpful
try:
    skill = toolset.get_skill(skill_name)
except SkillNotFoundError:
    print("Error")
```

### 3. Log Exceptions in Production

```python
import logging
from pydantic_ai_skills import SkillException

logger = logging.getLogger(__name__)

try:
    toolset = SkillsToolset(directories=["./skills"])
except SkillException as e:
    logger.error(f"Failed to initialize skills: {e}", exc_info=True)
    # Handle gracefully
```

## See Also

- [SkillsToolset](toolset.md) - Main toolset API
- [Types](types.md) - Type definitions
- [Core Concepts](../concepts.md) - Understanding skills

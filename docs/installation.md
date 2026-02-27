# Installation

## Requirements

- Python 3.10 or higher
- Pydantic AI (installed automatically as a dependency)

## Install from PyPI

```bash
pip install pydantic-ai-skills
```

## Install from Source

For development or to use the latest features:

```bash
git clone https://github.com/dougtrajano/pydantic-ai-skills.git
cd pydantic-ai-skills
pip install -e .
```

## Verify Installation

```python
from pydantic_ai_skills import SkillsToolset

print("pydantic-ai-skills installed successfully!")
```

## Dependencies

The package automatically installs:

- `pydantic-ai-slim>=0.0.1` - Core Pydantic AI framework
- `pyyaml>=6.0` - YAML parsing for skill metadata

## Optional Dependencies

Depending on your skills, you may need additional packages:

```bash
# For Git-based skill registries
pip install pydantic-ai-skills[git]

# For skills that use HTTP requests
pip install httpx

# For skills that work with pandas
pip install pandas

# For skills that use OpenAI
pip install openai
```

## Next Steps

- [Quick Start](quick-start.md) - Build your first agent with skills
- [Creating Skills](creating-skills.md) - Learn how to create custom skills
- [Skill Registries](registries.md) - Load skills from Git repositories

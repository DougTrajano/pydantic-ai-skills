# pydantic-ai-skills

Anthropic Agent Skills for pydantic-ai.

This package provides reusable skills for Anthropic agents using pydantic-ai. It includes a skill registry system that makes it easy to create, manage, and execute agent skills.

## Features

- 🎯 **Skill Registry**: Manage and organize agent skills
- 🔧 **Built-in Skills**: Text processing and data extraction skills included
- 🤖 **Anthropic Compatible**: Direct integration with Anthropic API tool format
- 📦 **Type Safe**: Built with Pydantic for robust type checking
- 🚀 **Easy to Extend**: Create custom skills by extending the base `Skill` class

## Installation

Using uv (recommended):

```bash
uv add pydantic-ai-skills
```

Using pip:

```bash
pip install pydantic-ai-skills
```

## Quick Start

```python
from pydantic_ai_skills import create_default_registry

# Create a registry with default skills
registry = create_default_registry()

# Execute a skill
result = registry.execute_skill(
    "text_processing",
    text="Hello World",
    operation="uppercase"
)
print(result)  # Output: HELLO WORLD

# Get Anthropic tools format
tools = registry.to_anthropic_tools()
```

## Built-in Skills

### TextProcessingSkill

Process and analyze text content with operations like:
- `uppercase`: Convert text to uppercase
- `lowercase`: Convert text to lowercase
- `word_count`: Count words in text
- `char_count`: Count characters in text

### DataExtractionSkill

Extract structured data from unstructured text:
- `email`: Extract email addresses
- `phone`: Extract phone numbers
- `url`: Extract URLs

## Creating Custom Skills

```python
from pydantic_ai_skills import Skill

class MyCustomSkill(Skill):
    name: str = "my_skill"
    description: str = "Description of what my skill does"
    parameters: dict = {
        "param1": {
            "type": "string",
            "description": "First parameter"
        }
    }
    
    def execute(self, param1: str) -> str:
        # Your skill implementation
        return f"Processed: {param1}"

# Register the skill
registry.register(MyCustomSkill())
```

## Usage with pydantic-ai

The skills can be converted to Anthropic tool format for use with pydantic-ai:

```python
from pydantic_ai_skills import create_default_registry

registry = create_default_registry()
tools = registry.to_anthropic_tools()

# Use tools with pydantic-ai agent
# agent = Agent(model='claude-3-5-sonnet-20241022', tools=tools)
```

## Examples

See the [examples](examples/) directory for more detailed usage examples.

## Development

This project uses `uv` for dependency management.

### Setup

```bash
# Install dependencies
uv sync

# Run example
uv run python examples/basic_usage.py
```

### Running Tests

```bash
uv run pytest
```

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.


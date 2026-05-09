# Contributing

Thank you for your interest in contributing to pydantic-ai-skills!

## Ways to Contribute

- **Report bugs** - Open an issue describing the problem
- **Suggest features** - Share ideas for new functionality
- **Improve documentation** - Fix typos, clarify explanations, add examples
- **Share skills** - Contribute useful skill examples
- **Submit code** - Fix bugs or implement features

## Development Setup

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/pydantic-ai-skills.git
cd pydantic-ai-skills
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### 4. Install Pre-commit Hooks

```bash
pre-commit install
```

## Making Changes

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

### 2. Make Your Changes

- Follow existing code style
- Add tests for new functionality
- Update documentation as needed
- Keep commits focused and atomic

### 3. Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pydantic_ai_skills

# Run specific test
pytest tests/test_toolset.py::test_discover_skills
```

### 4. Check Code Quality

```bash
# Run pre-commit checks
pre-commit run --all-files

# Or run individually
ruff check .
ruff format .
mypy pydantic_ai_skills
```

## Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/)
- Use type hints for all functions
- Maximum line length: 120 characters
- Use Ruff for linting and formatting

### Documentation

- Add docstrings to all public functions/classes
- Use Google-style docstring format
- Include examples in docstrings when helpful

### Example Docstring

```python
def discover_skills(
    directories: list[str | Path],
    validate: bool = True,
) -> list[Skill]:
    """Discover skills from filesystem directories.

    Searches for SKILL.md files in the given directories and loads
    skill metadata and structure.

    Args:
        directories: List of directory paths to search for skills.
        validate: Whether to validate skill structure.

    Returns:
        List of discovered Skill objects.

    Raises:
        ValueError: If validation enabled and skill is invalid.

    Example:
        ```python
        skills = discover_skills(
            directories=["./skills"],
            validate=True
        )
        for skill in skills:
            print(f"{skill.name}: {skill.metadata.description}")
        ```
    """
```

## Testing

### Writing Tests

- Place tests in `tests/` directory
- Use pytest for testing
- Aim for high code coverage
- Test edge cases and error conditions

### Test Structure

```python
import pytest
from pydantic_ai_skills import SkillsToolset

def test_toolset_init():
    """Test SkillsToolset initialization."""
    toolset = SkillsToolset(directories=["./test_skills"])
    assert len(toolset.skills) > 0

def test_get_skill_not_found():
    """Test get_skill raises error for non-existent skill."""
    toolset = SkillsToolset(directories=["./test_skills"])

    with pytest.raises(KeyError):
        toolset.get_skill("non-existent")
```

## Pull Request Process

### 1. Update Documentation

- Update README.md if needed
- Add/update docstrings
- Update relevant docs/ pages

### 2. Update CHANGELOG

Add an entry under "Unreleased":

```markdown
## [Unreleased]

### Added
- New feature description (#PR_NUMBER)

### Fixed
- Bug fix description (#PR_NUMBER)
```

### 3. Create Pull Request

- Write clear PR title and description
- Reference related issues
- Ensure all checks pass
- Request review

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] CHANGELOG updated
- [ ] All tests pass
- [ ] Pre-commit checks pass
```

## Reporting Issues

### Bug Reports

Include:
- Python version
- pydantic-ai-skills version
- Minimal reproducible example
- Expected vs actual behavior
- Full error traceback

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternative approaches considered
- Examples of usage

## Community Guidelines

- Be respectful and inclusive
- Follow the [Code of Conduct](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/CODE_OF_CONDUCT.md)
- Help others learn and grow
- Credit contributors

## Questions?

- Open a [Discussion](https://github.com/dougtrajano/pydantic-ai-skills/discussions)
- Join community channels (if available)
- Check existing issues and PRs

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

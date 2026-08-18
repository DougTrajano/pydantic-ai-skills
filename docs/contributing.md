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

### 2. Label the PR for the release notes

There is no `CHANGELOG.md`. Release notes are generated from merged PR titles, grouped by
label, as configured in [`.github/release.yml`](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/.github/release.yml).

So two things matter:

- **The PR title is the changelog entry.** Write it for someone reading the
  [releases page](https://github.com/dougtrajano/pydantic-ai-skills/releases), not for the diff.
- **Apply one label**: `feature`, `bug`, or `dependency` to place it in a section;
  `docs` or `chore` to leave it out of the notes entirely.

### 3. Create Pull Request

- Write clear PR title and description
- Reference related issues
- Ensure all checks pass
- Request review

### PR Template

GitHub fills this in for you from
[`.github/pull_request_template.md`](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/.github/pull_request_template.md)
when you open the PR. Work through the checklist it gives you rather than copying one from here.

One item on it is worth calling out: if you used an AI coding agent, you are attesting that
you reviewed its output line by line and stand behind it. Generated code is welcome; unread
generated code is not.

## Reporting Issues

Open an issue from the [issue templates](https://github.com/dougtrajano/pydantic-ai-skills/issues/new/choose).
The bug and feature-request forms prompt for everything needed to act on the report —
versions, a minimal reproducible example, expected versus actual behavior for bugs; use case,
proposal, and alternatives considered for features.

Usage questions belong in
[Discussions](https://github.com/dougtrajano/pydantic-ai-skills/discussions) instead.

Security vulnerabilities are the exception: **do not open a public issue**. Report them
privately as described in
[`SECURITY.md`](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/SECURITY.md).

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

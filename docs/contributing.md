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
pytest tests/test_capability.py::test_each_skill_becomes_one_deferred_capability
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
def index_libraries(
    libraries: Sequence[str | Path],
    *,
    script_executor: SkillScriptExecutor | None = None,
) -> dict[str, SkillPackage]:
    """Index the bundled files of every skill package in `libraries`.

    Scans the immediate child directories of each library for a `SKILL.md`, exactly as
    harness's `Skills` does, so the keys of the returned mapping line up with the `id`
    of each deferred capability harness produces.

    Args:
        libraries: Skill-library directories. Non-existent entries are skipped.
        script_executor: Executor used for the discovered scripts.

    Returns:
        Mapping of NFKC-normalized skill name to its `SkillPackage`.
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

from pydantic_ai_skills import SkillsCapability


def test_a_library_is_exposed_as_a_catalog(tmp_path):
    """Each skill package becomes one entry the model can load."""
    write_skill(tmp_path, 'demo-skill')

    assert SkillsCapability(tmp_path).skill_names == ['demo-skill']


def test_unknown_include_name_is_rejected(tmp_path):
    """A typo in a selection is a configuration error, not a silent no-op."""
    write_skill(tmp_path, 'demo-skill')

    with pytest.raises(ValueError, match='Unknown skill in include'):
        SkillsCapability(tmp_path, include=['nope'])
```

Every test function needs a docstring — Ruff enforces `D103` on `tests/` as well as on the package.
Write the docstring to say *why* the behaviour matters, not to restate the assertion.

### Testing against a model

Use `FunctionModel` to script exact tool calls. `TestModel` does not work with deferred
capabilities: it calls every tool with synthesized arguments, including `load_capability` with an id
that does not exist, which exhausts the retry budget. See `tests/test_capability.py` for worked
examples.

### The harness compatibility guard

`tests/test_harness_compat.py` pins the `pydantic-ai-harness` behaviour this package depends on —
that `Skills.apply()` yields `Capability` leaves, that a leaf's id is its directory name, that
instructions come back as plain strings, and that bundled files are *not* loaded. harness is on 0.x
and documents that its API may change between minor releases, so keep this file in sync with what
`capability.py` actually relies on. The same applies to `tests/test_pydantic_ai_compat.py` for the
private pydantic-ai symbols.

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

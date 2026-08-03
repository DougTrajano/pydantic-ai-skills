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

## Quality Gates

A lot of the code here is written by agents. The gates below exist so that whoever — or whatever —
wrote a change, it arrives already linted, tested, type-checked and reviewed. They come in two
layers: the ones that run on your machine while the code is being written, and the ones that run on
GitHub once it is pushed.

### Local: pre-commit

`pre-commit run --all-files` runs everything CI's lint job runs:

| Hook | Catches |
| --- | --- |
| `ruff`, `ruff-format` | Lint and formatting |
| `mypy` | Type errors |
| `actionlint` | Broken workflow syntax and expressions |
| `zizmor` | Workflow security: script injection, over-broad permissions, credential persistence |
| `pre-commit-hooks` | Merge markers, private keys, AWS credentials, large files, debug statements |

`zizmor` is configured by [`.github/zizmor.yml`](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/.github/zizmor.yml)
and runs `--offline`, so no GitHub token is needed.

### Local: agent hooks

[`.claude/settings.json`](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/.claude/settings.json)
wires four [Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks). They apply to
agent sessions in this repository and need no setup:

| Hook | When | What it does |
| --- | --- | --- |
| `session_start.py` | Session start | Installs the dev extras so `pytest` and `mypy` actually run in a fresh container |
| `post_edit_lint.py` | After every `Write`/`Edit` | `ruff format` + `ruff check --fix` on the edited Python file; `actionlint` + `zizmor` on an edited workflow. Unresolved problems are reported back to the agent immediately |
| `bash_guard.py` | Before every `git` command | Refuses `--no-verify`, bare `--force` pushes, and pushes to `main` |
| `stop_test_gate.py` | Before the session ends | Runs the test suite if the session touched Python, and blocks on failure |

Each rule is pinned by [`tests/test_agent_hooks.py`](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/tests/test_agent_hooks.py) —
a guard that silently stops matching is worse than no guard.

There is also a `pre-push-review` skill: a local review of the branch against the same rubric CI
uses. Run it before pushing.

### GitHub: required checks

The [CI workflow](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/.github/workflows/ci.yml)
runs on every pull request:

| Job | Gate |
| --- | --- |
| `Lint (pre-commit)` | Everything in the table above |
| `Test` | The suite on Python 3.10–3.14 × pydantic-ai-slim `1.105.0` / `2.0.0` / `latest`, with a coverage floor |
| `Docs (strict build)` | `mkdocs build --strict` — a broken link, a page missing from the nav, or a stale API reference fails |
| `Checks passed` | Aggregates the three above. **This is the one to mark as required** in branch protection; it stays accurate as jobs are added |

SonarCloud runs afterwards and reports its own quality gate.

### GitHub: AI review

Once CI passes, the [AI Review workflow](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/.github/workflows/ai-review.yml)
reviews the pull request against
[`.github/review-rubric.md`](https://github.com/dougtrajano/pydantic-ai-skills/blob/main/.github/review-rubric.md)
and posts inline comments plus a verdict.

Three properties are worth knowing:

- **It runs after CI, not on every push.** There is no point reviewing a diff that does not compile,
  and a review started on each push is cancelled by the next one.
- **The agent has no write access.** It reads the diff and writes a findings file; a separate
  deterministic script decides which lines are commentable, what the verdict is, and posts the
  review. A malformed or missing findings file means "no findings", never a failed job.
- **It is advisory.** `REQUEST_CHANGES` on a `critical` or `high` finding is a signal, not a merge
  block — the required checks are the gate. Findings are wrong sometimes; say so on the thread and
  move on.

To enable it, set either `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` as a repository secret.
Without one, the workflow records a neutral "AI Review skipped" check and does nothing else. It also
skips draft pull requests, fork branches, and commits it has already reviewed.

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

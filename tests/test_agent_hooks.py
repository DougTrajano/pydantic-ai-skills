"""Tests for the Claude Code hooks in `.claude/hooks/`.

The hooks decide what an agent is allowed to do in this repository. A guard that
silently stops matching is worse than no guard, so the rules are pinned here.
"""

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

HOOKS_DIR = Path(__file__).parent.parent / '.claude' / 'hooks'


def _load(name: str) -> ModuleType:
    """Import a hook module by path — `.claude/hooks` is not an importable package."""
    spec = importlib.util.spec_from_file_location(f'claude_hooks_{name}', HOOKS_DIR / f'{name}.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bash_guard = _load('bash_guard')
stop_test_gate = _load('stop_test_gate')
post_edit_lint = _load('post_edit_lint')


@pytest.mark.parametrize(
    'command',
    [
        'git commit --no-verify -m "wip"',
        'git commit -n -m "wip"',
        'git push --no-verify origin feature',
        'cd /repo && git commit --no-verify -m x',
    ],
)
def test_blocks_bypassing_pre_commit(command: str) -> None:
    """Skipping the hooks skips ruff, ruff-format and mypy — the same tools CI runs."""
    assert bash_guard.check(command) is not None


@pytest.mark.parametrize(
    'command',
    [
        'git push --force origin feature',
        'git push -f origin feature',
    ],
)
def test_blocks_bare_force_push(command: str) -> None:
    """A bare force push can discard commits that are not in the local history."""
    assert bash_guard.check(command) is not None


@pytest.mark.parametrize(
    'command',
    [
        'git push origin main',
        'git push --force-with-lease origin main',
        'git push origin main:main',
    ],
)
def test_blocks_pushing_to_main(command: str) -> None:
    """Pushing to the protected branch skips CI, review and branch protection."""
    assert bash_guard.check(command) is not None


@pytest.mark.parametrize(
    'command',
    [
        'git push -u origin feature/thing',
        'git push --force-with-lease origin feature/thing',
        'git commit -m "real commit"',
        'git log --oneline -n 5',
        'git push -n origin feature',  # -n is --dry-run for push, not --no-verify
        'git status --short',
        'python -m pytest -q',
    ],
)
def test_allows_ordinary_commands(command: str) -> None:
    """Everything that does not route around a gate is left alone."""
    assert bash_guard.check(command) is None


@pytest.mark.parametrize(
    'paths,expected',
    [
        ([Path('pydantic_ai_skills/toolset.py')], 1),
        ([Path('tests/test_toolset.py')], 1),
        ([Path('docs/index.md'), Path('README.md')], 0),
        ([Path('examples/demo.py')], 0),
        ([Path('pydantic_ai_skills/py.typed')], 0),
        ([Path('pydantic_ai_skills/toolset.py'), Path('docs/index.md')], 1),
    ],
)
def test_stop_gate_watches_package_and_tests(paths: list[Path], expected: int) -> None:
    """The suite only runs when the session touched code the suite covers."""
    assert len(stop_test_gate.touched_python(paths)) == expected


def test_stop_gate_tail_keeps_the_end_of_the_output() -> None:
    """Pytest puts the failure summary last, so the tail is the useful part."""
    text = '\n'.join(str(i) for i in range(100))

    assert stop_test_gate.tail(text, lines=3) == '97\n98\n99'


class _Result:
    """Stand-in for a CompletedProcess."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = 'linter output'
        self.stderr = ''


def _recorder(commands: list[list[str]], returncode: int = 0) -> Callable[..., _Result]:
    """Return a stand-in for `run` that records the command instead of executing it."""

    def record(cmd: list[str], **_kwargs: object) -> _Result:
        commands.append(cmd)
        return _Result(returncode)

    return record


def test_workflow_lint_falls_back_to_pre_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither linter is a project dependency, so the usual path is pre-commit's pinned copy."""
    commands: list[list[str]] = []
    monkeypatch.setattr(post_edit_lint, 'have', lambda tool: tool == 'pre-commit')
    monkeypatch.setattr(post_edit_lint, 'run', _recorder(commands))

    assert post_edit_lint.lint_workflow(Path('.github/workflows/ci.yml')) == []
    assert [cmd[:3] for cmd in commands] == [
        ['pre-commit', 'run', 'actionlint'],
        ['pre-commit', 'run', 'zizmor'],
    ]


def test_workflow_lint_prefers_a_binary_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the tool is installed, call it directly rather than paying pre-commit's overhead."""
    commands: list[list[str]] = []
    monkeypatch.setattr(post_edit_lint, 'have', lambda tool: True)
    monkeypatch.setattr(post_edit_lint, 'run', _recorder(commands))

    post_edit_lint.lint_workflow(Path('.github/workflows/ci.yml'))

    assert commands[0] == ['actionlint', '.github/workflows/ci.yml']
    assert commands[1][0] == 'zizmor'
    assert '--offline' in commands[1]


def test_workflow_lint_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero exit becomes a problem the agent is shown."""
    monkeypatch.setattr(post_edit_lint, 'have', lambda tool: tool == 'actionlint')
    monkeypatch.setattr(post_edit_lint, 'run', _recorder([], returncode=1))

    assert post_edit_lint.lint_workflow(Path('.github/workflows/ci.yml')) == ['linter output']

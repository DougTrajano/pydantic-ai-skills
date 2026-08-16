"""Tests for the SkillScriptExecutor protocol and the sandbox executor examples."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from pydantic_ai_skills import (
    CallableSkillScriptExecutor,
    LocalSkillScriptExecutor,
    SkillScript,
    SkillScriptExecutor,
    SkillsDirectory,
    SkillsToolset,
)

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class DuckTypedExecutor:
    """A custom executor that never inherits from the protocol."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> Any:
        self.calls.append((script.name, args))
        return f'duck ran {script.name}'


class NotAnExecutor:
    """Has no run method, so it must not satisfy the protocol."""


def test_builtin_executors_satisfy_protocol() -> None:
    """Both shipped executors are instances of the protocol."""
    assert isinstance(LocalSkillScriptExecutor(), SkillScriptExecutor)
    assert isinstance(CallableSkillScriptExecutor(func=lambda script, args=None: ''), SkillScriptExecutor)


def test_builtin_executors_are_nominal_subclasses() -> None:
    """The shipped executors declare the protocol explicitly, not just structurally."""
    assert issubclass(LocalSkillScriptExecutor, SkillScriptExecutor)
    assert issubclass(CallableSkillScriptExecutor, SkillScriptExecutor)


def test_duck_typed_executor_satisfies_protocol() -> None:
    """A third-party executor conforms without importing or subclassing anything."""
    assert isinstance(DuckTypedExecutor(), SkillScriptExecutor)


def test_object_without_run_does_not_satisfy_protocol() -> None:
    """Objects lacking run are rejected by the protocol."""
    assert not isinstance(NotAnExecutor(), SkillScriptExecutor)


# ---------------------------------------------------------------------------
# Backwards compatibility: duck-typed executors still work end to end
# ---------------------------------------------------------------------------


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a minimal skill with one script."""
    skill = tmp_path / 'demo-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'SKILL.md').write_text(
        '---\nname: demo-skill\ndescription: Demo skill for executor tests.\n---\n\nDemo body.\n'
    )
    (skill / 'scripts' / 'run.py').write_text('#!/usr/bin/env python3\nprint("hi")\n')
    return tmp_path


async def test_duck_typed_executor_runs_through_toolset(skill_dir: Path) -> None:
    """A duck-typed executor reaches run_skill_script unchanged."""
    executor = DuckTypedExecutor()
    toolset = SkillsToolset(directories=[SkillsDirectory(path=skill_dir, script_executor=executor)])

    skill = toolset.skills['demo-skill']
    script = next(s for s in skill.scripts if s.name == 'scripts/run.py')

    ctx = SimpleNamespace(deps=None)
    result = await script.run(ctx=ctx, args={'query': 'x'})

    assert result == 'duck ran scripts/run.py'
    assert executor.calls == [('scripts/run.py', {'query': 'x'})]


# ---------------------------------------------------------------------------
# Sandbox executor examples
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).parent.parent / 'examples'


def _load_example(module_name: str) -> Any:
    """Load an example module by path.

    Loading by path rather than importing ``examples.<name>`` keeps the example
    modules out of the package namespace, which would otherwise make the same
    file resolvable under two module names.
    """
    spec = importlib.util.spec_from_file_location(f'_example_{module_name}', EXAMPLES_DIR / f'{module_name}.py')
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def opensandbox_example() -> Any:
    """The OpenSandbox executor example module."""
    return _load_example('sandbox_opensandbox')


@pytest.fixture
def localsandbox_example() -> Any:
    """The LocalSandbox executor example module."""
    return _load_example('sandbox_localsandbox')


def test_sandbox_examples_satisfy_protocol(opensandbox_example: Any, localsandbox_example: Any) -> None:
    """Both sandbox examples implement the executor protocol."""
    assert isinstance(opensandbox_example.OpenSandboxScriptExecutor(), SkillScriptExecutor)
    assert isinstance(localsandbox_example.LocalSandboxScriptExecutor(), SkillScriptExecutor)


def test_opensandbox_example_reports_missing_extra(opensandbox_example: Any) -> None:
    """Without the SDK installed, the error names the extra that provides it."""
    with patch.dict('sys.modules', {'opensandbox': None}):
        with pytest.raises(ImportError, match=r'pydantic-ai-skills\[opensandbox\]'):
            opensandbox_example._require_opensandbox()


def test_localsandbox_example_reports_missing_extra(localsandbox_example: Any) -> None:
    """Without the SDK installed, the error names the extra that provides it."""
    with patch.dict('sys.modules', {'localsandbox': None}):
        with pytest.raises(ImportError, match=r'pydantic-ai-skills\[localsandbox\]'):
            localsandbox_example._require_localsandbox()


@pytest.fixture
def staged_skill(tmp_path: Path) -> Path:
    """A skill folder with a nested script, a top-level resource, and a symlink escape."""
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('host secret')

    skill = tmp_path / 'demo-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'resources').mkdir()
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'resources' / 'data.json').write_text('{"k": 1}')
    (skill / 'scripts' / 'run.py').write_text('print("hi")\n')
    (skill / 'scripts' / 'escape.txt').symlink_to(outside / 'secret.txt')
    return skill


@pytest.mark.parametrize('module_name', ['sandbox_opensandbox', 'sandbox_localsandbox'])
def test_staging_uses_skill_root_not_script_parent(module_name: str, staged_skill: Path) -> None:
    """script.name is relative to the skill folder, so the root is above scripts/."""
    example = _load_example(module_name)
    script = SkillScript(name='scripts/run.py', uri=str(staged_skill / 'scripts' / 'run.py'))

    assert example.skill_root_for(script) == staged_skill.resolve()


def _collect_staged(example: Any, skill_root: Path) -> dict[str, Path]:
    """Drain the staging generator into a mapping of relative path to source file."""
    return dict(example.iter_stageable_files(skill_root))


@pytest.mark.parametrize('module_name', ['sandbox_opensandbox', 'sandbox_localsandbox'])
@pytest.mark.filterwarnings('ignore:Skipping.*symlink escape:UserWarning')
def test_staging_includes_whole_skill_folder(module_name: str, staged_skill: Path) -> None:
    """SKILL.md and resources/ are staged, not just the script's own directory."""
    example = _load_example(module_name)

    staged = _collect_staged(example, staged_skill.resolve())

    assert 'SKILL.md' in staged
    assert 'resources/data.json' in staged
    assert 'scripts/run.py' in staged


@pytest.mark.parametrize('module_name', ['sandbox_opensandbox', 'sandbox_localsandbox'])
@pytest.mark.filterwarnings('ignore:Skipping.*symlink escape:UserWarning')
def test_staging_skips_symlinks_escaping_the_skill_folder(module_name: str, staged_skill: Path) -> None:
    """Following an escaping symlink would copy a host file into the sandbox."""
    example = _load_example(module_name)

    staged = _collect_staged(example, staged_skill.resolve())

    assert 'scripts/escape.txt' not in staged
    assert not any('secret' in path.name for path in staged.values())


@pytest.mark.parametrize('module_name', ['sandbox_opensandbox', 'sandbox_localsandbox'])
def test_staging_warns_about_symlink_escape(module_name: str, staged_skill: Path) -> None:
    """The skipped symlink is reported rather than silently dropped."""
    example = _load_example(module_name)
    skill_root = staged_skill.resolve()

    with pytest.warns(UserWarning, match='symlink escape'):
        _collect_staged(example, skill_root)


def _script_without_uri() -> SkillScript:
    """Build a script whose uri is None."""
    # __post_init__ requires a uri or a function, so clear it afterwards.
    script = SkillScript(name='no-uri', uri='placeholder')
    script.uri = None
    return script


async def test_localsandbox_example_rejects_unsupported_script_type(localsandbox_example: Any, tmp_path: Path) -> None:
    """LocalSandbox supports .py and shell scripts only, and says so before provisioning."""
    script_file = tmp_path / 'thing.rb'
    script_file.write_text('puts "hi"\n')
    script = SkillScript(name='thing.rb', uri=str(script_file))
    executor = localsandbox_example.LocalSandboxScriptExecutor()

    with pytest.raises(ValueError, match='unsupported type'):
        await executor.run(script)


async def test_localsandbox_example_requires_a_uri(localsandbox_example: Any) -> None:
    """The LocalSandbox executor rejects scripts with no URI."""
    script = _script_without_uri()
    executor = localsandbox_example.LocalSandboxScriptExecutor()

    with pytest.raises(ValueError, match='has no URI'):
        await executor.run(script)


async def test_opensandbox_example_requires_a_uri(opensandbox_example: Any) -> None:
    """The OpenSandbox executor rejects scripts with no URI."""
    script = _script_without_uri()
    executor = opensandbox_example.OpenSandboxScriptExecutor()

    with pytest.raises(ValueError, match='has no URI'):
        await executor.run(script)

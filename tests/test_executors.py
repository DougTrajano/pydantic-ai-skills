"""Tests for the SkillScriptExecutor protocol.

The sandbox executors live inside ``examples/sandbox_*.py``, which build an
``Agent`` at import time and so cannot be imported here. They are exercised the
same way every other example is: by running them.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


async def test_custom_executor_receives_skill_relative_script_name(skill_dir: Path) -> None:
    """script.name stays relative to the skill folder, which the sandbox executors rely on.

    They derive the skill root by walking up that many levels from ``script.uri``;
    if this contract changed they would stage the wrong directory.
    """
    executor = DuckTypedExecutor()
    toolset = SkillsToolset(directories=[SkillsDirectory(path=skill_dir, script_executor=executor)])

    script = next(s for s in toolset.skills['demo-skill'].scripts if s.name.endswith('run.py'))

    assert script.name == 'scripts/run.py'
    assert Path(str(script.uri)).parent.name == 'scripts'

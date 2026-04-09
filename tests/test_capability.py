"""Tests for SkillsCapability."""

from __future__ import annotations

import importlib.util
from types import SimpleNamespace

import pytest

import pydantic_ai_skills.capability as capability_module
from pydantic_ai_skills import SkillsCapability, SkillsToolset


def _capabilities_available() -> bool:
    return importlib.util.find_spec('pydantic_ai.capabilities') is not None


def test_skills_capability_legacy_runtime_error() -> None:
    """Legacy pydantic-ai versions should fail with a clear message."""
    if _capabilities_available():
        pytest.skip('Capabilities API is available in this environment')

    with pytest.raises(RuntimeError, match='pydantic-ai>=1.71'):
        SkillsCapability(skills=[], directories=[])


def test_skills_capability_get_toolset_when_available() -> None:
    """Capabilities-enabled versions should return a SkillsToolset."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(skills=[], directories=[])
    toolset = capability.get_toolset()

    assert isinstance(toolset, SkillsToolset)
    assert capability.toolset is toolset


def test_skills_capability_runtime_error_when_flag_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Constructor should fail with a clear error when capability support is disabled."""
    monkeypatch.setattr(capability_module, '_CAPABILITIES_AVAILABLE', False)

    with pytest.raises(RuntimeError, match='pydantic-ai>=1.71'):
        capability_module.SkillsCapability(skills=[], directories=[])


@pytest.mark.asyncio
async def test_skills_capability_get_instructions_delegates_to_toolset() -> None:
    """get_instructions should delegate to the wrapped SkillsToolset method."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(skills=[], directories=[])

    async def _fake_get_instructions(ctx: object) -> str:
        assert ctx is fake_ctx
        return 'delegated-instructions'

    fake_ctx = SimpleNamespace(deps=None)
    capability.toolset.get_instructions = _fake_get_instructions  # type: ignore[method-assign]

    instructions_provider = capability.get_instructions()
    assert callable(instructions_provider)
    assert await instructions_provider(fake_ctx) == 'delegated-instructions'


def test_skills_capability_init_with_minimal_params() -> None:
    """Constructor should work with only skills parameter."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(skills=[])
    assert isinstance(capability.get_toolset(), SkillsToolset)


def test_skills_capability_init_with_directories() -> None:
    """Constructor should accept directories parameter."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(directories=['./skills'])
    assert isinstance(capability.get_toolset(), SkillsToolset)


def test_skills_capability_init_with_all_params(tmp_path: object) -> None:
    """Constructor should accept all parameters."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(
        skills=[],
        directories=['./skills'],
        registries=[],
        validate=False,
        max_depth=5,
        id='test-toolset',
        instruction_template='Available skills: {skills_list}',
        exclude_tools={'run_skill_script'},
        auto_reload=True,
    )
    assert isinstance(capability.get_toolset(), SkillsToolset)
    toolset = capability.toolset
    assert toolset.id == 'test-toolset'


def test_skills_capability_toolset_property_is_same_as_get_toolset() -> None:
    """Toolset property should be the same instance as get_toolset()."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(skills=[])
    toolset_property = capability.toolset
    get_toolset_result = capability.get_toolset()
    assert toolset_property is get_toolset_result


@pytest.mark.asyncio
async def test_skills_capability_get_instructions_returns_callable() -> None:
    """get_instructions should always return a callable."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(skills=[])
    instructions_func = capability.get_instructions()
    assert callable(instructions_func)


@pytest.mark.asyncio
async def test_skills_capability_get_instructions_with_none_return() -> None:
    """get_instructions should handle None return from toolset."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(skills=[])

    async def _fake_get_instructions(ctx: object) -> None:
        return None

    fake_ctx = SimpleNamespace(deps=None)
    capability.toolset.get_instructions = _fake_get_instructions  # type: ignore[method-assign]

    instructions_provider = capability.get_instructions()
    result = await instructions_provider(fake_ctx)
    assert result is None


def test_skills_capability_with_exclude_tools_as_list() -> None:
    """Constructor should accept exclude_tools as a list."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    capability = SkillsCapability(
        skills=[],
        exclude_tools=['load_skill', 'run_skill_script'],
    )
    assert isinstance(capability.get_toolset(), SkillsToolset)


def test_skills_capability_init_with_custom_template() -> None:
    """Constructor should accept custom instruction template."""
    if not _capabilities_available():
        pytest.skip('Capabilities API is not available in this environment')

    template = 'Use these skills: {skills_list}'
    capability = SkillsCapability(
        skills=[],
        instruction_template=template,
    )
    assert isinstance(capability.get_toolset(), SkillsToolset)

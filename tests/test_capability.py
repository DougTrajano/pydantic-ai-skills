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

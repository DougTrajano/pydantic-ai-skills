"""Tests for SkillsCapability."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from pydantic_ai_skills import SkillsCapability, SkillsToolset


def test_skills_capability_get_toolset() -> None:
    """SkillsCapability should expose a SkillsToolset."""
    capability = SkillsCapability(skills=[], directories=[])
    toolset = capability.get_toolset()

    assert isinstance(toolset, SkillsToolset)
    assert capability.toolset is toolset


def test_skills_capability_init_with_minimal_params() -> None:
    """Constructor should work with only skills parameter."""
    capability = SkillsCapability(skills=[])
    assert isinstance(capability.get_toolset(), SkillsToolset)


def test_skills_capability_init_with_directories() -> None:
    """Constructor should accept directories parameter."""
    capability = SkillsCapability(directories=['./skills'])
    assert isinstance(capability.get_toolset(), SkillsToolset)


def test_skills_capability_init_with_all_params(tmp_path: Path) -> None:
    """Constructor should accept all parameters."""
    skills_dir = tmp_path / 'skills'
    skills_dir.mkdir()

    capability = SkillsCapability(
        skills=[],
        directories=[skills_dir],
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
    capability = SkillsCapability(skills=[])
    toolset_property = capability.toolset
    get_toolset_result = capability.get_toolset()
    assert toolset_property is get_toolset_result


def test_skills_capability_with_exclude_tools_as_list() -> None:
    """Constructor should accept exclude_tools as a list."""
    capability = SkillsCapability(
        skills=[],
        exclude_tools=['load_skill', 'run_skill_script'],
    )
    assert isinstance(capability.get_toolset(), SkillsToolset)


def test_skills_capability_init_with_custom_template() -> None:
    """Constructor should accept custom instruction template."""
    template = 'Use these skills: {skills_list}'
    capability = SkillsCapability(
        skills=[],
        instruction_template=template,
    )
    assert isinstance(capability.get_toolset(), SkillsToolset)


@pytest.mark.asyncio
async def test_skills_capability_get_instructions_returns_none() -> None:
    """get_instructions returns None — agent extracts instructions natively from the toolset."""
    capability = SkillsCapability(skills=[])
    assert capability.get_instructions() is None


def test_skills_capability_defaults_not_deferred() -> None:
    """By default the capability is not deferred and has no id/description."""
    capability = SkillsCapability(skills=[])
    assert capability.defer_loading is False
    assert capability.id is None
    assert capability.description is None


def test_skills_capability_defer_loading_sets_attributes() -> None:
    """defer_loading should set the capability id/description/defer_loading attributes."""
    capability = SkillsCapability(skills=[], id='skills', defer_loading=True)
    assert capability.defer_loading is True
    assert capability.id == 'skills'


def test_skills_capability_defer_loading_requires_id() -> None:
    """defer_loading without an id should raise a clear error."""
    with pytest.raises(ValueError, match="requires a stable 'id'"):
        SkillsCapability(skills=[], defer_loading=True)


def _write_skill(directory: Path, name: str) -> None:
    skill_dir = directory / name
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {name}\ndescription: The {name} skill.\n---\n# {name}\nBody.\n',
        encoding='utf-8',
    )


def test_skills_capability_get_description_summarizes_skills(tmp_path: Path) -> None:
    """get_description should summarize the available skill names when none is given."""
    _write_skill(tmp_path, 'alpha')
    _write_skill(tmp_path, 'beta')

    capability = SkillsCapability(id='skills', directories=[tmp_path], defer_loading=True)
    assert capability.get_description() == 'Provides specialized skills: alpha, beta.'


def test_skills_capability_get_description_prefers_explicit(tmp_path: Path) -> None:
    """An explicit description should override the generated summary."""
    _write_skill(tmp_path, 'alpha')

    capability = SkillsCapability(
        id='skills', directories=[tmp_path], defer_loading=True, description='Custom catalog text.'
    )
    assert capability.get_description() == 'Custom catalog text.'


def test_skills_capability_get_description_none_when_no_skills() -> None:
    """get_description should return None when there are no skills and no description."""
    capability = SkillsCapability(skills=[])
    assert capability.get_description() is None


# --- Agent spec support ---


def test_skills_capability_is_dataclass() -> None:
    """SkillsCapability must be a dataclass so it can register as a custom capability type."""
    assert dataclasses.is_dataclass(SkillsCapability)


def test_skills_capability_rejects_positional_args() -> None:
    """All constructor arguments are keyword-only."""
    with pytest.raises(TypeError):
        SkillsCapability([], [])  # type: ignore[misc]


def test_skills_capability_serialization_name() -> None:
    """The serialization name is the stable spec key."""
    assert SkillsCapability.get_serialization_name() == 'SkillsCapability'


def test_skills_capability_registers_in_capability_registry() -> None:
    """The class must be accepted by the pydantic-ai capability registry builder."""
    from pydantic_ai.agent.spec import get_capability_registry

    registry = get_capability_registry([SkillsCapability])
    assert registry.get('SkillsCapability') is SkillsCapability


def test_skills_capability_from_spec_builds_toolset(tmp_path: Path) -> None:
    """from_spec should construct a working capability from serializable arguments."""
    _write_skill(tmp_path, 'alpha')

    capability = SkillsCapability.from_spec(
        directories=[str(tmp_path)],
        id='skills',
        defer_loading=True,
        description='Catalog text.',
    )
    assert isinstance(capability.get_toolset(), SkillsToolset)
    assert capability.id == 'skills'
    assert capability.defer_loading is True
    assert capability.get_description() == 'Catalog text.'


def test_skills_capability_from_spec_defer_loading_requires_id() -> None:
    """from_spec should enforce the same defer_loading/id invariant as the constructor."""
    with pytest.raises(ValueError, match="requires a stable 'id'"):
        SkillsCapability.from_spec(directories=['./skills'], defer_loading=True)


def test_skills_capability_loaded_from_agent_spec(tmp_path: Path) -> None:
    """An agent built from a dict spec should expose the skills toolset."""
    from pydantic_ai import Agent

    _write_skill(tmp_path, 'alpha')

    spec = {
        'model': 'test',
        'capabilities': [
            {'SkillsCapability': {'directories': [str(tmp_path)], 'id': 'skills', 'defer_loading': True}},
        ],
    }
    agent = Agent.from_spec(spec, custom_capability_types=[SkillsCapability])

    leaves: list[object] = []
    agent._root_capability.apply(leaves.append)
    skills_caps = [c for c in leaves if isinstance(c, SkillsCapability)]
    assert len(skills_caps) == 1
    assert skills_caps[0].id == 'skills'
    assert isinstance(skills_caps[0].get_toolset(), SkillsToolset)


def test_skills_capability_spec_schema_generation() -> None:
    """JSON schema generation including SkillsCapability should succeed."""
    from pydantic_ai.agent.spec import AgentSpec

    schema = AgentSpec.model_json_schema_with_capabilities([SkillsCapability])
    assert 'SkillsCapability' in str(schema)

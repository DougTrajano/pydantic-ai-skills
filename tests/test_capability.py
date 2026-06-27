"""Tests for SkillsCapability."""

from __future__ import annotations

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

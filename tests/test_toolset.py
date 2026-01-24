"""Tests for SkillsToolset."""

from pathlib import Path

import pytest

from pydantic_ai_skills import SkillsToolset
from pydantic_ai_skills.exceptions import SkillNotFoundError


@pytest.fixture
def sample_skills_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample skills."""
    # Create skill 1
    skill1_dir = tmp_path / 'skill-one'
    skill1_dir.mkdir()
    (skill1_dir / 'SKILL.md').write_text("""---
name: skill-one
description: First test skill for basic operations
---

# Skill One

Use this skill for basic operations.

## Instructions

1. Do something simple
2. Return results
""")

    # Create skill 2 with resources
    skill2_dir = tmp_path / 'skill-two'
    skill2_dir.mkdir()
    (skill2_dir / 'SKILL.md').write_text("""---
name: skill-two
description: Second test skill with resources
---

# Skill Two

Advanced skill with resources.

See FORMS.md for details.
""")
    (skill2_dir / 'FORMS.md').write_text('# Forms\n\nForm filling guide.')
    (skill2_dir / 'REFERENCE.md').write_text('# API Reference\n\nDetailed reference.')

    # Create skill 3 with scripts
    skill3_dir = tmp_path / 'skill-three'
    skill3_dir.mkdir()
    (skill3_dir / 'SKILL.md').write_text("""---
name: skill-three
description: Third test skill with executable scripts
---

# Skill Three

Skill with executable scripts.
""")

    scripts_dir = skill3_dir / 'scripts'
    scripts_dir.mkdir()
    (scripts_dir / 'hello.py').write_text("""#!/usr/bin/env python3
import sys
print(f"Hello, {sys.argv[1] if len(sys.argv) > 1 else 'World'}!")
""")
    (scripts_dir / 'echo.py').write_text("""#!/usr/bin/env python3
import sys
print(' '.join(sys.argv[1:]))
""")

    return tmp_path


def test_toolset_initialization(sample_skills_dir: Path) -> None:
    """Test SkillsToolset initialization."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    assert len(toolset.skills) == 3
    assert 'skill-one' in toolset.skills
    assert 'skill-two' in toolset.skills
    assert 'skill-three' in toolset.skills


def test_toolset_get_skill(sample_skills_dir: Path) -> None:
    """Test getting a specific skill."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    skill = toolset.get_skill('skill-one')
    assert skill.name == 'skill-one'
    assert skill.description == 'First test skill for basic operations'


def test_toolset_get_skill_not_found(sample_skills_dir: Path) -> None:
    """Test getting a non-existent skill."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    with pytest.raises(SkillNotFoundError, match="Skill 'nonexistent' not found"):
        toolset.get_skill('nonexistent')


@pytest.mark.asyncio
async def test_list_skills_tool(sample_skills_dir: Path) -> None:
    """Test the list_skills tool by checking skills were loaded."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    # Verify all three skills were discovered
    assert len(toolset.skills) == 3
    assert 'skill-one' in toolset.skills
    assert 'skill-two' in toolset.skills
    assert 'skill-three' in toolset.skills

    # Verify descriptions
    assert toolset.skills['skill-one'].description == 'First test skill for basic operations'
    assert toolset.skills['skill-two'].description == 'Second test skill with resources'
    assert toolset.skills['skill-three'].description == 'Third test skill with executable scripts'


@pytest.mark.asyncio
async def test_load_skill_tool(sample_skills_dir: Path) -> None:
    """Test the load_skill tool."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    # The tools are internal, so we test via the public methods
    # We can check that the skills were loaded correctly
    skill = toolset.get_skill('skill-one')
    assert skill is not None
    assert skill.name == 'skill-one'
    assert 'First test skill for basic operations' in skill.description
    assert 'Use this skill for basic operations' in skill.content


@pytest.mark.asyncio
async def test_load_skill_not_found(sample_skills_dir: Path) -> None:
    """Test loading a non-existent skill."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    # Test that nonexistent skill raises an error
    with pytest.raises(SkillNotFoundError):
        toolset.get_skill('nonexistent-skill')


@pytest.mark.asyncio
async def test_read_skill_resource_tool(sample_skills_dir: Path) -> None:
    """Test the read_skill_resource tool."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    # Test that skill-two has the expected resources
    skill = toolset.get_skill('skill-two')
    assert skill.resources is not None
    assert len(skill.resources) == 2

    resource_names = [r.name for r in skill.resources]
    assert 'FORMS.md' in resource_names
    assert 'REFERENCE.md' in resource_names

    # Check that resources can be read
    for resource in skill.resources:
        resource_path = Path(resource.uri)
        assert resource_path.exists()
        assert resource_path.is_file()


@pytest.mark.asyncio
async def test_read_skill_resource_not_found(sample_skills_dir: Path) -> None:
    """Test reading a non-existent resource."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    # Test skill with no resources
    skill_one = toolset.get_skill('skill-one')
    assert skill_one.resources is None or len(skill_one.resources) == 0

    # Test skill with resources
    skill_two = toolset.get_skill('skill-two')
    assert skill_two.resources is not None
    resource_names = [r.name for r in skill_two.resources]
    assert 'NONEXISTENT.md' not in resource_names


@pytest.mark.asyncio
async def test_run_skill_script_tool(sample_skills_dir: Path) -> None:
    """Test the run_skill_script tool."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    # Test that skill-three has scripts
    skill = toolset.get_skill('skill-three')
    assert skill.scripts is not None
    assert len(skill.scripts) == 2

    script_names = [s.name for s in skill.scripts]
    # Scripts are now stored with relative paths
    assert 'scripts/hello.py' in script_names
    assert 'scripts/echo.py' in script_names

    # Check that scripts can be found
    for script in skill.scripts:
        script_path = Path(script.uri)
        assert script_path.exists()
        assert script_path.is_file()
        assert script_path.suffix == '.py'


@pytest.mark.asyncio
async def test_run_skill_script_not_found(sample_skills_dir: Path) -> None:
    """Test running a non-existent script."""
    toolset = SkillsToolset(directories=[sample_skills_dir])

    # Test skill with no scripts
    skill_one = toolset.get_skill('skill-one')
    assert skill_one.scripts is None or len(skill_one.scripts) == 0

    # Test skill with scripts
    skill_three = toolset.get_skill('skill-three')
    assert skill_three.scripts is not None
    script_names = [s.name for s in skill_three.scripts]
    assert 'nonexistent' not in script_names


@pytest.mark.asyncio
async def test_get_instructions(sample_skills_dir: Path) -> None:
    """Test generating the system prompt via get_instructions."""
    from unittest.mock import Mock

    toolset = SkillsToolset(directories=[sample_skills_dir])

    # Create a mock context (get_instructions doesn't use ctx, but requires it)
    mock_ctx = Mock()

    prompt = await toolset.get_instructions(mock_ctx)
    assert prompt is not None

    # Should include all skill names and descriptions
    assert 'skill-one' in prompt
    assert 'skill-two' in prompt
    assert 'skill-three' in prompt
    assert 'First test skill for basic operations' in prompt
    assert 'Second test skill with resources' in prompt
    assert 'Third test skill with executable scripts' in prompt

    # Should include usage instructions
    assert 'load_skill' in prompt
    # read_skill_resource and run_skill_script are mentioned in load_skill context, not in overview
    assert 'Use any additional skill resources and scripts as needed' in prompt


@pytest.mark.asyncio
async def test_get_instructions_empty() -> None:
    """Test system prompt with no skills."""
    from unittest.mock import Mock

    toolset = SkillsToolset(skills=[], directories=[])

    mock_ctx = Mock()
    prompt = await toolset.get_instructions(mock_ctx)
    assert prompt is None


# Tests for exclude_tools feature


def test_exclude_tools_single_string_set(sample_skills_dir: Path) -> None:
    """Test that tools are correctly excluded when specified as a set."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools={'run_skill_script'},
    )

    # Verify skills are still loaded
    assert len(toolset.skills) == 3

    # Check that run_skill_script is not registered
    # We can verify this by checking internal tool registration
    tool_names = set(toolset.tools.keys())
    assert 'list_skills' in tool_names
    assert 'load_skill' in tool_names
    assert 'read_skill_resource' in tool_names
    assert 'run_skill_script' not in tool_names


def test_exclude_tools_multiple_tools(sample_skills_dir: Path) -> None:
    """Test excluding multiple tools."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools={'run_skill_script', 'read_skill_resource'},
    )

    # Verify skills are still loaded
    assert len(toolset.skills) == 3

    # Check that specified tools are not registered
    tool_names = set(toolset.tools.keys())
    assert 'list_skills' in tool_names
    assert 'load_skill' in tool_names
    assert 'read_skill_resource' not in tool_names
    assert 'run_skill_script' not in tool_names


def test_exclude_tools_as_list(sample_skills_dir: Path) -> None:
    """Test that exclude_tools accepts lists in addition to sets."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools=['list_skills', 'load_skill'],
    )

    # Check that specified tools are not registered
    tool_names = set(toolset.tools.keys())
    assert 'list_skills' not in tool_names
    assert 'load_skill' not in tool_names
    assert 'read_skill_resource' in tool_names
    assert 'run_skill_script' in tool_names


def test_exclude_tools_invalid_tool_name(sample_skills_dir: Path) -> None:
    """Test that invalid tool names raise ValueError."""
    with pytest.raises(ValueError, match='Unknown tools.*invalid_tool'):
        SkillsToolset(
            directories=[sample_skills_dir],
            exclude_tools={'invalid_tool'},
        )


def test_exclude_tools_multiple_invalid_names(sample_skills_dir: Path) -> None:
    """Test ValueError with multiple invalid tool names."""
    with pytest.raises(ValueError, match='Unknown tools'):
        SkillsToolset(
            directories=[sample_skills_dir],
            exclude_tools={'fake_tool', 'another_fake', 'run_skill_script'},
        )


def test_exclude_tools_load_skill_warning(sample_skills_dir: Path) -> None:
    """Test that a warning is emitted when load_skill is excluded."""
    import warnings

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter('always')
        SkillsToolset(
            directories=[sample_skills_dir],
            exclude_tools={'load_skill'},
        )

        # Find the warning about load_skill being excluded
        load_skill_warnings = [w for w in warning_list if "'load_skill' is a critical tool" in str(w.message)]
        assert len(load_skill_warnings) == 1
        assert issubclass(load_skill_warnings[0].category, UserWarning)


def test_exclude_tools_no_warning_for_other_tools(sample_skills_dir: Path) -> None:
    """Test that no warning is emitted when other tools are excluded."""
    import warnings

    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter('always')
        SkillsToolset(
            directories=[sample_skills_dir],
            exclude_tools={'run_skill_script'},
        )

        # Filter out the default skills directory warning if it exists
        relevant_warnings = [
            w for w in warning_list if 'critical tool' in str(w.message) or 'load_skill' in str(w.message)
        ]
        assert len(relevant_warnings) == 0


def test_exclude_tools_empty_set(sample_skills_dir: Path) -> None:
    """Test that an empty exclude_tools set registers all tools."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools=set(),
    )

    # All tools should be registered
    tool_names = set(toolset.tools.keys())
    assert 'list_skills' in tool_names
    assert 'load_skill' in tool_names
    assert 'read_skill_resource' in tool_names
    assert 'run_skill_script' in tool_names


def test_exclude_tools_empty_list(sample_skills_dir: Path) -> None:
    """Test that an empty exclude_tools list registers all tools."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools=[],
    )

    # All tools should be registered
    tool_names = set(toolset.tools.keys())
    assert 'list_skills' in tool_names
    assert 'load_skill' in tool_names
    assert 'read_skill_resource' in tool_names
    assert 'run_skill_script' in tool_names


def test_exclude_tools_none(sample_skills_dir: Path) -> None:
    """Test that None (default) registers all tools."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools=None,
    )

    # All tools should be registered
    tool_names = set(toolset.tools.keys())
    assert 'list_skills' in tool_names
    assert 'load_skill' in tool_names
    assert 'read_skill_resource' in tool_names
    assert 'run_skill_script' in tool_names


def test_exclude_tools_exclude_all(sample_skills_dir: Path) -> None:
    """Test excluding all tools."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools={'list_skills', 'load_skill', 'read_skill_resource', 'run_skill_script'},
    )

    # No tools should be registered
    tool_names = set(toolset.tools.keys())
    assert len(tool_names) == 0
    assert 'list_skills' not in tool_names
    assert 'load_skill' not in tool_names
    assert 'read_skill_resource' not in tool_names
    assert 'run_skill_script' not in tool_names


def test_exclude_tools_skills_still_loaded(sample_skills_dir: Path) -> None:
    """Test that skills are still loaded when tools are excluded."""
    toolset = SkillsToolset(
        directories=[sample_skills_dir],
        exclude_tools={'run_skill_script', 'read_skill_resource'},
    )

    # Skills should still be loaded and accessible
    assert len(toolset.skills) == 3
    assert 'skill-one' in toolset.skills
    assert 'skill-two' in toolset.skills
    assert 'skill-three' in toolset.skills

    # get_skill should still work
    skill = toolset.get_skill('skill-one')
    assert skill.name == 'skill-one'


def test_exclude_tools_programmatic_skills(sample_skills_dir: Path) -> None:
    """Test exclude_tools with programmatic skills."""
    from pydantic_ai_skills import Skill

    custom_skill = Skill(name='custom-skill', description='Custom skill', content='Content')

    toolset = SkillsToolset(
        skills=[custom_skill],
        exclude_tools={'run_skill_script'},
    )

    # Custom skill should be loaded
    assert 'custom-skill' in toolset.skills

    # run_skill_script should be excluded
    tool_names = set(toolset.tools.keys())
    assert 'run_skill_script' not in tool_names
    assert 'list_skills' in tool_names


def test_exclude_tools_mixed_valid_invalid(sample_skills_dir: Path) -> None:
    """Test that invalid tool names in a mixed set raise ValueError."""
    with pytest.raises(ValueError, match='Unknown tools'):
        SkillsToolset(
            directories=[sample_skills_dir],
            exclude_tools={'run_skill_script', 'invalid_tool', 'load_skill'},
        )

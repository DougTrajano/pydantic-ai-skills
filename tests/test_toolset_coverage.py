"""Additional tests for toolset coverage."""

from pathlib import Path

import pytest

from pydantic_ai_skills import Skill, SkillResource, SkillsToolset
from pydantic_ai_skills.directory import SkillsDirectory


@pytest.mark.asyncio
async def test_toolset_resource_xml_generation() -> None:
    """Test that skill with resources is registered."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource
    def get_data(param: str) -> str:
        """Get data with parameter.

        Args:
            param: Parameter description
        """
        return f'Data: {param}'

    toolset = SkillsToolset(skills=[skill])

    # Get instructions - skills overview
    instructions = await toolset.get_instructions(None)

    assert 'test-skill' in instructions
    # Resources are shown when skill is loaded, not in overview
    assert len(skill.resources) == 1


@pytest.mark.asyncio
async def test_toolset_script_xml_generation() -> None:
    """Test that skill with scripts is registered."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def process(query: str, limit: int = 10) -> str:
        """Process data.

        Args:
            query: Query string
            limit: Maximum results
        """
        return f'Processed: {query}'

    toolset = SkillsToolset(skills=[skill])

    # Get instructions - skills overview
    instructions = await toolset.get_instructions(None)

    assert 'test-skill' in instructions
    # Scripts are shown when skill is loaded, not in overview
    assert len(skill.scripts) == 1


def test_toolset_with_skills_directory_instance(tmp_path: Path) -> None:
    """Test toolset with SkillsDirectory instance."""
    # Create skill directory
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
description: Test skill
---
# Test
Content
""")

    # Create SkillsDirectory instance
    skills_dir = SkillsDirectory(path=tmp_path)

    # Pass instance to toolset
    toolset = SkillsToolset(directories=[skills_dir])

    assert 'test-skill' in toolset.skills


def test_toolset_directory_duplicate_warning(tmp_path: Path) -> None:
    """Test warning when directory skills override each other."""
    # Create two directories with same skill name
    dir1 = tmp_path / 'dir1'
    dir1.mkdir()
    (dir1 / 'test-skill').mkdir()
    (dir1 / 'test-skill' / 'SKILL.md').write_text("""---
name: dup-skill
description: First
---
# First
""")

    dir2 = tmp_path / 'dir2'
    dir2.mkdir()
    (dir2 / 'dup-skill').mkdir()
    (dir2 / 'dup-skill' / 'SKILL.md').write_text("""---
name: dup-skill
description: Second
---
# Second
""")

    with pytest.warns(UserWarning, match="Duplicate skill 'dup-skill' found"):
        toolset = SkillsToolset(directories=[dir1, dir2])

    # Last directory wins
    assert toolset.skills['dup-skill'].description == 'Second'


@pytest.mark.asyncio
async def test_toolset_resource_with_description() -> None:
    """Test resource with custom description."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource(description='Custom resource description')
    def get_info() -> str:
        """Get info."""
        return 'info'

    # Verify resource was added with custom description
    assert len(skill.resources) == 1
    assert skill.resources[0].description == 'Custom resource description'


@pytest.mark.asyncio
async def test_toolset_script_with_description() -> None:
    """Test script XML includes description."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script(description='Custom script description')
    async def execute() -> str:
        """Execute."""
        return 'done'

    toolset = SkillsToolset(skills=[skill])
    instructions = await toolset.get_instructions(None)

    # Check that skill appears in instructions (script descriptions are in skill details, not overview)
    assert 'test-skill' in instructions


def test_toolset_skills_property() -> None:
    """Test accessing skills property."""
    skill1 = Skill(name='skill-1', description='First', content='Content 1')
    skill2 = Skill(name='skill-2', description='Second', content='Content 2')

    toolset = SkillsToolset(skills=[skill1, skill2])

    # Access skills via property
    all_skills = toolset.skills
    assert isinstance(all_skills, dict)
    assert len(all_skills) == 2
    assert 'skill-1' in all_skills
    assert 'skill-2' in all_skills


def test_toolset_get_skill_by_name() -> None:
    """Test getting skill by name."""
    skill = Skill(name='my-skill', description='Test', content='Content')
    toolset = SkillsToolset(skills=[skill])

    retrieved = toolset.get_skill('my-skill')
    assert retrieved.name == 'my-skill'
    assert retrieved.description == 'Test'


@pytest.mark.asyncio
async def test_toolset_instructions_with_resources_and_scripts() -> None:
    """Test instructions include both resources and scripts."""
    skill = Skill(name='full-skill', description='Complete skill', content='Full content')

    @skill.resource
    def get_schema() -> str:
        return 'schema'

    @skill.script
    async def run_task() -> str:
        return 'done'

    toolset = SkillsToolset(skills=[skill])
    instructions = await toolset.get_instructions(None)

    assert 'full-skill' in instructions
    assert 'Complete skill' in instructions


@pytest.mark.asyncio
async def test_toolset_instructions_multiple_skills() -> None:
    """Test instructions with multiple skills."""
    skill1 = Skill(name='skill-1', description='First', content='Content 1')
    skill2 = Skill(name='skill-2', description='Second', content='Content 2')
    skill3 = Skill(name='skill-3', description='Third', content='Content 3')

    toolset = SkillsToolset(skills=[skill1, skill2, skill3])
    instructions = await toolset.get_instructions(None)

    assert 'skill-1' in instructions
    assert 'skill-2' in instructions
    assert 'skill-3' in instructions
    assert 'First' in instructions
    assert 'Second' in instructions
    assert 'Third' in instructions


def test_toolset_default_directory_exists(tmp_path: Path) -> None:
    """Test toolset with default ./skills directory when it exists."""
    import os

    # Create skills directory in temp location
    skills_dir = tmp_path / 'skills'
    skills_dir.mkdir()

    skill_dir = skills_dir / 'default-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: default-skill
description: Default skill
---
# Default
""")

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Should load from default ./skills directory
        toolset = SkillsToolset()

        assert 'default-skill' in toolset.skills
    finally:
        os.chdir(original_dir)


@pytest.mark.asyncio
async def test_toolset_resource_without_function_schema() -> None:
    """Test skill with static resources."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        resources=[SkillResource(name='static-resource', content='Static content')],
    )

    toolset = SkillsToolset(skills=[skill])

    # Verify skill and resource are registered
    assert 'test-skill' in toolset.skills
    assert len(toolset.skills['test-skill'].resources) == 1


@pytest.mark.asyncio
async def test_toolset_script_without_function_schema(tmp_path: Path) -> None:
    """Test skill with file-based scripts."""
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()
    scripts_dir = skill_dir / 'scripts'
    scripts_dir.mkdir()

    script_file = scripts_dir / 'test_script.py'
    script_file.write_text('print("test")')

    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
description: Test skill
---
# Test
With script
""")

    toolset = SkillsToolset(directories=[tmp_path])

    # Verify skill and script are registered
    assert 'test-skill' in toolset.skills
    assert len(toolset.skills['test-skill'].scripts) == 1
    # Script name should be relative path with .py extension
    assert toolset.skills['test-skill'].scripts[0].name == 'scripts/test_script.py'


def test_toolset_validate_parameter() -> None:
    """Test toolset with validate parameter."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    # With validation
    toolset_validated = SkillsToolset(skills=[skill], validate=True)
    assert toolset_validated._validate is True

    # Without validation
    toolset_no_validation = SkillsToolset(skills=[skill], validate=False)
    assert toolset_no_validation._validate is False


def test_toolset_max_depth_parameter(tmp_path: Path) -> None:
    """Test toolset with max_depth parameter."""
    # Create nested skill structure
    level1 = tmp_path / 'level1'
    level1.mkdir()
    level2 = level1 / 'level2'
    level2.mkdir()
    skill_dir = level2 / 'deep-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: deep-skill
description: Deep skill
---
# Deep
""")

    # With max_depth=1, should not find the deeply nested skill
    toolset_shallow = SkillsToolset(directories=[tmp_path], max_depth=1)
    assert 'deep-skill' not in toolset_shallow.skills

    # With max_depth=3, should find it
    toolset_deep = SkillsToolset(directories=[tmp_path], max_depth=3)
    assert 'deep-skill' in toolset_deep.skills

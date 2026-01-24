"""Tests for programmatic skills functionality."""

from dataclasses import dataclass

import pytest
from pydantic_ai import RunContext

from pydantic_ai_skills import Skill, SkillResource, SkillScript, SkillsToolset


@dataclass
class MockDeps:
    """Mock dependencies for testing."""

    data: str = 'test data'


def test_skill_creation_with_resources_and_scripts() -> None:
    """Test creating a skill with inline resources and scripts."""
    skill = Skill(
        name='test-skill',
        description='Test skill',
        content='Instructions here',
        resources=[SkillResource(name='ref', content='Reference content')],
        scripts=[],
    )

    assert skill.name == 'test-skill'
    assert len(skill.resources) == 1
    assert skill.resources[0].name == 'ref'


def test_skill_resource_decorator() -> None:
    """Test adding resources via decorator."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource
    def get_info() -> str:
        """Get information."""
        return 'Dynamic info'

    assert len(skill.resources) == 1
    assert skill.resources[0].name == 'get_info'
    assert skill.resources[0].function is not None
    assert skill.resources[0].function_schema is not None


def test_skill_resource_decorator_with_custom_name() -> None:
    """Test resource decorator with custom name."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource(name='custom-resource', description='Custom description')
    def my_func() -> str:
        """Get data."""
        return 'data'

    assert len(skill.resources) == 1
    assert skill.resources[0].name == 'custom-resource'
    assert skill.resources[0].description == 'Custom description'


def test_skill_resource_decorator_with_context() -> None:
    """Test resource decorator with RunContext."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource
    async def get_data(ctx: RunContext[MockDeps]) -> str:
        """Get data from context."""
        return ctx.deps.data

    assert len(skill.resources) == 1
    assert skill.resources[0].takes_ctx is True


def test_skill_script_decorator() -> None:
    """Test adding scripts via decorator."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def process_data() -> str:
        """Process data."""
        return 'Processed'

    assert len(skill.scripts) == 1
    assert skill.scripts[0].name == 'process_data'
    assert skill.scripts[0].function is not None
    assert skill.scripts[0].function_schema is not None


def test_skill_script_decorator_with_custom_name() -> None:
    """Test script decorator with custom name."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script(name='custom-script', description='Custom script description')
    async def my_script() -> str:
        """Execute script."""
        return 'result'

    assert len(skill.scripts) == 1
    assert skill.scripts[0].name == 'custom-script'
    assert skill.scripts[0].description == 'Custom script description'


def test_skill_script_decorator_with_parameters() -> None:
    """Test script decorator with parameters."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def run_query(ctx: RunContext[MockDeps], query: str, limit: int = 10) -> str:  # noqa: D417
        """Execute query.

        Args:
            query: Query string
            limit: Max results
        """
        return f'Query: {query}, Limit: {limit}'

    assert len(skill.scripts) == 1
    assert skill.scripts[0].takes_ctx is True
    assert skill.scripts[0].function_schema is not None


def test_skill_script_decorator_with_context() -> None:
    """Test script decorator with RunContext."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def process(ctx: RunContext[MockDeps]) -> str:
        """Process with context."""
        return f'Processed: {ctx.deps.data}'

    assert len(skill.scripts) == 1
    assert skill.scripts[0].takes_ctx is True


def test_skill_resource_load_with_function() -> None:
    """Test loading resource with function."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource
    def get_value() -> str:
        return 'test value'

    resource = skill.resources[0]
    assert resource.function is not None


def test_skill_resource_load_with_static_content() -> None:
    """Test loading resource with static content."""
    resource = SkillResource(name='static', content='Static content here')
    assert resource.content == 'Static content here'
    assert resource.function is None


def test_skill_script_run_with_function() -> None:
    """Test running script with function."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def execute() -> str:
        return 'executed'

    script = skill.scripts[0]
    assert script.function is not None


def test_toolset_with_programmatic_skills() -> None:
    """Test toolset initialization with programmatic skills."""
    skill1 = Skill(name='skill-one', description='First skill', content='Content 1')
    skill2 = Skill(name='skill-two', description='Second skill', content='Content 2')

    toolset = SkillsToolset(skills=[skill1, skill2])

    assert len(toolset.skills) == 2
    assert 'skill-one' in toolset.skills
    assert 'skill-two' in toolset.skills


def test_toolset_with_mixed_skills(tmp_path) -> None:
    """Test toolset with both file-based and programmatic skills."""
    # Create file-based skill
    skill_dir = tmp_path / 'file-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: file-skill
description: File-based skill
---
# File Skill
Content here
""")

    # Create programmatic skill
    prog_skill = Skill(name='prog-skill', description='Programmatic skill', content='Prog content')

    toolset = SkillsToolset(directories=[tmp_path], skills=[prog_skill])

    assert len(toolset.skills) == 2
    assert 'file-skill' in toolset.skills
    assert 'prog-skill' in toolset.skills


def test_toolset_duplicate_skill_warning() -> None:
    """Test warning when duplicate skills are provided."""
    skill1 = Skill(name='duplicate', description='First', content='Content 1')
    skill2 = Skill(name='duplicate', description='Second', content='Content 2')

    with pytest.warns(UserWarning, match="Duplicate skill 'duplicate' found"):
        toolset = SkillsToolset(skills=[skill1, skill2])

    # Last one wins
    assert toolset.skills['duplicate'].description == 'Second'


def test_toolset_no_skills_or_directories_warning(tmp_path) -> None:
    """Test warning when default skills directory doesn't exist."""
    import os

    original_dir = os.getcwd()
    try:
        # Change to tmp directory where ./skills doesn't exist
        os.chdir(tmp_path)

        with pytest.warns(UserWarning, match='Default skills directory'):
            toolset = SkillsToolset()

        assert len(toolset.skills) == 0
    finally:
        os.chdir(original_dir)


def test_skill_metadata_property() -> None:
    """Test skill metadata property."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        metadata={'version': '1.0.0', 'author': 'Test Author'},
    )

    # metadata attribute exists and contains the data
    assert skill.metadata == {'version': '1.0.0', 'author': 'Test Author'}
    assert skill.metadata['version'] == '1.0.0'


def test_skill_resource_validation_no_content_or_function() -> None:
    """Test that resource requires either content or function."""
    with pytest.raises(ValueError, match='must have either content, function, or uri'):
        SkillResource(name='invalid')


def test_skill_resource_validation_function_without_schema() -> None:
    """Test that resource with function requires function_schema."""
    with pytest.raises(ValueError, match='with function must have function_schema'):
        SkillResource(name='invalid', function=lambda: 'test')


def test_skill_script_validation_no_function_or_uri() -> None:
    """Test that script requires either function or uri."""
    with pytest.raises(ValueError, match='must have either function or uri'):
        SkillScript(name='invalid')


def test_skill_script_validation_function_without_schema() -> None:
    """Test that script with function requires function_schema."""
    with pytest.raises(ValueError, match='with function must have function_schema'):
        SkillScript(name='invalid', function=lambda: 'test')


@pytest.mark.asyncio
async def test_skill_resource_load_error_no_content() -> None:
    """Test resource load raises error when no content or function."""
    # Create a resource that bypasses validation
    resource = SkillResource(name='test', uri='/fake/path')
    resource.uri = None  # Remove uri after creation to trigger error
    resource.content = None

    with pytest.raises(ValueError, match='has no content or function'):
        await resource.load(None)


@pytest.mark.asyncio
async def test_skill_script_run_error_no_function() -> None:
    """Test script run raises error when no function."""
    # Create a script that bypasses validation
    script = SkillScript(name='test', uri='/fake/path')
    script.uri = None  # Remove uri after creation to trigger error
    script.function = None

    with pytest.raises(ValueError, match='has no function'):
        await script.run(None)

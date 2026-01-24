"""Tests for uncovered code paths to improve coverage."""

import json
import warnings
from pathlib import Path

import pytest

from pydantic_ai_skills import Skill, SkillResource, SkillsToolset
from pydantic_ai_skills.directory import (
    SkillsDirectory,
    _discover_skills,
    _find_skill_files,
    _validate_skill_metadata,
)
from pydantic_ai_skills.exceptions import (
    SkillNotFoundError,
    SkillValidationError,
)
from pydantic_ai_skills.local import FileBasedSkillResource, LocalSkillScriptExecutor
from pydantic_ai_skills.types import normalize_skill_name

# ============================================================================
# Tests for normalize_skill_name (types.py lines 55-69, 127, 131)
# ============================================================================


def test_normalize_skill_name_with_consecutive_hyphens() -> None:
    """Test that consecutive hyphens are invalid."""
    with pytest.raises(SkillValidationError, match='consecutive hyphens'):
        normalize_skill_name('test--skill')


def test_normalize_skill_name_starts_with_hyphen() -> None:
    """Test that skill names starting with hyphen are invalid."""
    with pytest.raises(SkillValidationError, match='invalid'):
        normalize_skill_name('-test-skill')


def test_normalize_skill_name_ends_with_hyphen() -> None:
    """Test that skill names ending with hyphen are invalid."""
    with pytest.raises(SkillValidationError, match='invalid'):
        normalize_skill_name('test-skill-')


def test_normalize_skill_name_with_special_chars() -> None:
    """Test that special characters are invalid."""
    with pytest.raises(SkillValidationError, match='invalid'):
        normalize_skill_name('test.skill!')


def test_normalize_skill_name_exactly_64_chars() -> None:
    """Test skill name at exactly 64 character limit."""
    name_64 = 'a' * 64
    result = normalize_skill_name(name_64)
    assert result == name_64
    assert len(result) == 64


def test_normalize_skill_name_exceeds_64_chars() -> None:
    """Test skill name exceeding 64 character limit."""
    name_65 = 'a' * 65
    with pytest.raises(SkillValidationError, match='exceeds 64 characters'):
        normalize_skill_name(name_65)


# ============================================================================
# Tests for FileBasedSkillResource JSON parsing (local.py lines 75-79)
# ============================================================================


@pytest.mark.asyncio
async def test_file_based_resource_load_json(tmp_path: Path) -> None:
    """Test loading and parsing JSON resource."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    json_file = skill_dir / 'data.json'
    json_data = {'key': 'value', 'number': 42, 'nested': {'inner': 'data'}}
    json_file.write_text(json.dumps(json_data))

    resource = FileBasedSkillResource(
        name='data.json',
        uri=str(json_file),
    )

    content = await resource.load(None)
    assert isinstance(content, dict)
    assert content['key'] == 'value'
    assert content['number'] == 42
    assert content['nested']['inner'] == 'data'


@pytest.mark.asyncio
async def test_file_based_resource_load_invalid_json(tmp_path: Path) -> None:
    """Test loading invalid JSON falls back to text."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    json_file = skill_dir / 'bad.json'
    json_file.write_text('{ invalid json }')

    resource = FileBasedSkillResource(
        name='bad.json',
        uri=str(json_file),
    )

    content = await resource.load(None)
    # Should return raw text since JSON parsing failed
    assert isinstance(content, str)
    assert '{ invalid json }' in content


# ============================================================================
# Tests for FileBasedSkillResource YAML parsing (local.py lines 83-87)
# ============================================================================


@pytest.mark.asyncio
async def test_file_based_resource_load_yaml(tmp_path: Path) -> None:
    """Test loading and parsing YAML resource."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    yaml_file = skill_dir / 'config.yaml'
    yaml_data = 'key: value\nnumber: 42\nnested:\n  inner: data'
    yaml_file.write_text(yaml_data)

    resource = FileBasedSkillResource(
        name='config.yaml',
        uri=str(yaml_file),
    )

    content = await resource.load(None)
    assert isinstance(content, dict)
    assert content['key'] == 'value'
    assert content['number'] == 42
    assert content['nested']['inner'] == 'data'


@pytest.mark.asyncio
async def test_file_based_resource_load_yml_extension(tmp_path: Path) -> None:
    """Test loading YAML with .yml extension."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    yml_file = skill_dir / 'config.yml'
    yml_data = 'setting: enabled\nvalue: 100'
    yml_file.write_text(yml_data)

    resource = FileBasedSkillResource(
        name='config.yml',
        uri=str(yml_file),
    )

    content = await resource.load(None)
    assert isinstance(content, dict)
    assert content['setting'] == 'enabled'
    assert content['value'] == 100


@pytest.mark.asyncio
async def test_file_based_resource_load_invalid_yaml(tmp_path: Path) -> None:
    """Test loading invalid YAML falls back to text."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    yaml_file = skill_dir / 'bad.yaml'
    yaml_file.write_text('invalid: [unclosed')

    resource = FileBasedSkillResource(
        name='bad.yaml',
        uri=str(yaml_file),
    )

    content = await resource.load(None)
    # Should return raw text since YAML parsing failed
    assert isinstance(content, str)
    assert 'invalid' in content


# ============================================================================
# Tests for _find_skill_files depth limiting (directory.py lines 195-210)
# ============================================================================


def test_find_skill_files_depth_zero(tmp_path: Path) -> None:
    """Test finding skills with max_depth=0 (root only)."""
    # Create skill at root
    (tmp_path / 'SKILL.md').write_text('---\nname: root-skill\n---\nContent')

    # Create nested skill (should not be found with depth=0)
    nested = tmp_path / 'nested'
    nested.mkdir()
    (nested / 'SKILL.md').write_text('---\nname: nested-skill\n---\nContent')

    files = _find_skill_files(tmp_path, max_depth=0)

    # Should only find root SKILL.md
    assert len(files) == 1
    assert files[0].parent == tmp_path


def test_find_skill_files_depth_one(tmp_path: Path) -> None:
    """Test finding skills with max_depth=1 (one level deep)."""
    # Create skill at root
    (tmp_path / 'SKILL.md').write_text('---\nname: root\n---\nContent')

    # Create skill one level deep (should be found)
    level1 = tmp_path / 'level1'
    level1.mkdir()
    (level1 / 'SKILL.md').write_text('---\nname: level1\n---\nContent')

    # Create skill two levels deep (should not be found with depth=1)
    level2 = level1 / 'level2'
    level2.mkdir()
    (level2 / 'SKILL.md').write_text('---\nname: level2\n---\nContent')

    files = _find_skill_files(tmp_path, max_depth=1)

    assert len(files) == 2
    skill_dirs = {f.parent.name for f in files}
    assert 'level1' in skill_dirs or tmp_path.name in skill_dirs


def test_find_skill_files_unlimited_depth(tmp_path: Path) -> None:
    """Test finding skills with max_depth=None (unlimited)."""
    # Create deeply nested skill
    deep_path = tmp_path / 'a' / 'b' / 'c' / 'd' / 'e'
    deep_path.mkdir(parents=True)
    (deep_path / 'SKILL.md').write_text('---\nname: deep\n---\nContent')

    # With max_depth=3, should not find deep skill
    files_limited = _find_skill_files(tmp_path, max_depth=3)
    assert len(files_limited) == 0

    # With max_depth=None, should find deep skill
    files_unlimited = _find_skill_files(tmp_path, max_depth=None)
    assert len(files_unlimited) == 1


# ============================================================================
# Tests for validation error handling (directory.py lines 239-241, 299)
# ============================================================================


def test_validate_skill_metadata_compatibility_too_long() -> None:
    """Test validation when compatibility field exceeds 500 characters."""
    frontmatter = {
        'name': 'test-skill',
        'description': 'Test',
        'compatibility': 'x' * 501,
    }

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        is_valid = _validate_skill_metadata(frontmatter, 'Content')

        assert is_valid is False
        assert any('compatibility exceeds 500' in str(msg.message) for msg in w)


def test_discover_skills_invalid_yaml_frontmatter(tmp_path: Path) -> None:
    """Test discovering skill with invalid YAML frontmatter."""
    skill_dir = tmp_path / 'bad-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
invalid: [unclosed array
---
Content
""")

    # With validate=False, should skip skill with warning instead of raising
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        _discover_skills(tmp_path, validate=False)
        # Should have warning about invalid skill
        assert len(w) > 0
        assert 'Skipping invalid skill' in str(w[0].message)


def test_discover_skills_os_error_handling(tmp_path: Path) -> None:
    """Test handling of OS errors during skill discovery."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    skill_md = skill_dir / 'SKILL.md'
    skill_md.write_text('---\nname: test\n---\nContent')

    # Make file unreadable (on Unix systems)
    try:
        skill_md.chmod(0o000)

        # Should raise SkillValidationError
        with pytest.raises(SkillValidationError):
            _discover_skills(tmp_path, validate=False)
    finally:
        # Restore permissions for cleanup
        skill_md.chmod(0o644)


# ============================================================================
# Tests for toolset resource/script finding (toolset.py lines 305-346)
# ============================================================================


def test_toolset_find_skill_resource_by_name() -> None:
    """Test finding skill resource by exact name."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        resources=[
            SkillResource(name='FORMS.md', content='Forms'),
            SkillResource(name='REFERENCE.md', content='Reference'),
        ],
    )

    toolset = SkillsToolset(skills=[skill])

    # Test finding existing resource
    resource = toolset._find_skill_resource(skill, 'FORMS.md')
    assert resource is not None
    assert resource.name == 'FORMS.md'


def test_toolset_find_skill_resource_not_found() -> None:
    """Test finding non-existent skill resource."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        resources=[
            SkillResource(name='FORMS.md', content='Forms'),
        ],
    )

    toolset = SkillsToolset(skills=[skill])

    # Test finding non-existent resource
    resource = toolset._find_skill_resource(skill, 'NONEXISTENT.md')
    assert resource is None


def test_toolset_find_skill_resource_no_resources() -> None:
    """Test finding resource in skill with no resources."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        resources=[],
    )

    toolset = SkillsToolset(skills=[skill])

    # Should return None when skill has no resources
    resource = toolset._find_skill_resource(skill, 'ANY.md')
    assert resource is None


def test_toolset_find_skill_script_by_name() -> None:
    """Test finding skill script by exact name."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def process_data() -> str:
        return 'processed'

    toolset = SkillsToolset(skills=[skill])

    # Test finding existing script
    script = toolset._find_skill_script(skill, 'process_data')
    assert script is not None
    assert script.name == 'process_data'


def test_toolset_find_skill_script_not_found() -> None:
    """Test finding non-existent skill script."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def process() -> str:
        return 'done'

    toolset = SkillsToolset(skills=[skill])

    # Test finding non-existent script
    script = toolset._find_skill_script(skill, 'nonexistent')
    assert script is None


def test_toolset_find_skill_script_no_scripts() -> None:
    """Test finding script in skill with no scripts."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        scripts=[],
    )

    toolset = SkillsToolset(skills=[skill])

    # Should return None when skill has no scripts
    script = toolset._find_skill_script(skill, 'ANY')
    assert script is None


# ============================================================================
# Tests for toolset tool integration (toolset.py lines 387-409, 443-458)
# ============================================================================


@pytest.mark.asyncio
async def test_toolset_read_skill_resource_tool_with_callable() -> None:
    """Test read_skill_resource tool with callable resource."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource
    def get_data(user_id: int) -> str:
        """Get user data.

        Args:
            user_id: The user ID
        """
        return f'User {user_id} data'

    toolset = SkillsToolset(skills=[skill])

    # Verify the skill and resource were registered
    assert 'test-skill' in toolset.skills
    assert len(skill.resources) == 1
    assert skill.resources[0].name == 'get_data'
    assert skill.resources[0].function_schema is not None


@pytest.mark.asyncio
async def test_toolset_run_skill_script_tool_with_callable() -> None:
    """Test run_skill_script tool with callable script."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def execute(query: str) -> str:
        """Execute query.

        Args:
            query: The query string
        """
        return f'Executed: {query}'

    toolset = SkillsToolset(skills=[skill])

    # Verify the skill and script were registered
    assert 'test-skill' in toolset.skills
    assert len(skill.scripts) == 1
    assert skill.scripts[0].name == 'execute'
    assert skill.scripts[0].function_schema is not None


# ============================================================================
# Tests for toolset resource/script XML generation (toolset.py lines 287-312)
# ============================================================================


def test_toolset_build_resource_xml_with_description() -> None:
    """Test building XML for resource with description."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        resources=[
            SkillResource(name='FORMS.md', description='Form templates', content='Forms'),
        ],
    )

    toolset = SkillsToolset(skills=[skill])
    resource = skill.resources[0]

    xml = toolset._build_resource_xml(resource)

    assert '<resource' in xml
    assert 'name="FORMS.md"' in xml
    assert 'description="Form templates"' in xml
    assert '/>' in xml


def test_toolset_build_resource_xml_without_description() -> None:
    """Test building XML for resource without description."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
        resources=[
            SkillResource(name='DATA.json', content='{}'),
        ],
    )

    toolset = SkillsToolset(skills=[skill])
    resource = skill.resources[0]

    xml = toolset._build_resource_xml(resource)

    assert '<resource' in xml
    assert 'name="DATA.json"' in xml
    # Should not have description attribute
    assert 'description=' not in xml


def test_toolset_build_resource_xml_with_callable() -> None:
    """Test building XML for callable resource with parameters."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.resource
    def get_info(format: str = 'json') -> str:
        """Get information.

        Args:
            format: Output format
        """
        return 'info'

    toolset = SkillsToolset(skills=[skill])
    resource = skill.resources[0]

    xml = toolset._build_resource_xml(resource)

    assert '<resource' in xml
    assert 'name="get_info"' in xml
    assert 'parameters=' in xml  # Has parameter schema


def test_toolset_build_script_xml_with_description() -> None:
    """Test building XML for script with description."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def process() -> str:
        """Process data."""
        return 'done'

    toolset = SkillsToolset(skills=[skill])
    script = skill.scripts[0]

    xml = toolset._build_script_xml(script)

    assert '<script' in xml
    assert 'name="process"' in xml
    assert 'description="Process data."' in xml
    assert '/>' in xml


def test_toolset_build_script_xml_with_parameters() -> None:
    """Test building XML for script with parameters."""
    skill = Skill(name='test-skill', description='Test', content='Content')

    @skill.script
    async def analyze(data_path: str, threshold: float = 0.5) -> str:
        """Analyze data.

        Args:
            data_path: Path to data
            threshold: Analysis threshold
        """
        return 'analyzed'

    toolset = SkillsToolset(skills=[skill])
    script = skill.scripts[0]

    xml = toolset._build_script_xml(script)

    assert '<script' in xml
    assert 'name="analyze"' in xml
    assert 'parameters=' in xml  # Has parameter schema


# ============================================================================
# Tests for toolset get_instructions edge cases (toolset.py lines 588-638)
# ============================================================================


@pytest.mark.asyncio
async def test_toolset_get_instructions_with_custom_template() -> None:
    """Test get_instructions with custom instruction template."""
    skill = Skill(
        name='test-skill',
        description='A test skill',
        content='Instructions',
    )

    custom_template = """Available skills:
{skills_list}

Use these skills when appropriate."""

    toolset = SkillsToolset(
        skills=[skill],
        instruction_template=custom_template,
    )

    from unittest.mock import Mock

    mock_ctx = Mock()

    instructions = await toolset.get_instructions(mock_ctx)

    assert instructions is not None
    assert 'test-skill' in instructions
    assert 'Available skills:' in instructions


@pytest.mark.asyncio
async def test_toolset_get_instructions_with_proper_template() -> None:
    """Test that custom template without placeholder is handled gracefully."""
    skill = Skill(
        name='test-skill',
        description='A test skill',
        content='Instructions',
    )

    # Valid template with placeholder
    valid_template = """Available skills:
{skills_list}

Use them."""

    toolset = SkillsToolset(
        skills=[skill],
        instruction_template=valid_template,
    )

    from unittest.mock import Mock

    mock_ctx = Mock()

    # Should work fine with proper template
    instructions = await toolset.get_instructions(mock_ctx)
    assert instructions is not None


# ============================================================================
# Tests for error messages and edge cases (toolset.py lines 482-497, 651)
# ============================================================================


@pytest.mark.asyncio
async def test_load_skill_with_empty_skill_name() -> None:
    """Test load_skill with skill that exists."""
    skill = Skill(
        name='test-skill',
        description='Test',
        content='Content',
    )

    toolset = SkillsToolset(skills=[skill])

    # Verify the skill was registered
    assert 'test-skill' in toolset.skills
    registered_skill = toolset.get_skill('test-skill')
    assert registered_skill.name == 'test-skill'


@pytest.mark.asyncio
async def test_read_skill_resource_with_missing_skill() -> None:
    """Test read_skill_resource with skill that doesn't exist."""
    skill = Skill(
        name='existing-skill',
        description='Test',
        content='Content',
    )

    toolset = SkillsToolset(skills=[skill])

    # Verify error would be raised
    assert toolset.get_skill('existing-skill').name == 'existing-skill'

    with pytest.raises(SkillNotFoundError):
        toolset.get_skill('nonexistent-skill')


@pytest.mark.asyncio
async def test_run_skill_script_with_missing_skill() -> None:
    """Test run_skill_script with skill that doesn't exist."""
    skill = Skill(
        name='existing-skill',
        description='Test',
        content='Content',
    )

    toolset = SkillsToolset(skills=[skill])

    # Verify error would be raised
    with pytest.raises(SkillNotFoundError):
        toolset.get_skill('nonexistent-skill')


# ============================================================================
# Tests for SkillsDirectory initialization (directory.py lines 355-362, 446, 460-465)
# ============================================================================


def test_skills_directory_with_custom_executor(tmp_path: Path) -> None:
    """Test SkillsDirectory with custom script executor."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('---\nname: test\ndescription: Test\n---\nContent')

    # Create script
    scripts = skill_dir / 'scripts'
    scripts.mkdir()
    (scripts / 'test.py').write_text('print("test")')

    # Create custom executor
    custom_executor = LocalSkillScriptExecutor(timeout=60)

    # Initialize with custom executor
    skills_dir = SkillsDirectory(
        path=tmp_path,
        script_executor=custom_executor,
    )

    assert len(skills_dir.skills) == 1
    skill = list(skills_dir.skills.values())[0]
    assert len(skill.scripts) == 1


def test_skills_directory_get_skills_method(tmp_path: Path) -> None:
    """Test SkillsDirectory.get_skills() method."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('---\nname: test\ndescription: Test\n---\nContent')

    skills_dir = SkillsDirectory(path=tmp_path)

    # Test get_skills method
    skills_dict = skills_dir.get_skills()

    assert len(skills_dict) == 1
    # Keys are URIs
    skill_uris = list(skills_dict.keys())
    assert any('skill' in uri for uri in skill_uris)


def test_skills_directory_load_skill_method(tmp_path: Path) -> None:
    """Test SkillsDirectory.load_skill() method."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()
    skill_md = skill_dir / 'SKILL.md'
    skill_md.write_text('---\nname: test\ndescription: Test\n---\nContent')

    skills_dir = SkillsDirectory(path=tmp_path)

    # Get the skill URI
    skills = skills_dir.get_skills()
    skill_uri = list(skills.keys())[0]

    # Load skill by URI
    skill = skills_dir.load_skill(skill_uri)

    assert skill.name == 'test'
    assert skill.description == 'Test'


def test_skills_directory_load_skill_not_found(tmp_path: Path) -> None:
    """Test SkillsDirectory.load_skill() with non-existent URI."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('---\nname: test\ndescription: Test\n---\nContent')

    skills_dir = SkillsDirectory(path=tmp_path)

    # Try to load non-existent skill
    with pytest.raises(SkillNotFoundError):
        skills_dir.load_skill('/nonexistent/path')

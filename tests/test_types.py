"""Tests for pydantic-ai-skills types."""

from pathlib import Path

from pydantic_ai_skills.types import Skill, SkillResource, SkillScript


def test_skill_creation() -> None:
    """Test creating Skill with required fields."""
    skill = Skill(name='test-skill', description='A test skill', content='Test instructions')

    assert skill.name == 'test-skill'
    assert skill.description == 'A test skill'
    assert skill.content == 'Test instructions'
    assert skill.resources == []
    assert skill.scripts == []
    assert skill.metadata is None


def test_skill_with_metadata() -> None:
    """Test Skill with additional metadata."""
    skill = Skill(
        name='test-skill',
        description='A test skill',
        content='Test instructions',
        metadata={'version': '1.0.0', 'author': 'Test Author'},
    )

    assert skill.metadata is not None
    assert skill.metadata['version'] == '1.0.0'
    assert skill.metadata['author'] == 'Test Author'


def test_skill_resource_creation() -> None:
    """Test creating SkillResource with static content."""
    resource = SkillResource(name='reference', content='Reference documentation here')

    assert resource.name == 'reference'
    assert resource.content == 'Reference documentation here'
    assert resource.function is None
    assert resource.uri is None


def test_skill_script_creation(tmp_path: Path) -> None:
    """Test creating SkillScript with URI (file-based)."""
    script_path = tmp_path / 'skill' / 'scripts' / 'test_script.py'
    script = SkillScript(
        name='test_script',
        uri=str(script_path),
        skill_name='test-skill',
        function=None,
        function_schema=None,
    )

    assert script.name == 'test_script'
    assert script.uri == str(script_path)
    assert script.skill_name == 'test-skill'
    assert script.function is None

"""Tests for pydantic-ai-skills types."""

from pydantic_ai_skills.types import SkillMetadata, SkillResource, SkillScript


def test_skill_metadata_creation() -> None:
    """Test creating SkillMetadata with required fields."""
    metadata = SkillMetadata(name='test-skill', description='A test skill')

    assert metadata.name == 'test-skill'
    assert metadata.description == 'A test skill'
    assert metadata.extra is None


def test_skill_metadata_with_extra_fields() -> None:
    """Test SkillMetadata with additional fields."""
    metadata = SkillMetadata(
        name='test-skill', description='A test skill', extra={'version': '1.0.0', 'author': 'Test Author'}
    )

    assert metadata.extra is not None
    assert metadata.extra['version'] == '1.0.0'
    assert metadata.extra['author'] == 'Test Author'


def test_skill_resource_creation() -> None:
    """Test creating SkillResource."""
    resource = SkillResource(name='FORMS.md', uri='/tmp/skill/FORMS.md')

    assert resource.name == 'FORMS.md'
    assert resource.uri == '/tmp/skill/FORMS.md'
    assert resource.content is None


def test_skill_script_creation() -> None:
    """Test creating SkillScript."""
    script = SkillScript(name='test_script', uri='/tmp/skill/scripts/test_script.py', skill_name='test-skill')

    assert script.name == 'test_script'
    assert script.uri == '/tmp/skill/scripts/test_script.py'
    assert script.skill_name == 'test-skill'

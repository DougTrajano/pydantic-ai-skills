"""Tests for validation functionality."""

from pydantic_ai_skills.toolset import _validate_skill_metadata


def test_validate_skill_metadata_valid() -> None:
    """Test validation with valid metadata."""
    frontmatter = {
        'name': 'test-skill',
        'description': 'A valid test skill',
    }
    warnings = _validate_skill_metadata(frontmatter, 'Content here.')
    assert len(warnings) == 0


def test_validate_skill_metadata_name_too_long() -> None:
    """Test validation with name exceeding 64 characters."""
    frontmatter = {
        'name': 'a' * 65,
        'description': 'Test',
    }
    warnings = _validate_skill_metadata(frontmatter, 'Content')

    assert len(warnings) == 1
    assert '64 characters' in warnings[0]


def test_validate_skill_metadata_invalid_name_format() -> None:
    """Test validation with invalid name format."""
    frontmatter = {
        'name': 'Invalid_Name_With_Underscores',
        'description': 'Test',
    }
    warnings = _validate_skill_metadata(frontmatter, 'Content')

    assert len(warnings) >= 1
    assert any('lowercase letters, numbers, and hyphens' in w for w in warnings)


def test_validate_skill_metadata_reserved_word() -> None:
    """Test validation with reserved words in name."""
    frontmatter = {
        'name': 'anthropic-helper',
        'description': 'Test',
    }
    warnings = _validate_skill_metadata(frontmatter, 'Content')

    assert len(warnings) >= 1
    assert any('reserved word' in w for w in warnings)


def test_validate_skill_metadata_description_too_long() -> None:
    """Test validation with description exceeding 1024 characters."""
    frontmatter = {
        'name': 'test-skill',
        'description': 'x' * 1025,
    }
    warnings = _validate_skill_metadata(frontmatter, 'Content')

    assert len(warnings) >= 1
    assert any('1024 characters' in w for w in warnings)


def test_validate_skill_metadata_instructions_too_long() -> None:
    """Test validation with instructions exceeding 500 lines."""
    frontmatter = {
        'name': 'test-skill',
        'description': 'Test',
    }
    # Create content with 501 lines
    instructions = '\n'.join([f'Line {i}' for i in range(501)])

    warnings = _validate_skill_metadata(frontmatter, instructions)

    assert len(warnings) >= 1
    assert any('500 lines' in w for w in warnings)


def test_validate_skill_metadata_multiple_issues() -> None:
    """Test validation with multiple issues."""
    frontmatter = {
        'name': 'A' * 65,  # Too long
        'description': 'x' * 1025,  # Too long
    }
    instructions = '\n'.join([f'Line {i}' for i in range(501)])  # Too many lines

    warnings = _validate_skill_metadata(frontmatter, instructions)

    # Should have warnings for name, description, and instructions
    assert len(warnings) >= 3


def test_validate_skill_metadata_good_naming_conventions() -> None:
    """Test validation with valid naming conventions."""
    good_names = [
        'processing-pdfs',
        'analyzing-spreadsheets',
        'test-skill-123',
        'pdf-processing',
        'skill-1',
    ]

    for name in good_names:
        frontmatter = {'name': name, 'description': 'Test'}
        warnings = _validate_skill_metadata(frontmatter, 'Content')
        assert len(warnings) == 0, f"Name '{name}' should be valid"


def test_validate_skill_metadata_bad_naming_conventions() -> None:
    """Test validation with invalid naming conventions."""
    bad_names = [
        'Invalid_Name',  # Underscores
        'InvalidName',  # Capital letters
        'invalid name',  # Spaces
        'invalid.name',  # Periods
        'claude-tools',  # Reserved word
    ]

    for name in bad_names:
        frontmatter = {'name': name, 'description': 'Test'}
        warnings = _validate_skill_metadata(frontmatter, 'Content')
        assert len(warnings) > 0, f"Name '{name}' should trigger warnings"

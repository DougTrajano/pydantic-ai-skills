"""Tests for the minimal SKILL.md reading this package still does itself.

harness owns parsing and validation; what is left here is what runs *before* harness
sees a library — the fields a registry filter needs, and the name rewriting that keeps a
staged package's frontmatter in agreement with its directory.
"""

from pathlib import Path

import pytest

from pydantic_ai_skills._parsing import (
    parse_skill_md,
    read_skill_info,
    rewrite_skill_name,
    validate_skill_name,
)


def test_parse_skill_md_with_frontmatter() -> None:
    """Test parsing SKILL.md with valid frontmatter."""
    content = """---
name: test-skill
description: A test skill for testing
version: 1.0.0
---

# Test Skill

This is the main content.
"""

    frontmatter, instructions = parse_skill_md(content)

    assert frontmatter['name'] == 'test-skill'
    assert frontmatter['description'] == 'A test skill for testing'
    assert frontmatter['version'] == '1.0.0'
    assert instructions.startswith('# Test Skill')


def test_parse_skill_md_without_frontmatter() -> None:
    """Test parsing SKILL.md without frontmatter."""
    content = """# Test Skill

This skill has no frontmatter.
"""

    frontmatter, instructions = parse_skill_md(content)

    assert frontmatter == {}
    assert instructions.startswith('# Test Skill')


def test_parse_skill_md_empty_frontmatter() -> None:
    """Test parsing SKILL.md with empty frontmatter."""
    content = """---
---

# Test Skill

Content here.
"""

    frontmatter, instructions = parse_skill_md(content)

    assert frontmatter == {}
    assert instructions.startswith('# Test Skill')


def test_parse_skill_md_invalid_yaml() -> None:
    """Test parsing SKILL.md with invalid YAML."""
    content = """---
name: test-skill
description: [unclosed array
---

Content.
"""

    with pytest.raises(ValueError, match='Failed to parse YAML frontmatter'):
        parse_skill_md(content)


def test_parse_skill_md_multiline_description() -> None:
    """Test parsing SKILL.md with multiline description."""
    content = """---
name: test-skill
description: |
  This is a multiline
  description for testing
---

# Content
"""

    frontmatter, _ = parse_skill_md(content)

    assert 'multiline' in frontmatter['description']
    assert 'description for testing' in frontmatter['description']


def test_parse_skill_md_complex_frontmatter() -> None:
    """Test parsing SKILL.md with complex frontmatter."""
    content = """---
name: complex-skill
description: Complex skill with metadata
version: 2.0.0
author: Test Author
tags:
  - testing
  - example
metadata:
  category: test
  priority: high
---

# Complex Skill
"""

    frontmatter, _ = parse_skill_md(content)

    assert frontmatter['name'] == 'complex-skill'
    assert frontmatter['tags'] == ['testing', 'example']
    assert frontmatter['metadata']['category'] == 'test'


# ---------------------------------------------------------------------------
# read_skill_info: what a FilteredRegistry predicate sees
# ---------------------------------------------------------------------------


def test_read_skill_info_returns_directory_name_not_frontmatter_name(tmp_path: Path) -> None:
    """Harness names a skill after its directory, so filtering must agree with that."""
    skill = tmp_path / 'on-disk-name'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: on-disk-name\ndescription: A skill.\n---\n\nBody.\n')

    info = read_skill_info(skill)

    assert info is not None
    assert info.name == 'on-disk-name'
    assert info.description == 'A skill.'
    assert info.directory == skill


def test_read_skill_info_returns_none_without_a_skill_md(tmp_path: Path) -> None:
    """An ordinary directory in a library is not a skill."""
    plain = tmp_path / 'not-a-skill'
    plain.mkdir()

    assert read_skill_info(plain) is None


def test_read_skill_info_tolerates_malformed_frontmatter(tmp_path: Path) -> None:
    """One broken package must not stop the others in the same registry being filtered.

    harness reports the real error when it loads the library; raising here would take
    every sibling skill down with it.
    """
    skill = tmp_path / 'broken'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: [unclosed\n---\n\nBody.\n')

    info = read_skill_info(skill)

    assert info is not None
    assert info.name == 'broken'
    assert info.description == ''


# ---------------------------------------------------------------------------
# validate_skill_name: mirrors harness's rule so bad prefixes fail early
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'name',
    ['pdf', 'anthropic-pdf', 'a', 'skill-1', 'a' * 64],
)
def test_validate_skill_name_accepts_names_harness_accepts(name: str) -> None:
    """Names harness would accept pass through unchanged."""
    assert validate_skill_name(name, context='test') == name


@pytest.mark.parametrize(
    ('name', 'reason'),
    [
        ('', 'empty'),
        ('a' * 65, 'too long'),
        ('Upper', 'uppercase'),
        ('-leading', 'leading hyphen'),
        ('trailing-', 'trailing hyphen'),
        ('double--hyphen', 'consecutive hyphens'),
        ('has space', 'space'),
        ('has_underscore', 'underscore'),
    ],
)
def test_validate_skill_name_rejects_names_harness_rejects(name: str, reason: str) -> None:
    """Names harness would reject fail here instead, where the cause is visible."""
    with pytest.raises(ValueError, match='invalid skill name'):
        validate_skill_name(name, context='Prefixing')


def test_validate_skill_name_error_names_the_operation() -> None:
    """The message must say what produced the name, not just that it is bad."""
    with pytest.raises(ValueError, match="Prefixing 'pdf' with 'Bad_'"):
        validate_skill_name('Bad_pdf', context="Prefixing 'pdf' with 'Bad_'")


def test_validate_skill_name_agrees_with_harness(tmp_path: Path) -> None:
    """Pin the mirror: a name we accept is one harness actually accepts."""
    from pydantic_ai_harness import Skills

    name = validate_skill_name('anthropic-pdf', context='test')
    skill = tmp_path / name
    skill.mkdir()
    (skill / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: A skill.\n---\n\nBody.\n')

    leaves: list[object] = []
    Skills(tmp_path).apply(leaves.append)

    assert [leaf.id for leaf in leaves] == [name]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# rewrite_skill_name: keeps frontmatter and directory in agreement
# ---------------------------------------------------------------------------


def test_rewrite_skill_name_updates_the_frontmatter_key(tmp_path: Path) -> None:
    """Only the name key changes; the rest of the file is left as it was."""
    skill_file = tmp_path / 'SKILL.md'
    skill_file.write_text('---\nname: pdf\ndescription: A skill.\n---\n\nBody.\n')

    rewrite_skill_name(skill_file, 'anthropic-pdf')

    assert 'name: anthropic-pdf' in skill_file.read_text()
    assert 'description: A skill.' in skill_file.read_text()
    assert skill_file.read_text().endswith('Body.\n')


def test_rewrite_skill_name_leaves_a_nameless_frontmatter_alone(tmp_path: Path) -> None:
    """Harness derives the name from the directory when the key is absent."""
    skill_file = tmp_path / 'SKILL.md'
    original = '---\ndescription: A skill.\n---\n\nBody.\n'
    skill_file.write_text(original)

    rewrite_skill_name(skill_file, 'anthropic-pdf')

    assert skill_file.read_text() == original


def test_rewrite_skill_name_ignores_a_file_without_frontmatter(tmp_path: Path) -> None:
    """Nothing to rewrite means nothing is written."""
    skill_file = tmp_path / 'SKILL.md'
    original = 'Just a body, no frontmatter.\n'
    skill_file.write_text(original)

    rewrite_skill_name(skill_file, 'anthropic-pdf')

    assert skill_file.read_text() == original

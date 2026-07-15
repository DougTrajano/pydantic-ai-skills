"""Tests for skill discovery."""

import sys
from pathlib import Path

import pytest

from pydantic_ai_skills.directory import SkillsDirectory, discover_skills


def test_discover_skills_single_skill(tmp_path: Path) -> None:
    """Test discovering a single skill."""
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    skill_md = skill_dir / 'SKILL.md'
    skill_md.write_text("""---
name: test-skill
description: A test skill
---

# Test Skill

Instructions here.
""")

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 1
    assert skills[0].name == 'test-skill'
    assert skills[0].description == 'A test skill'
    assert 'Instructions here' in skills[0].content


def test_discover_skills_multiple_skills(tmp_path: Path) -> None:
    """Test discovering multiple skills."""
    # Create first skill
    skill1_dir = tmp_path / 'skill-one'
    skill1_dir.mkdir()
    (skill1_dir / 'SKILL.md').write_text("""---
name: skill-one
description: First skill
---

Content 1.
""")

    # Create second skill
    skill2_dir = tmp_path / 'skill-two'
    skill2_dir.mkdir()
    (skill2_dir / 'SKILL.md').write_text("""---
name: skill-two
description: Second skill
---

Content 2.
""")

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 2
    skill_names = {s.name for s in skills}
    assert skill_names == {'skill-one', 'skill-two'}


def test_discover_skills_with_resources(tmp_path: Path) -> None:
    """Test discovering skills with resource files."""
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
description: Skill with resources
---

See FORMS.md for details.
""")

    (skill_dir / 'FORMS.md').write_text('# Forms\n\nForm documentation.')
    (skill_dir / 'REFERENCE.md').write_text('# Reference\n\nAPI reference.')

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 1
    assert skills[0].resources is not None
    assert len(skills[0].resources) == 2
    resource_names = {r.name for r in skills[0].resources}
    assert resource_names == {'FORMS.md', 'REFERENCE.md'}


def test_discover_skills_with_scripts(tmp_path: Path) -> None:
    """Test discovering skills with scripts."""
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
description: Skill with scripts
---

Use the search script.
""")

    scripts_dir = skill_dir / 'scripts'
    scripts_dir.mkdir()
    (scripts_dir / 'search.py').write_text('#!/usr/bin/env python3\nprint("searching")')
    (scripts_dir / 'process.py').write_text('#!/usr/bin/env python3\nprint("processing")')

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 1
    assert skills[0].scripts is not None
    assert len(skills[0].scripts) == 2
    script_names = {s.name for s in skills[0].scripts}
    assert script_names == {'scripts/search.py', 'scripts/process.py'}


def test_discover_skills_with_shell_and_executable_scripts(tmp_path: Path) -> None:
    """Test discovering shell scripts and executable files."""
    if sys.platform == 'win32':
        pytest.skip('Executable-bit semantics differ on Windows')

    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
description: Skill with mixed script types
---

Use mixed scripts.
""")

    scripts_dir = skill_dir / 'scripts'
    scripts_dir.mkdir()

    shell_script = scripts_dir / 'deploy.sh'
    shell_script.write_text('#!/usr/bin/env bash\necho "deploy"\n')

    executable_script = scripts_dir / 'runner'
    executable_script.write_text('#!/usr/bin/env bash\necho "runner"\n')
    executable_script.chmod(0o755)

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 1
    assert skills[0].scripts is not None
    script_names = {s.name for s in skills[0].scripts}
    assert 'scripts/deploy.sh' in script_names
    assert 'scripts/runner' in script_names


def test_discover_skills_with_root_and_custom_executable_scripts(tmp_path: Path) -> None:
    """Test discovering executable scripts in skill root and with custom extension."""
    if sys.platform == 'win32':
        pytest.skip('Executable-bit semantics differ on Windows')

    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
description: Skill with root and custom executable scripts
---

Use mixed executable scripts.
""")

    root_script = skill_dir / 'bootstrap'
    root_script.write_text('#!/usr/bin/env sh\necho "boot"\n')
    root_script.chmod(0o755)

    scripts_dir = skill_dir / 'scripts'
    scripts_dir.mkdir()

    custom_extension_script = scripts_dir / 'run.custom'
    custom_extension_script.write_text('#!/usr/bin/env sh\necho "custom"\n')
    custom_extension_script.chmod(0o755)

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 1
    assert skills[0].scripts is not None
    script_names = {s.name for s in skills[0].scripts}
    assert 'bootstrap' in script_names
    assert 'scripts/run.custom' in script_names


def test_discover_skills_nested_directories(tmp_path: Path) -> None:
    """Test discovering skills in nested directories."""
    nested_dir = tmp_path / 'category' / 'subcategory' / 'test-skill'
    nested_dir.mkdir(parents=True)

    (nested_dir / 'SKILL.md').write_text("""---
name: nested-skill
description: Nested skill
---

Content.
""")

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 1
    assert skills[0].name == 'nested-skill'


def test_discover_skills_missing_name_with_validation(tmp_path: Path) -> None:
    """Test discovering skill missing name field with validation enabled."""
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
description: Missing name field
---

Content.
""")

    # With validation, missing name is an error
    with pytest.raises(ValueError, match='missing the required "name" field'):
        discover_skills(tmp_path, validate=True)


def test_discover_skills_missing_name_without_validation(tmp_path: Path) -> None:
    """Test discovering skill missing name field without validation."""
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
description: Missing name field
---

Content.
""")

    # Without validation, uses folder name
    skills = discover_skills(tmp_path, validate=False)
    assert len(skills) == 1
    assert skills[0].name == 'test-skill'  # Uses folder name


def test_discover_skills_nonexistent_directory(tmp_path: Path) -> None:
    """Test discovering skills from non-existent directory."""
    nonexistent = tmp_path / 'does-not-exist'

    # Should not raise, just log warning
    skills = discover_skills(nonexistent, validate=True)
    assert len(skills) == 0


def test_discover_skills_resources_subdirectory(tmp_path: Path) -> None:
    """Test discovering resources in resources/ subdirectory."""
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()

    (skill_dir / 'SKILL.md').write_text("""---
name: test-skill
description: Skill with resources subdirectory
---

Content.
""")

    resources_dir = skill_dir / 'resources'
    resources_dir.mkdir()
    (resources_dir / 'schema.json').write_text('{}')
    (resources_dir / 'template.txt').write_text('template')

    nested_dir = resources_dir / 'nested'
    nested_dir.mkdir()
    (nested_dir / 'data.csv').write_text('col1,col2')

    skills = discover_skills(tmp_path, validate=True)

    assert len(skills) == 1
    assert skills[0].resources is not None
    assert len(skills[0].resources) == 3

    resource_names = {r.name for r in skills[0].resources}
    assert 'resources/schema.json' in resource_names
    assert 'resources/template.txt' in resource_names
    assert 'resources/nested/data.csv' in resource_names


def _write_skill_with_sql(tmp_path: Path) -> Path:
    """Create a skill directory shipping a .sql resource and return the root."""
    skill_dir = tmp_path / 'sql-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: sql-skill
description: Skill shipping a SQL query
---

Read queries/report.sql for the query.
""")
    queries_dir = skill_dir / 'queries'
    queries_dir.mkdir()
    (queries_dir / 'report.sql').write_text('SELECT 1;')
    (skill_dir / 'notes.txt').write_text('notes')
    return tmp_path


def test_discover_skills_arbitrary_text_extension_by_default(tmp_path: Path) -> None:
    """Any readable text file is a resource by default, including .sql."""
    root = _write_skill_with_sql(tmp_path)

    skills = discover_skills(root, validate=True)

    assert len(skills) == 1
    resource_names = {r.name for r in skills[0].resources or []}
    assert 'queries/report.sql' in resource_names
    assert 'notes.txt' in resource_names


def test_discover_skills_skips_binary_files(tmp_path: Path) -> None:
    """Binary files (NUL byte) are not registered as resources."""
    root = _write_skill_with_sql(tmp_path)
    (root / 'sql-skill' / 'logo.png').write_bytes(b'\x89PNG\r\n\x00\x00binary')

    skills = discover_skills(root, validate=True)

    resource_names = {r.name for r in skills[0].resources or []}
    assert 'logo.png' not in resource_names


def test_discover_skills_rejects_invalid_utf8(tmp_path: Path) -> None:
    """A file that is not valid UTF-8 is skipped, even without a NUL byte.

    The loader reads resources as UTF-8, so discovery must reject anything it
    could not decode (here, a stray 0xFF byte the old NUL-only sniff missed).
    """
    root = _write_skill_with_sql(tmp_path)
    (root / 'sql-skill' / 'data.bin').write_bytes(b'\xff\xfe not utf-8')

    skills = discover_skills(root, validate=True)

    resource_names = {r.name for r in skills[0].resources or []}
    assert 'data.bin' not in resource_names
    assert 'notes.txt' in resource_names


def test_discover_skills_accepts_multibyte_utf8(tmp_path: Path) -> None:
    """Valid multibyte UTF-8 content is a resource and reads back intact."""
    skill_dir = tmp_path / 'unicode-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: unicode-skill
description: Skill with unicode content
---

See emoji.md.
""")
    (skill_dir / 'emoji.md').write_text('# café 🚀 日本語\n', encoding='utf-8')

    skills = discover_skills(tmp_path, validate=True)

    resource_names = {r.name for r in skills[0].resources or []}
    assert 'emoji.md' in resource_names


def test_discover_skills_excludes_scripts_from_resources(tmp_path: Path) -> None:
    """Files discovered as scripts are not also registered as resources."""
    skill_dir = tmp_path / 'script-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: script-skill
description: Skill with a script and a resource
---

Run run.py; read notes.md.
""")
    (skill_dir / 'run.py').write_text('print("hi")\n')
    (skill_dir / 'notes.md').write_text('# Notes\n')

    skills = discover_skills(tmp_path, validate=True)

    skill = skills[0]
    resource_names = {r.name for r in skill.resources or []}
    script_names = {s.name for s in skill.scripts or []}
    assert 'run.py' in script_names
    assert 'run.py' not in resource_names
    assert 'notes.md' in resource_names


def test_discover_skills_default_excludes_noise(tmp_path: Path) -> None:
    """__pycache__ and .DS_Store are excluded by the default patterns."""
    skill_dir = tmp_path / 'noisy-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text("""---
name: noisy-skill
description: Skill with noise files
---

Content.
""")
    (skill_dir / 'keep.txt').write_text('keep')
    (skill_dir / '.DS_Store').write_text('junk')
    pycache = skill_dir / '__pycache__'
    pycache.mkdir()
    (pycache / 'mod.cpython-312.pyc').write_text('cached')

    skills = discover_skills(tmp_path, validate=True)

    resource_names = {r.name for r in skills[0].resources or []}
    assert 'keep.txt' in resource_names
    assert '.DS_Store' not in resource_names
    assert not any(name.startswith('__pycache__/') for name in resource_names)


def test_discover_skills_exclude_resources_extends_defaults(tmp_path: Path) -> None:
    """User exclude patterns are additive; defaults still apply."""
    root = _write_skill_with_sql(tmp_path)
    (root / 'sql-skill' / '.DS_Store').write_text('junk')

    skills = discover_skills(root, validate=True, exclude_resources=['*.sql'])

    resource_names = {r.name for r in skills[0].resources or []}
    assert 'queries/report.sql' not in resource_names  # user pattern
    assert '.DS_Store' not in resource_names  # default still applied
    assert 'notes.txt' in resource_names


def test_skills_directory_exclude_resources(tmp_path: Path) -> None:
    """SkillsDirectory threads exclude_resources through to discovery."""
    root = _write_skill_with_sql(tmp_path)

    source = SkillsDirectory(path=root, exclude_resources=['queries/*.sql'])

    skills = list(source.skills.values())
    resource_names = {r.name for r in skills[0].resources or []}
    assert 'queries/report.sql' not in resource_names
    assert 'notes.txt' in resource_names


def test_skills_directory_missing_name_with_validation(tmp_path: Path) -> None:
    """SkillsDirectory with validate=True raises on a skill missing its name."""
    skill_dir = tmp_path / 'nameless'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('---\ndescription: No name\n---\n\nContent.\n')

    with pytest.raises(ValueError, match='missing the required "name" field'):
        SkillsDirectory(path=tmp_path, validate=True)


def test_skills_directory_missing_name_without_validation(tmp_path: Path) -> None:
    """SkillsDirectory with validate=False falls back to the directory name."""
    skill_dir = tmp_path / 'my-skill'
    skill_dir.mkdir()
    (skill_dir / 'SKILL.md').write_text('---\ndescription: No name\n---\n\nContent.\n')

    sd = SkillsDirectory(path=tmp_path, validate=False)
    skills = list(sd.get_skills().values())

    assert len(skills) == 1
    assert skills[0].name == 'my-skill'

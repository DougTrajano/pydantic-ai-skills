"""Tests for SkillsToolset.reload() and auto_reload functionality."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pydantic_ai_skills import Skill, SkillsToolset

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill(path: Path, name: str, description: str) -> None:
    """Write a minimal SKILL.md to *path/name/SKILL.md*."""
    skill_dir = path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nInstructions.\n'
    )


def _delete_skill(path: Path, name: str) -> None:
    """Remove the SKILL.md for *name* inside *path*."""
    (path / name / 'SKILL.md').unlink()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def skills_dir(tmp_path: Path) -> Path:
    """Temporary directory with a single pre-existing skill."""
    _write_skill(tmp_path, 'existing-skill', 'An existing skill')
    return tmp_path


# ---------------------------------------------------------------------------
# reload() — filesystem changes
# ---------------------------------------------------------------------------


def test_reload_picks_up_new_skill(skills_dir: Path) -> None:
    """A skill added after init is visible after reload()."""
    toolset = SkillsToolset(directories=[skills_dir])
    assert 'new-skill' not in toolset.skills

    _write_skill(skills_dir, 'new-skill', 'A brand new skill')
    toolset.reload()

    assert 'new-skill' in toolset.skills
    assert toolset.skills['new-skill'].description == 'A brand new skill'


def test_reload_removes_deleted_skill(skills_dir: Path) -> None:
    """A skill deleted after init is no longer present after reload()."""
    toolset = SkillsToolset(directories=[skills_dir])
    assert 'existing-skill' in toolset.skills

    _delete_skill(skills_dir, 'existing-skill')
    toolset.reload()

    assert 'existing-skill' not in toolset.skills


def test_reload_reflects_content_change(skills_dir: Path) -> None:
    """A changed description is picked up after reload()."""
    toolset = SkillsToolset(directories=[skills_dir])
    assert toolset.skills['existing-skill'].description == 'An existing skill'

    # Overwrite SKILL.md with a new description
    _write_skill(skills_dir, 'existing-skill', 'Updated description')
    toolset.reload()

    assert toolset.skills['existing-skill'].description == 'Updated description'


# ---------------------------------------------------------------------------
# reload() — programmatic skill preservation
# ---------------------------------------------------------------------------


def test_reload_preserves_programmatic_skills_from_param(skills_dir: Path) -> None:
    """Skills passed via skills=[] survive reload()."""
    prog_skill = Skill(name='prog-skill', description='Programmatic', content='Instructions')
    toolset = SkillsToolset(skills=[prog_skill], directories=[skills_dir])

    assert 'prog-skill' in toolset.skills
    toolset.reload()

    assert 'prog-skill' in toolset.skills
    assert toolset.skills['prog-skill'].description == 'Programmatic'


def test_reload_preserves_decorator_skills(tmp_path: Path) -> None:
    """Skills registered via @toolset.skill survive reload()."""
    toolset = SkillsToolset(directories=[tmp_path])

    @toolset.skill
    def my_decorator_skill() -> str:
        """A decorator-registered skill."""
        return 'Decorator skill instructions'

    assert 'my-decorator-skill' in toolset.skills
    toolset.reload()

    assert 'my-decorator-skill' in toolset.skills


def test_reload_programmatic_priority_over_directory(tmp_path: Path) -> None:
    """Programmatic skill wins over a same-named directory skill after reload()."""
    prog_skill = Skill(name='same-name', description='Programmatic version', content='Prog instructions')
    _write_skill(tmp_path, 'same-name', 'Directory version')

    toolset = SkillsToolset(skills=[prog_skill], directories=[tmp_path])

    # Programmatic skills have highest priority: on initial load, the programmatic
    # definition should win over the directory SKILL.md with the same name.
    assert 'same-name' in toolset.skills
    assert toolset.skills['same-name'].description == 'Programmatic version'
    assert toolset.skills['same-name'].content == 'Prog instructions'

    # After reload(), programmatic skills must still win over any directory-loaded
    # skills with the same name, proving they are re-applied and not overwritten.
    toolset.reload()

    assert 'same-name' in toolset.skills
    assert toolset.skills['same-name'].description == 'Programmatic version'
    assert toolset.skills['same-name'].content == 'Prog instructions'


def test_reload_no_skills_does_not_raise(tmp_path: Path) -> None:
    """reload() on a toolset with no sources works without errors."""
    toolset = SkillsToolset(skills=[])
    toolset.reload()  # should not raise

    assert toolset.skills == {}


# ---------------------------------------------------------------------------
# reload() — registry support
# ---------------------------------------------------------------------------


def test_reload_skips_registries_by_default(tmp_path: Path) -> None:
    """Registry.get_skills() is NOT called by reload() unless include_registries=True."""
    mock_registry = MagicMock()
    mock_registry.get_skills.return_value = []

    toolset = SkillsToolset(registries=[mock_registry])
    initial_call_count = mock_registry.get_skills.call_count

    toolset.reload()

    assert mock_registry.get_skills.call_count == initial_call_count


def test_reload_include_registries_calls_registry(tmp_path: Path) -> None:
    """Registry.get_skills() IS called when include_registries=True."""
    registry_skill = Skill(name='reg-skill', description='From registry', content='Reg instructions')
    mock_registry = MagicMock()
    mock_registry.get_skills.return_value = [registry_skill]

    toolset = SkillsToolset(registries=[mock_registry])
    initial_call_count = mock_registry.get_skills.call_count

    toolset.reload(include_registries=True)

    assert mock_registry.get_skills.call_count == initial_call_count + 1
    assert 'reg-skill' in toolset.skills


# ---------------------------------------------------------------------------
# auto_reload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_reload_picks_up_new_skill(skills_dir: Path) -> None:
    """With auto_reload=True, get_instructions() reflects a newly added skill."""
    toolset = SkillsToolset(directories=[skills_dir], auto_reload=True)
    assert 'auto-skill' not in toolset.skills

    _write_skill(skills_dir, 'auto-skill', 'Auto-reloaded skill')

    # Simulate ctx (get_instructions only uses ctx for the return value build,
    # not for reload logic; pass a MagicMock to satisfy the signature)
    ctx = MagicMock()
    instructions = await toolset.get_instructions(ctx)

    assert instructions is not None
    assert 'auto-skill' in instructions
    assert 'auto-skill' in toolset.skills


@pytest.mark.asyncio
async def test_auto_reload_false_does_not_rescan(skills_dir: Path) -> None:
    """With auto_reload=False (default), get_instructions() does NOT rescan."""
    toolset = SkillsToolset(directories=[skills_dir], auto_reload=False)

    _write_skill(skills_dir, 'late-skill', 'Added after init')

    ctx = MagicMock()
    instructions = await toolset.get_instructions(ctx)

    # late-skill was added after __init__ and auto_reload is off
    assert 'late-skill' not in toolset.skills
    # 'late-skill' should not appear in the instructions
    assert instructions is None or 'late-skill' not in instructions


@pytest.mark.asyncio
async def test_auto_reload_default_is_false(skills_dir: Path) -> None:
    """auto_reload defaults to False (no automatic rescan on get_instructions())."""
    toolset = SkillsToolset(directories=[skills_dir])

    # Add a new skill after initialization; with the default auto_reload behavior,
    # get_instructions() should not trigger a rescan.
    _write_skill(skills_dir, 'default-late-skill', 'Added after init with default auto_reload')

    ctx = MagicMock()
    instructions = await toolset.get_instructions(ctx)

    # default-late-skill was added after __init__ and auto_reload is off by default
    assert 'default-late-skill' not in toolset.skills
    # 'default-late-skill' should not appear in the instructions
    assert instructions is None or 'default-late-skill' not in instructions

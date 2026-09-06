"""Tests for the bundled-file layer: indexing a package and serving it to the model.

This is the half of the Agent Skills package that `pydantic-ai-harness` deliberately does
not touch — the `references/`, `assets/` and `scripts/` files a skill's instructions tell
the model to use.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic_ai import ModelRetry

from pydantic_ai_skills._toolset import SkillFilesToolset, _coerce_to_dict
from pydantic_ai_skills.packages import DEFAULT_RESOURCE_EXCLUDES, SkillPackage, index_libraries


def write_skill(library: Path, name: str = 'demo-skill') -> Path:
    """Create a minimal skill package and return its directory."""
    skill = library / name
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: A skill.\n---\n\nBody.\n')
    return skill


def ctx_with(*active: str) -> Any:
    """A stand-in RunContext exposing just the field the loaded-gate reads."""
    return SimpleNamespace(deps=None, active_capability_ids=set(active))


# ---------------------------------------------------------------------------
# index_libraries
# ---------------------------------------------------------------------------


def test_resources_are_keyed_by_relative_posix_path(tmp_path: Path) -> None:
    """The key is what a skill's instructions name, so it has to match the layout."""
    skill = write_skill(tmp_path)
    (skill / 'references').mkdir()
    (skill / 'references' / 'NOTES.md').write_text('the notes')
    (skill / 'TOP.md').write_text('top level')

    package = index_libraries([tmp_path])['demo-skill']

    assert sorted(package.resources_by_name) == ['TOP.md', 'references/NOTES.md']


def test_skill_md_is_never_a_resource(tmp_path: Path) -> None:
    """Its content already reaches the model as the skill's instructions."""
    write_skill(tmp_path)

    assert index_libraries([tmp_path])['demo-skill'].resources_by_name == {}


def test_binary_files_are_not_resources(tmp_path: Path) -> None:
    """Resources are read as UTF-8 text; a binary would fail at read time."""
    skill = write_skill(tmp_path)
    (skill / 'logo.png').write_bytes(b'\x89PNG\r\n\x1a\n\xff\xfe')

    assert index_libraries([tmp_path])['demo-skill'].resources_by_name == {}


@pytest.mark.parametrize('noise', DEFAULT_RESOURCE_EXCLUDES[:3])
def test_default_excludes_keep_noise_out(tmp_path: Path, noise: str) -> None:
    """Build artifacts would otherwise show up in the model's list of resources."""
    skill = write_skill(tmp_path)
    (skill / noise.replace('*', 'x')).write_text('noise')

    assert index_libraries([tmp_path])['demo-skill'].resources_by_name == {}


def test_extra_excludes_extend_rather_than_replace_the_defaults(tmp_path: Path) -> None:
    """A caller adding one pattern must not silently re-admit __pycache__."""
    skill = write_skill(tmp_path)
    (skill / '__pycache__').mkdir()
    (skill / '__pycache__' / 'x.txt').write_text('noise')
    (skill / 'draft.tmp').write_text('noise')
    (skill / 'keep.md').write_text('keep')

    package = index_libraries([tmp_path], exclude_resources=['*.tmp'])['demo-skill']

    assert sorted(package.resources_by_name) == ['keep.md']


def test_scripts_are_found_in_the_root_and_scripts_dir(tmp_path: Path) -> None:
    """Both layouts appear in published skill packages."""
    skill = write_skill(tmp_path)
    (skill / 'top.py').write_text('print("top")')
    (skill / 'scripts').mkdir()
    (skill / 'scripts' / 'nested.py').write_text('print("nested")')

    package = index_libraries([tmp_path])['demo-skill']

    assert sorted(package.scripts_by_name) == ['scripts/nested.py', 'top.py']


def test_a_file_is_never_both_a_script_and_a_resource(tmp_path: Path) -> None:
    """Otherwise the model sees one file offered by two tools that behave differently."""
    skill = write_skill(tmp_path)
    (skill / 'scripts').mkdir()
    (skill / 'scripts' / 'run.py').write_text('print("hi")')

    package = index_libraries([tmp_path])['demo-skill']

    assert sorted(package.scripts_by_name) == ['scripts/run.py']
    assert package.resources_by_name == {}


@pytest.mark.skipif(os.name == 'nt', reason='POSIX executable bit')
def test_an_executable_without_a_known_extension_is_a_script(tmp_path: Path) -> None:
    """Skill packages ship compiled helpers and extensionless shell scripts."""
    skill = write_skill(tmp_path)
    runner = skill / 'scripts'
    runner.mkdir()
    binary = runner / 'runner'
    binary.write_text('#!/bin/sh\necho hi\n')
    binary.chmod(0o755)

    assert 'scripts/runner' in index_libraries([tmp_path])['demo-skill'].scripts_by_name


@pytest.mark.skipif(sys.platform == 'win32', reason='symlinks need privileges on Windows')
def test_a_resource_symlink_escaping_the_skill_is_skipped(tmp_path: Path) -> None:
    """Otherwise a skill could hand the model any file the process can read."""
    outside = tmp_path / 'outside.txt'
    outside.write_text('secret')
    skill = write_skill(tmp_path / 'library')
    (skill / 'escape.md').symlink_to(outside)

    with pytest.warns(UserWarning, match='symlink escape'):
        package = index_libraries([tmp_path / 'library'])['demo-skill']

    assert package.resources_by_name == {}


@pytest.mark.skipif(sys.platform == 'win32', reason='symlinks need privileges on Windows')
def test_a_script_symlink_escaping_the_skill_is_skipped(tmp_path: Path) -> None:
    """The same containment rule, on the path that actually executes something."""
    outside = tmp_path / 'outside.py'
    outside.write_text('print("owned")')
    skill = write_skill(tmp_path / 'library')
    (skill / 'scripts').mkdir()
    (skill / 'scripts' / 'escape.py').symlink_to(outside)

    with pytest.warns(UserWarning, match='symlink escape'):
        package = index_libraries([tmp_path / 'library'])['demo-skill']

    assert package.scripts_by_name == {}


def test_a_missing_library_is_skipped_rather_than_raising(tmp_path: Path) -> None:
    """Harness validates library paths and reports them better than we could."""
    assert index_libraries([tmp_path / 'nope']) == {}


def test_later_libraries_win_on_a_duplicate_name(tmp_path: Path) -> None:
    """Matches the argument order the caller passed to harness."""
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    write_skill(first, 'shared')
    skill = write_skill(second, 'shared')
    (skill / 'ONLY_IN_SECOND.md').write_text('x')

    package = index_libraries([first, second])['shared']

    assert sorted(package.resources_by_name) == ['ONLY_IN_SECOND.md']


def test_a_programmatic_package_has_no_directory() -> None:
    """`${SKILL_DIR}` resolution is skipped for a skill with nothing on disk."""
    assert SkillPackage(name='in-python').directory is None


# ---------------------------------------------------------------------------
# SkillFilesToolset
# ---------------------------------------------------------------------------


@pytest.fixture
def toolset(tmp_path: Path) -> SkillFilesToolset:
    """A toolset over one skill with a resource and a script."""
    skill = write_skill(tmp_path)
    (skill / 'references').mkdir()
    (skill / 'references' / 'NOTES.md').write_text('the notes')
    (skill / 'scripts').mkdir()
    (skill / 'scripts' / 'hello.py').write_text('#!/usr/bin/env python3\nprint("hello")\n')
    return SkillFilesToolset(index_libraries([tmp_path]))


async def test_reading_a_resource_returns_its_content(toolset: SkillFilesToolset) -> None:
    """The happy path for a loaded skill."""
    resource = toolset.packages['demo-skill'].resources_by_name['references/NOTES.md']

    assert await resource.load(ctx=ctx_with('demo-skill'), args=None) == 'the notes'


async def test_an_unknown_skill_lists_what_is_available(toolset: SkillFilesToolset) -> None:
    """A retry the model can act on beats a bare failure."""
    ctx = ctx_with('demo-skill')

    with pytest.raises(ModelRetry, match='Skills with bundled files: demo-skill'):
        toolset._resolve_package(ctx, 'nope')


async def test_an_unloaded_skill_is_told_how_to_load_it(toolset: SkillFilesToolset) -> None:
    """The message has to name the tool and argument the model should use next."""
    ctx = ctx_with()

    with pytest.raises(ModelRetry, match=r"load_capability with id='demo-skill'"):
        toolset._resolve_package(ctx, 'demo-skill')


async def test_require_loaded_false_skips_the_gate(tmp_path: Path) -> None:
    """Opting out lets a skill's files be read without loading it first."""
    write_skill(tmp_path)
    (tmp_path / 'demo-skill' / 'NOTES.md').write_text('the notes')
    ungated = SkillFilesToolset(index_libraries([tmp_path]), require_loaded=False)

    assert ungated._resolve_package(ctx_with(), 'demo-skill').name == 'demo-skill'


def test_a_toolset_can_register_neither_tool() -> None:
    """`SkillsCapability` never builds this, but the toolset must not assume so."""
    assert SkillFilesToolset({}, resources=False, scripts=False).tools == {}


# ---------------------------------------------------------------------------
# name resolution -- models name a script the way the instructions' prose does
# ---------------------------------------------------------------------------


def test_an_exact_name_resolves(toolset: SkillFilesToolset) -> None:
    """The indexed path is always the primary key."""
    scripts = toolset.packages['demo-skill'].scripts_by_name
    resolved = toolset._resolve_file('Script', 'scripts/hello.py', scripts, 'demo-skill')

    assert resolved.name == 'scripts/hello.py'


@pytest.mark.parametrize('requested', ['hello', 'hello.py'])
def test_a_unique_shorthand_resolves(toolset: SkillFilesToolset, requested: str) -> None:
    """`scripts/hello.py` is reachable as `hello`, so a first guess is not wasted."""
    scripts = toolset.packages['demo-skill'].scripts_by_name
    resolved = toolset._resolve_file('Script', requested, scripts, 'demo-skill')

    assert resolved.name == 'scripts/hello.py'


def test_a_resource_shorthand_resolves(toolset: SkillFilesToolset) -> None:
    """Resources take the same shorthand as scripts."""
    resources = toolset.packages['demo-skill'].resources_by_name
    resolved = toolset._resolve_file('Resource', 'NOTES.md', resources, 'demo-skill')

    assert resolved.name == 'references/NOTES.md'


def test_an_ambiguous_shorthand_names_the_candidates(tmp_path: Path) -> None:
    """Two files sharing a name must not resolve to whichever sorted first."""
    skill = write_skill(tmp_path)
    (skill / 'references').mkdir()
    (skill / 'references' / 'NOTES.md').write_text('nested')
    (skill / 'NOTES.md').write_text('top level')
    toolset = SkillFilesToolset(index_libraries([tmp_path]))
    resources = toolset.packages['demo-skill'].resources_by_name

    with pytest.raises(ModelRetry, match=r"'NOTES' is ambiguous.*NOTES\.md.*references/NOTES\.md"):
        toolset._resolve_file('Resource', 'NOTES', resources, 'demo-skill')


def test_an_unmatched_name_lists_what_is_available(toolset: SkillFilesToolset) -> None:
    """Shorthand matching must not swallow the retry that lists the real names."""
    scripts = toolset.packages['demo-skill'].scripts_by_name

    with pytest.raises(ModelRetry, match=r"Script 'deploy' not found.*scripts/hello\.py"):
        toolset._resolve_file('Script', 'deploy', scripts, 'demo-skill')


def test_a_shorthand_never_escapes_the_index(toolset: SkillFilesToolset) -> None:
    """Resolution is a comparison against indexed names, never a path built from input."""
    scripts = toolset.packages['demo-skill'].scripts_by_name

    with pytest.raises(ModelRetry, match='not found'):
        toolset._resolve_file('Script', '../../etc/passwd', scripts, 'demo-skill')


# ---------------------------------------------------------------------------
# args coercion -- models routinely send a JSON string instead of an object
# ---------------------------------------------------------------------------


def test_a_json_object_string_is_coerced() -> None:
    """Several providers stringify nested tool arguments."""
    assert _coerce_to_dict('{"query": "x"}') == {'query': 'x'}


def test_a_dict_passes_through_unchanged() -> None:
    """Coercion must not disturb the normal case."""
    assert _coerce_to_dict({'query': 'x'}) == {'query': 'x'}


def test_none_passes_through_unchanged() -> None:
    """Most resources take no arguments at all."""
    assert _coerce_to_dict(None) is None


def test_invalid_json_reports_where_it_broke() -> None:
    """A bare JSONDecodeError tells the model nothing it can fix."""
    with pytest.raises(ValueError, match='Invalid JSON string'):
        _coerce_to_dict('{not json')


def test_a_json_scalar_is_rejected() -> None:
    """Valid JSON that is not an object still cannot be tool arguments."""
    with pytest.raises(ValueError, match='args must be a JSON object'):
        _coerce_to_dict('[1, 2]')

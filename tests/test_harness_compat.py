"""Compatibility guards for the `pydantic-ai-harness` surface this package builds on.

`SkillsCapability` hands Agent Skills discovery, `SKILL.md` validation and instruction
rendering to harness's `Skills`, then re-emits the leaves it produces with bundled-file
tools and `${SKILL_DIR}` resolution attached. That makes a handful of harness behaviours
load-bearing here — and harness is on 0.x releases, where its own README says the API may
change between minor releases. It did in 0.52, which moved discovery from construction to
the start of each run; the helpers in `tests/_harness.py` read the catalog a run sees under
either shape.

These tests pin exactly what this package depends on, so an upstream change fails loudly
with a clear pointer instead of surfacing as an obscure error deep inside a run. None of
them touch a private (`_`-prefixed) harness module: if one starts failing, the fix is to
adapt `capability.py`, not to reach further into harness.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai_harness import Skills

from pydantic_ai_skills._parsing import validate_skill_name
from tests._harness import (
    HARNESS_DISCOVERS_PER_RUN,
    harness_leaves,
    harness_names,
    harness_skills,
    instruction_parts,
    run_context,
)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A one-skill library."""
    skill = tmp_path / 'demo-skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: A demo skill.\n---\n\nThe body.\n')
    return tmp_path


def test_skills_is_importable_from_the_package_root() -> None:
    """`capability.py` imports `Skills` from the top-level namespace."""
    from pydantic_ai_harness import Skills as Exported  # noqa: F401


def test_skills_constructor_signature() -> None:
    """`SkillsCapability` passes `directories` positionally with keyword `include`/`exclude`."""
    parameters = inspect.signature(Skills.__init__).parameters

    assert 'directories' in parameters
    assert parameters['include'].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters['exclude'].kind is inspect.Parameter.KEYWORD_ONLY


def test_skills_accepts_a_sequence_of_directories(tmp_path: Path) -> None:
    """Local libraries and synced registries are concatenated into one list."""
    first = tmp_path / 'first' / 'alpha'
    second = tmp_path / 'second' / 'beta'
    for skill in (first, second):
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text(f'---\nname: {skill.name}\ndescription: A skill.\n---\n\nBody.\n')

    assert sorted(leaf.id for leaf in harness_leaves([first.parent, second.parent])) == ['alpha', 'beta']


def test_apply_yields_one_capability_per_skill(library: Path) -> None:
    """`SkillsCapability` collects these leaves and re-emits them."""
    leaves = harness_leaves(library)

    assert len(leaves) == 1
    assert isinstance(leaves[0], AbstractCapability)
    assert not isinstance(leaves[0], Skills)


def test_a_leaf_exposes_the_attributes_we_rebuild_from(library: Path) -> None:
    """Rebuilding a leaf for `${SKILL_DIR}` resolution reads exactly these."""
    leaf = harness_leaves(library)[0]

    assert leaf.id == 'demo-skill'
    assert leaf.get_description() == 'A demo skill.'
    assert leaf.defer_loading is True


def test_leaf_instructions_are_plain_strings(library: Path) -> None:
    """Placeholder substitution rewrites these strings and passes them back to `Capability`.

    harness renders a list of strings before 0.52 and a single string from 0.52. A richer
    instruction type would make `_rebuild_leaf` fall through to returning the leaf
    untouched, silently disabling `${SKILL_DIR}` resolution.
    """
    instructions = harness_leaves(library)[0].get_instructions()

    if isinstance(instructions, str):
        return
    assert isinstance(instructions, list)
    assert all(isinstance(part, str) for part in instructions)


def test_leaf_id_equals_the_directory_name(library: Path) -> None:
    """The bundled-file index is keyed by directory name and looked up by leaf id.

    If harness ever derived ids differently, `read_skill_resource` would stop finding
    packages for skills that are on the model's catalog.
    """
    assert harness_leaves(library)[0].id == 'demo-skill'


def test_instructions_carry_the_skill_heading(library: Path) -> None:
    """Programmatic skills mirror this format so both kinds read alike to the model."""
    assert instruction_parts(harness_leaves(library)[0]) == ['# Skill: demo-skill\n\nThe body.']


def test_only_immediate_children_are_discovered(tmp_path: Path) -> None:
    """`index_libraries` mirrors this rule; a change would desynchronize the two."""
    nested = tmp_path / 'outer' / 'inner'
    nested.mkdir(parents=True)
    (nested / 'SKILL.md').write_text('---\nname: inner\ndescription: Too deep.\n---\n\nBody.\n')

    assert harness_names(tmp_path) == []


def test_include_and_exclude_reject_unknown_names(library: Path) -> None:
    """`SkillsCapability` narrows the selection to names harness knows for this reason."""
    with pytest.raises(ValueError, match='Unknown skill in include'):
        harness_leaves(library, include=['not-a-skill'])


def test_a_name_this_package_generates_is_accepted(tmp_path: Path) -> None:
    """`validate_skill_name` mirrors harness's rule; this pins the two together.

    Prefixed and renamed registries stage directories under names this package produces,
    so a rule that drifted would only surface once a composed registry reached an agent.
    """
    name = validate_skill_name('vendor-pdf-tools', context='test')
    skill = tmp_path / name
    skill.mkdir()
    (skill / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: A skill.\n---\n\nBody.\n')

    assert harness_names(tmp_path) == [name]


def test_frontmatter_name_must_match_the_directory(tmp_path: Path) -> None:
    """Why prefixing and renaming rewrite the `name` key rather than only moving files.

    Before 0.52 harness rejects the library; from 0.52 it skips the skill with a warning,
    so a model-edited skill cannot take the others down with it.
    """
    skill = tmp_path / 'on-disk'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: different\ndescription: A skill.\n---\n\nBody.\n')

    if HARNESS_DISCOVERS_PER_RUN:
        with pytest.warns(UserWarning, match='must match its parent directory'):
            assert harness_names(tmp_path) == []
    else:
        with pytest.raises(ValueError, match='must match its parent directory'):
            harness_names(tmp_path)


def test_a_missing_name_key_is_derived_from_the_directory(tmp_path: Path) -> None:
    """`rewrite_skill_name` leaves a nameless frontmatter alone because of this."""
    skill = tmp_path / 'derived-name'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\ndescription: A skill.\n---\n\nBody.\n')

    assert harness_names(tmp_path) == ['derived-name']


def test_a_library_that_is_itself_a_skill_is_rejected(tmp_path: Path) -> None:
    """Registries must return the parent of the skill packages, not a package."""
    (tmp_path / 'SKILL.md').write_text('---\nname: whoops\ndescription: A skill.\n---\n\nBody.\n')

    with pytest.raises(ValueError, match='points to a skill package'):
        harness_leaves(tmp_path)


def test_bundled_files_are_not_loaded(tmp_path: Path) -> None:
    """The gap this package exists to fill.

    If harness ever started loading `references/` and `scripts/`, the two implementations
    would overlap and `SkillsCapability` would need to stop adding its own file tools.
    """
    skill = tmp_path / 'demo-skill'
    (skill / 'references').mkdir(parents=True)
    (skill / 'references' / 'NOTES.md').write_text('the notes')
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: A skill.\n---\n\nBody.\n')

    leaves = harness_leaves(tmp_path)

    # `Capability.get_toolset()` always returns a (here empty) FunctionToolset, so the
    # assertion is that harness contributes no tools -- not that it contributes nothing.
    toolset = leaves[0].get_toolset()
    assert toolset is None or not toolset.tools
    assert 'the notes' not in str(leaves[0].get_instructions())


def test_skill_dir_placeholders_are_left_in_place(tmp_path: Path) -> None:
    """The other gap: `SkillsCapability` resolves what harness deliberately leaves alone."""
    skill = tmp_path / 'demo-skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text(
        '---\nname: demo-skill\ndescription: A skill.\n---\n\nRun ${SKILL_DIR}/scripts/go.py\n'
    )

    assert '${SKILL_DIR}' in str(harness_leaves(tmp_path)[0].get_instructions())


@pytest.mark.skipif(not HARNESS_DISCOVERS_PER_RUN, reason='harness <0.52 scans libraries during construction')
def test_skills_reads_an_explicit_workspace_without_the_runs(library: Path) -> None:
    """`SkillsCapability` passes harness a local backend, so a run needs no workspace of its own.

    If harness started requiring `ctx.workspace` even with `workspace=` set, every existing
    caller that only passes directories would fail at run start.
    """
    from pydantic_ai.workspaces import LocalWorkspaceBackend

    parameters = inspect.signature(Skills.__init__).parameters
    assert parameters['workspace'].kind is inspect.Parameter.KEYWORD_ONLY

    skills = Skills(library, workspace=LocalWorkspaceBackend(Path.cwd()))
    assert leaves_of(skills) == [skills]

    resolved = asyncio.run(skills.for_run(run_context()))
    assert sorted(leaf.id for leaf in leaves_of(resolved)) == ['demo-skill']


def leaves_of(capability: AbstractCapability[Any]) -> list[Any]:
    """The capabilities `apply` visits."""
    leaves: list[Any] = []
    capability.apply(leaves.append)
    return leaves


@pytest.mark.skipif(not HARNESS_DISCOVERS_PER_RUN, reason='harness <0.52 scans libraries during construction')
async def test_for_run_returns_skills_itself_when_nothing_is_selected(library: Path) -> None:
    """`SkillsCapability._harness_leaves` filters this out rather than re-emitting it as a skill."""
    skills = harness_skills(library, include=[])

    assert await skills.for_run(run_context()) is skills

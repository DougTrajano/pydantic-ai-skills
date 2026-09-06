"""Compatibility guards for the `pydantic-ai-harness` surface this package builds on.

`SkillsCapability` hands Agent Skills discovery, `SKILL.md` validation and instruction
rendering to harness's `Skills`, then re-emits the leaves it produces with bundled-file
tools and `${SKILL_DIR}` resolution attached. That makes a handful of harness behaviours
load-bearing here — and harness is on 0.x releases, where its own README says the API may
change between minor releases.

These tests pin exactly what this package depends on, so an upstream change fails loudly
with a clear pointer instead of surfacing as an obscure error deep inside a run. None of
them touch a private (`_`-prefixed) harness module: if one starts failing, the fix is to
adapt `capability.py`, not to reach further into harness.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai.capabilities import Capability
from pydantic_ai_harness import Skills

from pydantic_ai_skills._parsing import validate_skill_name


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

    assert leaf_ids(Skills([first.parent, second.parent])) == ['alpha', 'beta']


def leaf_ids(skills: Skills[Any]) -> list[str]:
    """Ids of the leaves `Skills.apply` yields."""
    leaves: list[Any] = []
    skills.apply(leaves.append)
    return sorted(leaf.id for leaf in leaves)


def test_apply_yields_one_capability_per_skill(library: Path) -> None:
    """`SkillsCapability` collects these leaves and re-emits them."""
    leaves: list[Any] = []
    Skills(library).apply(leaves.append)

    assert len(leaves) == 1
    assert isinstance(leaves[0], Capability)


def test_a_leaf_exposes_the_attributes_we_rebuild_from(library: Path) -> None:
    """Rebuilding a leaf for `${SKILL_DIR}` resolution reads exactly these."""
    leaves: list[Any] = []
    Skills(library).apply(leaves.append)
    leaf = leaves[0]

    assert leaf.id == 'demo-skill'
    assert leaf.get_description() == 'A demo skill.'
    assert leaf.defer_loading is True


def test_leaf_instructions_are_a_list_of_plain_strings(library: Path) -> None:
    """Placeholder substitution rewrites these strings and passes them back to `Capability`.

    A richer instruction type would make `_rebuild_leaf` fall through to returning the
    leaf untouched, silently disabling `${SKILL_DIR}` resolution.
    """
    leaves: list[Any] = []
    Skills(library).apply(leaves.append)
    instructions = leaves[0].get_instructions()

    assert isinstance(instructions, list)
    assert all(isinstance(part, str) for part in instructions)


def test_leaf_id_equals_the_directory_name(library: Path) -> None:
    """The bundled-file index is keyed by directory name and looked up by leaf id.

    If harness ever derived ids differently, `read_skill_resource` would stop finding
    packages for skills that are on the model's catalog.
    """
    leaves: list[Any] = []
    Skills(library).apply(leaves.append)

    assert leaves[0].id == 'demo-skill'


def test_instructions_carry_the_skill_heading(library: Path) -> None:
    """Programmatic skills mirror this format so both kinds read alike to the model."""
    leaves: list[Any] = []
    Skills(library).apply(leaves.append)

    assert leaves[0].get_instructions() == ['# Skill: demo-skill\n\nThe body.']


def test_only_immediate_children_are_discovered(tmp_path: Path) -> None:
    """`index_libraries` mirrors this rule; a change would desynchronize the two."""
    nested = tmp_path / 'outer' / 'inner'
    nested.mkdir(parents=True)
    (nested / 'SKILL.md').write_text('---\nname: inner\ndescription: Too deep.\n---\n\nBody.\n')

    assert leaf_ids(Skills(tmp_path)) == []


def test_include_and_exclude_reject_unknown_names(library: Path) -> None:
    """`SkillsCapability` narrows the selection to names harness knows for this reason."""
    with pytest.raises(ValueError, match='Unknown skill in include'):
        Skills(library, include=['not-a-skill'])


def test_a_name_this_package_generates_is_accepted(tmp_path: Path) -> None:
    """`validate_skill_name` mirrors harness's rule; this pins the two together.

    Prefixed and renamed registries stage directories under names this package produces,
    so a rule that drifted would only surface once a composed registry reached an agent.
    """
    name = validate_skill_name('vendor-pdf-tools', context='test')
    skill = tmp_path / name
    skill.mkdir()
    (skill / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: A skill.\n---\n\nBody.\n')

    assert leaf_ids(Skills(tmp_path)) == [name]


def test_frontmatter_name_must_match_the_directory(tmp_path: Path) -> None:
    """Why prefixing and renaming rewrite the `name` key rather than only moving files."""
    skill = tmp_path / 'on-disk'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: different\ndescription: A skill.\n---\n\nBody.\n')

    with pytest.raises(ValueError, match='must match its parent directory'):
        Skills(tmp_path)


def test_a_missing_name_key_is_derived_from_the_directory(tmp_path: Path) -> None:
    """`rewrite_skill_name` leaves a nameless frontmatter alone because of this."""
    skill = tmp_path / 'derived-name'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\ndescription: A skill.\n---\n\nBody.\n')

    assert leaf_ids(Skills(tmp_path)) == ['derived-name']


def test_a_library_that_is_itself_a_skill_is_rejected(tmp_path: Path) -> None:
    """Registries must return the parent of the skill packages, not a package."""
    (tmp_path / 'SKILL.md').write_text('---\nname: whoops\ndescription: A skill.\n---\n\nBody.\n')

    with pytest.raises(ValueError, match='points to a skill package'):
        Skills(tmp_path)


def test_bundled_files_are_not_loaded(tmp_path: Path) -> None:
    """The gap this package exists to fill.

    If harness ever started loading `references/` and `scripts/`, the two implementations
    would overlap and `SkillsCapability` would need to stop adding its own file tools.
    """
    skill = tmp_path / 'demo-skill'
    (skill / 'references').mkdir(parents=True)
    (skill / 'references' / 'NOTES.md').write_text('the notes')
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: A skill.\n---\n\nBody.\n')

    leaves: list[Any] = []
    Skills(tmp_path).apply(leaves.append)

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

    leaves: list[Any] = []
    Skills(tmp_path).apply(leaves.append)

    assert '${SKILL_DIR}' in str(leaves[0].get_instructions())

"""Tests for registry composition.

A registry's contract in v2 is one method: `sync()` returns a local skill-library
directory. The composition wrappers therefore present a *different* library than the one
they wrap, which means staging real directories rather than mapping objects in memory.
These tests pin that the staged output is something harness will actually accept.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from pydantic_ai_harness import Skills

from pydantic_ai_skills import SkillsCapability
from pydantic_ai_skills.registries import (
    CombinedRegistry,
    FilteredRegistry,
    LocalSkillsRegistry,
    SkillRegistry,
    WrapperRegistry,
)


def write_skill(library: Path, name: str, *, description: str | None = None, declare_name: bool = True) -> Path:
    """Create a skill package under `library` and return its directory."""
    skill = library / name
    skill.mkdir(parents=True, exist_ok=True)
    declared = f'name: {name}\n' if declare_name else ''
    (skill / 'SKILL.md').write_text(
        f'---\n{declared}description: {description or f"The {name} skill."}\n---\n\nBody.\n'
    )
    return skill


def library_names(library: Path) -> list[str]:
    """Names of the skill packages in a library, sorted."""
    return sorted(child.name for child in library.iterdir() if (child / 'SKILL.md').is_file())


def harness_names(library: Path) -> list[str]:
    """What harness would actually call the skills in `library`.

    The real assertion for a staged library: harness both accepts it and agrees with the
    directory names we chose.
    """
    leaves: list[object] = []
    Skills(library).apply(leaves.append)
    return sorted(leaf.id for leaf in leaves)  # type: ignore[attr-defined]


@pytest.fixture
def source(tmp_path: Path) -> LocalSkillsRegistry:
    """A registry over a library holding three skills, one with a bundled file."""
    library = tmp_path / 'source'
    write_skill(library, 'pdf-tools', description='Work with PDF documents.')
    write_skill(library, 'web-research', description='Search the web.')
    skill = write_skill(library, 'data-analysis', description='Analyze datasets.')
    (skill / 'references').mkdir()
    (skill / 'references' / 'NOTES.md').write_text('the notes')
    return LocalSkillsRegistry(library)


# ---------------------------------------------------------------------------
# LocalSkillsRegistry
# ---------------------------------------------------------------------------


def test_local_registry_returns_its_directory(source: LocalSkillsRegistry) -> None:
    """A local library needs no fetching, so sync just hands it back."""
    assert library_names(source.sync()) == ['data-analysis', 'pdf-tools', 'web-research']


def test_local_registry_rejects_a_missing_directory(tmp_path: Path) -> None:
    """Failing here beats a confusing error from harness later."""
    registry = LocalSkillsRegistry(tmp_path / 'nope')

    with pytest.raises(ValueError, match='does not exist'):
        registry.sync()


def test_local_registry_rejects_a_file(tmp_path: Path) -> None:
    """A library is a directory of skill packages, not a file."""
    a_file = tmp_path / 'a-file'
    a_file.write_text('not a directory')

    registry = LocalSkillsRegistry(a_file)

    with pytest.raises(ValueError, match='not a directory'):
        registry.sync()


def test_skill_names_reads_the_synced_library(source: LocalSkillsRegistry) -> None:
    """Callers can inspect a registry without building an agent."""
    assert source.skill_names() == ['data-analysis', 'pdf-tools', 'web-research']


def test_skill_infos_carry_the_description(source: LocalSkillsRegistry) -> None:
    """The description is what a filter predicate usually matches on."""
    infos = {info.name: info for info in source.skill_infos()}

    assert infos['pdf-tools'].description == 'Work with PDF documents.'
    assert infos['pdf-tools'].directory.name == 'pdf-tools'


# ---------------------------------------------------------------------------
# WrapperRegistry
# ---------------------------------------------------------------------------


def test_wrapper_delegates_sync(source: LocalSkillsRegistry) -> None:
    """The base wrapper is pure delegation; subclasses override what they change."""
    assert WrapperRegistry(wrapped=source).sync() == source.sync()


def test_a_custom_registry_only_has_to_implement_sync(tmp_path: Path) -> None:
    """The ABC is deliberately one method wide."""
    library = tmp_path / 'custom'
    write_skill(library, 'custom-skill')

    class MyRegistry(SkillRegistry):
        def sync(self) -> Path:
            return library

    assert MyRegistry().skill_names() == ['custom-skill']


# ---------------------------------------------------------------------------
# FilteredRegistry
# ---------------------------------------------------------------------------


def test_filtered_stages_only_matching_skills(source: LocalSkillsRegistry) -> None:
    """Only matching packages are copied into the staged library."""
    staged = FilteredRegistry(wrapped=source, predicate=lambda info: 'data' in info.name).sync()

    assert library_names(staged) == ['data-analysis']
    assert harness_names(staged) == ['data-analysis']


def test_filtered_can_match_on_description(source: LocalSkillsRegistry) -> None:
    """Predicates see the description, not just the name."""
    staged = source.filtered(lambda info: 'PDF' in info.description).sync()

    assert library_names(staged) == ['pdf-tools']


def test_filtered_leaves_the_source_untouched(source: LocalSkillsRegistry) -> None:
    """Composition is a view: the wrapped registry is never modified."""
    source.filtered(lambda info: False).sync()

    assert library_names(source.sync()) == ['data-analysis', 'pdf-tools', 'web-research']


def test_filtered_copies_bundled_files(source: LocalSkillsRegistry) -> None:
    """Filtering must not quietly drop a skill's references or scripts."""
    staged = source.filtered(lambda info: info.name == 'data-analysis').sync()

    assert (staged / 'data-analysis' / 'references' / 'NOTES.md').read_text() == 'the notes'


def test_filtered_matching_nothing_yields_an_empty_library(source: LocalSkillsRegistry) -> None:
    """An empty library is valid, and harness accepts it."""
    staged = source.filtered(lambda info: False).sync()

    assert library_names(staged) == []
    assert harness_names(staged) == []


def test_filtered_stages_into_a_requested_directory(source: LocalSkillsRegistry, tmp_path: Path) -> None:
    """A caller can pin where a composed library lands instead of using a temp dir."""
    target = tmp_path / 'staged'

    staged = source.filtered(
        lambda info: info.name == 'pdf-tools',
    ).sync()
    assert staged != target  # sanity: the default is a temporary directory

    staged = FilteredRegistry(
        wrapped=source,
        predicate=lambda info: info.name == 'pdf-tools',
        target_dir=target,
    ).sync()

    assert staged == target.resolve()
    assert library_names(staged) == ['pdf-tools']


def test_resyncing_a_target_directory_drops_stale_skills(source: LocalSkillsRegistry, tmp_path: Path) -> None:
    """A narrowed filter must not leave the previous run's skills behind."""
    target = tmp_path / 'staged'
    FilteredRegistry(wrapped=source, predicate=lambda info: True, target_dir=target).sync()
    assert len(library_names(target)) == 3

    staged = FilteredRegistry(
        wrapped=source,
        predicate=lambda info: info.name == 'pdf-tools',
        target_dir=target,
    ).sync()

    assert library_names(staged) == ['pdf-tools']


# ---------------------------------------------------------------------------
# PrefixedRegistry
# ---------------------------------------------------------------------------


def test_prefixed_renames_the_directories(source: LocalSkillsRegistry) -> None:
    """Skills are named after their directory, so prefixing renames it."""
    staged = source.prefixed('vendor-').sync()

    assert library_names(staged) == ['vendor-data-analysis', 'vendor-pdf-tools', 'vendor-web-research']


def test_prefixed_rewrites_the_frontmatter_name(source: LocalSkillsRegistry) -> None:
    """Harness rejects a SKILL.md whose `name` disagrees with its directory.

    Without the rewrite, prefixing would produce a library harness refuses outright.
    """
    staged = source.prefixed('vendor-').sync()

    assert 'name: vendor-pdf-tools' in (staged / 'vendor-pdf-tools' / 'SKILL.md').read_text()
    assert harness_names(staged) == ['vendor-data-analysis', 'vendor-pdf-tools', 'vendor-web-research']


def test_prefixed_handles_a_skill_md_without_a_name_key(tmp_path: Path) -> None:
    """Harness derives the name from the directory, so there is nothing to rewrite."""
    library = tmp_path / 'source'
    write_skill(library, 'nameless', declare_name=False)

    staged = LocalSkillsRegistry(library).prefixed('vendor-').sync()

    assert harness_names(staged) == ['vendor-nameless']


def test_prefixed_rejects_a_prefix_that_yields_an_invalid_name(source: LocalSkillsRegistry) -> None:
    """Failing here names the prefix; failing inside harness would not."""
    registry = source.prefixed('Vendor_')

    with pytest.raises(ValueError, match='Prefixing'):
        registry.sync()


def test_prefixed_copies_bundled_files(source: LocalSkillsRegistry) -> None:
    """Prefixing must not quietly drop a skill's references or scripts."""
    staged = source.prefixed('vendor-').sync()

    assert (staged / 'vendor-data-analysis' / 'references' / 'NOTES.md').read_text() == 'the notes'


# ---------------------------------------------------------------------------
# RenamedRegistry
# ---------------------------------------------------------------------------


def test_renamed_maps_the_named_skills(source: LocalSkillsRegistry) -> None:
    """A mapped skill is staged, and named, under its new name."""
    staged = source.renamed({'documents': 'pdf-tools'}).sync()

    assert library_names(staged) == ['data-analysis', 'documents', 'web-research']
    assert harness_names(staged) == ['data-analysis', 'documents', 'web-research']


def test_renamed_leaves_unmapped_skills_alone(source: LocalSkillsRegistry) -> None:
    """Skills the map does not mention keep their original name."""
    staged = source.renamed({'documents': 'pdf-tools'}).sync()

    assert 'name: web-research' in (staged / 'web-research' / 'SKILL.md').read_text()


def test_renamed_rejects_an_unknown_original(source: LocalSkillsRegistry) -> None:
    """A typo in the map is a configuration error, not a silent no-op."""
    registry = source.renamed({'new-name': 'nope'})

    with pytest.raises(ValueError, match='Unknown skill in name_map: nope'):
        registry.sync()


def test_renamed_rejects_an_invalid_new_name(source: LocalSkillsRegistry) -> None:
    """The new name still has to be one harness accepts."""
    registry = source.renamed({'Bad_Name': 'pdf-tools'})

    with pytest.raises(ValueError, match='Renaming'):
        registry.sync()


def test_renamed_rejects_a_collision(source: LocalSkillsRegistry) -> None:
    """Renaming onto an existing name would hand harness a duplicate."""
    registry = source.renamed({'web-research': 'pdf-tools'})

    with pytest.raises(ValueError, match='the same name'):
        registry.sync()


# ---------------------------------------------------------------------------
# CombinedRegistry
# ---------------------------------------------------------------------------


def test_combined_merges_libraries(tmp_path: Path) -> None:
    """Both registries' skills end up in one library harness can read."""
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    write_skill(first, 'alpha')
    write_skill(second, 'beta')

    staged = CombinedRegistry(registries=[LocalSkillsRegistry(first), LocalSkillsRegistry(second)]).sync()

    assert library_names(staged) == ['alpha', 'beta']
    assert harness_names(staged) == ['alpha', 'beta']


def test_combined_prefers_the_earlier_registry_and_warns(tmp_path: Path) -> None:
    """Silently merging would make the catalog depend on directory iteration order."""
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    write_skill(first, 'shared', description='From the first registry.')
    write_skill(second, 'shared', description='From the second registry.')

    combined = CombinedRegistry(registries=[LocalSkillsRegistry(first), LocalSkillsRegistry(second)])
    with pytest.warns(UserWarning, match='provided by more than one registry'):
        staged = combined.sync()

    assert library_names(staged) == ['shared']
    assert 'From the first registry.' in (staged / 'shared' / 'SKILL.md').read_text()


def test_or_operator_builds_a_combined_registry(tmp_path: Path) -> None:
    """The `|` operator is shorthand for CombinedRegistry."""
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    write_skill(first, 'alpha')
    write_skill(second, 'beta')

    combined = LocalSkillsRegistry(first) | LocalSkillsRegistry(second)

    assert isinstance(combined, CombinedRegistry)
    assert library_names(combined.sync()) == ['alpha', 'beta']


# ---------------------------------------------------------------------------
# Chaining
# ---------------------------------------------------------------------------


def test_filtered_then_prefixed(source: LocalSkillsRegistry) -> None:
    """Wrappers chain, each staging from the previous one's output."""
    staged = source.filtered(lambda info: 'pdf' in info.name).prefixed('vendor-').sync()

    assert harness_names(staged) == ['vendor-pdf-tools']


def test_prefixed_then_filtered(source: LocalSkillsRegistry) -> None:
    """The predicate sees the prefixed names, because filtering runs on the staged library."""
    staged = source.prefixed('vendor-').filtered(lambda info: info.name == 'vendor-pdf-tools').sync()

    assert harness_names(staged) == ['vendor-pdf-tools']


def test_renamed_then_prefixed(source: LocalSkillsRegistry) -> None:
    """A renamed skill can be prefixed again further down the chain."""
    staged = source.renamed({'documents': 'pdf-tools'}).prefixed('vendor-').sync()

    assert 'vendor-documents' in harness_names(staged)


def test_combined_with_prefixes_exposes_both_sides_of_a_collision(tmp_path: Path) -> None:
    """The documented escape hatch when two registries ship the same skill name."""
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    write_skill(first, 'shared')
    write_skill(second, 'shared')

    combined = LocalSkillsRegistry(first).prefixed('a-') | LocalSkillsRegistry(second).prefixed('b-')

    with warnings.catch_warnings():
        warnings.simplefilter('error')
        staged = combined.sync()

    assert harness_names(staged) == ['a-shared', 'b-shared']


# ---------------------------------------------------------------------------
# Composed registries reach the agent
# ---------------------------------------------------------------------------


def test_a_composed_registry_feeds_the_capability(source: LocalSkillsRegistry) -> None:
    """The whole point: a composed source reaches the agent."""
    capability = SkillsCapability(registries=[source.filtered(lambda info: 'pdf' in info.name).prefixed('vendor-')])

    assert capability.skill_names == ['vendor-pdf-tools']


def test_bundled_files_survive_composition(source: LocalSkillsRegistry) -> None:
    """A staged copy is only useful if the skill's files came with it."""
    capability = SkillsCapability(registries=[source.prefixed('vendor-')])

    package = capability.packages['vendor-data-analysis']
    assert sorted(package.resources_by_name) == ['references/NOTES.md']

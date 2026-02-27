"""Tests for registry composition classes.

Tests WrapperRegistry, FilteredRegistry, PrefixedRegistry, RenamedRegistry,
and CombinedRegistry independently of any concrete registry implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pydantic_ai_skills.exceptions import SkillNotFoundError
from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.registries.combined import CombinedRegistry
from pydantic_ai_skills.registries.filtered import FilteredRegistry
from pydantic_ai_skills.registries.prefixed import PrefixedRegistry
from pydantic_ai_skills.registries.renamed import RenamedRegistry
from pydantic_ai_skills.registries.wrapper import WrapperRegistry
from pydantic_ai_skills.types import Skill

# ---------------------------------------------------------------------------
# Stub registry for testing
# ---------------------------------------------------------------------------


@dataclass
class StubRegistry(SkillRegistry):
    """In-memory registry for testing composition wrappers."""

    skills: list[Skill] = field(default_factory=list)

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        q = query.lower()
        return [s for s in self.skills if q in s.name.lower() or q in (s.description or '').lower()][:limit]

    async def get(self, skill_name: str) -> Skill:
        for s in self.skills:
            if s.name == skill_name:
                return s
        raise SkillNotFoundError(f"Skill '{skill_name}' not found.")

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        await self.get(skill_name)  # validate exists
        dest = Path(target_dir) / skill_name
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        return await self.install(skill_name, target_dir)

    def get_skills(self) -> list[Skill]:
        return list(self.skills)


def _make_skills() -> list[Skill]:
    """Create a standard set of test skills."""
    return [
        Skill(name='pdf', description='PDF manipulation skill.', content='PDF instructions.'),
        Skill(name='xlsx', description='Excel spreadsheet skill.', content='Excel instructions.'),
        Skill(name='web-research', description='Search the web for information.', content='Web instructions.'),
    ]


@pytest.fixture()
def stub_registry() -> StubRegistry:
    """Return a stub registry with 3 skills."""
    return StubRegistry(skills=_make_skills())


# ===========================================================================
# WrapperRegistry
# ===========================================================================


async def test_wrapper_delegates_search(stub_registry: StubRegistry) -> None:
    """WrapperRegistry.search() delegates to the wrapped registry."""
    wrapper = WrapperRegistry(wrapped=stub_registry)
    results = await wrapper.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'pdf'


async def test_wrapper_delegates_get(stub_registry: StubRegistry) -> None:
    """WrapperRegistry.get() delegates to the wrapped registry."""
    wrapper = WrapperRegistry(wrapped=stub_registry)
    skill = await wrapper.get('xlsx')
    assert skill.name == 'xlsx'


async def test_wrapper_delegates_install(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """WrapperRegistry.install() delegates to the wrapped registry."""
    wrapper = WrapperRegistry(wrapped=stub_registry)
    result = await wrapper.install('pdf', tmp_path)
    assert result.is_dir()
    assert result.name == 'pdf'


async def test_wrapper_delegates_update(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """WrapperRegistry.update() delegates to the wrapped registry."""
    wrapper = WrapperRegistry(wrapped=stub_registry)
    result = await wrapper.update('pdf', tmp_path)
    assert result.is_dir()


async def test_wrapper_get_raises_not_found(stub_registry: StubRegistry) -> None:
    """WrapperRegistry.get() propagates SkillNotFoundError."""
    wrapper = WrapperRegistry(wrapped=stub_registry)
    with pytest.raises(SkillNotFoundError):
        await wrapper.get('nonexistent')


# ===========================================================================
# FilteredRegistry
# ===========================================================================


async def test_filtered_search_limits_results(stub_registry: StubRegistry) -> None:
    """FilteredRegistry.search() only returns skills matching the predicate."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: s.name == 'pdf')
    results = await filtered.search('skill')
    assert all(s.name == 'pdf' for s in results)


async def test_filtered_search_returns_empty(stub_registry: StubRegistry) -> None:
    """FilteredRegistry.search() returns empty when predicate matches nothing."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: False)
    results = await filtered.search('pdf')
    assert results == []


async def test_filtered_get_passes_predicate(stub_registry: StubRegistry) -> None:
    """FilteredRegistry.get() returns a skill that passes the predicate."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: s.name == 'pdf')
    skill = await filtered.get('pdf')
    assert skill.name == 'pdf'


async def test_filtered_get_rejects_excluded(stub_registry: StubRegistry) -> None:
    """FilteredRegistry.get() raises SkillNotFoundError for excluded skills."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: s.name == 'pdf')
    with pytest.raises(SkillNotFoundError):
        await filtered.get('xlsx')


async def test_filtered_install_validates(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """FilteredRegistry.install() checks predicate before installing."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: s.name == 'pdf')
    result = await filtered.install('pdf', tmp_path)
    assert result.is_dir()


async def test_filtered_install_rejects_excluded(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """FilteredRegistry.install() raises for excluded skills."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: s.name == 'pdf')
    with pytest.raises(SkillNotFoundError):
        await filtered.install('xlsx', tmp_path)


async def test_filtered_update_validates(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """FilteredRegistry.update() checks predicate before updating."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: s.name == 'pdf')
    result = await filtered.update('pdf', tmp_path)
    assert result.is_dir()


async def test_filtered_update_rejects_excluded(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """FilteredRegistry.update() raises for excluded skills."""
    filtered = FilteredRegistry(wrapped=stub_registry, predicate=lambda s: s.name == 'pdf')
    with pytest.raises(SkillNotFoundError):
        await filtered.update('xlsx', tmp_path)


async def test_filtered_via_convenience_method(stub_registry: StubRegistry) -> None:
    """SkillRegistry.filtered() returns a FilteredRegistry."""
    filtered = stub_registry.filtered(lambda s: s.name == 'xlsx')
    assert isinstance(filtered, FilteredRegistry)
    skill = await filtered.get('xlsx')
    assert skill.name == 'xlsx'


# ===========================================================================
# PrefixedRegistry
# ===========================================================================


async def test_prefixed_search_adds_prefix(stub_registry: StubRegistry) -> None:
    """PrefixedRegistry.search() prepends prefix to all result names."""
    prefixed = PrefixedRegistry(wrapped=stub_registry, prefix='acme-')
    results = await prefixed.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'acme-pdf'


async def test_prefixed_get_with_prefix(stub_registry: StubRegistry) -> None:
    """PrefixedRegistry.get() resolves prefixed name to the inner skill."""
    prefixed = PrefixedRegistry(wrapped=stub_registry, prefix='acme-')
    skill = await prefixed.get('acme-pdf')
    assert skill.name == 'acme-pdf'


async def test_prefixed_get_without_prefix_raises(stub_registry: StubRegistry) -> None:
    """PrefixedRegistry.get() raises when prefix is missing."""
    prefixed = PrefixedRegistry(wrapped=stub_registry, prefix='acme-')
    with pytest.raises(SkillNotFoundError):
        await prefixed.get('pdf')


async def test_prefixed_install_strips_prefix(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """PrefixedRegistry.install() strips prefix before delegating."""
    prefixed = PrefixedRegistry(wrapped=stub_registry, prefix='acme-')
    result = await prefixed.install('acme-pdf', tmp_path)
    assert result.is_dir()
    # Installed under the original (un-prefixed) name
    assert result.name == 'pdf'


async def test_prefixed_update_strips_prefix(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """PrefixedRegistry.update() strips prefix before delegating."""
    prefixed = PrefixedRegistry(wrapped=stub_registry, prefix='acme-')
    result = await prefixed.update('acme-pdf', tmp_path)
    assert result.is_dir()
    assert result.name == 'pdf'


async def test_prefixed_via_convenience_method(stub_registry: StubRegistry) -> None:
    """SkillRegistry.prefixed() returns a PrefixedRegistry."""
    prefixed = stub_registry.prefixed('x-')
    assert isinstance(prefixed, PrefixedRegistry)
    skill = await prefixed.get('x-pdf')
    assert skill.name == 'x-pdf'


# ===========================================================================
# RenamedRegistry
# ===========================================================================


async def test_renamed_search_maps_names(stub_registry: StubRegistry) -> None:
    """RenamedRegistry.search() applies the name map to results."""
    renamed = RenamedRegistry(wrapped=stub_registry, name_map={'doc-tool': 'pdf'})
    results = await renamed.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'doc-tool'


async def test_renamed_get_with_new_name(stub_registry: StubRegistry) -> None:
    """RenamedRegistry.get() resolves new name to original."""
    renamed = RenamedRegistry(wrapped=stub_registry, name_map={'doc-tool': 'pdf'})
    skill = await renamed.get('doc-tool')
    assert skill.name == 'doc-tool'


async def test_renamed_get_unmapped_name(stub_registry: StubRegistry) -> None:
    """RenamedRegistry.get() passes through names not in the map."""
    renamed = RenamedRegistry(wrapped=stub_registry, name_map={'doc-tool': 'pdf'})
    skill = await renamed.get('xlsx')
    assert skill.name == 'xlsx'


async def test_renamed_install_resolves_name(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """RenamedRegistry.install() resolves renamed name before delegating."""
    renamed = RenamedRegistry(wrapped=stub_registry, name_map={'doc-tool': 'pdf'})
    result = await renamed.install('doc-tool', tmp_path)
    assert result.is_dir()
    assert result.name == 'pdf'


async def test_renamed_update_resolves_name(stub_registry: StubRegistry, tmp_path: Path) -> None:
    """RenamedRegistry.update() resolves renamed name before delegating."""
    renamed = RenamedRegistry(wrapped=stub_registry, name_map={'doc-tool': 'pdf'})
    result = await renamed.update('doc-tool', tmp_path)
    assert result.is_dir()
    assert result.name == 'pdf'


async def test_renamed_via_convenience_method(stub_registry: StubRegistry) -> None:
    """SkillRegistry.renamed() returns a RenamedRegistry."""
    renamed = stub_registry.renamed({'doc-tool': 'pdf'})
    assert isinstance(renamed, RenamedRegistry)
    skill = await renamed.get('doc-tool')
    assert skill.name == 'doc-tool'


# ===========================================================================
# CombinedRegistry
# ===========================================================================


async def test_combined_search_merges_results() -> None:
    """CombinedRegistry.search() merges results from all child registries."""
    reg1 = StubRegistry(skills=[Skill(name='pdf', description='PDF skill.', content='')])
    reg2 = StubRegistry(skills=[Skill(name='xlsx', description='Excel skill.', content='')])
    combined = CombinedRegistry(registries=[reg1, reg2])
    results = await combined.search('skill')
    names = {s.name for s in results}
    assert names == {'pdf', 'xlsx'}


async def test_combined_search_deduplicates() -> None:
    """CombinedRegistry.search() deduplicates by name (first wins)."""
    reg1 = StubRegistry(skills=[Skill(name='pdf', description='First.', content='')])
    reg2 = StubRegistry(skills=[Skill(name='pdf', description='Second.', content='')])
    combined = CombinedRegistry(registries=[reg1, reg2])
    results = await combined.search('pdf')
    assert len(results) == 1
    assert results[0].description == 'First.'


async def test_combined_get_first_match() -> None:
    """CombinedRegistry.get() returns the first registry's match."""
    reg1 = StubRegistry(skills=[Skill(name='pdf', description='First.', content='')])
    reg2 = StubRegistry(skills=[Skill(name='pdf', description='Second.', content='')])
    combined = CombinedRegistry(registries=[reg1, reg2])
    skill = await combined.get('pdf')
    assert skill.description == 'First.'


async def test_combined_get_tries_all_registries() -> None:
    """CombinedRegistry.get() falls through to the next registry on miss."""
    reg1 = StubRegistry(skills=[Skill(name='pdf', description='PDF.', content='')])
    reg2 = StubRegistry(skills=[Skill(name='xlsx', description='Excel.', content='')])
    combined = CombinedRegistry(registries=[reg1, reg2])
    skill = await combined.get('xlsx')
    assert skill.name == 'xlsx'


async def test_combined_get_raises_when_missing() -> None:
    """CombinedRegistry.get() raises when no registry has the skill."""
    reg1 = StubRegistry(skills=[Skill(name='pdf', description='PDF.', content='')])
    combined = CombinedRegistry(registries=[reg1])
    with pytest.raises(SkillNotFoundError):
        await combined.get('nonexistent')


async def test_combined_install_routes_to_owner(tmp_path: Path) -> None:
    """CombinedRegistry.install() routes to the registry that owns the skill."""
    reg1 = StubRegistry(skills=[Skill(name='pdf', description='PDF.', content='')])
    reg2 = StubRegistry(skills=[Skill(name='xlsx', description='Excel.', content='')])
    combined = CombinedRegistry(registries=[reg1, reg2])
    result = await combined.install('xlsx', tmp_path)
    assert result.is_dir()
    assert result.name == 'xlsx'


async def test_combined_install_raises_when_missing(tmp_path: Path) -> None:
    """CombinedRegistry.install() raises when no registry has the skill."""
    combined = CombinedRegistry(registries=[StubRegistry(skills=[])])
    with pytest.raises(SkillNotFoundError):
        await combined.install('nonexistent', tmp_path)


async def test_combined_update_routes_to_owner(tmp_path: Path) -> None:
    """CombinedRegistry.update() routes to the registry that owns the skill."""
    reg1 = StubRegistry(skills=[Skill(name='pdf', description='PDF.', content='')])
    combined = CombinedRegistry(registries=[reg1])
    result = await combined.update('pdf', tmp_path)
    assert result.is_dir()


async def test_combined_update_raises_when_missing(tmp_path: Path) -> None:
    """CombinedRegistry.update() raises when no registry has the skill."""
    combined = CombinedRegistry(registries=[StubRegistry(skills=[])])
    with pytest.raises(SkillNotFoundError):
        await combined.update('nonexistent', tmp_path)


async def test_combined_search_respects_limit() -> None:
    """CombinedRegistry.search() respects the limit parameter."""
    skills = [Skill(name=f'skill-{i}', description='Test.', content='') for i in range(20)]
    reg = StubRegistry(skills=skills)
    combined = CombinedRegistry(registries=[reg])
    results = await combined.search('test', limit=5)
    assert len(results) == 5


# ===========================================================================
# Chaining / composition
# ===========================================================================


async def test_filtered_then_prefixed(stub_registry: StubRegistry) -> None:
    """Chaining filtered() then prefixed() applies both transformations."""
    view = stub_registry.filtered(lambda s: s.name == 'pdf').prefixed('x-')
    results = await view.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'x-pdf'


async def test_prefixed_then_filtered(stub_registry: StubRegistry) -> None:
    """Chaining prefixed() then filtered() — predicate sees prefixed names."""
    view = stub_registry.prefixed('a-').filtered(lambda s: s.name == 'a-pdf')
    results = await view.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'a-pdf'


async def test_renamed_then_filtered(stub_registry: StubRegistry) -> None:
    """Chaining renamed() then filtered() — predicate sees renamed names."""
    view = stub_registry.renamed({'doc': 'pdf'}).filtered(lambda s: s.name == 'doc')
    results = await view.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'doc'


async def test_filtered_then_renamed(stub_registry: StubRegistry) -> None:
    """Chaining filtered() then renamed() applies both transformations."""
    view = stub_registry.filtered(lambda s: s.name == 'pdf').renamed({'doc': 'pdf'})
    skill = await view.get('doc')
    assert skill.name == 'doc'


async def test_combined_with_filtered_children() -> None:
    """CombinedRegistry with filtered children works correctly."""
    reg1 = StubRegistry(
        skills=[
            Skill(name='pdf', description='PDF.', content=''),
            Skill(name='xlsx', description='Excel.', content=''),
        ]
    )
    reg2 = StubRegistry(
        skills=[
            Skill(name='web-research', description='Web.', content=''),
        ]
    )
    combined = CombinedRegistry(
        registries=[
            reg1.filtered(lambda s: s.name == 'pdf'),
            reg2,
        ]
    )
    results = await combined.search('', limit=10)
    names = {s.name for s in results}
    # xlsx is filtered out from reg1
    assert 'xlsx' not in names
    assert 'pdf' in names
    assert 'web-research' in names


async def test_triple_chain(stub_registry: StubRegistry) -> None:
    """Three-level chaining: filtered → prefixed → renamed."""
    view = stub_registry.filtered(lambda s: s.name == 'pdf').prefixed('acme-').renamed({'document-tool': 'acme-pdf'})
    skill = await view.get('document-tool')
    assert skill.name == 'document-tool'

"""Tests for SkillsCapability, the composite over harness's `Skills`.

The point of these is the seam: that discovery, validation and instruction rendering
really are harness's, that what this package adds on top (remote sources, bundled files,
programmatic skills, `${SKILL_DIR}` resolution) lands on the same deferred capabilities,
and that a run drives the whole thing end to end.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability, Capability
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pydantic_ai_skills import Skill, SkillsCapability
from pydantic_ai_skills._toolset import SkillFilesToolset
from pydantic_ai_skills.registries import LocalSkillsRegistry


def write_skill(
    library: Path,
    name: str,
    *,
    description: str = 'A skill.',
    body: str = 'Body.',
    frontmatter_name: str | None = None,
) -> Path:
    """Create a skill package under `library` and return its directory."""
    skill = library / name
    skill.mkdir(parents=True)
    declared = f'name: {frontmatter_name or name}\n'
    (skill / 'SKILL.md').write_text(f'---\n{declared}description: {description}\n---\n\n{body}\n')
    return skill


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A skill library holding one package with a resource and a script."""
    lib = tmp_path / 'skills'
    skill = write_skill(
        lib,
        'demo-skill',
        description='Demo skill.',
        body='Read references/NOTES.md, then run scripts/hello.py.',
    )
    (skill / 'references').mkdir()
    (skill / 'references' / 'NOTES.md').write_text('the notes')
    (skill / 'scripts').mkdir()
    (skill / 'scripts' / 'hello.py').write_text('#!/usr/bin/env python3\nprint("hello from the script")\n')
    return lib


def leaves_of(capability: AbstractCapability[Any]) -> list[AbstractCapability[Any]]:
    """Collect the capabilities `apply` visits.

    For a `SkillsCapability` that contributes bundled-file tools this includes the
    capability itself, which is how pydantic-ai finds the toolset's owner.
    """
    collected: list[AbstractCapability[Any]] = []
    capability.apply(collected.append)
    return collected


# ---------------------------------------------------------------------------
# Discovery is harness's; each skill is its own deferred capability
# ---------------------------------------------------------------------------


def test_each_skill_becomes_one_deferred_capability(library: Path) -> None:
    """The v1 `list_skills`/`load_skill` pair is replaced by pydantic-ai's own flow."""
    capability = SkillsCapability(library)

    skill_leaves = [leaf for leaf in leaves_of(capability) if leaf is not capability]

    assert [leaf.id for leaf in skill_leaves] == ['demo-skill']
    assert all(leaf.defer_loading for leaf in skill_leaves)
    assert skill_leaves[0].get_description() == 'Demo skill.'
    assert capability.skill_names == ['demo-skill']


def test_instructions_carry_the_harness_skill_heading(library: Path) -> None:
    """The rendered body is harness's, not ours -- including the `# Skill:` heading."""
    capability = SkillsCapability(library)

    leaf = next(leaf for leaf in leaves_of(capability) if leaf.id == 'demo-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    assert instructions[0].startswith('# Skill: demo-skill\n\n')


def test_a_directory_without_skill_md_is_not_a_skill(tmp_path: Path) -> None:
    """Only immediate children holding a SKILL.md count, matching harness."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'real-skill')
    (lib / 'just-a-folder').mkdir()
    (lib / 'nested' / 'deeper').mkdir(parents=True)
    (lib / 'nested' / 'deeper' / 'SKILL.md').write_text('---\nname: deeper\ndescription: Too deep.\n---\n\nBody.\n')

    assert SkillsCapability(lib).skill_names == ['real-skill']


def test_harness_validation_errors_surface_at_construction(tmp_path: Path) -> None:
    """We do not pre-empt harness's validation, so its message is what the caller sees."""
    lib = tmp_path / 'skills'
    skill = lib / 'bad-skill'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: mismatched\ndescription: A skill.\n---\n\nBody.\n')

    with pytest.raises(ValueError, match='must match its parent directory'):
        SkillsCapability(lib)


def test_multiple_libraries_are_merged(tmp_path: Path) -> None:
    """Several libraries contribute to one catalog, as they do for harness."""
    first = tmp_path / 'first'
    second = tmp_path / 'second'
    write_skill(first, 'alpha')
    write_skill(second, 'beta')

    assert SkillsCapability([first, second]).skill_names == ['alpha', 'beta']


def test_a_single_path_is_accepted_without_wrapping(library: Path) -> None:
    """One path need not be wrapped in a list."""
    assert SkillsCapability(library).skill_names == SkillsCapability([library]).skill_names


def test_no_source_at_all_is_rejected() -> None:
    """v1 silently defaulted to ./skills; v2 asks rather than guessing."""
    with pytest.raises(ValueError, match='at least one source'):
        SkillsCapability()


# ---------------------------------------------------------------------------
# include / exclude
# ---------------------------------------------------------------------------


def test_include_limits_the_catalog(tmp_path: Path) -> None:
    """Only the named skills reach the model."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'alpha')
    write_skill(lib, 'beta')

    assert SkillsCapability(lib, include=['alpha']).skill_names == ['alpha']


def test_exclude_omits_from_the_catalog(tmp_path: Path) -> None:
    """The named skills are kept out of the catalog."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'alpha')
    write_skill(lib, 'beta')

    assert SkillsCapability(lib, exclude=['alpha']).skill_names == ['beta']


def test_empty_include_exposes_nothing(tmp_path: Path) -> None:
    """An empty include is a valid way to expose no skills."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'alpha')

    assert SkillsCapability(lib, include=[]).skill_names == []


def test_include_and_exclude_together_are_rejected(library: Path) -> None:
    """The two options answer the same question two ways."""
    with pytest.raises(ValueError, match='cannot be used together'):
        SkillsCapability(library, include=['demo-skill'], exclude=['demo-skill'])


def test_unknown_include_name_is_rejected(library: Path) -> None:
    """A typo in a selection is a configuration error, not a no-op."""
    with pytest.raises(ValueError, match='Unknown skill in include: nope'):
        SkillsCapability(library, include=['nope'])


def test_include_may_name_a_programmatic_skill(library: Path) -> None:
    """A selection may name a skill harness never sees, so it is split across sources.

    Passing the full `include` straight through would make harness reject a name it has
    no way to know about.
    """
    python_skill = Skill(name='in-python', description='Defined in Python.', content='Body.')

    capability = SkillsCapability(library, skills=[python_skill], include=['in-python'])

    assert capability.skill_names == ['in-python']


def test_exclude_may_name_a_programmatic_skill(library: Path) -> None:
    """Exclusion spans every source, not just the directory ones."""
    python_skill = Skill(name='in-python', description='Defined in Python.', content='Body.')

    capability = SkillsCapability(library, skills=[python_skill], exclude=['in-python'])

    assert capability.skill_names == ['demo-skill']


def test_selection_error_lists_skills_from_every_source(library: Path) -> None:
    """The error has to name what is actually available."""
    python_skill = Skill(name='in-python', description='Defined in Python.', content='Body.')

    with pytest.raises(ValueError, match='Available skills: demo-skill, in-python'):
        SkillsCapability(library, skills=[python_skill], include=['nope'])


def test_include_must_not_be_a_bare_string(library: Path) -> None:
    """A string is iterable, so it would silently select letters."""
    with pytest.raises(TypeError, match='not a string'):
        SkillsCapability(library, include='demo-skill')


# ---------------------------------------------------------------------------
# Bundled files: the gap harness leaves open
# ---------------------------------------------------------------------------


def test_bundled_files_are_indexed(library: Path) -> None:
    """A skill's references and scripts are found and keyed by relative path."""
    package = SkillsCapability(library).packages['demo-skill']

    assert sorted(package.resources_by_name) == ['references/NOTES.md']
    assert sorted(package.scripts_by_name) == ['scripts/hello.py']


def test_the_file_tools_come_from_the_capability_itself(library: Path) -> None:
    """pydantic-ai collects toolsets from a container's direct children, not via `apply`.

    A toolset parked on one of the leaves this capability yields would never be
    registered with the agent, so `get_toolset` has to return it here.
    """
    toolset = SkillsCapability(library).get_toolset()

    assert isinstance(toolset, SkillFilesToolset)
    assert sorted(toolset.tools) == ['read_skill_resource', 'run_skill_script']


def test_resources_false_drops_only_the_resource_tool(library: Path) -> None:
    """Replaces v1 `exclude_tools` for the resource tool."""
    toolset = SkillsCapability(library, resources=False).get_toolset()

    assert isinstance(toolset, SkillFilesToolset)
    assert sorted(toolset.tools) == ['run_skill_script']


def test_scripts_false_drops_only_the_script_tool(library: Path) -> None:
    """Replaces v1 `exclude_tools` for the script tool."""
    toolset = SkillsCapability(library, scripts=False).get_toolset()

    assert isinstance(toolset, SkillFilesToolset)
    assert sorted(toolset.tools) == ['read_skill_resource']


def test_no_file_toolset_when_no_skill_ships_files(tmp_path: Path) -> None:
    """Registering tools that can never succeed only wastes context."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'plain-skill')

    assert SkillsCapability(lib).get_toolset() is None


# ---------------------------------------------------------------------------
# ${SKILL_DIR} resolution -- harness leaves the placeholder in place
# ---------------------------------------------------------------------------


@pytest.mark.parametrize('placeholder', ['${SKILL_DIR}', '${CLAUDE_SKILL_DIR}'])
def test_skill_dir_placeholder_is_resolved(tmp_path: Path, placeholder: str) -> None:
    """A placeholder becomes the real directory, which is what the script tool needs."""
    lib = tmp_path / 'skills'
    skill = write_skill(lib, 'demo-skill', body=f'Run {placeholder}/scripts/go.py')

    leaf = next(leaf for leaf in leaves_of(SkillsCapability(lib)) if leaf.id == 'demo-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    assert str(skill.resolve()) in instructions[0]
    assert placeholder not in instructions[0]


def test_skill_dir_placeholder_is_left_alone_when_disabled(tmp_path: Path) -> None:
    """Opting out gives back exactly what harness rendered."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'demo-skill', body='Run ${SKILL_DIR}/scripts/go.py')

    leaf = next(leaf for leaf in leaves_of(SkillsCapability(lib, resolve_skill_dir=False)) if leaf.id == 'demo-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    assert '${SKILL_DIR}' in instructions[0]


def test_a_leaf_with_nothing_to_add_is_passed_through_untouched(library: Path) -> None:
    """No placeholder and no inventory means no rebuild, so harness's own object reaches the agent."""
    from pydantic_ai_harness import Skills

    harness_leaves: list[AbstractCapability[Any]] = []
    Skills(library).apply(harness_leaves.append)
    capability = SkillsCapability(library, list_bundled_files=False)
    ours = next(leaf for leaf in leaves_of(capability) if leaf.id == 'demo-skill')

    assert ours.get_instructions() == harness_leaves[0].get_instructions()


# ---------------------------------------------------------------------------
# Bundled-file inventory -- the names the file tools expect, at load time
# ---------------------------------------------------------------------------


def test_bundled_files_are_listed_in_the_instructions(library: Path) -> None:
    """A SKILL.md names its files in prose; the tools need the indexed paths."""
    leaf = next(leaf for leaf in leaves_of(SkillsCapability(library)) if leaf.id == 'demo-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    inventory = instructions[-1]
    assert '## Bundled files' in inventory
    assert '- `references/NOTES.md`' in inventory
    assert '- `scripts/hello.py`' in inventory


def test_the_inventory_can_be_turned_off(library: Path) -> None:
    """A skill whose own instructions list its files does not need ours."""
    capability = SkillsCapability(library, list_bundled_files=False)
    leaf = next(leaf for leaf in leaves_of(capability) if leaf.id == 'demo-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    assert not any('Bundled files' in part for part in instructions)


def test_the_inventory_omits_a_kind_whose_tool_is_not_registered(library: Path) -> None:
    """Advertising names the model has no tool to use would be noise."""
    capability = SkillsCapability(library, scripts=False)
    leaf = next(leaf for leaf in leaves_of(capability) if leaf.id == 'demo-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    inventory = instructions[-1]
    assert '- `references/NOTES.md`' in inventory
    assert 'scripts/hello.py' not in inventory


def test_a_skill_with_no_bundled_files_gets_no_inventory(tmp_path: Path) -> None:
    """Instructions-only skills are the case harness alone already covers."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'plain-skill', body='Just instructions.')

    leaf = next(leaf for leaf in leaves_of(SkillsCapability(lib)) if leaf.id == 'plain-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    assert not any('Bundled files' in part for part in instructions)


def test_a_long_inventory_is_truncated(tmp_path: Path) -> None:
    """A package shipping hundreds of files must not flood the loaded instructions."""
    lib = tmp_path / 'skills'
    skill = write_skill(lib, 'big-skill', body='Body.')
    (skill / 'references').mkdir()
    for index in range(60):
        (skill / 'references' / f'note-{index:03d}.md').write_text('note')

    leaf = next(leaf for leaf in leaves_of(SkillsCapability(lib)) if leaf.id == 'big-skill')
    instructions = leaf.get_instructions()

    assert isinstance(instructions, list)
    assert '- ...and 10 more' in instructions[-1]


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------


def test_a_registry_contributes_its_synced_library(library: Path) -> None:
    """A registry is just another source of libraries."""
    capability = SkillsCapability(registries=[LocalSkillsRegistry(library)])

    assert capability.skill_names == ['demo-skill']


def test_registries_and_directories_combine(tmp_path: Path) -> None:
    """Local and remote sources sit side by side in one catalog."""
    local = tmp_path / 'local'
    remote = tmp_path / 'remote'
    write_skill(local, 'local-skill')
    write_skill(remote, 'remote-skill')

    capability = SkillsCapability(local, registries=[LocalSkillsRegistry(remote)])

    assert capability.skill_names == ['local-skill', 'remote-skill']


# ---------------------------------------------------------------------------
# Programmatic skills
# ---------------------------------------------------------------------------


def test_a_programmatic_skill_joins_the_deferred_catalog(library: Path) -> None:
    """Python-defined skills are deferred like the rest."""
    python_skill = Skill(name='in-python', description='Defined in Python.', content='Do the thing.')

    capability = SkillsCapability(library, skills=[python_skill])

    leaf = next(leaf for leaf in leaves_of(capability) if leaf.id == 'in-python')
    assert leaf.defer_loading is True
    assert leaf.get_description() == 'Defined in Python.'
    assert leaf.get_instructions() == ['# Skill: in-python\n\nDo the thing.']


def test_a_programmatic_skill_shadowing_a_directory_one_warns(library: Path) -> None:
    """Silently picking a winner would make the catalog depend on argument order."""
    python_skill = Skill(name='demo-skill', description='Also called demo-skill.', content='Body.')

    with pytest.warns(UserWarning, match='shadows a skill of the same name'):
        capability = SkillsCapability(library, skills=[python_skill])

    assert capability.skill_names == ['demo-skill']


def test_a_capability_may_hold_only_programmatic_skills() -> None:
    """No directory or registry is required."""
    python_skill = Skill(name='in-python', description='Defined in Python.', content='Body.')

    assert SkillsCapability(skills=[python_skill]).skill_names == ['in-python']


# ---------------------------------------------------------------------------
# Composite plumbing
# ---------------------------------------------------------------------------


def test_visit_and_replace_returns_self_when_nothing_changed(library: Path) -> None:
    """An unchanged tree must not be rebuilt."""
    capability = SkillsCapability(library)

    assert capability.visit_and_replace(lambda leaf: leaf) is capability


def test_visit_and_replace_rebuilds_the_container(library: Path) -> None:
    """A replaced leaf survives inside a fresh container."""
    capability = SkillsCapability(library)
    replacement = Capability[Any](id='demo-skill', instructions='replaced', defer_loading=True)

    rewritten = capability.visit_and_replace(lambda leaf: replacement if leaf.id == 'demo-skill' else leaf)

    assert rewritten is not None
    assert rewritten is not capability
    assert replacement in leaves_of(rewritten)


def test_visit_and_replace_returns_none_when_everything_is_removed(library: Path) -> None:
    """Removing every leaf removes the container."""
    assert SkillsCapability(library).visit_and_replace(lambda leaf: None) is None


def test_repr_shows_only_caller_configuration(library: Path) -> None:
    """The repr must not dump indexed packages or leaves."""
    text = repr(SkillsCapability(library, include=['demo-skill']))

    assert text.startswith('SkillsCapability(')
    assert 'include=frozenset({' in text


# ---------------------------------------------------------------------------
# Agent specs
# ---------------------------------------------------------------------------


def test_serialization_name_is_stable() -> None:
    """Agent specs reference the capability by this name."""
    assert SkillsCapability.get_serialization_name() == 'SkillsCapability'


def test_from_spec_builds_the_same_catalog(library: Path) -> None:
    """A spec-built capability behaves like a Python-built one."""
    capability = SkillsCapability.from_spec(directories=[str(library)], include=['demo-skill'])

    # `from_spec` returns `AbstractCapability[Any]`, matching the base class it overrides,
    # so narrowing is the caller's job.
    assert isinstance(capability, SkillsCapability)
    assert capability.skill_names == ['demo-skill']


def test_from_spec_accepts_a_single_directory_string(library: Path) -> None:
    """YAML often carries one path as a bare string."""
    capability = SkillsCapability.from_spec(directories=str(library))

    assert isinstance(capability, SkillsCapability)
    assert capability.skill_names == ['demo-skill']


# ---------------------------------------------------------------------------
# End to end through a real agent run
# ---------------------------------------------------------------------------


async def test_a_run_loads_a_skill_then_reads_and_runs_its_files(library: Path) -> None:
    """The full progressive-disclosure path: catalog, load_capability, then the files."""
    seen_tools: list[list[str]] = []
    steps: list[ToolCallPart] = [
        ToolCallPart('load_capability', {'id': 'demo-skill'}),
        ToolCallPart('read_skill_resource', {'skill_name': 'demo-skill', 'resource_name': 'references/NOTES.md'}),
        ToolCallPart('run_skill_script', {'skill_name': 'demo-skill', 'script_name': 'scripts/hello.py'}),
    ]

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen_tools.append(sorted(tool.name for tool in info.function_tools))
        step = len(seen_tools) - 1
        if step < len(steps):
            return ModelResponse(parts=[steps[step]])
        return ModelResponse(parts=[TextPart('done')])

    agent = Agent(FunctionModel(model_fn), capabilities=[SkillsCapability(library)])
    result = await agent.run('use the demo skill')

    assert result.output == 'done'
    assert 'load_capability' in seen_tools[0], 'the skill must start deferred'

    returns = {
        part.tool_name: part.content
        for message in result.all_messages()
        for part in getattr(message, 'parts', [])
        if part.part_kind == 'tool-return'
    }
    assert returns['read_skill_resource'] == 'the notes'
    assert 'hello from the script' in str(returns['run_skill_script'])


async def test_reading_files_before_loading_the_skill_is_refused(library: Path) -> None:
    """Bundled files stay behind the same boundary as the skill's instructions."""
    calls: list[int] = []

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        'read_skill_resource',
                        {'skill_name': 'demo-skill', 'resource_name': 'references/NOTES.md'},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart('gave up')])

    agent = Agent(FunctionModel(model_fn), capabilities=[SkillsCapability(library)])
    result = await agent.run('read the notes without loading anything')

    retries = [
        part.content
        for message in result.all_messages()
        for part in getattr(message, 'parts', [])
        if part.part_kind == 'retry-prompt'
    ]
    assert any('is not loaded' in str(retry) for retry in retries)


async def test_require_loaded_false_lets_files_be_read_directly(library: Path) -> None:
    """Opting out of the gate lets a skill ship files usable without loading it."""
    calls: list[int] = []

    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        if len(calls) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        'read_skill_resource',
                        {'skill_name': 'demo-skill', 'resource_name': 'references/NOTES.md'},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart('done')])

    agent = Agent(FunctionModel(model_fn), capabilities=[SkillsCapability(library, require_loaded=False)])
    result = await agent.run('read the notes')

    returns = [
        part.content
        for message in result.all_messages()
        for part in getattr(message, 'parts', [])
        if part.part_kind == 'tool-return' and part.tool_name == 'read_skill_resource'
    ]
    assert returns == ['the notes']


def test_overlong_description_warning_comes_from_harness(tmp_path: Path) -> None:
    """We pass descriptions through unchanged, so harness's own warning is what fires."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'wordy-skill', description='x' * 1500)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        SkillsCapability(lib)

    assert any('1,024-character limit' in str(warning.message) for warning in caught)


def test_apply_visits_self_so_the_file_toolset_has_a_registered_owner(library: Path) -> None:
    """pydantic-ai builds the run's capability registry from `apply`.

    A toolset whose owner is missing from that registry fails the run the first time the
    model calls one of its tools, so this is load-bearing rather than cosmetic.
    """
    capability = SkillsCapability(library)

    assert capability in leaves_of(capability)


def test_apply_stays_a_pure_container_without_bundled_files(tmp_path: Path) -> None:
    """Nothing to own means nothing to register."""
    lib = tmp_path / 'skills'
    write_skill(lib, 'plain-skill')
    capability = SkillsCapability(lib)

    assert capability not in leaves_of(capability)

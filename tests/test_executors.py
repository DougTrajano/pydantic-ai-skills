"""Tests for the SkillScriptExecutor protocol and the bundled sandbox executors."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import types
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import anyio
import pytest

from pydantic_ai_skills import (
    CallableSkillScriptExecutor,
    LocalSandboxScriptExecutor,
    LocalSkillScriptExecutor,
    OpenSandboxScriptExecutor,
    SkillScript,
    SkillScriptExecutor,
    SkillsDirectory,
    SkillsToolset,
    discover_skills,
)
from pydantic_ai_skills.local import FileBasedSkillScript
from pydantic_ai_skills.sandboxes import (
    iter_stageable_dirs,
    iter_stageable_files,
    localsandbox as localsandbox_module,
    opensandbox as opensandbox_module,
    skill_root_for,
)

# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class DuckTypedExecutor:
    """A custom executor that never inherits from the protocol."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> Any:
        self.calls.append((script.name, args))
        return f'duck ran {script.name}'


class NotAnExecutor:
    """Has no run method, so it must not satisfy the protocol."""


def test_builtin_executors_satisfy_protocol() -> None:
    """Both shipped executors are instances of the protocol."""
    assert isinstance(LocalSkillScriptExecutor(), SkillScriptExecutor)
    assert isinstance(CallableSkillScriptExecutor(func=lambda script, args=None: ''), SkillScriptExecutor)


def test_builtin_executors_are_nominal_subclasses() -> None:
    """The shipped executors declare the protocol explicitly, not just structurally."""
    assert issubclass(LocalSkillScriptExecutor, SkillScriptExecutor)
    assert issubclass(CallableSkillScriptExecutor, SkillScriptExecutor)


def test_duck_typed_executor_satisfies_protocol() -> None:
    """A third-party executor conforms without importing or subclassing anything."""
    assert isinstance(DuckTypedExecutor(), SkillScriptExecutor)


def test_object_without_run_does_not_satisfy_protocol() -> None:
    """Objects lacking run are rejected by the protocol."""
    assert not isinstance(NotAnExecutor(), SkillScriptExecutor)


# ---------------------------------------------------------------------------
# Backwards compatibility: duck-typed executors still work end to end
# ---------------------------------------------------------------------------


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a minimal skill with one script."""
    skill = tmp_path / 'demo-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'SKILL.md').write_text(
        '---\nname: demo-skill\ndescription: Demo skill for executor tests.\n---\n\nDemo body.\n'
    )
    (skill / 'scripts' / 'run.py').write_text('#!/usr/bin/env python3\nprint("hi")\n')
    return tmp_path


async def test_duck_typed_executor_runs_through_toolset(skill_dir: Path) -> None:
    """A duck-typed executor reaches run_skill_script unchanged."""
    executor = DuckTypedExecutor()
    toolset = SkillsToolset(directories=[SkillsDirectory(path=skill_dir, script_executor=executor)])

    skill = toolset.skills['demo-skill']
    script = next(s for s in skill.scripts if s.name == 'scripts/run.py')

    ctx = SimpleNamespace(deps=None)
    result = await script.run(ctx=ctx, args={'query': 'x'})

    assert result == 'duck ran scripts/run.py'
    assert executor.calls == [('scripts/run.py', {'query': 'x'})]


async def test_custom_executor_receives_skill_relative_script_name(skill_dir: Path) -> None:
    """script.name stays relative to the skill folder, and uri points inside it.

    The sandbox executors anchor the skill root on the nearest ``SKILL.md``
    ancestor of ``script.uri``; this pins the layout that relies on.
    """
    executor = DuckTypedExecutor()
    toolset = SkillsToolset(directories=[SkillsDirectory(path=skill_dir, script_executor=executor)])

    script = next(s for s in toolset.skills['demo-skill'].scripts if s.name.endswith('run.py'))

    assert script.name == 'scripts/run.py'
    assert Path(str(script.uri)).parent.name == 'scripts'


# ---------------------------------------------------------------------------
# Registry skills are the least-trusted source, so they must be sandboxable
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_skills_root(tmp_path: Path) -> Path:
    """A skills root shaped like a cloned registry checkout."""
    skill = tmp_path / 'remote-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: remote-skill\ndescription: From a registry.\n---\n\nBody.\n')
    (skill / 'scripts' / 'run.py').write_text('#!/usr/bin/env python3\nprint("hi")\n')
    return tmp_path


def test_git_registry_forwards_script_executor(registry_skills_root: Path) -> None:
    """Without this, registry scripts always run on the host."""
    pytest.importorskip('git')
    from pydantic_ai_skills import GitSkillsRegistry

    executor = DuckTypedExecutor()
    registry = GitSkillsRegistry(
        repo_url='https://example.invalid/repo.git',
        target_dir=registry_skills_root,
        auto_install=False,
        script_executor=executor,
    )

    script = next(s for s in registry.get_skills()[0].scripts if s.name.endswith('run.py'))

    assert isinstance(script, FileBasedSkillScript)
    assert script.executor is executor


def test_s3_registry_forwards_script_executor(registry_skills_root: Path) -> None:
    """Without this, registry scripts always run on the host."""
    executor = DuckTypedExecutor()
    from pydantic_ai_skills import S3SkillsRegistry

    registry = S3SkillsRegistry(
        bucket='irrelevant',
        target_dir=registry_skills_root,
        boto3_client=object(),
        auto_install=False,
        script_executor=executor,
    )

    script = next(s for s in registry.get_skills()[0].scripts if s.name.endswith('run.py'))

    assert isinstance(script, FileBasedSkillScript)
    assert script.executor is executor


# ---------------------------------------------------------------------------
# Sandbox executors: staging boundary
# ---------------------------------------------------------------------------


@pytest.fixture
def staged_skill(tmp_path: Path) -> Path:
    """A skill folder with a nested script, a top-level resource, and a symlink escape."""
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('host secret')

    skill = tmp_path / 'demo-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'resources').mkdir()
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'resources' / 'data.json').write_text('{"k": 1}')
    (skill / 'scripts' / 'run.py').write_text('print("hi")\n')
    (skill / 'scripts' / 'escape.txt').symlink_to(outside / 'secret.txt')
    return skill


def _collect_staged(skill_root: Path) -> dict[str, Path]:
    """Drain the staging generator into a mapping of relative path to source file."""
    return dict(iter_stageable_files(skill_root))


def test_staging_uses_skill_root_not_script_parent(staged_skill: Path) -> None:
    """script.name is relative to the skill folder, so the root is above scripts/."""
    script = SkillScript(name='scripts/run.py', uri=str(staged_skill / 'scripts' / 'run.py'))

    assert skill_root_for(script) == staged_skill.resolve()


def test_skill_root_survives_depth_changing_symlink(tmp_path: Path) -> None:
    """A resolved uri can be shallower than script.name; anchoring on SKILL.md fixes it.

    Walking up by name depth would land on the skills root and stage every
    sibling skill into the sandbox.
    """
    root = tmp_path / 'skills-root'
    (root / 'skill-a' / 'scripts').mkdir(parents=True)
    (root / 'skill-a' / 'SKILL.md').write_text('---\nname: skill-a\ndescription: A.\n---\n\nBody.\n')
    (root / 'skill-a' / 'run.py').write_text('print("hi")\n')
    (root / 'skill-a' / 'scripts' / 'run.py').symlink_to(root / 'skill-a' / 'run.py')

    # Mirrors what discovery stores: unresolved name, resolved uri.
    script = SkillScript(name='scripts/run.py', uri=str((root / 'skill-a' / 'run.py').resolve()))

    assert skill_root_for(script) == (root / 'skill-a').resolve()


@pytest.mark.filterwarnings('ignore:Skipping.*symlink escape:UserWarning')
def test_staging_includes_whole_skill_folder(staged_skill: Path) -> None:
    """SKILL.md and resources/ are staged, not just the script's own directory."""
    staged = _collect_staged(staged_skill.resolve())

    assert 'SKILL.md' in staged
    assert 'resources/data.json' in staged
    assert 'scripts/run.py' in staged


@pytest.mark.filterwarnings('ignore:Skipping.*symlink escape:UserWarning')
def test_staging_skips_symlinks_escaping_the_skill_folder(staged_skill: Path) -> None:
    """Following an escaping symlink would copy a host file into the sandbox."""
    staged = _collect_staged(staged_skill.resolve())

    assert 'scripts/escape.txt' not in staged
    assert not any('secret' in path.name for path in staged.values())


def test_staging_warns_about_symlink_escape(staged_skill: Path) -> None:
    """The skipped symlink is reported rather than silently dropped."""
    skill_root = staged_skill.resolve()

    with pytest.warns(UserWarning, match='symlink escape'):
        _collect_staged(skill_root)


# ---------------------------------------------------------------------------
# LocalSandbox: Pyodide wrapper semantics
# ---------------------------------------------------------------------------


class _StubPyodideSandbox:
    """Runs the generated wrapper under CPython so the tests need no SDK."""

    async def aexecute_python(self, code: str, cwd: str | None = None, preload_packages: Any = None) -> Any:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exec(compile(code, '<wrapper>', 'exec'), {'__name__': '__wrapper__'})
        return SimpleNamespace(stdout=buffer.getvalue(), stderr='', error=None, exit_code=0)

    def read_file(self, path: str) -> str:
        return Path(path).read_text(encoding='utf-8')


async def test_python_wrapper_normalizes_boolean_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """sys.exit(not ok) yields a bool, which must be written as 1 rather than 'True'."""
    monkeypatch.setattr(localsandbox_module, '_EXIT_CODE_FILE', str(tmp_path / 'exit_code'))
    script = tmp_path / 'run.py'
    script.write_text('import sys\nsys.exit(not False)\n', encoding='utf-8')

    _, _, exit_code = await LocalSandboxScriptExecutor()._run_python(
        _StubPyodideSandbox(), str(script), str(tmp_path), None
    )

    assert exit_code == 1


async def test_python_wrapper_preserves_non_bmp_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSON-escaping argv would deliver lone surrogates instead of the character."""
    monkeypatch.setattr(localsandbox_module, '_EXIT_CODE_FILE', str(tmp_path / 'exit_code'))
    script = tmp_path / 'run.py'
    script.write_text('import sys\nprint(sys.argv[1:])\n', encoding='utf-8')

    stdout, _, _ = await LocalSandboxScriptExecutor()._run_python(
        _StubPyodideSandbox(), str(script), str(tmp_path), {'msg': 'hi 😀'}
    )

    assert 'hi 😀' in stdout
    assert '\\ud83d' not in stdout


# ---------------------------------------------------------------------------
# Sandbox reuse
# ---------------------------------------------------------------------------


class _LocalSandboxShell:
    """Records the shell commands LocalSandbox fakes are asked to run.

    Shared by every LocalSandbox stub so a new call in the executor fails them
    all at once rather than whichever one was remembered.
    """

    def __init__(self) -> None:
        self.shell_commands: list[str] = []

    def bash(self, command: str) -> Any:
        self.shell_commands.append(command)
        return SimpleNamespace(stdout='', stderr='', exit_code=0, duration_ms=0)


class _FakeLocalSandbox(_LocalSandboxShell):
    """Records the files staged into it and whether it was closed."""

    instances: list[_FakeLocalSandbox] = []

    def __init__(self, files: dict[str, Any], cwd: str, **kwargs: Any) -> None:
        super().__init__()
        self.files = files
        self.closed = False
        type(self).instances.append(self)

    def __exit__(self, *exc: Any) -> None:
        self.closed = True


@pytest.mark.filterwarnings('ignore:Skipping.*symlink escape:UserWarning')
def test_reused_localsandbox_restages_after_same_root_edits(
    staged_skill: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """auto_reload surfaces edits under an unchanged root, so the fingerprint must catch them."""
    monkeypatch.setattr(_FakeLocalSandbox, 'instances', [])
    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: _FakeLocalSandbox)
    executor = LocalSandboxScriptExecutor(reuse_sandbox=True)
    skill_root = staged_skill.resolve()

    first = executor._get_sandbox(skill_root)
    assert executor._get_sandbox(skill_root) is first, 'unchanged skill should reuse the sandbox'

    (staged_skill / 'scripts' / 'run.py').write_text('print("edited")\n')
    second = executor._get_sandbox(skill_root)

    assert second is not first, 'edited skill must be restaged'
    assert first.closed, 'the stale sandbox should be closed'
    assert b'edited' in second.files[f'{executor.workdir}/scripts/run.py']


class _FakeOpenSandbox:
    """Counts creations and kills so lifetime handling is observable."""

    created = 0
    killed = 0

    @classmethod
    async def create(cls, image: str, env: Any = None, timeout: Any = None) -> _FakeOpenSandbox:
        cls.created += 1
        return cls()

    async def kill(self) -> None:
        type(self).killed += 1


async def test_reused_opensandbox_recreated_after_lifetime_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sandbox.create fixes the lifetime, so a stale handle must not be handed out forever."""
    monkeypatch.setattr(_FakeOpenSandbox, 'created', 0)
    monkeypatch.setattr(_FakeOpenSandbox, 'killed', 0)
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: _FakeOpenSandbox)

    # Lifetime shorter than the per-script timeout leaves no headroom, so the
    # deadline is already in the past when the sandbox is handed back.
    executor = OpenSandboxScriptExecutor(timeout=30, reuse_sandbox=True, sandbox_timeout=timedelta(seconds=1))
    await executor._get_sandbox()
    await executor._get_sandbox()

    assert _FakeOpenSandbox.created == 2, 'expired sandbox must be replaced'
    assert _FakeOpenSandbox.killed == 1, 'the expired sandbox must be killed'


async def test_reused_opensandbox_kept_within_its_lifetime(monkeypatch: pytest.MonkeyPatch) -> None:
    """A sandbox with time left is reused rather than recreated every run."""
    monkeypatch.setattr(_FakeOpenSandbox, 'created', 0)
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: _FakeOpenSandbox)

    executor = OpenSandboxScriptExecutor(timeout=30, reuse_sandbox=True, sandbox_timeout=timedelta(minutes=10))

    assert await executor._get_sandbox() is await executor._get_sandbox()
    assert _FakeOpenSandbox.created == 1


# ---------------------------------------------------------------------------
# Missing optional dependencies
# ---------------------------------------------------------------------------


def test_opensandbox_reports_missing_extra() -> None:
    """Without the SDK installed, the error names the extra that provides it."""
    with patch.dict('sys.modules', {'opensandbox': None}):
        with pytest.raises(ImportError, match=r'pydantic-ai-skills\[opensandbox\]'):
            opensandbox_module._require_opensandbox()


def test_localsandbox_reports_missing_extra() -> None:
    """Without the SDK installed, the error names the extra that provides it."""
    with patch.dict('sys.modules', {'localsandbox': None}):
        with pytest.raises(ImportError, match=r'pydantic-ai-skills\[localsandbox\]'):
            localsandbox_module._require_localsandbox()


async def test_localsandbox_rejects_unsupported_script_type(tmp_path: Path) -> None:
    """LocalSandbox supports .py and shell scripts only, and says so before provisioning."""
    script_file = tmp_path / 'thing.rb'
    script_file.write_text('puts "hi"\n')
    script = SkillScript(name='thing.rb', uri=str(script_file))
    executor = LocalSandboxScriptExecutor()

    with pytest.raises(ValueError, match='unsupported type'):
        await executor.run(script)


def _script_without_uri() -> SkillScript:
    """Build a script whose uri is None."""
    # __post_init__ requires a uri or a function, so clear it afterwards.
    script = SkillScript(name='no-uri', uri='placeholder')
    script.uri = None
    return script


async def test_localsandbox_requires_a_uri() -> None:
    """The LocalSandbox executor rejects scripts with no URI."""
    executor = LocalSandboxScriptExecutor()
    script = _script_without_uri()

    with pytest.raises(ValueError, match='has no URI'):
        await executor.run(script)


async def test_opensandbox_requires_a_uri() -> None:
    """The OpenSandbox executor rejects scripts with no URI."""
    executor = OpenSandboxScriptExecutor()
    script = _script_without_uri()

    with pytest.raises(ValueError, match='has no URI'):
        await executor.run(script)


# ---------------------------------------------------------------------------
# Full run() paths, driven by fake SDK objects
# ---------------------------------------------------------------------------


@pytest.fixture
def runnable_skill(tmp_path: Path) -> Path:
    """A skill whose script sits in scripts/ alongside a top-level resource."""
    skill = tmp_path / 'demo-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'resources').mkdir()
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'resources' / 'data.json').write_text('{"k": 1}')
    (skill / 'scripts' / 'run.py').write_text('print("hi")\n')
    (skill / 'scripts' / 'go.sh').write_text('#!/bin/sh\necho hi\n')
    return skill


def _script_in(skill: Path, name: str) -> SkillScript:
    """Build a discovery-shaped script for a file inside a skill folder."""
    return SkillScript(name=name, uri=str(skill / name), skill_name=skill.name)


def _fake_filesystem(
    *,
    write_files: Any,
    create_directories: Any,
    delete_files: Any,
    delete_directories: Any,
) -> SimpleNamespace:
    """Build the `sandbox.files` surface the OpenSandbox executor calls.

    Kept in one place so a new call in the executor fails every fake at once
    rather than only the ones that happened to be updated.
    """
    return SimpleNamespace(
        write_files=write_files,
        create_directories=create_directories,
        delete_files=delete_files,
        delete_directories=delete_directories,
    )


class _FakeOpenSandboxRun:
    """A sandbox that records the staged files and the command it was asked to run."""

    def __init__(self) -> None:
        self.written: list[Any] = []
        self.directories: list[str] = []
        self.deleted: list[str] = []
        self.deleted_dirs: list[str] = []
        self.command: str | None = None
        self.opts: Any = None
        self.killed = False
        self.files = _fake_filesystem(
            write_files=self._write_files,
            create_directories=self._create_directories,
            delete_files=self._delete_files,
            delete_directories=self._delete_directories,
        )
        self.commands = SimpleNamespace(run=self._run)

    async def _create_directories(self, entries: list[Any]) -> None:
        self.directories.extend(e.path for e in entries)

    async def _write_files(self, entries: list[Any]) -> None:
        self.written.extend(entries)

    async def _delete_files(self, paths: list[str]) -> None:
        self.deleted.extend(paths)

    async def _delete_directories(self, paths: list[str]) -> None:
        self.deleted_dirs.extend(paths)

    async def _run(self, command: str, opts: Any = None) -> Any:
        self.command = command
        self.opts = opts
        return SimpleNamespace(
            exit_code=0,
            logs=SimpleNamespace(
                stdout=[SimpleNamespace(text='hello\n')],
                stderr=[SimpleNamespace(text='warned\n')],
            ),
        )

    async def kill(self) -> None:
        self.killed = True


@pytest.fixture
def fake_opensandbox_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the SDK model modules that run() imports at call time."""

    class WriteEntry:
        def __init__(self, path: str, data: Any = None, mode: int = 0o644) -> None:
            self.path, self.data, self.mode = path, data, mode

    class RunCommandOpts:
        def __init__(self, **kwargs: Any) -> None:
            self.__dict__.update(kwargs)

    package = types.ModuleType('opensandbox')
    models = types.ModuleType('opensandbox.models')
    models.WriteEntry = WriteEntry  # type: ignore[attr-defined]
    execd = types.ModuleType('opensandbox.models.execd')
    execd.RunCommandOpts = RunCommandOpts  # type: ignore[attr-defined]
    package.models = models  # type: ignore[attr-defined]
    models.execd = execd  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, 'opensandbox', package)
    monkeypatch.setitem(sys.modules, 'opensandbox.models', models)
    monkeypatch.setitem(sys.modules, 'opensandbox.models.execd', execd)


async def test_opensandbox_run_stages_and_executes(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """The whole skill folder is staged and the script runs from its own directory."""
    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(workdir='/workspace/skills')

    output = await executor.run(_script_in(runnable_skill, 'scripts/run.py'), {'query': 'x', 'verbose': True})

    staged = {entry.path for entry in sandbox.written}
    assert staged == {
        '/workspace/skills/SKILL.md',
        '/workspace/skills/resources/data.json',
        '/workspace/skills/scripts/run.py',
        '/workspace/skills/scripts/go.sh',
    }
    # write_files does not create parents, so directories must be made first.
    assert '/workspace/skills/scripts' in sandbox.directories
    assert '/workspace/skills/resources' in sandbox.directories
    assert sandbox.command == 'python3 /workspace/skills/scripts/run.py --query x --verbose'
    assert sandbox.opts.working_directory == '/workspace/skills/scripts'
    assert output == 'hello\n\n\nStderr:\nwarned'
    assert sandbox.killed, 'a non-reused sandbox is killed after the run'


def _returning(value: Any) -> Any:
    """Build an async factory that always yields ``value``."""

    async def factory(*args: Any, **kwargs: Any) -> Any:
        return value

    return factory


async def test_opensandbox_default_workdir_avoids_tmp() -> None:
    """/tmp is world-writable, so a staged script could be swapped before it runs."""
    assert not OpenSandboxScriptExecutor()._workdir.startswith('/tmp')


async def test_opensandbox_aclose_kills_reused_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing releases the container rather than leaving it to expire."""
    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(reuse_sandbox=True)
    await executor._get_sandbox()

    await executor.aclose()

    assert sandbox.killed
    assert executor._sandbox is None


class _FakeLocalSandboxRun(_LocalSandboxShell):
    """A LocalSandbox stand-in covering both the Pyodide and just-bash paths."""

    def __init__(self, files: dict[str, Any], cwd: str, **kwargs: Any) -> None:
        super().__init__()
        self.files = files
        self.cwd = cwd
        self.closed = False
        self.command: str | None = None

    async def aexecute_python(self, code: str, cwd: str | None = None, preload_packages: Any = None) -> Any:
        self.command = code
        return SimpleNamespace(stdout='hello\n', stderr='warned\n', error=None, exit_code=0)

    async def abash(self, command: str) -> Any:
        self.command = command
        return SimpleNamespace(stdout='hello\n', stderr='warned\n', exit_code=0, duration_ms=1)

    def read_file(self, path: str) -> str:
        return '0'

    def __exit__(self, *exc: Any) -> None:
        self.closed = True


@pytest.fixture
def fake_localsandbox_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the SDK module that _run_shell imports at call time."""

    class CommandError(Exception):
        def __init__(self, message: str, exit_code: int, stdout: str, stderr: str) -> None:
            super().__init__(message)
            self.exit_code, self.stdout, self.stderr = exit_code, stdout, stderr

    module = types.ModuleType('localsandbox')
    module.CommandError = CommandError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, 'localsandbox', module)


async def test_localsandbox_run_executes_shell_script(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch, fake_localsandbox_module: None
) -> None:
    """Shell scripts go through abash with normal --flag value argv."""
    created: list[_FakeLocalSandboxRun] = []

    def factory(**kwargs: Any) -> _FakeLocalSandboxRun:
        sandbox = _FakeLocalSandboxRun(**kwargs)
        created.append(sandbox)
        return sandbox

    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: factory)
    executor = LocalSandboxScriptExecutor(workdir='/data/skill')

    output = await executor.run(_script_in(runnable_skill, 'scripts/go.sh'), {'query': 'x'})

    assert created[0].command == 'cd /data/skill/scripts && sh /data/skill/scripts/go.sh --query x'
    assert output == 'hello\n\n\nStderr:\nwarned'
    assert created[0].closed, 'a non-reused sandbox is closed after the run'


async def test_localsandbox_run_executes_python_script(runnable_skill: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Python scripts are wrapped for Pyodide and staged with the whole skill folder."""
    created: list[_FakeLocalSandboxRun] = []

    def factory(**kwargs: Any) -> _FakeLocalSandboxRun:
        sandbox = _FakeLocalSandboxRun(**kwargs)
        created.append(sandbox)
        return sandbox

    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: factory)
    executor = LocalSandboxScriptExecutor(workdir='/data/skill')

    output = await executor.run(_script_in(runnable_skill, 'scripts/run.py'))

    assert '/data/skill/SKILL.md' in created[0].files
    assert '/data/skill/resources/data.json' in created[0].files
    assert 'runpy.run_path' in (created[0].command or '')
    assert output == 'hello\n\n\nStderr:\nwarned'


async def test_localsandbox_surfaces_pyodide_error_with_stderr(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An uncaught exception must not be dropped in favour of earlier stderr."""

    class _Failing(_FakeLocalSandboxRun):
        async def aexecute_python(self, code: str, cwd: str | None = None, preload_packages: Any = None) -> Any:
            return SimpleNamespace(stdout='partial\n', stderr='warned\n', error='Traceback: boom', exit_code=1)

    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: _Failing)
    executor = LocalSandboxScriptExecutor()

    output = await executor.run(_script_in(runnable_skill, 'scripts/run.py'))

    assert 'warned' in output
    assert 'Traceback: boom' in output


async def test_localsandbox_close_releases_reused_sandbox(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Closing drops the sandbox and its staging fingerprint."""
    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: _FakeLocalSandboxRun)
    executor = LocalSandboxScriptExecutor(reuse_sandbox=True)
    sandbox = executor._get_sandbox(runnable_skill.resolve())

    executor.close()

    assert sandbox.closed
    assert executor._sandbox is None
    assert executor._staged_fingerprint is None


# ---------------------------------------------------------------------------
# Version-control metadata must never reach the sandbox
# ---------------------------------------------------------------------------


@pytest.fixture
def cloned_skill(tmp_path: Path) -> Path:
    """A skill whose SKILL.md sits at a clone root, so .git is inside the skill root."""
    clone = tmp_path / 'clone'
    (clone / '.git').mkdir(parents=True)
    (clone / 'scripts').mkdir()
    (clone / 'SKILL.md').write_text('---\nname: root-skill\ndescription: At the clone root.\n---\n\nBody.\n')
    (clone / 'scripts' / 'run.py').write_text('print("hi")\n')
    (clone / '.git' / 'config').write_text(
        '[remote "origin"]\n\turl = https://oauth2:ghp_SECRETTOKEN@github.com/acme/skills.git\n'
    )
    return clone


def test_staging_excludes_version_control_metadata(cloned_skill: Path) -> None:
    """GitSkillsRegistry clones with a token-bearing URL, which git stores in .git/config.

    Staging that would hand the caller's PAT to any script the sandbox runs.
    """
    staged = _collect_staged(cloned_skill.resolve())

    assert sorted(staged) == ['SKILL.md', 'scripts/run.py']
    assert not any(path.startswith('.git/') for path in staged)
    assert not any('ghp_SECRETTOKEN' in source.read_text(errors='ignore') for source in staged.values())


def test_staging_excludes_are_pruned_not_just_filtered(cloned_skill: Path) -> None:
    """Nested files under an excluded directory are skipped too, without descending."""
    deep = cloned_skill / '.git' / 'objects' / 'ab'
    deep.mkdir(parents=True)
    (deep / 'cdef').write_bytes(b'object data')

    staged = _collect_staged(cloned_skill.resolve())

    assert not any('.git' in path for path in staged)


def test_pycache_is_not_staged(cloned_skill: Path) -> None:
    """__pycache__ is noise in a sandbox and is already excluded from resources."""
    cache = cloned_skill / 'scripts' / '__pycache__'
    cache.mkdir()
    (cache / 'run.cpython-313.pyc').write_bytes(b'\x00')

    staged = _collect_staged(cloned_skill.resolve())

    assert not any('__pycache__' in path for path in staged)


async def test_localsandbox_shell_script_runs_from_its_own_directory(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch, fake_localsandbox_module: None
) -> None:
    """Abash takes no cwd, so the command must change directory itself.

    Without this a shell script reading ../resources/data.json resolves it
    differently than under LocalSkillScriptExecutor.
    """
    created: list[_FakeLocalSandboxRun] = []

    def factory(**kwargs: Any) -> _FakeLocalSandboxRun:
        sandbox = _FakeLocalSandboxRun(**kwargs)
        created.append(sandbox)
        return sandbox

    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: factory)
    executor = LocalSandboxScriptExecutor(workdir='/data/skill')

    await executor.run(_script_in(runnable_skill, 'scripts/go.sh'))

    assert (created[0].command or '').startswith('cd /data/skill/scripts && ')


# ---------------------------------------------------------------------------
# OpenSandbox command construction
# ---------------------------------------------------------------------------


def _opensandbox_command(executor: OpenSandboxScriptExecutor, script: Path, args: Any = None) -> str:
    """Build the command line the executor would run for a local script file."""
    return executor._build_command(script, f'/workspace/skills/{script.name}', script.suffix.lower(), args)


@pytest.mark.parametrize(
    ('shebang', 'expected_prefix'),
    [
        ('#!/bin/bash\n', '/bin/bash '),
        ('#!/usr/bin/env bash\n', '/usr/bin/env bash '),
        ('#!/usr/bin/env python3\n', '/usr/bin/env python3 '),
    ],
)
def test_opensandbox_honors_shebang(tmp_path: Path, shebang: str, expected_prefix: str) -> None:
    """A bash-only script must not be launched with sh just because it ends in .sh."""
    script = tmp_path / 'go.sh'
    script.write_text(f'{shebang}echo hi\n')

    command = _opensandbox_command(OpenSandboxScriptExecutor(), script)

    assert command.startswith(expected_prefix)


def test_opensandbox_falls_back_to_suffix_without_shebang(tmp_path: Path) -> None:
    """Without a shebang the suffix mapping still applies."""
    script = tmp_path / 'go.sh'
    script.write_text('echo hi\n')

    command = _opensandbox_command(OpenSandboxScriptExecutor(), script)

    assert command.startswith('sh ')


def test_opensandbox_runs_unknown_types_directly(tmp_path: Path) -> None:
    """An executable with no shebang and no known suffix is run as-is."""
    script = tmp_path / 'tool'
    script.write_text('binary-ish\n')

    command = _opensandbox_command(OpenSandboxScriptExecutor(), script)

    assert command == '/workspace/skills/tool'


def test_opensandbox_shebang_does_not_resolve_against_the_host(tmp_path: Path) -> None:
    """The interpreter must be taken verbatim; it has to exist in the container, not here."""
    script = tmp_path / 'go.sh'
    script.write_text('#!/opt/custom/bin/bash\necho hi\n')

    command = _opensandbox_command(OpenSandboxScriptExecutor(), script)

    assert command.startswith('/opt/custom/bin/bash ')


# ---------------------------------------------------------------------------
# Concurrency: one shared sandbox must not be torn down mid-run
# ---------------------------------------------------------------------------


@pytest.fixture
def second_skill(tmp_path: Path) -> Path:
    """A second skill folder, so a reused executor has to switch roots."""
    skill = tmp_path / 'other-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: other-skill\ndescription: Other.\n---\n\nBody.\n')
    (skill / 'scripts' / 'run.py').write_text('print("other")\n')
    return skill


class _SlowLocalSandbox(_LocalSandboxShell):
    """Yields control during execution so a competing run can interleave."""

    live: int = 0
    max_live: int = 0
    closed_while_running = False

    def __init__(self, files: dict[str, Any], cwd: str, **kwargs: Any) -> None:
        super().__init__()
        self.files = files
        self.closed = False
        self.running = False

    async def aexecute_python(self, code: str, cwd: str | None = None, preload_packages: Any = None) -> Any:
        self.running = True
        type(self).live += 1
        type(self).max_live = max(type(self).max_live, type(self).live)
        await anyio.sleep(0.02)  # Long enough for a competing run to reach _get_sandbox.
        if self.closed:
            type(self).closed_while_running = True
        type(self).live -= 1
        self.running = False
        return SimpleNamespace(stdout='ok\n', stderr='', error=None, exit_code=0)

    def read_file(self, path: str) -> str:
        return '0'

    def __exit__(self, *exc: Any) -> None:
        if self.running:
            type(self).closed_while_running = True
        self.closed = True


async def test_reused_localsandbox_serializes_concurrent_runs(
    runnable_skill: Path, second_skill: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second skill must not close the sandbox the first run is still using."""
    monkeypatch.setattr(_SlowLocalSandbox, 'live', 0)
    monkeypatch.setattr(_SlowLocalSandbox, 'max_live', 0)
    monkeypatch.setattr(_SlowLocalSandbox, 'closed_while_running', False)
    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: _SlowLocalSandbox)
    executor = LocalSandboxScriptExecutor(reuse_sandbox=True)

    async with anyio.create_task_group() as tg:
        tg.start_soon(executor.run, _script_in(runnable_skill, 'scripts/run.py'))
        tg.start_soon(executor.run, _script_in(second_skill, 'scripts/run.py'))

    assert not _SlowLocalSandbox.closed_while_running, 'a live sandbox was closed mid-run'
    assert _SlowLocalSandbox.max_live == 1, 'reused-sandbox runs must not overlap'


class _SlowOpenSandbox:
    """Counts containers so a duplicate creation is observable."""

    created = 0

    def __init__(self) -> None:
        self.killed = False
        self.files = _fake_filesystem(
            write_files=self._noop,
            create_directories=self._noop,
            delete_files=self._noop,
            delete_directories=self._noop,
        )
        self.commands = SimpleNamespace(run=self._run)

    @classmethod
    async def create(cls, image: str, env: Any = None, timeout: Any = None) -> _SlowOpenSandbox:
        cls.created += 1
        await anyio.sleep(0.02)  # Suspends inside create, where the race lived.
        return cls()

    async def _noop(self, entries: list[Any]) -> None:
        return None

    async def _run(self, command: str, opts: Any = None) -> Any:
        await anyio.sleep(0.01)
        return SimpleNamespace(
            exit_code=0,
            logs=SimpleNamespace(stdout=[SimpleNamespace(text='ok\n')], stderr=[]),
        )

    async def kill(self) -> None:
        self.killed = True


async def test_reused_opensandbox_creates_one_container_under_concurrency(
    runnable_skill: Path,
    second_skill: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_opensandbox_models: None,
) -> None:
    """Two concurrent first runs must not each create a container, leaking one."""
    monkeypatch.setattr(_SlowOpenSandbox, 'created', 0)
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: _SlowOpenSandbox)
    executor = OpenSandboxScriptExecutor(reuse_sandbox=True)

    async with anyio.create_task_group() as tg:
        tg.start_soon(executor.run, _script_in(runnable_skill, 'scripts/run.py'))
        tg.start_soon(executor.run, _script_in(second_skill, 'scripts/run.py'))

    assert _SlowOpenSandbox.created == 1, 'a duplicate container was created and leaked'
    assert executor._sandbox is not None


class _HangingOpenSandbox(_SlowOpenSandbox):
    """Blocks inside command execution so the run can be cancelled mid-flight."""

    async def _run(self, command: str, opts: Any = None) -> Any:
        await anyio.sleep_forever()

    async def kill(self) -> None:
        # A real kill() is a network round trip, so it contains a checkpoint.
        # Without one, cancellation would never get a chance to interrupt it and
        # this test would pass even with the shield removed.
        await anyio.lowlevel.checkpoint()
        self.killed = True


async def test_opensandbox_kills_container_even_when_cancelled(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """Cleanup must survive cancellation, or the container leaks until it expires."""
    monkeypatch.setattr(_HangingOpenSandbox, 'created', 0)
    sandboxes: list[_HangingOpenSandbox] = []

    async def create(image: str, env: Any = None, timeout: Any = None) -> _HangingOpenSandbox:
        sandbox = _HangingOpenSandbox()
        sandboxes.append(sandbox)
        return sandbox

    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=create))
    executor = OpenSandboxScriptExecutor()

    with anyio.move_on_after(0.05):
        await executor.run(_script_in(runnable_skill, 'scripts/run.py'))

    assert sandboxes, 'the run should have created a container'
    assert sandboxes[0].killed, 'a cancelled run must still tear its container down'


async def test_reused_opensandbox_removes_deleted_files_on_restage(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """A reused container keeps what earlier runs wrote, so restaging must prune."""
    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(workdir='/workspace/skills', reuse_sandbox=True)
    script = _script_in(runnable_skill, 'scripts/run.py')

    await executor.run(script)
    (runnable_skill / 'resources' / 'data.json').unlink()
    await executor.run(script)

    assert sandbox.deleted == ['/workspace/skills/resources/data.json']


async def test_reused_opensandbox_skips_restaging_when_unchanged(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """An unchanged skill need not be re-uploaded on every run."""
    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(reuse_sandbox=True)
    script = _script_in(runnable_skill, 'scripts/run.py')

    await executor.run(script)
    uploaded_after_first = len(sandbox.written)
    await executor.run(script)

    assert len(sandbox.written) == uploaded_after_first


# ---------------------------------------------------------------------------
# Skill root comes from discovery, not from inference
# ---------------------------------------------------------------------------


def test_skill_root_prefers_the_root_recorded_by_discovery(tmp_path: Path) -> None:
    """A skill nesting another skill makes the nearest SKILL.md the wrong answer.

    Discovery records the folder it loaded the skill from, so the parent's script
    still stages the parent's resources rather than the nested skill's folder.
    """
    root = tmp_path / 'root'
    parent = root / 'parent'
    (parent / 'scripts').mkdir(parents=True)
    (parent / 'resources').mkdir()
    (parent / 'SKILL.md').write_text('---\nname: parent-skill\ndescription: Parent.\n---\n\nBody.\n')
    (parent / 'scripts' / 'SKILL.md').write_text('---\nname: nested-skill\ndescription: Nested.\n---\n\nBody.\n')
    (parent / 'resources' / 'data.json').write_text('{"v": 1}')
    (parent / 'scripts' / 'run.py').write_text('print("hi")\n')

    skills = {skill.name: skill for skill in discover_skills(root)}
    script = next(s for s in skills['parent-skill'].scripts if s.name.endswith('run.py'))

    assert skill_root_for(script) == parent.resolve()
    assert 'resources/data.json' in dict(iter_stageable_files(skill_root_for(script)))


def test_skill_root_falls_back_when_not_recorded(tmp_path: Path) -> None:
    """Scripts built outside discovery still resolve via the SKILL.md anchor."""
    skill = tmp_path / 'demo-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'scripts' / 'run.py').write_text('print("hi")\n')

    script = SkillScript(name='scripts/run.py', uri=str(skill / 'scripts' / 'run.py'))

    assert skill_root_for(script) == skill.resolve()


async def test_reused_opensandbox_restages_when_only_the_skill_root_differs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """Two skills can share relative paths, sizes and mtimes, so the root must be keyed too.

    Without it the second skill would run the first skill's staged script.
    """
    timestamp = 1_700_000_000
    for name, body in (('skill-a', 'print("A")\n'), ('skill-b', 'print("B")\n')):
        skill = tmp_path / name
        (skill / 'scripts').mkdir(parents=True)
        (skill / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: Same shape.\n---\n\nBody.\n')
        (skill / 'scripts' / 'run.py').write_text(body)  # Identical length, so identical size.
        for path in (skill / 'SKILL.md', skill / 'scripts' / 'run.py'):
            os.utime(path, (timestamp, timestamp))

    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(workdir='/workspace/skills', reuse_sandbox=True)

    await executor.run(_script_in(tmp_path / 'skill-a', 'scripts/run.py'))
    await executor.run(_script_in(tmp_path / 'skill-b', 'scripts/run.py'))

    staged_scripts = [e.data for e in sandbox.written if e.path.endswith('scripts/run.py')]
    assert staged_scripts[-1] == b'print("B")\n', "skill B's script must replace skill A's"


def test_staging_rejects_symlink_aliases_into_excluded_directories(cloned_skill: Path) -> None:
    """Pruning directories does not stop an alias to a file inside one.

    A committed `resources/config -> ../.git/config` is an ordinary file entry
    whose target still lives under the skill root, so it would otherwise carry
    the clone token into the sandbox.
    """
    (cloned_skill / 'resources').mkdir()
    (cloned_skill / 'resources' / 'config').symlink_to(cloned_skill / '.git' / 'config')
    skill_root = cloned_skill.resolve()

    with pytest.warns(UserWarning, match='excluded directory'):
        staged = _collect_staged(skill_root)

    assert 'resources/config' not in staged
    assert not any('ghp_SECRETTOKEN' in source.read_text(errors='ignore') for source in staged.values())


async def test_reused_sandboxes_detect_edits_that_preserve_size_and_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """Reproducible-build tooling pins mtimes, so size+mtime cannot detect an edit.

    A same-size change with the mtime restored must still be restaged.
    """
    skill = tmp_path / 'demo-skill'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    script = skill / 'scripts' / 'run.py'
    script.write_text('print("A")\n')
    stat = script.stat()
    stamp_ns = (stat.st_atime_ns, stat.st_mtime_ns)

    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(reuse_sandbox=True)
    skill_script = _script_in(skill, 'scripts/run.py')

    await executor.run(skill_script)
    script.write_text('print("B")\n')  # Same length as the original.
    os.utime(script, ns=stamp_ns)  # Same mtime, to the nanosecond.
    await executor.run(skill_script)

    staged = [entry.data for entry in sandbox.written if entry.path.endswith('scripts/run.py')]
    assert staged[-1] == b'print("B")\n', 'a same-size, same-mtime edit must still be restaged'


async def test_reused_opensandbox_removes_directories_replaced_by_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """A path that was a directory must be removed before a file can take its place."""
    first = tmp_path / 'skill-a'
    (first / 'resources' / 'config').mkdir(parents=True)
    (first / 'SKILL.md').write_text('---\nname: skill-a\ndescription: A.\n---\n\nBody.\n')
    (first / 'resources' / 'config' / 'item').write_text('nested\n')
    (first / 'run.py').write_text('print("A")\n')

    second = tmp_path / 'skill-b'
    (second / 'resources').mkdir(parents=True)
    (second / 'SKILL.md').write_text('---\nname: skill-b\ndescription: B.\n---\n\nBody.\n')
    (second / 'resources' / 'config').write_text('now a file\n')
    (second / 'run.py').write_text('print("B")\n')

    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(workdir='/workspace/skills', reuse_sandbox=True)

    await executor.run(_script_in(first, 'run.py'))
    await executor.run(_script_in(second, 'run.py'))

    assert '/workspace/skills/resources/config' in sandbox.deleted_dirs


async def test_reused_sandbox_restages_when_only_the_executable_bit_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """Chmod +x makes discovery treat a file as a script; a stale 0644 copy cannot run."""
    skill = tmp_path / 'demo-skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    tool = skill / 'tool'
    tool.write_text('#!/bin/sh\necho hi\n')

    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(reuse_sandbox=True)
    script = _script_in(skill, 'tool')

    await executor.run(script)
    tool.chmod(0o755)  # Contents untouched.
    await executor.run(script)

    modes = [entry.mode for entry in sandbox.written if entry.path.endswith('/tool')]
    assert modes[-1] == 0o755, 'the executable bit must trigger a restage'


async def test_reused_opensandbox_prunes_ancestor_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """Creating resources/config/sub also leaves resources/config, which must be pruned."""
    first = tmp_path / 'skill-a'
    (first / 'resources' / 'config' / 'sub').mkdir(parents=True)
    (first / 'SKILL.md').write_text('---\nname: skill-a\ndescription: A.\n---\n\nBody.\n')
    (first / 'resources' / 'config' / 'sub' / 'item').write_text('deep\n')
    (first / 'run.py').write_text('print("A")\n')

    second = tmp_path / 'skill-b'
    (second / 'resources').mkdir(parents=True)
    (second / 'SKILL.md').write_text('---\nname: skill-b\ndescription: B.\n---\n\nBody.\n')
    (second / 'resources' / 'config').write_text('now a file\n')
    (second / 'run.py').write_text('print("B")\n')

    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))
    executor = OpenSandboxScriptExecutor(workdir='/workspace/skills', reuse_sandbox=True)

    await executor.run(_script_in(first, 'run.py'))
    await executor.run(_script_in(second, 'run.py'))

    assert '/workspace/skills/resources/config' in sandbox.deleted_dirs
    assert '/workspace/skills/resources/config/sub' in sandbox.deleted_dirs


# ---------------------------------------------------------------------------
# A falsey custom executor must not be swapped for the host one
# ---------------------------------------------------------------------------


class FalseyExecutor(DuckTypedExecutor):
    """A pool-backed executor that is falsey while its pool is empty."""

    def __len__(self) -> int:
        return 0


def test_falsey_executor_is_not_replaced_by_the_local_one(skill_dir: Path) -> None:
    """`or` would silently run untrusted scripts on the host instead."""
    executor = FalseyExecutor()
    assert not executor, 'the fixture must actually be falsey'

    directory = SkillsDirectory(path=skill_dir, script_executor=executor)
    skill = next(iter(directory.get_skills().values()))  # keyed by path, not name
    script = next(s for s in skill.scripts if s.name.endswith('run.py'))

    assert isinstance(script, FileBasedSkillScript)
    assert script.executor is executor


def test_falsey_executor_survives_discover_skills(skill_dir: Path) -> None:
    """Same fallback bug lives in the functional entry point."""
    executor = FalseyExecutor()

    script = next(s for s in discover_skills(skill_dir)[0].scripts if s.name.endswith('run.py'))
    assert isinstance(script, FileBasedSkillScript)
    assert not isinstance(script.executor, FalseyExecutor), 'sanity: default is the local executor'

    script = next(
        s for s in discover_skills(skill_dir, script_executor=executor)[0].scripts if s.name.endswith('run.py')
    )
    assert isinstance(script, FileBasedSkillScript)
    assert script.executor is executor


# ---------------------------------------------------------------------------
# In-tree directory aliases
# ---------------------------------------------------------------------------


def test_staging_expands_in_tree_directory_symlinks(tmp_path: Path) -> None:
    """A script reading ../resources/current/x must find it in the sandbox too."""
    skill = tmp_path / 'demo-skill'
    (skill / 'data' / 'v2').mkdir(parents=True)
    (skill / 'resources').mkdir()
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'data' / 'v2' / 'config.json').write_text('{"v": 2}')
    (skill / 'resources' / 'current').symlink_to(skill / 'data' / 'v2')

    staged = dict(iter_stageable_files(skill.resolve()))

    assert 'data/v2/config.json' in staged, 'the real path must still be staged'
    assert 'resources/current/config.json' in staged, 'the alias path must be staged too'


def test_staging_rejects_directory_symlinks_into_excluded_dirs(cloned_skill: Path) -> None:
    """A directory alias must not become a second route into .git."""
    (cloned_skill / 'resources').mkdir()
    (cloned_skill / 'resources' / 'meta').symlink_to(cloned_skill / '.git')

    staged = _collect_staged(cloned_skill.resolve())

    assert not any(path.startswith('resources/meta') for path in staged)
    assert not any('ghp_SECRETTOKEN' in source.read_text(errors='ignore') for source in staged.values())


# ---------------------------------------------------------------------------
# LocalSandbox shell dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('shebang', 'expected'),
    [
        ('#!/bin/bash\n', ['bash']),
        ('#!/usr/bin/env bash\n', ['bash']),
        ('#!/bin/sh\n', ['sh']),
        ('#!/usr/bin/env -S zsh\n', ['zsh']),
    ],
)
def test_localsandbox_shebang_resolves_to_a_bare_shell_name(tmp_path: Path, shebang: str, expected: list[str]) -> None:
    """just-bash exposes shells as built-ins, so only the basename is usable.

    A literal `/bin/bash` fails inside the sandbox with "command not found".
    """
    script = tmp_path / 'go.sh'
    script.write_text(f'{shebang}echo hi\n')

    assert localsandbox_module._shebang_shell(script) == expected


@pytest.mark.parametrize('shebang', ['#!/bin/bash -e\n', '#!/usr/bin/env -S bash -u\n'])
def test_localsandbox_warns_that_shebang_options_are_dropped(tmp_path: Path, shebang: str) -> None:
    """just-bash rejects every shell flag, so options cannot be passed through.

    `bash -e script` fails there with status 127, so honouring them would break
    scripts that currently run. Dropping them is surfaced rather than silent.
    """
    script = tmp_path / 'go.sh'
    script.write_text(f'{shebang}echo hi\n')

    with pytest.warns(UserWarning, match='shebang options'):
        command = localsandbox_module._shebang_shell(script)

    assert command == ['bash']


def test_localsandbox_ignores_non_shell_shebangs(tmp_path: Path) -> None:
    """A python shebang on a .sh file must not become a bogus command."""
    script = tmp_path / 'go.sh'
    script.write_text('#!/usr/bin/env python3\necho hi\n')

    assert localsandbox_module._shebang_shell(script) is None


async def test_localsandbox_runs_shell_script_under_its_shebang(
    runnable_skill: Path, monkeypatch: pytest.MonkeyPatch, fake_localsandbox_module: None
) -> None:
    """A bash shebang selects bash rather than the suffix default."""
    (runnable_skill / 'scripts' / 'go.sh').write_text('#!/bin/bash\narr=(a b)\necho "${arr[1]}"\n')
    created: list[_FakeLocalSandboxRun] = []

    def factory(**kwargs: Any) -> _FakeLocalSandboxRun:
        sandbox = _FakeLocalSandboxRun(**kwargs)
        created.append(sandbox)
        return sandbox

    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: factory)

    await LocalSandboxScriptExecutor(workdir='/data/skill').run(_script_in(runnable_skill, 'scripts/go.sh'))

    assert created[0].command == 'cd /data/skill/scripts && bash /data/skill/scripts/go.sh'


# ---------------------------------------------------------------------------
# Staging must survive odd filesystems, and preserve the tree's shape
# ---------------------------------------------------------------------------


@pytest.mark.filterwarnings('ignore::UserWarning')
def test_staging_skips_cyclic_symlinks(tmp_path: Path) -> None:
    """A symlink loop must be skipped, not abort staging.

    Asserts the outcome rather than a warning: Python <=3.12 raises RuntimeError
    from resolve() and the guard warns, while 3.13+ returns the path unresolved
    and it is dropped by the is_file() check. Both must leave the rest staged.
    """
    skill = tmp_path / 'demo-skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'run.py').write_text('print("hi")\n')
    loop = skill / 'loop'
    loop.symlink_to(loop)

    staged = _collect_staged(skill.resolve())

    assert sorted(staged) == ['SKILL.md', 'run.py'], 'the loop is skipped, the rest still stages'


def test_staging_captures_empty_directories(tmp_path: Path) -> None:
    """A skill may ship an empty scratch/ for its script to write into."""
    skill = tmp_path / 'demo-skill'
    (skill / 'scratch').mkdir(parents=True)
    (skill / 'out' / 'nested').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')

    directories = sorted(iter_stageable_dirs(skill.resolve()))

    assert 'scratch' in directories
    assert 'out/nested' in directories


async def test_localsandbox_creates_empty_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_localsandbox_module: None
) -> None:
    """The files mapping cannot express an empty directory, so mkdir must run."""
    skill = tmp_path / 'demo-skill'
    (skill / 'scratch').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'go.sh').write_text('#!/bin/sh\necho hi\n')

    created: list[_FakeLocalSandboxRun] = []

    def factory(**kwargs: Any) -> _FakeLocalSandboxRun:
        sandbox = _FakeLocalSandboxRun(**kwargs)
        created.append(sandbox)
        return sandbox

    monkeypatch.setattr(localsandbox_module, '_require_localsandbox', lambda: factory)

    await LocalSandboxScriptExecutor(workdir='/data/skill').run(_script_in(skill, 'go.sh'))

    mkdirs = ' '.join(created[0].shell_commands)
    assert '/data/skill/scratch' in mkdirs


async def test_opensandbox_creates_empty_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_opensandbox_models: None
) -> None:
    """Ancestors of staged files are not enough when a directory holds no files."""
    skill = tmp_path / 'demo-skill'
    (skill / 'scratch').mkdir(parents=True)
    (skill / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Demo.\n---\n\nBody.\n')
    (skill / 'run.py').write_text('print("hi")\n')

    sandbox = _FakeOpenSandboxRun()
    monkeypatch.setattr(opensandbox_module, '_require_opensandbox', lambda: SimpleNamespace(create=_returning(sandbox)))

    await OpenSandboxScriptExecutor(workdir='/workspace/skills').run(_script_in(skill, 'run.py'))

    assert '/workspace/skills/scratch' in sandbox.directories


# ---------------------------------------------------------------------------
# Exit status must mean the same thing in both executors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(('requested', 'expected'), [(256, 0), (300, 44), (3, 3), (255, 255), (-1, 255)])
async def test_python_wrapper_truncates_exit_codes_like_a_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requested: int, expected: int
) -> None:
    """A local subprocess reports code & 0xFF, so sys.exit(256) must not become failure."""
    monkeypatch.setattr(localsandbox_module, '_EXIT_CODE_FILE', str(tmp_path / 'exit_code'))
    script = tmp_path / 'run.py'
    script.write_text(f'import sys\nsys.exit({requested})\n', encoding='utf-8')

    _, _, exit_code = await LocalSandboxScriptExecutor()._run_python(
        _StubPyodideSandbox(), str(script), str(tmp_path), None
    )

    assert exit_code == expected

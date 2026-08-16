"""Example running skill scripts inside a LocalSandbox virtual filesystem.

This example shows how to create an agent whose skill scripts execute in a
[LocalSandbox](https://github.com/coplane/localsandbox) virtual filesystem
(just-bash + Pyodide, no container runtime) rather than a local subprocess.
Only the `script_executor=` argument differs from `basic_usage_capability.py`.

Requires `pip install -e ".[examples,localsandbox]"`.

The executor stages the whole skill folder — `SKILL.md`, `resources/`,
`scripts/` — and runs the script with its own directory as the working
directory, so relative paths resolve exactly as they do locally. Symlinks
resolving outside the skill folder are skipped, so staging cannot pull host
files into the sandbox. Output is formatted like local execution, so switching
backends does not change what the model sees.

Note:
    Pyodide has no sockets and only a subset of the ecosystem, so the bundled
    `arxiv-search` script cannot run here — it needs the `arxiv` package and
    network access. The resource-only skills (`pydanticai-docs`, `web-research`)
    work normally, since resources are read on the host.
"""

from __future__ import annotations

import shlex
import warnings
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import logfire
import uvicorn
from dotenv import load_dotenv
from pydantic_ai import Agent

from pydantic_ai_skills import (
    LocalSkillScriptExecutor,
    SkillsCapability,
    SkillScript,
    SkillScriptExecutor,
    SkillsDirectory,
)

if TYPE_CHECKING:
    from localsandbox import LocalSandbox


def skill_root_for(script: SkillScript) -> Path:
    """Resolve the skill folder root that a script belongs to.

    ``script.name`` is relative to the skill folder (for example
    ``scripts/run.py``), so walking that many levels up from the script file
    yields the skill root rather than just the script's parent directory.

    Args:
        script: A file-based script with a ``uri``.

    Returns:
        Resolved path to the skill folder.
    """
    script_path = Path(str(script.uri)).resolve()
    root = script_path.parent
    for _ in range(len(PurePosixPath(script.name).parts) - 1):
        root = root.parent
    return root


def iter_stageable_files(skill_root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(relative_posix_path, resolved_file)`` for files safe to stage.

    Symlinks that resolve outside ``skill_root`` are skipped with a warning.
    Discovery already rejects those, but staging re-walks the folder, and
    following such a link would copy an arbitrary host file into the sandbox
    where the script could read it back out.

    Args:
        skill_root: Resolved path to the skill folder.

    Yields:
        Tuples of the path relative to ``skill_root`` and the resolved file.
    """
    for path in sorted(skill_root.rglob('*')):
        resolved = path.resolve()
        if not resolved.is_relative_to(skill_root):
            warnings.warn(
                f"Skipping '{path}': resolves outside the skill folder (symlink escape detected).",
                UserWarning,
                stacklevel=2,
            )
            continue
        if resolved.is_file():
            yield path.relative_to(skill_root).as_posix(), resolved


def _stage_snapshot(skill_root: Path) -> tuple[list[tuple[str, Path]], tuple[tuple[str, int, int], ...]]:
    """Walk the skill folder once, returning its files and a change fingerprint.

    The fingerprint covers every staged path with its size and modification
    time, so a reused sandbox can tell whether the source skill was edited since
    it was staged — ``auto_reload`` and ``reload()`` both surface edits under an
    unchanged skill root.

    Args:
        skill_root: Resolved path to the skill folder.

    Returns:
        The staged ``(relative, resolved)`` pairs and their fingerprint.
    """
    entries: list[tuple[str, Path]] = []
    fingerprint: list[tuple[str, int, int]] = []
    for relative, resolved in iter_stageable_files(skill_root):
        entries.append((relative, resolved))
        stat = resolved.stat()
        fingerprint.append((relative, stat.st_size, stat.st_mtime_ns))
    return entries, tuple(fingerprint)


_SHELL_INTERPRETERS: dict[str, list[str]] = {
    '.sh': ['sh'],
    '.bash': ['bash'],
    '.zsh': ['zsh'],
}

# Written by the Pyodide wrapper so sys.exit(N) survives as a real exit code.
_EXIT_CODE_FILE = '/data/.skill_exit_code'

_PYTHON_WRAPPER = """import runpy, sys
sys.argv = {argv}
__skill_exit_code = 0
try:
    runpy.run_path({script_path!r}, run_name='__main__')
except SystemExit as exc:
    if isinstance(exc.code, int):
        # int() also normalizes bool, so sys.exit(not ok) reports 1 rather than 'True'.
        __skill_exit_code = int(exc.code)
    elif exc.code is not None:
        __skill_exit_code = 1
        print(exc.code, file=sys.stderr)
with open({exit_file!r}, 'w') as __skill_f:
    __skill_f.write(str(__skill_exit_code))
"""


def _require_localsandbox() -> Any:
    """Import the localsandbox SDK, or explain which extra installs it."""
    try:
        from localsandbox import LocalSandbox as _LocalSandbox
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            'LocalSandboxScriptExecutor requires the "localsandbox" package. '
            'Install it with: pip install "pydantic-ai-skills[localsandbox]"'
        ) from exc

    return _LocalSandbox


class LocalSandboxScriptExecutor(SkillScriptExecutor):
    """Execute file-based skill scripts inside a LocalSandbox virtual filesystem.

    LocalSandbox has no CPython binary on ``PATH``, so there are two paths:
    shell scripts run through ``abash``, and ``.py`` scripts run through
    ``aexecute_python`` (Pyodide) with an injected ``sys.argv`` and
    ``runpy.run_path(..., run_name='__main__')``, so ``argparse`` and
    ``if __name__ == '__main__'`` behave normally.

    Pyodide ships a subset of the ecosystem and has no sockets or subprocesses,
    so scripts needing third-party wheels or network access will fail here.

    Attributes:
        workdir: Directory inside the sandbox that the skill folder is staged into.
    """

    def __init__(
        self,
        *,
        workdir: str = '/data/skill',
        preset: Any | None = None,
        preload_packages: list[str] | None = None,
        reuse_sandbox: bool = False,
    ) -> None:
        """Initialize the LocalSandbox executor.

        Args:
            workdir: Directory inside the sandbox that the skill folder is staged into.
            preset: Optional ``localsandbox.ExecutionPreset`` controlling resource
                limits. When None, the SDK default (``NORMAL``) is used.
            preload_packages: Pyodide packages to preload before running Python scripts.
            reuse_sandbox: Keep a single sandbox alive across runs instead of
                creating one per run. Faster, but runs share state.
        """
        self.workdir = workdir.rstrip('/') or '/data/skill'
        self._preset = preset
        self._preload_packages = preload_packages
        self._reuse_sandbox = reuse_sandbox
        self._sandbox: LocalSandbox | None = None
        self._staged_root: Path | None = None
        self._staged_fingerprint: tuple[tuple[str, int, int], ...] | None = None
        # Reused for its host-independent argument marshalling and output formatting.
        self._formatter = LocalSkillScriptExecutor()

    def _get_sandbox(self, skill_root: Path) -> LocalSandbox:
        """Return the sandbox to run in, creating and staging one when needed.

        Staging happens at construction, so a reused sandbox is rebuilt whenever
        the skill changes — either a different skill (one executor instance
        serves every skill in a ``SkillsDirectory``) or edited files under the
        same root, which ``auto_reload`` and ``reload()`` both surface.
        """
        entries, fingerprint = _stage_snapshot(skill_root)

        if self._reuse_sandbox and self._sandbox is not None:
            if self._staged_root == skill_root and self._staged_fingerprint == fingerprint:
                return self._sandbox
            self.close()

        sandbox_cls = _require_localsandbox()
        files: dict[str, str | bytes] = {
            f'{self.workdir}/{relative}': resolved.read_bytes() for relative, resolved in entries
        }
        kwargs: dict[str, Any] = {'files': files, 'cwd': self.workdir}
        if self._preset is not None:
            kwargs['preset'] = self._preset

        sandbox: LocalSandbox = sandbox_cls(**kwargs)
        if self._reuse_sandbox:
            self._sandbox = sandbox
            self._staged_root = skill_root
            self._staged_fingerprint = fingerprint
        return sandbox

    async def _run_python(
        self, sandbox: LocalSandbox, remote_path: str, cwd: str, args: dict[str, Any] | None
    ) -> tuple[str, str, int]:
        """Run a Python script through Pyodide with an injected argv."""
        argv: list[str] = [PurePosixPath(remote_path).name]
        if args:
            self._formatter._build_args(argv, args)

        code = _PYTHON_WRAPPER.format(
            # repr, not json.dumps: JSON escapes non-BMP characters as UTF-16
            # surrogate pairs, which become two lone surrogates in Python source.
            argv=repr(argv),
            script_path=remote_path,
            exit_file=_EXIT_CODE_FILE,
        )
        result = await sandbox.aexecute_python(
            code,
            cwd=cwd,
            preload_packages=self._preload_packages,
        )

        stderr = result.stderr or ''
        if result.error:
            # The wrapper never reached the exit-code file. Pyodide usually mirrors the
            # traceback into stderr already, so append rather than replace or duplicate.
            if result.error not in stderr:
                stderr = f'{stderr}\n{result.error}' if stderr else result.error
            return result.stdout or '', stderr, result.exit_code or 1

        try:
            exit_code = int(sandbox.read_file(_EXIT_CODE_FILE))
        except (OSError, ValueError):  # pragma: no cover - wrapper always writes it
            exit_code = result.exit_code or 0

        return result.stdout or '', stderr, exit_code

    async def _run_shell(
        self, sandbox: LocalSandbox, remote_path: str, suffix: str, args: dict[str, Any] | None
    ) -> tuple[str, str, int]:
        """Run a shell script through just-bash."""
        from localsandbox import CommandError

        cmd = [*_SHELL_INTERPRETERS[suffix], remote_path]
        if args:
            self._formatter._build_args(cmd, args)

        try:
            result = await sandbox.abash(shlex.join(cmd))
        except CommandError as exc:
            # abash raises on non-zero exit; surface it like local execution does.
            return exc.stdout, exc.stderr, exc.exit_code

        return result.stdout, result.stderr, result.exit_code

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> Any:
        """Run a skill script inside a LocalSandbox virtual filesystem.

        Args:
            script: The script to run; ``script.uri`` must point at a local file.
            args: Named arguments, marshalled with the same rules as
                [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor].
            ctx: Unused; accepted for protocol compatibility.

        Returns:
            Combined stdout and stderr, formatted like local execution.

        Raises:
            ValueError: If the script has no URI, or its type is unsupported here.
        """
        if script.uri is None:
            raise ValueError(f"Script '{script.name}' has no URI for sandbox execution")

        script_path = Path(script.uri).resolve()
        skill_root = skill_root_for(script)
        suffix = script_path.suffix.lower()
        remote_path = f'{self.workdir}/{script_path.relative_to(skill_root).as_posix()}'
        # cwd is the script's own directory, matching LocalSkillScriptExecutor.
        cwd = str(PurePosixPath(remote_path).parent)

        # Validated before provisioning, so an unsupported script never starts a sandbox.
        if suffix != '.py' and suffix not in _SHELL_INTERPRETERS:
            raise ValueError(
                f"Script '{script.name}' has unsupported type '{suffix}' for LocalSandbox. "
                f'Supported: .py (Pyodide), {", ".join(sorted(_SHELL_INTERPRETERS))} (just-bash).'
            )

        sandbox = self._get_sandbox(skill_root)
        try:
            if suffix == '.py':
                stdout, stderr, exit_code = await self._run_python(sandbox, remote_path, cwd, args)
            else:
                stdout, stderr, exit_code = await self._run_shell(sandbox, remote_path, suffix, args)
        finally:
            if not self._reuse_sandbox:
                sandbox.__exit__(None, None, None)

        return self._formatter._format_output([stdout.encode()], [stderr.encode()], exit_code)

    def close(self) -> None:
        """Close the reused sandbox, if one is alive."""
        if self._sandbox is not None:
            self._sandbox.__exit__(None, None, None)
            self._sandbox = None
            self._staged_root = None
            self._staged_fingerprint = None


load_dotenv()

logfire.configure()
logfire.instrument_pydantic_ai()

# Get the skills directory (examples/skills)
skills_dir = Path(__file__).parent / 'skills'

# Initialize Skills Capability with skill scripts sandboxed via LocalSandbox
skills_capability = SkillsCapability(
    directories=[SkillsDirectory(path=skills_dir, script_executor=LocalSandboxScriptExecutor())],
)

# Create agent with skills capability
agent = Agent(
    model='gateway/openai:gpt-5.2',
    instructions='You are a helpful research assistant.',
    capabilities=[skills_capability],
)

app = agent.to_web()

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=7932)

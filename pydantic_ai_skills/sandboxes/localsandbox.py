"""Run skill scripts inside a LocalSandbox virtual filesystem.

[LocalSandbox](https://github.com/coplane/localsandbox) combines just-bash and
Pyodide over a SQLite-backed virtual filesystem. Nothing touches the host
filesystem and no container runtime is required, which makes it a good fit for
local development and CI.

Requires the ``localsandbox`` extra:

```bash
pip install "pydantic-ai-skills[localsandbox]"
```
"""

from __future__ import annotations

import shlex
import warnings
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import anyio

from pydantic_ai_skills.local import LocalSkillScriptExecutor
from pydantic_ai_skills.sandboxes._staging import _stage_snapshot, skill_root_for
from pydantic_ai_skills.types import SkillScript

if TYPE_CHECKING:
    from localsandbox import LocalSandbox

__all__ = ['LocalSandboxScriptExecutor']

_SHELL_INTERPRETERS: dict[str, list[str]] = {
    '.sh': ['sh'],
    '.bash': ['bash'],
    '.zsh': ['zsh'],
}

#: Shell names just-bash accepts as commands. Only the basename of a shebang is
#: usable: just-bash provides `sh` and `bash` as built-ins, not as files, so a
#: literal `#!/bin/bash` would fail with "command not found".
_SHELL_NAMES = frozenset({'sh', 'bash', 'zsh'})


def _shebang_shell(script_path: Path) -> list[str] | None:
    """Return the shell command a script's shebang asks for, or None.

    The interpreter is reduced to its basename, and only accepted when it names
    a shell just-bash knows: paths such as ``/bin/bash`` do not exist inside the
    sandbox, where shells are built-ins.

    Shell options cannot be honoured here. just-bash rejects every flag —
    ``bash -e script`` fails with "-e: No such file or directory" and status 127 —
    so passing them through would break scripts that currently run. They are
    dropped with a warning instead, since ``-e`` does change behaviour.
    OpenSandbox runs a real shell and keeps them.

    Args:
        script_path: Local path to the script file.

    Returns:
        A single-element command such as ``['bash']``, or None without a usable
        shebang.
    """
    try:
        with script_path.open('rb') as handle:
            first_line = handle.readline()
    except OSError:  # pragma: no cover - unreadable files are skipped earlier
        return None

    if not first_line.startswith(b'#!'):
        return None

    parts = shlex.split(first_line[2:].decode('utf-8', errors='ignore').strip())
    if parts and PurePosixPath(parts[0]).name == 'env':
        # Drop env's own switches (-S, -i, ...) but keep the interpreter's.
        parts = parts[1:]
        while parts and parts[0].startswith('-'):
            parts = parts[1:]
    if not parts:
        return None

    name = PurePosixPath(parts[0]).name
    if name not in _SHELL_NAMES:
        return None

    if parts[1:]:
        warnings.warn(
            f"Ignoring shebang options {' '.join(parts[1:])!r} for '{script_path.name}': "
            'just-bash accepts no shell flags, so they cannot be passed through. '
            'Behaviour may differ from local execution.',
            UserWarning,
            stacklevel=2,
        )
    return [name]


_EXIT_CODE_FILE = '/data/.skill_exit_code'

_PYTHON_WRAPPER = """import runpy, sys
sys.argv = {argv}
__skill_exit_code = 0
try:
    runpy.run_path({script_path!r}, run_name='__main__')
except SystemExit as exc:
    if isinstance(exc.code, int):
        # int() also normalizes bool, so sys.exit(not ok) reports 1 rather than 'True'.
        # & 0xFF matches the POSIX status a local subprocess would report:
        # sys.exit(256) is 0 and sys.exit(300) is 44.
        __skill_exit_code = int(exc.code) & 0xFF
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
            'Install it with: pip install "pydantic-ai-skills[localsandbox]". '
            'Note that localsandbox requires Python 3.12 or newer, so the extra '
            'installs nothing on 3.10 and 3.11.'
        ) from exc

    return _LocalSandbox


class LocalSandboxScriptExecutor:
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
        self._staged_fingerprint: str | None = None
        # Serializes runs that share one sandbox; see run().
        self._reuse_lock = anyio.Lock()
        # Reused for its host-independent argument marshalling and output formatting.
        self._formatter = LocalSkillScriptExecutor()

    def _get_sandbox(self, skill_root: Path) -> LocalSandbox:
        """Return the sandbox to run in, creating and staging one when needed.

        Staging happens at construction, so a reused sandbox is rebuilt whenever
        the skill changes — either a different skill (one executor instance
        serves every skill in a ``SkillsDirectory``) or edited files under the
        same root, which ``auto_reload`` and ``reload()`` both surface.
        """
        entries, directories, fingerprint = _stage_snapshot(skill_root)

        if self._reuse_sandbox and self._sandbox is not None:
            if self._staged_root == skill_root and self._staged_fingerprint == fingerprint:
                return self._sandbox
            self.close()

        sandbox_cls = _require_localsandbox()
        files: dict[str, str | bytes] = {f'{self.workdir}/{entry.relative}': entry.data for entry in entries}
        kwargs: dict[str, Any] = {'files': files, 'cwd': self.workdir}
        if self._preset is not None:
            kwargs['preset'] = self._preset

        sandbox: LocalSandbox = sandbox_cls(**kwargs)
        if directories:
            # The files mapping cannot express an empty directory, and a skill may
            # ship one for its script to write into.
            paths = ' '.join(shlex.quote(f'{self.workdir}/{name}') for name in directories)
            sandbox.bash(f'mkdir -p {paths}')

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
        self,
        sandbox: LocalSandbox,
        script_path: Path,
        remote_path: str,
        cwd: str,
        suffix: str,
        args: dict[str, Any] | None,
    ) -> tuple[str, str, int]:
        """Run a shell script through just-bash from the script's own directory."""
        from localsandbox import CommandError

        # A shebang wins over the suffix, matching LocalSkillScriptExecutor.
        shell = _shebang_shell(script_path) or _SHELL_INTERPRETERS[suffix]
        cmd = [*shell, remote_path]
        if args:
            self._formatter._build_args(cmd, args)

        # abash takes no cwd, so change directory as part of the command; without
        # this a script reading ../resources/data.json would resolve it differently
        # than under LocalSkillScriptExecutor.
        command = f'cd {shlex.quote(cwd)} && {shlex.join(cmd)}'

        try:
            result = await sandbox.abash(command)
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
        del ctx  # Required by the SkillScriptExecutor protocol; unused by this backend.

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

        if not self._reuse_sandbox:
            return await self._execute(skill_root, script_path, remote_path, cwd, suffix, args)

        # One sandbox serving concurrent runs has to serialize them: a second run
        # switching skills would otherwise close the sandbox the first is still
        # using, and both would share a filesystem mid-execution anyway.
        async with self._reuse_lock:
            return await self._execute(skill_root, script_path, remote_path, cwd, suffix, args)

    async def _execute(
        self,
        skill_root: Path,
        script_path: Path,
        remote_path: str,
        cwd: str,
        suffix: str,
        args: dict[str, Any] | None,
    ) -> Any:
        """Provision a sandbox, run the script in it, and format the output."""
        sandbox = self._get_sandbox(skill_root)
        try:
            if suffix == '.py':
                stdout, stderr, exit_code = await self._run_python(sandbox, remote_path, cwd, args)
            else:
                stdout, stderr, exit_code = await self._run_shell(sandbox, script_path, remote_path, cwd, suffix, args)
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

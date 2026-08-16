"""Run skill scripts inside a LocalSandbox virtual filesystem.

Implements the [`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor]
protocol on top of [LocalSandbox](https://github.com/coplane/localsandbox), which
combines just-bash and Pyodide over a SQLite-backed virtual filesystem. Nothing
runs against the host filesystem, and no container runtime is required.

Requirements:
    pip install "pydantic-ai-skills[localsandbox]"

Two execution paths, because LocalSandbox has no CPython binary on ``PATH``:

- **Shell scripts** (``.sh``, ``.bash``) run through ``abash`` with the usual
  ``--flag value`` argv.
- **Python scripts** (``.py``) run through ``aexecute_python`` (Pyodide). Since
  Pyodide has no ``sys.argv``, this executor injects one and executes the staged
  file with ``runpy.run_path(..., run_name='__main__')``, so ``argparse`` and
  ``if __name__ == '__main__'`` behave normally. ``sys.exit(N)`` is captured and
  reported as the exit code.

Limitations worth knowing before pointing this at real skills:

- Pyodide ships a subset of the ecosystem. Scripts importing third-party packages
  not available as Pyodide wheels will fail; use ``preload_packages`` where it helps.
- Subprocesses, sockets, and host filesystem access are unavailable by design.
- ``abash`` accepts no per-command timeout or environment; use ``preset`` to pick
  an execution limit profile (``STRICT``, ``NORMAL``, ``PERMISSIVE``).

Lifecycle: a fresh sandbox is created per run and closed afterwards. Pass
``reuse_sandbox=True`` to keep one warm across runs — faster, but runs share state.

Staging: the whole skill directory (the script's parent folder) is copied into the
sandbox, so sibling modules and bundled data files resolve as they do locally.

Example:
    ```python
    from pydantic_ai_skills import SkillsDirectory

    from examples.sandbox_localsandbox import LocalSandboxScriptExecutor

    executor = LocalSandboxScriptExecutor()
    directory = SkillsDirectory(path='./skills', script_executor=executor)
    ```
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic_ai_skills import LocalSkillScriptExecutor, SkillScript, SkillScriptExecutor

if TYPE_CHECKING:
    from localsandbox import LocalSandbox

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
        __skill_exit_code = exc.code
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
        # Reused for its host-independent argument marshalling and output formatting.
        self._formatter = LocalSkillScriptExecutor()

    def _stage_files(self, skill_folder: Path) -> dict[str, str | bytes]:
        """Map every file in the skill folder to its path inside the sandbox."""
        files: dict[str, str | bytes] = {}
        for path in sorted(skill_folder.rglob('*')):
            if path.is_file():
                relative = path.relative_to(skill_folder).as_posix()
                files[f'{self.workdir}/{relative}'] = path.read_bytes()
        return files

    def _get_sandbox(self, skill_folder: Path) -> LocalSandbox:
        """Return the sandbox to run in, creating and staging one when needed."""
        if self._reuse_sandbox and self._sandbox is not None:
            return self._sandbox

        sandbox_cls = _require_localsandbox()
        kwargs: dict[str, Any] = {'files': self._stage_files(skill_folder), 'cwd': self.workdir}
        if self._preset is not None:
            kwargs['preset'] = self._preset

        sandbox: LocalSandbox = sandbox_cls(**kwargs)
        if self._reuse_sandbox:
            self._sandbox = sandbox
        return sandbox

    async def _run_python(
        self, sandbox: LocalSandbox, remote_path: str, args: dict[str, Any] | None
    ) -> tuple[str, str, int]:
        """Run a Python script through Pyodide with an injected argv."""
        argv: list[str] = [Path(remote_path).name]
        if args:
            self._formatter._build_args(argv, args)

        code = _PYTHON_WRAPPER.format(
            argv=json.dumps(argv),
            script_path=remote_path,
            exit_file=_EXIT_CODE_FILE,
        )
        result = await sandbox.aexecute_python(
            code,
            cwd=self.workdir,
            preload_packages=self._preload_packages,
        )

        stderr = result.stderr or ''
        if result.error:
            # The wrapper never reached the exit-code file: report the Pyodide traceback.
            return result.stdout or '', stderr or result.error, result.exit_code or 1

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

        script_path = Path(script.uri)
        skill_folder = script_path.parent
        suffix = script_path.suffix.lower()
        remote_path = f'{self.workdir}/{script_path.relative_to(skill_folder).as_posix()}'

        # Validated before provisioning, so an unsupported script never starts a sandbox.
        if suffix != '.py' and suffix not in _SHELL_INTERPRETERS:
            raise ValueError(
                f"Script '{script.name}' has unsupported type '{suffix}' for LocalSandbox. "
                f'Supported: .py (Pyodide), {", ".join(sorted(_SHELL_INTERPRETERS))} (just-bash).'
            )

        sandbox = self._get_sandbox(skill_folder)
        try:
            if suffix == '.py':
                stdout, stderr, exit_code = await self._run_python(sandbox, remote_path, args)
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

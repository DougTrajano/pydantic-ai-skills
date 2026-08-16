"""Run skill scripts inside an OpenSandbox container.

[OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) runs each script
in a container, giving the strongest isolation of the bundled executors plus a
full CPython environment with real third-party packages.

Requires the ``opensandbox`` extra and a reachable OpenSandbox server:

```bash
pip install "pydantic-ai-skills[opensandbox]"

osb config set connection.domain localhost:8080
osb config set connection.protocol http
osb config set connection.api_key <your-api-key>
```
"""

from __future__ import annotations

import shlex
import time
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import anyio

from pydantic_ai_skills.local import LocalSkillScriptExecutor
from pydantic_ai_skills.sandboxes._staging import _stage_snapshot, skill_root_for
from pydantic_ai_skills.types import SkillScript

if TYPE_CHECKING:
    from opensandbox import Sandbox

__all__ = ['OpenSandboxScriptExecutor']

_DEFAULT_WORKDIR = '/workspace/skills'

# Suffix -> interpreter, resolved inside the sandbox rather than on the host.
_SANDBOX_INTERPRETERS: dict[str, list[str]] = {
    '.py': ['python3'],
    '.sh': ['sh'],
    '.bash': ['bash'],
    '.zsh': ['zsh'],
    '.fish': ['fish'],
}


def _shebang_command(script_path: Path) -> list[str] | None:
    """Return the interpreter command a script's shebang asks for, or None.

    The tokens are returned verbatim, exactly as the kernel would use them
    inside the sandbox. Unlike
    :meth:`~pydantic_ai_skills.LocalSkillScriptExecutor._extract_shebang_command`
    nothing is resolved against the host filesystem: ``/bin/bash`` must exist in
    the container, not here.

    Args:
        script_path: Local path to the staged script file.

    Returns:
        The shebang's tokens, or None when there is no usable shebang.
    """
    try:
        with script_path.open('rb') as handle:
            first_line = handle.readline()
    except OSError:  # pragma: no cover - unreadable files are skipped earlier
        return None

    if not first_line.startswith(b'#!'):
        return None

    parts = shlex.split(first_line[2:].decode('utf-8', errors='ignore').strip())
    return parts or None


def _require_opensandbox() -> Any:
    """Import the opensandbox SDK, or explain which extra installs it."""
    try:
        from opensandbox import Sandbox as _Sandbox
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            'OpenSandboxScriptExecutor requires the "opensandbox" package. '
            'Install it with: pip install "pydantic-ai-skills[opensandbox]"'
        ) from exc

    return _Sandbox


class OpenSandboxScriptExecutor:
    """Execute file-based skill scripts inside an OpenSandbox container.

    Attributes:
        timeout: Per-script execution timeout in seconds.
    """

    def __init__(
        self,
        image: str = 'opensandbox/code-interpreter:v1.1.0',
        *,
        timeout: int = 30,
        workdir: str = '/workspace/skills',
        env_vars: dict[str, str] | None = None,
        reuse_sandbox: bool = False,
        sandbox_timeout: timedelta = timedelta(minutes=10),
    ) -> None:
        """Initialize the OpenSandbox executor.

        Args:
            image: Container image used for each sandbox.
            timeout: Per-script execution timeout in seconds.
            workdir: Directory inside the sandbox that the skill folder is staged into.
                Deliberately not under ``/tmp``: that is world-writable, so another
                process in the sandbox could tamper with a staged script between
                upload and execution. The directory is created if missing.
            env_vars: Environment variables exported to the script process.
            reuse_sandbox: Keep a single sandbox alive across runs instead of
                creating and killing one per run. Faster, but runs share state.
            sandbox_timeout: Lifetime of the sandbox itself, passed to ``Sandbox.create``.
        """
        self.timeout = timeout
        self._image = image
        self._workdir = workdir.rstrip('/') or _DEFAULT_WORKDIR
        self._env_vars = dict(env_vars or {})
        self._reuse_sandbox = reuse_sandbox
        self._sandbox_timeout = sandbox_timeout
        self._sandbox: Sandbox | None = None
        self._sandbox_deadline: float = 0.0
        self._staged_paths: set[str] = set()
        self._staged_dirs: set[str] = set()
        self._staged_root: Path | None = None
        self._staged_fingerprint: str | None = None
        # Serializes runs that share one sandbox; see run().
        self._reuse_lock = anyio.Lock()
        # Reused for its host-independent argument marshalling and output formatting.
        self._formatter = LocalSkillScriptExecutor()

    async def _get_sandbox(self) -> Sandbox:
        """Return the sandbox to run in, creating one when needed.

        A reused sandbox is replaced once its server-side lifetime is close to
        expiring. ``Sandbox.create`` fixes that lifetime, so holding the handle
        past it would send every later run to an expired sandbox. The deadline
        leaves one script timeout of headroom so a run started now can finish.
        """
        if self._reuse_sandbox and self._sandbox is not None:
            if time.monotonic() < self._sandbox_deadline:
                return self._sandbox
            # aclose() also clears the staging record: the replacement starts empty.
            await self.aclose()

        sandbox_cls = _require_opensandbox()
        sandbox: Sandbox = await sandbox_cls.create(
            self._image,
            env=self._env_vars or None,
            timeout=self._sandbox_timeout,
        )
        if self._reuse_sandbox:
            self._sandbox = sandbox
            self._sandbox_deadline = time.monotonic() + self._sandbox_timeout.total_seconds() - self.timeout
        return sandbox

    async def _stage_skill_folder(self, sandbox: Sandbox, skill_root: Path) -> None:
        """Upload the skill folder into the sandbox workdir.

        A reused sandbox keeps whatever earlier runs wrote, so restaging has to
        remove files that no longer exist in the source skill. Without that, a
        resource deleted or renamed between runs stays readable and the script
        goes on using stale data. When nothing changed, staging is skipped.
        """
        from opensandbox.models import WriteEntry

        entries, source_dirs, fingerprint = _stage_snapshot(skill_root)
        # Keyed on the root as well: two skills can share relative paths and
        # contents, and fingerprint alone would then run skill B against skill A's
        # staged files.
        if self._reuse_sandbox and (skill_root, fingerprint) == (self._staged_root, self._staged_fingerprint):
            return

        paths = {f'{self._workdir}/{entry.relative}' for entry in entries}
        # Every ancestor, not just the immediate parent: creating resources/a/b also
        # leaves resources/a behind, and an untracked ancestor would survive pruning
        # and block a later skill that needs a file at that path.
        # Every source directory, so a skill's empty scratch/ exists too.
        directories = {self._workdir} | {f'{self._workdir}/{name}' for name in source_dirs}
        for entry in entries:
            parent = PurePosixPath(entry.relative).parent
            while parent != PurePosixPath('.'):
                directories.add(f'{self._workdir}/{parent}')
                parent = parent.parent

        stale_files = sorted(self._staged_paths - paths)
        if stale_files:
            await sandbox.files.delete_files(stale_files)

        # Directories too: a path that was a directory in the previous skill and is
        # a file in this one would otherwise block the write. Deepest first so
        # children go before their parents.
        stale_dirs = sorted(self._staged_dirs - directories, key=lambda path: path.count('/'), reverse=True)
        if stale_dirs:
            await sandbox.files.delete_directories(stale_dirs)

        await sandbox.files.create_directories([WriteEntry(path=path) for path in sorted(directories)])

        if entries:
            await sandbox.files.write_files(
                [
                    WriteEntry(
                        path=f'{self._workdir}/{entry.relative}',
                        data=entry.data,
                        mode=0o755 if entry.executable else 0o644,
                    )
                    for entry in entries
                ]
            )

        if self._reuse_sandbox:
            self._staged_paths = paths
            self._staged_dirs = directories
            self._staged_root = skill_root
            self._staged_fingerprint = fingerprint

    def _build_command(self, script_path: Path, remote_path: str, suffix: str, args: dict[str, Any] | None) -> str:
        """Build the shell command line executed inside the sandbox.

        A shebang wins over the suffix fallback, matching
        [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor];
        otherwise a ``#!/bin/bash`` script using bash-only syntax would run under
        ``sh`` here but bash locally.
        """
        interpreter = _shebang_command(script_path) or _SANDBOX_INTERPRETERS.get(suffix)
        cmd = [*interpreter, remote_path] if interpreter else [remote_path]

        if args:
            # Reuse the built-in bool/list/None marshalling rules.
            self._formatter._build_args(cmd, args)

        return shlex.join(cmd)

    async def run(
        self,
        script: SkillScript,
        args: dict[str, Any] | None = None,
        ctx: Any | None = None,
    ) -> Any:
        """Run a skill script inside an OpenSandbox container.

        Args:
            script: The script to run; ``script.uri`` must point at a local file.
            args: Named arguments, marshalled with the same rules as
                [`LocalSkillScriptExecutor`][pydantic_ai_skills.LocalSkillScriptExecutor].
            ctx: Unused; accepted for protocol compatibility.

        Returns:
            Combined stdout and stderr, formatted like local execution.

        Raises:
            ValueError: If the script has no URI configured.
        """
        del ctx  # Required by the SkillScriptExecutor protocol; unused by this backend.

        if script.uri is None:
            raise ValueError(f"Script '{script.name}' has no URI for sandbox execution")

        script_path = Path(script.uri).resolve()
        skill_root = skill_root_for(script)
        remote_path = f'{self._workdir}/{script_path.relative_to(skill_root).as_posix()}'
        # cwd is the script's own directory, matching LocalSkillScriptExecutor.
        working_directory = str(PurePosixPath(remote_path).parent)
        command = self._build_command(script_path, remote_path, script_path.suffix.lower(), args)

        if not self._reuse_sandbox:
            return await self._execute(skill_root, command, working_directory)

        # One sandbox serving concurrent runs has to serialize them: two first
        # runs would otherwise each create a container and leak one, and both
        # would stage over each other's files in the shared workdir.
        async with self._reuse_lock:
            return await self._execute(skill_root, command, working_directory)

    async def _execute(self, skill_root: Path, command: str, working_directory: str) -> Any:
        """Provision a sandbox, stage the skill, run the command, and format the output."""
        # _get_sandbox raises the ImportError naming the extra, so import the SDK
        # models only once a sandbox exists.
        sandbox = await self._get_sandbox()
        from opensandbox.models.execd import RunCommandOpts

        try:
            await self._stage_skill_folder(sandbox, skill_root)
            execution = await sandbox.commands.run(
                command,
                opts=RunCommandOpts(
                    working_directory=working_directory,
                    timeout=timedelta(seconds=self.timeout),
                    envs=self._env_vars or None,
                ),
            )
        finally:
            if not self._reuse_sandbox:
                # Shielded: a cancelled scope would cancel this await too, leaking
                # the container until its server-side lifetime expires.
                with anyio.CancelScope(shield=True):
                    await sandbox.kill()

        stdout = ''.join(message.text for message in execution.logs.stdout)
        stderr = ''.join(message.text for message in execution.logs.stderr)
        return self._formatter._format_output([stdout.encode()], [stderr.encode()], execution.exit_code or 0)

    async def aclose(self) -> None:
        """Kill the reused sandbox, if one is alive."""
        if self._sandbox is not None:
            await self._sandbox.kill()
            self._sandbox = None
            self._sandbox_deadline = 0.0
            self._staged_paths = set()
            self._staged_dirs = set()
            self._staged_root = None
            self._staged_fingerprint = None

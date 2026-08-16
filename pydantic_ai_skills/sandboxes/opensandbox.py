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

from pydantic_ai_skills.local import LocalSkillScriptExecutor
from pydantic_ai_skills.sandboxes._staging import _stage_snapshot, skill_root_for
from pydantic_ai_skills.types import SkillScript

if TYPE_CHECKING:
    from opensandbox import Sandbox

__all__ = ['OpenSandboxScriptExecutor']

# Suffix -> interpreter, resolved inside the sandbox rather than on the host.
_SANDBOX_INTERPRETERS: dict[str, list[str]] = {
    '.py': ['python3'],
    '.sh': ['sh'],
    '.bash': ['bash'],
    '.zsh': ['zsh'],
    '.fish': ['fish'],
}


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
        workdir: str = '/tmp/skills',
        env_vars: dict[str, str] | None = None,
        reuse_sandbox: bool = False,
        sandbox_timeout: timedelta = timedelta(minutes=10),
    ) -> None:
        """Initialize the OpenSandbox executor.

        Args:
            image: Container image used for each sandbox.
            timeout: Per-script execution timeout in seconds.
            workdir: Directory inside the sandbox that the skill folder is staged into.
            env_vars: Environment variables exported to the script process.
            reuse_sandbox: Keep a single sandbox alive across runs instead of
                creating and killing one per run. Faster, but runs share state.
            sandbox_timeout: Lifetime of the sandbox itself, passed to ``Sandbox.create``.
        """
        self.timeout = timeout
        self._image = image
        self._workdir = workdir.rstrip('/') or '/tmp/skills'
        self._env_vars = dict(env_vars or {})
        self._reuse_sandbox = reuse_sandbox
        self._sandbox_timeout = sandbox_timeout
        self._sandbox: Sandbox | None = None
        self._sandbox_deadline: float = 0.0
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
        """Upload every stageable file in the skill folder into the sandbox workdir."""
        from opensandbox.models import WriteEntry

        entries, _ = _stage_snapshot(skill_root)
        write_entries = [
            WriteEntry(
                path=f'{self._workdir}/{relative}',
                data=resolved.read_bytes(),
                mode=0o755 if resolved.stat().st_mode & 0o111 else 0o644,
            )
            for relative, resolved in entries
        ]

        if write_entries:
            await sandbox.files.write_files(write_entries)

    def _build_command(self, remote_path: str, suffix: str, args: dict[str, Any] | None) -> str:
        """Build the shell command line executed inside the sandbox."""
        interpreter = _SANDBOX_INTERPRETERS.get(suffix)
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
        if script.uri is None:
            raise ValueError(f"Script '{script.name}' has no URI for sandbox execution")

        script_path = Path(script.uri).resolve()
        skill_root = skill_root_for(script)
        remote_path = f'{self._workdir}/{script_path.relative_to(skill_root).as_posix()}'
        # cwd is the script's own directory, matching LocalSkillScriptExecutor.
        working_directory = str(PurePosixPath(remote_path).parent)
        command = self._build_command(remote_path, script_path.suffix.lower(), args)

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

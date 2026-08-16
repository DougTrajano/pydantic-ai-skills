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
``reuse_sandbox=True`` to keep one warm across runs — faster, but runs share
state. A reused sandbox is rebuilt automatically when the skill changes, since
one executor instance serves every skill in a ``SkillsDirectory``.

Staging: the whole skill folder is copied in — ``SKILL.md``, ``resources/``,
``scripts/`` and anything else — and the script runs with its own directory as
the working directory, so sibling modules and ``../resources/data.json`` resolve
exactly as they do locally. Symlinks resolving outside the skill folder are
skipped with a warning, so staging cannot pull host files into the sandbox.

Running this example:
    ```bash
    pip install -e ".[examples,localsandbox]"
    python -m examples.sandbox_localsandbox
    ```

It writes a small stdlib-only demo skill under ``examples/tmp/``, wires it to an
agent through ``SkillsCapability``, and serves the agent on
http://127.0.0.1:7932. Ask it to inspect the sandbox and compare the answer with
your own machine — the paths and the visible filesystem belong to the sandbox.

The bundled ``examples/skills`` are not used here on purpose: they import
third-party packages such as ``arxiv``, which Pyodide has no wheels for.
"""

from __future__ import annotations

import shlex
import warnings
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent

from pydantic_ai_skills import (
    LocalSkillScriptExecutor,
    SkillsCapability,
    SkillScript,
    SkillScriptExecutor,
    SkillsDirectory,
)

EXAMPLES_DIR = Path(__file__).parent
TMP_DIR = EXAMPLES_DIR / 'tmp'
SKILL_DIR = TMP_DIR / 'sandbox-demo-skill'

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
        # Reused for its host-independent argument marshalling and output formatting.
        self._formatter = LocalSkillScriptExecutor()

    def _stage_files(self, skill_root: Path) -> dict[str, str | bytes]:
        """Map every stageable file in the skill folder to its path inside the sandbox."""
        return {
            f'{self.workdir}/{relative}': resolved.read_bytes()
            for relative, resolved in iter_stageable_files(skill_root)
        }

    def _get_sandbox(self, skill_root: Path) -> LocalSandbox:
        """Return the sandbox to run in, creating and staging one when needed.

        Staging happens at construction, so a reused sandbox is rebuilt whenever
        the skill changes. One executor instance serves every skill in a
        ``SkillsDirectory``, and without this the second skill would find the
        first skill's files still in place.
        """
        if self._reuse_sandbox and self._sandbox is not None:
            if self._staged_root == skill_root:
                return self._sandbox
            self.close()

        sandbox_cls = _require_localsandbox()
        kwargs: dict[str, Any] = {'files': self._stage_files(skill_root), 'cwd': self.workdir}
        if self._preset is not None:
            kwargs['preset'] = self._preset

        sandbox: LocalSandbox = sandbox_cls(**kwargs)
        if self._reuse_sandbox:
            self._sandbox = sandbox
            self._staged_root = skill_root
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


# ---------------------------------------------------------------------------
# Demo agent
# ---------------------------------------------------------------------------

_SKILL_MD = """---
name: sandbox-demo
description: Inspect the environment that skill scripts execute in. Use this skill whenever the user asks where scripts run, what the sandbox looks like, or to prove that execution is isolated from the host machine.
---

# Sandbox demo

Run `scripts/inspect_sandbox.py` to report the interpreter, platform, working
directory and visible files of whatever environment the script executes in.

Pass `--show-config` to also read `resources/config.json`, which lives at the
skill root rather than next to the script. It only resolves when the whole
skill folder was made available to the script.
"""

_INSPECT_SCRIPT = '''#!/usr/bin/env python3
"""Report where this script is really running."""

import argparse
import json
import platform
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Inspect the execution environment.')
    parser.add_argument('--label', default='sandbox-demo')
    parser.add_argument('--show-config', action='store_true')
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    report = {
        'label': args.label,
        'python_version': platform.python_version(),
        'platform': sys.platform,
        'cwd': str(Path.cwd()),
        'script_dir': str(script_dir),
        'files_next_to_script': sorted(p.name for p in script_dir.iterdir()),
    }

    if args.show_config:
        # Lives at the skill root, one level up from scripts/.
        config = script_dir.parent / 'resources' / 'config.json'
        report['config'] = json.loads(config.read_text(encoding='utf-8'))

    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
'''

_CONFIG_JSON = '{\n  "environment": "sandbox-demo",\n  "answer": 42\n}\n'


def write_demo_skill() -> Path:
    """Create a self-contained, stdlib-only demo skill under ``examples/tmp/``.

    The script lives in ``scripts/`` while its config lives in ``resources/``,
    so a run only succeeds when the whole skill folder reaches the sandbox.

    Returns:
        Path to the demo skill directory.
    """
    (SKILL_DIR / 'scripts').mkdir(parents=True, exist_ok=True)
    (SKILL_DIR / 'resources').mkdir(parents=True, exist_ok=True)

    (SKILL_DIR / 'SKILL.md').write_text(_SKILL_MD, encoding='utf-8')
    (SKILL_DIR / 'scripts' / 'inspect_sandbox.py').write_text(_INSPECT_SCRIPT, encoding='utf-8')
    (SKILL_DIR / 'resources' / 'config.json').write_text(_CONFIG_JSON, encoding='utf-8')
    return SKILL_DIR


def build_agent(model: str = 'gateway/openai:gpt-5.2') -> Agent:
    """Build an agent whose skill scripts execute inside LocalSandbox.

    Args:
        model: Model identifier passed to :class:`~pydantic_ai.Agent`.

    Returns:
        Configured agent with skills wired to the sandbox executor.
    """
    executor = LocalSandboxScriptExecutor()
    skills = SkillsCapability(directories=[SkillsDirectory(path=TMP_DIR, script_executor=executor)])

    return Agent(
        model=model,
        instructions=(
            'You are a demo assistant for sandboxed skill execution. '
            'When asked about the execution environment, run the sandbox-demo skill '
            'and report exactly what it prints.'
        ),
        capabilities=[skills],
    )


if __name__ == '__main__':
    # Imported here so the executor above stays importable without the examples extra.
    import logfire
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    logfire.configure()
    logfire.instrument_pydantic_ai()

    write_demo_skill()
    uvicorn.run(build_agent().to_web(), host='127.0.0.1', port=7932)

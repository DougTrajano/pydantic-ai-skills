"""Sandbox script executors.

Implementations of the
[`SkillScriptExecutor`][pydantic_ai_skills.SkillScriptExecutor] protocol that run
file-based skill scripts somewhere other than a local subprocess:

- [`OpenSandboxScriptExecutor`][pydantic_ai_skills.OpenSandboxScriptExecutor]:
  a container, via OpenSandbox. Needs the ``opensandbox`` extra.
- [`LocalSandboxScriptExecutor`][pydantic_ai_skills.LocalSandboxScriptExecutor]:
  a SQLite-backed virtual filesystem, via LocalSandbox. Needs the
  ``localsandbox`` extra.

Both stage the whole skill folder, run the script with its own directory as the
working directory, skip symlinks escaping the skill folder, and format output
exactly like local execution. Provider SDKs are imported lazily, so importing
this package never requires an extra to be installed.
"""

from pydantic_ai_skills.sandboxes._staging import iter_stageable_dirs, iter_stageable_files, skill_root_for
from pydantic_ai_skills.sandboxes.localsandbox import LocalSandboxScriptExecutor
from pydantic_ai_skills.sandboxes.opensandbox import OpenSandboxScriptExecutor

__all__ = [
    'LocalSandboxScriptExecutor',
    'OpenSandboxScriptExecutor',
    'iter_stageable_dirs',
    'iter_stageable_files',
    'skill_root_for',
]

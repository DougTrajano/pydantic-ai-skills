"""Read harness's skill catalog the same way on every supported `pydantic-ai-harness`.

Before 0.52, `Skills` scanned its libraries during construction and `apply` yielded one leaf
per skill. From 0.52 it reads them from a workspace in `for_run`, at the start of each run,
and only the capability `for_run` returns has per-skill leaves. These helpers resolve a
capability for a run first, which is a no-op on the older shape, so a test asserts on what a
run actually sees under either.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from pydantic_ai_harness import Skills

# Whether the installed harness reads skills at the start of each run (0.52+).
HARNESS_DISCOVERS_PER_RUN = 'workspace' in inspect.signature(Skills.__init__).parameters


def run_context() -> RunContext[None]:
    """A bare run context, enough for a capability's `for_run`."""
    return RunContext(deps=None, model=TestModel(), usage=RunUsage())


def for_run(capability: AbstractCapability[Any]) -> AbstractCapability[Any]:
    """Resolve `capability` for one run, as an agent does before reading it."""
    return asyncio.run(capability.for_run(run_context()))


def run_leaves(capability: AbstractCapability[Any]) -> list[AbstractCapability[Any]]:
    """The capabilities `apply` visits once `capability` is resolved for a run."""
    collected: list[AbstractCapability[Any]] = []
    for_run(capability).apply(collected.append)
    return collected


def harness_skills(directories: str | Path | Sequence[str | Path], **kwargs: Any) -> Skills[Any]:
    """Construct harness's `Skills` over local directories, on either harness shape."""
    if HARNESS_DISCOVERS_PER_RUN:
        from pydantic_ai.workspaces import LocalWorkspaceBackend

        kwargs.setdefault('workspace', LocalWorkspaceBackend(Path.cwd()))
    return Skills(directories, **kwargs)


def harness_leaves(directories: str | Path | Sequence[str | Path], **kwargs: Any) -> list[AbstractCapability[Any]]:
    """The per-skill leaves harness produces for `directories` in a run.

    From 0.52, a run that finds no skill gets `Skills` itself back, which is not a skill.
    """
    return [leaf for leaf in run_leaves(harness_skills(directories, **kwargs)) if not isinstance(leaf, Skills)]


def harness_names(library: Path) -> list[str]:
    """What harness would actually call the skills in `library`."""
    return sorted(leaf.id for leaf in harness_leaves(library) if leaf.id)


def instruction_parts(capability: AbstractCapability[Any]) -> list[str]:
    """A leaf's instructions as a list of strings.

    harness renders a single string from 0.52 and a one-element list before it; a leaf this
    package rebuilt always carries a list.
    """
    instructions = capability.get_instructions()
    if isinstance(instructions, str):
        return [instructions]
    assert isinstance(instructions, list)
    assert all(isinstance(part, str) for part in instructions)
    return list(instructions)

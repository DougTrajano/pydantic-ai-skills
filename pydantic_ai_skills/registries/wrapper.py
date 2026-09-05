"""Wrapper base class for registry composition.

Provides :class:`WrapperRegistry`, the base for the registry decorators (filtered,
prefixed, renamed). Follows the same delegation pattern as Pydantic AI's
``WrapperToolset``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai_skills.registries._base import SkillRegistry

__all__ = ['WrapperRegistry']


@dataclass
class WrapperRegistry(SkillRegistry):
    """A registry that wraps another registry and delegates to it.

    :meth:`sync` is forwarded to ``wrapped``. Subclasses that present a different library
    than the one they wrap override it to stage their own.

    Attributes:
        wrapped: The registry being decorated.
        target_dir: Where a subclass stages its composed library. When None, a
            process-lifetime temporary directory is used.
    """

    wrapped: SkillRegistry
    target_dir: str | Path | None = field(default=None, kw_only=True)

    def sync(self) -> Path:
        """Delegate sync to the wrapped registry."""
        return self.wrapped.sync()

"""Compatibility guards for the pydantic-ai internals this package relies on.

These symbols live in private (`_`-prefixed) pydantic-ai modules. They are not part
of the public API, so a future pydantic-ai release may move or remove them. This test
exists so such a break fails loudly here (and in CI) with a clear pointer, rather than
surfacing as an obscure error deep inside a skill run.
"""

from __future__ import annotations


def test_private_pydantic_ai_imports_available() -> None:
    """The private pydantic-ai symbols used across this package must import."""
    from pydantic_ai._function_schema import FunctionSchema, function_schema  # noqa: F401
    from pydantic_ai._griffe import doc_descriptions  # noqa: F401
    from pydantic_ai._utils import is_async_callable, run_in_executor  # noqa: F401
    from pydantic_ai.tools import GenerateToolJsonSchema  # noqa: F401


def test_public_run_context_import() -> None:
    """RunContext is imported from the public pydantic_ai namespace."""
    from pydantic_ai import RunContext  # noqa: F401

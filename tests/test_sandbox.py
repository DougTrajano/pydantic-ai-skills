"""Tests for LocalSandboxSkillScriptExecutor (sandbox.py).

All tests inject a fake ``localsandbox`` module via an autouse fixture so they
run without Deno or ``pip install localsandbox``.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

from pydantic_ai_skills.exceptions import SkillScriptExecutionError
from pydantic_ai_skills.local import FileBasedSkillScript
from pydantic_ai_skills.sandbox import LocalSandboxSkillScriptExecutor

# ── shared mock module ────────────────────────────────────────────────────────
_MOCK_LOCALSANDBOX = MagicMock()
_MOCK_LOCALSANDBOX.ExecutionPreset.NORMAL = 'NORMAL'
_MOCK_LOCALSANDBOX.ExecutionPreset.STRICT = 'STRICT'
_MOCK_LOCALSANDBOX.ExecutionPreset.PERMISSIVE = 'PERMISSIVE'


@pytest.fixture(autouse=True)
def _patch_localsandbox():
    """Inject a fake localsandbox module so all tests run without Deno."""
    with patch.dict(sys.modules, {'localsandbox': _MOCK_LOCALSANDBOX}):
        yield _MOCK_LOCALSANDBOX


def _make_sandbox_cm(
    stdout: str = '',
    stderr: str = '',
    error: str = '',
) -> tuple[MagicMock, MagicMock]:
    """Return (sandbox_cm, inner_sb) where sandbox_cm is a synchronous context manager."""
    inner_result = MagicMock()
    inner_result.stdout = stdout
    inner_result.stderr = stderr
    inner_result.error = error

    inner_sb = AsyncMock()
    inner_sb.aexecute_python = AsyncMock(return_value=inner_result)

    sandbox_cm = MagicMock()
    sandbox_cm.__enter__ = MagicMock(return_value=inner_sb)
    sandbox_cm.__exit__ = MagicMock(return_value=False)

    return sandbox_cm, inner_sb


# ── basic execution ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_localsandbox_executor_basic(tmp_path: object) -> None:
    """Happy path: stdout is returned from sandboxed execution."""
    script_file = tmp_path / 'hello.py'  # type: ignore[operator]
    script_file.write_text('print("hello from sandbox")')

    sandbox_cm, inner_sb = _make_sandbox_cm(stdout='hello from sandbox')
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor(timeout=30)
    script = FileBasedSkillScript(name='hello', uri=str(script_file))
    result = await executor.run(script)

    assert 'hello from sandbox' in result
    inner_sb.aexecute_python.assert_awaited_once()


@pytest.mark.asyncio
async def test_localsandbox_executor_no_output(tmp_path: object) -> None:
    """Script that produces no output returns '(no output)'."""
    script_file = tmp_path / 'silent.py'  # type: ignore[operator]
    script_file.write_text('pass')

    sandbox_cm, _ = _make_sandbox_cm(stdout='', stderr='', error='')
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor()
    script = FileBasedSkillScript(name='silent', uri=str(script_file))
    result = await executor.run(script)

    assert result == '(no output)'


# ── argument building ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_localsandbox_executor_with_args(tmp_path: object) -> None:
    """Args are injected as --key value pairs into the sys.argv preamble."""
    script_file = tmp_path / 'args_script.py'  # type: ignore[operator]
    script_file.write_text('import sys\nprint(sys.argv)')

    sandbox_cm, inner_sb = _make_sandbox_cm(stdout='')
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor()
    script = FileBasedSkillScript(name='args_script', uri=str(script_file))
    await executor.run(script, args={'query': 'test', 'limit': '5'})

    called_code: str = inner_sb.aexecute_python.call_args[0][0]
    assert '--query' in called_code
    assert 'test' in called_code
    assert '--limit' in called_code
    assert '5' in called_code


@pytest.mark.asyncio
async def test_localsandbox_executor_args_boolean(tmp_path: object) -> None:
    """Boolean True arg emits flag only; False/None is omitted."""
    script_file = tmp_path / 'bool_script.py'  # type: ignore[operator]
    script_file.write_text('pass')

    sandbox_cm, inner_sb = _make_sandbox_cm()
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor()
    script = FileBasedSkillScript(name='bool_script', uri=str(script_file))
    await executor.run(script, args={'verbose': True, 'debug': False, 'empty': None})

    called_code: str = inner_sb.aexecute_python.call_args[0][0]
    assert '--verbose' in called_code
    assert '--debug' not in called_code
    assert '--empty' not in called_code


@pytest.mark.asyncio
async def test_localsandbox_executor_args_list(tmp_path: object) -> None:
    """List values repeat the flag for each item."""
    script_file = tmp_path / 'list_script.py'  # type: ignore[operator]
    script_file.write_text('pass')

    sandbox_cm, inner_sb = _make_sandbox_cm()
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor()
    script = FileBasedSkillScript(name='list_script', uri=str(script_file))
    await executor.run(script, args={'item': ['a', 'b', 'c']})

    called_code: str = inner_sb.aexecute_python.call_args[0][0]
    assert called_code.count('--item') == 3
    assert '"a"' in called_code
    assert '"b"' in called_code
    assert '"c"' in called_code


# ── error / output variations ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_localsandbox_executor_with_stderr(tmp_path: object) -> None:
    """Stderr output is appended to the returned string."""
    script_file = tmp_path / 'stderr_script.py'  # type: ignore[operator]
    script_file.write_text('import sys\nprint("out")\nprint("err", file=sys.stderr)')

    sandbox_cm, _ = _make_sandbox_cm(stdout='out', stderr='err')
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor()
    script = FileBasedSkillScript(name='stderr_script', uri=str(script_file))
    result = await executor.run(script)

    assert 'out' in result
    assert 'Stderr:' in result
    assert 'err' in result


@pytest.mark.asyncio
async def test_localsandbox_executor_with_error(tmp_path: object) -> None:
    """Error field from sandbox result is appended to the returned string."""
    script_file = tmp_path / 'error_script.py'  # type: ignore[operator]
    script_file.write_text('raise RuntimeError("boom")')

    sandbox_cm, _ = _make_sandbox_cm(stdout='', error='RuntimeError: boom')
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor()
    script = FileBasedSkillScript(name='error_script', uri=str(script_file))
    result = await executor.run(script)

    assert 'Error:' in result
    assert 'boom' in result


@pytest.mark.asyncio
async def test_localsandbox_executor_no_uri() -> None:
    """Script without URI raises SkillScriptExecutionError."""
    executor = LocalSandboxSkillScriptExecutor()
    script = FileBasedSkillScript(name='no_uri', uri='/tmp/placeholder')
    script.uri = None

    with pytest.raises(SkillScriptExecutionError, match='has no URI'):
        await executor.run(script)


# ── timeout ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_localsandbox_executor_timeout(tmp_path: object) -> None:
    """Execution that exceeds timeout raises SkillScriptExecutionError."""
    script_file = tmp_path / 'slow.py'  # type: ignore[operator]
    script_file.write_text('import time\ntime.sleep(10)')

    async def _slow_execute(*args, **kwargs):
        await anyio.sleep(10)

    inner_sb = AsyncMock()
    inner_sb.aexecute_python = _slow_execute

    sandbox_cm = MagicMock()
    sandbox_cm.__enter__ = MagicMock(return_value=inner_sb)
    sandbox_cm.__exit__ = MagicMock(return_value=False)
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor(timeout=1)
    script = FileBasedSkillScript(name='slow', uri=str(script_file))

    with pytest.raises(SkillScriptExecutionError, match='timed out'):
        await executor.run(script)


# ── optional-dep error ────────────────────────────────────────────────────────


def test_localsandbox_executor_missing_dep() -> None:
    """ImportError with installation hint is raised when localsandbox is absent."""
    with patch.dict(sys.modules, {'localsandbox': None}):
        with pytest.raises(ImportError, match='pydantic-ai-skills\\[sandbox\\]'):
            LocalSandboxSkillScriptExecutor()


# ── shared sandbox ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_localsandbox_executor_shared_sandbox(tmp_path: object) -> None:
    """When sandbox= is provided, the existing instance is reused (no new LocalSandbox)."""
    script_file = tmp_path / 'shared.py'  # type: ignore[operator]
    script_file.write_text('print("shared")')

    mock_result = MagicMock()
    mock_result.stdout = 'shared'
    mock_result.stderr = ''
    mock_result.error = ''

    shared_sb = AsyncMock()
    shared_sb.aexecute_python = AsyncMock(return_value=mock_result)

    _MOCK_LOCALSANDBOX.LocalSandbox.reset_mock()

    executor = LocalSandboxSkillScriptExecutor(sandbox=shared_sb)
    script = FileBasedSkillScript(name='shared', uri=str(script_file))
    result = await executor.run(script)

    _MOCK_LOCALSANDBOX.LocalSandbox.assert_not_called()
    shared_sb.aexecute_python.assert_awaited_once()
    assert 'shared' in result


# ── configuration pass-through ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_localsandbox_executor_preset_passed(tmp_path: object) -> None:
    """The preset is forwarded to the LocalSandbox constructor."""
    script_file = tmp_path / 'preset_script.py'  # type: ignore[operator]
    script_file.write_text('pass')

    sandbox_cm, _ = _make_sandbox_cm()
    _MOCK_LOCALSANDBOX.LocalSandbox.reset_mock()
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    custom_preset = _MOCK_LOCALSANDBOX.ExecutionPreset.STRICT
    executor = LocalSandboxSkillScriptExecutor(preset=custom_preset)
    script = FileBasedSkillScript(name='preset_script', uri=str(script_file))
    await executor.run(script)

    _MOCK_LOCALSANDBOX.LocalSandbox.assert_called_once_with(preset=custom_preset)


@pytest.mark.asyncio
async def test_localsandbox_executor_preload_packages(tmp_path: object) -> None:
    """preload_packages is forwarded to aexecute_python."""
    script_file = tmp_path / 'numpy_script.py'  # type: ignore[operator]
    script_file.write_text('import numpy as np\nprint(np.__version__)')

    sandbox_cm, inner_sb = _make_sandbox_cm(stdout='1.24.0')
    _MOCK_LOCALSANDBOX.LocalSandbox.return_value = sandbox_cm

    executor = LocalSandboxSkillScriptExecutor(preload_packages=['numpy'])
    script = FileBasedSkillScript(name='numpy_script', uri=str(script_file))
    await executor.run(script)

    _, kwargs = inner_sb.aexecute_python.call_args
    assert kwargs.get('preload_packages') == ['numpy']


def test_localsandbox_executor_default_timeout() -> None:
    """Default timeout is 30 seconds."""
    executor = LocalSandboxSkillScriptExecutor()
    assert executor.timeout == 30


def test_localsandbox_executor_custom_timeout() -> None:
    """Custom timeout is stored correctly."""
    executor = LocalSandboxSkillScriptExecutor(timeout=120)
    assert executor.timeout == 120

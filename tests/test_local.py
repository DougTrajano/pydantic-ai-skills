"""Tests for file-based resources and script execution (local.py)."""

from pathlib import Path

import pytest

from pydantic_ai_skills.exceptions import SkillResourceLoadError, SkillScriptExecutionError
from pydantic_ai_skills.local import (
    CallableSkillScriptExecutor,
    FileBasedSkillResource,
    FileBasedSkillScript,
    LocalSkillScriptExecutor,
)
from pydantic_ai_skills.types import SkillScript


def test_file_based_resource_load(tmp_path: Path) -> None:
    """Test loading file-based resource."""
    # Create a resource file
    skill_dir = tmp_path / 'test-skill'
    skill_dir.mkdir()
    resource_file = skill_dir / 'REFERENCE.md'
    resource_file.write_text('# Reference\n\nTest content')

    resource = FileBasedSkillResource(
        name='REFERENCE.md',
        uri=str(resource_file),
        skill_uri=str(skill_dir),
    )

    # Load synchronously by calling the async function
    import asyncio

    content = asyncio.run(resource.load(None))
    assert '# Reference' in content
    assert 'Test content' in content


def test_file_based_resource_no_uri() -> None:
    """Test file-based resource without URI raises error during load."""
    # Create resource with minimal valid fields, then clear uri to test load behavior
    resource = FileBasedSkillResource(name='test', content='temp', uri=None)
    resource.uri = None  # Clear after creation
    resource.content = None  # Also clear content to force URI path

    import asyncio

    with pytest.raises(SkillResourceLoadError, match='has no URI'):
        asyncio.run(resource.load(None))


def test_file_based_resource_path_traversal(tmp_path: Path) -> None:
    """Test file-based resource prevents path traversal."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    # Try to access file outside skill directory
    outside_file = tmp_path / 'outside.txt'
    outside_file.write_text('Should not be accessible')

    resource = FileBasedSkillResource(
        name='malicious',
        uri=str(outside_file),
        skill_uri=str(skill_dir),
    )

    import asyncio

    with pytest.raises(SkillResourceLoadError, match='Resource path escapes skill directory'):
        asyncio.run(resource.load(None))


def test_file_based_resource_file_not_found(tmp_path: Path) -> None:
    """Test file-based resource with non-existent file."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    resource = FileBasedSkillResource(
        name='missing',
        uri=str(skill_dir / 'missing.md'),
        skill_uri=str(skill_dir),
    )

    import asyncio

    with pytest.raises(SkillResourceLoadError, match='Failed to read resource'):
        asyncio.run(resource.load(None))


@pytest.mark.asyncio
async def test_local_script_executor_no_uri() -> None:
    """Test LocalSkillScriptExecutor with script without URI."""
    executor = LocalSkillScriptExecutor()
    # Create with temp uri, then clear to test runtime behavior
    script = FileBasedSkillScript(name='test', uri='/temp')
    script.uri = None

    with pytest.raises(SkillScriptExecutionError, match='has no URI'):
        await executor.run(script)


@pytest.mark.asyncio
async def test_local_script_executor_with_args(tmp_path: Path) -> None:
    """Test LocalSkillScriptExecutor with command-line arguments."""
    # Create a test script
    script_file = tmp_path / 'test_script.py'
    script_file.write_text("""#!/usr/bin/env python3
import sys
print(f"Args: {sys.argv[1:]}")
for i in range(1, len(sys.argv), 2):
    print(f"{sys.argv[i]}: {sys.argv[i+1]}")
""")

    executor = LocalSkillScriptExecutor()
    script = FileBasedSkillScript(
        name='test_script',
        uri=str(script_file),
    )

    result = await executor.run(script, args={'query': 'test', 'limit': '5'})

    assert '--query' in result or 'query' in result
    assert 'test' in result


@pytest.mark.asyncio
async def test_local_script_executor_timeout(tmp_path: Path) -> None:
    """Test LocalSkillScriptExecutor timeout."""
    # Create a script that sleeps longer than timeout
    script_file = tmp_path / 'slow_script.py'
    script_file.write_text("""#!/usr/bin/env python3
import time
time.sleep(5)
print("Done")
""")

    executor = LocalSkillScriptExecutor(timeout=1)  # 1 second timeout
    script = FileBasedSkillScript(
        name='slow_script',
        uri=str(script_file),
    )

    with pytest.raises(SkillScriptExecutionError, match='timed out'):
        await executor.run(script)


@pytest.mark.asyncio
async def test_local_script_executor_with_stderr(tmp_path: Path) -> None:
    """Test LocalSkillScriptExecutor captures stderr."""
    script_file = tmp_path / 'error_script.py'
    script_file.write_text("""#!/usr/bin/env python3
import sys
print("stdout output")
print("stderr output", file=sys.stderr)
""")

    executor = LocalSkillScriptExecutor()
    script = FileBasedSkillScript(
        name='error_script',
        uri=str(script_file),
    )

    result = await executor.run(script)

    assert 'stdout output' in result
    assert 'stderr output' in result


@pytest.mark.asyncio
async def test_local_script_executor_nonzero_exit(tmp_path: Path) -> None:
    """Test LocalSkillScriptExecutor with non-zero exit code."""
    script_file = tmp_path / 'failing_script.py'
    script_file.write_text("""#!/usr/bin/env python3
import sys
print("Error occurred")
sys.exit(1)
""")

    executor = LocalSkillScriptExecutor()
    script = FileBasedSkillScript(
        name='failing_script',
        uri=str(script_file),
    )

    result = await executor.run(script)

    assert 'Error occurred' in result
    assert 'exited with code 1' in result


@pytest.mark.asyncio
async def test_local_script_executor_with_cwd(tmp_path: Path) -> None:
    """Test LocalSkillScriptExecutor sets working directory."""
    skill_dir = tmp_path / 'skill'
    skill_dir.mkdir()

    script_file = skill_dir / 'test_cwd.py'
    script_file.write_text("""#!/usr/bin/env python3
import os
print(f"CWD: {os.getcwd()}")
""")

    executor = LocalSkillScriptExecutor()
    script = FileBasedSkillScript(
        name='test_cwd',
        uri=str(script_file),
    )

    result = await executor.run(script, skill_uri=str(skill_dir))

    assert str(skill_dir) in result or skill_dir.name in result


@pytest.mark.asyncio
async def test_local_script_executor_invalid_script(tmp_path: Path) -> None:
    """Test LocalSkillScriptExecutor with invalid Python syntax."""
    script_file = tmp_path / 'invalid.py'
    # Write invalid Python code
    script_file.write_text('this is not ( valid python syntax')

    executor = LocalSkillScriptExecutor()
    script = FileBasedSkillScript(
        name='invalid',
        uri=str(script_file),
    )

    # Invalid syntax will cause Python to exit with non-zero code
    result = await executor.run(script)
    # Should include error message and non-zero exit code
    assert 'exited with code' in result or 'SyntaxError' in result


@pytest.mark.asyncio
async def test_callable_script_executor_sync() -> None:
    """Test CallableSkillScriptExecutor with sync function."""

    def my_executor(script, args=None, skill_uri=None):
        return f'Executed {script.name} with args {args}'

    executor = CallableSkillScriptExecutor(func=my_executor)
    script = SkillScript(name='test', uri='/fake', function=None, function_schema=None)

    result = await executor.run(script, args={'key': 'value'})

    assert 'test' in result
    assert "{'key': 'value'}" in result


@pytest.mark.asyncio
async def test_callable_script_executor_async() -> None:
    """Test CallableSkillScriptExecutor with async function."""

    async def my_async_executor(script, args=None, skill_uri=None):
        return f'Async executed {script.name}'

    executor = CallableSkillScriptExecutor(func=my_async_executor)
    script = SkillScript(name='test_async', uri='/fake', function=None, function_schema=None)

    result = await executor.run(script)

    assert 'test_async' in result


@pytest.mark.asyncio
async def test_local_script_executor_no_output(tmp_path: Path) -> None:
    """Test LocalSkillScriptExecutor with script that produces no output."""
    script_file = tmp_path / 'silent_script.py'
    script_file.write_text("""#!/usr/bin/env python3
# Script with no output
pass
""")

    executor = LocalSkillScriptExecutor()
    script = FileBasedSkillScript(
        name='silent_script',
        uri=str(script_file),
    )

    result = await executor.run(script)

    assert result == '(no output)'


def test_local_script_executor_custom_python() -> None:
    """Test LocalSkillScriptExecutor with custom Python executable."""
    import sys

    executor = LocalSkillScriptExecutor(python_executable=sys.executable)

    assert executor._python_executable == sys.executable


def test_local_script_executor_custom_timeout() -> None:
    """Test LocalSkillScriptExecutor with custom timeout."""
    executor = LocalSkillScriptExecutor(timeout=120)

    assert executor.timeout == 120

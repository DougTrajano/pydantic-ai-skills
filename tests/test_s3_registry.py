"""Tests for S3SkillsRegistry."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pydantic_ai_skills.registries.s3 import S3SkillsRegistry

# ---------------------------------------------------------------------------
# Fake boto3 S3 client
# ---------------------------------------------------------------------------


class _FakePaginator:
    def __init__(self, store: dict[str, bytes], modified: datetime) -> None:
        self._store = store
        self._modified = modified

    def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        contents = [{'Key': key, 'LastModified': self._modified} for key in self._store if key.startswith(Prefix)]
        # Split across two pages to exercise pagination handling.
        mid = len(contents) // 2 or len(contents)
        return [{'Contents': contents[:mid]}, {'Contents': contents[mid:]}]


class FakeS3Client:
    """Minimal in-memory stand-in for a boto3 S3 client."""

    def __init__(self, store: dict[str, bytes] | None = None) -> None:
        self.store: dict[str, bytes] = dict(store or {})
        self.modified = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.secret = 'super-secret-key'

    def get_paginator(self, name: str) -> _FakePaginator:
        assert name == 'list_objects_v2'
        return _FakePaginator(self.store, self.modified)

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        Path(Filename).write_bytes(self.store[Key])


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _skill_md(name: str, description: str) -> bytes:
    return f'---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nInstructions here.\n'.encode()


@pytest.fixture()
def client() -> FakeS3Client:
    """Fake client with two skills under the ``skills/`` prefix."""
    return FakeS3Client(
        {
            'skills/pdf/SKILL.md': _skill_md('pdf', 'PDF manipulation skill.'),
            'skills/xlsx/SKILL.md': _skill_md('xlsx', 'Excel spreadsheet skill.'),
        }
    )


def _make_registry(client: FakeS3Client, **kwargs: Any) -> S3SkillsRegistry:
    return S3SkillsRegistry(bucket='my-bucket', prefix='skills', boto3_client=client, **kwargs)


# ---------------------------------------------------------------------------
# Construction / client injection
# ---------------------------------------------------------------------------


def test_import_error_when_boto3_missing_and_no_client() -> None:
    """Building a default client without boto3 installed raises a helpful ImportError."""
    with patch.dict('sys.modules', {'boto3': None}):
        with pytest.raises(ImportError, match=r'pip install pydantic-ai-skills\[s3\]'):
            S3SkillsRegistry(bucket='my-bucket')


def test_repr_does_not_leak_client_or_credentials(client: FakeS3Client) -> None:
    """__repr__ shows bucket/prefix/target_dir but never the client or its credentials."""
    registry = _make_registry(client)
    result = repr(registry)
    assert 'my-bucket' in result
    assert 'skills' in result
    assert 'super-secret-key' not in result
    assert 'FakeS3Client' not in result


def test_injected_client_skips_boto3_import(client: FakeS3Client) -> None:
    """A supplied client works even when boto3 cannot be imported."""
    with patch.dict('sys.modules', {'boto3': None}):
        registry = _make_registry(client)
    assert {s.name for s in registry.get_skills()} == {'pdf', 'xlsx'}


# ---------------------------------------------------------------------------
# get_skills / search / get
# ---------------------------------------------------------------------------


def test_get_skills_returns_all(client: FakeS3Client) -> None:
    """get_skills returns every skill synced from the bucket."""
    registry = _make_registry(client)
    assert {s.name for s in registry.get_skills()} == {'pdf', 'xlsx'}


async def test_search_returns_matching_skills(client: FakeS3Client) -> None:
    """Search returns skills whose name matches the query."""
    registry = _make_registry(client)
    results = await registry.search('pdf')
    assert [s.name for s in results] == ['pdf']


async def test_search_is_case_insensitive(client: FakeS3Client) -> None:
    """Search matching ignores case for both name and description."""
    registry = _make_registry(client)
    results = await registry.search('EXCEL')
    assert [s.name for s in results] == ['xlsx']


async def test_search_respects_limit(client: FakeS3Client) -> None:
    """Search returns at most *limit* results."""
    registry = _make_registry(client)
    results = await registry.search('skill', limit=1)
    assert len(results) == 1


async def test_get_returns_skill_by_name(client: FakeS3Client) -> None:
    """Get returns the skill matching the exact name."""
    registry = _make_registry(client)
    skill = await registry.get('pdf')
    assert skill.name == 'pdf'


async def test_get_raises_for_unknown_skill(client: FakeS3Client) -> None:
    """Get raises KeyError when the skill name is not present."""
    registry = _make_registry(client)
    with pytest.raises(KeyError):
        await registry.get('nonexistent')


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


async def test_metadata_contains_registry_keys(client: FakeS3Client) -> None:
    """Enriched skills carry registry, bucket, prefix, source_url, and version metadata."""
    registry = _make_registry(client)
    skill = await registry.get('pdf')
    assert skill.metadata is not None
    assert skill.metadata['registry'] == 'S3SkillsRegistry'
    assert skill.metadata['bucket'] == 'my-bucket'
    assert skill.metadata['prefix'] == 'skills'
    assert skill.metadata['source_url'] == 's3://my-bucket/skills/pdf'
    assert skill.metadata['version'] == '2024-01-01T00:00:00+00:00'


# ---------------------------------------------------------------------------
# Prefix scoping
# ---------------------------------------------------------------------------


def test_empty_prefix_lists_root() -> None:
    """An empty prefix discovers skills at the bucket root."""
    client = FakeS3Client({'pdf/SKILL.md': _skill_md('pdf', 'PDF skill.')})
    registry = S3SkillsRegistry(bucket='my-bucket', prefix='', boto3_client=client)
    assert {s.name for s in registry.get_skills()} == {'pdf'}


# ---------------------------------------------------------------------------
# install / update
# ---------------------------------------------------------------------------


async def test_install_copies_skill_directory(client: FakeS3Client, tmp_path: Path) -> None:
    """Install copies a skill's files into a named subdirectory of the target."""
    registry = _make_registry(client)
    dest = await registry.install('pdf', tmp_path / 'installed')
    assert dest == (tmp_path / 'installed' / 'pdf').resolve()
    assert (dest / 'SKILL.md').exists()


async def test_install_raises_for_unknown_skill(client: FakeS3Client, tmp_path: Path) -> None:
    """Install raises KeyError for a skill that is not in the registry."""
    registry = _make_registry(client)
    with pytest.raises(KeyError):
        await registry.install('nonexistent', tmp_path)


async def test_update_installs_when_not_present(client: FakeS3Client, tmp_path: Path) -> None:
    """Update falls back to a plain install when the skill is not yet installed."""
    registry = _make_registry(client)
    dest = await registry.update('pdf', tmp_path / 'installed')
    assert (dest / 'SKILL.md').exists()


async def test_update_resyncs_and_reinstalls(client: FakeS3Client, tmp_path: Path) -> None:
    """Update re-syncs from S3 and re-copies an already-installed skill."""
    registry = _make_registry(client)
    target = tmp_path / 'installed'
    await registry.install('pdf', target)
    dest = await registry.update('pdf', target)
    assert (dest / 'SKILL.md').exists()


async def test_update_mirrors_removed_skill(client: FakeS3Client, tmp_path: Path) -> None:
    """A skill deleted from the bucket disappears locally after the next sync."""
    registry = _make_registry(client)
    assert {s.name for s in registry.get_skills()} == {'pdf', 'xlsx'}

    target = tmp_path / 'installed'
    await registry.install('pdf', target)

    # Remove xlsx from the bucket, then trigger a re-sync via update.
    del client.store['skills/xlsx/SKILL.md']
    await registry.update('pdf', target)

    assert {s.name for s in registry.get_skills()} == {'pdf'}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_list_failure_wrapped_in_runtime_error(tmp_path: Path) -> None:
    """A client error during listing is wrapped in RuntimeError with context."""

    class FailingListClient(FakeS3Client):
        def get_paginator(self, name: str) -> Any:
            raise RuntimeError('boom: access denied')

    with pytest.raises(RuntimeError, match="Failed to list objects in bucket 'my-bucket'"):
        S3SkillsRegistry(bucket='my-bucket', prefix='skills', boto3_client=FailingListClient())


def test_download_failure_wrapped_in_runtime_error(client: FakeS3Client) -> None:
    """A client error during download is wrapped in RuntimeError with context."""

    class FailingDownloadClient(FakeS3Client):
        def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
            raise RuntimeError('boom: timeout')

    failing = FailingDownloadClient(client.store)
    with pytest.raises(RuntimeError, match="Failed to download .* from bucket 'my-bucket'"):
        S3SkillsRegistry(bucket='my-bucket', prefix='skills', boto3_client=failing)


# ---------------------------------------------------------------------------
# auto_install
# ---------------------------------------------------------------------------


def test_auto_install_false_does_not_sync(client: FakeS3Client, tmp_path: Path) -> None:
    """With auto_install disabled, no sync happens and an empty cache yields no skills."""
    registry = S3SkillsRegistry(
        bucket='my-bucket',
        prefix='skills',
        target_dir=tmp_path / 'cache',
        boto3_client=client,
        auto_install=False,
    )
    # Nothing on disk yet → no skills.
    assert registry.get_skills() == []


# ---------------------------------------------------------------------------
# Path traversal protection
# ---------------------------------------------------------------------------


def test_sync_rejects_path_traversal_key(tmp_path: Path) -> None:
    """A malicious object key that escapes the target directory raises ValueError."""
    client = FakeS3Client({'../evil/SKILL.md': _skill_md('evil', 'escape attempt')})
    with pytest.raises(ValueError, match='escapes target directory'):
        S3SkillsRegistry(
            bucket='my-bucket',
            prefix='',
            target_dir=tmp_path / 'cache',
            boto3_client=client,
        )


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def test_top_level_import() -> None:
    """S3SkillsRegistry is exported from the top-level package."""
    from pydantic_ai_skills import S3SkillsRegistry as TopLevel

    assert TopLevel is S3SkillsRegistry


def test_registries_module_import() -> None:
    """S3SkillsRegistry is exported from the registries module."""
    from pydantic_ai_skills.registries import S3SkillsRegistry as FromRegistries

    assert FromRegistries is S3SkillsRegistry

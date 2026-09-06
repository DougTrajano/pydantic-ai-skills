"""Tests for S3SkillsRegistry.

A registry's job in v2 is to put an S3 prefix on the local filesystem as a skill library
harness can read; it does not parse SKILL.md or build Skill objects. These tests drive
that contract against an in-memory stand-in for boto3.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic_ai_harness import Skills

from pydantic_ai_skills import SkillsCapability
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


def library_names(library: Path) -> list[str]:
    """Names of the skill packages in a library, sorted."""
    return sorted(child.name for child in library.iterdir() if (child / 'SKILL.md').is_file())


def harness_names(library: Path) -> list[str]:
    """What harness would actually call the skills in `library`."""
    leaves: list[Any] = []
    Skills(library).apply(leaves.append)
    return sorted(leaf.id for leaf in leaves)


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
    assert library_names(registry.sync()) == ['pdf', 'xlsx']


def test_construction_does_not_contact_s3(client: FakeS3Client) -> None:
    """Fetching is `sync`'s job, so building a registry never does network I/O."""
    calls: list[str] = []
    client.on_list = calls.append  # type: ignore[attr-defined]

    _make_registry(client)

    assert calls == []


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


def test_sync_downloads_the_prefix(client: FakeS3Client) -> None:
    """Every object under the prefix is mirrored into the local library."""
    # Held, not inlined: the default cache is a TemporaryDirectory owned by the registry,
    # so a throwaway registry takes its downloads with it.
    registry = _make_registry(client)
    library = registry.sync()

    assert library_names(library) == ['pdf', 'xlsx']
    assert 'PDF manipulation skill.' in (library / 'pdf' / 'SKILL.md').read_text()


def test_sync_returns_a_library_harness_accepts(client: FakeS3Client) -> None:
    """The whole contract: the returned path is something `Skills` can read."""
    assert harness_names(_make_registry(client).sync()) == ['pdf', 'xlsx']


def test_sync_reaches_the_capability(client: FakeS3Client) -> None:
    """The skills a bucket holds end up in the agent's deferred catalog."""
    assert SkillsCapability(registries=[_make_registry(client)]).skill_names == ['pdf', 'xlsx']


def test_empty_prefix_lists_the_bucket_root(client: FakeS3Client) -> None:
    """A registry without a prefix mirrors the whole bucket."""
    client.store = {'pdf/SKILL.md': _skill_md('pdf', 'PDF manipulation skill.')}
    registry = S3SkillsRegistry(bucket='my-bucket', boto3_client=client)

    assert library_names(registry.sync()) == ['pdf']


def test_resync_mirrors_a_removed_skill(client: FakeS3Client, tmp_path: Path) -> None:
    """A skill deleted from the bucket must not linger in the local cache."""
    registry = _make_registry(client, target_dir=tmp_path / 'cache')
    assert library_names(registry.sync()) == ['pdf', 'xlsx']

    del client.store['skills/xlsx/SKILL.md']

    assert library_names(registry.sync()) == ['pdf']


def test_sync_ignores_directory_markers(client: FakeS3Client) -> None:
    """S3 consoles create zero-byte keys ending in `/`; there is nothing to download."""
    client.store['skills/'] = b''
    client.store['skills/pdf/'] = b''

    assert library_names(_make_registry(client).sync()) == ['pdf', 'xlsx']


def test_revision_reports_the_newest_object_time(client: FakeS3Client) -> None:
    """Lets a caller record which version of a moving prefix a run used."""
    registry = _make_registry(client)
    registry.sync()

    assert registry.revision('pdf') == client.modified.isoformat()


def test_revision_is_none_before_a_sync(client: FakeS3Client) -> None:
    """Nothing has been listed yet, so there is no modification time to report."""
    assert _make_registry(client).revision('pdf') is None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


def test_list_failure_wrapped_in_runtime_error(tmp_path: Path) -> None:
    """A boto3 listing error is re-raised with the bucket and prefix named."""

    class BrokenClient(FakeS3Client):
        def get_paginator(self, name: str) -> Any:
            raise RuntimeError('boom')

    registry = _make_registry(BrokenClient(), target_dir=tmp_path)

    with pytest.raises(RuntimeError, match=r"Failed to list objects in bucket 'my-bucket'"):
        registry.sync()


def test_download_failure_wrapped_in_runtime_error(client: FakeS3Client) -> None:
    """A boto3 download error is re-raised with the failing key named."""

    def broken_download(Bucket: str, Key: str, Filename: str) -> None:
        raise RuntimeError('boom')

    client.download_file = broken_download  # type: ignore[method-assign]

    registry = _make_registry(client)

    with pytest.raises(RuntimeError, match=r"Failed to download 'skills/"):
        registry.sync()


def test_sync_rejects_path_traversal_key(tmp_path: Path) -> None:
    """A malicious key must not write outside the cache directory."""
    client = FakeS3Client({'skills/../../escaped.txt': b'nope'})
    registry = _make_registry(client, target_dir=tmp_path / 'cache')

    with pytest.raises(ValueError, match='escapes target directory'):
        registry.sync()


def test_auto_install_false_does_not_contact_s3(client: FakeS3Client, tmp_path: Path) -> None:
    """Air-gapped deployments read only what is already on disk."""
    cache = tmp_path / 'cache'
    (cache / 'skills' / 'preexisting').mkdir(parents=True)
    (cache / 'skills' / 'preexisting' / 'SKILL.md').write_bytes(_skill_md('preexisting', 'Already downloaded.'))

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError('sync must not contact S3 when auto_install is False')

    client.get_paginator = fail  # type: ignore[method-assign]
    registry = _make_registry(client, target_dir=cache, auto_install=False)

    assert library_names(registry.sync()) == ['preexisting']


def test_auto_install_false_reports_an_empty_cache(client: FakeS3Client, tmp_path: Path) -> None:
    """Silently returning nothing would look like a bucket with no skills."""
    registry = _make_registry(client, target_dir=tmp_path / 'empty', auto_install=False)

    with pytest.raises(ValueError, match='auto_install is disabled'):
        registry.sync()


def test_a_prefix_matching_nothing_is_reported(client: FakeS3Client, tmp_path: Path) -> None:
    """The usual cause is a prefix that does not match the bucket's layout."""
    registry = S3SkillsRegistry(
        bucket='my-bucket',
        prefix='wrong-prefix',
        boto3_client=client,
        target_dir=tmp_path / 'cache',
    )

    with pytest.raises(ValueError, match='matched no objects'):
        registry.sync()


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def test_top_level_import() -> None:
    """S3SkillsRegistry is exported from the package root."""
    from pydantic_ai_skills import S3SkillsRegistry as Exported

    assert Exported is S3SkillsRegistry


def test_registries_module_import() -> None:
    """S3SkillsRegistry is exported from the registries subpackage."""
    from pydantic_ai_skills.registries import S3SkillsRegistry as Exported

    assert Exported is S3SkillsRegistry

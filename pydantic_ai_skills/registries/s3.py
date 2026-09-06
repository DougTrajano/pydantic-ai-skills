"""S3-backed skill registry using boto3.

Provides :class:`S3SkillsRegistry` for downloading skills from an Amazon S3
bucket (or any S3-compatible store such as MinIO, Ceph, or Cloudflare R2) and
handing their skill library to :class:`~pydantic_ai_skills.SkillsCapability`.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_ai_skills.registries._base import SkillRegistry

__all__ = ['S3SkillsRegistry']


class S3SkillsRegistry(SkillRegistry):
    """Skills registry backed by an S3 bucket, downloaded with boto3.

    :meth:`sync` lists and downloads every object under ``bucket/prefix`` into a local
    cache directory, then returns the directory holding the skill packages. Each sync
    mirrors the remote prefix — the cached subtree is cleared first, so skills removed
    from the bucket no longer appear locally.

    Works with Amazon S3 and any S3-compatible store (MinIO, Ceph, Cloudflare R2,
    etc.). All connection details — credentials, ``endpoint_url``, region, TLS,
    and path-style addressing — are configured on the boto3 client you pass via
    ``boto3_client``. When omitted, a default ``boto3.client("s3")`` is built,
    which uses boto3's standard credential resolution chain.

    It does not parse ``SKILL.md``: the directory it produces is handed to
    :class:`~pydantic_ai_skills.SkillsCapability`, and validating and rendering the
    packages inside it is `pydantic-ai-harness`'s job.

    Args:
        bucket: Name of the S3 bucket containing the skills.
        prefix: Key prefix inside the bucket where skill directories live.
            Defaults to the bucket root (``""``). For example, pass ``"skills"``
            when skills live at ``s3://bucket/skills/<skill>/``.
        target_dir: Local directory where objects are downloaded. Defaults to a
            temporary directory scoped to the registry instance. A directory you pass
            persists across :meth:`sync` calls and is **not** cleaned up automatically —
            callers own the lifecycle.
        boto3_client: A pre-built boto3 S3 client. Use this to configure
            credentials, ``endpoint_url`` (for MinIO/Ceph/R2), region, TLS, and
            path-style addressing. When ``None``, a default ``boto3.client("s3")``
            is created (requires the ``s3`` extra: ``pip install pydantic-ai-skills[s3]``).
        auto_install: When ``True`` (default), :meth:`sync` contacts S3 so the local copy
            is up to date. Set to ``False`` to read only what already exists in
            ``target_dir``, which is what offline or air-gapped environments want.

    Examples:
        Amazon S3 with the ambient credential chain:

        ```python
        from pydantic_ai_skills import S3SkillsRegistry, SkillsCapability

        capability = SkillsCapability(
            registries=[S3SkillsRegistry(bucket="my-skills", prefix="skills")]
        )
        ```

        MinIO (or any S3-compatible store) with a custom client:

        ```python
        import boto3
        from botocore.config import Config
        from pydantic_ai_skills.registries.s3 import S3SkillsRegistry

        client = boto3.client(
            "s3",
            endpoint_url="http://localhost:9000",
            aws_access_key_id="minioadmin",
            aws_secret_access_key="minioadmin",
            config=Config(s3={"addressing_style": "path"}),
        )
        registry = S3SkillsRegistry(bucket="skills", boto3_client=client)
        ```
    """

    def __init__(
        self,
        bucket: str,
        *,
        prefix: str = '',
        target_dir: str | Path | None = None,
        boto3_client: Any | None = None,
        auto_install: bool = True,
    ) -> None:
        if boto3_client is None:
            try:
                import boto3
            except ImportError as exc:
                raise ImportError(
                    'boto3 is required to build a default S3 client for S3SkillsRegistry. '
                    'Install it with: pip install pydantic-ai-skills[s3], or pass a pre-built '
                    'boto3_client.'
                ) from exc
            self._client = boto3.client('s3')
        else:
            self._client = boto3_client

        self._bucket = bucket
        self._prefix = prefix.strip('/')
        self._auto_install = auto_install
        self._tmp_dir: Any | None = None
        # Cache of the most recent object listing (Key -> LastModified), populated by _sync.
        self._object_modified: dict[str, datetime | None] = {}

        if target_dir is None:
            import tempfile

            self._tmp_dir = tempfile.TemporaryDirectory()
            self._target_dir = Path(self._tmp_dir.name)
        else:
            self._target_dir = Path(target_dir).expanduser().resolve()

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}('
            f'bucket={self._bucket!r}, '
            f'prefix={self._prefix!r}, '
            f'target_dir={str(self._target_dir)!r})'
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _skills_root(self) -> Path:
        """Return the path inside the cache where skill directories live."""
        if self._prefix:
            return self._target_dir / self._prefix
        return self._target_dir

    def _list_objects(self) -> list[dict[str, Any]]:
        """Return all object summaries under ``bucket/prefix`` via pagination."""
        list_prefix = f'{self._prefix}/' if self._prefix else ''
        try:
            paginator = self._client.get_paginator('list_objects_v2')
            objects: list[dict[str, Any]] = []
            for page in paginator.paginate(Bucket=self._bucket, Prefix=list_prefix):
                objects.extend(page.get('Contents', []))
            return objects
        except Exception as exc:  # surface any boto3/botocore error with context
            raise RuntimeError(
                f"Failed to list objects in bucket '{self._bucket}' (prefix '{self._prefix}'): {exc}"
            ) from exc

    def _sync(self) -> None:
        """Mirror all objects under ``bucket/prefix`` into ``target_dir``.

        Clears the cached prefix subtree first so skills removed from the bucket
        do not linger locally, then downloads the current objects. The listing is
        fetched once and cached for metadata enrichment.
        """
        objects = self._list_objects()
        self._object_modified = {obj['Key']: obj.get('LastModified') for obj in objects}

        # Mirror the remote: drop the previously synced subtree before re-downloading.
        skills_root = self._skills_root()
        if skills_root.exists():
            shutil.rmtree(skills_root)

        self._target_dir.mkdir(parents=True, exist_ok=True)
        target_resolved = self._target_dir.resolve()

        for obj in objects:
            key = obj['Key']
            if key.endswith('/'):
                # Directory marker — nothing to download.
                continue

            dest = self._target_dir / key
            # Path-traversal guard: the resolved destination must stay inside target_dir.
            if not dest.resolve().is_relative_to(target_resolved):
                raise ValueError(f"Object key '{key}' escapes target directory '{target_resolved}'.")

            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._client.download_file(self._bucket, key, str(dest))
            except Exception as exc:  # surface any boto3/botocore error with context
                raise RuntimeError(f"Failed to download '{key}' from bucket '{self._bucket}': {exc}") from exc

    def _latest_modified(self, skill_name: str) -> str | None:
        """Return the newest ``LastModified`` across one skill's objects, ISO-formatted.

        Reads the object listing cached by the most recent :meth:`sync`, so it performs no
        additional S3 calls.
        """
        key_prefix = f'{self._prefix}/{skill_name}/'.lstrip('/')
        latest: datetime | None = None
        for key, modified in self._object_modified.items():
            if key.startswith(key_prefix) and modified is not None and (latest is None or modified > latest):
                latest = modified
        return latest.isoformat() if latest is not None else None

    # ------------------------------------------------------------------
    # SkillRegistry interface
    # ------------------------------------------------------------------

    def sync(self) -> Path:
        """Download the bucket prefix and return its skill-library directory.

        The returned path is ``target_dir`` joined with ``prefix``, whose immediate
        children are the skill packages. With ``auto_install=False`` nothing is
        downloaded and whatever is already on disk is returned.

        Returns:
            Path to the local skill-library directory.

        Raises:
            RuntimeError: On S3 listing or download errors.
            ValueError: When the prefix holds no synced skill library — usually a
                ``prefix`` that does not match the bucket's layout, or
                ``auto_install=False`` with nothing downloaded yet.
        """
        if self._auto_install:
            self._sync()

        skills_root = self._skills_root()
        if not skills_root.is_dir():
            detail = (
                'nothing has been downloaded yet and auto_install is disabled'
                if not self._auto_install
                else f'prefix={self._prefix!r} matched no objects'
            )
            raise ValueError(f"No skill library at {skills_root} for bucket '{self._bucket}': {detail}.")
        return skills_root

    def revision(self, skill_name: str) -> str | None:
        """Return the newest object modification time for one skill, ISO-formatted.

        Useful for recording which version of a remote skill an agent ran with, since
        :meth:`sync` otherwise tracks a moving prefix. Returns None before the first sync
        or when the skill has no objects in the cached listing.
        """
        return self._latest_modified(skill_name)

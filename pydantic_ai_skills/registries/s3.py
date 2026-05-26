"""S3-backed skill registry using boto3.

Provides :class:`S3SkillsRegistry` for downloading skills from an Amazon S3
bucket (or any S3-compatible store such as MinIO, Ceph, or Cloudflare R2) and
exposing them to :class:`~pydantic_ai_skills.SkillsToolset`.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_ai_skills.directory import discover_skills
from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.types import Skill

__all__ = ['S3SkillsRegistry']


class S3SkillsRegistry(SkillRegistry):
    """Skills registry backed by an S3 bucket, downloaded with boto3.

    Lists and downloads every object under ``bucket/prefix`` into a local cache
    directory on the first call to ``search``/``get``/``install`` (or eagerly
    during ``__init__`` when ``auto_install=True``), then parses the synced tree
    with :func:`~pydantic_ai_skills.discover_skills`. Re-syncs on ``update``.

    Works with Amazon S3 and any S3-compatible store (MinIO, Ceph, Cloudflare R2,
    etc.). All connection details — credentials, ``endpoint_url``, region, TLS,
    and path-style addressing — are configured on the boto3 client you pass via
    ``boto3_client``. When omitted, a default ``boto3.client("s3")`` is built,
    which uses boto3's standard credential resolution chain.

    ``search()`` and ``get()`` return :class:`~pydantic_ai_skills.Skill` objects
    parsed from ``SKILL.md`` frontmatter + body. Registry-specific metadata
    (``source_url``, ``version``, ``bucket``, ``prefix``) is stored in
    ``skill.metadata``.

    Args:
        bucket: Name of the S3 bucket containing the skills.
        prefix: Key prefix inside the bucket where skill directories live.
            Defaults to the bucket root (``""``). For example, pass ``"skills"``
            when skills live at ``s3://bucket/skills/<skill>/``.
        target_dir: Local directory where objects are downloaded. Defaults to a
            temporary directory scoped to the registry instance. The synced tree
            persists across ``install`` / ``update`` calls but is **not** cleaned
            up automatically — callers own the lifecycle.
        boto3_client: A pre-built boto3 S3 client. Use this to configure
            credentials, ``endpoint_url`` (for MinIO/Ceph/R2), region, TLS, and
            path-style addressing. When ``None``, a default ``boto3.client("s3")``
            is created (requires the ``s3`` extra: ``pip install pydantic-ai-skills[s3]``).
        validate: Whether to run metadata validation on every discovered
            ``SKILL.md`` after syncing. Mirrors the homonymous flag on
            :class:`~pydantic_ai_skills.SkillsDirectory`. Defaults to ``True``.
        auto_install: When ``True`` (default), ``search`` and ``get`` trigger a
            sync automatically so the local copy is always up to date. Set to
            ``False`` to require explicit ``install`` / ``update`` calls, which is
            preferable in offline or air-gapped environments.

    Examples:
        Amazon S3 with the ambient credential chain:

        ```python
        from pydantic_ai_skills import SkillsToolset
        from pydantic_ai_skills.registries.s3 import S3SkillsRegistry

        toolset = SkillsToolset(
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
        validate: bool = True,
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
        self._validate = validate
        self._auto_install = auto_install
        self._tmp_dir: tempfile.TemporaryDirectory[str] | None = None

        if target_dir is None:
            self._tmp_dir = tempfile.TemporaryDirectory()
            self._target_dir = Path(self._tmp_dir.name)
        else:
            self._target_dir = Path(target_dir).expanduser().resolve()

        self._cached_skills: list[Skill] = []
        if self._auto_install:
            self._sync()
            self._cached_skills = [self._enrich_metadata(s) for s in self._load_skills()]

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
        paginator = self._client.get_paginator('list_objects_v2')
        objects: list[dict[str, Any]] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=list_prefix):
            objects.extend(page.get('Contents', []))
        return objects

    def _sync(self) -> None:
        """Download all objects under ``bucket/prefix`` into ``target_dir``."""
        self._target_dir.mkdir(parents=True, exist_ok=True)
        target_resolved = self._target_dir.resolve()

        for obj in self._list_objects():
            key = obj['Key']
            if key.endswith('/'):
                # Directory marker — nothing to download.
                continue

            dest = self._target_dir / key
            # Path-traversal guard: the resolved destination must stay inside target_dir.
            if not dest.resolve().is_relative_to(target_resolved):
                raise ValueError(f"Object key '{key}' escapes target directory '{target_resolved}'.")

            dest.parent.mkdir(parents=True, exist_ok=True)
            self._client.download_file(self._bucket, key, str(dest))

    def _ensure_synced(self) -> None:
        """Sync the cache when ``auto_install`` is enabled; otherwise trust on-disk state."""
        if self._auto_install:
            self._sync()

    def _load_skills(self) -> list[Skill]:
        """Discover all skills from the synced cache path."""
        skills_root = self._skills_root()
        if not skills_root.exists():
            return []
        return discover_skills(path=skills_root, validate=self._validate, max_depth=2)

    def _skill_version(self, skill: Skill) -> str | None:
        """Return the latest LastModified across the skill's objects, ISO-formatted."""
        if not skill.uri:
            return None
        try:
            skill_dir = Path(skill.uri).resolve().relative_to(self._target_dir.resolve())
        except ValueError:
            return None
        key_prefix = f'{skill_dir.as_posix()}/'
        latest: datetime | None = None
        for obj in self._list_objects():
            if obj['Key'].startswith(key_prefix):
                modified = obj.get('LastModified')
                if modified is not None and (latest is None or modified > latest):
                    latest = modified
        return latest.isoformat() if latest is not None else None

    def _enrich_metadata(self, skill: Skill) -> Skill:
        """Inject registry-specific keys into ``skill.metadata``."""
        skill_path = f'{self._prefix}/{skill.name}'.strip('/')
        extra: dict[str, Any] = {
            'source_url': f's3://{self._bucket}/{skill_path}',
            'registry': type(self).__name__,
            'bucket': self._bucket,
            'prefix': self._prefix,
            'version': self._skill_version(skill),
        }
        existing = dict(skill.metadata) if skill.metadata else {}
        existing.update(extra)
        return replace(skill, metadata=existing)

    def _ensure_skills_loaded(self) -> None:
        """Populate the skills cache if empty, respecting ``auto_install``."""
        if self._cached_skills:
            return
        if self._auto_install:
            self._sync()
        self._cached_skills = [self._enrich_metadata(s) for s in self._load_skills()]

    # ------------------------------------------------------------------
    # Synchronous skill access for SkillsToolset integration
    # ------------------------------------------------------------------

    def get_skills(self) -> list[Skill]:
        """Return all skills discovered from the bucket.

        Returns:
            List of enriched :class:`~pydantic_ai_skills.Skill` objects.
        """
        self._ensure_skills_loaded()
        return list(self._cached_skills)

    # ------------------------------------------------------------------
    # SkillRegistry interface
    # ------------------------------------------------------------------

    async def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Search available skills by keyword.

        Matches ``query`` (case-insensitively) against each skill's ``name`` and
        ``description``.

        Args:
            query: Keyword to search for.
            limit: Maximum number of results.

        Returns:
            List of matching :class:`~pydantic_ai_skills.Skill` objects.
        """
        q = query.lower()
        results: list[Skill] = []
        for skill in self.get_skills():
            if q in skill.name.lower() or q in (skill.description or '').lower():
                results.append(skill)
                if len(results) >= limit:
                    break
        return results

    async def get(self, skill_name: str) -> Skill:
        """Return the full skill by name.

        Args:
            skill_name: Exact skill name.

        Returns:
            A fully-parsed :class:`~pydantic_ai_skills.Skill`.

        Raises:
            KeyError: When no skill with ``skill_name`` exists.
        """
        for skill in self.get_skills():
            if skill.name == skill_name:
                return skill
        raise KeyError(f"Skill '{skill_name}' not found in bucket '{self._bucket}'.")

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Copy a skill from the synced cache into ``target_dir``.

        Args:
            skill_name: Name of the skill to install.
            target_dir: Destination directory; a ``skill_name`` subdirectory is
                created inside it.

        Returns:
            Path to the installed skill directory (``target_dir/skill_name``).

        Raises:
            KeyError: When ``skill_name`` is not found in the registry.
            ValueError: When the destination or source path escapes its expected
                directory (path traversal protection).
        """
        self._ensure_skills_loaded()

        src_skill_dir: Path | None = None
        for skill in self._cached_skills:
            if skill.name == skill_name and skill.uri:
                src_skill_dir = Path(skill.uri)
                break

        if src_skill_dir is None:
            raise KeyError(f"Skill '{skill_name}' not found in bucket '{self._bucket}'.")

        dest_root = Path(target_dir).expanduser().resolve()
        dest_root.mkdir(parents=True, exist_ok=True)
        dest_skill_dir = dest_root / skill_name

        if not dest_skill_dir.resolve().is_relative_to(dest_root):
            raise ValueError(f"Destination path '{dest_skill_dir}' escapes target directory '{dest_root}'.")

        src_resolved = src_skill_dir.resolve()
        for src_file in src_resolved.rglob('*'):
            if src_file.is_symlink() or src_file.is_file():
                try:
                    src_file.resolve().relative_to(src_resolved)
                except ValueError as exc:
                    raise ValueError(
                        f"Source path '{src_file}' escapes skill directory (path traversal detected)."
                    ) from exc

        if dest_skill_dir.exists():
            shutil.rmtree(dest_skill_dir)
        shutil.copytree(src_resolved, dest_skill_dir)

        return dest_skill_dir

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Re-sync from S3 and re-copy the skill to ``target_dir``.

        Performs a fresh sync of the cache before re-installing. Falls back to a
        plain ``install`` if the skill is not yet installed.

        Args:
            skill_name: Name of the skill to update.
            target_dir: Directory where the skill was previously installed.

        Returns:
            Path to the updated skill directory.

        Raises:
            KeyError: When ``skill_name`` is not found after the sync.
        """
        dest = Path(target_dir).expanduser().resolve() / skill_name
        if not dest.exists():
            return await self.install(skill_name, target_dir)

        self._sync()
        self._cached_skills = [self._enrich_metadata(s) for s in self._load_skills()]
        return await self.install(skill_name, target_dir)

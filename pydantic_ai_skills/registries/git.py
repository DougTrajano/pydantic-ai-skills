"""Git-backed skill registry using GitPython.

Provides :class:`GitSkillsRegistry` and :class:`GitCloneOptions` for cloning
a remote Git repository and exposing its skills to :class:`~pydantic_ai_skills.SkillsToolset`.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from pydantic_ai_skills.directory import discover_skills
from pydantic_ai_skills.exceptions import SkillNotFoundError, SkillRegistryError
from pydantic_ai_skills.registries._base import SkillRegistry
from pydantic_ai_skills.types import Skill

__all__ = ['GitCloneOptions', 'GitSkillsRegistry']


@dataclass
class GitCloneOptions:
    """Low-level GitPython configuration for clone and fetch operations.

    All fields map directly to arguments accepted by ``git.Repo.clone_from`` or
    ``git.Remote.fetch`` / ``git.Remote.pull``, so developers who know GitPython can
    use the full API without any wrapper layer.

    Args:
        depth: Create a shallow clone with history truncated to this many commits.
            Passed as ``--depth`` to git. ``None`` means a full clone.
            Useful for large repositories where only the latest snapshot is needed.
        branch: Name of the remote branch, tag, or ref to check out after cloning
            (``--branch`` flag). Defaults to the repository's default branch when
            ``None``.
        single_branch: When ``True``, clone only the branch specified by ``branch``
            (``--single-branch``). Has no effect when ``branch`` is ``None``.
        sparse_paths: List of path patterns to include in a sparse checkout
            (``--sparse`` + ``git sparse-checkout set``). An empty list disables
            sparse checkout and fetches the full tree.
        env: Mapping of environment variables forwarded to every git sub-process
            (e.g. ``GIT_SSH_COMMAND``, ``GIT_ASKPASS``). These override the
            process environment for git calls only.
        multi_options: Extra ``--option`` strings passed verbatim to
            ``git.Repo.clone_from(multi_options=...)``. Use for git options not
            exposed by other fields (e.g. ``['--filter=blob:none']`` for a
            partial/blobless clone).
        git_options: Mapping forwarded as keyword arguments directly to
            ``git.Repo.clone_from`` or ``repo.remotes.origin.pull``. This is the
            escape hatch for any GitPython kwarg not covered above
            (e.g. ``{'allow_unsafe_protocols': True}``).
    """

    depth: int | None = None
    branch: str | None = None
    single_branch: bool = False
    sparse_paths: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    multi_options: list[str] = field(default_factory=list)
    git_options: dict[str, Any] = field(default_factory=dict)


def _inject_token_into_url(repo_url: str, token: str) -> str:
    """Embed a PAT into an HTTPS URL for authentication.

    Args:
        repo_url: The original repository URL.
        token: Personal access token or password.

    Returns:
        URL with the token embedded as the password component.
    """
    parsed = urlparse(repo_url)
    if parsed.scheme in ('http', 'https'):
        netloc = f'oauth2:{token}@{parsed.hostname}'
        if parsed.port:
            netloc = f'{netloc}:{parsed.port}'
        return urlunparse(parsed._replace(netloc=netloc))
    return repo_url


def _sanitize_url(repo_url: str) -> str:
    """Return the URL with credentials redacted.

    Args:
        repo_url: A URL possibly containing a token in the netloc.

    Returns:
        URL with password replaced by ``***``.
    """
    parsed = urlparse(repo_url)
    if parsed.password:
        netloc = f'{parsed.hostname}'
        if parsed.port:
            netloc = f'{netloc}:{parsed.port}'
        return urlunparse(parsed._replace(netloc=netloc))
    return repo_url


def _sanitize_error_message(exc: Exception, clone_url: str, clean_url: str) -> str:
    """Redact credentials from a git error message.

    ``GitCommandError`` often includes the full command line (with the
    token-bearing URL).  Replace the authenticated clone URL with the
    previously sanitized one so secrets never leak into logs or
    tracebacks.

    Args:
        exc: The caught exception.
        clone_url: The URL that may contain embedded credentials.
        clean_url: The sanitized (credential-free) URL.

    Returns:
        Sanitized string representation of the exception.
    """
    return str(exc).replace(clone_url, clean_url)


def _build_source_url(repo_url: str, path: str, skill_name: str, branch: str | None) -> str:
    """Construct a browsable URL to the skill directory.

    For GitHub/GitLab, builds a ``/tree/<ref>/`` URL. Falls back to the repo URL.

    Args:
        repo_url: Repository URL (no token).
        path: Sub-path inside the repo.
        skill_name: Skill directory name.
        branch: Branch/commit ref.

    Returns:
        Human-readable URL for the skill directory.
    """
    ref = branch or 'main'
    skill_path = f'{path}/{skill_name}'.strip('/')
    clean_url = repo_url.rstrip('/')
    if clean_url.endswith('.git'):
        clean_url = clean_url[:-4]
    return f'{clean_url}/tree/{ref}/{skill_path}'


class GitSkillsRegistry(SkillRegistry):
    """Skills registry backed by a Git repository cloned with GitPython.

    Clones the target repository on the first call to ``install`` or
    ``search``/``get``, then performs a ``git pull`` on subsequent calls
    (or a full re-clone if the local copy is corrupted/missing).

    The registry only reads the filesystem after cloning — it never calls any
    hosting platform's REST/GraphQL API — so it works with any git host
    accessible over HTTPS or SSH (GitHub, GitLab, Bitbucket, self-hosted, etc.).

    ``search()`` and ``get()`` return :class:`~pydantic_ai_skills.Skill` objects
    parsed from ``SKILL.md`` frontmatter + body. Registry-specific metadata
    (``source_url``, ``version``, ``repo``) is stored in ``skill.metadata``.

    Args:
        repo_url: Full URL of the Git repository to clone (e.g.
            ``"https://github.com/anthropics/skills"``). Works with any Git host
            accessible over HTTPS or SSH (GitHub, GitLab, Bitbucket,
            self-hosted, etc.).
        target_dir: Local directory where the repository is cloned. Defaults to
            a temporary directory scoped to the registry instance. The cloned
            tree persists across ``install`` / ``update`` calls but is **not**
            cleaned up automatically — callers own the lifecycle.
        path: Sub-path inside the repository that contains the skill directories.
            Defaults to the repository root (``""``). For example, pass
            ``"skills"`` when skills live at ``owner/name/skills/<skill>/``.
        token: Personal access token (or any HTTPS password) used for
            authentication. When ``None`` the registry falls back to the
            ``GITHUB_TOKEN`` environment variable. Anonymous access is used when
            neither is set (rate-limited for public repos, fails for private ones).
        ssh_key_file: Path to a private SSH key for SSH-based authentication.
            When provided, ``GIT_SSH_COMMAND`` is injected into
            ``clone_options.env``.
        clone_options: Fine-grained GitPython configuration. See
            :class:`GitCloneOptions` for the full list of knobs. Any value set
            here is forwarded verbatim to ``git.Repo.clone_from`` /
            ``repo.remotes.origin.pull``.
        validate: Whether to run ``validate_skill_metadata()`` on every
            discovered ``SKILL.md`` after installation. Mirrors the homonymous
            flag on :class:`~pydantic_ai_skills.SkillsDirectory`. Defaults to ``True``.
        auto_install: When ``True`` (default), ``search`` and ``get`` trigger a
            clone/pull automatically so the local copy is always up to date.
            Set to ``False`` to require explicit ``install`` / ``update`` calls,
            which is preferable in offline or air-gapped environments.

    Examples:
        Basic usage — clone and register all skills:

        ```python
        from pydantic_ai_skills import SkillsToolset
        from pydantic_ai_skills.registries.git import GitSkillsRegistry

        toolset = SkillsToolset(
            registries=[
                GitSkillsRegistry(
                    repo_url="https://github.com/anthropics/skills",
                    path="skills",
                    target_dir="./cached-skills",
                ),
            ]
        )
        ```

        Blobless shallow clone with a PAT, only the ``pdf`` sub-path:

        ```python
        from pydantic_ai_skills.registries.git import GitSkillsRegistry, GitCloneOptions

        registry = GitSkillsRegistry(
            repo_url="https://github.com/anthropics/skills",
            path="skills/pdf",
            token="ghp_...",
            clone_options=GitCloneOptions(
                depth=1,
                single_branch=True,
                sparse_paths=["skills/pdf"],
                multi_options=["--filter=blob:none"],
            ),
        )
        ```

        Filter to only PDF-related skills:

        ```python
        pdf_registry = registry.filtered(lambda skill: "pdf" in skill.name.lower())
        ```

        Prefix all skill names from this registry:

        ```python
        prefixed_registry = registry.prefixed("anthropic-")
        # "pdf" skill is now accessible as "anthropic-pdf"
        ```

        SSH authentication with a custom key:

        ```python
        registry = GitSkillsRegistry(
            repo_url="git@github.com:my-org/private-skills.git",
            ssh_key_file="~/.ssh/id_ed25519_skills",
        )
        ```

        Offline / air-gapped — pre-clone manually, disable auto-install:

        ```python
        registry = GitSkillsRegistry(
            repo_url="https://github.com/anthropics/skills",
            target_dir="/opt/skills-mirror",
            auto_install=False,
        )
        ```
    """

    def __init__(
        self,
        repo_url: str,
        *,
        target_dir: str | Path | None = None,
        path: str = '',
        token: str | None = None,
        ssh_key_file: str | Path | None = None,
        clone_options: GitCloneOptions | None = None,
        validate: bool = True,
        auto_install: bool = True,
    ) -> None:
        try:
            import git as _git  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                'GitPython is required for GitSkillsRegistry. Install it with: pip install pydantic-ai-skills[git]'
            ) from exc

        self._repo_url = repo_url
        self._path = path.strip('/')
        self._validate = validate
        self._auto_install = auto_install
        self._clone_options = clone_options or GitCloneOptions()
        self._tmp_dir: tempfile.TemporaryDirectory[str] | None = None

        # Resolve effective token (explicit arg beats env var)
        effective_token = token or os.environ.get('GITHUB_TOKEN')
        self._token: str | None = effective_token  # kept private for masking

        # Build the URL used for cloning (with token embedded if available)
        if effective_token:
            self._clone_url = _inject_token_into_url(repo_url, effective_token)
        else:
            self._clone_url = repo_url

        # Resolve target directory
        if target_dir is None:
            self._tmp_dir = tempfile.TemporaryDirectory()
            self._target_dir = Path(self._tmp_dir.name)
        else:
            self._target_dir = Path(target_dir).expanduser().resolve()

        # SSH key handling
        if ssh_key_file is not None:
            key_path = Path(ssh_key_file).expanduser().resolve()
            # Warn if permissions are wider than 0o600
            try:
                key_stat = key_path.stat()
                if key_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                    warnings.warn(
                        f"SSH key file '{key_path}' has permissions wider than 0o600. "
                        'Consider restricting with: chmod 600 '
                        f'{key_path}',
                        UserWarning,
                        stacklevel=2,
                    )
            except OSError:
                pass
            self._clone_options.env['GIT_SSH_COMMAND'] = f'ssh -i {key_path} -o StrictHostKeyChecking=no'

        # Clean repo URL (no credentials) for display and metadata
        self._clean_repo_url = _sanitize_url(repo_url)

        # Eagerly clone/pull and cache discovered skills
        self._cached_skills: list[Skill] = []
        if self._auto_install:
            self._ensure_cloned()
            self._cached_skills = [self._enrich_metadata(s) for s in self._load_skills()]

    # ------------------------------------------------------------------
    # repr — never expose the token
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}('
            f'repo_url={self._clean_repo_url!r}, '
            f'path={self._path!r}, '
            f'target_dir={str(self._target_dir)!r})'
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _skills_root(self) -> Path:
        """Return the path inside the clone where skill directories live."""
        if self._path:
            return self._target_dir / self._path
        return self._target_dir

    def _is_cloned(self) -> bool:
        """Return True if a valid git repository already exists in the target dir."""
        import git

        if not self._target_dir.exists():
            return False
        try:
            git.Repo(str(self._target_dir))
            return True
        except git.exc.InvalidGitRepositoryError:
            return False

    def _clone(self) -> None:
        """Clone the repository into the target directory."""
        import git

        opts = self._clone_options
        clone_kwargs: dict[str, Any] = {}

        if opts.depth is not None:
            clone_kwargs['depth'] = opts.depth
        if opts.branch is not None:
            clone_kwargs['branch'] = opts.branch
        if opts.single_branch:
            clone_kwargs['single_branch'] = True
        if opts.multi_options:
            clone_kwargs['multi_options'] = opts.multi_options
        if opts.env:
            clone_kwargs['env'] = opts.env

        clone_kwargs.update(opts.git_options)

        self._target_dir.mkdir(parents=True, exist_ok=True)

        try:
            repo = git.Repo.clone_from(
                self._clone_url,
                str(self._target_dir),
                **clone_kwargs,
            )
        except git.exc.GitCommandError as exc:
            sanitized = _sanitize_error_message(exc, self._clone_url, self._clean_repo_url)
            raise SkillRegistryError(f'Failed to clone repository {self._clean_repo_url!r}: {sanitized}') from exc

        # Apply sparse checkout if requested
        if opts.sparse_paths:
            try:
                repo.git.sparse_checkout('init')
                repo.git.sparse_checkout('set', *opts.sparse_paths)
            except git.exc.GitCommandError as exc:
                sanitized = _sanitize_error_message(exc, self._clone_url, self._clean_repo_url)
                raise SkillRegistryError(f'Failed to configure sparse checkout: {sanitized}') from exc

    def _pull(self) -> None:
        """Perform ``git pull`` on the existing clone."""
        import git

        pull_kwargs: dict[str, Any] = {}
        if self._clone_options.env:
            pull_kwargs['env'] = self._clone_options.env
        pull_kwargs.update(self._clone_options.git_options)

        try:
            repo = git.Repo(str(self._target_dir))
            repo.remotes.origin.pull(**pull_kwargs)
        except git.exc.InvalidGitRepositoryError:
            # Clone is corrupted or missing — start fresh
            shutil.rmtree(str(self._target_dir), ignore_errors=True)
            self._clone()
        except git.exc.GitCommandError as exc:
            sanitized = _sanitize_error_message(exc, self._clone_url, self._clean_repo_url)
            raise SkillRegistryError(
                f'Failed to pull latest changes from {self._clean_repo_url!r}: {sanitized}'
            ) from exc

    def _ensure_cloned(self) -> None:
        """Clone or pull the repository to ensure the local cache is up to date."""
        if self._is_cloned():
            self._pull()
        else:
            self._clone()

    def _get_commit_sha(self) -> str | None:
        """Return the current HEAD commit SHA, or None on failure."""
        import git

        try:
            repo = git.Repo(str(self._target_dir))
            return repo.head.commit.hexsha
        except (OSError, ValueError, git.exc.InvalidGitRepositoryError, git.exc.GitCommandError):
            return None

    def _load_skills(self) -> list[Skill]:
        """Discover all skills from the cloned repository path."""
        skills_root = self._skills_root()
        if not skills_root.exists():
            return []
        return discover_skills(path=skills_root, validate=self._validate, max_depth=2)

    def _enrich_metadata(self, skill: Skill, *, version: str | None = None) -> Skill:
        """Inject registry-specific keys into ``skill.metadata``."""
        from dataclasses import replace

        extra: dict[str, Any] = {
            'source_url': _build_source_url(
                self._clean_repo_url,
                self._path,
                skill.name,
                self._clone_options.branch,
            ),
            'registry': type(self).__name__,
            'repo': self._clean_repo_url,
            'version': version or self._get_commit_sha(),
        }
        existing = dict(skill.metadata) if skill.metadata else {}
        existing.update(extra)
        return replace(skill, metadata=existing)

    def _refresh(self) -> None:
        """Pull latest changes and rebuild the skills cache."""
        self._ensure_cloned()
        self._cached_skills = [self._enrich_metadata(s) for s in self._load_skills()]

    def _ensure_skills_loaded(self) -> None:
        """Populate the skills cache if empty, respecting ``auto_install``."""
        if self._cached_skills:
            return
        if self._auto_install:
            self._ensure_cloned()
        self._cached_skills = [self._enrich_metadata(s) for s in self._load_skills()]

    # ------------------------------------------------------------------
    # Synchronous skill access for SkillsToolset integration
    # ------------------------------------------------------------------

    def get_skills(self) -> list[Skill]:
        """Return all skills discovered from the cloned repository.

        If ``auto_install=True`` (default), the repository was cloned during
        ``__init__`` and skills are returned from cache. Otherwise, loads
        from whatever exists on disk without triggering a clone/pull.

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
        ``description``. Uses the cached skill list populated during ``__init__``.

        Args:
            query: Keyword to search for.
            limit: Maximum number of results.

        Returns:
            List of :class:`~pydantic_ai_skills.Skill` objects. Each skill's
            ``metadata`` dict contains ``"source_url"`` for traceability.
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
            skill_name: Exact skill name (with optional prefix).

        Returns:
            A fully-parsed :class:`~pydantic_ai_skills.Skill` with ``metadata``
            containing ``"source_url"``.

        Raises:
            SkillNotFoundError: When no skill with ``skill_name`` exists.
        """
        for skill in self.get_skills():
            if skill.name == skill_name:
                return skill
        raise SkillNotFoundError(f"Skill '{skill_name}' not found in registry {self._clean_repo_url!r}.")

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """Copy a skill from the cloned repository into ``target_dir``.

        Clones the repository first if the local cache doesn't exist. Validation
        is handled by ``discover_skills()`` during cache population, so skills
        in the cache are already validated.

        Args:
            skill_name: Name of the skill to install.
            target_dir: Destination directory; a ``skill_name`` subdirectory
                is created inside it.

        Returns:
            Path to the installed skill directory (``target_dir/skill_name``).

        Raises:
            SkillNotFoundError: When ``skill_name`` is not found in the registry.
            SkillRegistryError: On git or filesystem errors.
        """
        # Ensure we have skills loaded (already parsed and validated by discover_skills)
        self._ensure_skills_loaded()

        # Find skill in cache — its uri points to the source directory
        src_skill_dir: Path | None = None
        for skill in self._cached_skills:
            if skill.name == skill_name and skill.uri:
                src_skill_dir = Path(skill.uri)
                break

        if src_skill_dir is None:
            raise SkillNotFoundError(f"Skill '{skill_name}' not found in repository {self._clean_repo_url!r}.")

        dest_root = Path(target_dir).expanduser().resolve()
        dest_root.mkdir(parents=True, exist_ok=True)
        dest_skill_dir = dest_root / skill_name

        # Path traversal check on destination
        if not dest_skill_dir.resolve().is_relative_to(dest_root):
            raise SkillRegistryError(f"Destination path '{dest_skill_dir}' escapes target directory '{dest_root}'.")

        # Validate no source symlinks escape the skill directory
        src_resolved = src_skill_dir.resolve()
        for src_file in src_resolved.rglob('*'):
            if src_file.is_symlink() or src_file.is_file():
                try:
                    src_file.resolve().relative_to(src_resolved)
                except ValueError as exc:
                    raise SkillRegistryError(
                        f"Source path '{src_file}' escapes skill directory (path traversal detected)."
                    ) from exc

        # Copy the skill directory
        if dest_skill_dir.exists():
            shutil.rmtree(dest_skill_dir)
        shutil.copytree(src_resolved, dest_skill_dir)

        return dest_skill_dir

    async def update(self, skill_name: str, target_dir: str | Path) -> Path:
        """Pull the latest changes and re-copy the skill to ``target_dir``.

        Performs a ``git pull`` on the cached clone before re-installing.
        Falls back to a fresh ``install`` if the skill is not yet installed.

        Args:
            skill_name: Name of the skill to update.
            target_dir: Directory where the skill was previously installed.

        Returns:
            Path to the updated skill directory.

        Raises:
            SkillNotFoundError: When ``skill_name`` is not found after the pull.
            SkillRegistryError: On git or network errors.
        """
        dest = Path(target_dir).expanduser().resolve() / skill_name
        if not dest.exists():
            return await self.install(skill_name, target_dir)

        # Pull latest and refresh cache before reinstalling
        self._ensure_cloned()
        self._cached_skills = [self._enrich_metadata(s) for s in self._load_skills()]
        return await self.install(skill_name, target_dir)

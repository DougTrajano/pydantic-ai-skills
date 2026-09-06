"""Git-backed skill registry using GitPython.

Provides :class:`GitSkillsRegistry` and :class:`GitCloneOptions` for cloning a remote Git
repository and handing its skill library to
:class:`~pydantic_ai_skills.SkillsCapability`.
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

from pydantic_ai_skills.registries._base import SkillRegistry

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


class GitSkillsRegistry(SkillRegistry):
    """Skills registry backed by a Git repository cloned with GitPython.

    :meth:`sync` clones the repository on first call and performs a ``git pull`` on
    subsequent ones (or a full re-clone if the local copy is corrupted or missing), then
    returns the directory holding the skill packages.

    The registry only reads the filesystem after cloning — it never calls any
    hosting platform's REST/GraphQL API — so it works with any git host
    accessible over HTTPS or SSH (GitHub, GitLab, Bitbucket, self-hosted, etc.).

    It does not parse ``SKILL.md``: the directory it produces is handed to
    :class:`~pydantic_ai_skills.SkillsCapability`, and validating and rendering the
    packages inside it is `pydantic-ai-harness`'s job.

    Args:
        repo_url: Full URL of the Git repository to clone (e.g.
            ``"https://github.com/anthropics/skills"``). Works with any Git host
            accessible over HTTPS or SSH (GitHub, GitLab, Bitbucket,
            self-hosted, etc.).
        target_dir: Local directory where the repository is cloned. Defaults to
            a temporary directory scoped to the registry instance. A directory you
            pass persists across :meth:`sync` calls and is **not** cleaned up
            automatically — callers own the lifecycle.
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
        auto_install: When ``True`` (default), :meth:`sync` clones or pulls so the local
            copy is up to date. Set to ``False`` to read only what is already on disk,
            which is what offline or air-gapped environments want.

    Examples:
        Basic usage — clone a repository and expose all its skills:

        ```python
        from pydantic_ai_skills import GitSkillsRegistry, SkillsCapability

        capability = SkillsCapability(
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
        pdf_registry = registry.filtered(lambda info: "pdf" in info.name)
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

        Offline / air-gapped — pre-clone manually, disable auto-install so
        :meth:`sync` never reaches the network:

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
            # Use accept-new to avoid disabling host key checking entirely while still
            # allowing non-interactive first-time connections.
            self._clone_options.env['GIT_SSH_COMMAND'] = f'ssh -i {key_path} -o StrictHostKeyChecking=accept-new'

        # Clean repo URL (no credentials) for display and errors
        self._clean_repo_url = _sanitize_url(repo_url)

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
            raise RuntimeError(f'Failed to clone repository {self._clean_repo_url!r}: {sanitized}') from exc

        # Apply sparse checkout if requested
        if opts.sparse_paths:
            try:
                repo.git.sparse_checkout('init')
                repo.git.sparse_checkout('set', *opts.sparse_paths)
            except git.exc.GitCommandError as exc:
                sanitized = _sanitize_error_message(exc, self._clone_url, self._clean_repo_url)
                raise RuntimeError(f'Failed to configure sparse checkout: {sanitized}') from exc

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
            raise RuntimeError(f'Failed to pull latest changes from {self._clean_repo_url!r}: {sanitized}') from exc

    def _ensure_cloned(self) -> None:
        """Clone or pull the repository to ensure the local cache is up to date."""
        if self._is_cloned():
            self._pull()
        else:
            self._clone()

    def _revision(self) -> str | None:
        """Return the current HEAD commit SHA, or None on failure."""
        import git

        try:
            repo = git.Repo(str(self._target_dir))
            return repo.head.commit.hexsha
        except (OSError, ValueError, git.exc.InvalidGitRepositoryError, git.exc.GitCommandError):
            return None

    # ------------------------------------------------------------------
    # SkillRegistry interface
    # ------------------------------------------------------------------

    def sync(self) -> Path:
        """Clone or pull the repository and return its skill-library directory.

        The returned path is ``target_dir`` joined with ``path``, whose immediate children
        are the skill packages. With ``auto_install=False`` nothing is fetched and
        whatever is already on disk is returned, which is what an air-gapped deployment
        wants.

        Returns:
            Path to the local skill-library directory.

        Raises:
            RuntimeError: On git or network errors.
            ValueError: When the configured ``path`` does not exist in the clone -- the
                usual cause is a ``path`` that does not match the repository's layout.
        """
        if self._auto_install:
            self._ensure_cloned()

        skills_root = self._skills_root()
        if not skills_root.is_dir():
            # Distinguish the two causes: a clone that never happened, versus a clone that
            # did but has no such sub-path. Reporting the first for both would send a
            # caller with a mistyped `path` looking for a network problem.
            if not self._target_dir.is_dir():
                detail = 'the repository has not been cloned yet and auto_install is disabled'
            else:
                detail = f'path={self._path!r} does not exist in the repository'
            raise ValueError(f'No skill library at {skills_root} for {self._clean_repo_url!r}: {detail}.')
        return skills_root

    def revision(self) -> str | None:
        """Return the commit SHA the local clone is on, or None if it is not cloned.

        Useful for recording exactly which version of a remote skill library an agent ran
        with, since :meth:`sync` otherwise tracks a moving branch.
        """
        return self._revision()

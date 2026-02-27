"""Tests for GitSkillsRegistry."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pydantic_ai_skills.exceptions import SkillNotFoundError, SkillRegistryError
from pydantic_ai_skills.registries.git import GitCloneOptions, GitSkillsRegistry

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _write_skill(base: Path, name: str, description: str = 'A test skill.') -> Path:
    """Write a minimal skill directory inside *base*."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nInstructions here.\n',
        encoding='utf-8',
    )
    return skill_dir


@pytest.fixture()
def fake_clone(tmp_path: Path) -> Path:
    """Return a subdirectory of *tmp_path* that looks like a cloned repo with two skills."""
    clone_dir = tmp_path / 'clone'
    clone_dir.mkdir()
    _write_skill(clone_dir, 'pdf', 'PDF manipulation skill.')
    _write_skill(clone_dir, 'xlsx', 'Excel spreadsheet skill.')
    return clone_dir


def _make_registry(
    fake_clone_path: Path,
    *,
    path: str = '',
    token: str | None = None,
    validate: bool = True,
    auto_install: bool = False,
    clone_options: GitCloneOptions | None = None,
) -> GitSkillsRegistry:
    """Create a GitSkillsRegistry pointing at a pre-existing fake clone."""
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=fake_clone_path,
        path=path,
        token=token,
        validate=validate,
        auto_install=auto_install,
        clone_options=clone_options,
    )
    return registry


# ---------------------------------------------------------------------------
# GitCloneOptions
# ---------------------------------------------------------------------------


def test_git_clone_options_defaults() -> None:
    """Test that GitCloneOptions has the expected default field values."""
    opts = GitCloneOptions()
    assert opts.depth is None
    assert opts.branch is None
    assert opts.single_branch is False
    assert opts.sparse_paths == []
    assert opts.env == {}
    assert opts.multi_options == []
    assert opts.git_options == {}


def test_git_clone_options_custom() -> None:
    """Test that GitCloneOptions accepts custom field values."""
    opts = GitCloneOptions(depth=1, branch='main', single_branch=True)
    assert opts.depth == 1
    assert opts.branch == 'main'
    assert opts.single_branch is True


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------


def test_import_error_when_gitpython_missing() -> None:
    """Instantiating GitSkillsRegistry without gitpython raises ImportError."""
    with patch.dict('sys.modules', {'git': None}):
        with pytest.raises(ImportError, match='pip install pydantic-ai-skills\\[git\\]'):
            GitSkillsRegistry(repo_url='https://github.com/example/skills')


# ---------------------------------------------------------------------------
# repr / str — token masking
# ---------------------------------------------------------------------------


def test_repr_does_not_expose_token(fake_clone: Path) -> None:
    """Verify that the token does not appear in __repr__."""
    registry = _make_registry(fake_clone, token='super-secret-token')
    result = repr(registry)
    assert 'super-secret-token' not in result
    assert 'https://github.com/example/skills' in result


def test_str_does_not_expose_token(fake_clone: Path) -> None:
    """Verify that the token does not appear in __str__."""
    registry = _make_registry(fake_clone, token='my-pat')
    assert 'my-pat' not in str(registry)


# ---------------------------------------------------------------------------
# Token URL injection
# ---------------------------------------------------------------------------


def test_token_embedded_in_clone_url(fake_clone: Path) -> None:
    """Explicit token is embedded into the internal clone URL."""
    registry = _make_registry(fake_clone, token='ghp_abc123')
    assert 'ghp_abc123' in registry._clone_url
    # Clean URL should not contain the token
    assert 'ghp_abc123' not in registry._clean_repo_url


def test_github_token_env_variable_fallback(fake_clone: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GITHUB_TOKEN env var is used when no explicit token is provided."""
    monkeypatch.setenv('GITHUB_TOKEN', 'env-token-xyz')
    registry = _make_registry(fake_clone)
    assert 'env-token-xyz' in registry._clone_url


# ---------------------------------------------------------------------------
# SSH key injection and permissions warning
# ---------------------------------------------------------------------------


def test_ssh_key_injects_git_ssh_command(tmp_path: Path, fake_clone: Path) -> None:
    """Providing ssh_key_file sets GIT_SSH_COMMAND in clone_options.env."""
    key_file = tmp_path / 'id_ed25519'
    key_file.write_text('FAKE KEY')
    key_file.chmod(0o600)

    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=fake_clone,
        ssh_key_file=key_file,
        auto_install=False,
    )
    assert 'GIT_SSH_COMMAND' in registry._clone_options.env
    assert str(key_file.resolve()) in registry._clone_options.env['GIT_SSH_COMMAND']


def test_ssh_key_wide_permissions_warning(tmp_path: Path, fake_clone: Path) -> None:
    """SSH key file with permissions wider than 0o600 triggers a UserWarning."""
    key_file = tmp_path / 'id_rsa'
    key_file.write_text('FAKE KEY')
    key_file.chmod(0o644)  # too permissive

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        GitSkillsRegistry(
            repo_url='https://github.com/example/skills',
            target_dir=fake_clone,
            ssh_key_file=key_file,
            auto_install=False,
        )

    messages = [str(warning.message) for warning in w]
    assert any('wider than 0o600' in m for m in messages)


# ---------------------------------------------------------------------------
# Clone / pull behaviour — mocked
# ---------------------------------------------------------------------------


def test_clone_called_when_not_cloned(tmp_path: Path) -> None:
    """clone_from is called when no repo exists yet."""
    clone_dir = tmp_path / 'clone'

    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'abc123'

    # clone_dir does not exist yet, so _is_cloned() short-circuits to False
    # without calling git.Repo().  Only clone_from needs to be patched.
    with patch('git.Repo.clone_from', return_value=mock_repo) as mock_clone:
        registry = GitSkillsRegistry(
            repo_url='https://github.com/example/skills',
            target_dir=clone_dir,
            auto_install=False,
        )
        registry._clone()
        mock_clone.assert_called_once()


def test_pull_called_when_already_cloned(fake_clone: Path) -> None:
    """Pull is called when a valid repo already exists."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'def456'

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False)
        registry._pull()
        mock_repo.remotes.origin.pull.assert_called_once()


def test_network_failure_raises_skill_registry_error(tmp_path: Path) -> None:
    """GitCommandError is mapped to SkillRegistryError."""
    import git

    clone_dir = tmp_path / 'clone'
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=clone_dir,
        auto_install=False,
    )

    with patch('git.Repo.clone_from', side_effect=git.exc.GitCommandError('clone', 128)):
        with pytest.raises(SkillRegistryError, match='Failed to clone'):
            registry._clone()


def test_pull_network_failure_raises_skill_registry_error(fake_clone: Path) -> None:
    """GitCommandError on pull is mapped to SkillRegistryError."""
    import git

    mock_repo = MagicMock()
    mock_repo.remotes.origin.pull.side_effect = git.exc.GitCommandError('pull', 128)

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False)
        with pytest.raises(SkillRegistryError, match='Failed to pull'):
            registry._pull()


def test_pull_falls_back_to_clone_on_corrupt_repo(tmp_path: Path) -> None:
    """If the local clone is corrupt, _pull re-clones."""
    import git

    clone_dir = tmp_path / 'clone'
    clone_dir.mkdir()

    mock_repo = MagicMock()

    with (
        patch('git.Repo', side_effect=git.exc.InvalidGitRepositoryError),
        patch('git.Repo.clone_from', return_value=mock_repo) as mock_clone,
    ):
        registry = GitSkillsRegistry(
            repo_url='https://github.com/example/skills',
            target_dir=clone_dir,
            auto_install=False,
        )
        registry._pull()
        mock_clone.assert_called_once()


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


async def test_search_returns_matching_skills(fake_clone: Path) -> None:
    """Search returns skills whose name matches the query."""
    registry = _make_registry(fake_clone)
    results = await registry.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'pdf'


async def test_search_is_case_insensitive(fake_clone: Path) -> None:
    """Search query matching is case-insensitive."""
    registry = _make_registry(fake_clone)
    results = await registry.search('PDF')
    assert len(results) == 1
    assert results[0].name == 'pdf'


async def test_search_returns_empty_for_no_match(fake_clone: Path) -> None:
    """Search returns an empty list when no skill matches the query."""
    registry = _make_registry(fake_clone)
    results = await registry.search('nonexistent')
    assert results == []


async def test_search_respects_limit(fake_clone: Path) -> None:
    """Search returns at most *limit* results."""
    registry = _make_registry(fake_clone)
    results = await registry.search('skill', limit=1)
    assert len(results) <= 1


async def test_search_populates_metadata(fake_clone: Path) -> None:
    """Skills returned by search include registry metadata."""
    registry = _make_registry(fake_clone)
    results = await registry.search('pdf')
    assert len(results) == 1
    meta = results[0].metadata
    assert meta is not None
    assert meta['registry'] == 'GitSkillsRegistry'
    assert meta['repo'] == 'https://github.com/example/skills'
    assert 'source_url' in meta


async def test_search_triggers_auto_install(fake_clone: Path) -> None:
    """auto_install=True triggers _ensure_cloned which calls _pull."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'abc'

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=True)
        results = await registry.search('pdf')
        assert len(results) == 1
        mock_repo.remotes.origin.pull.assert_called()


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


async def test_get_returns_skill_by_name(fake_clone: Path) -> None:
    """get() returns the skill with the matching name."""
    registry = _make_registry(fake_clone)
    skill = await registry.get('pdf')
    assert skill.name == 'pdf'


async def test_get_raises_for_unknown_skill(fake_clone: Path) -> None:
    """get() raises SkillNotFoundError for an unknown skill name."""
    registry = _make_registry(fake_clone)
    with pytest.raises(SkillNotFoundError):
        await registry.get('unknown-skill')


async def test_get_populates_metadata(fake_clone: Path) -> None:
    """Skills returned by get() include registry metadata."""
    registry = _make_registry(fake_clone)
    skill = await registry.get('pdf')
    assert skill.metadata is not None
    assert skill.metadata['registry'] == 'GitSkillsRegistry'
    assert skill.metadata['repo'] == 'https://github.com/example/skills'
    assert 'source_url' in skill.metadata


# ---------------------------------------------------------------------------
# install()
# ---------------------------------------------------------------------------


async def test_install_copies_skill_directory(fake_clone: Path, tmp_path: Path) -> None:
    """install() copies the skill directory into the target directory."""
    install_dir = tmp_path / 'installed'
    registry = _make_registry(fake_clone)
    result = await registry.install('pdf', install_dir)
    assert result.is_dir()
    assert (result / 'SKILL.md').is_file()


async def test_install_raises_for_unknown_skill(fake_clone: Path, tmp_path: Path) -> None:
    """install() raises SkillNotFoundError when the skill does not exist."""
    registry = _make_registry(fake_clone)
    with pytest.raises(SkillNotFoundError):
        await registry.install('ghost', tmp_path)


async def test_install_validation_failure_raises(tmp_path: Path) -> None:
    """Validation warnings during install do not prevent the install from completing."""
    # Create a skill with a name that is too long (>64 chars)
    long_name = 'a' * 65
    skill_dir = tmp_path / 'source' / long_name
    skill_dir.mkdir(parents=True)
    (skill_dir / 'SKILL.md').write_text(
        f'---\nname: {long_name}\ndescription: desc\n---\n\n# instructions\n',
        encoding='utf-8',
    )

    install_dir = tmp_path / 'installed'
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=tmp_path / 'source',
        validate=True,
        auto_install=False,
    )
    # validation emits a warning (not error) per current validator
    with warnings.catch_warnings(record=True):
        warnings.simplefilter('always')
        result = await registry.install(long_name, install_dir)
    # installation should still complete (validation is a warning, not exception)
    assert result.exists()


async def test_install_path_traversal_attempt(fake_clone: Path, tmp_path: Path) -> None:
    """A symlink pointing outside target_dir should be skipped or raise."""
    import os

    install_dir = tmp_path / 'installed'
    secret_file = tmp_path / 'secret.txt'
    secret_file.write_text('TOP SECRET')

    # Plant a symlink inside the pdf skill that escapes the clone
    pdf_dir = fake_clone / 'pdf'
    traversal_link = pdf_dir / 'escape.txt'
    try:
        os.symlink(secret_file, traversal_link)
    except NotImplementedError:
        pytest.skip('Symlinks not supported on this platform')

    registry = _make_registry(fake_clone)
    # install should succeed; the symlink is either copied or raises SkillRegistryError
    # (the security check resolves dest paths against target)
    try:
        await registry.install('pdf', install_dir)
        # If no exception, the file must NOT be the secret file (copy broke the symlink)
        escaped = install_dir / 'pdf' / 'escape.txt'
        if escaped.exists():
            assert escaped.read_text() != 'TOP SECRET'
    except SkillRegistryError:
        pass  # also acceptable


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


async def test_update_installs_when_not_present(fake_clone: Path, tmp_path: Path) -> None:
    """update() falls back to install when the skill is not yet installed."""
    install_dir = tmp_path / 'installed'
    registry = _make_registry(fake_clone)
    result = await registry.update('pdf', install_dir)
    assert result.is_dir()
    assert (result / 'SKILL.md').is_file()


async def test_update_pulls_and_reinstalls(fake_clone: Path, tmp_path: Path) -> None:
    """update() performs git pull before re-installing the skill."""
    install_dir = tmp_path / 'installed'
    registry = _make_registry(fake_clone)

    # Pre-install
    await registry.install('pdf', install_dir)

    mock_repo = MagicMock()
    with patch('git.Repo', return_value=mock_repo):
        result = await registry.update('pdf', install_dir)
        mock_repo.remotes.origin.pull.assert_called()

    assert result.is_dir()


# ---------------------------------------------------------------------------
# filtered()
# ---------------------------------------------------------------------------


async def test_filtered_includes_matching_skills(fake_clone: Path) -> None:
    """filtered() limits search results to skills matching the predicate."""
    registry = _make_registry(fake_clone)
    pdf_only = registry.filtered(lambda s: s.name == 'pdf')
    results = await pdf_only.search('skill')
    assert all(s.name == 'pdf' for s in results)


async def test_filtered_get_passes_predicate(fake_clone: Path) -> None:
    """filtered().get() returns a skill when the predicate passes."""
    registry = _make_registry(fake_clone)
    filtered = registry.filtered(lambda s: s.name == 'pdf')
    skill = await filtered.get('pdf')
    assert skill.name == 'pdf'


async def test_filtered_get_raises_for_excluded_skill(fake_clone: Path) -> None:
    """filtered().get() raises SkillNotFoundError for excluded skills."""
    registry = _make_registry(fake_clone)
    filtered = registry.filtered(lambda s: s.name == 'pdf')
    with pytest.raises(SkillNotFoundError):
        await filtered.get('xlsx')


async def test_filtered_shares_clone_directory(fake_clone: Path) -> None:
    """Filtered view wraps the same registry instance (shares clone)."""
    registry = _make_registry(fake_clone)
    filtered = registry.filtered(lambda s: True)
    assert filtered.wrapped is registry
    assert isinstance(filtered.wrapped, GitSkillsRegistry)
    assert filtered.wrapped._target_dir == registry._target_dir


# ---------------------------------------------------------------------------
# prefixed()
# ---------------------------------------------------------------------------


async def test_prefixed_search_returns_prefixed_names(fake_clone: Path) -> None:
    """prefixed() prepends the prefix to every skill name returned by search."""
    registry = _make_registry(fake_clone)
    prefixed = registry.prefixed('anthropic-')
    results = await prefixed.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'anthropic-pdf'


async def test_prefixed_get_with_prefix(fake_clone: Path) -> None:
    """prefixed().get() returns the skill when the prefixed name is used."""
    registry = _make_registry(fake_clone)
    prefixed = registry.prefixed('anthropic-')
    skill = await prefixed.get('anthropic-pdf')
    assert skill.name == 'anthropic-pdf'


async def test_prefixed_get_original_name_not_found(fake_clone: Path) -> None:
    """prefixed().get() raises SkillNotFoundError when prefix is missing."""
    registry = _make_registry(fake_clone)
    prefixed = registry.prefixed('anthropic-')
    # 'pdf' without prefix should not be found — prefix must be present
    with pytest.raises(SkillNotFoundError):
        await prefixed.get('pdf')


async def test_prefixed_shares_clone_directory(fake_clone: Path) -> None:
    """Prefixed view wraps the same registry instance (shares clone)."""
    registry = _make_registry(fake_clone)
    prefixed = registry.prefixed('x-')
    assert prefixed.wrapped is registry
    assert isinstance(prefixed.wrapped, GitSkillsRegistry)
    assert prefixed.wrapped._target_dir == registry._target_dir


async def test_prefixed_install_strips_prefix(fake_clone: Path, tmp_path: Path) -> None:
    """prefixed().install() strips the prefix before copying the skill."""
    install_dir = tmp_path / 'installed'
    registry = _make_registry(fake_clone)
    prefixed = registry.prefixed('anthropic-')
    result = await prefixed.install('anthropic-pdf', install_dir)
    assert result.is_dir()
    assert (result / 'SKILL.md').is_file()


# ---------------------------------------------------------------------------
# filtered + prefixed composition
# ---------------------------------------------------------------------------


async def test_filtered_then_prefixed(fake_clone: Path) -> None:
    """Chaining filtered() then prefixed() applies both transformations."""
    registry = _make_registry(fake_clone)
    view = registry.filtered(lambda s: s.name == 'pdf').prefixed('x-')
    results = await view.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'x-pdf'


async def test_prefixed_then_filtered(fake_clone: Path) -> None:
    """Chaining prefixed() then filtered() applies both transformations."""
    registry = _make_registry(fake_clone)
    # The predicate sees prefixed names since FilteredRegistry wraps PrefixedRegistry output.
    view = registry.prefixed('a-').filtered(lambda s: s.name == 'a-pdf')
    results = await view.search('pdf')
    assert len(results) == 1
    assert results[0].name == 'a-pdf'


# ---------------------------------------------------------------------------
# Skill.metadata
# ---------------------------------------------------------------------------


async def test_metadata_contains_required_keys(fake_clone: Path) -> None:
    """Skills returned by the registry include all required metadata keys."""
    registry = _make_registry(fake_clone)
    skill = await registry.get('pdf')
    meta = skill.metadata
    assert meta is not None
    for key in ('source_url', 'registry', 'repo', 'version'):
        assert key in meta, f'Missing metadata key: {key}'


async def test_metadata_registry_name(fake_clone: Path) -> None:
    """metadata['registry'] contains the registry class name."""
    registry = _make_registry(fake_clone)
    skill = await registry.get('pdf')
    assert skill.metadata['registry'] == 'GitSkillsRegistry'  # type: ignore[index]


async def test_metadata_repo_is_clean_url(fake_clone: Path) -> None:
    """metadata['repo'] never contains the authentication token."""
    registry = _make_registry(fake_clone, token='secret')
    skill = await registry.get('pdf')
    assert 'secret' not in str(skill.metadata['repo'])  # type: ignore[index]


# ---------------------------------------------------------------------------
# auto_install=False skips clone/pull
# ---------------------------------------------------------------------------


async def test_auto_install_false_does_not_clone(tmp_path: Path) -> None:
    """auto_install=False prevents automatic clone/pull calls."""
    _write_skill(tmp_path, 'pdf')

    with patch.object(GitSkillsRegistry, '_ensure_cloned') as mock_ensure:
        registry = GitSkillsRegistry(
            repo_url='https://github.com/example/skills',
            target_dir=tmp_path,
            auto_install=False,
        )
        await registry.search('pdf')
        mock_ensure.assert_not_called()


# ---------------------------------------------------------------------------
# Sub-path support via path=
# ---------------------------------------------------------------------------


async def test_subpath_skills_discovery(tmp_path: Path) -> None:
    """Skills in a sub-path of the repository are discovered correctly."""
    skills_subdir = tmp_path / 'skills'
    _write_skill(skills_subdir, 'pdf')

    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=tmp_path,
        path='skills',
        auto_install=False,
    )
    results = await registry.search('pdf')
    assert len(results) == 1


# ---------------------------------------------------------------------------
# Top-level exports
# ---------------------------------------------------------------------------


def test_top_level_imports() -> None:
    """SkillRegistry, GitSkillsRegistry, GitCloneOptions and SkillRegistryError are top-level exports."""
    from pydantic_ai_skills import GitCloneOptions, GitSkillsRegistry, SkillRegistry, SkillRegistryError

    assert GitSkillsRegistry is not None
    assert GitCloneOptions is not None
    assert SkillRegistry is not None
    assert SkillRegistryError is not None


def test_registries_module_imports() -> None:
    """SkillRegistry, GitSkillsRegistry and GitCloneOptions are exported from pydantic_ai_skills.registries."""
    from pydantic_ai_skills.registries import GitCloneOptions, GitSkillsRegistry, SkillRegistry

    assert GitSkillsRegistry is not None
    assert GitCloneOptions is not None
    assert SkillRegistry is not None


# ---------------------------------------------------------------------------
# Helper function unit tests — _inject_token_into_url
# ---------------------------------------------------------------------------


def test_inject_token_into_url_with_port() -> None:
    """Token injection preserves a non-standard port in the URL."""
    from pydantic_ai_skills.registries.git import _inject_token_into_url

    url = _inject_token_into_url('https://git.example.com:8443/repo.git', 'my-token')
    assert 'my-token' in url
    assert ':8443' in url
    assert 'oauth2:my-token@' in url


def test_inject_token_into_url_ssh_passthrough() -> None:
    """SSH URLs are returned unchanged by _inject_token_into_url."""
    from pydantic_ai_skills.registries.git import _inject_token_into_url

    ssh_url = 'git@github.com:user/repo.git'
    result = _inject_token_into_url(ssh_url, 'my-token')
    assert result == ssh_url


def test_inject_token_into_url_http() -> None:
    """HTTP URL (not just HTTPS) also gets token injected."""
    from pydantic_ai_skills.registries.git import _inject_token_into_url

    result = _inject_token_into_url('http://example.com/repo.git', 'tok')
    assert 'oauth2:tok@' in result


# ---------------------------------------------------------------------------
# Helper function unit tests — _sanitize_url
# ---------------------------------------------------------------------------


def test_sanitize_url_with_password_and_port() -> None:
    """_sanitize_url removes password and preserves port."""
    from pydantic_ai_skills.registries.git import _sanitize_url

    url = 'https://oauth2:secret@git.example.com:8443/repo.git'
    result = _sanitize_url(url)
    assert 'secret' not in result
    assert ':8443' in result
    assert 'git.example.com' in result


def test_sanitize_url_with_password_no_port() -> None:
    """_sanitize_url removes password from standard-port URL."""
    from pydantic_ai_skills.registries.git import _sanitize_url

    url = 'https://oauth2:secret@github.com/repo.git'
    result = _sanitize_url(url)
    assert 'secret' not in result
    assert 'github.com' in result


def test_sanitize_url_no_password() -> None:
    """_sanitize_url returns URL unchanged when no password is present."""
    from pydantic_ai_skills.registries.git import _sanitize_url

    url = 'https://github.com/user/repo.git'
    result = _sanitize_url(url)
    assert result == url


# ---------------------------------------------------------------------------
# Helper function unit tests — _build_source_url
# ---------------------------------------------------------------------------


def test_build_source_url_strips_dot_git_suffix() -> None:
    """_build_source_url strips trailing .git before building the tree URL."""
    from pydantic_ai_skills.registries.git import _build_source_url

    result = _build_source_url('https://github.com/org/repo.git', 'skills', 'pdf', 'main')
    assert result == 'https://github.com/org/repo/tree/main/skills/pdf'
    assert '.git' not in result


def test_build_source_url_defaults_branch_to_main() -> None:
    """_build_source_url uses 'main' when branch is None."""
    from pydantic_ai_skills.registries.git import _build_source_url

    result = _build_source_url('https://github.com/org/repo', '', 'my-skill', None)
    assert '/tree/main/' in result


def test_build_source_url_custom_branch() -> None:
    """_build_source_url uses the specified branch."""
    from pydantic_ai_skills.registries.git import _build_source_url

    result = _build_source_url('https://github.com/org/repo', 'skills', 'pdf', 'develop')
    assert '/tree/develop/' in result


# ---------------------------------------------------------------------------
# Helper function unit tests — _sanitize_error_message
# ---------------------------------------------------------------------------


def test_sanitize_error_message_replaces_token_url() -> None:
    """_sanitize_error_message redacts the clone URL containing a token."""
    from pydantic_ai_skills.registries.git import _sanitize_error_message

    exc = Exception('fatal: https://oauth2:secret@github.com/repo.git not found')
    result = _sanitize_error_message(
        exc,
        'https://oauth2:secret@github.com/repo.git',
        'https://github.com/repo.git',
    )
    assert 'secret' not in result
    assert 'https://github.com/repo.git' in result


# ---------------------------------------------------------------------------
# target_dir=None — temporary directory
# ---------------------------------------------------------------------------


def test_target_dir_none_uses_temp_directory() -> None:
    """When target_dir is None, a temporary directory is created."""
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=None,
        auto_install=False,
    )
    assert registry._tmp_dir is not None
    assert registry._target_dir.exists()


# ---------------------------------------------------------------------------
# SSH key — OSError handling
# ---------------------------------------------------------------------------


def test_ssh_key_nonexistent_file_skips_permission_check(tmp_path: Path, fake_clone: Path) -> None:
    """A non-existent SSH key file doesn't crash — OSError is caught."""
    key_file = tmp_path / 'nonexistent_key'
    # key_file intentionally not created

    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=fake_clone,
        ssh_key_file=key_file,
        auto_install=False,
    )
    # Should still set GIT_SSH_COMMAND even if stat failed
    assert 'GIT_SSH_COMMAND' in registry._clone_options.env


# ---------------------------------------------------------------------------
# _is_cloned() edge cases
# ---------------------------------------------------------------------------


def test_is_cloned_false_when_dir_does_not_exist(tmp_path: Path) -> None:
    """_is_cloned returns False when target dir doesn't exist."""
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=tmp_path / 'nonexistent',
        auto_install=False,
    )
    assert registry._is_cloned() is False


def test_is_cloned_false_for_non_git_directory(fake_clone: Path) -> None:
    """_is_cloned returns False for a directory that is not a git repo."""
    import git

    with patch('git.Repo', side_effect=git.exc.InvalidGitRepositoryError):
        registry = _make_registry(fake_clone, auto_install=False)
        assert registry._is_cloned() is False


def test_is_cloned_true_for_valid_repo(fake_clone: Path) -> None:
    """_is_cloned returns True when a valid git repo exists."""
    mock_repo = MagicMock()
    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False)
        assert registry._is_cloned() is True


# ---------------------------------------------------------------------------
# _clone() with all clone options
# ---------------------------------------------------------------------------


def test_clone_with_all_options(tmp_path: Path) -> None:
    """_clone forwards depth, branch, single_branch, multi_options, and env to clone_from."""
    clone_dir = tmp_path / 'clone'
    mock_repo = MagicMock()

    opts = GitCloneOptions(
        depth=1,
        branch='develop',
        single_branch=True,
        multi_options=['--filter=blob:none'],
        env={'GIT_SSH_COMMAND': 'ssh -i key'},
        git_options={'allow_unsafe_protocols': True},
    )

    with patch('git.Repo.clone_from', return_value=mock_repo) as mock_clone:
        registry = GitSkillsRegistry(
            repo_url='https://github.com/example/skills',
            target_dir=clone_dir,
            clone_options=opts,
            auto_install=False,
        )
        registry._clone()

        mock_clone.assert_called_once()
        call_kwargs = mock_clone.call_args[1]
        assert call_kwargs['depth'] == 1
        assert call_kwargs['branch'] == 'develop'
        assert call_kwargs['single_branch'] is True
        assert call_kwargs['multi_options'] == ['--filter=blob:none']
        assert call_kwargs['env'] == {'GIT_SSH_COMMAND': 'ssh -i key'}
        assert call_kwargs['allow_unsafe_protocols'] is True


def test_clone_with_sparse_checkout(tmp_path: Path) -> None:
    """_clone applies sparse checkout when sparse_paths is configured."""
    clone_dir = tmp_path / 'clone'
    mock_repo = MagicMock()

    opts = GitCloneOptions(sparse_paths=['skills/pdf', 'skills/xlsx'])

    with patch('git.Repo.clone_from', return_value=mock_repo) as mock_clone:
        registry = GitSkillsRegistry(
            repo_url='https://github.com/example/skills',
            target_dir=clone_dir,
            clone_options=opts,
            auto_install=False,
        )
        registry._clone()

        mock_clone.assert_called_once()
        mock_repo.git.sparse_checkout.assert_any_call('init')
        mock_repo.git.sparse_checkout.assert_any_call('set', 'skills/pdf', 'skills/xlsx')


def test_clone_sparse_checkout_failure_raises(tmp_path: Path) -> None:
    """Sparse checkout failure raises SkillRegistryError."""
    import git

    clone_dir = tmp_path / 'clone'
    mock_repo = MagicMock()
    mock_repo.git.sparse_checkout.side_effect = git.exc.GitCommandError('sparse-checkout', 128)

    opts = GitCloneOptions(sparse_paths=['skills/pdf'])

    with patch('git.Repo.clone_from', return_value=mock_repo):
        registry = GitSkillsRegistry(
            repo_url='https://github.com/example/skills',
            target_dir=clone_dir,
            clone_options=opts,
            auto_install=False,
        )
        with pytest.raises(SkillRegistryError, match='sparse checkout'):
            registry._clone()


# ---------------------------------------------------------------------------
# _pull() with env
# ---------------------------------------------------------------------------


def test_pull_passes_env_from_clone_options(fake_clone: Path) -> None:
    """_pull forwards clone_options.env to the pull call."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'abc'

    opts = GitCloneOptions(env={'GIT_SSH_COMMAND': 'ssh -i key'})

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False, clone_options=opts)
        registry._pull()

        pull_kwargs = mock_repo.remotes.origin.pull.call_args[1]
        assert pull_kwargs['env'] == {'GIT_SSH_COMMAND': 'ssh -i key'}


def test_pull_passes_git_options(fake_clone: Path) -> None:
    """_pull forwards clone_options.git_options to the pull call."""
    mock_repo = MagicMock()

    opts = GitCloneOptions(git_options={'rebase': True})

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False, clone_options=opts)
        registry._pull()

        pull_kwargs = mock_repo.remotes.origin.pull.call_args[1]
        assert pull_kwargs['rebase'] is True


# ---------------------------------------------------------------------------
# _ensure_cloned — both branches
# ---------------------------------------------------------------------------


def test_ensure_cloned_calls_clone_when_not_cloned(tmp_path: Path) -> None:
    """_ensure_cloned calls _clone when repo does not exist."""
    clone_dir = tmp_path / 'clone'
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=clone_dir,
        auto_install=False,
    )

    with patch.object(registry, '_is_cloned', return_value=False), patch.object(registry, '_clone') as mock_clone:
        registry._ensure_cloned()
        mock_clone.assert_called_once()


def test_ensure_cloned_calls_pull_when_already_cloned(fake_clone: Path) -> None:
    """_ensure_cloned calls _pull when repo already exists."""
    registry = _make_registry(fake_clone, auto_install=False)

    with patch.object(registry, '_is_cloned', return_value=True), patch.object(registry, '_pull') as mock_pull:
        registry._ensure_cloned()
        mock_pull.assert_called_once()


# ---------------------------------------------------------------------------
# _get_commit_sha — exception branch
# ---------------------------------------------------------------------------


def test_get_commit_sha_returns_none_on_error(fake_clone: Path) -> None:
    """_get_commit_sha returns None when git operations fail."""
    import git

    with patch('git.Repo', side_effect=git.exc.InvalidGitRepositoryError):
        registry = _make_registry(fake_clone, auto_install=False)
        result = registry._get_commit_sha()
        assert result is None


def test_get_commit_sha_returns_none_on_os_error(fake_clone: Path) -> None:
    """_get_commit_sha returns None on OSError."""
    with patch('git.Repo', side_effect=OSError('disk failure')):
        registry = _make_registry(fake_clone, auto_install=False)
        result = registry._get_commit_sha()
        assert result is None


def test_get_commit_sha_returns_hexsha(fake_clone: Path) -> None:
    """_get_commit_sha returns the HEAD commit SHA."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'deadbeef1234'

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False)
        result = registry._get_commit_sha()
        assert result == 'deadbeef1234'


# ---------------------------------------------------------------------------
# _ensure_skills_loaded — auto_install path
# ---------------------------------------------------------------------------


async def test_ensure_skills_loaded_with_auto_install(fake_clone: Path) -> None:
    """_ensure_skills_loaded triggers _ensure_cloned when auto_install=True and cache is empty."""
    mock_repo = MagicMock()

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=True)
        # Clear the cache manually to test the lazy loading path
        registry._cached_skills = []

        with patch.object(registry, '_ensure_cloned') as mock_ensure:
            registry._ensure_skills_loaded()
            mock_ensure.assert_called_once()
        assert len(registry._cached_skills) > 0


async def test_ensure_skills_loaded_skips_when_cached(fake_clone: Path) -> None:
    """_ensure_skills_loaded does nothing when cache is already populated."""
    registry = _make_registry(fake_clone, auto_install=False)
    # Manually populate cache
    registry._cached_skills = [MagicMock()]

    with patch.object(registry, '_ensure_cloned') as mock_ensure:
        registry._ensure_skills_loaded()
        mock_ensure.assert_not_called()


# ---------------------------------------------------------------------------
# get_skills — synchronous interface
# ---------------------------------------------------------------------------


def test_get_skills_returns_all_skills(fake_clone: Path) -> None:
    """get_skills returns all discovered skills."""
    registry = _make_registry(fake_clone, auto_install=False)
    skills = registry.get_skills()
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {'pdf', 'xlsx'}


def test_get_skills_returns_copy(fake_clone: Path) -> None:
    """get_skills returns a new list each time (not the internal cache)."""
    registry = _make_registry(fake_clone, auto_install=False)
    skills1 = registry.get_skills()
    skills2 = registry.get_skills()
    assert skills1 is not skills2
    assert len(skills1) == len(skills2)


# ---------------------------------------------------------------------------
# _refresh
# ---------------------------------------------------------------------------


def test_refresh_pulls_and_reloads_cache(fake_clone: Path) -> None:
    """_refresh calls _ensure_cloned and rebuilds the skill cache."""
    registry = _make_registry(fake_clone, auto_install=False)

    with patch.object(registry, '_ensure_cloned') as mock_cloned:
        registry._refresh()
        mock_cloned.assert_called_once()
    assert len(registry._cached_skills) > 0


# ---------------------------------------------------------------------------
# _skills_root
# ---------------------------------------------------------------------------


def test_skills_root_without_path(fake_clone: Path) -> None:
    """_skills_root returns target_dir when path is empty."""
    registry = _make_registry(fake_clone, path='', auto_install=False)
    assert registry._skills_root() == registry._target_dir


def test_skills_root_with_path(fake_clone: Path) -> None:
    """_skills_root returns target_dir / path when path is set."""
    registry = _make_registry(fake_clone, path='skills', auto_install=False)
    assert registry._skills_root() == registry._target_dir / 'skills'


# ---------------------------------------------------------------------------
# _load_skills — empty / non-existent root
# ---------------------------------------------------------------------------


def test_load_skills_returns_empty_when_path_missing(tmp_path: Path) -> None:
    """_load_skills returns [] when skills root does not exist."""
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=tmp_path,
        path='nonexistent',
        auto_install=False,
    )
    assert registry._load_skills() == []


# ---------------------------------------------------------------------------
# search() — matches on description
# ---------------------------------------------------------------------------


async def test_search_matches_on_description(fake_clone: Path) -> None:
    """search() matches against skill descriptions too."""
    registry = _make_registry(fake_clone)
    results = await registry.search('spreadsheet')
    assert len(results) == 1
    assert results[0].name == 'xlsx'


async def test_search_returns_all_on_broad_query(fake_clone: Path) -> None:
    """search() with a broad query returns all matching skills."""
    registry = _make_registry(fake_clone)
    results = await registry.search('skill')
    assert len(results) == 2


# ---------------------------------------------------------------------------
# install() — overwrite existing skill
# ---------------------------------------------------------------------------


async def test_install_overwrites_existing_skill(fake_clone: Path, tmp_path: Path) -> None:
    """install() overwrites an already-installed skill directory."""
    install_dir = tmp_path / 'installed'
    registry = _make_registry(fake_clone)

    # Install once
    result1 = await registry.install('pdf', install_dir)
    assert result1.is_dir()
    # Write an extra file
    (result1 / 'extra.txt').write_text('temp')

    # Install again — should overwrite
    result2 = await registry.install('pdf', install_dir)
    assert result2.is_dir()
    assert not (result2 / 'extra.txt').exists()


# ---------------------------------------------------------------------------
# update() — existing destination triggers pull + reinstall
# ---------------------------------------------------------------------------


async def test_update_existing_destination_pulls_and_reinstalls(fake_clone: Path, tmp_path: Path) -> None:
    """update() with an existing install performs pull then reinstall."""
    install_dir = tmp_path / 'installed'
    registry = _make_registry(fake_clone)

    # Pre-install the skill
    await registry.install('pdf', install_dir)
    dest = install_dir / 'pdf'
    assert dest.is_dir()

    # Now update — should trigger _ensure_cloned + reinstall
    with patch.object(registry, '_ensure_cloned'):
        result = await registry.update('pdf', install_dir)
        assert result.is_dir()
        assert (result / 'SKILL.md').is_file()


# ---------------------------------------------------------------------------
# renamed() — composition wrapper
# ---------------------------------------------------------------------------


async def test_renamed_get_by_new_name(fake_clone: Path) -> None:
    """renamed().get() returns the skill using its new name."""
    registry = _make_registry(fake_clone)
    renamed = registry.renamed({'doc-pdf': 'pdf'})
    skill = await renamed.get('doc-pdf')
    assert skill.name == 'doc-pdf'


async def test_renamed_search(fake_clone: Path) -> None:
    """renamed().search() returns skills with remapped names."""
    registry = _make_registry(fake_clone)
    renamed = registry.renamed({'doc-pdf': 'pdf', 'doc-xlsx': 'xlsx'})
    results = await renamed.search('skill')
    names = {s.name for s in results}
    assert 'doc-pdf' in names
    assert 'doc-xlsx' in names


# ---------------------------------------------------------------------------
# _enrich_metadata with explicit version
# ---------------------------------------------------------------------------


def test_enrich_metadata_with_explicit_version(fake_clone: Path) -> None:
    """_enrich_metadata uses explicit version over commit SHA."""
    registry = _make_registry(fake_clone, auto_install=False)
    skills = registry._load_skills()
    assert len(skills) > 0

    enriched = registry._enrich_metadata(skills[0], version='v1.2.3')
    assert enriched.metadata['version'] == 'v1.2.3'


def test_enrich_metadata_uses_commit_sha_as_fallback(fake_clone: Path) -> None:
    """_enrich_metadata falls back to commit SHA when version is not given."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'cafe1234'

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False)
        skills = registry._load_skills()
        enriched = registry._enrich_metadata(skills[0])
        assert enriched.metadata['version'] == 'cafe1234'


# ---------------------------------------------------------------------------
# GitCloneOptions — additional field combinations
# ---------------------------------------------------------------------------


def test_git_clone_options_sparse_paths() -> None:
    """GitCloneOptions accepts sparse_paths list."""
    opts = GitCloneOptions(sparse_paths=['skills/pdf', 'skills/xlsx'])
    assert opts.sparse_paths == ['skills/pdf', 'skills/xlsx']


def test_git_clone_options_env_and_multi_options() -> None:
    """GitCloneOptions accepts env and multi_options."""
    opts = GitCloneOptions(
        env={'GIT_ASKPASS': '/usr/bin/true'},
        multi_options=['--filter=blob:none', '--no-tags'],
    )
    assert opts.env == {'GIT_ASKPASS': '/usr/bin/true'}
    assert opts.multi_options == ['--filter=blob:none', '--no-tags']


def test_git_clone_options_git_options() -> None:
    """GitCloneOptions accepts arbitrary git_options kwargs."""
    opts = GitCloneOptions(git_options={'allow_unsafe_protocols': True, 'recurse_submodules': True})
    assert opts.git_options['allow_unsafe_protocols'] is True
    assert opts.git_options['recurse_submodules'] is True


# ---------------------------------------------------------------------------
# Token masking — no token scenario
# ---------------------------------------------------------------------------


def test_repr_without_token(fake_clone: Path) -> None:
    """__repr__ works when no token is set."""
    registry = _make_registry(fake_clone)
    result = repr(registry)
    assert 'GitSkillsRegistry(' in result
    assert 'repo_url=' in result


def test_str_without_token(fake_clone: Path) -> None:
    """__str__ works when no token is set."""
    registry = _make_registry(fake_clone)
    result = str(registry)
    assert 'GitSkillsRegistry(' in result


# ---------------------------------------------------------------------------
# auto_install=True — eager clone during __init__
# ---------------------------------------------------------------------------


async def test_install_destination_path_traversal_raises(fake_clone: Path, tmp_path: Path) -> None:
    """install() raises SkillRegistryError when skill name would escape target_dir."""
    from dataclasses import replace as dc_replace

    registry = _make_registry(fake_clone)
    # Load skills first
    registry._ensure_skills_loaded()
    # Inject a crafted skill with a traversal name into the cache
    real_skill = registry._cached_skills[0]
    evil_skill = dc_replace(real_skill, name='../escape')
    registry._cached_skills.append(evil_skill)

    with pytest.raises(SkillRegistryError, match='escapes target directory'):
        await registry.install('../escape', tmp_path / 'installed')


def test_auto_install_true_populates_cache(fake_clone: Path) -> None:
    """auto_install=True eagerly clones and populates skill cache in __init__."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'aaa111'

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=True)
        assert len(registry._cached_skills) > 0
        names = {s.name for s in registry._cached_skills}
        assert 'pdf' in names
        assert 'xlsx' in names

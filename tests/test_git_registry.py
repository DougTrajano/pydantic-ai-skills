"""Tests for GitSkillsRegistry.

A registry's job in v2 is to put a remote repository on the local filesystem as a skill
library harness can read; it does not parse SKILL.md or build Skill objects. Clone and
pull behaviour is exercised against a pre-made directory plus mocked GitPython, so no
test reaches the network.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai_harness import Skills

from pydantic_ai_skills import SkillsCapability
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


def library_names(library: Path) -> list[str]:
    """Names of the skill packages in a library, sorted."""
    return sorted(child.name for child in library.iterdir() if (child / 'SKILL.md').is_file())


def harness_names(library: Path) -> list[str]:
    """What harness would actually call the skills in `library`."""
    leaves: list[object] = []
    Skills(library).apply(leaves.append)
    return sorted(leaf.id for leaf in leaves)  # type: ignore[attr-defined]


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
    auto_install: bool = False,
    clone_options: GitCloneOptions | None = None,
) -> GitSkillsRegistry:
    """Create a GitSkillsRegistry pointing at a pre-existing fake clone."""
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=fake_clone_path,
        path=path,
        token=token,
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
    """GitCommandError is mapped to RuntimeError."""
    import git

    clone_dir = tmp_path / 'clone'
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=clone_dir,
        auto_install=False,
    )

    with patch('git.Repo.clone_from', side_effect=git.exc.GitCommandError('clone', 128)):
        with pytest.raises(RuntimeError, match='Failed to clone'):
            registry._clone()


def test_pull_network_failure_raises_skill_registry_error(fake_clone: Path) -> None:
    """GitCommandError on pull is mapped to RuntimeError."""
    import git

    mock_repo = MagicMock()
    mock_repo.remotes.origin.pull.side_effect = git.exc.GitCommandError('pull', 128)

    with patch('git.Repo', return_value=mock_repo):
        registry = _make_registry(fake_clone, auto_install=False)
        with pytest.raises(RuntimeError, match='Failed to pull'):
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


# ---------------------------------------------------------------------------
# sync() — the whole SkillRegistry contract
# ---------------------------------------------------------------------------


def test_sync_returns_the_clone_root(fake_clone: Path) -> None:
    """With no sub-path configured, the repository root is the skill library."""
    registry = _make_registry(fake_clone)

    assert registry.sync() == fake_clone
    assert library_names(registry.sync()) == ['pdf', 'xlsx']


def test_sync_returns_the_configured_sub_path(tmp_path: Path) -> None:
    """Most published repositories keep skills under a directory such as `skills/`."""
    clone_dir = tmp_path / 'clone'
    _write_skill(clone_dir / 'skills', 'pdf', 'PDF manipulation skill.')
    registry = _make_registry(clone_dir, path='skills')

    assert registry.sync() == clone_dir / 'skills'
    assert library_names(registry.sync()) == ['pdf']


def test_sync_returns_a_library_harness_accepts(fake_clone: Path) -> None:
    """The whole contract: the returned path is something `Skills` can read."""
    assert harness_names(_make_registry(fake_clone).sync()) == ['pdf', 'xlsx']


def test_sync_reaches_the_capability(fake_clone: Path) -> None:
    """The skills a repository holds end up in the agent's deferred catalog."""
    assert SkillsCapability(registries=[_make_registry(fake_clone)]).skill_names == ['pdf', 'xlsx']


def test_sync_clones_when_auto_install_is_on(tmp_path: Path) -> None:
    """`sync`, not `__init__`, is what reaches the network."""
    clone_dir = tmp_path / 'clone'

    def fake_clone_from(url: str, target: str, **kwargs: object) -> MagicMock:
        _write_skill(Path(target), 'pdf', 'PDF manipulation skill.')
        return MagicMock()

    with patch('git.Repo.clone_from', side_effect=fake_clone_from) as mock_clone:
        registry = GitSkillsRegistry(repo_url='https://github.com/example/skills', target_dir=clone_dir)
        mock_clone.assert_not_called()

        assert library_names(registry.sync()) == ['pdf']
        mock_clone.assert_called_once()


def test_sync_pulls_an_existing_clone(fake_clone: Path) -> None:
    """A second sync refreshes the local copy rather than starting over."""
    mock_repo = MagicMock()

    with patch('git.Repo', return_value=mock_repo):
        _make_registry(fake_clone, auto_install=True).sync()

    mock_repo.remotes.origin.pull.assert_called_once()


def test_auto_install_false_never_reaches_the_network(fake_clone: Path) -> None:
    """Air-gapped deployments read only what is already on disk."""
    with patch('git.Repo.clone_from', side_effect=AssertionError('must not clone')):
        assert library_names(_make_registry(fake_clone).sync()) == ['pdf', 'xlsx']


def test_auto_install_false_reports_a_missing_clone(tmp_path: Path) -> None:
    """Silently returning nothing would look like a repository with no skills."""
    registry = _make_registry(tmp_path / 'never-cloned')

    with pytest.raises(ValueError, match='auto_install is disabled'):
        registry.sync()


def test_a_path_missing_from_the_repository_is_reported(fake_clone: Path) -> None:
    """The usual cause is a `path` that does not match the repository's layout."""
    registry = _make_registry(fake_clone, path='wrong-place')

    with pytest.raises(ValueError, match='does not exist in the repository'):
        registry.sync()


def test_sync_error_does_not_leak_the_token(tmp_path: Path) -> None:
    """An error message is one of the easiest places for a credential to escape."""
    registry = GitSkillsRegistry(
        repo_url='https://github.com/example/skills',
        target_dir=tmp_path / 'never-cloned',
        token='ghp_supersecret',
        auto_install=False,
    )

    with pytest.raises(ValueError) as exc_info:
        registry.sync()

    assert 'ghp_supersecret' not in str(exc_info.value)


def test_revision_reports_the_head_sha(fake_clone: Path) -> None:
    """Lets a caller record which commit of a moving branch a run used."""
    mock_repo = MagicMock()
    mock_repo.head.commit.hexsha = 'abc123'

    with patch('git.Repo', return_value=mock_repo):
        assert _make_registry(fake_clone).revision() == 'abc123'


def test_revision_is_none_when_not_a_repository(fake_clone: Path) -> None:
    """A directory that was never cloned has no revision to report."""
    import git

    with patch('git.Repo', side_effect=git.exc.InvalidGitRepositoryError):
        assert _make_registry(fake_clone).revision() is None


def test_composition_works_on_a_git_registry(fake_clone: Path) -> None:
    """Prefixing a remote source is the documented way to avoid name collisions."""
    registry = _make_registry(fake_clone).prefixed('vendor-')

    assert harness_names(registry.sync()) == ['vendor-pdf', 'vendor-xlsx']

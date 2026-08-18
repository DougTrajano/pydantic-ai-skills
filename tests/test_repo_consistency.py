"""Guard against drift between the files that declare which Pythons we support.

The supported-Python set is spelled out in five places that nothing links
together: the CI matrix, the package classifiers, ``requires-python``, the
SonarCloud properties, and the pyupgrade target. A change that updates one and
misses the others is silent -- CI stays green while the package advertises the
wrong versions, or pyupgrade emits syntax the floor interpreter cannot parse.
These tests make that a test failure instead.
"""

import re
from pathlib import Path

import pytest
import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 has no tomllib
    tomllib = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    tomllib is None,
    reason='tomllib is only available on Python 3.11+; these checks run on the rest of the matrix',
)

REPO_ROOT = Path(__file__).resolve().parent.parent

PYPROJECT = REPO_ROOT / 'pyproject.toml'
CI_WORKFLOW = REPO_ROOT / '.github' / 'workflows' / 'ci.yml'
SONAR_PROPERTIES = REPO_ROOT / 'sonar-project.properties'
PRE_COMMIT_CONFIG = REPO_ROOT / '.pre-commit-config.yaml'


def _version_tuple(version: str) -> tuple[int, ...]:
    """Turn a dotted version string into a sortable tuple of ints."""
    return tuple(int(part) for part in version.split('.'))


def _sorted_versions(versions: set[str]) -> list[str]:
    """Sort dotted version strings numerically rather than lexicographically."""
    return sorted(versions, key=_version_tuple)


@pytest.fixture(scope='module')
def pyproject() -> dict:
    """Parse pyproject.toml once for the whole module."""
    return tomllib.loads(PYPROJECT.read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def ci_matrix_versions() -> set[str]:
    """Python versions exercised by the ``test`` job matrix in CI."""
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding='utf-8'))
    versions = workflow['jobs']['test']['strategy']['matrix']['python-version']
    # The matrix quotes them ("3.10") so YAML keeps 3.10 distinct from 3.1.
    assert all(isinstance(version, str) for version in versions), (
        'Quote every python-version in the CI matrix, otherwise YAML parses 3.10 as the float 3.1.'
    )
    return set(versions)


@pytest.fixture(scope='module')
def classifier_versions(pyproject: dict) -> set[str]:
    """Python versions advertised by the ``Programming Language`` classifiers."""
    pattern = re.compile(r'^Programming Language :: Python :: (\d+\.\d+)$')
    matches = (pattern.match(classifier) for classifier in pyproject['project']['classifiers'])
    return {match.group(1) for match in matches if match}


@pytest.fixture(scope='module')
def sonar_versions() -> set[str]:
    """Python versions declared in sonar-project.properties."""
    text = SONAR_PROPERTIES.read_text(encoding='utf-8')
    match = re.search(r'^sonar\.python\.version=(.+)$', text, re.MULTILINE)
    assert match is not None, 'sonar-project.properties is missing sonar.python.version'
    return {version.strip() for version in match.group(1).split(',')}


def test_classifiers_match_ci_matrix(classifier_versions: set[str], ci_matrix_versions: set[str]) -> None:
    """Every Python CI tests is advertised in the classifiers, and vice versa."""
    assert _sorted_versions(classifier_versions) == _sorted_versions(ci_matrix_versions), (
        'pyproject.toml classifiers and the ci.yml test matrix disagree. '
        f'classifiers={_sorted_versions(classifier_versions)} matrix={_sorted_versions(ci_matrix_versions)}'
    )


def test_sonar_versions_match_ci_matrix(sonar_versions: set[str], ci_matrix_versions: set[str]) -> None:
    """SonarCloud analyses the same Python versions CI tests."""
    assert _sorted_versions(sonar_versions) == _sorted_versions(ci_matrix_versions), (
        'sonar-project.properties and the ci.yml test matrix disagree. '
        f'sonar={_sorted_versions(sonar_versions)} matrix={_sorted_versions(ci_matrix_versions)}'
    )


def test_requires_python_floor_matches_ci_matrix(pyproject: dict, ci_matrix_versions: set[str]) -> None:
    """``requires-python`` declares exactly the lowest version CI tests."""
    requires_python = pyproject['project']['requires-python']
    match = re.fullmatch(r'>=\s*(\d+\.\d+)', requires_python.strip())
    assert match is not None, f'Expected requires-python of the form ">=X.Y", got {requires_python!r}'

    lowest_tested = _sorted_versions(ci_matrix_versions)[0]
    assert match.group(1) == lowest_tested, (
        f'requires-python floor is {match.group(1)} but the lowest Python in the CI matrix is {lowest_tested}.'
    )


def test_ruff_target_version_matches_floor(pyproject: dict, ci_matrix_versions: set[str]) -> None:
    """Ruff targets the floor, so it flags syntax the oldest interpreter rejects."""
    target = pyproject['tool']['ruff']['target-version']
    expected = 'py' + _sorted_versions(ci_matrix_versions)[0].replace('.', '')
    assert target == expected, f'[tool.ruff] target-version is {target!r}, expected {expected!r} to match the floor.'


def test_pyupgrade_does_not_exceed_floor(ci_matrix_versions: set[str]) -> None:
    """Reject a pyupgrade target that could emit syntax the floor interpreter cannot parse."""
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding='utf-8'))
    args = [
        arg
        for repo in config['repos']
        for hook in repo['hooks']
        if hook['id'] == 'pyupgrade'
        for arg in hook.get('args', [])
    ]
    assert args, 'Could not find the pyupgrade hook args in .pre-commit-config.yaml'

    targets = [re.fullmatch(r'--py(\d)(\d+)-plus', arg) for arg in args]
    matched = [match for match in targets if match]
    assert matched, f'pyupgrade has no --pyXY-plus argument, got {args}'

    floor = _version_tuple(_sorted_versions(ci_matrix_versions)[0])
    for match in matched:
        target = (int(match.group(1)), int(match.group(2)))
        assert target <= floor, (
            f'pyupgrade targets {match.group(0)} but the lowest supported Python is '
            f'{".".join(str(part) for part in floor)}; it can emit syntax that version cannot parse.'
        )

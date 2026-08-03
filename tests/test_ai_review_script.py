"""Tests for `.github/scripts/submit_ai_review.py`.

The script is the only part of the AI review that writes to GitHub, and the
decisions it makes — which lines may carry an inline comment, what the verdict
is, how a malformed findings file is handled — are exactly the ones that must not
depend on a model's output being well formed.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / '.github' / 'scripts' / 'submit_ai_review.py'


def _load() -> ModuleType:
    """Import the script by path — it lives outside any importable package."""
    spec = importlib.util.spec_from_file_location('submit_ai_review', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


submit = _load()


PATCH = """\
diff --git a/pkg/mod.py b/pkg/mod.py
index 1111111..2222222 100644
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -10,6 +10,8 @@ def existing():
     context_one
     context_two
+added_at_12
+added_at_13
     context_three
-removed_line
+replacement_at_15
diff --git a/docs/page.md b/docs/page.md
--- a/docs/page.md
+++ b/docs/page.md
@@ -1 +1,2 @@
 title
+added_at_2
"""


def test_parse_patch_marks_only_added_lines() -> None:
    """Added lines are commentable; context and removed lines are not."""
    commentable = submit.parse_patch(PATCH)

    assert commentable['pkg/mod.py'] == {12, 13, 15}
    assert commentable['docs/page.md'] == {2}


def test_parse_patch_empty_input() -> None:
    """An empty diff yields no commentable lines rather than raising."""
    assert submit.parse_patch('') == {}


@pytest.mark.parametrize(
    'raw,expected',
    [
        ({'path': 'a.py', 'line': 3, 'severity': 'HIGH', 'comment': 'x'}, 'high'),
        ({'path': 'a.py', 'line': 3, 'severity': 'catastrophic', 'comment': 'x'}, 'medium'),
        ({'path': 'a.py', 'line': 3, 'comment': 'x'}, 'medium'),
    ],
)
def test_normalize_severity(raw: dict, expected: str) -> None:
    """Severity is lower-cased, and anything off-scale falls back to medium."""
    normalized = submit.normalize(raw)

    assert normalized is not None
    assert normalized['severity'] == expected


@pytest.mark.parametrize(
    'raw',
    [
        'not a dict',
        {'path': 'a.py', 'line': 3},  # no comment
        {'line': 3, 'comment': 'x'},  # no path
        {'path': '  ', 'comment': 'x'},
    ],
)
def test_normalize_rejects_unusable(raw: object) -> None:
    """A finding without a path or a comment cannot be posted, so it is dropped."""
    assert submit.normalize(raw) is None


def test_normalize_non_numeric_line() -> None:
    """A non-numeric line becomes 0, which routes the finding to the review body."""
    normalized = submit.normalize({'path': 'a.py', 'line': 'somewhere', 'comment': 'x'})

    assert normalized is not None
    assert normalized['line'] == 0


@pytest.mark.parametrize(
    'severities,expected',
    [
        ([], 'APPROVE'),
        (['low'], 'COMMENT'),
        (['medium', 'low'], 'COMMENT'),
        (['medium', 'high'], 'REQUEST_CHANGES'),
        (['critical'], 'REQUEST_CHANGES'),
    ],
)
def test_verdict_mapping(severities: list[str], expected: str) -> None:
    """Verdict follows the rubric: critical/high block, everything else comments."""
    findings = [{'path': 'a.py', 'line': 1, 'severity': s, 'comment': 'x'} for s in severities]

    assert submit.verdict_for(findings) == expected


def test_split_findings_moves_uncommentable_lines_to_the_body() -> None:
    """A finding on a line the diff does not touch would be rejected by GitHub."""
    findings = [
        {'path': 'pkg/mod.py', 'line': 12, 'severity': 'high', 'comment': 'on a changed line'},
        {'path': 'pkg/mod.py', 'line': 99, 'severity': 'high', 'comment': 'on an untouched line'},
        {'path': 'other.py', 'line': 1, 'severity': 'low', 'comment': 'in an unchanged file'},
    ]

    inline, body = submit.split_findings(findings, submit.parse_patch(PATCH))

    assert [f['comment'] for f in inline] == ['on a changed line']
    assert {f['comment'] for f in body} == {'on an untouched line', 'in an unchanged file'}


def test_split_findings_caps_inline_comments() -> None:
    """Beyond the cap the remaining findings go to the body, worst-first."""
    findings = [{'path': 'pkg/mod.py', 'line': 12, 'severity': 'high', 'comment': f'#{i}'} for i in range(5)]
    findings.append({'path': 'pkg/mod.py', 'line': 13, 'severity': 'critical', 'comment': 'worst'})

    inline, body = submit.split_findings(findings, submit.parse_patch(PATCH), max_comments=2)

    assert len(inline) == 2
    assert inline[0]['comment'] == 'worst'  # highest severity keeps its inline slot
    assert len(body) == 4


def test_build_payload_shape() -> None:
    """The payload matches what POST /pulls/{n}/reviews expects."""
    findings = [{'path': 'pkg/mod.py', 'line': 12, 'severity': 'high', 'comment': 'boom'}]

    payload = submit.build_payload('abc123', 'a note', findings, submit.parse_patch(PATCH))

    assert payload['commit_id'] == 'abc123'
    assert payload['event'] == 'REQUEST_CHANGES'
    assert payload['comments'] == [{'path': 'pkg/mod.py', 'line': 12, 'side': 'RIGHT', 'body': '**high** — boom'}]
    assert submit.MARKER in payload['body']
    assert 'Reviewed at `abc123`' in payload['body']
    assert 'a note' in payload['body']


def test_build_payload_with_no_findings_approves() -> None:
    """A clean review approves and says so."""
    payload = submit.build_payload('abc123', '', [], {})

    assert payload['event'] == 'APPROVE'
    assert payload['comments'] == []
    assert 'No findings.' in payload['body']


def test_load_findings_missing_file(tmp_path: Path) -> None:
    """An agent that crashed leaves no file — which is not the same as a clean review."""
    assert submit.load_findings(tmp_path / 'nope.json') is None


def test_load_findings_malformed_json(tmp_path: Path) -> None:
    """Invalid JSON is an unfinished review, not an exception and not an approval."""
    path = tmp_path / 'findings.json'
    path.write_text('{not json')

    assert submit.load_findings(path) is None


def test_load_findings_empty_findings_is_a_clean_review(tmp_path: Path) -> None:
    """The reviewer writes an empty list when it has nothing to say; that does post."""
    path = tmp_path / 'findings.json'
    path.write_text(json.dumps({'summary': '', 'findings': []}))

    assert submit.load_findings(path) == ('', [])


def test_main_posts_nothing_when_the_reviewer_did_not_finish(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No findings file means no review — never an approval nobody performed."""
    patch = tmp_path / 'pr.diff'
    patch.write_text(PATCH)

    exit_code = submit.main(
        [
            '--findings',
            str(tmp_path / 'missing.json'),
            '--patch',
            str(patch),
            '--repo',
            'owner/repo',
            '--pr',
            '1',
            '--commit',
            'deadbeef',
        ]
    )

    assert exit_code == 0
    assert 'Posting nothing' in capsys.readouterr().out


def test_load_findings_drops_unusable_entries(tmp_path: Path) -> None:
    """Well-formed entries survive alongside junk ones."""
    path = tmp_path / 'findings.json'
    path.write_text(
        json.dumps(
            {
                'summary': 'note',
                'findings': [
                    {'path': 'a.py', 'line': 1, 'severity': 'low', 'comment': 'keep'},
                    {'path': 'a.py'},
                    'garbage',
                ],
            }
        )
    )

    summary, findings = submit.load_findings(path)

    assert summary == 'note'
    assert [f['comment'] for f in findings] == ['keep']


def test_main_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--dry-run prints the payload and posts nothing."""
    findings = tmp_path / 'findings.json'
    findings.write_text(json.dumps({'summary': '', 'findings': []}))
    patch = tmp_path / 'pr.diff'
    patch.write_text(PATCH)

    exit_code = submit.main(
        [
            '--findings',
            str(findings),
            '--patch',
            str(patch),
            '--repo',
            'owner/repo',
            '--pr',
            '1',
            '--commit',
            'deadbeef',
            '--dry-run',
        ]
    )

    assert exit_code == 0
    assert '"event": "APPROVE"' in capsys.readouterr().out
